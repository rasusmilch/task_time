"""Shared caller-owned recording operations; no transaction/dataset ownership."""
from .records import StaleState, integer, uuid_text
from .timekeeping import local_date, resolve_start, resolve_minute, parse_date, parse_duration

TIMED = set('task_id entry_id start_date start_time end_date end_time start_occurrence end_occurrence comment'.split())
DATED = set('task_id entry_id work_date duration_text comment'.split())
FIELDS = {
 'start_timer': {'task_id','entry_id','expected_task_version'},
 'stop_timer': {'entry_id','expected_version'},
 'switch_timer': {'expected_active_entry_id','expected_active_version','next_task_id','next_entry_id','expected_task_version'},
 'correct_active_start': {'entry_id','expected_version','date_text','time_text','occurrence','comment'},
 'add_timed_work': TIMED, 'add_date_only_work': DATED,
 'edit_closed_timed_work': TIMED|{'expected_revision'},
 'edit_date_only_work': DATED|{'expected_revision'},
 'delete_work_entry': {'task_id','entry_id','expected_revision','comment'},
 'set_week_start': {'week_start','expected_week_start'},
 'dismiss_polr_reminder_today': {'local_date'},
 'register_timesheet_export': {'candidate'},
 'confirm_polr_absolute': set('batch_id mode source_export_id source_metadata reviewed_rows selected_keys manual_cells acknowledgements'.split()),
}


def apply_work(c, request, a, *, zone, recordable):
    from .services import TimerService as H
    op = request.operation
    if type(a["comment"]) is not str:
        raise ValueError("Work comment must be text")
    adding = op.startswith("add_")
    kind = "timed" if op in ("add_timed_work", "edit_closed_timed_work") else "date_only"
    if adding:
        uuid_text(a["task_id"])
        uuid_text(a["entry_id"])
        recordable(c, a['task_id'])
        old, revision = None, 1
    else:
        old = H._reviewed_work(c, a["task_id"], a["entry_id"], a["expected_revision"],
                                  None if op == "delete_work_entry" else kind)
        kind, revision = old["kind"], old["revision"] + 1
    if op == "delete_work_entry":
        return H._append_revision(c, request, a["entry_id"], revision, kind,
                                     old["start_utc_us"], old["stop_utc_us"], old["work_date"],
                                     old["duration_us"], 1, a["comment"])
    start = stop = day = duration = None
    if kind == "timed":
        start = resolve_minute(a["start_date"], a["start_time"], a["start_occurrence"], zone,
                               original=old["start_utc_us"] if old else None)
        stop = resolve_minute(a["end_date"], a["end_time"], a["end_occurrence"], zone,
                              original=old["stop_utc_us"] if old else None)
        if old and (start, stop) == (old["start_utc_us"], old["stop_utc_us"]):
            return None
        if stop <= start:
            raise ValueError("End must be strictly after start in UTC")
        if stop > request.action_utc_us:
            raise ValueError("Timed work end cannot be later than the accepted observation")
    else:
        day, duration = parse_date(a["work_date"]).isoformat(), parse_duration(a["duration_text"])
        if old and (day, duration) == (old["work_date"], old["duration_us"]):
            return None
    if adding:
        c.execute("""INSERT INTO work_entries
          (entry_id,task_id,kind,original_start_utc_us,current_revision,created_request_id) VALUES(?,?,?,?,1,?)""",
                  (a["entry_id"], a["task_id"], kind, start, request.request_id))
    return H._append_revision(c, request, a["entry_id"], revision, kind,
                                 start, stop, day, duration, 0, a["comment"])


def apply_common(c, request, *, dataset_id, zone, recordable):
    """One existing recording/configuration/report operation; caller commits."""
    from .services import TimerService as H
    from .sqlite_store import SQLiteStore as S
    a,op,now=request.args(),request.operation,request.action_utc_us
    if op not in FIELDS or set(a)!=FIELDS[op]:raise ValueError('Incorrect recording/configuration/report fields')
    local_date(now,zone)
    if op in ('add_timed_work','add_date_only_work','edit_closed_timed_work','edit_date_only_work','delete_work_entry'):
        return apply_work(c,request,a,zone=zone,recordable=recordable)
    if op=='set_week_start':
        new=integer(a['week_start'],'Week start',0,6);prior=integer(a['expected_week_start'],'Reviewed week start',0,6)
        if c.execute('SELECT week_start FROM dataset_meta').fetchone()[0]!=prior:raise StaleState('Reviewed week start changed; refresh before trying again')
        if new==prior:return None
        c.execute('UPDATE dataset_meta SET week_start=? WHERE singleton=1',(new,));return dict(week_start=new)
    if op=='dismiss_polr_reminder_today':
        from .polr_allocation import civil
        day=civil(a['local_date'])
        if day!=local_date(now,zone):raise StaleState('Dismissal date differs from accepted dataset-local observation')
        if S.dismissed_date(c)==day.isoformat():return None
        c.execute('UPDATE dataset_meta SET polr_reminder_dismissed_local_date=? WHERE singleton=1',(day.isoformat(),))
        return dict(local_date=day.isoformat())
    if op=='register_timesheet_export':
        from .timesheet import from_content
        value=from_content(a['candidate'])
        if value.dataset_id!=dataset_id or value.timezone!=zone.key:raise ValueError('Wrong candidate dataset/timezone')
        return S.insert_export(c,value,request)
    if op=='confirm_polr_absolute':
        source=S.read_export(c,a['source_export_id']) if a['source_export_id'] is not None else None
        return S.insert_confirmation(c,request,source,H._export_sequence(c,source.export_id) if source else None)
    if op=='start_timer':
        H._task(c,a['task_id'],a['expected_task_version']);recordable(c,a['task_id'])
        if c.execute('SELECT 1 FROM active_timer').fetchone():raise StaleState('Another timer is active; use Switch')
        H._open(c,a['task_id'],a['entry_id'],request);return dict(entry_id=a['entry_id'],version=1)
    if op in ('stop_timer','switch_timer'):
        active=H._active(c,a['expected_active_entry_id'] if op=='switch_timer' else a['entry_id'],
                         a['expected_active_version'] if op=='switch_timer' else a['expected_version'])
        if op=='switch_timer':
            H._task(c,a['next_task_id'],a['expected_task_version']);recordable(c,a['next_task_id'])
            if active['task_id']==a['next_task_id']:raise ValueError('Switch requires a different task')
        H._close(c,active,request)
        if op=='stop_timer':return dict(entry_id=active['entry_id'],revision=1)
        H._open(c,a['next_task_id'],a['next_entry_id'],request)
        return dict(closed_entry_id=active['entry_id'],entry_id=a['next_entry_id'],version=1)
    active=H._active(c,a['entry_id'],a['expected_version'])
    if type(a['comment']) is not str:raise ValueError('Correction comment must be text')
    corrected=resolve_start(active['start_utc_us'],a['date_text'],a['time_text'],a['occurrence'],zone)
    if corrected==active['start_utc_us']:return None
    if corrected>now:raise ValueError('Corrected start cannot be later than the accepted observation')
    version=active['version']+1
    c.execute('INSERT INTO active_start_corrections(entry_id,version,prior_start_utc_us,corrected_start_utc_us,audit_utc_us,comment,request_id) VALUES(?,?,?,?,?,?,?)',
              (active['entry_id'],version,active['start_utc_us'],corrected,now,a['comment'].strip(),request.request_id))
    c.execute('UPDATE active_timer SET start_utc_us=?,version=? WHERE entry_id=?',(corrected,version,active['entry_id']))
    return dict(entry_id=active['entry_id'],version=version)
