"""Complete task/work/template/frozen/POL-R and read-only backend integration."""
from copy import deepcopy
import pytest
from schema4_cases import *
from chronicle.schema4_services import read_state,reconciliation,reminder,history
from chronicle.sqlite_store import SQLiteStore
from chronicle.polr_confirmation import proposal
from test_project_movement import review


@pytest.mark.parametrize('scope',['all','selected'])
def test_frozen_bytes_labels_and_confirmations_survive_live_changes(adapter,scope):
    a=adapter;p=project(a);q=project(a);t=task(a,p);dated(a,t);child=task(a,p,t);dated(a,child,'0:30')
    options=dict(scope_kind=scope,task_ids=(t,)) if scope=='selected' else {}
    value=export(a,**options);before=snapshot(a)
    assert len(value.tasks)==(1 if scope=='selected' else 2)
    send(a,'move_project_subtree',**review(a,source=p,destination=q))
    send(a,'move_task_branch',**move_args(a,t,group=q))
    send(a,'rename_task',task_id=t,name='Later label',expected_version=2)
    lifecycle(a,'project',q)
    after=snapshot(a)
    for table in schema.EXPORT_TABLES:assert after[table]==before[table]
    assert value.report_utf8==after['timesheet_exports'][0]['report_utf8']
    manual(a,t,0)
    c=a.connect(readonly=True)
    try:
        c.execute('BEGIN');assert SQLiteStore.read_export(Rows(c),value.export_id)==value
        state=read_state(c,a.context,cutoff_utc_us=NOW);rows=reconciliation(c,a.context,cutoff_utc_us=NOW)
        assert state['report']['application']['today_us']==45*M
        assert state['report']['project_direct'][q]['today_us']==45*M
        assert rows['daily_cells'] and rows['visible_totals']['exact_actual_us']==45*M;c.execute('ROLLBACK')
    finally:c.close()
    assert verified(a).semantic_verified


def test_source_manual_zero_prior_chain_and_stale_source_acknowledgement(adapter):
    a=adapter;p=project(a);t=task(a,p);dated(a,t);value=export(a)
    _,first=manual(a,t,0)
    c=a.connect(readonly=True)
    try:
        current,_=SQLiteStore.confirmation_state(Rows(c));seq=next(r['commit_seq'] for r in snapshot(a)['committed_requests'] if r['operation']=='register_timesheet_export')
        proposed=proposal(value,current,seq)
    finally:c.close()
    args=dict(batch_id=uid(),mode='source',source_export_id=value.export_id,manual_cells=[],acknowledgements=[],**proposed)
    assert any(r['requires_stale_acknowledgement'] for r in args['reviewed_rows'])
    frozen=Request.make(uid(),a.context.dataset_id,'confirm_polr_absolute',NOW,**args);before=snapshot(a)
    assert a.execute(frozen).status=='rejected' and snapshot(a)==before
    args['acknowledgements']=[dict(task_id=r['task_id'],work_date=r['work_date'],suggested_quarters=r['suggested_quarters'],
        reviewed_prior_batch_id=r['prior_batch_id'],reviewed_prior_quarters=r['prior_quarters']) for r in args['reviewed_rows']
        if r['requires_stale_acknowledgement'] and dict(task_id=r['task_id'],work_date=r['work_date']) in args['selected_keys']]
    _,second=send(a,'confirm_polr_absolute',**args)
    assert verified(a).semantic_verified
    before=snapshot(a)
    assert a.execute(frozen).status=='rejected' and snapshot(a)==before
    send(a,'dismiss_polr_reminder_today',local_date='2026-10-19')
    c=a.connect(readonly=True)
    try:
        c.execute('BEGIN');status=reminder(c,a.context,cutoff_utc_us=NOW);assert status;c.execute('ROLLBACK')
    finally:c.close()


def test_apply_under_former_leaf_and_direct_history_and_read_purity(adapter):
    a=adapter;p=project(a);deep=project(a,project(a,p));root=task(a,deep);dated(a,root,'0:10')
    d=template(a,2);_,result=send(a,'apply_template',**apply_args(a,d,parent=root));leaf=result.result['created_tasks'][-1]['task_id'];dated(a,leaf,'0:20')
    before=snapshot(a);c=a.connect(readonly=True)
    try:
        c.execute('BEGIN');state=read_state(c,a.context,cutoff_utc_us=NOW)
        own=history(c,a.context,root,cutoff_utc_us=NOW,period='all')
        assert len(own['rows'])==1
        assert state['report']['individual'][root]['today_us']==10*M
        assert state['report']['cumulative'][root]['today_us']==30*M
        assert state['report']['projects'][p]['today_us']==30*M
        assert all('parent_project_id' in row and 'effective_archived' in row for row in state['projects'])
        assert state['templates'] and c.in_transaction;c.execute('ROLLBACK')
    finally:c.close()
    assert snapshot(a)==before


@pytest.mark.parametrize('damage',['text','hash','basis','cell','confirmation','pointer'])
def test_frozen_and_confirmation_corruption_refuses(adapter,damage):
    a=adapter;p=project(a);t=task(a,p);dated(a,t);value=export(a);manual(a,t)
    if damage=='text':corrupt(a,'timesheet_exports','UPDATE timesheet_exports SET report_utf8=?',(b'forged',))
    if damage=='hash':corrupt(a,'timesheet_exports','UPDATE timesheet_exports SET report_sha256=?',('0'*64,))
    if damage=='basis':corrupt(a,'timesheet_export_week_basis','UPDATE timesheet_export_week_basis SET actual_us=actual_us+1')
    if damage=='cell':corrupt(a,'timesheet_export_cells','UPDATE timesheet_export_cells SET suggested_quarters=suggested_quarters+1')
    if damage=='confirmation':corrupt(a,'polr_confirmation_cells','UPDATE polr_confirmation_cells SET confirmed_quarters=1')
    if damage=='pointer':corrupt(a,'polr_confirmed_current','DELETE FROM polr_confirmed_current')
    before=a.path.read_bytes()
    with pytest.raises(ValueError):verified(a)
    assert a.path.read_bytes()==before


def test_previous_week_reminder_and_unavailable_cutoff_are_not_zero(adapter):
    a=adapter;p=project(a);t=task(a,p);dated(a,t,day='2026-10-12')
    c=a.connect(readonly=True)
    try:
        c.execute('BEGIN');status=reminder(c,a.context,cutoff_utc_us=NOW)
        assert status['evaluation_status']=='AVAILABLE' and status['previous_week_outstanding_counts']['UNKNOWN']==1 and status['reminder_due']
        c.execute('ROLLBACK')
    finally:c.close()
    send(a,'start_timer',task_id=t,entry_id=uid(),expected_task_version=1)
    before=snapshot(a);c=a.connect(readonly=True)
    try:
        c.execute('BEGIN');state=read_state(c,a.context,cutoff_utc_us=NOW-1)
        assert state['report'] is None and state['calculation_error'] and state['active']
        c.execute('ROLLBACK')
    finally:c.close()
    assert snapshot(a)==before
