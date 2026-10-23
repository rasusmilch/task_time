"""Observation contracts; synthetic Windows fields are not NTFS qualification."""
from functools import partial
import hashlib
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from chronicle import backup_restore as br, sqlite_store as db, timesheet_files as files


def observation(**changes):
    fields = dict(st_dev=123, st_ino=456, st_mode=stat.S_IFREG | 0o600,
                  st_size=10, st_mtime_ns=200, st_ctime_ns=300)
    fields.update(changes)
    return SimpleNamespace(**fields)


def test_raw_six_field_contract_and_unchanged_posix_observations(tmp_path):
    path = tmp_path / 'sample'; path.write_bytes(b'complete bytes')
    with path.open('rb') as handle:
        p, h = path.lstat(), os.fstat(handle.fileno())
        assert files.metadata(p) == (p.st_dev,p.st_ino,p.st_mode,p.st_size,p.st_mtime_ns,p.st_ctime_ns)
        assert files.same_file_identity(p,h)
        # A real path/handle POSIX equality assertion is native POSIX evidence.
        if os.name != 'nt':
            assert files.path_matches_handle(p,h,windows=False)
        assert files.same_domain_metadata(p,path.lstat())
        assert files.same_domain_metadata(h,os.fstat(handle.fileno()))


def test_windows_creation_change_time_and_executable_synthesis_are_cross_domain_only():
    path = observation(st_ctime_ns=100,st_birthtime_ns=100,st_mode=stat.S_IFREG | 0o777)
    handle = observation(st_ctime_ns=900,st_birthtime_ns=100,st_mode=stat.S_IFREG | 0o666)
    assert files.path_matches_handle(path,handle,windows=True)
    assert not files.path_matches_handle(path,handle,windows=False)
    assert not files.same_domain_metadata(path,handle)
    assert files.metadata(path)[5] == 100 and files.metadata(handle)[5] == 900


@pytest.mark.parametrize('field,value',[
    ('st_dev',124),('st_ino',457),('st_mode',stat.S_IFDIR | 0o600),
    ('st_mode',stat.S_IFLNK | 0o600),('st_mode',stat.S_IFREG | 0o400),
    ('st_mode',stat.S_IFREG | 0o610),('st_size',11),('st_mtime_ns',201),
    ('st_birthtime_ns',101),
])
def test_windows_cross_domain_unexplained_differences_reject(field,value):
    path, handle = observation(st_birthtime_ns=100), observation(st_birthtime_ns=100)
    setattr(path,field,value)
    assert not files.path_matches_handle(path,handle,windows=True)


@pytest.mark.parametrize('field',['st_dev','st_ino'])
@pytest.mark.parametrize('value',[None,0,-1,False,'123'])
def test_unusable_identity_never_establishes_ownership_even_if_equal(field,value):
    a,b = observation(**{field:value}),observation(**{field:value})
    assert not files.same_file_identity(a,b)
    assert not files.same_domain_metadata(a,b)
    for windows in (False,True):
        assert not files.path_matches_handle(a,b,windows=windows)


def test_missing_identity_and_unsuitable_objects_cannot_bind():
    a,b = observation(),observation()
    del a.st_ino
    assert not files.same_file_identity(a,b)
    for mode in (stat.S_IFIFO,stat.S_IFLNK,stat.S_IFCHR,0):
        assert not files.same_file_identity(observation(st_mode=mode),observation(st_mode=mode))


@pytest.mark.parametrize('field',['st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns'])
def test_each_raw_field_remains_required_for_same_domain_stability(field):
    a,b = observation(),observation()
    setattr(b,field,getattr(b,field)+1)
    assert not files.same_domain_metadata(a,b)
    assert not files.path_matches_handle(a,b,windows=False)


def test_windows_birthtime_is_optional_but_not_allowed_to_disagree():
    assert files.path_matches_handle(observation(st_birthtime_ns=100),observation(st_ctime_ns=900),windows=True)
    assert not files.path_matches_handle(observation(st_birthtime_ns=100),observation(st_birthtime_ns=101),windows=True)
    assert not files.path_matches_handle(observation(st_mode=stat.S_IFREG | 0o600),
                                         observation(st_mode=stat.S_IFREG | 0o711),windows=True)


@pytest.mark.parametrize('change',['path','handle','incomplete','growing'])
def test_report_read_requires_both_domains_stable_and_complete(tmp_path,monkeypatch,change):
    path = tmp_path/'report'; payload=b'known bytes';path.write_bytes(payload)
    initial=path.lstat();lstat=Path.lstat;fstat=os.fstat;read=os.read;seen=[]
    if change=='path':
        def replaced(p,*a,**k):
            value=lstat(p,*a,**k)
            if p==path:
                fields=dict(zip(('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns'),files.metadata(value)))
                fields['st_ino']+=1
                return SimpleNamespace(**fields)
            return value
        monkeypatch.setattr(Path,'lstat',replaced)
    elif change=='handle':
        def modified(fd):
            value=fstat(fd);seen.append(fd)
            if len(seen)==2:
                fields=dict(zip(('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns'),files.metadata(value)))
                fields['st_ctime_ns']+=1
                return SimpleNamespace(**fields)
            return value
        monkeypatch.setattr(os,'fstat',modified)
    else:
        def content(fd,n):
            if change=='incomplete':return b''
            # Real complete bytes followed by one extra byte, without changing
            # metadata: the bounded read itself must reject the extra content.
            chunk=read(fd,n)
            return chunk if chunk else b'x'
        monkeypatch.setattr(os,'read',content)
    with pytest.raises(OSError):
        files._read_regular(path,initial,payload,hashlib.sha256(payload).hexdigest())


def test_synthetic_windows_binding_through_actual_report_startup_backup_and_restore(store,tmp_path,monkeypatch):
    """Exercise production call sites with independently stable descriptor ctime.

    No platform identity is patched. Real file bytes, SQLite and hard links are
    used; only descriptor observations and the comparison's Windows switch are
    synthetic. Native identity availability/semantics remain unverified.
    """
    directory=store.directory;identity=store.dataset_id;store.close()
    fstat=os.fstat
    binding=files.path_matches_handle
    def descriptor(fd):
        fields=dict(vars(observation()))
        fields.update(zip(('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns'),files.metadata(fstat(fd))))
        fields['st_ctime_ns']+=1000000
        return SimpleNamespace(**fields)
    with monkeypatch.context() as m:
        m.setattr(os,'fstat',descriptor)
        for module in (files,br,db):
            m.setattr(module,'path_matches_handle',partial(binding,windows=True))
        reopened=db.SQLiteStore(directory)
        try:
            assert reopened.dataset_id==identity
            assert br.inspect_dataset(directory).ordinary_startup_permitted
            result=reopened.backup(tmp_path/'image.sqlite3')
            assert result.verified,result.error
            assert br.restore_image(result.destination,tmp_path/'restored').verified
            payload=b'frozen report';digest=hashlib.sha256(payload).hexdigest();target=tmp_path/'report'
            assert files.materialize('test',target,payload,digest,directory).verified
            assert files.materialize('test',target,payload,digest,directory).phase==files.PublicationPhase.REUSED
            target.write_bytes(b'conflicting bytes')
            conflict=files.inspect(target,payload,digest).conflict
            assert conflict is not None and len(conflict.metadata)==6
            assert files.materialize('test',target,payload,digest,directory,
                                     confirmed_overwrite=True,expected_conflict=conflict).verified
            assert target.read_bytes()==payload
        finally:reopened.close()
    restored=db.SQLiteStore(tmp_path/'restored')
    try:assert restored.dataset_id==identity
    finally:restored.close()


@pytest.mark.parametrize('operation',['admission','fingerprint','comparison','sync'])
@pytest.mark.parametrize('domain',['path','handle'])
def test_storage_paths_retain_complete_independent_domain_stability(store,tmp_path,monkeypatch,operation,domain):
    target=store.path
    before=target.read_bytes();fstat=os.fstat;lstat=Path.lstat;seen=[]
    with target.open('rb') as handle:created=fstat(handle.fileno())
    def changed(value):
        fields=dict(zip(('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns'),files.metadata(value)))
        fields['st_ctime_ns']+=1
        return SimpleNamespace(**fields)
    def observed_path(path,*a,**k):
        value=lstat(path,*a,**k)
        if path==target:
            seen.append(True)
            if len(seen)>=2:return changed(value)
        return value
    def observed_handle(fd):
        value=fstat(fd)
        if (value.st_dev,value.st_ino)==(created.st_dev,created.st_ino):
            seen.append(True)
            if len(seen)>=2:return changed(value)
        return value
    with monkeypatch.context() as m:
        if domain=='path':m.setattr(Path,'lstat',observed_path)
        else:m.setattr(os,'fstat',observed_handle)
        with pytest.raises(OSError):
            if operation=='admission':store._admit_existing()
            elif operation=='fingerprint':br._fingerprint(target)
            elif operation=='comparison':br._same_content(target,target)
            else:br._sync(target,created)
    assert target.read_bytes()==before
