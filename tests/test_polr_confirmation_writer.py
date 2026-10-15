"""Dedicated confirmation writer: serialized service use, isolated journal fixtures."""
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from task_timer import app as app_module
from task_timer.app import TaskTimerService
from task_timer.polr_confirmations import CONFIRMATION_EVENT_TYPE
from task_timer.storage import EventStorage
from test_export_snapshot_registration import files, prepare
from test_polr_confirmation_replay import cell, batch, journal, projected, forbid_timezone_lookup_and_network
from test_timesheet_renderer import setup, dated, SUN, MON, TUE, SAT, CUTOFF


def capture(s):
    return deepcopy(s.state), deepcopy(s.events), s.get_effective_polr_confirmations(), files(s), s.list_timesheet_export_snapshots()


def occurrences(s):
    return [e for e in journal(s) if e['event_type'] == CONFIRMATION_EVENT_TYPE]


def register(s, *cells):
    event = s.prepare_polr_confirmation_batch(list(cells))
    assert s.register_prepared_polr_confirmation_batch(event) == event['event_id']
    return event


def fail(*args, **kwargs):
    raise OSError('injected failure')


def require_writable_flush_handles(monkeypatch):
    """Model Windows flush access using real file objects, not platform flags."""
    real_open, real_fsync = Path.open, os.fsync
    handles, flushed = {}, []
    def open_file(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        handles[handle.fileno()] = path, handle
        return handle
    def fsync(fd):
        path, handle = handles[fd]
        if not handle.writable():
            raise PermissionError('Simulated Windows flushing requires writable access')
        real_fsync(fd)
        flushed.append(path)
    monkeypatch.setattr(Path, 'open', open_file)
    monkeypatch.setattr(os, 'fsync', fsync)
    return flushed


def test_reuse_flushes_writable_handles_without_changing_journal_or_latest_projection(setup, monkeypatch):
    s, a, _, _, _ = setup
    candidate = register(s, cell(a))
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    latest = register(s, cell(a, 500, prior=candidate['event_id']))
    expected = [s.storage.data_dir / entry['path'] for entry in s.storage.load_manifest()['archives']]
    expected += [s.storage.active_path, s.storage.manifest_path]
    before, original = capture(s), deepcopy(candidate)
    flushed = require_writable_flush_handles(monkeypatch)
    monkeypatch.setattr(s.storage, 'append_event', lambda *a: pytest.fail('retry appended'))
    assert s.register_prepared_polr_confirmation_batch(candidate) == candidate['event_id']
    assert flushed == expected
    assert capture(s) == before and candidate == original
    assert occurrences(s) == [candidate, latest]
    assert s.get_effective_polr_confirmations()[a, MON.isoformat()] == projected(500, latest)


def test_complete_append_error_recovers_with_writable_sync_handles(setup, monkeypatch):
    s, a, _, _, _ = setup
    candidate = s.prepare_polr_confirmation_batch([cell(a)])
    original, before, append = deepcopy(candidate), capture(s), s.storage.append_event
    calls = []
    def complete_then_error(event):
        calls.append(1)
        append(event)
        raise OSError('complete append followed by error')
    flushed = require_writable_flush_handles(monkeypatch)
    monkeypatch.setattr(s.storage, 'append_event', complete_then_error)
    assert s.register_prepared_polr_confirmation_batch(candidate) == candidate['event_id']
    assert flushed == [s.storage.active_path, s.storage.active_path, s.storage.manifest_path]
    assert calls == [1] and occurrences(s) == [candidate] and candidate == original
    assert s.state == before[0] and s.list_timesheet_export_snapshots() == before[4]
    assert {k: v for k, v in files(s).items() if k != 'active_events.jsonl'} == {
        k: v for k, v in before[3].items() if k != 'active_events.jsonl'}
    committed = capture(s)
    s.register_prepared_polr_confirmation_batch(candidate)
    assert calls == [1] and capture(s) == committed


def test_preparation_is_detached_pure_frozen_and_offline(setup, monkeypatch):
    s, a, b, _, _ = setup
    inputs = [cell(b, 0, day=TUE), cell(a)]
    before = capture(s)
    identity = str(uuid4())
    s.local_tz_name = 'UTC-05:00'
    lookups = forbid_timezone_lookup_and_network(monkeypatch)
    calls = []
    monkeypatch.setattr(app_module, 'utc_now', lambda: calls.append(1) or CUTOFF)
    for name in ('append_event', 'save_snapshot', 'synchronize_journal'):
        monkeypatch.setattr(s.storage, name, lambda *a, **k: pytest.fail('preparation wrote/synchronized'))
    monkeypatch.setattr(s, 'calculate_date_window', lambda *a, **k: pytest.fail('recalculated Actual'))
    event = s.prepare_polr_confirmation_batch(inputs, batch_id=identity)
    assert event == batch(*inputs, identity=identity) | {'local_timezone': 'UTC-05:00'}
    assert calls == [1] and lookups == [] and capture(s) == before
    inputs[0]['confirmed_hundredths'] = 123
    assert event['payload']['cells'][0]['confirmed_hundredths'] == 0
    event['payload']['cells'][1]['confirmed_hundredths'] = 456
    assert inputs[1]['confirmed_hundredths'] == 300
    assert json.loads(json.dumps(event, allow_nan=False)) == event


@pytest.mark.parametrize('fault', ['empty', 'tuple', 'dict', 'none', 'extra', 'duplicate', 'unknown-task',
                                  'bad-date', 'bool', 'float', 'negative', 'unknown-export',
                                  'wrong-prior', 'unneeded-ack', 'bad-id', 'bad-zone'])
def test_invalid_preparation_never_mutates(setup, fault):
    s, a, _, _, _ = setup
    cells, identity = [cell(a)], None
    if fault == 'empty': cells = []
    elif fault == 'tuple': cells = tuple(cells)
    elif fault == 'dict': cells = cells[0]
    elif fault == 'none': cells = None
    elif fault == 'extra': cells[0]['extra'] = None
    elif fault == 'duplicate': cells *= 2
    elif fault == 'unknown-task': cells[0]['task_id'] = str(uuid4())
    elif fault == 'bad-date': cells[0]['work_date'] = '2026-02-30'
    elif fault == 'bool': cells[0]['confirmed_hundredths'] = True
    elif fault == 'float': cells[0]['confirmed_hundredths'] = 3.0
    elif fault == 'negative': cells[0]['confirmed_hundredths'] = -1
    elif fault == 'unknown-export': cells[0]['source_export_id'] = str(uuid4())
    elif fault == 'wrong-prior': cells[0]['expected_prior_confirmation_id'] = str(uuid4())
    elif fault == 'unneeded-ack': cells[0]['stale_export_acknowledged'] = True
    elif fault == 'bad-id': identity = 'invalid'
    elif fault == 'bad-zone': s.local_tz_name = 'UTC\x00bad'
    before, original = capture(s), deepcopy(cells)
    with pytest.raises(ValueError):
        s.prepare_polr_confirmation_batch(cells, batch_id=identity)
    assert capture(s) == before and cells == original


def test_writer_absolute_zero_frozen_provenance_and_unchanged_actual(setup, tmp_path, monkeypatch):
    s, a, b, _, _ = setup
    dated(s, a, MON, 10800)
    export = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(export)
    target = tmp_path / 'frozen.txt'
    s.materialize_timesheet_export(export['event_id'], target)
    dated(s, a, MON, 7200)
    s.start_task(a)
    before = (deepcopy(s.state), s.snapshot_dict(), s.calculate_date_window(SUN, SAT, cutoff_utc=CUTOFF, all_tasks=True),
              s.list_time_submissions(), s.list_timesheet_export_snapshots(), files(s), target.read_bytes())
    # Frozen provenance is independent of current external-file readiness.
    with monkeypatch.context() as m:
        m.setattr(s, '_verify_timesheet_export_file', lambda *a: pytest.fail('inspected external file'))
        m.setattr(s, 'calculate_date_window', lambda *a, **k: pytest.fail('recalculated'))
        for name in ('save_snapshot',): m.setattr(s.storage, name, fail)
        m.setattr(s, 'create_backup_now', fail)
        event = register(s, cell(a, 300, source=export['event_id']), cell(b, 0, day=TUE))
    assert s.get_effective_polr_confirmations() == {
        (a, MON.isoformat()): projected(300, event), (b, TUE.isoformat()): projected(0, event)}
    assert (b, MON.isoformat()) not in s.get_effective_polr_confirmations()
    after = (s.state, s.snapshot_dict(), s.calculate_date_window(SUN, SAT, cutoff_utc=CUTOFF, all_tasks=True),
             s.list_time_submissions(), s.list_timesheet_export_snapshots(), files(s), target.read_bytes())
    assert after[:5] == before[:5] and after[-1] == before[-1]
    assert {k: v for k, v in after[5].items() if k != 'active_events.jsonl'} == {
        k: v for k, v in before[5].items() if k != 'active_events.jsonl'}
    assert s.state.tasks[a].is_running and occurrences(s) == [event]
    assert not any('confirmation' in k for k in s.snapshot_dict())
    event['payload']['cells'][0]['confirmed_hundredths'] = 999
    assert s.get_effective_polr_confirmations()[a, MON.isoformat()]['confirmed_hundredths'] == 300


@pytest.mark.parametrize('same_amount', [False, True])
def test_superseded_prior_rejects_entire_prepared_batch(setup, same_amount):
    s, a, b, _, _ = setup
    first = register(s, cell(a))
    candidate = s.prepare_polr_confirmation_batch([cell(b), cell(a, 500, prior=first['event_id'])])
    register(s, cell(a, 300 if same_amount else 400, prior=first['event_id']))
    before, original = capture(s), deepcopy(candidate)
    with pytest.raises(ValueError, match='prior identity'):
        s.register_prepared_polr_confirmation_batch(candidate)
    assert capture(s) == before and candidate == original
    assert (b, MON.isoformat()) not in s.get_effective_polr_confirmations()


def test_unrelated_change_and_retry_preserve_latest_projection(setup, monkeypatch):
    s, a, b, _, _ = setup
    first = s.prepare_polr_confirmation_batch([cell(a)])
    unrelated = register(s, cell(b, 0))
    s.register_prepared_polr_confirmation_batch(first)
    latest = register(s, cell(a, 500, prior=first['event_id']))
    before = capture(s)
    monkeypatch.setattr(s.storage, 'append_event', lambda *a: pytest.fail('duplicate append'))
    assert s.register_prepared_polr_confirmation_batch(first) == first['event_id']
    assert capture(s) == before and occurrences(s) == [unrelated, first, latest]
    assert s.get_effective_polr_confirmations()[a, MON.isoformat()] == projected(500, latest)


@pytest.mark.parametrize('when', ['2000-01-01T00:00:00Z', '2026-10-25T12:00:00Z'])
def test_registration_follows_physical_not_audit_order(setup, when):
    s, a, _, _, _ = setup
    first = register(s, cell(a))
    candidate = s.prepare_polr_confirmation_batch([cell(a, 0, prior=first['event_id'])])
    candidate['timestamp_utc'] = when
    s.register_prepared_polr_confirmation_batch(candidate)
    assert s.get_effective_polr_confirmations()[a, MON.isoformat()] == projected(0, candidate)
    assert TaskTimerService(EventStorage(s.storage.data_dir)).get_effective_polr_confirmations() == s.get_effective_polr_confirmations()


@pytest.mark.parametrize('source_after_prior', [False, True])
@pytest.mark.parametrize('same_amount', [False, True])
@pytest.mark.parametrize('ack', [False, True])
def test_writer_exact_stale_acknowledgement_truth(setup, source_after_prior, same_amount, ack):
    s, a, _, _, _ = setup
    dated(s, a, MON, 60)
    if source_after_prior:
        prior = register(s, cell(a, 2 if same_amount else 300))
    export = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(export)
    if not source_after_prior:
        prior = register(s, cell(a, 2 if same_amount else 300))
    inputs = [cell(a, 2, source=export['event_id'], prior=prior['event_id'], acknowledged=ack)]
    stale = not source_after_prior and not same_amount
    before = capture(s)
    if ack != stale:
        with pytest.raises(ValueError, match='acknowledgement'):
            s.prepare_polr_confirmation_batch(inputs)
        assert capture(s) == before
    else:
        register(s, *inputs)


@pytest.mark.parametrize('fault', ['changed', 'reordered', 'other-type', 'invalid-cell', 'invalid-envelope'])
def test_registration_rejects_content_or_identity_collision_without_mutation(setup, fault):
    s, a, b, _, _ = setup
    event = register(s, cell(a), cell(b))
    candidate = deepcopy(event)
    if fault == 'changed': candidate['payload']['cells'][0]['confirmed_hundredths'] += 1
    elif fault == 'reordered': candidate['payload']['cells'].reverse()
    elif fault == 'other-type': candidate['event_id'] = next(e['event_id'] for e in journal(s) if e['event_type'] == 'task_created')
    elif fault == 'invalid-cell': candidate['payload']['cells'][0]['confirmed_hundredths'] = True
    else: candidate['extra'] = None
    before = capture(s)
    with pytest.raises(ValueError): s.register_prepared_polr_confirmation_batch(candidate)
    assert capture(s) == before


@pytest.mark.parametrize('fault', ['bad-json', 'missing-active', 'missing-manifest', 'invalid-confirmation'])
def test_journal_not_caches_authorizes_preparation_and_registration(setup, fault):
    s, a, _, _, _ = setup
    event = s.prepare_polr_confirmation_batch([cell(a)])
    if fault == 'bad-json':
        with s.storage.active_path.open('a') as f: f.write('{broken')
    elif fault == 'missing-active': s.storage.active_path.unlink()
    elif fault == 'missing-manifest': s.storage.manifest_path.unlink()
    else: s.storage.append_event(batch(cell(a, prior=str(uuid4()))))
    s._polr_confirmations = {(a, MON.isoformat()): projected(300, event)}
    before = capture(s)
    for op in (lambda: s.prepare_polr_confirmation_batch([cell(a)]),
               lambda: s.register_prepared_polr_confirmation_batch(event)):
        with pytest.raises((ValueError, OSError)): op()
        assert capture(s) == before


@pytest.mark.parametrize('fault', ['before', 'noop', 'partial', 'complete-error'])
def test_append_failure_boundaries(setup, monkeypatch, fault):
    s, a, _, _, _ = setup
    candidate = s.prepare_polr_confirmation_batch([cell(a)])
    original, before, append = deepcopy(candidate), capture(s), s.storage.append_event
    error = OSError('original append failure')
    def injected(event):
        if fault == 'before': raise error
        if fault == 'noop': return
        if fault == 'partial':
            with s.storage.active_path.open('ab') as handle: handle.write(b'{partial')
            raise error
        append(event)
        raise error
    monkeypatch.setattr(s.storage, 'append_event', injected)
    if fault == 'complete-error':
        assert s.register_prepared_polr_confirmation_batch(candidate) == candidate['event_id']
        assert occurrences(s) == [candidate]
    else:
        with pytest.raises((OSError, ValueError)) as caught:
            s.register_prepared_polr_confirmation_batch(candidate)
        if fault != 'noop': assert caught.value is error
        assert s.get_effective_polr_confirmations() == before[2] and s.events == before[1]
        if fault != 'partial': assert capture(s) == before
        else:
            assert s.storage.active_path.read_bytes() == before[3]['active_events.jsonl'] + b'{partial'
    assert candidate == original
    if fault == 'before':
        monkeypatch.setattr(s.storage, 'append_event', append)
        s.register_prepared_polr_confirmation_batch(candidate)
        assert occurrences(s) == [candidate]


@pytest.mark.parametrize('persistent', [False, True])
def test_failed_fsync_requires_successful_recovery_sync(setup, monkeypatch, persistent):
    s, a, _, _, _ = setup
    candidate = s.prepare_polr_confirmation_batch([cell(a)])
    before = capture(s)
    real_fsync, calls = os.fsync, []
    def injected(fd):
        calls.append(1)
        if persistent or len(calls) == 1: raise OSError('fsync failed')
        return real_fsync(fd)
    monkeypatch.setattr(os, 'fsync', injected)
    if persistent:
        for _ in range(2):
            with pytest.raises(OSError, match='fsync failed') as caught:
                s.register_prepared_polr_confirmation_batch(candidate)
            assert any('uncertain' in n for n in caught.value.__notes__)
            assert s.get_effective_polr_confirmations() == before[2]
            assert occurrences(s) == [candidate]
        monkeypatch.setattr(os, 'fsync', real_fsync)
        s.register_prepared_polr_confirmation_batch(candidate)
    else:
        s.register_prepared_polr_confirmation_batch(candidate)
        assert len(calls) == 3  # failed append fsync, then active and manifest synchronization
    assert occurrences(s) == [candidate]
    assert s.get_effective_polr_confirmations()[a, MON.isoformat()] == projected(300, candidate)


def test_reuse_synchronizes_all_indexed_journal_files_without_byte_changes(setup, monkeypatch):
    s, a, _, _, _ = setup
    candidate = register(s, cell(a))
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    register(s, cell(a, 0, prior=candidate['event_id']))
    paths = [s.storage.data_dir / entry['path'] for entry in s.storage.load_manifest()['archives']]
    paths += [s.storage.active_path, s.storage.manifest_path]
    expected = [(p.stat().st_dev, p.stat().st_ino) for p in paths]
    observed, real = [], os.fsync
    def fsync(fd):
        info = os.fstat(fd)
        observed.append((info.st_dev, info.st_ino))
        return real(fd)
    before = capture(s)
    monkeypatch.setattr(os, 'fsync', fsync)
    s.register_prepared_polr_confirmation_batch(candidate)
    assert observed == expected and capture(s) == before


@pytest.mark.parametrize('fault', ['sync', 'open', 'fsync', 'close', 'post-sync-inspection'])
def test_reuse_sync_or_close_failure_never_succeeds_or_appends(setup, monkeypatch, fault):
    s, a, _, _, _ = setup
    candidate = register(s, cell(a))
    before = capture(s)
    real_open, read, install = Path.open, s.storage.iter_all_events, s._install_export_journal
    reached, installed = [], []
    monkeypatch.setattr(s.storage, 'append_event', lambda *a: pytest.fail('retry appended'))
    def track_install(*args):
        installed.append(1)
        return install(*args)
    monkeypatch.setattr(s, '_install_export_journal', track_install)
    with monkeypatch.context() as m:
        if fault == 'sync': m.setattr(s.storage, 'synchronize_journal', fail)
        elif fault == 'open':
            def denied(path, *args, **kwargs):
                if path == s.storage.active_path and args == ('r+b',):
                    reached.append('open')
                    raise PermissionError('writable access denied')
                return real_open(path, *args, **kwargs)
            m.setattr(Path, 'open', denied)
        elif fault == 'fsync':
            def failed_flush(fd):
                reached.append('fsync')
                raise OSError('fsync failed')
            m.setattr(os, 'fsync', failed_flush)
        elif fault == 'close':
            class CloseFailure:
                def __enter__(self):
                    self.handle = real_open(s.storage.active_path, 'r+b')
                    assert self.handle.writable()
                    reached.append('opened')
                    return self.handle
                def __exit__(self, *args):
                    self.handle.close()
                    reached.append('closed')
                    raise OSError('close failed')
            def open_file(path, *args, **kwargs):
                return CloseFailure() if path == s.storage.active_path and args == ('r+b',) else real_open(path, *args, **kwargs)
            m.setattr(Path, 'open', open_file)
        else:
            calls = []
            def inspect(*args, **kwargs):
                calls.append(1)
                if len(calls) == 3: raise OSError('post-sync inspection failed')
                return read(*args, **kwargs)
            m.setattr(s.storage, 'iter_all_events', inspect)
        with pytest.raises(OSError) as caught: s.register_prepared_polr_confirmation_batch(candidate)
        assert any('uncertain' in n for n in caught.value.__notes__)
        assert installed == [] and capture(s) == before
    if fault == 'close': assert reached == ['opened', 'closed']
    elif fault in ('open', 'fsync'): assert reached == [fault]
    assert s.register_prepared_polr_confirmation_batch(candidate) == candidate['event_id']
    assert installed == [1] and capture(s) == before and occurrences(s) == [candidate]


@pytest.mark.parametrize('component', ['archive', 'active', 'manifest'])
def test_sync_missing_existing_file_is_not_recreated(setup, monkeypatch, component):
    s, a, _, _, _ = setup
    candidate = register(s, cell(a))
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    archive = s.storage.data_dir / s.storage.load_manifest()['archives'][0]['path']
    target = {'archive': archive, 'active': s.storage.active_path, 'manifest': s.storage.manifest_path}[component]
    before, original, real_open = capture(s), deepcopy(candidate), Path.open
    reached = []
    def disappear_before_open(path, *args, **kwargs):
        if path == target and args == ('r+b',):
            reached.append(1)
            path.unlink()  # isolated fixture race after successful strict preflight
        return real_open(path, *args, **kwargs)
    with monkeypatch.context() as m:
        m.setattr(Path, 'open', disappear_before_open)
        m.setattr(s.storage, 'append_event', lambda *a: pytest.fail('retry appended'))
        with pytest.raises(FileNotFoundError) as caught:
            s.register_prepared_polr_confirmation_batch(candidate)
        assert any('uncertain' in note for note in caught.value.__notes__)
    assert reached == [1] and not target.exists() and candidate == original
    expected_files = before[3] | {}
    del expected_files[str(target.relative_to(s.storage.data_dir))]
    assert files(s) == expected_files
    assert (s.state, s.events, s.get_effective_polr_confirmations(), s.list_timesheet_export_snapshots()) == (
        before[0], before[1], before[2], before[4])
    with pytest.raises((ValueError, OSError)):
        s.register_prepared_polr_confirmation_batch(candidate)
    assert not target.exists() and files(s) == expected_files


def test_rotation_manifest_failure_fails_closed_without_duplicate_or_repair(setup, monkeypatch):
    s, a, _, _, _ = setup
    event = s.prepare_polr_confirmation_batch([cell(a)])
    s.storage.max_active_events = 1
    monkeypatch.setattr(s.storage, 'save_manifest', fail)
    with pytest.raises(OSError) as caught: s.register_prepared_polr_confirmation_batch(event)
    assert any('uncertain' in n for n in caught.value.__notes__)
    before = files(s)
    assert len(list(s.storage.archives_dir.glob('*.jsonl'))) == 1
    for _ in range(2):
        with pytest.raises(ValueError, match='unindexed'): s.register_prepared_polr_confirmation_batch(event)
        assert files(s) == before
    assert s.get_effective_polr_confirmations() == {}


@pytest.mark.parametrize('fault', ['inspection', 'installation'])
def test_post_append_failure_preserves_identity_for_recovery(setup, monkeypatch, fault):
    s, a, _, _, _ = setup
    event = s.prepare_polr_confirmation_batch([cell(a)])
    before = capture(s)
    read = s.storage.iter_all_events
    with monkeypatch.context() as m:
        if fault == 'installation': m.setattr(s, '_install_export_journal', fail)
        else:
            calls = []
            def inspect(*args, **kwargs):
                calls.append(1)
                if len(calls) > 1: raise OSError('inspection failed')
                return read(*args, **kwargs)
            m.setattr(s.storage, 'iter_all_events', inspect)
        with pytest.raises(OSError): s.register_prepared_polr_confirmation_batch(event)
    assert s.state == before[0] and s.events == before[1] and s.get_effective_polr_confirmations() == before[2]
    assert occurrences(s) == [event]
    s.register_prepared_polr_confirmation_batch(event)
    assert occurrences(s) == [event]
    assert s.get_effective_polr_confirmations()[a, MON.isoformat()] == projected(300, event)


def test_writer_restart_rotation_rebuild_and_backup_restore(setup):
    s, a, b, _, q = setup
    dated(s, a, MON, 60)
    s.start_task(a)
    export = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(export)
    first = register(s, cell(a, 2, source=export['event_id']), cell(b, 0, day=TUE))
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    latest = register(s, cell(a, 500, prior=first['event_id']))
    expected = s.get_effective_polr_confirmations()
    backup = s.create_backup_now()
    register(s, cell(a, 0, prior=latest['event_id']))
    s.restore_from_backup(backup)
    assert s.get_effective_polr_confirmations() == expected
    s = TaskTimerService(EventStorage(s.storage.data_dir))
    assert s.get_effective_polr_confirmations() == expected
    s.update_task(a, 'Renamed', '')
    s.assign_task_to_project(a, q)
    s.delete_task(a)
    s.rebuild_snapshot_from_journal()
    assert s.get_effective_polr_confirmations() == expected
    assert s.get_timesheet_export_snapshot(export['event_id']) == export
    before = capture(s)
    s.register_prepared_polr_confirmation_batch(first)
    assert capture(s) == before and occurrences(s) == [first, latest]


@pytest.mark.parametrize('fault', ['duplicate', 'source-mismatch', 'future-source', 'unknown-task', 'extra-cell'])
def test_unreviewed_registration_rejects_entire_batch(setup, fault):
    s, a, b, _, _ = setup
    dated(s, a, MON, 60)
    export = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(export)
    candidate = s.prepare_polr_confirmation_batch([cell(b, 0), cell(a, 2, source=export['event_id'])])
    invalid = candidate['payload']['cells'][1]
    if fault == 'duplicate': candidate['payload']['cells'].append(deepcopy(invalid))
    elif fault == 'source-mismatch': invalid['confirmed_hundredths'] = 3
    elif fault == 'future-source': invalid['source_export_id'] = prepare(s, all_tasks=True)['event_id']
    elif fault == 'unknown-task': invalid['task_id'] = str(uuid4())
    else: invalid['extra'] = False
    before, frozen = capture(s), deepcopy(candidate)
    with pytest.raises(ValueError): s.register_prepared_polr_confirmation_batch(candidate)
    assert capture(s) == before and candidate == frozen


def test_new_registration_does_not_trust_stale_prior_cache(setup):
    s, a, _, _, _ = setup
    event = s.prepare_polr_confirmation_batch([cell(a)])
    s.storage.append_event(batch(cell(a)))  # committed elsewhere in the serialized test, not installed
    before = capture(s)
    with pytest.raises(ValueError, match='prior identity'): s.register_prepared_polr_confirmation_batch(event)
    assert capture(s) == before


@pytest.mark.parametrize('fault', ['conflicting-complete', 'invalid-complete'])
def test_ambiguous_append_with_invalid_evidence_never_installs_or_repairs(setup, monkeypatch, fault):
    s, a, _, _, _ = setup
    event = s.prepare_polr_confirmation_batch([cell(a)])
    append = s.storage.append_event
    def injected(candidate):
        altered = deepcopy(candidate)
        if fault == 'conflicting-complete': altered['payload']['cells'][0]['confirmed_hundredths'] += 1
        else: altered['payload']['cells'][0]['confirmed_hundredths'] = True
        append(altered)
        raise OSError('append reported failure')
    monkeypatch.setattr(s.storage, 'append_event', injected)
    before = deepcopy(s.events), s.get_effective_polr_confirmations()
    with pytest.raises(OSError) as caught: s.register_prepared_polr_confirmation_batch(event)
    assert any('uncertain' in note for note in caught.value.__notes__)
    assert (s.events, s.get_effective_polr_confirmations()) == before
    surviving = files(s)
    with pytest.raises(ValueError): s.register_prepared_polr_confirmation_batch(event)
    assert files(s) == surviving


def test_install_validates_complete_projection_before_changing_any_evidence(setup):
    s, a, b, _, _ = setup
    first = register(s, cell(a))
    invalid = batch(cell(b), cell(a, 500))
    loaded = s.storage.iter_all_events(strict=True)
    invalid['_read_sequence'] = max(e['_read_sequence'] for e in loaded) + 1
    before = capture(s)
    with pytest.raises(ValueError): s._install_export_journal([*loaded, invalid], {})
    assert capture(s) == before
    assert s.get_effective_polr_confirmations()[a, MON.isoformat()] == projected(300, first)


def test_sync_revalidation_does_not_install_corrupted_evidence(setup, monkeypatch):
    s, a, _, _, _ = setup
    event = register(s, cell(a))
    sync = s.storage.synchronize_journal
    def corrupted():
        loaded = sync()
        loaded[-1]['payload']['cells'][0]['confirmed_hundredths'] = True
        return loaded
    monkeypatch.setattr(s.storage, 'synchronize_journal', corrupted)
    before = capture(s)
    with pytest.raises(ValueError): s.register_prepared_polr_confirmation_batch(event)
    assert capture(s) == before
