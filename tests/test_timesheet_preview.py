"""Frozen-candidate preview over real isolated accounting and snapshot preparation."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from task_timer import timesheet_preview as previews
from task_timer.settings import UISettingsStore
from task_timer.storage import EventStorage
from task_timer.app import TaskTimerService
from test_mixed_accounting import setup, dated, local, MON, TUE, SAT
from test_work_history import interval, capture
from test_work_history_browser import Clock, Widget, Popup, Calendar
from test_history_window import tk_root, pointer

UTC = timezone.utc


class Variable:
    def __init__(self, master, value=''):
        self.value, self.callbacks = value, []
    def get(self): return self.value
    def set(self, value):
        self.value = value
        for callback in tuple(self.callbacks): callback('', '', 'write')
    def trace_add(self, mode, callback): self.callbacks.append(callback)


class Button(Widget):
    def invoke(self):
        variable = self.options.get('variable')
        if variable is not None:
            variable.set(self.options.get('value', not variable.get()))
        command = self.options.get('command')
        return command() if command else None


class Canvas(Widget):
    def create_window(self, *args, **kw): pass
    def bbox(self, *args): return (0, 0, 700, 200)
    def yview(self, *args): pass
    xview = yview


class Text(Canvas):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.text, self.failure = '', None
    def configure(self, **options):
        if self.failure == 'configure': raise self.error
        super().configure(**options)
    def delete(self, *args):
        if self.failure == 'delete': raise self.error
        self.text = ''
    def insert(self, index, value):
        if self.failure == 'insert':
            self.text = 'partial untrusted output'
            raise self.error
        self.text = value
    def get(self, *args): return self.text


@pytest.fixture
def build(monkeypatch):
    errors = []
    root = SimpleNamespace(report_callback_exception=lambda *args: errors.append(args))
    monkeypatch.setattr(ttk.Frame, '__init__', Widget.__init__)
    for name in ('grid', 'grid_remove', 'configure', 'bind', 'destroy', 'winfo_toplevel'):
        monkeypatch.setattr(ttk.Frame, name, getattr(Widget, name))
    for name in ('grid_columnconfigure', 'grid_rowconfigure'):
        monkeypatch.setattr(ttk.Frame, name, lambda *a, **kw: None)
    monkeypatch.setattr(ttk.Frame, '_root', lambda self: root)
    for name in ('Button', 'Radiobutton', 'Checkbutton'): monkeypatch.setattr(ttk, name, Button)
    for name in ('Entry', 'Label', 'Scrollbar'): monkeypatch.setattr(ttk, name, Widget)
    monkeypatch.setattr(previews.tk, 'Canvas', Canvas)
    monkeypatch.setattr(previews.tk, 'Text', Text)
    monkeypatch.setattr(previews, 'StringVar', Variable)
    monkeypatch.setattr(previews, 'BooleanVar', Variable)
    monkeypatch.setattr(previews, 'Calendar', Calendar)
    monkeypatch.setattr(previews, 'Toplevel', Popup)
    def create(service, clock):
        frame = previews.TimesheetPreviewFrame(object(), service, now_utc=clock)
        frame.diagnostics = errors
        return frame
    return create


def spy(service, monkeypatch):
    prepare, calculate = service.prepare_timesheet_export_snapshot, service.calculate_date_window
    calls, calculations, events = [], [], []
    def freeze(*args, **kw):
        calls.append((args, deepcopy(kw)))
        result = prepare(*args, **kw)
        events.append(deepcopy(result))
        return result
    def account(*args, **kw):
        calculations.append((args, deepcopy(kw)))
        return calculate(*args, **kw)
    monkeypatch.setattr(service, 'prepare_timesheet_export_snapshot', freeze)
    monkeypatch.setattr(service, 'calculate_date_window', account)
    return calls, calculations, events


def pure(frame, monkeypatch, operation=None):
    s = frame.service
    before = capture(s)
    def forbidden(*args, **kw): pytest.fail('Preview performed prohibited durable operation')
    with monkeypatch.context() as m:
        for name in ('register_prepared_timesheet_export', 'materialize_timesheet_export',
                     'evaluate_timesheet_export_file_status', '_append', '_save_snapshot',
                     'generate_date_range_timesheet', 'create_backup_now', '_rebuild_state'):
            m.setattr(s, name, forbidden)
        for name in ('append_event', 'save_snapshot', 'iter_all_events', 'synchronize_journal'):
            m.setattr(s.storage, name, forbidden)
        m.setattr(s.backups, 'create_backup', forbidden)
        m.setattr(s.backups, 'create_safety_backup', forbidden)
        m.setattr(UISettingsStore, 'save', forbidden)
        result = (operation or frame.refresh_preview)()
    assert capture(s) == before
    return result


def drafts(frame, start, end):
    frame.period_buttons['Custom'].invoke()
    frame.start_var.set(start)
    frame.end_var.set(end)


def cell(event, task_id, day):
    task = next(row for row in event['payload']['tasks'] if row['task_id'] == task_id)
    return next(row for row in task['daily'] if row['work_date'] == str(day))


def test_constructor_explicit_only_and_invalid_clock_configuration(setup, build, monkeypatch):
    s, *_ = setup
    clock = Clock(local(s, TUE, 12))
    calls, calculations, _ = spy(s, monkeypatch)
    frame = build(s, clock)
    assert isinstance(frame, ttk.Frame) and clock.calls == 0 and calls == calculations == []
    assert frame.period_var.get() == 'This week' and frame.scope_var.get() == 'All tasks'
    assert frame.preview_button.options['text'] == 'Preview'
    assert frame.get_prepared_export() is None and frame.report.options['state'] == 'disabled'
    with pytest.raises(ValueError, match='callable'): build(s, None)
    assert clock.calls == 0 and calls == []


@pytest.mark.parametrize('observation,start', [
    (datetime(2026, 10, 12, 12, tzinfo=UTC), date(2026, 10, 11)),  # Monday
    (datetime(2027, 1, 1, 12, tzinfo=UTC), date(2026, 12, 27)),
    (datetime(2026, 3, 9, 12, tzinfo=UTC), date(2026, 3, 8)),
    (datetime(2026, 11, 2, 12, tzinfo=UTC), date(2026, 11, 1)),
    (datetime(2026, 10, 18, 2, tzinfo=UTC), date(2026, 10, 11)),  # Still local Saturday
])
@pytest.mark.parametrize('period,delta', [('This week', 0), ('Last week', 7)])
def test_relative_periods_one_observation_exact_service_request(setup, build, monkeypatch, observation, start, period, delta):
    s, *_ = setup
    clock = Clock(observation.astimezone(timezone(timedelta(hours=5, minutes=30))))
    frame = build(s, clock)
    calls, calculations, events = spy(s, monkeypatch)
    frame.period_buttons[period].invoke()
    assert clock.calls == 0
    assert pure(frame, monkeypatch) is True
    first = start - timedelta(days=delta)
    assert calls == [((first, first + timedelta(days=6)), dict(cutoff_utc=observation,
        all_tasks=True, task_ids=(), include_deleted=True, preferred_destination=None))]
    assert len(calculations) == clock.calls == 1 and calculations[0][1]['cutoff_utc'] == observation
    candidate = frame.get_prepared_export()
    assert candidate == events[0] and candidate['payload']['preferred_destination'] is None
    assert frame.report.text == candidate['payload']['report_text']
    assert frame.preview_button.options['text'] == 'Refresh'
    assert str(first) in frame.info_var.get() and observation.isoformat().replace('+00:00', 'Z') in frame.info_var.get()


def test_mixed_rounding_cutoff_independent_selected_and_deleted_identity(setup, build, monkeypatch):
    s, a, b, _, _, clock_value = setup
    child = s.create_subtask(a, 'A', '')
    s.update_task(b, 'A', '')
    interval(s, a, local(s, MON, 8), local(s, MON, 9))
    dated(s, a, MON, 18.125)  # 0.005 hour boundary rounds half up.
    dated(s, child, SAT, 50400.125)
    dated(s, b, MON, 1800)
    s.delete_task_only(b)
    clock_value[0] = local(s, TUE, 10).astimezone(UTC)
    s.start_task(a)
    cutoff = local(s, TUE, 11).astimezone(UTC)
    frame = build(s, Clock(cutoff))
    calls, calculations, _ = spy(s, monkeypatch)
    assert set(frame.task_buttons) == {a, b, child}
    assert '(deleted)' in frame.task_buttons[b].options['text']
    assert all(key in frame.task_buttons[key].options['text'] for key in (a, b, child))
    frame.scope_buttons['Selected tasks'].invoke()
    assert pure(frame, monkeypatch) is False and not calls
    frame.task_buttons[a].invoke()
    assert not frame.task_vars[child].get() and not calls
    drafts(frame, f' {MON} ', str(SAT))
    assert pure(frame, monkeypatch) is True
    event = frame.get_prepared_export()
    assert {row['task_id'] for row in event['payload']['tasks']} == {a}
    assert event['payload']['selection']['task_ids'] == [a]
    assert cell(event, a, MON)['actual_seconds'] == 3618.125 and cell(event, a, MON)['decimal_hundredths'] == 101
    assert cell(event, a, TUE)['actual_seconds'] == 3600
    frame.task_buttons[b].invoke()
    assert frame.get_prepared_export() is None
    assert pure(frame, monkeypatch) is True
    assert cell(frame.get_prepared_export(), b, MON)['decimal_hundredths'] == 50
    frame.scope_buttons['All tasks'].invoke()
    assert pure(frame, monkeypatch) is True
    event = frame.get_prepared_export()
    assert cell(event, child, SAT)['actual_seconds'] == 50400.125
    assert frame.report.text == event['payload']['report_text']
    assert sha256(frame.report.text.encode('utf-8')).hexdigest() == event['payload']['report_sha256']
    assert len(calculations) == len(calls) == 3 and frame._now_utc.calls == 4


@pytest.mark.parametrize('edit', ['period', 'start', 'end', 'scope', 'task'])
def test_drafts_backtracking_getter_purity_and_frozen_later_work(setup, build, monkeypatch, edit):
    s, a, _, _, _, clock_value = setup
    entry = dated(s, a, MON, 3600)
    clock = Clock(local(s, TUE, 12))
    frame = build(s, clock)
    assert pure(frame, monkeypatch)
    old = frame.get_prepared_export()
    returned = frame.get_prepared_export()
    returned['payload']['report_text'] = 'caller mutation'
    returned['payload']['tasks'][0]['daily'][0]['actual_seconds'] = -999
    assert frame.get_prepared_export() == old
    # Actual changes and labels do not mutate or automatically refresh this candidate.
    dated(s, a, MON, 7200, entry, 'dated_duration_corrected')
    s.update_task(a, 'Renamed', '')
    s.assign_task_to_project(a, s.create_project('New grouping'))
    assert frame.get_prepared_export() == old and clock.calls == 1
    variable, value = {'period': (frame.period_var, 'Last week'), 'start': (frame.start_var, 'bad'),
        'end': (frame.end_var, str(SAT)), 'scope': (frame.scope_var, 'Selected tasks'),
        'task': (frame.task_vars[a], True)}[edit]
    prior = variable.get()
    variable.set(value)
    variable.set(prior)
    assert frame.get_prepared_export() is None and frame.report.text == old['payload']['report_text']
    assert 'Previous preview:' in frame.info_var.get() and old['payload']['start_date'] in frame.info_var.get()
    with monkeypatch.context() as m:
        m.setattr(frame, '_now_utc', lambda: pytest.fail('getter observed clock'))
        m.setattr(s, 'prepare_timesheet_export_snapshot', lambda *a, **kw: pytest.fail('getter prepared'))
        assert pure(frame, monkeypatch, frame.get_prepared_export) is None
    assert clock.calls == 1
    assert pure(frame, monkeypatch)
    refreshed = frame.get_prepared_export()
    assert cell(refreshed, a, MON)['actual_seconds'] == 7200
    assert next(row for row in refreshed['payload']['tasks'] if row['task_id'] == a)['name'] == 'Renamed'
    assert refreshed['event_id'] != old['event_id']
    clock.value += timedelta(days=7)
    assert pure(frame, monkeypatch)
    assert frame.get_prepared_export()['event_id'] != old['event_id']
    assert frame.get_prepared_export()['payload']['start_date'] != old['payload']['start_date']
    assert frame.report.text != old['payload']['report_text']


@pytest.mark.parametrize('start,end', [('2026-1-12', str(TUE)), ('20261012', str(TUE)),
    ('2026-W42-1', str(TUE)), ('2026-02-30', str(TUE)), ('', str(TUE)), (str(TUE), str(MON)),
    (str(MON), '9999-12-31'), ('0000-01-01', str(TUE))])
def test_invalid_custom_retains_previous_applied_report_and_drafts(setup, build, monkeypatch, start, end):
    s, *_ = setup
    frame = build(s, Clock(local(s, TUE, 12)))
    assert pure(frame, monkeypatch)
    old = frame.report.text, frame._applied_info
    drafts(frame, start, end)
    assert pure(frame, monkeypatch) is False
    assert frame.report.text == old[0] and frame._applied_info == old[1]
    assert frame.get_prepared_export() is None and frame.error_label.visible
    assert frame.start_var.get() == start and frame.end_var.get() == end


@pytest.mark.parametrize('fault', ['clock', 'naive', 'boundary', 'prepare', 'synthetic', 'content', 'configure', 'delete', 'insert'])
def test_failures_preserve_diagnostics_invalidate_and_explicitly_recover(setup, build, monkeypatch, fault):
    s, a, *_ = setup
    frame = build(s, Clock(local(s, TUE, 12)))
    assert pure(frame, monkeypatch)
    old = frame.get_prepared_export()
    error = OSError('injected preview failure')
    error.add_note('original diagnostic note')
    def fail(*a, **kw): raise error
    if fault == 'synthetic': s.add_manual_duration(a, MON, 60, 'Legacy')
    with monkeypatch.context() as m:
        if fault == 'clock': frame._now_utc.error = error
        elif fault == 'naive': frame._now_utc.value = datetime(2026, 10, 13)
        elif fault == 'boundary': frame._now_utc.value = datetime.min.replace(tzinfo=UTC)
        elif fault == 'prepare': m.setattr(s, 'prepare_timesheet_export_snapshot', fail)
        elif fault == 'content':
            invalid = deepcopy(old)
            invalid['payload']['report_text'] = None
            m.setattr(s, 'prepare_timesheet_export_snapshot', lambda *a, **kw: invalid)
        elif fault in ('configure', 'delete', 'insert'):
            frame.report.failure, frame.report.error = fault, error
        assert pure(frame, monkeypatch) is False
    assert frame.get_prepared_export() is None and frame.error_label.visible
    diagnostic = frame.diagnostics[-1]
    assert diagnostic[2] is diagnostic[1].__traceback__
    if fault in ('clock', 'prepare', 'configure', 'delete', 'insert'):
        assert diagnostic[1] is error and 'original diagnostic note' in error.__notes__
    if fault in ('configure', 'delete', 'insert'):
        assert not frame.report_frame.visible and frame._prepared is None
    else:
        assert frame.report_frame.visible and frame.report.text == old['payload']['report_text']
    frame.report.failure = None
    frame._now_utc.error, frame._now_utc.value = None, local(s, TUE, 12)
    if fault == 'synthetic':
        s.delete_interval(a, next(iter(s.state.tasks[a].intervals)), 'Explicit fixture correction')
    assert pure(frame, monkeypatch) is True
    assert frame.report_frame.visible and frame.get_prepared_export() is not None
    assert not frame.error_label.visible and frame.report.options['state'] == 'disabled'


def test_picker_seed_selection_cancel_destroy_and_no_observation(setup, build, monkeypatch):
    s, *_ = setup
    clock = Clock(local(s, TUE, 12))
    frame = build(s, clock)
    drafts(frame, '', 'bad')
    assert frame.picker_buttons['Start'].invoke() is False and clock.calls == 0
    frame.start_var.set(str(MON))
    assert frame.picker_buttons['Start'].invoke()
    popup, calendar = next(iter(frame._pickers.items()))
    assert calendar.selected == MON
    popup.bindings['WM_DELETE_WINDOW']()
    assert frame.start_var.get() == str(MON) and not frame._pickers
    frame.period_buttons['This week'].invoke()
    assert pure(frame, monkeypatch)
    assert frame.picker_buttons['End'].invoke()
    popup, calendar = next(iter(frame._pickers.items()))
    assert calendar.selected == TUE
    calendar.choose(SAT)
    assert frame.end_var.get() == str(SAT) and frame.get_prepared_export() is None and not frame._pickers
    frame.picker_buttons['Start'].invoke()
    frame.picker_buttons['End'].invoke()
    owned = list(frame._pickers)
    assert pure(frame, monkeypatch, frame.destroy) is None
    assert all(p.destroyed for p in owned) and not frame._pickers and clock.calls == 1


def test_empty_all_is_success_without_registration(setup, build, monkeypatch, tmp_path):
    s = TaskTimerService(EventStorage(tmp_path / 'empty-preview'))
    frame = build(s, Clock(local(s, TUE, 12)))
    assert pure(frame, monkeypatch) is True
    assert frame.get_prepared_export()['payload']['tasks'] == []
    assert frame.report.text and not frame.error_label.visible


def test_real_tk_checkboxes_typed_dates_calendar_readonly_readiness_and_failure_recovery(
        setup, tk_root, pointer, monkeypatch):
    s, a, b, *_ = setup
    dated(s, a, MON, 18.125)
    dated(s, b, SAT, 50400.125)
    clock = Clock(local(s, TUE, 12))
    frame = previews.TimesheetPreviewFrame(tk_root, s, now_utc=clock)
    frame.pack(fill='both', expand=True)
    tk_root.geometry('1000x800+0+0')
    tk_root.update()
    diagnostics = []
    tk_root.report_callback_exception = lambda *args: diagnostics.append(args)
    before = capture(s)
    assert clock.calls == 0 and frame.get_prepared_export() is None
    pointer.click(frame.period_buttons['Custom'])
    for key, text in [('Start', str(MON)), ('End', str(SAT))]:
        entry = frame.date_entries[key]
        entry.delete(0, 'end')
        entry.insert(0, text)
    pointer.click(frame.scope_buttons['Selected tasks'])  # Focus loss must not apply typed drafts.
    pointer.click(frame.task_buttons[a])
    assert frame.task_vars[a].get() and not frame.task_vars[b].get() and clock.calls == 0
    pointer.click(frame.picker_buttons['Start'])
    popup, calendar = next(iter(frame._pickers.items()))
    assert calendar.selection_get() == MON
    day = next(label for week in calendar._calendar for label in week if label.cget('text') == '13')
    pointer.click(day)  # Actual Calendar widget mouse selection updates only this draft.
    assert frame.start_var.get() == str(TUE) and not frame._pickers and clock.calls == 0
    pointer.click(frame.picker_buttons['End'])
    popup = next(iter(frame._pickers))
    cancel = next(child for child in popup.winfo_children() if isinstance(child, ttk.Button))
    pointer.click(cancel)
    assert frame.end_var.get() == str(SAT) and not frame._pickers and clock.calls == 0
    frame.date_entries['Start'].delete(0, 'end')
    frame.date_entries['Start'].insert(0, str(MON))
    pointer.click(frame.preview_button)
    event = frame.get_prepared_export()
    assert event and clock.calls == 1 and not diagnostics and capture(s) == before
    assert frame.report.get('1.0', 'end-1c') == event['payload']['report_text']
    assert str(frame.report.cget('state')) == 'disabled'
    assert frame.report.cget('wrap') == 'none'
    assert frame.report.cget('xscrollcommand') and frame.report.cget('yscrollcommand')
    frame.report.yview_moveto(1)
    assert frame.report.yview()[1] == 1.0
    frame.report.yview_moveto(0)
    frame.report.insert('1.0', 'unauthorized edit')
    assert frame.report.get('1.0', 'end-1c') == event['payload']['report_text']
    assert frame.preview_button.cget('text') == 'Refresh'
    pointer.click(frame.task_buttons[b])
    assert frame.get_prepared_export() is None and 'Previous preview:' in frame.info_var.get()
    assert clock.calls == 1 and frame.report.get('1.0', 'end-1c') == event['payload']['report_text']
    pointer.click(frame.preview_button)
    assert {row['task_id'] for row in frame.get_prepared_export()['payload']['tasks']} == {a, b}
    prepared = frame.get_prepared_export()
    error = OSError('injected real-widget update failure')
    original_insert = frame.report.insert
    def broken_insert(*args):
        original_insert('1.0', 'partial')
        raise error
    with monkeypatch.context() as m:
        m.setattr(frame.report, 'insert', broken_insert)
        pointer.click(frame.preview_button)
    assert frame.get_prepared_export() is None and not frame.report_frame.winfo_ismapped()
    assert frame.error_label.winfo_ismapped() and diagnostics[-1][1] is error
    pointer.click(frame.preview_button)
    assert frame.report_frame.winfo_ismapped() and not frame.error_label.winfo_ismapped()
    assert frame.get_prepared_export()['event_id'] != prepared['event_id']
    assert frame.report.get('1.0', 'end-1c') == frame.get_prepared_export()['payload']['report_text']
    pointer.click(frame.picker_buttons['Start'])
    owned = tuple(frame._pickers)
    frame.destroy()
    assert not frame._pickers and all(not popup.winfo_exists() for popup in owned)
    assert capture(s) == before
