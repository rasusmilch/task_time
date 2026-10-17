"""Real service/table composition, UI doubles and separate actual-calendar Tk evidence."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest
from tkcalendar import Calendar as RealCalendar

from task_timer import work_history_browser as browsers
from task_timer import app as app_module
from task_timer.settings import UISettingsStore
from test_mixed_accounting import setup, dated, local, MON, TUE, SAT
from test_work_history import interval, capture
from test_work_history_view import make_view, Widget as TableWidget, Tree, values

UTC = timezone.utc


class Clock:
    def __init__(self, value):
        self.value, self.calls = value, 0
        self.error = None

    def __call__(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.value


class Widget(TableWidget):
    def bind(self, event, callback, add=None):
        self.bindings[event] = callback

    def winfo_toplevel(self):
        return self

    def destroy(self):
        self.destroyed = True
        if "<Destroy>" in self.bindings:
            self.bindings["<Destroy>"](SimpleNamespace(widget=self))


class Button(Widget):
    def invoke(self):
        if "variable" in self.options:
            self.options["variable"].set(self.options["value"])
        return self.options["command"]()


class Entry(Widget):
    def focus_out(self):
        if "<FocusOut>" in self.bindings:
            self.bindings["<FocusOut>"](None)


class HeadingTree(Tree):
    def heading(self, key, **options):
        self.headings.setdefault(key, {}).update(options)


class Popup(Widget):
    def title(self, text):
        self.title_text = text

    def transient(self, owner):
        self.owner = owner

    def protocol(self, name, callback):
        self.bindings[name] = callback


class Calendar(Widget):
    def __init__(self, master, **options):
        super().__init__(master, **options)
        self.selected = date(options['year'], options['month'], options['day'])

    def selection_get(self):
        return self.selected

    def choose(self, day):
        self.selected = day
        self.bindings['<<CalendarSelected>>'](None)


@pytest.fixture
def build(make_view, monkeypatch):
    monkeypatch.setattr(ttk.Frame, '__init__', Widget.__init__)
    for name in ('bind', 'winfo_toplevel', 'destroy'):
        monkeypatch.setattr(ttk.Frame, name, getattr(Widget, name))
    monkeypatch.setattr(ttk, 'Treeview', HeadingTree)
    monkeypatch.setattr(ttk, 'Button', Button)
    monkeypatch.setattr(ttk, 'Radiobutton', Button)
    monkeypatch.setattr(ttk, 'Entry', Entry)
    monkeypatch.setattr(browsers, 'Toplevel', Popup)
    monkeypatch.setattr(browsers, 'Calendar', Calendar)
    # Both modules use real StringVar names but share the same test variable contract.
    from test_work_history_view import Variable
    monkeypatch.setattr(browsers, 'StringVar', Variable)
    return lambda s, task, clock, **kw: browsers.WorkHistoryBrowserFrame(object(), s, task, now_utc=clock, **kw)


def spy(s, monkeypatch):
    original = s.get_task_work_history
    calls = []
    def read(task, **options):
        calls.append((task, deepcopy(options)))
        return original(task, **options)
    monkeypatch.setattr(s, 'get_task_work_history', read)
    return calls


def state(browser):
    return (deepcopy(browser._rows), browser._applied, browser._cutoff_utc,
            browser.newest_first, browser.info_var.get())


def drafts(browser, start, end):
    browser.period_buttons['Custom'].invoke()
    browser.start_var.set(start)
    browser.end_var.set(end)


@pytest.mark.parametrize('option,value', [('week_start', True), ('week_start', -1), ('week_start', 7),
    ('week_start', 1.0), ('week_start', '6'), ('newest_first', 1), ('newest_first', None), ('now_utc', None)])
def test_configuration_rejected_before_loading(setup, build, monkeypatch, option, value):
    s, a, _, _, _, _ = setup
    clock = Clock(local(s, TUE, 12))
    calls = spy(s, monkeypatch)
    if option == 'now_utc':
        with pytest.raises(ValueError):
            browsers.WorkHistoryBrowserFrame(object(), s, a, now_utc=value)
    else:
        with pytest.raises(ValueError):
            build(s, a, clock, **{option: value})
    assert not calls and clock.calls == 0


@pytest.mark.parametrize('week_start,start', [(0, MON), (1, TUE), (2, date(2026, 10, 7)),
    (3, date(2026, 10, 8)), (4, date(2026, 10, 9)), (5, date(2026, 10, 10)), (6, date(2026, 10, 11))])
def test_initial_load_all_week_starts_exact_arguments_and_purity(setup, build, monkeypatch, week_start, start):
    s, a, _, _, _, _ = setup
    before = capture(s)
    cutoff = local(s, TUE, 12).astimezone(timezone(timedelta(hours=5, minutes=30)))
    clock = Clock(cutoff)
    calls = spy(s, monkeypatch)
    browser = build(s, a, clock, week_start=week_start, newest_first=False)
    assert calls == [(a, {'cutoff_utc': cutoff.astimezone(UTC), 'newest_first': False,
                         'start_date': start, 'end_date': start + timedelta(days=6)})]
    assert clock.calls == 1 and not browser.newest_first
    assert browser._rows == [] and browser._applied == ('Current week', start, start + timedelta(days=6))
    assert browser.info_var.get().startswith(f'Last successful: Current week: {start}')
    assert 'as of 2026-10-13 12:00-05:00' in browser.info_var.get()
    assert not browser.error_var.get() and capture(s) == before


@pytest.mark.parametrize('instant,expected', [
    (datetime(2026, 10, 18, 4, 59, tzinfo=UTC), date(2026, 10, 11)),
    (datetime(2026, 10, 18, 5, 0, tzinfo=UTC), date(2026, 10, 18)),
    (datetime(2026, 3, 8, 6, 0, tzinfo=UTC), date(2026, 3, 8)),
    (datetime(2026, 11, 1, 5, 0, tzinfo=UTC), date(2026, 11, 1)),
])
def test_current_week_local_dates_roll_over_on_refresh_not_fixed_utc_hours(setup, build, monkeypatch, instant, expected):
    s, a, _, _, _, _ = setup
    clock = Clock(local(s, TUE, 12))
    calls = spy(s, monkeypatch)
    browser = build(s, a, clock)
    clock.value = instant
    assert browser.refresh() is True
    assert calls[-1][1]['start_date'] == expected
    assert calls[-1][1]['end_date'] == expected + timedelta(days=6)
    assert calls[-1][1]['cutoff_utc'] == instant
    assert clock.calls == len(calls) == 2


@pytest.mark.parametrize('day,hours', [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_browser_loads_dst_day_amounts_through_real_reader_and_table(setup, build, day, hours):
    s, a, _, _, _, _ = setup
    first = local(s, day).astimezone(UTC)
    stop = local(s, day + timedelta(days=1)).astimezone(UTC)
    identity = interval(s, a, first, stop)
    browser = build(s, a, Clock(local(s, day + timedelta(days=1), 12)))
    assert len(browser._rows) == 1 and browser._rows[0]['entry_id'] == identity
    assert browser._rows[0]['duration_seconds'] == hours * 3600
    assert values(browser.history)[0][-1] == f'{hours}:00'


def test_custom_all_mixed_running_future_dated_and_inclusive_filtering(setup, build, monkeypatch):
    s, a, _, _, _, service_clock = setup
    identity = interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated_id = dated(s, a, SAT, 50400.125)  # future relative to Tuesday cutoff, still declared Saturday
    service_clock[0] = local(s, TUE, 9).astimezone(UTC)
    s.start_task(a)
    cutoff = local(s, TUE, 10).astimezone(UTC)
    clock = Clock(cutoff)
    calls = spy(s, monkeypatch)
    before = capture(s)
    browser = build(s, a, clock)
    assert {r['entry_id'] for r in browser._rows} == {identity, dated_id, '__open__'}
    assert next(r for r in browser._rows if r['entry_id'] == dated_id)['duration_seconds'] == 50400.125
    assert next(r for r in browser._rows if r['is_running'])['segment_stop_utc'] == cutoff
    assert list(browser.history._rows_by_iid.values()) == browser._rows
    old = deepcopy(browser._rows)
    drafts(browser, f' {MON} ', str(MON))
    assert len(calls) == clock.calls == 1
    assert browser.apply_button.invoke() is True
    assert {r['work_date'] for r in browser._rows} == {MON}
    assert browser._rows[0]['continues_after'] and browser._rows[0]['original_stop_utc'] == local(s, TUE, 8).astimezone(UTC)
    assert browser.period_buttons['All'].invoke() is True
    assert set(calls[-1][1]) == {'cutoff_utc', 'newest_first'}
    assert browser.start_var.get() == f' {MON} ' and browser.end_var.get() == str(MON)
    assert browser._rows == old and capture(s) == before


def test_sort_only_existing_rows_stably_no_clock_new_work_or_draft_application(setup, build, monkeypatch):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 10), local(s, MON, 11))
    interval(s, a, local(s, MON, 8), local(s, MON, 9))
    dated(s, a, MON, 119.9)
    dated(s, a, TUE, 60)
    clock = Clock(local(s, TUE, 12))
    calls = spy(s, monkeypatch)
    browser = build(s, a, clock)
    before = state(browser)
    monday = [r for r in before[0] if r['work_date'] == MON]
    late_id = dated(s, a, TUE, 7200)
    drafts(browser, 'bad', 'also bad')
    browser.history.tree.choose(browser.history.tree.get_children()[0])
    heading = browser.history.tree.headings['date']['command']
    assert heading() is True
    assert not browser.newest_first and browser._rows == monday + [r for r in before[0] if r['work_date'] == TUE]
    assert len(calls) == clock.calls == 1
    assert browser._applied == before[1] and browser._cutoff_utc == before[2] and browser.info_var.get() == before[4]
    assert not browser.history.tree.selection()
    assert not any(r['entry_id'] == late_id for r in browser._rows)
    assert heading() is True and browser._rows == before[0] and browser.newest_first
    assert browser.refresh() is True
    assert any(r['entry_id'] == late_id for r in browser._rows)
    assert len(calls) == clock.calls == 2
    assert browser.start_var.get() == 'bad'
    before[0][0]['reason'] = 'mutated detached result'
    assert all(r['reason'] != 'mutated detached result' for r in browser._rows)


@pytest.mark.parametrize('start,end', [('2026-1-12', str(TUE)), ('20261012', str(TUE)),
    ('2026-W42-1', str(TUE)), ('2026-02-30', str(TUE)), ('', str(TUE)), (str(TUE), str(MON)),
    (str(MON), '9999-12-31'), ('0000-01-01', str(TUE))])
def test_invalid_drafts_preserve_rows_selection_information_and_text(setup, build, monkeypatch, start, end):
    s, a, _, _, _, _ = setup
    dated(s, a, MON, 60)
    clock = Clock(local(s, TUE, 12))
    calls = spy(s, monkeypatch)
    browser = build(s, a, clock)
    browser.history.tree.choose(browser.history.tree.get_children()[0])
    old = state(browser), deepcopy(browser.history._rows_by_iid), browser.history.tree.selection()
    drafts(browser, start, end)
    browser.date_entries['Start'].focus_out()
    assert browser.apply_button.invoke() is False
    assert (state(browser), browser.history._rows_by_iid, browser.history.tree.selection()) == old
    assert (browser.start_var.get(), browser.end_var.get()) == (start, end)
    assert clock.calls == len(calls) == 1 and browser.error_label.visible


def test_refresh_uses_committed_custom_not_new_drafts_or_unapplied_period(setup, build, monkeypatch):
    s, a, _, _, _, _ = setup
    clock = Clock(local(s, TUE, 12))
    calls = spy(s, monkeypatch)
    browser = build(s, a, clock)
    drafts(browser, str(MON), str(TUE))
    assert browser.apply_button.invoke()
    browser.start_var.set('bad')
    browser.end_var.set(str(SAT))
    clock.value += timedelta(days=10)
    assert browser.refresh_button.invoke()
    assert calls[-1][1]['start_date'] == MON and calls[-1][1]['end_date'] == TUE
    assert browser.start_var.get() == 'bad' and browser.end_var.get() == str(SAT)
    assert browser._cutoff_utc == clock.value.astimezone(UTC)
    browser.period_buttons['Current week'].invoke()
    assert browser._applied == ('Current week', date(2026, 10, 18), date(2026, 10, 24))
    assert browser.start_var.get() == 'bad'


def test_picker_drafts_seeds_cancellation_and_owned_destruction_no_load(setup, build, monkeypatch):
    s, a, _, _, _, _ = setup
    clock = Clock(local(s, TUE, 12))
    calls = spy(s, monkeypatch)
    browser = build(s, a, clock)
    drafts(browser, 'bad', str(SAT))
    browser.picker_buttons['Start'].invoke()
    popup, calendar = next(iter(browser._pickers.items()))
    assert calendar.selected == TUE
    popup.bindings['WM_DELETE_WINDOW']()
    assert popup.destroyed and browser.start_var.get() == 'bad' and not browser._pickers
    browser.picker_buttons['End'].invoke()
    popup, calendar = next(iter(browser._pickers.items()))
    assert calendar.selected == SAT
    calendar.choose(MON)
    assert popup.destroyed and browser.end_var.get() == str(MON) and browser.start_var.get() == 'bad'
    browser.picker_buttons['Start'].invoke()
    browser.picker_buttons['End'].invoke()
    owned = list(browser._pickers)
    browser.destroy()
    assert all(p.destroyed for p in owned) and not browser._pickers
    assert clock.calls == len(calls) == 1


def test_initial_failure_no_seed_then_retry_week_and_valid_empty_are_distinct(setup, build, monkeypatch):
    s, a, _, _, _, _ = setup
    clock = Clock(None)
    calls = spy(s, monkeypatch)
    browser = build(s, a, clock)
    assert browser.info_var.get() == 'Not loaded' and browser._rows is None
    assert browser.error_label.visible and not calls
    assert browser.history.tree.headings['date']['command']() is False
    drafts(browser, '', '')
    assert browser.picker_buttons['Start'].invoke() is False
    assert not browser._pickers and 'No valid draft' in browser.error_var.get()
    assert clock.calls == 1
    # A valid draft can seed a picker even without any valid clock observation.
    browser.end_var.set(str(SAT))
    assert browser.picker_buttons['End'].invoke()
    assert next(iter(browser._pickers.values())).selected == SAT
    browser.end_var.set('invalid')
    clock.value = local(s, TUE, 12)
    assert browser.refresh() is True
    assert browser._rows == [] and browser._applied[0] == 'Current week'
    assert browser.info_var.get().startswith('Last successful:') and browser.error_var.get() == ''
    assert clock.calls == 2 and len(calls) == 1


def test_initial_service_failure_remains_not_loaded_until_explicit_retry(setup, build, monkeypatch):
    s, a, _, _, _, _ = setup
    clock = Clock(local(s, TUE, 12))
    with monkeypatch.context() as m:
        m.setattr(s, 'get_task_work_history', lambda *args, **kw: (_ for _ in ()).throw(OSError('reader unavailable')))
        browser = build(s, a, clock)
    assert browser._applied is None and browser._rows is None and browser.info_var.get() == 'Not loaded'
    assert 'reader unavailable' in browser.error_var.get()
    assert browser._observation_date == TUE
    assert browser.refresh() is True
    assert browser._rows == [] and browser._cutoff_utc == clock.value.astimezone(UTC)


def test_picker_failure_is_inline_without_clock_reader_or_draft_change(setup, build, monkeypatch):
    s, a, _, _, _, _ = setup
    clock = Clock(local(s, TUE, 12))
    calls = spy(s, monkeypatch)
    browser = build(s, a, clock)
    drafts(browser, 'bad', str(SAT))
    with monkeypatch.context() as m:
        m.setattr(browsers, 'Calendar', lambda *args, **kw: (_ for _ in ()).throw(tk.TclError('calendar failed')))
        assert browser.picker_buttons['Start'].invoke() is False
    assert browser.start_var.get() == 'bad' and not browser._pickers
    assert 'calendar failed' in browser.error_var.get()
    browser.picker_buttons['End'].invoke()
    popup, calendar = next(iter(browser._pickers.items()))
    calendar.choose('invalid selection')
    assert browser.end_var.get() == str(SAT) and 'calendar date' in browser.error_var.get()
    assert clock.calls == len(calls) == 1


@pytest.mark.parametrize('fault', ['clock-error', 'naive', 'wrong-type', 'unrepresentable', 'service', 'preparation', 'widget'])
def test_failed_load_never_installs_candidate_or_rolls_back_table_guarantees(setup, build, monkeypatch, fault):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    clock = Clock(local(s, TUE, 12))
    browser = build(s, a, clock)
    browser.history.tree.choose(browser.history.tree.get_children()[0])
    old, mapping, selection = state(browser), deepcopy(browser.history._rows_by_iid), browser.history.tree.selection()
    original = s.get_task_work_history
    drafts(browser, str(MON), str(TUE))
    clock.value += timedelta(hours=1)
    if fault == 'clock-error': clock.error = OSError('clock failed')
    if fault == 'naive': clock.value = datetime(2026, 10, 13)
    if fault == 'wrong-type': clock.value = 'not a datetime'
    if fault == 'unrepresentable': clock.value = datetime.min.replace(tzinfo=UTC)
    def broken(*args, **kwargs):
        if fault == 'service': raise OSError('reader failed')
        result = original(*args, **kwargs)
        if fault == 'preparation': result[-1]['entry_kind'] = 'unsupported'
        return result
    with monkeypatch.context() as m:
        if fault in ('service', 'preparation'): m.setattr(s, 'get_task_work_history', broken)
        if fault == 'widget': browser.history.tree.fail_at = browser.history.tree.serial + 2
        assert browser.apply_button.invoke() is False
    assert state(browser) == old
    assert (browser.start_var.get(), browser.end_var.get()) == (str(MON), str(TUE))
    assert browser.error_label.visible
    if fault == 'widget':
        assert browser.history._rows_by_iid == {} and not browser.history.table.visible
        assert not browser.history.tree.selection() and 'Table unavailable' in browser.history.error_var.get()
    else:
        assert browser.history._rows_by_iid == mapping and browser.history.tree.selection() == selection
    clock.error, clock.value = None, local(s, TUE, 14)
    browser.history.tree.fail_at = None
    assert browser.refresh() is True
    assert browser._applied[0] == 'Current week'  # failed custom candidate was never applied
    assert not browser.history.tree.selection() and not browser.error_var.get()
    assert browser.history.table.visible


def test_failed_sort_keeps_direction_cutoff_applied_result_and_never_observes_clock(setup, build):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    clock = Clock(local(s, TUE, 12))
    browser = build(s, a, clock)
    before = state(browser)
    browser.history.tree.fail_at = browser.history.tree.serial + 1
    assert browser.history.tree.headings['date']['command']() is False
    assert state(browser) == before and clock.calls == 1
    assert not browser.history.table.visible and browser.history._rows_by_iid == {}
    browser.history.tree.fail_at = None
    assert browser.refresh() is True
    assert browser.newest_first and browser.history.table.visible


def test_switch_failure_refreshes_previous_all_period_and_keeps_drafts(setup, build):
    s, a, _, _, _, _ = setup
    clock = Clock(local(s, TUE, 12))
    browser = build(s, a, clock)
    assert browser.period_buttons['All'].invoke()
    drafts(browser, 'unapplied', 'drafts')
    clock.error = OSError('unavailable')
    assert browser.period_buttons['Current week'].invoke() is False
    assert browser._applied[0] == 'All'
    clock.error = None
    assert browser.refresh() and browser._applied == ('All', None, None)
    assert (browser.start_var.get(), browser.end_var.get()) == ('unapplied', 'drafts')


def test_all_operations_are_work_dataset_settings_and_timer_pure(setup, build, monkeypatch):
    s, a, _, _, _, service_clock = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated(s, a, SAT, 50400.125)
    service_clock[0] = local(s, TUE, 9).astimezone(UTC)
    s.start_task(a)
    before = capture(s)
    clock = Clock(local(s, TUE, 12))
    def forbidden(*args, **kwargs):
        pytest.fail('Browser attempted work/settings persistence, reconstruction or scheduled loading')
    with monkeypatch.context() as m:
        for name in ('_append', '_save_snapshot', 'start_task', 'stop_task', 'create_backup_now', 'calculate_date_window'):
            m.setattr(s, name, forbidden)
        for name in ('iter_all_events', 'append_event', 'save_snapshot', 'synchronize_journal'):
            m.setattr(s.storage, name, forbidden)
        for name in ('__init__', 'load', 'save'):
            m.setattr(UISettingsStore, name, forbidden)
        for name in ('write_bytes', 'write_text', 'unlink', 'mkdir'):
            m.setattr(Path, name, forbidden)
        for name in ('after', 'after_idle'):
            m.setattr(ttk.Frame, name, forbidden)
        m.setattr(app_module, 'utc_now', forbidden)
        m.setattr(app_module, 'uuid4', forbidden)
        browser = build(s, a, clock)
        browser.period_buttons['All'].invoke()
        drafts(browser, str(MON), str(TUE))
        browser.picker_buttons['Start'].invoke()
        popup, calendar = next(iter(browser._pickers.items()))
        calendar.choose(MON)
        browser.apply_button.invoke()
        browser.history.tree.choose(browser.history.tree.get_children()[0])
        browser.history.tree.headings['date']['command']()
        browser.refresh()
    assert capture(s) == before


@pytest.fixture
def real_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f'Real Tk/display unavailable: {exc}')
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    try:
        yield root
    finally:
        root.destroy()
        assert errors == []


def test_real_tk_calendar_drafts_focus_apply_heading_refresh_failures_and_disposal(setup, real_root, monkeypatch):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated(s, a, SAT, 50400.125)
    clock = Clock(local(s, TUE, 12))
    calls = spy(s, monkeypatch)
    before = capture(s)
    browser = browsers.WorkHistoryBrowserFrame(real_root, s, a, now_utc=clock)
    browser.grid()
    real_root.deiconify()
    real_root.update()
    browser.period_buttons['Custom'].invoke()
    browser.date_entries['Start'].insert(0, 'invalid draft')
    browser.date_entries['Start'].focus_force()
    real_root.update()
    assert real_root.focus_get() == browser.date_entries['Start']
    browser.date_entries['End'].focus_set()
    real_root.update()
    assert real_root.focus_get() == browser.date_entries['End']
    assert browser.start_var.get() == 'invalid draft' and clock.calls == len(calls) == 1
    browser.picker_buttons['Start'].invoke()
    popup, calendar = next(iter(browser._pickers.items()))
    assert isinstance(calendar, RealCalendar) and calendar.selection_get() == TUE
    calendar.selection_set(MON)
    calendar.event_generate('<<CalendarSelected>>')
    real_root.update()
    assert browser.start_var.get() == str(MON) and not popup.winfo_exists()
    browser.end_var.set(str(TUE))
    browser.picker_buttons['End'].invoke()
    popup, calendar = next(iter(browser._pickers.items()))
    assert calendar.selection_get() == TUE
    popup.tk.call(popup.protocol('WM_DELETE_WINDOW'))
    real_root.update()
    assert browser.end_var.get() == str(TUE) and not browser._pickers
    assert clock.calls == len(calls) == 1
    browser.apply_button.invoke()
    real_root.update()
    assert browser._applied == ('Custom', MON, TUE) and clock.calls == len(calls) == 2
    handles = browser.history.tree.get_children()
    browser.history.tree.selection_set(handles[0])
    real_root.update()
    assert browser.history.tree.selection()
    command = browser.history.tree.heading('date', 'command')
    browser.history.tree.tk.call(command)
    real_root.update()
    assert not browser.newest_first and not browser.history.tree.selection()
    assert clock.calls == len(calls) == 2
    browser.start_var.set('unapplied bad draft')
    browser.refresh_button.invoke()
    real_root.update()
    assert browser._applied == ('Custom', MON, TUE) and browser.start_var.get() == 'unapplied bad draft'
    assert clock.calls == len(calls) == 3
    old = state(browser), browser.history.tree.get_children()
    clock.error = OSError('injected unavailable clock')
    browser.refresh_button.invoke()
    real_root.update()
    assert (state(browser), browser.history.tree.get_children()) == old
    assert browser.error_label.winfo_manager() == 'grid'
    clock.error = None
    browser.refresh_button.invoke()
    real_root.update()
    assert browser.error_var.get() == ''
    # Inject a real widget update failure, retaining the table's own invalidation.
    with monkeypatch.context() as m:
        m.setattr(browser.history.tree, 'insert', lambda *args, **kwargs: (_ for _ in ()).throw(tk.TclError('injected widget')))
        browser.refresh_button.invoke()
    real_root.update()
    assert browser.history._rows_by_iid == {} and browser.history.table.winfo_manager() == ''
    browser.refresh_button.invoke()
    real_root.update()
    assert browser.history.table.winfo_manager() == 'grid' and browser.error_var.get() == ''
    assert list(browser.history._rows_by_iid.values()) == browser._rows
    browser.picker_buttons['Start'].invoke()
    popup = next(iter(browser._pickers))
    browser.destroy()
    real_root.update()
    assert not popup.winfo_exists() and not browser._pickers
    assert capture(s) == before
