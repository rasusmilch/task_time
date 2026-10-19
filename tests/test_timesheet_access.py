"""Production Timesheet controls, session retention and shutdown."""
from datetime import date
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from task_timer import app as app_module, dialogs, timesheet_window as windows, timesheet_save as saves
from task_timer.settings import UISettings, UISettingsStore
from test_timesheet_window import owner, Shell, setup, save_widgets, preview_widgets, owner_factory
from test_timesheet_preview import Variable, drafts
from test_timesheet_save import ready, dialog, exports, no_recalculation
from test_work_history import capture
from test_mixed_accounting import dated, local, MON, TUE
from test_work_history_browser import Widget
from test_history_window import Window, tk_root, pointer


_BUILD_UI = app_module.TaskTimerApp._build_ui


class Menu:
    def __init__(self, *a, **kw): self.items = []
    def add_command(self, **kw): self.items.append(('command', kw))
    def add_separator(self): self.items.append(('separator', {}))
    def add_cascade(self, **kw): self.items.append(('cascade', kw))


@pytest.fixture
def controls(owner, monkeypatch):
    monkeypatch.setattr(Widget, 'pack', Widget.grid, raising=False)
    monkeypatch.setattr(Widget, 'pack_forget', Widget.grid_remove, raising=False)
    for name in ('Frame', 'Label'): monkeypatch.setattr(app_module.tk, name, Widget)
    monkeypatch.setattr(app_module.tk, 'Menu', Menu)
    monkeypatch.setattr(app_module, 'StringVar', lambda: Variable(None))
    monkeypatch.setattr(ttk.Frame, 'pack', Widget.grid)
    monkeypatch.setattr(ttk.Frame, 'pack_forget', Widget.grid_remove)
    owner.root.configure = lambda **kw: setattr(owner.root, 'menu', kw['menu'])
    owner.root.winfo_exists = lambda: owner.root.exists
    owner.root.deiconify = lambda: None
    owner._init_row_fonts = lambda: None
    owner._build_task_tree = owner._build_selected_task_panel = lambda: None
    _BUILD_UI(owner)
    return owner


def button(parent, text):
    return next(w for w in parent.widgets if w.options.get('text') == text)


def launch(owner, route):
    if route == 'toolbar': return button(owner.toolbar_frame, 'Timesheet').invoke()
    if route == 'banner': return button(owner.reminder_banner, 'Open Timesheet').invoke()
    if route == 'menu':
        menu = next(kw['menu'] for kind, kw in owner.root.menu.items if kw.get('label') == 'File')
        return next(kw['command'] for kind, kw in menu.items if kw.get('label') == 'Timesheet…')()
    return owner._on_close_request()


@pytest.mark.parametrize('route', ['toolbar', 'menu', 'banner', 'close'])
def test_constructed_routes_share_one_owner_frozen_save_and_no_reminder_dismissal(
        setup, controls, monkeypatch, tmp_path, route):
    s, a, b, *_ = setup
    dated(s, a, MON, 119.9)
    dated(s, b, TUE, 3600)
    s.delete_task_only(b)
    s.start_task(a)
    owner = controls
    owner.ui_settings.month_end_reminder_enabled = True
    owner.ui_settings.month_end_reminder_show_close_notice = True
    owner._local_today = lambda: date(2026, 10, 30)
    monkeypatch.setattr(app_module, 'is_last_business_day', lambda day: True)
    monkeypatch.setattr(app_module, 'MonthEndCloseReminderDialog', lambda root: SimpleNamespace(choice='timesheet'))
    calls = []
    prepare = s.prepare_timesheet_export_snapshot
    def preparation(*args, **kw): calls.append((args, kw)); return prepare(*args, **kw)
    monkeypatch.setattr(s, 'prepare_timesheet_export_snapshot', preparation)
    def forbidden(*a, **kw): pytest.fail('Legacy export, reminder dismissal or incidental write')
    for name in ('export_report', 'export_selected_tasks_report', 'reset_task', 'delete_selected_tasks'):
        monkeypatch.setattr(s, name, forbidden)
    monkeypatch.setattr(UISettingsStore, 'save', forbidden)
    monkeypatch.setattr(owner, 'mark_month_end_reminder_handled_today', forbidden)
    target = tmp_path / 'timesheet.txt'
    dialog(monkeypatch, str(target))
    before = capture(s)
    def drive(_window):
        wrapper = owner._timesheet_window
        frame = wrapper.save_frame
        assert calls == [] and frame.preview.get_prepared_export() is None
        assert owner.open_timesheet() is None
        event = ready(frame)
        assert len(calls) == 1 and calls[0][1]['all_tasks'] and calls[0][1]['include_deleted']
        assert {t['task_id'] for t in event['payload']['tasks']} == {a, b}
        assert frame.save() and frame.saved_path == target
        assert wrapper.close()
        assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    Shell.action = drive
    launch(owner, route)
    after = capture(s)
    assert after[0] == before[0] and after[2] == before[2] and after[4] == before[4] and after[6] == before[6]
    assert owner._timesheet_window is None and owner.root.exists and len(exports(s)) == 1
    assert not any(e['event_type'] in ('stopped', 'reset', 'export_checkpoint', 'time_submission_created')
                   for e in s.events if e['event_id'] not in {e['event_id'] for e in before[1]})



def test_production_custom_independent_parent_child_and_deleted_selection(setup, controls, monkeypatch, tmp_path):
    s, parent, other, *_ = setup
    child = s.create_subtask(parent, 'Child', '')
    dated(s, parent, MON, 3600)
    dated(s, child, MON, 7200)
    dated(s, other, MON, 10800)
    s.delete_task_only(other)
    target = tmp_path / 'selected.txt'
    dialog(monkeypatch, str(target))
    before = capture(s)
    def inspect(_window):
        wrapper = controls._timesheet_window
        frame, preview = wrapper.save_frame, wrapper.save_frame.preview
        drafts(preview, str(MON), str(TUE))
        preview.scope_buttons['Selected tasks'].invoke()
        preview.task_buttons[parent].invoke()
        preview.task_buttons[other].invoke()
        assert not preview.task_vars[child].get()
        assert preview.preview_button.invoke()
        event = preview.get_prepared_export()
        assert {task['task_id'] for task in event['payload']['tasks']} == {parent, other}
        assert event['payload']['selection']['task_ids'] == sorted([parent, other])
        assert frame.save_button.invoke()
        assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
        wrapper.close()
    Shell.action = inspect
    launch(controls, 'menu')
    after = capture(s)
    assert after[0] == before[0] and after[2] == before[2] and after[4] == before[4]


def test_constructed_menus_and_controls_have_no_parallel_export_or_checkpoint_route(controls):
    owner = controls
    labels = [w.options.get('text', '') for w in owner.toolbar_frame.widgets + owner.reminder_banner.widgets]
    assert 'Timesheet' in labels and 'Open Timesheet' in labels and 'Export' not in labels
    menus = {kw['label']: kw['menu'] for kind, kw in owner.root.menu.items}
    all_commands = [kw['label'] for menu in menus.values() for kind, kw in menu.items if kind == 'command']
    assert 'Timesheet…' in all_commands
    assert not any('export' in label.casefold() or 'checkpoint' in label.casefold() for label in all_commands)
    for name in ('export', 'export_selected_tasks', '_handle_selected_export_post_action',
                 '_reopen_last_export_checkpoint', '_clear_selection_if_deleted'):
        assert not hasattr(app_module.TaskTimerApp, name)
    for name in ('SelectedTaskExportDialog', 'SelectedTaskExportResult', 'PostSelectedExportActionDialog'):
        assert not hasattr(dialogs, name)


def test_launch_failure_inline_original_exception_and_competing_grab_preserved(controls, monkeypatch):
    owner = controls
    error = RuntimeError('Cannot construct Timesheet'); error.add_note('Original detail')
    def broken(*a, **kw): raise error
    monkeypatch.setattr(windows, 'TimesheetWindow', broken)
    launch(owner, 'toolbar')
    assert owner.diagnostics[-1][1] is error and owner.diagnostics[-1][2] is error.__traceback__
    assert owner.timesheet_launch_error_var.get().startswith('Unable to open Timesheet:')
    assert owner.reminder_timesheet_error_label.visible and not owner._timesheet_window_opening
    competitor = Shell(owner.root); competitor.grab_set(); competitor.focus_set()
    launch(owner, 'banner')
    assert Window.grabbed is competitor and owner.root.tk.focus is competitor
    competitor.destroy()


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('presented', [False, True])
def test_unfinished_exit_warning_precedes_monthly_prompt_cancel_and_confirm(
        setup, controls, monkeypatch, tmp_path, enabled, presented):
    s, *_ = setup
    owner = controls
    owner.ui_settings.month_end_reminder_enabled = enabled
    owner.ui_settings.month_end_reminder_show_close_notice = True
    owner._local_today = lambda: date(2026, 10, 30)
    monkeypatch.setattr(app_module, 'MonthEndCloseReminderDialog', lambda *a: pytest.fail('Stacked monthly prompt'))
    target = tmp_path / 'conflict.txt'; target.write_bytes(b'Keep file')
    dialog(monkeypatch, str(target))
    confirmations = []
    def drive(_window):
        wrapper = owner._timesheet_window
        ready(wrapper.save_frame); assert not wrapper.save_frame.save()
        before, attempt = capture(s), wrapper.save_frame.get_save_attempt()
        if not presented:
            monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: True)
            assert wrapper.close()
        def cancel(**kw):
            confirmations.append(kw)
            owner._on_close_request()  # Nested callback cannot stack another warning.
            assert owner.open_timesheet() is None  # Exit confirmation cannot resume/open history.
            assert owner._timesheet_window is wrapper
            return False
        monkeypatch.setattr(app_module.messagebox, 'askyesno', cancel)
        owner._on_close_request()
        assert owner.root.exists and wrapper.save_frame.get_save_attempt() == attempt and capture(s) == before
        assert confirmations[-1]['default'] == 'no' and 'not deleted' in confirmations[-1]['message']
        assert confirmations[-1]['parent'] is (wrapper.window if presented else owner.root)
        monkeypatch.setattr(app_module.messagebox, 'askyesno', lambda **kw: True)
        owner._on_close_request()
        assert not owner.root.exists and owner._timesheet_window is None and target.read_bytes() == b'Keep file'
    Shell.action = drive
    owner.open_timesheet()



def test_reentrant_open_during_monthly_exit_choice_has_no_effect(controls, monkeypatch):
    owner = controls
    owner.ui_settings.month_end_reminder_enabled = True
    owner.ui_settings.month_end_reminder_show_close_notice = True
    owner._local_today = lambda: date(2026, 10, 30)
    def close_choice(_parent):
        assert owner._exit_in_progress and owner.open_timesheet() is None
        assert owner._timesheet_window is None
        return SimpleNamespace(choice='return')
    owner.root.lift = owner.root.focus_force = lambda: None
    monkeypatch.setattr(app_module, 'MonthEndCloseReminderDialog', close_choice)
    owner._on_close_request()
    assert owner.root.exists and not owner._exit_in_progress


def test_explicit_dismiss_still_updates_reminder_settings(controls):
    owner = controls
    calls = []
    owner.mark_month_end_reminder_handled_today = lambda: calls.append('dismiss')
    owner._refresh_month_end_reminder_ui = lambda: calls.append('indicator')
    button(owner.reminder_banner, 'Dismiss').invoke()
    assert calls == ['dismiss', 'indicator']


@pytest.fixture
def desktop(setup, tk_root, monkeypatch):
    s, *_ = setup
    monkeypatch.setattr(app_module, 'install_zoom_guard', lambda root: None)
    monkeypatch.setattr(app_module.TaskTimerApp, '_maybe_show_startup_reminder_popup', lambda self: None)
    monkeypatch.setattr(UISettingsStore, 'load', lambda self: UISettings())
    owner = app_module.TaskTimerApp(tk_root, s)
    owner._local_today = lambda: date(2026, 10, 30)
    owner.ui_settings.month_end_reminder_enabled = True
    owner._refresh_month_end_reminder_ui()
    tk_root.update()
    return owner


def real_button(parent, text):
    for child in parent.winfo_children():
        if isinstance(child, ttk.Button) and child.cget('text') == text:
            return child
        found = real_button(child, text)
        if found is not None: return found


def drive_modal(root, owner, action):
    failures = []
    def probe():
        wrapper = owner._timesheet_window
        if wrapper is None or not wrapper.is_presented() or root.grab_current() is not wrapper.window:
            root.after(10, probe)
            return
        try:
            wrapper.window.geometry('900x650+450+30')
            root.update()
            action(wrapper)
        except BaseException as exc:
            failures.append(exc)
            wrapper._dispose()
    def timeout():
        wrapper = owner._timesheet_window
        failures.append(AssertionError(f'Timesheet modal interaction timed out: {wrapper}, {owner.timesheet_launch_error_var.get()}, presented={wrapper._presented if wrapper else None}, state={wrapper.window.state() if wrapper else None}, grab={root.grab_current()}'))
        if owner._timesheet_window is not None: owner._timesheet_window._dispose()
    root.after(20, probe)
    job = root.after(5000, timeout)
    return failures, job


def test_real_tk_production_toolbar_calendars_blocking_timers_and_fresh_open(
        setup, desktop, tk_root, pointer, monkeypatch):
    s, a, b, *_ = setup
    dated(s, a, MON, 119.9)
    s.start_task(a)
    owner = desktop
    owner.ui_settings.keep_mini_open = True
    owner.open_mini_mode()
    owner.mini_mode_window.window.geometry('300x130+20+780')
    owner.task_tree.selection_set(a); owner.selected_task_id = a; owner._refresh_selected_task_panel()
    before = capture(s)
    calls = []
    prepare = s.prepare_timesheet_export_snapshot
    monkeypatch.setattr(s, 'prepare_timesheet_export_snapshot', lambda *a, **kw: calls.append(kw) or prepare(*a, **kw))
    def inspect(wrapper):
        frame, preview = wrapper.save_frame, wrapper.save_frame.preview
        assert not calls and preview.get_prepared_export() is None
        assert wrapper.window.grab_status() == 'local'
        pointer.click(owner.selected_toggle_btn)
        pointer.click(owner.mini_mode_window.toggle_btn)
        assert s.state.running_task_id == a and s.state.tasks[a].is_running
        assert owner.open_timesheet() is None
        ticks = []
        tk_root.after(0, lambda: ticks.append(True)); tk_root.update()
        assert ticks == [True]
        pointer.click(preview.period_buttons['Last week'])
        assert not calls
        pointer.click(preview.preview_button)
        assert preview.get_prepared_export()['payload']['start_date'] == '2026-10-11'
        pointer.click(preview.period_buttons['Custom'])
        for key, value in [('Start', str(MON)), ('End', str(TUE))]:
            entry = preview.date_entries[key]; entry.delete(0, 'end'); entry.insert(0, value)
        pointer.click(preview.picker_buttons['Start'])
        popup, calendar = next(iter(preview._pickers.items()))
        day = next(label for week in calendar._calendar for label in week if label.cget('text') == '13')
        pointer.click(day)
        assert preview.start_var.get() == str(TUE) and not preview._pickers
        pointer.click(preview.picker_buttons['End'])
        assert preview._pickers, (preview.error_var.get(), wrapper.is_presented(), wrapper.window.grab_current(), preview.picker_buttons['End'].winfo_rootx(), preview.picker_buttons['End'].winfo_rooty())
        popup = next(iter(preview._pickers)); popup.focus_force(); tk_root.update(); pointer.escape()
        assert not preview._pickers and wrapper.is_presented() and tk_root.grab_current() is wrapper.window
        assert len(calls) == 1 and preview.get_prepared_export() is None
        pointer.click(preview.preview_button)
        assert len(calls) == 2
        pointer.click(wrapper.close_button)
    failures, job = drive_modal(tk_root, owner, inspect)
    pointer.click(real_button(owner.toolbar_frame, 'Timesheet'))
    tk_root.after_cancel(job)
    if failures: raise failures[0]
    assert owner._timesheet_window is None and capture(s) == before
    def fresh(wrapper):
        assert wrapper.save_frame.preview.period_var.get() == 'This week'
        assert wrapper.save_frame.get_save_attempt() is None and len(calls) == 2
        pointer.click(wrapper.close_button)
    failures, job = drive_modal(tk_root, owner, fresh)
    pointer.click(real_button(owner.reminder_banner, 'Open Timesheet'))
    tk_root.after_cancel(job)
    assert failures == [] and capture(s) == before


def test_real_tk_file_menu_retention_overwrite_reopen_and_shutdown(
        setup, desktop, tk_root, pointer, monkeypatch, tmp_path):
    s, a, *_ = setup
    dated(s, a, MON, 3600)
    s.start_task(a)
    owner = desktop
    diagnostics = []
    tk_root.report_callback_exception = lambda *args: diagnostics.append(args)
    target = tmp_path / 'existing.txt'; target.write_bytes(b'Preserve until confirmed')
    dialog(monkeypatch, str(target))
    retained = []
    def first(wrapper):
        frame, preview = wrapper.save_frame, wrapper.save_frame.preview
        pointer.click(preview.period_buttons['Last week']); pointer.click(preview.preview_button)
        pointer.click(frame.save_button)
        assert frame.has_unfinished_attempt() and frame._can_overwrite
        retained.append((wrapper, frame.get_save_attempt(), preview.report.get('1.0', 'end-1c')))
        monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: False)
        pointer.click(wrapper.close_button)
        assert wrapper.is_presented()
        monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: True)
        pointer.click(wrapper.close_button)
    failures, job = drive_modal(tk_root, owner, first)
    menubar = tk_root.nametowidget(tk_root.cget('menu'))
    menu = tk_root.nametowidget(menubar.entrycget('File', 'menu'))
    menu.post(100, 100)
    pointer.click(menu, x_offset=50, y_offset=menu.yposition(menu.index('Timesheet…')) + 8)
    tk_root.after_cancel(job)
    if failures: raise failures[0]
    assert owner._timesheet_window is retained[0][0]
    before = capture(s)
    def resumed(wrapper):
        old, attempt, text = retained[0]
        assert wrapper is old and wrapper.save_frame.get_save_attempt() == attempt
        frame = wrapper.save_frame
        assert frame.preview.report.get('1.0', 'end-1c') == text and frame.preview._locked
        # Root's real registered close protocol retains the attempt on cancel.
        monkeypatch.setattr(app_module.messagebox, 'askyesno', lambda **kw: False)
        tk_root.tk.call(tk_root.protocol('WM_DELETE_WINDOW'))
        assert owner._timesheet_window is wrapper and wrapper.window.winfo_exists()
        pointer.click(frame.overwrite_button)
        assert target.read_bytes() == b'Preserve until confirmed'
        monkeypatch.setattr(app_module.messagebox, 'askyesno', lambda **kw: True)
        pointer.click(frame.overwrite_button)
        assert frame.saved_path == target and not frame.has_unfinished_attempt()
        pointer.click(wrapper.close_button)
    failures, job = drive_modal(tk_root, owner, resumed)
    pointer.click(real_button(owner.toolbar_frame, 'Timesheet'))
    tk_root.after_cancel(job)
    assert failures == [] and capture(s) == before and len(exports(s)) == 1
    assert target.read_bytes() == retained[0][1]['prepared_event']['payload']['report_text'].encode('utf-8')
    def shutdown(wrapper):
        preview = wrapper.save_frame.preview
        pointer.click(preview.period_buttons['Custom'])
        pointer.click(preview.picker_buttons['Start'])  # No captured date: visible inline validation.
        assert preview.get_prepared_export() is None and preview.error_label.winfo_ismapped()
        preview.start_var.set(str(MON))
        pointer.click(preview.picker_buttons['Start'])
        assert preview._pickers
        owner.ui_settings.month_end_reminder_enabled = False
        tk_root.tk.call(tk_root.protocol('WM_DELETE_WINDOW'))
    failures, job = drive_modal(tk_root, owner, shutdown)
    pointer.click(real_button(owner.toolbar_frame, 'Timesheet'))
    tk_root.after_cancel(job)
    if failures: raise failures[0]
    assert owner._timesheet_window is None
    assert not retained[0][0].save_frame.preview._pickers


def test_real_tk_close_reminder_opens_timesheet_and_returns_without_exit(
        setup, desktop, tk_root, pointer, monkeypatch):
    s, *_ = setup
    owner = desktop
    owner.ui_settings.month_end_reminder_show_close_notice = True
    before = capture(s)
    errors = []
    def choose():
        prompt = next((w for w in tk_root.winfo_children()
                       if isinstance(w, tk.Toplevel) and w.title() == 'Month-End Reminder'), None)
        if prompt is None:
            tk_root.after(10, choose)
            return
        try:
            pointer.click(real_button(prompt, 'Open Timesheet'))
        except BaseException as exc:
            errors.append(exc)
            prompt.destroy()
    def inspect(wrapper):
        assert wrapper.save_frame.preview.get_prepared_export() is None
        pointer.click(wrapper.close_button)
    failures, job = drive_modal(tk_root, owner, inspect)
    tk_root.after(10, choose)
    tk_root.tk.call(tk_root.protocol('WM_DELETE_WINDOW'))
    tk_root.after_cancel(job)
    if errors or failures: raise (errors + failures)[0]
    assert tk_root.winfo_exists() and owner._timesheet_window is None and capture(s) == before


@pytest.fixture
def monthly_dialog(controls, monkeypatch):
    """Actual reminder controls/grab; isolate only Tk construction and waiting."""
    owner = controls
    owner.ui_settings.month_end_reminder_enabled = True
    owner.ui_settings.month_end_reminder_show_close_notice = True
    owner._local_today = lambda: date(2026, 10, 30)
    monkeypatch.setattr(dialogs, 'Toplevel', Shell)
    monkeypatch.setattr(Shell, 'resizable', lambda *args: None, raising=False)
    seen, actions = [], []
    def wait(window):
        seen.append(window)
        assert Window.grabbed is window
        actions[-1](window)
    owner.root.wait_window = wait
    return owner, actions, seen


def reminder_button(window, text):
    for widget in window.widgets:
        if widget.options.get('text') == text:
            return widget
        result = reminder_button(widget, text)
        if result is not None:
            return result


@pytest.mark.parametrize('completed', [False, True], ids=['preview', 'saved'])
@pytest.mark.parametrize('choice', ['Return to App', 'Open Timesheet', 'Close Anyway'])
def test_presented_timesheet_monthly_round_trip_preserves_modal_and_frozen_state(
        setup, monthly_dialog, monkeypatch, tmp_path, completed, choice):
    s, task, *_ = setup
    dated(s, task, MON, 119.9)
    s.start_task(task)
    owner, actions, reminders = monthly_dialog
    root_focus = []
    owner.root.focus_force = lambda: root_focus.append('root focus override')
    owner.root.lift = lambda: None
    target = tmp_path / 'saved.txt'
    dialog(monkeypatch, str(target))
    def inspect(_window):
        wrapper, frame = owner._timesheet_window, owner._timesheet_window.save_frame
        frame.preview.scope_buttons['Selected tasks'].invoke()
        frame.preview.task_buttons[task].invoke()
        candidate = ready(frame)
        if completed:
            assert frame.save() and frame.saved_path == target
        before = capture(s)
        report = frame.preview.report.get()
        fields = tuple(v.get() for v in (frame.preview.period_var, frame.preview.scope_var,
                                        frame.preview.start_var, frame.preview.end_var,
                                        *frame.preview.task_vars.values()))
        def choose(reminder):
            assert owner._exit_in_progress
            owner._on_close_request()
            assert owner.open_timesheet() is None and len(reminders) == 1
            reminder_button(reminder, choice).invoke()
        actions.append(choose)
        with monkeypatch.context() as m:
            def forbidden(*args, **kwargs): pytest.fail('Reminder rebuilt or recalculated Timesheet')
            m.setattr(windows, 'TimesheetWindow', forbidden)
            m.setattr(wrapper, 'show_modal', forbidden)
            for name in ('prepare_timesheet_export_snapshot', 'register_prepared_timesheet_export',
                         'materialize_timesheet_export'):
                m.setattr(s, name, forbidden)
            m.setattr(UISettingsStore, 'save', forbidden)
            owner._on_close_request()
        assert capture(s) == before and not owner._exit_in_progress
        assert wrapper.save_frame is frame and frame.preview.get_prepared_export() == candidate
        assert frame.preview.report.get() == report
        assert tuple(v.get() for v in (frame.preview.period_var, frame.preview.scope_var,
                                      frame.preview.start_var, frame.preview.end_var,
                                      *frame.preview.task_vars.values())) == fields
        if completed:
            assert target.read_bytes() == candidate['payload']['report_text'].encode('utf-8')
            assert not frame.has_unfinished_attempt()
        if choice == 'Close Anyway':
            assert not owner.root.exists and wrapper._destroyed and owner._timesheet_window is None
        else:
            assert owner._timesheet_window is wrapper and wrapper.is_presented()
            assert Window.grabbed is wrapper.window
            assert wrapper.window.grab_status() == 'local' and root_focus == []
            assert owner.root.tk.focus is wrapper.window
            assert wrapper.close() and owner._timesheet_window is None
    Shell.action = inspect
    owner.open_timesheet()
    assert owner.diagnostics == []
    assert not owner._timesheet_window_opening
    if choice != 'Close Anyway':
        Shell.action = lambda window: owner._timesheet_window.close()
        fresh = owner.open_timesheet()
        assert fresh.save_frame.get_save_attempt() is None
        assert fresh.save_frame.preview.get_prepared_export() is None


@pytest.mark.parametrize('kind', ['local', 'global'])
@pytest.mark.parametrize('when', ['before', 'during'])
def test_monthly_return_never_displaces_competing_grab(monthly_dialog, monkeypatch, kind, when):
    from test_history_modal_return import Focus
    owner, actions, seen = monthly_dialog
    competitors = []
    def inspect(window):
        wrapper = owner._timesheet_window
        competitor = Shell(owner.root); competitor.status = kind
        focus = Focus(competitor)
        competitors.append(competitor)
        def occupy():
            competitor.grab_set(); focus.focus_set()
        if when == 'before': occupy()
        else:
            def choose(reminder):
                occupy()
                reminder_button(reminder, 'Return to App').invoke()
            actions.append(choose)
        owner._on_close_request()
        assert len(seen) == int(when == 'during')
        assert Window.grabbed is competitor and owner.root.tk.focus is focus
        assert not owner._exit_in_progress and owner._timesheet_window is wrapper
        wrapper.close()
    Shell.action = inspect
    owner.open_timesheet()
    assert owner.diagnostics == [] and not owner._timesheet_window_opening
    assert Window.grabbed is competitors[0]
    competitors[0].destroy()


@pytest.mark.parametrize('change', ['destroy-window', 'destroy-root', 'dead-focus', 'reused-focus'])
def test_monthly_return_handles_invalidation_and_focus_identity(monthly_dialog, monkeypatch, change):
    from test_history_modal_return import Focus
    owner, actions, _ = monthly_dialog
    owner.root.lift = owner.root.focus_force = lambda: None
    def inspect(window):
        wrapper = owner._timesheet_window
        focus = Focus(window); focus.focus_set()
        count = window.acquisitions
        def choose(reminder):
            if change == 'destroy-window': window.destroy()
            elif change == 'destroy-root': owner.root.destroy(); return
            elif change == 'dead-focus': focus.exists = False
            else: Focus(window)  # Same Tcl name; saved Python widget is stale.
            reminder_button(reminder, 'Return to App').invoke()
        actions.append(choose)
        owner._on_close_request()
        if change.startswith('destroy'):
            assert owner._timesheet_window is None and window.acquisitions == count
        else:
            assert Window.grabbed is window and owner.root.tk.focus is window
            assert focus.focuses == 1  # Only the explicit pre-reminder focus.
            wrapper.close()
    Shell.action = inspect
    owner.open_timesheet()
    assert owner.diagnostics == [] and not owner._exit_in_progress


@pytest.mark.parametrize('primary_failure', [False, True])
def test_monthly_restoration_failure_reports_original_and_releases_guards(
        monthly_dialog, monkeypatch, primary_failure):
    owner, actions, _ = monthly_dialog
    original = RuntimeError('Reminder wait failed')
    restoration = OSError('Local grab restoration failed')
    def inspect(window):
        wrapper = owner._timesheet_window
        def choose(reminder):
            reminder_button(reminder, 'Return to App').invoke()
            if primary_failure: raise original
        actions.append(choose)
        with monkeypatch.context() as m:
            def fail(): raise restoration
            m.setattr(window, 'grab_set', fail)
            owner._on_close_request()
        error = original if primary_failure else restoration
        assert owner.diagnostics[-1][1] is error
        assert owner.diagnostics[-1][2] is error.__traceback__
        if primary_failure:
            assert 'Local grab restoration failed' in '\n'.join(error.__notes__)
        assert Window.grabbed is None and not owner._exit_in_progress
        wrapper.close()
    Shell.action = inspect
    owner.open_timesheet()
    assert len(owner.diagnostics) == 1 and not owner._timesheet_window_opening


def test_restore_modal_is_guarded_and_avoids_redundant_acquisition(monthly_dialog, monkeypatch):
    owner, actions, _ = monthly_dialog
    def inspect(window):
        wrapper = owner._timesheet_window
        before = window.acquisitions
        assert wrapper.restore_modal() and window.acquisitions == before
        window.grab_release()
        with monkeypatch.context() as m:
            m.setattr(wrapper.save_frame, '_busy', True)
            assert not wrapper.restore_modal() and Window.grabbed is None
        # A global grab, including on the same window, is never replaced.
        window.grab_set(); window.status = 'global'
        assert not wrapper.restore_modal() and window.acquisitions == before + 1
        window.status = 'local'
        def choose(reminder): reminder_button(reminder, 'Open Timesheet').invoke()
        actions.append(choose)
        acquire = window.grab_set
        def guarded_acquire():
            assert owner._exit_in_progress and owner.open_timesheet() is None
            owner._on_close_request()
            acquire()
        monkeypatch.setattr(window, 'grab_set', guarded_acquire)
        owner._on_close_request()
        assert Window.grabbed is window and window.acquisitions == before + 2
        wrapper.close()
        assert not wrapper.restore_modal()
    Shell.action = inspect
    owner.open_timesheet()
    assert owner.diagnostics == []


def test_monthly_close_during_visibility_transition_does_not_stack_dialogs(owner, monkeypatch):
    def visible(window):
        owner._on_close_request()
        assert not owner._exit_in_progress and Window.grabbed is None
        window.visible = True
    monkeypatch.setattr(Shell, 'winfo_viewable', lambda self: False)
    monkeypatch.setattr(Shell, 'wait_visibility', visible)
    monkeypatch.setattr(app_module, 'MonthEndCloseReminderDialog', lambda *a: pytest.fail('Transition opened reminder'))
    owner.open_timesheet()
    assert owner.diagnostics == [] and owner._timesheet_window is None


@pytest.mark.parametrize('withdrawn', [False, True])
def test_unfinished_exit_cancel_restores_presented_only_without_monthly_prompt(
        owner, setup, monkeypatch, tmp_path, withdrawn):
    s, *_ = setup
    target = tmp_path / 'conflict.txt'; target.write_bytes(b'Keep')
    dialog(monkeypatch, str(target))
    monkeypatch.setattr(app_module, 'MonthEndCloseReminderDialog', lambda *a: pytest.fail('Stacked monthly prompt'))
    def inspect(window):
        frame = owner._timesheet_window.save_frame
        ready(frame); assert not frame.save()
        monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: True)
        owner._timesheet_window.close() if withdrawn else None
        if not withdrawn:
            verify()
            monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: True)
            owner._timesheet_window.close()
    def verify():
        wrapper = owner._timesheet_window
        attempt, before = wrapper.save_frame.get_save_attempt(), capture(s)
        def cancel(**kw):
            assert kw['default'] == 'no'
            assert owner.open_timesheet() is None
            owner._on_close_request()
            if Window.grabbed is wrapper.window:
                wrapper.window.grab_release()  # Model a dialog returning without restoring grab.
            return False
        monkeypatch.setattr(app_module.messagebox, 'askyesno', cancel)
        owner._on_close_request()
        assert Window.grabbed is (None if withdrawn else wrapper.window)
        assert wrapper.save_frame.get_save_attempt() == attempt and capture(s) == before
        assert not owner._exit_in_progress
    Shell.action = inspect
    owner.open_timesheet()
    assert owner.diagnostics == []
    if withdrawn: verify()
    assert not owner._timesheet_window.restore_modal()


def real_monthly_choice(root, owner, pointer, choice):
    """Bound the nested real reminder wait, including cleanup if routing fails."""
    failures, jobs = [], []
    active = True
    def prompt():
        return next((w for w in root.winfo_children()
                     if isinstance(w, tk.Toplevel) and w.title() == 'Month-End Reminder'), None)
    def choose():
        if not active: return
        reminder = prompt()
        if reminder is None:
            jobs.append(root.after(10, choose))
            return
        try:
            reminder.geometry('+20+180')
            root.update()
            assert root.grab_current() is reminder
            owner._on_close_request()
            assert owner.open_timesheet() is None
            pointer.click(real_button(reminder, choice))
        except BaseException as exc:
            failures.append(exc)
            if owner._history_widget_exists(reminder): reminder.destroy()
    def timeout():
        failures.append(AssertionError('Monthly reminder interaction timed out'))
        reminder = prompt()
        if reminder is not None: reminder.destroy()
    jobs.append(root.after(20, choose))
    jobs.append(root.after(2500, timeout))
    try:
        root.tk.call(root.protocol('WM_DELETE_WINDOW'))
    finally:
        active = False
        for job in jobs: root.after_cancel(job)
    if failures: raise failures[0]


@pytest.mark.parametrize('completed', [False, True], ids=['preview', 'saved'])
@pytest.mark.parametrize('shutdown', [False, True], ids=['return-and-open', 'close-anyway'])
def test_real_tk_presented_timesheet_monthly_modal_return_before_and_after_save(
        setup, desktop, tk_root, pointer, monkeypatch, tmp_path, completed, shutdown):
    s, task, *_ = setup
    dated(s, task, MON, 119.9)
    s.start_task(task)
    owner = desktop
    owner.ui_settings.month_end_reminder_show_close_notice = True
    owner.ui_settings.keep_mini_open = True
    owner.open_mini_mode()
    owner.mini_mode_window.window.geometry('300x130+20+780')
    owner.task_tree.selection_set(task); owner.selected_task_id = task; owner._refresh_selected_task_panel()
    target = tmp_path / 'saved.txt'
    dialog(monkeypatch, str(target))
    calls = []
    for name in ('prepare_timesheet_export_snapshot', 'register_prepared_timesheet_export',
                 'materialize_timesheet_export'):
        original = getattr(s, name)
        def observe(*args, _name=name, _original=original, **kw):
            calls.append(_name)
            return _original(*args, **kw)
        monkeypatch.setattr(s, name, observe)
    def inspect(wrapper):
        frame, preview = wrapper.save_frame, wrapper.save_frame.preview
        pointer.click(preview.scope_buttons['Selected tasks'])
        pointer.click(preview.task_buttons[task])
        pointer.click(preview.period_buttons['Last week'])
        pointer.click(preview.preview_button)
        candidate = preview.get_prepared_export()
        assert candidate is not None
        if completed:
            pointer.click(frame.save_button)
            assert frame.saved_path == target and not frame.has_unfinished_attempt()
        before, operations = capture(s), list(calls)
        report = preview.report.get('1.0', 'end-1c')
        fields = tuple(v.get() for v in (preview.period_var, preview.scope_var, preview.start_var,
                                        preview.end_var, *preview.task_vars.values()))
        grabs = []
        acquire = wrapper.window.grab_set
        def record_grab():
            assert owner._history_widget_exists(wrapper.window)
            grabs.append(True); acquire()
        monkeypatch.setattr(wrapper.window, 'grab_set', record_grab)
        if shutdown:
            real_monthly_choice(tk_root, owner, pointer, 'Close Anyway')
            assert owner._timesheet_window is None and wrapper._destroyed and grabs == []
        else:
            for choice in ('Return to App', 'Open Timesheet'):
                # Ordinary focus may be absent under the window manager; that
                # case must return to the Timesheet itself rather than root.
                pointer.click(preview.report)
                saved_focus = tk_root.focus_get()
                expected_focus = (saved_focus if saved_focus is not None
                                  and saved_focus.winfo_toplevel() is wrapper.window else wrapper.window)
                real_monthly_choice(tk_root, owner, pointer, choice)
                assert owner._timesheet_window is wrapper and wrapper.save_frame is frame
                assert wrapper.is_presented() and tk_root.grab_current() is wrapper.window
                assert wrapper.window.grab_status() == 'local'
                # This assertion uses the isolated xfwm4 window manager; grab/input
                # checks below are separate server-delivered interaction evidence.
                assert tk_root.focus_get() is expected_focus
                pointer.click(owner.selected_toggle_btn)
                pointer.click(owner.mini_mode_window.toggle_btn)
                assert s.state.running_task_id == task and s.state.tasks[task].is_running
                assert calls == operations and capture(s) == before
                assert preview.get_prepared_export() == candidate
                assert preview.report.get('1.0', 'end-1c') == report
                assert tuple(v.get() for v in (preview.period_var, preview.scope_var, preview.start_var,
                                              preview.end_var, *preview.task_vars.values())) == fields
                assert not owner._exit_in_progress
            assert len(grabs) == 2
            if not completed:
                pointer.click(preview.period_buttons['Custom'])
                preview.start_var.set(str(MON))
                pointer.click(preview.picker_buttons['Start'])
                popup = next(iter(preview._pickers)); popup.focus_set(); tk_root.update()
                pointer.escape()
                assert not preview._pickers and tk_root.grab_current() is wrapper.window
            pointer.click(wrapper.close_button)
            assert wrapper._destroyed and owner._timesheet_window is None
        assert calls == operations and capture(s) == before
        if completed:
            assert target.read_bytes() == candidate['payload']['report_text'].encode('utf-8')
            assert frame.saved_path == target and len(exports(s)) == 1
        else:
            assert not target.exists() and exports(s) == []
    failures, job = drive_modal(tk_root, owner, inspect)
    pointer.click(real_button(owner.toolbar_frame, 'Timesheet'))
    tk_root.after_cancel(job)
    if failures: raise failures[0]
    assert not owner._timesheet_window_opening
    if not shutdown:
        def fresh(wrapper):
            assert wrapper.save_frame.preview.get_prepared_export() is None
            assert wrapper.save_frame.get_save_attempt() is None
            pointer.click(wrapper.close_button)
        failures, job = drive_modal(tk_root, owner, fresh)
        pointer.click(real_button(owner.toolbar_frame, 'Timesheet'))
        tk_root.after_cancel(job)
        assert failures == []


@pytest.mark.parametrize('invalid', ['withdrawn', 'stale-window', 'dead-parent'])
def test_restore_modal_rejects_nonpresentable_identity(monthly_dialog, monkeypatch, invalid):
    owner, *_ = monthly_dialog
    def inspect(window):
        wrapper = owner._timesheet_window
        window.grab_release()
        count = window.acquisitions
        with monkeypatch.context() as m:
            if invalid == 'withdrawn': window.withdraw()
            elif invalid == 'stale-window': m.setitem(window.master.children, window._name, object())
            else: m.setattr(owner.root, 'exists', False)
            assert not wrapper.restore_modal() and Window.grabbed is None
            assert window.acquisitions == count
        wrapper.close()
    Shell.action = inspect
    owner.open_timesheet()
    assert owner.diagnostics == []


@pytest.mark.parametrize('kind', ['local', 'global'])
def test_nonreminder_exit_preserves_shutdown_with_presented_timesheet(monthly_dialog, kind):
    owner, actions, seen = monthly_dialog
    owner.ui_settings.month_end_reminder_enabled = False
    def inspect(window):
        wrapper = owner._timesheet_window
        competitor = Shell(owner.root); competitor.status = kind; competitor.grab_set()
        acquired = window.acquisitions
        owner._on_close_request()
        assert not owner.root.exists and wrapper._destroyed
        assert owner._timesheet_window is None and seen == []
        assert window.acquisitions == acquired
    Shell.action = inspect
    owner.open_timesheet()
    assert owner.diagnostics == [] and not owner._exit_in_progress
