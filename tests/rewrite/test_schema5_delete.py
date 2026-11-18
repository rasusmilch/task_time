"""Nested unused-only Delete, independent survivors and no-retry uncertainty."""
from chronicle.schema5_services import apply_operation
from schema5_cases import adapter, Schema5Adapter, uid
from test_schema5_services import rejected
import pytest


def test_nested_unused_delete_retires_only_owned_receipts_and_preserves_high_water(adapter):
    a = adapter; root = a.project(); deep = a.project(a.project(root)); task = a.task(deep); a.task(deep, task)
    unrelated = a.project(); other = a.task(unrelated); a.dated(other)
    before = a.snapshot(); request = a.delete_request('project', deep)
    retired = {r['request_id'] for r in request.args()['review']['retire_receipts']}
    result = a.execute(request); assert result.status == 'committed', result
    after = a.snapshot()
    assert after['sqlite_sequence'] == before['sqlite_sequence']
    assert {r['request_id'] for r in before['committed_requests']} - {r['request_id'] for r in after['committed_requests']} == retired
    assert all(r['receipt_class'] == 'administrative' for r in before['committed_requests'] if r['request_id'] in retired)
    assert after['work_entries'] == before['work_entries'] and after['work_revisions'] == before['work_revisions']
    assert len(after['tasks']) == 1 and after['tasks'][0]['task_id'] == other
    assert not any(r['operation'] in ('delete_task','delete_project','delete_template') for r in after['committed_requests'])


def test_partial_apply_delete_refuses_whole_unused_scope_can_retire_apply(adapter):
    a = adapter; p = a.project(); definition = a.template(2)
    r, result = a.send('apply_template', **a.apply_args(definition, p))
    leaf = result.result['created_tasks'][-1]['task_id']
    partial = a.delete_request('task', leaf)
    assert not partial.args()['review']['eligible']
    rejected(a, partial)
    whole = a.delete_request('project', p)
    assert whole.args()['review']['eligible']
    assert r.request_id in {row['request_id'] for row in whole.args()['review']['retire_receipts']}
    highwater = a.snapshot()['sqlite_sequence']
    assert a.execute(whole).status == 'committed'
    final = a.snapshot()
    assert not final['tasks'] and not final['projects']
    assert final['template_definitions'] and final['sqlite_sequence'] == highwater


@pytest.mark.parametrize('protected', ['work', 'export', 'confirmation', 'active'])
def test_protected_work_export_zero_confirmation_and_active_scope_refuse(adapter, protected):
    a = adapter; p = a.project(); task = a.task(p)
    if protected == 'work': a.dated(task)
    elif protected == 'export': a.export()
    elif protected == 'confirmation': a.manual(task, 0)
    else: a.send('start_timer', task_id=task, entry_id=uid(), expected_task_version=1)
    request = a.delete_request('project', p)
    assert not request.args()['review']['eligible']
    rejected(a, request)


@pytest.mark.parametrize('invalid', ['delete', ' DELETE', 'DELETE ', ''])
def test_delete_requires_exact_typed_confirmation(adapter, invalid):
    a = adapter; p = a.project(); a.task(p)
    rejected(a, a.delete_request('project', p, invalid))


def test_stale_delete_review_and_ordinary_delete_dispatch_refuse(adapter):
    a = adapter; p = a.project(); task = a.task(p); request = a.delete_request('task', task)
    a.send('rename_task', task_id=task, expected_version=1, name='Changed')
    rejected(a, request)
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        with pytest.raises(ValueError, match='separate no-receipt'): apply_operation(c, a.delete_request('task', task), a.context)
        c.execute('ROLLBACK')
    finally: c.close()


def test_definition_delete_after_apply_retains_protected_instances_and_frozen_receipts(adapter):
    a = adapter; p = a.project(); definition = a.template(2)
    duplicate, _ = a.send('duplicate_template', template_id=uid(), name='Surviving copy',
        source_template_id=definition['template_id'], expected_source_version=definition['version'], reviewed_source=definition,
        node_mapping=sorted([dict(node_id=n['node_id'], new_node_id=uid()) for n in definition['nodes']], key=lambda r:r['node_id']))
    applied, result = a.send('apply_template', **a.apply_args(definition, p))
    task = result.result['created_tasks'][-1]['task_id']; a.dated(task); value = a.export(); a.manual(task)
    before = a.snapshot(); request = a.delete_request('template', definition['template_id'])
    assert request.args()['review']['eligible']
    assert a.execute(request).status == 'committed'
    after = a.snapshot()
    assert len(after['template_definitions']) == 1 and after['template_definitions'][0]['name'] == 'Surviving copy'
    assert all(n['template_id'] == duplicate.args()['template_id'] for n in after['template_nodes'])
    for table in ('tasks','work_entries','work_revisions','timesheet_exports','timesheet_export_tasks',
                  'timesheet_export_week_basis','timesheet_export_cells','polr_confirmation_batches','polr_confirmation_cells','polr_confirmed_current','sqlite_sequence'):
        assert after[table] == before[table]
    assert next(r for r in after['committed_requests'] if r['request_id'] == applied.request_id) == next(r for r in before['committed_requests'] if r['request_id'] == applied.request_id)
    assert next(r for r in after['committed_requests'] if r['request_id'] == duplicate.request_id) == next(r for r in before['committed_requests'] if r['request_id'] == duplicate.request_id)
    assert a.read('timesheet_export', value.export_id) == value


@pytest.mark.parametrize('phase', ['facts', 'verification', 'commit_after'])
def test_delete_faults_never_retry_uncertain_commit_or_infer_history_from_presence(adapter, phase):
    a = adapter; p = a.project(); a.task(p); request = a.delete_request('project', p); before = a.snapshot()
    primary = OSError('Delete '+phase)
    def fault(point, c):
        if point == phase: raise primary
    a.checkpoint = fault; result = a.execute(request)
    assert result.error is primary
    if phase == 'commit_after':
        assert result.status == 'unverified' and a.unresolved_delete
        observed = a.snapshot(); assert not observed['projects'] and not observed['tasks']
        assert a.inspect(request).status == 'unverified'
        assert a.execute(request).status == 'unavailable'
        assert a.execute(a.request('create_project', project_id=uid(), name='Blocked')).status == 'unavailable'
        assert a.snapshot() == observed
        reopened = Schema5Adapter(a.path, a.context.dataset_id)
        with pytest.raises(ValueError, match='presence is not historical Delete proof'):
            reopened.delete_request('project', p)
        assert reopened.snapshot() == observed
    else:
        assert result.status == 'rolled_back' and not a.unresolved_delete
        assert a.snapshot() == before
