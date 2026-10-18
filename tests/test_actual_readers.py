"""Coordinated production Actual readers; isolated services and separate Tk input."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import tkinter as tk

import pytest

from task_timer import app as app_module
from task_timer.mini_mode import MiniModeWindow
from task_timer.settings import UISettings
from test_mixed_accounting import setup, dated, local, files
from test_work_history import interval, capture
from test_history_window import tk_root, pointer

UTC = timezone.utc
TODAY = date(2026, 10, 20)


class Var:
    def __init__(self): self.value = ''
    def set(self, value): self.value = value
    def get(self): return self.value


class Widget:
    def __init__(self): self.config, self.states = {}, []
    def configure(self, **kw): self.config.update(kw)
    def state(self, values): self.states = values


class Tree:
    def __init__(self, service):
        self.rows = {key: dict(today='—', week='—', state='■ Stopped')
                     for key, task in service.state.tasks.items() if not task.is_deleted}
        self.service = service
        self.writes = []
    def exists(self, key): return key in self.rows
    def set(self, key, column, value=None):
        if value is not None:
            self.rows[key][column] = value
            self.writes.append((key, column, value))
        return self.rows[key][column]
    def parent(self, key): return self.service.state.tasks[key].parent_task_id or ''
    def item(self, *args, **kw): pass


def make_mini(service):
    mini = MiniModeWindow.__new__(MiniModeWindow)
    mini.service = service
    mini.window = SimpleNamespace(winfo_exists=lambda: True)
    mini.task_name_var, mini.elapsed_var, mini.time_totals_error_var = Var(), Var(), Var()
    mini.toggle_btn, mini.elapsed_bar_label = Widget(), Widget()
    return mini


def make_owner(service):
    owner = app_module.TaskTimerApp.__new__(app_module.TaskTimerApp)
    owner.service, owner.task_tree = service, Tree(service)
    owner.daily_var, owner.weekly_var, owner.time_totals_error_var = Var(), Var(), Var()
    owner.ui_settings, owner.expanded_parents = UISettings(), set()
    reports, jobs = [], []
    owner.root = SimpleNamespace(report_callback_exception=lambda *a: reports.append(a),
                                 winfo_exists=lambda: True, after=lambda *a: jobs.append(a))
    owner.mini_mode_window = make_mini(service)
    owner.mini_mode_window.refresh_callback = owner.refresh_live_values
    return owner, reports, jobs


def observe(service, monkeypatch):
    calls, reports = [], []
    calculate = service.calculate_date_window
    def calculate_once(*args, **kw):
        result = calculate(*args, **kw)
        calls.append((args, kw))
        reports.append(deepcopy(result))
        return result
    monkeypatch.setattr(service, 'calculate_date_window', calculate_once)
    return calls, reports


def pure_refresh(owner, monkeypatch):
    s = owner.service
    before = capture(s)
    def forbidden(*a, **kw): pytest.fail('Actual refresh attempted domain or settings I/O')
    with monkeypatch.context() as m:
        for name in ('append_event', 'save_snapshot', 'iter_all_events', 'synchronize_journal'):
            m.setattr(s.storage, name, forbidden)
        for name in ('_append', '_save_snapshot', '_rebuild_state', 'create_backup_now'):
            m.setattr(s, name, forbidden)
        m.setattr(s.backups, 'create_backup', forbidden)
        m.setattr(app_module.UISettingsStore, 'save', forbidden)
        owner.refresh_live_values()
    assert capture(s) == before


def test_mixed_own_rows_deleted_application_future_dated_and_one_observation(setup, monkeypatch):
    s, a, b, _, _, clock = setup
    child = s.create_subtask(a, 'Child', '')
    interval(s, a, local(s, TODAY, 8), local(s, TODAY, 10))
    dated(s, a, TODAY, 119.9)
    dated(s, a, date(2026, 10, 24), 50400.125)
    dated(s, child, TODAY, 7200)
    dated(s, b, TODAY, 1800)
    s.delete_task_only(b)
    s.start_task(a)  # Start equals observation; it adds no elapsed amount.
    owner, errors, _ = make_owner(s)
    calls, reports = observe(s, monkeypatch)
    clocks, handoffs = [], []
    monkeypatch.setattr(app_module, 'utc_now', lambda: clocks.append(clock[0]) or clock[0])
    refresh_mini = owner.mini_mode_window.refresh_live_values
    def handoff(**kw):
        handoffs.append(deepcopy(kw['today_seconds_by_task']))
        refresh_mini(**kw)
    monkeypatch.setattr(owner.mini_mode_window, 'refresh_live_values', handoff)
    pure_refresh(owner, monkeypatch)
    assert calls == [((date(2026, 10, 18), date(2026, 10, 24)),
                     dict(cutoff_utc=clock[0], all_tasks=True, include_deleted=True))]
    assert clocks == [clock[0]] and len(handoffs) == 1 and errors == []
    assert handoffs[0][a] == 3719.9 and handoffs[0][b] == 1800
    assert reports[0]['tasks'][a]['window_seconds'] == pytest.approx(54120.025)
    assert owner.task_tree.rows[a]['today'] == '01:01'
    assert owner.task_tree.rows[a]['week'] == '15:02'
    assert owner.task_tree.rows[child]['today'] == '02:00' and b not in owner.task_tree.rows
    assert owner.daily_var.get() == 'Today: 03:31'
    assert owner.weekly_var.get() == 'This week: 17:32'
    assert owner.mini_mode_window.elapsed_var.get() == 'Today: 01:01'
    assert owner.time_totals_error_var.get() == owner.mini_mode_window.time_totals_error_var.get() == ''


@pytest.mark.parametrize('day,hours', [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_dst_full_local_day_and_calendar_week(setup, monkeypatch, day, hours):
    s, a, *_ = setup
    first, last = local(s, day), local(s, day + timedelta(days=1))
    interval(s, a, first.astimezone(UTC), last.astimezone(UTC))
    clock = last.astimezone(UTC) - timedelta(seconds=1)
    monkeypatch.setattr(app_module, 'utc_now', lambda: clock)
    owner, errors, _ = make_owner(s)
    calls, reports = observe(s, monkeypatch)
    pure_refresh(owner, monkeypatch)
    assert calls[0][0] == (day, day + timedelta(days=6))
    assert reports[0]['tasks'][a]['window_seconds'] == hours * 3600 - 1
    assert owner.task_tree.rows[a]['today'] == f'{hours-1:02}:59' and errors == []


def test_local_midnight_week_rollover_and_running_cutoff(setup, monkeypatch):
    s, a, _, _, _, clock = setup
    saturday = date(2026, 10, 24)
    clock[0] = local(s, saturday, 23, 30).astimezone(UTC)
    s.start_task(a)
    owner, errors, _ = make_owner(s)
    calls, _ = observe(s, monkeypatch)
    clock[0] = local(s, saturday, 23, 59).astimezone(UTC)  # Already Sunday in UTC.
    pure_refresh(owner, monkeypatch)
    assert owner.task_tree.rows[a]['today'] == owner.task_tree.rows[a]['week'] == '00:29'
    assert calls[-1][0] == (date(2026, 10, 18), saturday)
    clock[0] = local(s, saturday + timedelta(days=1), 0, 1).astimezone(UTC)
    pure_refresh(owner, monkeypatch)
    assert owner.task_tree.rows[a]['today'] == owner.task_tree.rows[a]['week'] == '00:01'
    assert calls[-1][0] == (saturday + timedelta(days=1), saturday + timedelta(days=7))
    assert s.state.tasks[a].currently_open_interval_start_utc == local(s, saturday, 23, 30).astimezone(UTC)
    assert errors == []



def test_aware_offset_observation_normalizes_to_one_utc_cutoff(setup, monkeypatch):
    s, a, _, _, _, clock = setup
    dated(s, a, TODAY, 60.125)
    offset_observation = clock[0].astimezone(timezone(timedelta(hours=5, minutes=30)))
    monkeypatch.setattr(app_module, 'utc_now', lambda: offset_observation)
    owner, errors, _ = make_owner(s)
    calls, _ = observe(s, monkeypatch)
    pure_refresh(owner, monkeypatch)
    assert calls[0][1]['cutoff_utc'] == clock[0]
    assert calls[0][1]['cutoff_utc'].tzinfo is UTC and errors == []
    assert owner.task_tree.rows[a]['today'] == '00:01'

def test_effective_corrections_redating_deletion_resets_and_confirmations(setup, monkeypatch):
    s, a, _, _, _, clock = setup
    old = interval(s, a, local(s, TODAY, 6), local(s, TODAY, 7))
    entry = dated(s, a, TODAY, 7200)
    owner, _, _ = make_owner(s)
    pure_refresh(owner, monkeypatch)
    assert owner.task_tree.rows[a]['today'] == '03:00'
    s.reset_task(a)
    prepared = s.prepare_polr_confirmation_batch([dict(task_id=a, work_date=str(TODAY),
        confirmed_hundredths=9999, source_export_id=None, expected_prior_confirmation_id=None,
        stale_export_acknowledged=False)])
    s.register_prepared_polr_confirmation_batch(prepared)
    pure_refresh(owner, monkeypatch)
    assert owner.task_tree.rows[a]['today'] == '03:00'
    s.edit_interval(a, old, local(s, TODAY, 6), local(s, TODAY, 6, 30), 'Correct')
    dated(s, a, TODAY + timedelta(days=1), 5400, entry, 'dated_duration_corrected')
    pure_refresh(owner, monkeypatch)
    assert owner.task_tree.rows[a]['today'] == '00:30' and owner.task_tree.rows[a]['week'] == '02:00'
    replacement = next(key for key, record in s.state.tasks[a].intervals.items() if not record.deleted)
    s.delete_interval(a, replacement, 'Void')
    s._append(a, 'dated_duration_deleted', dict(entry_id=entry, reason='Void'))
    pure_refresh(owner, monkeypatch)
    assert owner.task_tree.rows[a]['today'] == owner.task_tree.rows[a]['week'] == '00:00'


@pytest.mark.parametrize('fault', ['clock', 'naive', 'wrong-clock', 'boundary', 'accounting', 'missing-row',
                                  'negative', 'nan', 'infinite', 'bool', 'format', 'synthetic'])
def test_failure_marks_all_numbers_reports_original_and_recovers(setup, monkeypatch, fault):
    s, a, b, _, _, clock = setup
    dated(s, a, TODAY, 3600)
    owner, errors, jobs = make_owner(s)
    pure_refresh(owner, monkeypatch)
    assert owner.daily_var.get() == 'Today: 01:00'
    error = OSError('injected failure')
    def fail(*a, **kw): raise error
    if fault == 'synthetic': s.add_manual_duration(a, TODAY, 60, 'Legacy')
    before = capture(s)
    owner.task_tree.writes.clear()
    with monkeypatch.context() as m:
        if fault == 'clock': m.setattr(app_module, 'utc_now', fail)
        elif fault == 'naive': m.setattr(app_module, 'utc_now', lambda: datetime(2026, 10, 20))
        elif fault == 'wrong-clock': m.setattr(app_module, 'utc_now', lambda: None)
        elif fault == 'boundary': m.setattr(app_module, 'utc_now', lambda: datetime.min.replace(tzinfo=UTC))
        elif fault == 'accounting': m.setattr(s, 'calculate_date_window', fail)
        elif fault == 'format': m.setattr(app_module, 'format_duration_hm', fail)
        elif fault in ('missing-row', 'negative', 'nan', 'infinite', 'bool'):
            original = s.calculate_date_window
            def bad(*a, **kw):
                result = original(*a, **kw)
                if fault == 'missing-row': del result['tasks'][b]
                else: result['tasks'][b]['window_seconds'] = {'negative': -1, 'nan': float('nan'),
                                                            'infinite': float('inf'), 'bool': True}[fault]
                return result
            m.setattr(s, 'calculate_date_window', bad)
        owner._tick()
    assert capture(s) == before
    assert all(row['today'] == row['week'] == '—' for row in owner.task_tree.rows.values())
    assert owner.daily_var.get() == 'Today: —' and owner.weekly_var.get() == 'This week: —'
    assert owner.time_totals_error_var.get() == owner.mini_mode_window.time_totals_error_var.get() == 'Time totals unavailable.'
    assert owner.mini_mode_window.elapsed_var.get() == 'Today: —'
    assert owner.mini_mode_window.toggle_btn.states == ['!disabled']
    assert len(errors) == len(jobs) == 1 and jobs[0][0] >= 1000
    assert all(value == '—' for _, column, value in owner.task_tree.writes if column in ('today', 'week'))
    if fault in ('clock', 'accounting', 'format'): assert errors[0][1] is error
    assert errors[0][2] is errors[0][1].__traceback__
    if fault == 'synthetic':
        legacy = next(iter(s.state.tasks[a].intervals))
        s.delete_interval(a, legacy, 'Explicit test mutation')
    before_recovery = capture(s)
    jobs[0][1]()  # The next ordinary scheduled tick can recover.
    assert capture(s) == before_recovery and len(jobs) == 2
    assert owner.daily_var.get() == 'Today: 01:00' and not owner.time_totals_error_var.get()
    assert not owner.mini_mode_window.time_totals_error_var.get()


def test_start_stop_during_failure_and_reminder_only_never_recalculates(setup, monkeypatch):
    s, a, _, _, _, clock = setup
    owner, errors, _ = make_owner(s)
    def fail(*args, **kw): raise OSError('unavailable')
    with monkeypatch.context() as m:
        m.setattr(s, 'calculate_date_window', fail)
        owner.refresh_live_values()
        owner.mini_mode_window.toggle()
        running = s.state.running_task_id
        assert running is not None
        clock[0] += timedelta(minutes=2)
        owner.mini_mode_window.toggle()
        assert s.state.running_task_id is None
    pure_refresh(owner, monkeypatch)
    assert owner.mini_mode_window.elapsed_var.get() == 'Today: 00:02'
    mini = owner.mini_mode_window
    mini.reminder_label = SimpleNamespace(pack=lambda **kw: None, pack_forget=lambda: None)
    mini.month_end_due_provider = lambda: True
    owner.reminder_banner = SimpleNamespace(winfo_ismapped=lambda: True, pack_forget=lambda: None)
    owner._is_month_end_reminder_due_today = lambda: True
    before = mini.elapsed_var.get(), capture(s)
    def forbidden(*args, **kw): pytest.fail('Reminder-only update recalculated numbers')
    monkeypatch.setattr(app_module, 'utc_now', forbidden)
    monkeypatch.setattr(s, 'calculate_date_window', forbidden)
    owner._refresh_month_end_reminder_ui()
    assert (mini.elapsed_var.get(), capture(s)) == before


def test_empty_result_and_destroyed_root_do_not_schedule(setup, monkeypatch):
    s, a, b, *_ = setup
    owner, errors, jobs = make_owner(s)
    s.delete_task_tree(a)
    s.delete_task_tree(b)
    owner.task_tree = Tree(s)
    pure_refresh(owner, monkeypatch)
    assert owner.daily_var.get() == 'Today: 00:00' and owner.weekly_var.get() == 'This week: 00:00'
    assert owner.mini_mode_window.elapsed_var.get() == 'Today: 00:00'
    assert owner.mini_mode_window.task_name_var.get() == 'No tasks available' and errors == []
    owner.root.winfo_exists = lambda: False
    owner._tick()
    assert jobs == []
    def destroyed(): raise tk.TclError('application destroyed')
    owner.root.winfo_exists = destroyed
    owner._tick()
    assert jobs == []


def test_real_tk_columns_mini_open_start_stop_failure_recovery_and_minimum_size(
        setup, tk_root, pointer, monkeypatch):
    s, a, b, _, _, clock = setup
    dated(s, a, TODAY, 119.9)
    monkeypatch.setattr(app_module.TaskTimerApp, '_tick', lambda self: None)
    monkeypatch.setattr(app_module.TaskTimerApp, '_open_mini_mode_if_persistent_enabled', lambda self: None)
    monkeypatch.setattr(app_module.TaskTimerApp, '_maybe_show_startup_reminder_popup', lambda self: None)
    owner = app_module.TaskTimerApp(tk_root, s)
    owner.ui_settings.keep_mini_open = True  # Session fixture only; no settings save.
    tk_root.geometry('800x500+0+0')
    tk_root.update()
    assert owner.task_tree['columns'] == ('notes', 'state', 'today', 'week')
    for key, title in [('today', 'Today'), ('week', 'This week')]:
        assert owner.task_tree.heading(key, 'text') == title
        x, y, width, height = owner.task_tree.bbox(a, key)
        assert width >= 75 and x + width <= owner.task_tree.winfo_width()
    assert owner.daily_var.get() == 'Today: 00:01'
    owner.refresh_structure()
    assert owner.task_tree.set(a, 'today') == owner.task_tree.set(a, 'week') == '—'
    owner.refresh_live_values()
    mini_button = next(w for w in owner.toolbar_frame.winfo_children() if w.cget('text') == 'Mini Mode')
    calls, _ = observe(s, monkeypatch)
    assert owner.mini_mode_window is None
    original_init = MiniModeWindow.__init__
    original_refresh = MiniModeWindow.refresh_live_values
    def construct(mini, *args, **kw):
        original_init(mini, *args, **kw)
        assert owner.mini_mode_window is None and calls == []
        assert mini.elapsed_var.get() == 'Today: —'
    def refresh(mini, **kw):
        assert owner.mini_mode_window is mini  # Published before coordinated refresh.
        return original_refresh(mini, **kw)
    monkeypatch.setattr(MiniModeWindow, '__init__', construct)
    monkeypatch.setattr(MiniModeWindow, 'refresh_live_values', refresh)
    pointer.click(mini_button)
    mini = owner.mini_mode_window
    assert len(calls) == 1 and mini.elapsed_var.get() == 'Today: 00:01'
    mini.window.geometry('+820+0')
    tk_root.update()
    before = capture(s)
    pointer.click(mini_button)  # Existing mini: one new coordinated observation.
    assert len(calls) == 2 and capture(s) == before
    # Actual server input, not invoke(), operates timers even with failed accounting.
    reports = []
    tk_root.report_callback_exception = lambda *a: reports.append(a)
    calculate = s.calculate_date_window
    error = OSError('injected unavailable calculation')
    def fail(*a, **kw): raise error
    monkeypatch.setattr(s, 'calculate_date_window', fail)
    owner.refresh_live_values()
    assert owner.daily_var.get() == 'Today: —' and mini.elapsed_var.get() == 'Today: —'
    assert owner.time_totals_error_var.get() == mini.time_totals_error_var.get() == 'Time totals unavailable.'
    pointer.click(mini.toggle_btn)
    task_id = s.state.running_task_id
    assert task_id is not None
    clock[0] += timedelta(minutes=2)
    pointer.click(mini.toggle_btn)
    assert s.state.running_task_id is None and reports[-1][1] is error
    monkeypatch.setattr(s, 'calculate_date_window', calculate)
    owner.refresh_live_values()
    assert mini.elapsed_var.get() == 'Today: 00:03'
    assert owner.time_totals_error_var.get() == mini.time_totals_error_var.get() == ''
    owner.task_tree.selection_set(a)
    owner._on_tree_select()
    pointer.click(owner.selected_toggle_btn)
    assert s.state.running_task_id == a
    pointer.click(owner.selected_toggle_btn)
    assert s.state.running_task_id is None
    before = capture(s)
    owner.refresh_live_values()
    assert capture(s) == before
