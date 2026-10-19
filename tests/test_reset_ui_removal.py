"""Reset-free shipped controls/export paths; retained backend contracts are separate."""

from copy import deepcopy
from datetime import date, timedelta, timezone
from tkinter import ttk

import pytest

from task_timer import app as app_module
from task_timer.settings import BackupSettings
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
        'Manage Tags', 'Manage Subtask Templates', 'Month-End Reminder Settings']
    assert [kind for kind, item in tools.items] == ['command', 'command', 'command']


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
    assert labels == ['Manage Tags', 'Manage Subtask Templates', 'Month-End Reminder Settings']
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
