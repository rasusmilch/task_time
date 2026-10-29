"""Real SQLite images, cold restore, logical evidence equality and bounded faults."""
from dataclasses import replace
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest

from chronicle import backup_restore as br
from chronicle.records import Outcome, Request
from chronicle.services import TimerService
from chronicle.sqlite_store import DATABASE, SQLiteStore
from chronicle.worker import DatabaseWorker, Message
from conftest import NOW, uid
from test_manual_work import dated, timed, M
from test_polr_confirmation import manual, source_args, submit
from test_timesheet_candidate import preview
from test_worker import receive


def logical(path):
    c = sqlite3.connect(Path(path).absolute().as_uri()+'?mode=ro', uri=True)
    try:
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
        return {n: sorted([tuple(r) for r in c.execute(f'SELECT * FROM {n}')], key=repr) for n in names}
    finally:
        c.close()


def symlink(source, target, directory=False):
    try:
        target.symlink_to(source, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        if (isinstance(exc, OSError) and exc.errno not in (1,13,38,95)
                and getattr(exc, 'winerror', None) != 1314):
            raise
        pytest.skip(f'Native symlink setup unavailable: {exc}')


@pytest.mark.parametrize('winerror', [1314, 87, None])
def test_symlink_setup_windows_privilege_denial_is_narrow(tmp_path, monkeypatch, winerror):
    error = OSError(22, 'Synthetic Windows symlink fixture failure')
    error.winerror = winerror
    def fail(*args, **kwargs): raise error
    monkeypatch.setattr(Path, 'symlink_to', fail)
    if winerror == 1314:
        with pytest.raises(pytest.skip.Exception, match='Native symlink setup unavailable'):
            symlink(tmp_path/'source', tmp_path/'link')
    else:
        with pytest.raises(OSError) as caught:
            symlink(tmp_path/'source', tmp_path/'link')
        assert caught.value is error
    assert not list(tmp_path.iterdir())


@pytest.fixture
def rich(service, task, store, tmp_path):
    project, second, deleted = uid(), uid(), uid()
    assert service.create_project(project, 'Project', request_id=uid(), action_utc_us=NOW).status=='committed'
    assert service.assign_task_to_project(task, project, expected_version=1, request_id=uid(), action_utc_us=NOW).status=='committed'
    for key in (second, deleted):
        assert service.create_task(key, 'Example', request_id=uid(), action_utc_us=NOW).status=='committed'
    entry = timed(service, task, comment='genuine')
    assert service.edit_closed_timed_work(task,entry,'2026-10-19','08:01','2026-10-19','09:00',expected_revision=1,comment='correction',request_id=uid(),action_utc_us=NOW).status=='committed'
    d = dated(service, task, duration='0:20')
    assert service.edit_date_only_work(task,d,'2026-10-20','0:21',expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    removed = dated(service, second)
    assert service.delete_work_entry(second,removed,expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    dated(service, deleted)
    store.connection.execute('UPDATE tasks SET is_archived=1,archived_at_utc_us=0 WHERE task_id=?',(deleted,))
    assert service.set_week_start(0,expected_week_start=6,request_id=uid(),action_utc_us=NOW).status=='committed'
    active = uid()
    assert service.start_timer(second,active,expected_task_version=1,request_id=uid(),action_utc_us=NOW-5*M).status=='committed'
    assert service.correct_active_start(active,'2026-10-19','09:54',expected_version=1,comment='earlier',request_id=uid(),action_utc_us=NOW).status=='committed'
    candidate = replace(preview(service), preferred_destination=str(tmp_path/'report.txt'))
    assert service.register_timesheet_export(candidate,request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.materialize_registered_timesheet_export(candidate.export_id,candidate.preferred_destination).verified
    assert submit(service,source_args(service,candidate)).status=='committed'
    assert submit(service,manual(service,task,9)).status=='committed'
    assert submit(service,manual(service,second,0,day='2026-10-20')).status=='committed'
    assert service.dismiss_polr_reminder_today('2026-10-19',request_id=uid(),action_utc_us=NOW).status=='committed'
    return dict(task=task,second=second,active=active,candidate=candidate)


@pytest.mark.parametrize('populated',[False,True])
def test_consistent_snapshot_full_evidence_restore_reopen_and_independent_future_work(store, service, task, rich, tmp_path, populated):
    # A separate fresh image establishes the genuinely empty case.
    if not populated:
        other = SQLiteStore(tmp_path/'empty', create=True, timezone='UTC')
        try:
            result = other.backup(tmp_path/'empty.sqlite3')
            assert result.verified
            assert logical(result.destination)==logical(other.path)
        finally:
            other.close()
        return
    before, raw = logical(store.path), store.path.read_bytes()
    report_bytes = Path(rich['candidate'].preferred_destination).read_bytes()
    backup = tmp_path/'backup.sqlite3'
    result = store.backup(backup)
    assert result.verified and result.image.dataset_id==store.dataset_id
    assert result.phase is br.BackupPhase.VERIFIED
    assert logical(backup)==before==logical(store.path)
    assert store.path.read_bytes()==raw
    backup_bytes=backup.read_bytes()
    restored=br.restore_image(backup,tmp_path/'recovered')
    assert restored.verified
    assert logical(restored.destination)==before
    recovered=SQLiteStore(tmp_path/'recovered')
    try:
        s=TimerService(recovered)
        assert recovered.dataset_id==store.dataset_id and recovered.week_start==0
        assert recovered.info['journal_mode']=='delete' and recovered.info['synchronous']==3 and recovered.info['foreign_keys']==1
        active=s.read_current_state(cutoff_utc_us=NOW)['active']
        assert active['entry_id']==rich['active'] and active['version']==2
        assert s.read_registered_timesheet_export(rich['candidate'].export_id)==rich['candidate']
        assert Path(rich['candidate'].preferred_destination).read_bytes()==report_bytes
        assert s.read_polr_reconciliation(cutoff_utc_us=NOW)==service.read_polr_reconciliation(cutoff_utc_us=NOW)
        assert s.read_polr_reminder_status(cutoff_utc_us=NOW)['dismissed_local_date']=='2026-10-19'
        dated(s,rich['task'],duration='0:01')
        assert logical(recovered.path)!=before
    finally:
        recovered.close()
    assert logical(store.path)==before and store.path.read_bytes()==raw and backup.read_bytes()==backup_bytes
    assert not list(tmp_path.glob('.chronicle-backup-*'))


def test_minimal_backup_validate_restore_without_rich_report_fixture(store,tmp_path):
    before=logical(store.path);raw=store.path.read_bytes()
    result=store.backup(tmp_path/'minimal.sqlite3')
    assert result.verified,result.error
    assert br.validate_image(result.destination).dataset_id==store.dataset_id
    restored=br.restore_image(result.destination,tmp_path/'minimal-restored')
    assert restored.verified,restored.error
    assert logical(restored.destination)==before==logical(store.path)
    assert store.path.read_bytes()==raw
    assert br.inspect_dataset(tmp_path/'minimal-restored').ordinary_startup_permitted


@pytest.mark.parametrize('kind',['file','directory','symlink','dangling','fifo','dataset','alias'])
def test_backup_never_overwrites_objects_or_dataset_aliases(store, tmp_path, kind):
    target=tmp_path/'target'
    if kind=='file': target.write_bytes(b'keep')
    elif kind=='directory': target.mkdir()
    elif kind in ('symlink','dangling'):
        symlink(store.path if kind=='symlink' else tmp_path/'missing',target)
    elif kind=='fifo':
        if not hasattr(os,'mkfifo'):pytest.skip('Native FIFO API unavailable')
        try:os.mkfifo(target)
        except OSError as exc:
            if exc.errno not in (1,13,38,95):raise
            pytest.skip(f'Native FIFO unavailable: {exc}')
    elif kind=='dataset': target=store.directory/'new-backup'
    elif kind=='alias':
        alias=tmp_path/'alias';symlink(store.directory,alias,True);target=alias/'new-backup'
    before=logical(store.path)
    result=store.backup(target)
    assert not result.verified and result.phase is br.BackupPhase.NOT_STARTED
    assert logical(store.path)==before
    if kind=='file':assert target.read_bytes()==b'keep'
    if kind in ('dataset','alias'):assert not target.exists()


@pytest.mark.parametrize('path',['', '\0bad', 12, None])
def test_invalid_path_never_creates_output(store,path):
    with pytest.raises(ValueError):store.backup(path)


def test_missing_parent_and_unresolved_transaction_refuse(store,tmp_path):
    result=store.backup(tmp_path/'missing'/'backup')
    assert not result.verified and not (tmp_path/'missing').exists()
    store.connection.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(RuntimeError):store.backup(tmp_path/'not-created')
        assert not (tmp_path/'not-created').exists()
    finally:store.connection.execute('ROLLBACK')


@pytest.mark.parametrize('fault',['stage','copy','sync','validate','identity','publication','final','cleanup','lost_ack','racing_target'])
def test_bounded_faults_keep_primary_do_not_roll_back_final_and_keep_source(store,task,tmp_path,monkeypatch,fault):
    target=tmp_path/'output';before=logical(store.path);primary=OSError('injected primary')
    original_validate=br.validate_image;link=br.os.link;calls=[]
    def fail(*a,**kw):raise primary
    if fault=='stage':monkeypatch.setattr(br,'_stage',fail)
    elif fault=='copy':monkeypatch.setattr(br,'_copy',fail)
    elif fault=='sync':monkeypatch.setattr(br,'_sync',fail)
    elif fault=='identity':monkeypatch.setattr(br,'_owned',fail)
    elif fault=='validate':monkeypatch.setattr(br,'validate_image',fail)
    elif fault=='cleanup':monkeypatch.setattr(br,'_remove_owned',fail)
    elif fault in ('publication','lost_ack','racing_target'):
        def publish(stage,final):
            if fault=='lost_ack':link(stage,final)
            if fault=='racing_target':final.write_bytes(b'other owner')
            raise primary
        monkeypatch.setattr(br.os,'link',publish)
    elif fault=='final':
        def validate(path):
            calls.append(path)
            if path==target:raise primary
            return original_validate(path)
        monkeypatch.setattr(br,'validate_image',validate)
    result=store.backup(target)
    assert not result.verified and result.error is primary and logical(store.path)==before
    if fault in ('lost_ack','final','cleanup'):
        assert target.exists() and logical(target)==before
        assert result.phase in (br.BackupPhase.PUBLISHED_UNVERIFIED,br.BackupPhase.VERIFIED)
        assert original_validate(target).dataset_id==store.dataset_id
    elif fault=='racing_target':assert target.read_bytes()==b'other owner'
    else:assert not target.exists()
    if fault!='cleanup':assert not list(tmp_path.glob('.chronicle-backup-*'))


def test_cleanup_failure_is_secondary_not_primary(store,tmp_path,monkeypatch):
    primary=OSError('copy failed');secondary=OSError('cleanup failed')
    def fail(*a):raise primary
    def cleanup(*a):raise secondary
    monkeypatch.setattr(br,'_copy',fail);monkeypatch.setattr(br,'_remove_owned',cleanup)
    result=store.backup(tmp_path/'backup')
    assert result.error is primary and any('cleanup failed' in n for n in primary.__notes__)
    assert not (tmp_path/'backup').exists()


@pytest.mark.parametrize('kind',['empty_dir','nonempty_dir','file','symlink','source_alias'])
def test_restore_existing_targets_never_change(store,tmp_path,kind):
    backup=tmp_path/'backup';assert store.backup(backup).verified
    target=tmp_path/'target';before=logical(store.path);raw=backup.read_bytes()
    if kind.endswith('dir'):
        target.mkdir()
        if kind=='nonempty_dir':(target/'unknown').write_bytes(b'keep')
    elif kind=='file':target.write_bytes(b'keep')
    elif kind=='source_alias':target=backup
    else:symlink(store.directory,target,True)
    with pytest.raises((ValueError,FileExistsError)):br.restore_image(backup,target)
    assert backup.read_bytes()==raw and logical(store.path)==before
    if kind=='nonempty_dir':assert (target/'unknown').read_bytes()==b'keep'


@pytest.mark.parametrize('fault',['foreign','corrupt','application','schema','fk','revision','export','confirmation','current','receipt','reminder','journal'])
def test_invalid_source_is_read_only_and_target_not_reserved(store,service,rich,tmp_path,fault):
    backup=tmp_path/'bad.sqlite3';assert store.backup(backup).verified
    c=sqlite3.connect(backup)
    try:
        c.execute('PRAGMA foreign_keys=OFF')
        if fault=='application':c.execute('PRAGMA application_id=5')
        elif fault=='schema':c.execute('CREATE TABLE unexpected(x)')
        elif fault=='fk':c.execute("UPDATE tasks SET project_id=? WHERE task_id=?",(uid(),rich['task']))
        elif fault=='reminder':c.execute("UPDATE dataset_meta SET polr_reminder_dismissed_local_date='2026-02-30'")
        elif fault=='current':c.execute('DELETE FROM polr_confirmed_current')
        elif fault=='journal':c.execute('PRAGMA journal_mode=WAL')
        elif fault in ('revision','export','confirmation','receipt'):
            # Corruption setup bypasses guards, then restores exact schema definitions.
            table={'revision':'work_revisions','export':'timesheet_exports','confirmation':'polr_confirmation_cells','receipt':'committed_requests'}[fault]
            triggers=list(c.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",(table,)))
            for name,sql in triggers:c.execute(f'DROP TRIGGER {name}')
            if fault=='revision':c.execute('UPDATE work_revisions SET request_id=? WHERE entry_id=? AND revision=2',(uid(),next(r[0] for r in c.execute("SELECT entry_id FROM work_revisions WHERE revision=2"))))
            elif fault=='export':c.execute("UPDATE timesheet_exports SET report_sha256=?",('0'*64,))
            elif fault=='confirmation':c.execute('UPDATE polr_confirmation_cells SET confirmed_quarters=99')
            else:c.execute("UPDATE committed_requests SET request_bytes=x'7B7D' WHERE commit_seq=1")
            for name,sql in triggers:c.execute(sql)
        c.commit()
    finally:c.close()
    if fault=='foreign':
        backup=tmp_path/'foreign';c=sqlite3.connect(backup);c.execute('CREATE TABLE other(x)');c.close()
    if fault=='corrupt':backup.write_bytes(b'not SQLite')
    raw=backup.read_bytes();target=tmp_path/'no-target'
    with pytest.raises((ValueError,sqlite3.Error,KeyError)):br.restore_image(backup,target)
    assert not target.exists() and backup.read_bytes()==raw


def test_changed_source_after_staging_refuses_restore(store,tmp_path,monkeypatch):
    backup=tmp_path/'backup';assert store.backup(backup).verified
    copy=br._copy
    def changed(source,stage):
        copy(source,stage)
        with backup.open('ab') as f:f.write(b'changed')
    monkeypatch.setattr(br,'_copy',changed)
    result=br.restore_image(backup,tmp_path/'restore')
    assert not result.verified and 'source changed' in str(result.error)
    assert not (tmp_path/'restore'/DATABASE).exists()


def test_worker_backup_uses_existing_owner_serialization_and_shutdown(tmp_path,monkeypatch):
    original=SQLiteStore.backup;threads=[]
    def observed(self,destination):
        threads.append(threading.get_ident())
        return original(self,destination)
    monkeypatch.setattr(SQLiteStore,'backup',observed)
    worker=DatabaseWorker(tmp_path/'source',create=True,timezone='UTC');worker.start()
    ready=receive(worker,'ready');task=uid();request=Request.make(uid(),ready['dataset_id'],'create_task',NOW,task_id=task,name='worker',project_id=None)
    worker.requests.put(Message('mutate',1,request))
    destination=tmp_path/'worker-backup'
    worker.requests.put(Message('backup',2,dict(request_id=uid(),destination=str(destination))))
    worker.requests.put(Message('shutdown'))
    assert receive(worker,'mutate').status=='committed'
    assert receive(worker,'backup')['result'].verified
    receive(worker,'stopped');worker.join(5)
    assert not worker.is_alive() and threads==[worker.ident] and worker.ident!=threading.get_ident()
    assert logical(destination)==logical(tmp_path/'source'/DATABASE)


def cli(*args):
    return subprocess.run([sys.executable,'-B','run_chronicle.py',*map(str,args)],capture_output=True,text=True,timeout=15,
                          env={**os.environ,'DISPLAY':''})


def test_cli_verify_restore_no_display_source_unchanged_reopen(store,tmp_path):
    backup=tmp_path/'backup';assert store.backup(backup).verified;raw=backup.read_bytes()
    verified=cli('--verify-backup',backup)
    assert verified.returncode==0,verified.stderr
    assert 'Backup verified' in verified.stdout
    result=cli('--restore-from',backup,'--data-dir',tmp_path/'restore')
    assert result.returncode==0,result.stderr
    assert 'Ready for a new Chronicle launch' in result.stdout
    with_reopen=SQLiteStore(tmp_path/'restore')
    try:assert with_reopen.dataset_id==store.dataset_id
    finally:with_reopen.close()
    assert backup.read_bytes()==raw


@pytest.mark.parametrize('args',[
    ['--verify-backup','missing','--restore-from','missing'],
    ['--verify-backup','missing','--create'], ['--verify-backup','missing','--timezone','UTC'],
    ['--restore-from','missing'], ['--restore-from','missing','--data-dir','unused','--create'],
    ['--restore-from','missing','--data-dir','unused','--timezone','UTC'],
    ['--verify-backup','missing','--data-dir','unused'],
])
def test_cli_invalid_combinations_before_root_worker_or_files(args,tmp_path):
    result=cli(*args)
    assert result.returncode==2 and 'TclError' not in result.stderr
    assert not (tmp_path/'unused').exists()


def test_cli_invalid_source_nonzero_no_target(tmp_path):
    bad=tmp_path/'bad';bad.write_bytes(b'bad')
    result=cli('--restore-from',bad,'--data-dir',tmp_path/'not-created')
    assert result.returncode==1 and not (tmp_path/'not-created').exists()


@pytest.mark.parametrize('fault',['connect','backup','progress','close','fsync','compare'])
def test_actual_staging_boundaries_abort_without_false_success(store,tmp_path,monkeypatch,fault):
    primary=OSError(f'{fault} fault');target=tmp_path/'backup';before=logical(store.path)
    connect=br.sqlite3.connect
    class Destination:
        def __init__(self,inner):self.inner=inner
        def __getattr__(self,name):return getattr(self.inner,name)
        def close(self):
            self.inner.close()
            raise primary
    if fault in ('connect','close'):
        def stage_connect(path,*a,**kw):
            staging=isinstance(path,Path) and path.name.startswith('.chronicle-backup-')
            if staging and fault=='connect':raise primary
            result=connect(path,*a,**kw)
            return Destination(result) if staging and fault=='close' else result
        monkeypatch.setattr(br.sqlite3,'connect',stage_connect)
    if fault in ('backup','progress','close'):
        real=store.connection
        class Source:
            def __getattr__(self,name):return getattr(real,name)
            def backup(self,destination,**kw):
                if fault=='backup':raise primary
                if fault=='progress':kw['progress'](sqlite3.SQLITE_BUSY,1,2)
                else:real.backup(destination.inner,**kw)
        store.connection=Source()
    if fault=='fsync':
        def fail(fd):raise primary
        monkeypatch.setattr(br.os,'fsync',fail)
    if fault=='compare':
        def fail(*a):raise primary
        monkeypatch.setattr(br,'_same_content',fail)
    result=store.backup(target)
    assert not result.verified and result.error is not None
    if fault=='progress':assert isinstance(result.error,TimeoutError)
    else:assert result.error is primary
    if fault=='compare':assert logical(target)==before and result.phase is br.BackupPhase.PUBLISHED_UNVERIFIED
    else:assert not target.exists()
    assert logical(store.path)==before and not list(tmp_path.glob('.chronicle-backup-*'))


def test_unowned_stage_and_unexpected_restore_objects_are_never_deleted(store,tmp_path,monkeypatch):
    copy=br._copy;replaced=[]
    def hijack(source,stage):
        copy(source,stage)
        other=stage.with_name('unknown-object')
        other.write_bytes(b'other owner')
        os.replace(other,stage)
        replaced.append(stage)
    monkeypatch.setattr(br,'_copy',hijack)
    result=store.backup(tmp_path/'backup')
    assert not result.verified and replaced[0].read_bytes()==b'other owner'
    assert any('ownership' in n for n in result.error.__notes__)
    monkeypatch.setattr(br,'_copy',copy)
    assert store.backup(tmp_path/'source-image').verified
    acquire=br.DatasetLock.acquire
    def reserve(self):
        acquire(self)
        (self.path.parent/'unexpected').write_bytes(b'preserve')
    monkeypatch.setattr(br.DatasetLock,'acquire',reserve)
    result=br.restore_image(tmp_path/'source-image',tmp_path/'restore')
    assert not result.verified and (tmp_path/'restore'/'unexpected').read_bytes()==b'preserve'
    assert not (tmp_path/'restore'/DATABASE).exists()


def test_worker_refuses_backup_until_exact_unverified_mutation_reconciles(tmp_path,monkeypatch):
    execute=TimerService.execute;state={'failed':False}
    def uncertain(self,request):
        result=execute(self,request)
        if not state['failed']:
            state['failed']=True
            return Outcome('unverified',error=OSError('acknowledgement unavailable'))
        return result
    monkeypatch.setattr(TimerService,'execute',uncertain)
    worker=DatabaseWorker(tmp_path/'source',create=True,timezone='UTC');worker.start()
    try:
        ready=receive(worker,'ready')
        request=Request.make(uid(),ready['dataset_id'],'create_task',NOW,task_id=uid(),name='one',project_id=None)
        worker.requests.put(Message('mutate',1,request));assert receive(worker,'mutate').status=='unverified'
        worker.requests.put(Message('backup',2,dict(request_id=uid(),destination=str(tmp_path/'refused'))))
        result=receive(worker,'backup')['result']
        assert result.status=='unavailable' and 'unresolved' in str(result.error) and not (tmp_path/'refused').exists()
        worker.requests.put(Message('reconcile',3,request));assert receive(worker,'reconcile').status=='committed'
        worker.requests.put(Message('backup',4,dict(request_id=uid(),destination=str(tmp_path/'good'))))
        assert receive(worker,'backup')['result'].verified
    finally:
        worker.requests.put(Message('shutdown'));receive(worker,'stopped');worker.join(5)


def test_verification_and_restore_never_construct_root_app_or_worker(store,tmp_path,monkeypatch):
    from chronicle import bootstrap
    backup=tmp_path/'backup';assert store.backup(backup).verified
    def forbidden(*a,**kw):raise AssertionError('Recovery cannot construct a runtime session')
    monkeypatch.setattr(bootstrap.tk,'Tk',forbidden)
    monkeypatch.setattr(bootstrap,'ChronicleApp',forbidden)
    monkeypatch.setattr(bootstrap,'DatabaseWorker',forbidden)
    assert bootstrap.main(['--verify-backup',str(backup)]).dataset_id==store.dataset_id
    assert bootstrap.main(['--restore-from',str(backup),'--data-dir',str(tmp_path/'recovered-cli')]).verified


def test_wal_rejection_does_not_create_sidecars(store,tmp_path):
    backup=tmp_path/'wal-image';assert store.backup(backup).verified
    c=sqlite3.connect(backup);c.execute('PRAGMA journal_mode=WAL');c.close()
    before={p.name:p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    with pytest.raises(ValueError,match='DELETE'):br.validate_image(backup)
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}==before


@pytest.mark.parametrize('network',['//server/share/new',r'\\server\share\new'])
def test_restore_refuses_explicit_network_target_before_reservation(store,tmp_path,network):
    backup=tmp_path/'backup';assert store.backup(backup).verified
    with pytest.raises(ValueError,match='local'):br.restore_image(backup,network)


def test_backup_after_stop_switch_and_correction_preserves_all_receipts(service,task,store,tmp_path):
    second,entry,next_entry=uid(),uid(),uid()
    assert service.create_task(second,'second',request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.start_timer(task,entry,expected_task_version=1,request_id=uid(),action_utc_us=NOW-5*M).status=='committed'
    assert service.correct_active_start(entry,'2026-10-19','09:54',expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.switch_timer(entry,second,next_entry,expected_active_version=2,expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.stop_timer(next_entry,expected_version=1,request_id=uid(),action_utc_us=NOW+M).status=='committed'
    result=store.backup(tmp_path/'backup')
    assert result.verified and logical(result.destination)==logical(store.path)


def test_real_sqlite_progress_interruption_has_no_published_partial_image(store,rich,tmp_path):
    real=store.connection;primary=OSError('interrupted actual SQLite page backup');progress=[]
    class Source:
        def __getattr__(self,name):return getattr(real,name)
        def backup(self,destination,**kw):
            def interrupt(status,remaining,total):
                progress.append((status,remaining,total))
                assert remaining>0
                raise primary
            real.backup(destination,pages=1,progress=interrupt,sleep=0.05)
    before=logical(store.path);store.connection=Source()
    result=store.backup(tmp_path/'backup')
    assert result.error is primary and not result.verified and progress
    assert not (tmp_path/'backup').exists() and not list(tmp_path.glob('.chronicle-backup-*'))
    assert logical(store.path)==before


def test_stage_changes_before_publication_and_source_stability_reject(store,tmp_path,monkeypatch):
    validate=br.validate_image
    def change(path):
        image=validate(path)
        if Path(path).name.startswith('.chronicle-backup-'):
            with Path(path).open('ab') as f:f.write(b'change after validation')
        return image
    monkeypatch.setattr(br,'validate_image',change)
    result=store.backup(tmp_path/'backup')
    assert not result.verified and 'stage changed' in str(result.error)
    assert not (tmp_path/'backup').exists() and not list(tmp_path.glob('.chronicle-backup-*'))


@pytest.mark.parametrize('kind',['directory','symlink','dangling','unreadable'])
def test_unsuitable_source_does_not_reserve_restore_target(store,tmp_path,kind):
    path=tmp_path/'source-image';target=tmp_path/'not-created'
    if kind=='directory':path.mkdir()
    elif kind in ('symlink','dangling'):symlink(store.path if kind=='symlink' else tmp_path/'absent',path)
    else:
        assert store.backup(path).verified
        path.chmod(0)
        if os.access(path,os.R_OK):
            path.chmod(0o600)
            pytest.skip('Native privilege bypasses file read permission; permission case unavailable')
    try:
        with pytest.raises((ValueError,OSError)):br.restore_image(path,target)
        assert not target.exists()
    finally:
        if kind=='unreadable':path.chmod(0o600)


def test_stage_name_collision_never_writes_or_cleans_final_destination(store,tmp_path,monkeypatch):
    identity=uid();monkeypatch.setattr(br,'uuid4',lambda:identity)
    target=tmp_path/f'.chronicle-backup-{identity}.tmp'
    result=store.backup(target)
    assert not result.verified and 'staging must differ' in str(result.error)
    assert not target.exists()
