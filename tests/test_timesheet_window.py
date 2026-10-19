"""Owned Timesheet lifecycle over real components; temporary datasets only."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from task_timer import app as app_module, timesheet_window as windows, timesheet_save as saves
from test_mixed_accounting import setup, dated, local, MON, TUE
from test_work_history import capture
from test_timesheet_preview import build as preview_widgets, Variable, drafts
from test_timesheet_save import build as save_widgets, ready, dialog, exports, no_recalculation
from test_history_session_direction import owner_factory
from test_history_window import Root, Window, tk_root, pointer
from test_work_history_browser import Clock


class Shell(Window):
    action = None
    def winfo_viewable(self): return self.visible
    def state(self): return 'normal' if self.visible else 'withdrawn'
    def wait_variable(self, variable):
        self.waits += 1
        if Shell.action: Shell.action(self)
        else: self.bindings['WM_DELETE_WINDOW']()
        assert variable.get(), 'Modal wait did not terminate'


@pytest.fixture
def owner(setup, save_widgets, owner_factory, monkeypatch):
    Window.created, Window.grabbed, Shell.action = [], None, None
    monkeypatch.setattr(windows, 'Toplevel', Shell)
    monkeypatch.setattr(windows, 'BooleanVar', Variable)
    s, *_ = setup
    result = owner_factory(s)
    result.root = Root()
    result.diagnostics = []
    result.root.report_callback_exception = lambda *args: result.diagnostics.append(args)
    return result


def fail(*args, **kw): raise OSError('Injected operation failure')


def test_actual_constructor_initializes_timesheet_ownership_before_use(setup, owner_factory, monkeypatch):
    s, *_ = setup
    checked = []
    def before_controls(result):
        assert result._timesheet_window is None and not result._timesheet_window_opening
        assert not result._exit_in_progress
        checked.append(True)
    monkeypatch.setattr(app_module.TaskTimerApp, '_build_ui', before_controls)
    result = owner_factory(s)
    assert checked == [True]
    assert result._timesheet_window is None and not result._timesheet_window_opening
    assert not result._exit_in_progress


def test_fresh_open_close_discard_and_duplicates_without_observation(setup, owner, monkeypatch):
    s, *_ = setup
    before = capture(s)
    monkeypatch.setattr(app_module, 'utc_now', lambda: pytest.fail('opening observed time'))
    visited = []
    def inspect(_window):
        wrapper = owner._timesheet_window
        assert owner._timesheet_window_opening and wrapper.is_presented()
        frame = wrapper.save_frame
        assert frame.preview.period_var.get() == 'This week' and frame.preview.scope_var.get() == 'All tasks'
        assert frame.preview.get_prepared_export() is None and frame.get_save_attempt() is None
        assert owner.open_timesheet() is None
        visited.append(frame)
        assert wrapper.close()
    Shell.action = inspect
    first = owner.open_timesheet()
    assert owner._timesheet_window is None and first._destroyed
    second = owner.open_timesheet()
    assert visited[0] is not visited[1] and second is not first and capture(s) == before


def test_retained_attempt_same_component_no_recalculation_and_newer_evidence(setup, owner, monkeypatch, tmp_path):
    from test_polr_confirmation_writer import register
    from test_polr_confirmation_replay import cell
    s, a, *_ = setup
    dated(s, a, MON, 10800)
    s.start_task(a)
    target = tmp_path / 'attempt.txt'
    dialog(monkeypatch, str(target))
    monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: True)
    retained = []
    def first(_window):
        wrapper = owner._timesheet_window
        frame = wrapper.save_frame
        event = ready(frame)
        with monkeypatch.context() as m:
            m.setattr(s, 'materialize_timesheet_export', fail)
            assert not frame.save()
        retained.append((wrapper, frame, frame.get_save_attempt(), frame.preview.report.get()))
        assert wrapper.has_unfinished_attempt() and wrapper.close()
        assert not wrapper._destroyed and not wrapper.is_presented()
    Shell.action = first
    wrapper = owner.open_timesheet()
    dated(s, a, MON, 7200)
    confirmation = register(s, cell(a, 500))
    before = capture(s)
    no_recalculation(monkeypatch, s)
    monkeypatch.setattr(app_module, 'utc_now', lambda: pytest.fail('resume observed a clock'))
    def resume(_window):
        current = owner._timesheet_window
        old, frame, attempt, text = retained[0]
        assert current is old and current.save_frame is frame
        assert frame.get_save_attempt() == attempt and frame.preview.report.get() == text
        assert frame.preview._locked and frame.save()
        assert not frame.has_unfinished_attempt()
        assert current.close()
    Shell.action = resume
    assert owner.open_timesheet() is wrapper and owner._timesheet_window is None
    assert len(exports(s)) == 1 and capture(s) == before
    assert s.get_effective_polr_confirmations()[a, str(MON)]['batch_event_id'] == confirmation['event_id']
    assert target.read_bytes() == retained[0][2]['prepared_event']['payload']['report_text'].encode('utf-8')


@pytest.mark.parametrize('closure', ['close', 'wm', 'escape'])
def test_unfinished_close_default_cancel_and_confirmation_are_guarded(setup, owner, monkeypatch, tmp_path, closure):
    s, *_ = setup
    target = tmp_path / 'conflict.txt'; target.write_bytes(b'Keep')
    dialog(monkeypatch, str(target))
    asked = []
    def inspect(window):
        wrapper = owner._timesheet_window
        frame = wrapper.save_frame
        ready(frame); assert not frame.save()
        before, attempt = capture(s), frame.get_save_attempt()
        def cancel(**kw):
            asked.append(kw)
            assert wrapper.is_busy() and not wrapper.close()
            owner._on_close_request()
            assert not owner._exit_in_progress
            return False
        monkeypatch.setattr(windows.messagebox, 'askyesno', cancel)
        action = wrapper.close if closure == 'close' else (
            window.bindings['WM_DELETE_WINDOW'] if closure == 'wm' else lambda: window.bindings['<Escape>'](None))
        action()
        assert wrapper.is_presented() and Window.grabbed is window
        assert frame.get_save_attempt() == attempt and capture(s) == before
        assert asked[-1]['default'] == 'no' and 'session' in asked[-1]['message']
        monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: True)
        action()
        assert not wrapper.is_presented() and Window.grabbed is None
    Shell.action = inspect
    wrapper = owner.open_timesheet()
    assert owner._timesheet_window is wrapper and not wrapper._destroyed


def test_busy_dialog_guards_close_exit_open_and_preserves_cancellation(setup, owner, monkeypatch):
    s, *_ = setup
    def inspect(_window):
        wrapper = owner._timesheet_window
        frame = wrapper.save_frame
        event = ready(frame)
        before = capture(s)
        def cancel():
            assert frame.is_busy() and wrapper.is_busy()
            assert not wrapper.close() and owner.open_timesheet() is None
            owner._on_close_request()
            assert owner.root.exists
            return ''
        dialog(monkeypatch, cancel)
        assert not frame.save() and frame.get_save_attempt() is None
        assert frame.preview.get_prepared_export() == event and capture(s) == before
        assert wrapper.close()
    Shell.action = inspect
    owner.open_timesheet()


@pytest.mark.parametrize('fault', ['construct', 'visibility', 'grab', 'competing-grab'])
def test_failed_construction_or_presentation_cleans_up_and_allows_reopen(setup, owner, monkeypatch, fault):
    s, *_ = setup
    before = capture(s)
    with monkeypatch.context() as m:
        if fault == 'construct': m.setattr(windows, 'TimesheetSaveFrame', fail)
        if fault == 'visibility': m.setattr(Shell, 'winfo_viewable', lambda self: False); m.setattr(Shell, 'wait_visibility', fail)
        if fault == 'grab': m.setattr(Shell, 'grab_set', fail)
        if fault == 'competing-grab':
            competitor = Shell(owner.root)
            m.setattr(Shell, 'winfo_viewable', lambda self: False)
            m.setattr(Shell, 'wait_visibility', lambda self: competitor.grab_set())
        assert owner.open_timesheet() is None
    assert owner._timesheet_window is None and not owner._timesheet_window_opening
    if fault == 'competing-grab':
        assert Window.grabbed is competitor
        competitor.destroy()
    assert owner.diagnostics and owner.open_timesheet()._destroyed and capture(s) == before


def test_retained_presentation_failure_preserves_attempt_and_cleanup_notes(setup, owner, monkeypatch, tmp_path):
    s, *_ = setup
    target = tmp_path / 'conflict.txt'; target.write_bytes(b'Existing')
    dialog(monkeypatch, str(target))
    monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: True)
    def inspect(_window):
        wrapper = owner._timesheet_window
        ready(wrapper.save_frame); assert not wrapper.save_frame.save()
        wrapper.close()
    Shell.action = inspect
    wrapper = owner.open_timesheet()
    attempt = wrapper.save_frame.get_save_attempt()
    with monkeypatch.context() as m:
        m.setattr(Shell, 'grab_set', fail)
        assert owner.open_timesheet() is None
    assert owner._timesheet_window is wrapper and not wrapper._destroyed and not wrapper.is_presented()
    assert wrapper.save_frame.get_save_attempt() == attempt and not owner._timesheet_window_opening
    Shell.action = lambda window: wrapper.close()
    assert owner.open_timesheet() is wrapper


def test_destroy_callback_identity_child_external_and_root_shutdown(setup, owner):
    wrappers = []
    def inspect(window):
        wrapper = owner._timesheet_window
        wrapper._on_destroy(SimpleNamespace(widget=wrapper.save_frame))
        assert owner._timesheet_window is wrapper
        owner._timesheet_disposed(object())
        assert owner._timesheet_window is wrapper
        wrappers.append(wrapper)
        window.destroy()
    Shell.action = inspect
    first = owner.open_timesheet()
    assert first._destroyed and owner._timesheet_window is None
    def shutdown(_window): owner.root.destroy()
    Shell.action = shutdown
    second = owner.open_timesheet()
    assert second._destroyed and owner._timesheet_window is None and not owner._timesheet_window_opening


@pytest.mark.parametrize('fault', ['registration-absent', 'registration-ambiguous', 'post-publication', 'conflict'])
def test_uncertain_attempt_closure_resume_preserves_identity_and_explicit_retry(
        setup, owner, monkeypatch, tmp_path, fault):
    s, a, *_ = setup
    dated(s, a, MON, 3600)
    s.start_task(a)
    target = tmp_path / 'retry.txt'
    if fault == 'conflict': target.write_bytes(b'Conflict')
    dialog(monkeypatch, str(target))
    confirmations, retained = [], []
    monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: confirmations.append(kw) or True)
    before = capture(s)
    def first(_window):
        wrapper = owner._timesheet_window
        frame = wrapper.save_frame
        event = ready(frame)
        append, materialize = s.storage.append_event, s.materialize_timesheet_export
        def ambiguous(candidate): append(candidate); raise OSError('Append result unverified')
        def after(identity, destination): materialize(identity, destination); raise OSError('After publication')
        with monkeypatch.context() as m:
            if fault == 'registration-absent': m.setattr(s.storage, 'append_event', fail)
            if fault == 'registration-ambiguous':
                m.setattr(s.storage, 'append_event', ambiguous)
                m.setattr(s.storage, 'synchronize_journal', fail)
            if fault == 'post-publication': m.setattr(s, 'materialize_timesheet_export', after)
            assert not frame.save() and frame.has_unfinished_attempt()
        if fault.startswith('registration'): assert not target.exists()
        if fault == 'post-publication': assert target.exists() and frame.saved_path is None
        retained.append((wrapper, frame.get_save_attempt(), event))
        assert wrapper.close()
    Shell.action = first
    wrapper = owner.open_timesheet()
    with monkeypatch.context() as m:
        m.setattr(s, 'prepare_timesheet_export_snapshot', lambda *a, **kw: pytest.fail('Resume recalculated'))
        def resumed(_window):
            assert owner._timesheet_window is wrapper
            frame = wrapper.save_frame
            assert frame.get_save_attempt() == retained[0][1]
            if fault == 'conflict':
                assert not frame.save() and frame.overwrite()
            else:
                assert frame.save()
            wrapper.close()
        Shell.action = resumed
        owner.open_timesheet()
    assert target.read_bytes() == retained[0][2]['payload']['report_text'].encode('utf-8')
    after = capture(s)
    assert after[0] == before[0] and after[2] == before[2] and after[4] == before[4] and after[6] == before[6]
    assert len(exports(s)) == 1
    assert len(confirmations) == (2 if fault == 'conflict' else 1)


def test_known_completion_presentation_failure_disposes_without_unverified_close_prompt(setup, owner, monkeypatch, tmp_path):
    s, *_ = setup
    target = tmp_path / 'saved.txt'
    dialog(monkeypatch, str(target))
    completed = []
    monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: pytest.fail('Known completion was called unverified'))
    def inspect(_window):
        wrapper = owner._timesheet_window
        frame = wrapper.save_frame
        ready(frame)
        with monkeypatch.context() as m:
            m.setattr(frame.status_var, 'set', fail)
            assert frame.save() and frame.saved_path == target
        assert not wrapper.has_unfinished_attempt()
        completed.append(frame)
        wrapper.close()
    Shell.action = inspect
    owner.open_timesheet()
    assert owner._timesheet_window is None and completed[0].saved_path == target
    Shell.action = lambda window: owner._timesheet_window.close()
    fresh = owner.open_timesheet()
    assert fresh.save_frame is not completed[0] and fresh.save_frame.get_save_attempt() is None


def test_failed_preview_then_empty_preview_is_usable_without_launch_failure(setup, owner, monkeypatch):
    s, *_ = setup
    before = capture(s)
    def inspect(_window):
        wrapper = owner._timesheet_window
        frame = wrapper.save_frame
        with monkeypatch.context() as m:
            m.setattr(s, 'prepare_timesheet_export_snapshot', fail)
            assert not frame.preview.refresh_preview() and frame.preview.error_label.visible
        assert frame.preview.refresh_preview() and frame.preview.get_prepared_export() is not None
        assert not frame.preview.error_label.visible and not frame.has_unfinished_attempt()
        wrapper.close()
    Shell.action = inspect
    assert owner.open_timesheet()._destroyed and capture(s) == before


def test_reentrant_constructor_stale_callback_and_cleanup_failure_keep_primary(setup, owner, monkeypatch):
    factory = windows.TimesheetSaveFrame
    def construct(*args, **kw):
        assert owner.open_timesheet() is None
        owner._on_close_request()
        assert owner.root.exists
        return factory(*args, **kw)
    monkeypatch.setattr(windows, 'TimesheetSaveFrame', construct)
    error = OSError('Release failure')
    def inspect(window):
        wrapper = owner._timesheet_window
        with monkeypatch.context() as m:
            m.setattr(window, 'grab_release', lambda: (_ for _ in ()).throw(error))
            wrapper.close()
    Shell.action = inspect
    assert owner.open_timesheet() is None
    assert owner.diagnostics[-1][1] is error and owner._timesheet_window is None
    assert not owner._timesheet_window_opening
    Shell.action = lambda window: owner._timesheet_window.close()
    owner.open_timesheet()


def test_real_tk_withdrawal_wait_reopen_and_external_destruction(setup, tk_root, pointer, monkeypatch, tmp_path):
    s, *_ = setup
    clock = Clock(local(s, TUE, 12))
    disposed, errors = [], []
    tk_root.report_callback_exception = lambda *args: errors.append(args)
    wrapper = windows.TimesheetWindow(tk_root, s, now_utc=clock, on_disposed=disposed.append)
    assert clock.calls == 0 and wrapper.window.state() == 'withdrawn'
    target = tmp_path / 'conflict.txt'; target.write_bytes(b'Keep')
    dialog(monkeypatch, str(target))
    monkeypatch.setattr(windows.messagebox, 'askyesno', lambda **kw: True)
    failures = []
    def first():
        try:
            ready(wrapper.save_frame)
            assert not wrapper.save_frame.save()
            pointer.click(wrapper.close_button)
        except BaseException as exc:
            failures.append(exc); wrapper._dispose()
    tk_root.after(50, first)
    wrapper.show_modal()
    assert failures == [] and not wrapper._destroyed and wrapper.window.state() == 'withdrawn'
    event, observation = wrapper.save_frame.get_save_attempt(), clock.calls
    def destroy():
        try:
            assert wrapper.save_frame.get_save_attempt() == event and clock.calls == observation
            wrapper.window.destroy()
        except BaseException as exc:
            failures.append(exc); wrapper._dispose()
    tk_root.after(50, destroy)
    wrapper.show_modal()
    assert failures == [] and disposed == [wrapper] and wrapper._destroyed
