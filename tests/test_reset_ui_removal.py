"""Reset-free shipped controls/export paths; retained backend contracts are separate."""

from copy import deepcopy
from datetime import date, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from task_timer import app as app_module, dialogs
from task_timer.settings import BackupSettings, UISettings, UISettingsStore
from test_mixed_accounting import setup, dated, local, MON, TUE
from test_work_history import interval
from test_history_session_direction import owner_factory
from test_work_history_view import make_view
from test_work_history_browser import build
from test_history_window import owned_ui, Window, tk_root, pointer, modal_action
from test_history_access import controls, select_task


@pytest.fixture
def running(setup, monkeypatch):
    s, a, b, _, _, clock = setup
    interval(s, a, local(s, MON, 8), local(s, MON, 9))
    dated(s, a, MON, 119.9)
    clock[0] = local(s, TUE + timedelta(days=7), 9).astimezone(timezone.utc)
    s.start_task(a)
    clock[0] = local(s, TUE + timedelta(days=7), 12).astimezone(timezone.utc)
    # Every backup invocation gets a distinct timestamp, including promotions/retention.
    backup_clock = [clock[0]]
    def backup_now():
        backup_clock[0] += timedelta(seconds=1)
        return backup_clock[0]
    monkeypatch.setattr('task_timer.backups.utc_now', backup_now)
    s.save_backup_settings(BackupSettings(auto_backup_before_risky_operations=True))
    return s, a, b, clock


def forbid_reset(s, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Shipped UI requested a backend task reset')
    for name in ('reset_task', 'reset_task_only', 'reset_task_tree',
                 'reset_selected_tasks', 'reset_all_non_deleted_tasks'):
        monkeypatch.setattr(s, name, forbidden)


def evidence(s):
    return deepcopy(s.state), deepcopy(s.events), deepcopy(sorted(s.storage.iter_all_events(strict=True), key=lambda e: e['_read_sequence']))


def assert_preserved(s, before, expected):
    state, events, journal = before
    assert s.state == state
    assert s.events[:len(events)] == events
    persisted = sorted(s.storage.iter_all_events(strict=True), key=lambda e: e['_read_sequence'])
    assert persisted[:len(journal)] == journal
    added = s.events[len(events):]
    assert [event['event_type'] for event in added] == expected
    assert not any(event['event_type'] in ('reset', 'stopped') for event in added)
    assert s.get_effective_polr_confirmations() == {}
    return added


@pytest.fixture
def export_owner(running, owner_factory, monkeypatch):
    s, a, b, clock = running
    owner = owner_factory(s)
    owner.ui_settings_store = UISettingsStore(s.storage.data_dir)
    owner._local_today = lambda: date(2026, 10, 30)
    calls = []
    owner.refresh_structure = lambda: calls.append('structure')
    owner.refresh_live_values = lambda: calls.append('live')
    owner._refresh_month_end_reminder_ui = lambda: calls.append('reminder')
    owner.selected_task_id = a
    owner.task_tree = SimpleNamespace(selection=lambda: (a,), selection_remove=lambda *ids: calls.append(('clear', ids)))
    forbid_reset(s, monkeypatch)
    return owner, calls


def selected_input(owner, task_ids, monkeypatch, *, mark=False):
    end = app_module.utc_now()
    monkeypatch.setattr(app_module, 'SelectedTaskExportDialog', lambda *args: SimpleNamespace(
        result=SimpleNamespace(task_ids=task_ids, window_start_utc=local(owner.service, MON).astimezone(timezone.utc), window_end_utc=end,
                               mark_submitted=mark, reason='Reviewed external entry')))


@pytest.mark.parametrize('route', ['full', 'banner', 'close'])
def test_full_export_routes_preserve_running_work_with_checkpoint_backup_and_reminder(
        running, export_owner, monkeypatch, tmp_path, route):
    s, a, b, clock = running
    owner, calls = export_owner
    before = evidence(s)
    target = tmp_path / 'full.txt'
    monkeypatch.setattr(app_module.filedialog, 'asksaveasfilename', lambda **kw: str(target))
    def no_prompt(*args, **kwargs): pytest.fail('Full export introduced a completion confirmation')
    monkeypatch.setattr(app_module.messagebox, 'askyesno', no_prompt)
    if route == 'close':
        owner.ui_settings.month_end_reminder_enabled = True
        owner.ui_settings.month_end_reminder_show_close_notice = True
        monkeypatch.setattr(app_module, 'MonthEndCloseReminderDialog', lambda parent: SimpleNamespace(choice='export'))
        owner.root.deiconify = lambda: calls.append('deiconify')
        owner.root.lift = lambda: calls.append('lift')
    if route == 'full': assert owner.export() is True
    elif route == 'banner': owner._on_reminder_export()
    else: owner._on_close_request()
    added = assert_preserved(s, before, ['export_checkpoint'])
    assert added[0]['payload']['reset_after'] is False and target.is_file()
    assert 'Reset requested after export: No' in target.read_text(encoding='utf-8')
    assert calls[:3] == ['structure', 'live', 'reminder']
    assert calls[3:] == ([] if route == 'full' else ['reminder'] if route == 'banner' else ['deiconify', 'lift'])
    saved = owner.ui_settings_store.load()
    assert saved.month_end_reminder_last_export_prompted_local_date == '2026-10-30'
    assert saved.month_end_reminder_last_dismissed_local_date == '2026-10-30'
    assert {entry.reason for entry in s.list_managed_backups()} == {'safety: before export'}


@pytest.mark.parametrize('mark', [False, True])
def test_selected_leave_preserves_running_work_and_optional_submission_without_checkpoint(
        running, export_owner, monkeypatch, tmp_path, mark):
    s, a, b, clock = running
    owner, calls = export_owner
    selected_input(owner, [a], monkeypatch, mark=mark)
    target, messages = tmp_path / 'selected.txt', []
    monkeypatch.setattr(app_module.filedialog, 'asksaveasfilename', lambda **kw: str(target))
    monkeypatch.setattr(app_module, 'PostSelectedExportActionDialog', lambda parent: SimpleNamespace(choice='leave'))
    monkeypatch.setattr(app_module.messagebox, 'showinfo', lambda *a, **kw: messages.append(a))
    before = evidence(s)
    assert owner.export_selected_tasks() is True
    assert_preserved(s, before, ['time_submission_created'] if mark else [])
    assert target.is_file() and messages == [('Export Selected Tasks', 'Selected-task export complete.')]
    assert calls == [] and not owner.ui_settings_store.path.exists()
    assert {entry.reason for entry in s.list_managed_backups()} == {'safety: before selected export'}
    submissions = s.list_time_submissions()
    assert len(submissions) == int(mark)
    if mark: assert submissions[0].task_ids == {a}


def test_selected_overlap_acknowledgement_continues_with_real_marker_and_no_reset(
        running, export_owner, monkeypatch, tmp_path):
    s, a, *_ = running
    owner, calls = export_owner
    start = local(s, MON).astimezone(timezone.utc)
    s.create_time_submission_marker([a], start, app_module.utc_now(), 'Earlier entry', None)
    selected_input(owner, [a], monkeypatch, mark=True)
    prompts = []
    def acknowledge(*args, **kwargs):
        prompts.append(args)
        return True
    monkeypatch.setattr(app_module.messagebox, 'askyesno', acknowledge)
    monkeypatch.setattr(app_module.messagebox, 'showinfo', lambda *a, **kw: None)
    target = tmp_path / 'acknowledged.txt'
    monkeypatch.setattr(app_module.filedialog, 'asksaveasfilename', lambda **kw: str(target))
    monkeypatch.setattr(app_module, 'PostSelectedExportActionDialog', lambda parent: SimpleNamespace(choice='leave'))
    before = evidence(s)
    assert owner.export_selected_tasks() is True
    assert_preserved(s, before, ['time_submission_created'])
    assert len(prompts) == 1 and prompts[0][0] == 'Possible duplicate Epicor entry'
    assert len(s.list_time_submissions()) == 2 and target.is_file()
    assert calls == [] and not owner.ui_settings_store.path.exists()


@pytest.mark.parametrize('where', ['full-file', 'selected-dialog', 'selected-file', 'overlap'])
def test_cancel_does_not_reach_export_or_completion(running, export_owner, monkeypatch, where):
    s, a, *_ = running
    owner, calls = export_owner
    selected_input(owner, [a], monkeypatch, mark=where == 'overlap')
    if where == 'selected-dialog':
        monkeypatch.setattr(app_module, 'SelectedTaskExportDialog', lambda *a: SimpleNamespace(result=None))
    if where == 'overlap':
        # Actual existing submission creates the overlap; declining must not append another.
        s.create_time_submission_marker([a], local(s, MON).astimezone(timezone.utc), app_module.utc_now(), 'Earlier entry', None)
        monkeypatch.setattr(app_module.messagebox, 'askyesno', lambda *a, **kw: False)
    def forbidden(*a, **kw): pytest.fail('Cancellation reached export or completion')
    monkeypatch.setattr(app_module, 'PostSelectedExportActionDialog', forbidden)
    monkeypatch.setattr(app_module.messagebox, 'showinfo', forbidden)
    monkeypatch.setattr(s, 'export_report', forbidden)
    monkeypatch.setattr(s, 'export_selected_tasks_report', forbidden)
    monkeypatch.setattr(app_module.filedialog, 'asksaveasfilename',
                        forbidden if where in ('overlap', 'selected-dialog') else lambda **kw: '')
    before = evidence(s)
    assert (owner.export() if where == 'full-file' else owner.export_selected_tasks()) is False
    assert_preserved(s, before, [])
    assert calls == [] and not owner.ui_settings_store.path.exists()


@pytest.mark.parametrize('selected', [False, True])
@pytest.mark.parametrize('failure', ['write', 'backup'])
def test_export_failure_does_not_proceed_to_completion(
        running, export_owner, monkeypatch, tmp_path, selected, failure):
    s, a, *_ = running
    owner, calls = export_owner
    selected_input(owner, [a], monkeypatch)
    target = tmp_path / 'failed.txt'
    monkeypatch.setattr(app_module.filedialog, 'asksaveasfilename', lambda **kw: str(target))
    error = OSError('injected export failure')
    def fail(*a, **kw): raise error
    def forbidden(*a, **kw): pytest.fail('Failed export reached completion')
    monkeypatch.setattr(app_module, 'PostSelectedExportActionDialog', forbidden)
    monkeypatch.setattr(app_module.messagebox, 'showinfo', forbidden)
    monkeypatch.setattr(app_module.messagebox, 'askyesno', forbidden)
    if failure == 'write': monkeypatch.setattr(app_module, 'write_export_file', fail)
    else: monkeypatch.setattr(s.backups, 'create_safety_backup', fail)
    before = evidence(s)
    with pytest.raises(OSError) as raised:
        (owner.export_selected_tasks if selected else owner.export)()
    assert raised.value is error
    assert_preserved(s, before, [])
    assert calls == [] and not owner.ui_settings_store.path.exists() and not target.exists()
    # A pre-export backup may have completed before a file-write failure.
    assert bool(s.list_managed_backups()) is (failure == 'write')


def test_selected_delete_retains_scoping_backup_selection_cleanup_and_explicit_stop(
        running, export_owner, monkeypatch, tmp_path):
    s, a, b, clock = running
    owner, calls = export_owner
    child = s.create_subtask(a, 'Child', '')
    selected_input(owner, [a], monkeypatch)
    target = tmp_path / 'deleted-after-export.txt'
    monkeypatch.setattr(app_module.filedialog, 'asksaveasfilename', lambda **kw: str(target))
    monkeypatch.setattr(app_module, 'PostSelectedExportActionDialog', lambda parent: SimpleNamespace(choice='delete'))
    monkeypatch.setattr(app_module.messagebox, 'showinfo', lambda *a, **kw: None)
    before = evidence(s)
    assert owner.export_selected_tasks() is True
    assert s.state.tasks[a].is_deleted and s.state.tasks[child].is_deleted
    assert s.state.tasks[b] == before[0].tasks[b] and s.state.running_task_id is None
    assert s.state.tasks[a].intervals.keys() >= before[0].tasks[a].intervals.keys()
    for key, record in before[0].tasks[a].intervals.items(): assert s.state.tasks[a].intervals[key] == record
    assert s.state.tasks[a].dated_durations == before[0].tasks[a].dated_durations
    added = s.events[len(before[1]):]
    assert [e['event_type'] for e in added].count('stopped') == 1
    assert [e['event_type'] for e in added].count('task_deleted') == 2
    assert not any(e['event_type'] in ('reset', 'export_checkpoint') for e in added)
    assert s.events[:len(before[1])] == before[1]
    assert sorted(s.storage.iter_all_events(strict=True), key=lambda e: e['_read_sequence'])[:len(before[2])] == before[2]
    assert calls == [('clear', (a,)), 'structure', 'live'] and owner.selected_task_id is None
    assert {entry.reason for entry in s.list_managed_backups()} == {
        'safety: before selected export', 'safety: before deleting selected exported tasks'}


def test_constructed_task_panel_and_menus_have_only_surviving_actions(controls, monkeypatch):
    owner = controls
    buttons = [w.options['text'] for w in owner.root.tk.widgets.values()
               if hasattr(w, 'options') and 'command' in w.options and 'text' in w.options]
    assert buttons == ['Start', 'Delete', 'Move Task', 'Edit Task', 'Work History']
    class Menu:
        def __init__(self, *a, **kw): self.items = []
        def add_command(self, **kw): self.items.append(('command', kw))
        def add_separator(self): self.items.append(('separator', {}))
        def add_cascade(self, **kw): self.items.append(('cascade', kw))
    monkeypatch.setattr(app_module.tk, 'Menu', Menu)
    owner.root.configure = lambda **kw: setattr(owner.root, 'menu', kw['menu'])
    owner._build_menus()
    tools = next(item['menu'] for kind, item in owner.root.menu.items if item.get('label') == 'Tools')
    assert [item['label'] for kind, item in tools.items if kind == 'command'] == [
        'Reopen Last Export Checkpoint', 'Manage Tags', 'Manage Subtask Templates', 'Month-End Reminder Settings']
    assert [kind for kind, item in tools.items] == ['command', 'separator', 'command', 'command', 'command']


@pytest.mark.parametrize('choice', ['leave', 'delete', 'wm'])
def test_constructed_post_export_choices_and_close_as_leave(controls, monkeypatch, choice):
    owner = controls
    monkeypatch.setattr(Window, 'resizable', lambda *a: None, raising=False)
    constructed = []
    original = dialogs.PostSelectedExportActionDialog.__init__
    def observe(self, *a, **kw):
        constructed.append(self)
        original(self, *a, **kw)
    monkeypatch.setattr(dialogs.PostSelectedExportActionDialog, '__init__', observe)
    def drive(window):
        current = constructed[0]
        buttons = [w for w in window.tk.widgets.values() if hasattr(w, 'options') and 'command' in w.options
                   and w.options.get('text') in ('Leave tasks unchanged', 'Delete/remove selected tasks from active list')]
        assert {w.options['text'] for w in buttons} == {'Leave tasks unchanged', 'Delete/remove selected tasks from active list'}
        assert not any('Reset' in w.options.get('text', '') for w in window.tk.widgets.values() if hasattr(w, 'options'))
        if choice == 'wm': window.bindings['WM_DELETE_WINDOW']()
        else: next(w for w in buttons if w.options['text'].startswith('Leave' if choice == 'leave' else 'Delete')).invoke()
    Window.wait_action = drive
    result = dialogs.PostSelectedExportActionDialog(owner.root)
    assert result.choice == ('leave' if choice == 'wm' else choice)


@pytest.fixture
def desktop(running, tk_root, monkeypatch):
    """Actual application, controls, menus and services on a disposable dataset."""
    s, a, b, clock = running
    monkeypatch.setattr(app_module, 'install_zoom_guard', lambda root: None)
    monkeypatch.setattr(app_module.TaskTimerApp, '_tick', lambda self: None)
    monkeypatch.setattr(app_module.TaskTimerApp, '_maybe_show_startup_reminder_popup', lambda self: None)
    owner = app_module.TaskTimerApp(tk_root, s)
    owner._local_today = lambda: date(2026, 10, 30)
    tk_root.update()
    forbid_reset(s, monkeypatch)
    return owner


def all_buttons(widget):
    result = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Button): result.append(child)
        result.extend(all_buttons(child))
    return result


def test_real_tk_controls_tools_menu_start_stop_and_work_history(
        running, desktop, tk_root, pointer, monkeypatch):
    s, a, b, clock = running
    owner = desktop
    select_task(owner, b)
    labels = [button.cget('text') for button in all_buttons(tk_root)]
    assert 'Start' in labels and 'Work History' in labels
    assert not any('reset' in label.casefold() for label in labels)
    menubar = tk_root.nametowidget(tk_root.cget('menu'))
    tools = tk_root.nametowidget(menubar.entrycget('Tools', 'menu'))
    labels = [tools.entrycget(i, 'label') for i in range(tools.index('end') + 1) if tools.type(i) == 'command']
    assert labels == ['Reopen Last Export Checkpoint', 'Manage Tags', 'Manage Subtask Templates', 'Month-End Reminder Settings']
    visited = []
    # Isolate the selected surviving command's effect, retaining actual menu wiring.
    tk_root.nametowidget(menubar.entrycget('Tools', 'menu')).entryconfigure('Manage Tags', command=lambda: visited.append('tags'))
    tools.post(100, 100)
    index = tools.index('Manage Tags')
    pointer.click(tools, x_offset=30, y_offset=tools.yposition(index) + 8)
    assert visited == ['tags']
    tools.unpost()
    before = len(s.events)
    pointer.click(owner.selected_toggle_btn)
    assert s.state.running_task_id == b and s.state.tasks[b].is_running
    clock[0] += timedelta(minutes=1)
    pointer.click(owner.selected_toggle_btn)
    assert s.state.running_task_id is None and not s.state.tasks[b].is_running
    assert [e['event_type'] for e in s.events[before:]] == ['stopped', 'started', 'stopped']
    captured = evidence(s)
    def browse(wrapper):
        assert wrapper.browser.task_id == b and wrapper.browser._rows
        assert {row['duration_seconds'] for row in wrapper.browser._rows} == {60}
        pointer.click(wrapper.close_button)
    failures, job = modal_action(tk_root, owner, browse)
    pointer.click(owner.selected_history_btn)
    tk_root.after_cancel(job)
    assert failures == []
    assert_preserved(s, captured, [])


@pytest.mark.parametrize('route', ['toolbar', 'banner', 'close'])
def test_real_tk_export_controls_do_not_offer_reset_or_stop_running_work(
        running, desktop, tk_root, pointer, monkeypatch, tmp_path, route):
    s, a, b, clock = running
    owner = desktop
    target = tmp_path / f'{route}.txt'
    monkeypatch.setattr(app_module.filedialog, 'asksaveasfilename', lambda **kw: str(target))
    def no_prompt(*a, **kw): pytest.fail('Unexpected export completion prompt')
    monkeypatch.setattr(app_module.messagebox, 'askyesno', no_prompt)
    before = evidence(s)
    if route == 'toolbar':
        pointer.click(next(button for button in owner.toolbar_frame.winfo_children()
                           if isinstance(button, ttk.Button) and button.cget('text') == 'Export'))
    elif route == 'banner':
        owner.ui_settings.month_end_reminder_enabled = True
        owner._refresh_month_end_reminder_ui()
        pointer.click(next(button for button in owner.reminder_banner.winfo_children() if isinstance(button, ttk.Button) and button.cget('text') == 'Export'))
    else:
        owner.ui_settings.month_end_reminder_enabled = True
        owner.ui_settings.month_end_reminder_show_close_notice = True
        errors = []
        def choose():
            try:
                top = next(w for w in tk_root.winfo_children() if isinstance(w, tk.Toplevel))
                assert top.title() == 'Month-End Reminder'
                pointer.click(next(b for b in all_buttons(top) if b.cget('text') == 'Export Time'))
            except BaseException as exc:
                errors.append(exc)
                for w in tk_root.winfo_children():
                    if isinstance(w, tk.Toplevel): w.destroy()
        tk_root.after(100, choose)
        # Deliver WM close through Tk's registered production close handler.
        tk_root.tk.call(tk_root.protocol('WM_DELETE_WINDOW'))
        assert errors == [] and tk_root.winfo_exists()
    assert_preserved(s, before, ['export_checkpoint'])
    assert target.is_file()
    assert owner.ui_settings_store.load().month_end_reminder_last_dismissed_local_date == '2026-10-30'


@pytest.mark.parametrize('choice', ['leave', 'delete', 'wm'])
def test_real_tk_selected_export_file_menu_and_remaining_post_choices(
        running, desktop, tk_root, pointer, monkeypatch, tmp_path, choice):
    s, a, b, clock = running
    owner = desktop
    target = tmp_path / f'selected-{choice}.txt'
    monkeypatch.setattr(app_module.filedialog, 'asksaveasfilename', lambda **kw: str(target))
    monkeypatch.setattr(app_module.messagebox, 'showinfo', lambda *a, **kw: None)
    select_task(owner, a)
    before, errors = evidence(s), []
    def post_action():
        try:
            top = next(w for w in tk_root.winfo_children() if isinstance(w, tk.Toplevel))
            assert top.title() == 'Selected Export Complete'
            buttons = all_buttons(top)
            assert [button.cget('text') for button in buttons] == [
                'Leave tasks unchanged', 'Delete/remove selected tasks from active list']
            if choice == 'wm': top.tk.call(top.protocol('WM_DELETE_WINDOW'))
            else: pointer.click(next(button for button in buttons if button.cget('text').startswith('Leave' if choice == 'leave' else 'Delete')))
        except BaseException as exc:
            errors.append(exc)
            for w in tk_root.winfo_children():
                if isinstance(w, tk.Toplevel): w.destroy()
    def prepare():
        try:
            top = next(w for w in tk_root.winfo_children() if isinstance(w, tk.Toplevel))
            assert top.title() == 'Export Selected Tasks'
            # Interact with the actual dialog through its checkbox and export button.
            def children(w):
                for c in w.winfo_children():
                    yield c
                    yield from children(c)
            checks = [w for w in children(top) if isinstance(w, ttk.Checkbutton)]
            task_check = next(w for w in checks if w.cget('text').startswith('A —'))
            pointer.click(task_check)
            mark = next(w for w in checks if 'Mark exported time' in w.cget('text'))
            # Keep this real-Tk path focused on Leave/Delete; marker effects have real-service coverage above.
            if mark.instate(['selected']): pointer.click(mark)
            top.bind('<Destroy>', lambda event: tk_root.after(100, post_action) if event.widget is top else None, add='+')
            pointer.click(next(button for button in all_buttons(top) if button.cget('text') == 'Export Selected'))
        except BaseException as exc:
            errors.append(exc)
            for w in tk_root.winfo_children():
                if isinstance(w, tk.Toplevel): w.destroy()
    menu = tk_root.nametowidget(tk_root.nametowidget(tk_root.cget('menu')).entrycget('File', 'menu'))
    def timeout():
        errors.append(AssertionError('Selected-export interaction timed out'))
        for window in tuple(tk_root.winfo_children()):
            if isinstance(window, tk.Toplevel): window.destroy()
    watchdog = tk_root.after(6000, timeout)
    tk_root.after(100, prepare)
    menu.post(100, 100)
    pointer.click(menu, x_offset=60, y_offset=menu.yposition(menu.index('Export Selected Tasks...')) + 8)
    menu.unpost()
    tk_root.after_cancel(watchdog)
    assert errors == [] and target.is_file()
    if choice == 'delete':
        assert s.state.tasks[a].is_deleted and s.state.running_task_id is None
        assert owner.selected_task_id is None and not owner.task_tree.selection()
        assert not any(e['event_type'] == 'reset' for e in s.events[len(before[1]):])
    else:
        assert_preserved(s, before, [])
