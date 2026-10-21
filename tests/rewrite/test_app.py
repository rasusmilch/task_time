from contextlib import contextmanager
from datetime import timedelta
from queue import Queue
import threading
import tkinter as tk

import pytest

from chronicle.app import ChronicleApp
from chronicle.records import Outcome, Request
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import from_us
from chronicle.worker import DatabaseWorker, Message
from conftest import NOW, uid


def pump(root, predicate, timeout=8000):
    done, errors, scheduled = [], [], []
    def check():
        try:
            if predicate():
                done.append(True)
                root.quit()
            else:
                scheduled.append(root.after(5, check))
        except Exception as exc:
            errors.append(exc)
            root.quit()
    deadline = root.after(timeout, root.quit)
    scheduled.append(root.after(0, check))
    try:
        root.mainloop()  # Bounded test driver; the runtime itself owns one ordinary mainloop.
    finally:
        for token in [deadline, *scheduled]:
            try:
                root.after_cancel(token)
            except tk.TclError:
                pass  # Test driver may have deliberately destroyed its interpreter.
    if errors:
        raise errors[0]
    assert done, "Timed out waiting for the connected Tk/worker result"


@pytest.fixture
def root():
    import gc
    # Dispose prior test interpreters on their creating thread before starting another worker.
    gc.collect()
    try:
        value = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Real Tk display unavailable: {exc}")
    value.geometry("950x600+20+20")
    errors = []
    value.report_callback_exception = lambda *args: errors.append(args)
    value.test_errors = errors
    yield value
    try:
        value.destroy()
    except tk.TclError:
        pass
    gc.collect()


class Clock:
    def __init__(self):
        self.value = from_us(NOW)
        self.calls = 0
    def __call__(self):
        self.calls += 1
        return self.value


@pytest.fixture
def connected(root, tmp_path):
    worker = DatabaseWorker(tmp_path / "fresh", create=True, timezone="America/Chicago")
    clock = Clock()
    app = ChronicleApp(root, worker, now_utc=clock)
    worker.start()
    pump(root, lambda: app.ready and app.state.get("report") is not None)
    yield app, worker, clock
    if app.alive:
        root.destroy()  # Forced test cleanup sends orderly worker shutdown, without UI join.
    worker.join(timeout=8)
    assert not worker.is_alive()


@pytest.fixture
def click(root):
    """Actual X11 server input; no direct Button.invoke substitute."""
    import ctypes as c
    from ctypes.util import find_library
    import sys
    if sys.platform != "linux" or not find_library("X11") or not find_library("Xtst"):
        pytest.skip("Server-input fixture requires Linux X11/XTest; Windows evidence is separate")
    x, xt = c.CDLL(find_library("X11")), c.CDLL(find_library("Xtst"))
    x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [c.c_char_p], c.c_void_p
    x.XCloseDisplay.argtypes = [c.c_void_p]
    x.XSync.argtypes = [c.c_void_p, c.c_int]
    xt.XTestFakeMotionEvent.argtypes = [c.c_void_p, c.c_int, c.c_int, c.c_int, c.c_ulong]
    xt.XTestFakeButtonEvent.argtypes = [c.c_void_p, c.c_uint, c.c_int, c.c_ulong]
    display = x.XOpenDisplay(None)
    if not display:
        pytest.skip("XTest cannot open the isolated display")
    def perform(widget, xy=None, *, closes_root=False):
        pump(root, lambda: widget.winfo_ismapped() and widget.winfo_width() > 1)
        xx, yy = xy or (widget.winfo_width() // 2, widget.winfo_height() // 2)
        assert xt.XTestFakeMotionEvent(display, -1, widget.winfo_rootx() + xx, widget.winfo_rooty() + yy, 0)
        assert xt.XTestFakeButtonEvent(display, 1, True, 0)
        assert xt.XTestFakeButtonEvent(display, 1, False, 0)
        x.XSync(display, False)
        if closes_root:
            deadline = root.after(6000, root.quit)
            root.mainloop()  # Successful shutdown may destroy Tk before the normal click check.
            root.after_cancel(deadline)
            return
        flag = []
        root.after(40, lambda: flag.append(True))
        pump(root, lambda: flag)
    yield perform
    x.XCloseDisplay(display)


def create(app, name="Same"):
    assert app._submit("create_task", task_id=uid(), name=name, project_id=None)
    pump(app.root, lambda: app.pending is None and not app.executing and app._read_inflight is None)
    return next(t["task_id"] for t in app.state["tasks"] if t["name"] == name)


def test_real_tk_production_controls_main_mini_switch_and_shared_cutoff(connected, root, click, monkeypatch):
    app, worker, clock = connected
    import chronicle.app as module
    names = iter(["Same", "Same"])
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *args, **kwargs: next(names))
    click(app.buttons["Create task"])
    pump(root, lambda: len(app.state["tasks"]) == 1 and app.pending is None)
    click(app.buttons["Create task"])
    pump(root, lambda: len(app.state["tasks"]) == 2 and app.pending is None)
    first, second = [t["task_id"] for t in app.state["tasks"]]
    assert first != second
    box = app.tree.bbox(first)
    click(app.tree, (box[0] + 35, box[1] + box[3] // 2))
    assert app.selected_task_id() == first
    before = clock.calls
    click(app.buttons["Start"])
    pump(root, lambda: app.state["active"] is not None and app.pending is None)
    accepted = app.state["active"]["start_utc_us"]
    assert accepted == NOW and clock.calls >= before + 1
    clock.value += timedelta(minutes=2, microseconds=123)
    box = app.tree.bbox(second)
    click(app.tree, (box[0] + 35, box[1] + box[3] // 2))
    click(app.buttons["Switch"])
    pump(root, lambda: app.state["active"]["task_id"] == second and app.pending is None)
    click(app.buttons["Mini mode"])
    pump(root, lambda: app.mini is not None and app._read_inflight is None)
    assert app.mini.name.cget("text") == "Same"
    assert "Today: 00:00" == app.mini.today.cget("text")
    assert app.state["report"]["tasks"][first]["today_us"] == 120_000_123
    clock.value += timedelta(minutes=1)
    click(app.mini.toggle)
    pump(root, lambda: app.state["active"] is None and app.pending is None)
    assert app.state["report"]["application"]["today_us"] == 180_000_123
    assert app.mini.today.cget("text") == "Today: 00:01"
    assert root.test_errors == []


def test_real_tk_slow_worker_accepted_instant_reentry_and_queued_shutdown(connected, root, monkeypatch):
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    gate, entered = threading.Event(), threading.Event()
    original = TimerService.execute
    def slow(self, request):
        if request.operation == "start_timer":
            entered.set()
            assert gate.wait(5)
        return original(self, request)
    monkeypatch.setattr(TimerService, "execute", slow)
    assert app.start()
    assert not app.start()
    request = app.pending
    clock.value += timedelta(hours=5)
    live = []
    root.after(30, lambda: live.append(True))
    pump(root, lambda: entered.is_set() and live)
    assert app.pending is request and app.executing
    app.request_close()
    assert app.closing and not app._shutdown_sent
    assert not app.exceptional_exit()
    gate.set()
    # Root destruction is the expected completion; drive with bounded mainloop.
    root.after(6000, root.quit)
    root.mainloop()
    assert not app.alive
    worker.join(timeout=5)
    store = SQLiteStore(worker.directory)
    try:
        active = TimerService(store).read_current_state(cutoff_utc_us=NOW + 1)["active"]
        assert active["start_utc_us"] == request.action_utc_us == NOW
        assert store.connection.execute("SELECT count(*) FROM work_revisions").fetchone()[0] == 0
    finally:
        store.close()


def test_real_tk_clock_warning_recovery_preserves_original_start(connected, root, click):
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    assert app.start()
    pump(root, lambda: app.state["active"] is not None)
    entry = app.state["active"]["entry_id"]
    clock.value -= timedelta(hours=1)
    app.refresh()
    pump(root, lambda: app.state.get("report") is None)
    assert "precedes" in app.error.cget("text")
    assert str(app.buttons["Stop"].cget("state")) == "normal"
    assert app.headline.cget("text") == "Today: —    This week: —"
    click(app.buttons["Correct active start"])
    pump(root, lambda: app.editor is not None)
    from tkinter import ttk
    entries = [w for w in app.editor.winfo_children() if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]
    entries[1].delete(0, "end")
    entries[1].insert(0, "08:00")
    button = next(w for w in app.editor.winfo_children() if isinstance(w, ttk.Button))
    click(button)
    pump(root, lambda: app.pending is None and app.state["active"]["version"] == 2 and app.state.get("report") is not None)
    assert app.state["active"]["entry_id"] == entry
    assert app.state["report"]["tasks"][task]["today_us"] == 3_600_000_000
    clock.value += timedelta(seconds=1)
    assert app.stop()
    pump(root, lambda: app.state["active"] is None)


def test_real_tk_unverified_exit_cancel_reconcile_same_identity(connected, root, monkeypatch):
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    original = TimerService.execute
    committed = []
    def lost(self, request):
        result = original(self, request)
        if request.operation == "start_timer" and not committed:
            committed.append(request)
            return Outcome("unverified", error=OSError("lost acknowledgement"))
        return result
    monkeypatch.setattr(TimerService, "execute", lost)
    assert app.start()
    pump(root, lambda: app.pending is not None and not app.executing)
    frozen = app.pending
    app.request_close()
    assert app.closing and frozen is committed[0]
    import chronicle.app as module
    decisions = []
    def cancel(*args, **kwargs):
        decisions.append(kwargs)
        assert not app.retry()  # Confirmation owns busy guard.
        return False
    monkeypatch.setattr(module.messagebox, "askyesno", cancel)
    assert not app.exceptional_exit()
    assert decisions[0]["default"] == "no"
    assert app.pending is frozen and app.alive
    app.cancel_close()
    assert app.retry()
    pump(root, lambda: app.pending is None and app.state["active"] is not None)
    assert app.state["active"]["entry_id"] == frozen.args()["entry_id"]
    assert "Saved" in app.status.cget("text")


def test_real_tk_unverified_confirmed_exit_does_not_stop_timer(connected, root, monkeypatch):
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    original = TimerService.execute
    def lost(self, request):
        result = original(self, request)
        return Outcome("unverified", error=OSError("lost")) if request.operation == "start_timer" else result
    monkeypatch.setattr(TimerService, "execute", lost)
    app.start()
    pump(root, lambda: app.pending is not None and not app.executing)
    entry = app.pending.args()["entry_id"]
    app.request_close()
    import chronicle.app as module
    monkeypatch.setattr(module.messagebox, "askyesno", lambda *args, **kwargs: True)
    assert app.exceptional_exit()
    root.after(6000, root.quit)
    root.mainloop()
    worker.join(timeout=5)
    store = SQLiteStore(worker.directory)
    try:
        assert store.connection.execute("SELECT entry_id FROM active_timer").fetchone()[0] == entry
    finally:
        store.close()


def test_stale_read_rejected_but_closed_origin_commit_handled():
    app = ChronicleApp.__new__(ChronicleApp)
    app._read_inflight, app._token, app.executing = 1, 2, False
    app._read_again = False
    called = []
    app.refresh = lambda: called.append("read")
    app._render = lambda value: called.append("render")
    app._handle(Message("read", 1, {}))
    assert called == ["read"]
    class Label:
        text = ""
        def configure(self, **kwargs):
            self.text = kwargs["text"]
        def cget(self, name):
            return self.text
    app.status = Label()
    app.pending = Request.make(uid(), uid(), "create_task", NOW, task_id=uid(), name="Detached", project_id=None)
    app.closing, app.editor = False, None
    app._work_editor = None
    app.history = None
    app.timesheet = None
    app._timesheet_opening = False
    app._timesheet_attempt = app._timesheet_handoff = None
    app._timesheet_dialog_busy = False
    app._pending_token = 2
    app.executing = True
    app._controls = lambda: None
    app.recheck_polr = lambda: None  # This double isolates owner completion, not reminder reads.
    app._handle(Message("mutate", 2, Outcome("committed", {"entry_id": "retained"})))
    assert app.pending is None and app.status.text == "Saved."


def test_old_mutation_completion_cannot_consume_new_pending_request():
    app = ChronicleApp.__new__(ChronicleApp)
    app.pending, app._pending_token, app.executing = object(), 9, True
    saved = app.pending
    app._handle(Message("mutate", 8, Outcome("committed", {"old": True})))
    assert app.pending is saved and app.executing


def test_destroyed_owner_direct_callbacks_do_not_touch_tk():
    app = ChronicleApp.__new__(ChronicleApp)
    app.alive = False
    assert app.selected_task_id() is None
    app._controls()
    assert app.exceptional_exit() is False


def test_real_tk_numeric_failure_after_commit_recovery_and_reader_purity(connected, root, monkeypatch):
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    import chronicle.app as module
    original = module.format_duration
    def fail(value):
        raise ValueError("numeric presentation fault")
    monkeypatch.setattr(module, "format_duration", fail)
    assert app.start()
    pump(root, lambda: app.pending is None and "numeric presentation fault" in app.error.cget("text"))
    assert app.state["active"] is not None
    assert "Saved" in app.status.cget("text")
    assert str(app.buttons["Stop"].cget("state")) == "normal"
    assert app.tree.item(task, "values")[-2:] == ("—", "—")
    monkeypatch.setattr(module, "format_duration", original)
    clock.value += timedelta(seconds=10)
    app.refresh()
    pump(root, lambda: app.state["report"] is not None)
    before = {p.name: p.read_bytes() for p in worker.directory.iterdir() if p.is_file()}
    for _ in range(3):
        app.refresh()
        pump(root, lambda: app._read_inflight is None)
    after = {p.name: p.read_bytes() for p in worker.directory.iterdir() if p.is_file()}
    assert before == after
    assert app.error.cget("text") == ""


def test_real_tk_ui_calls_are_on_creator_thread_and_empty_mini(connected, root, monkeypatch):
    app, worker, clock = connected
    identity = threading.get_ident()
    calls = []
    for widget, method in ((root, "after"), (app.tree, "item"), (app.headline, "configure")):
        original = getattr(widget, method)
        def observed(*args, _original=original, **kwargs):
            calls.append(threading.get_ident())
            assert threading.get_ident() == identity
            return _original(*args, **kwargs)
        monkeypatch.setattr(widget, method, observed)
    app.open_mini()
    pump(root, lambda: app._read_inflight is None)
    assert app.mini.today.cget("text") == "Today: 00:00"
    assert app.mini.name.cget("text") == "No task selected"
    task = create(app)
    app.tree.selection_set(task)
    app._selection_changed()
    assert app.mini.name.cget("text") == "Same"
    assert app.start()
    pump(root, lambda: app.pending is None and app.state["active"] is not None)
    assert calls and all(c == identity for c in calls)


def test_real_tk_startup_failure_can_close_without_waiting_for_dead_worker(root, tmp_path):
    worker = DatabaseWorker(tmp_path / "missing")
    app = ChronicleApp(root, worker)
    worker.start()
    pump(root, lambda: app._worker_stopped)
    assert not app.ready and "Unable to open dataset" in app.status.cget("text")
    app.request_close()
    assert not app.alive
    worker.join(timeout=5)
    assert not worker.is_alive()


def test_real_tk_root_launcher_source_smoke(root, tmp_path, monkeypatch):
    import chronicle.bootstrap as bootstrap
    import chronicle.app as module
    import runpy
    import sys
    root.destroy()
    directory = tmp_path / "source-launch"
    isolated_home = tmp_path / "isolated-home"
    old = isolated_home / ".task_timer_data"
    old.mkdir(parents=True)
    (old / "evidence").write_bytes(b"untouched old data")
    monkeypatch.setenv("HOME", str(isolated_home))
    from pathlib import Path
    original_iterdir = Path.iterdir
    def no_old_scan(path):
        assert path != old, "Replacement scanned the old default dataset"
        return original_iterdir(path)
    monkeypatch.setattr(Path, "iterdir", no_old_scan)
    seen, finished = [], []
    submitted = set()
    original = bootstrap.ChronicleApp
    class Driven(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            seen.append(self)
            def drive():
                if not self.alive:
                    return
                if self.state.get("report") is not None and "create" not in submitted and self.can_mutate():
                    submitted.add("create")
                    self.create_task()
                elif self.state["tasks"] and "start" not in submitted and self.can_mutate():
                    submitted.add("start")
                    self.tree.selection_set(self.state["tasks"][0]["task_id"])
                    self.start()
                elif self.state["active"] is not None and self.pending is None:
                    finished.append(True)
                    self.request_close()
                    return
                self.root.after(10, drive)
            self.root.after(10, drive)
            self.root.after(8000, self.root.destroy)
    monkeypatch.setattr(bootstrap, "ChronicleApp", Driven)
    monkeypatch.setattr(module.simpledialog, "askstring", lambda *args, **kwargs: "Source launch")
    monkeypatch.setattr(sys, "argv", ["run_chronicle.py", "--data-dir", str(directory), "--timezone", "UTC", "--create"])
    runpy.run_path("run_chronicle.py", run_name="__main__")
    app = seen[0]
    app.worker.join(timeout=5)
    assert finished and not app.alive and not app.worker.is_alive(), app.status.cget("text") if app.alive else "source driver timed out"
    assert (old / "evidence").read_bytes() == b"untouched old data"
    store = SQLiteStore(directory)
    try:
        assert store.connection.execute("SELECT count(*) FROM active_timer").fetchone()[0] == 1
    finally:
        store.close()


def test_real_tk_one_observation_handoff_and_minimum_size(connected, root):
    app, worker, clock = connected
    root.after_cancel(app._tick_id)
    app._tick_id = None
    before = clock.calls
    app.open_mini()
    pump(root, lambda: app._read_inflight is None)
    assert clock.calls == before + 1
    assert app.state["report"]["cutoff_utc_us"] == NOW
    root.geometry("720x420")
    pump(root, lambda: root.winfo_width() == 720)
    for button in app.buttons.values():
        assert button.winfo_x() >= 0
        assert button.winfo_x() + button.winfo_width() <= button.master.winfo_width()
    assert app.tree.column("today")["minwidth"] >= 80
    assert app.tree.column("week")["minwidth"] >= 80


def test_real_tk_correction_drafts_clear_occurrence_without_loading(connected, root):
    from tkinter import ttk
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    app.start()
    pump(root, lambda: app.pending is None and app.state["active"] is not None)
    app.correct_active_start()
    top = app.editor
    entries = [w for w in top.winfo_children() if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]
    day, clock_entry = entries[:2]
    selector = next(w for w in top.winfo_children() if isinstance(w, ttk.Combobox))
    day.delete(0, "end"); day.insert(0, "2026-11-01")
    clock_entry.delete(0, "end"); clock_entry.insert(0, "01:30")
    assert len(selector.cget("values")) == 2
    selector.current(0)
    clock_entry.delete(0, "end"); clock_entry.insert(0, "01:45")
    assert selector.get() == "" and len(selector.cget("values")) == 2
    selector.current(1)
    day.delete(0, "end"); day.insert(0, "invalid")
    assert selector.get() == "" and not selector.winfo_ismapped()
    assert app.pending is None
    app._close_editor(top)


def test_real_tk_correction_queue_acceptance_is_not_completion(connected, root, monkeypatch):
    from tkinter import ttk
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    assert app.start()
    pump(root, lambda: app.pending is None and app.state['active'] is not None)
    app.correct_active_start()
    top = app.editor
    entries = [w for w in top.winfo_children() if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]
    entries[1].delete(0, 'end')
    entries[1].insert(0, '09:00')
    gate, entered = threading.Event(), threading.Event()
    original = TimerService.execute
    def slow(self, request):
        if request.operation == 'correct_active_start':
            entered.set()
            assert gate.wait(5)
        return original(self, request)
    monkeypatch.setattr(TimerService, 'execute', slow)
    try:
        next(w for w in top.winfo_children() if isinstance(w, ttk.Button)).invoke()
        pump(root, entered.is_set)
        assert app.editor is top and top.winfo_exists(), 'Queue acceptance must retain the correction editor'
        assert app.executing and app.pending.operation == 'correct_active_start'
    finally:
        gate.set()
    pump(root, lambda: app.pending is None and app.editor is None)


def open_active_editor(connected, root):
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    assert app.start()
    pump(root, lambda: app.pending is None and app.state['active'] is not None and app._read_inflight is None)
    app.correct_active_start()
    session = app._work_editor
    pump(root, lambda: root.grab_current() is session.window)
    return session


def draft(session, day='2026-10-19', clock='09:00', comment='  reviewed draft  ', occurrence=None):
    for field, text in zip(session.fields, (day, clock, comment)):
        field.delete(0, 'end')
        field.insert(0, text)
    if occurrence is not None:
        session.selector.current(occurrence)
    return (*[field.get() for field in session.fields], session.selector.get())


def visible_draft(session):
    return (*[field.get() for field in session.fields], session.selector.get())


def evidence(worker):
    import sqlite3
    from pathlib import Path
    with sqlite3.connect(Path(worker.directory, 'chronicle.sqlite3').as_uri() + '?mode=ro', uri=True) as connection:
        return {table: connection.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()
                for table in ('work_entries', 'work_revisions', 'active_timer', 'active_start_corrections', 'committed_requests')}


@pytest.mark.parametrize('failure', ['clock', 'queue'])
def test_real_tk_correction_synchronous_submission_failure_retains_editable_draft(connected, root, monkeypatch, failure):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    values = draft(session)
    before = evidence(worker)
    if failure == 'clock':
        monkeypatch.setattr(app, 'now_utc', lambda: None)
    else:
        def fail(message):
            raise OSError('queue unavailable')
        monkeypatch.setattr(worker.requests, 'put', fail)
    session.save.invoke()
    assert app.editor is session.window and visible_draft(session) == values
    assert app.pending is None and not app.executing
    assert str(session.fields[0].cget('state')) == 'normal'
    assert session.status.cget('text') and root.test_errors
    assert evidence(worker) == before
    monkeypatch.undo()
    session.save.invoke()
    pump(root, lambda: app.editor is None and app.pending is None)


@pytest.mark.parametrize('day,clock_text,occurrence,error', [
    ('2026-03-08', '02:30', None, 'does not exist'),
    ('2026-10-19', '10:01', None, 'later than'),
    ('2026-10-19', '09:00:01', None, 'minute-only'),
    ('2026-11-01', '01:30', 1, 'later than'),
])
def test_real_tk_correction_worker_rejection_preserves_every_draft_then_recovers(connected, root, day, clock_text, occurrence, error):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    values = draft(session, day, clock_text, occurrence=occurrence)
    before = evidence(worker)
    reviewed = (session.entry_id, session.version)
    session.save.invoke()
    pump(root, lambda: app.pending is None and not app.executing)
    assert app.editor is session.window and visible_draft(session) == values
    assert error in session.status.cget('text')
    assert str(session.fields[0].cget('state')) == 'normal'
    assert (session.entry_id, session.version) == reviewed
    assert evidence(worker) == before
    draft(session)
    session.save.invoke()
    pump(root, lambda: app.editor is None and app.state['active']['version'] == 2)
    assert app.state['active']['entry_id'] == reviewed[0]
    rows = evidence(worker)
    assert len(rows['active_start_corrections']) == 1 and not rows['work_revisions']
    assert rows['work_entries'] == before['work_entries']
    assert rows['active_start_corrections'][0][-2] == 'reviewed draft'
    app.correct_active_start()
    assert app._work_editor is not session
    app._close_editor(app.editor)
    assert app._work_editor is None


def test_real_tk_worker_repeated_requirement_rejects_without_erasing_draft(connected, root, monkeypatch):
    import chronicle.app as module
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    original = module.local_minute_candidates
    # An incomplete presentation observation cannot bypass authoritative DST validation.
    monkeypatch.setattr(module, 'local_minute_candidates', lambda *args: original(*args)[:1])
    values = draft(session, '2026-11-01', '01:30')
    before = evidence(worker)
    session.save.invoke()
    pump(root, lambda: app.pending is None)
    assert 'first or second' in session.status.cget('text')
    assert visible_draft(session) == values and app.editor is session.window
    assert evidence(worker) == before


@pytest.mark.parametrize('fault', ['rolled_back', 'unavailable'])
def test_real_tk_correction_settled_storage_failure_allows_new_request(connected, root, monkeypatch, fault):
    from test_services import FaultConnection
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    values = draft(session)
    before = evidence(worker)
    original, submitted = TimerService.execute, []
    def fail_once(service, request):
        if request.operation == 'correct_active_start':
            submitted.append(request)
            if len(submitted) == 1:
                if fault == 'rolled_back':
                    service.store.connection = FaultConnection(service.store.connection)
                else:
                    recover = service.store._recover_connection
                    def unavailable():
                        service.store._recover_connection = recover
                        raise OSError('storage unavailable before execution')
                    service.store._recover_connection = unavailable
        return original(service, request)
    monkeypatch.setattr(TimerService, 'execute', fail_once)
    session.save.invoke()
    pump(root, lambda: app.pending is None and not app.executing)
    assert session.outcome.status == fault
    assert visible_draft(session) == values and str(session.save.cget('state')) == 'normal'
    assert evidence(worker) == before
    clock.value += timedelta(minutes=1)
    session.save.invoke()
    pump(root, lambda: app.editor is None and app.state['active']['version'] == 2)
    assert submitted[0].request_id != submitted[1].request_id
    assert submitted[1].action_utc_us > submitted[0].action_utc_us
    assert len(evidence(worker)['active_start_corrections']) == 1


def test_real_tk_stale_correction_keeps_reviewed_identity_and_draft(connected, root, monkeypatch):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    values = draft(session)
    original, attempted = TimerService.execute, []
    def changed(service, request):
        if request.operation == 'correct_active_start' and not attempted:
            attempted.append(request)
            assert service.correct_active_start(session.entry_id, '2026-10-19', '09:30', expected_version=1,
                                                request_id=uid(), action_utc_us=NOW).status == 'committed'
        return original(service, request)
    monkeypatch.setattr(TimerService, 'execute', changed)
    session.save.invoke()
    pump(root, lambda: app.pending is None and app._read_inflight is None)
    assert session.phase == 'stale' and 'Close and reopen' in session.status.cget('text')
    assert visible_draft(session) == values and session.version == 1
    assert str(session.save.cget('state')) == 'disabled'
    session.save.invoke()
    assert len(attempted) == 1 and len(evidence(worker)['active_start_corrections']) == 1
    app._close_editor(session.window)
    app.correct_active_start()
    assert app._work_editor.version == 2 and app._work_editor.entry_id == session.entry_id


@pytest.mark.parametrize('already_committed', [False, True])
def test_real_tk_correction_unverified_exact_editor_retry_and_duplicate_results(connected, root, monkeypatch, already_committed):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    values = draft(session)
    original, reconcile = TimerService.execute, TimerService.reconcile_request
    accepted, reconciled = [], []
    def uncertain(service, request):
        if request.operation == 'correct_active_start':
            accepted.append(request)
            if len(accepted) == 1:
                if already_committed:
                    assert original(service, request).status == 'committed'
                return Outcome('unverified', error=OSError('ambiguous correction acknowledgement'))
        return original(service, request)
    def still_uncertain(service, request):
        reconciled.append(request)
        if len(reconciled) == 1:
            return Outcome('unverified', error=OSError('independent inspection unavailable'))
        return reconcile(service, request)
    monkeypatch.setattr(TimerService, 'execute', uncertain)
    monkeypatch.setattr(TimerService, 'reconcile_request', still_uncertain)
    session.save.invoke()
    frozen, token = app.pending, app._pending_token
    pump(root, lambda: not app.executing)
    assert session.phase == 'unverified' and session.request is app.pending is frozen
    assert visible_draft(session) == values
    assert str(session.fields[0].cget('state')) == 'disabled'
    assert session.retry.winfo_manager() and session.exit.winfo_manager()
    assert not app._close_editor(session.window)
    session.save.invoke()
    assert len(accepted) == 1
    session.retry.invoke()
    assert app.executing and app.pending is frozen
    pump(root, lambda: not app.executing)
    assert session.phase == 'unverified' and 'inspection unavailable' in session.status.cget('text')
    assert visible_draft(session) == values and app.pending is frozen
    clock.value += timedelta(hours=1)
    session.retry.invoke()
    pump(root, lambda: app.editor is None and app.pending is None and app._read_inflight is None)
    assert all(request is frozen for request in accepted + reconciled)
    assert frozen.action_utc_us == NOW and frozen.args()['comment'] == values[2]
    rows = evidence(worker)
    assert len(rows['active_start_corrections']) == 1
    assert sum(row[1] == frozen.request_id for row in rows['committed_requests']) == 1
    app.correct_active_start()
    newer = app._work_editor
    new_draft = draft(newer, clock='08:00')
    app._handle(Message('reconcile', token, Outcome('committed')))
    assert app._work_editor is newer and visible_draft(newer) == new_draft
    # Even a matching owner token cannot settle a different session's request.
    app._work_editor_result(frozen, token, Outcome('committed'))
    assert app._work_editor is newer


def test_real_tk_unchanged_correction_preserves_microseconds_and_no_evidence(connected, root):
    app, worker, clock = connected
    clock.value += timedelta(microseconds=123456)
    session = open_active_editor(connected, root)
    before = evidence(worker)
    session.save.invoke()
    pump(root, lambda: app.editor is None and app.pending is None)
    assert app.status.cget('text') == 'Unchanged; nothing written.'
    assert evidence(worker) == before
    assert app.state['active']['start_utc_us'] == NOW + 123456


def test_real_tk_committed_correction_survives_report_and_cleanup_failure(connected, root, monkeypatch):
    import chronicle.app as module
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    draft(session)
    original = app._close_editor
    def cleanup(top):
        original(top)
        raise OSError('cleanup acknowledgement fault')
    monkeypatch.setattr(app, '_close_editor', cleanup)
    def no_numbers(value):
        raise ValueError('later report failure')
    monkeypatch.setattr(module, 'format_duration', no_numbers)
    session.save.invoke()
    pump(root, lambda: app.editor is None and app.pending is None and 'later report failure' in app.error.cget('text'))
    assert 'Saved' in app.status.cget('text')
    assert len(evidence(worker)['active_start_corrections']) == 1
    errors = [args[1] for args in root.test_errors]
    cleanup_error = next(exc for exc in errors if 'cleanup acknowledgement' in str(exc))
    assert any('remains committed' in note for note in cleanup_error.__notes__)
    assert app._work_editor is None


def test_real_tk_unexpected_editor_destruction_retains_owner_request(connected, root, monkeypatch):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    draft(session)
    original = TimerService.execute
    def lost(service, request):
        result = original(service, request)
        return Outcome('unverified', error=OSError('lost correction response'))
    monkeypatch.setattr(TimerService, 'execute', lost)
    session.save.invoke()
    frozen = app.pending
    session.window.destroy()
    assert app.editor is None and app._work_editor is None and app.pending is frozen
    pump(root, lambda: not app.executing)
    assert app.pending is frozen and app.retry_button.winfo_manager()
    assert app.retry()
    pump(root, lambda: app.pending is None)
    assert app.editor is None and len(evidence(worker)['active_start_corrections']) == 1


@pytest.mark.parametrize('confirm', [False, True])
def test_real_tk_correction_modal_exceptional_exit_is_reachable(connected, root, monkeypatch, confirm):
    import chronicle.app as module
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    values = draft(session)
    original = TimerService.execute
    def lost(service, request):
        result = original(service, request)
        return Outcome('unverified', error=OSError('lost correction response'))
    monkeypatch.setattr(TimerService, 'execute', lost)
    session.save.invoke()
    frozen = app.pending
    pump(root, lambda: not app.executing)
    asked = []
    def decide(*args, **kwargs):
        asked.append(kwargs)
        assert kwargs['parent'] is session.window and kwargs['default'] == 'no'
        assert not app.retry() and not app.exceptional_exit()
        app.request_close()  # Cannot stack another warning during confirmation.
        return confirm
    monkeypatch.setattr(module.messagebox, 'askyesno', decide)
    app.request_close()
    assert len(asked) == 1
    if confirm:
        root.after(6000, root.quit)
        root.mainloop()
        assert not app.alive
        worker.join(timeout=5)
        with _reopen_store(worker) as store:
            active = store.connection.execute('SELECT entry_id,version FROM active_timer').fetchone()
            assert tuple(active) == (session.entry_id, 2)
            assert store.connection.execute('SELECT count(*) FROM active_start_corrections').fetchone()[0] == 1
    else:
        assert app.pending is frozen and app.editor is session.window and not app.closing
        assert visible_draft(session) == values and root.grab_current() is session.window
        session.exit.invoke()
        assert len(asked) == 2 and app.pending is frozen
        session.retry.invoke()
        pump(root, lambda: app.editor is None and app.pending is None)


@contextmanager
def _reopen_store(worker):
    store = SQLiteStore(worker.directory)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def keyboard(root, click):
    """Server-delivered keyboard events; capability handling mirrors the pointer fixture."""
    import ctypes as c
    from ctypes.util import find_library
    x, xt = c.CDLL(find_library('X11')), c.CDLL(find_library('Xtst'))
    x.XOpenDisplay.argtypes, x.XOpenDisplay.restype = [c.c_char_p], c.c_void_p
    x.XCloseDisplay.argtypes = [c.c_void_p]
    x.XSync.argtypes = [c.c_void_p, c.c_int]
    x.XStringToKeysym.argtypes, x.XStringToKeysym.restype = [c.c_char_p], c.c_ulong
    x.XKeysymToKeycode.argtypes, x.XKeysymToKeycode.restype = [c.c_void_p, c.c_ulong], c.c_uint
    xt.XTestFakeKeyEvent.argtypes = [c.c_void_p, c.c_uint, c.c_int, c.c_ulong]
    display = x.XOpenDisplay(None)
    if not display:
        pytest.skip('XTest cannot open the isolated keyboard display')
    def press(name, control=False, shift=False):
        modifiers = [key for key, used in [('Control_L', control), ('Shift_L', shift)] if used]
        def send(key, down):
            code = x.XKeysymToKeycode(display, x.XStringToKeysym(key.encode()))
            assert code and xt.XTestFakeKeyEvent(display, code, down, 0)
        for key in modifiers:
            send(key, True)
        send(name, True)
        send(name, False)
        for key in reversed(modifiers):
            send(key, False)
        x.XSync(display, False)
    def replace(widget, text):
        click(widget)
        pump(root, lambda: root.focus_get() is widget)
        press('Home')
        press('End', shift=True)
        press('BackSpace')
        for char in text:
            press('semicolon' if char == ':' else 'minus' if char == '-' else 'space' if char == ' ' else char,
                  shift=char == ':')
        pump(root, lambda: widget.get() == text)
    yield press, replace
    x.XCloseDisplay(display)


def test_real_tk_server_input_rejection_recovery_and_modal_blocking(connected, root, click, keyboard):
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    click(app.buttons['Start'])
    pump(root, lambda: app.state['active'] is not None and app.pending is None)
    click(app.buttons['Mini mode'])
    mini = app.mini
    pump(root, lambda: mini is not None)
    click(app.buttons['Correct active start'])
    session = app._work_editor
    pump(root, lambda: root.grab_current() is session.window)
    press, replace = keyboard
    replace(session.fields[0], '2026-03-08')
    replace(session.fields[1], '02:30')
    replace(session.fields[2], 'operator draft')
    values, before = visible_draft(session), evidence(worker)
    click(session.save)
    pump(root, lambda: not app.executing and app.pending is None)
    assert 'does not exist' in session.status.cget('text')
    assert app.editor is session.window and visible_draft(session) == values
    assert evidence(worker) == before
    # Server input aimed at ancestors/mini must not reach them through the local grab.
    hits = []
    root.bind('<ButtonPress-1>', lambda event: hits.append('root'), add='+')
    mini.window.bind('<ButtonPress-1>', lambda event: hits.append('mini'), add='+')
    click(app.buttons['Stop'])
    click(mini.toggle)
    assert hits == [] and app.pending is None and app.state['active']['version'] == 1
    assert not app.stop() and not app.mini_toggle()  # Direct callbacks are guarded too.
    replace(session.fields[0], '2026-10-19')
    replace(session.fields[1], '09:00')
    click(session.save)
    pump(root, lambda: app.editor is None and app.state['active']['version'] == 2)
    assert len(evidence(worker)['active_start_corrections']) == 1
    click(app.buttons['Correct active start'])
    later = app._work_editor
    pump(root, lambda: root.grab_current() is later.window)
    before = evidence(worker)
    press('Escape')
    pump(root, lambda: app.editor is None)
    assert evidence(worker) == before


def test_real_tk_server_escape_wm_close_and_cancel_cannot_interrupt_correction(connected, root, click, keyboard, monkeypatch):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    values = draft(session)
    gate, entered, ticks = threading.Event(), threading.Event(), []
    original = TimerService.execute
    accepted = []
    def slow(service, request):
        if request.operation == 'correct_active_start':
            accepted.append(request)
            entered.set()
            assert gate.wait(5)
        return original(service, request)
    monkeypatch.setattr(TimerService, 'execute', slow)
    try:
        click(session.save)
        pump(root, entered.is_set)
        root.after(30, lambda: ticks.append(True))
        keyboard[0]('Escape')
        root.tk.call(session.window.protocol('WM_DELETE_WINDOW'))
        session.cancel.invoke()
        session.save.invoke()
        app.request_close()
        assert not app.exceptional_exit() and not app.stop()
        pump(root, lambda: ticks)
        assert len(accepted) == 1 and app.editor is session.window
        assert visible_draft(session) == values and root.grab_current() is session.window
        assert app.executing and not app.closing
        assert str(session.fields[0].cget('state')) == 'disabled'
    finally:
        gate.set()
    pump(root, lambda: app.editor is None and app.pending is None)


def test_real_tk_server_repeated_selection_retention_and_editor_reconcile(connected, root, click, keyboard, monkeypatch):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    press, replace = keyboard
    replace(session.fields[0], '2026-11-01')
    replace(session.fields[1], '01:30')
    click(session.selector)
    press('Down')
    press('Return')
    pump(root, lambda: session.selector.get() != '')
    choice = session.selector.get()
    click(session.save)  # Future relative to accepted observation; authoritative rejection.
    pump(root, lambda: app.pending is None and not app.executing)
    assert session.selector.get() == choice and 'later than' in session.status.cget('text')
    # Choosing an earlier unambiguous draft clears the occurrence only on the edit.
    replace(session.fields[0], '2026-10-19')
    replace(session.fields[1], '09:00')
    assert session.selector.get() == ''
    original = TimerService.execute
    def lost(service, request):
        result = original(service, request)
        return Outcome('unverified', error=OSError('lost committed acknowledgement'))
    monkeypatch.setattr(TimerService, 'execute', lost)
    click(session.save)
    pump(root, lambda: session.phase == 'unverified')
    frozen = app.pending
    click(session.retry)
    pump(root, lambda: app.editor is None and app.pending is None)
    assert len(evidence(worker)['active_start_corrections']) == 1
    assert frozen.args()['occurrence'] is None


def test_real_tk_native_default_cancel_exit_keeps_correction_and_exact_request(connected, root, click, keyboard, monkeypatch):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    draft(session)
    original = TimerService.execute
    def uncertain(service, request):
        result = original(service, request)
        return Outcome('unverified', error=OSError('lost correction acknowledgement'))
    monkeypatch.setattr(TimerService, 'execute', uncertain)
    click(session.save)
    pump(root, lambda: session.phase == 'unverified')
    frozen, shown = app.pending, []
    import time
    deadline = time.monotonic() + 4
    def respond():
        # Toolkit messageboxes are Tcl-owned windows, not Python widget objects.
        grab = str(root.tk.call('grab', 'current', root._w))
        focus = str(root.tk.call('focus'))
        if grab and grab != str(session.window) and focus.startswith(grab):
            shown.append(grab)
            keyboard[0]('Return')  # Native yes/no defaults to No, not affirmative exit.
        elif time.monotonic() < deadline:
            root.after(10, respond)
    def abort_dialog():
        grab = str(root.tk.call('grab', 'current', root._w))
        if grab and grab != str(session.window):
            root.tk.call('destroy', grab)
    # Independent timeout also bounds an unexpected error in the interaction driver.
    timeout = root.after(5000, abort_dialog)
    root.after(10, respond)
    click(session.exit)
    root.after_cancel(timeout)
    assert shown and app.alive and app.editor is session.window and app.pending is frozen
    assert not app.closing and not app.executing
    assert root.grab_current() is session.window
    click(session.retry)
    pump(root, lambda: app.editor is None and app.pending is None)


def test_real_tk_completed_editor_does_not_steal_competing_grab(connected, root, monkeypatch):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    draft(session)
    gate, entered = threading.Event(), threading.Event()
    original = TimerService.execute
    def slow(service, request):
        entered.set()
        assert gate.wait(5)
        return original(service, request)
    monkeypatch.setattr(TimerService, 'execute', slow)
    try:
        session.save.invoke()
        pump(root, entered.is_set)
        other = tk.Toplevel(root)
        pump(root, other.winfo_viewable)
        other.grab_set()
        other.focus_set()
        gate.set()
        pump(root, lambda: app.editor is None and app.pending is None)
        assert root.grab_current() is other and other.grab_status() == 'local'
    finally:
        gate.set()
        if 'other' in locals() and other.winfo_exists():
            other.destroy()


def test_real_tk_absent_uncertain_correction_can_settle_rejected_then_save_new(connected, root, monkeypatch):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    values = draft(session, clock='10:01')
    before = evidence(worker)
    original, requests = TimerService.execute, []
    def first_unknown(service, request):
        requests.append(request)
        if len(requests) == 1:
            return Outcome('unverified', error=OSError('execution not established'))
        return original(service, request)
    monkeypatch.setattr(TimerService, 'execute', first_unknown)
    session.save.invoke()
    frozen = app.pending
    pump(root, lambda: session.phase == 'unverified')
    session.retry.invoke()  # Genuine healthy absence; worker executes the original request.
    pump(root, lambda: app.pending is None and not app.executing)
    assert requests == [frozen, frozen] and session.outcome.status == 'rejected'
    assert session.phase == 'editing' and visible_draft(session) == values
    assert evidence(worker) == before
    draft(session)
    session.save.invoke()
    pump(root, lambda: app.editor is None)
    assert requests[-1].request_id != frozen.request_id
    assert len(evidence(worker)['active_start_corrections']) == 1


def test_real_tk_duplicate_delivery_cannot_unfreeze_executing_reconciliation(connected, root, monkeypatch):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    draft(session)
    original = TimerService.execute
    def lost(service, request):
        result = original(service, request)
        return Outcome('unverified', error=OSError('lost acknowledgement'))
    monkeypatch.setattr(TimerService, 'execute', lost)
    session.save.invoke()
    frozen, old_token = app.pending, app._pending_token
    pump(root, lambda: session.phase == 'unverified')
    gate, entered = threading.Event(), threading.Event()
    reconcile = TimerService.reconcile_request
    def slow(service, request):
        entered.set()
        assert gate.wait(5)
        return reconcile(service, request)
    monkeypatch.setattr(TimerService, 'reconcile_request', slow)
    try:
        session.retry.invoke()
        pump(root, entered.is_set)
        assert app._pending_token != old_token
        app._handle(Message('mutate', old_token, Outcome('unverified')))
        app._handle(Message('mutate', old_token, Outcome('committed')))
        assert app.executing and app.pending is session.request is frozen
        assert session.phase == 'executing' and app.editor is session.window
        assert not app.retry()
    finally:
        gate.set()
    pump(root, lambda: app.editor is None and app.pending is None)


def test_real_tk_reconcile_queue_failure_retains_frozen_request_and_controls(connected, root, monkeypatch):
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    draft(session)
    original = TimerService.execute
    def lost(service, request):
        result = original(service, request)
        return Outcome('unverified', error=OSError('lost acknowledgement'))
    monkeypatch.setattr(TimerService, 'execute', lost)
    session.save.invoke()
    frozen = app.pending
    pump(root, lambda: session.phase == 'unverified')
    def no_queue(message):
        raise OSError('reconciliation queue unavailable')
    with monkeypatch.context() as local:
        local.setattr(worker.requests, 'put', no_queue)
        session.retry.invoke()
    assert app.pending is session.request is frozen and not app.executing
    assert session.phase == 'unverified' and 'queue unavailable' in session.status.cget('text')
    session.retry.invoke()
    pump(root, lambda: app.editor is None and app.pending is None)


def test_real_tk_correction_verified_commit_keeps_original_warning(connected, root, monkeypatch):
    from test_services import FaultConnection
    app, worker, clock = connected
    session = open_active_editor(connected, root)
    draft(session)
    original = TimerService.execute
    def acknowledgement_fault(service, request):
        if request.operation == 'correct_active_start':
            service.store.connection = FaultConnection(service.store.connection, after=True)
        return original(service, request)
    monkeypatch.setattr(TimerService, 'execute', acknowledgement_fault)
    session.save.invoke()
    pump(root, lambda: app.editor is None and app.state['active']['version'] == 2)
    assert 'Saved.' in app.status.cget('text') and 'acknowledgement fault' in app.status.cget('text')
    warning = root.test_errors[-1][1]
    assert any('committed receipt verified' in note for note in warning.__notes__)
    assert len(evidence(worker)['active_start_corrections']) == 1


def test_real_tk_cleanup_failure_cannot_cancel_back_into_closed_worker(connected, root, monkeypatch, click):
    from test_bootstrap import child
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    app.start()
    pump(root, lambda: app.pending is None and app.state['active'] is not None)
    entry = app.state['active']['entry_id']
    original, calls = SQLiteStore.close, []
    def fail_once(store):
        calls.append(threading.get_ident())
        if len(calls) == 1:
            raise OSError('close still owns dataset')
        return original(store)
    monkeypatch.setattr(SQLiteStore, 'close', fail_once)
    app.request_close()
    pump(root, lambda: 'Worker cleanup failed' in app.status.cget('text'))
    assert app.alive and worker.is_alive() and app.closing
    assert child('from chronicle.sqlite_store import SQLiteStore; import sys; SQLiteStore(sys.argv[1])', worker.directory).returncode != 0
    app.cancel_close()
    assert app.closing, 'A cleanup-only worker cannot resume normal mutations'
    assert not app.stop() and app.pending is None
    click(app.retry_button, closes_root=True)
    worker.join(timeout=5)
    assert not app.alive and not worker.is_alive() and calls == [worker.ident, worker.ident]
    with _reopen_store(worker) as store:
        assert store.connection.execute('SELECT entry_id FROM active_timer').fetchone()[0] == entry


def test_real_tk_failed_startup_cleanup_retry_is_accessible(root, tmp_path, monkeypatch, click):
    import chronicle.worker as module
    original, calls = module.SQLiteStore, []
    class FailedStartup(original):
        def _profile(self):
            super()._profile()
            raise OSError('startup configuration failed')
        def close(self):
            calls.append(threading.get_ident())
            if len(calls) < 3:
                raise OSError('startup connection still owned')
            return super().close()
    monkeypatch.setattr(module, 'SQLiteStore', FailedStartup)
    worker = DatabaseWorker(tmp_path / 'partial', create=True, timezone='UTC')
    app = ChronicleApp(root, worker)
    worker.start()
    try:
        pump(root, lambda: app._cleanup_failed)
        assert app.alive and not app.ready and worker.is_alive()
        app._selection_changed()
        assert app.retry_button.winfo_manager() and not app.can_mutate()
        click(app.retry_button)
        pump(root, lambda: app._worker_stopped)
        assert not app._cleanup_failed and app.alive
        app.request_close()
        assert not app.alive
    finally:
        worker.requests.put(Message('shutdown'))
        worker.join(timeout=8)
        assert not worker.is_alive()
    assert calls == [worker.ident] * 3
    assert 'Initialization cleanup failed' in str(root.test_errors[0][1].__notes__)


def test_real_tk_forced_root_destruction_still_drains_accepted_io(connected, root, monkeypatch):
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    gate, entered = threading.Event(), threading.Event()
    original = TimerService.execute
    def slow(service, request):
        entered.set()
        assert gate.wait(5)
        return original(service, request)
    monkeypatch.setattr(TimerService, 'execute', slow)
    try:
        assert app.start()
        frozen = app.pending
        pump(root, entered.is_set)
        root.destroy()
        assert not app.alive and app.pending is frozen
    finally:
        gate.set()
    worker.join(timeout=8)  # Test verification only, not the application's Tk thread lifecycle.
    assert not worker.is_alive()
    with _reopen_store(worker) as store:
        service = TimerService(store)
        assert service.reconcile_request(frozen).status == 'committed'
        assert service.read_current_state(cutoff_utc_us=NOW)['active']['entry_id'] == frozen.args()['entry_id']
        assert store.connection.execute('SELECT count(*) FROM work_revisions').fetchone()[0] == 0


def test_real_tk_result_callback_failure_keeps_commit_and_drain_alive(connected, root, monkeypatch):
    app, worker, clock = connected
    task = create(app)
    app.tree.selection_set(task)
    original, failed = app._controls, []
    def fail_once():
        if app.pending is None and app.status.cget('text') == 'Saved.' and not failed:
            failed.append(True)
            raise ValueError('completion presentation callback failed')
        return original()
    monkeypatch.setattr(app, '_controls', fail_once)
    assert app.start()
    frozen = app.pending
    pump(root, lambda: app.state['active'] is not None and app.pending is None)
    assert failed and 'Saved.' in app.status.cget('text')
    assert any(str(args[1]) == 'completion presentation callback failed' for args in root.test_errors)
    assert app.state['active']['entry_id'] == frozen.args()['entry_id']
    assert app._drain_id is not None and app._tick_id is not None
    assert len(evidence(worker)['work_entries']) == 1


def test_real_tk_reports_effective_sqlite_profile(connected, root):
    app, worker, clock = connected
    assert app.runtime['journal_mode'] == 'delete'
    assert app.runtime['synchronous'] == 3 and app.runtime['foreign_keys'] == 1
    assert app.runtime['python'] and app.runtime['sqlite'] and app.runtime['source_id']
    status = app.status.cget('text')
    assert 'DELETE' in status and 'synchronous=3 (EXTRA)' in status and 'foreign_keys=1' in status
    assert not root.test_errors
