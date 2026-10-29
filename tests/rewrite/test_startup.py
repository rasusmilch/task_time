"""One-root source startup, real worker readiness, and isolated preferences."""
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk

import pytest

from chronicle.app import ChronicleApp
from chronicle import bootstrap, launcher_selection as ls
from chronicle.records import Request
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.startup import StartupWindow, OTHER
from chronicle.worker import DatabaseWorker
from conftest import NOW, uid
from test_app import root, pump, click, keyboard
from test_chronicle_history_operator import choose_combo
from test_backup_restore import logical, rich
from test_interruptions import hot_dataset, leave_hot_journal


@pytest.fixture
def launch(root, tmp_path):
    values = []
    places = ls.Locations(tmp_path/'user-local'/'Data', tmp_path/'user-local'/'launcher-selection.json')
    def make(**kw):
        value = StartupWindow(root, app_factory=kw.pop('app_factory', ChronicleApp),
            worker_factory=kw.pop('worker_factory', DatabaseWorker),
            locations=kw.pop('locations', places), timezone_id='Central Standard Time', **kw)
        values.append(value)
        return value
    yield make
    for flow in values:
        worker = flow.worker
        try: root.destroy()
        except tk.TclError: pass
        if worker is not None:
            worker.join(8)
            assert not worker.is_alive()


def choose_create(flow, directory):
    flow.folder.delete(0, 'end'); flow.folder.insert(0, str(directory))
    flow.timezone.set('Central Time (US & Canada)'); flow.zone_changed()


def seed(directory, *, active=False):
    store = SQLiteStore(directory, create=True, timezone='Australia/Lord_Howe')
    service = TimerService(store)
    task, entry = uid(), uid()
    assert service.create_task(task, 'Retained', request_id=uid(), action_utc_us=NOW).status == 'committed'
    if active:
        assert service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=NOW).status == 'committed'
    identity = store.dataset_id
    store.close()
    return identity, entry


def test_real_tk_first_run_cancel_never_creates_worker_settings_or_dataset(launch, root, tmp_path, click):
    calls = []
    def forbidden(*a, **kw): calls.append(True); pytest.fail('Cancel constructed a worker')
    flow = launch(worker_factory=forbidden)
    pump(root, lambda: flow.discover_id is None)
    assert root.title() == 'Welcome to Chronicle'
    assert flow.timezone.get() == 'Central Time (US & Canada)'
    assert not flow.locations.folder.exists() and not flow.locations.record.exists()
    click(flow.cancel_button, closes_root=True)
    assert not calls and flow.app is None and not flow.alive
    assert not list(tmp_path.iterdir())


def test_real_tk_choose_timezone_create_handoff_one_root_and_ready_only_settings(launch, root, tmp_path, monkeypatch, click, keyboard):
    flow = launch()
    pump(root, lambda: flow.discover_id is None)
    data = tmp_path/'spaces Ω'/'dataset'
    monkeypatch.setattr('chronicle.startup.filedialog.askdirectory', lambda **kw: str(data))
    click(flow.choose_button)
    choose_combo(root, flow.timezone, 7, click, keyboard)
    assert flow.folder.get() == str(data) and 'UTC' in flow.zone_label.cget('text')
    original, remembered = ls.remember, []
    def remember(*args):
        assert flow.app.ready and flow.app.root is root
        assert flow.app.dataset_id and flow.app.timezone == 'Etc/UTC'
        remembered.append(args)
        return original(*args)
    monkeypatch.setattr(ls, 'remember', remember)
    click(flow.create_button)
    pump(root, lambda: flow.app is not None and flow.app.state.get('report') is not None)
    assert len(remembered) == 1 and not flow.alive and flow.poll_id is None
    assert not flow.frame.winfo_exists() and root.grab_current() is None
    assert root.title() == 'Chronicle' and flow.app.root is root
    assert ls.read_selection(flow.locations.record).directory == data
    assert not any(w.winfo_class() == 'Toplevel' for w in root.winfo_children())


@pytest.mark.parametrize('remembered', [True, False])
def test_real_tk_remembered_or_default_existing_opens_without_create_or_timezone(launch, root, tmp_path, remembered):
    data = tmp_path/'existing' if remembered else tmp_path/'user-local'/'Data'
    identity, entry = seed(data, active=True)
    facts = logical(data/'chronicle.sqlite3')
    if remembered: ls.remember(tmp_path/'user-local'/'launcher-selection.json', data, None)
    calls = []
    def worker(directory, **kw):
        calls.append((directory, kw))
        return DatabaseWorker(directory, **kw)
    flow = launch(worker_factory=worker)
    pump(root, lambda: flow.app is not None and flow.app.state.get('report') is not None)
    assert calls == [(data, {'create': False, 'timezone': None})]
    assert flow.app.dataset_id == identity and flow.app.timezone == 'Australia/Lord_Howe'
    assert flow.app.state['active']['entry_id'] == entry
    assert logical(data/'chronicle.sqlite3') == facts


@pytest.mark.parametrize('kind', ['empty', 'nonempty', 'missing'])
def test_real_tk_default_discovery_never_implicitly_creates(launch, root, tmp_path, kind):
    data = tmp_path/'user-local'/'Data'
    if kind != 'missing': data.mkdir(parents=True)
    if kind == 'nonempty': (data/'unknown').write_bytes(b'keep')
    flow = launch()
    pump(root, lambda: flow.discover_id is None)
    assert flow.app is flow.worker is None and not flow.locations.record.exists()
    assert not (data/'chronicle.sqlite3').exists()
    if kind == 'nonempty':
        assert 'unknown or incomplete' in flow.status.cget('text')
        assert (data/'unknown').read_bytes() == b'keep'


def test_real_tk_open_existing_owned_chooser_cancel_and_timezone_preserved(launch, root, tmp_path, monkeypatch, click):
    identity, _ = seed(tmp_path/'existing')
    flow = launch()
    pump(root, lambda: flow.discover_id is None)
    choices = iter(['', str(tmp_path/'existing')]); parents = []
    def chooser(**kw):
        parents.append(kw)
        return next(choices)
    monkeypatch.setattr('chronicle.startup.filedialog.askdirectory', chooser)
    click(flow.open_button)
    assert flow.worker is None and not flow.locations.record.exists()
    click(flow.open_button)
    pump(root, lambda: flow.app is not None and flow.app.state.get('report') is not None)
    assert all(v['parent'] is root and v['mustexist'] is True for v in parents)
    assert flow.app.dataset_id == identity and flow.app.timezone == 'Australia/Lord_Howe'


@pytest.mark.parametrize('kind', ['missing', 'foreign', 'schema', 'v1', 'unreadable_record', 'corrupt_record'])
def test_real_tk_bad_remembered_selection_refuses_preserves_and_allows_cancel(launch, root, tmp_path, kind, click):
    data, record = tmp_path/'existing', tmp_path/'user-local'/'launcher-selection.json'
    if kind != 'missing': seed(data)
    ls.remember(record, data, None)
    if kind == 'foreign':
        import sqlite3
        with sqlite3.connect(data/'chronicle.sqlite3') as c: c.execute('PRAGMA application_id=123')
    if kind == 'v1':
        import sqlite3
        with sqlite3.connect(data/'chronicle.sqlite3') as c: c.execute('PRAGMA user_version=1')
    if kind == 'schema':
        import sqlite3
        with sqlite3.connect(data/'chronicle.sqlite3') as c: c.execute('CREATE TABLE extra(x)')
    if kind == 'corrupt_record': record.write_bytes(b'{broken')
    if kind == 'unreadable_record':
        record.unlink(); record.mkdir()
    raw = record.read_bytes() if record.is_file() else None
    files = {p.name: p.read_bytes() for p in data.iterdir()} if data.exists() else {}
    flow = launch()
    pump(root, lambda: flow.discover_id is None and flow.worker is None and bool(flow.status.cget('text')))
    assert flow.app is None
    if kind == 'v1': assert 'schema' in flow.status.cget('text').lower()
    assert (record.read_bytes() if record.is_file() else None) == raw
    assert ({p.name: p.read_bytes() for p in data.iterdir()} if data.exists() else {}) == files
    click(flow.cancel_button, closes_root=True)
    assert not flow.alive


@pytest.mark.parametrize('kind', ['unknown', 'invalid_zone', 'race_file', 'race_directory'])
def test_real_tk_failed_creation_preserves_draft_data_and_selection(launch, root, tmp_path, kind):
    flow = launch()
    pump(root, lambda: flow.discover_id is None)
    data = tmp_path/'create'
    choose_create(flow, data)
    if kind == 'unknown': data.mkdir(); (data/'unknown').write_bytes(b'keep')
    if kind == 'invalid_zone': flow.timezone.set(OTHER); flow.other.insert(0, 'Not/AZone')
    if kind.startswith('race'):
        def race(directory, **kw):
            directory.mkdir()
            if kind == 'race_file': (directory/'unknown').write_bytes(b'keep')
            else: (directory/'unknown').mkdir()
            return DatabaseWorker(directory, **kw)
        flow.worker_factory = race
    flow.create()
    pump(root, lambda: flow.worker is None and bool(flow.status.cget('text')))
    assert flow.app is None and not flow.locations.record.exists()
    assert flow.folder.get() == str(data)
    assert not (data/'chronicle.sqlite3').exists()
    if kind in ('unknown', 'race_file'): assert (data/'unknown').read_bytes() == b'keep'
    if kind == 'race_directory': assert (data/'unknown').is_dir()


def test_real_tk_settings_write_failure_preserves_successful_open(launch, root, tmp_path, monkeypatch):
    flow = launch()
    pump(root, lambda: flow.discover_id is None)
    choose_create(flow, tmp_path/'created')
    def fail(*a): raise PermissionError('selection publication denied')
    monkeypatch.setattr(ls, 'remember', fail)
    flow.create()
    pump(root, lambda: flow.app is not None and flow.app.state.get('report') is not None)
    assert flow.app.ready and 'could not be remembered' in flow.app.launcher_notice.cget('text')
    request = Request.make(uid(), flow.app.dataset_id, 'create_task', NOW, task_id=uid(), name='Still usable', project_id=None)
    flow.app._submit('create_task', task_id=request.args()['task_id'], name='Still usable', project_id=None)
    pump(root, lambda: flow.app.pending is None and bool(flow.app.state['tasks']))
    assert not flow.locations.record.exists()


def test_real_tk_corrupt_record_explicit_choice_opens_without_replacing_record(launch, root, tmp_path, monkeypatch):
    record = tmp_path/'user-local'/'launcher-selection.json'; record.parent.mkdir()
    record.write_bytes(b'{bad selection')
    seed(tmp_path/'existing')
    flow = launch()
    pump(root, lambda: flow.discover_id is None)
    monkeypatch.setattr('chronicle.startup.filedialog.askdirectory', lambda **kw: str(tmp_path/'existing'))
    flow.open_existing()
    pump(root, lambda: flow.app is not None and flow.app.state.get('report') is not None)
    assert record.read_bytes() == b'{bad selection'
    assert 'could not be remembered' in flow.app.launcher_notice.cget('text')


def test_real_tk_second_owner_refusal_never_adopts_or_replaces_selection(launch, root, tmp_path):
    data = tmp_path/'owned'; owner = SQLiteStore(data, create=True, timezone='UTC')
    try:
        record = tmp_path/'user-local'/'launcher-selection.json'
        ls.remember(record, data, None); raw = record.read_bytes()
        flow = launch()
        pump(root, lambda: flow.discover_id is None and flow.worker is None and flow.failure is not None)
        assert flow.app is None and record.read_bytes() == raw
        assert owner.connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally: owner.close()


def test_real_tk_cleanup_retry_retains_ownership_before_new_selection(launch, root, tmp_path, monkeypatch):
    original_close = SQLiteStore.close
    allow = []
    def profile(self): raise ValueError('initial profile failure')
    def close(self):
        if not allow: raise OSError('close pending')
        return original_close(self)
    monkeypatch.setattr(SQLiteStore, '_profile', profile)
    monkeypatch.setattr(SQLiteStore, 'close', close)
    flow = launch()
    pump(root, lambda: flow.discover_id is None)
    choose_create(flow, tmp_path/'failed')
    flow.create()
    pump(root, lambda: flow.cleanup_failed)
    assert flow.app is None and flow.worker.is_alive()
    from chronicle.dataset_lock import DatasetLock
    contender = DatasetLock(tmp_path/'failed')
    try:
        with pytest.raises(OSError): contender.acquire()
    finally: contender.close()
    flow.cancel(); assert flow.alive and flow.worker is not None
    allow.append(True); flow.retry_cleanup()
    pump(root, lambda: flow.worker is None)
    owner = DatasetLock(tmp_path/'failed')
    try: owner.acquire()
    finally: owner.close()
    assert not flow.locations.record.exists()


@pytest.mark.parametrize('args', [['--create'], ['--timezone', 'UTC'], ['--create', '--timezone', 'UTC']])
def test_cli_incomplete_explicit_creation_refuses_before_tk(args, monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap.tk, 'Tk', lambda: pytest.fail('Invalid CLI constructed Tk'))
    with pytest.raises(SystemExit) as caught: bootstrap.main(args)
    assert caught.value.code == 2 and not list(tmp_path.iterdir())


def test_real_tk_root_launcher_noargs_create_then_remembered_active_reopen(root, tmp_path):
    env = {**os.environ, 'HOME': str(tmp_path), 'XDG_DATA_HOME': str(tmp_path/'local'),
           'LOCALAPPDATA': str(tmp_path)}
    code = r'''
import runpy, sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from chronicle.startup import StartupWindow
import chronicle.startup as module
Original = StartupWindow
mode, directory = sys.argv[1:]
class Driver(Original):
    def __init__(self, root, **kw):
        super().__init__(root, **kw)
        root.after(10, self.drive)
    def drive(self):
        if self.app is not None and self.app.state.get('report') is not None:
            print('READY', self.app.dataset_id, self.app.state.get('active'), flush=True)
            self.app.request_close()
            return
        if mode == 'create' and self.worker is None:
            self.folder.delete(0, 'end'); self.folder.insert(0, directory)
            self.timezone.set('Central Time (US & Canada)')
            self.create()
        self.root.after(10, self.drive)
module.StartupWindow = Driver
sys.argv = ['run_chronicle.py']
runpy.run_path('run_chronicle.py', run_name='__main__')
'''
    data = tmp_path/'source dataset Ω'
    def run(mode):
        result = subprocess.run([sys.executable, '-B', '-c', code, mode, str(data)], env=env,
            capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        assert 'READY' in result.stdout
        return result.stdout
    run('create')
    _, entry = seed_active(data)
    before = logical(data/'chronicle.sqlite3')
    assert entry in run('reopen')
    assert logical(data/'chronicle.sqlite3') == before


def seed_active(data):
    store = SQLiteStore(data)
    task, entry = uid(), uid()
    service = TimerService(store)
    try:
        assert service.create_task(task, 'Active', request_id=uid(), action_utc_us=NOW).status == 'committed'
        assert service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=NOW).status == 'committed'
        return task, entry
    finally: store.close()


def test_real_tk_explicit_cli_does_not_read_or_replace_remembered_selection(root, tmp_path, monkeypatch):
    data = tmp_path/'explicit'; identity, _ = seed(data)
    record = tmp_path/'selection'; ls.remember(record, tmp_path/'remembered', None)
    raw = record.read_bytes()
    original = ChronicleApp
    class Driver(original):
        def __init__(self, root, worker):
            super().__init__(root, worker)
            root.after(10, self.drive)
        def drive(self):
            if self.ready and self.state.get('report') is not None:
                assert self.dataset_id == identity
                self.request_close()
            elif self.alive: self.root.after(10, self.drive)
    monkeypatch.setattr(bootstrap.tk, 'Tk', lambda: root)
    monkeypatch.setattr(bootstrap, 'ChronicleApp', Driver)
    monkeypatch.setattr(ls, 'locations', lambda: pytest.fail('Explicit CLI read launcher preferences'))
    monkeypatch.setattr(ls, 'remember', lambda *a: pytest.fail('Explicit CLI replaced launcher preferences'))
    app = bootstrap.main(['--data-dir', str(data)])
    app.worker.join(8)
    assert not app.worker.is_alive() and record.read_bytes() == raw


def test_recovery_commands_never_construct_onboarding(store, tmp_path, monkeypatch):
    backup = tmp_path/'backup'; assert store.backup(backup).verified
    def forbidden(*a, **kw): pytest.fail('Recovery constructed a GUI/worker or read preferences')
    monkeypatch.setattr(bootstrap.tk, 'Tk', forbidden)
    monkeypatch.setattr(bootstrap, 'ChronicleApp', forbidden)
    monkeypatch.setattr(bootstrap, 'DatabaseWorker', forbidden)
    monkeypatch.setattr(ls, 'locations', forbidden)
    assert bootstrap.main(['--verify-backup', str(backup)]).dataset_id == store.dataset_id
    assert bootstrap.main(['--restore-from', str(backup), '--data-dir', str(tmp_path/'restored')]).verified


def test_real_tk_no_legacy_discovery(launch, root, tmp_path, monkeypatch):
    legacy = tmp_path/'.task_timer_data'; legacy.mkdir()
    sentinel = legacy/'active_events.jsonl'; sentinel.write_bytes(b'legacy untouched')
    iterdir = Path.iterdir
    def checked(path):
        if path == legacy: pytest.fail('Legacy discovery')
        return iterdir(path)
    monkeypatch.setattr(Path, 'iterdir', checked)
    flow = launch()
    pump(root, lambda: flow.discover_id is None)
    assert flow.worker is None and sentinel.read_bytes() == b'legacy untouched'



def test_real_tk_remembered_hot_journal_uses_owned_worker_not_cold_inspection(launch, root, tmp_path, hot_dataset, monkeypatch):
    from chronicle import backup_restore
    directory, before, _ = hot_dataset
    leave_hot_journal(directory)
    ls.remember(tmp_path/'user-local'/'launcher-selection.json', directory, None)
    monkeypatch.setattr(backup_restore, 'inspect_dataset', lambda *a: pytest.fail('Cold inspection gated normal recovery'))
    flow = launch()
    pump(root, lambda: flow.app is not None and flow.app.state.get('report') is not None)
    assert logical(directory/'chronicle.sqlite3') == before
    assert flow.app.runtime['journal_mode'] == 'delete'
    assert flow.app.runtime['synchronous'] == 3 and flow.app.runtime['foreign_keys'] == 1


def test_real_tk_folder_chooser_reentry_cancel_and_exception_preserve_setup(launch, root, monkeypatch):
    flow = launch()
    pump(root, lambda: flow.discover_id is None)
    original_folder = flow.folder.get()
    def chooser(**kwargs):
        assert kwargs['parent'] is root and flow.choosing
        assert flow.create_button.instate(['disabled'])
        flow.create(); flow.open_existing(); flow.choose_folder(); flow.cancel()
        assert flow.worker is None and flow.alive
        raise OSError('owned folder chooser unavailable')
    monkeypatch.setattr('chronicle.startup.filedialog.askdirectory', chooser)
    flow.choose_folder()
    assert not flow.choosing and flow.worker is None
    assert 'owned folder chooser unavailable' in flow.status.cget('text')
    assert flow.folder.get() == original_folder and not flow.locations.record.exists()
    assert not flow.cancel_button.instate(['disabled'])


@pytest.mark.parametrize('when', ['constructor', 'ready'])
def test_real_tk_failed_handoff_retires_callbacks_then_retains_setup_and_dataset(launch, root, tmp_path, monkeypatch, when):
    callbacks = []
    class Broken(ChronicleApp):
        def __init__(self, root, worker):
            super().__init__(root, worker)
            root.after(20, lambda: callbacks.append('obsolete partial app'))
            if when == 'constructor': raise OSError('constructor handoff failed')
        def _handle(self, message):
            super()._handle(message)
            if message.kind == 'ready': raise OSError('ready handoff failed')
    flow = launch(app_factory=Broken)
    pump(root, lambda: flow.discover_id is None)
    data = tmp_path/'retained'; choose_create(flow, data)
    flow.create()
    pump(root, lambda: flow.worker is None and flow.failure is not None)
    assert flow.alive and flow.app is None and not callbacks
    assert 'handoff failed' in flow.status.cget('text')
    assert not flow.locations.record.exists()
    before = logical(data/'chronicle.sqlite3')
    flow.app_factory = ChronicleApp
    monkeypatch.setattr('chronicle.startup.filedialog.askdirectory', lambda **kw: str(data))
    flow.open_existing()
    pump(root, lambda: flow.app is not None and flow.app.state.get('report') is not None)
    assert logical(data/'chronicle.sqlite3') == before and not callbacks
    assert root.grab_current() is None
