"""Actual staged service orchestration and guarded UTF-8 file output."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import errno

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


@pytest.mark.parametrize('destination', ['ordinary', 'events', 'manifest', 'snapshot', 'directory', 'symlink', 'dangling'])
def test_existing_destinations_are_never_overwritten(setup, tmp_path, destination):
    s, a, _, _, _, _ = setup
    target = {'events': s.storage.active_path, 'manifest': s.storage.manifest_path,
              'snapshot': s.storage.snapshot_path, 'directory': s.storage.data_dir}.get(destination, tmp_path / destination)
    if destination == 'ordinary':
        target.write_bytes(b'Existing report\x00')
    if destination in ('symlink', 'dangling'):
        target.symlink_to(s.storage.active_path if destination == 'symlink' else tmp_path / 'missing')
    before, bytes_before = capture(s), files(tmp_path)
    with pytest.raises(FileExistsError):
        save(s, target, task_ids=(a,))
    assert capture(s) == before and files(tmp_path) == bytes_before


@pytest.mark.parametrize('options', [
    {'start': TUE, 'end': MON}, {'start': '2026-10-11'}, {'end': datetime(2026, 10, 17)},
    {'cutoff_utc': datetime(2026, 10, 25)}, {'task_ids': ('unknown',)}, {'project_ids': ('unknown',)},
    {'task_ids': 'bad-selection'}, {'project_ids': None}, {'all_tasks': 1},
])
def test_accounting_failure_before_any_destination_open(setup, tmp_path, monkeypatch, options):
    s, _, _, _, _, _ = setup
    target = tmp_path / 'invalid.txt'
    arguments = {'start_date': options.get('start', SUN), 'end_date': options.get('end', SAT),
                 'cutoff_utc': options.get('cutoff_utc', CUTOFF),
                 **{key: value for key, value in options.items() if key not in ('start', 'end', 'cutoff_utc')}}
    before = capture(s)
    original_open = Path.open
    def guard(path, mode='r', *args, **kwargs):
        assert mode != 'x', 'An invalid request tried to open an output'
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guard)
    with pytest.raises(ValueError):
        s.save_date_range_timesheet(target, **arguments)
    assert not target.exists() and capture(s) == before


def test_unsupported_legacy_and_renderer_failure_never_create_output(setup, tmp_path, monkeypatch):
    s, a, _, _, _, _ = setup
    s.add_manual_duration(a, MON, 3600, 'Legacy synthetic')
    before = capture(s)
    target = tmp_path / 'unsupported.txt'
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
    original_open = Path.open
    def denied(path, mode='r', *args, **kwargs):
        if path == target and mode == 'x':
            raise PermissionError(errno.EACCES, 'Injected destination permission failure', str(path))
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', denied)
    with pytest.raises(PermissionError, match='permission failure'):
        save(s, target)
    assert not target.exists() and capture(s) == before


@pytest.mark.parametrize('phase', ['write', 'flush', 'close', 'fsync'])
def test_partial_output_removed_on_filesystem_failure(setup, tmp_path, monkeypatch, phase):
    s = setup[0]
    target = tmp_path / 'failed.txt'
    before = capture(s)
    original_open = Path.open
    class FailingOutput:
        def __init__(self, wrapped):
            self.wrapped = wrapped
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.wrapped.close()
            if phase == 'close':
                raise OSError(errno.EIO, 'Injected close failure')
        def fileno(self):
            return self.wrapped.fileno()
        def write(self, text):
            if phase == 'write':
                self.wrapped.write(text[:18])
                raise OSError(errno.ENOSPC, 'Injected write failure')
            return self.wrapped.write(text)
        def flush(self):
            self.wrapped.flush()
            if phase == 'flush':
                raise OSError(errno.EIO, 'Injected flush failure')
    def open_output(path, mode='r', *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        return FailingOutput(handle) if path == target and mode == 'x' else handle
    monkeypatch.setattr(Path, 'open', open_output)
    if phase == 'fsync':
        def failed_sync(fd):
            raise OSError(errno.EIO, 'Injected fsync failure')
        monkeypatch.setattr('task_timer.app.os.fsync', failed_sync)
    with pytest.raises(OSError, match=f'Injected {phase} failure'):
        save(s, target)
    assert not target.exists() and capture(s) == before


def test_cleanup_failure_retains_original_error_and_reports_incomplete_file(setup, tmp_path, monkeypatch):
    s = setup[0]
    target = tmp_path / 'cannot-clean.txt'
    before = capture(s)
    def failed_sync(fd):
        raise OSError(errno.EIO, 'Output sync failed')
    original_unlink = Path.unlink
    def denied_unlink(path, *args, **kwargs):
        if path == target:
            raise PermissionError(errno.EACCES, 'Cleanup denied')
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr('task_timer.app.os.fsync', failed_sync)
    monkeypatch.setattr(Path, 'unlink', denied_unlink)
    with pytest.raises(OSError, match='Output sync failed') as caught:
        save(s, target)
    assert any('Could not remove incomplete timesheet' in note and 'Cleanup denied' in note for note in caught.value.__notes__)
    assert target.exists()  # explicitly reported as a failure, never success
    assert capture(s) == before


def test_cleanup_does_not_remove_a_concurrent_replacement(setup, tmp_path, monkeypatch):
    s = setup[0]
    target = tmp_path / 'replaced.txt'
    before = capture(s)
    def replace_and_fail(fd):
        target.unlink()
        target.write_bytes(b'Independently replaced output')
        raise OSError(errno.EIO, 'Failure after replacement')
    monkeypatch.setattr('task_timer.app.os.fsync', replace_and_fail)
    with pytest.raises(OSError, match='Failure after replacement'):
        save(s, target)
    assert target.read_bytes() == b'Independently replaced output'
    assert capture(s) == before


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
