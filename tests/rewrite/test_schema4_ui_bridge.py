"""Real threaded Message/SQLite controls; these do not claim connected Tk."""
from threading import get_ident
import pytest
from chronicle.worker import Message
from chronicle.records import Request,Outcome
from schema4_ui_bridge import CandidateBridge
from schema4_cases import adapter,project,task,dated,snapshot,uid,NOW,export,manual


def exchange(worker,kind,value=None,token=1):
    worker.requests.put(Message(kind,token,value));message=worker.results.get(timeout=10)
    assert message.kind==kind and message.token==token
    return message


@pytest.fixture
def bridge(adapter):
    worker=CandidateBridge(adapter);worker.start();ready=worker.results.get(timeout=10)
    assert ready.kind=='ready' and ready.value['schema_version']==4 and ready.value['candidate_verified'] is True
    try:yield worker,ready
    finally:
        worker.requests.put(Message('shutdown'));worker.join(timeout=10);assert not worker.is_alive()
        assert worker.adapter.retired is None


def test_real_thread_exact_request_readiness_snapshot_and_unsupported_message(bridge):
    w,ready=bridge;a=w.adapter
    r=Request.make(uid(),a.context.dataset_id,'create_project',NOW,project_id=uid(),name='Direct runtime')
    result=exchange(w,'mutate',r,19)
    assert result.request is r and result.value.status=='committed'
    state=exchange(w,'read',NOW,20).value
    assert state['projects'][0]['project_id']==r.args()['project_id'] and state['schema_version']==4
    assert state['report']['application']['today_us']==0
    assert exchange(w,'reconcile',r,21).value.result==result.value.result
    refused=exchange(w,'unapproved',None,22).value
    assert isinstance(refused,Outcome) and refused.status=='unavailable'
    assert all(thread!=get_ident() for thread,_ in w.handled)


def test_real_bridge_delete_no_receipt_and_no_reconcile(bridge):
    w,_=bridge;a=w.adapter;r=Request.make(uid(),a.context.dataset_id,'create_project',NOW,project_id=uid(),name='Unused')
    assert exchange(w,'mutate',r).value.status=='committed'
    review=exchange(w,'delete_preview',dict(entity_type='project',entity_id=r.args()['project_id'])).value
    deletion=Request.make(uid(),a.context.dataset_id,'delete_project',NOW,project_id=r.args()['project_id'],expected_version=1,review=review,confirmed_text='DELETE')
    assert exchange(w,'mutate',deletion).value.status=='committed'
    assert exchange(w,'reconcile',deletion).value.status=='unverified'
    presence=exchange(w,'delete_presence',dict(entity_type='project',entity_id=r.args()['project_id'])).value
    assert not presence['present'] and presence['historical_outcome_verified'] is False


def test_rich_read_messages_preserve_frozen_bytes_and_direct_scope(adapter):
    a=adapter;p=project(a);q=project(a,p);t=task(a,q);entry=dated(a,t);child=task(a,q,t);dated(a,child)
    frozen=export(a);manual(a,t);before=snapshot(a);w=CandidateBridge(a);w.start();assert w.results.get(timeout=10).kind=='ready'
    try:
        direct=exchange(w,'history_snapshot',dict(task_id=t,cutoff_utc_us=NOW,period='all')).value
        assert len(direct['rows'])==1 and direct['rows'][0]['entry_id']==entry
        choices=exchange(w,'timesheet_tasks').value
        assert len(choices['projects'])==2 and {r['task_id'] for r in choices['tasks']}=={t,child}
        selected=exchange(w,'timesheet_preview',dict(export_id=uid(),cutoff_utc_us=NOW,scope_kind='selected',task_ids=(t,))).value
        assert [r.task_id for r in selected.tasks]==[t]
        assert exchange(w,'timesheet_export',frozen.export_id).value.report_utf8==frozen.report_utf8
        assert exchange(w,'polr_manual',dict(task_id=t,work_date='2026-10-19',cutoff_utc_us=NOW)).value['confirmed_quarters']==0
        assert exchange(w,'polr_reconciliation',dict(cutoff_utc_us=NOW)).value['daily_cells']
    finally:w.requests.put(Message('shutdown'));w.join(timeout=10);assert not w.is_alive()
    assert snapshot(a)==before


def test_bridge_lost_delete_ack_blocks_all_mutation_and_requires_exit(adapter):
    a=adapter;p=project(a)
    def checkpoint(stage,c):
        if stage=='after_commit':raise OSError('Original lost Delete acknowledgement')
    a.checkpoint=checkpoint;w=CandidateBridge(a);w.start();assert w.results.get(timeout=10).kind=='ready'
    try:
        review=exchange(w,'delete_preview',dict(entity_type='project',entity_id=p)).value
        request=Request.make(uid(),a.context.dataset_id,'delete_project',NOW,project_id=p,expected_version=1,review=review,confirmed_text='DELETE')
        result=exchange(w,'mutate',request).value
        assert result.status=='unverified' and 'Original lost' in str(result.error)
        assert exchange(w,'reconcile',request).value.status=='unverified'
        next_request=Request.make(uid(),a.context.dataset_id,'create_project',NOW,project_id=uid(),name='Blocked')
        assert exchange(w,'mutate',next_request).value.status=='unverified'
        presence=exchange(w,'delete_presence',dict(entity_type='project',entity_id=p)).value
        assert not presence['present'] and not presence['historical_outcome_verified']
    finally:w.requests.put(Message('shutdown'));w.join(timeout=10);assert not w.is_alive()


def test_bridge_startup_close_failure_retains_and_verifies_owning_cleanup(adapter):
    connect=adapter.connect;connections=[]
    class FailsOnce:
        def __init__(self,c):self.inner=c;self.calls=0
        def __getattr__(self,name):return getattr(self.inner,name)
        def close(self):
            self.calls+=1
            if self.calls==1:raise OSError('Original candidate read close failure')
            self.inner.close()
    def opened(readonly=False):
        c=FailsOnce(connect(readonly));connections.append(c);return c
    adapter.connect=opened;w=CandidateBridge(adapter);w.start()
    try:
        failed=w.results.get(timeout=10)
        assert failed.kind=='startup_failed' and 'Original candidate read close' in str(failed.value)
        assert w.results.get(timeout=10).kind=='stopped'
    finally:w.requests.put(Message('shutdown'));w.join(timeout=10);assert not w.is_alive()
    assert adapter.retired is None and len(connections)==1 and connections[0].calls==2
