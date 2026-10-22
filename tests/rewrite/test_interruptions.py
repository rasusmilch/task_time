"""Bounded killed-child experiments at actual SQLite transaction boundaries.

These establish process-death recovery on the exercised filesystem, not power loss.
"""
from contextlib import contextmanager
from dataclasses import asdict, replace
import json
import os
import sqlite3
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Thread

import pytest

from chronicle.records import Request
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from conftest import NOW, uid


@contextmanager
def paused_child(code, *args):
    env = {**os.environ, 'PYTHONPATH': str(Path('src').resolve())}
    process = subprocess.Popen([sys.executable, '-B', '-c', code, *map(str, args)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env)
    lines = Queue()
    reader = Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
    reader.start()
    try:
        line = lines.get(timeout=10)
        assert line.strip() == 'BARRIER', (line, process.poll())
        yield process
    finally:
        if process.poll() is None:
            process.kill()  # Disposable child only; never a production recovery operation.
        out, err = process.communicate(timeout=10)
        reader.join(timeout=2)
        assert not reader.is_alive()
        assert not err, err


TRANSACTION_CHILD = r'''
import json, sys
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
from chronicle.records import Request
path, phase, encoded = sys.argv[1:]
a = json.loads(encoded); a['arguments'] = bytes.fromhex(a['arguments'])
request = Request(**a)
def barrier():
    print('BARRIER', flush=True)
    sys.stdin.readline()
store = SQLiteStore(path)
service = TimerService(store)
class Observed:
    def __init__(self, inner): self.inner = inner
    def __getattr__(self, name): return getattr(self.inner, name)
    def execute(self, sql, *args):
        if phase == 'commit_ready' and sql == 'COMMIT':
            from pathlib import Path
            assert Path(str(store.path) + '-journal').is_file()
            barrier()  # Journal written, immediately before SQLite's commit operation.
        result = self.inner.execute(sql, *args)
        if phase == 'committed' and sql == 'COMMIT':
            from pathlib import Path
            assert not Path(str(store.path) + '-journal').exists()
        facts = sql.startswith(('INSERT INTO work_', 'INSERT INTO active_', 'UPDATE active_', 'DELETE FROM active_'))
        if ((phase == 'begin' and sql == 'BEGIN IMMEDIATE') or
            (phase == 'facts' and facts) or
            (phase == 'receipt' and sql.startswith('INSERT INTO committed_requests')) or
            (phase == 'committed' and sql == 'COMMIT') or
            (phase == 'refresh' and sql.startswith('SELECT * FROM tasks ORDER'))):
            barrier()
        return result
store.connection = Observed(store.connection)
if phase == 'before': barrier()
result = service.execute(request)
assert result.status == 'committed', result
if phase == 'refresh': service.read_current_state(cutoff_utc_us=request.action_utc_us)
store.close()
'''


def frozen_json(request):
    value = asdict(request)
    value['arguments'] = request.arguments.hex()
    return json.dumps(value)


def rows(store):
    probe = store._probe()  # Independent committed state, including after a failed connection was retired.
    try:
        probe.execute('BEGIN')
        return {table: [tuple(row) for row in probe.execute(f'SELECT * FROM {table} ORDER BY 1,2')]
                for table in ('dataset_meta', 'tasks', 'projects', 'work_entries', 'work_revisions',
                              'active_timer', 'active_start_corrections', 'committed_requests')}
    finally:
        probe.close()


@pytest.mark.parametrize('operation', ['start_timer', 'stop_timer', 'switch_timer', 'correct_active_start'])
@pytest.mark.parametrize('phase', ['before', 'begin', 'facts', 'receipt', 'commit_ready', 'committed', 'refresh'])
def test_process_interruption_atomic_facts_and_exact_receipt(tmp_path, operation, phase):
    directory = tmp_path / 'interruption'
    store = SQLiteStore(directory, create=True, timezone='America/Chicago')
    service = TimerService(store)
    first, second, project, entry, next_entry = [uid() for _ in range(5)]
    assert service.create_project(project, 'P', request_id=uid(), action_utc_us=NOW).status == 'committed'
    for task in (first, second):
        assert service.create_task(task, 'Duplicate', project, request_id=uid(), action_utc_us=NOW).status == 'committed'
    if operation != 'start_timer':
        assert service.start_timer(first, entry, expected_task_version=1, request_id=uid(), action_utc_us=NOW).status == 'committed'
    args = {
        'start_timer': dict(task_id=first, entry_id=entry, expected_task_version=1),
        'stop_timer': dict(entry_id=entry, expected_version=1),
        'switch_timer': dict(expected_active_entry_id=entry, expected_active_version=1,
                             next_task_id=second, next_entry_id=next_entry, expected_task_version=1),
        'correct_active_start': dict(entry_id=entry, expected_version=1, date_text='2026-10-19',
                                    time_text='09:00', occurrence=None, comment='exact correction'),
    }[operation]
    frozen = Request.make(uid(), store.dataset_id, operation, NOW + 60_000_123, **args)
    before = rows(store)
    store.close()
    with paused_child(TRANSACTION_CHILD, directory, phase, frozen_json(frozen)) as process:
        process.kill()
    reopened = SQLiteStore(directory)
    try:
        service = TimerService(reopened)
        assert reopened.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert reopened.connection.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'
        committed = phase in ('committed', 'refresh')
        evidence = service.reconcile_request(frozen)
        assert evidence.status == ('committed' if committed else 'absent')
        if not committed:
            assert rows(reopened) == before  # Includes every identity, work fact and receipt.
        result = service.execute(frozen)
        assert result.status == 'committed'
        after = rows(reopened)
        assert len(after['committed_requests']) == len(before['committed_requests']) + 1
        assert after['tasks'] == before['tasks'] and after['projects'] == before['projects']
        active = service.read_current_state(cutoff_utc_us=frozen.action_utc_us)['active']
        if operation == 'start_timer':
            assert active['entry_id'] == entry and active['start_utc_us'] == frozen.action_utc_us
            assert not after['work_revisions']
        elif operation == 'stop_timer':
            assert active is None and len(after['work_revisions']) == 1
            assert after['work_revisions'][0][3:5] == (NOW, frozen.action_utc_us)
        elif operation == 'switch_timer':
            assert active['entry_id'] == next_entry and active['task_id'] == second
            assert active['start_utc_us'] == after['work_revisions'][0][4] == frozen.action_utc_us
            assert len(after['work_entries']) == 2 and len(after['work_revisions']) == 1
        else:
            assert active['entry_id'] == entry and active['version'] == 2
            assert len(after['active_start_corrections']) == 1 and not after['work_revisions']
            assert after['work_entries'] == before['work_entries']
        # Newer work must survive exact historical request reuse.
        assert service.rename_task(second, 'Newer', expected_version=1, request_id=uid(),
                                   action_utc_us=NOW + 100_000_000).status == 'committed'
        latest = rows(reopened)
        assert service.execute(frozen).result == result.result
        assert rows(reopened) == latest
        assert service.execute(replace(frozen, action_utc_us=frozen.action_utc_us + 1)).status == 'rejected'
        assert rows(reopened) == latest
    finally:
        reopened.close()


@pytest.mark.parametrize('phase', ['ordinary', 'reopen'])
def test_active_owner_crash_and_repeated_reopen(tmp_path, phase):
    directory = tmp_path / 'active'
    store = SQLiteStore(directory, create=True, timezone='America/Chicago')
    service = TimerService(store)
    task, entry = uid(), uid()
    service.create_task(task, 'Active', request_id=uid(), action_utc_us=NOW)
    service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=NOW)
    original = rows(store)
    store.close()
    code = r'''
from chronicle.sqlite_store import SQLiteStore
import sys
store = SQLiteStore(sys.argv[1])
if sys.argv[2] == 'ordinary':
    from chronicle.services import TimerService
    assert TimerService(store).read_current_state(cutoff_utc_us=int(sys.argv[3]))['active'] is not None
print('BARRIER', flush=True); sys.stdin.readline()
'''
    with paused_child(code, directory, phase, NOW):
        pass
    if phase == 'reopen':
        with paused_child(code, directory, phase, NOW):
            pass  # Another crash during reopening must not create a new Start.
    reopened = SQLiteStore(directory)
    try:
        assert rows(reopened) == original
        assert reopened.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert TimerService(reopened).read_current_state(cutoff_utc_us=NOW + 8 * 3_600_000_000)['report']['application']['today_us'] == 8 * 3_600_000_000
    finally:
        reopened.close()


@pytest.mark.parametrize('phase', ['profile', 'schema'])
def test_interrupted_initial_schema_is_not_overwritten(tmp_path, phase):
    directory = tmp_path / 'partial'
    code = r'''
from chronicle.sqlite_store import SQLiteStore
import chronicle.sqlite_store as module
import sys
if sys.argv[2] == 'profile':
    original = SQLiteStore._profile
    def pause(self):
        original(self)
        print('BARRIER', flush=True); sys.stdin.readline()
    SQLiteStore._profile = pause
else:
    original = module.schema_statements
    def statements():
        for index, statement in enumerate(original()):
            yield statement
            if index == 0:
                print('BARRIER', flush=True); sys.stdin.readline()
    module.schema_statements = statements
SQLiteStore(sys.argv[1], create=True, timezone='UTC')
'''
    with paused_child(code, directory, phase):
        pass
    before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    for create in (True, False):
        with pytest.raises((ValueError, sqlite3.DatabaseError)):
            SQLiteStore(directory, create=create, timezone='UTC' if create else None)
    assert all((directory / name).read_bytes() == data for name, data in before.items())
    assert {p.name for p in directory.iterdir()} == before.keys()


@pytest.mark.parametrize('committed', [False, True])
def test_interrupted_worker_shutdown_drains_accepted_request_truthfully(tmp_path, committed):
    directory = tmp_path / 'shutdown'
    store = SQLiteStore(directory, create=True, timezone='UTC')
    request = Request.make(uid(), store.dataset_id, 'create_task', NOW, task_id=uid(), name='Accepted', project_id=None)
    store.close()
    code = r'''
import sys,json
from chronicle.worker import DatabaseWorker,Message
from chronicle.services import TimerService
from chronicle.records import Request
args=json.loads(sys.argv[2]); args['arguments']=bytes.fromhex(args['arguments']); request=Request(**args)
original=TimerService.execute
class Observed:
    def __init__(self,inner): self.inner=inner
    def __getattr__(self,name): return getattr(self.inner,name)
    def execute(self,sql,*args):
        result=self.inner.execute(sql,*args)
        boundary = sql=='COMMIT' if sys.argv[3]=='True' else sql.startswith('INSERT INTO committed_requests')
        if boundary: print('BARRIER',flush=True); sys.stdin.readline()
        return result

def execute(self,request):
    self.store.connection=Observed(self.store.connection)
    return original(self,request)
TimerService.execute=execute
worker=DatabaseWorker(sys.argv[1]); worker.start()
assert worker.results.get(timeout=5).kind=='ready'
worker.requests.put(Message('mutate',1,request))
worker.requests.put(Message('shutdown'))
worker.join(timeout=10)
'''
    with paused_child(code, directory, frozen_json(request), committed):
        pass
    reopened = SQLiteStore(directory)
    try:
        assert TimerService(reopened).reconcile_request(request).status == ('committed' if committed else 'absent')
        assert len(rows(reopened)['tasks']) == int(committed)
        assert reopened.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        reopened.close()


@pytest.mark.parametrize('phase',['begin','facts','receipt','committed'])
def test_reminder_dismissal_process_death_never_confirms_or_partially_commits(tmp_path,phase):
    directory=tmp_path/'dismissal';store=SQLiteStore(directory,create=True,timezone='America/Chicago')
    request=Request.make(uid(),store.dataset_id,'dismiss_polr_reminder_today',NOW,local_date='2026-10-19')
    before=rows(store);store.close()
    code=TRANSACTION_CHILD.replace("facts = sql.startswith((", "facts = sql.startswith(('UPDATE dataset_meta', ")
    with paused_child(code,directory,phase,frozen_json(request)):pass
    reopened=SQLiteStore(directory)
    try:
        service=TimerService(reopened);committed=phase=='committed'
        assert service.reconcile_request(request).status==('committed' if committed else 'absent')
        assert reopened.dismissed_date(reopened.connection)==('2026-10-19' if committed else None)
        assert reopened.connection.execute('SELECT count(*) FROM polr_confirmation_batches').fetchone()[0]==0
        assert rows(reopened)['active_timer']==before['active_timer']
        assert reopened.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    finally:reopened.close()


FILE_CHILD=r'''
import sys
from chronicle.worker import DatabaseWorker,Message
from chronicle import backup_restore as br,timesheet_files as tf
from chronicle.sqlite_store import SQLiteStore
path,kind,phase,destination,export_id,request_id=sys.argv[1:]
def barrier():
 print('BARRIER',flush=True);sys.stdin.readline()
link=br.os.link;replace=br.os.replace
def publish(stage,target):
 if phase=='before':barrier()
 result=link(stage,target)
 if phase=='after':barrier()
 return result
def replacing(stage,target):
 if phase=='before':barrier()
 result=replace(stage,target)
 if phase=='after':barrier()
 return result
br.os.link=publish;br.os.replace=replacing
if kind=='backup' and phase=='progress':
 copy=br._copy
 def partial(source,stage):
  class Source:
   def backup(self,destination,**kw):
    def progress(status,remaining,total):
     if remaining:barrier()
    source.backup(destination,pages=1,progress=progress)
  copy(Source(),stage)
 br._copy=partial
if kind=='backup' and phase=='validation':
 verify=br.validate_image
 def validate(path):
  result=verify(path)
  if path.name.startswith('.chronicle-backup-'):barrier()
  return result
 br.validate_image=validate
worker=DatabaseWorker(path);worker.start();assert worker.results.get(timeout=5).kind=='ready'
if kind=='backup':worker.requests.put(Message('backup',1,dict(request_id=request_id,destination=destination)))
else:
 args=dict(export_id=export_id,destination=destination)
 if kind=='overwrite':
  from chronicle.timesheet_files import ContentConflict,metadata
  import hashlib
  from pathlib import Path
  p=Path(destination)
  args.update(confirmed_overwrite=True,expected_conflict=ContentConflict(str(p),metadata(p.lstat()),hashlib.sha256(p.read_bytes()).hexdigest()))
 worker.requests.put(Message('timesheet_publish',1,args))
worker.join(20)
'''


@pytest.mark.parametrize('kind,phase',[('backup','progress'),('backup','validation'),('backup','before'),('backup','after'),('report','before'),('report','after'),('overwrite','before'),('overwrite','after')])
def test_worker_file_process_death_protects_facts_and_never_rolls_back_published_output(tmp_path,kind,phase):
    from test_backup_restore import logical
    from test_timesheet_candidate import preview
    from test_manual_work import dated
    from chronicle.backup_restore import validate_image
    directory=tmp_path/'source';store=SQLiteStore(directory,create=True,timezone='America/Chicago');s=TimerService(store)
    task,active=uid(),uid();assert s.create_task(task,'Work',request_id=uid(),action_utc_us=NOW).status=='committed'
    dated(s,task);assert s.start_timer(task,active,expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    candidate=preview(s);assert s.register_timesheet_export(candidate,request_id=uid(),action_utc_us=NOW).status=='committed'
    before=logical(store.path);raw=store.path.read_bytes();store.close()
    destination=tmp_path/'external'
    if kind=='overwrite':destination.write_bytes(b'original conflicting file')
    with paused_child(FILE_CHILD,directory,kind,phase,destination,candidate.export_id,uid()):pass
    reopened=SQLiteStore(directory)
    try:
        assert logical(reopened.path)==before and reopened.path.read_bytes()==raw
        assert reopened.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert TimerService(reopened).read_current_state(cutoff_utc_us=NOW)['active']['entry_id']==active
    finally:reopened.close()
    if phase=='after':
        if kind=='backup':assert validate_image(destination).dataset_id==before['dataset_meta'][0][1]
        else:assert destination.read_bytes()==candidate.report_utf8
    elif kind=='overwrite':assert destination.read_bytes()==b'original conflicting file'
    else:assert not destination.exists()
    # A crashed child's stage is not automatically swept or declared verified.
    assert list(tmp_path.glob('.chronicle-*')) or phase=='after' and kind=='overwrite'
