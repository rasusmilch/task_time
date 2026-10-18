"""Verified copies of committed evidence; every dataset/output is disposable."""
from copy import deepcopy
from datetime import datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import errno
import os
from types import SimpleNamespace

import pytest

from task_timer import app as app_module
from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage
from test_export_snapshot_registration import prepare, files
from test_timesheet_renderer import setup, dated, MON, TUE, CUTOFF, table_rows


def capture(s):
    return (deepcopy(s.state), deepcopy(s.events), files(s),
            s.list_timesheet_export_snapshots(), s.list_time_submissions())


def stages(parent):
    return list(parent.glob('.chronicle-*.tmp'))


@pytest.fixture
def registered(setup, tmp_path):
    s, a, b, p, q = setup
    s.update_task(a, 'Management é 漢字 e\u0301 \u202e ' + 'long assignment ' * 8 + 'end', '')
    u = s.create_task('Unassigned', '')
    dated(s, a, MON, 60)
    start = datetime.combine(MON, time(9), s.local_tz)
    s.add_manual_interval(b, start, start + timedelta(seconds=60), 'Real work')
    dated(s, u, MON, 60)
    s.start_task(a)
    target = tmp_path / 'timesheet.txt'
    event = prepare(s, all_tasks=True, preferred_destination=str(target))
    s.register_prepared_timesheet_export(event)
    return s, event, target


def test_frozen_utf8_bytes_decimal_values_and_purity(registered):
    s, event, target = registered
    before = capture(s)
    assert s.materialize_timesheet_export(event['event_id'], target) == target
    content = target.read_bytes()
    assert content == event['payload']['report_text'].encode('utf-8')
    assert sha256(content).hexdigest() == event['payload']['report_sha256']
    assert content.endswith(b'\n') and b'\r\n' not in content
    assert table_rows(content.decode(), 'Application total')[0][-1] == '0.06'
    assert sum(cell['actual_seconds'] for row in event['payload']['tasks'] for cell in row['daily']) == 180
    assert s.state.tasks[s.state.running_task_id].is_running
    assert not stages(target.parent) and capture(s) == before


def test_default_preference_and_alternative_paths_do_not_change_snapshot(registered):
    s, event, target = registered
    before = capture(s)
    assert s.materialize_timesheet_export(event['event_id']) == target
    other = target.with_name('alternative.txt')
    assert s.materialize_timesheet_export(event['event_id'], str(other)) == other
    assert other.read_bytes() == target.read_bytes()
    assert s.get_timesheet_export_snapshot(event['event_id']) == event
    assert capture(s) == before


@pytest.mark.parametrize('identity', ['invalid', True, None, 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA', str(uuid4())])
def test_invalid_unknown_ids_cannot_create_files(registered, identity):
    s, _, target = registered
    before = capture(s)
    with pytest.raises(ValueError):
        s.materialize_timesheet_export(identity, target)
    assert not target.exists() and not stages(target.parent) and capture(s) == before


def test_prepared_but_unregistered_or_cached_only_event_is_not_authority(registered):
    s, _, target = registered
    candidate = prepare(s, all_tasks=True)
    s._timesheet_exports[candidate['event_id']] = deepcopy(candidate)  # deliberately forged cache
    before = capture(s)
    with pytest.raises(ValueError, match='committed'):
        s.materialize_timesheet_export(candidate['event_id'], target)
    assert not target.exists() and not stages(target.parent) and capture(s) == before


def test_destination_is_required_without_preference(registered):
    s, _, target = registered
    candidate = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(candidate)
    before = capture(s)
    with pytest.raises(ValueError, match='destination'):
        s.materialize_timesheet_export(candidate['event_id'])
    assert not target.exists() and not stages(target.parent) and capture(s) == before


@pytest.mark.parametrize('target', ['', 3, True, [], 'bad\x00path'])
def test_invalid_destination_rejected_before_staging(registered, target):
    s, event, preferred = registered
    before = capture(s)
    with pytest.raises(ValueError):
        s.materialize_timesheet_export(event['event_id'], target)
    assert not preferred.exists() and not stages(preferred.parent) and capture(s) == before


@pytest.mark.parametrize('damage', ['partial', 'missing-active', 'missing-manifest', 'conflict', 'digest'])
def test_unhealthy_authoritative_journal_prevents_all_publication(registered, damage, monkeypatch):
    s, event, target = registered
    if damage == 'partial':
        with s.storage.active_path.open('a', encoding='utf-8') as stream:
            stream.write('{')
    elif damage.startswith('missing'):
        (s.storage.active_path if damage == 'missing-active' else s.storage.manifest_path).unlink()
    else:
        bad = deepcopy(event)
        if damage == 'conflict':
            bad['payload']['preferred_destination'] = 'conflicting.txt'
        else:
            bad['event_id'] = str(uuid4())
            bad['payload']['report_sha256'] = '0' * 64
        s.storage.append_event(bad)
    before = capture(s)
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', lambda **_: pytest.fail('Unverified evidence reached staging'))
    with pytest.raises((ValueError, OSError)):
        s.materialize_timesheet_export(event['event_id'], target)
    assert not target.exists() and capture(s) == before


def test_frozen_journal_contents_override_a_corrupt_memory_cache(registered):
    s, event, target = registered
    s._timesheet_exports[event['event_id']]['payload']['report_text'] = 'Unverified cached text\n'
    before = capture(s)
    s.materialize_timesheet_export(event['event_id'], target)
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert capture(s) == before


def test_existing_matching_file_is_verified_without_rewriting(registered, monkeypatch):
    s, event, target = registered
    target.write_bytes(event['payload']['report_text'].encode('utf-8'))
    status = target.stat()
    before = capture(s)
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', lambda **_: pytest.fail('Matching file was restaged'))
    monkeypatch.setattr(app_module.os, 'link', lambda *_: pytest.fail('Matching file was republished'))
    assert s.materialize_timesheet_export(event['event_id'], target) == target
    assert (target.stat().st_ino, target.stat().st_mtime_ns) == (status.st_ino, status.st_mtime_ns)
    assert capture(s) == before


def test_full_byte_comparison_rejects_same_size_even_with_matching_digest(registered, monkeypatch):
    s, event, target = registered
    expected = event['payload']['report_text'].encode('utf-8')
    wrong = b'X' + expected[1:]
    target.write_bytes(wrong)
    before = capture(s)
    monkeypatch.setattr(app_module, 'sha256', lambda _: SimpleNamespace(hexdigest=lambda: event['payload']['report_sha256']))
    with pytest.raises(FileExistsError, match='conflicts'):
        s.materialize_timesheet_export(event['event_id'], target)
    assert target.read_bytes() == wrong and capture(s) == before
    assert not stages(target.parent)


@pytest.mark.parametrize('kind', ['directory', 'symlink', 'dangling', 'fifo'])
def test_unsuitable_existing_destinations_are_not_followed_or_replaced(registered, kind):
    s, event, target = registered
    other = target.with_name('unrelated.txt')
    other.write_bytes(b'Existing independent file')
    if kind == 'directory':
        target.mkdir()
    elif kind == 'fifo':
        if not hasattr(os, 'mkfifo'):
            pytest.skip('Named pipe creation unavailable')
        os.mkfifo(target)
    else:
        try:
            target.symlink_to(other if kind == 'symlink' else target.with_name('absent.txt'))
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f'Symlink creation unavailable: {exc}')
    status = target.lstat()
    before = capture(s)
    with pytest.raises(FileExistsError, match='not a regular file'):
        s.materialize_timesheet_export(event['event_id'], target)
    assert target.lstat().st_mode == status.st_mode and target.lstat().st_ino == status.st_ino
    assert other.read_bytes() == b'Existing independent file'
    assert not stages(target.parent) and capture(s) == before


def test_missing_parent_is_not_created(registered):
    s, event, target = registered
    target = target.parent / 'absent-parent' / 'report.txt'
    before = capture(s)
    with pytest.raises(FileNotFoundError):
        s.materialize_timesheet_export(event['event_id'], target)
    assert not target.parent.exists() and capture(s) == before


@pytest.mark.parametrize('existing', [False, True])
def test_permission_failures_are_not_matches_or_success(registered, monkeypatch, existing):
    s, event, target = registered
    failure = PermissionError(errno.EACCES, 'Injected denied access')
    if existing:
        target.write_bytes(event['payload']['report_text'].encode('utf-8'))
        original = os.open
        def denied(path, flags, *args, **kwargs):
            if Path(path) == target:
                raise failure
            return original(path, flags, *args, **kwargs)
        monkeypatch.setattr(app_module.os, 'open', denied)
    else:
        monkeypatch.setattr(app_module.tempfile, 'mkstemp', lambda **_: (_ for _ in ()).throw(failure))
    before = capture(s)
    with pytest.raises(PermissionError) as caught:
        s.materialize_timesheet_export(event['event_id'], target)
    assert caught.value is failure
    assert target.exists() is existing and not stages(target.parent) and capture(s) == before


def staged_stream(monkeypatch, callback):
    original = os.fdopen
    class Stream:
        def __init__(self, wrapped):
            self.wrapped = wrapped
        def __enter__(self):
            return self
        def __exit__(self, typ, error, tb):
            self.wrapped.close()
            if error is None:
                callback('close', self.wrapped, None)
        def write(self, content):
            return callback('write', self.wrapped, content)
        def flush(self):
            return callback('flush', self.wrapped, None)
        def fileno(self):
            return self.wrapped.fileno()
    def wrap(fd, mode, *args, **kwargs):
        stream = original(fd, mode, *args, **kwargs)
        return Stream(stream) if mode == 'wb' else stream
    monkeypatch.setattr(app_module.os, 'fdopen', wrap)


def test_complete_staging_is_synced_closed_then_published_and_verified(registered, monkeypatch):
    s, event, target = registered
    expected = event['payload']['report_text'].encode('utf-8')
    before = capture(s)
    sequence = []
    def operation(phase, stream, content):
        assert not target.exists()
        if phase == 'write':
            sequence.append('write')
            stream.write(content[:21])
            stream.flush()
            assert stages(target.parent)[0].read_bytes() == expected[:21]
            assert not target.exists()
            stream.write(content[21:])
            return len(content)
        sequence.append(phase)
        if phase == 'flush':
            stream.flush()
        else:
            assert stream.closed
    staged_stream(monkeypatch, operation)
    real_sync, real_link, verify = os.fsync, os.link, s._verify_timesheet_export_file
    def sync(fd):
        sequence.append('fsync')
        return real_sync(fd)
    def link(stage, destination):
        assert sequence == ['write', 'flush', 'fsync', 'close']
        assert Path(stage).read_bytes() == expected
        if os.name == 'posix':
            assert Path(stage).stat().st_mode & 0o777 == 0o600
        sequence.append('link')
        return real_link(stage, destination)
    def verified(path, content, digest):
        if path.exists():
            assert sequence[-1] == 'link'
            sequence.append('verify')
        return verify(path, content, digest)
    monkeypatch.setattr(app_module.os, 'fsync', sync)
    monkeypatch.setattr(app_module.os, 'link', link)
    monkeypatch.setattr(s, '_verify_timesheet_export_file', verified)
    assert s.materialize_timesheet_export(event['event_id'], target) == target
    assert sequence == ['write', 'flush', 'fsync', 'close', 'link', 'verify']
    assert target.read_bytes() == expected and not stages(target.parent) and capture(s) == before


@pytest.mark.parametrize('phase', ['write', 'short-write', 'flush', 'fsync', 'close'])
def test_staging_failures_never_publish_partial_report(registered, monkeypatch, phase):
    s, event, target = registered
    before = capture(s)
    failure = OSError(errno.EIO, f'Injected {phase} failure')
    def operation(operation, stream, content):
        assert not target.exists()
        if operation == 'write':
            if phase in ('write', 'short-write'):
                stream.write(content[:21])
                stream.flush()
                if phase == 'write':
                    raise failure
                return 21
            return stream.write(content)
        if operation == 'flush':
            stream.flush()
        if phase == operation:
            raise failure
    staged_stream(monkeypatch, operation)
    if phase == 'fsync':
        monkeypatch.setattr(app_module.os, 'fsync', lambda _: (_ for _ in ()).throw(failure))
    monkeypatch.setattr(app_module.os, 'link', lambda *_: pytest.fail('Incomplete staging was published'))
    with pytest.raises(OSError) as caught:
        s.materialize_timesheet_export(event['event_id'], target)
    if phase != 'short-write':
        assert caught.value is failure
    assert not target.exists() and not stages(target.parent) and capture(s) == before


@pytest.mark.parametrize('error_code', [errno.EIO, errno.ENOTSUP, errno.EACCES])
def test_publication_failures_have_no_unsafe_fallback(registered, monkeypatch, error_code):
    s, event, target = registered
    before = capture(s)
    failure = OSError(error_code, 'Link unavailable')
    monkeypatch.setattr(app_module.os, 'link', lambda *_: (_ for _ in ()).throw(failure))
    with pytest.raises(OSError) as caught:
        s.materialize_timesheet_export(event['event_id'], target)
    assert caught.value is failure and 'not been verified' in failure.__notes__[0]
    assert not target.exists() and not stages(target.parent) and capture(s) == before


def test_concurrent_destination_is_preserved_and_retry_rejects_conflict(registered, monkeypatch):
    s, event, target = registered
    before = capture(s)
    real_link = os.link
    def race(stage, destination):
        target.write_bytes(b'Concurrent independent contents')
        return real_link(stage, destination)
    with monkeypatch.context() as patch:
        patch.setattr(app_module.os, 'link', race)
        with pytest.raises(FileExistsError):
            s.materialize_timesheet_export(event['event_id'], target)
    with pytest.raises(FileExistsError, match='conflicts'):
        s.materialize_timesheet_export(event['event_id'], target)
    assert target.read_bytes() == b'Concurrent independent contents'
    assert not stages(target.parent) and capture(s) == before


def test_ambiguous_link_success_is_not_claimed_verified_and_retry_reuses_file(registered, monkeypatch):
    s, event, target = registered
    before = capture(s)
    real_link = os.link
    failure = OSError(errno.EIO, 'Interrupted after link')
    def interrupted(stage, destination):
        real_link(stage, destination)
        raise failure
    with monkeypatch.context() as patch:
        patch.setattr(app_module.os, 'link', interrupted)
        with pytest.raises(OSError) as caught:
            s.materialize_timesheet_export(event['event_id'], target)
    assert caught.value is failure and 'not been verified' in failure.__notes__[0]
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    status = target.stat()
    assert s.materialize_timesheet_export(event['event_id'], target) == target
    assert target.stat().st_mtime_ns == status.st_mtime_ns
    assert not stages(target.parent) and capture(s) == before


@pytest.mark.parametrize('failure_kind', ['read', 'different-bytes', 'digest'])
def test_postpublication_verification_failure_never_deletes_or_returns_success(registered, monkeypatch, failure_kind):
    s, event, target = registered
    before = capture(s)
    real_link, real_open, real_sha = os.link, os.open, app_module.sha256
    published = []
    def link(stage, destination):
        real_link(stage, destination)
        published.append(True)
        if failure_kind == 'different-bytes':
            target.write_bytes(b'Changed by another process after publication')
    def read(path, flags, *args, **kwargs):
        if published and Path(path) == target and failure_kind == 'read':
            raise PermissionError('Postpublication read denied')
        return real_open(path, flags, *args, **kwargs)
    def digest(content):
        if published and failure_kind == 'digest':
            return SimpleNamespace(hexdigest=lambda: '0' * 64)
        return real_sha(content)
    monkeypatch.setattr(app_module.os, 'link', link)
    monkeypatch.setattr(app_module.os, 'open', read)
    monkeypatch.setattr(app_module, 'sha256', digest)
    with pytest.raises(OSError) as caught:
        s.materialize_timesheet_export(event['event_id'], target)
    assert 'published at' in caught.value.__notes__[0] and 'did not succeed' in caught.value.__notes__[0]
    assert target.exists() and not stages(target.parent) and capture(s) == before


@pytest.mark.parametrize('phase', ['before', 'after-unverified', 'after-verified'])
def test_cleanup_failure_preserves_original_error_or_reports_verified_output(registered, monkeypatch, phase):
    s, event, target = registered
    before = capture(s)
    failure = OSError(errno.EIO, 'Primary operation failed')
    cleanup = OSError(errno.EACCES, 'Staging unlink failed')
    real_unlink = Path.unlink
    def unlink(path, *args, **kwargs):
        assert path != target, 'Cleanup must never delete the destination'
        if path.name.startswith('.chronicle-'):
            raise cleanup
        return real_unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', unlink)
        if phase == 'before':
            patch.setattr(app_module.os, 'fsync', lambda _: (_ for _ in ()).throw(failure))
        elif phase == 'after-unverified':
            patch.setattr(s, '_verify_timesheet_export_file', lambda *_: (_ for _ in ()).throw(failure))
        with pytest.raises(OSError) as caught:
            s.materialize_timesheet_export(event['event_id'], target)
    assert len(stages(target.parent)) == 1
    if phase == 'after-verified':
        assert 'published and verified' in str(caught.value) and caught.value.__cause__ is cleanup
        assert Path(caught.value.filename) == stages(target.parent)[0]
        assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
        assert s.materialize_timesheet_export(event['event_id'], target) == target
    elif phase == 'before':
        assert caught.value is failure and 'cleanup failed' in failure.__notes__[-1]
        assert str(stages(target.parent)[0]) in failure.__notes__[-1]
        assert not target.exists()
    else:
        assert caught.value is failure
        assert 'verification did not succeed' in failure.__notes__[0]
        assert 'cleanup failed' in failure.__notes__[-1]
        assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert capture(s) == before


def test_existing_file_read_failure_is_not_reclassified_as_absence(registered, monkeypatch):
    s, event, target = registered
    expected = event['payload']['report_text'].encode('utf-8')
    target.write_bytes(expected)
    failure = FileNotFoundError('Injected verification read failure')
    before = capture(s)
    monkeypatch.setattr(s, '_verify_timesheet_export_file', lambda *_: (_ for _ in ()).throw(failure))
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', lambda **_: pytest.fail('Read failure reached staging'))
    with pytest.raises(FileNotFoundError) as caught:
        s.materialize_timesheet_export(event['event_id'], target)
    assert caught.value is failure and target.read_bytes() == expected and capture(s) == before


def test_changed_staging_ownership_is_retained_not_published_or_deleted(registered, monkeypatch):
    s, event, target = registered
    before = capture(s)
    real_lstat = Path.lstat
    def ambiguous(path):
        result = real_lstat(path)
        if path.name.startswith('.chronicle-'):
            return SimpleNamespace(st_dev=result.st_dev, st_ino=result.st_ino + 1, st_mode=result.st_mode)
        return result
    monkeypatch.setattr(Path, 'lstat', ambiguous)
    with pytest.raises(OSError, match='ownership is uncertain') as caught:
        s.materialize_timesheet_export(event['event_id'], target)
    assert not target.exists() and len(stages(target.parent)) == 1
    assert 'cleanup failed' in caught.value.__notes__[-1] and capture(s) == before


def test_replacement_before_verification_open_is_rejected_and_preserved(registered, monkeypatch):
    s, event, target = registered
    before = capture(s)
    replacement = target.with_name('independent.txt')
    replacement.write_bytes(b'Independent replacement')
    real_open = os.open
    def replaced(path, flags, *args, **kwargs):
        if Path(path) == target:
            replacement.replace(target)  # simulate a different process
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(app_module.os, 'open', replaced)
    with pytest.raises(OSError, match='changed before verification'):
        s.materialize_timesheet_export(event['event_id'], target)
    assert target.read_bytes() == b'Independent replacement'
    assert not stages(target.parent) and capture(s) == before


def test_postverification_cleanup_failure_never_deletes_concurrent_replacement(registered, monkeypatch):
    s, event, target = registered
    before = capture(s)
    real_unlink = Path.unlink
    failure = OSError('Cleanup failed after independent replacement')
    def cleanup(path, *args, **kwargs):
        assert path != target, 'Application cleanup targeted the final destination'
        if path.name.startswith('.chronicle-'):
            real_unlink(target)  # simulate replacement by a different process
            target.write_bytes(b'New independent destination')
            raise failure
        return real_unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', cleanup)
        with pytest.raises(OSError) as caught:
            s.materialize_timesheet_export(event['event_id'], target)
    assert caught.value.__cause__ is failure
    assert target.read_bytes() == b'New independent destination'
    assert len(stages(target.parent)) == 1 and capture(s) == before
    with pytest.raises(FileExistsError, match='conflicts'):
        s.materialize_timesheet_export(event['event_id'], target)


def test_later_changes_and_renderer_updates_cannot_change_frozen_file(registered, monkeypatch):
    s, event, target = registered
    task = event['payload']['tasks'][0]['task_id']
    owner = next(key for key, state in s.state.tasks.items() if state.dated_durations)
    entry = next(iter(s.state.tasks[owner].dated_durations))
    s._append(owner, 'dated_duration_corrected', {'entry_id': entry, 'work_date_local': TUE.isoformat(),
                                               'duration_seconds': 10800, 'reason': 'Correct work'})
    s.update_task(task, 'New name', '')
    project = s.create_project('New grouping')
    s.assign_task_to_project(task, project)
    s.rename_project(project, 'Renamed grouping')
    before = capture(s)
    def forbidden(*args, **kwargs):
        pytest.fail('Materialization recalculated or regenerated current work')
    monkeypatch.setattr(s, 'calculate_date_window', forbidden)
    monkeypatch.setattr(app_module, 'build_decimal_timesheet_text', forbidden)
    monkeypatch.setattr('task_timer.export_snapshots.build_decimal_timesheet_text', forbidden)
    monkeypatch.setattr('task_timer.exporter.build_decimal_timesheet_text', forbidden)
    monkeypatch.setattr(app_module, 'utc_now', forbidden)
    assert s.materialize_timesheet_export(event['event_id'], target) == target
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert capture(s) == before


def test_restart_rotation_and_backup_restore_remain_materializable(registered):
    s, event, target = registered
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    backup = s.create_backup_now()
    s.create_task('Later task', '')
    s.restore_from_backup(backup)
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert restarted.get_timesheet_export_snapshot(event['event_id']) == event
    before = capture(restarted)
    assert restarted.materialize_timesheet_export(event['event_id'], target) == target
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert capture(restarted) == before
