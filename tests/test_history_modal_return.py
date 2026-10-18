"""Originating-parent validation and return, with real nested-editor Tk evidence."""

from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import pytest

from task_timer import app as app_module, dialogs
from task_timer.settings import UISettingsStore
from test_mixed_accounting import setup, dated, local, MON, TUE
from test_work_history import capture, interval
from test_work_history_view import make_view
from test_work_history_browser import build, Clock, spy
from test_history_session_direction import owner_factory
from test_history_window import owned_ui, Window, Root, tk_root, pointer, modal_action


class Focus(tk.Misc):
    def __init__(self, parent):
        self.master, self.tk = parent, parent.tk
        self._name = 'focus'
        parent.children[self._name] = self
        self._w, self.exists, self.focuses = parent._w + '.focus', True, 0
        self.tk.widgets[self._w] = self

    def winfo_toplevel(self):
        return self.master

    def focus_set(self):
        self.focuses += 1
        self.tk.focus = self


@pytest.mark.parametrize('how', ['close', 'wm', 'external'])
@pytest.mark.parametrize('prior', [False, True])
def test_explicit_parent_normal_return_restores_only_captured_grab_and_focus(
        setup, owned_ui, how, prior):
    s, a, *_ = setup
    parent = Window(owned_ui.root)
    focus = Focus(parent)
    parent.tk.focus = focus
    if prior:
        parent.grab_set()
    before = capture(s)
    clock = Clock(local(s, TUE, 12))
    def drive(window):
        wrapper = owned_ui._history_window
        assert window.master is parent and wrapper.browser.task_id == a
        assert owned_ui._history_window_opening
        if how == 'close': wrapper.close()
        elif how == 'wm': window.bindings['WM_DELETE_WINDOW']()
        else: window.destroy()
        assert owned_ui._history_window is None and owned_ui._history_window_opening
        assert focus.focuses == 0  # Restoration is outside the Destroy callback.
    Window.wait_action = drive
    owned_ui._open_history_window(s, a, now_utc=clock, modal_parent=parent)
    assert parent.tk.focus is focus and focus.focuses == 1
    assert Window.grabbed is (parent if prior else None)
    assert parent.acquisitions == (2 if prior else 0)
    assert not owned_ui._history_window_opening and capture(s) == before


def test_root_default_and_already_held_parent_grab_avoid_reacquisition(setup, owned_ui):
    s, a, *_ = setup
    root = owned_ui.root
    root.grab_set()
    focus = Focus(root)
    root.tk.focus = focus
    def drive(window):
        assert window.master is root
        owned_ui._history_window.close()
        root.grab_set()  # Another callback already returned this captured grab.
    Window.wait_action = drive
    owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)))
    assert root.acquisitions == 2 and Window.grabbed is root and root.tk.focus is focus


@pytest.mark.parametrize('focus_kind', ['none', 'destroyed', 'other-top'])
def test_missing_or_outside_saved_focus_falls_back_to_origin(setup, owned_ui, focus_kind):
    s, a, *_ = setup
    parent = Window(owned_ui.root)
    saved = None if focus_kind == 'none' else Focus(parent if focus_kind == 'destroyed' else owned_ui.root)
    parent.tk.focus = saved
    def drive(window):
        if focus_kind == 'destroyed': saved.exists = False
        owned_ui._history_window.close()
    Window.wait_action = drive
    owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)), modal_parent=parent)
    assert parent.tk.focus is parent and Window.grabbed is None


@pytest.mark.parametrize('kind', ['object', 'child', 'destroyed', 'foreign-root', 'foreign-top'])
def test_invalid_parent_rejected_without_widget_clock_or_work_access(setup, owned_ui, monkeypatch, kind):
    s, a, *_ = setup
    if kind == 'object': parent = object()
    elif kind == 'child': parent = Focus(owned_ui.root)
    elif kind == 'destroyed':
        parent = Window(owned_ui.root)
        parent.destroy()
    elif kind == 'foreign-root': parent = Root()
    else: parent = Window(Root())
    count, before = len(Window.created), capture(s)
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid parent caused construction, clock capture or reading work')
    monkeypatch.setattr(owned_ui, '_make_history_browser', forbidden)
    monkeypatch.setattr(s, 'get_task_work_history', forbidden)
    with pytest.raises(ValueError, match='live top-level'):
        owned_ui._open_history_window(s, a, now_utc=forbidden, modal_parent=parent)
    assert len(Window.created) == count and capture(s) == before
    assert owned_ui._history_window is None and not owned_ui._history_window_opening


@pytest.mark.parametrize('kind', ['unrelated-local', 'unrelated-global', 'parent-global'])
def test_initial_grab_conflicts_are_rejected_unchanged_before_loading(setup, owned_ui, monkeypatch, kind):
    s, a, *_ = setup
    parent = Window(owned_ui.root)
    grab = parent if kind == 'parent-global' else Window(owned_ui.root)
    grab.status = 'global' if 'global' in kind else 'local'
    grab.grab_set()
    focus = Focus(grab)
    grab.tk.focus = focus
    count = len(Window.created)
    def forbidden(*args, **kwargs):
        pytest.fail('Conflicting grab caused a history load')
    monkeypatch.setattr(owned_ui, '_make_history_browser', forbidden)
    with pytest.raises(ValueError, match='unrelated or global'):
        owned_ui._open_history_window(s, a, now_utc=forbidden, modal_parent=parent)
    assert len(Window.created) == count and Window.grabbed is grab
    assert grab.tk.focus is focus and focus.focuses == grab.releases == 0
    assert not owned_ui._history_window_opening


def test_guard_blocks_invalid_reentry_through_return_after_owned_reference_cleared(setup, owned_ui, monkeypatch):
    s, a, *_ = setup
    parent = Window(owned_ui.root)
    parent.grab_set()
    focus = Focus(parent)
    parent.tk.focus = focus
    restored = []
    original_focus = focus.focus_set
    def restore_focus():
        assert owned_ui._history_window is None and owned_ui._history_window_opening
        count = len(Window.created)
        # Malformed arguments are intentionally not inspected for a duplicate.
        assert owned_ui._open_history_window(object(), None, now_utc=None,
                                            week_start='invalid', modal_parent=object()) is None
        assert len(Window.created) == count
        restored.append(True)
        original_focus()
    monkeypatch.setattr(focus, 'focus_set', restore_focus)
    owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)), modal_parent=parent)
    assert restored == [True] and not owned_ui._history_window_opening


@pytest.mark.parametrize('kind', ['local', 'global'])
def test_competing_return_grab_preserves_its_focus_and_grab(setup, owned_ui, kind):
    s, a, *_ = setup
    parent, competitor = Window(owned_ui.root), Window(owned_ui.root)
    parent.grab_set()
    saved, competing_focus = Focus(parent), Focus(competitor)
    parent.tk.focus = saved
    competitor.status = kind
    def drive(window):
        owned_ui._history_window.close()
        competitor.grab_set()
        competitor.tk.focus = competing_focus
    Window.wait_action = drive
    owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)), modal_parent=parent)
    assert Window.grabbed is competitor and competitor.tk.focus is competing_focus
    assert parent.acquisitions == 1 and saved.focuses == competing_focus.focuses == 0


@pytest.mark.parametrize('kind', ['unrelated', 'global-parent'])
def test_visibility_wait_grab_change_is_rechecked_without_stealing(setup, owned_ui, monkeypatch, kind):
    s, a, *_ = setup
    parent = Window(owned_ui.root)
    grab = Window(owned_ui.root) if kind == 'unrelated' else parent
    grab.status = 'global' if kind == 'global-parent' else 'local'
    focus = Focus(grab)
    def appear(window):
        grab.grab_set()
        grab.tk.focus = focus
    monkeypatch.setattr(Window, 'wait_visibility', appear)
    clock = Clock(local(s, TUE, 12))
    with pytest.raises(ValueError, match='cannot acquire'):
        owned_ui._open_history_window(s, a, now_utc=clock, modal_parent=parent)
    history = Window.created[-1]
    assert not history.exists and history.acquisitions == 0
    assert Window.grabbed is grab and grab.releases == 0
    if kind == 'unrelated': assert grab.tk.focus is focus
    assert clock.calls == 1 and not owned_ui._history_window_opening


@pytest.mark.parametrize('destroy', ['parent', 'root'])
def test_destroyed_origin_skips_restoration_without_redirect(setup, owned_ui, monkeypatch, destroy):
    s, a, *_ = setup
    parent = Window(owned_ui.root)
    focus = Focus(parent)
    parent.tk.focus = focus
    parent.grab_set()
    def drive(window):
        owned_ui._history_window.close()
        if destroy == 'root': owned_ui.root.destroy()
        else: parent.destroy()
    Window.wait_action = drive
    def forbidden(*args):
        pytest.fail('Destroyed origin was focused, grabbed or replaced by an ancestor')
    monkeypatch.setattr(parent, 'focus_set', forbidden)
    monkeypatch.setattr(parent, 'grab_set', forbidden)
    monkeypatch.setattr(owned_ui.root, 'focus_set', forbidden)
    owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)), modal_parent=parent)
    assert focus.focuses == 0 and not owned_ui._history_window_opening


@pytest.mark.parametrize('phase', ['construction', 'acquisition'])
def test_failures_return_to_captured_modal_context_and_allow_retry(setup, owned_ui, monkeypatch, phase):
    s, a, *_ = setup
    parent = Window(owned_ui.root)
    parent.grab_set()
    focus = Focus(parent)
    parent.tk.focus = focus
    before, clock = capture(s), Clock(local(s, TUE, 12))
    original_make, original_grab = owned_ui._make_history_browser, Window.grab_set
    error = RuntimeError(f'{phase} failed')
    with monkeypatch.context() as m:
        if phase == 'construction':
            def fail(*args, **kwargs):
                original_make(*args, **kwargs)
                raise error
            m.setattr(owned_ui, '_make_history_browser', fail)
        else:
            def fail(window):
                original_grab(window)
                if window is not parent: raise error
            m.setattr(Window, 'grab_set', fail)
        with pytest.raises(RuntimeError) as result:
            owned_ui._open_history_window(s, a, now_utc=clock, modal_parent=parent)
    assert result.value is error and Window.grabbed is parent and parent.tk.focus is focus
    assert owned_ui._history_window is None and not owned_ui._history_window_opening
    owned_ui._open_history_window(s, a, now_utc=clock, modal_parent=parent)
    assert capture(s) == before and clock.calls == 2


@pytest.mark.parametrize('primary', [False, True])
@pytest.mark.parametrize('kind', ['focus', 'grab'])
def test_restoration_failure_propagates_or_retains_primary_and_cleanup_diagnostics(
        setup, owned_ui, monkeypatch, primary, kind):
    s, a, *_ = setup
    parent = Window(owned_ui.root)
    parent.grab_set()
    focus = Focus(parent)
    parent.tk.focus = focus
    first, restoration = ValueError('presentation failed'), tk.TclError(f'return {kind} failed')
    def fail_focus(): raise restoration
    with monkeypatch.context() as m:
        m.setattr(focus if kind == 'focus' else parent, 'focus_set' if kind == 'focus' else 'grab_set', fail_focus)
        if primary:
            def fail_present(window): raise first
            def fail_release(window): raise tk.TclError('cleanup release failed')
            m.setattr(Window, 'focus_force', fail_present)
            m.setattr(Window, 'grab_release', fail_release)
        with pytest.raises((ValueError, tk.TclError)) as result:
            owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)), modal_parent=parent)
    assert result.value is (first if primary else restoration)
    if primary:
        notes = '\n'.join(first.__notes__)
        assert 'cleanup release failed' in notes and f'return {kind} failed' in notes
    assert owned_ui._history_window is None and not owned_ui._history_window_opening
    owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)), modal_parent=parent)


@pytest.mark.parametrize('phase', ['validation', 'restoration'])
def test_unexpected_liveness_errors_are_not_misclassified_as_destruction(setup, owned_ui, monkeypatch, phase):
    s, a, *_ = setup
    parent = Window(owned_ui.root)
    original = owned_ui._history_widget_exists
    error = tk.TclError('unexpected interpreter inspection failure')
    def inspect(widget):
        if phase == 'validation' or owned_ui._history_window is None and len(Window.created) > 1:
            raise error
        return original(widget)
    monkeypatch.setattr(owned_ui, '_history_widget_exists', inspect)
    with pytest.raises(tk.TclError) as result:
        owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)), modal_parent=parent)
    assert result.value is error and not owned_ui._history_window_opening


def test_explicit_modal_handoff_sort_and_return_do_not_write_or_reload(setup, owned_ui, monkeypatch):
    s, a, _, _, _, service_clock = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    service_clock[0] = local(s, TUE, 9)
    s.start_task(a)
    parent = Window(owned_ui.root)
    parent.grab_set()
    focus = Focus(parent)
    parent.tk.focus = focus
    before, clock = capture(s), Clock(local(s, TUE, 12))
    def forbidden(*args, **kwargs):
        pytest.fail('Modal handoff attempted persistence, forced return focus or extra observation')
    def drive(window):
        browser = owned_ui._history_window.browser
        rows, request = deepcopy(browser._rows), (browser._applied, browser._cutoff_utc)
        browser.period_buttons['Custom'].invoke()
        browser.start_var.set('unapplied draft')
        with monkeypatch.context() as m:
            m.setattr(s, 'get_task_work_history', forbidden)
            m.setattr(browser, '_now_utc', forbidden)
            assert browser.history.tree.headings['date']['command']() is True
            assert browser._rows == sorted(rows, key=lambda row: row['work_date'])
            assert (browser._applied, browser._cutoff_utc) == request
            assert browser.start_var.get() == 'unapplied draft'
            owned_ui._history_window.close()
    Window.wait_action = drive
    with monkeypatch.context() as m:
        for name in ('_append', '_save_snapshot', 'start_task', 'stop_task', 'create_backup_now'):
            m.setattr(s, name, forbidden)
        for name in ('append_event', 'save_snapshot', 'synchronize_journal', 'iter_all_events'):
            m.setattr(s.storage, name, forbidden)
        for name in ('__init__', 'load', 'save'):
            m.setattr(UISettingsStore, name, forbidden)
        for name in ('write_bytes', 'write_text', 'mkdir', 'unlink'):
            m.setattr(Path, name, forbidden)
        m.setattr(app_module, 'utc_now', forbidden)
        m.setattr(parent, 'focus_force', forbidden)
        m.setattr(focus, 'focus_force', forbidden)
        owned_ui._open_history_window(s, a, now_utc=clock, modal_parent=parent)
    assert clock.calls == 1 and capture(s) == before
    assert Window.grabbed is parent and parent.tk.focus is focus
    assert owned_ui._history_newest_first is False and not owned_ui._history_window_opening


@pytest.mark.parametrize('nested,how', [(False, 'close'), (True, 'close'), (True, 'wm'), (True, 'external')])
def test_real_tk_actual_task_and_nested_editors_preserve_drafts_and_return_modal_context(
        setup, owner_factory, tk_root, pointer, monkeypatch, nested, how):
    s, a, _, _, _, service_clock = setup
    child = s.create_subtask(a, 'Child', '')
    grandchild = s.create_subtask(child, 'Grandchild', '')
    path = [a, child, grandchild] if nested else [a]
    task = path[-1]
    interval(s, task, local(s, MON, 20), local(s, TUE, 8))
    dated(s, task, TUE, 119.9)
    service_clock[0] = local(s, TUE, 9)
    s.start_task(a)
    before, clock = capture(s), Clock(local(s, TUE, 12))
    owner = owner_factory(s)
    owner.root = tk_root
    calls = spy(s, monkeypatch)
    editors, failures, ticks, blocked = [], [], [], []
    original_init = dialogs.EditTaskDialog.__init__
    def observe(editor, *args, **kwargs):
        editors.append(editor)
        original_init(editor, *args, **kwargs)
    monkeypatch.setattr(dialogs.EditTaskDialog, '__init__', observe)
    main = ttk.Button(tk_root, text='Main probe', command=lambda: blocked.append('main'))
    main.place(x=10, y=10)
    pointer.click(main)
    assert blocked == ['main']
    blocked.clear()

    def safe(action):
        def run():
            try:
                action()
            except BaseException as exc:
                failures.append(exc)
                if owner._history_window is not None: owner._history_window.close()
                for editor in reversed(editors):
                    if owner._history_widget_exists(editor.window): editor.window.destroy()
        return run

    def visit(level):
        editor = editors[-1]
        assert editor.task_id == path[level]
        editor.window.geometry('+150+80')
        editor.name_var.set(f'Unsaved name {level}')
        editor.notes_var.set(f'Unsaved note {level}')
        editor.tag_selector.set_selected_tags(['draft-only'])
        draft = (editor.name_var.get(), editor.notes_var.get(), editor.tag_selector.get_selected_tags(),
                 editor.changed, editor.added_subtask)
        if level + 1 < len(path):
            editor.subtask_tree.selection_set(path[level + 1])
            selection = editor.subtask_tree.selection()
            tk_root.after(100, safe(lambda: visit(level + 1)))
            editor._edit_selected_subtask()  # Actual recursive constructor and nested Tk wait.
            assert editor.subtask_tree.selection() == selection
        else:
            field = next(widget for widget in editor.window.winfo_children()
                         if isinstance(widget, ttk.Entry) and widget.cget('textvariable') == str(editor.name_var))
            field.selection_range(1, 4)
            field.icursor(2)
            probe = ttk.Button(editor.window, text='Editor probe', command=lambda: blocked.append('editor'))
            probe.place(x=10, y=10)
            pointer.click(probe)
            assert blocked == ['editor']
            blocked.clear()
            field.focus_force()
            tk_root.update()
            assert editor.window.grab_current() is editor.window
            assert editor.window.focus_get() is field

            def inspect(wrapper):
                assert wrapper.window.master is editor.window
                assert str(wrapper.window.transient()) == str(editor.window)
                assert owner._history_window_opening
                assert wrapper.browser.task_id == task
                wrapper.window.geometry('+350+190')
                tk_root.update()
                pointer.click(main)
                pointer.click(probe)
                assert blocked == []
                wrapper.window.focus_force()  # Establish the test input target after blocked ancestor clicks.
                tk_root.update()
                tk_root.after(0, lambda: ticks.append(True))
                tk_root.update()
                assert ticks == [True]
                browser = wrapper.browser
                pointer.click(browser.period_buttons['Custom'])
                pointer.click(browser.picker_buttons['Start'])
                popup, calendar = next(iter(browser._pickers.items()))
                popup.geometry('+300+460')
                tk_root.update()
                day = next(label for week in calendar._calendar for label in week if label.cget('text') == '12')
                pointer.click(day)
                assert browser.start_var.get() == str(MON) and not popup.winfo_exists()
                assert browser._applied[0] == 'Current week' and clock.calls == 1
                pointer.click(browser.picker_buttons['End'])
                popup = next(iter(browser._pickers))
                popup.focus_force()
                tk_root.update()
                pointer.escape()
                assert not popup.winfo_exists() and wrapper.window.grab_current() is wrapper.window
                command = browser.history.tree.heading('date', 'command')
                browser.history.tree.tk.call(command)
                assert owner._history_newest_first is False and len(calls) == clock.calls == 1
                if how == 'close': pointer.click(wrapper.close_button)
                elif how == 'wm': wrapper.window.tk.call(wrapper.window.protocol('WM_DELETE_WINDOW'))
                else: wrapper.window.destroy()

            inner_failures, job = modal_action(tk_root, owner, inspect)
            owner._open_history_window(s, task, now_utc=clock, week_start=6, modal_parent=editor.window)
            tk_root.after_cancel(job)
            assert inner_failures == []
            tk_root.update()
            assert owner._history_window is None and not owner._history_window_opening
            assert editor.window.grab_current() is editor.window and editor.window.grab_status() == 'local'
            assert editor.window.focus_get() is field
            assert (field.index('sel.first'), field.index('sel.last'), field.index('insert')) == (1, 4, 2)
            assert clock.calls == 1 and owner._history_newest_first is False
        assert (editor.name_var.get(), editor.notes_var.get(), editor.tag_selector.get_selected_tags(),
                editor.changed, editor.added_subtask) == draft
        editor.window.destroy()

    def timeout():
        failures.append(AssertionError('Nested editor test timed out'))
        if owner._history_window is not None: owner._history_window.close()
        for editor in reversed(editors):
            if owner._history_widget_exists(editor.window): editor.window.destroy()
    watchdog = tk_root.after(7000, timeout)
    tk_root.after(100, safe(lambda: visit(0)))
    dialogs.EditTaskDialog(tk_root, s, a)
    tk_root.after_cancel(watchdog)
    assert failures == [] and len(editors) == len(path)
    assert capture(s) == before and clock.calls == 1
    # A later root-default opening keeps sorting without creating a root grab.
    errors, job = modal_action(tk_root, owner, lambda wrapper: wrapper.close())
    later = owner._open_history_window(s, task, now_utc=clock)
    tk_root.after_cancel(job)
    assert errors == [] and later.browser.newest_first is False and tk_root.grab_current() is None


@pytest.mark.parametrize('destroy', ['parent', 'root'])
def test_real_tk_actual_editor_or_root_destruction_skips_return_and_disposes_calendar(
        setup, owner_factory, tk_root, monkeypatch, destroy):
    s, a, *_ = setup
    owner = owner_factory(s)
    owner.root = tk_root
    clock, before = Clock(local(s, TUE, 12)), capture(s)
    editors, errors = [], []
    original = dialogs.EditTaskDialog.__init__
    def observe(editor, *args, **kwargs):
        editors.append(editor)
        original(editor, *args, **kwargs)
    monkeypatch.setattr(dialogs.EditTaskDialog, '__init__', observe)
    def drive():
        editor = editors[-1]
        popups = []
        def destroy_origin(wrapper):
            wrapper.browser.picker_buttons['Start'].invoke()
            popups.extend(wrapper.browser._pickers)
            (tk_root if destroy == 'root' else editor.window).destroy()
        failures, job = modal_action(tk_root, owner, destroy_origin)
        try:
            wrapper = owner._open_history_window(s, a, now_utc=clock, modal_parent=editor.window)
            assert failures == [] and not wrapper.browser._pickers
            assert owner._history_window is None and not owner._history_window_opening
            assert not owner._history_widget_exists(editor.window)
            assert all(not owner._history_widget_exists(popup) for popup in popups)
        except BaseException as exc:
            errors.append(exc)
        finally:
            tk_root.after_cancel(job)
            if owner._history_widget_exists(editor.window): editor.window.destroy()
    tk_root.after(100, drive)
    dialogs.EditTaskDialog(tk_root, s, a)
    assert errors == [] and capture(s) == before and clock.calls == 1


@pytest.mark.parametrize('kind', ['local', 'global'])
def test_real_tk_new_grab_during_visibility_is_not_stolen_or_focused_away(
        setup, owner_factory, tk_root, monkeypatch, kind):
    s, a, *_ = setup
    owner = owner_factory(s)
    owner.root = tk_root
    parent, competitor = tk.Toplevel(tk_root), tk.Toplevel(tk_root)
    field = ttk.Entry(competitor)
    field.pack()
    tk_root.update()
    parent.grab_set()
    original = tk.Toplevel.wait_visibility
    def wait(window, *args):
        original(window, *args)
        if kind == 'global': competitor.grab_set_global()
        else: competitor.grab_set()
        field.focus_force()
        tk_root.update()
    monkeypatch.setattr(tk.Toplevel, 'wait_visibility', wait)
    try:
        with pytest.raises(ValueError, match='cannot acquire'):
            owner._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)), modal_parent=parent)
        assert competitor.grab_current() is competitor and competitor.grab_status() == kind
        assert competitor.focus_get() is field
        assert owner._history_window is None and not owner._history_window_opening
    finally:
        competitor.destroy()
        parent.destroy()


def test_real_tk_recreated_focus_path_is_not_the_saved_focus(setup, owner_factory, tk_root):
    s, a, *_ = setup
    owner = owner_factory(s)
    owner.root = tk_root
    parent = tk.Toplevel(tk_root)
    saved = ttk.Entry(parent, name='saved')
    saved.pack()
    if not parent.winfo_viewable():
        parent.wait_visibility()
    parent.grab_set()
    saved.focus_force()
    tk_root.update()
    replacement = []
    def replace(wrapper):
        saved.destroy()
        replacement.append(ttk.Entry(parent, name='saved'))
        replacement[0].pack()
        wrapper.close()
    failures, job = modal_action(tk_root, owner, replace)
    owner._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)), modal_parent=parent)
    tk_root.after_cancel(job)
    tk_root.update()
    assert failures == [] and parent.grab_current() is parent
    assert parent.focus_get() is parent and parent.focus_get() is not replacement[0]
    parent.destroy()
