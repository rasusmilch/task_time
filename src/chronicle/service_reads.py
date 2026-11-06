"""Shared caller-owned reporting reads; no clock, transaction or dataset opener."""
from datetime import timedelta
from .records import uuid_text
from .timekeeping import instant


def polr_day_status(c, store, task_id, work_date, cutoff):
    from .accounting import calculate_daily
    from .polr_allocation import allocate_week,actual_hundredths,civil,complete_week,Q
    uuid_text(task_id);day=civil(work_date);instant(cutoff)
    task=c.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()
    if task is None:raise ValueError('Unknown retained task UUID')
    first=day-timedelta(days=(day.weekday()-store.week_start)%7)
    last=civil(complete_week(first.isoformat())[-1])
    tasks=[dict(r) for r in c.execute('SELECT * FROM tasks')]
    work=[dict(r) for r in c.execute("""SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r
      ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0""")]
    row=c.execute('SELECT * FROM active_timer').fetchone()
    daily=calculate_daily(tasks,work,dict(row) if row else None,cutoff,store.zone,first,last)[task_id]
    values=tuple(((first+timedelta(days=i)).isoformat(),daily.get((first+timedelta(days=i)).isoformat(),0)) for i in range(7))
    allocation=dict(allocate_week(first.isoformat(),values));actual=daily.get(work_date,0);hundredths=actual_hundredths(actual)
    current,_=store.confirmation_state(c);prior=current.get((task_id,work_date));confirmed=prior[1] if prior else None
    return dict(task_id=task_id,task_name=task['name'],is_archived=bool(task['is_archived']),work_date=work_date,
                cutoff_utc_us=cutoff,timezone=store.timezone,week_start=store.week_start,
                actual_us=actual,actual_hundredths=hundredths,suggested_quarters=allocation[work_date],
                confirmed_quarters=confirmed,current_batch_id=prior[0] if prior else None,
                daily_delta_hundredths=hundredths-25*confirmed if prior else None,
                suggested_entry_gap_quarters=allocation[work_date]-confirmed if prior else None,
                full_week_adjustment_us=sum(allocation.values())*Q-sum(v for _,v in values))
