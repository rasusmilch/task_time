"""Immutable revisions, exact retries, stale guards and reopen validation."""
from dataclasses import replace
import sqlite3

import pytest

from chronicle.records import Request
from chronicle.sqlite_store import SQLiteStore
from conftest import NOW, uid
from test_manual_work import H, M, dated, timed, facts
from test_services import FaultConnection


def closed_precise(service,task):
    entry=uid()
    assert service.start_timer(task,entry,expected_task_version=1,request_id=uid(),action_utc_us=NOW-H+123456).status=='committed'
    assert service.stop_timer(entry,expected_version=1,request_id=uid(),action_utc_us=NOW-M+654321).status=='committed'
    return entry


def test_timed_precision_unchanged_changed_and_reverted_minute(service,task,store):
    entry=closed_precise(service,task)
    first=service.read_work_entry_revisions(entry)
    before=facts(store)
    kwargs=dict(expected_revision=1,request_id=uid(),action_utc_us=NOW,comment='comment-only')
    assert service.edit_closed_timed_work(task,entry,'2026-10-19','9am','2026-10-19','09:59',**kwargs).status=='unchanged'
    assert facts(store)==before
    out=service.edit_closed_timed_work(task,entry,'2026-10-19','08:30','2026-10-19','09:59',
                                     expected_revision=1,request_id=uid(),action_utc_us=NOW,comment='earlier')
    assert out.status=='committed'
    detail=service.read_work_entry_revisions(entry)
    assert detail['entry']['entry_id']==entry and detail['entry']['original_start_utc_us']==first['entry']['original_start_utc_us']
    assert detail['revisions'][0]==first['revisions'][0]
    assert detail['revisions'][1]['stop_utc_us']==first['revisions'][0]['stop_utc_us']
    # Returning text to the reviewed stored minute preserves its precise endpoint.
    before=facts(store)
    assert service.edit_closed_timed_work(task,entry,'2026-10-19','8:30am','2026-10-19','9:59am',
        expected_revision=2,request_id=uid(),action_utc_us=NOW).status=='unchanged'
    assert facts(store)==before
    assert service.edit_closed_timed_work(task,entry,'2026-10-19','08:30','2026-10-19','09:58',
        expected_revision=2,request_id=uid(),action_utc_us=NOW).status=='committed'
    detail=service.read_work_entry_revisions(entry)
    assert detail['revisions'][2]['start_utc_us']==detail['revisions'][1]['start_utc_us']


def test_date_redate_duration_noops_delete_and_reopen(service,task,store):
    entry=dated(service,task,comment='first')
    before=facts(store)
    assert service.edit_date_only_work(task,entry,' 2026-10-19 ','01:30',expected_revision=1,
        comment='comment only',request_id=uid(),action_utc_us=NOW).status=='unchanged'
    assert facts(store)==before
    assert service.edit_date_only_work(task,entry,'2026-10-20','14:00',expected_revision=1,
        comment='new day',request_id=uid(),action_utc_us=NOW).status=='committed'
    before_delete=service.read_work_entry_revisions(entry)
    request=Request.make(uid(),store.dataset_id,'delete_work_entry',NOW,task_id=task,entry_id=entry,expected_revision=2,comment='deleted')
    assert service.execute(request).status=='committed'
    detail=service.read_work_entry_revisions(entry)
    assert [r['revision'] for r in detail['revisions']]==[1,2,3]
    assert detail['revisions'][:2]==before_delete['revisions']
    assert detail['revisions'][2]['is_deleted']==1
    assert (detail['revisions'][2]['work_date'],detail['revisions'][2]['duration_us'])==('2026-10-20',14*H)
    assert service.read_current_state(cutoff_utc_us=NOW)['report']['application']['week_us']==0
    before=facts(store)
    assert service.delete_work_entry(task,entry,expected_revision=3,request_id=uid(),action_utc_us=NOW).status=='rejected'
    assert service.edit_date_only_work(task,entry,'2026-10-20','1:00',expected_revision=3,request_id=uid(),action_utc_us=NOW).status=='rejected'
    assert service.execute(request).result=={'entry_id':entry,'revision':3}
    assert facts(store)==before
    directory=store.directory; store.close()
    reopened=SQLiteStore(directory)
    try:
        from chronicle.services import TimerService
        assert TimerService(reopened).read_work_entry_revisions(entry)==detail
    finally: reopened.close()


@pytest.mark.parametrize('case',['wrong_owner','wrong_kind','stale','active'])
def test_entry_guards_never_retarget(service,task,store,case):
    entry=timed(service,task)
    if case=='wrong_kind': entry=dated(service,task)
    if case=='active':
        entry=uid(); service.start_timer(task,entry,expected_task_version=1,request_id=uid(),action_utc_us=NOW)
    before=facts(store)
    result=service.edit_closed_timed_work(uid() if case=='wrong_owner' else task,entry,'2026-10-19','08:00','2026-10-19','09:30',
        expected_revision=2 if case=='stale' else 1,request_id=uid(),action_utc_us=NOW)
    assert result.status=='rejected' and facts(store)==before
    if case=='active':
        assert service.delete_work_entry(task,entry,expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='rejected'
        assert facts(store)==before


def test_timed_delete_retains_full_values_and_original_identity(service,task,store):
    e=closed_precise(service,task)
    initial=service.read_work_entry_revisions(e)
    assert service.delete_work_entry(task,e,expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    detail=service.read_work_entry_revisions(e)
    assert detail['entry']['original_start_utc_us']==initial['entry']['original_start_utc_us']
    assert [(r['start_utc_us'],r['stop_utc_us']) for r in detail['revisions']]==[
        (initial['revisions'][0]['start_utc_us'],initial['revisions'][0]['stop_utc_us'])]*2
    assert detail['revisions'][1]['is_deleted']==1


@pytest.mark.parametrize('operation',['edit_date_only_work','delete_work_entry'])
@pytest.mark.parametrize('after',[False,True])
def test_revision_commit_failure_reconciles_exact_request(service,task,store,operation,after):
    e=dated(service,task)
    args=dict(task_id=task,entry_id=e,expected_revision=1,comment='change')
    if operation=='edit_date_only_work': args.update(work_date='2026-10-20',duration_text='2:00')
    request=Request.make(uid(),store.dataset_id,operation,NOW,**args)
    before=facts(store)
    store.connection=FaultConnection(store.connection,after=after)
    out=service.execute(request)
    assert out.status==('committed' if after else 'rolled_back')
    if not after: assert facts(store)==before
    assert service.execute(request).status=='committed'
    # Later revision/deletion cannot change historical exact reuse.
    latest=service.read_work_entry_revisions(e)
    assert len(latest['revisions'])==2
    before=facts(store)
    assert service.execute(request).result=={'entry_id':e,'revision':2}
    assert service.execute(replace(request,action_utc_us=NOW+1)).status=='rejected'
    assert facts(store)==before


def test_uncertain_initial_commit_retry_preserves_identity_and_newer_work(service,task,store,monkeypatch):
    e=uid(); r=Request.make(uid(),store.dataset_id,'add_date_only_work',NOW,task_id=task,entry_id=e,
                           work_date='2026-10-19',duration_text='1:00',comment='frozen')
    store.connection=FaultConnection(store.connection,after=True)
    original=store._probe
    with monkeypatch.context() as m:
        m.setattr(store,'_probe',lambda: (_ for _ in ()).throw(OSError('lookup unavailable')))
        assert service.execute(r).status=='unverified'
    newer=dated(service,task,duration='2:00')
    assert service.execute(r).result=={'entry_id':e,'revision':1}
    assert service.read_work_entry_revisions(newer)['revisions'][0]['duration_us']==2*H
    assert len(service.read_work_entry_revisions(e)['revisions'])==1


@pytest.mark.parametrize('damage',['gap','current','date','delete_values'])
def test_reopen_validates_revision_chains_and_dates(service,task,store,damage):
    e=dated(service,task)
    c=store.connection
    # Deliberately damaged disposable facts after dropping the relevant guard.
    if damage=='gap':
        c.execute('DROP TRIGGER immutable_work_revisions_update')
        c.execute('PRAGMA foreign_keys=OFF')
        c.execute('UPDATE work_revisions SET revision=2 WHERE entry_id=?',(e,))
    elif damage=='current':
        c.execute('DROP TRIGGER current_revision_forward'); c.execute('PRAGMA foreign_keys=OFF'); c.execute('UPDATE work_entries SET current_revision=9 WHERE entry_id=?',(e,))
    elif damage=='date':
        c.execute('DROP TRIGGER immutable_work_revisions_update'); c.execute("UPDATE work_revisions SET work_date='2026-02-30' WHERE entry_id=?",(e,))
    else:
        service.delete_work_entry(task,e,expected_revision=1,request_id=uid(),action_utc_us=NOW)
        c.execute('DROP TRIGGER immutable_work_revisions_update'); c.execute('UPDATE work_revisions SET duration_us=? WHERE entry_id=? AND revision=2',(2*H,e))
    # Restore exact schema guard so validation reaches data rather than only signature rejection.
    from chronicle.sqlite_store import schema_statements
    for statement in schema_statements():
        if statement.startswith('CREATE TRIGGER immutable_work_revisions_update'):
            if damage in ('gap','date','delete_values'): c.execute(statement)
        if damage=='current' and statement.startswith('CREATE TRIGGER current_revision_forward'): c.execute(statement)
    directory=store.directory;store.close()
    with pytest.raises((ValueError,sqlite3.DatabaseError)): SQLiteStore(directory)


@pytest.mark.parametrize('operation',['add_timed_work','add_date_only_work','edit_closed_timed_work','edit_date_only_work','delete_work_entry','set_week_start'])
@pytest.mark.parametrize('phase',['facts','receipt','commit_ready','committed','refresh'])
def test_mixed_operations_process_death_keep_atomic_facts(tmp_path,operation,phase):
    from test_interruptions import paused_child,TRANSACTION_CHILD,frozen_json
    from chronicle.services import TimerService
    store=SQLiteStore(tmp_path/'interrupted-mixed',create=True,timezone='America/Chicago')
    s=TimerService(store);task=uid();s.create_task(task,'Interrupted',request_id=uid(),action_utc_us=NOW)
    if operation in ('edit_date_only_work','delete_work_entry'): entry=dated(s,task)
    elif operation=='edit_closed_timed_work': entry=timed(s,task)
    else: entry=uid()
    args=dict(task_id=task,entry_id=entry,comment='exact')
    if operation in ('add_timed_work','edit_closed_timed_work'):
        args.update(start_date='2026-10-19',start_time='07:00',end_date='2026-10-19',end_time='09:00',start_occurrence=None,end_occurrence=None)
    if operation in ('add_date_only_work','edit_date_only_work'):
        args.update(work_date='2026-10-20',duration_text='2:00')
    if operation in ('edit_closed_timed_work','edit_date_only_work','delete_work_entry'):args['expected_revision']=1
    if operation=='set_week_start':args=dict(week_start=0,expected_week_start=6)
    request=Request.make(uid(),store.dataset_id,operation,NOW,**args)
    before=facts(store);directory=store.directory;store.close()
    code=TRANSACTION_CHILD.replace("'DELETE FROM active_'", "'DELETE FROM active_', 'UPDATE dataset_meta'")
    with paused_child(code,directory,phase,frozen_json(request)):
        pass
    reopened=SQLiteStore(directory)
    try:
        s=TimerService(reopened)
        assert reopened.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        committed=phase in ('committed','refresh')
        assert s.reconcile_request(request).status==('committed' if committed else 'absent')
        if not committed:assert facts(reopened)==before
        result=s.execute(request);assert result.status=='committed'
        final=facts(reopened)
        assert s.execute(request).result==result.result and facts(reopened)==final
        assert len(final['committed_requests'])==len(before['committed_requests'])+1
    finally:reopened.close()
