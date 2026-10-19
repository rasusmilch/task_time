from datetime import timedelta
from queue import Queue
import threading
import tkinter as tk

import pytest

from chronicle.app import ChronicleApp
from chronicle.records import Outcome
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import from_us
from chronicle.worker import DatabaseWorker, Message
from conftest import NOW, uid


def pump(root, predicate, timeout=8000):
    done, errors = [], []
    def check():
        try:
            if predicate():
                done.append(True)
                root.quit()
            else:
                root.after(5, check)
        except Exception as exc:
            errors.append(exc)
            root.quit()
    deadline = root.after(timeout, root.quit)
    root.after(0, check)
    root.mainloop()  # Bounded test driver; the runtime itself owns one ordinary mainloop.
    root.after_cancel(deadline)
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
    def perform(widget, xy=None):
        pump(root, lambda: widget.winfo_ismapped() and widget.winfo_width() > 1)
        xx, yy = xy or (widget.winfo_width() // 2, widget.winfo_height() // 2)
        assert xt.XTestFakeMotionEvent(display, -1, widget.winfo_rootx() + xx, widget.winfo_rooty() + yy, 0)
        assert xt.XTestFakeButtonEvent(display, 1, True, 0)
        assert xt.XTestFakeButtonEvent(display, 1, False, 0)
        x.XSync(display, False)
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
    app.pending, app.closing, app.editor = object(), False, None
    app._pending_token = 2
    app._controls = lambda: None
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
