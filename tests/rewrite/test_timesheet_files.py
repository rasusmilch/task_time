"""Registered SQLite evidence through real protected file operations and bounded faults."""
from dataclasses import replace
import errno
import hashlib
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import chronicle.timesheet_files as files
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timesheet_files import FileState as S,PublicationPhase as P
from conftest import NOW,uid
from test_timesheet_candidate import preview,case_c
from test_manual_work import facts,dated
from test_timesheet_registration import exports


@pytest.fixture
def registered(service,task,store,tmp_path):
    case_c(service,task)
    candidate=preview(service)
    assert service.register_timesheet_export(candidate,request_id=uid(),action_utc_us=NOW).status=='committed'
    return service,store,candidate,tmp_path/'timesheet.txt'


def publish(r,**kw):
    service,store,c,target=r
    return service.materialize_registered_timesheet_export(c.export_id,target,**kw)


def inspect(r):
    service,store,c,target=r
    return service.inspect_registered_export_destination(c.export_id,target)


def native_symlink(target,link):
    try: link.symlink_to(target,target_is_directory=target.is_dir())
    except (NotImplementedError,AttributeError) as exc: pytest.skip(f'Native symlink unavailable: {exc}')
    except OSError as exc:
        if exc.errno in (errno.EPERM,errno.EACCES,errno.ENOSYS,errno.ENOTSUP,errno.EOPNOTSUPP) or getattr(exc,'winerror',None)==1314:
            pytest.skip(f'Native symlink unsupported/denied: {exc}')
        raise


def test_fresh_status_exact_publication_matching_reuse_and_no_work_changes(registered,monkeypatch):
    service,store,c,path=registered;before=facts(store);evidence=exports(store)
    assert service.inspect_registered_export_destination(c.export_id).state==S.PENDING
    assert inspect(registered).state==S.MISSING
    result=publish(registered)
    assert result.verified and result.phase==P.VERIFIED and result.inspection.state==S.READY
    assert path.read_bytes()==c.report_utf8 and hashlib.sha256(path.read_bytes()).hexdigest()==c.report_sha256
    observation=path.stat()
    with monkeypatch.context() as m:
        m.setattr(files.os,'link',lambda *a,**k:pytest.fail('matching copy was published again'))
        m.setattr(files.os,'replace',lambda *a,**k:pytest.fail('matching copy replaced'))
        result=publish(registered)
    assert result.phase==P.REUSED and files.metadata(path.stat())==files.metadata(observation)
    assert not list(path.parent.glob('.chronicle-timesheet-*.tmp'))
    assert facts(store)==before and exports(store)==evidence
    path.unlink();assert inspect(registered).state==S.MISSING


@pytest.mark.parametrize('bad',[None,False,7,b'',[],{},'','  ','bad\x00path'])
def test_strict_explicit_destination(registered,bad):
    service,store,c,path=registered
    with pytest.raises((ValueError,TypeError)):
        service.materialize_registered_timesheet_export(c.export_id,bad)


@pytest.mark.parametrize('bad',[1,0,'yes',None])
def test_overwrite_requires_actual_boolean(registered,bad):
    with pytest.raises(ValueError):publish(registered,confirmed_overwrite=bad)


def test_committed_evidence_gate_before_any_file_operation(registered,monkeypatch):
    service,store,c,path=registered
    with monkeypatch.context() as m:
        m.setattr(files,'inspect',lambda *a:pytest.fail('unregistered/corrupt evidence inspected a file'))
        for identity in ('bad',uid()):
            with pytest.raises(ValueError):service.materialize_registered_timesheet_export(identity,path)
        store._recover_connection()
        store.connection.execute('DROP TRIGGER immutable_timesheet_exports_update')
        store.connection.execute("UPDATE timesheet_exports SET report_sha256=?",('0'*64,))
        with pytest.raises(ValueError):publish(registered)
    assert not path.exists()


def test_stable_content_conflict_requires_exact_single_call_observation(registered):
    service,store,c,path=registered;path.write_bytes(b'different')
    status=inspect(registered)
    assert status.state==S.CONFLICT and type(status.conflict) is files.ContentConflict
    assert not publish(registered).verified and path.read_bytes()==b'different'
    with pytest.raises(ValueError):publish(registered,confirmed_overwrite=True)
    assert publish(registered,confirmed_overwrite=True,expected_conflict=status.conflict).verified
    assert path.read_bytes()==c.report_utf8
    path.write_bytes(b'new conflict')
    assert not publish(registered).verified and path.read_bytes()==b'new conflict'
    stale=publish(registered,confirmed_overwrite=True,expected_conflict=status.conflict)
    assert not stale.verified and 'changed' in str(stale.error) and path.read_bytes()==b'new conflict'


@pytest.mark.parametrize('kind',['directory','symlink','dangling','fifo'])
def test_unsuitable_objects_never_authorize_overwrite(registered,kind,tmp_path):
    service,store,c,path=registered
    if kind=='directory':path.mkdir()
    elif kind in ('symlink','dangling'):
        other=tmp_path/'other';
        if kind=='symlink':other.write_bytes(c.report_utf8)
        native_symlink(other,path)
    else:
        if not hasattr(os,'mkfifo'):pytest.skip('Native FIFO API unavailable')
        try:os.mkfifo(path)
        except OSError as exc:
            if exc.errno in (errno.EPERM,errno.EACCES,errno.ENOSYS,errno.ENOTSUP):pytest.skip(f'Native FIFO unavailable: {exc}')
            raise
    result=inspect(registered)
    assert result.state==S.CONFLICT and result.conflict is None
    assert not publish(registered).verified


@pytest.mark.parametrize('fault',['read','incomplete','identity','size','mtime','ctime'])
def test_inconclusive_file_inspection_has_no_consent(registered,monkeypatch,fault):
    service,store,c,path=registered;path.write_bytes(b'content conflict')
    opened=files.os.open;read=files.os.read;fstat=files.os.fstat;count=[]
    if fault in ('read','incomplete'):
        def fail(fd,n):
            if fault=='read':raise PermissionError('read denied')
            return b''
        monkeypatch.setattr(files.os,'read',fail)
    else:
        def changed(fd):
            value=fstat(fd);count.append(1)
            if len(count)==2:
                data={k:getattr(value,k) for k in ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')}
                data[{'identity':'st_ino','size':'st_size','mtime':'st_mtime_ns','ctime':'st_ctime_ns'}[fault]]+=1
                return SimpleNamespace(**data)
            return value
        monkeypatch.setattr(files.os,'fstat',changed)
    result=inspect(registered)
    assert result.state==S.UNVERIFIABLE and result.conflict is None and result.error


@pytest.mark.parametrize('relative',[False,True])
@pytest.mark.parametrize('name',['chronicle.sqlite3','.chronicle.lock','chronicle.sqlite3-journal','new.txt','nested/new.txt',''])
def test_dataset_paths_protected_before_staging(registered,relative,name,monkeypatch):
    service,store,c,path=registered;target=store.directory/name
    if relative:target=Path(os.path.relpath(target))
    before=facts(store);raw=store.path.read_bytes()
    with monkeypatch.context() as m:
        m.setattr(files.os,'open',lambda *a,**k:pytest.fail('protected path opened'))
        with pytest.raises(ValueError,match='protected'):service.materialize_registered_timesheet_export(c.export_id,target)
    assert store.path.read_bytes()==raw and facts(store)==before


def test_resolved_parent_alias_into_dataset_is_protected(registered,tmp_path,monkeypatch):
    service,store,c,path=registered;alias=tmp_path/'alias';native_symlink(store.directory,alias)
    with pytest.raises(ValueError,match='protected'):
        service.materialize_registered_timesheet_export(c.export_id,alias/'absent.txt')
    with pytest.raises(ValueError,match='protected'):
        service.inspect_registered_export_destination(c.export_id,alias/'absent.txt')


def test_concurrent_exclusive_target_and_no_unsafe_hardlink_fallback(registered,monkeypatch):
    service,store,c,path=registered;original=files.os.link
    def racer(stage,target):path.write_bytes(b'racer');return original(stage,target)
    with monkeypatch.context() as m:
        m.setattr(files.os,'link',racer)
        result=publish(registered)
    assert not result.verified and result.phase==P.ATTEMPTED and path.read_bytes()==b'racer'
    path.unlink()
    with monkeypatch.context() as m:
        m.setattr(files.os,'link',lambda *a:(_ for _ in ()).throw(OSError(errno.ENOTSUP,'hardlink unavailable')))
        result=publish(registered)
    assert not result.verified and not path.exists()
    assert not list(path.parent.glob('.chronicle-timesheet-*.tmp'))


@pytest.mark.parametrize('phase',['fdopen','write','short','flush','fsync','close','stage_identity','stage_content','link','replace'])
def test_staging_faults_preserve_existing_target_and_original_error(registered,monkeypatch,phase):
    service,store,c,path=registered
    replacement=phase=='replace'
    if replacement:path.write_bytes(b'old')
    conflict=inspect(registered).conflict if replacement else None
    fault=OSError(phase);fdopen=files.os.fdopen;owned=files._owned;read_regular=files._read_regular
    class Stream:
        def __init__(self,inner):self.inner=inner
        def __getattr__(self,key):return getattr(self.inner,key)
        def write(self,data):
            if phase=='write':raise fault
            return self.inner.write(data[:-1] if phase=='short' else data)
        def flush(self):
            if phase=='flush':raise fault
            return self.inner.flush()
        def close(self):
            self.inner.close()
            if phase=='close':raise fault
    with monkeypatch.context() as m:
        if phase=='fdopen':m.setattr(files.os,'fdopen',lambda *a:(_ for _ in ()).throw(fault))
        elif phase in ('write','short','flush','close'):m.setattr(files.os,'fdopen',lambda *a:Stream(fdopen(*a)))
        elif phase=='fsync':m.setattr(files.os,'fsync',lambda *a:(_ for _ in ()).throw(fault))
        elif phase=='stage_identity':
            def fail(stage,created):
                if stage.name.startswith('.chronicle'):raise fault
                return owned(stage,created)
            m.setattr(files,'_owned',fail)
        elif phase=='stage_content':
            m.setattr(files,'_read_regular',lambda t,*a:(False,'bad') if t.name.startswith('.chronicle') else read_regular(t,*a))
        else:m.setattr(files.os,phase,lambda *a:(_ for _ in ()).throw(fault))
        result=publish(registered,confirmed_overwrite=replacement,expected_conflict=conflict)
    assert not result.verified and result.error
    if phase not in ('short','stage_content'):assert result.error is fault
    if replacement:assert path.read_bytes()==b'old'
    else:assert not path.exists()
    if phase!='stage_identity':assert not list(path.parent.glob('.chronicle-timesheet-*.tmp'))


@pytest.mark.parametrize('change',['replace','delete','mode','size','symlink','ctime'])
def test_final_target_recheck_deterministic_metadata_and_real_changes(registered,monkeypatch,change,tmp_path):
    service,store,c,path=registered;path.write_bytes(b'old');reviewed=inspect(registered).conflict
    if change=='symlink':
        # Establish native capability before the operation, not inside fault injection.
        native_symlink(path,tmp_path/'capability-link')
    original=files._owned;last_lstat=Path.lstat;replacement_calls=[];mutated=[]
    def staged(stage,created):
        result=original(stage,created)
        if not mutated:
            mutated.append(True)
            if change=='replace':path.rename(path.with_suffix('.earlier'));path.write_bytes(b'NEW')
            elif change=='delete':path.unlink()
            elif change=='mode':path.chmod(0o400)
            elif change=='size':path.write_bytes(b'changed size')
            elif change=='symlink':path.unlink();path.symlink_to(tmp_path/'other')
            else:
                old=path.stat();path.write_bytes(b'NEW');os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns))
        return result
    def observed(target,*a,**kw):
        result=last_lstat(target,*a,**kw)
        if change=='ctime' and target==path and mutated:
            # Preserve every compared field except deterministic changed ctime.
            data={key:value for key,value in zip(('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns'),reviewed.metadata)}
            data['st_ctime_ns']+=1
            return SimpleNamespace(**data)
        return result
    with monkeypatch.context() as m:
        m.setattr(files,'_owned',staged);m.setattr(Path,'lstat',observed)
        m.setattr(files.os,'replace',lambda *a:replacement_calls.append(a))
        result=publish(registered,confirmed_overwrite=True,expected_conflict=reviewed)
    assert not result.verified and not replacement_calls and result.error
    if change in ('replace','ctime'):assert path.read_bytes()==b'NEW'
    if change=='delete':assert not path.exists()
    if change=='size':assert path.read_bytes()==b'changed size'
    if change=='symlink':assert path.is_symlink()
    assert not list(path.parent.glob('.chronicle-timesheet-*.tmp'))


@pytest.mark.parametrize('replacement',[False,True])
def test_postpublication_uncertainty_retry_reuses_without_rewrite(registered,monkeypatch,replacement):
    service,store,c,path=registered
    if replacement:path.write_bytes(b'old')
    conflict=inspect(registered).conflict if replacement else None
    name='replace' if replacement else 'link';original=getattr(files.os,name);fault=OSError('lost file acknowledgement')
    def lost(*args):original(*args);raise fault
    with monkeypatch.context() as m:
        m.setattr(files.os,name,lost)
        result=publish(registered,confirmed_overwrite=replacement,expected_conflict=conflict)
    assert result.phase==P.ATTEMPTED and result.error is fault and not result.verified
    assert path.read_bytes()==c.report_utf8 and result.inspection.state==S.READY
    observed=path.stat();assert publish(registered).phase==P.REUSED and files.metadata(path.stat())==files.metadata(observed)
    assert service.read_registered_timesheet_export(c.export_id)==c


def test_final_verify_failure_and_owned_cleanup_diagnostics(registered,monkeypatch):
    service,store,c,path=registered;original=files.inspect;counter=[];fault=OSError('cleanup fault')
    def failed_check(target,*args):
        counter.append(1)
        if len(counter)==2:return files.Inspection(S.UNVERIFIABLE,str(target),error=OSError('verification unavailable'))
        return original(target,*args)
    with monkeypatch.context() as m:
        m.setattr(files,'inspect',failed_check)
        m.setattr(files,'_remove_owned',lambda *a:(_ for _ in ()).throw(fault))
        result=publish(registered)
    assert result.phase==P.PUBLISHED and not result.verified and result.error
    assert 'cleanup fault' in ' '.join(result.error.__notes__)
    assert path.read_bytes()==c.report_utf8
    assert publish(registered).phase==P.REUSED


def test_verified_completion_survives_stage_cleanup_failure(registered,monkeypatch):
    service,store,c,path=registered;fault=OSError('cannot remove own stage')
    monkeypatch.setattr(files,'_remove_owned',lambda *a:(_ for _ in ()).throw(fault))
    result=publish(registered)
    assert result.verified and result.error is fault and path.read_bytes()==c.report_utf8


def test_changed_stage_is_not_deleted(registered,monkeypatch):
    service,store,c,path=registered;original=files._owned;foreign=[]
    def changed(stage,created):
        if not foreign:
            foreign.append(stage);stage.rename(stage.with_suffix('.retained'));stage.write_bytes(b'foreign staging replacement')
        return original(stage,created)
    monkeypatch.setattr(files,'_owned',changed)
    result=publish(registered)
    assert not result.verified and not path.exists()
    assert foreign[0].read_bytes()==b'foreign staging replacement'


def test_reopen_frozen_bytes_ignore_current_renderer_and_later_actual(registered,monkeypatch,tmp_path):
    service,store,c,path=registered;task=c.tasks[0].task_id
    assert publish(registered).verified
    dated(service,task,duration='2:00')
    service.rename_task(task,'Renamed',expected_version=1,request_id=uid(),action_utc_us=NOW)
    service.set_week_start(0,expected_week_start=6,request_id=uid(),action_utc_us=NOW)
    directory=store.directory;store.close();reopened=SQLiteStore(directory)
    try:
        s=TimerService(reopened)
        with monkeypatch.context() as m:
            m.setattr('chronicle.timesheet.render',lambda *a:pytest.fail('recovery rerendered'))
            m.setattr('chronicle.timesheet.calculate_daily',lambda *a,**k:pytest.fail('recovery recalculated'))
            second=tmp_path/'alternate.txt'
            result=s.materialize_registered_timesheet_export(c.export_id,second)
            assert result.verified and second.read_bytes()==path.read_bytes()==c.report_utf8
            assert s.read_registered_timesheet_export(c.export_id)==c
    finally:reopened.close()


@pytest.mark.parametrize('replacement',[False,True])
@pytest.mark.parametrize('boundary',['before','after'])
def test_process_death_at_file_publication_boundary_keeps_registered_recovery(registered,replacement,boundary):
    from test_interruptions import paused_child
    service,store,c,path=registered
    if replacement:path.write_bytes(b'old')
    before=facts(store);frozen=exports(store);directory=store.directory;store.close()
    code=r'''
import sys
import chronicle.timesheet_files as files
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
from pathlib import Path
root,identity,destination,replacement,boundary=sys.argv[1:]
store=SQLiteStore(root);service=TimerService(store)
replacement=replacement=='True'
name='replace' if replacement else 'link';original=getattr(files.os,name)
def barrier():
    print('BARRIER',flush=True);sys.stdin.readline()
def observed(*args):
    if boundary=='before':barrier()
    value=original(*args)
    if boundary=='after':barrier()
    return value
setattr(files.os,name,observed)
conflict=service.inspect_registered_export_destination(identity,destination).conflict if replacement else None
service.materialize_registered_timesheet_export(identity,destination,confirmed_overwrite=replacement,expected_conflict=conflict)
'''
    with paused_child(code,directory,c.export_id,path,replacement,boundary):pass
    reopened=SQLiteStore(directory)
    try:
        recovered=TimerService(reopened)
        assert reopened.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert facts(reopened)==before and exports(reopened)==frozen
        assert recovered.read_registered_timesheet_export(c.export_id)==c
        if boundary=='after':assert path.read_bytes()==c.report_utf8
        elif replacement:assert path.read_bytes()==b'old'
        else:assert not path.exists()
        conflict=recovered.inspect_registered_export_destination(c.export_id,path).conflict if replacement and boundary=='before' else None
        result=recovered.materialize_registered_timesheet_export(c.export_id,path,confirmed_overwrite=conflict is not None,expected_conflict=conflict)
        assert result.verified and path.read_bytes()==c.report_utf8
        assert facts(reopened)==before and exports(reopened)==frozen
    finally:reopened.close()


def test_inspection_read_error_preserves_primary_when_close_also_fails(registered,monkeypatch):
    service,store,c,path=registered;path.write_bytes(b'conflict')
    fault=OSError('original read failure');close=files.os.close
    def failed_close(fd):close(fd);raise OSError('secondary close failure')
    with monkeypatch.context() as m:
        m.setattr(files.os,'read',lambda *a:(_ for _ in ()).throw(fault))
        m.setattr(files.os,'close',failed_close)
        result=inspect(registered)
    assert result.state==S.UNVERIFIABLE and result.error is fault and result.conflict is None
    assert any('secondary close failure' in note for note in fault.__notes__)
