"""Actual staged service orchestration and guarded UTF-8 file output."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import errno
import os

from task_timer import app as app_module

import pytest

from task_timer.app import TaskTimerService
from task_timer.exporter import build_timesheet_text
from task_timer.storage import EventStorage

SUN, MON, TUE, SAT, NEXT = [date(2026, 10, day) for day in (11, 12, 13, 17, 18)]
CUTOFF = datetime(2026, 10, 25, 14, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    clock = [CUTOFF]
    monkeypatch.setattr('task_timer.app.utc_now', lambda: clock[0])
    monkeypatch.setattr('task_timer.app.detect_local_timezone', lambda: ZoneInfo('America/Chicago'))
    s = TaskTimerService(EventStorage(tmp_path / 'fresh'))
    p = s.create_project('P')
    q = s.create_project('Q')
    a = s.create_task('A', '', project_id=p)
    b = s.create_task('B', '', project_id=p)
    return s, a, b, p, q, clock


def local(s, day, hour=0, minute=0):
    return datetime.combine(day, datetime.min.time(), s.local_tz) + timedelta(hours=hour, minutes=minute)


def dated(s, task, day, seconds, entry=None, kind='dated_duration_added'):
    entry = entry or str(uuid4())
    s._append(task, kind, {'entry_id': entry, 'work_date_local': day.isoformat(),
                          'duration_seconds': seconds, 'reason': 'Declared work'})
    return entry


def example(s, a, b):
    s.add_manual_interval(a, local(s, MON, 9), local(s, MON, 10), 'Timed work')
    s.add_manual_interval(b, local(s, MON, 9), local(s, MON, 11), 'Timed work')
    dated(s, a, TUE, 5400)
    dated(s, b, TUE, 1800)


def generate(s, start=SUN, end=SAT, **options):
    return s.generate_date_range_timesheet(start, end, cutoff_utc=CUTOFF, **options)


def save(s, target, start=SUN, end=SAT, **options):
    return s.save_date_range_timesheet(target, start, end, cutoff_utc=CUTOFF, **options)


def rows(text, name):
    logical, physical = [], []
    for line in text.splitlines():
        if line.startswith('|'):
            physical.append([part[1:-1] for part in line.split('|')[1:-1]])
        elif physical:
            logical.append([''.join(part[index].rstrip() for part in physical) for index in range(len(physical[0]))])
            physical = []
    assert not physical
    return [row for row in logical if row[0] == name]


def files(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*') if path.is_file()}


def capture(s):
    return (deepcopy(s.state), deepcopy(s.events), files(s.storage.data_dir),
            deepcopy(s.list_time_submissions()),
            {key: s.task_elapsed(task, CUTOFF) for key, task in s.state.tasks.items()})


def test_complete_weekly_report_has_independent_exact_values(setup):
    s, a, b, _, _, _ = setup
    example(s, a, b)
    before = capture(s)
    text = generate(s, all_tasks=True)
    assert rows(text, 'A')[0][3:] == ['00:00:00', '01:00:00', '01:30:00'] + ['00:00:00'] * 4 + ['02:30:00']
    assert rows(text, 'B')[0][3:] == ['00:00:00', '02:00:00', '00:30:00'] + ['00:00:00'] * 4 + ['02:30:00']
    subtotal = rows(text, 'Project total — informational')[0]
    assert subtotal[4:6] == ['03:00:00', '02:00:00']
    assert subtotal[-1] == rows(text, 'Application total')[0][-1] == '05:00:00'
    assert len(rows(text, 'A')) == len(rows(text, 'B')) == 1
    assert 'Scope: Complete eligible-task scope' in text
    assert 'Local timezone: America/Chicago' in text
    assert text == build_timesheet_text(s.calculate_date_window(SUN, SAT, cutoff_utc=CUTOFF, all_tasks=True))
    assert capture(s) == before


@pytest.mark.parametrize('selection', ['task', 'project', 'combined', 'tasks', 'empty'])
def test_selection_is_forwarded_without_expansion_or_duplicates(setup, selection):
    s, a, b, p, _, _ = setup
    example(s, a, b)
    options = {'task': {'task_ids': (a,)}, 'project': {'project_ids': (p,)},
               'combined': {'project_ids': (p,), 'task_ids': (a,)},
               'tasks': {'task_ids': (a, b)}, 'empty': {'task_ids': (), 'project_ids': ()}}[selection]
    before = capture(s)
    text = generate(s, **options)
    assert rows(text, 'Selected-scope total')[0][-1] == {'task': '02:30:00', 'empty': '00:00:00'}.get(selection, '05:00:00')
    assert len(rows(text, 'A')) == int(selection != 'empty')
    assert len(rows(text, 'B')) == int(selection not in ('task', 'empty'))
    if selection == 'task':
        assert rows(text, 'Selected tasks subtotal — informational')[0][-1] == '02:30:00'
    elif selection != 'empty':
        assert rows(text, 'Project total — informational')[0][-1] == '05:00:00'
    assert capture(s) == before


def test_multiple_projects_unassigned_and_deleted_history(setup):
    s, a, b, p, q, _ = setup
    example(s, a, b)
    s.assign_task_to_project(b, q)
    u = s.create_task('Unassigned work', '')
    dated(s, u, MON, 1800)
    s.delete_task_only(b)
    text = generate(s, project_ids=(p, q))
    assert not rows(text, 'B') and not rows(text, 'Unassigned work')
    historical = generate(s, project_ids=(p, q), include_unassigned=True, include_deleted=True)
    assert historical.index('Project: P') < historical.index('| A ') < historical.index('Project: Q') < historical.index('| B ')
    assert rows(historical, 'B')[0][1] == 'Inactive (deleted)'
    assert rows(historical, 'Unassigned work')[0][-1] == '00:30:00'
    assert rows(historical, 'Selected-scope total')[0][-1] == '05:30:00'


def test_empty_complete_report(tmp_path):
    s = TaskTimerService(EventStorage(tmp_path / 'empty'))
    before = capture(s)
    text = generate(s, all_tasks=True)
    assert 'Scope: Complete eligible-task scope' in text
    assert 'No tasks included in this scope.' in text
    assert rows(text, 'Application total')[0][3:] == ['00:00:00'] * 8
    assert capture(s) == before


def test_midnight_and_sunday_clipping_with_whole_dated_amount(setup):
    s, a, b, _, _, _ = setup
    s.add_manual_interval(a, local(s, SAT, 23, 30), local(s, NEXT, 1, 30), 'Cross week')
    dated(s, b, SAT, 50400)
    text = generate(s, SAT, NEXT, all_tasks=True)
    assert [row[-1] for row in rows(text, 'A')] == ['00:30:00', '01:30:00']
    assert [row[-1] for row in rows(text, 'B')] == ['14:00:00', '00:00:00']
    assert rows(text, 'A')[0][3:] == ['out of scope'] * 6 + ['00:30:00', '00:30:00']
    assert rows(text, 'A')[1][3:] == ['01:30:00'] + ['out of scope'] * 6 + ['01:30:00']
    only_sunday = generate(s, NEXT, NEXT, all_tasks=True)
    assert rows(only_sunday, 'Application total')[0][-1] == '01:30:00'
    assert s.state.tasks[b].intervals == {}


def test_effective_corrections_and_deletions_not_previous_versions(setup):
    s, a, b, _, _, _ = setup
    s.add_manual_interval(a, local(s, MON, 9), local(s, MON, 10), 'Real')
    old = next(iter(s.state.tasks[a].intervals))
    s.edit_interval(a, old, local(s, MON, 9), local(s, MON, 10, 30), 'Correct')
    entry = dated(s, b, MON, 7200)
    dated(s, b, TUE, 10800, entry, 'dated_duration_corrected')
    original_events = deepcopy(s.events)
    text = generate(s, all_tasks=True)
    assert rows(text, 'A')[0][-1] == '01:30:00'
    assert rows(text, 'B')[0][4:6] == ['00:00:00', '03:00:00']
    assert rows(text, 'Application total')[0][-1] == '04:30:00'
    s.delete_interval(a, next(reversed(s.state.tasks[a].intervals)), 'Void')
    s._append(b, 'dated_duration_deleted', {'entry_id': entry, 'reason': 'Void'})
    assert rows(generate(s, all_tasks=True), 'Application total')[0][-1] == '00:00:00'
    assert s.events[:len(original_events)] == original_events


def test_running_fixed_cutoff_never_interrupts_timer(setup, tmp_path):
    s, a, _, _, _, clock = setup
    clock[0] = local(s, MON, 9).astimezone(timezone.utc)
    s.start_task(a)
    cutoff = local(s, MON, 10).astimezone(timezone.utc)
    before = capture(s)
    text = s.generate_date_range_timesheet(MON, MON, cutoff_utc=cutoff, task_ids=(a,))
    assert rows(text, 'A')[0][-1] == '01:00:00'
    assert text == s.generate_date_range_timesheet(MON, MON, cutoff_utc=cutoff, task_ids=(a,))
    target = tmp_path / 'running.txt'
    assert s.save_date_range_timesheet(target, MON, MON, cutoff_utc=cutoff, task_ids=(a,)) == text
    assert s.state.running_task_id == a and s.state.tasks[a].is_running
    assert capture(s) == before


def test_submissions_checkpoints_and_resets_are_independent(setup, tmp_path, monkeypatch):
    s, a, b, _, _, clock = setup
    example(s, a, b)
    clock[0] = local(s, MON, 11).astimezone(timezone.utc)
    s.reset_task(a)
    clock[0] = CUTOFF
    s.create_time_submission_marker([a, b], None, CUTOFF, 'Legacy evidence', None)
    expected = generate(s, all_tasks=True)
    s._append('__app__', 'export_checkpoint', {'path': 'legacy.txt', 'generated_at_utc': '2026-10-25T14:00:00Z', 'reset_after': False})
    before = capture(s)
    def forbidden(*args, **kwargs):
        pytest.fail('New date-range workflow invoked a legacy or mutating operation')
    for name in ('_aggregate_parent_rows', 'export_report', 'export_selected_tasks_report',
                 'find_last_export_checkpoint_utc', '_append', '_save_snapshot', '_create_risky_operation_backup'):
        monkeypatch.setattr(s, name, forbidden)
    assert generate(s, all_tasks=True) == expected
    assert save(s, tmp_path / 'actual.txt', all_tasks=True) == expected
    assert rows(expected, 'Application total')[0][-1] == '05:00:00'
    assert 'submitted' not in expected.lower()
    assert capture(s) == before


def test_exact_unicode_utf8_saving_only_changes_requested_output(setup, tmp_path):
    s, a, _, _, _, _ = setup
    s.update_task(a, 'Café 管理\u202e descriptive management task ' * 4 + 'end', '')
    dated(s, a, MON, 12600.25)
    expected = generate(s, task_ids=(a,))
    state_before, files_before = capture(s), files(tmp_path)
    target = tmp_path / 'timesheet.txt'
    assert save(s, str(target), task_ids=(a,)) == expected
    assert target.read_bytes() == expected.encode('utf-8')
    assert target.read_bytes().endswith(b'\n') and b'\r\n' not in target.read_bytes()
    assert '\u202e' not in expected and r'\u202e' in expected
    assert rows(expected, 'Selected-scope total')[0][-1] == '03:30:00.25'
    assert capture(s) == state_before
    assert files(tmp_path) == {**files_before, 'timesheet.txt': expected.encode('utf-8')}


@pytest.mark.parametrize('destination', ['ordinary', 'events', 'manifest', 'snapshot', 'backup', 'directory', 'symlink', 'dangling'])
def test_existing_destinations_are_never_overwritten(setup, tmp_path, destination):
    s, a, _, _, _, _ = setup
    target = {'events': s.storage.active_path, 'manifest': s.storage.manifest_path,
              'snapshot': s.storage.snapshot_path, 'directory': s.storage.data_dir}.get(destination, tmp_path / destination)
    if destination == 'backup':
        target = s.create_backup_now('Existing backup protection')
    if destination == 'ordinary':
        target.write_bytes(b'Existing report\x00')
    if destination in ('symlink', 'dangling'):
        target.symlink_to(s.storage.active_path if destination == 'symlink' else tmp_path / 'missing')
    before, bytes_before = capture(s), files(tmp_path)
    with pytest.raises(FileExistsError):
        save(s, target, task_ids=(a,))
    assert capture(s) == before and files(tmp_path) == bytes_before
    assert not staging_files(target.parent)
    if destination in ('symlink', 'dangling'):
        assert target.is_symlink()


@pytest.mark.parametrize('options', [
    {'start': TUE, 'end': MON}, {'start': '2026-10-11'}, {'end': datetime(2026, 10, 17)},
    {'cutoff_utc': datetime(2026, 10, 25)}, {'task_ids': ('unknown',)}, {'project_ids': ('unknown',)},
    {'task_ids': 'bad-selection'}, {'project_ids': None}, {'all_tasks': 1},
])
def test_accounting_failure_before_staging_or_publication(setup, tmp_path, monkeypatch, options):
    s, _, _, _, _, _ = setup
    target = tmp_path / 'invalid.txt'
    arguments = {'start_date': options.get('start', SUN), 'end_date': options.get('end', SAT),
                 'cutoff_utc': options.get('cutoff_utc', CUTOFF),
                 **{key: value for key, value in options.items() if key not in ('start', 'end', 'cutoff_utc')}}
    before = capture(s)
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid accounting request reached filesystem staging/publication')
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', forbidden)
    monkeypatch.setattr(app_module.os, 'link', forbidden)
    with pytest.raises(ValueError):
        s.save_date_range_timesheet(target, **arguments)
    assert not target.exists() and capture(s) == before


def test_unsupported_legacy_and_renderer_failure_never_create_output(setup, tmp_path, monkeypatch):
    s, a, _, _, _, _ = setup
    s.add_manual_duration(a, MON, 3600, 'Legacy synthetic')
    before = capture(s)
    target = tmp_path / 'unsupported.txt'
    def forbidden(*args, **kwargs):
        pytest.fail('Calculation/rendering failure reached staging or publication')
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', forbidden)
    monkeypatch.setattr(app_module.os, 'link', forbidden)
    with pytest.raises(ValueError, match='Legacy synthetic duration'):
        save(s, target, task_ids=(a,))
    assert not target.exists() and capture(s) == before
    def invalid_render(report):
        raise ValueError('Renderer failure')
    monkeypatch.setattr('task_timer.app.build_timesheet_text', invalid_render)
    with pytest.raises(ValueError, match='Renderer failure'):
        save(s, target)  # empty selection is valid accounting, rendering fails
    assert not target.exists() and capture(s) == before


@pytest.mark.parametrize('destination', ['', None, 42, 'bad\x00path'])
def test_invalid_destination_types_and_names(setup, destination):
    before = capture(setup[0])
    with pytest.raises(ValueError):
        save(setup[0], destination)
    assert capture(setup[0]) == before


def test_missing_parent_and_permission_errors_propagate(setup, tmp_path, monkeypatch):
    s = setup[0]
    before = capture(s)
    with pytest.raises(FileNotFoundError):
        save(s, tmp_path / 'absent-directory' / 'out.txt')
    assert not (tmp_path / 'absent-directory').exists()
    target = tmp_path / 'denied.txt'
    def denied(*args, **kwargs):
        raise PermissionError(errno.EACCES, 'Injected staging permission failure', str(target.parent))
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', denied)
    with pytest.raises(PermissionError, match='permission failure'):
        save(s, target)
    assert not target.exists() and capture(s) == before


def test_separate_empty_installation_does_not_import_or_modify_unrelated_data(setup, tmp_path, monkeypatch):
    old_home = tmp_path / 'old-home'
    old = TaskTimerService(EventStorage(old_home / '.task_timer_data'))
    a = old.create_task('Historical task', '')
    dated(old, a, MON, 12600)
    original = files(old.storage.data_dir)
    # Existing old-home data is unrelated to this explicitly supplied dataset.
    monkeypatch.setattr(Path, 'home', lambda: old_home)
    fresh = TaskTimerService(EventStorage(tmp_path / 'new-installation'))
    fresh.local_tz = ZoneInfo('UTC')
    fresh.local_tz_name = 'stale display label'
    before = capture(fresh)
    text = save(fresh, tmp_path / 'fresh.txt', all_tasks=True)
    assert 'Scope: Complete eligible-task scope' in text
    assert 'Local timezone: UTC' in text
    assert rows(text, 'Application total')[0][-1] == '00:00:00'
    assert fresh.events == [] and fresh.state.tasks == fresh.state.projects == {}
    assert capture(fresh) == before
    assert files(old.storage.data_dir) == original


def staging_files(parent):
    return list(parent.glob('.chronicle-*.tmp'))


def staged_writer(monkeypatch, callback):
    """Instrument real staging streams without opening the final destination."""
    original = os.fdopen
    class Stream:
        def __init__(self, wrapped):
            self.wrapped = wrapped
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            try:
                self.wrapped.close()
            except BaseException as close_error:
                if exc is None:
                    raise
                exc.add_note(f'Secondary close error: {close_error}')
            if exc is None:
                callback('close', self.wrapped, None)
        def write(self, text):
            return callback('write', self.wrapped, text)
        def flush(self):
            return callback('flush', self.wrapped, None)
        def fileno(self):
            return self.wrapped.fileno()
    def wrap(fd, *args, **kwargs):
        return Stream(original(fd, *args, **kwargs))
    monkeypatch.setattr(app_module.os, 'fdopen', wrap)


def test_incomplete_staging_never_appears_at_final_destination(setup, tmp_path, monkeypatch):
    s, a, b, _, _, _ = setup
    example(s, a, b)
    target = tmp_path / 'complete.txt'
    expected = generate(s, all_tasks=True)
    before = capture(s)
    sequence = []
    def staging_operation(phase, wrapped, text):
        assert not target.exists()
        stages = staging_files(tmp_path)
        assert len(stages) == 1 and stages[0].parent == target.parent
        if phase == 'write':
            sequence.append('partial write')
            wrapped.write(text[:18])
            wrapped.flush()
            assert stages[0].read_bytes() == text[:18].encode('utf-8')
            assert not target.exists()
            wrapped.write(text[18:])
            return len(text)
        if phase == 'flush':
            sequence.append('flush')
            return wrapped.flush()
        sequence.append('close')
        assert wrapped.closed
    staged_writer(monkeypatch, staging_operation)
    real_link, real_sync, real_open = os.link, os.fsync, Path.open
    def synced(fd):
        sequence.append('fsync')
        assert not target.exists()
        return real_sync(fd)
    def publish(stage, destination):
        assert sequence == ['partial write', 'flush', 'fsync', 'close']
        assert Path(stage).read_bytes() == expected.encode('utf-8')
        if os.name == 'posix':
            assert Path(stage).stat().st_mode & 0o777 == 0o600
        sequence.append('link')
        return real_link(stage, destination)
    def forbid_final_writes(path, mode='r', *args, **kwargs):
        if path == target:
            assert not any(flag in mode for flag in 'wax+')
        return real_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(app_module.os, 'fsync', synced)
    monkeypatch.setattr(app_module.os, 'link', publish)
    monkeypatch.setattr(Path, 'open', forbid_final_writes)
    assert save(s, target, all_tasks=True) == expected
    assert target.read_bytes() == expected.encode('utf-8')
    assert target.read_bytes().endswith(b'\n') and b'\r\n' not in target.read_bytes()
    assert not staging_files(tmp_path) and capture(s) == before


@pytest.mark.parametrize('phase', ['write', 'flush', 'fsync', 'close'])
def test_staging_failure_removes_only_staging_and_preserves_original_error(setup, tmp_path, monkeypatch, phase):
    s = setup[0]
    target = tmp_path / 'failed.txt'
    before = capture(s)
    failure = OSError(errno.EIO, f'Injected {phase} failure')
    def staging_operation(operation, wrapped, text):
        assert not target.exists()
        if operation == 'write':
            if phase == 'write':
                wrapped.write(text[:18])
                wrapped.flush()
                raise failure
            return wrapped.write(text)
        if operation == 'flush':
            wrapped.flush()
        if operation == phase:
            raise failure
    staged_writer(monkeypatch, staging_operation)
    if phase == 'fsync':
        def failed_sync(fd):
            assert not target.exists()
            raise failure
        monkeypatch.setattr(app_module.os, 'fsync', failed_sync)
    def forbidden_publication(*args, **kwargs):
        pytest.fail('Failed staging was published')
    monkeypatch.setattr(app_module.os, 'link', forbidden_publication)
    with pytest.raises(OSError) as caught:
        save(s, target)
    assert caught.value is failure
    assert not target.exists() and not staging_files(tmp_path)
    assert capture(s) == before


@pytest.mark.parametrize('error_code', [errno.EIO, errno.EACCES, errno.ENOTSUP])
def test_publication_failure_or_unsupported_operation_fails_closed(setup, tmp_path, monkeypatch, error_code):
    s = setup[0]
    target = tmp_path / 'unsupported.txt'
    before = capture(s)
    failure = OSError(error_code, 'No-clobber publication failed')
    expected = generate(s)
    def failed_link(stage, destination):
        assert Path(stage).read_bytes() == expected.encode('utf-8')
        assert not target.exists()
        raise failure
    monkeypatch.setattr(app_module.os, 'link', failed_link)
    with pytest.raises(OSError) as caught:
        save(s, target)
    assert caught.value is failure
    assert not target.exists() and not staging_files(tmp_path)
    assert capture(s) == before


def test_concurrent_creation_at_publication_survives(setup, tmp_path, monkeypatch):
    s = setup[0]
    target = tmp_path / 'concurrent.txt'
    before = capture(s)
    real_link = os.link
    def concurrent_link(stage, destination):
        assert Path(stage).read_bytes() == generate(s).encode('utf-8')
        target.write_bytes(b'Independent concurrent report')
        return real_link(stage, destination)
    monkeypatch.setattr(app_module.os, 'link', concurrent_link)
    with pytest.raises(FileExistsError):
        save(s, target)
    assert target.read_bytes() == b'Independent concurrent report'
    assert not staging_files(tmp_path) and capture(s) == before


def test_original_check_then_delete_race_cannot_delete_replacement(setup, tmp_path, monkeypatch):
    s = setup[0]
    target = tmp_path / 'race.txt'
    before = capture(s)
    real_lstat, real_unlink, real_os_unlink = Path.lstat, Path.unlink, os.unlink
    observed, inspected = [], []
    failure = OSError(errno.EIO, 'Failed staging sync triggers cleanup')
    def fail_after_concurrent_creation(fd):
        target.write_bytes(b'Original destination identity to be observed')
        raise failure
    def replace_at_cleanup_observation(path):
        inspected.append(path)
        status = real_lstat(path)
        if path == target or path.name.startswith('.chronicle-'):
            # Reproduce the original observation->replacement window while
            # actual failed-write cleanup is about to delete a pathname.
            # Old destination cleanup would return the original target stat,
            # see a matching identity, then try to delete its replacement.
            observed.append(real_lstat(target))
            real_os_unlink(target)
            target.write_bytes(b'Replacement at former vulnerable point')
        return status
    def cleanup(path, *args, **kwargs):
        assert path != target, 'Application tried to delete the final destination'
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', replace_at_cleanup_observation)
    monkeypatch.setattr(Path, 'unlink', cleanup)
    monkeypatch.setattr(app_module.os, 'fsync', fail_after_concurrent_creation)
    with pytest.raises(OSError) as caught:
        save(s, target)
    assert caught.value is failure
    assert observed and target not in inspected
    assert target.read_bytes() == b'Replacement at former vulnerable point'
    assert not staging_files(tmp_path) and capture(s) == before


@pytest.mark.parametrize('failure_phase', ['write', 'publication'])
def test_cleanup_failure_before_publication_preserves_original_error(setup, tmp_path, monkeypatch, failure_phase):
    s = setup[0]
    target = tmp_path / 'never-published.txt'
    before = capture(s)
    failure = OSError(errno.EIO, 'Original operation failed')
    if failure_phase == 'write':
        def failed_write(operation, wrapped, text):
            if operation == 'write':
                wrapped.write(text[:18])
                raise failure
            if operation == 'flush':
                wrapped.flush()
        staged_writer(monkeypatch, failed_write)
    else:
        def failed_link(*args, **kwargs):
            raise failure
        monkeypatch.setattr(app_module.os, 'link', failed_link)
    def denied_cleanup(path, *args, **kwargs):
        assert path != target
        raise PermissionError(errno.EACCES, 'Staging cleanup denied', str(path))
    monkeypatch.setattr(Path, 'unlink', denied_cleanup)
    with pytest.raises(OSError) as caught:
        save(s, target)
    assert caught.value is failure
    stages = staging_files(tmp_path)
    assert len(stages) == 1 and not target.exists()
    assert any(str(stages[0]) in note and 'Staging cleanup denied' in note for note in failure.__notes__)
    assert capture(s) == before


def test_cleanup_failure_after_publication_reports_successful_output(setup, tmp_path, monkeypatch):
    s = setup[0]
    target = tmp_path / 'published.txt'
    expected = generate(s)
    before = capture(s)
    def denied_cleanup(path, *args, **kwargs):
        assert path != target
        raise PermissionError(errno.EACCES, 'Staging cleanup denied', str(path))
    monkeypatch.setattr(Path, 'unlink', denied_cleanup)
    with pytest.raises(OSError, match='Complete timesheet published at') as caught:
        save(s, target)
    stages = staging_files(tmp_path)
    assert len(stages) == 1
    assert caught.value.filename == str(stages[0])
    assert isinstance(caught.value.__cause__, PermissionError)
    assert target.read_bytes() == stages[0].read_bytes() == expected.encode('utf-8')
    assert capture(s) == before


def test_postpublication_replacement_is_never_deleted(setup, tmp_path, monkeypatch):
    s = setup[0]
    target = tmp_path / 'replaced-after-publication.txt'
    real_unlink = os.unlink
    before = capture(s)
    def replaced_during_cleanup(path, *args, **kwargs):
        assert path != target
        assert target.read_bytes() == generate(s).encode('utf-8')
        real_unlink(target)
        target.write_bytes(b'Independent postpublication replacement')
        raise PermissionError(errno.EACCES, 'Postpublication cleanup failed')
    monkeypatch.setattr(Path, 'unlink', replaced_during_cleanup)
    with pytest.raises(OSError, match='Complete timesheet published at'):
        save(s, target)
    assert target.read_bytes() == b'Independent postpublication replacement'
    assert len(staging_files(tmp_path)) == 1 and capture(s) == before


def test_ambiguous_staging_replacement_is_retained(setup, tmp_path, monkeypatch):
    s = setup[0]
    target = tmp_path / 'ambiguous.txt'
    real_link = os.link
    def replace_staging_after_link(stage, destination):
        real_link(stage, destination)  # final retains the original inode
        os.unlink(stage)
        Path(stage).write_bytes(b'Unrelated replacement at staging pathname')
    monkeypatch.setattr(app_module.os, 'link', replace_staging_after_link)
    with pytest.raises(OSError, match='Staging ownership is uncertain'):
        save(s, target)
    stages = staging_files(tmp_path)
    assert len(stages) == 1 and stages[0].read_bytes() == b'Unrelated replacement at staging pathname'
    assert target.read_bytes() == generate(s).encode('utf-8')


def test_second_publication_refuses_existing_complete_report(setup, tmp_path):
    s = setup[0]
    target = tmp_path / 'once.txt'
    expected = save(s, target)
    before = capture(s)
    with pytest.raises(FileExistsError):
        save(s, target)
    assert target.read_bytes() == expected.encode('utf-8')
    assert not staging_files(tmp_path) and capture(s) == before


def test_staging_name_cannot_be_the_requested_destination(setup, tmp_path):
    # Even a temporary-looking caller path is only created by publication.
    target = tmp_path / '.CHRONICLE-TIMESHEET-caller.tmp'
    expected = save(setup[0], target)
    assert target.read_bytes() == expected.encode('utf-8')
    assert [path for path in staging_files(tmp_path) if path != target] == []


def test_fdopen_failure_closes_descriptor_and_cleans_staging(setup, tmp_path, monkeypatch):
    target = tmp_path / 'no-stream.txt'
    failure = OSError(errno.EIO, 'Staging stream creation failed')
    descriptors = []
    def failed_open(fd, *args, **kwargs):
        descriptors.append(fd)
        raise failure
    monkeypatch.setattr(app_module.os, 'fdopen', failed_open)
    with pytest.raises(OSError) as caught:
        save(setup[0], target)
    assert caught.value is failure
    assert not target.exists() and not staging_files(tmp_path)
    with pytest.raises(OSError) as closed:
        os.fstat(descriptors[0])
    assert closed.value.errno == errno.EBADF


def test_detected_staging_replacement_before_publication_is_retained(setup, tmp_path, monkeypatch):
    target = tmp_path / 'must-not-publish-foreign-data.txt'
    moved = tmp_path / 'externally-moved-stage'
    real_lstat = Path.lstat
    intercepted = []
    def replace_before_check(path):
        if path.name.startswith('.chronicle-') and not intercepted:
            intercepted.append(path)
            path.rename(moved)  # keep original inode alive, preventing reuse
            path.write_bytes(b'Foreign staging replacement')
        return real_lstat(path)
    def forbidden_link(*args, **kwargs):
        pytest.fail('Detected foreign staging replacement was published')
    monkeypatch.setattr(Path, 'lstat', replace_before_check)
    monkeypatch.setattr(app_module.os, 'link', forbidden_link)
    with pytest.raises(OSError, match='Staging ownership is uncertain') as caught:
        save(setup[0], target)
    assert not target.exists()
    assert intercepted[0].read_bytes() == b'Foreign staging replacement'
    assert any('Staging cleanup failed' in note for note in caught.value.__notes__)


def test_saving_preserves_running_state_submissions_backups_and_prior_outputs(setup, tmp_path):
    s, a, b, _, _, clock = setup
    example(s, a, b)
    s.create_time_submission_marker([a, b], None, CUTOFF, 'Prior evidence', None)
    s.create_backup_now('Prior backup')
    clock[0] = local(s, MON, 9).astimezone(timezone.utc)
    s.start_task(a)
    prior = tmp_path / 'prior.txt'
    prior.write_bytes(b'Existing output sentinel')
    expected = generate(s, task_ids=(a,))
    before = capture(s), files(tmp_path)
    target = tmp_path / 'new.txt'
    assert save(s, target, task_ids=(a,)) == expected
    assert capture(s) == before[0]
    assert files(tmp_path) == {**before[1], 'new.txt': expected.encode('utf-8')}
    assert s.state.running_task_id == a
    assert not staging_files(tmp_path)
