"""Frozen export review/selection, with isolated nonpersistent service orchestration."""
from copy import deepcopy
from uuid import uuid4

import pytest

from task_timer import app as app_module
from test_mixed_accounting import setup, dated, files, MON, TUE, CUTOFF
from test_polr_confirmation_replay import cell
from test_polr_confirmation_writer import register, occurrences


def capture(s):
    return (deepcopy(s.state), deepcopy(s.events), s.get_effective_polr_confirmations(),
            s.list_timesheet_export_snapshots(), s.snapshot_dict(), s.list_time_submissions(), files(s))


def readonly(s, monkeypatch, operation, *, proposal=False):
    before = capture(s)
    def forbidden(*args, **kwargs): pytest.fail('Proposal workflow invoked a forbidden side effect/cache/Actual reader')
    try:
        with monkeypatch.context() as m:
            for name in ('append_event', 'synchronize_journal', 'save_snapshot', 'save_manifest',
                         'rotate_if_needed', '_atomic_write_json'):
                m.setattr(s.storage, name, forbidden)
            for name in ('_rebuild_state', '_install_export_journal', '_save_snapshot', 'create_backup_now',
                         'materialize_timesheet_export', 'register_prepared_polr_confirmation_batch',
                         'calculate_date_window', 'calculate_polr_reconciliation',
                         'get_timesheet_export_snapshot', 'get_effective_polr_confirmations'):
                m.setattr(s, name, forbidden)
            m.setattr(s.backups, 'create_backup', forbidden)
            m.setattr(s, '_verify_timesheet_export_file', forbidden)
            for name in ('build_decimal_timesheet_text', 'build_timesheet_text'):
                m.setattr(app_module, name, forbidden)
            if proposal:
                m.setattr(app_module, 'utc_now', forbidden)
                m.setattr(app_module, 'uuid4', forbidden)
            return operation()
    finally:
        assert capture(s) == before


def propose(s, monkeypatch, export):
    return readonly(s, monkeypatch, lambda: s.propose_export_polr_confirmation(export['event_id']), proposal=True)


def prepare_reviewed(s, monkeypatch, proposal, **options):
    before = deepcopy(proposal), deepcopy(options)
    try:
        return readonly(s, monkeypatch, lambda: s.prepare_export_polr_confirmation_batch(proposal, **options))
    finally:
        assert (proposal, options) == before


def export(s, **selection):
    event = s.prepare_timesheet_export_snapshot(MON, TUE, cutoff_utc=CUTOFF, **selection)
    s.register_prepared_timesheet_export(event)
    return event


def key(task, day=MON): return task, day.isoformat()


def row(proposal, task, day=MON):
    return next(r for r in proposal['cells'] if (r['task_id'], r['work_date']) == key(task, day))


@pytest.fixture
def frozen(setup):
    s, a, b, p, q, clock = setup
    dated(s, a, MON, 10800)
    dated(s, b, TUE, 3600)
    return s, a, b, p, q, export(s, all_tasks=True)


def test_frozen_names_amounts_order_and_coverage_after_current_changes(frozen, monkeypatch):
    s, a, b, p, q, event = frozen
    before = propose(s, monkeypatch, event)
    assert set(before) == {'source_export_id', 'cells'}
    assert len(before['cells']) == 4
    expected_fields = {'task_id', 'work_date', 'task_name', 'proposed_hundredths',
                       'prior_confirmed_hundredths', 'expected_prior_confirmation_id',
                       'requires_stale_acknowledgement'}
    assert all(set(r) == expected_fields for r in before['cells'])
    assert [key(r['task_id'], MON if r['work_date'] == str(MON) else TUE) for r in before['cells']] == sorted(
        [key(t, day) for t in (a, b) for day in (MON, TUE)])
    assert row(before, a)['proposed_hundredths'] == 300
    assert row(before, b, TUE)['proposed_hundredths'] == 100
    assert row(before, a, TUE)['proposed_hundredths'] == 0
    assert row(before, a)['prior_confirmed_hundredths'] is None
    s.update_task(a, 'Renamed after export', '')
    s.assign_task_to_project(a, q)
    entry = dated(s, a, MON, 7200)
    dated(s, a, MON, 9000, entry, 'dated_duration_corrected')
    s.delete_task_only(a)
    assert propose(s, monkeypatch, event) == before
    assert prepare_reviewed(s, monkeypatch, before, selected_cells=[key(a)])['payload']['cells'] == [
        cell(a, 300, source=event['event_id'])]
    before['cells'][0]['task_name'] = 'Changed result'
    assert propose(s, monkeypatch, event)['cells'][0]['task_name'] != 'Changed result'


def test_default_positive_only_equal_values_and_explicit_zero(frozen, monkeypatch):
    s, a, b, _, _, event = frozen
    known = register(s, cell(a, 300), cell(b, 0))
    proposal = propose(s, monkeypatch, event)
    assert row(proposal, b)['prior_confirmed_hundredths'] == 0
    assert row(proposal, b)['expected_prior_confirmation_id'] == known['event_id']
    assert not row(proposal, a)['requires_stale_acknowledgement']
    prepared = prepare_reviewed(s, monkeypatch, proposal, batch_id=str(uuid4()))
    assert [(r['task_id'], r['work_date']) for r in prepared['payload']['cells']] == sorted([key(a), key(b, TUE)])
    assert next(r for r in prepared['payload']['cells'] if r['task_id'] == a)['expected_prior_confirmation_id'] == known['event_id']
    zero = prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(b)])
    assert zero['payload']['cells'] == [cell(b, 0, source=event['event_id'], prior=known['event_id'])]
    assert occurrences(s) == [known]  # neither preparation registered anything


def test_nonzero_rounded_zero_all_zero_and_empty_exports(setup, monkeypatch):
    s, a, b, _, _, _ = setup
    dated(s, a, MON, 0.001)
    zero = export(s, task_ids=(a,))
    proposal = propose(s, monkeypatch, zero)
    assert row(proposal, a)['proposed_hundredths'] == 0
    with pytest.raises(ValueError, match='Select at least'):
        prepare_reviewed(s, monkeypatch, proposal)
    prepared = prepare_reviewed(s, monkeypatch, proposal, selected_cells=(key(a),))
    assert prepared['payload']['cells'] == [cell(a, 0, source=zero['event_id'])]
    assert s.state.tasks[a].dated_durations[next(iter(s.state.tasks[a].dated_durations))].duration_seconds == 0.001
    empty = propose(s, monkeypatch, export(s))
    assert empty == {'source_export_id': empty['source_export_id'], 'cells': []}
    with pytest.raises(ValueError): prepare_reviewed(s, monkeypatch, empty)
    with pytest.raises(ValueError): prepare_reviewed(s, monkeypatch, empty, selected_cells=[])


def test_checked_selection_canonical_order_and_duplicate_names(frozen, monkeypatch):
    s, a, b, _, _, _ = frozen
    s.update_task(a, 'Same', '')
    s.update_task(b, 'Same', '')
    event = export(s, all_tasks=True)
    proposal = propose(s, monkeypatch, event)
    assert {r['task_name'] for r in proposal['cells']} == {'Same'}
    selected = [key(b, TUE), key(a)]
    prepared = prepare_reviewed(s, monkeypatch, proposal, selected_cells=list(reversed(sorted(selected))))
    assert [(r['task_id'], r['work_date']) for r in prepared['payload']['cells']] == sorted(selected)
    assert set(r['task_id'] for r in prepared['payload']['cells']) == {a, b}


def test_explicit_zero_replacement_requires_its_own_stale_acknowledgement(frozen, monkeypatch):
    s, a, b, _, _, event = frozen
    prior = register(s, cell(b, 200))  # exported zero now conflicts with a later positive confirmation
    proposal = propose(s, monkeypatch, event)
    assert row(proposal, b)['requires_stale_acknowledgement']
    default = prepare_reviewed(s, monkeypatch, proposal)
    assert key(b) not in [(r['task_id'], r['work_date']) for r in default['payload']['cells']]
    with pytest.raises(ValueError):
        prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(b)])
    zero = prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(b)], acknowledged_cells=[key(b)])
    assert zero['payload']['cells'] == [cell(b, 0, source=event['event_id'], prior=prior['event_id'], acknowledged=True)]


@pytest.mark.parametrize('placement', ['none', 'before', 'after'])
@pytest.mark.parametrize('same', [False, True])
@pytest.mark.parametrize('timestamp', ['2000-01-01T00:00:00Z', '2026-10-20T14:00:00Z'])
def test_stale_truth_table_uses_first_physical_occurrences(setup, monkeypatch, placement, same, timestamp):
    s, a, _, _, _, _ = setup
    dated(s, a, MON, 10800)
    prior = None
    if placement == 'before': prior = register(s, cell(a, 300 if same else 500))
    event = export(s, task_ids=(a,))
    if placement == 'after':
        prior = s.prepare_polr_confirmation_batch([cell(a, 300 if same else 500)])
        prior['timestamp_utc'] = timestamp
        s.register_prepared_polr_confirmation_batch(prior)
    if prior:
        s.storage.append_event(deepcopy(prior))  # duplicate is not a new effective occurrence
    s.storage.append_event(deepcopy(event))  # does not move the export's first occurrence
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    proposal = propose(s, monkeypatch, event)
    stale = placement == 'after' and not same
    assert row(proposal, a)['requires_stale_acknowledgement'] is stale
    prepared = prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(a)],
                                acknowledged_cells=[key(a)] if stale else [])
    s.register_prepared_polr_confirmation_batch(prepared)
    assert s.get_effective_polr_confirmations()[key(a)]['confirmed_hundredths'] == 300


@pytest.mark.parametrize('fault', ['missing', 'extra', 'duplicate', 'unselected', 'nonconflicting', 'boolean'])
def test_acknowledgement_must_exactly_cover_selected_conflicts(frozen, monkeypatch, fault):
    s, a, b, _, _, event = frozen
    register(s, cell(a, 500))
    proposal = propose(s, monkeypatch, event)
    selected, ack = [key(a)], [key(a)]
    if fault == 'missing': ack = []
    elif fault == 'extra': ack += [key(b, TUE)]
    elif fault == 'duplicate': ack *= 2
    elif fault == 'unselected': selected, ack = [key(b, TUE)], [key(a)]
    elif fault == 'nonconflicting': selected, ack = [key(b, TUE)], [key(b, TUE)]
    else: ack = True
    with pytest.raises(ValueError):
        prepare_reviewed(s, monkeypatch, proposal, selected_cells=selected, acknowledged_cells=ack)


@pytest.mark.parametrize('selection', ['', True, {}, {('x', 'y')}, [()], [['x', 'y']], [('x', 'y')]])
def test_invalid_selection_collections_rejected(frozen, monkeypatch, selection):
    s, a, _, _, _, event = frozen
    with pytest.raises(ValueError):
        prepare_reviewed(s, monkeypatch, propose(s, monkeypatch, event), selected_cells=selection)


def test_duplicate_unknown_and_empty_selection_keys_rejected(frozen, monkeypatch):
    s, a, _, _, _, event = frozen
    proposal = propose(s, monkeypatch, event)
    for selection in ([], [key(a), key(a)], [(str(uuid4()), str(MON))], [(a, '2026-1-1')]):
        with pytest.raises(ValueError): prepare_reviewed(s, monkeypatch, proposal, selected_cells=selection)


@pytest.mark.parametrize('amount', [300, 500])
def test_selected_prior_identity_change_rejects_even_equal_amount(frozen, monkeypatch, amount):
    s, a, _, _, _, event = frozen
    first = register(s, cell(a, 300))
    proposal = propose(s, monkeypatch, event)
    register(s, cell(a, amount, prior=first['event_id']))
    with pytest.raises(ValueError, match='changed'):
        prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(a)])


def test_unselected_changes_do_not_invalidate_selected_review(frozen, monkeypatch):
    s, a, b, _, _, event = frozen
    first = register(s, cell(a, 300), cell(b, 50, day=TUE))
    proposal = propose(s, monkeypatch, event)
    register(s, cell(b, 700, day=TUE, prior=first['event_id']))
    prepared = prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(a)])
    assert prepared['payload']['cells'] == [cell(a, 300, source=event['event_id'], prior=first['event_id'])]
    s.register_prepared_polr_confirmation_batch(prepared)
    assert s.get_effective_polr_confirmations()[key(b, TUE)]['confirmed_hundredths'] == 700


@pytest.mark.parametrize('fault', ['extra', 'row-extra', 'missing-row', 'extra-row', 'duplicate-row', 'reverse',
                                  'name', 'name-type', 'amount', 'bool-amount', 'float-amount', 'negative',
                                  'task-id', 'date', 'prior-pair', 'prior-amount', 'prior-id', 'stale', 'stale-type',
                                  'bool-prior', 'float-prior', 'negative-prior', 'bad-prior-id',
                                  'bad-source-id', 'cells-type', 'missing-field', 'bad-utf8'])
def test_tampered_proposals_rejected_before_low_level_preparation(frozen, monkeypatch, fault):
    s, a, _, _, _, event = frozen
    register(s, cell(a, 300))
    proposal = propose(s, monkeypatch, event)
    target = row(proposal, a)
    if fault == 'extra': proposal['extra'] = None
    elif fault == 'row-extra': target['extra'] = None
    elif fault == 'missing-row': proposal['cells'].pop()
    elif fault == 'extra-row':
        proposal['cells'].append(dict(target, task_id=str(uuid4())))
        proposal['cells'].sort(key=lambda r: (r['task_id'], r['work_date']))
    elif fault == 'duplicate-row': proposal['cells'].append(deepcopy(target))
    elif fault == 'reverse': proposal['cells'].reverse()
    elif fault == 'name': target['task_name'] = 'Tampered label'
    elif fault == 'name-type': target['task_name'] = 123
    elif fault == 'amount': target['proposed_hundredths'] += 1
    elif fault == 'bool-amount': target['proposed_hundredths'] = True
    elif fault == 'float-amount': target['proposed_hundredths'] = 300.0
    elif fault == 'negative': target['proposed_hundredths'] = -1
    elif fault == 'task-id': target['task_id'] = 'invalid'
    elif fault == 'date': target['work_date'] = '2026-02-30'
    elif fault == 'bool-prior': target['prior_confirmed_hundredths'] = True
    elif fault == 'float-prior': target['prior_confirmed_hundredths'] = 300.0
    elif fault == 'negative-prior': target['prior_confirmed_hundredths'] = -1
    elif fault == 'bad-prior-id': target['expected_prior_confirmation_id'] = 'invalid'
    elif fault == 'bad-source-id': proposal['source_export_id'] = 'invalid'
    elif fault == 'cells-type': proposal['cells'] = tuple(proposal['cells'])
    elif fault == 'missing-field': del target['task_name']
    elif fault == 'bad-utf8': target['task_name'] = '\ud800'
    elif fault == 'prior-pair': target['prior_confirmed_hundredths'] = None
    elif fault == 'prior-amount': target['prior_confirmed_hundredths'] += 1
    elif fault == 'prior-id': target['expected_prior_confirmation_id'] = str(uuid4())
    elif fault == 'stale': target['requires_stale_acknowledgement'] = True
    else: target['requires_stale_acknowledgement'] = 1
    monkeypatch.setattr(s, 'prepare_polr_confirmation_batch', lambda *a, **k: pytest.fail('prepared tampered input'))
    with pytest.raises(ValueError): prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(a)])


def test_fresh_evidence_overrides_forged_caches_without_installing(frozen, monkeypatch):
    s, a, _, _, _, event = frozen
    candidate = s.prepare_polr_confirmation_batch([cell(a, 500)])
    s.storage.append_event(candidate)
    s._timesheet_exports = {}
    s._polr_confirmations = {}
    proposal = propose(s, monkeypatch, event)
    assert row(proposal, a)['expected_prior_confirmation_id'] == candidate['event_id']
    assert row(proposal, a)['requires_stale_acknowledgement']
    prepared = prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(a)], acknowledged_cells=[key(a)])
    assert prepared['payload']['cells'][0]['expected_prior_confirmation_id'] == candidate['event_id']
    assert s._timesheet_exports == {} and s._polr_confirmations == {}


@pytest.mark.parametrize('fault', ['missing-active', 'partial', 'bad-confirmation', 'bad-export', 'denied'])
def test_bad_journal_fails_proposal_and_preparation_without_mutation(frozen, monkeypatch, fault):
    s, a, _, _, _, event = frozen
    proposal = propose(s, monkeypatch, event)
    if fault == 'missing-active': s.storage.active_path.unlink()
    elif fault == 'partial':
        with s.storage.active_path.open('ab') as handle: handle.write(b'{partial')
    elif fault == 'bad-confirmation':
        invalid = s.prepare_polr_confirmation_batch([cell(a)])
        invalid['payload']['cells'][0]['confirmed_hundredths'] = True
        s.storage.append_event(invalid)
    elif fault == 'bad-export':
        invalid = deepcopy(event)
        invalid['payload']['report_sha256'] = '0' * 64
        s.storage.append_event(invalid)
    else:
        def denied(*args, **kwargs): raise PermissionError('journal denied')
        monkeypatch.setattr(s.storage, 'iter_all_events', denied)
    with pytest.raises((ValueError, OSError)): propose(s, monkeypatch, event)
    with pytest.raises((ValueError, OSError)): prepare_reviewed(s, monkeypatch, proposal)


def test_invalid_unknown_and_prepared_only_export_identity_rejected(setup, monkeypatch):
    s, _, _, _, _, _ = setup
    unregistered = s.prepare_timesheet_export_snapshot(MON, TUE, cutoff_utc=CUTOFF)
    for identity in ('invalid', str(uuid4()), unregistered['event_id'], None):
        with pytest.raises(ValueError):
            readonly(s, monkeypatch, lambda: s.propose_export_polr_confirmation(identity), proposal=True)


def test_real_checked_workflow_detachment_and_exact_retry(frozen, monkeypatch):
    s, a, b, _, _, event = frozen
    prior = register(s, cell(a, 500), cell(b, 200, day=TUE))
    proposal = propose(s, monkeypatch, event)
    saved = deepcopy(proposal)
    identity = str(uuid4())
    prepared = prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(a), key(b)],
                                acknowledged_cells=[key(a)], batch_id=identity)
    assert prepared['event_id'] == identity
    expected_cells = [cell(a, 300, source=event['event_id'], prior=prior['event_id'], acknowledged=True),
                      cell(b, 0, source=event['event_id'])]
    assert prepared['payload']['cells'] == sorted(expected_cells, key=lambda r: (r['task_id'], r['work_date']))
    assert set(prepared['payload']) == {'cells'}
    assert s.get_effective_polr_confirmations()[key(a)]['confirmed_hundredths'] == 500
    assert s.register_prepared_polr_confirmation_batch(prepared) == identity
    assert s.get_effective_polr_confirmations()[key(b, TUE)]['confirmed_hundredths'] == 200
    assert s.get_effective_polr_confirmations()[key(b)]['confirmed_hundredths'] == 0
    later = register(s, cell(a, 700, prior=identity))
    before = capture(s)
    s.register_prepared_polr_confirmation_batch(prepared)
    assert capture(s) == before
    assert s.get_effective_polr_confirmations()[key(a)]['batch_event_id'] == later['event_id']
    assert len(occurrences(s)) == 3 and proposal == saved
    persisted = occurrences(s)
    prepared['payload']['cells'][0]['confirmed_hundredths'] = 999
    assert proposal == saved and occurrences(s) == persisted
    assert row(propose(s, monkeypatch, event), a)['proposed_hundredths'] == 300


def test_empty_selection_never_delegates_event_preparation(frozen, monkeypatch):
    s, a, _, _, _, event = frozen
    proposal = propose(s, monkeypatch, event)
    monkeypatch.setattr(s, 'prepare_polr_confirmation_batch', lambda *a, **k: pytest.fail('prepared empty selection'))
    with pytest.raises(ValueError, match='Select at least'):
        prepare_reviewed(s, monkeypatch, proposal, selected_cells=[])


def test_selected_change_after_preparation_is_rejected_by_existing_registration(frozen, monkeypatch):
    s, a, _, _, _, event = frozen
    proposal = propose(s, monkeypatch, event)
    prepared = prepare_reviewed(s, monkeypatch, proposal, selected_cells=[key(a)])
    register(s, cell(a, 300))
    before = capture(s)
    with pytest.raises(ValueError, match='prior identity'):
        s.register_prepared_polr_confirmation_batch(prepared)
    assert capture(s) == before
