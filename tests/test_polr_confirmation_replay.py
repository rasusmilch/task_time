"""Confirmation fixtures append isolated evidence; no production writer exists."""
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest

from task_timer import app as app_module
from task_timer.app import TaskTimerService
from task_timer.models import event_dict
from task_timer.polr_confirmations import (
    CONFIRMATION_EVENT_TYPE, collect_polr_confirmations, validate_polr_confirmation_batch,
)
from task_timer.storage import EventStorage
from test_export_snapshot_registration import prepare, files
from test_timesheet_renderer import setup, dated, MON, TUE, CUTOFF, SUN, SAT


def cell(task, amount=300, *, day=MON, source=None, prior=None, acknowledged=False):
    return {'task_id': task, 'work_date': day.isoformat(), 'confirmed_hundredths': amount,
            'source_export_id': source, 'expected_prior_confirmation_id': prior,
            'stale_export_acknowledged': acknowledged}


def batch(*cells, identity=None, timestamp='2026-10-25T12:00:00Z'):
    return event_dict(event_id=identity or str(uuid4()), timestamp_utc=timestamp,
                      local_timezone='America/Chicago', task_id='__app__',
                      event_type=CONFIRMATION_EVENT_TYPE, payload={'cells': list(cells)})


def journal(s, *extra):
    physical = sorted(s.storage.iter_all_events(strict=True), key=lambda e: e['_read_sequence'])
    return [{k: deepcopy(v) for k, v in event.items() if k != '_read_sequence'} for event in physical] + list(extra)


def projected(amount, event):
    return {'confirmed_hundredths': amount, 'batch_event_id': event['event_id']}


@pytest.fixture
def exported(setup):
    s, a, b, p, q = setup
    dated(s, a, MON, 60)
    dated(s, b, MON, 60)
    event = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(event)
    return s, a, b, p, q, event


def test_manual_zero_unknown_multiple_cells_and_input_purity(setup):
    s, a, b, _, _ = setup
    event = batch(cell(b, 0, day=TUE), cell(a, 300))  # array order is unrestricted
    events = journal(s, event)
    before = deepcopy(events)
    result = collect_polr_confirmations(events)
    assert result == {(a, MON.isoformat()): projected(300, event), (b, TUE.isoformat()): projected(0, event)}
    assert (b, MON.isoformat()) not in result  # Unknown is absence, never zero
    result[(a, MON.isoformat())]['confirmed_hundredths'] = 999
    assert collect_polr_confirmations(events)[a, MON.isoformat()] == projected(300, event)
    assert events == before


def test_export_link_freezes_amount_without_current_actual_or_file(exported, monkeypatch):
    s, a, _, _, _, export = exported
    dated(s, a, MON, 18000)
    event = batch(cell(a, 2, source=export['event_id']))
    def forbidden(*args, **kwargs):
        pytest.fail('Replay consulted current accounting, renderer, clock or file copy')
    monkeypatch.setattr(s, 'calculate_date_window', forbidden)
    monkeypatch.setattr('task_timer.export_snapshots.build_decimal_timesheet_text', forbidden)
    monkeypatch.setattr(app_module, 'utc_now', forbidden)
    assert collect_polr_confirmations(journal(s, event))[a, MON.isoformat()] == projected(2, event)


@pytest.mark.parametrize('field,value', [
    ('schema_version', True), ('schema_version', 2), ('event_id', 'invalid'),
    ('task_id', 'not-app'), ('event_type', 'not-confirmation'),
    ('timestamp_utc', '2026-10-25T12:00:00'), ('timestamp_utc', '2026-10-25T12:00:00+00:00'),
    ('timestamp_utc', '2026-10-25T12:00:00.123Z'), ('timestamp_utc', '2026-02-30T12:00:00Z'),
    ('local_timezone', ''), ('local_timezone', 'Unknown/Timezone'), ('local_timezone', False),
    ('payload', {}), ('payload', {'cells': []}), ('payload', {'cells': {}}),
    ('payload', {'cells': [], 'extra': True}),
])
def test_invalid_envelope_and_payload_shape(setup, field, value):
    _, a, _, _, _ = setup
    event = batch(cell(a))
    event[field] = value
    with pytest.raises(ValueError):
        validate_polr_confirmation_batch(event)


@pytest.mark.parametrize('location', ['envelope-extra', 'envelope-missing', 'cell-extra', 'cell-missing', 'not-cell'])
def test_exact_fields_are_mandatory(setup, location):
    _, a, _, _, _ = setup
    event = batch(cell(a))
    if location == 'envelope-extra':
        event['other'] = 1
    elif location == 'envelope-missing':
        del event['event_id']
    elif location == 'cell-extra':
        event['payload']['cells'][0]['actual'] = 300
    elif location == 'cell-missing':
        del event['payload']['cells'][0]['source_export_id']
    else:
        event['payload']['cells'] = [None]
    with pytest.raises(ValueError):
        validate_polr_confirmation_batch(event)


@pytest.mark.parametrize('field,value', [
    ('task_id', 'invalid'), ('work_date', '2026-10-32'), ('work_date', '20261012'),
    ('work_date', True), ('confirmed_hundredths', -1), ('confirmed_hundredths', True),
    ('confirmed_hundredths', 300.0), ('confirmed_hundredths', float('nan')),
    ('confirmed_hundredths', float('inf')), ('confirmed_hundredths', '300'),
    ('source_export_id', False), ('source_export_id', 'invalid'),
    ('expected_prior_confirmation_id', 'invalid'), ('stale_export_acknowledged', 1),
])
def test_invalid_cells_rejected(setup, field, value):
    s, a, _, _, _ = setup
    event = batch(cell(a))
    event['payload']['cells'][0][field] = value
    with pytest.raises(ValueError):
        collect_polr_confirmations(journal(s, event))


def test_duplicate_cells_and_unknown_or_future_task_creation_rejected(setup):
    s, a, _, _, _ = setup
    with pytest.raises(ValueError, match='Duplicate task/day'):
        collect_polr_confirmations(journal(s, batch(cell(a), cell(a, 0))))
    unknown = str(uuid4())
    creation = event_dict(event_id=str(uuid4()), timestamp_utc='2026-10-25T12:00:00Z',
                          local_timezone='UTC', task_id=unknown, event_type='task_created', payload={'name': 'Later'})
    for following in ([], [creation]):
        with pytest.raises(ValueError, match='preceding creation'):
            collect_polr_confirmations(journal(s, batch(cell(unknown)), *following))


@pytest.mark.parametrize('kind', ['unknown', 'future', 'missing-task-cell', 'missing-date-cell', 'wrong-value'])
def test_invalid_export_relationships(exported, kind):
    s, a, b, _, _, export = exported
    source, owner, day, amount, suffix = export['event_id'], a, MON, 2, []
    if kind == 'unknown':
        source = str(uuid4())
    elif kind in ('future', 'missing-task-cell'):
        candidate = prepare(s, task_ids=(a,))
        source = candidate['event_id']
        if kind == 'future':
            suffix = [candidate]
        else:
            s.register_prepared_timesheet_export(candidate)
            owner = b
    elif kind == 'missing-date-cell':
        day = SAT + timedelta(days=1)
    else:
        amount = 3
    with pytest.raises(ValueError):
        collect_polr_confirmations(journal(s, batch(cell(owner, amount, day=day, source=source)), *suffix))


def test_priors_are_per_cell_and_partial_batch_leaves_other_cells_unchanged(setup):
    s, a, b, _, _ = setup
    first = batch(cell(a, 300), cell(b, 500))
    second = batch(cell(a, 250, prior=first['event_id']))
    result = collect_polr_confirmations(journal(s, first, second))
    assert result == {(a, MON.isoformat()): projected(250, second), (b, MON.isoformat()): projected(500, first)}
    for invalid in (batch(cell(a, prior=str(uuid4()))), batch(cell(a, 500)),
                    batch(cell(b, 0, prior=second['event_id']))):
        with pytest.raises(ValueError, match='prior identity'):
            collect_polr_confirmations(journal(s, first, second, invalid))
    with pytest.raises(ValueError, match='prior identity'):
        collect_polr_confirmations(journal(s, batch(cell(a, prior=first['event_id']))))


@pytest.mark.parametrize('prior_after_export', [True, False])
@pytest.mark.parametrize('same_amount', [True, False])
@pytest.mark.parametrize('acknowledged', [True, False])
def test_stale_acknowledgement_exact_truth_table(exported, prior_after_export, same_amount, acknowledged):
    s, a, _, _, _, export = exported
    base = journal(s)
    base.remove(export)
    prior = batch(cell(a, 2 if same_amount else 300))
    proposal = batch(cell(a, 2, source=export['event_id'], prior=prior['event_id'], acknowledged=acknowledged))
    middle = [export, prior] if prior_after_export else [prior, export]
    events = base + middle + [proposal]
    conflict = prior_after_export and not same_amount
    if acknowledged == conflict:
        assert collect_polr_confirmations(events)[a, MON.isoformat()] == projected(2, proposal)
    else:
        with pytest.raises(ValueError, match='acknowledgement'):
            collect_polr_confirmations(events)


def test_acknowledgements_are_cell_specific_and_manual_never_has_stale_conflict(exported):
    s, a, b, _, _, export = exported
    first = batch(cell(a, 300), cell(b, 500))
    proposal = batch(cell(a, 2, source=export['event_id'], prior=first['event_id'], acknowledged=True),
                     cell(b, 2, source=export['event_id'], prior=first['event_id']))
    with pytest.raises(ValueError, match='acknowledgement'):
        collect_polr_confirmations(journal(s, first, proposal))
    proposal['payload']['cells'][1]['stale_export_acknowledged'] = True
    assert len(collect_polr_confirmations(journal(s, first, proposal))) == 2
    manual = batch(cell(a, 100, prior=first['event_id'], acknowledged=True))
    with pytest.raises(ValueError, match='acknowledgement'):
        collect_polr_confirmations(journal(s, first, manual))
    manual['payload']['cells'][0]['stale_export_acknowledged'] = False
    assert collect_polr_confirmations(journal(s, first, manual))[a, MON.isoformat()] == projected(100, manual)


@pytest.mark.parametrize('timestamp', ['2026-10-25T12:00:00Z', '2020-01-01T00:00:00Z'])
def test_physical_order_not_audit_time_or_input_list_order(setup, timestamp):
    s, a, _, _, _ = setup
    first = batch(cell(a))
    second = batch(cell(a, 500, prior=first['event_id']), timestamp=timestamp)
    events = [{**event, '_read_sequence': i} for i, event in enumerate(journal(s, first, second))]
    assert collect_polr_confirmations(list(reversed(events)))[a, MON.isoformat()] == projected(500, second)
    s.storage.append_event(first)
    s.storage.append_event(second)
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert restarted.get_effective_polr_confirmations()[a, MON.isoformat()] == projected(500, second)


def test_exact_duplicate_after_intervening_batch_never_rolls_back(setup):
    s, a, _, _, _ = setup
    first = batch(cell(a))
    second = batch(cell(a, 500, prior=first['event_id']))
    assert collect_polr_confirmations(journal(s, first, second, deepcopy(first)))[a, MON.isoformat()] == projected(500, second)
    for changed in (batch(cell(a, 301), identity=first['event_id']),
                    batch(cell(a), identity=first['event_id'], timestamp='2026-10-26T12:00:00Z')):
        with pytest.raises(ValueError, match='duplicate confirmation'):
            collect_polr_confirmations(journal(s, first, changed))
    floated = deepcopy(first)
    floated['payload']['cells'][0]['confirmed_hundredths'] = 300.0
    with pytest.raises(ValueError):
        collect_polr_confirmations(journal(s, first, floated))


@pytest.mark.parametrize('other_first', [True, False])
def test_confirmation_identity_cannot_collide_with_other_event_type(setup, other_first):
    s, a, _, _, _ = setup
    event = batch(cell(a))
    other = event_dict(event_id=event['event_id'], timestamp_utc=event['timestamp_utc'],
                      task_id='__app__', local_timezone='UTC', event_type='legacy_marker', payload={})
    with pytest.raises(ValueError, match='collides'):
        collect_polr_confirmations(journal(s, *([other, event] if other_first else [event, other])))


def test_duplicate_export_does_not_reset_source_order(exported):
    s, a, _, _, _, export = exported
    first = batch(cell(a, 300))
    proposal = batch(cell(a, 2, source=export['event_id'], prior=first['event_id'], acknowledged=True))
    assert collect_polr_confirmations(journal(s, first, deepcopy(export), proposal))[a, MON.isoformat()] == projected(2, proposal)


def test_invalid_batch_does_not_install_partial_state_or_projection(exported):
    s, a, b, _, _, export = exported
    first = batch(cell(a))
    s._rebuild_state(journal(s, first))
    before = deepcopy(s.state), s.get_effective_polr_confirmations(), s.list_timesheet_export_snapshots(), files(s)
    invalid = batch(cell(b, 200), cell(a, 250))  # second cell has stale prior identity
    with pytest.raises(ValueError, match='prior identity'):
        s._rebuild_state(journal(s, first, invalid))
    assert (s.state, s.get_effective_polr_confirmations(), s.list_timesheet_export_snapshots(), files(s)) == before
    assert (b, MON.isoformat()) not in s.get_effective_polr_confirmations()


def test_generic_service_append_is_not_a_confirmation_writer(setup):
    s, a, _, _, _ = setup
    before = deepcopy(s.state), deepcopy(s.events), files(s)
    with pytest.raises(ValueError, match='generic append is prohibited'):
        s._append('__app__', CONFIRMATION_EVENT_TYPE, {'cells': [cell(a)]})
    assert (s.state, s.events, files(s)) == before


@pytest.mark.parametrize('fault', ['duplicate-cell', 'wrong-prior', 'bad-amount', 'extra-envelope',
                                 'duplicate-identity', 'other-type-collision'])
def test_malformed_persisted_confirmation_prevents_startup_and_export_operations(exported, fault, tmp_path):
    s, a, _, _, _, export = exported
    invalid = batch(cell(a))
    if fault == 'duplicate-cell':
        invalid['payload']['cells'].append(cell(a))
    elif fault == 'wrong-prior':
        invalid['payload']['cells'][0]['expected_prior_confirmation_id'] = str(uuid4())
    elif fault == 'bad-amount':
        invalid['payload']['cells'][0]['confirmed_hundredths'] = True
    elif fault == 'extra-envelope':
        invalid['extra'] = 1
    elif fault == 'duplicate-identity':
        s.storage.append_event(deepcopy(invalid))
        invalid['payload']['cells'][0]['confirmed_hundredths'] += 1
    else:
        other = deepcopy(invalid)
        other['event_type'], other['payload'] = 'legacy_marker', {}
        s.storage.append_event(other)
    candidate = prepare(s, all_tasks=True)
    s.storage.append_event(invalid)
    before = files(s)
    target = tmp_path / 'unwritten.txt'
    for operation in (lambda: TaskTimerService(EventStorage(s.storage.data_dir)),
                      lambda: s.register_prepared_timesheet_export(candidate),
                      lambda: s.materialize_timesheet_export(export['event_id'], target),
                      lambda: s.evaluate_timesheet_export_file_status(export['event_id'])):
        with pytest.raises(ValueError):
            operation()
        assert files(s) == before and not target.exists()


def test_restart_rotation_rebuild_backup_and_later_task_changes_preserve_evidence(exported):
    s, a, b, _, q, export = exported
    first = batch(cell(a, 2, source=export['event_id']), cell(b, 0, day=TUE))
    s.storage.append_event(first)
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    second = batch(cell(a, 500, prior=first['event_id']))
    s.storage.append_event(second)
    s.storage.append_event(deepcopy(first))
    s = TaskTimerService(EventStorage(s.storage.data_dir))
    expected = {(a, MON.isoformat()): projected(500, second), (b, TUE.isoformat()): projected(0, first)}
    assert s.get_effective_polr_confirmations() == expected
    s.update_task(a, 'Renamed', '')
    s.assign_task_to_project(a, q)
    s.delete_task(a)
    s.rebuild_snapshot_from_journal()
    assert s.get_effective_polr_confirmations() == expected
    assert s.get_timesheet_export_snapshot(export['event_id']) == export
    assert not any('confirmation' in name for name in s.snapshot_dict())
    detached = s.get_effective_polr_confirmations()
    detached[a, MON.isoformat()]['confirmed_hundredths'] = 999
    assert s.get_effective_polr_confirmations() == expected
    backup = s.create_backup_now()
    third = batch(cell(a, 0, prior=second['event_id']))
    s.storage.append_event(third)
    s.restore_from_backup(backup)
    assert s.get_effective_polr_confirmations() == expected
    assert TaskTimerService(EventStorage(s.storage.data_dir)).get_effective_polr_confirmations() == expected
    persisted = journal(s)
    assert [event for event in persisted if event['event_type'] == CONFIRMATION_EVENT_TYPE] == [first, second, first]


def test_confirmation_rebuild_changes_no_actual_timer_export_files_or_legacy_state(exported, tmp_path):
    s, a, _, _, _, export = exported
    s.start_task(a)
    target = tmp_path / 'frozen.txt'
    s.materialize_timesheet_export(export['event_id'], target)
    before = (deepcopy(s.state), s.calculate_date_window(SUN, SAT, cutoff_utc=CUTOFF, all_tasks=True),
              s.list_timesheet_export_snapshots(), s.list_time_submissions(), files(s), target.read_bytes())
    event = batch(cell(a, 999999))  # absolute external evidence cannot create Actual
    s._rebuild_state(journal(s, event))
    after = (s.state, s.calculate_date_window(SUN, SAT, cutoff_utc=CUTOFF, all_tasks=True),
             s.list_timesheet_export_snapshots(), s.list_time_submissions(), files(s), target.read_bytes())
    assert after == before and s.state.tasks[a].is_running
    assert s.get_effective_polr_confirmations()[a, MON.isoformat()] == projected(999999, event)
