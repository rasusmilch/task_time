"""Complete candidate work/configuration evidence, with real canonical receipts."""
from dataclasses import replace
import json
import pytest
from schema4_cases import *
from test_project_movement import review


@pytest.fixture
def rich(adapter):
    a=adapter;p=project(a);child=project(a,p);t=task(a,child);second=task(a,child)
    dated_entry=dated(a,t)
    send(a,'edit_date_only_work',task_id=t,entry_id=dated_entry,expected_revision=1,work_date='2026-10-20',duration_text='0:20',comment='Changed')
    send(a,'delete_work_entry',task_id=t,entry_id=dated_entry,expected_revision=2,comment='Retained deletion')
    e=uid();send(a,'start_timer',task_id=t,entry_id=e,expected_task_version=1,now=NOW-5*M)
    send(a,'correct_active_start',entry_id=e,expected_version=1,date_text='2026-10-19',time_text='09:54',occurrence=None,comment='Correction',now=NOW-4*M)
    other=uid();send(a,'switch_timer',expected_active_entry_id=e,expected_active_version=2,next_task_id=second,next_entry_id=other,expected_task_version=1,now=NOW-M)
    send(a,'stop_timer',entry_id=other,expected_version=1)
    timed=uid();send(a,'add_timed_work',task_id=t,entry_id=timed,start_date='2026-10-19',start_time='08:00',end_date='2026-10-19',end_time='08:15',start_occurrence=None,end_occurrence=None,comment='Manual')
    send(a,'edit_closed_timed_work',task_id=t,entry_id=timed,expected_revision=1,start_date='2026-10-19',start_time='08:00',end_date='2026-10-19',end_time='08:20',start_occurrence=None,end_occurrence=None,comment='Changed')
    # Former leaf retains direct recording, including deleted revisions.
    nested=task(a,child,t);lifecycle(a,'task',t)
    send(a,'set_week_start',week_start=0,expected_week_start=6)
    send(a,'dismiss_polr_reminder_today',local_date='2026-10-19')
    return a,dict(project=p,child=child,task=t,second=second,nested=nested,timed=timed,dated=dated_entry)


def test_complete_rich_work_and_configuration_admission(rich):
    a,ids=rich;report=verified(a)
    assert report.semantic_verified and not report.ordinary_startup_permitted
    state=snapshot(a)
    assert len(state['work_entries'])==4 and len(state['work_revisions'])==7
    assert state['dataset_meta'][0]['week_start']==0
    assert state['dataset_meta'][0]['polr_reminder_dismissed_local_date']=='2026-10-19'
    assert state['tasks'] and not state['active_timer']


@pytest.mark.parametrize('damage',['work owner','work creation','revision time','revision comment','revision prior','correction','request bytes','result bytes','dataset','unknown','configuration','reminder','missing creation'])
def test_complete_verifier_refuses_required_evidence_damage(rich,damage):
    a,ids=rich;state=snapshot(a)
    if damage=='work owner':corrupt(a,'work_entries','UPDATE work_entries SET task_id=? WHERE entry_id=?',(ids['second'],ids['timed']))
    if damage=='work creation':corrupt(a,'work_entries','UPDATE work_entries SET original_start_utc_us=original_start_utc_us+1 WHERE entry_id=?',(ids['timed'],))
    if damage=='revision time':corrupt(a,'work_revisions','UPDATE work_revisions SET audit_utc_us=audit_utc_us+1 WHERE entry_id=?',(ids['timed'],))
    if damage=='revision comment':corrupt(a,'work_revisions',"UPDATE work_revisions SET comment='unreviewed' WHERE entry_id=?",(ids['timed'],))
    if damage=='revision prior':corrupt(a,'work_entries','UPDATE work_entries SET current_revision=1 WHERE entry_id=?',(ids['timed'],))
    if damage=='correction':corrupt(a,'active_start_corrections','UPDATE active_start_corrections SET corrected_start_utc_us=corrected_start_utc_us+1')
    row=next(r for r in state['committed_requests'] if r['operation']=='add_timed_work')
    if damage=='request bytes':corrupt(a,'committed_requests','UPDATE committed_requests SET request_bytes=? WHERE request_id=?',(row['request_bytes']+b' ',row['request_id']))
    if damage=='result bytes':corrupt(a,'committed_requests','UPDATE committed_requests SET result_bytes=? WHERE request_id=?',(b'{}',row['request_id']))
    if damage in ('dataset','unknown'):
        x=json.loads(row['request_bytes'])
        if damage=='dataset':x['dataset_id']=uid()
        else:x['operation']='unknown_protected'
        corrupt(a,'committed_requests','UPDATE committed_requests SET request_bytes=?,operation=? WHERE request_id=?',(__import__('chronicle.records',fromlist=['canonical']).canonical(x),x['operation'],row['request_id']))
    if damage=='configuration':corrupt(a,'dataset_meta','UPDATE dataset_meta SET week_start=2')
    if damage=='reminder':corrupt(a,'dataset_meta',"UPDATE dataset_meta SET polr_reminder_dismissed_local_date='2026-10-20'")
    if damage=='missing creation':corrupt(a,'committed_requests','DELETE FROM committed_requests WHERE request_id=?',(row['request_id'],))
    before=a.path.read_bytes()
    with pytest.raises((ValueError,KeyError)):verified(a)
    assert a.path.read_bytes()==before


def test_active_state_and_historical_nonleaf_archived_eligibility(adapter):
    a=adapter;p=project(a);child=project(a,p);t=task(a,child);entry=uid()
    frozen,_=send(a,'start_timer',task_id=t,entry_id=entry,expected_task_version=1)
    assert verified(a).semantic_verified
    before=snapshot(a)
    bad=Request.make(uid(),a.context.dataset_id,'archive_project',NOW,project_id=p,expected_version=1)
    assert a.execute(bad).status=='rejected' and snapshot(a)==before
    corrupt(a,'active_timer','UPDATE active_timer SET version=2')
    with pytest.raises(ValueError):verified(a)


@pytest.mark.parametrize('kind',['archived ancestor','nonleaf','stale version'])
def test_new_work_refuses_ineligible_current_context(adapter,kind):
    a=adapter;p=project(a);child=project(a,p);t=task(a,child)
    if kind=='archived ancestor':lifecycle(a,'project',p)
    if kind=='nonleaf':task(a,child,t)
    version=2 if kind=='stale version' else 1
    before=snapshot(a);r=Request.make(uid(),a.context.dataset_id,'start_timer',NOW,task_id=t,entry_id=uid(),expected_task_version=version)
    assert a.execute(r).status=='rejected' and snapshot(a)==before


@pytest.mark.parametrize('late_context',['nonleaf','archived'])
def test_final_valid_rows_do_not_replace_historical_new_work_eligibility(adapter,late_context):
    a=adapter;p=project(a);t=task(a,p);dated(a,t)
    if late_context=='nonleaf':task(a,p,t)
    else:lifecycle(a,'project',p)
    state=snapshot(a);record=next(r for r in state['committed_requests'] if r['operation']=='add_date_only_work');later=max(state['committed_requests'],key=lambda r:r['commit_seq'])
    # Invert only these accepted events, retaining valid rows and exact restored
    # schema. Current archive/parent state alone cannot decide past eligibility.
    corrupt(a,'committed_requests','UPDATE committed_requests SET commit_seq=commit_seq+100')
    corrupt(a,'committed_requests','UPDATE committed_requests SET commit_seq=CASE WHEN request_id=? THEN ? WHEN request_id=? THEN ? ELSE commit_seq-100 END',
            (record['request_id'],later['commit_seq'],later['request_id'],record['commit_seq']))
    with pytest.raises(ValueError,match='Historical new work'):verified(a)


def test_complete_candidate_requires_pinned_valid_timezone(adapter):
    corrupt(adapter,'dataset_meta',"UPDATE dataset_meta SET timezone='Invalid/Unavailable'")
    with pytest.raises(ValueError):verified(adapter)


@pytest.mark.parametrize('damage',['missing sequence','duplicate sequence','unknown sequence','internal table'])
def test_complete_table_and_sequence_coverage_is_not_silently_skipped(adapter,damage):
    a=adapter;project(a)
    c=a.connect()
    try:
        if damage=='missing sequence':c.execute('DELETE FROM sqlite_sequence')
        if damage=='duplicate sequence':c.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('committed_requests',1)")
        if damage=='unknown sequence':c.execute("INSERT INTO sqlite_sequence(name,seq) VALUES('unreviewed',1)")
        if damage=='internal table':c.execute('ANALYZE')
    finally:c.close()
    with pytest.raises(ValueError):verified(a)
