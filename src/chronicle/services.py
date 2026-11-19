"""Current service facade and caller-owned reads; SQLiteStore owns transactions."""
from . import schema
from .operations import read_state, history, reconciliation, reminder, apply_operation
from . import reporting
from .records import Outcome, Request, uuid_text
from .hierarchy import task_observations

def read_message(c, dataset_id, kind, value, *, dataset_directory):
    if c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0] != dataset_id:
        raise ValueError('Read snapshot dataset identity differs from its authoritative owner')
    if kind == 'read':
        return read_state(c, dataset_id, cutoff_utc_us=value)
    if kind == 'history_snapshot':
        return history(c, dataset_id, **value)
    if kind == 'revisions':
        entry = c.execute('SELECT * FROM work_entries WHERE entry_id=?', (value,)).fetchone()
        if entry is None:
            raise ValueError('Unknown work identity')
        return dict(entry=dict(entry), revisions=[dict(r) for r in c.execute('SELECT * FROM work_revisions WHERE entry_id=? ORDER BY revision', (value,))], active_start_corrections=[dict(r) for r in c.execute('SELECT * FROM active_start_corrections WHERE entry_id=? ORDER BY version', (value,))])
    if kind == 'polr_reconciliation':
        return reconciliation(c, dataset_id, **value)
    if kind == 'polr_reminder':
        return reminder(c, dataset_id, cutoff_utc_us=value)
    meta = dict(c.execute('SELECT * FROM dataset_meta').fetchone())
    tasks = schema._rows(c, 'tasks')
    projects = schema._rows(c, 'projects')
    if kind == 'timesheet_tasks':
        obs = task_observations(tasks, projects)
        groups = {p['project_id']: p for p in projects}
        return dict(dataset_id=dataset_id, projects=projects, tasks=[dict(t, **obs[t['task_id']], project_name=groups[t['project_id']]['name']) for t in tasks])
    if kind == 'timesheet_preview':
        from .timesheet import prepare
        work = [dict(r) for r in c.execute('SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0')]
        active = c.execute('SELECT * FROM active_timer').fetchone()
        return prepare(dataset_id=dataset_id, timezone=meta['timezone'], week_start=meta['week_start'], tasks=tasks, projects=projects, work=work, active=dict(active) if active else None, **value)
    if kind == 'timesheet_export':
        return reporting.read_export(c, value)
    if kind == 'timesheet_exports':
        exports = []
        for row in c.execute('SELECT export_id,registered_utc_us FROM timesheet_exports ORDER BY registered_utc_us,export_id'):
            e = reporting.read_export(c, row['export_id'])
            exports.append(dict(export_id=e.export_id, registered_utc_us=row['registered_utc_us'], start_date=e.start_date, end_date=e.end_date, cutoff_utc_us=e.cutoff_utc_us, timezone=e.timezone, week_start=e.week_start, scope_kind=e.scope_kind, tasks=e.tasks, preferred_destination=e.preferred_destination))
        return exports
    if kind == 'polr_proposal':
        from .polr_confirmation import proposal
        from . import recording_services as helpers
        current, _ = reporting.confirmation_state(c)
        return proposal(reporting.read_export(c, value), current, helpers._export_sequence(c, value))
    if kind in ('polr_day', 'polr_manual'):
        from . import recording_services as helpers
        from .service_reads import polr_day_status
        try:
            return polr_day_status(c, value['task_id'], value['work_date'], value['cutoff_utc_us'],timezone=meta['timezone'],week_start=meta['week_start'])
        except (ValueError, OverflowError) as exc:
            if kind != 'polr_manual':
                raise
            task = next((t for t in tasks if t['task_id'] == value['task_id']))
            current, _ = reporting.confirmation_state(c)
            prior = current.get((value['task_id'], value['work_date']))
            return dict(task_id=task['task_id'], task_name=task['name'], is_archived=bool(task['is_archived']), work_date=value['work_date'], cutoff_utc_us=value['cutoff_utc_us'], timezone=meta['timezone'], week_start=meta['week_start'], actual_us=None, actual_hundredths=None, suggested_quarters=None, confirmed_quarters=prior[1] if prior else None, current_batch_id=prior[0] if prior else None, daily_delta_hundredths=None, suggested_entry_gap_quarters=None, full_week_adjustment_us=None, calculation_error=exc)
    if kind in ('polr_history', 'polr_batch'):
        from . import recording_services as helpers
        if kind == 'polr_batch':
            return helpers._confirmation_batch(c, value)
        return [helpers._confirmation_batch(c, row[0]) for row in c.execute('SELECT b.batch_id FROM polr_confirmation_batches b JOIN committed_requests r ON r.request_id=b.created_request_id ORDER BY r.commit_seq')]
    if kind in ('timesheet_status', 'timesheet_publish'):
        from .timesheet_files import destination_path, inspect, protect, materialize
        e = reporting.read_export(c, value['export_id'])
        target = destination_path(value.get('destination') or e.preferred_destination) if value.get('destination') or e.preferred_destination else None
        if target is not None:
            protect(target, dataset_directory)
        if kind == 'timesheet_status':
            return inspect(target, e.report_utf8, e.report_sha256)
        return materialize(e.export_id, target, e.report_utf8, e.report_sha256, dataset_directory, confirmed_overwrite=value.get('confirmed_overwrite', False), expected_conflict=value.get('expected_conflict'))
    raise ValueError('Unsupported current read message: ' + kind)

class RuntimeService:
    """Thin Request/read facade; the supplied SQLiteStore owns every transaction."""

    def __init__(self, store):
        self.store = store
        self.dataset_id = uuid_text(store.dataset_id)

    def execute(self, request):
        if not isinstance(request,Request):
            return Outcome('rejected',error=ValueError('A canonical Request is required'))
        try:
            request.content()
        except (ValueError, TypeError) as exc:
            return Outcome('rejected', error=exc)
        if request.operation in ('delete_task', 'delete_project', 'delete_template'):
            return self.store.delete_unused(request)
        return self.store.transact(request, lambda c: apply_operation(c, request, self.dataset_id))

    def reconcile_request(self, request):
        return self.store.reconcile(request)

    def _read(self, kind, value=None):
        with self.store.read_transaction() as c:
            return read_message(c, self.dataset_id, kind, value, dataset_directory=self.store.directory)

    def read_current_state(self, *, cutoff_utc_us):
        return dict(self._read('read', cutoff_utc_us), schema_version=5, semantic_verified=True, ordinary_startup_permitted=True)

    def read_history_snapshot(self, task_id, **value):
        return self._read('history_snapshot', dict(value, task_id=task_id))

    def read_work_entry_revisions(self, entry_id):
        return self._read('revisions', entry_id)

    def read_timesheet_task_choices(self):
        return self._read('timesheet_tasks')

    def prepare_timesheet_preview(self, **value):
        return self._read('timesheet_preview', value)

    def list_registered_timesheet_exports(self):
        return self._read('timesheet_exports')

    def read_registered_timesheet_export(self, export_id):
        return self._read('timesheet_export', export_id)

    def inspect_registered_export_destination(self, export_id, destination=None):
        return self._read('timesheet_status', dict(export_id=export_id, destination=destination))

    def materialize_registered_timesheet_export(self, export_id, destination, **value):
        return self._read('timesheet_publish', dict(value, export_id=export_id, destination=destination))

    def read_polr_confirmation_proposal(self, export_id):
        return self._read('polr_proposal', export_id)

    def read_polr_manual_context(self, task_id, work_date, **value):
        return self._read('polr_manual', dict(value, task_id=task_id, work_date=work_date))

    def read_polr_day_status(self, task_id, work_date, **value):
        return self._read('polr_day', dict(value, task_id=task_id, work_date=work_date))

    def list_polr_confirmation_batches(self):
        return self._read('polr_history')

    def read_polr_confirmation_batch(self, batch_id):
        return self._read('polr_batch', batch_id)

    def read_polr_reconciliation(self, **value):
        return self._read('polr_reconciliation', value)

    def read_polr_reminder_status(self, *, cutoff_utc_us):
        return self._read('polr_reminder', cutoff_utc_us)

    def read_delete_preview(self, entity_type, entity_id):
        from .deletion import preview
        if self.store._unresolved_delete is not None:
            raise ValueError('Exit/reopen before another Delete review')
        with self.store.read_transaction() as c:
            return preview(c, self.dataset_id, entity_type, entity_id)

    def read_delete_presence(self, entity_type, entity_id):
        if entity_type not in ('task', 'project', 'template'):
            raise ValueError('Unknown Delete entity')
        uuid_text(entity_id)
        table = 'template_definitions' if entity_type == 'template' else entity_type + 's'
        with self.store.read_transaction() as c:
            present = c.execute(f'SELECT 1 FROM {table} WHERE {entity_type}_id=?', (entity_id,)).fetchone() is not None
        return dict(dataset_id=self.store.dataset_id, entity_type=entity_type, entity_id=entity_id, present=present, historical_outcome_verified=False)
