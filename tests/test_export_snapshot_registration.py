"""Immutable journal evidence in isolated datasets; no report materialization."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from uuid import uuid4

import pytest

from task_timer.app import TaskTimerService
from task_timer.export_snapshots import EXPORT_EVENT_TYPE
from task_timer.exporter import build_decimal_timesheet_text
from task_timer.storage import EventStorage
from test_storage import _tree
from test_timesheet_renderer import setup, dated, SUN, MON, TUE, SAT, CUTOFF, table_rows


def files(s):
    root = s.storage.data_dir
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def prepare(s, **kwargs):
    return s.prepare_timesheet_export_snapshot(SUN, SAT, cutoff_utc=CUTOFF, **kwargs)


def capture(s):
    return deepcopy(s.state), deepcopy(s.events), files(s), deepcopy(s.list_time_submissions())


def payload(event):
    return event['payload']


def cell(event, task, day=MON):
    return next(c for row in payload(event)['tasks'] if row['task_id'] == task
                for c in row['daily'] if c['work_date'] == day.isoformat())


def committed(s):
    return [event for event in s.storage.iter_all_events(strict=True) if event['event_type'] == EXPORT_EVENT_TYPE]


def test_preparation_freezes_one_calculation_without_writes(setup, monkeypatch, tmp_path):
    s, a, b, p, q = setup
    c = s.create_task('第三 tâche e\u0301\u202e', '', project_id=p)
    for task in (a, b, c):
        dated(s, task, MON, 60)
    calls = []
    original = s.calculate_date_window
    def calculate(*args, **kwargs):
        report = original(*args, **kwargs)
        calls.append(deepcopy(report))
        return report
    monkeypatch.setattr(s, 'calculate_date_window', calculate)
    before = capture(s)
    destination = tmp_path / 'nonexistent-parent' / 'not-written.txt'
    identity = str(uuid4())
    event = prepare(s, all_tasks=True, preferred_destination=str(destination), export_id=identity)
    assert len(calls) == 1
    assert event['event_id'] == identity and event['task_id'] == '__app__'
    assert set(event) == {'schema_version', 'event_id', 'timestamp_utc', 'local_timezone', 'task_id', 'event_type', 'payload'}
    assert event['event_type'] == EXPORT_EVENT_TYPE and event['schema_version'] == 1
    data = payload(event)
    assert data['cutoff_utc'] == '2026-10-25T12:00:00.123456Z'
    assert event['timestamp_utc'] == '2026-10-25T12:00:00Z'
    assert 'timestamp_utc' not in data and 'export_id' not in data
    assert data['week_start'] == 6 and data['report_timezone'] == 'America/Chicago'
    assert data['start_date'] == SUN.isoformat() and data['end_date'] == SAT.isoformat()
    assert data['scope'] == 'complete'
    assert data['preferred_destination'] == str(destination)
    assert not destination.parent.exists()
    assert data['report_text'] == build_decimal_timesheet_text(calls[0])
    assert data['report_text'].endswith('\n') and '\r' not in data['report_text']
    assert sha256(data['report_text'].encode('utf-8')).hexdigest() == data['report_sha256']
    assert table_rows(data['report_text'], 'Application total')[0][-1] == '0.06'
    for task in (a, b, c):
        assert cell(event, task) == {'work_date': MON.isoformat(), 'actual_seconds': 60, 'decimal_hundredths': 2}
        assert cell(event, task, TUE)['actual_seconds'] == cell(event, task, TUE)['decimal_hundredths'] == 0
    assert calls[0]['application']['window_seconds'] == 180
    assert len(next(row for row in data['tasks'] if row['task_id'] == a)['daily']) == 7
    assert next(row for row in data['projects'] if row['project_id'] == q)['task_ids'] == []
    assert json.loads(json.dumps(event, allow_nan=False, ensure_ascii=False)) == event
    assert capture(s) == before and s.list_timesheet_export_snapshots() == []
    s.register_prepared_timesheet_export(event)
    assert not destination.parent.exists()


@pytest.mark.parametrize('kind', ['task', 'project', 'combined', 'empty', 'empty-project', 'unassigned', 'deleted'])
def test_original_selection_frozen_and_deduplicated(setup, kind):
    s, a, b, p, q = setup
    u = s.create_task('Unassigned', '')
    dated(s, a, MON, 60)
    dated(s, b, MON, 900)
    dated(s, u, MON, 1800)
    if kind == 'deleted':
        s.delete_task(b)
    options = {
        'task': {'task_ids': (a,)}, 'project': {'project_ids': (p,)},
        'combined': {'task_ids': (a, a), 'project_ids': (p, p)}, 'empty': {},
        'empty-project': {'project_ids': (q,)}, 'unassigned': {'include_unassigned': True},
        'deleted': {'task_ids': (b,), 'include_deleted': True},
    }[kind]
    event = prepare(s, **options)
    data = payload(event)
    assert data['scope'] == 'selected'
    assert data['selection'] == {'all_tasks': False, 'task_ids': sorted(set(options.get('task_ids', ()))),
        'project_ids': sorted(set(options.get('project_ids', ()))), 'include_unassigned': kind == 'unassigned',
        'include_deleted': kind == 'deleted'}
    expected = {'task': {a}, 'project': {a, b}, 'combined': {a, b},
                'empty': set(), 'empty-project': set(), 'unassigned': {u}, 'deleted': {b}}[kind]
    assert {row['task_id'] for row in data['tasks']} == expected
    if kind == 'task':
        assert data['projects'][0]['scope'] == 'selected_tasks'
    if kind == 'empty-project':
        assert data['projects'] == [{'project_id': q, 'name': 'Project Q', 'scope': 'full_project', 'task_ids': []}]
    if kind == 'unassigned':
        assert data['tasks'][0]['project_id'] is None and data['projects'] == []
    if kind == 'deleted':
        assert data['tasks'][0]['is_deleted'] is True
    s.register_prepared_timesheet_export(event)
    assert s.get_timesheet_export_snapshot(event['event_id']) == event


def test_empty_complete_dataset(tmp_path):
    s = TaskTimerService(EventStorage(tmp_path / 'empty'))
    event = prepare(s, all_tasks=True)
    assert payload(event)['scope'] == 'complete' and payload(event)['tasks'] == payload(event)['projects'] == []
    s.register_prepared_timesheet_export(event)
    assert s.list_timesheet_export_snapshots() == [event]


def test_registration_idempotency_detached_reads_and_no_work_side_effects(setup, monkeypatch):
    s, a, b, p, _ = setup
    s.update_task(a, 'Same name', '')
    s.update_task(b, 'Same name', '')
    for task in (a, b):
        dated(s, task, MON, 60)
    s.start_task(a)
    event = prepare(s, all_tasks=True)
    before_state, before_events, before_files, submissions = capture(s)
    monkeypatch.setattr(s.storage, 'save_snapshot', lambda *_: pytest.fail('registration must not save derived snapshot'))
    key = s.register_prepared_timesheet_export(event)
    assert key == event['event_id']
    assert s.state == before_state and s.state.running_task_id == a
    assert s.list_time_submissions() == submissions
    assert all(item['event_type'] not in ('polr_confirmation_batch_recorded', 'time_submission_created',
                                         'export_checkpoint', 'reset') for item in s.events[len(before_events):])
    assert len(s.events) == len(before_events) + 1 and len(committed(s)) == 1
    assert set(files(s)) == set(before_files)
    assert all(files(s)[name] == content for name, content in before_files.items() if name != 'active_events.jsonl')
    assert all(row['name'] == 'Same name' for row in payload(event)['tasks'])
    assert a in payload(event)['report_text'] and b in payload(event)['report_text']
    assert s.register_prepared_timesheet_export(deepcopy(event)) == key
    assert len(committed(s)) == 1
    read = s.get_timesheet_export_snapshot(key)
    read['payload']['tasks'][0]['name'] = 'Caller change'
    listed = s.list_timesheet_export_snapshots()
    listed[0]['payload']['tasks'].clear()
    event['payload']['projects'].clear()
    assert len(s.get_timesheet_export_snapshot(key)['payload']['projects']) == 2
    assert s.get_timesheet_export_snapshot(key)['payload']['tasks'][0]['name'] == 'Same name'
    with pytest.raises(ValueError, match='Unknown'):
        s.get_timesheet_export_snapshot(str(uuid4()))
    with pytest.raises(ValueError, match='UUID'):
        s.get_timesheet_export_snapshot('AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA')
    with pytest.raises(ValueError, match='Unknown'):
        s.get_timesheet_export_snapshot(a)


def test_frozen_evidence_survives_changes_and_replay_without_renderer(setup, monkeypatch):
    s, a, _, p, q = setup
    dated(s, a, MON, 7200)
    entry = next(iter(s.state.tasks[a].dated_durations))
    first = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(first)
    s._append(a, 'dated_duration_corrected', {'entry_id': entry, 'work_date_local': TUE.isoformat(),
                                             'duration_seconds': 10800, 'reason': 'Correct date and amount'})
    s.rename_project(p, 'Renamed P')
    s.update_task(a, 'New task name', '')
    s.assign_task_to_project(a, q)
    s.delete_task(a)
    second = prepare(s, all_tasks=True, include_deleted=True)
    s.register_prepared_timesheet_export(second)
    assert second['event_id'] != first['event_id']
    assert cell(first, a)['actual_seconds'] == 7200 and cell(second, a)['actual_seconds'] == 0
    assert cell(second, a, TUE)['actual_seconds'] == 10800
    monkeypatch.setattr('task_timer.export_snapshots.build_decimal_timesheet_text', lambda *_: pytest.fail('never rerender committed evidence'))
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert restarted.list_timesheet_export_snapshots() == [first, second]
    assert restarted.get_timesheet_export_snapshot(first['event_id']) == first
    assert restarted.register_prepared_timesheet_export(first) == first['event_id']
    assert len(committed(restarted)) == 2


@pytest.mark.parametrize('component', ['active_events.jsonl', 'log_manifest.json'])
@pytest.mark.parametrize('rotated', [False, True])
def test_missing_journal_component_rejects_real_restart_with_frozen_evidence(setup, component, rotated):
    s, a, _, _, _ = setup
    dated(s, a, MON, 12600)
    event = prepare(s, task_ids=(a,))
    s.register_prepared_timesheet_export(event)
    assert s.get_timesheet_export_snapshot(event['event_id']) == event
    assert s.state.tasks[a].dated_durations
    if rotated:
        s.storage.max_active_events = 1
        s.storage.rotate_if_needed()
        assert s.storage.load_manifest()['archives']
    s.create_backup_now()
    root = s.storage.data_dir
    (root / component).unlink()
    before = _tree(root)
    with pytest.raises(ValueError, match='initialization refused to protect existing history') as error:
        TaskTimerService(EventStorage(root))
    assert component in str(error.value)
    assert not (root / component).exists()
    assert _tree(root) == before


def test_registration_uses_prepared_membership_and_labels_not_current_state(setup):
    s, a, _, p, q = setup
    dated(s, a, MON, 60)
    event = prepare(s, task_ids=(a,))
    s.assign_task_to_project(a, q)
    s.rename_project(p, 'Changed P')
    s.update_task(a, 'Renamed later', '')
    s.delete_task(a)
    assert s.register_prepared_timesheet_export(event) == event['event_id']
    frozen = s.get_timesheet_export_snapshot(event['event_id'])
    assert payload(frozen)['tasks'][0]['project_id'] == p
    assert payload(frozen)['tasks'][0]['name'] == 'Task A'
    assert payload(frozen)['tasks'][0]['is_deleted'] is False
    assert payload(frozen)['projects'][0]['name'] == 'Project P'


def test_strict_replay_accepts_crlf_jsonl_without_altering_frozen_utf8_text(setup):
    s, a, _, _, _ = setup
    event = prepare(s, task_ids=(a,))
    s.register_prepared_timesheet_export(event)
    s.storage.active_path.write_bytes(s.storage.active_path.read_bytes().replace(b'\n', b'\r\n'))
    before = s.storage.active_path.read_bytes()
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert restarted.get_timesheet_export_snapshot(event['event_id']) == event
    assert s.storage.active_path.read_bytes() == before


def test_journal_order_not_preparation_timestamp_and_exact_duplicates_once(setup):
    s, a, _, _, _ = setup
    first, second = prepare(s, task_ids=(a,)), prepare(s, task_ids=(a,))
    first['timestamp_utc'] = '2026-10-26T12:00:00Z'
    s.register_prepared_timesheet_export(first)
    s.register_prepared_timesheet_export(second)
    s.storage.append_event(deepcopy(first))  # identical duplicate evidence has one effective identity
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert restarted.list_timesheet_export_snapshots() == [first, second]
    restarted._rebuild_state(list(reversed(restarted.events)))
    assert restarted.list_timesheet_export_snapshots() == [first, second]
    assert restarted.register_prepared_timesheet_export(first) == first['event_id']
    assert len(committed(restarted)) == 3  # preexisting duplicate never rewritten/repaired


def test_rotation_rebuild_and_backup_restore_preserve_frozen_order(setup):
    s, a, _, _, _ = setup
    dated(s, a, MON, 12600)
    s.storage.max_active_events = 1
    first, second = prepare(s, all_tasks=True), prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(first)
    s.register_prepared_timesheet_export(second)
    assert len(s.storage.load_manifest()['archives']) == 2
    archives = {p.name: p.read_bytes() for p in s.storage.archives_dir.iterdir()}
    backup = s.create_backup_now()
    third = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(third)
    s.restore_from_backup(backup)
    assert s.list_timesheet_export_snapshots() == [first, second]
    assert {p.name: p.read_bytes() for p in s.storage.archives_dir.iterdir()} == archives
    s.storage.snapshot_path.write_text('{}', encoding='utf-8')
    s.rebuild_snapshot_from_journal()
    assert s.list_timesheet_export_snapshots() == [first, second]
    assert not any('export' in name for name in s.snapshot_dict())
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert restarted.list_timesheet_export_snapshots() == [first, second]


def test_failed_derived_snapshot_write_cannot_undo_committed_export(setup, monkeypatch):
    s, a, _, _, _ = setup
    event = prepare(s, task_ids=(a,))
    s.register_prepared_timesheet_export(event)
    before = files(s)
    with monkeypatch.context() as patch:
        patch.setattr(EventStorage, 'save_snapshot', lambda *_: (_ for _ in ()).throw(OSError('derived snapshot failed')))
        with pytest.raises(OSError, match='derived snapshot failed'):
            TaskTimerService(EventStorage(s.storage.data_dir))
    assert files(s) == before
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert restarted.get_timesheet_export_snapshot(event['event_id']) == event


@pytest.mark.parametrize('change', ['preferred', 'numeric-type', 'other-type'])
def test_existing_identity_cannot_be_replaced(setup, change):
    s, a, _, _, _ = setup
    event = prepare(s, task_ids=(a,))
    if change == 'other-type':
        event['event_id'] = s.events[0]['event_id']
    else:
        s.register_prepared_timesheet_export(event)
    altered = deepcopy(event)
    if change == 'preferred':
        payload(altered)['preferred_destination'] = 'different.txt'
    elif change == 'numeric-type':
        cell(altered, a)['actual_seconds'] = 0.0  # equal in Python; distinct JSON content
    before = capture(s)
    with pytest.raises(ValueError, match='identity'):
        s.register_prepared_timesheet_export(altered)
    assert capture(s) == before


def mutations(event, a, p):
    """Each candidate breaks a specific schema/integrity invariant."""
    def changed(path, value):
        result = deepcopy(event)
        owner = result
        for key in path[:-1]:
            owner = owner[key]
        owner[path[-1]] = value
        return result
    fields = [
        (('event_id',), 'bad'), (('schema_version',), True), (('schema_version',), 2),
        (('task_id',), a), (('event_type',), 'other'), (('timestamp_utc',), 'bad'),
        (('timestamp_utc',), '2026-10-25T12:00:00'), (('local_timezone',), 'UTC'),
        (('payload', 'extra'), 1), (('payload', 'start_date'), '2026-W42-1'),
        (('payload', 'start_date'), '2026-10-32'), (('payload', 'end_date'), '2026-10-01'),
        (('payload', 'cutoff_utc'), '2026-10-25T12:00:00+00:00'),
        (('payload', 'report_timezone'), ''), (('payload', 'week_start'), True),
        (('payload', 'week_start'), 0), (('payload', 'scope'), 'complete'),
        (('payload', 'selection', 'include_deleted'), 1), (('payload', 'selection', 'all_tasks'), 'no'),
        (('payload', 'selection', 'task_ids'), [str(uuid4())]),
        (('payload', 'selection', 'project_ids'), [str(uuid4())]),
        (('payload', 'selection', 'task_ids'), [a, a]),
        (('payload', 'tasks', 0, 'task_id'), str(uuid4())),
        (('payload', 'tasks', 0, 'task_id'), p),
        (('payload', 'tasks', 0, 'project_id'), str(uuid4())),
        (('payload', 'tasks', 0, 'is_deleted'), True),
        (('payload', 'tasks', 0, 'name'), ''),
        (('payload', 'tasks', 0, 'extra'), 1),
        (('payload', 'tasks', 0, 'daily', 0, 'work_date'), '2026-10-10'),
        (('payload', 'tasks', 0, 'daily', 0, 'work_date'), '2026-02-30'),
        (('payload', 'tasks', 0, 'daily', 0, 'work_date'), MON.isoformat()),
        (('payload', 'tasks', 0, 'daily', 0, 'actual_seconds'), -1),
        (('payload', 'tasks', 0, 'daily', 0, 'actual_seconds'), float('nan')),
        (('payload', 'tasks', 0, 'daily', 0, 'actual_seconds'), float('inf')),
        (('payload', 'tasks', 0, 'daily', 0, 'actual_seconds'), True),
        (('payload', 'tasks', 0, 'daily', 0, 'actual_seconds'), '60'),
        (('payload', 'tasks', 0, 'daily', 0, 'decimal_hundredths'), -1),
        (('payload', 'tasks', 0, 'daily', 0, 'decimal_hundredths'), 0.0),
        (('payload', 'tasks', 0, 'daily', 0, 'decimal_hundredths'), True),
        (('payload', 'tasks', 0, 'daily', 0, 'decimal_hundredths'), 1),
        (('payload', 'projects', 0, 'task_ids'), []),
        (('payload', 'projects', 0, 'scope'), 'invalid'),
        (('payload', 'report_sha256'), '0' * 64), (('payload', 'report_sha256'), 'A' * 64),
        (('payload', 'report_text'), 'Changed\n'), (('payload', 'report_text'), '\ud800\n'),
        (('payload', 'preferred_destination'), ''), (('payload', 'preferred_destination'), 'null\x00path'),
        (('payload', 'preferred_destination'), 5),
    ]
    result = [changed(path, value) for path, value in fields]
    for name in event:
        candidate = deepcopy(event)
        del candidate[name]
        result.append(candidate)
    for field in ('tasks', 'projects'):
        candidate = deepcopy(event)
        payload(candidate)[field].append(deepcopy(payload(candidate)[field][0]))
        result.append(candidate)
    candidate = deepcopy(event)
    payload(candidate)['tasks'][0]['daily'].pop()
    result.append(candidate)
    candidate = changed(('payload', 'report_text'), 'Different but digest-matching report\n')
    payload(candidate)['report_sha256'] = sha256(payload(candidate)['report_text'].encode()).hexdigest()
    result.append(candidate)
    return result


def test_malformed_candidates_never_append_or_mutate_state(setup):
    s, a, _, p, _ = setup
    event = prepare(s, task_ids=(a,))
    for candidate in mutations(event, a, p):
        before = capture(s)
        with pytest.raises(ValueError):
            s.register_prepared_timesheet_export(candidate)
        assert capture(s) == before
        assert s.list_timesheet_export_snapshots() == []


@pytest.mark.parametrize('corruption', ['digest', 'conflicting-id', 'other-type-collision', 'missing-reference', 'extra-envelope'])
def test_corrupt_archived_export_fails_closed_without_rewrites(setup, corruption):
    s, a, _, _, _ = setup
    event = prepare(s, task_ids=(a,))
    s.register_prepared_timesheet_export(event)
    bad = deepcopy(event)
    if corruption == 'digest':
        payload(bad)['report_sha256'] = '0' * 64
        bad['event_id'] = str(uuid4())
    elif corruption == 'conflicting-id':
        payload(bad)['preferred_destination'] = 'conflict.txt'
    elif corruption == 'other-type-collision':
        bad['event_id'] = s.events[0]['event_id']
    elif corruption == 'missing-reference':
        bad['event_id'] = str(uuid4())
        payload(bad)['tasks'][0]['task_id'] = str(uuid4())
    else:
        bad['event_id'] = str(uuid4())
        bad['extra'] = True
    s.storage.max_active_events = 1
    s.storage.append_event(bad)
    before = files(s)
    with pytest.raises(ValueError):
        TaskTimerService(EventStorage(s.storage.data_dir))
    assert files(s) == before
    with pytest.raises(ValueError):
        s.register_prepared_timesheet_export(event)
    assert files(s) == before


@pytest.mark.parametrize('failure', ['before', 'partial', 'complete-then-error', 'silent-no-append', 'fsync'])
def test_append_outcome_inspection_and_same_operation_retry(setup, monkeypatch, failure):
    s, a, _, _, _ = setup
    event = prepare(s, task_ids=(a,))
    prepared_copy = deepcopy(event)
    before = capture(s)
    original = s.storage.append_event
    error = OSError('injected append failure')
    def append(candidate):
        if failure == 'partial':
            with s.storage.active_path.open('a', encoding='utf-8') as stream:
                stream.write('{"event_id":')
            raise error
        if failure == 'before':
            raise error
        if failure == 'silent-no-append':
            return
        original(candidate)
        raise error
    with monkeypatch.context() as patch:
        if failure == 'fsync':
            patch.setattr('task_timer.storage.os.fsync', lambda *_: (_ for _ in ()).throw(error))
        else:
            patch.setattr(s.storage, 'append_event', append)
        if failure in ('complete-then-error', 'fsync'):
            assert s.register_prepared_timesheet_export(event) == event['event_id']
        else:
            with pytest.raises((OSError, ValueError)) as raised:
                s.register_prepared_timesheet_export(event)
            if failure in ('partial', 'before'):
                assert raised.value is error
    assert s.state == before[0]
    assert event == prepared_copy
    if failure == 'partial':
        corrupt = files(s)
        with pytest.raises(ValueError, match='incomplete'):
            s.register_prepared_timesheet_export(event)
        assert files(s) == corrupt and s.list_timesheet_export_snapshots() == []
        assert 'uncertain' in error.__notes__[0]
    else:
        assert s.register_prepared_timesheet_export(event) == event['event_id']
        assert len(committed(s)) == 1
        assert s.list_timesheet_export_snapshots() == [event]


def test_failure_after_append_before_memory_update_is_recoverable(setup, monkeypatch):
    s, a, _, _, _ = setup
    event = prepare(s, task_ids=(a,))
    with monkeypatch.context() as patch:
        patch.setattr(s, '_install_export_journal', lambda *_: (_ for _ in ()).throw(RuntimeError('memory update failed')))
        with pytest.raises(RuntimeError, match='memory update'):
            s.register_prepared_timesheet_export(event)
    assert len(committed(s)) == 1 and s.list_timesheet_export_snapshots() == []
    assert s.register_prepared_timesheet_export(event) == event['event_id']
    assert len(committed(s)) == 1


def test_rotation_manifest_failure_leaves_uncertain_evidence_untouched(setup, monkeypatch):
    s, a, _, _, _ = setup
    event = prepare(s, task_ids=(a,))
    s.storage.max_active_events = 1
    error = OSError('manifest write failed after archive rename')
    with monkeypatch.context() as patch:
        patch.setattr(s.storage, 'save_manifest', lambda *_: (_ for _ in ()).throw(error))
        with pytest.raises(OSError) as raised:
            s.register_prepared_timesheet_export(event)
    assert raised.value is error and 'uncertain' in error.__notes__[0]
    assert s.list_timesheet_export_snapshots() == []
    before = files(s)
    with pytest.raises(ValueError, match='unindexed'):
        s.register_prepared_timesheet_export(event)
    assert files(s) == before


def test_postappend_inspection_failure_never_returns_false_success(setup, monkeypatch):
    s, a, _, _, _ = setup
    event = prepare(s, task_ids=(a,))
    read = s.storage.iter_all_events
    calls = []
    def fail_second_read(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise OSError('journal read unavailable')
        return read(**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(s.storage, 'iter_all_events', fail_second_read)
        with pytest.raises(OSError, match='unavailable'):
            s.register_prepared_timesheet_export(event)
    assert s.list_timesheet_export_snapshots() == [] and len(committed(s)) == 1
    assert s.register_prepared_timesheet_export(event) == event['event_id']
    assert len(committed(s)) == 1


def test_new_candidate_text_must_match_structured_labels_and_cells(setup):
    s, a, _, _, _ = setup
    for path, replacement in ((('name',), 'Different name'), (('daily', 1, 'actual_seconds'), 18)):
        candidate = prepare(s, task_ids=(a,))
        row = payload(candidate)['tasks'][0]
        owner = row
        for key in path[:-1]:
            owner = owner[key]
        owner[path[-1]] = replacement
        if len(path) > 1:
            row['daily'][1]['decimal_hundredths'] = 1
        before = capture(s)
        with pytest.raises(ValueError, match='do not agree'):
            s.register_prepared_timesheet_export(candidate)
        assert capture(s) == before


@pytest.mark.parametrize('corruption', ['partial-json', 'complete-without-newline', 'duplicate-json-key',
    'missing-archive', 'unindexed-archive', 'malformed-manifest', 'duplicate-manifest-key',
    'invalid-next-sequence', 'archive-count', 'missing-active', 'incomplete-crlf'])
def test_unhealthy_journal_blocks_retry_without_repair(setup, corruption):
    s, a, _, _, _ = setup
    event = prepare(s, task_ids=(a,))
    if corruption in ('missing-archive', 'unindexed-archive', 'archive-count'):
        s.storage.max_active_events = 1
        s.storage.rotate_if_needed()
        archive = next(s.storage.archives_dir.glob('*.jsonl'))
        if corruption == 'missing-archive':
            archive.unlink()
        elif corruption == 'unindexed-archive':
            archive.with_name('unindexed.jsonl').write_bytes(archive.read_bytes())
        else:
            manifest = s.storage.load_manifest()
            manifest['archives'][0]['event_count'] += 1
            s.storage.save_manifest(manifest)
    elif corruption in ('malformed-manifest', 'duplicate-manifest-key', 'invalid-next-sequence'):
        s.storage.manifest_path.write_text({'malformed-manifest': '{',
            'duplicate-manifest-key': '{"archives": [], "archives": [], "next_sequence": 1}',
            'invalid-next-sequence': '{"archives": [], "next_sequence": "invalid"}'}[corruption], encoding='utf-8')
    elif corruption == 'missing-active':
        s.storage.active_path.unlink()
    else:
        with s.storage.active_path.open('a', encoding='utf-8') as stream:
            stream.write({'partial-json': '{', 'complete-without-newline': json.dumps(event),
                          'incomplete-crlf': json.dumps(event) + '\r',
                          'duplicate-json-key': '{"event_id":"one", "event_id":"two"}\n'}[corruption])
    before = files(s)
    with pytest.raises(ValueError):
        s.register_prepared_timesheet_export(event)
    assert files(s) == before and s.list_timesheet_export_snapshots() == []


@pytest.mark.parametrize('kwargs', [
    {'export_id': 'bad'}, {'export_id': True}, {'preferred_destination': ''},
    {'preferred_destination': 'bad\x00path'}, {'preferred_destination': 3},
    {'task_ids': 'bad'}, {'task_ids': None}, {'task_ids': (str(uuid4()),)},
    {'project_ids': (str(uuid4()),)}, {'all_tasks': 1}, {'include_deleted': 'yes'},
])
def test_invalid_preparation_has_no_effect(setup, kwargs):
    s, *_ = setup
    before = capture(s)
    with pytest.raises(ValueError):
        prepare(s, **kwargs)
    assert capture(s) == before


def test_invalid_dates_cutoff_and_legacy_work_fail_preparation(setup):
    s, a, _, _, _ = setup
    before = capture(s)
    for start, end, cutoff in ((SAT, SUN, CUTOFF), ('2026-10-11', SAT, CUTOFF), (SUN, SAT, datetime(2026, 10, 25))):
        with pytest.raises(ValueError):
            s.prepare_timesheet_export_snapshot(start, end, cutoff_utc=cutoff, all_tasks=True)
    assert capture(s) == before
    s.add_manual_duration(a, MON, 3600, 'Legacy fixture')
    before = capture(s)
    with pytest.raises(ValueError, match='Legacy synthetic'):
        prepare(s, all_tasks=True)
    assert capture(s) == before
