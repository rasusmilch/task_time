"""Retained real-project work, frozen bytes and independent POL-R examples."""
from dataclasses import replace
import hashlib

import pytest

from chronicle import project_ui as ui
from chronicle.timesheet import from_content, render
from schema5_cases import adapter, uid, M
from test_schema5_services import rejected


def reconciliation(a, task, full=False):
    return a.read('polr_reconciliation', dict(cutoff_utc_us=a.now, period='custom',
        start_date='2026-10-18' if full else '2026-10-19', end_date='2026-10-24' if full else '2026-10-20', scope_kind='selected', task_ids=[task]))


def test_real_timer_correction_switch_work_revisions_and_configuration(adapter):
    a = adapter; p = a.project(); first, second = a.task(p), a.task(p)
    running = uid(); start, _ = a.send('start_timer', task_id=first, entry_id=running, expected_task_version=1)
    a.send('correct_active_start', entry_id=running, expected_version=1, date_text='2026-10-19', time_text='09:59', occurrence=None, comment='Reviewed earlier start')
    corrected = a.state()['active']; next_entry = uid()
    switch, _ = a.send('switch_timer', expected_active_entry_id=running, expected_active_version=2,
                       next_task_id=second, next_entry_id=next_entry, expected_task_version=1)
    stop, _ = a.send('stop_timer', entry_id=next_entry, expected_version=1)
    snapshot = a.snapshot(); revisions = {r['entry_id']:r for r in snapshot['work_revisions']}
    assert a.state()['active'] is None
    assert revisions[running]['start_utc_us'] == corrected['start_utc_us']
    assert revisions[running]['stop_utc_us'] == switch.action_utc_us
    assert revisions[next_entry]['start_utc_us'] == switch.action_utc_us
    assert revisions[next_entry]['stop_utc_us'] == stop.action_utc_us
    assert len(snapshot['active_start_corrections']) == 1
    dated = a.dated(first, '0:10')
    a.send('edit_date_only_work', task_id=first, entry_id=dated, expected_revision=1,
           work_date='2026-10-19', duration_text='0:20', comment='Corrected')
    a.send('delete_work_entry', task_id=first, entry_id=dated, expected_revision=2, comment='Retain history')
    timed = uid(); args = dict(task_id=first, entry_id=timed, start_date='2026-10-19', start_time='09:00',
        end_date='2026-10-19', end_time='09:15', start_occurrence=None, end_occurrence=None, comment='Manual')
    a.send('add_timed_work', **args)
    a.send('edit_closed_timed_work', **dict(args, expected_revision=1, end_time='09:30'))
    a.send('set_week_start', week_start=0, expected_week_start=6)
    a.send('dismiss_polr_reminder_today', local_date='2026-10-19')
    final = a.snapshot()
    assert [r['revision'] for r in final['work_revisions'] if r['entry_id'] == dated] == [1,2,3]
    assert next(r for r in final['work_revisions'] if r['entry_id'] == dated and r['revision'] == 3)['is_deleted'] == 1
    assert final['dataset_meta'][0]['week_start'] == 0
    assert final['dataset_meta'][0]['polr_reminder_dismissed_local_date'] == '2026-10-19'


@pytest.mark.parametrize('monday,tuesday,quarters,adjustment', [
    ('1:08','1:07',(5,4),0), ('1:08','1:08',(5,5),14),
    ('1:10','0:20',(5,1),0), ('0:03','0:03',(1,0),9),
    ('0:15','0:30',(1,2),0)], ids=['C','D','E','F','G'])
def test_independent_C_to_G_frozen_allocation_and_real_project_accounting(adapter, monday, tuesday, quarters, adjustment):
    a = adapter; root = a.project(); deep = a.project(a.project(root)); task = a.task(deep)
    a.dated(task, monday); a.dated(task, tuesday, '2026-10-20')
    value = a.export(scope_kind='selected', task_ids=[task])
    assert tuple(c.suggested_quarters for c in value.cells) == quarters
    assert len(value.basis) == 7 and value.tasks[0].project_id == deep
    assert sum(r.suggested_quarters * 15*M-r.actual_us for r in value.basis) == adjustment*M
    assert a.read('timesheet_export', value.export_id).report_utf8 == value.report_utf8
    state = a.state(); amount = state['report']['individual'][task]['week_us']
    assert state['report']['application']['week_us'] == amount
    assert state['report']['project_direct'][deep]['week_us'] == amount
    assert state['report']['projects'][root]['week_us'] == amount
    before = a.snapshot(); a.read('timesheet_export', value.export_id); a.state()
    assert a.snapshot() == before


def rerender(value):
    labels = tuple(replace(t, ordinal=i) for i,t in enumerate(sorted(value.tasks, key=lambda t:(t.project_name,t.name,t.task_id))))
    order = {t.task_id:i for i,t in enumerate(labels)}
    value = replace(value, tasks=labels,
                    basis=tuple(sorted(value.basis, key=lambda r:(order[r.task_id],r.week_start_date,r.work_date))),
                    cells=tuple(sorted(value.cells, key=lambda r:(order[r.task_id],r.work_date))))
    text = render(value)
    return replace(value, report_text=text, report_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest())


@pytest.mark.parametrize('damage', ['null', 'unknown project', 'different project', 'unknown task', 'omitted task', 'basis'])
def test_crafted_export_refuses_invalid_reviewed_ownership_or_basis(adapter, damage):
    a = adapter; p, q = a.project(), a.project(); first, second = a.task(p), a.task(p)
    a.dated(first); a.dated(second)
    value = a.preview(); label = value.tasks[0]
    if damage == 'null':
        value = replace(value, tasks=(replace(label, project_id=None, project_name='Unassigned'), *value.tasks[1:]))
    elif damage in ('unknown project', 'different project'):
        value = replace(value, tasks=(replace(label, project_id=uid() if damage == 'unknown project' else q), *value.tasks[1:]))
    elif damage == 'unknown task':
        key = uid(); old = label.task_id
        value = replace(value, tasks=(replace(label, task_id=key), *value.tasks[1:]),
                        basis=tuple(replace(r, task_id=key) if r.task_id == old else r for r in value.basis),
                        cells=tuple(replace(r, task_id=key) if r.task_id == old else r for r in value.cells))
    elif damage == 'omitted task':
        value = replace(value, tasks=(replace(value.tasks[1], ordinal=0),),
                        basis=tuple(r for r in value.basis if r.task_id != label.task_id),
                        cells=tuple(r for r in value.cells if r.task_id != label.task_id))
    else:
        value = replace(value, basis=(replace(value.basis[0], actual_us=value.basis[0].actual_us+1), *value.basis[1:]))
    value = rerender(value)
    if damage in ('null', 'unknown project', 'different project', 'omitted task'):
        assert from_content(value.content()) == value  # Refusal must reach ownership, not a broken renderer.
    rejected(a, a.request('register_timesheet_export', candidate=value.content()))


def test_frozen_labels_bytes_and_accounting_survive_task_and_project_moves(adapter):
    a = adapter; root = a.project(name='Root'); deep = a.project(a.project(root)); other = a.project(name='Other')
    parent = a.task(deep); a.dated(parent, '0:10'); child = a.task(deep, parent); a.dated(child, '0:20')
    value = a.export(); before = a.snapshot(); frozen = value.report_utf8
    a.send('rename_project', project_id=deep, expected_version=1, name='Renamed')
    a.send('move_task_branch', **a.move_args(parent, other))
    a.send('move_project_subtree', **ui.ProjectMoveReview(a.state(), deep).arguments(other))
    report = a.state()['report']; after = a.snapshot()
    assert report['application']['today_us'] == 30*M
    assert report['individual'][parent]['today_us'] == 10*M and report['cumulative'][parent]['today_us'] == 30*M
    assert report['project_direct'][other]['today_us'] == report['projects'][other]['today_us'] == 30*M
    assert report['projects'][root]['today_us'] == 0
    assert a.read('timesheet_export', value.export_id) == value
    assert a.read('timesheet_export', value.export_id).report_utf8 == frozen
    for table in ('work_entries','work_revisions','timesheet_exports','timesheet_export_tasks','timesheet_export_week_basis','timesheet_export_cells'):
        assert after[table] == before[table]


def test_source_manual_zero_stale_acknowledgement_and_daily_opposition(adapter):
    a = adapter; p = a.project(); task = a.task(p); a.dated(task, '0:03'); a.dated(task, '0:03', '2026-10-20')
    value = a.export(); report = reconciliation(a, task)
    assert [r['classification'] for r in report['daily_cells']] == ['UNKNOWN','UNKNOWN']
    a.manual(task, 0)
    proposal = a.read('polr_proposal', value.export_id)
    args = dict(batch_id=uid(), mode='source', source_export_id=value.export_id, manual_cells=[], acknowledgements=[], **proposal)
    rejected(a, a.request('confirm_polr_absolute', **args))
    args['acknowledgements'] = [dict(task_id=r['task_id'], work_date=r['work_date'], suggested_quarters=r['suggested_quarters'],
        reviewed_prior_batch_id=r['prior_batch_id'], reviewed_prior_quarters=r['prior_quarters']) for r in args['reviewed_rows']
        if r['requires_stale_acknowledgement'] and dict(task_id=r['task_id'], work_date=r['work_date']) in args['selected_keys']]
    a.send('confirm_polr_absolute', **args)
    report = reconciliation(a, task)
    assert [r['classification'] for r in report['daily_cells']] == ['MATCH','UNKNOWN']
    r, outcome = a.manual(task, 0, '2026-10-20'); zero = outcome.result['batch_id']
    assert a.read('polr_day', dict(task_id=task, work_date='2026-10-20', cutoff_utc_us=a.now))['current_batch_id'] == zero
    assert a.read('polr_batch', zero)['cells'][0]['confirmed_quarters'] == 0
    report = reconciliation(a, task, full=True)
    assert report['task_weeks'][0]['review_complete'] and report['coverage']['complete']
    assert report['task_weeks'][0]['coverage']['NOT_APPLICABLE'] == 5
    other = a.task(p); a.dated(other, '1:15'); a.dated(other, '0:45', '2026-10-20')
    a.manual(other, 4); a.manual(other, 4, '2026-10-20'); report = reconciliation(a, other)
    assert [r['suggested_gap_quarters'] for r in report['daily_cells']] == [1,-1]
    assert [r['classification'] for r in report['daily_cells']] == ['MISMATCH','MISMATCH']
    assert report['task_weeks'][0]['known_confirmed_quarters'] == report['task_weeks'][0]['weekly_target_quarters'] == 8
    assert not report['coverage']['complete']


def test_current_corrections_signed_delta_and_reminder_do_not_rewrite_frozen_report(adapter):
    a = adapter; p = a.project(); task = a.task(p); a.dated(task, '3:00'); original = a.export(); a.manual(task, 12)
    a.dated(task, '2:00'); day = a.read('polr_day', dict(task_id=task, work_date='2026-10-19', cutoff_utc_us=a.now))
    assert (day['actual_hundredths'], day['suggested_quarters'], day['confirmed_quarters'], day['daily_delta_hundredths'], day['suggested_entry_gap_quarters']) == (500,20,12,200,8)
    other = a.task(p); entry = a.dated(other, '3:00'); a.manual(other, 12)
    a.send('edit_date_only_work', task_id=other, entry_id=entry, expected_revision=1,
           work_date='2026-10-19', duration_text='2:30', comment='Correction')
    day = a.read('polr_day', dict(task_id=other, work_date='2026-10-19', cutoff_utc_us=a.now))
    assert (day['actual_hundredths'], day['suggested_quarters'], day['confirmed_quarters'], day['daily_delta_hundredths'], day['suggested_entry_gap_quarters']) == (250,10,12,-50,-2)
    assert a.read('timesheet_export', original.export_id) == original
    a.send('dismiss_polr_reminder_today', local_date='2026-10-19')
    before = a.snapshot(); a.read('polr_reminder', a.now)
    assert a.snapshot() == before
