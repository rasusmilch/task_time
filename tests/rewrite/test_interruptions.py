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
from chronicle.sqlite_store import SQLiteStore, EXPORT_TABLES, CONFIRMATION_TABLES
from conftest import NOW, uid
from test_backup_restore import rich, logical, cli
from test_worker import receive
from test_app import root, click, pump, Clock


SPILLED_TRANSACTION_CHILD = r'''
import sqlite3, sys
from pathlib import Path
path = Path(sys.argv[1]) / 'chronicle.sqlite3'
c = sqlite3.connect(path, isolation_level=None)
assert c.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete'
c.execute('PRAGMA synchronous=EXTRA')
c.execute('PRAGMA cache_size=1')
c.execute('PRAGMA cache_spill=ON')
c.execute('BEGIN IMMEDIATE')
if sys.argv[2] == 'header':
    c.execute('PRAGMA application_id=123')
    c.execute('PRAGMA user_version=99999')
c.execute("UPDATE tasks SET name=replace(name,'Original','Uncommitted'),version=version+1")
assert Path(str(path)+'-journal').is_file()
print('BARRIER', flush=True)
sys.stdin.readline()
'''


@pytest.fixture
def hot_dataset(store, service, rich):
    # Overflow pages force real main-file writes, not just a journal pathname.
    assert service.create_task(uid(), 'Original' * 12000, request_id=uid(),
                               action_utc_us=NOW).status == 'committed'
    before = logical(store.path)
    directory = store.directory
    store.close()
    return directory, before, rich


def leave_hot_journal(directory, *, header=False):
    path = directory / 'chronicle.sqlite3'
    before = path.read_bytes()
    with paused_child(SPILLED_TRANSACTION_CHILD, directory, 'header' if header else 'facts'):
        assert path.read_bytes() != before, 'Fixture did not spill dirty database pages'
    journal = Path(str(path) + '-journal')
    assert journal.read_bytes()[:8] == bytes.fromhex('d9d505f920a163d7')
    # SQLite may hold page 1 until COMMIT even though other pages spill. The
    # header variant tests rollback of pending markers, not universal page-1 spill.
    # Independent reproduction of the original startup failure mechanism.
    c = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None)
    try:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            c.execute('PRAGMA integrity_check').fetchall()
    finally:
        c.close()


@pytest.mark.parametrize('header', [False, True])
@pytest.mark.parametrize('owner', ['store', 'worker'])
def test_genuine_hot_journal_native_startup_preserves_all_committed_evidence(hot_dataset, header, owner):
    from chronicle import backup_restore as br
    from chronicle.worker import DatabaseWorker, Message
    from test_dataset_compatibility import preserved
    directory, before, rich = hot_dataset
    report = Path(rich['candidate'].preferred_destination)
    output = report.read_bytes()
    leave_hot_journal(directory, header=header)
    cold = preserved(directory, report)
    result = br.inspect_dataset(directory)
    assert result.classification == br.Compatibility.UNSAFE_OR_UNAVAILABLE
    assert not result.full_validation_completed
    assert preserved(directory, report) == cold
    result = cli('--inspect-dataset', directory)
    assert result.returncode == 4 and 'UNSAFE_OR_UNAVAILABLE' in result.stdout
    assert preserved(directory, report) == cold
    if owner == 'worker':
        worker = DatabaseWorker(directory)
        worker.start()
        try:
            first = worker.results.get(timeout=10)
            assert first.kind == 'ready', first.value
            assert first.value['runtime']['journal_mode'] == 'delete'
            worker.requests.put(Message('read', 1, NOW))
            assert receive(worker, 'read')['active']['entry_id'] == rich['active']
        finally:
            worker.requests.put(Message('shutdown'))
            worker.join(10)
            assert not worker.is_alive()
    recovered = SQLiteStore(directory)
    try:
        assert logical(recovered.path) == before
        assert recovered._profile_values() == {'journal_mode':'delete', 'synchronous':3, 'foreign_keys':1}
        assert list(recovered.connection.execute('PRAGMA foreign_key_check')) == []
        assert recovered.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert report.read_bytes() == output
        assert not Path(str(recovered.path) + '-journal').exists()
    finally:
        recovered.close()
    assert br.inspect_dataset(directory).ordinary_startup_permitted
    # Repeated reopen changes no evidence, and legitimate new work still commits.
    reopened = SQLiteStore(directory)
    try:
        assert logical(reopened.path) == before
        service = TimerService(reopened)
        request = Request.make(uid(), reopened.dataset_id, 'create_task', NOW,
                               task_id=uid(), name='After recovery', project_id=None)
        outcome = service.execute(request)
        assert outcome.status == 'committed'
        after = logical(reopened.path)
        assert service.execute(request).result == outcome.result
        assert service.execute(replace(request, action_utc_us=NOW+1)).status == 'rejected'
        assert logical(reopened.path) == after
        for table in ('work_entries','work_revisions','active_timer','active_start_corrections',
                      *EXPORT_TABLES, *CONFIRMATION_TABLES):
            assert after[table] == before[table]
    finally:
        reopened.close()


def test_hot_journal_cold_inspector_never_opens_sqlite_or_owns_session(hot_dataset, monkeypatch):
    from chronicle import backup_restore as br, bootstrap
    from chronicle.dataset_lock import DatasetLock
    from test_dataset_compatibility import preserved
    directory, _, _ = hot_dataset
    leave_hot_journal(directory)
    before = preserved(directory)
    def forbidden(*a, **kw):
        pytest.fail('Cold inspection entered application ownership/recovery')
    with monkeypatch.context() as m:
        m.setattr(DatasetLock, '__init__', forbidden)
        m.setattr(bootstrap.tk, 'Tk', forbidden)
        m.setattr(bootstrap.DatabaseWorker, '__init__', forbidden)
        m.setattr(br, '_readonly', forbidden)
        m.setattr(SQLiteStore, '_connect', forbidden)
        assert br.inspect_dataset(directory).classification == br.Compatibility.UNSAFE_OR_UNAVAILABLE
    assert preserved(directory) == before


def test_hot_journal_competing_owner_prevents_writable_recovery(hot_dataset, monkeypatch):
    from chronicle.backup_restore import metadata
    from chronicle.dataset_lock import DatasetLock
    from test_dataset_compatibility import preserved
    directory, _, _ = hot_dataset
    leave_hot_journal(directory)
    lock = DatasetLock(directory)
    before = preserved(directory)
    readable_before = {name: value for name, value in before[1].items() if name != lock.path.name}
    def readable_files():
        # Preserve all database/journal bytes and metadata, but do not read the
        # byte Windows locks in .chronicle.lock through a competing handle.
        return {p.name: (metadata(p.lstat()), p.read_bytes())
                for p in directory.iterdir() if p != lock.path}
    lock.acquire()
    def forbidden(*a):
        pytest.fail('Competing owner reached writable SQLite recovery')
    try:
        monkeypatch.setattr(SQLiteStore, '_connect', forbidden)
        with pytest.raises(OSError):
            SQLiteStore(directory)
        assert lock.file is not None and not lock.file.closed
        contender = DatasetLock(directory)
        try:
            with pytest.raises(OSError): contender.acquire()
            assert contender.file is None
        finally:
            contender.close()
        assert metadata(directory.lstat()) == before[0][0]
        assert metadata(lock.path.lstat()) == before[1][lock.path.name][0]
        assert readable_files() == readable_before
    finally:
        lock.close()
    assert lock.file is None
    assert preserved(directory) == before
    next_owner = DatasetLock(directory)
    try:
        next_owner.acquire()
        assert next_owner.file is not None
        assert readable_files() == readable_before
    finally:
        next_owner.close()
    assert next_owner.file is None
    assert preserved(directory) == before


def test_hot_journal_admission_does_not_treat_raw_header_markers_as_committed(hot_dataset, monkeypatch):
    import chronicle.sqlite_store as module
    directory, before, _ = hot_dataset
    leave_hot_journal(directory)
    original = module.os.read
    observations = []
    def header_observation(fd, size):
        value = original(fd, size)
        if size == 100 and value.startswith(b'SQLite format 3\x00'):
            # Inject only the bounded admission observation. Real recovery and
            # all authoritative SQLite validation still execute on the real file.
            raw = bytearray(value)
            raw[60:64] = (99999).to_bytes(4, 'big')
            raw[68:72] = (123).to_bytes(4, 'big')
            observations.append(1)
            return bytes(raw)
        return value
    with monkeypatch.context() as m:
        m.setattr(module.os, 'read', header_observation)
        recovered = SQLiteStore(directory)
        try:
            assert logical(recovered.path) == before
        finally:
            recovered.close()
    assert observations


@pytest.mark.parametrize('gate', ['validation', 'profile'])
def test_hot_journal_worker_ready_waits_for_owned_full_validation_and_profile(hot_dataset, monkeypatch, gate):
    from queue import Empty
    from threading import Event, get_ident
    import chronicle.worker as module
    from chronicle.dataset_lock import DatasetLock
    directory, before, _ = hot_dataset
    leave_hot_journal(directory)
    entered, release = Event(), Event()
    calls = []
    def pause(phase):
        calls.append((phase, get_ident()))
        if phase == gate:
            entered.set()
            assert release.wait(10), 'Test did not release startup gate'
    class Observed(SQLiteStore):
        @classmethod
        def _verify_complete(cls, c):
            pause('validation')
            super()._verify_complete(c)
        def _profile(self):
            pause('profile')
            super()._profile()
    monkeypatch.setattr(module, 'SQLiteStore', Observed)
    worker = module.DatabaseWorker(directory)
    worker.start()
    try:
        assert entered.wait(10)
        with pytest.raises(Empty): worker.results.get_nowait()
        contender = DatasetLock(directory)
        with pytest.raises(OSError): contender.acquire()
        release.set()
        assert worker.results.get(timeout=10).kind == 'ready'
        assert calls == [('validation', worker.ident), ('profile', worker.ident)]
        assert logical(directory/'chronicle.sqlite3') == before
    finally:
        release.set()
        worker.requests.put(module.Message('shutdown'))
        worker.join(10)
        assert not worker.is_alive()


@pytest.mark.parametrize('kind', ['newer', 'foreign', 'trigger', 'receipt', 'export', 'current', 'timezone'])
def test_hot_journal_recovery_does_not_adopt_invalid_committed_state(hot_dataset, monkeypatch, kind):
    from test_dataset_compatibility import damage
    directory, _, _ = hot_dataset
    damage(directory, kind)
    committed = logical(directory/'chronicle.sqlite3')
    leave_hot_journal(directory)
    def forbidden(*a): pytest.fail('Invalid recovered state reached runtime configuration')
    monkeypatch.setattr(SQLiteStore, '_profile', forbidden)
    with pytest.raises((ValueError, KeyError, sqlite3.Error)):
        SQLiteStore(directory)
    # SQLite may have physically rolled back the journal; Chronicle wrote no facts.
    assert logical(directory/'chronicle.sqlite3') == committed
    from chronicle.worker import DatabaseWorker
    worker = DatabaseWorker(directory)
    worker.start()
    try:
        assert worker.results.get(timeout=10).kind == 'startup_failed'
        assert worker.results.get(timeout=10).kind == 'stopped'
    finally:
        worker.join(10)
        assert not worker.is_alive()
    assert logical(directory/'chronicle.sqlite3') == committed


@pytest.mark.parametrize('fault', ['admission', 'lock', 'open', 'recovery', 'validation', 'profile'])
def test_hot_journal_startup_faults_preserve_primary_and_never_publish_ready(hot_dataset, monkeypatch, fault):
    import chronicle.worker as module
    from chronicle.dataset_lock import DatasetLock
    from test_dataset_compatibility import preserved
    directory, before, _ = hot_dataset
    leave_hot_journal(directory)
    cold = preserved(directory)
    primary = sqlite3.OperationalError(f'{fault} boundary failed')
    def fail(*a, **kw): raise primary
    class RecoveryFault:
        def __init__(self, c): self.inner = c
        def __getattr__(self, name): return getattr(self.inner, name)
        def execute(self, sql, *args):
            if sql == 'PRAGMA integrity_check': raise primary
            return self.inner.execute(sql, *args)
    if fault == 'lock': monkeypatch.setattr(DatasetLock, 'acquire', fail)
    class Failed(SQLiteStore):
        def _admit_existing(self):
            if fault == 'admission': raise primary
            return super()._admit_existing()
        def _connect(self):
            if fault == 'open': raise primary
            c = super()._connect()
            return RecoveryFault(c) if fault == 'recovery' else c
        @classmethod
        def _verify_complete(cls, c):
            super()._verify_complete(c)
            if fault == 'validation': raise primary
        def _profile(self):
            if fault == 'profile': raise primary
            super()._profile()
    monkeypatch.setattr(module, 'SQLiteStore', Failed)
    worker = module.DatabaseWorker(directory)
    worker.start()
    try:
        message = worker.results.get(timeout=10)
        assert message.kind == 'startup_failed' and message.value is primary
        assert worker.results.get(timeout=10).kind == 'stopped'
    finally:
        worker.join(10)
        assert not worker.is_alive()
    if fault in ('admission', 'lock', 'open', 'recovery'):
        assert preserved(directory) == cold
    else:
        assert logical(directory/'chronicle.sqlite3') == before


@pytest.mark.parametrize('cleanup', ['connection', 'lock'])
def test_hot_recovery_failed_close_retains_lock_for_worker_cleanup_retry(hot_dataset, monkeypatch, cleanup):
    import chronicle.worker as module
    from chronicle.dataset_lock import DatasetLock
    directory, before, _ = hot_dataset
    leave_hot_journal(directory)
    primary = ValueError('Post-recovery validation fault')
    attempts = []
    def fail_close():
        attempts.append(1)
        if len(attempts) < 3: raise OSError('Cleanup still uncertain')
    class CloseFault:
        def __init__(self, c): self.inner = c
        def __getattr__(self, name): return getattr(self.inner, name)
        def close(self):
            fail_close()
            self.inner.close()
    class Failed(SQLiteStore):
        def _connect(self):
            c = super()._connect()
            return CloseFault(c) if cleanup == 'connection' else c
        @classmethod
        def _verify_complete(cls, c):
            super()._verify_complete(c)
            raise primary
    close = DatasetLock.close
    def lock_close(self):
        if self.path.parent == directory: fail_close()
        close(self)
    if cleanup == 'lock': monkeypatch.setattr(DatasetLock, 'close', lock_close)
    monkeypatch.setattr(module, 'SQLiteStore', Failed)
    worker = module.DatabaseWorker(directory)
    worker.start()
    try:
        message = worker.results.get(timeout=10)
        assert message.kind == 'startup_failed' and message.value is primary
        assert 'Cleanup still uncertain' in '\n'.join(primary.__notes__)
        assert worker.results.get(timeout=10).kind == 'shutdown_failed'
        assert worker.is_alive()
        with pytest.raises(OSError): DatasetLock(directory).acquire()
        worker.requests.put(module.Message('shutdown'))
        assert worker.results.get(timeout=10).kind == 'stopped'
    finally:
        worker.requests.put(module.Message('shutdown'))
        worker.join(10)
        assert not worker.is_alive()
    assert len(attempts) == 3 and logical(directory/'chronicle.sqlite3') == before
    with monkeypatch.context() as m:
        m.setattr(DatasetLock, 'close', close)
        lock = DatasetLock(directory)
        lock.acquire()
        lock.close()


def test_real_tk_hot_journal_worker_startup_and_ordinary_timer_close_reopen(hot_dataset, root, click):
    from chronicle.app import ChronicleApp
    from chronicle.worker import DatabaseWorker
    from chronicle import backup_restore as br
    from test_timesheet_save_ui import exit_settled
    directory, before, rich = hot_dataset
    leave_hot_journal(directory)
    worker = DatabaseWorker(directory)
    app = ChronicleApp(root, worker, now_utc=Clock())
    worker.start()
    try:
        pump(root, lambda: app.ready and app.state.get('report') is not None)
        assert app.state['active']['entry_id'] == rich['active']
        assert logical(directory/'chronicle.sqlite3') == before
        assert not any('upgrade' in label.lower() for label in app.buttons)
        click(app.buttons['Stop'])
        pump(root, lambda: app.pending is None and app.state['active'] is None)
        app.request_close()
        exit_settled(app)
    finally:
        if app.alive: root.destroy()
        worker.join(10)
        assert not worker.is_alive()
    assert not root.test_errors
    assert br.inspect_dataset(directory).ordinary_startup_permitted
    reopened = SQLiteStore(directory)
    try:
        assert TimerService(reopened).read_current_state(cutoff_utc_us=NOW)['active'] is None
        after = logical(reopened.path)
        for table in (*EXPORT_TABLES, *CONFIRMATION_TABLES):
            assert after[table] == before[table]
    finally:
        reopened.close()


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
