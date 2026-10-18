"""Application-lifetime direction handoff, without production history routing."""

import builtins
from copy import deepcopy
from datetime import timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from tkinter import ttk

from task_timer import app as app_module
from task_timer import work_history_browser as browsers
from task_timer.settings import UISettings, UISettingsStore
from task_timer.storage import EventStorage
from test_app_ui import _FakeRoot
from test_mixed_accounting import setup, dated, local, MON, TUE
from test_work_history import interval, capture
from test_work_history_view import make_view
from test_work_history_browser import build, real_root, Clock, spy, state, drafts


@pytest.fixture
def owner_factory(monkeypatch):
    """Exercise the real constructor, isolating unrelated existing startup effects."""
    monkeypatch.setattr(app_module, 'install_zoom_guard', lambda root: None)
    monkeypatch.setattr(app_module, 'StringVar', lambda: SimpleNamespace())
    for name in ('refresh_structure', '_refresh_month_end_reminder_ui',
                 '_maybe_show_startup_reminder_popup', 'refresh_live_values', '_tick'):
        monkeypatch.setattr(app_module.TaskTimerApp, name, lambda self: None)
    def build_controls(owner):
        assert owner._history_newest_first is True  # established before controls
    monkeypatch.setattr(app_module.TaskTimerApp, '_build_ui', build_controls)

    def create(service, *, settings=None):
        settings = settings or UISettings()
        root = _FakeRoot()
        root.title = root.protocol = lambda *args: None
        with monkeypatch.context() as m:
            m.setattr(app_module, 'UISettingsStore', lambda path: SimpleNamespace(load=lambda: settings))
            m.setattr(app_module.tk, 'BooleanVar', lambda value=False: SimpleNamespace(get=lambda: value))
            return app_module.TaskTimerApp(root, service)
    return create


@pytest.mark.parametrize('unrelated_preference', [False, True])
def test_actual_startup_defaults_before_controls_without_importing_browser(setup, owner_factory, monkeypatch,
                                                                        unrelated_preference):
    s, *_ = setup
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        assert 'work_history_browser' not in name, 'Startup imported the staged browser'
        return original_import(name, *args, **kwargs)
    with monkeypatch.context() as m:
        m.setattr(builtins, '__import__', guarded_import)
        owner = owner_factory(s, settings=UISettings(sort_alphabetically=unrelated_preference,
                                                   keep_mini_open=unrelated_preference))
    assert owner._history_newest_first is True
    owner._remember_history_date_direction(False)
    assert owner._history_newest_first is False
    assert owner_factory(s)._history_newest_first is True


def test_sequential_tasks_and_datasets_receive_owner_choice_after_committed_render(
        setup, build, owner_factory, monkeypatch, tmp_path):
    s, a, b, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated(s, b, MON, 119.9)
    other = app_module.TaskTimerService(EventStorage(tmp_path / 'other-dataset'))
    c = other.create_task('Other dataset task', '')
    dated(other, c, TUE, 3600)
    before = capture(s), capture(other)
    owner = owner_factory(s)
    clock = Clock(local(s, TUE, 12))
    calls, other_calls = spy(s, monkeypatch), spy(other, monkeypatch)
    notifications = []
    setter = owner._remember_history_date_direction
    browser = None
    def remember(direction):
        assert browser.newest_first is direction
        assert list(browser.history._rows_by_iid.values()) == browser._rows
        assert not browser.history.tree.selection()
        notifications.append(direction)
        setter(direction)
    monkeypatch.setattr(owner, '_remember_history_date_direction', remember)
    browser = owner._make_history_browser(object(), s, a, now_utc=clock, week_start=0)
    assert browser.service is s and browser.task_id == a and browser.week_start == 0
    assert calls[-1] == (a, dict(cutoff_utc=clock.value.astimezone(timezone.utc),
                               newest_first=True, start_date=MON, end_date=MON + timedelta(days=6)))
    assert notifications == [] and owner.service is s
    old = state(browser)
    drafts(browser, 'unapplied', 'drafts')
    browser.history.tree.choose(browser.history.tree.get_children()[0])
    assert browser.history.tree.headings['date']['command']() is True
    assert notifications == [False] and owner._history_newest_first is False
    assert state(browser)[1:3] == old[1:3] and browser.info_var.get() == old[4]
    assert (browser.start_var.get(), browser.end_var.get()) == ('unapplied', 'drafts')
    assert clock.calls == len(calls) == 1
    assert browser.refresh() is True and notifications == [False]
    browser.destroy()
    assert owner._history_newest_first is False and notifications == [False]
    for service, task in ((s, b), (other, c)):
        subsequent = owner._make_history_browser(object(), service, task, now_utc=clock)
        assert subsequent.service is service and subsequent.task_id == task
        assert subsequent.newest_first is False
        subsequent.destroy()
    assert calls[-1][0] == b and calls[-1][1]['newest_first'] is False
    assert other_calls[-1][0] == c and other_calls[-1][1]['newest_first'] is False
    assert owner.service is s and notifications == [False]
    assert owner_factory(other)._history_newest_first is True
    assert (capture(s), capture(other)) == before


@pytest.mark.parametrize('fault', ['preparation', 'widget'])
def test_failed_sort_never_notifies_and_preserves_table_failure_boundary(
        setup, build, owner_factory, monkeypatch, fault):
    s, a, *_ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    owner = owner_factory(s)
    notifications = []
    monkeypatch.setattr(owner, '_remember_history_date_direction', notifications.append)
    clock = Clock(local(s, TUE, 12))
    browser = owner._make_history_browser(object(), s, a, now_utc=clock)
    browser.history.tree.choose(browser.history.tree.get_children()[0])
    before, mapping, selection = state(browser), deepcopy(browser.history._rows_by_iid), browser.history.tree.selection()
    if fault == 'preparation':
        # Fail the actual table preparation while preserving its previous mapping.
        class Uncopyable:
            def __deepcopy__(self, memo):
                raise ValueError('injected preparation failure')
        original = browser.history.display_rows
        monkeypatch.setattr(browser.history, 'display_rows', lambda rows: original([*rows, Uncopyable()]))
    else:
        browser.history.tree.fail_at = browser.history.tree.serial + 1
    assert browser.history.tree.headings['date']['command']() is False
    assert owner._history_newest_first is True and notifications == []
    assert state(browser) == before and clock.calls == 1
    assert 'Unable to sort history' in browser.error_var.get()
    if fault == 'preparation':
        assert browser.history._rows_by_iid == mapping and browser.history.tree.selection() == selection
        assert 'Previous results remain' in browser.history.error_var.get()
    else:
        assert browser.history._rows_by_iid == {} and not browser.history.tree.selection()
        assert not browser.history.table.visible


@pytest.mark.parametrize('initial_clock_valid', [False, True])
def test_loads_pickers_and_destruction_never_notify(setup, build, initial_clock_valid):
    s, a, *_ = setup
    notifications = []
    clock = Clock(local(s, TUE, 12) if initial_clock_valid else None)
    before = capture(s)
    browser = build(s, a, clock, on_direction_changed=notifications.append)
    assert notifications == []
    if not initial_clock_valid:
        assert browser.history.tree.headings['date']['command']() is False
    clock.value = local(s, TUE, 12)
    assert browser.refresh() is True
    drafts(browser, 'unapplied', 'drafts')
    assert browser.picker_buttons['Start'].invoke() is True
    popup, calendar = next(iter(browser._pickers.items()))
    calendar.choose(MON)
    browser.picker_buttons['End'].invoke()
    browser.destroy()
    assert notifications == [] and clock.calls == 2
    assert not browser._pickers and capture(s) == before


@pytest.mark.parametrize('callback', [False, 1, 'callback', object()])
def test_invalid_callback_rejected_before_widgets_clock_or_loading(setup, monkeypatch, callback):
    s, a, *_ = setup
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid callback reached widget construction, clock or service')
    monkeypatch.setattr(ttk.Frame, '__init__', forbidden)
    monkeypatch.setattr(s, 'get_task_work_history', forbidden)
    with pytest.raises(ValueError, match='on_direction_changed'):
        browsers.WorkHistoryBrowserFrame(object(), s, a, now_utc=forbidden, on_direction_changed=callback)


def test_notification_failure_is_completed_sort_not_render_failure(setup, build):
    s, a, *_ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    notifications = []
    def broken(direction):
        assert browser.newest_first is direction
        assert list(browser.history._rows_by_iid.values()) == browser._rows
        notifications.append(direction)
        raise RuntimeError('injected handoff failure')
    clock = Clock(local(s, TUE, 12))
    browser = build(s, a, clock, on_direction_changed=broken)
    before = state(browser)
    browser.history.tree.choose(browser.history.tree.get_children()[0])
    assert browser.history.tree.headings['date']['command']() is True
    assert notifications == [False] and browser.newest_first is False
    assert browser.history.table.visible and not browser.history.tree.selection()
    assert browser._rows == sorted(before[0], key=lambda row: row['work_date'])
    assert state(browser)[1:3] == before[1:3] and browser.info_var.get() == before[4]
    assert 'Unable to remember the session direction: injected handoff failure' == browser.error_var.get()
    assert 'sort history' not in browser.error_var.get() and browser.error_label.visible
    assert browser.history.error_var.get() == '' and clock.calls == 1


def test_sort_handoff_has_no_loading_persistence_cutoff_or_draft_effects(setup, build, owner_factory, monkeypatch):
    s, a, *_ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    owner = owner_factory(s)
    clock = Clock(local(s, TUE, 12))
    browser = owner._make_history_browser(object(), s, a, now_utc=clock)
    drafts(browser, 'unapplied', 'drafts')
    before, domain = state(browser), capture(s)
    def forbidden(*args, **kwargs):
        pytest.fail('Sort/handoff attempted loading, clock capture, settings or domain writes')
    with monkeypatch.context() as m:
        m.setattr(browser, '_now_utc', forbidden)
        for name in ('get_task_work_history', '_append', '_save_snapshot', 'start_task', 'stop_task'):
            m.setattr(s, name, forbidden)
        for name in ('append_event', 'save_snapshot', 'synchronize_journal', 'iter_all_events'):
            m.setattr(s.storage, name, forbidden)
        for name in ('__init__', 'load', 'save'):
            m.setattr(UISettingsStore, name, forbidden)
        for name in ('write_text', 'write_bytes', 'mkdir', 'unlink'):
            m.setattr(Path, name, forbidden)
        assert browser.history.tree.headings['date']['command']() is True
    assert owner._history_newest_first is False and clock.calls == 1
    assert state(browser)[1:3] == before[1:3] and browser.info_var.get() == before[4]
    assert (browser.start_var.get(), browser.end_var.get()) == ('unapplied', 'drafts')
    assert capture(s) == domain


def test_real_tk_sequential_construct_sort_destroy_reopen(setup, real_root, owner_factory):
    s, a, b, *_ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated(s, b, MON, 60)
    before = capture(s)
    owner = owner_factory(s)
    clock = Clock(local(s, TUE, 12))
    browser = owner._make_history_browser(real_root, s, a, now_utc=clock)
    browser.grid()
    real_root.update()
    command = browser.history.tree.heading('date', 'command')
    assert int(browser.history.tree.tk.call(command)) == 1
    assert owner._history_newest_first is False and browser.newest_first is False
    assert clock.calls == 1
    browser.destroy()
    real_root.update()
    assert owner._history_newest_first is False
    reopened = owner._make_history_browser(real_root, s, b, now_utc=clock)
    reopened.grid()
    real_root.update()
    assert reopened.newest_first is False and reopened.task_id == b
    assert list(reopened.history._rows_by_iid.values()) == reopened._rows
    reopened.destroy()
    real_root.update()
    assert clock.calls == 2 and capture(s) == before
    assert owner_factory(s)._history_newest_first is True
