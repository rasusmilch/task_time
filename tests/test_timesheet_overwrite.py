"""Explicit one-call replacement; disposable services and connected Save controls."""
from pathlib import Path
from hashlib import sha256
import errno
from types import SimpleNamespace

import pytest

from task_timer import app as app_module
from task_timer import timesheet_save as saves
from test_export_materialization import capture as evidence, stages, staged_stream
from test_timesheet_renderer import setup as export_setup
from test_export_snapshot_registration import prepare
from test_timesheet_save import build, ready, dialog, exports, no_recalculation
from test_timesheet_preview import build as preview_widgets
from test_mixed_accounting import setup, dated, local, MON, TUE
from test_work_history import capture
from test_history_window import tk_root, pointer


_NATIVE_UNAVAILABLE = {errno.EACCES, errno.EPERM, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP}


def _make_fifo(path):
    if not hasattr(app_module.os, 'mkfifo'):
        pytest.skip('FIFO creation unavailable: os.mkfifo is absent')
    try:
        app_module.os.mkfifo(path)
    except (OSError, NotImplementedError) as exc:
        if isinstance(exc, (PermissionError, NotImplementedError)) or exc.errno in _NATIVE_UNAVAILABLE:
            pytest.skip(f'FIFO creation unavailable: {exc}')
        raise


def _make_symlink(path, target, *, target_is_directory=False):
    try:
        path.symlink_to(target, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:
        if (isinstance(exc, (PermissionError, NotImplementedError))
                or exc.errno in _NATIVE_UNAVAILABLE
                or getattr(exc, 'winerror', None) in (1, 50, 1314)):
            pytest.skip(f'Symlink creation unavailable: {exc}')
        raise


@pytest.fixture
def registered(export_setup, tmp_path):
    s, a, *_ = export_setup
    event = prepare(s, all_tasks=True)
    s.register_prepared_timesheet_export(event)
    target = tmp_path / 'replace.txt'
    target.write_bytes(b'Original external report')
    return s, event, target


def test_explicit_replacement_preserves_frozen_evidence(registered):
    s, event, target = registered
    before = evidence(s)
    assert s.materialize_timesheet_export(event['event_id'], target, overwrite=True) == target
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert sha256(target.read_bytes()).hexdigest() == event['payload']['report_sha256']
    assert evidence(s) == before and not stages(target.parent)


@pytest.mark.parametrize('overwrite', [None, 1, 'yes'])
def test_overwrite_requires_actual_bool(registered, overwrite):
    s, event, target = registered
    with pytest.raises(ValueError, match='bool'):
        s.materialize_timesheet_export(event['event_id'], target, overwrite=overwrite)
    assert target.read_bytes() == b'Original external report'


def test_connected_overwrite_control_is_explicit(setup, build, monkeypatch, tmp_path):
    s, *_ = setup
    frame = build(s)
    event = ready(frame)
    target = tmp_path / 'existing.txt'
    target.write_bytes(b'Keep until authorized')
    dialog(monkeypatch, str(target))
    assert not frame.save()
    assert frame.overwrite_button.options['state'] == 'normal'
    monkeypatch.setattr(saves.messagebox, 'askyesno', lambda **kw: True)
    assert frame.overwrite_button.invoke()
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert len(exports(s)) == 1


@pytest.mark.parametrize('overwrite', [False, True])
def test_matching_copy_is_reused_without_staging_or_rewriting(registered, monkeypatch, overwrite):
    s, event, target = registered
    target.write_bytes(event['payload']['report_text'].encode('utf-8'))
    before = target.stat()
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', lambda **kw: pytest.fail('matching copy staged'))
    assert s.materialize_timesheet_export(event['event_id'], target, overwrite=overwrite) == target
    assert target.stat() == before


def test_absent_overwrite_still_uses_exclusive_creation_and_preserves_racer(registered, monkeypatch):
    s, event, target = registered
    target.unlink()
    link = app_module.os.link
    def race(stage, destination):
        target.write_bytes(b'A newly created independent file')
        return link(stage, destination)
    monkeypatch.setattr(app_module.os, 'replace', lambda *a: pytest.fail('absent destination replaced'))
    with monkeypatch.context() as m:
        m.setattr(app_module.os, 'link', race)
        with pytest.raises(FileExistsError):
            s.materialize_timesheet_export(event['event_id'], target, overwrite=True)
    assert target.read_bytes() == b'A newly created independent file' and not stages(target.parent)
    target.unlink()
    assert s.materialize_timesheet_export(event['event_id'], target, overwrite=True) == target


@pytest.mark.parametrize('kind', ['directory', 'symlink', 'dangling', 'fifo', 'unreadable', 'short', 'unstable'])
def test_unsuitable_or_inconclusive_inspection_cannot_authorize_replacement(registered, monkeypatch, kind):
    from task_timer.export_files import ExportFileContentConflict
    s, event, target = registered
    if kind in ('directory', 'symlink', 'dangling', 'fifo'):
        target.unlink()
        if kind == 'directory': target.mkdir()
        elif kind == 'fifo': _make_fifo(target)
        else: _make_symlink(target, target.parent / ('missing' if kind == 'dangling' else 'source.txt'))
    source = target.parent / 'source.txt'
    source.write_bytes(b'Symlink source remains')
    original_open, fdopen = app_module.os.open, app_module.os.fdopen
    def denied(path, *args, **kw):
        if Path(path) == target: raise PermissionError('Inspection denied')
        return original_open(path, *args, **kw)
    class Reader:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): self.stream.close()
        def fileno(self): return self.stream.fileno()
        def read(self):
            data = self.stream.read()
            if kind == 'unstable': target.write_bytes(b'Changed during inspection')
            return data[:1] if kind == 'short' else data
    def wrapped(fd, mode, *args, **kw):
        stream = fdopen(fd, mode, *args, **kw)
        return Reader(stream) if mode == 'rb' else stream
    if kind == 'unreadable': monkeypatch.setattr(app_module.os, 'open', denied)
    if kind in ('short', 'unstable'): monkeypatch.setattr(app_module.os, 'fdopen', wrapped)
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', lambda **kw: pytest.fail('unsafe conflict reached staging'))
    with pytest.raises(OSError) as caught:
        s.materialize_timesheet_export(event['event_id'], target, overwrite=True)
    assert not isinstance(caught.value, ExportFileContentConflict)
    assert source.read_bytes() == b'Symlink source remains'
    assert s.evaluate_timesheet_export_file_status(event['event_id'], target) == (
        'UNVERIFIABLE' if kind in ('short', 'unstable', 'unreadable') else 'CONFLICT')


@pytest.mark.parametrize('relative', ['active_events.jsonl', 'log_manifest.json', 'state_snapshot.json',
                                      'settings.json', 'backups/retained.txt', 'archives/retained.txt'])
@pytest.mark.parametrize('alias', [False, True])
def test_dataset_paths_and_resolved_directory_aliases_are_protected(registered, monkeypatch, tmp_path, relative, alias):
    s, event, _ = registered
    target = s.storage.data_dir / relative
    if not target.exists():
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b'Protected dataset artifact')
    before = {p: p.read_bytes() for p in s.storage.data_dir.rglob('*') if p.is_file()}
    if alias:
        directory = tmp_path / 'dataset-alias'
        _make_symlink(directory, s.storage.data_dir, target_is_directory=True)
        target = directory / relative
    monkeypatch.setattr(app_module.tempfile, 'mkstemp', lambda **kw: pytest.fail('dataset replacement staged'))
    with pytest.raises(ValueError, match='dataset'):
        s.materialize_timesheet_export(event['event_id'], target, overwrite=True)
    assert {p: p.read_bytes() for p in s.storage.data_dir.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('change', ['disappear', 'replace', 'modify', 'symlink'])
def test_target_change_after_staging_is_detected_before_replacement(registered, monkeypatch, change):
    s, event, target = registered
    # Establish native symlink capability before entering the service operation.
    pending_link = target.with_name('changed-symlink')
    if change == 'symlink':
        _make_symlink(pending_link, target.parent / 'another-file')
    before = evidence(s)
    sync = app_module.os.fsync
    def change_target(fd):
        sync(fd)
        if change != 'modify': target.unlink()
        if change in ('replace', 'modify'): target.write_bytes(b'Changed target must survive')
        if change == 'symlink': pending_link.rename(target)
    monkeypatch.setattr(app_module.os, 'fsync', change_target)
    monkeypatch.setattr(app_module.os, 'replace', lambda *a: pytest.fail('changed target replaced'))
    with pytest.raises(OSError): s.materialize_timesheet_export(event['event_id'], target, overwrite=True)
    if change in ('replace', 'modify'): assert target.read_bytes() == b'Changed target must survive'
    elif change == 'symlink': assert target.is_symlink()
    else: assert not target.exists()
    assert not stages(target.parent) and evidence(s) == before


def test_restored_mtime_change_time_portability_recheck_is_deterministic(registered, monkeypatch):
    s, event, target = registered
    before = evidence(s)
    lstat, sync = Path.lstat, app_module.os.fsync
    initial, final_checks, changed = [], [], []
    fields = ('st_mode', 'st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    def observation(path, *args, **kw):
        current = lstat(path, *args, **kw)
        if path != target:
            return current
        if not initial:
            initial.append(current)
        if changed:
            # Only the final target recheck receives injected metadata. Keep all
            # other compared fields equal, independent of native ctime semantics.
            values = {field: getattr(initial[0], field) for field in fields}
            values['st_ctime_ns'] += 1
            final_checks.append(values)
            return SimpleNamespace(**values)
        return current
    def mutate_after_staging_sync(fd):
        sync(fd)
        target.write_bytes(b'X' * initial[0].st_size)
        app_module.os.utime(target, ns=(initial[0].st_atime_ns, initial[0].st_mtime_ns))
        changed.append(True)
    monkeypatch.setattr(Path, 'lstat', observation)
    monkeypatch.setattr(app_module.os, 'fsync', mutate_after_staging_sync)
    monkeypatch.setattr(app_module.os, 'replace', lambda *a: pytest.fail('changed target replaced'))
    with pytest.raises(OSError, match='changed before replacement'):
        s.materialize_timesheet_export(event['event_id'], target, overwrite=True)
    assert changed == [True] and len(final_checks) == 1
    assert all(final_checks[0][field] == getattr(initial[0], field) for field in fields[:-1])
    assert final_checks[0]['st_ctime_ns'] == initial[0].st_ctime_ns + 1
    assert target.read_bytes() == b'X' * initial[0].st_size
    assert not stages(target.parent) and evidence(s) == before


@pytest.mark.parametrize('phase', ['write', 'short-write', 'flush', 'fsync', 'close', 'replace'])
def test_prepublication_faults_preserve_old_file_and_original_diagnostics(registered, monkeypatch, phase):
    s, event, target = registered
    failure = OSError(f'Injected {phase} failure')
    before = evidence(s)
    def operation(operation, stream, content):
        assert target.read_bytes() == b'Original external report'
        if operation == 'write':
            if phase == 'short-write': return stream.write(content[:3])
            if phase == 'write': raise failure
            return stream.write(content)
        if operation == 'flush': stream.flush()
        if phase == operation: raise failure
    staged_stream(monkeypatch, operation)
    if phase == 'fsync': monkeypatch.setattr(app_module.os, 'fsync', lambda *_: (_ for _ in ()).throw(failure))
    if phase == 'replace': monkeypatch.setattr(app_module.os, 'replace', lambda *_: (_ for _ in ()).throw(failure))
    with pytest.raises(OSError) as caught:
        s.materialize_timesheet_export(event['event_id'], target, overwrite=True)
    if phase != 'short-write': assert caught.value is failure
    if phase == 'replace': assert 'Replacement attempted' in failure.__notes__[0]
    assert target.read_bytes() == b'Original external report'
    assert not stages(target.parent) and evidence(s) == before


def test_staging_sequence_closes_before_replace_and_verifies_consumed_path(registered, monkeypatch):
    s, event, target = registered
    sequence, replace = [], app_module.os.replace
    def operation(phase, stream, content):
        sequence.append(phase)
        if phase == 'write': return stream.write(content)
        if phase == 'flush': stream.flush()
        if phase == 'close': assert stream.closed
    staged_stream(monkeypatch, operation)
    sync = app_module.os.fsync
    def flushed(fd):
        sequence.append('fsync')
        return sync(fd)
    def replaced(stage, destination):
        assert sequence == ['write', 'flush', 'fsync', 'close']
        assert Path(stage).read_bytes() == event['payload']['report_text'].encode('utf-8')
        sequence.append('replace')
        replace(stage, destination)
        assert not Path(stage).exists()
    monkeypatch.setattr(app_module.os, 'fsync', flushed)
    monkeypatch.setattr(app_module.os, 'replace', replaced)
    assert s.materialize_timesheet_export(event['event_id'], target, overwrite=True) == target
    assert sequence[-1] == 'replace' and not stages(target.parent)


@pytest.mark.parametrize('fault', ['ambiguous-replace', 'verification', 'different-final-bytes', 'foreign-stage'])
def test_postreplacement_failure_is_truthful_and_never_rolls_back(registered, monkeypatch, fault):
    from task_timer.export_files import ExportFileContentConflict
    s, event, target = registered
    replace, verify = app_module.os.replace, s._verify_timesheet_export_file
    failure = OSError('After replacement fault')
    replaced = []
    def publication(stage, destination):
        replace(stage, destination)
        replaced.append(True)
        if fault == 'ambiguous-replace': raise failure
        if fault == 'different-final-bytes': target.write_bytes(b'External change after replacement')
        if fault == 'foreign-stage': Path(stage).write_bytes(b'Unowned staging pathname')
    def verification(*args):
        if replaced and fault == 'verification': raise failure
        return verify(*args)
    with monkeypatch.context() as m:
        m.setattr(app_module.os, 'replace', publication)
        m.setattr(s, '_verify_timesheet_export_file', verification)
        with pytest.raises(OSError) as caught:
            s.materialize_timesheet_export(event['event_id'], target, overwrite=True)
    assert not isinstance(caught.value, ExportFileContentConflict)
    if fault in ('ambiguous-replace', 'verification'):
        assert caught.value is failure and failure.__traceback__ is not None
        assert ('Replacement attempted' if fault == 'ambiguous-replace' else 'replacement occurred') in failure.__notes__[0]
    elif fault == 'different-final-bytes':
        assert isinstance(caught.value.__cause__, ExportFileContentConflict)
        assert target.read_bytes() == b'External change after replacement'
        return
    else:
        assert 'published and verified' in str(caught.value)
        assert stages(target.parent)[0].read_bytes() == b'Unowned staging pathname'
    observation = target.stat()
    assert s.materialize_timesheet_export(event['event_id'], target) == target
    assert target.stat() == observation


def test_replacement_and_cleanup_errors_keep_primary_error_and_old_file(registered, monkeypatch):
    s, event, target = registered
    error, unlink = OSError('Replacement denied'), Path.unlink
    def cleanup(path, *a, **kw):
        assert path != target
        if path.name.startswith('.chronicle-'): raise PermissionError('Cleanup denied')
        return unlink(path, *a, **kw)
    monkeypatch.setattr(app_module.os, 'replace', lambda *a: (_ for _ in ()).throw(error))
    monkeypatch.setattr(Path, 'unlink', cleanup)
    with pytest.raises(OSError) as caught:
        s.materialize_timesheet_export(event['event_id'], target, overwrite=True)
    assert caught.value is error and any('cleanup failed' in note for note in error.__notes__)
    assert target.read_bytes() == b'Original external report' and len(stages(target.parent)) == 1


def test_confirmation_cancel_reentry_and_one_call_authorization(setup, build, monkeypatch, tmp_path):
    s, a, *_ = setup
    dated(s, a, MON, 10800.125)
    s.start_task(a)
    frame = build(s)
    event = ready(frame)
    target = tmp_path / 'authorize.txt'
    target.write_bytes(b'Original contents')
    dialog(monkeypatch, str(target))
    assert not frame.save() and not frame.save()  # Ordinary Retry stays protective.
    before, attempt = capture(s), frame.get_save_attempt()
    assert frame._can_overwrite
    calls = []
    def cancel(**kw):
        calls.append(kw)
        assert frame._busy
        assert not frame.save() and not frame.overwrite() and not frame.choose_another_file()
        return False
    monkeypatch.setattr(saves.messagebox, 'askyesno', cancel)
    assert not frame.overwrite_button.invoke()
    assert len(calls) == 1 and calls[0]['default'] == 'no' and str(target) in calls[0]['message']
    assert 'parent' in calls[0] and capture(s) == before and frame.get_save_attempt() == attempt
    assert frame._can_overwrite and frame.preview._locked
    no_recalculation(monkeypatch, s)
    register, materialize = s.register_prepared_timesheet_export, s.materialize_timesheet_export
    sequence = []
    def registration(candidate):
        sequence.append('register')
        assert not frame._can_overwrite and candidate == event
        assert target.read_bytes() == b'Original contents'
        return register(candidate)
    def publication(identity, destination, **kw):
        assert sequence == ['register'] and kw == {'overwrite': True}
        sequence.append('publish')
        return materialize(identity, destination, **kw)
    monkeypatch.setattr(s, 'register_prepared_timesheet_export', registration)
    monkeypatch.setattr(s, 'materialize_timesheet_export', publication)
    monkeypatch.setattr(saves.messagebox, 'askyesno', lambda **kw: True)
    assert frame.overwrite() and sequence == ['register', 'publish']
    assert frame.saved_path == target and frame.get_save_attempt() == attempt and len(exports(s)) == 1
    assert capture(s) == before and not frame.overwrite() and not frame.save()


@pytest.mark.parametrize('source', ['registration', 'inspection', 'publication', 'type-conflict'])
def test_only_materialization_content_conflict_enables_overwrite(setup, build, monkeypatch, tmp_path, source):
    from task_timer.export_files import ExportFileContentConflict, ExportFileConflict
    s, *_ = setup
    frame = build(s)
    ready(frame)
    target = tmp_path / 'error.txt'
    dialog(monkeypatch, str(target))
    errors = {'registration': ExportFileContentConflict('not from materialization'),
              'inspection': PermissionError('read denied'), 'publication': FileExistsError('raced'),
              'type-conflict': ExportFileConflict('directory')}
    name = 'register_prepared_timesheet_export' if source == 'registration' else 'materialize_timesheet_export'
    monkeypatch.setattr(s, name, lambda *a, **kw: (_ for _ in ()).throw(errors[source]))
    assert not frame.save() and not frame._can_overwrite and not frame.overwrite()
    assert frame.overwrite_button.options['state'] == 'disabled'


def test_failed_overwrite_does_not_authorize_retry_or_alternate_path(setup, build, monkeypatch, tmp_path):
    s, *_ = setup
    frame = build(s)
    event = ready(frame)
    target, alternate = tmp_path / 'one.txt', tmp_path / 'two.txt'
    target.write_bytes(b'One'); alternate.write_bytes(b'Two')
    dialog(monkeypatch, str(target))
    assert not frame.save() and frame._can_overwrite
    confirm, materialize = [], s.materialize_timesheet_export
    monkeypatch.setattr(saves.messagebox, 'askyesno', lambda **kw: confirm.append(kw) or True)
    error = OSError('Replacement unavailable')
    with monkeypatch.context() as m:
        m.setattr(app_module.os, 'replace', lambda *a: (_ for _ in ()).throw(error))
        assert not frame.overwrite()
    assert not frame._can_overwrite and target.read_bytes() == b'One'
    assert not frame.save() and frame._can_overwrite  # New stable conflict, not inherited permission.
    dialog(monkeypatch, str(alternate))
    assert not frame.choose_another_file() and alternate.read_bytes() == b'Two'
    assert frame._can_overwrite and len(confirm) == 1
    assert frame.overwrite() and len(confirm) == 2 and str(alternate) in confirm[-1]['message']
    assert target.read_bytes() == b'One' and alternate.read_bytes() == event['payload']['report_text'].encode('utf-8')


def test_ambiguous_publication_retains_exact_inputs_and_newer_work_confirmation(setup, build, monkeypatch, tmp_path):
    from test_polr_confirmation_writer import register
    from test_polr_confirmation_replay import cell
    s, a, *_ = setup
    dated(s, a, MON, 10800)
    s.start_task(a)
    frame = build(s)
    event = ready(frame)
    target = tmp_path / 'ambiguous.txt'
    target.write_bytes(b'Conflicting report')
    dialog(monkeypatch, str(target))
    assert not frame.save()
    dated(s, a, MON, 7200)
    register(s, cell(a, 500))
    before, retained = capture(s), frame.get_save_attempt()
    replace = app_module.os.replace
    failure = OSError('Replace returned an ambiguous failure')
    def ambiguous(stage, destination):
        replace(stage, destination)
        raise failure
    monkeypatch.setattr(saves.messagebox, 'askyesno', lambda **kw: True)
    with monkeypatch.context() as m:
        m.setattr(app_module.os, 'replace', ambiguous)
        assert not frame.overwrite()
    assert frame.saved_path is None and frame.diagnostics[-1][1] is failure
    assert frame.get_save_attempt() == retained and not frame._can_overwrite
    stat = target.stat()
    no_recalculation(monkeypatch, s)
    assert frame.save() and frame.saved_path == target
    assert target.stat() == stat and capture(s) == before and len(exports(s)) == 1
    assert target.read_bytes() == event['payload']['report_text'].encode('utf-8')


def test_real_tk_overwrite_retry_alternate_confirmation_and_replacement(setup, tk_root, pointer, monkeypatch, tmp_path):
    from test_work_history_browser import Clock
    s, a, *_ = setup
    dated(s, a, MON, 3600)
    frame = saves.TimesheetSaveFrame(tk_root, s, now_utc=Clock(local(s, TUE, 12)))
    frame.pack(fill='both', expand=True)
    errors = []
    tk_root.report_callback_exception = lambda *args: errors.append(args)
    tk_root.update()
    frame.preview.period_var.set('Custom')
    frame.preview.start_var.set(str(MON)); frame.preview.end_var.set(str(TUE))
    pointer.click(frame.preview.preview_button)
    event = frame.preview.get_prepared_export()
    first, second = tmp_path / 'first.txt', tmp_path / 'second.txt'
    first.write_bytes(b'First'); second.write_bytes(b'Second')
    dialog(monkeypatch, str(first))
    pointer.click(frame.save_button)
    assert frame.overwrite_button.winfo_ismapped() and frame.overwrite_button.instate(['!disabled'])
    before = capture(s)
    confirms = []
    monkeypatch.setattr(saves.messagebox, 'askyesno', lambda **kw: confirms.append(kw) or False)
    pointer.click(frame.overwrite_button)
    assert confirms[-1]['default'] == 'no' and capture(s) == before and first.read_bytes() == b'First'
    pointer.click(frame.save_button)  # Retry remains non-overwriting.
    assert first.read_bytes() == b'First'
    dialog(monkeypatch, str(second))
    pointer.click(frame.choose_button)
    assert second.read_bytes() == b'Second' and frame._can_overwrite
    monkeypatch.setattr(saves.messagebox, 'askyesno', lambda **kw: confirms.append(kw) or True)
    pointer.click(frame.overwrite_button)
    assert frame.saved_path == second and frame.save_button.instate(['disabled'])
    assert not frame.overwrite_button.winfo_ismapped()
    assert second.read_bytes() == event['payload']['report_text'].encode('utf-8')
    assert first.read_bytes() == b'First' and str(second) in confirms[-1]['message']
    assert capture(s) == before and len(exports(s)) == 1


def test_fifo_api_unavailable_portability_skips_only_native_setup(monkeypatch, tmp_path):
    monkeypatch.delattr(app_module.os, 'mkfifo', raising=False)
    with pytest.raises(pytest.skip.Exception, match='FIFO'):
        _make_fifo(tmp_path / 'pipe')


@pytest.mark.parametrize('kind', ['fifo', 'symlink'])
@pytest.mark.parametrize('error', [PermissionError(errno.EACCES, 'Denied'),
                                 OSError(errno.ENOTSUP, 'Unsupported'),
                                 NotImplementedError('Unavailable')])
def test_native_setup_portability_restrictions_are_narrow_skips(monkeypatch, tmp_path, kind, error):
    def restricted(*args, **kw): raise error
    if kind == 'fifo':
        monkeypatch.setattr(app_module.os, 'mkfifo', restricted, raising=False)
    else:
        monkeypatch.setattr(Path, 'symlink_to', restricted)
    with pytest.raises(pytest.skip.Exception, match='unavailable'):
        if kind == 'fifo': _make_fifo(tmp_path / 'pipe')
        else: _make_symlink(tmp_path / 'alias', tmp_path / 'source', target_is_directory=True)


@pytest.mark.parametrize('kind', ['fifo', 'symlink'])
@pytest.mark.parametrize('error', [OSError(errno.EIO, 'Unexpected I/O error'),
                                 FileNotFoundError(errno.ENOENT, 'Bad setup path'),
                                 AssertionError('Unexpected setup assertion')])
def test_unexpected_setup_errors_portability_remain_failures(monkeypatch, tmp_path, kind, error):
    def broken(*args, **kw): raise error
    if kind == 'fifo':
        monkeypatch.setattr(app_module.os, 'mkfifo', broken, raising=False)
    else:
        monkeypatch.setattr(Path, 'symlink_to', broken)
    try:
        with pytest.raises(type(error)) as caught:
            if kind == 'fifo': _make_fifo(tmp_path / 'pipe')
            else: _make_symlink(tmp_path / 'alias', tmp_path / 'source')
    except pytest.skip.Exception as skipped:
        pytest.fail(f'Unexpected setup failure was hidden as a capability skip: {skipped}')
    assert caught.value is error


def test_symlink_target_setup_portability_precedes_materialization(registered, monkeypatch):
    s, _, _ = registered
    calls = []
    def denied(*args, **kw): raise PermissionError(errno.EACCES, 'No symlink privilege')
    def service(*args, **kw):
        calls.append(1)
        pytest.fail('Native test object was not established before service execution')
    monkeypatch.setattr(Path, 'symlink_to', denied)
    monkeypatch.setattr(s, 'materialize_timesheet_export', service)
    with pytest.raises(pytest.skip.Exception, match='Symlink'):
        test_target_change_after_staging_is_detected_before_replacement(registered, monkeypatch, 'symlink')
    assert calls == []
