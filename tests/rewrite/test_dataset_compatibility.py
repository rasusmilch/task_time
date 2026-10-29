"""Cold inspection diagnostics and refusal; unsupported markers are not new schemas."""
from dataclasses import FrozenInstanceError,asdict
import os
from pathlib import Path
import sqlite3

import pytest

from chronicle import backup_restore as br
from chronicle.sqlite_store import APPLICATION_ID,DATABASE,SCHEMA_VERSION,SQLiteStore
from chronicle.services import TimerService
from chronicle.worker import DatabaseWorker
from conftest import NOW,uid
from test_backup_restore import rich,logical,cli,symlink
from test_manual_work import dated
from test_worker import receive
from test_app import root,click,pump,Clock

C=br.Compatibility


def preserved(directory,*extras):
    """Bytes, identities and modification metadata, deliberately excluding atime."""
    def observe(p):
        value=p.lstat();data=p.read_bytes() if p.is_file() and not p.is_symlink() else os.readlink(p) if p.is_symlink() else None
        return br.metadata(value),data
    return observe(directory),{p.name:observe(p) for p in directory.iterdir()},[observe(p) for p in extras]


@pytest.fixture
def image(store,rich,tmp_path):
    directory=tmp_path/'candidate';directory.mkdir()
    assert store.backup(directory/DATABASE).verified
    return directory


def damage(directory,kind):
    """Test-only unsupported/corrupt copies; never a supported version-2 target."""
    path=directory/DATABASE;c=sqlite3.connect(path,isolation_level=None)
    try:
        if kind in ('older','newer','future','corrupt_lower'):
            c.execute(f"PRAGMA user_version={0 if kind in ('older','corrupt_lower') else 2 if kind=='newer' else 99999}")
        elif kind=='foreign':c.execute('PRAGMA application_id=123')
        elif kind=='missing_table':c.execute('DROP TABLE projects')
        elif kind=='table_definition':c.execute('ALTER TABLE tasks ADD COLUMN not_supported TEXT')
        elif kind=='trigger':c.execute('DROP TRIGGER immutable_work_revisions_update')
        elif kind=='extra':c.execute('CREATE INDEX unexpected ON tasks(name)')
        elif kind=='timezone':c.execute("UPDATE dataset_meta SET timezone='Not/AZone'")
        elif kind=='reminder':c.execute("UPDATE dataset_meta SET polr_reminder_dismissed_local_date='2026-02-30'")
        elif kind=='current':c.execute('DELETE FROM polr_confirmed_current')
        elif kind=='wal':assert c.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
        elif kind in ('revision','association','export','receipt'):
            table={'revision':'work_revisions','association':'work_revisions','export':'timesheet_exports','receipt':'committed_requests'}[kind]
            guards=list(c.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",(table,)))
            for name,sql in guards:c.execute(f'DROP TRIGGER {name}')
            if kind=='revision':c.execute('UPDATE work_revisions SET request_id=? WHERE revision=2',(uid(),))
            elif kind=='association':c.execute('UPDATE work_revisions SET request_id=(SELECT request_id FROM committed_requests ORDER BY commit_seq LIMIT 1) WHERE revision=2')
            elif kind=='export':c.execute("UPDATE timesheet_exports SET report_sha256=?",('0'*64,))
            else:c.execute("UPDATE committed_requests SET request_bytes=x'7b7d' WHERE commit_seq=1")
            for name,sql in guards:c.execute(sql)
    finally:c.close()
    if kind=='header':path.write_bytes(b'Not a SQLite database')
    if kind in ('truncated','corrupt_lower'):
        raw=path.read_bytes();path.write_bytes(raw[:len(raw)//2])


CASES=[('supported',C.SUPPORTED_CURRENT,0),('older',C.OLDER_UNSUPPORTED,2),
       ('newer',C.NEWER_UNSUPPORTED,2),('future',C.NEWER_UNSUPPORTED,2),
       ('foreign',C.FOREIGN_DATABASE,3),('missing_table',C.UNSUPPORTED_LAYOUT,3),
       ('table_definition',C.UNSUPPORTED_LAYOUT,3),('trigger',C.UNSUPPORTED_LAYOUT,3),('extra',C.UNSUPPORTED_LAYOUT,3),
       *[(k,C.UNSAFE_OR_UNAVAILABLE,4) for k in ('timezone','reminder','current','revision','association','export','receipt','header','truncated','corrupt_lower')],
       ('wal',C.UNSUPPORTED_PROFILE,3)]


@pytest.mark.parametrize('kind,classification,status',CASES)
def test_real_images_classify_and_preserve_source_and_external_evidence(image,rich,store,kind,classification,status):
    damage(image,kind)
    report=Path(rich['candidate'].preferred_destination)
    before=preserved(image,report,store.path)
    result=br.inspect_dataset(image)
    assert result.classification==classification and result.exit_status==status
    assert result.candidate_path==image/DATABASE and result.supported_schema_version==1
    assert result.full_validation_completed==(kind=='supported')
    assert result.ordinary_startup_permitted==(kind=='supported')
    assert preserved(image,report,store.path)==before
    assert not (image/'.chronicle.lock').exists()
    if kind in ('older','newer','future'):
        assert result.observed_application_id==APPLICATION_ID
        assert result.observed_user_version=={'older':0,'newer':2,'future':99999}[kind]
        assert 'migration' in result.explanation
    if kind=='supported':
        assert result.error is None and result.observed_journal_profile=='delete'
        with pytest.raises(FrozenInstanceError):result.explanation='changed'
        assert all(not isinstance(v,(sqlite3.Connection,sqlite3.Cursor)) for v in asdict(result).values())
    if kind=='corrupt_lower':assert result.observed_user_version is None


@pytest.mark.parametrize('kind,classification,status',CASES)
def test_source_launcher_headless_status_and_no_state_writes(image,kind,classification,status):
    damage(image,kind);before=preserved(image)
    result=cli('--inspect-dataset',image)
    assert result.returncode==status,(result.stdout,result.stderr)
    assert classification.value in result.stdout and 'No upgrade was performed.' in result.stdout
    assert ('startup: permitted' in result.stdout)==(kind=='supported')
    assert 'Example' not in result.stdout and 'TclError' not in result.stderr
    assert preserved(image)==before


@pytest.mark.parametrize('kind',['older','newer','future','foreign','missing_table','table_definition','trigger','extra','timezone','reminder','current','revision','association','export','receipt','header','truncated','corrupt_lower','wal'])
def test_startup_backup_and_restore_refuse_before_adoption_or_target_reservation(image,kind,tmp_path):
    damage(image,kind);before=preserved(image);target=tmp_path/'not-reserved'
    for action in (lambda:SQLiteStore(image),lambda:br.validate_image(image/DATABASE),lambda:br.restore_image(image/DATABASE,target)):
        with pytest.raises((ValueError,sqlite3.Error,KeyError)):action()
        assert preserved(image)==before and not target.exists()
    worker=DatabaseWorker(image);worker.start()
    try:
        assert worker.results.get(timeout=5).kind=='startup_failed'
        receive(worker,'stopped')
    finally:worker.join(5);assert not worker.is_alive()
    assert preserved(image)==before


@pytest.mark.parametrize('args',[
 ['--inspect-dataset','missing','--verify-backup','missing'],
 ['--inspect-dataset','missing','--restore-from','missing'],
 ['--inspect-dataset','missing','--create'],
 ['--inspect-dataset','missing','--timezone','UTC'],
 ['--inspect-dataset','missing','--data-dir','unused'],
 ['--inspect-dataset'],
])
def test_cli_invalid_combinations_cannot_start_or_create(args,tmp_path):
    result=cli(*args);assert result.returncode==2 and 'TclError' not in result.stderr
    assert not list(tmp_path.iterdir())


def test_headless_inspection_constructs_no_tk_app_worker_or_lock(image,monkeypatch):
    from chronicle import bootstrap
    def forbidden(*a,**k):pytest.fail('Read-only inspection attempted application/lock construction')
    monkeypatch.setattr(bootstrap.tk,'Tk',forbidden)
    monkeypatch.setattr(bootstrap,'ChronicleApp',forbidden)
    monkeypatch.setattr(bootstrap,'DatabaseWorker',forbidden)
    monkeypatch.setattr(br.DatasetLock,'acquire',forbidden)
    before=preserved(image);assert bootstrap.main(['--inspect-dataset',str(image)]).exit_status==0
    assert preserved(image)==before


@pytest.mark.parametrize('kind',['missing','file','directory_alias','ancestor_alias','database_link','dangling','database_directory','fifo','unreadable'])
def test_unsafe_paths_never_open_sqlite_or_change_objects(image,tmp_path,monkeypatch,kind):
    directory=image;path=image/DATABASE
    if kind=='missing':directory=tmp_path/'missing'
    elif kind=='file':directory=path
    elif kind=='directory_alias':directory=tmp_path/'alias';symlink(image,directory,True)
    elif kind=='ancestor_alias':
        alias=tmp_path/'alias';symlink(tmp_path,alias,True);directory=alias/image.name
    elif kind in ('database_link','dangling'):
        original=tmp_path/'original';path.rename(original);symlink(original if kind=='database_link' else tmp_path/'absent',path)
    elif kind=='database_directory':path.unlink();path.mkdir()
    elif kind=='fifo':
        if not hasattr(os,'mkfifo'):pytest.skip('Native FIFO API unavailable')
        path.unlink()
        try:os.mkfifo(path)
        except OSError as exc:
            if exc.errno not in (1,13,38,95):raise
            pytest.skip(f'Native FIFO creation unavailable: {exc}')
    elif kind=='unreadable':
        if os.name!='posix' or os.geteuid()==0:pytest.skip('Native POSIX read permission enforcement unavailable')
        path.chmod(0)
    def forbidden(*a):pytest.fail('Unsafe path reached SQLite connection creation')
    monkeypatch.setattr(br,'_readonly',forbidden)
    # Do not read an intentionally unreadable fixture as part of its snapshot.
    if kind=='unreadable':before=br.metadata(path.lstat())
    else:before=preserved(image)
    try:
        result=br.inspect_dataset(directory)
        assert result.classification==C.UNSAFE_OR_UNAVAILABLE and not result.ordinary_startup_permitted
        assert (br.metadata(path.lstat()) if kind=='unreadable' else preserved(image))==before
    finally:
        if kind=='unreadable':path.chmod(0o600)  # Explicit test-fixture cleanup, never runtime behavior.


@pytest.mark.parametrize('value',[None,True,42,'','   ','bad\x00path','//server/share','\\\\server\\share'])
def test_invalid_or_network_path_is_not_resolved_or_created(value,monkeypatch):
    def forbidden(*a):pytest.fail('Invalid path reached filesystem inspection')
    monkeypatch.setattr(br,'_cold_directory',forbidden)
    assert br.inspect_dataset(value).classification==C.UNSAFE_OR_UNAVAILABLE


@pytest.mark.parametrize('suffix',['-journal','-wal','-shm'])
def test_outstanding_sidecar_is_retained_and_not_recovered(image,suffix,monkeypatch):
    (image/(DATABASE+suffix)).write_bytes(b'unverified journal state')
    before=preserved(image)
    def forbidden(*a):pytest.fail('Cold inspector must not enter SQLite recovery')
    monkeypatch.setattr(br,'_readonly',forbidden)
    result=br.inspect_dataset(image)
    assert result.classification==C.UNSAFE_OR_UNAVAILABLE and 'clean cold' in result.explanation
    assert preserved(image)==before


def test_wal_header_refuses_before_sqlite_connection_and_keeps_directory(image,monkeypatch):
    damage(image,'wal');before=preserved(image)
    def forbidden(*a,**kw):pytest.fail('WAL candidate reached SQLite open')
    monkeypatch.setattr(br,'_readonly',forbidden)
    monkeypatch.setattr(SQLiteStore,'_probe',forbidden)
    assert br.inspect_dataset(image).classification==C.UNSUPPORTED_PROFILE
    with pytest.raises(br.UnsupportedImageProfile):SQLiteStore(image)
    assert preserved(image)==before


@pytest.mark.parametrize('fault',['path','fingerprint','open','identity','version','integrity','schema','work','export','confirmation','receipt','close','stability'])
def test_original_faults_never_claim_completion_or_mutate(image,monkeypatch,fault):
    primary=OSError(f'{fault} unavailable');before=preserved(image);connections=[];fingerprint=br._fingerprint
    def fail(*a,**kw):raise primary
    if fault=='path':monkeypatch.setattr(br,'_cold_directory',fail)
    elif fault=='fingerprint':monkeypatch.setattr(br,'_fingerprint',fail)
    elif fault=='open':monkeypatch.setattr(br,'_readonly',fail)
    elif fault=='stability':
        calls=[]
        def changed(path):
            calls.append(path)
            if len(calls)>1:raise primary
            return fingerprint(path)
        monkeypatch.setattr(br,'_fingerprint',changed)
    elif fault in ('schema','work','export','confirmation','receipt'):
        method={'schema':'_verify_schema','work':'assert_lifecycle','export':'read_export','confirmation':'assert_confirmations','receipt':'verify_receipts'}[fault]
        monkeypatch.setattr(SQLiteStore,method,staticmethod(fail))
    else:
        readonly=br._readonly
        class Connection:
            def __init__(self,c):self.inner=c
            def __getattr__(self,n):return getattr(self.inner,n)
            def execute(self,sql,*args):
                if (fault=='identity' and sql=='PRAGMA application_id' or fault=='version' and sql=='PRAGMA user_version' or fault=='integrity' and sql=='PRAGMA integrity_check'):raise primary
                return self.inner.execute(sql,*args)
            def close(self):
                if fault=='close':raise primary
                return self.inner.close()
        def opened(path):
            result=Connection(readonly(path));connections.append(result);return result
        monkeypatch.setattr(br,'_readonly',opened)
    try:
        result=br.inspect_dataset(image)
        assert result.classification==C.UNSAFE_OR_UNAVAILABLE and result.error is primary
        assert not result.full_validation_completed and not result.ordinary_startup_permitted
        assert result.error.__traceback__ is not None and len(connections)<=1
        assert preserved(image)==before
    finally:
        for c in connections:c.inner.close()  # The test owns injected failed-close handles.


def test_primary_validation_error_survives_failed_readonly_close_without_retry(image,monkeypatch):
    primary,secondary=ValueError('original evidence failure'),OSError('read-only close unavailable')
    readonly=br._readonly;connections=[];before=preserved(image)
    class Connection:
        def __init__(self,c):self.inner=c
        def __getattr__(self,n):return getattr(self.inner,n)
        def close(self):raise secondary
    def opened(path):
        result=Connection(readonly(path));connections.append(result);return result
    def fail(c):raise primary
    monkeypatch.setattr(br,'_readonly',opened);monkeypatch.setattr(SQLiteStore,'_verify_complete',staticmethod(fail))
    try:
        result=br.inspect_dataset(image)
        assert result.error is primary and len(connections)==1 and not result.full_validation_completed
        assert any('read-only close unavailable' in n for n in primary.__notes__)
        assert preserved(image)==before
    finally:connections[0].inner.close()


@pytest.mark.parametrize('change',['contents','directory','sidecar','profile'])
def test_change_during_inspection_rejects_without_cleaning_changed_source(image,tmp_path,monkeypatch,change):
    readonly=br._readonly;changed=[]
    class Connection:
        def __init__(self,c):self.inner=c
        def __getattr__(self,n):return getattr(self.inner,n)
        def close(self):
            self.inner.close()
            if change=='contents':
                with (image/DATABASE).open('ab') as f:f.write(b'explicit test mutation')
            elif change=='directory':
                old=tmp_path/'moved';image.rename(old);image.mkdir();os.link(old/DATABASE,image/DATABASE)
            elif change=='profile':
                c=sqlite3.connect(image/DATABASE)
                try:assert c.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
                finally:c.close()
            else:(image/(DATABASE+'-journal')).write_bytes(b'explicit test journal')
            changed.append(preserved(image))
    monkeypatch.setattr(br,'_readonly',lambda p:Connection(readonly(p)))
    result=br.inspect_dataset(image)
    assert result.classification==C.UNSAFE_OR_UNAVAILABLE and result.observed_user_version is None
    assert len(changed)==1 and preserved(image)==changed[0]


def test_inspection_uses_one_readonly_query_only_connection_and_full_gate(image,monkeypatch):
    readonly=br._readonly;complete=SQLiteStore._verify_complete;seen=[]
    def opened(path):
        c=readonly(path);seen.append(c)
        assert c.execute('PRAGMA query_only').fetchone()[0]==1
        with pytest.raises(sqlite3.OperationalError):c.execute('UPDATE dataset_meta SET week_start=3')
        return c
    calls=[]
    def checked(c):calls.append(c);return complete(c)
    monkeypatch.setattr(br,'_readonly',opened);monkeypatch.setattr(SQLiteStore,'_verify_complete',staticmethod(checked))
    before=preserved(image);result=br.inspect_dataset(image)
    assert result.ordinary_startup_permitted and calls==seen and len(seen)==1
    with pytest.raises(sqlite3.ProgrammingError):seen[0].execute('SELECT 1')
    assert preserved(image)==before


def test_cli_reporting_failure_is_nonzero_and_retains_original_diagnostic(image,monkeypatch,capsys):
    from chronicle import bootstrap
    primary=OSError('output unavailable')
    def fail(*a):raise primary
    monkeypatch.setattr(bootstrap,'_present_inspection',fail);before=preserved(image)
    with pytest.raises(SystemExit) as exit:bootstrap.main(['--inspect-dataset',str(image)])
    out=capsys.readouterr();assert exit.value.code==4 and 'output unavailable' in out.err
    assert 'SUPPORTED_CURRENT' not in out.out and preserved(image)==before


@pytest.mark.parametrize('argument',['','   ','missing-dataset'])
def test_cli_unsuitable_explicit_path_fails_without_creation(argument):
    result=cli('--inspect-dataset',argument)
    assert result.returncode==4 and 'UNSAFE_OR_UNAVAILABLE' in result.stdout and 'TclError' not in result.stderr


INSPECTION_CHILD=r'''
import runpy,sys
from chronicle import backup_restore as br,bootstrap
from chronicle.sqlite_store import SQLiteStore
path,phase=sys.argv[1:]
def barrier():
 print('BARRIER',flush=True);sys.stdin.readline()
original=br._fingerprint;seen=[]
def fingerprint(path):
 result=original(path);seen.append(path)
 if phase=='fingerprint' and len(seen)==1:barrier()
 return result
br._fingerprint=fingerprint
readonly=br._readonly
class Observed:
 def __init__(self,c):self.inner=c
 def __getattr__(self,n):return getattr(self.inner,n)
 def execute(self,sql,*a):
  result=self.inner.execute(sql,*a)
  if phase=='identity' and sql=='PRAGMA user_version' or phase=='integrity' and sql=='PRAGMA integrity_check':barrier()
  return result
def opened(path):
 result=Observed(readonly(path))
 if phase=='open':barrier()
 return result
br._readonly=opened
present=bootstrap._present_inspection
def presenting(result):
 if phase=='reporting':barrier()
 return present(result)
bootstrap._present_inspection=presenting
sys.argv=['run_chronicle.py','--inspect-dataset',path]
runpy.run_path('run_chronicle.py',run_name='__main__')
'''


@pytest.mark.parametrize('phase',['fingerprint','open','identity','integrity','reporting'])
def test_killed_inspection_leaves_no_transformation_and_next_owner_works(image,phase):
    from test_interruptions import paused_child
    before=preserved(image);facts=logical(image/DATABASE)
    with paused_child(INSPECTION_CHILD,image,phase):pass
    assert preserved(image)==before and logical(image/DATABASE)==facts
    assert br.inspect_dataset(image).ordinary_startup_permitted
    reopened=SQLiteStore(image)
    try:
        service=TimerService(reopened);task=uid()
        assert service.create_task(task,'After read-only interruption',request_id=uid(),action_utc_us=NOW).status=='committed'
    finally:reopened.close()


def test_crashed_transaction_journal_is_not_recovered_or_deleted_by_inspector(image):
    from test_interruptions import paused_child
    code=r'''
import sqlite3,sys
from pathlib import Path
path=Path(sys.argv[1])/'chronicle.sqlite3'
c=sqlite3.connect(path,isolation_level=None)
c.execute('PRAGMA synchronous=EXTRA');c.execute('PRAGMA cache_size=1')
c.execute('BEGIN IMMEDIATE')
c.execute('UPDATE tasks SET version=version+1')
assert Path(str(path)+'-journal').is_file()
print('BARRIER',flush=True);sys.stdin.readline()
'''
    with paused_child(code,image):pass
    before=preserved(image);result=br.inspect_dataset(image)
    assert result.classification==C.UNSAFE_OR_UNAVAILABLE and not result.full_validation_completed
    assert preserved(image)==before and (image/(DATABASE+'-journal')).exists()


def test_rich_current_inspection_backup_restore_reopen_and_independent_work(image,rich,tmp_path):
    source=image/DATABASE;before=preserved(image);facts=logical(source)
    first=br.inspect_dataset(image);assert first.ordinary_startup_permitted
    assert preserved(image)==before and logical(source)==facts
    store=SQLiteStore(image);service=TimerService(store)
    backup=tmp_path/'recovery-image'
    try:
        reconciliation=service.read_polr_reconciliation(cutoff_utc_us=NOW)
        reminder=service.read_polr_reminder_status(cutoff_utc_us=NOW)
        active=service.read_current_state(cutoff_utc_us=NOW)['active']
        assert service.read_task_work_history(rich['task'],cutoff_utc_us=NOW,period='all')
        assert store.backup(backup).verified and logical(backup)==facts
    finally:store.close()
    original=preserved(image);backup_bytes=backup.read_bytes()
    assert br.validate_image(backup).dataset_id==rich['candidate'].dataset_id
    restored=br.restore_image(backup,tmp_path/'restored');assert restored.verified
    assert br.inspect_dataset(tmp_path/'restored').ordinary_startup_permitted
    reopened=SQLiteStore(tmp_path/'restored');service=TimerService(reopened)
    try:
        assert logical(reopened.path)==facts
        assert service.read_polr_reconciliation(cutoff_utc_us=NOW)==reconciliation
        assert service.read_polr_reminder_status(cutoff_utc_us=NOW)==reminder
        assert service.read_current_state(cutoff_utc_us=NOW)['active']==active
        assert service.read_registered_timesheet_export(rich['candidate'].export_id)==rich['candidate']
        dated(service,rich['task'],duration='0:01')
        assert service.stop_timer(active['entry_id'],expected_version=active['version'],request_id=uid(),action_utc_us=NOW+60_000_000).status=='committed'
        next_entry=uid();assert service.start_timer(rich['task'],next_entry,expected_task_version=2,request_id=uid(),action_utc_us=NOW+60_000_001).status=='committed'
        assert service.switch_timer(next_entry,rich['second'],uid(),expected_active_version=1,expected_task_version=1,request_id=uid(),action_utc_us=NOW+120_000_000).status=='committed'
    finally:reopened.close()
    assert preserved(image)==original and backup.read_bytes()==backup_bytes
    assert Path(rich['candidate'].preferred_destination).read_bytes()==rich['candidate'].report_utf8


@pytest.mark.parametrize('kind',['supported','newer','receipt','extra'])
def test_real_tk_normal_startup_after_inspection_and_rejection_without_upgrade_ui(image,rich,kind,root,click):
    import tkinter as tk
    from chronicle.app import ChronicleApp
    from test_timesheet_save_ui import exit_settled
    damage(image,kind);before=preserved(image)
    result=br.inspect_dataset(image)
    assert result.ordinary_startup_permitted==(kind=='supported') and preserved(image)==before
    worker=DatabaseWorker(image);app=ChronicleApp(root,worker,now_utc=Clock());worker.start()
    try:
        if kind!='supported':
            pump(root,lambda:app._worker_stopped)
            assert not app.ready and all(b.instate(['disabled']) for b in app.buttons.values())
            assert preserved(image)==before
            app.request_close();assert not app.alive
            return
        pump(root,lambda:app.ready and app.state.get('report') is not None)
        assert not any('upgrade' in label.lower() or 'inspect' in label.lower() for label in app.buttons)
        app.tree.selection_set(app.task_row(rich['task']));app._selection_changed()
        click(app.buttons['Stop']);pump(root,lambda:app.pending is None and app.state['active'] is None)
        click(app.buttons['Start']);pump(root,lambda:app.pending is None and app.state['active'] is not None)
        active=dict(app.state['active']);app.request_close();exit_settled(app)
        worker.join(8);assert not worker.is_alive()
        assert br.inspect_dataset(image).ordinary_startup_permitted
        # Ordinary reopen constructs fresh UI/worker ownership, never an upgrade session.
        other=tk.Tk();other_errors=[];other.report_callback_exception=lambda *a:other_errors.append(a)
        next_worker=DatabaseWorker(image);fresh=ChronicleApp(other,next_worker,now_utc=Clock());next_worker.start()
        try:
            pump(other,lambda:fresh.ready and fresh.state.get('report') is not None)
            assert fresh.state['active']==active and fresh.pending is None
            fresh.request_close();exit_settled(fresh)
        finally:
            if fresh.alive:other.destroy()
            next_worker.join(8);assert not next_worker.is_alive()
        assert not other_errors and not root.test_errors
    finally:
        if app.alive:root.destroy()
        worker.join(8);assert not worker.is_alive()


@pytest.mark.parametrize('literal',["'TIMED'","'timed  '"])
def test_same_version_literal_change_is_not_normalized_into_supported_schema(tmp_path,literal):
    directory=tmp_path/'literal';store=SQLiteStore(directory,create=True,timezone='UTC');store.close()
    c=sqlite3.connect(directory/DATABASE)
    try:
        sql=c.execute("SELECT sql FROM sqlite_schema WHERE name='work_entries'").fetchone()[0]
        c.execute('PRAGMA writable_schema=ON')
        c.execute("UPDATE sqlite_schema SET sql=? WHERE name='work_entries'",(sql.replace("'timed'",literal),))
        c.commit()
    finally:c.close()
    before=preserved(directory)
    assert br.inspect_dataset(directory).classification==C.UNSUPPORTED_LAYOUT
    assert preserved(directory)==before


def test_layout_refusal_keeps_original_diagnostic_when_close_also_fails(image,monkeypatch):
    from chronicle.sqlite_store import UnsupportedSchemaLayout
    primary=UnsupportedSchemaLayout('original layout refusal');secondary=OSError('close also failed')
    readonly=br._readonly;connections=[]
    class Connection:
        def __init__(self,c):self.inner=c
        def __getattr__(self,n):return getattr(self.inner,n)
        def close(self):raise secondary
    def opened(path):
        result=Connection(readonly(path));connections.append(result);return result
    def fail(c):raise primary
    monkeypatch.setattr(br,'_readonly',opened);monkeypatch.setattr(SQLiteStore,'_verify_schema',staticmethod(fail))
    before=preserved(image)
    try:
        result=br.inspect_dataset(image)
        assert result.error is primary and result.classification==C.UNSAFE_OR_UNAVAILABLE
        assert not result.full_validation_completed and len(connections)==1
        assert any('close also failed' in n for n in primary.__notes__) and preserved(image)==before
    finally:connections[0].inner.close()


def test_busy_cold_image_returns_unavailable_without_writable_recovery(image):
    c=sqlite3.connect(image/DATABASE,isolation_level=None)
    c.execute('BEGIN EXCLUSIVE');before=preserved(image)
    try:
        result=br.inspect_dataset(image)
        assert result.classification==C.UNSAFE_OR_UNAVAILABLE
        assert isinstance(result.error,sqlite3.OperationalError) and not result.full_validation_completed
        assert preserved(image)==before
    finally:c.close()
