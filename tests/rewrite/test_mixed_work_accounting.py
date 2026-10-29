"""Active-reader gate: real services expose all effective work together."""
import pytest
from conftest import NOW,uid
from test_manual_work import H,M,dated,timed,stamp,facts


def test_mixed_precision_future_dates_and_independent_tasks(service,task,store):
    second,project=uid(),uid()
    service.create_project(project,'P',request_id=uid(),action_utc_us=NOW)
    service.assign_task_to_project(task,project,expected_version=1,request_id=uid(),action_utc_us=NOW)
    service.create_task(second,'Example',project,expected_project_version=1,request_id=uid(),action_utc_us=NOW)
    dated(service,task,'2026-10-24','14:00')
    dated(service,second,'2026-10-19','0:15')
    timed(service,task)
    entry=uid();service.start_timer(task,entry,expected_task_version=2,request_id=uid(),action_utc_us=NOW-1234567)
    state=service.read_current_state(cutoff_utc_us=NOW)
    a,b=state['report']['tasks'][task],state['report']['tasks'][second]
    assert a['today_us']==H+1234567 and a['week_us']==15*H+1234567
    assert a['daily_us']['2026-10-24']==14*H
    assert a['daily_us'].get('2026-10-23',0)==a['daily_us'].get('2026-10-25',0)==0
    assert b['today_us']==15*M
    assert state['report']['application']['week_us']==a['week_us']+b['week_us']
    store.connection.execute('UPDATE tasks SET is_archived=1,archived_at_utc_us=0 WHERE task_id=?',(second,))
    assert service.read_current_state(cutoff_utc_us=NOW)['report']['application']==state['report']['application']


@pytest.mark.parametrize('start,end,expected',[
    ('2026-03-08T00:00:00-06:00','2026-03-09T00:00:00-05:00',23*H),
    ('2026-11-01T00:00:00-05:00','2026-11-02T00:00:00-06:00',25*H)])
def test_dst_real_timer_plus_whole_date(service,task,store,start,end,expected):
    e=uid();a,b=stamp(start),stamp(end)
    service.start_timer(task,e,expected_task_version=1,request_id=uid(),action_utc_us=a)
    service.stop_timer(e,expected_version=1,request_id=uid(),action_utc_us=b)
    day=start[:10]
    dated(service,task,day,'14:00')
    result=service.read_current_state(cutoff_utc_us=b-1)['report']
    assert result['tasks'][task]['daily_us'][day]==expected-1+14*H
    assert sum(r['duration_us'] for r in service.read_task_work_history(task,cutoff_utc_us=b-1))==result['application']['week_us']


def test_cross_midnight_redate_correction_deletion_and_read_purity(service,task,store):
    from chronicle.timesheet_files import metadata
    e=timed(service,task,'2026-10-18','23:00','2026-10-19','01:00')
    d=dated(service,task,'2026-10-18','1:00')
    report=service.read_current_state(cutoff_utc_us=NOW)['report']['tasks'][task]
    assert report['daily_us']=={'2026-10-18':2*H,'2026-10-19':H}
    service.edit_date_only_work(task,d,'2026-10-20','2:00',expected_revision=1,request_id=uid(),action_utc_us=NOW)
    service.edit_closed_timed_work(task,e,'2026-10-18','22:00','2026-10-19','01:00',expected_revision=1,request_id=uid(),action_utc_us=NOW)
    report=service.read_current_state(cutoff_utc_us=NOW)['report']['tasks'][task]
    assert report['daily_us']=={'2026-10-18':2*H,'2026-10-19':H,'2026-10-20':2*H}
    service.delete_work_entry(task,e,expected_revision=2,request_id=uid(),action_utc_us=NOW)
    before=facts(store)
    lock_path=store.lock.path
    assert lock_path.is_file()
    lock_metadata=metadata(lock_path.lstat())
    owner=store.lock.file
    assert owner is not None and not owner.closed
    def readable_files():
        # Windows prohibits competing reads of the active lock byte. Keep every
        # other dataset file, including SQLite sidecars, in the byte snapshot.
        return {p.name:p.read_bytes() for p in store.directory.iterdir() if p != lock_path}
    files=readable_files()
    for _ in range(3):
        assert service.read_current_state(cutoff_utc_us=NOW)['report']['tasks'][task]['week_us']==2*H
        service.read_task_work_history(task,cutoff_utc_us=NOW)
        service.read_work_entry_revisions(e)
    assert facts(store)==before
    assert readable_files()==files
    assert lock_path.is_file() and metadata(lock_path.lstat())==lock_metadata
    assert store.lock.file is owner and not owner.closed
