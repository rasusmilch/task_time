"""Calendar schedule and minimal durable dismissal through real transactions."""
from datetime import datetime,timedelta,timezone
import sqlite3

import pytest

from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import to_us,from_us,local_date
from chronicle.records import Request
from conftest import NOW,uid
from test_manual_work import dated,M
from test_polr_confirmation import manual,submit,all_facts
from test_services import FaultConnection


def observed(day,hour=15):return to_us(datetime.fromisoformat(day).replace(hour=hour,tzinfo=timezone.utc))

def status(s,day):return s.read_polr_reminder_status(cutoff_utc_us=observed(day))


@pytest.mark.parametrize('weekday',range(7))
@pytest.mark.parametrize('offset',range(7))
def test_previous_every_day_current_civil_monday_friday_all_week_settings(service,task,weekday,offset):
    service.set_week_start(weekday,expected_week_start=6,request_id=uid(),action_utc_us=NOW)
    day=(datetime(2026,10,18)+timedelta(days=offset)).date()
    first=day-timedelta(days=(day.weekday()-weekday)%7)
    dated(service,task,day=(first-timedelta(days=1)).isoformat(),duration='0:03')
    dated(service,task,day=first.isoformat(),duration='0:03')
    r=status(service,day.isoformat())
    assert r['previous_week_start']==(first-timedelta(days=7)).isoformat()
    assert r['previous_week_end']==(first-timedelta(days=1)).isoformat()
    assert r['previous_week_outstanding_counts']['UNKNOWN']==1 and r['reminder_due']
    assert r['current_week_checked']==(day.weekday() in (0,4))
    assert r['current_week_coverage_counts'] is None if day.weekday() not in (0,4) else r['current_week_outstanding_counts']['UNKNOWN']==1


def test_case_F_explained_delta_and_opposing_gaps_reminder_truth(service,task):
    dated(service,task,day='2026-10-12',duration='0:03');dated(service,task,day='2026-10-13',duration='0:03')
    submit(service,manual(service,task,1,'2026-10-12'))
    r=status(service,'2026-10-19');assert r['previous_week_outstanding_counts']['UNKNOWN']==1
    submit(service,manual(service,task,0,'2026-10-13'))
    assert not status(service,'2026-10-19')['reminder_due']
    # A matching allocated amount has explained Delta, not an outstanding cell.
    dated(service,task,day='2026-10-14',duration='1:08');submit(service,manual(service,task,5,'2026-10-14'))
    # Full-week allocation now moves the original 0.25 away from Monday: inspect fresh suggestions explicitly.
    report=service.read_polr_reconciliation(cutoff_utc_us=NOW,period='last_week')
    for c in report['daily_cells']:
        if c['classification'] in ('UNKNOWN','MISMATCH'):submit(service,manual(service,task,c['suggested_quarters'],c['work_date']))
    assert not status(service,'2026-10-19')['reminder_due']
    assert any(c['daily_delta_hundredths'] for c in service.read_polr_reconciliation(cutoff_utc_us=NOW,period='last_week')['daily_cells'] if c['daily_delta_hundredths'] is not None)


def test_dismiss_same_day_restart_new_day_absence_and_purity(service,task,store):
    dated(service,task,day='2026-10-12',duration='1:00')
    assert status(service,'2026-10-19')['reminder_due']
    before=all_facts(store);request=Request.make(uid(),store.dataset_id,'dismiss_polr_reminder_today',NOW,local_date='2026-10-19')
    assert service.execute(request).status=='committed'
    after=all_facts(store)
    assert all(after[k]==before[k] for k in before if k not in ('dataset_meta','committed_requests'))
    assert store.connection.execute('SELECT polr_reminder_dismissed_local_date FROM dataset_meta').fetchone()[0]=='2026-10-19'
    assert not status(service,'2026-10-19')['reminder_due']
    assert service.dismiss_polr_reminder_today('2026-10-19',request_id=uid(),action_utc_us=NOW).status=='unchanged'
    assert all_facts(store)==after
    dated(service,task,day='2026-10-13',duration='1:00')
    assert not status(service,'2026-10-19')['reminder_due']
    directory=store.directory;store.close();opened=SQLiteStore(directory)
    try:
        fresh=TimerService(opened)
        assert not status(fresh,'2026-10-19')['reminder_due']
        assert status(fresh,'2026-10-20')['reminder_due']
        assert not status(fresh,'2026-11-15')['reminder_due'] # No replay of absent-day notifications.
        assert fresh.execute(request).status=='committed'
    finally:opened.close()


@pytest.mark.parametrize('bad',['2026-02-30','2026-10-18',' 2026-10-19 ',None,19])
def test_bad_dismissal_rejects_without_evidence(service,store,bad):
    before=all_facts(store)
    assert service.dismiss_polr_reminder_today(bad,request_id=uid(),action_utc_us=NOW).status=='rejected'
    assert all_facts(store)==before


@pytest.mark.parametrize('date_text',['2026-02-30','bad'])
def test_corrupt_dismissal_refuses_reopen_without_repair(store,date_text):
    store.connection.execute('PRAGMA ignore_check_constraints=ON')
    store.connection.execute('UPDATE dataset_meta SET polr_reminder_dismissed_local_date=?',(date_text,))
    directory=store.directory;raw=store.path.read_bytes();store.close()
    with pytest.raises(ValueError):SQLiteStore(directory)
    assert (directory/'chronicle.sqlite3').read_bytes()==raw


@pytest.mark.parametrize('after,expected',[(False,'rolled_back'),(True,'committed')])
def test_failed_commit_truth_and_exact_retry(service,store,after,expected):
    r=Request.make(uid(),store.dataset_id,'dismiss_polr_reminder_today',NOW,local_date='2026-10-19')
    store.connection=FaultConnection(store.connection,after=after)
    outcome=service.execute(r);assert outcome.status==expected
    assert service.reconcile_request(r).status==('committed' if after else 'absent')
    assert service.execute(r).status=='committed'
    assert store.connection.execute('SELECT count(*) FROM committed_requests').fetchone()[0]==1


def test_committed_unacknowledged_dismissal_reconciles_exactly(service,store,monkeypatch):
    r=Request.make(uid(),store.dataset_id,'dismiss_polr_reminder_today',NOW,local_date='2026-10-19')
    store.connection=FaultConnection(store.connection,after=True)
    original=store._probe
    def failed():raise sqlite3.OperationalError('unreadable independent evidence')
    monkeypatch.setattr(store,'_probe',failed)
    outcome=service.execute(r);assert outcome.status=='unverified'
    assert service.reconcile_request(r).status=='unverified'
    monkeypatch.setattr(store,'_probe',original)
    assert service.execute(r).status=='committed'
    before=all_facts(store)
    assert service.execute(r).status=='committed' and all_facts(store)==before


def test_local_midnight_utc_midnight_and_dst_use_dataset_zone(service,task):
    dated(service,task,day='2026-10-12',duration='0:01')
    before=service.read_polr_reminder_status(cutoff_utc_us=to_us(datetime(2026,10,20,0,30,tzinfo=timezone.utc)))
    after=service.read_polr_reminder_status(cutoff_utc_us=to_us(datetime(2026,10,20,5,1,tzinfo=timezone.utc)))
    assert before['local_today']=='2026-10-19' and before['current_week_checked']
    assert after['local_today']=='2026-10-20' and not after['current_week_checked']
    dst=service.read_polr_reminder_status(cutoff_utc_us=to_us(datetime(2026,11,1,7,30,tzinfo=timezone.utc)))
    assert dst['local_today']=='2026-11-01' and not dst['current_week_checked']


def test_unavailable_read_never_fabricates_clean(service,monkeypatch):
    def broken(*a,**kw):raise ValueError('incomplete calculation')
    monkeypatch.setattr('chronicle.timesheet.calculate_daily',broken)
    result=status(service,'2026-10-19')
    assert result['evaluation_status']=='UNAVAILABLE' and result['reminder_due'] is None
    assert result['previous_week_coverage_counts'] is None and str(result['calculation_error'])=='incomplete calculation'


def test_old_exact_dismiss_retry_never_reinstalls_yesterday(service,store):
    old=Request.make(uid(),store.dataset_id,'dismiss_polr_reminder_today',NOW,local_date='2026-10-19')
    assert service.execute(old).status=='committed'
    assert service.dismiss_polr_reminder_today('2026-10-20',request_id=uid(),action_utc_us=NOW+24*60*60_000_000).status=='committed'
    before=all_facts(store)
    assert service.execute(old).status=='committed' and all_facts(store)==before
    assert store.connection.execute('SELECT polr_reminder_dismissed_local_date FROM dataset_meta').fetchone()[0]=='2026-10-20'


def test_readable_dismissal_metadata_survives_calculation_failure_and_reopen(service,store,monkeypatch):
    service.dismiss_polr_reminder_today('2026-10-19',request_id=uid(),action_utc_us=NOW)
    directory=store.directory;store.close();opened=SQLiteStore(directory);fresh=TimerService(opened)
    fault=ValueError('accounting unavailable')
    try:
        with monkeypatch.context() as m:
            m.setattr('chronicle.timesheet.calculate_daily',lambda *a,**k:(_ for _ in ()).throw(fault))
            result=status(fresh,'2026-10-19')
            assert result['dismissed_local_date']=='2026-10-19' and result['calculation_error'] is fault
            assert result['reminder_due'] is None and result['previous_week_outstanding_counts'] is None
            assert result['evaluation_status']=='UNAVAILABLE'
    finally:opened.close()
