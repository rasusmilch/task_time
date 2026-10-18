"""Connected frozen save/retry over disposable services; separate real Tk input."""

from hashlib import sha256
from pathlib import Path

import pytest

from task_timer import timesheet_save as saves
from task_timer import timesheet_preview as previews
from task_timer.settings import UISettingsStore
from test_mixed_accounting import setup, dated, local, MON, TUE, SAT
from test_work_history import capture, interval
from test_work_history_browser import Clock
from test_timesheet_preview import build as preview_widgets, Variable, drafts, cell
from test_history_window import tk_root, pointer


@pytest.fixture
def build(preview_widgets, monkeypatch):
    monkeypatch.setattr(saves, 'StringVar', Variable)
    def create(service, clock=None):
        frame = saves.TimesheetSaveFrame(object(), service, now_utc=clock or Clock(local(service, TUE, 12)))
        frame.diagnostics = []
        frame._root().report_callback_exception = lambda *args: frame.diagnostics.append(args)
        return frame
    return create


def ready(frame):
    drafts(frame.preview, str(MON), str(SAT))
    assert frame.preview.refresh_preview()
    return frame.preview.get_prepared_export()


def dialog(monkeypatch, result):
    calls = []
    def choose(**kw):
        calls.append(kw)
        return result() if callable(result) else result
    monkeypatch.setattr(saves.filedialog, 'asksaveasfilename', choose)
    return calls


def exports(s):
    return [e for e in s.storage.iter_all_events(strict=True) if e['event_type'] == 'timesheet_export_snapshot_created']


def no_recalculation(monkeypatch, s):
    def forbidden(*a, **kw): pytest.fail('Save performed prohibited calculation or unrelated write')
    for name in ('prepare_timesheet_export_snapshot', 'calculate_date_window', '_append',
                 '_save_snapshot', 'evaluate_timesheet_export_file_status', 'create_backup_now'):
        monkeypatch.setattr(s, name, forbidden)
    monkeypatch.setattr(s.backups, 'create_backup', forbidden)
    monkeypatch.setattr(s.backups, 'create_safety_backup', forbidden)
    monkeypatch.setattr(UISettingsStore, 'save', forbidden)


def assert_only_export(s, before, candidate):
    after = capture(s)
    assert after[0] == before[0]  # Includes timers, checkpoints and all prior work.
    assert after[2] == before[2] and after[4] == before[4] and after[6] == before[6]
    def nonjournal(captured):
        return {p: value for p, value in captured.items()
                if Path(p).parts[0] != 'archives' and p not in ('active_events.jsonl', 'log_manifest.json')}
    assert nonjournal(after[3]) == nonjournal(before[3])  # Snapshots/settings/backups unchanged.
    assert after[5] == before[5] + [candidate]
    def persisted(event):
        return {key: value for key, value in event.items() if key != '_read_sequence'}
    old = {e['event_id']: persisted(e) for e in before[1]}
    assert all(persisted(e) == old[e['event_id']] for e in after[1] if e['event_id'] in old)
    assert after[3]['active_events.jsonl'].startswith(before[3]['active_events.jsonl'])
    assert len(exports(s)) == 1 and exports(s)[0]['event_id'] == candidate['event_id']


def test_readiness_dirty_failed_preview_and_controls(setup, build, monkeypatch):
    s, *_ = setup
    frame = build(s)
    calls = dialog(monkeypatch, pytest.fail)
    before = capture(s)
    assert frame.saved_path is None and frame.get_save_attempt() is None
    assert frame.save_button.options['state'] == 'disabled'
    assert not frame.save() and calls == []
    ready(frame)
    assert frame.save_button.options['state'] == 'normal'
    frame.preview.start_var.set('bad')
    assert not frame.save() and calls == []
    assert not frame.preview.refresh_preview() and not frame.save()
    assert frame.save_button.options['state'] == 'disabled' and capture(s) == before


@pytest.mark.parametrize('path', ['', None, 'bad\x00path', 42])
def test_cancel_invalid_destination_preserve_candidate_without_durable_effects(setup, build, monkeypatch, path):
    s, *_ = setup
    frame = build(s)
    event = ready(frame)
    before = capture(s)
    calls = dialog(monkeypatch, path)
    assert not frame.save()
    assert len(calls) == 1 and calls[0]['defaultextension'] == '.txt'
    assert calls[0]['confirmoverwrite'] is False and 'parent' in calls[0]
    assert not frame.preview._locked and frame.preview.get_prepared_export() == event
    assert frame.get_save_attempt() is None and capture(s) == before


@pytest.mark.parametrize('change', ['dirty', 'candidate'])
def test_dialog_rechecks_reviewed_event_and_readiness(setup, build, monkeypatch, tmp_path, change):
    s, *_ = setup
    frame = build(s)
    ready(frame)
    before = capture(s)
    def choose():
        assert frame.preview._locked
        if change == 'dirty': frame.preview.end_var.set(str(TUE))
        else: frame.preview._prepared['payload']['report_text'] += 'changed'
        return str(tmp_path / 'not-published.txt')
    dialog(monkeypatch, choose)
    assert not frame.save() and frame.get_save_attempt() is None
    assert not frame.preview._locked and capture(s) == before
    assert 'Review' in frame.status_var.get()


def test_exact_save_registers_before_publish_and_preserves_unrelated_state(setup, build, monkeypatch, tmp_path):
    s, a, *_ = setup
    dated(s, a, MON, 10800.125)
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    s.start_task(a)
    frame = build(s)
    event = ready(frame)
    assert cell(event, a, MON)['actual_seconds'] == 25200.125
    before = capture(s)
    target = tmp_path / 'frozen.txt'
    dialog(monkeypatch, str(target))
    no_recalculation(monkeypatch, s)
    register, materialize = s.register_prepared_timesheet_export, s.materialize_timesheet_export
    order = []
    def registration(candidate):
        assert not target.exists() and candidate == event
        order.append('register')
        return register(candidate)
    def publication(identity, destination):
        assert exports(s)[0]['event_id'] == identity == event['event_id']
        order.append('materialize')
        return materialize(identity, destination)
    monkeypatch.setattr(s, 'register_prepared_timesheet_export', registration)
    monkeypatch.setattr(s, 'materialize_timesheet_export', publication)
    assert frame.save() and order == ['register', 'materialize']
    assert frame.saved_path == target and frame.preview._locked
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert sha256(target.read_bytes()).hexdigest() == event['payload']['report_sha256']
    attempt = frame.get_save_attempt()
    assert set(attempt) == {'prepared_event', 'destination'}
    assert attempt == {'prepared_event': event, 'destination': str(target)}
    assert event['payload']['preferred_destination'] is None
    attempt['prepared_event']['payload']['report_text'] = 'external mutation'
    assert frame.get_save_attempt()['prepared_event'] == event
    assert not frame.save() and not frame.choose_another_file() and order == ['register', 'materialize']
    assert frame.save_button.options['state'] == frame.choose_button.options['state'] == 'disabled'
    assert_only_export(s, before, event)


@pytest.mark.parametrize('ambiguous', [False, True])
def test_absent_and_ambiguous_registration_failures_retry_exact_identity(setup, build, monkeypatch, tmp_path, ambiguous):
    s, a, *_ = setup
    dated(s, a, MON, 3600)
    s.start_task(a)
    frame = build(s)
    event = ready(frame)
    before = capture(s)
    target = tmp_path / 'retry.txt'
    dialog(monkeypatch, str(target))
    append = s.storage.append_event
    error = OSError('append outcome uncertain')
    error.add_note('original diagnostic context')
    def fail(candidate):
        if ambiguous: append(candidate)
        raise error
    with monkeypatch.context() as m:
        m.setattr(s.storage, 'append_event', fail)
        if ambiguous:
            m.setattr(s.storage, 'synchronize_journal', lambda: (_ for _ in ()).throw(OSError('sync unavailable')))
        assert not frame.save()
    assert not target.exists() and frame.saved_path is None and frame.preview._locked
    assert 'Registration not verified' in frame.status_var.get()
    reported = frame.diagnostics[-1][1]
    assert reported.__cause__ is error if ambiguous else reported is error
    assert frame.diagnostics[-1][2] is reported.__traceback__
    assert 'original diagnostic context' in error.__notes__
    assert len(exports(s)) == int(ambiguous)
    # Retry ignores even a programmatic dirty draft and a broken readiness getter.
    frame.preview.start_var.set('invalid draft')
    monkeypatch.setattr(frame.preview, 'get_prepared_export', lambda: pytest.fail('retry consulted preview'))
    no_recalculation(monkeypatch, s)
    assert frame.save() and target.exists()
    assert frame.get_save_attempt()['prepared_event'] == event
    assert_only_export(s, before, event)


def test_visible_committed_bytes_do_not_bypass_persistent_sync_failure(setup, build, monkeypatch, tmp_path):
    s, *_ = setup
    frame = build(s)
    event = ready(frame)
    s.register_prepared_timesheet_export(event)
    target = tmp_path / 'not-yet-published.txt'
    dialog(monkeypatch, str(target))
    monkeypatch.setattr(s.storage, 'synchronize_journal', lambda: (_ for _ in ()).throw(OSError('persistent flush failure')))
    assert not frame.save() and not frame.save()
    assert not target.exists() and len(exports(s)) == 1
    assert frame.get_save_attempt()['prepared_event'] == event


def test_wrong_registrar_identity_cannot_publish(setup, build, monkeypatch, tmp_path):
    s, *_ = setup
    frame = build(s)
    ready(frame)
    target = tmp_path / 'never.txt'
    dialog(monkeypatch, str(target))
    monkeypatch.setattr(s, 'register_prepared_timesheet_export', lambda e: 'wrong')
    monkeypatch.setattr(s, 'materialize_timesheet_export', lambda *a: pytest.fail('unverified publication'))
    assert not frame.save() and frame.get_save_attempt() and not target.exists()
    assert 'expected export identity' in frame.status_var.get()


def test_conflict_then_cancel_then_another_destination_reuses_event(setup, build, monkeypatch, tmp_path):
    s, *_ = setup
    frame = build(s)
    event = ready(frame)
    conflict = tmp_path / 'conflict.txt'
    conflict.write_bytes(b'Keep this file')
    dialog(monkeypatch, str(conflict))
    assert not frame.save() and conflict.read_bytes() == b'Keep this file'
    attempt = frame.get_save_attempt()
    assert frame.choose_button.options['state'] == 'normal'
    assert frame.save_button.options['text'] == 'Retry'
    dialog(monkeypatch, '')
    assert not frame.choose_another_file() and frame.get_save_attempt() == attempt
    target = tmp_path / 'another.txt'
    dialog(monkeypatch, str(target))
    no_recalculation(monkeypatch, s)
    assert frame.choose_another_file() and frame.saved_path == target
    assert frame.get_save_attempt() == {'prepared_event': event, 'destination': str(target)}
    assert len(exports(s)) == 1 and conflict.read_bytes() == b'Keep this file'


@pytest.mark.parametrize('existing', [False, True])
def test_existing_matching_copy_and_failure_after_publication_recover(setup, build, monkeypatch, tmp_path, existing):
    s, *_ = setup
    frame = build(s)
    event = ready(frame)
    target = tmp_path / 'copy.txt'
    if existing: target.write_bytes(event['payload']['report_text'].encode('utf-8'))
    dialog(monkeypatch, str(target))
    materialize = s.materialize_timesheet_export
    failure = OSError('verification return interrupted')
    failure.add_note('file may have been published')
    def after(identity, destination):
        materialize(identity, destination)
        raise failure
    with monkeypatch.context() as m:
        m.setattr(s, 'materialize_timesheet_export', after)
        assert not frame.save()
    stat = target.stat()
    assert frame.saved_path is None and frame.diagnostics[-1][1] is failure
    assert 'Save call did not complete' in frame.status_var.get()
    assert frame.save() and target.stat().st_ino == stat.st_ino and target.stat().st_mtime_ns == stat.st_mtime_ns
    assert len(exports(s)) == 1 and frame.saved_path == target


def test_retry_preserves_later_work_and_confirmations_without_recalculation(setup, build, monkeypatch, tmp_path):
    from test_polr_confirmation_writer import register
    from test_polr_confirmation_replay import cell as confirmation_cell
    s, a, *_ = setup
    dated(s, a, MON, 10800)
    frame = build(s)
    event = ready(frame)
    target = tmp_path / 'frozen-before-new-work.txt'
    dialog(monkeypatch, str(target))
    with monkeypatch.context() as m:
        m.setattr(s, 'materialize_timesheet_export', lambda *a: (_ for _ in ()).throw(OSError('later retry')))
        assert not frame.save()
    dated(s, a, MON, 7200)
    confirmation = register(s, confirmation_cell(a, 500))
    before = capture(s)
    no_recalculation(monkeypatch, s)
    assert frame.save()
    assert s.state == before[0] and s.get_effective_polr_confirmations() == before[4]
    assert s.get_effective_polr_confirmations()[a, str(MON)]['batch_event_id'] == confirmation['event_id']
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert cell(event, a, MON)['actual_seconds'] == 10800 and len(exports(s)) == 1


def test_reentry_and_direct_locked_callbacks_cannot_start_another_operation(setup, build, monkeypatch, tmp_path):
    s, *_ = setup
    clock = Clock(local(s, TUE, 12))
    frame = build(s, clock)
    event = ready(frame)
    preview = frame.preview
    assert preview._open_picker(preview.start_var)
    owned = tuple(preview._pickers)
    def choose():
        assert not preview._pickers and all(not p.visible for p in owned)
        assert not frame.save() and not frame.choose_another_file()
        assert not preview.refresh_preview() and not preview._open_picker(preview.start_var)
        assert preview.get_prepared_export() == event
        assert all(c.options['state'] == 'disabled' for c in preview.task_buttons.values())
        return str(tmp_path / 'one.txt')
    dialog(monkeypatch, choose)
    register = s.register_prepared_timesheet_export
    def reenter(e):
        assert not frame.save() and not frame.choose_another_file()
        return register(e)
    monkeypatch.setattr(s, 'register_prepared_timesheet_export', reenter)
    assert frame.save() and clock.calls == 1 and len(exports(s)) == 1


def test_success_presentation_failure_cannot_erase_verified_completion(setup, build, monkeypatch, tmp_path):
    s, *_ = setup
    frame = build(s)
    ready(frame)
    target = tmp_path / 'saved.txt'
    dialog(monkeypatch, str(target))
    error = RuntimeError('status display failed')
    monkeypatch.setattr(frame.status_var, 'set', lambda value: (_ for _ in ()).throw(error))
    assert frame.save() and frame.saved_path == target and frame._completed
    assert frame.diagnostics[-1][1] is error and not frame.save()


def test_preview_committed_readiness_notifications_locking_and_callback_failure(setup, preview_widgets, monkeypatch):
    s, *_ = setup
    # Reuse actual construction with installed widget doubles.
    preview_widgets(s, Clock(local(s, TUE, 12)))
    notifications, errors = [], []
    frame = None
    def notify(ready):
        notifications.append((ready, frame.get_prepared_export()))
    frame = previews.TimesheetPreviewFrame(object(), s, now_utc=Clock(local(s, TUE, 12)), on_readiness_changed=notify)
    frame._root().report_callback_exception = lambda *a: errors.append(a)
    assert notifications == []
    drafts(frame, str(MON), str(SAT))
    assert frame.refresh_preview() and notifications[-1] == (True, frame.get_prepared_export())
    event = frame.get_prepared_export()
    frame.set_locked(True)
    assert frame.get_prepared_export() == event and len(notifications) == 1
    assert not frame.refresh_preview() and not frame._open_picker(frame.start_var)
    frame.start_var.set('bad')
    assert notifications[-1] == (False, None)
    frame.set_locked(False)
    frame.start_var.set(str(MON))
    failure = RuntimeError('readiness observer failed')
    frame._on_readiness_changed = lambda value: (_ for _ in ()).throw(failure)
    assert frame.refresh_preview() and frame.get_prepared_export() is not None
    assert errors[-1][1] is failure and 'unable to notify owner' in frame.error_var.get()
    with pytest.raises(ValueError): frame.set_locked(1)
    with pytest.raises(ValueError):
        previews.TimesheetPreviewFrame(object(), s, now_utc=lambda: None, on_readiness_changed=False)


def test_real_tk_preview_save_invalidation_cancel_lock_retry_and_completion(setup, tk_root, pointer, monkeypatch, tmp_path):
    s, a, *_ = setup
    dated(s, a, MON, 119.9)
    frame = saves.TimesheetSaveFrame(tk_root, s, now_utc=Clock(local(s, TUE, 12)))
    frame.pack(fill='both', expand=True)
    errors = []
    tk_root.report_callback_exception = lambda *args: errors.append(args)
    tk_root.update()
    assert frame.save_button.instate(['disabled'])
    pointer.click(frame.preview.period_buttons['Custom'])
    for key, value in [('Start', str(MON)), ('End', str(SAT))]:
        entry = frame.preview.date_entries[key]
        entry.delete(0, 'end'); entry.insert(0, value)
    pointer.click(frame.preview.preview_button)
    assert frame.save_button.instate(['!disabled'])
    pointer.click(frame.preview.task_buttons[a])
    assert frame.save_button.instate(['disabled'])
    pointer.click(frame.preview.preview_button)
    event = frame.preview.get_prepared_export()
    dialog(monkeypatch, '')
    pointer.click(frame.save_button)
    assert frame.get_save_attempt() is None and not frame.preview._locked
    conflict = tmp_path / 'occupied.txt'
    conflict.write_text('Preserve', encoding='utf-8')
    dialog(monkeypatch, str(conflict))
    pointer.click(frame.save_button)
    assert frame.save_button.cget('text') == 'Retry' and frame.preview._locked
    assert frame.preview.date_entries['Start'].instate(['disabled'])
    assert frame.preview.report.cget('state') == 'disabled' and frame.preview.get_prepared_export() == event
    assert errors and frame.choose_button.winfo_ismapped()
    dialog(monkeypatch, '')
    pointer.click(frame.choose_button)
    assert frame.get_save_attempt()['destination'] == str(conflict)
    target = tmp_path / 'success.txt'
    dialog(monkeypatch, str(target))
    pointer.click(frame.choose_button)
    assert frame.saved_path == target and frame.save_button.instate(['disabled'])
    assert 'Timesheet saved:' in frame.status_var.get()
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert conflict.read_text() == 'Preserve' and len(exports(s)) == 1
