"""Real SQLite absolute confirmation, complete source and historical commit-order proof."""
from copy import deepcopy
from dataclasses import replace
import json
import sqlite3

import pytest

from chronicle.polr_confirmation import parse_hours,MAX_QUARTERS
from chronicle.records import Request
from chronicle.sqlite_store import SQLiteStore,CONFIRMATION_TABLES
from chronicle.services import TimerService
from conftest import archive, NOW,uid
from test_manual_work import dated,timed,facts,M,H
from test_timesheet_candidate import preview
from test_timesheet_registration import exports
from test_services import FaultConnection

DAY='2026-10-19'


def all_facts(store):
    store._recover_connection()
    names=[r[0] for r in store.connection.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {n:[tuple(r) for r in store.connection.execute(f'SELECT * FROM {n} ORDER BY 1,2')] for n in names}


def manual(service,task,value,day=DAY,*,batch=None,now=NOW):
    current=service.read_polr_current_cells([dict(task_id=task,work_date=day)])[0]
    return dict(batch_id=batch or uid(),mode='manual',source_export_id=None,source_metadata=None,reviewed_rows=[],selected_keys=[],
                manual_cells=[dict(task_id=task,work_date=day,confirmed_quarters=value,
                                   prior_batch_id=current['current_batch_id'],prior_quarters=current['confirmed_quarters'])],acknowledgements=[])


def submit(service,args,*,request_id=None,now=NOW):
    return service.confirm_polr_absolute(**args,request_id=request_id or uid(),action_utc_us=now)


def frozen(service,task,*,duration='0:03'):
    dated(service,task,day=DAY,duration=duration);dated(service,task,day='2026-10-20',duration='0:03')
    c=preview(service,period='custom',start_date=DAY,end_date='2026-10-20')
    assert service.register_timesheet_export(c,request_id=uid(),action_utc_us=NOW).status=='committed'
    return c


def source_args(service,c):
    p=service.read_polr_confirmation_proposal(c.export_id)
    return dict(batch_id=uid(),mode='source',source_export_id=c.export_id,**p,manual_cells=[],acknowledgements=[])


def ack(row):
    return dict(task_id=row['task_id'],work_date=row['work_date'],suggested_quarters=row['suggested_quarters'],
                reviewed_prior_batch_id=row['prior_batch_id'],reviewed_prior_quarters=row['prior_quarters'])


@pytest.mark.parametrize('text,value',[('0',0),('0.00',0),('0.25',1),('1',4),('1.00',4),('1.25',5),('2.5',10),('2.50',10),('3.75',15),('5.00',20),(' 125.75 ',503),('0'*100+'.25',1)])
def test_exact_quarter_parser(text,value):assert parse_hours(text)==value


@pytest.mark.parametrize('bad',['2.30','1.10','1.01','-1','NaN','Infinity','1e2','1,25','1:30','.25','1.000','',1,True,1.25,'9'*100])
def test_invalid_manual_hours_never_round(bad):
    with pytest.raises(ValueError):parse_hours(bad)


def test_unknown_zero_equal_absolute_history_reopen_and_read_purity(service,task,store):
    raw=store.path.read_bytes();before=all_facts(store)
    assert service.read_polr_day_status(task,DAY,cutoff_utc_us=NOW)['daily_delta_hundredths'] is None
    assert all_facts(store)==before and store.path.read_bytes()==raw
    first=manual(service,task,0);assert submit(service,first).status=='committed'
    second=manual(service,task,0);assert submit(service,second,now=NOW-100).status=='committed'
    current=service.read_polr_current_cells([dict(task_id=task,work_date=DAY)])[0]
    assert current['confirmed_quarters']==0 and current['current_batch_id']==second['batch_id']
    batches=service.list_polr_confirmation_batches();assert [b['batch_id'] for b in batches]==[first['batch_id'],second['batch_id']]
    assert batches[1]['cells'][0]['expected_prior_batch_id']==first['batch_id']
    batches[0]['cells'].clear();assert len(service.read_polr_confirmation_batch(first['batch_id'])['cells'])==1
    directory=store.directory;store.close();reopened=SQLiteStore(directory)
    try:assert TimerService(reopened).read_polr_current_cells([dict(task_id=task,work_date=DAY)])[0]==current
    finally:reopened.close()


def test_case_F_default_positive_only_checked_zero_and_complete_source(service,task,store):
    c=frozen(service,task);before=all_facts(store);p=service.read_polr_confirmation_proposal(c.export_id)
    assert [r['suggested_quarters'] for r in p['reviewed_rows']]==[1,0]
    assert p['selected_keys']==[dict(task_id=task,work_date=DAY)] and len(c.basis)==7
    assert all_facts(store)==before
    a=source_args(service,c);assert submit(service,a).status=='committed'
    cells=service.read_polr_current_cells([dict(task_id=task,work_date=d) for d in (DAY,'2026-10-20')])
    assert [r['confirmed_quarters'] for r in cells]==[1,None]
    a=source_args(service,c);assert a['selected_keys']==[dict(task_id=task,work_date=DAY)] # Already equal stays default.
    a['selected_keys']=[dict(task_id=task,work_date='2026-10-20')]
    assert submit(service,a).status=='committed'
    assert service.read_polr_current_cells(a['selected_keys'])[0]['confirmed_quarters']==0


@pytest.mark.parametrize('fault',['missing','extra','duplicate','reordered','name','amount','unchecked_amount','stale_int','forged_stale','metadata','digest','association','basis_selection','empty','duplicate_selection','extra_field','missing_field'])
def test_complete_frozen_coverage_rejects_whole_batch(service,task,store,fault):
    c=frozen(service,task);a=source_args(service,c);rows=a['reviewed_rows']
    if fault=='missing':rows.pop()
    elif fault=='extra':rows.append({**rows[-1],'work_date':'2026-10-21'})
    elif fault=='duplicate':rows.append(deepcopy(rows[-1]))
    elif fault=='reordered':rows.reverse()
    elif fault=='name':rows[0]['task_name']='forged'
    elif fault in ('amount','unchecked_amount'):rows[0 if fault=='amount' else 1]['suggested_quarters']+=1
    elif fault=='stale_int':rows[0]['requires_stale_acknowledgement']=0
    elif fault=='forged_stale':rows[0]['requires_stale_acknowledgement']=True
    elif fault=='metadata':a['source_metadata']['scope_kind']='selected'
    elif fault=='digest':a['source_metadata']['report_sha256']='0'*64
    elif fault=='association':a['source_metadata']['source_tasks'][0]['name']='current instead of frozen'
    elif fault=='basis_selection':a['selected_keys']=[dict(task_id=task,work_date='2026-10-18')]
    elif fault=='empty':a['selected_keys']=[]
    elif fault=='duplicate_selection':a['selected_keys']*=2
    elif fault=='extra_field':a['extra']=False
    else:a.pop('manual_cells')
    before=all_facts(store)
    r=Request.make(uid(),store.dataset_id,'confirm_polr_absolute',NOW,**a)
    assert service.execute(r).status=='rejected'
    assert all_facts(store)==before


@pytest.mark.parametrize('before_export,equal',[(True,False),(False,True),(False,False)])
def test_source_precedence_uses_committed_sequence_not_audit(service,task,store,before_export,equal):
    if before_export:assert submit(service,manual(service,task,3),now=NOW+100).status=='committed'
    c=frozen(service,task)
    if not before_export:assert submit(service,manual(service,task,1 if equal else 3),now=NOW-100).status=='committed'
    a=source_args(service,c);row=a['reviewed_rows'][0]
    conflict=not before_export and not equal
    assert row['requires_stale_acknowledgement'] is conflict
    if conflict:
        before=all_facts(store);assert submit(service,a).status=='rejected';assert all_facts(store)==before
        a['acknowledgements']=[ack(row)]
    assert submit(service,a).status=='committed'
    assert service.read_polr_current_cells(a['selected_keys'])[0]['confirmed_quarters']==1


@pytest.mark.parametrize('fault',['missing','extra','duplicate','unchecked','proposed','prior','amount','blanket','nonconflict'])
def test_acknowledgements_are_exact_individual_reviewed_conflicts(service,task,store,fault):
    c=frozen(service,task);assert submit(service,manual(service,task,3)).status=='committed'
    a=source_args(service,c);good=ack(a['reviewed_rows'][0]);a['acknowledgements']=[good]
    if fault=='missing':a['acknowledgements']=[]
    elif fault=='extra':a['acknowledgements'].append({**good,'work_date':'2026-10-21'})
    elif fault=='duplicate':a['acknowledgements']*=2
    elif fault=='unchecked':a['selected_keys']=[dict(task_id=task,work_date='2026-10-20')]
    elif fault=='proposed':good['suggested_quarters']+=1
    elif fault=='prior':good['reviewed_prior_batch_id']=uid()
    elif fault=='amount':good['reviewed_prior_quarters']+=1
    elif fault=='blanket':a['acknowledgements']=True
    else:good['work_date']='2026-10-20'
    before=all_facts(store);assert submit(service,a).status=='rejected';assert all_facts(store)==before


@pytest.mark.parametrize('selected,same',[(True,True),(True,False),(False,True),(False,False)])
def test_selected_prior_identity_changes_reject_unchecked_newer_does_not(service,task,store,selected,same):
    c=frozen(service,task);day=DAY if selected else '2026-10-20'
    assert submit(service,manual(service,task,1,day)).status=='committed'
    a=source_args(service,c)
    assert submit(service,manual(service,task,1 if same else 2,day)).status=='committed'
    before=all_facts(store);out=submit(service,a)
    assert out.status==('rejected' if selected else 'committed')
    if selected:assert all_facts(store)==before and 'prior changed' in str(out.error)


def test_manual_multiple_cells_exact_old_retry_never_reinstalls_current(service,task,store):
    a=manual(service,task,12);a['manual_cells'].append({**a['manual_cells'][0],'work_date':'2026-10-20','confirmed_quarters':0})
    r=Request.make(uid(),store.dataset_id,'confirm_polr_absolute',NOW,**a)
    assert service.execute(r).status=='committed'
    newer=manual(service,task,20);assert submit(service,newer).status=='committed';before=all_facts(store)
    assert service.execute(r).status=='committed' and all_facts(store)==before
    assert service.execute(replace(r,action_utc_us=NOW+1)).status=='rejected' and all_facts(store)==before


@pytest.mark.parametrize('bad',[True,1.0,-1,MAX_QUARTERS+1,'1',None])
def test_strict_quarter_amounts_reject_without_write(service,task,store,bad):
    a=manual(service,task,bad);before=all_facts(store)
    if type(bad) is float:
        with pytest.raises(ValueError):submit(service,a)
    else:assert submit(service,a).status=='rejected'
    assert all_facts(store)==before


@pytest.mark.parametrize('fault',['unknown_task','bad_date','bad_uuid','prior_shape','duplicate','order','source_in_manual','manual_in_source'])
def test_manual_shapes_and_modes_fail_closed(service,task,store,fault):
    a=manual(service,task,4);cell=a['manual_cells'][0]
    if fault=='unknown_task':cell['task_id']=uid()
    elif fault=='bad_date':cell['work_date']='2026-02-30'
    elif fault=='bad_uuid':cell['task_id']='bad'
    elif fault=='prior_shape':cell['prior_quarters']=0
    elif fault=='duplicate':a['manual_cells']*=2
    elif fault=='order':a['manual_cells']=[{**cell,'work_date':'2026-10-20'},cell]
    elif fault=='source_in_manual':a['source_export_id']=uid()
    else:a['mode']='source'
    before=all_facts(store);assert submit(service,a).status=='rejected';assert all_facts(store)==before


def test_mandatory_A_B_exact_status_and_frozen_evidence(service,task,store,tmp_path):
    entry=dated(service,task,duration='3:00');c=preview(service,period='custom',start_date=DAY,end_date=DAY)
    service.register_timesheet_export(c,request_id=uid(),action_utc_us=NOW)
    dest=tmp_path/'saved.txt';assert service.materialize_registered_timesheet_export(c.export_id,dest).verified
    additional=dated(service,task,duration='2:00');before=facts(store);ex=exports(store)
    assert submit(service,source_args(service,c)).status=='committed'
    status=service.read_polr_day_status(task,DAY,cutoff_utc_us=NOW)
    assert (status['actual_hundredths'],status['confirmed_quarters'],status['daily_delta_hundredths'],status['suggested_entry_gap_quarters'])==(500,12,200,8)
    assert submit(service,manual(service,task,20)).status=='committed'
    assert service.read_polr_day_status(task,DAY,cutoff_utc_us=NOW)['daily_delta_hundredths']==0
    # New explicit work edits, separate from confirmation-purity checks.
    service.delete_work_entry(task,additional,expected_revision=1,request_id=uid(),action_utc_us=NOW)
    service.edit_date_only_work(task,entry,DAY,'2:30',expected_revision=1,request_id=uid(),action_utc_us=NOW)
    assert submit(service,manual(service,task,12)).status=='committed'
    status=service.read_polr_day_status(task,DAY,cutoff_utc_us=NOW)
    assert (status['actual_hundredths'],status['confirmed_quarters'],status['daily_delta_hundredths'],status['suggested_entry_gap_quarters'])==(250,12,-50,-2)
    assert exports(store)==ex and dest.read_bytes()==c.report_utf8


@pytest.mark.parametrize('after',[False,True])
def test_real_failed_commit_and_exact_reconciliation(service,task,store,after):
    a=manual(service,task,4);r=Request.make(uid(),store.dataset_id,'confirm_polr_absolute',NOW,**a)
    before=all_facts(store);fault=FaultConnection(store.connection,after=after);store.connection=fault
    result=service.execute(r);assert result.status==('committed' if after else 'rolled_back')
    assert fault.transaction_at_commit and result.error
    if not after:assert all_facts(store)==before
    assert service.execute(r).status=='committed'


def test_real_uncertain_commit_reuses_exact_request_after_newer_work(service,task,store,monkeypatch):
    a=manual(service,task,4);r=Request.make(uid(),store.dataset_id,'confirm_polr_absolute',NOW,**a)
    store.connection=FaultConnection(store.connection,after=True)
    with monkeypatch.context() as m:
        m.setattr(store,'_probe',lambda:(_ for _ in ()).throw(OSError('probe unavailable')))
        assert service.execute(r).status=='unverified'
    assert submit(service,manual(service,task,8)).status=='committed';before=all_facts(store)
    assert service.reconcile_request(r).status=='committed' and service.execute(r).status=='committed'
    assert all_facts(store)==before


@pytest.mark.parametrize('table',CONFIRMATION_TABLES[:2])
@pytest.mark.parametrize('verb',['UPDATE','DELETE'])
def test_immutable_sql_guards(service,task,store,table,verb):
    a=manual(service,task,0);assert submit(service,a).status=='committed'
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(f'UPDATE {table} SET batch_id=batch_id' if verb=='UPDATE' else f'DELETE FROM {table}')


@pytest.mark.parametrize('damage',['current_old','current_missing','prior','receipt','source','extra_cell'])
def test_damaged_confirmation_read_and_reopen_refuse_without_repair(service,task,store,damage):
    c=frozen(service,task);a=source_args(service,c);assert submit(service,a).status=='committed'
    b=manual(service,task,8);assert submit(service,b).status=='committed'
    conn=store.connection
    def change(table,sql,args=()):
        trigger=f'immutable_{table}_'+('delete' if sql.startswith('DELETE') else 'update')
        definition=conn.execute('SELECT sql FROM sqlite_schema WHERE name=?',(trigger,)).fetchone()[0]
        conn.execute(f'DROP TRIGGER {trigger}');conn.execute(sql,args);conn.execute(definition)
    conn.execute('PRAGMA foreign_keys=OFF')
    if damage=='current_old':conn.execute('UPDATE polr_confirmed_current SET batch_id=?',(a['batch_id'],))
    elif damage=='current_missing':conn.execute('DELETE FROM polr_confirmed_current')
    elif damage=='prior':change('polr_confirmation_cells','UPDATE polr_confirmation_cells SET expected_prior_batch_id=NULL,expected_prior_quarters=NULL WHERE batch_id=?',(b['batch_id'],))
    elif damage=='receipt':change('committed_requests',"DELETE FROM committed_requests WHERE request_id=(SELECT created_request_id FROM polr_confirmation_batches WHERE batch_id=?)",(b['batch_id'],))
    elif damage=='source':change('polr_confirmation_batches',"UPDATE polr_confirmation_batches SET source_export_id=NULL,mode='manual' WHERE batch_id=?",(a['batch_id'],))
    else:
        trigger=conn.execute("SELECT sql FROM sqlite_schema WHERE name='sealed_polr_confirmation_cells'").fetchone()[0]
        conn.execute('DROP TRIGGER sealed_polr_confirmation_cells')
        conn.execute('INSERT INTO polr_confirmation_cells VALUES(?,?,?,?,?,?,?)',(b['batch_id'],task,'2026-10-21',0,None,None,0))
        conn.execute(trigger)
    conn.execute('PRAGMA foreign_keys=ON');raw=store.path.read_bytes()
    with pytest.raises(ValueError):service.read_polr_confirmation_batch(b['batch_id'])
    directory=store.directory;store.close()
    with pytest.raises(ValueError):SQLiteStore(directory)
    assert (directory/'chronicle.sqlite3').read_bytes()==raw


@pytest.mark.parametrize('phase',['batch','cell','current','receipt','commit_ready','committed'])
def test_interrupted_confirmation_is_atomic_and_exact_retry_preserves_newer(service,task,store,phase):
    from test_interruptions import paused_child,TRANSACTION_CHILD,frozen_json
    a=manual(service,task,4);r=Request.make(uid(),store.dataset_id,'confirm_polr_absolute',NOW,**a)
    before=all_facts(store);directory=store.directory;store.close()
    prefix={'batch':'INSERT INTO polr_confirmation_batches','cell':'INSERT INTO polr_confirmation_cells','current':'INSERT INTO polr_confirmed_current'}.get(phase)
    code=TRANSACTION_CHILD
    if prefix:code=code.replace("phase == 'facts' and facts",f"phase == {phase!r} and sql.startswith({prefix!r})")
    with paused_child(code,directory,phase,frozen_json(r)):pass
    reopened=SQLiteStore(directory)
    try:
        s=TimerService(reopened);assert reopened.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert s.reconcile_request(r).status==('committed' if phase=='committed' else 'absent')
        if phase!='committed':assert all_facts(reopened)==before
        assert s.execute(r).status=='committed'
        assert submit(s,manual(s,task,8)).status=='committed';after=all_facts(reopened)
        assert s.execute(r).status=='committed' and all_facts(reopened)==after
    finally:reopened.close()


def test_duplicate_names_deleted_tasks_partial_source_and_current_independence(service,task,store):
    other=uid();service.create_task(other,'Example',request_id=uid(),action_utc_us=NOW)
    for t in (task,other):dated(service,t,day=DAY,duration='0:15')
    archive(service, 'task', other, now=0)
    c=preview(service,period='custom',start_date=DAY,end_date=DAY)
    service.register_timesheet_export(c,request_id=uid(),action_utc_us=NOW)
    a=source_args(service,c);assert len(a['reviewed_rows'])==2 and len(a['selected_keys'])==2 and len(c.basis)==14
    before=facts(store);assert submit(service,a).status=='committed';after=facts(store)
    assert all(after[k]==before[k] for k in before if k!='committed_requests')
    assert len(service.read_polr_current_cells(a['selected_keys']))==2
    assert submit(service,manual(service,other,0)).status=='committed'


def test_positive_equal_source_is_new_evidence_and_labels_stay_frozen(service,task,store):
    c=frozen(service,task)
    a=source_args(service,c);assert submit(service,a).status=='committed'
    service.rename_task(task,'Later name',expected_version=1,request_id=uid(),action_utc_us=NOW)
    b=source_args(service,c)
    assert b['reviewed_rows'][0]['task_name']=='Example' and b['selected_keys']==a['selected_keys']
    assert submit(service,b).status=='committed'
    assert len(service.list_polr_confirmation_batches())==2
    assert service.read_polr_current_cells(b['selected_keys'])[0]['current_batch_id']==b['batch_id']


def test_manual_prior_available_when_optional_accounting_context_fails(service,task,store,monkeypatch):
    fault=ValueError('current calculation unavailable')
    monkeypatch.setattr('chronicle.accounting.calculate_daily',lambda *a,**k:(_ for _ in ()).throw(fault))
    context=service.read_polr_manual_context(task,DAY,cutoff_utc_us=NOW)
    assert context['current_batch_id'] is None and context['confirmed_quarters'] is None and context['actual_us'] is None
    assert context['calculation_error'] is fault
    assert submit(service,manual(service,task,4)).status=='committed'
    assert service.read_polr_manual_context(task,DAY,cutoff_utc_us=NOW)['confirmed_quarters']==4
    with pytest.raises(ValueError):service.read_polr_manual_context(task,'2026-02-30',cutoff_utc_us=NOW)


@pytest.mark.parametrize('prefix',['INSERT INTO polr_confirmation_batches','INSERT INTO polr_confirmation_cells','INSERT INTO polr_confirmed_current','INSERT INTO committed_requests'])
def test_partial_sql_mutation_rolls_back_entire_batch(service,task,store,prefix):
    a=manual(service,task,4);r=Request.make(uid(),store.dataset_id,'confirm_polr_absolute',NOW,**a);before=all_facts(store)
    class Partial(FaultConnection):
        def execute(self,sql,*args):
            if sql=='COMMIT':return self.inner.execute(sql,*args)
            result=self.inner.execute(sql,*args)
            if sql.startswith(prefix):raise sqlite3.OperationalError('fault after partial confirmation SQL')
            return result
    store.connection=Partial(store.connection)
    assert service.execute(r).status=='rolled_back' and all_facts(store)==before
