"""Standalone widget wiring connected to real disposable Chronicle journals."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from task_timer import timed_interval_editor as editors, timed_interval_form as forms
from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage
from test_mixed_accounting import setup, local, dated, files, MON, TUE, CUTOFF
from test_polr_confirmation_replay import cell, journal
from test_timed_interval_corrections import capture, seed, fail, forbidden
from test_timed_interval_form import Variable, Widget, real_root


class Control(Widget):
    def invoke(self):
        if self.options.get('state') != 'disabled':
            return self.options['command']()


class Window:
    created = []

    def __init__(self, parent):
        self.widgets, self.bindings, self.protocols = [], {}, {}
        self.destroyed = self.grabbed = False
        self.created.append(self)

    def title(self, text): self.caption = text
    def transient(self, parent): self.parent = parent
    def grid_columnconfigure(self, *args, **kwargs): pass
    def bind(self, name, callback): self.bindings[name] = callback
    def protocol(self, name, callback): self.protocols[name] = callback
    def grab_set(self): self.grabbed = True
    def destroy(self): self.destroyed, self.grabbed = True, False


@pytest.fixture
def ui(monkeypatch):
    # Local widget doubles only. Form construction, validators and all service paths stay real.
    Window.created = []
    monkeypatch.setattr(editors, 'Toplevel', Window)
    monkeypatch.setattr(editors, 'StringVar', Variable)
    monkeypatch.setattr(forms, 'StringVar', Variable)
    def initialise(frame, parent): frame.widgets = []
    monkeypatch.setattr(forms.ttk.Frame, '__init__', initialise)
    monkeypatch.setattr(forms.ttk.Frame, 'grid', lambda *a, **k: None)
    monkeypatch.setattr(forms.ttk.Frame, 'grid_columnconfigure', lambda *a, **k: None)
    for name in ('Entry', 'Label', 'Combobox', 'Button'):
        monkeypatch.setattr(forms.ttk, name, Control)
    class Parent:
        def wait_window(self, window): self.window = window
    return Parent()


def open_editor(ui, s, a, old):
    return editors.TimedIntervalCorrectionDialog(ui, s, a, old)


def draft(dialog):
    return tuple(getattr(dialog.form, f'{endpoint}_{field}_var').get()
                 for endpoint in ('start', 'end') for field in ('date', 'time', 'occurrence')) + (dialog.comment_var.get(),)


def assert_locked(dialog):
    for endpoint in ('start', 'end'):
        for field in ('date_entry', 'time_entry', 'occurrence_selector'):
            assert getattr(dialog.form, f'{endpoint}_{field}').options['state'] == 'disabled'
    assert dialog.comment_entry.options['state'] == 'disabled'
    assert dialog.close_button.options['text'] == 'Close'


def evidence(s, a, tmp_path):
    export = s.prepare_timesheet_export_snapshot(MON, TUE, cutoff_utc=CUTOFF, all_tasks=True)
    s.register_prepared_timesheet_export(export)
    path = tmp_path / 'frozen.txt'
    s.materialize_timesheet_export(export['event_id'], path)
    confirm = s.prepare_polr_confirmation_batch([cell(a)])
    s.register_prepared_polr_confirmation_batch(confirm)
    return export, confirm, path


def test_actual_constructor_precise_same_minute_comment_only_noop_is_pure(setup, ui, monkeypatch):
    s, a, _, _, _, _ = setup
    first = local(s, MON, 9).astimezone(timezone.utc) + timedelta(seconds=12, microseconds=345678)
    identity = str(uuid4())
    s._append(a, 'manual_interval_added', {'interval_id': identity, 'start_utc': first.isoformat(),
              'stop_utc': first.replace(second=15, microsecond=456789).isoformat(), 'reason': 'original'})
    before = capture(s)
    dialog = open_editor(ui, s, a, identity)
    assert draft(dialog) == (str(MON), '09:00', '', str(MON), '09:00', '', '')
    dialog.form.start_time_var.set('9am')
    dialog.comment_var.set('This alone is not a time correction')
    monkeypatch.setattr(s.storage, 'append_event', forbidden)
    monkeypatch.setattr(s, '_create_risky_operation_backup', forbidden)
    dialog.save_button.invoke()
    assert dialog.result == {'status': 'unchanged', 'prepared_event': None, 'registration_result': None}
    assert dialog.window.destroyed and not dialog.window.grabbed and capture(s) == before


@pytest.mark.parametrize('fault', ['project', 'missing-task', 'deleted-task', 'missing', 'deleted', 'superseded', 'dated', 'synthetic', 'open', 'span', 'representability'])
def test_initial_rejection_never_creates_modal_or_grab(setup, ui, fault):
    s, a, _, p, _, _ = setup
    old = seed(s, a)
    owner = a
    if fault == 'project': owner = p
    elif fault == 'missing-task': owner = str(uuid4())
    elif fault == 'deleted-task': s.delete_task(a)
    elif fault == 'missing': old = str(uuid4())
    elif fault == 'deleted': s.delete_interval(a, old, 'removed')
    elif fault == 'superseded': s.edit_interval(a, old, local(s, MON, 9), local(s, MON, 10, 30), 'changed')
    elif fault == 'dated': old = dated(s, a, MON, 3600)
    elif fault == 'synthetic':
        s.add_manual_duration(a, MON, 3600, 'legacy')
        old = next(reversed(s.state.tasks[a].intervals))
    elif fault == 'open': old = '__open__'
    elif fault in ('span', 'representability'):
        old = str(uuid4())
        first = datetime.min.replace(tzinfo=timezone.utc) if fault == 'representability' else local(s, MON, 9)
        last = first + timedelta(hours=1) if fault == 'representability' else first
        s._append(a, 'manual_interval_added', {'interval_id': old, 'start_utc': first.isoformat(),
                  'stop_utc': last.isoformat(), 'reason': 'unsupported original'})
    before = capture(s)
    with pytest.raises(ValueError): open_editor(ui, s, owner, old)
    assert Window.created == [] and capture(s) == before


def test_initial_loading_uses_supplied_timezone_and_no_implicit_clock(setup, ui, monkeypatch):
    from task_timer import app, time_utils
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    before = capture(s)
    s.local_tz_name = 'Unknown/Timezone audit label'
    monkeypatch.setattr(app, 'utc_now', forbidden)
    monkeypatch.setattr(app, 'detect_local_timezone', forbidden)
    monkeypatch.setattr(time_utils, 'detect_local_timezone', forbidden)
    dialog = open_editor(ui, s, a, old)
    assert dialog.form.local_timezone is s.local_tz
    dialog.close_button.invoke()
    assert capture(s) == before


def test_widget_construction_failure_cleans_partial_window(setup, ui, monkeypatch):
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    monkeypatch.setattr(editors, 'TimedIntervalInputFrame', fail)
    before = capture(s)
    with pytest.raises(OSError): open_editor(ui, s, a, old)
    assert len(Window.created) == 1 and Window.created[0].destroyed and not Window.created[0].grabbed
    assert capture(s) == before


@pytest.mark.parametrize('action', ['button', 'escape', 'window'])
def test_cancel_paths_are_pure(setup, ui, action):
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    before = capture(s)
    dialog = open_editor(ui, s, a, old)
    dialog.form.start_time_var.set('bad')
    if action == 'button': dialog.close_button.invoke()
    elif action == 'escape': dialog.window.bindings['<Escape>'](None)
    else: dialog.window.protocols['WM_DELETE_WINDOW']()
    assert dialog.result == {'status': 'cancelled', 'prepared_event': None, 'registration_result': None}
    assert capture(s) == before


def test_connected_save_preserves_precision_other_work_timers_markers_and_frozen_evidence(setup, ui, tmp_path):
    s, a, b, _, _, _ = setup
    old = seed(s, a, fractional=True)
    dated(s, b, TUE, 123.456)
    export, confirm, path = evidence(s, a, tmp_path)
    s.create_time_submission_marker([a], None, CUTOFF, 'legacy marker', None)
    legacy = tmp_path / 'legacy.txt'
    s.export_report(legacy, reset_after=False)
    s.start_task(a)
    before, copies = deepcopy(s.state), (path.read_bytes(), legacy.read_bytes())
    markers = s.list_time_submissions(), s.find_active_export_checkpoint()['event_id']
    dialog = open_editor(ui, s, a, old)
    dialog.form.end_time_var.set('11')
    dialog.comment_var.set('  Adjusted end  ')
    dialog.save_button.invoke()
    result = dialog.result
    assert result['status'] == 'registered'
    event = result['prepared_event']
    new = s.state.tasks[a].intervals[result['registration_result']['replacement_interval_id']]
    assert new.start_utc == before.tasks[a].intervals[old].start_utc and new.stop_utc == local(s, MON, 11).astimezone(timezone.utc)
    assert new.edit_reason == 'Adjusted end' and before.tasks[a].intervals[old].deleted is False
    expected = deepcopy(before)
    expected.tasks[a].intervals[old].deleted = True
    expected.tasks[a].intervals[new.interval_id] = deepcopy(new)
    assert s.state == expected and s.state.tasks[a].is_running
    assert (s.list_time_submissions(), s.find_active_export_checkpoint()['event_id']) == markers
    assert (path.read_bytes(), legacy.read_bytes()) == copies
    assert s.get_timesheet_export_snapshot(export['event_id']) == export
    assert s.get_effective_polr_confirmations()[a, MON.isoformat()]['batch_event_id'] == confirm['event_id']
    assert sum(e['event_id'] == event['event_id'] for e in journal(s)) == 1
    result['prepared_event']['payload']['reason'] = 'caller mutation'
    result['registration_result']['warnings'] = ('caller mutation',)
    assert dialog._prepared_event['payload']['reason'] == 'Adjusted end' and new.edit_reason == 'Adjusted end'


def test_invalid_drafts_retain_values_and_fresh_comparison_precedes_every_preparation(setup, ui, monkeypatch):
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    dialog = open_editor(ui, s, a, old)
    dialog.form.end_time_var.set('10:00:01')
    dialog.comment_var.set('keep this')
    before, fields = capture(s), draft(dialog)
    dialog.save_button.invoke()
    assert capture(s) == before and draft(dialog) == fields and dialog.form.error_var.get()
    dialog.form.end_time_var.set('11')
    prepare, calls = s.prepare_timed_interval_correction, []
    def rejected_preparation(*args, **kwargs):
        calls.append(args)
        raise ValueError('temporary preparation rejection')
    monkeypatch.setattr(s, 'prepare_timed_interval_correction', rejected_preparation)
    dialog.save_button.invoke()
    assert calls == [(a, old)] and capture(s) == before
    s.edit_interval(a, old, local(s, MON, 9), local(s, MON, 10, 30), 'other editor')
    fields, before = draft(dialog), capture(s)
    monkeypatch.setattr(s, 'prepare_timed_interval_correction', prepare)
    dialog.save_button.invoke()
    assert 'Reviewed work changed' in dialog.message_var.get()
    assert capture(s) == before and draft(dialog) == fields and dialog._prepared_event is None


@pytest.mark.parametrize('change', ['replace-chain', 'delete', 'delete-task', 'branch'])
def test_stale_conflict_uses_fresh_evidence_without_retargeting_or_draft_mutation(setup, ui, monkeypatch, change):
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    dialog = open_editor(ui, s, a, old)
    dialog.form.end_time_var.set('11')
    dialog.comment_var.set('Retained comment')
    expected = None
    if change in ('replace-chain', 'branch'):
        s.edit_interval(a, old, local(s, MON, 9), local(s, MON, 10, 30), 'first')
        latest = next(reversed(s.state.tasks[a].intervals))
        s.edit_interval(a, latest if change == 'replace-chain' else old, local(s, MON, 9), local(s, MON, 10, 45), 'second')
        expected = next(reversed(s.state.tasks[a].intervals)) if change == 'replace-chain' else 'branching'
    elif change == 'delete':
        s.delete_interval(a, old, 'removed')
        expected = 'deleted'
    else:
        s.delete_task(a)
        expected = 'task is now deleted'
    fields, before = draft(dialog), capture(s)
    monkeypatch.setattr(s, 'prepare_timed_interval_correction', forbidden)
    dialog.save_button.invoke()
    assert expected in dialog.message_var.get()
    assert capture(s) == before and draft(dialog) == fields and dialog.interval_id == old


@pytest.mark.parametrize('fault', ['missing', 'cycle', 'cross-task', 'unsupported'])
def test_conflict_graph_uncertainty_is_read_only_and_never_selects_another_target(setup, ui, fault):
    s, a, b, _, _, _ = setup
    old = seed(s, a)
    dialog = open_editor(ui, s, a, old)
    task = s.read_task_for_timed_interval_correction(a)
    if fault == 'missing': task.intervals.clear()
    else:
        replacement = deepcopy(task.intervals[old])
        replacement.interval_id = str(uuid4())
        replacement.replaced_interval_id = old
        task.intervals[old].deleted = True
        task.intervals[replacement.interval_id] = replacement
        if fault == 'cycle':
            replacement.deleted = True
            task.intervals[old].replaced_interval_id = replacement.interval_id
        elif fault == 'cross-task': replacement.task_id = b
        else: replacement.entry_mode = 'duration'
    before, fields = deepcopy(task), draft(dialog)
    text = dialog._conflict_information(task)
    assert ('unavailable' if fault == 'missing' else 'cycle' if fault == 'cycle' else 'unsupported') in text
    assert task == before and draft(dialog) == fields and dialog.interval_id == old


def test_unrelated_task_changes_do_not_invalidate_record_review(setup, ui):
    s, a, b, _, q, _ = setup
    old = seed(s, a)
    dialog = open_editor(ui, s, a, old)
    s.update_task(a, 'Renamed while open', 'notes changed')
    s.assign_task_to_project(a, q)
    dated(s, b, TUE, 7200)
    dialog.form.end_time_var.set('11')
    dialog.save_button.invoke()
    assert dialog.result['status'] == 'registered'
    assert s.state.tasks[a].name == 'Renamed while open' and s.state.tasks[a].project_id == q
    assert s.state.tasks[b].dated_durations


@pytest.mark.parametrize('fault', ['install', 'snapshot'])
def test_registered_warning_failed_retry_keeps_verified_result_and_close_does_not_claim_uncertainty(setup, ui, monkeypatch, fault):
    s, a, _, _, _, _ = setup
    dialog = open_editor(ui, s, a, seed(s, a))
    dialog.form.end_time_var.set('11')
    with monkeypatch.context() as m:
        m.setattr(s, '_install_timed_correction_journal' if fault == 'install' else '_save_snapshot', fail)
        dialog.save_button.invoke()
    assert_locked(dialog)
    assert 'Correction recorded' in dialog.message_var.get() and 'Refresh incomplete' in dialog.message_var.get()
    returned, event = deepcopy(dialog._registration_result), deepcopy(dialog._prepared_event)
    with monkeypatch.context() as m:
        m.setattr(s.storage, 'synchronize_journal', fail)
        dialog.save_button.invoke()
    assert 'was recorded' in dialog.message_var.get() and 'retry failed' in dialog.message_var.get()
    assert dialog._registration_result == returned and dialog._prepared_event == event
    monkeypatch.setattr(editors.messagebox, 'askyesno', forbidden)
    dialog.close_button.invoke()
    assert dialog.result == {'status': 'registered', 'prepared_event': event, 'registration_result': returned}
    assert sum(e['event_id'] == event['event_id'] for e in journal(s)) == 1


def test_complete_append_error_recovery_warning_is_not_an_incomplete_refresh(setup, ui, monkeypatch):
    s, a, _, _, _, _ = setup
    dialog = open_editor(ui, s, a, seed(s, a))
    dialog.form.end_time_var.set('11')
    append = s.storage.append_event
    def complete_then_error(event):
        append(event)
        raise OSError('complete append uncertainty')
    monkeypatch.setattr(s.storage, 'append_event', complete_then_error)
    dialog.save_button.invoke()
    assert_locked(dialog)
    assert 'complete append uncertainty' in dialog.message_var.get()
    assert 'incomplete' not in dialog.message_var.get().lower()
    assert dialog.save_button.options['state'] == 'disabled'
    monkeypatch.setattr(s, 'register_prepared_timed_interval_correction', forbidden)
    dialog.window.bindings['<Return>'](None)
    dialog.close_button.invoke()
    assert dialog.result['status'] == 'registered'
    assert dialog.result['registration_result']['snapshot_saved']


@pytest.mark.parametrize('action', ['button', 'escape', 'window'])
def test_unverified_close_requires_confirmation_and_retains_exact_event(setup, ui, monkeypatch, action):
    s, a, _, _, _, _ = setup
    dialog = open_editor(ui, s, a, seed(s, a))
    dialog.form.end_time_var.set('11')
    monkeypatch.setattr(s.storage, 'append_event', fail)
    dialog.save_button.invoke()
    assert_locked(dialog)
    assert 'may already be recorded' in dialog.message_var.get()
    event, before = deepcopy(dialog._prepared_event), capture(s)
    answers, prompts = iter((False, True)), []
    def confirm(*args, **kwargs):
        prompts.append(args)
        # Nested window/Save callbacks cannot bypass confirmation or prepare again.
        dialog._close()
        dialog._save()
        return next(answers)
    monkeypatch.setattr(editors.messagebox, 'askyesno', confirm)
    close = dialog.close_button.invoke if action == 'button' else lambda: dialog.window.bindings['<Escape>'](None) if action == 'escape' else dialog.window.protocols['WM_DELETE_WINDOW']()
    close()
    assert not dialog.window.destroyed
    close()
    assert len(prompts) == 2 and 'may already be recorded' in prompts[0][1]
    assert dialog.result == {'status': 'unverified', 'prepared_event': event, 'registration_result': None}
    assert capture(s) == before


def test_exact_retry_after_newer_work_and_confirmations_never_reprepares_or_rolls_back(setup, ui, tmp_path, monkeypatch):
    s, a, b, _, _, _ = setup
    old = seed(s, a)
    export, confirm, path = evidence(s, a, tmp_path)
    s.start_task(b)
    dialog = open_editor(ui, s, a, old)
    dialog.form.end_time_var.set('11')
    append = s.storage.append_event
    with monkeypatch.context() as m:
        def complete_then_error(event):
            append(event)
            raise OSError('complete append error')
        m.setattr(s.storage, 'append_event', complete_then_error)
        m.setattr(s.storage, 'synchronize_journal', fail)
        dialog.save_button.invoke()
    first = deepcopy(dialog._prepared_event)
    assert dialog._registration_result is None
    other = TaskTimerService(EventStorage(s.storage.data_dir))
    newer = other.prepare_timed_interval_correction(a, first['payload']['new_interval_id'], stop_utc=local(s, MON, 12))
    other.register_prepared_timed_interval_correction(newer)
    batch = other.prepare_polr_confirmation_batch([cell(a, 500, prior=confirm['event_id'])])
    other.register_prepared_polr_confirmation_batch(batch)
    expected = deepcopy(other.state), other.get_effective_polr_confirmations(), files(s), path.read_bytes(), journal(s)
    monkeypatch.setattr(s, 'read_task_for_timed_interval_correction', forbidden)
    monkeypatch.setattr(s, 'prepare_timed_interval_correction', forbidden)
    monkeypatch.setattr(s.storage, 'append_event', forbidden)
    dialog.save_button.invoke()
    assert dialog.result['status'] == 'registered' and dialog.result['prepared_event'] == first
    assert (s.state, s.get_effective_polr_confirmations(), files(s), path.read_bytes(), journal(s)) == expected
    assert s.get_timesheet_export_snapshot(export['event_id']) == export and s.state.tasks[b].is_running
    assert sum(e['event_id'] == first['event_id'] for e in journal(s)) == 1


def test_save_reentry_retains_one_preparation_and_one_registration(setup, ui, monkeypatch):
    s, a, _, _, _, _ = setup
    dialog = open_editor(ui, s, a, seed(s, a))
    dialog.form.end_time_var.set('11')
    prepare, register, calls = s.prepare_timed_interval_correction, s.register_prepared_timed_interval_correction, []
    def prepare_once(*args, **kwargs):
        calls.append('prepare')
        dialog._save(); dialog._close()
        return prepare(*args, **kwargs)
    def register_once(event):
        calls.append('register')
        dialog._save(); dialog._retry(); dialog._close()
        return register(event)
    monkeypatch.setattr(s, 'prepare_timed_interval_correction', prepare_once)
    monkeypatch.setattr(s, 'register_prepared_timed_interval_correction', register_once)
    dialog.save_button.invoke()
    dialog._save(); dialog._retry(); dialog._close()
    assert calls == ['prepare', 'register'] and dialog.result['status'] == 'registered'


def test_stored_repeat_is_proved_but_changed_repeat_requires_selection(setup, ui):
    s, a, _, _, _, _ = setup
    day = date(2026, 11, 1)
    first, last = datetime(2026, 11, 1, 6, 30, 12, tzinfo=timezone.utc), datetime(2026, 11, 1, 7, 30, 15, tzinfo=timezone.utc)
    old = str(uuid4())
    s._append(a, 'manual_interval_added', {'interval_id': old, 'start_utc': first.isoformat(), 'stop_utc': last.isoformat(), 'reason': 'repeat'})
    dialog = open_editor(ui, s, a, old)
    assert 'First 01:30' in dialog.form.start_occurrence_var.get()
    assert 'Second 01:30' in dialog.form.end_occurrence_var.get()
    dialog.form.end_time_var.set('1:45')
    before = capture(s)
    dialog.save_button.invoke()
    assert capture(s) == before and 'Select first or second' in dialog.message_var.get()
    dialog.form.set_occurrence('end', 'second')
    dialog.save_button.invoke()
    new = s.state.tasks[a].intervals[dialog.result['registration_result']['replacement_interval_id']]
    assert new.start_utc == first and new.stop_utc == datetime(2026, 11, 1, 7, 45, tzinfo=timezone.utc)


@pytest.mark.parametrize('mode', ['refresh-retry', 'unverified-close'])
def test_real_tk_correction_construction_occurrence_save_retry_and_close(setup, real_root, monkeypatch, mode):
    from tkinter import ttk
    s, a, _, _, _, _ = setup
    old = str(uuid4())
    s._append(a, 'manual_interval_added', {'interval_id': old, 'start_utc': '2026-11-01T06:30:12.345678Z',
              'stop_utc': '2026-11-01T07:30:15.456789Z', 'reason': 'repeat'})
    errors = []
    def drive():
        window = real_root.winfo_children()[0]
        try:
            frame = next(w for w in window.winfo_children() if isinstance(w, forms.TimedIntervalInputFrame))
            buttons = [w for w in window.winfo_children() if isinstance(w, ttk.Button)]
            save = next(w for w in buttons if w.cget('text') == 'Save')
            close = next(w for w in buttons if w.cget('text') == 'Cancel')
            assert 'First' in frame.start_occurrence_var.get() and 'Second' in frame.end_occurrence_var.get()
            frame.end_time_var.set('1:45')
            frame.set_occurrence('end', 'second')
            with monkeypatch.context() as m:
                if mode == 'refresh-retry': m.setattr(s, '_save_snapshot', fail)
                else: m.setattr(s.storage, 'append_event', fail)
                save.invoke()
            assert str(frame.end_time_entry.cget('state')) == 'disabled' and close.cget('text') == 'Close'
            if mode == 'refresh-retry': save.invoke()
            else:
                monkeypatch.setattr(editors.messagebox, 'askyesno', lambda *a, **k: True)
                window.tk.call(window.protocol('WM_DELETE_WINDOW'))
        except BaseException as exc:
            errors.append(exc)
            window.destroy()
    real_root.after(0, drive)
    dialog = editors.TimedIntervalCorrectionDialog(real_root, s, a, old)
    assert not errors
    assert dialog.result['status'] == ('registered' if mode == 'refresh-retry' else 'unverified')
