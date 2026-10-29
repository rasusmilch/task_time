"""Task-scoped daily portions retain complete immutable entry identity."""
from collections import defaultdict

import pytest
from conftest import NOW,uid
from test_manual_work import H,M,dated,timed,stamp,facts


def test_portions_keep_full_identity_offsets_precision_and_scope(service,task,store):
    e=timed(service,task,'2026-10-17','23:00','2026-10-19','01:00',comment='complete interval')
    d=dated(service,task,'2026-10-18','14:00')
    rows=service.read_task_work_history(task,cutoff_utc_us=NOW,period='all')
    pieces=[r for r in rows if r['entry_id']==e]
    assert [r['work_date'] for r in pieces]==['2026-10-19','2026-10-18','2026-10-17']
    assert [r['duration_us'] for r in pieces]==[H,24*H,H]
    assert len({r['link_identity'] for r in pieces})==1
    assert {r['revision'] for r in pieces}=={1}
    assert {r['start_utc_us'] for r in pieces}=={stamp('2026-10-17T23:00:00-05:00')}
    assert {r['stop_utc_us'] for r in pieces}=={stamp('2026-10-19T01:00:00-05:00')}
    assert {r['comment'] for r in pieces}=={'complete interval'}
    assert [(r['continues_before'],r['continues_after']) for r in reversed(pieces)]==[(False,True),(True,True),(True,False)]
    assert pieces[1]['segment_stop_utc_us']==stamp('2026-10-19T00:00:00-05:00')
    assert pieces[1]['segment_start_offset_seconds']==-5*3600
    dated_row=next(r for r in rows if r['entry_id']==d)
    assert dated_row['kind']=='date_only' and dated_row['link_identity'] is None
    assert dated_row['segment_start_utc_us'] is dated_row['stop_utc_us'] is None
    assert dated_row['duration_us']==14*H
    custom=service.read_task_work_history(task,cutoff_utc_us=NOW,period='custom',start_date='2026-10-18',end_date='2026-10-18')
    assert custom==[r for r in rows if r['work_date']=='2026-10-18']
    current=service.read_task_work_history(task,cutoff_utc_us=NOW)
    sums=defaultdict(int)
    for r in current: sums[r['work_date']]+=r['duration_us']
    assert dict(sums)==service.read_current_state(cutoff_utc_us=NOW)['report']['tasks'][task]['daily_us']
    rows[0]['comment']='mutated detached row'
    assert service.read_task_work_history(task,cutoff_utc_us=NOW,period='all')[0]['comment']!='mutated detached row'


def test_running_cutoff_and_active_audit_never_save_a_stop(service,task,store):
    e=uid(); start=NOW-H+123456
    service.start_timer(task,e,expected_task_version=1,request_id=uid(),action_utc_us=start)
    service.correct_active_start(e,'2026-10-19','08:30',expected_version=1,comment='actual start',request_id=uid(),action_utc_us=NOW)
    before=facts(store)
    rows=service.read_task_work_history(task,cutoff_utc_us=NOW,period='all')
    assert len(rows)==1
    r=rows[0]
    assert r['entry_id']==e and r['is_running'] and r['revision'] is None and r['active_version']==2
    assert r['stop_utc_us'] is None and r['segment_stop_utc_us']==NOW
    assert r['original_start_utc_us']==start and r['duration_us']==90*M
    assert r['comment']=='actual start' and r['audit_utc_us']==NOW
    assert facts(store)==before and not before['work_revisions']


def test_retained_task_deleted_effective_work_and_revision_details(service,task,store):
    e=dated(service,task)
    service.edit_date_only_work(task,e,'2026-10-20','2:00',expected_revision=1,request_id=uid(),action_utc_us=NOW)
    store.connection.execute('UPDATE tasks SET is_archived=1,archived_at_utc_us=0 WHERE task_id=?',(task,))
    assert service.read_task_work_history(task,cutoff_utc_us=NOW)[0]['duration_us']==2*H
    service.delete_work_entry(task,e,expected_revision=2,request_id=uid(),action_utc_us=NOW)
    assert service.read_task_work_history(task,cutoff_utc_us=NOW,period='all')==[]
    detail=service.read_work_entry_revisions(e)
    assert [r['revision'] for r in detail['revisions']]==[1,2,3]
    assert [r['is_deleted'] for r in detail['revisions']]==[0,0,1]
    detail['revisions'].clear()
    assert len(service.read_work_entry_revisions(e)['revisions'])==3


@pytest.mark.parametrize('options',[
    dict(period='custom',start_date='2026-10-20',end_date='2026-10-19'),
    dict(period='custom',start_date='2026-10-19'),dict(period='custom',start_date='2026-02-30',end_date='2026-03-01'),
    dict(period='custom',start_date='9999-12-31',end_date='9999-12-31'),
    dict(period='all',start_date='2026-10-19'),dict(period='current_week',end_date='2026-10-19'),dict(period='bad')])
def test_invalid_history_requests_do_not_write(service,task,store,options):
    before=facts(store)
    with pytest.raises(ValueError): service.read_task_work_history(task,cutoff_utc_us=NOW,**options)
    assert facts(store)==before


def test_earlier_observation_clips_timed_but_never_dated_work(service,task):
    e=timed(service,task)
    d=dated(service,task,'2026-10-24','14:00')
    rows=service.read_task_work_history(task,cutoff_utc_us=NOW-3*H)
    assert [r['entry_id'] for r in rows]==[d]
    rows=service.read_task_work_history(task,cutoff_utc_us=NOW-H-30*M)
    assert next(r for r in rows if r['entry_id']==e)['duration_us']==30*M
    assert next(r for r in rows if r['entry_id']==e)['stop_utc_us']==NOW-H


def test_repeat_offsets_and_missing_identities(service,task):
    cutoff=stamp('2026-11-01T10:00:00+00:00')
    e=timed(service,task,'2026-11-01','01:30','2026-11-01','01:30',now=cutoff,start_occurrence='first',end_occurrence='second')
    r=service.read_task_work_history(task,cutoff_utc_us=cutoff)[0]
    assert r['duration_us']==H and r['segment_start_offset_seconds']==-5*3600 and r['segment_stop_offset_seconds']==-6*3600
    for invalid in (uid(),'missing',None):
        with pytest.raises(ValueError): service.read_task_work_history(invalid,cutoff_utc_us=NOW)
        with pytest.raises(ValueError): service.read_work_entry_revisions(invalid)


def test_just_started_timer_is_observed_without_inventing_closed_work(service,task,store):
    e=uid();service.start_timer(task,e,expected_task_version=1,request_id=uid(),action_utc_us=NOW)
    before=facts(store)
    rows=service.read_task_work_history(task,cutoff_utc_us=NOW)
    assert len(rows)==1 and rows[0]['entry_id']==e and rows[0]['is_running']
    assert rows[0]['duration_us']==0 and rows[0]['stop_utc_us'] is None
    assert rows[0]['segment_start_utc_us']==rows[0]['segment_stop_utc_us']==NOW
    assert service.read_current_state(cutoff_utc_us=NOW)['report']['application']['today_us']==0
    assert facts(store)==before
