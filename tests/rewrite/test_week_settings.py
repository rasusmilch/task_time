"""Current metadata, exact setting requests and all seven civil-week conventions."""
import pytest
from chronicle.records import Request
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
from conftest import NOW,uid
from test_manual_work import dated,H,facts


@pytest.mark.parametrize('weekday,first,last,expected',[
    (0,'2026-10-19','2026-10-25',9),(1,'2026-10-13','2026-10-19',17),
    (2,'2026-10-14','2026-10-20',20),(3,'2026-10-15','2026-10-21',20),
    (4,'2026-10-16','2026-10-22',20),(5,'2026-10-17','2026-10-23',20),
    (6,'2026-10-18','2026-10-24',10)])
def test_seven_selected_weeks_reader_agreement_and_reopen(service,task,store,weekday,first,last,expected):
    for day,amount in [('2026-10-17','14:00'),('2026-10-18','1:00'),('2026-10-19','2:00'),('2026-10-20','3:00'),('2026-10-24','4:00')]:
        dated(service,task,day,amount)
    before=facts(store)
    out=service.set_week_start(weekday,expected_week_start=6,request_id=uid(),action_utc_us=NOW)
    assert out.status==('unchanged' if weekday==6 else 'committed')
    report=service.read_current_state(cutoff_utc_us=NOW)['report']
    assert (report['week_start'],report['week_end'])==(first,last)
    assert report['application']['today_us']==2*H and report['application']['week_us']==expected*H
    assert sum(r['duration_us'] for r in service.read_task_work_history(task,cutoff_utc_us=NOW))==expected*H
    after=facts(store)
    assert all(before[k]==after[k] for k in before if k not in ('dataset_meta','committed_requests'))
    assert store.week_start==weekday
    directory=store.directory;store.close();reopened=SQLiteStore(directory)
    try:
        assert TimerService(reopened).read_current_state(cutoff_utc_us=NOW)['week_start']==weekday
    finally: reopened.close()


def test_week_stale_noop_type_and_exact_historical_reuse(service,store):
    before=facts(store)
    assert service.set_week_start(6,expected_week_start=6,request_id=uid(),action_utc_us=NOW).status=='unchanged'
    assert facts(store)==before
    r=Request.make(uid(),store.dataset_id,'set_week_start',NOW,week_start=0,expected_week_start=6)
    assert service.execute(r).status=='committed'
    assert service.set_week_start(1,expected_week_start=0,request_id=uid(),action_utc_us=NOW).status=='committed'
    before=facts(store)
    assert service.execute(r).result=={'week_start':0} and store.week_start==1
    for new,prior in ((2,6),(-1,1),(7,1),(True,1),(1,True)):
        assert service.set_week_start(new,expected_week_start=prior,request_id=uid(),action_utc_us=NOW).status=='rejected'
        assert facts(store)==before
