"""Genuine isolated service operations and adjudicated owner/service boundary."""
from dataclasses import FrozenInstanceError, replace
import ast
from pathlib import Path
import sqlite3

import pytest

from chronicle.project_services import CandidateProjectContext
from chronicle.schema5_services import apply_operation
from chronicle.schema5_evidence import verify_transaction
from chronicle.records import Request, Outcome
from chronicle import project_ui as ui
from schema5_cases import adapter, Schema5Adapter, uid, NOW, M, facts


def rejected(a, request):
    before = a.snapshot()
    result = a.execute(request)
    assert result.status == 'rejected', result
    assert result.error is not None and a.snapshot() == before
    return result


def test_fresh_complete_semantics_are_isolated_and_context_is_exact(adapter):
    a = adapter
    assert a.context.schema_version == 5
    with a.reader() as c:
        proof = verify_transaction(c)
        assert proof.schema_version == 5 and proof.semantic_verified and proof.administrative_history_verified
        assert proof.ordinary_startup_permitted is False
    assert a.state()['tasks'] == [] and a.state()['projects'] == []
    assert CandidateProjectContext(a.context.dataset_id).schema_version == 4
    with pytest.raises(FrozenInstanceError): a.context.schema_version = 4
    for invalid in (True, 3, 6, '5', None):
        with pytest.raises(ValueError): CandidateProjectContext(a.context.dataset_id, invalid)


def test_owner_issues_immediate_before_service_and_owns_commit_and_rollback(adapter):
    a = adapter; a.events.clear()
    request, _ = a.send('create_project', project_id=uid(), name='Owned')
    begin = a.events.index(('sql', 'BEGIN IMMEDIATE'))
    invocation = a.events.index(('service', request.request_id, True))
    commit = a.events.index(('sql', 'COMMIT'))
    assert begin < invocation < commit
    assert ('sql', 'BEGIN') in a.events[commit+1:]  # Independent committed read.
    a.events.clear()
    rejected(a, a.request('create_task', task_id=uid(), name='No owner', reviewed_destination_project_ancestry=[]))
    assert ('sql', 'ROLLBACK') in a.events and ('sql', 'COMMIT') not in a.events


def test_active_transaction_is_required_but_begin_mode_belongs_to_owner(adapter, monkeypatch):
    a = adapter; c = a.connect()
    request = a.request('create_project', project_id=uid(), name='Direct caller')
    before = a.snapshot()
    try:
        with pytest.raises(ValueError, match='owned transaction'): apply_operation(c, request, a.context)
        c.execute('BEGIN')  # Adjudicated: valid service precondition, not owner contract.
        captured = []; c.set_trace_callback(captured.append)
        def forbidden(*args, **kwargs): raise AssertionError('Service opened another connection')
        monkeypatch.setattr(sqlite3, 'connect', forbidden)
        result = apply_operation(c, request, a.context)
        assert result == dict(project_id=request.args()['project_id'], version=1)
        assert c.in_transaction
        assert not any(s in ('BEGIN', 'BEGIN IMMEDIATE', 'COMMIT', 'ROLLBACK') for s in captured)
        c.execute('ROLLBACK')
    finally: c.close()
    monkeypatch.undo()
    assert a.snapshot() == before


@pytest.mark.parametrize('wrong', ['context version', 'context dataset', 'request dataset', 'paired wrong dataset', 'connection version'])
def test_admission_refuses_independent_identity_mismatches(adapter, wrong):
    a = adapter; c = a.connect(); context = a.context
    request = a.request('create_project', project_id=uid(), name='Wrong')
    if wrong == 'context version': context = CandidateProjectContext(a.context.dataset_id, 4)
    if wrong == 'context dataset': context = CandidateProjectContext(uid(), 5)
    if wrong == 'request dataset': request = replace(request, dataset_id=uid())
    if wrong == 'paired wrong dataset':
        other = uid(); context = CandidateProjectContext(other, 5); request = replace(request, dataset_id=other)
    if wrong == 'connection version': c.execute('PRAGMA user_version=4')
    try:
        c.execute('BEGIN IMMEDIATE'); before = facts(c)
        with pytest.raises(ValueError): apply_operation(c, request, context)
        assert facts(c) == before
        c.execute('ROLLBACK')
    finally: c.close()


def test_genuine_schema4_connection_and_historical_entry_refuse_schema5_authority(adapter, tmp_path):
    from chronicle import schema_profiles
    from chronicle.schema4_services import apply_operation as apply4
    dataset = uid(); c = sqlite3.connect(tmp_path/'actual-schema4.sqlite3', isolation_level=None)
    try:
        schema_profiles.create_candidate(c, dataset_id=dataset, timezone='America/Chicago')
        c.execute('BEGIN IMMEDIATE'); before = facts(c)
        request = Request.make(uid(), dataset, 'create_project', NOW, project_id=uid(), name='Wrong authority')
        with pytest.raises(ValueError): apply_operation(c, request, CandidateProjectContext(dataset, 5))
        assert facts(c) == before
        c.execute('ROLLBACK')
    finally:c.close()
    c = adapter.connect()
    try:
        c.execute('BEGIN IMMEDIATE'); before = facts(c)
        with pytest.raises(ValueError, match='version-4 context'):
            apply4(c, adapter.request('create_project', project_id=uid(), name='Not a v4 route'), adapter.context)
        assert facts(c) == before
        c.execute('ROLLBACK')
    finally:c.close()


def test_nested_projects_and_three_task_levels_preserve_identity_and_canonical_receipt(adapter):
    a = adapter; root = a.project(); deep = root
    for _ in range(5): deep = a.project(deep)
    task = a.task(deep); child = a.task(deep, task); leaf = a.task(deep, child)
    state = a.state(); rows = {t['task_id']: t for t in state['tasks']}
    assert len(state['projects']) == 6 and len(rows) == 3
    assert {rows[k]['project_id'] for k in (task, child, leaf)} == {deep}
    assert [rows[k]['depth'] for k in (task, child, leaf)] == [1, 2, 3]
    rejected(a, a.request('create_task', task_id=uid(), name='Fourth', **ui.new_task_review(
        dict(state, active=None), task, deep) | dict(parent_task_id=leaf, expected_parent_version=1)))
    with a.reader() as c:
        receipt = c.execute("SELECT * FROM committed_requests WHERE operation='create_task' ORDER BY commit_seq DESC LIMIT 1").fetchone()
        assert receipt['receipt_class'] == 'administrative'
        assert rows[leaf]['created_request_id'] == receipt['request_id']
        assert rows[leaf]['created_utc_us'] == rows[leaf]['updated_utc_us'] == receipt['action_utc_us']


@pytest.mark.parametrize('bad', ['missing', 'null', 'unknown', 'invalid', 'version', 'ancestry', 'archived', 'inherited archive', 'child mismatch', 'parent version', 'running parent'])
def test_task_creation_refusals_are_atomic(adapter, bad):
    a = adapter; p = a.project(); q = a.project(); deep = a.project(p); parent = a.task(deep)
    args = dict(task_id=uid(), name='Child', **ui.new_task_review(a.state(), parent if bad in ('child mismatch', 'parent version', 'running parent') else None, deep))
    if bad == 'missing': args.pop('project_id')
    elif bad == 'null': args['project_id'] = None
    elif bad == 'unknown': args['project_id'] = uid()
    elif bad == 'invalid': args['project_id'] = 'invalid'
    elif bad == 'version': args['expected_project_version'] = 99
    elif bad == 'ancestry': args['reviewed_destination_project_ancestry'] = []
    elif bad == 'archived': a.lifecycle('project', deep)
    elif bad == 'inherited archive': a.lifecycle('project', p)
    elif bad == 'child mismatch': args['project_id'] = q
    elif bad == 'parent version': args['expected_parent_version'] = 99
    else: a.send('start_timer', task_id=parent, entry_id=uid(), expected_task_version=1)
    rejected(a, a.request('create_task', **args))


def assignment(a, task, destination):
    state = a.state(); t = next(t for t in state['tasks'] if t['task_id'] == task)
    return dict(task_id=task, expected_version=t['version'], project_id=destination,
                reviewed_source_project_ancestry=ui.ancestry(state, t['project_id']),
                reviewed_destination_project_ancestry=ui.ancestry(state, destination))


def test_standalone_assignment_noop_stale_and_work_conservation(adapter):
    a = adapter; p, q = a.project(), a.project(); task = a.task(p); a.dated(task)
    before = a.snapshot(); args = assignment(a, task, q)
    r, _ = a.send('assign_task_to_project', **args)
    after = a.snapshot()
    assert after['work_entries'] == before['work_entries'] and after['work_revisions'] == before['work_revisions']
    assert next(t for t in a.state()['tasks'] if t['task_id'] == task)['version'] == 2
    assert a.execute(r).status == 'committed' and a.snapshot() == after
    rejected(a, a.request('assign_task_to_project', **args))
    a.send('assign_task_to_project', expect='unchanged', **assignment(a, task, q))
    assert a.snapshot() == after


@pytest.mark.parametrize('bad', ['null', 'unknown', 'archived', 'ancestry', 'version', 'has parent', 'has child'])
def test_assignment_refusals_preserve_all_facts(adapter, bad):
    a = adapter; p, q = a.project(), a.project(); task = a.task(p)
    if bad == 'has parent': task = a.task(p, task)
    if bad == 'has child': a.task(p, task)
    args = assignment(a, task, q)
    if bad == 'null': args.update(project_id=None, reviewed_destination_project_ancestry=[])
    elif bad == 'unknown': args['project_id'] = uid()
    elif bad == 'archived': a.lifecycle('project', q)
    elif bad == 'ancestry': args['reviewed_source_project_ancestry'] = []
    elif bad == 'version': args['expected_version'] = 99
    rejected(a, a.request('assign_task_to_project', **args))


def test_atomic_branch_and_project_root_moves_preserve_work_and_active_identity(adapter):
    a = adapter; p, q = a.project(), a.project(); deep = a.project(p)
    root = a.task(deep); a.dated(root, '0:10'); leaf = a.task(deep, root); entry = uid()
    a.send('start_timer', task_id=leaf, entry_id=entry, expected_task_version=1)
    before = a.snapshot(); args = a.move_args(root, q)
    a.send('move_task_branch', **args)
    after = a.snapshot()
    assert after['work_entries'] == before['work_entries'] and after['work_revisions'] == before['work_revisions']
    assert after['active_timer'] == before['active_timer']
    assert {t['project_id'] for t in after['tasks']} == {q}
    a.send('move_project_subtree', **ui.ProjectMoveReview(a.state(), deep).arguments(None))
    assert next(p for p in a.state()['projects'] if p['project_id'] == deep)['parent_project_id'] is None
    current = a.snapshot()
    a.send('move_task_branch', expect='unchanged', **a.move_args(root, q))
    assert a.snapshot() == current


@pytest.mark.parametrize('bad', ['null', 'missing member', 'duplicate member', 'member version', 'source project', 'ancestry', 'archived', 'depth', 'running parent'])
def test_branch_move_refusals_are_atomic(adapter, bad):
    a = adapter; p, q = a.project(), a.project(); root = a.task(p); leaf = a.task(p, root); other = a.task(q)
    args = a.move_args(root, q)
    if bad == 'null': args.update(destination_project_id=None, expected_destination_project_version=None, reviewed_destination_project_ancestry=[])
    elif bad == 'missing member': args['reviewed_subtree'].pop()
    elif bad == 'duplicate member': args['reviewed_subtree'].append(dict(args['reviewed_subtree'][0]))
    elif bad == 'member version': args['reviewed_subtree'][0]['expected_version'] = 99
    elif bad == 'source project': args['source_project_id'] = None
    elif bad == 'ancestry': args['reviewed_source_project_ancestry'] = []
    elif bad == 'archived': a.lifecycle('project', q)
    elif bad == 'depth':
        bottom = a.task(q, a.task(q, other)); args.update(destination_parent_task_id=bottom, expected_destination_parent_version=1)
    else:
        a.send('start_timer', task_id=other, entry_id=uid(), expected_task_version=1)
        args.update(destination_parent_task_id=other, expected_destination_parent_version=1)
    rejected(a, a.request('move_task_branch', **args))


def test_templates_management_real_destinations_and_definition_independence(adapter):
    a = adapter; p = a.project(a.project()); parent = a.task(p); definition = a.template(2)
    a.send('edit_template', template_id=definition['template_id'], expected_version=1, name='Edited', nodes=definition['nodes'])
    definition = a.state()['templates'][0]
    a.send('duplicate_template', template_id=uid(), name='Copy', source_template_id=definition['template_id'],
           expected_source_version=definition['version'], reviewed_source=definition,
           node_mapping=sorted([dict(node_id=n['node_id'], new_node_id=uid()) for n in definition['nodes']], key=lambda r:r['node_id']))
    a.lifecycle('template', definition['template_id']); a.lifecycle('template', definition['template_id'], 'unarchive')
    definition = next(t for t in a.state()['templates'] if t['template_id'] == definition['template_id'])
    r, result = a.send('apply_template', **a.apply_args(definition, p, parent))
    created = {r['task_id'] for r in result.result['created_tasks']}
    assert all(t['project_id'] == p for t in a.state()['tasks'])
    assert len(created) == 2 and len({t['task_id'] for t in a.state()['tasks']}) == 3
    assert sum(x['request_id'] == r.request_id for x in a.snapshot()['committed_requests']) == 1


@pytest.mark.parametrize('bad', ['null', 'unknown', 'archived', 'ancestry', 'definition', 'mapping', 'depth', 'running', 'parent mismatch'])
def test_template_apply_refusals_preserve_definition_and_tasks(adapter, bad):
    a = adapter; p, q = a.project(), a.project(); parent = a.task(p); definition = a.template(2)
    args = a.apply_args(definition, p)
    if bad == 'null': args.update(destination_project_id=None, expected_destination_project_version=None, reviewed_destination_project_ancestry=[])
    elif bad == 'unknown': args['destination_project_id'] = uid()
    elif bad == 'archived': a.lifecycle('project', p)
    elif bad == 'ancestry': args['reviewed_destination_project_ancestry'] = []
    elif bad == 'definition': args['expected_template_version'] = 99
    elif bad == 'mapping': args['node_mapping'].append(dict(args['node_mapping'][0]))
    elif bad == 'depth': args = a.apply_args(definition, p, a.task(p, parent))
    elif bad == 'running':
        args = a.apply_args(definition, p, parent); a.send('start_timer', task_id=parent, entry_id=uid(), expected_task_version=1)
    else: args = a.apply_args(definition, q, parent)
    rejected(a, a.request('apply_template', **args))


@pytest.mark.parametrize('phase', ['facts', 'receipt', 'verification', 'commit_before', 'commit_after'])
def test_owner_faults_rollback_or_independently_prove_exact_receipt(adapter, phase):
    a = adapter; before = a.snapshot(); primary = OSError('original '+phase)
    def fault(point, c):
        if point == phase: raise primary
    a.checkpoint = fault
    r = a.request('create_project', project_id=uid(), name='Fault boundary')
    result = a.execute(r)
    assert result.error is primary
    if phase == 'commit_after':
        assert result.status == 'committed' and a.inspect(r).status == 'committed'
        retained = a.snapshot(); a.checkpoint = lambda *args: None
        assert a.execute(r).status == 'committed' and a.snapshot() == retained
    else: assert result.status == 'rolled_back' and a.snapshot() == before


def test_unknown_acknowledgement_retains_original_and_never_blindly_retries(adapter, monkeypatch):
    a = adapter
    def fault(point, c):
        if point == 'commit_after': raise OSError('Lost acknowledgment')
    a.checkpoint = fault; original_inspect = a.inspect
    monkeypatch.setattr(a, 'inspect', lambda request: Outcome('unverified'))
    r = a.request('create_project', project_id=uid(), name='Committed unknown'); result = a.execute(r)
    assert result.status == 'unverified' and a.pending is r
    before = a.snapshot(); a.checkpoint = lambda *args: None
    assert a.execute(r).status == 'unavailable' and a.snapshot() == before
    monkeypatch.setattr(a, 'inspect', original_inspect)
    assert a.reconcile(replace(r)).status == 'unavailable'
    assert a.reconcile(r).status == 'committed' and a.pending is None and a.snapshot() == before
    assert a.execute(replace(r, action_utc_us=r.action_utc_us+1)).status == 'rejected'


def test_owner_verifies_prior_post_and_independent_committed_state(adapter, monkeypatch):
    import schema5_cases
    original = schema5_cases.verify_transaction; observed = []
    def capture(c):
        observed.append((c.in_transaction, c.execute('SELECT count(*) FROM committed_requests').fetchone()[0]))
        return original(c)
    monkeypatch.setattr(schema5_cases, 'verify_transaction', capture)
    a = adapter
    r = a.request('create_project', project_id=uid(), name='Verification phases')
    assert a.execute(r).status == 'committed'
    a.snapshot()
    assert observed == [(True,0), (True,1), (True,1)]


def test_cleanup_uncertainty_preserves_primary_and_blocks_reopening_until_closed(adapter):
    a = adapter
    primary = OSError('Original operation fault'); cleanup = OSError('Connection lifetime unverified')
    def fault(phase, c):
        if phase == 'facts': raise primary
        if phase == 'close': raise cleanup
    a.checkpoint = fault
    r = a.request('create_project', project_id=uid(), name='Rolled back but cleanup unknown')
    result = a.execute(r)
    assert result.status == 'unverified' and result.error is primary and a.retired is not None
    assert any('Connection close failed' in n for n in primary.__notes__)
    assert a.execute(r).status == 'unavailable'
    a.retired.close(); a.retired = None; a.checkpoint = lambda *args: None
    assert a.reconcile(r).status == 'absent'
    assert a.execute(r).status == 'committed'


def test_valid_task_reparenting_and_inherited_archive_lifecycle(adapter):
    a = adapter; p = a.project(); q = a.project(); target = a.task(q); root = a.task(p); leaf = a.task(p, root)
    a.send('move_task_branch', **a.move_args(root, q, target))
    rows = {t['task_id']:t for t in a.state()['tasks']}
    assert rows[root]['parent_task_id'] == target and rows[leaf]['depth'] == 3
    a.send('move_task_branch', **a.move_args(root, q))
    a.lifecycle('task', leaf); a.lifecycle('project', q); a.lifecycle('project', q, 'unarchive')
    rows = {t['task_id']:t for t in a.state()['tasks']}
    assert rows[leaf]['explicit_archived'] and rows[leaf]['effective_archived']
    a.lifecycle('task', leaf, 'unarchive')
    r, _ = a.send('start_timer', task_id=leaf, entry_id=uid(), expected_task_version=rows[leaf]['version']+1)
    before = a.snapshot()
    a.lifecycle('project', q, expect='rejected')
    assert a.snapshot() == before and a.state()['active']['entry_id'] == r.args()['entry_id']


@pytest.mark.parametrize('malformed', ['duck type', 'noncanonical bytes', 'boolean time'])
def test_canonical_request_boundary_refuses_before_mutation(adapter, malformed):
    a = adapter; c = a.connect(); request = a.request('create_project', project_id=uid(), name='Invalid protocol')
    if malformed == 'duck type':
        class Fake:
            def content(self): return request.content()
        incoming = Fake()
    elif malformed == 'noncanonical bytes': incoming = replace(request, arguments=b'{ "name": "Invalid protocol" }')
    else: incoming = replace(request, action_utc_us=True)
    try:
        c.execute('BEGIN IMMEDIATE'); before = facts(c)
        with pytest.raises(ValueError): apply_operation(c, incoming, a.context)
        assert facts(c) == before
        c.execute('ROLLBACK')
    finally:c.close()


def test_isolated_source_has_no_opener_transaction_commands_or_production_adapter_imports():
    root = Path(__file__).resolve().parents[2]
    for name in ('schema5_services.py', 'schema5_evidence.py'):
        text = (root/'src/chronicle'/name).read_text(); tree = ast.parse(text)
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
            assert not isinstance(call.func, ast.Name) or call.func.id not in ('SQLiteStore', 'DatabaseWorker', 'ChronicleApp')
            if isinstance(call.func, ast.Attribute): assert call.func.attr not in ('connect', 'commit', 'rollback', 'close')
            if isinstance(call.func, ast.Attribute) and call.func.attr == 'execute' and call.args and isinstance(call.args[0], ast.Constant):
                assert not str(call.args[0].value).startswith(('BEGIN', 'COMMIT', 'ROLLBACK'))
    for path in (root/'src/chronicle').glob('*.py'):
        assert 'schema5_cases' not in path.read_text()
