"""Independent expected results through pure projection and real SQLite services."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import sqlite3
from unittest.mock import patch

import pytest

from chronicle.reconciliation import classify,coverage,adjustment_text,project
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.records import Request,Outcome
from chronicle.timekeeping import to_us,from_us
from conftest import archive, NOW,uid
from test_manual_work import dated,timed,M,H
from test_timesheet_candidate import preview,case_c
from test_polr_confirmation import manual,submit,source_args,all_facts
from test_services import FaultConnection

DAY='2026-10-19'


def read(service,**kw):return service.read_polr_reconciliation(cutoff_utc_us=NOW,**kw)

def cell(report,task,day=DAY):return next(c for c in report['daily_cells'] if (c['task_id'],c['work_date'])==(task,day))


@pytest.mark.parametrize('actual,suggested,confirmed,expected',[
    (0,0,None,'NOT_APPLICABLE'),(1,0,None,'UNKNOWN'),(0,1,None,'UNKNOWN'),
    (1,0,0,'MATCH'),(0,0,0,'MATCH'),(0,0,1,'MISMATCH'),(H,4,4,'MATCH'),
    (H,4,3,'MISMATCH'),(H,4,5,'MISMATCH'),(None,None,0,'UNAVAILABLE')])
def test_daily_classification(actual,suggested,confirmed,expected):
    assert classify(actual,suggested,confirmed)==expected


def test_cases_A_B_export_confirm_correct_never_rewrite(service,task,store,tmp_path):
    entry=dated(service,task,duration='3:00')
    c=preview(service);assert service.register_timesheet_export(c,request_id=uid(),action_utc_us=NOW).status=='committed'
    dest=tmp_path/'frozen.txt';service.materialize_registered_timesheet_export(c.export_id,str(dest))
    dated(service,task,duration='2:00')
    args=source_args(service,c);assert submit(service,args).status=='committed'
    before=all_facts(store);raw=store.path.read_bytes()
    r=read(service,source_export_id=c.export_id);v=cell(r,task)
    assert (v['actual_hundredths'],v['suggested_quarters'],v['confirmed_quarters'],v['daily_delta_hundredths'],v['suggested_gap_quarters'],v['classification'])==(500,20,12,200,8,'MISMATCH')
    assert r['source_comparison']['cells'][1]['flags']==['CURRENT_SUGGESTION_DIFFERS_FROM_FROZEN']
    assert store.path.read_bytes()==raw and all_facts(store)==before
    assert submit(service,manual(service,task,20)).status=='committed'
    assert cell(read(service),task)['classification']=='MATCH'
    # Revise both original amounts to total 2.50; evidence and frozen file remain.
    assert service.edit_date_only_work(task,entry,DAY,'0:30',expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    assert submit(service,manual(service,task,12)).status=='committed'
    v=cell(read(service),task)
    assert (v['actual_hundredths'],v['suggested_quarters'],v['confirmed_quarters'],v['daily_delta_hundredths'],v['suggested_gap_quarters'])==(250,10,12,-50,-2)
    assert dest.read_bytes()==c.report_utf8 and service.read_registered_timesheet_export(c.export_id)==c
    assert len(service.list_polr_confirmation_batches())==3


def test_case_F_known_zero_coverage_no_invented_empty_confirmation(service,task):
    dated(service,task,duration='0:03');dated(service,task,day='2026-10-20',duration='0:03')
    r=read(service);w=r['task_weeks'][0]
    assert r['coverage']['UNKNOWN']==2 and w['weekly_target_quarters']==1 and w['weekly_adjustment_us']==9*M
    assert [cell(r,task,d)['suggested_quarters'] for d in (DAY,'2026-10-20')]==[1,0]
    submit(service,manual(service,task,1));r=read(service)
    assert cell(r,task)['classification']=='MATCH' and cell(r,task,'2026-10-20')['classification']=='UNKNOWN'
    assert not r['task_weeks'][0]['review_complete']
    submit(service,manual(service,task,0,'2026-10-20'));r=read(service)
    assert r['coverage']['MATCH']==2 and r['coverage']['NOT_APPLICABLE']==5 and r['task_weeks'][0]['review_complete']
    assert cell(r,task,'2026-10-20')['current_batch_id'] is not None


def test_opposing_daily_mismatch_never_nets_clean(service,task):
    dated(service,task,duration='1:15');dated(service,task,day='2026-10-20',duration='0:45')
    submit(service,manual(service,task,4));submit(service,manual(service,task,4,'2026-10-20'))
    r=read(service);w=r['task_weeks'][0];cross=r['cross_task_weeks'][0]
    assert w['weekly_target_quarters']==w['known_confirmed_quarters']==8
    assert [cell(r,task,d)['suggested_gap_quarters'] for d in (DAY,'2026-10-20')]==[1,-1]
    assert w['coverage']['MISMATCH']==2 and not w['review_complete'] and not cross['review_complete']


def test_explained_delta_and_partial_scope_full_week_context(service,task):
    case_c(service,task)
    submit(service,manual(service,task,5));submit(service,manual(service,task,4,'2026-10-20'))
    r=read(service,period='custom',start_date='2026-10-20',end_date='2026-10-20')
    v=cell(r,task,'2026-10-20');w=r['task_weeks'][0]
    assert (v['classification'],v['daily_delta_hundredths'],v['suggested_gap_quarters'])==('MATCH',12,0)
    assert w['exact_actual_us']==135*M and w['weekly_target_quarters']==9 and w['weekly_adjustment_us']==0
    assert w['coverage']['complete'] and not w['full_scope'] and not w['review_complete']
    assert r['visible_totals']['suggested_quarters']==4 and len(w['allocation'])==7
    assert adjustment_text(14*M+123456)=='14 minutes, 0 seconds, 123456 microseconds'


def test_cell_display_rounding_per_task_independence_deleted_and_scope(service,task,store):
    other=uid();service.create_task(other,'Example',request_id=uid(),action_utc_us=NOW)
    project_id=uid();service.create_project(project_id,'Group',request_id=uid(),action_utc_us=NOW)
    service.assign_task_to_project(other,project_id,expected_version=1,request_id=uid(),action_utc_us=NOW)
    for t in (task,other):dated(service,t,duration='0:03')
    archive(service, 'task', other, now=0)
    r=read(service);assert r['cross_task_weeks'][0]['weekly_target_quarters']==2
    assert r['cross_task_weeks'][0]['exact_actual_us']==6*M
    assert r['cross_task_weeks'][0]['weekly_adjustment_us']==24*M
    assert r['visible_totals']['actual_hundredths']==10
    selected=read(service,scope_kind='selected',task_ids=(other,))
    assert len(selected['tasks'])==1 and not selected['tasks'][0]['is_deleted'] and len(selected['daily_cells'])==7
    assert selected['visible_totals']['exact_actual_us']==3*M
    with pytest.raises(ValueError):read(service,scope_kind='selected',task_ids=())


@pytest.mark.parametrize('weekday',range(7))
def test_all_week_starts_and_no_carryover(service,task,weekday):
    service.set_week_start(weekday,expected_week_start=6,request_id=uid(),action_utc_us=NOW)
    for d in ('2026-10-01','2026-10-15','2026-10-29'):dated(service,task,day=d,duration='0:01')
    r=read(service,period='custom',start_date='2026-10-01',end_date='2026-10-31')
    assert sum(w['weekly_target_quarters'] for w in r['task_weeks'])==3
    assert all(datetime.fromisoformat(w['week_start_date']).weekday()==weekday for w in r['task_weeks'])
    assert all(0<=w['weekly_adjustment_us']<15*M for w in r['task_weeks'])


@pytest.mark.parametrize('zone,start,stop,amounts',[
    ('America/Chicago','2026-03-08T06:00:00+00:00','2026-03-09T05:00:00+00:00',{'2026-03-08':23*H}),
    ('America/Chicago','2026-11-01T05:00:00+00:00','2026-11-02T06:00:00+00:00',{'2026-11-01':25*H}),
    ('Australia/Lord_Howe','2026-10-03T13:30:00+00:00','2026-10-04T13:00:00+00:00',{'2026-10-04':23*H+30*M}),
    ('UTC','2026-10-19T23:59:59.999999+00:00','2026-10-20T00:00:00.000001+00:00',{DAY:1,'2026-10-20':1}),
])
def test_real_mixed_accounting_calendar_boundaries(zone,start,stop,amounts):
    t=uid();s=to_us(datetime.fromisoformat(start));e=to_us(datetime.fromisoformat(stop))
    tasks=[dict(task_id=t,name='Task',project_id=None,is_deleted=0)]
    facts=dict(dataset_id=uid(),timezone=zone,week_start=6,tasks=tasks,projects=[],current={},
        work=[dict(task_id=t,kind='timed',start_utc_us=s,stop_utc_us=e,is_deleted=0)],active=None)
    r=project(**facts,cutoff_utc_us=e,period='custom',start_date=min(amounts),end_date=max(amounts))
    assert {c['work_date']:c['exact_actual_us'] for c in r['daily_cells'] if c['exact_actual_us']}==amounts
    assert r['visible_totals']['actual_hundredths']==sum((a+18_000_000)//36_000_000 for a in amounts.values())


def test_running_cutoff_future_dated_and_read_purity_single_transaction(service,task,store):
    dated(service,task,day='2026-10-24',duration='14:00')
    service.start_timer(task,uid(),expected_task_version=1,request_id=uid(),action_utc_us=NOW-5*M-123)
    before=all_facts(store);raw=store.path.read_bytes();statements=[]
    store.connection.set_trace_callback(statements.append)
    r=read(service)
    assert cell(r,task)['exact_actual_us']==5*M+123
    assert cell(r,task,'2026-10-24')['exact_actual_us']==14*H
    assert statements.count('BEGIN')==statements.count('COMMIT')==1
    assert not any(s.startswith(('INSERT','UPDATE','DELETE')) for s in statements)
    assert all_facts(store)==before and store.path.read_bytes()==raw
    r['daily_cells'].clear();assert len(read(service)['daily_cells'])==7


def test_frozen_comparison_redistributes_other_dates_and_priors(service,task,store):
    entry=dated(service,task,duration='0:03');dated(service,task,day='2026-10-20',duration='0:03')
    c=preview(service,period='custom',start_date=DAY,end_date='2026-10-20')
    service.register_timesheet_export(c,request_id=uid(),action_utc_us=NOW)
    service.edit_date_only_work(task,entry,DAY,'0:01',expected_revision=1,request_id=uid(),action_utc_us=NOW)
    submit(service,manual(service,task,1));submit(service,manual(service,task,1,'2026-10-20'))
    before=all_facts(store)
    with patch('chronicle.timesheet.calculate_daily',wraps=__import__('chronicle.accounting',fromlist=['calculate_daily']).calculate_daily) as calculate:
        r=read(service,source_export_id=c.export_id)
    assert calculate.call_count==1
    rows=r['source_comparison']['cells'];assert len(rows)==2 # Not seven context dates.
    assert rows[0]['flags']==['CURRENT_SUGGESTION_DIFFERS_FROM_FROZEN'] # Newer equal frozen is not differing.
    assert rows[1]['flags']==['CURRENT_SUGGESTION_DIFFERS_FROM_FROZEN','NEWER_DIFFERING_CONFIRMATION']
    assert service.read_registered_timesheet_export(c.export_id)==c and all_facts(store)==before
    service.set_week_start(0,expected_week_start=6,request_id=uid(),action_utc_us=NOW)
    compare=read(service,source_export_id=c.export_id)['source_comparison']
    assert (compare['frozen_week_start'],compare['current_week_start'])==(6,0)
    with pytest.raises(ValueError):read(service,source_export_id=uid())


def test_empty_all_and_failed_calculation_not_successful_empty(service,store,monkeypatch):
    r=read(service);assert r['daily_cells']==[] and r['coverage']['complete']
    assert r['cross_task_weeks'][0]['weekly_target_quarters']==0
    monkeypatch.setattr('chronicle.timesheet.calculate_daily',lambda *a,**k:(_ for _ in ()).throw(ValueError('calculation failed')))
    with pytest.raises(ValueError,match='calculation failed'):read(service)
    assert not store.connection.in_transaction


def test_unavailable_coverage_and_explicit_zero_remain_distinct():
    c=coverage([dict(classification=s) for s in ('MATCH','UNKNOWN','UNAVAILABLE','NOT_APPLICABLE')])
    assert c['applicable']==3 and not c['complete'] and c['outstanding']==1 and c['UNAVAILABLE']==1


def test_redating_and_deletion_move_only_actual_not_confirmations(service,task):
    entry=dated(service,task,duration='0:15');submit(service,manual(service,task,1))
    assert service.edit_date_only_work(task,entry,'2026-10-20','0:15',expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    r=read(service)
    assert cell(r,task)['classification']=='MISMATCH' and cell(r,task,'2026-10-20')['classification']=='UNKNOWN'
    assert cell(r,task)['confirmed_quarters']==1 and cell(r,task,'2026-10-20')['confirmed_quarters'] is None
    assert service.delete_work_entry(task,entry,expected_revision=2,request_id=uid(),action_utc_us=NOW).status=='committed'
    r=read(service);assert cell(r,task,'2026-10-20')['classification']=='NOT_APPLICABLE'
    assert cell(r,task)['confirmed_quarters']==1 and len(service.read_work_entry_revisions(entry)['revisions'])==3


def test_read_transaction_failure_retains_original_error_and_data(service,task,store):
    before=all_facts(store);raw=store.path.read_bytes();fault=sqlite3.OperationalError('snapshot unavailable')
    class ReadFault:
        def __init__(self,inner):self.inner=inner
        def __getattr__(self,name):return getattr(self.inner,name)
        def execute(self,sql,*args):
            if sql=='SELECT * FROM projects ORDER BY project_id':raise fault
            return self.inner.execute(sql,*args)
    store.connection=ReadFault(store.connection)
    with pytest.raises(sqlite3.OperationalError) as error:read(service)
    assert error.value is fault and store.connection is None
    assert all_facts(store)==before and store.path.read_bytes()==raw
    assert read(service)['coverage']['complete']


def test_distant_source_calculates_only_distinct_needed_weeks(service,task):
    dated(service,task,day='2025-01-06',duration='0:03')
    c=preview(service,period='custom',start_date='2025-01-06',end_date='2025-01-06')
    service.register_timesheet_export(c,request_id=uid(),action_utc_us=NOW)
    from chronicle.polr_allocation import allocate_week
    with patch('chronicle.timesheet.allocate_week',wraps=allocate_week) as allocate:
        r=read(service,source_export_id=c.export_id)
    assert allocate.call_count==3 # One existing frozen-evidence validation plus current/historical context; no intervening weeks.
    assert r['source_comparison']['cells'][0]['frozen_suggested_quarters']==1
