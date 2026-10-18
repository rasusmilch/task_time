"""Shipped Work History controls, shared ownership and real-Tk operator routing."""

from copy import deepcopy
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from task_timer import app as app_module, dialogs
from task_timer.settings import UISettings, UISettingsStore
from test_mixed_accounting import setup, dated, local, MON, TUE
from test_work_history import interval, capture
from test_work_history_view import Variable, make_view
from test_work_history_browser import spy, build
from test_history_session_direction import owner_factory
from test_history_window import owned_ui, Window, tk_root, pointer, modal_action


@pytest.fixture
def controls(owned_ui, monkeypatch):
    """Construct the real shipped panel/editors; isolate unrelated Tk/tag effects."""
    class Control:
        serial = 0
        def __init__(self, parent, **options):
            self.master, self.tk = parent, parent.tk
            self.options, self.visible, self.exists = options, False, True
            self.children, self.widgets = {}, []
            self._name = f'control{Control.serial}'
            Control.serial += 1
            self._w = parent._w + '.' + self._name
            self.tk.widgets[self._w] = self
            parent.children[self._name] = self
        def grid(self, **kw): self.visible = True
        pack = grid
        def grid_remove(self): self.visible = False
        def grid_columnconfigure(self, *a, **kw): pass
        grid_rowconfigure = grid_columnconfigure
        def configure(self, **kw): self.options.update(kw)
        def invoke(self):
            if self.options.get('state') != 'disabled': return self.options['command']()
    for name in ('Frame', 'Label', 'Button'):
        monkeypatch.setattr(ttk, name, Control)
    monkeypatch.setattr(app_module.tk, 'Label', Control)
    monkeypatch.setattr(app_module, 'StringVar', lambda value='': Variable(None, value))
    monkeypatch.setattr(app_module.tk, 'StringVar', lambda value='': Variable(None, value))
    monkeypatch.setattr(dialogs, 'StringVar', lambda value='': Variable(None, value))
    monkeypatch.setattr(dialogs, 'Toplevel', Window)
    monkeypatch.setattr(Window, 'geometry', lambda *a: None, raising=False)
    monkeypatch.setattr(dialogs, 'TagSelectionFrame', lambda *a, **kw: SimpleNamespace(grid=lambda **kw: None))
    owner = owned_ui
    owner.root.wait_window = lambda window: window.wait_window()
    owner.root.cget = lambda key: '#ffffff'
    owner.table_frame = owner.root
    owner._refresh_selected_task_panel = app_module.TaskTimerApp._refresh_selected_task_panel.__get__(owner)
    owner._selected_task_id = lambda: owner.selected_task_id
    owner.selected_task_id = None
    owner._build_selected_task_panel()
    return owner


def test_constructed_main_command_enablement_and_exact_adapter_arguments(setup, controls, monkeypatch):
    s, a, b, *_ = setup
    owner = controls
    calls = []
    monkeypatch.setattr(owner, '_open_history_window', lambda *a, **kw: calls.append((a, kw)))
    assert owner.selected_history_btn.options['text'] == 'Work History'
    assert owner.selected_history_btn.options['state'] == 'disabled'
    owner.selected_history_btn.invoke()
    assert calls == []
    owner.selected_task_id = a
    owner._refresh_selected_task_panel()
    assert owner.selected_history_btn.options['state'] == 'normal'
    owner.selected_history_btn.invoke()
    assert calls == [((s, a), dict(modal_parent=owner.root, now_utc=app_module.utc_now, week_start=6))]
    owner._set_history_launch_error('old failure')
    owner._refresh_selected_task_panel()
    assert owner.history_launch_error_label.visible
    owner.selected_task_id = b
    owner._refresh_selected_task_panel()
    assert not owner.history_launch_error_label.visible and owner.history_launch_error_var.get() == ''
    owner.selected_task_id = None
    owner._refresh_selected_task_panel()
    owner._open_selected_history()
    assert len(calls) == 1 and owner.selected_history_btn.options['state'] == 'disabled'


@pytest.mark.parametrize('origin', ['main', 'editor'])
@pytest.mark.parametrize('destroy', [False, True])
def test_launch_error_preserves_original_diagnostics_without_grab_or_focus_changes(
        setup, controls, monkeypatch, origin, destroy):
    s, a, *_ = setup
    owner = controls
    owner.selected_task_id = a
    owner._refresh_selected_task_panel()
    reports = []
    owner.root.report_callback_exception = lambda *a: reports.append(a)
    error = RuntimeError('launch failed')
    error.add_note('original cleanup detail')
    def fail(*a, **kw):
        assert not current.history_launch_error_label.visible
        assert current.history_launch_error_var.get() == ''
        if destroy: current.history_launch_error_label.exists = False
        raise error
    monkeypatch.setattr(owner, '_open_history_window', fail)
    current = owner
    def check(window):
        nonlocal current
        editor = next_editor[0]
        current = editor
        editor._set_history_launch_error('previous launch error')
        editor.history_button.invoke()
        assert not editor.changed
        window.destroy()
    next_editor = []
    if origin == 'editor':
        # Use a maximum-depth real task so no unrelated subtask Treeview double is needed.
        child = s.create_subtask(a, 'Child', '')
        leaf = s.create_subtask(child, 'Leaf', '')
        init = dialogs.EditTaskDialog.__init__
        def observe(self, *a, **kw):
            next_editor.append(self)
            init(self, *a, **kw)
        monkeypatch.setattr(dialogs.EditTaskDialog, '__init__', observe)
        Window.wait_action = check
        dialogs.EditTaskDialog(owner.root, s, leaf, open_history=owner._open_task_history)
    else:
        owner._set_history_launch_error('previous launch error')
        owner.selected_history_btn.invoke()
    assert reports[0][0] is RuntimeError and reports[0][1] is error
    assert reports[0][2] is error.__traceback__ and error.__notes__ == ['original cleanup detail']
    if not destroy:
        assert current.history_launch_error_label.visible
        assert current.history_launch_error_var.get().startswith('Unable to open work history:')
    assert Window.grabbed is None
    assert owner.root.tk.focus is None


@pytest.fixture
def live_owner(setup, tk_root, monkeypatch):
    """Real application constructor and shipped controls; unrelated startup isolated."""
    s = setup[0]
    monkeypatch.setattr(app_module, 'install_zoom_guard', lambda root: None)
    def build(owner):
        owner.table_frame = ttk.Frame(owner.root)
        owner.table_frame.pack(fill='both', expand=True)
        owner._build_task_tree()
        owner._build_selected_task_panel()
    monkeypatch.setattr(app_module.TaskTimerApp, '_build_ui', build)
    for name in ('_refresh_month_end_reminder_ui', '_maybe_show_startup_reminder_popup', '_tick'):
        monkeypatch.setattr(app_module.TaskTimerApp, name, lambda self: None)
    monkeypatch.setattr(UISettingsStore, 'load', lambda self: UISettings())
    return app_module.TaskTimerApp(tk_root, s)


def select_task(owner, task):
    owner.task_tree.selection_set(task)
    owner.task_tree.focus(task)
    owner.selected_task_id = task
    owner._refresh_selected_task_panel()


def test_real_tk_main_control_browser_failures_refresh_and_session_reopening(
        setup, live_owner, tk_root, pointer, monkeypatch):
    s, a, b, _, _, clock = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated(s, a, TUE, 119.9)
    clock[0] = local(s, TUE, 12)
    s.start_task(b)
    owner = live_owner
    owner.refresh_structure()
    select_task(owner, a)
    before = capture(s)
    calls = spy(s, monkeypatch)
    original_read = s.get_task_work_history
    errors = [True]
    def read(*a, **kw):
        if errors[0]: raise RuntimeError('injected load failure')
        return original_read(*a, **kw)
    monkeypatch.setattr(s, 'get_task_work_history', read)
    def forbidden(*a, **kw): pytest.fail('History command mutated domain/settings or refreshed its origin')
    monkeypatch.setattr(owner, '_after_state_change', forbidden)
    monkeypatch.setattr(UISettingsStore, 'save', forbidden)
    monkeypatch.setattr(s, '_append', forbidden)
    def inspect(wrapper):
        browser = wrapper.browser
        assert wrapper.window.master is tk_root and browser.task_id == a
        assert browser._rows is None and browser.info_var.get() == 'Not loaded'
        assert browser.error_label.winfo_ismapped() and not owner.history_launch_error_label.winfo_ismapped()
        errors[0] = False
        pointer.click(browser.refresh_button)
        assert len(browser._rows) == 3 and len(calls) == 1
        assert {row['entry_kind'] for row in browser._rows} == {'interval', 'dated_duration'}
        portions = [row for row in browser._rows if row['entry_kind'] == 'interval']
        assert len({row['entry_id'] for row in portions}) == 1
        assert sorted(row['duration_seconds'] for row in portions) == [14400, 28800]
        assert all(row['original_start_utc'] == local(s, MON, 20).astimezone(app_module.timezone.utc)
                   and row['original_stop_utc'] == local(s, TUE, 8).astimezone(app_module.timezone.utc)
                   for row in portions)
        assert next(row for row in browser._rows if row['entry_kind'] == 'dated_duration')['duration_seconds'] == 119.9
        assert list(browser.history._rows_by_iid.values()) == browser._rows
        pointer.click(browser.period_buttons['Custom'])
        browser.start_var.set(str(MON))
        browser.end_var.set(str(TUE))
        assert len(calls) == 1  # Drafting alone cannot load.
        pointer.click(browser.apply_button)
        assert browser._applied == ('Custom', MON, TUE) and len(calls) == 2
        old, cutoff = deepcopy(browser._rows), browser._cutoff_utc
        pointer.click(owner.selected_toggle_btn)  # Server input must be blocked by history.
        assert s.state.tasks[b].is_running and not s.state.tasks[a].is_running
        wrapper.window.focus_force()
        tk_root.update()
        ticks = []
        tk_root.after(0, lambda: ticks.append(True))
        tk_root.update()
        assert ticks == [True]
        errors[0] = True
        pointer.click(browser.refresh_button)
        assert browser._rows == old and browser._cutoff_utc == cutoff
        assert browser.error_label.winfo_ismapped()
        # Actual Date-header mouse input; sorting neither reloads nor advances cutoff.
        tree = browser.history.tree
        x = tree.column('#1', 'width') + tree.column('#2', 'width') // 2
        pointer.click(tree, x_offset=x, y_offset=5)
        assert browser.newest_first is False and owner._history_newest_first is False
        assert browser._cutoff_utc == cutoff and len(calls) == 2
        pointer.click(wrapper.close_button)
    failures, job = modal_action(tk_root, owner, inspect)
    pointer.click(owner.selected_history_btn)
    tk_root.after_cancel(job)
    assert failures == [] and capture(s) == before
    select_task(owner, b)
    errors[0] = False
    def empty(wrapper):
        assert wrapper.browser.task_id == b and not wrapper.browser.newest_first
        # The running timer starts exactly at this cutoff, yielding valid empty history.
        assert wrapper.browser._rows == [] and wrapper.browser._applied is not None
        pointer.click(wrapper.close_button)
    failures, job = modal_action(tk_root, owner, empty)
    pointer.click(owner.selected_history_btn)
    tk_root.after_cancel(job)
    assert failures == [] and capture(s) == before


def test_real_tk_recursive_editor_controls_share_owner_preserve_drafts_and_calendars(
        setup, live_owner, tk_root, pointer, monkeypatch):
    s, a, _, _, _, clock = setup
    child = s.create_subtask(a, 'Child', '')
    leaf = s.create_subtask(child, 'Leaf', '')
    dated(s, leaf, MON, 50400.125)
    interval(s, leaf, local(s, MON, 20), local(s, TUE, 8))
    clock[0] = local(s, TUE, 12)
    owner = live_owner
    owner.refresh_structure()
    select_task(owner, a)
    before = capture(s)
    calls = spy(s, monkeypatch)
    def forbidden(*a, **kw): pytest.fail('History changed work/settings or refreshed the origin')
    monkeypatch.setattr(owner, '_after_state_change', forbidden)
    monkeypatch.setattr(UISettingsStore, 'save', forbidden)
    monkeypatch.setattr(s, '_append', forbidden)
    editors, failures, visited = [], [], []
    init = dialogs.EditTaskDialog.__init__
    def observe(editor, *a, **kw):
        editors.append(editor)
        assert kw['open_history'] == owner._open_task_history
        init(editor, *a, **kw)
    monkeypatch.setattr(dialogs.EditTaskDialog, '__init__', observe)
    def safe(action):
        def run():
            try: action()
            except BaseException as exc:
                failures.append(exc)
                if owner._history_window: owner._history_window.close()
                for e in reversed(editors):
                    if owner._history_widget_exists(e.window): e.window.destroy()
        return run
    def visit(level):
        editor = editors[-1]
        task = (a, child, leaf)[level]
        assert editor.task_id == task
        editor.name_var.set('Unsaved name')
        editor.notes_var.set('Unsaved notes')
        editor.tag_selector.set_selected_tags(['draft-only'])
        draft = (editor.name_var.get(), editor.notes_var.get(), editor.tag_selector.get_selected_tags(), editor.changed, editor.added_subtask)
        field = next(w for w in editor.window.winfo_children() if isinstance(w, ttk.Entry) and w.cget('textvariable') == str(editor.name_var))
        field.selection_range(1, 4)
        field.icursor(2)
        pointer.click(field)
        field.selection_range(1, 4)
        field.icursor(2)
        field.focus_set()
        tk_root.update()
        def inspect(wrapper):
            browser = wrapper.browser
            assert wrapper.window.master is editor.window and browser.task_id == task
            assert browser.newest_first is (level % 2 == 0)
            visited.append(task)
            count = len(calls)
            pointer.click(owner.selected_toggle_btn)
            pointer.click(editor.history_button)
            assert owner._history_window is wrapper and len(calls) == count
            wrapper.window.focus_force()
            tk_root.update()
            pointer.click(browser.period_buttons['Custom'])
            pointer.click(browser.picker_buttons['Start'])
            popup, calendar = next(iter(browser._pickers.items()))
            day = next(label for week in calendar._calendar for label in week if label.cget('text') == '12')
            pointer.click(day)
            assert browser.start_var.get() == str(MON) and len(calls) == count
            pointer.click(browser.picker_buttons['End'])
            next(iter(browser._pickers)).focus_force()
            tk_root.update()
            pointer.escape()
            assert not browser._pickers and wrapper.window.grab_current() is wrapper.window
            # The existing table's command is already covered by server input in the main case.
            browser.history.tree.tk.call(browser.history.tree.heading('date', 'command'))
            assert len(calls) == count
            pointer.click(wrapper.close_button)
        inner, job = modal_action(tk_root, owner, inspect)
        pointer.click(editor.history_button)
        tk_root.after_cancel(job)
        assert inner == []
        assert editor.window.grab_current() is editor.window and editor.window.focus_get() is editor.history_button
        assert (field.index('sel.first'), field.index('sel.last'), field.index('insert')) == (1, 4, 2)
        assert (editor.name_var.get(), editor.notes_var.get(), editor.tag_selector.get_selected_tags(), editor.changed, editor.added_subtask) == draft
        if level < 2:
            editor.subtask_tree.selection_set((child, leaf)[level])
            saved_selection = editor.subtask_tree.selection()
            tk_root.after(100, safe(lambda: visit(level + 1)))
            button = next(w for frame in editor.window.winfo_children() for w in frame.winfo_children()
                          for w in w.winfo_children() if isinstance(w, ttk.Button) and w.cget('text') == 'Edit Selected Subtask')
            pointer.click(button)
            assert editor.subtask_tree.selection() == saved_selection
        pointer.click(next(w for frame in editor.window.winfo_children() for w in frame.winfo_children()
                           if isinstance(w, ttk.Button) and w.cget('text') == 'Cancel'))
    def timeout():
        failures.append(AssertionError('Production editor route timed out'))
        if owner._history_window: owner._history_window.close()
        for e in reversed(editors):
            if owner._history_widget_exists(e.window): e.window.destroy()
    job = tk_root.after(12000, timeout)
    tk_root.after(100, safe(lambda: visit(0)))
    pointer.click(owner.selected_edit_btn)
    tk_root.after_cancel(job)
    assert failures == [] and visited == [a, child, leaf]
    assert capture(s) == before and not owner._history_window_opening
    assert len(calls) == 3


@pytest.mark.parametrize('origin', ['main', 'editor'])
@pytest.mark.parametrize('destroy_origin', [False, True])
def test_real_tk_launch_failure_keeps_competing_grab_and_original_diagnostics(
        setup, live_owner, tk_root, pointer, monkeypatch, origin, destroy_origin):
    s, a, *_ = setup
    owner = live_owner
    select_task(owner, a)
    reports, editors, failures = [], [], []
    tk_root.report_callback_exception = lambda *args: reports.append(args)
    error = RuntimeError('presentation conflict')
    error.add_note('original acquisition diagnostics')
    competitor = tk.Toplevel(tk_root)
    competitor.withdraw()
    competitor_field = ttk.Entry(competitor)
    competitor_field.pack()
    init = dialogs.EditTaskDialog.__init__
    def observe(editor, *args, **kw):
        editors.append(editor)
        init(editor, *args, **kw)
    monkeypatch.setattr(dialogs.EditTaskDialog, '__init__', observe)
    def fail(service, task, **kw):
        assert service is s and task == a
        parent = kw['modal_parent']
        assert parent is (tk_root if origin == 'main' else editors[-1].window)
        competitor.deiconify()
        if not competitor.winfo_viewable(): competitor.wait_visibility()
        competitor.grab_set()
        competitor_field.focus_force()
        tk_root.update()
        if destroy_origin:
            # Destroy the actual origin (and its label), not merely a label double.
            parent.destroy()
        raise error
    monkeypatch.setattr(owner, '_open_history_window', fail)
    def inspect_editor():
        try:
            editor = editors[-1]
            pointer.click(editor.history_button)
            assert not editor.changed
            if not destroy_origin:
                assert editor.history_launch_error_label.winfo_ismapped()
                assert editor.history_launch_error_var.get().startswith('Unable to open work history:')
                assert tk_root.grab_current() is competitor and tk_root.focus_get() is competitor_field
                competitor.grab_release()
                editor.window.destroy()
        except BaseException as exc:
            failures.append(exc)
            if owner._history_widget_exists(tk_root):
                for editor in editors:
                    if owner._history_widget_exists(editor.window): editor.window.destroy()
    if origin == 'main':
        pointer.click(owner.selected_history_btn)
        if not destroy_origin:
            assert owner.history_launch_error_label.winfo_ismapped()
            assert owner.history_launch_error_var.get().startswith('Unable to open work history:')
            assert tk_root.grab_current() is competitor and tk_root.focus_get() is competitor_field
            competitor.grab_release()
    else:
        watchdog = tk_root.after(4000, lambda: [editor.window.destroy() for editor in editors
                                              if owner._history_widget_exists(editor.window)])
        tk_root.after(100, inspect_editor)
        pointer.click(owner.selected_edit_btn)
        if owner._history_widget_exists(tk_root): tk_root.after_cancel(watchdog)
    assert failures == []
    assert len(reports) == 1 and reports[0][0] is RuntimeError and reports[0][1] is error
    assert reports[0][2] is error.__traceback__ and error.__notes__ == ['original acquisition diagnostics']
    if owner._history_widget_exists(tk_root):
        competitor.destroy()


def test_real_tk_unsupported_work_is_browser_error_without_legacy_fallback(
        setup, live_owner, tk_root, pointer):
    s, a, _, _, _, clock = setup
    interval(s, a, local(s, MON, 9), local(s, MON, 10))
    dated(s, a, MON, 60)
    # Deliberately unsupported synthetic evidence in this disposable dataset:
    # registration, read-only opening and error display must never convert it.
    s.add_manual_duration(a, MON, 3600, 'Unsupported historical fixture')
    clock[0] = local(s, TUE, 12)
    owner = live_owner
    select_task(owner, a)
    before = capture(s)
    def inspect(wrapper):
        browser = wrapper.browser
        assert browser._rows is None and browser.info_var.get() == 'Not loaded'
        assert 'synthetic' in browser.error_var.get().lower()
        assert browser.error_label.winfo_ismapped() and not owner.history_launch_error_label.winfo_ismapped()
        assert owner._history_window is wrapper
        pointer.click(browser.refresh_button)
        assert browser._rows is None and browser.error_label.winfo_ismapped()
        pointer.click(wrapper.close_button)
    failures, job = modal_action(tk_root, owner, inspect)
    pointer.click(owner.selected_history_btn)
    tk_root.after_cancel(job)
    assert failures == [] and capture(s) == before
