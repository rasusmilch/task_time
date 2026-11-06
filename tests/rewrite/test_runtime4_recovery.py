"""Real paired hot-journal recovery and fail-closed original-file preservation."""
from pathlib import Path
import os,sqlite3
import pytest
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
from chronicle.schema4_runtime_service import Schema4RuntimeService
from chronicle.recovery_preflight import PrivateRecovery
from chronicle.timesheet_files import metadata
from runtime4_cases import Runtime,uid,NOW
from test_backup_restore import logical
from test_interruptions import paused_child,SPILLED_TRANSACTION_CHILD


def pair(path):
    return {p.name:dict(bytes=p.read_bytes(),metadata=metadata(p.stat())) for p in (path,Path(str(path)+'-journal'))}


@pytest.fixture(params=[(3,'spill'),(4,'spill'),(3,'commit delete denial')])
def hot(request,tmp_path):
    version,mode=(request.param,'spill') if type(request.param) is int else request.param
    if mode=='commit delete denial' and os.name!='posix':
        pytest.skip('Real directory-unlink denial control requires POSIX; native Windows evidence remains separate')
    directory=tmp_path/'original'
    s=SQLiteStore(directory,create=True,timezone='America/Chicago',schema_version=version)
    if version==4:
        h=Runtime(s);key=h.task(name='Original'*12000)
        h.send('add_date_only_work',task_id=key,entry_id=uid(),work_date='2026-10-19',duration_text='0:15',comment='Retained protected work')
        h.send('start_timer',task_id=key,entry_id=uid(),expected_task_version=1)
    else:assert TimerService(s).create_task(uid(),'Original'*12000,request_id=uid(),action_utc_us=NOW).status=='committed'
    facts=logical(s.path);path=s.path;s.close()
    # Genuine SQLite undo evidence, with an unrecovered page-1 marker that lies
    # about a schema-3 committed image. The private recovery must discover 3.
    code=SPILLED_TRANSACTION_CHILD.replace('PRAGMA application_id=123','PRAGMA application_id=0x4348524E').replace('PRAGMA user_version=99999','PRAGMA user_version=4')
    if mode=='commit delete denial':
        # Force an actual SQLite COMMIT journal-unlink failure on this disposable
        # directory. Main page 1 reaches version 4 while the genuine hot undo
        # journal still restores committed version 3. No rollback bytes are made
        # up, edited or parsed by the application/test.
        code=code.replace('import sqlite3, sys','import os, sqlite3, sys')
        code=code.replace("print('BARRIER', flush=True)\nsys.stdin.readline()", """os.chmod(Path(sys.argv[1]),0o500)
try:
    c.execute('COMMIT')
except sqlite3.OperationalError:
    print('BARRIER',flush=True)
    sys.stdin.readline()
else:
    raise AssertionError('Native unlink denial was not established')
os._exit(0)""")
    before=path.read_bytes()
    try:
        with paused_child(code,directory,'header'):
            assert path.read_bytes()!=before
    finally:directory.chmod(0o700)
    assert Path(str(path)+'-journal').stat().st_size>512
    assert int.from_bytes(path.read_bytes()[60:64],'big')==(4 if mode=='commit delete denial' else version)
    yield version,directory,path,facts,pair(path)


def test_hot_schema_identity_is_established_on_private_pair_before_original_recovery(hot,monkeypatch):
    version,directory,path,facts,before=hot;opened=[];connect=SQLiteStore._connect
    def observed(self):opened.append(self.path);return connect(self)
    monkeypatch.setattr(SQLiteStore,'_connect',observed)
    if version==3:
        with pytest.raises(ValueError,match='require schema 4'):SQLiteStore(directory)
        assert not opened and pair(path)==before
    else:
        s=SQLiteStore(directory)
        try:
            assert opened==[path] and logical(path)==facts
            assert not Path(str(path)+'-journal').exists()
            state=Schema4RuntimeService(s).read_current_state(cutoff_utc_us=NOW+10000000)
            assert state['semantic_verified'] and state['ordinary_startup_permitted']
            assert state['active']['entry_id']==facts['active_timer'][0][1]
        finally:s.close()


@pytest.mark.parametrize('fault',['copy','changed journal','validation','cleanup'])
def test_private_failure_never_opens_original_writable(hot,monkeypatch,fault):
    version,directory,path,facts,before=hot
    monkeypatch.setattr(SQLiteStore,'_connect',lambda *a:pytest.fail('Original opened before successful private admission'))
    if fault=='copy':monkeypatch.setattr(PrivateRecovery,'_copy',lambda *a:(_ for _ in ()).throw(OSError('Paired copy fault')))
    elif fault=='changed journal':monkeypatch.setattr(PrivateRecovery,'unchanged',lambda *a:(_ for _ in ()).throw(OSError('Journal stability fault')))
    elif fault=='validation':
        from chronicle.schema_policy import SchemaPolicy
        monkeypatch.setattr(SchemaPolicy,'verify',lambda *a,**k:(_ for _ in ()).throw(ValueError('Private semantic failure')))
    else:
        close=PrivateRecovery.close;calls=[]
        def fail_once(self):
            if not calls:calls.append(True);raise OSError('Private cleanup fault')
            return close(self)
        monkeypatch.setattr(PrivateRecovery,'close',fail_once)
    with pytest.raises((ValueError,OSError)) as caught:SQLiteStore(directory)
    assert pair(path)==before
    owner=getattr(caught.value,'_chronicle_cleanup_store',None)
    if owner is not None:owner.close()


@pytest.mark.parametrize('hot',[4],indirect=True)
def test_persistent_private_close_failure_retains_connection_and_dataset_lock(hot,monkeypatch):
    version,directory,path,facts,before=hot
    assert version==4
    import chronicle.recovery_preflight as recovery
    connect=sqlite3.connect;release=[];connections=[]
    class CloseFault:
        def __init__(self,c):object.__setattr__(self,'c',c)
        def __getattr__(self,k):return getattr(self.c,k)
        def __setattr__(self,k,v):setattr(self.c,k,v)
        def close(self):
            if not release:raise OSError('Private connection close unverified')
            return self.c.close()
    def wrapped(*a,**k):
        c=CloseFault(connect(*a,**k));connections.append(c);return c
    monkeypatch.setattr(recovery.sqlite3,'connect',wrapped)
    with pytest.raises(OSError) as caught:SQLiteStore(directory)
    owner=caught.value._chronicle_cleanup_store
    try:
        assert owner._private_recovery.connection is connections[0] and owner.lock.file is not None
        assert pair(path)==before
    finally:
        release.append(True);owner.close()
    assert owner.lock.file is None and owner._private_recovery is None


@pytest.mark.parametrize('hot',[4],indirect=True)
@pytest.mark.parametrize('phase',['paired copy','verified private recovery'])
def test_process_death_during_private_preflight_never_recovers_original(hot,tmp_path,phase):
    version,directory,path,facts,before=hot
    private=tmp_path/'owned-private-root';private.mkdir()
    code=r'''
import sys,tempfile
from pathlib import Path
from chronicle.sqlite_store import SQLiteStore
from chronicle.recovery_preflight import PrivateRecovery
from chronicle.schema_policy import SchemaPolicy
path,phase,private=sys.argv[1:];tempfile.tempdir=private
calls=[]
def barrier():print('BARRIER',flush=True);sys.stdin.readline()
if phase=='paired copy':
 copy=PrivateRecovery._copy
 def paired(self,*a):
  copy(self,*a);calls.append(True)
  if len(calls)==2:barrier()
 PrivateRecovery._copy=paired
else:
 verify=SchemaPolicy.verify
 def checked(self,c,**kw):
  result=verify(self,c,**kw)
  if Path(c.execute('PRAGMA database_list').fetchone()[2]).is_relative_to(private):barrier()
  return result
 SchemaPolicy.verify=checked
SQLiteStore(path)
'''
    with paused_child(code,directory,phase,private):pass
    assert pair(path)==before
    # Killed processes cannot run application cleanup. Parent owns this isolated
    # fixture root and removes only the two exact possible copied filenames.
    folders=list(private.iterdir());assert len(folders)==1 and folders[0].is_dir()
    for item in folders[0].iterdir():
        assert item.name in ('chronicle.sqlite3','chronicle.sqlite3-journal') and item.is_file()
        item.unlink()
    folders[0].rmdir();private.rmdir()
    s=SQLiteStore(directory)
    try:assert logical(s.path)==facts
    finally:s.close()


@pytest.mark.parametrize('kind',['foreign','future','schema','semantic','missing journal','unsuitable journal','unreadable journal'])
def test_incompatible_or_unproven_hot_image_never_opens_original_writable(tmp_path,monkeypatch,kind):
    from test_interruptions import leave_hot_journal
    from chronicle import schema_profiles
    directory=tmp_path/'incompatible';s=SQLiteStore(directory,create=True,timezone='America/Chicago');h=Runtime(s)
    h.task(name='Original'*12000)
    if kind=='foreign':s.connection.execute('PRAGMA application_id=123')
    elif kind=='future':s.connection.execute('PRAGMA user_version=5')
    elif kind=='schema':s.connection.execute('DROP TRIGGER active_only_open')
    elif kind=='semantic':
        s.connection.execute('DROP TRIGGER immutable_committed_requests_update')
        s.connection.execute('UPDATE committed_requests SET result_bytes=?',(b'{}',))
        s.connection.execute(next(q for q in schema_profiles.schema_statements() if q.startswith('CREATE TRIGGER immutable_committed_requests_update')))
    path=s.path;s.close();leave_hot_journal(directory);journal=Path(str(path)+'-journal')
    if kind=='missing journal':journal.unlink()  # Deliberate disposable fixture damage, never application repair.
    if kind=='unsuitable journal':journal.rename(directory/'retained-journal');journal.mkdir()
    def files():return {p.name:(p.read_bytes(),metadata(p.stat())) for p in directory.iterdir() if p.is_file() and p.name!='.chronicle.lock'}
    before=files();opened=[]
    monkeypatch.setattr(SQLiteStore,'_connect',lambda *a:opened.append(True) or pytest.fail('Original incompatible image opened writable'))
    if kind=='unreadable journal':
        open_file=os.open
        def denied(file,*a,**k):
            if Path(file)==journal:raise PermissionError('Original journal unreadable')
            return open_file(file,*a,**k)
        monkeypatch.setattr(os,'open',denied)
    with pytest.raises((ValueError,OSError,sqlite3.DatabaseError)):SQLiteStore(directory)
    assert not opened and files()==before
