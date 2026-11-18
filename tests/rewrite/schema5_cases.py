"""Disposable schema-5 transaction owner, TEST INFRASTRUCTURE ONLY.

No application imports this adapter. One writer connection is closed before any
independent committed-state read. No automatic retry, especially for Delete.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from chronicle import schema5_profiles as schema, project_ui as ui
from chronicle.project_services import CandidateProjectContext
from chronicle.schema5_evidence import verify_transaction
from chronicle.schema5_services import apply_operation, apply_delete, preview_delete
from chronicle.schema4_runtime_service import read_message
from chronicle.records import Request, Outcome, canonical
from conftest import NOW

M = 60_000_000


class RequestConflict(ValueError):
    pass


def uid(): return str(uuid4())


def facts(c):
    return {name: sorted(schema._rows(c, name), key=repr) for name, in c.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'")}


class Schema5Adapter:
    def __init__(self, path, dataset_id):
        self.path = Path(path)
        self.context = CandidateProjectContext(dataset_id, 5)
        self.now = NOW
        self.events = []
        self.checkpoint = lambda phase, c: None
        self.pending = None
        self.unresolved_delete = False
        self.retired = None

    def connect(self, readonly=False):
        c = sqlite3.connect(self.path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'),
                            uri=True, isolation_level=None, timeout=5)
        try:
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA synchronous=EXTRA')
            c.execute('PRAGMA foreign_keys=ON')
            c.set_trace_callback(lambda sql: self.events.append(('sql', sql)))
        except BaseException:
            c.close()
            raise
        return c

    def receipt(self, c, request):
        row = c.execute('SELECT * FROM committed_requests WHERE request_id=?', (request.request_id,)).fetchone()
        if row is None: return None
        if row['request_bytes'] != request.content() or row['operation'] != request.operation:
            raise RequestConflict('Exact Request identity/content conflict')
        value = json.loads(row['result_bytes'])
        if type(value) is not dict or canonical(value) != row['result_bytes']:
            raise ValueError('Noncanonical retained result')
        return value

    def envelope(self, request):
        request.content()
        if request.dataset_id != self.context.dataset_id: raise ValueError('Wrong dataset')
        if self.retired is not None: raise RuntimeError('Connection cleanup unverified')

    @contextmanager
    def reader(self):
        if self.retired is not None: raise RuntimeError('Connection cleanup unverified')
        c = self.connect(readonly=True)
        try:
            c.execute('BEGIN')
            verify_transaction(c)
            yield c
        finally:
            if c.in_transaction: c.execute('ROLLBACK')
            c.close()

    def snapshot(self):
        with self.reader() as c: return facts(c)

    def read(self, kind, value=None):
        with self.reader() as c:
            return read_message(c, self.context, kind, value, dataset_directory=self.path.parent)

    def state(self): return self.read('read', self.now)

    def inspect(self, request):
        if request.operation.startswith('delete_') and request.operation in ('delete_task', 'delete_project', 'delete_template'):
            return Outcome('unverified', error=ValueError('Delete has no receipt and never reconciles/retries'))
        if self.unresolved_delete or self.pending is not None and request is not self.pending:
            return Outcome('unavailable', error=ValueError('Only the original unresolved Request may reconcile'))
        try:
            self.envelope(request)
            with self.reader() as c: value = self.receipt(c, request)
            return Outcome('committed', value) if value is not None else Outcome('absent')
        except RequestConflict as error:
            return Outcome('conflict', error=error)
        except Exception as error:
            return Outcome('unverified', error=error)

    def reconcile(self, request):
        value = self.inspect(request)
        if request is self.pending and value.status in ('committed', 'absent'):
            self.pending = None
        return value  # Absence never triggers execution automatically.

    def execute(self, request):
        if self.unresolved_delete or self.pending is not None:
            return Outcome('unavailable', error=ValueError('Unresolved operation blocks new mutation; reconcile exact original'))
        try:
            self.envelope(request)
        except Exception as error:
            return Outcome('rejected' if isinstance(error, ValueError) else 'unavailable', error=error)
        deleting = request.operation in ('delete_project', 'delete_task', 'delete_template')
        c = None
        commit_attempted = False
        try:
            self.envelope(request)
            c = self.connect()
            c.execute('BEGIN IMMEDIATE')  # The owner, never a domain service.
            verify_transaction(c)
            old = self.receipt(c, request)
            if old is not None:
                if deleting: raise ValueError('Delete Request belongs to a retained receipt')
                c.execute('ROLLBACK')
                return Outcome('committed', old)
            self.events.append(('service', request.request_id, c.in_transaction))
            result = (apply_delete if deleting else apply_operation)(c, request, self.context)
            self.checkpoint('facts', c)
            if result is None:
                c.execute('ROLLBACK')
                return Outcome('unchanged')
            if not deleting:
                self.checkpoint('receipt', c)
                c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                          (request.request_id, request.operation,
                           'administrative' if request.operation in schema.ADMINISTRATIVE_OPERATIONS else 'protected',
                           request.content(), canonical(result), request.action_utc_us))
            self.checkpoint('verification', c)
            verify_transaction(c)
            self.checkpoint('commit_before', c)
            commit_attempted = True
            c.execute('COMMIT')
            self.checkpoint('commit_after', c)
            return Outcome('committed', result)
        except Exception as primary:
            clean = True
            if c is not None:
                try:
                    if c.in_transaction: c.execute('ROLLBACK')
                except Exception as secondary:
                    primary.add_note('Rollback cleanup failed: ' + repr(secondary)); clean = False
                try:
                    self.checkpoint('close', c)
                    c.close()
                except Exception as secondary:
                    primary.add_note('Connection close failed: ' + repr(secondary)); self.retired = c; clean = False
                c = None
            if deleting:
                if commit_attempted or not clean:
                    self.unresolved_delete = True
                    return Outcome('unverified', error=primary)
                return Outcome('rejected' if isinstance(primary, ValueError) else 'rolled_back', error=primary)
            observed = self.inspect(request) if clean else Outcome('unverified')
            if observed.status == 'committed': return Outcome('committed', observed.result, error=primary)
            if clean and observed.status == 'absent':
                return Outcome('rejected' if isinstance(primary, ValueError) else 'rolled_back', error=primary)
            if clean and observed.status == 'conflict': return Outcome('rejected', error=primary)
            self.pending = request
            return Outcome('unverified', error=primary)
        finally:
            if c is not None:
                try:
                    self.checkpoint('close', c)
                    c.close()
                except Exception as cleanup:
                    self.retired = c
                    if deleting and commit_attempted: self.unresolved_delete = True
                    else: self.pending = request
                    # Connection lifetime is still unverified; don't open another
                    # connection to guess an outcome or silently retry.
                    return Outcome('unverified', error=cleanup)

    def request(self, operation, **args):
        self.now += 1_000_000
        return Request.make(uid(), self.context.dataset_id, operation, self.now, **args)

    def send(self, operation, expect='committed', **args):
        r = self.request(operation, **args)
        outcome = self.execute(r)
        assert outcome.status == expect, outcome
        if outcome.status == 'committed':
            snapshot = self.snapshot()  # Independent committed-state read.
            if operation not in ('delete_task', 'delete_project', 'delete_template'):
                rows = [row for row in snapshot['committed_requests'] if row['request_id'] == r.request_id]
                assert len(rows) == 1
                assert rows[0]['request_bytes'] == r.content() and rows[0]['result_bytes'] == canonical(outcome.result)
                assert rows[0]['action_utc_us'] == r.action_utc_us and rows[0]['operation'] == operation
        return r, outcome

    def project(self, parent=None, name='Project'):
        key = uid(); args = dict(project_id=key, name=name)
        if parent is not None:
            p = next(p for p in self.state()['projects'] if p['project_id'] == parent)
            args.update(parent_project_id=parent, expected_parent_version=p['version'],
                        reviewed_parent_ancestry=ui.ancestry(self.state(), parent))
        self.send('create_child_project' if parent else 'create_project', **args)
        return key

    def task(self, group, parent=None, name='Task'):
        key = uid()
        self.send('create_task', task_id=key, name=name, **ui.new_task_review(self.state(), parent, group))
        return key

    def dated(self, task, duration='0:15', day='2026-10-19'):
        key = uid()
        self.send('add_date_only_work', task_id=task, entry_id=key, work_date=day, duration_text=duration, comment='Reviewed')
        return key

    def lifecycle(self, entity, key, operation='archive', expect='committed'):
        row = next(r for r in self.state()[entity+'s'] if r[entity+'_id'] == key)
        return self.send(operation+'_'+entity, expect=expect, **{entity+'_id': key, 'expected_version': row['version']})

    def move_args(self, key, group, parent=None):
        from chronicle.movement import snapshot
        return ui.task_move_arguments(self.state(), key, parent, group, snapshot(self.state()['tasks'], key))[0]

    def template(self, depth=2, name='Blueprint'):
        from test_templates import nodes
        key = uid(); self.send('create_template', template_id=key, name=name, nodes=nodes(depth))
        return next(t for t in self.state()['templates'] if t['template_id'] == key)

    def apply_args(self, definition, group, parent=None):
        tasks = {t['task_id']: t for t in self.state()['tasks']}
        projects = {p['project_id']: p for p in self.state()['projects']}
        return dict(template_id=definition['template_id'], expected_template_version=definition['version'],
                    reviewed_definition=definition, destination_project_id=group, destination_parent_task_id=parent,
                    expected_destination_project_version=projects[group]['version'] if group else None,
                    expected_destination_parent_version=tasks[parent]['version'] if parent else None,
                    reviewed_destination_project_ancestry=ui.ancestry(self.state(), group),
                    node_mapping=[dict(node_id=n['node_id'], task_id=uid()) for n in definition['nodes']])

    def preview(self, **options):
        return self.read('timesheet_preview', dict(export_id=uid(), cutoff_utc_us=self.now,
                                                 period='custom', start_date='2026-10-19', end_date='2026-10-20', **options))

    def export(self, **options):
        value = self.preview(**options)
        self.send('register_timesheet_export', candidate=value.content())
        return value

    def manual(self, task, quarters=0, day='2026-10-19'):
        context = self.read('polr_manual', dict(task_id=task, work_date=day, cutoff_utc_us=self.now))
        return self.send('confirm_polr_absolute', batch_id=uid(), mode='manual', source_export_id=None,
                         source_metadata=None, reviewed_rows=[], selected_keys=[], acknowledgements=[],
                         manual_cells=[dict(task_id=task, work_date=day, confirmed_quarters=quarters,
                                            prior_batch_id=context['current_batch_id'], prior_quarters=context['confirmed_quarters'])])

    def delete_request(self, entity, key, text='DELETE'):
        with self.reader() as c: review = preview_delete(c, self.context, entity, key)
        return self.request('delete_'+entity, **{entity+'_id': key, 'expected_version': review['selected']['version'],
                                               'review': review, 'confirmed_text': text})


@pytest.fixture
def adapter(tmp_path):
    path = tmp_path / 'isolated-schema5.sqlite3'
    dataset = uid()
    c = sqlite3.connect(path, isolation_level=None)
    try: schema.create_candidate(c, dataset_id=dataset, timezone='America/Chicago')
    finally: c.close()
    a = Schema5Adapter(path, dataset)
    try: yield a
    finally:
        if a.retired is not None: a.retired.close()
