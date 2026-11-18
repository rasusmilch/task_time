"""Independent retained chronology, tamper refusal and historical policy isolation."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from chronicle import schema5_profiles as schema, project_ui as ui
from chronicle.administration import verify_project_history, verify_schema4_history
from chronicle.project_services import CandidateProjectContext
from chronicle.records import canonical
from chronicle.schema5_evidence import verify_transaction
from schema5_cases import adapter, uid, facts
from test_schema5_services import assignment


def alter(a, table, callback):
    """Tamper only disposable facts; restore the exact SQL guards before readback."""
    c = a.connect()
    try:
        c.execute('PRAGMA foreign_keys=OFF')
        c.execute('PRAGMA ignore_check_constraints=ON')
        c.execute('BEGIN IMMEDIATE')
        triggers = [r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='trigger' AND tbl_name=?", (table,))]
        for name in triggers: c.execute('DROP TRIGGER '+name)
        callback(c)
        for statement in schema.schema_statements():
            if any(statement.startswith('CREATE TRIGGER '+name+' ') for name in triggers): c.execute(statement)
        c.execute('COMMIT')
    finally:
        if c.in_transaction: c.execute('ROLLBACK')
        c.close()


def rewrite_requests(a, edits):
    def update(c):
        for row in c.execute('SELECT * FROM committed_requests').fetchall():
            content = json.loads(row['request_bytes']); edit = edits.get(row['request_id'])
            if edit is not None:
                edit(content['arguments'])
                c.execute('UPDATE committed_requests SET request_bytes=? WHERE request_id=?', (canonical(content), row['request_id']))
    alter(a, 'committed_requests', update)


def refuses_complete(a, structural=False):
    before = a.path.read_bytes(); c = a.connect(readonly=True)
    try:
        c.execute('BEGIN')
        if structural: schema.verify_structure(c)
        with pytest.raises((ValueError, KeyError, StopIteration)): verify_transaction(c)
        c.execute('ROLLBACK')
    finally: c.close()
    assert a.path.read_bytes() == before


@pytest.mark.parametrize('event', ['create null', 'create missing', 'assignment', 'move', 'apply'])
def test_projectless_history_cannot_be_hidden_by_later_real_assignment(adapter, event):
    a = adapter; p, q = a.project(), a.project()
    if event == 'apply':
        d = a.template(2); first, result = a.send('apply_template', **a.apply_args(d, p))
        task = result.result['created_tasks'][0]['task_id']
    else:
        task = a.task(p)
        first_id = next(t for t in a.snapshot()['tasks'] if t['task_id'] == task)['created_request_id']
        first = next(r for r in a.snapshot()['committed_requests'] if r['request_id'] == first_id)
    if event in ('create null', 'create missing'):
        later, _ = a.send('assign_task_to_project', **assignment(a, task, q))
        def corrupt_create(args):
            if event == 'create missing': args.pop('project_id')
            else: args['project_id'] = None
            args.update(expected_project_version=None, reviewed_destination_project_ancestry=[])
        edits = {first['request_id']: corrupt_create,
                 later.request_id: lambda args: args.update(reviewed_source_project_ancestry=[])}
    elif event == 'assignment':
        first, _ = a.send('assign_task_to_project', **assignment(a, task, q))
        later, _ = a.send('assign_task_to_project', **assignment(a, task, p))
        edits = {first.request_id: lambda args: args.update(project_id=None, reviewed_destination_project_ancestry=[]),
                 later.request_id: lambda args: args.update(reviewed_source_project_ancestry=[])}
    elif event == 'move':
        first, _ = a.send('move_task_branch', **a.move_args(task, q))
        later, _ = a.send('move_task_branch', **a.move_args(task, p))
        def fix_later(args):
            args.update(source_project_id=None, reviewed_source_project_ancestry=[])
            for member in args['reviewed_subtree']: member['project_id'] = None
        edits = {first.request_id: lambda args: args.update(destination_project_id=None,
                    expected_destination_project_version=None, reviewed_destination_project_ancestry=[]), later.request_id: fix_later}
    else:
        later, _ = a.send('move_task_branch', **a.move_args(task, q))
        def fix_later(args):
            args.update(source_project_id=None, reviewed_source_project_ancestry=[])
            for member in args['reviewed_subtree']: member['project_id'] = None
        edits = {first.request_id: lambda args: args.update(destination_project_id=None,
                    expected_destination_project_version=None, reviewed_destination_project_ancestry=[]), later.request_id: fix_later}
    rewrite_requests(a, edits)
    c = a.connect(readonly=True)
    try:
        c.execute('BEGIN'); schema.verify_structure(c); snapshot = facts(c); c.execute('ROLLBACK')
    finally: c.close()
    assert all(t['project_id'] is not None for t in snapshot['tasks'])
    # The same optional-project reconstruction remains meaningful for historical
    # v4 facts. Explicit v5 policy must reject at the original event.
    verify_schema4_history(snapshot['projects'], snapshot['tasks'], snapshot['committed_requests'], a.context.dataset_id, facts=snapshot)
    with pytest.raises(ValueError):
        verify_project_history(snapshot['projects'], snapshot['tasks'], snapshot['committed_requests'], a.context.dataset_id,
                               facts=snapshot, policy=CandidateProjectContext(a.context.dataset_id, 5))
    refuses_complete(a, structural=True)


@pytest.mark.parametrize('damage', ['class', 'request bytes', 'result', 'dataset', 'version', 'owner', 'timestamp', 'sequence', 'high water', 'work owner', 'revision', 'unknown table'])
def test_complete_receipt_work_and_inventory_tamper_refuses(adapter, damage):
    a = adapter; p = a.project(); task = a.task(p); other = a.task(p); entry = a.dated(task)
    r, _ = a.send('rename_task', task_id=task, expected_version=1, name='Renamed')
    if damage == 'class': alter(a, 'committed_requests', lambda c:c.execute("UPDATE committed_requests SET receipt_class='protected' WHERE request_id=?", (r.request_id,)))
    elif damage == 'request bytes': alter(a, 'committed_requests', lambda c:c.execute('UPDATE committed_requests SET request_bytes=? WHERE request_id=?', (b'{}', r.request_id)))
    elif damage == 'result': alter(a, 'committed_requests', lambda c:c.execute('UPDATE committed_requests SET result_bytes=? WHERE request_id=?', (b'{}', r.request_id)))
    elif damage == 'dataset':
        def bad(c):
            row = c.execute('SELECT request_bytes FROM committed_requests WHERE request_id=?', (r.request_id,)).fetchone()
            content = json.loads(row[0]); content['dataset_id'] = uid()
            c.execute('UPDATE committed_requests SET request_bytes=? WHERE request_id=?', (canonical(content), r.request_id))
        alter(a, 'committed_requests', bad)
    elif damage == 'version': rewrite_requests(a, {r.request_id:lambda args:args.update(expected_version=99)})
    elif damage == 'owner':
        owner = next(t for t in a.snapshot()['tasks'] if t['task_id'] == task)['created_request_id']
        alter(a, 'committed_requests', lambda c:c.execute('DELETE FROM committed_requests WHERE request_id=?', (owner,)))
    elif damage == 'timestamp': alter(a, 'tasks', lambda c:c.execute('UPDATE tasks SET updated_utc_us=updated_utc_us+1 WHERE task_id=?', (task,)))
    elif damage == 'sequence': alter(a, 'committed_requests', lambda c:c.execute('UPDATE committed_requests SET commit_seq=0 WHERE request_id=?', (r.request_id,)))
    elif damage == 'high water': alter(a, 'sqlite_sequence', lambda c:c.execute('UPDATE sqlite_sequence SET seq=0'))
    elif damage == 'work owner': alter(a, 'work_entries', lambda c:c.execute('UPDATE work_entries SET task_id=? WHERE entry_id=?', (other, entry)))
    elif damage == 'revision': alter(a, 'work_revisions', lambda c:c.execute("UPDATE work_revisions SET comment='Forged' WHERE entry_id=?", (entry,)))
    else:
        c = a.connect()
        try: c.execute('CREATE TABLE sqliteXunexpected(value TEXT) STRICT')
        finally:c.close()
    refuses_complete(a)


@pytest.mark.parametrize('late', ['nonleaf', 'archived'])
def test_historical_recording_eligibility_not_replaced_by_final_context(adapter, late):
    a = adapter; p = a.project(); task = a.task(p); entry = a.dated(task)
    work = next(r for r in a.snapshot()['work_entries'] if r['entry_id'] == entry)['created_request_id']
    if late == 'nonleaf':
        child = a.task(p, task)
        changed = next(t for t in a.snapshot()['tasks'] if t['task_id'] == child)['created_request_id']
    else:
        request, _ = a.lifecycle('project', p); changed = request.request_id
        a.lifecycle('project', p, 'unarchive')
    def swap(c):
        left = c.execute('SELECT commit_seq FROM committed_requests WHERE request_id=?', (work,)).fetchone()[0]
        right = c.execute('SELECT commit_seq FROM committed_requests WHERE request_id=?', (changed,)).fetchone()[0]
        c.execute('UPDATE committed_requests SET commit_seq=-1 WHERE request_id=?', (work,))
        c.execute('UPDATE committed_requests SET commit_seq=? WHERE request_id=?', (left, changed))
        c.execute('UPDATE committed_requests SET commit_seq=? WHERE request_id=?', (right, work))
    alter(a, 'committed_requests', swap)
    refuses_complete(a, structural=True)


def test_complete_replayer_never_invokes_mutation_services(adapter, monkeypatch):
    a = adapter; p = a.project(); q = a.project(p); task = a.task(q); a.dated(task)
    d = a.template(1); a.send('apply_template', **a.apply_args(d, q))
    a.send('move_project_subtree', **ui.ProjectMoveReview(a.state(), q).arguments(None))
    def forbidden(*args, **kwargs): raise AssertionError('Replay invoked mutation implementation')
    for module, name in [('chronicle.schema5_services','apply_operation'), ('chronicle.project_services','apply_project_operation'),
                         ('chronicle.schema4_tasks','apply_task_operation'), ('chronicle.project_lifecycle','apply_lifecycle_operation'),
                         ('chronicle.schema4_templates','apply_template_operation')]:
        monkeypatch.setattr(module+'.'+name, forbidden)
    with a.reader() as c:
        assert verify_transaction(c).semantic_verified
        assert not schema.verify_structure(c).effective_archived[q]
    c = a.connect(readonly=True)
    try:
        proof = schema.verify_candidate(c)
        assert proof.structural_verified and not proof.semantic_verified and not proof.ordinary_startup_permitted
    finally:c.close()


def test_frozen_registration_ownership_checked_in_historical_not_current_project(adapter):
    from test_schema5_reporting import rerender
    a = adapter; p, q = a.project(), a.project(); task = a.task(p); a.dated(task); value = a.export()
    a.send('assign_task_to_project', **assignment(a, task, q))
    forged = rerender(replace(value, tasks=(replace(value.tasks[0], project_id=q),)))
    def rewrite_export(c):
        c.execute('UPDATE timesheet_export_tasks SET project_id=? WHERE export_id=?', (q, value.export_id))
    alter(a, 'timesheet_export_tasks', rewrite_export)
    alter(a, 'timesheet_exports', lambda c:c.execute('UPDATE timesheet_exports SET report_utf8=?,report_sha256=? WHERE export_id=?',
                                                 (forged.report_utf8, forged.report_sha256, value.export_id)))
    def rewrite_receipt(c):
        row = c.execute("SELECT * FROM committed_requests WHERE operation='register_timesheet_export'").fetchone()
        content = json.loads(row['request_bytes']); content['arguments']['candidate'] = forged.content()
        result = json.loads(row['result_bytes']); result['report_sha256'] = forged.report_sha256
        c.execute('UPDATE committed_requests SET request_bytes=?,result_bytes=? WHERE request_id=?',
                  (canonical(content), canonical(result), row['request_id']))
    alter(a, 'committed_requests', rewrite_receipt)
    refuses_complete(a, structural=True)


@pytest.mark.parametrize('damage', ['text', 'hash', 'basis', 'cell', 'confirmation', 'pointer', 'correction'])
def test_complete_protected_evidence_and_current_pointer_tamper_refuse(adapter, damage):
    a = adapter; p = a.project(); task = a.task(p); a.dated(task); value = a.export(); a.manual(task, 1)
    entry = uid(); a.send('start_timer', task_id=task, entry_id=entry, expected_task_version=1)
    a.send('correct_active_start', entry_id=entry, expected_version=1, date_text='2026-10-19',
           time_text='09:59', occurrence=None, comment='Reviewed correction')
    if damage == 'text': alter(a, 'timesheet_exports', lambda c:c.execute('UPDATE timesheet_exports SET report_utf8=?', (b'forged',)))
    elif damage == 'hash': alter(a, 'timesheet_exports', lambda c:c.execute('UPDATE timesheet_exports SET report_sha256=?', ('0'*64,)))
    elif damage == 'basis': alter(a, 'timesheet_export_week_basis', lambda c:c.execute('UPDATE timesheet_export_week_basis SET actual_us=actual_us+1'))
    elif damage == 'cell': alter(a, 'timesheet_export_cells', lambda c:c.execute('UPDATE timesheet_export_cells SET suggested_quarters=suggested_quarters+1'))
    elif damage == 'confirmation': alter(a, 'polr_confirmation_cells', lambda c:c.execute('UPDATE polr_confirmation_cells SET confirmed_quarters=0'))
    elif damage == 'pointer': alter(a, 'polr_confirmed_current', lambda c:c.execute('DELETE FROM polr_confirmed_current'))
    else: alter(a, 'active_start_corrections', lambda c:c.execute('UPDATE active_start_corrections SET prior_start_utc_us=prior_start_utc_us-1'))
    refuses_complete(a)
