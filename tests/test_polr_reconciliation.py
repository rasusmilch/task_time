"""Read-only daily reconciliation against isolated Actual and journal evidence."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import inspect
from uuid import uuid4

import pytest

from task_timer import app as app_module
from task_timer.accounting import UnsupportedLegacyDurationError
from task_timer.polr_reconciliation import build_polr_reconciliation
from test_mixed_accounting import setup, dated, local, files, MON, TUE, SAT, SUN, CUTOFF
from test_polr_confirmation_replay import cell, batch
from test_polr_confirmation_writer import register


def capture(s):
    return (deepcopy(s.state), deepcopy(s.events), s.get_effective_polr_confirmations(),
            s.list_timesheet_export_snapshots(), s.snapshot_dict(), s.list_time_submissions(), files(s))


def calculate(s, monkeypatch, start=MON, end=TUE, **options):
    before = capture(s)
    options.setdefault('cutoff_utc', CUTOFF)
    def forbidden(*args, **kwargs):
        pytest.fail('Reconciliation attempted a write, state installation, rendering or implicit clock')
    try:
        with monkeypatch.context() as m:
            for name in ('append_event', 'synchronize_journal', 'save_snapshot', 'save_manifest',
                         'rotate_if_needed', '_atomic_write_json'):
                m.setattr(s.storage, name, forbidden)
            for name in ('_rebuild_state', '_install_export_journal', '_save_snapshot', 'create_backup_now',
                         'materialize_timesheet_export', 'prepare_polr_confirmation_batch',
                         'register_prepared_polr_confirmation_batch'):
                m.setattr(s, name, forbidden)
            m.setattr(s.backups, 'create_backup', forbidden)
            for name in ('utc_now', 'build_decimal_timesheet_text', 'build_timesheet_text'):
                m.setattr(app_module, name, forbidden)
            result = s.calculate_polr_reconciliation(start, end, **options)
        assert set(result) == {'actual', 'cells'}
        assert all(set(value) == {'actual_hundredths', 'confirmed_hundredths', 'delta_hundredths',
                                  'enter_hundredths', 'batch_event_id'} for value in result['cells'].values())
        return result
    finally:
        assert capture(s) == before


def expected(actual, confirmed=None, batch_id=None):
    return {'actual_hundredths': actual, 'confirmed_hundredths': confirmed,
            'delta_hundredths': None if confirmed is None else actual - confirmed,
            'enter_hundredths': actual, 'batch_event_id': batch_id}


def test_unknown_and_explicit_zero_are_distinct_included_cells(setup, monkeypatch):
    s, a, b, _, _, _ = setup
    dated(s, a, MON, 3600)
    event = register(s, cell(b, 0))
    result = calculate(s, monkeypatch, all_tasks=True)
    assert result['cells'] == {(a, str(MON)): expected(100), (a, str(TUE)): expected(0),
                               (b, str(MON)): expected(0, 0, event['event_id']), (b, str(TUE)): expected(0)}
    assert result['actual']['tasks'][b]['daily_seconds'] == {}


def test_mandatory_frozen_three_to_five_and_absolute_replacement(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    dated(s, a, MON, 10800)
    export = s.prepare_timesheet_export_snapshot(MON, TUE, cutoff_utc=CUTOFF, all_tasks=True)
    s.register_prepared_timesheet_export(export)
    dated(s, a, MON, 7200)
    first = register(s, cell(a, 300, source=export['event_id']))
    before = calculate(s, monkeypatch, all_tasks=True)
    assert before['cells'][a, str(MON)] == expected(500, 300, first['event_id'])
    assert before['actual']['tasks'][a]['daily_seconds'][MON] == 18000
    second = register(s, cell(a, 500, prior=first['event_id']))
    after = calculate(s, monkeypatch, all_tasks=True)
    assert after['cells'][a, str(MON)] == expected(500, 500, second['event_id'])
    assert before['cells'][a, str(MON)] == expected(500, 300, first['event_id'])
    assert s.get_timesheet_export_snapshot(export['event_id']) == export


def test_corrections_and_removal_keep_confirmed_zero_actual_dates(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    entry = dated(s, a, MON, 10800)
    event = register(s, cell(a, 300))
    dated(s, a, MON, 9000, entry, 'dated_duration_corrected')
    corrected = calculate(s, monkeypatch, task_ids=(a,))
    assert corrected['cells'][a, str(MON)] == expected(250, 300, event['event_id'])
    s._append(a, 'dated_duration_deleted', {'entry_id': entry, 'reason': 'Remove erroneous work'})
    removed = calculate(s, monkeypatch, task_ids=(a,))
    assert removed['actual']['tasks'][a]['daily_seconds'] == {}
    assert removed['cells'][a, str(MON)] == expected(0, 300, event['event_id'])


def test_manual_partial_batch_leaves_unchecked_confirmations_unchanged(setup, monkeypatch):
    s, a, b, _, _, _ = setup
    dated(s, a, MON, 3600)
    first = register(s, cell(a, 250), cell(b, 200, day=TUE))
    second = register(s, cell(a, 50, prior=first['event_id']))
    result = calculate(s, monkeypatch, all_tasks=True)
    assert result['cells'][a, str(MON)] == expected(100, 50, second['event_id'])
    assert result['cells'][b, str(TUE)] == expected(0, 200, first['event_id'])
    assert result['cells'][b, str(MON)] == expected(0)


@pytest.mark.parametrize('seconds,hundredths', [(0.001, 0), (17.999, 0), (18, 1), (53.999, 1), (54, 2), (60.5, 2)])
def test_half_up_fractional_actual_is_never_rounded_or_erased(setup, monkeypatch, seconds, hundredths):
    s, a, _, _, _, _ = setup
    dated(s, a, MON, seconds)
    result = calculate(s, monkeypatch, task_ids=(a,))
    assert result['cells'][a, str(MON)] == expected(hundredths)
    assert result['actual']['tasks'][a]['daily_seconds'][MON] == seconds


def test_three_sixty_second_cells_conserve_without_project_cells(setup, monkeypatch):
    s, a, b, p, q, _ = setup
    u = s.create_task('Unassigned', '')
    for task in (a, b, u): dated(s, task, MON, 60)
    for regroup in (False, True):
        if regroup: s.assign_task_to_project(b, q)
        result = calculate(s, monkeypatch, MON, MON, all_tasks=True)
        assert len(result['cells']) == 3
        assert [v['actual_hundredths'] for v in result['cells'].values()] == [2, 2, 2]
        assert sum(v['actual_hundredths'] for v in result['cells'].values()) == 6
        assert result['actual']['application']['window_seconds'] == 180
        assert p not in {task for task, _ in result['cells']}


def test_selection_union_names_membership_deletion_and_scope_boundaries(setup, monkeypatch):
    s, a, b, p, q, _ = setup
    u = s.create_task('Same', '')
    s.update_task(a, 'Same', '')
    s.update_task(b, 'Same', '')
    for task in (a, b, u): dated(s, task, MON, 3600)
    event = register(s, cell(a, 50), cell(a, 100, day=SAT), cell(b, 0), cell(u, 250))
    assert calculate(s, monkeypatch)['cells'] == {}
    assert calculate(s, monkeypatch, task_ids=(), project_ids=())['cells'] == {}
    empty_project = s.create_project('Empty')
    assert calculate(s, monkeypatch, project_ids=(empty_project,))['cells'] == {}
    union = calculate(s, monkeypatch, task_ids=(a, a), project_ids=(p, p), include_unassigned=True)
    assert set(union['cells']) == {(task, str(day)) for task in (a, b, u) for day in (MON, TUE)}
    assert len(union['actual']['tasks']) == 3 and union['actual']['scope'] == 'selected'
    assert {row['name'] for row in union['actual']['tasks'].values()} == {'Same'}
    selected = calculate(s, monkeypatch, task_ids=(a,))
    assert selected['actual']['projects'][p]['scope'] == 'selected_tasks'
    assert selected['cells'][a, str(TUE)] == expected(0)
    assert (a, str(SAT)) not in selected['cells']
    s.assign_task_to_project(a, q)
    assert set(calculate(s, monkeypatch, project_ids=(p,))['actual']['tasks']) == {b}
    moved = calculate(s, monkeypatch, project_ids=(q,))
    assert moved['actual']['tasks'][a]['project_id'] == q
    assert moved['cells'][a, str(MON)] == expected(100, 50, event['event_id'])
    s.delete_task_only(a)
    assert calculate(s, monkeypatch, task_ids=(a,))['cells'] == {}
    historical = calculate(s, monkeypatch, task_ids=(a,), include_deleted=True)
    assert historical['actual']['tasks'][a]['is_deleted']
    assert historical['cells'][a, str(MON)] == expected(100, 50, event['event_id'])
    unassigned = calculate(s, monkeypatch, include_unassigned=True)
    assert set(unassigned['actual']['tasks']) == {u}


def test_single_read_single_actual_call_forwards_original_arguments(setup, monkeypatch):
    s, a, _, p, _, _ = setup
    read, accounting = s.storage.iter_all_events, s.calculate_date_window
    reads, calls, reports = [], [], []
    ids, projects = [a, a], [p]
    cutoff = CUTOFF.replace(microsecond=123456)
    def strict_read(*args, **kwargs):
        reads.append((args, kwargs))
        return read(*args, **kwargs)
    def actual(*args, **kwargs):
        calls.append((args, kwargs))
        reports.append(accounting(*args, **kwargs))
        return reports[-1]
    monkeypatch.setattr(s.storage, 'iter_all_events', strict_read)
    monkeypatch.setattr(s, 'calculate_date_window', actual)
    result = calculate(s, monkeypatch, MON, SUN, cutoff_utc=cutoff, all_tasks=False, task_ids=ids,
                       project_ids=projects, include_unassigned=True, include_deleted=True)
    assert reads == [((), {'strict': True})]
    assert calls == [((MON, SUN), {'cutoff_utc': cutoff, 'all_tasks': False, 'task_ids': ids,
                                 'project_ids': projects, 'include_unassigned': True, 'include_deleted': True})]
    assert calls[0][1]['task_ids'] is ids and calls[0][1]['project_ids'] is projects
    assert calls[0][1]['cutoff_utc'] is cutoff
    assert result['actual'] == reports[0] and result['actual'] is not reports[0]
    assert inspect.signature(s.calculate_polr_reconciliation) == inspect.signature(accounting)


def test_running_cutoff_and_physical_confirmation_order_ignore_audit_cutoff(setup, monkeypatch):
    s, a, _, _, _, clock = setup
    clock[0] = local(s, MON, 9).astimezone(timezone.utc)
    s.start_task(a)
    cutoff = clock[0] + timedelta(hours=1)
    first = register(s, cell(a, 300))
    second = s.prepare_polr_confirmation_batch([cell(a, 50, prior=first['event_id'])])
    second['timestamp_utc'] = '2000-01-01T00:00:00Z'
    s.register_prepared_polr_confirmation_batch(second)
    # Physical order wins regardless of audit timestamps relative to the cutoff.
    register_later = s.prepare_polr_confirmation_batch([cell(a, 75, prior=second['event_id'])])
    register_later['timestamp_utc'] = '2030-01-01T00:00:00Z'
    s.register_prepared_polr_confirmation_batch(register_later)
    result = calculate(s, monkeypatch, task_ids=(a,), cutoff_utc=cutoff)
    assert result['cells'][a, str(MON)] == expected(100, 75, register_later['event_id'])
    assert result['actual']['tasks'][a]['daily_seconds'][MON] == 3600
    assert s.state.tasks[a].is_running


def test_fresh_journal_projection_does_not_install_or_use_stale_cache(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    event = batch(cell(a, 123))
    s.storage.append_event(event)
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    assert s.get_effective_polr_confirmations() == {}
    result = calculate(s, monkeypatch, task_ids=(a,))
    assert result['cells'][a, str(MON)] == expected(0, 123, event['event_id'])
    assert s.get_effective_polr_confirmations() == {}
    s._polr_confirmations = {(a, str(TUE)): {'confirmed_hundredths': 999, 'batch_event_id': str(uuid4())}}
    result = calculate(s, monkeypatch, task_ids=(a,))
    assert result['cells'][a, str(MON)] == expected(0, 123, event['event_id'])
    assert result['cells'][a, str(TUE)] == expected(0)


@pytest.mark.parametrize('empty', [False, True])
@pytest.mark.parametrize('fault', ['missing-active', 'missing-manifest', 'partial', 'invalid-confirmation', 'conflict', 'denied'])
def test_unhealthy_journal_fails_even_with_empty_selection(setup, monkeypatch, empty, fault):
    s, a, _, _, _, _ = setup
    if fault == 'missing-active': s.storage.active_path.unlink()
    elif fault == 'missing-manifest': s.storage.manifest_path.unlink()
    elif fault == 'partial':
        with s.storage.active_path.open('ab') as handle: handle.write(b'{partial')
    elif fault == 'invalid-confirmation': s.storage.append_event(batch(cell(a, prior=str(uuid4()))))
    elif fault == 'conflict':
        event = batch(cell(a))
        s.storage.append_event(event)
        changed = deepcopy(event)
        changed['payload']['cells'][0]['confirmed_hundredths'] += 1
        s.storage.append_event(changed)
    else:
        def denied(*args, **kwargs): raise PermissionError('journal access denied')
        monkeypatch.setattr(s.storage, 'iter_all_events', denied)
    with pytest.raises((ValueError, OSError)):
        calculate(s, monkeypatch, task_ids=() if empty else (a,))


def test_detached_results_repeat_freshness_and_pure_projection_inputs(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    dated(s, a, MON, 3600)
    first = calculate(s, monkeypatch, task_ids=(a,))
    frozen = deepcopy(first)
    event = register(s, cell(a, 125))
    dated(s, a, MON, 1800)
    second = calculate(s, monkeypatch, task_ids=(a,))
    assert second['cells'][a, str(MON)] == expected(150, 125, event['event_id'])
    assert first == frozen
    second['actual']['tasks'][a]['name'] = 'Changed result'
    second['cells'][a, str(MON)]['confirmed_hundredths'] = 999
    assert calculate(s, monkeypatch, task_ids=(a,))['cells'][a, str(MON)] == expected(150, 125, event['event_id'])
    report = s.calculate_date_window(MON, TUE, cutoff_utc=CUTOFF, task_ids=(a,))
    confirmations = s.get_effective_polr_confirmations()
    before = deepcopy(report), deepcopy(confirmations)
    projected = build_polr_reconciliation(report, confirmations)
    assert (report, confirmations) == before
    report['tasks'][a]['daily_seconds'][MON] = 0
    confirmations[a, str(MON)]['confirmed_hundredths'] = 0
    assert projected['cells'][a, str(MON)] == expected(150, 125, event['event_id'])
    assert projected['actual']['tasks'][a]['daily_seconds'][MON] == 5400


@pytest.mark.parametrize('options', [{'task_ids': ('unknown',)}, {'project_ids': ('unknown',)},
                                  {'all_tasks': 1}, {'include_deleted': None}, {'task_ids': 'bad'},
                                  {'cutoff_utc': datetime(2026, 10, 20)}])
def test_invalid_requests_preserve_accounting_failures(setup, monkeypatch, options):
    with pytest.raises(ValueError): calculate(setup[0], monkeypatch, **options)


@pytest.mark.parametrize('start,end', [(TUE, MON), ('2026-10-12', TUE), (MON, date.max)])
def test_invalid_date_windows_preserve_accounting_failures(setup, monkeypatch, start, end):
    with pytest.raises(ValueError): calculate(setup[0], monkeypatch, start, end, all_tasks=True)


def test_unsupported_legacy_duration_remains_an_explicit_accounting_error(setup, monkeypatch):
    s, a, b, _, _, _ = setup
    s.add_manual_duration(a, MON, 3600, 'Legacy')
    with pytest.raises(UnsupportedLegacyDurationError): calculate(s, monkeypatch, all_tasks=True)
    assert calculate(s, monkeypatch, task_ids=(b,))['actual']['tasks'][b]['window_seconds'] == 0
