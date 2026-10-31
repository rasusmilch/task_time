"""Current destination observations only, using disposable registered datasets."""
from copy import deepcopy
import errno
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from task_timer import app as app_module
from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage
from test_export_materialization import registered, capture
from test_export_snapshot_registration import prepare, committed
from test_timesheet_renderer import setup


def frozen(event):
    return event['payload']['report_text'].encode('utf-8')


def test_pending_without_path_does_not_inspect_files(registered, monkeypatch):
    s, _, _ = registered
    event = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(event)
    before = capture(s)
    monkeypatch.setattr(Path, 'lstat', lambda *_: pytest.fail('No destination should be inspected'))
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'PENDING'
    assert capture(s) == before


def test_preference_and_explicit_precedence_do_not_remember_alternatives(registered):
    s, event, preferred = registered
    alternative = preferred.with_name('alternative.txt')
    alternative.write_bytes(frozen(event))
    before = capture(s)
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'MISSING'
    assert s.evaluate_timesheet_export_file_status(event['event_id'], str(alternative)) == 'READY'
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'MISSING'
    preferred.write_bytes(frozen(event))
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'READY'
    assert s.get_timesheet_export_snapshot(event['event_id']) == event
    assert capture(s) == before


@pytest.mark.parametrize('parent_exists', [True, False])
def test_reliably_absent_destination_is_missing_without_creation(registered, parent_exists):
    s, event, target = registered
    if not parent_exists:
        target = target.parent / 'absent-parent' / 'report.txt'
    before = capture(s)
    assert s.evaluate_timesheet_export_file_status(event['event_id'], target) == 'MISSING'
    assert not target.exists() and capture(s) == before
    if not parent_exists:
        assert not target.parent.exists()


@pytest.mark.parametrize('content', [b'Other complete contents', b'', b'Short'])
def test_complete_different_or_shorter_file_is_conclusive_conflict(registered, content):
    s, event, target = registered
    target.write_bytes(content)
    before = capture(s)
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'CONFLICT'
    assert target.read_bytes() == content and capture(s) == before


def test_same_length_byte_conflict_is_independent_of_digest_agreement(registered, monkeypatch):
    s, event, target = registered
    wrong = b'X' + frozen(event)[1:]
    target.write_bytes(wrong)
    monkeypatch.setattr(app_module, 'sha256', lambda _: SimpleNamespace(
        hexdigest=lambda: event['payload']['report_sha256']))
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'CONFLICT'
    assert target.read_bytes() == wrong


def test_matching_bytes_still_require_destination_digest_agreement(registered, monkeypatch):
    s, event, target = registered
    target.write_bytes(frozen(event))
    real_digest = app_module.sha256
    calls = []
    def digest(content):
        calls.append(content)
        return real_digest(content) if len(calls) == 1 else SimpleNamespace(hexdigest=lambda: '0' * 64)
    monkeypatch.setattr(app_module, 'sha256', digest)
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'CONFLICT'
    assert len(calls) == 2


@pytest.mark.parametrize('kind', ['directory', 'symlink', 'dangling', 'fifo'])
def test_unsuitable_objects_are_conflicts_without_following_them(registered, monkeypatch, kind):
    s, event, target = registered
    other = target.with_name('other.txt')
    other.write_bytes(frozen(event))
    if kind == 'directory':
        target.mkdir()
    elif kind == 'fifo':
        if not hasattr(os, 'mkfifo'):
            pytest.skip('Named pipe creation unavailable')
        os.mkfifo(target)
    else:
        try:
            target.symlink_to(other if kind == 'symlink' else target.with_name('absent.txt'))
        except (OSError, NotImplementedError) as error:
            pytest.skip(f'Symlink creation unavailable: {error}')
    before = target.lstat(), capture(s)
    monkeypatch.setattr(app_module.os, 'open', lambda *_a, **_k: pytest.fail('Unsuitable target was opened'))
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'CONFLICT'
    assert (target.lstat(), capture(s)) == before
    assert other.read_bytes() == frozen(event)


@pytest.mark.parametrize('stage', ['initial', 'verification'])
@pytest.mark.parametrize('error', [PermissionError('Denied'), FileExistsError('Not a proven conflict'),
                                 OSError(errno.EIO, 'I/O error'), InterruptedError('Interrupted')])
def test_inspection_errors_are_not_proven_conflicts(registered, monkeypatch, stage, error):
    s, event, target = registered
    target.write_bytes(frozen(event))
    before = capture(s)
    if stage == 'initial':
        real_lstat = Path.lstat
        def lstat(path):
            if path == target:
                raise error
            return real_lstat(path)
        monkeypatch.setattr(Path, 'lstat', lstat)
    else:
        monkeypatch.setattr(s, '_verify_timesheet_export_file', lambda *_: (_ for _ in ()).throw(error))
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'UNVERIFIABLE'
    assert target.read_bytes() == frozen(event) and capture(s) == before


def read_stream(monkeypatch, action):
    real_fdopen = os.fdopen
    class Stream:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            return self
        def __exit__(self, typ, error, traceback):
            self.handle.close()
        def fileno(self):
            return self.handle.fileno()
        def read(self):
            return action(self.handle)
    def fdopen(fd, mode, *args, **kwargs):
        handle = real_fdopen(fd, mode, *args, **kwargs)
        return Stream(handle) if mode == 'rb' else handle
    monkeypatch.setattr(app_module.os, 'fdopen', fdopen)


@pytest.mark.parametrize('kind', ['short-read', 'io', 'interrupted', 'same-inode-change'])
def test_incomplete_or_changing_reads_are_unverifiable(registered, monkeypatch, kind):
    s, event, target = registered
    target.write_bytes(frozen(event))
    before = capture(s)
    def read(handle):
        if kind == 'io':
            raise OSError(errno.EIO, 'Read failed')
        if kind == 'interrupted':
            raise InterruptedError('Read interrupted')
        if kind == 'same-inode-change':
            content = handle.read()
            target.write_bytes(b'Concurrent modification')
            return content
        return handle.read()[:-1]  # inspection omitted bytes that still exist
    read_stream(monkeypatch, read)
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'UNVERIFIABLE'
    assert capture(s) == before
    assert target.read_bytes() == (b'Concurrent modification' if kind == 'same-inode-change' else frozen(event))


@pytest.mark.parametrize('stage', ['before-open', 'during-read'])
def test_observed_file_disappearance_is_uncertainty_not_initial_absence(registered, monkeypatch, stage):
    s, event, target = registered
    target.write_bytes(frozen(event))
    before = capture(s)
    if stage == 'before-open':
        real_verify = s._verify_timesheet_export_file
        def disappeared(*args):
            target.unlink()  # independent actor, after evaluator observed presence
            return real_verify(*args)
        monkeypatch.setattr(s, '_verify_timesheet_export_file', disappeared)
    else:
        def read(handle):
            content = handle.read()
            target.unlink()
            return content
        read_stream(monkeypatch, read)
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'UNVERIFIABLE'
    assert not target.exists() and capture(s) == before


@pytest.mark.parametrize('stage', ['before-verifier', 'open', 'after-read'])
def test_detected_destination_replacement_is_unverifiable(registered, monkeypatch, stage):
    s, event, target = registered
    target.write_bytes(frozen(event))
    replacement = target.with_name('replacement.txt')
    replacement.write_bytes(frozen(event))  # matching bytes do not excuse a detected race
    before = capture(s)
    if stage == 'before-verifier':
        real_verify = s._verify_timesheet_export_file
        def replaced(*args):
            replacement.replace(target)
            return real_verify(*args)
        monkeypatch.setattr(s, '_verify_timesheet_export_file', replaced)
    elif stage == 'open':
        real_open = os.open
        def opened(path, flags, *args, **kwargs):
            if Path(path) == target:
                replacement.replace(target)
            return real_open(path, flags, *args, **kwargs)
        monkeypatch.setattr(app_module.os, 'open', opened)
    else:
        def read(handle):
            content = handle.read()
            replacement.replace(target)
            return content
        read_stream(monkeypatch, read)
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'UNVERIFIABLE'
    assert target.read_bytes() == frozen(event) and capture(s) == before


@pytest.mark.parametrize('destination', ['', 3, True, [], 'bad\x00path'])
def test_invalid_destination_arguments_raise_before_inspection(registered, monkeypatch, destination):
    s, event, _ = registered
    before = capture(s)
    monkeypatch.setattr(Path, 'lstat', lambda *_: pytest.fail('Invalid path inspected'))
    with pytest.raises(ValueError):
        s.evaluate_timesheet_export_file_status(event['event_id'], destination)
    assert capture(s) == before


@pytest.mark.parametrize('identity', ['invalid', None, True, 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA', '8f628bd2-e8d1-4c73-ae21-300000000001'])
def test_invalid_and_unknown_ids_fail_without_file_status(registered, identity):
    s, _, _ = registered
    if identity == '8f628bd2-e8d1-4c73-ae21-300000000001':
        assert str(UUID(identity)) == identity
        assert identity not in {e['event_id'] for e in committed(s)}
    before = capture(s)
    with pytest.raises(ValueError):
        s.evaluate_timesheet_export_file_status(identity)
    assert capture(s) == before


def test_forged_cache_cannot_authorize_unregistered_export(registered):
    s, _, target = registered
    event = prepare(s, all_tasks=True)
    target.write_bytes(frozen(event))
    s._timesheet_exports[event['event_id']] = deepcopy(event)
    before = capture(s)
    with pytest.raises(ValueError, match='committed'):
        s.evaluate_timesheet_export_file_status(event['event_id'], target)
    assert capture(s) == before


def test_corrupt_or_missing_cache_does_not_override_valid_journal(registered):
    s, event, target = registered
    target.write_bytes(frozen(event))
    for cache in ({}, {event['event_id']: {'payload': {'report_text': 'Untrusted'}}}):
        s._timesheet_exports = cache
        before = capture(s)
        assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'READY'
        assert capture(s) == before


@pytest.mark.parametrize('damage', ['missing-active', 'missing-manifest', 'partial', 'malformed',
                                  'conflict', 'digest', 'missing-archive', 'access'])
def test_journal_failures_raise_even_without_any_destination(registered, monkeypatch, damage):
    s, _, target = registered
    event = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(event)
    if damage.startswith('missing-'):
        if damage == 'missing-archive':
            s.storage.max_active_events = 1
            s.storage.rotate_if_needed()
            next(s.storage.archives_dir.glob('*.jsonl')).unlink()
        else:
            (s.storage.active_path if damage == 'missing-active' else s.storage.manifest_path).unlink()
    elif damage in ('partial', 'malformed'):
        with s.storage.active_path.open('a', encoding='utf-8') as stream:
            stream.write('{' if damage == 'partial' else '{bad json}\n')
    elif damage in ('conflict', 'digest'):
        bad = deepcopy(event)
        if damage == 'conflict':
            bad['payload']['preferred_destination'] = 'Conflicting preference'
        else:
            bad['event_id'] = str(uuid4())
            bad['payload']['report_sha256'] = '0' * 64
        s.storage.append_event(bad)
    else:
        monkeypatch.setattr(s.storage, 'iter_all_events', lambda **_: (_ for _ in ()).throw(PermissionError('Journal denied')))
    before = capture(s)
    monkeypatch.setattr(Path, 'lstat', lambda *_: pytest.fail('Evidence failure reached destination inspection'))
    for destination in (None, target):
        with pytest.raises((ValueError, OSError)):
            s.evaluate_timesheet_export_file_status(event['event_id'], destination)
    assert capture(s) == before and not target.exists()


def test_ready_is_reevaluated_after_modification_deletion_and_denied_access(registered, monkeypatch):
    s, event, target = registered
    target.write_bytes(frozen(event))
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'READY'
    target.write_bytes(b'Changed externally')
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'CONFLICT'
    target.unlink()
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'MISSING'
    target.write_bytes(frozen(event))
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'READY'
    real_open = os.open
    def denied(path, flags, *args, **kwargs):
        if Path(path) == target:
            raise PermissionError('No longer readable')
        return real_open(path, flags, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(app_module.os, 'open', denied)
        assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'UNVERIFIABLE'
    assert s.evaluate_timesheet_export_file_status(event['event_id']) == 'READY'


@pytest.mark.parametrize('preferred', [True, False])
def test_restart_replays_evidence_without_remembering_alternative_or_status(registered, preferred):
    s, event, target = registered
    if not preferred:
        event = prepare(s, all_tasks=True)
        s.register_prepared_timesheet_export(event)
    alternative = target.with_name('alternative.txt')
    alternative.write_bytes(frozen(event))
    assert s.evaluate_timesheet_export_file_status(event['event_id'], alternative) == 'READY'
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    before = capture(restarted)
    assert restarted.evaluate_timesheet_export_file_status(event['event_id']) == ('MISSING' if preferred else 'PENDING')
    assert restarted.evaluate_timesheet_export_file_status(event['event_id'], alternative) == 'READY'
    assert capture(restarted) == before


@pytest.mark.parametrize('error', [RuntimeError('Programming error'), KeyboardInterrupt(), SystemExit()])
def test_programming_and_process_control_errors_are_not_swallowed(registered, monkeypatch, error):
    s, event, target = registered
    target.write_bytes(frozen(event))
    monkeypatch.setattr(s, '_verify_timesheet_export_file', lambda *_: (_ for _ in ()).throw(error))
    with pytest.raises(type(error)) as caught:
        s.evaluate_timesheet_export_file_status(event['event_id'])
    assert caught.value is error


@pytest.mark.parametrize('status', ['PENDING', 'READY', 'MISSING', 'CONFLICT', 'UNVERIFIABLE'])
def test_all_results_are_read_only_without_retained_status(registered, monkeypatch, tmp_path, status):
    s, event, target = registered
    if status == 'PENDING':
        event = prepare(s, all_tasks=True)
        s.register_prepared_timesheet_export(event)
    if status in ('READY', 'UNVERIFIABLE', 'CONFLICT'):
        target.write_bytes(b'Conflicting bytes' if status == 'CONFLICT' else frozen(event))
    s.create_backup_now()
    before = capture(s)
    contents = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    metadata = target.stat() if target.exists() else None
    def forbidden(*args, **kwargs):
        pytest.fail('Evaluation invoked a writer, accounting, clock or renderer')
    for name in ('append_event', 'save_snapshot', 'save_manifest', 'rotate_if_needed'):
        monkeypatch.setattr(s.storage, name, forbidden)
    for name in ('materialize_timesheet_export', 'calculate_date_window'):
        monkeypatch.setattr(s, name, forbidden)
    attributes = set(vars(s))  # include test-injected methods, not a status cache
    for name in ('link', 'unlink', 'mkdir', 'replace', 'rename', 'fsync'):
        monkeypatch.setattr(app_module.os, name, forbidden)
    for name in ('unlink', 'mkdir', 'write_bytes', 'write_text'):
        monkeypatch.setattr(Path, name, forbidden)
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', forbidden)
    monkeypatch.setattr(app_module, 'build_decimal_timesheet_text', forbidden)
    monkeypatch.setattr(app_module, 'utc_now', forbidden)
    original_open, original_path_open = os.open, Path.open
    def readonly_open(path, flags, *args, **kwargs):
        assert not flags & (os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_RDWR)
        if Path(path) == target and status == 'UNVERIFIABLE':
            raise PermissionError('Injected denied read')
        return original_open(path, flags, *args, **kwargs)
    def readonly_path_open(path, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+')
        return original_path_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(app_module.os, 'open', readonly_open)
    monkeypatch.setattr(Path, 'open', readonly_path_open)
    for _ in range(2):
        assert s.evaluate_timesheet_export_file_status(event['event_id']) == status
    assert capture(s) == before and set(vars(s)) == attributes
    assert {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == contents
    if metadata:
        after = target.stat()
        assert (after.st_ino, after.st_mtime_ns, after.st_size) == (metadata.st_ino, metadata.st_mtime_ns, metadata.st_size)
