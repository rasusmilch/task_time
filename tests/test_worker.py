from contextlib import contextmanager
import threading
import pytest
from chronicle.worker import DatabaseWorker,Message
from chronicle.sqlite_store import SQLiteStore
from chronicle.records import Outcome,Request
from conftest import uid,NOW


@contextmanager
def running(directory,create=True):
    worker=DatabaseWorker(directory,create=create,timezone='America/Chicago' if create else None);worker.start()
    try:yield worker
    finally:
        if worker.is_alive():worker.requests.put(Message('shutdown'))
        worker.join(15);assert not worker.is_alive()


def exchange(worker,kind,value=None,token=1):
    worker.requests.put(Message(kind,token,value));message=worker.results.get(timeout=15)
    assert message.kind==kind and message.token==token
    return message


def test_actual_worker_ready_one_owner_serialized_request_and_shutdown(tmp_path,monkeypatch):
    observed=[];original=SQLiteStore.__init__
    def init(self,*a,**kw):
        original(self,*a,**kw);observed.append((threading.get_ident(),self))
    monkeypatch.setattr(SQLiteStore,'__init__',init)
    with running(tmp_path/'worker') as w:
        ready=w.results.get(timeout=15);assert ready.kind=='ready'
        assert ready.value['schema_version']==5 and ready.value['semantic_verified'] and ready.value['ordinary_startup_permitted']
        assert len(observed)==1 and observed[0][0]==w.ident!=threading.get_ident()
        r=Request.make(uid(),ready.value['dataset_id'],'create_project',NOW,project_id=uid(),name='Worker owned')
        result=exchange(w,'mutate',r);assert result.request is r and result.value.status=='committed'
        state=exchange(w,'read',NOW+1_000_000).value;assert len(state['projects'])==1
        with pytest.raises(OSError):SQLiteStore(tmp_path/'worker')
    assert observed[0][1].connection is None and observed[0][1].lock.file is None
    assert w.results.get(timeout=5).kind=='stopped'


def test_worker_refuses_damaged_semantics_before_ready(tmp_path):
    s=SQLiteStore(tmp_path/'bad',create=True,timezone='UTC');s.connection.execute('DROP TRIGGER active_only_open');s.close()
    with running(tmp_path/'bad',False) as w:
        failed=w.results.get(timeout=15);assert failed.kind=='startup_failed' and isinstance(failed.value,ValueError)
        assert w.results.get(timeout=15).kind=='stopped'


def test_worker_original_request_uncertainty_isolation(tmp_path,monkeypatch):
    original=SQLiteStore._commit;lost=[]
    def fault(self,c):
        original(self,c)
        if not lost:lost.append(True);raise OSError('Lost acknowledgement')
    monkeypatch.setattr(SQLiteStore,'_commit',fault)
    with running(tmp_path/'unknown') as w:
        ready=w.results.get(timeout=15);r=Request.make(uid(),ready.value['dataset_id'],'create_project',NOW,project_id=uid(),name='Original')
        assert exchange(w,'mutate',r).value.status=='unverified'
        other=Request.make(uid(),ready.value['dataset_id'],'create_project',NOW+1,project_id=uid(),name='Blocked')
        assert exchange(w,'mutate',other).value.status=='unavailable'
        assert exchange(w,'reconcile',other).value.status=='unavailable'
        assert exchange(w,'reconcile',r).value.status=='committed'
        assert len(exchange(w,'read',NOW+2).value['projects'])==1
