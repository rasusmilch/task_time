"""Real mixed SQLite facts through one consistent frozen preview context."""
from dataclasses import FrozenInstanceError,replace
from datetime import datetime,timezone
from unittest.mock import patch

import pytest

from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timesheet import from_content,validate,render
from chronicle.timekeeping import to_us
from conftest import archive, NOW,uid
from test_manual_work import dated,timed,facts,H,M


def preview(service,**kw):
    return service.prepare_timesheet_preview(export_id=uid(),cutoff_utc_us=NOW,**kw)


def case_c(service,task):
    dated(service,task,day='2026-10-19',duration='1:08')
    dated(service,task,day='2026-10-20',duration='1:07')


def test_full_week_partial_tuesday_C_precision_and_purity(service,task,store):
    case_c(service,task)
    before=facts(store); raw=store.path.read_bytes(); statements=[]
    store.connection.set_trace_callback(statements.append)
    candidate=preview(service,period='custom',start_date=' 2026-10-20 ',end_date='2026-10-20')
    assert candidate.start_date==candidate.end_date=='2026-10-20'
    assert len(candidate.basis)==7 and len(candidate.cells)==1
    assert candidate.cells[0].suggested_quarters==4
    assert candidate.basis[1].actual_us==68*M and candidate.basis[1].suggested_quarters==5
    assert 'Displayed scope: partial week' in candidate.report_text
    assert 'POL-R weekly target: 2.25' in candidate.report_text
    assert '2026-10-19 |' not in candidate.report_text
    assert render(candidate)==candidate.report_text
    assert from_content(candidate.content())==candidate
    assert candidate.report_utf8==candidate.report_text.encode('utf-8')
    assert facts(store)==before and store.path.read_bytes()==raw
    assert sum(s=='BEGIN' for s in statements)==1
    assert sum(s=='COMMIT' for s in statements)==1
    assert not any(s.startswith(('INSERT','UPDATE','DELETE')) for s in statements)
    with pytest.raises(FrozenInstanceError): candidate.cells[0].actual_us=0
    content=candidate.content(); content['cells'][0]['actual_us']=0
    assert candidate.cells[0].actual_us==67*M


@pytest.mark.parametrize('weekday',range(7))
def test_periods_use_committed_week_all_seven(service,task,weekday):
    assert service.set_week_start(weekday,expected_week_start=6,request_id=uid(),action_utc_us=NOW).status in ('committed','unchanged')
    this=preview(service); last=preview(service,period='last_week')
    assert datetime.fromisoformat(this.start_date).weekday()==weekday
    assert (datetime.fromisoformat(this.start_date)-datetime.fromisoformat(last.start_date)).days==7
    assert this.week_start==last.week_start==weekday
    assert len(this.basis)==len(last.basis)==7


def test_multieweek_task_independence_duplicate_names_projects_deleted_and_labels(service,task,store):
    second,project=uid(),uid()
    service.create_project(project,'Project\nForged\trow',request_id=uid(),action_utc_us=NOW)
    service.create_task(second,'Example',project,expected_project_version=1,request_id=uid(),action_utc_us=NOW)
    for t in (task,second):
        dated(service,t,day='2026-10-19',duration='0:03')
        dated(service,t,day='2026-10-26',duration='0:03')
    archive(service, 'task', second, now=0)
    c=preview(service,period='custom',start_date='2026-10-19',end_date='2026-10-26')
    assert len(c.basis)==28 and len(c.cells)==16
    assert all(sum(b.suggested_quarters for b in c.basis if b.task_id==t)==2 for t in (task,second))
    assert c.tasks[0].project_name=='Project\nForged\trow' and not c.tasks[0].is_deleted
    assert 'Project: Project\\u000aForged\\u0009row' in c.report_text
    selected=preview(service,scope_kind='selected',task_ids=(second,))
    assert [t.task_id for t in selected.tasks]==[second] and not selected.tasks[0].is_deleted
    assert selected.selected_task_ids==(second,)


@pytest.mark.parametrize('scope,ids',[('selected',()),('selected',('bad',)),('selected',('unknown',)),('all',('anything',))])
def test_bad_scope_rejects(service,scope,ids):
    with pytest.raises(ValueError): preview(service,scope_kind=scope,task_ids=ids)


def test_unknown_duplicate_selected_and_valid_empty_all(service,task):
    for ids in ((uid(),),(task,task)):
        with pytest.raises(ValueError): preview(service,scope_kind='selected',task_ids=ids)
    empty=preview(service,scope_kind='all')
    assert len(empty.tasks)==1  # Known task with no work is explicit zero cells.
    assert all(c.actual_us==0 for c in empty.cells)


def test_no_tasks_is_valid_empty_all(service):
    candidate=preview(service)
    assert not candidate.tasks and not candidate.basis and not candidate.cells
    assert 'No tasks (valid empty All report).' in candidate.report_text


@pytest.mark.parametrize('first,last',[('2026-02-30','2026-03-01'),('2026-10-21','2026-10-20'),
    ('0001-01-01','0001-01-01'),('9999-12-30','9999-12-31')])
def test_bad_or_unrepresentable_expanded_bounds_even_empty(service,first,last):
    with pytest.raises((ValueError,OverflowError)): preview(service,period='custom',start_date=first,end_date=last)


def test_mixed_precise_running_future_correction_deletion_and_frozen(service,task,store):
    entry=uid()
    service.start_timer(task,entry,expected_task_version=1,request_id=uid(),action_utc_us=NOW-H+123456)
    service.stop_timer(entry,expected_version=1,request_id=uid(),action_utc_us=NOW-M+654321)
    date_id=dated(service,task,day='2026-10-24',duration='14:00')
    running=uid();service.start_timer(task,running,expected_task_version=1,request_id=uid(),action_utc_us=NOW-M)
    c=preview(service)
    assert c.cells[1].actual_us==H+530865
    assert c.cells[-1].actual_us==14*H
    frozen=c.content()
    service.edit_date_only_work(task,date_id,'2026-10-23','1:00',expected_revision=1,request_id=uid(),action_utc_us=NOW)
    fresh=preview(service)
    assert fresh.cells[-1].actual_us==0 and fresh.cells[-2].actual_us==H
    service.delete_work_entry(task,date_id,expected_revision=2,request_id=uid(),action_utc_us=NOW)
    assert preview(service).cells[-2].actual_us==0 and c.content()==frozen
    assert service.read_current_state(cutoff_utc_us=NOW)['active']['entry_id']==running


@pytest.mark.parametrize('zone,start,end,cutoff,day,expected',[
    ('America/Chicago','2026-03-08T06:00:00+00:00','2026-03-09T05:00:00+00:00','2026-03-10T12:00:00+00:00','2026-03-08',23*H),
    ('America/Chicago','2026-11-01T05:00:00+00:00','2026-11-02T06:00:00+00:00','2026-11-03T12:00:00+00:00','2026-11-01',25*H),
    ('Australia/Lord_Howe','2026-10-03T13:30:00+00:00','2026-10-04T13:00:00+00:00','2026-10-05T12:00:00+00:00','2026-10-04',23*H+30*M),
    ('America/Chicago','2026-12-31T06:00:00+00:00','2027-01-01T06:00:00+00:00','2027-01-01T07:00:00+00:00','2026-12-31',24*H),
    ('UTC','2028-02-29T00:00:00+00:00','2028-03-01T00:00:00+00:00','2028-03-01T12:00:00+00:00','2028-02-29',24*H)])
def test_actual_calendar_attribution_dst_nonhour_year_and_leap(tmp_path,zone,start,end,cutoff,day,expected):
    store=SQLiteStore(tmp_path/'zone',create=True,timezone=zone);service=TimerService(store); task=uid();entry=uid()
    stamp=lambda s:to_us(datetime.fromisoformat(s))
    try:
        service.create_task(task,'Unicode 雪',request_id=uid(),action_utc_us=stamp(start))
        service.start_timer(task,entry,expected_task_version=1,request_id=uid(),action_utc_us=stamp(start))
        service.stop_timer(entry,expected_version=1,request_id=uid(),action_utc_us=stamp(end))
        c=service.prepare_timesheet_preview(export_id=uid(),cutoff_utc_us=stamp(cutoff),period='custom',start_date=day,end_date=day)
        assert c.cells[0].actual_us==expected and 'Unicode 雪' in c.report_text
    finally:store.close()


def test_local_date_different_from_utc_and_one_explicit_cutoff(service,task):
    cutoff=to_us(datetime(2026,10,19,2,tzinfo=timezone.utc))
    c=service.prepare_timesheet_preview(export_id=uid(),cutoff_utc_us=cutoff)
    assert c.start_date=='2026-10-18' and c.cutoff_utc_us==cutoff


def test_preview_fails_entirely_on_accounting_error(service,task):
    with patch('chronicle.timesheet.calculate_daily',side_effect=ValueError('unsupported work')):
        with pytest.raises(ValueError,match='unsupported work'):preview(service)
