"""Test-owned candidate transaction adapter. Not an application runtime.

Callers exclusively own disposable files and join interrupted children before
reopening. No concurrent application writer or general coordinator is supported.
Fault checkpoints make real transaction boundaries observable to killed children.
"""
import json
import sqlite3
from pathlib import Path

from chronicle import schema_profiles as schema
from chronicle.project_services import CandidateProjectContext, apply_project_operation
from chronicle.project_lifecycle import apply_lifecycle_operation, OPERATIONS as LIFECYCLE_OPERATIONS
from chronicle.records import Outcome, canonical


def facts(c):
    return {name: sorted(schema._rows(c, name), key=repr) for name, in c.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'")}


class RequestConflict(ValueError):
    pass


def receipt_extension(before, c, request, result):
    """Independent complete surviving facts, not the service's mutation plan."""
    after = facts(c)
    previous = next((r['seq'] for r in before['sqlite_sequence'] if r['name'] == 'committed_requests'), 0)
    row = dict(commit_seq=previous+1, request_id=request.request_id, operation=request.operation,
               receipt_class='administrative' if request.operation in schema.ADMINISTRATIVE_OPERATIONS else 'protected', request_bytes=request.content(),
               result_bytes=canonical(result), action_utc_us=request.action_utc_us)
    expected = dict(before, projects=after['projects'],
                    committed_requests=sorted(before['committed_requests']+[row], key=repr),
                    sqlite_sequence=[dict(name='committed_requests', seq=previous+1)])
    op=request.operation
    domains={
      'create_task':{'tasks'},'rename_task':{'tasks'},'rename_project':{'projects'},
      'assign_task_to_project':{'tasks'},'move_task_branch':{'tasks'},
      'apply_template':{'tasks'},
      'start_timer':{'work_entries','active_timer'},'stop_timer':{'work_entries','work_revisions','active_timer'},
      'switch_timer':{'work_entries','work_revisions','active_timer'},
      'correct_active_start':{'active_timer','active_start_corrections'},
      'add_timed_work':{'work_entries','work_revisions'},'add_date_only_work':{'work_entries','work_revisions'},
      'edit_closed_timed_work':{'work_entries','work_revisions'},'edit_date_only_work':{'work_entries','work_revisions'},
      'delete_work_entry':{'work_entries','work_revisions'},'set_week_start':{'dataset_meta'},'dismiss_polr_reminder_today':{'dataset_meta'},
      'register_timesheet_export':set(schema.EXPORT_TABLES),'confirm_polr_absolute':set(schema.CONFIRMATION_TABLES),
    }
    from chronicle.templates import MANAGEMENT
    if op in MANAGEMENT:domains[op]={'template_definitions','template_nodes'}
    if op in domains:
        expected['projects']=before['projects']
        for table in domains[op]:expected[table]=after[table]
    if request.operation in LIFECYCLE_OPERATIONS:
        entity = 'project' if request.operation.endswith('_project') else 'task'
        table, field = entity+'s', entity+'_id'
        key = request.args()[field]
        archived = int(request.operation.startswith('archive_'))
        expected['projects'] = before['projects']
        expected[table] = sorted([dict(r, is_archived=archived,
            archived_at_utc_us=request.action_utc_us if archived else None,
            version=r['version']+1, updated_utc_us=request.action_utc_us) if r[field] == key else r
            for r in before[table]], key=repr)
    if after != expected:
        raise ValueError('Unexpected receipt extension or unrelated row change')


class CandidateAdapter:
    def __init__(self, path, dataset_id, checkpoint=lambda stage, c: None):
        self.path = Path(path).resolve()
        self.context = CandidateProjectContext(dataset_id)
        self.checkpoint = checkpoint
        self.retired = None
        self.unresolved_delete = None

    def connect(self, readonly=False):
        c = sqlite3.connect(self.path.as_uri()+('?mode=ro' if readonly else '?mode=rw'),
                            uri=True, isolation_level=None, timeout=schema.BUSY_MS/1000)
        try:
            c.execute('PRAGMA synchronous=EXTRA')
            c.execute('PRAGMA foreign_keys=ON')
            return c
        except BaseException as primary:
            try:c.close()
            except Exception as secondary:
                self.retired=c
                primary.add_note('Candidate setup close failed: '+repr(secondary))
            raise

    def receipt(self, c, request):
        row = c.execute('SELECT operation,request_bytes,result_bytes FROM committed_requests WHERE request_id=?',
                        (request.request_id,)).fetchone()
        if row is None:
            return None
        if row[:2] != (request.operation, request.content()):
            raise RequestConflict('Request UUID reused with different content')
        result = json.loads(row[2])
        if type(result) is not dict or canonical(result) != row[2]:
            raise ValueError('Invalid committed result bytes')
        return result

    def envelope(self, request):
        if self.unresolved_delete is not None:raise RuntimeError('Delete outcome unresolved; exit and reopen before new mutation/review')
        request.content()
        if request.dataset_id != self.context.dataset_id:
            raise ValueError('Wrong candidate dataset')

    def inspect(self, request):
        """Independent exact evidence/absence under test-owned exclusive ownership."""
        if request.operation in ('delete_project','delete_task','delete_template'):
            return Outcome('unverified',error=RuntimeError('Delete has no receipt and must never reconcile/retry'))
        c = None
        try:
            self.envelope(request)
            if self.retired is not None:
                raise RuntimeError('Unverified old connection cleanup')
            c = self.connect(readonly=True)
            c.execute('BEGIN')
            if c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0] != request.dataset_id:
                raise ValueError('Wrong installed dataset')
            conflict = None
            try:
                result = self.receipt(c, request)
            except RequestConflict as error:
                conflict, result = error, None
            schema.verify_candidate_transaction(c)
            c.execute('ROLLBACK')
            c.close()
            c = None
            if conflict is not None:
                return Outcome('conflict', error=conflict)
            return Outcome('committed', result) if result is not None else Outcome('absent')
        except Exception as error:
            if c is not None:
                try:
                    c.close()
                except Exception as secondary:
                    error.add_note(f'Independent close failed: {secondary!r}')
                    self.retired = c
            return Outcome('unverified', error=error)

    def execute(self, request):
        if request.operation in ('delete_project','delete_task','delete_template'):
            return Outcome('rejected',error=ValueError('Delete requires the separate no-receipt/no-retry path'))
        try:
            self.envelope(request)
        except (ValueError,RuntimeError) as error:
            return Outcome('unverified' if self.unresolved_delete is not None else 'rejected', error=error)
        c = None
        try:
            self.envelope(request)
            if self.retired is not None:
                raise RuntimeError('Unverified old connection cleanup')
            c = self.connect()
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0] != request.dataset_id:
                raise ValueError('Wrong installed dataset')
            previous = self.receipt(c, request)  # Before new-state/stale evaluation.
            schema.verify_candidate_transaction(c)
            if previous is not None:
                result = Outcome('committed', previous)
                c.execute('ROLLBACK')
            else:
                before = facts(c)
                if request.operation in ('create_project','create_child_project','move_project_subtree'):
                    applied = apply_project_operation(c,request,self.context)
                else:
                    from chronicle.schema4_services import apply_operation
                    applied = apply_operation(c,request,self.context)
                self.checkpoint('after_apply', c)
                if applied is None:
                    c.execute('ROLLBACK')
                    result = Outcome('unchanged')
                else:
                    c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                              (request.request_id, request.operation, 'administrative' if request.operation in schema.ADMINISTRATIVE_OPERATIONS else 'protected', request.content(),
                               canonical(applied), request.action_utc_us))
                    self.checkpoint('after_receipt', c)
                    receipt_extension(before, c, request, applied)
                    schema.verify_candidate_transaction(c)
                    self.checkpoint('after_verify', c)
                    self.checkpoint('before_commit', c)
                    c.execute('COMMIT')
                    self.checkpoint('after_commit', c)
                    result = Outcome('committed', applied)
            self.checkpoint('close', c)
            c.close()
            return result
        except Exception as error:
            clean = True
            if c is not None:
                try:
                    if c.in_transaction:
                        self.checkpoint('rollback', c)
                        c.execute('ROLLBACK')
                except Exception as secondary:
                    error.add_note(f'Rollback failed: {secondary!r}')
                    clean = False
                try:
                    self.checkpoint('close', c)
                    c.close()
                except Exception as secondary:
                    error.add_note(f'Close failed: {secondary!r}')
                    self.retired = c
                    clean = False
            # Never treat COMMIT errors as absence. Retire first, independently
            # verify complete state, then reconcile the *same* original request.
            observed = self.inspect(request)
            if observed.status == 'committed':
                return observed
            if clean and observed.status == 'absent':
                return Outcome('rejected' if isinstance(error, ValueError) else 'rolled_back', error=error)
            if clean and observed.status == 'conflict':
                return Outcome('rejected', error=error)
            return Outcome('unverified', error=error)

    def delete(self, request):
        """No-receipt path under the same exclusive test-owned file authority."""
        from chronicle.schema4_delete import OPERATIONS,apply_delete
        if self.unresolved_delete is not None or self.retired is not None:
            return Outcome('unverified',error=RuntimeError('Unresolved Delete/cleanup; no destructive retry'))
        c=None;begun=attempted=False
        try:
            self.envelope(request)
            if request.operation not in OPERATIONS:raise ValueError('Not a Delete request')
            c=self.connect();c.execute('BEGIN IMMEDIATE');begun=True
            before=facts(c)
            result=apply_delete(c,request,self.context)
            self.checkpoint('after_apply',c)
            schema.verify_candidate_transaction(c)
            from chronicle.schema4_delete import survivors
            review=request.args()['review'];entity=review['entity_type']
            expected=survivors(before,{p['project_id'] for p in review['projects']},
                {t['task_id'] for t in review['tasks']},{r['request_id'] for r in review['retire_receipts']},
                review['entity_id'] if entity=='template' else None)
            if facts(c)!=expected:raise ValueError('Delete final survivor comparison failed')
            self.checkpoint('before_commit',c)
            attempted=True;c.execute('COMMIT');self.checkpoint('after_commit',c)
            self.checkpoint('close',c);c.close();return Outcome('committed',result)
        except Exception as primary:
            clean=self.retired is None
            if c is not None:
                try:
                    if c.in_transaction:
                        self.checkpoint('rollback',c);c.execute('ROLLBACK')
                except Exception as secondary:clean=False;primary.add_note('Delete rollback failed: '+repr(secondary))
                try:self.checkpoint('close',c);c.close()
                except Exception as secondary:
                    clean=False;self.retired=c;primary.add_note('Delete close failed: '+repr(secondary))
            if attempted or not clean:
                self.unresolved_delete=request
                primary.add_note('Delete outcome uncertain. Do not retry. Presence is current state only; exit and reopen for a fresh review/typed confirmation.')
                return Outcome('unverified',error=primary)
            return Outcome('rejected' if isinstance(primary,ValueError) else 'rolled_back' if begun else 'unavailable',error=primary)

    def preview(self,entity,identity):
        from chronicle.schema4_delete import preview
        if self.retired is not None or self.unresolved_delete is not None:raise RuntimeError('Exit/reopen before another Delete review')
        c=self.connect(readonly=True)
        try:
            c.execute('BEGIN');result=preview(c,self.context,entity,identity);c.execute('ROLLBACK');return result
        finally:c.close()

    def presence(self,entity,identity):
        """Current read only; never proves the historical outcome of Delete."""
        if self.retired is not None:raise RuntimeError('Old connection cleanup unverified')
        if entity not in ('project','task','template'):raise ValueError('Invalid entity')
        table='template_definitions' if entity=='template' else entity+'s'
        c=self.connect(readonly=True)
        try:return dict(entity_type=entity,entity_id=identity,present=c.execute(f'SELECT 1 FROM {table} WHERE {entity}_id=?',(identity,)).fetchone() is not None,historical_outcome_verified=False)
        finally:c.close()
