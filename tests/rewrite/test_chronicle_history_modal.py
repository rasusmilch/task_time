"""History lifecycle/return failures using actual Tk and represented callbacks."""
from tk_observation import wait_observed
from copy import deepcopy
import tkinter as tk
from tkinter import ttk

import pytest

from chronicle.history_window import HistoryWindow, widget_live
from chronicle.records import Outcome
from chronicle.worker import Message
from test_app import root, connected, pump, create, evidence
from test_chronicle_history_ui import selected_task, open_history, seed, select


@pytest.mark.parametrize('mode',['local','none','missing','reused'])
def test_real_tk_history_parent_grab_focus_return_identity_and_guard(connected,root,monkeypatch,mode):
    app,worker,clock=connected; selected_task(app)
    saved=ttk.Entry(root,name='saved_focus'); saved.grid(row=9,column=0)
    pump(root,lambda:saved.winfo_ismapped())
    saved.focus_set(); wait_observed(root,lambda:root.focus_get() is saved,
        phase='PRECONDITION History origin focus',widgets=(saved,),foreground=True)
    if mode=='local': root.grab_set()
    before=evidence(worker); history=open_history(app)
    if mode in ('missing','reused'):
        saved.destroy()
        if mode=='reused':
            replacement=ttk.Entry(root,name='saved_focus'); replacement.grid(row=9,column=0)
            assert not widget_live(saved)
    targets=[]; expected=saved if mode in ('local','none') else root
    original=expected.focus_set
    def restore():
        targets.append(expected)
        assert app._history_opening and app.history is None
        assert not app.open_history()
        original()
    monkeypatch.setattr(expected,'focus_set',restore)
    history.close()
    assert app.history is None and not app._history_opening and targets==[expected]
    wait_observed(root,lambda:root.focus_get() is expected,phase='History actual return focus',widgets=(expected,))
    assert root.grab_current() is (root if mode=='local' else None)
    if mode=='local': root.grab_release()
    assert evidence(worker)==before and root.test_errors==[]


@pytest.mark.parametrize('global_grab',[False,True])
def test_real_tk_history_competing_local_or_global_grab_never_stolen(connected,root,global_grab):
    app,worker,clock=connected; selected_task(app)
    other=tk.Toplevel(root); field=ttk.Entry(other);field.pack()
    pump(root,lambda:other.winfo_viewable())
    if global_grab: other.grab_set_global()
    else: other.grab_set()
    before=evidence(worker); count=clock.calls
    assert not app.open_history() and app.history is None and not app._history_opening
    assert root.grab_current() is other and clock.calls==count and evidence(worker)==before
    other.grab_release()
    history=open_history(app)
    if global_grab: other.grab_set_global()
    else: other.grab_set()
    field.focus_set()
    history.close()
    assert root.grab_current() is other
    other.grab_release(); other.destroy()


@pytest.mark.parametrize('fault',['construction','presentation','map_grab'])
def test_real_tk_history_launch_failures_keep_original_diagnostics_and_allow_reopen(connected,root,monkeypatch,fault):
    import chronicle.history_window as module
    app,worker,clock=connected; selected_task(app)
    root.grab_set(); before=evidence(worker); error=RuntimeError(f'{fault} failure')
    with monkeypatch.context() as m:
        if fault=='construction': m.setattr(HistoryWindow,'_build',lambda self: (_ for _ in ()).throw(error))
        elif fault=='presentation': m.setattr(HistoryWindow,'present',lambda self: (_ for _ in ()).throw(error))
        else:
            original=tk.Toplevel.grab_set
            m.setattr(tk.Toplevel,'grab_set',lambda self: (_ for _ in ()).throw(error))
        accepted=app.open_history()
        if fault=='map_grab':
            assert accepted; pump(root,lambda:app.history is None)
        else: assert not accepted
    assert root.grab_current() is root and not app._history_opening and app.history is None
    assert evidence(worker)==before and any(args[1] is error for args in root.test_errors)
    root.grab_release()
    history=open_history(app); history.close()


def test_real_tk_history_grab_change_after_construction_is_rechecked(connected,root,monkeypatch):
    app,worker,clock=connected; selected_task(app)
    other=tk.Toplevel(root); pump(root,lambda:other.winfo_viewable())
    original=HistoryWindow.present
    def compete(history):
        assert app.history is history and app._history_opening
        assert not app.open_history()
        other.grab_set()
        original(history)
    monkeypatch.setattr(HistoryWindow,'present',compete)
    assert app.open_history(); pump(root,lambda:app.history is None)
    assert root.grab_current() is other and not app._history_opening
    other.grab_release(); other.destroy()
    assert any('unrelated or global' in str(args[1]) for args in root.test_errors)


def test_real_tk_history_return_failure_is_diagnosed_and_stale_disposal_cannot_clear_new_owner(connected,root,monkeypatch):
    app,worker,clock=connected; selected_task(app); history=open_history(app)
    error=RuntimeError('ordinary return focus failed')
    with monkeypatch.context() as m:
        m.setattr(root,'focus_set',lambda: (_ for _ in ()).throw(error))
        history.close()
    assert any(args[1] is error for args in root.test_errors)
    assert app.history is None and not app._history_opening
    later=open_history(app)
    app._history_disposed(history)
    assert app.history is later
    later.close()


def test_real_tk_history_primary_launch_failure_retains_return_diagnostic(connected,root,monkeypatch):
    app,worker,clock=connected; selected_task(app)
    primary=RuntimeError('presentation primary'); secondary=RuntimeError('return secondary')
    monkeypatch.setattr(HistoryWindow,'present',lambda self: (_ for _ in ()).throw(primary))
    monkeypatch.setattr(root,'focus_set',lambda: (_ for _ in ()).throw(secondary))
    assert not app.open_history()
    assert any(args[1] is primary for args in root.test_errors)
    assert any('return secondary' in note for note in primary.__notes__)
    assert not app._history_opening and app.history is None


def test_real_tk_history_root_destruction_disposes_calendar_and_queues_worker_shutdown(connected,root):
    app,worker,clock=connected; selected_task(app); history=open_history(app)
    history.period.set('Custom');history.period_changed(); history.start.set('2026-10-19')
    assert history.open_picker(history.start)
    picker=history.picker; before=len(root.test_errors)
    root.destroy();worker.join(timeout=6)
    assert not app.alive and not worker.is_alive()
    assert history.disposed and history.picker is None and app.history is None
    assert not widget_live(picker)
    assert root.test_errors[before:]==[]


def test_real_tk_history_loading_close_and_new_session_ignore_old_reads(connected,root,monkeypatch):
    from threading import Event
    from chronicle.services import TimerService
    app,worker,clock=connected; selected_task(app)
    entered,release=Event(),Event(); original=TimerService.read_history_snapshot
    def slow(service,**kwargs):
        entered.set();assert release.wait(5)
        return original(service,**kwargs)
    monkeypatch.setattr(TimerService,'read_history_snapshot',slow)
    assert app.open_history(); history=app.history
    pump(root,lambda:entered.is_set()); old=history.snapshot_token
    assert history.close() and app.history is None
    release.set(); monkeypatch.setattr(TimerService,'read_history_snapshot',original)
    later=open_history(app); snapshot=deepcopy(later.snapshot)
    app._handle(Message('history_snapshot',old,Outcome('unavailable',error=OSError('obsolete read'))))
    assert later.snapshot==snapshot and later.current and app.pending is None


def test_real_tk_history_launch_diagnostic_failure_never_masks_primary(connected,root,monkeypatch):
    app,worker,clock=connected;selected_task(app)
    primary=RuntimeError('construct primary'); secondary=RuntimeError('status secondary')
    with monkeypatch.context() as m:
        m.setattr(HistoryWindow,'_build',lambda self: (_ for _ in ()).throw(primary))
        m.setattr(app.status,'configure',lambda **kwargs: (_ for _ in ()).throw(secondary))
        assert not app.open_history()
    assert any(args[1] is primary for args in root.test_errors)
    assert any('status secondary' in note for note in primary.__notes__)
    assert not app._history_opening and app.history is None
    history=open_history(app);history.close()
