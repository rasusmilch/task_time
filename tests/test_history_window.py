"""Owned modal history composition; doubles and separate server-input Tk evidence."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from task_timer import app as app_module
from task_timer import history_window as windows
from task_timer.settings import UISettingsStore
from task_timer.storage import EventStorage
from test_history_session_direction import owner_factory
from test_app_ui import _FakeRoot
from test_mixed_accounting import setup, dated, local, MON, TUE
from test_work_history import interval, capture
from test_work_history_view import make_view
from test_work_history_browser import build, Clock, spy, Popup


class FakeTk:
    def __init__(self):
        self.widgets = {}
        self.focus = None

    def call(self, *args):
        assert args[:3] == ('namespace', 'which', '-command')
        widget = self.widgets.get(args[3])
        return args[3] if widget is not None and widget.exists else ''


class Root(_FakeRoot, tk.Misc):
    def __init__(self):
        _FakeRoot.__init__(self)
        self.master, self._w, self.exists = None, '.', True
        self.tk = FakeTk()
        self.tk.widgets[self._w] = self
        self.widgets = []
        self.children = {}
        self.acquisitions = 0

    def winfo_toplevel(self):
        return self

    def grab_current(self):
        return Window.grabbed

    def grab_status(self):
        return 'local' if Window.grabbed is self else None

    def grab_set(self):
        self.acquisitions += 1
        Window.grabbed = self

    def focus_get(self):
        return self.tk.focus

    def focus_set(self):
        self.tk.focus = self

    def destroy(self):
        self.exists = False
        for child in tuple(Window.created):
            child.destroy()


class Window(Popup, tk.Misc):
    created = []
    grabbed = None
    wait_action = None

    def __init__(self, parent):
        super().__init__(parent)
        self.master = parent
        self._name = f'window{len(self.created)}'
        self.children = {}
        parent.children[self._name] = self
        self.tk, self._w = parent.tk, f'{parent._w.rstrip(".")}.{self._name}'
        self.tk.widgets[self._w] = self
        self.exists = True
        self.releases = 0
        self.waits = 0
        self.acquisitions = 0
        self.status = 'local'
        self.created.append(self)

    def withdraw(self):
        self.visible = False

    def deiconify(self):
        self.visible = True

    def grid_columnconfigure(self, *args, **kwargs):
        pass

    grid_rowconfigure = grid_columnconfigure

    def winfo_exists(self):
        return self.exists

    def wait_visibility(self):
        assert self.visible

    def grab_current(self):
        return Window.grabbed

    def grab_set(self):
        self.acquisitions += 1
        Window.grabbed = self

    def grab_status(self):
        return self.status if Window.grabbed is self else None

    def focus_get(self):
        return self.tk.focus

    def focus_set(self):
        self.tk.focus = self

    def grab_release(self):
        assert Window.grabbed is self
        self.releases += 1
        Window.grabbed = None

    def focus_force(self):
        self.focused = True
        self.tk.focus = self

    def wait_window(self):
        self.waits += 1
        if Window.wait_action:
            Window.wait_action(self)
        else:
            self.bindings['WM_DELETE_WINDOW']()

    def destroy(self):
        if not self.exists:
            return
        def destroy_children(widget):
            for child in tuple(widget.widgets):
                destroy_children(child)
            widget.destroyed = True
            if '<Destroy>' in widget.bindings:
                widget.bindings['<Destroy>'](SimpleNamespace(widget=widget))
        self.exists = False
        if Window.grabbed is self:
            Window.grabbed = None  # Tk also drops a grab on external destruction.
        destroy_children(self)


@pytest.fixture
def owned_ui(build, owner_factory, setup, monkeypatch):
    Window.created, Window.grabbed, Window.wait_action = [], None, None
    monkeypatch.setattr(windows, 'Toplevel', Window)
    owner = owner_factory(setup[0])
    owner.root = Root()
    return owner


def test_actual_initialization_sets_empty_ownership_before_controls(setup, owner_factory, monkeypatch):
    seen = []
    def controls(owner):
        seen.append((owner._history_window, owner._history_window_opening, owner._history_newest_first))
    monkeypatch.setattr(app_module.TaskTimerApp, '_build_ui', controls)
    owner = owner_factory(setup[0])
    assert seen == [(None, False, True)]
    assert owner._history_window is None and owner._history_window_opening is False


def test_constructor_is_withdrawn_without_grab_wait_or_second_load(setup, owned_ui):
    s, a, *_ = setup
    clock, closed = Clock(local(s, TUE, 12)), []
    wrapper = windows.HistoryWindow(
        owned_ui.root,
        make_browser=lambda parent: owned_ui._make_history_browser(parent, s, a, now_utc=clock),
        on_closed=closed.append,
    )
    assert not wrapper.window.visible and wrapper.window.waits == 0
    assert Window.grabbed is None and clock.calls == 1
    assert closed == [] and wrapper.browser.task_id == a
    wrapper.close()
    wrapper.close()
    assert closed == [wrapper]


def test_one_owned_window_reentrancy_sequential_tasks_datasets_and_session_direction(
        setup, owned_ui, monkeypatch, tmp_path):
    s, a, b, _, _, service_clock = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    service_clock[0] = local(s, TUE, 9)
    s.start_task(a)
    other = app_module.TaskTimerService(EventStorage(tmp_path / 'other'))
    c = other.create_task('Different dataset', '')
    dated(other, c, MON, 119.9)
    before = capture(s), capture(other)
    owner, clock = owned_ui, Clock(local(s, TUE, 12))
    calls, other_calls = spy(s, monkeypatch), spy(other, monkeypatch)
    make = owner._make_history_browser
    builds, shown = [], []
    def forbidden():
        pytest.fail('Duplicate request observed a clock')
    def make_with_reentry(parent, service, task, **options):
        builds.append((service, task, options))
        assert owner._history_window_opening is True
        assert owner._open_history_window(object(), 'invalid', now_utc=forbidden) is None
        return make(parent, service, task, **options)
    monkeypatch.setattr(owner, '_make_history_browser', make_with_reentry)
    def during_wait(window):
        wrapper = owner._history_window
        assert wrapper.window is window and owner._history_window_opening
        assert window.grab_current() is window and window.focused
        assert wrapper.browser.task_id == builds[-1][1]
        old = deepcopy(wrapper.browser._rows), wrapper.browser._cutoff_utc
        assert owner._open_history_window(s, a, now_utc=forbidden) is None
        assert owner._open_history_window(object(), b, now_utc=forbidden) is None
        assert (wrapper.browser._rows, wrapper.browser._cutoff_utc) == old
        shown.append(wrapper)
        if len(shown) == 1:
            assert wrapper.browser.history.tree.headings['date']['command']() is True
            assert owner._history_newest_first is False
            wrapper.browser.period_buttons['Custom'].invoke()
            wrapper.browser.picker_buttons['Start'].invoke()
            assert wrapper.browser._pickers
        wrapper.close_button.invoke()
        assert not wrapper.browser._pickers
    Window.wait_action = during_wait
    first = owner._open_history_window(s, a, now_utc=clock, week_start=0)
    assert first is shown[0] and owner._history_window is None
    owner._open_history_window(s, b, now_utc=clock)
    owner._open_history_window(other, c, now_utc=clock)
    assert len(builds) == len(shown) == len(Window.created) == clock.calls == 3
    assert [call[1]['newest_first'] for call in calls] == [True, False]
    assert other_calls[0][1]['newest_first'] is False
    assert owner.service is s and owner._history_newest_first is False
    assert all(w.waits == w.releases == 1 for w in Window.created)
    assert (capture(s), capture(other)) == before


@pytest.mark.parametrize('fault', ['withdraw', 'browser', 'button', 'transient', 'deiconify',
                                 'wait_visibility', 'grab_set', 'focus_force', 'wait_window'])
def test_failure_disposes_partial_window_clears_guard_and_allows_reopening(
        setup, owned_ui, monkeypatch, fault):
    s, a, *_ = setup
    owner, clock = owned_ui, Clock(local(s, TUE, 12))
    before = capture(s)
    closed = []
    callback = owner._history_window_closed
    monkeypatch.setattr(owner, '_history_window_closed', lambda wrapper: (closed.append(wrapper), callback(wrapper)))
    def fail(*args, **kwargs):
        if fault == 'grab_set':
            Window.grabbed = args[0]  # Also clean up an ambiguous acquired grab.
        raise tk.TclError(f'injected {fault}')
    with monkeypatch.context() as m:
        if fault == 'browser':
            original = owner._make_history_browser
            def broken(*args, **kwargs):
                original(*args, **kwargs)
                fail()
            m.setattr(owner, '_make_history_browser', broken)
        elif fault == 'button':
            original = ttk.Button
            m.setattr(ttk, 'Button', lambda *args, **kwargs: fail() if kwargs.get('text') == 'Close'
                      else original(*args, **kwargs))
        else:
            m.setattr(Window, fault, fail)
        with pytest.raises(tk.TclError, match=f'injected {fault}'):
            owner._open_history_window(s, a, now_utc=clock)
    assert owner._history_window is None and owner._history_window_opening is False
    assert not Window.created[0].exists and Window.grabbed is None
    assert len(closed) == (0 if fault in ('withdraw', 'browser', 'button') else 1)
    owner._open_history_window(s, a, now_utc=clock)
    assert len(Window.created) == 2 and owner._history_window is None
    assert capture(s) == before


def test_initial_load_failure_is_usable_and_only_explicit_refresh_recovers(setup, owned_ui):
    s, a, *_ = setup
    clock = Clock(None)
    def inspect(window):
        browser = owned_ui._history_window.browser
        assert browser._rows is None and browser.info_var.get() == 'Not loaded'
        assert browser.error_label.visible and clock.calls == 1
        clock.value = local(s, TUE, 12)
        assert browser.refresh_button.invoke() is True
        assert browser._rows == [] and clock.calls == 2
        window.bindings['WM_DELETE_WINDOW']()
    Window.wait_action = inspect
    owned_ui._open_history_window(s, a, now_utc=clock)
    assert owned_ui._history_window is None


@pytest.mark.parametrize('how', ['close', 'wm', 'external', 'root'])
def test_destruction_notifies_once_for_owned_toplevel_only(setup, owned_ui, monkeypatch, how):
    s, a, *_ = setup
    closed = []
    callback = owned_ui._history_window_closed
    monkeypatch.setattr(owned_ui, '_history_window_closed', lambda wrapper: (closed.append(wrapper), callback(wrapper)))
    def inspect(window):
        wrapper = owned_ui._history_window
        wrapper._on_destroy(SimpleNamespace(widget=wrapper.browser))
        assert owned_ui._history_window is wrapper and closed == []
        wrapper.browser.picker_buttons['Start'].invoke()
        popups = tuple(wrapper.browser._pickers)
        if how == 'close': wrapper.close()
        elif how == 'wm': window.bindings['WM_DELETE_WINDOW']()
        elif how == 'external': window.destroy()
        else:
            # Isolate root destruction itself; actual Tk shutdown is tested below.
            owned_ui.root.destroy()
        wrapper.close()
        wrapper._on_destroy(SimpleNamespace(widget=window))
        assert closed == [wrapper] and owned_ui._history_window is None
        assert all(p.destroyed for p in popups) and not wrapper.browser._pickers
    Window.wait_action = inspect
    owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)))
    assert Window.grabbed is None


def test_stale_reference_and_old_callback_cannot_block_or_clear_new_owner(setup, owned_ui):
    s, a, *_ = setup
    stale = SimpleNamespace(window=Window(owned_ui.root))
    stale.window.destroy()
    Window.created.clear()
    owned_ui._history_window = stale
    def inspect(window):
        current = owned_ui._history_window
        owned_ui._history_window_closed(stale)
        assert owned_ui._history_window is current
        current.close()
    Window.wait_action = inspect
    owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)))
    assert owned_ui._history_window is None and len(Window.created) == 1


def test_cleanup_never_releases_a_foreign_grab(setup, owned_ui, monkeypatch):
    s, a, *_ = setup
    foreign = Window(owned_ui.root)
    def fail_after_replacement(window):
        Window.grabbed = foreign
        raise tk.TclError('focus failed')
    monkeypatch.setattr(Window, 'focus_force', fail_after_replacement)
    with pytest.raises(tk.TclError, match='focus failed'):
        owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)))
    assert Window.grabbed is foreign and foreign.releases == 0
    assert owned_ui._history_window is None


def test_presentation_error_retains_cleanup_failure_context(setup, owned_ui, monkeypatch):
    s, a, *_ = setup
    def fail_focus(window):
        raise ValueError('presentation failed')
    def fail_release(window):
        raise tk.TclError('release failed')
    monkeypatch.setattr(Window, 'focus_force', fail_focus)
    monkeypatch.setattr(Window, 'grab_release', fail_release)
    with pytest.raises(ValueError, match='presentation failed') as error:
        owned_ui._open_history_window(s, a, now_utc=Clock(local(s, TUE, 12)))
    assert 'release failed' in error.value.__notes__[0]
    assert not Window.created[0].exists and Window.grabbed is None
    assert owned_ui._history_window is None


def test_window_lifecycle_preserves_dataset_timers_settings_and_clock_count(setup, owned_ui, monkeypatch):
    s, a, _, _, _, service_clock = setup
    service_clock[0] = local(s, TUE, 9)
    s.start_task(a)
    before = capture(s)
    clock = Clock(local(s, TUE, 12))
    def forbidden(*args, **kwargs):
        pytest.fail('History window mutated domain/settings or scheduled loading')
    with monkeypatch.context() as m:
        for name in ('_append', '_save_snapshot', 'start_task', 'stop_task', 'create_backup_now'):
            m.setattr(s, name, forbidden)
        for name in ('append_event', 'save_snapshot', 'synchronize_journal', 'iter_all_events'):
            m.setattr(s.storage, name, forbidden)
        for name in ('__init__', 'load', 'save'):
            m.setattr(UISettingsStore, name, forbidden)
        for name in ('write_bytes', 'write_text', 'mkdir', 'unlink'):
            m.setattr(Path, name, forbidden)
        for name in ('after', 'after_idle'):
            m.setattr(ttk.Frame, name, forbidden)
        owned_ui._open_history_window(s, a, now_utc=clock)
    assert clock.calls == 1 and capture(s) == before


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f'Real Tk/display unavailable: {exc}')
    root.geometry('1000x700+0+0')
    root.update()
    if not root.winfo_viewable():
        root.wait_visibility()
    root.focus_force()
    root.update()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    try:
        yield root
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass  # Root-destruction cases already disposed the interpreter's windows.
        assert errors == []


@pytest.fixture
def pointer(tk_root):
    """Server-delivered X11 input, rather than invoking buttons past a Tk grab."""
    import ctypes as c
    from ctypes.util import find_library
    import sys
    if sys.platform != 'linux':
        pytest.skip('XTest fixture is Linux/X11 evidence; native platform evidence is separate')
    if not find_library('X11') or not find_library('Xtst'):
        pytest.skip('Real pointer/grab evidence requires available X11 XTest libraries')
    x = c.CDLL(find_library('X11'))
    xt = c.CDLL(find_library('Xtst'))
    x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [c.c_char_p], c.c_void_p
    x.XCloseDisplay.argtypes = [c.c_void_p]
    x.XSync.argtypes = [c.c_void_p, c.c_int]
    x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [c.c_char_p], c.c_ulong
    x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [c.c_void_p, c.c_ulong], c.c_uint
    xt.XTestFakeMotionEvent.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_ulong]
    xt.XTestFakeButtonEvent.argtypes = [c.c_void_p, c.c_uint, c.c_int, c.c_ulong]
    xt.XTestFakeKeyEvent.argtypes = [c.c_void_p, c.c_uint, c.c_int, c.c_ulong]
    display = x.XOpenDisplay(None)
    assert display, 'Could not open the test display for real pointer input'
    def settle():
        # Let the separate window manager process map/configure/focus requests
        # before using screen coordinates; keep normal Tk events running.
        done = tk.StringVar(tk_root, value='')
        tk_root.after(20, lambda: done.set('ready'))
        tk_root.wait_variable(done)
    def sync():
        x.XSync(display, False)
        tk_root.update()  # Deliver input before waiting; it may destroy the root.
        if tk_root.tk.call('namespace', 'which', '-command', tk_root._w):
            settle()
            tk_root.update()
    def click(widget, *, x_offset=None, y_offset=None):
        top = widget.winfo_toplevel()
        if not top.winfo_viewable():
            top.wait_visibility()
        settle()
        tk_root.update()
        assert widget.winfo_ismapped()
        xx = widget.winfo_rootx() + (widget.winfo_width() // 2 if x_offset is None else x_offset)
        yy = widget.winfo_rooty() + (widget.winfo_height() // 2 if y_offset is None else y_offset)
        assert xt.XTestFakeMotionEvent(display, -1, xx, yy, 0)
        sync()
        for pressed in (True, False):
            assert xt.XTestFakeButtonEvent(display, 1, pressed, 0)
            sync()
    def escape():
        code = x.XKeysymToKeycode(display, x.XStringToKeysym(b'Escape'))
        assert code
        for pressed in (True, False):
            assert xt.XTestFakeKeyEvent(display, code, pressed, 0)
            sync()
    try:
        yield SimpleNamespace(click=click, escape=escape)
    finally:
        x.XCloseDisplay(display)


def modal_action(root, owner, action):
    """Bound test-driving callbacks; surface assertions instead of hanging a wait."""
    failures = []
    def drive():
        try:
            assert owner._history_window is not None
            assert root.grab_current() is owner._history_window.window
            action(owner._history_window)
        except BaseException as exc:
            failures.append(exc)
        finally:
            if owner._history_window is not None:
                owner._history_window.close()
    def timeout():
        failures.append(AssertionError('Modal test did not return before watchdog'))
        if owner._history_window is not None:
            owner._history_window.close()
    job = root.after(4000, timeout)
    root.after(100, drive)
    return failures, job


def test_real_tk_local_grab_blocks_main_mouse_input_but_calendar_controls_work(
        setup, owner_factory, tk_root, pointer, monkeypatch):
    s, a, _, _, _, service_clock = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    service_clock[0] = local(s, TUE, 9)
    s.start_task(a)
    before = capture(s)
    owner = owner_factory(s)
    owner.root = tk_root
    clock, main_clicks, ticks = Clock(local(s, TUE, 12)), [], []
    calls = spy(s, monkeypatch)
    main = ttk.Button(tk_root, text='Main application action', command=lambda: main_clicks.append(True))
    main.place(x=10, y=10)
    pointer.click(main)
    assert main_clicks == [True]  # Prove the physical test click works before grabbing.
    main_clicks.clear()
    def interact(wrapper):
        window, browser = wrapper.window, wrapper.browser
        window.geometry('+200+130')
        tk_root.update()
        assert window.grab_status() == 'local'
        assert tk_root.focus_get().winfo_toplevel() is window
        child = ttk.Label(window, text='Temporary child')
        child.destroy()
        tk_root.update()
        assert owner._history_window is wrapper
        assert clock.calls == len(calls) == 1
        pointer.click(main)
        assert main_clicks == []  # No invoke()/direct event dispatch bypasses the grab.
        tk_root.after(0, lambda: ticks.append(tk_root.grab_current()))
        tk_root.update()
        assert ticks == [window]  # Normal scheduled event processing inside wait_window.
        pointer.click(browser.period_buttons['Custom'])
        old = browser._applied, browser._cutoff_utc
        pointer.click(browser.picker_buttons['Start'])
        popup, calendar = next(iter(browser._pickers.items()))
        popup.geometry('+250+430')
        tk_root.update()
        day = next(label for week in calendar._calendar for label in week if label.cget('text') == '12')
        pointer.click(day)
        assert browser.start_var.get() == str(MON) and not popup.winfo_exists()
        assert tk_root.grab_current() is window
        assert (browser._applied, browser._cutoff_utc) == old and clock.calls == 1
        pointer.click(browser.picker_buttons['End'])
        popup = next(iter(browser._pickers))
        popup.geometry('+250+430')
        tk_root.update()
        cancel = next(child for child in popup.winfo_children()
                      if isinstance(child, ttk.Button) and child.cget('text') == 'Cancel')
        pointer.click(cancel)
        assert browser.end_var.get() == '' and not popup.winfo_exists()
        assert tk_root.grab_current() is window
        pointer.click(browser.picker_buttons['End'])
        popup = next(iter(browser._pickers))
        popup.focus_force()
        tk_root.update()
        pointer.escape()
        assert not popup.winfo_exists() and window.winfo_exists()
        assert tk_root.grab_current() is window and clock.calls == 1
        browser.end_var.set(str(TUE))
        pointer.click(browser.apply_button)
        assert browser._applied == ('Custom', MON, TUE) and clock.calls == len(calls) == 2
        pointer.click(browser.refresh_button)
        assert clock.calls == len(calls) == 3
        command = browser.history.tree.heading('date', 'command')
        assert int(browser.history.tree.tk.call(command)) == 1
        assert owner._history_newest_first is False and clock.calls == 3
        pointer.click(main)
        assert main_clicks == []
        pointer.click(wrapper.close_button)
        assert owner._history_window is None
    failures, job = modal_action(tk_root, owner, interact)
    wrapper = owner._open_history_window(s, a, now_utc=clock)
    tk_root.after_cancel(job)
    assert failures == []
    assert not wrapper.window.winfo_exists() and tk_root.grab_current() is None
    pointer.click(main)
    assert main_clicks == [True] and capture(s) == before


@pytest.mark.parametrize('how', ['close', 'wm', 'external', 'root'])
def test_real_tk_destruction_with_open_calendar_releases_wait_and_ownership(
        setup, owner_factory, tk_root, how):
    s, a, *_ = setup
    owner = owner_factory(s)
    owner.root = tk_root
    before, clock = capture(s), Clock(local(s, TUE, 12))
    closed, popups, wrappers = [], [], []
    original = owner._history_window_closed
    owner._history_window_closed = lambda wrapper: (closed.append(wrapper), original(wrapper))
    def destroy(wrapper):
        wrappers.append(wrapper)
        wrapper.browser.picker_buttons['Start'].invoke()
        popups.extend(wrapper.browser._pickers)
        assert len(popups) == 1
        if how == 'close': wrapper.close_button.invoke()
        elif how == 'wm': wrapper.window.tk.call(wrapper.window.protocol('WM_DELETE_WINDOW'))
        elif how == 'external': wrapper.window.destroy()
        else: tk_root.destroy()
    failures, job = modal_action(tk_root, owner, destroy)
    owner._open_history_window(s, a, now_utc=clock)
    tk_root.after_cancel(job)
    assert failures == [] and closed == wrappers
    assert owner._history_window is None and clock.calls == 1 and capture(s) == before
    assert not wrappers[0].browser._pickers
    wrappers[0].close()  # Also idempotent after interpreter-wide root destruction.
    if how != 'root':
        assert tk_root.grab_current() is None
        assert all(not p.winfo_exists() for p in popups)
        failures, job = modal_action(tk_root, owner, lambda wrapper: wrapper.close())
        owner._open_history_window(s, a, now_utc=clock)
        tk_root.after_cancel(job)
        assert failures == [] and clock.calls == 2


@pytest.mark.parametrize('fault', ['construction', 'grab'])
def test_real_tk_failure_disposes_actual_widgets_and_permits_reopen(
        setup, owner_factory, tk_root, monkeypatch, fault):
    s, a, *_ = setup
    owner = owner_factory(s)
    owner.root = tk_root
    clock = Clock(local(s, TUE, 12))
    before = capture(s)
    with monkeypatch.context() as m:
        if fault == 'construction':
            original = owner._make_history_browser
            def broken(*args, **kwargs):
                browser = original(*args, **kwargs)
                browser.picker_buttons['Start'].invoke()
                raise ValueError('browser construction failed')
            m.setattr(owner, '_make_history_browser', broken)
        else:
            original = tk.Toplevel.grab_set
            def broken(window):
                original(window)
                raise ValueError('grab failed after acquisition')
            m.setattr(tk.Toplevel, 'grab_set', broken)
        with pytest.raises(ValueError, match='failed'):
            owner._open_history_window(s, a, now_utc=clock)
    assert owner._history_window is None and owner._history_window_opening is False
    assert tk_root.winfo_children() == [] and tk_root.grab_current() is None
    failures, job = modal_action(tk_root, owner, lambda wrapper: wrapper.close())
    owner._open_history_window(s, a, now_utc=clock)
    tk_root.after_cancel(job)
    assert failures == [] and clock.calls == 2 and capture(s) == before
