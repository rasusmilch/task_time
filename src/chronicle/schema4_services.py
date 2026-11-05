"""Caller-owned schema-4 backend entry points, never a dataset opener or worker."""
from . import schema_profiles as schema
from .schema4_tasks import check,apply_task_operation,OPERATIONS as TASK_OPERATIONS
from .project_services import apply_project_operation,OPERATIONS as PROJECT_OPERATIONS
from .project_lifecycle import apply_lifecycle_operation,OPERATIONS as LIFECYCLE_OPERATIONS
from .schema4_evidence import Rows,verify_transaction
from .hierarchy import candidate_task_observations,ProjectForest
from .records import StaleState
from .timekeeping import load_zone,instant


def recordable(c,task_id):
    values=candidate_task_observations(schema._rows(c,'tasks'),schema._rows(c,'projects'))
    if task_id not in values or not values[task_id]['eligible_for_new_work']:raise StaleState('New recording requires an effectively active leaf')


def apply_operation(c,request,context):
    check(c,request,context)
    from .recording_services import FIELDS,apply_common
    from .templates import OPERATIONS as TEMPLATE_OPERATIONS
    from .schema4_templates import apply_template_operation
    if request.operation in PROJECT_OPERATIONS:return apply_project_operation(c,request,context)
    if request.operation in LIFECYCLE_OPERATIONS:return apply_lifecycle_operation(c,request,context)
    if request.operation in TASK_OPERATIONS:return apply_task_operation(c,request,context)
    if request.operation in TEMPLATE_OPERATIONS:return apply_template_operation(Rows(c),request,context)
    if request.operation in FIELDS:
        zone=load_zone(c.execute('SELECT timezone FROM dataset_meta').fetchone()[0])
        return apply_common(Rows(c),request,dataset_id=context.dataset_id,zone=zone,recordable=recordable)
    raise ValueError('Unknown candidate operation; Delete requires its no-receipt path')


def read_state(c,context,*,cutoff_utc_us):
    """One caller-owned authoritative snapshot; no mutable calculation cache."""
    from .accounting import calculate
    from .project_accounting import project_report
    from .templates import read
    instant(cutoff_utc_us);verify_transaction(c)
    meta=schema._rows(c,'dataset_meta')[0]
    if meta['dataset_id']!=context.dataset_id:raise ValueError('Wrong candidate dataset')
    tasks=schema._rows(c,'tasks');projects=schema._rows(c,'projects')
    observations=candidate_task_observations(tasks,projects);forest=ProjectForest(projects)
    work=[dict(r) for r in Rows(c).execute('SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0')]
    active_rows=schema._rows(c,'active_timer');active=active_rows[0] if active_rows else None
    try:
        report=project_report(calculate(tasks,work,active,cutoff_utc_us,load_zone(meta['timezone']),meta['week_start']),tasks,projects)
        error=None
    except (ValueError,OverflowError) as exc:report=None;error=str(exc)
    return dict(dataset_id=meta['dataset_id'],timezone=meta['timezone'],week_start=meta['week_start'],cutoff_utc_us=cutoff_utc_us,
                tasks=[dict(t,**observations[t['task_id']]) for t in tasks],
                projects=[dict(p,effective_archived=forest.effective_archived[p['project_id']]) for p in projects],
                templates=list(read(Rows(c)).values()),active=active,report=report,calculation_error=error)


def reconciliation(c,context,*,cutoff_utc_us,**options):
    from .reconciliation import project
    state=read_state(c,context,cutoff_utc_us=cutoff_utc_us)
    work=[dict(r) for r in Rows(c).execute('SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0')]
    from .sqlite_store import SQLiteStore
    current,_=SQLiteStore.confirmation_state(Rows(c))
    source_id=options.pop('source_export_id',None)
    source=SQLiteStore.read_export(Rows(c),source_id) if source_id is not None else None
    source_seq=c.execute('SELECT commit_seq FROM committed_requests WHERE request_id=(SELECT created_request_id FROM timesheet_exports WHERE export_id=?)',(source_id,)).fetchone()[0] if source is not None else None
    return project(dataset_id=context.dataset_id,cutoff_utc_us=cutoff_utc_us,timezone=state['timezone'],week_start=state['week_start'],
        tasks=state['tasks'],projects=state['projects'],work=work,active=state['active'],
        current={k:dict(batch_id=v[0],quarters=v[1],seq=v[2]) for k,v in current.items()},source=source,source_seq=source_seq,**options)


def history(c,context,task_id,*,cutoff_utc_us,**options):
    from .work_history import read_snapshot
    verify_transaction(c)
    meta=schema._rows(c,'dataset_meta')[0]
    if meta['dataset_id']!=context.dataset_id:raise ValueError('Wrong candidate dataset')
    return read_snapshot(Rows(c),context.dataset_id,load_zone(meta['timezone']),task_id,cutoff_utc_us=cutoff_utc_us,**options)


def reminder(c,context,*,cutoff_utc_us):
    from .reconciliation import reminder_status,reminder_periods,reminder_context
    verify_transaction(c)
    meta=schema._rows(c,'dataset_meta')[0];dismissed=meta['polr_reminder_dismissed_local_date']
    if meta['dataset_id']!=context.dataset_id:raise ValueError('Wrong candidate dataset')
    today,previous,end,first,last,checked=reminder_periods(cutoff_utc_us,load_zone(meta['timezone']),meta['week_start'])
    unavailable=reminder_context(dataset_id=context.dataset_id,cutoff_utc_us=cutoff_utc_us,timezone=meta['timezone'],week_start=meta['week_start'],dismissed_local_date=dismissed)
    try:
        report=reconciliation(c,context,cutoff_utc_us=cutoff_utc_us,period='custom',start_date=previous.isoformat(),end_date=(last if checked else end).isoformat())
    except (ValueError,OverflowError) as error:
        unavailable['calculation_error']=error;return unavailable
    return reminder_status(report,dismissed)
