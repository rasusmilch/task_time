"""Tk-thread application owner. Views submit values, never SQL or file I/O."""

from __future__ import annotations

from copy import deepcopy
from queue import Empty
import time
import traceback
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from uuid import uuid4

from .mini_mode import MiniModeWindow
from .records import ClockWarning, Outcome, Request
from .timekeeping import format_duration, from_us, local_minute_candidates, parse_date, to_us, utc_now
from .worker import Message


class ChronicleApp:
    def __init__(self, root, worker, *, now_utc=utc_now):
        self.root, self.worker, self.now_utc = root, worker, now_utc
        self.alive, self.ready, self.closing = True, False, False
        self.executing, self.pending = False, None
        self._pending_token = None
        self.state = {"tasks": [], "projects": [], "active": None, "report": None}
        self.dataset_id = self.timezone = None
        self.zone = None
        self.runtime = None
        self.mini = self.editor = None
        self._token, self._read_inflight, self._read_again = 0, None, False
        self._drain_id = self._tick_id = None
        self._shutdown_sent = False
        self._worker_stopped = False
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.request_close)
        root.bind("<Destroy>", self._destroyed, add="+")
        self._drain_id = root.after(20, self._drain)
        self._tick_id = root.after(1000, self._tick)

    def _build(self):
        self.root.title("Chronicle")
        self.root.geometry("850x550")
        self.root.minsize(720, 420)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        bar = ttk.Frame(self.root)
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.buttons = {}
        for column, (label, callback) in enumerate((
            ("Create task", self.create_task), ("Rename task", self.rename_task),
            ("Create project", self.create_project), ("Rename project", self.rename_project),
            ("Assign project", self.assign_project), ("Mini mode", self.open_mini))):
            button = ttk.Button(bar, text=label, command=callback)
            button.grid(row=0, column=column, padx=2)
            self.buttons[label] = button
        self.headline = ttk.Label(self.root, text="Today: —    This week: —")
        self.headline.grid(row=1, column=0, sticky="w", padx=10)
        holder = ttk.Frame(self.root)
        holder.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(holder, columns=("project", "today", "week"), selectmode="browse")
        self.tree.heading("#0", text="Task")
        self.tree.column("#0", width=230, minwidth=100)
        for name, label, width in (("project", "Project", 180), ("today", "Today", 100), ("week", "This week", 100)):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, minwidth=80)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda event: self._selection_changed())
        actions = ttk.Frame(self.root)
        actions.grid(row=3, column=0, sticky="ew", padx=8)
        for column, (label, callback) in enumerate((("Start", self.start), ("Stop", self.stop),
                                                   ("Switch", self.switch), ("Correct active start", self.correct_active_start))):
            button = ttk.Button(actions, text=label, command=callback)
            button.grid(row=0, column=column, padx=3, pady=6)
            self.buttons[label] = button
        self.active_label = ttk.Label(self.root, text="No active timer")
        self.active_label.grid(row=4, column=0, sticky="w", padx=10)
        self.error = ttk.Label(self.root, text="", wraplength=700)
        self.error.grid(row=5, column=0, sticky="w", padx=10)
        self.status = ttk.Label(self.root, text="Opening explicit dataset…", wraplength=700)
        self.status.grid(row=6, column=0, sticky="w", padx=10)
        self.recovery = ttk.Frame(self.root)
        self.recovery.grid(row=7, column=0, sticky="w", padx=8, pady=6)
        self.retry_button = ttk.Button(self.recovery, text="Retry/Reconcile", command=self.retry)
        self.exit_button = ttk.Button(self.recovery, text="Exit despite unresolved save", command=self.exceptional_exit)
        self.cancel_close_button = ttk.Button(self.recovery, text="Cancel exit", command=self.cancel_close)
        self._controls()

    def can_mutate(self):
        return self.alive and self.ready and not self.closing and self.pending is None and not self.executing

    def selected_task_id(self):
        if not self.alive:
            return None
        selected = self.tree.selection()
        return selected[0] if selected and any(t["task_id"] == selected[0] for t in self.state["tasks"]) else None

    def _selected(self):
        key = self.selected_task_id()
        return next((t for t in self.state["tasks"] if t["task_id"] == key and not t["is_deleted"]), None)

    def _diagnose(self, exc):
        if self.alive:
            self.root.report_callback_exception(type(exc), exc, exc.__traceback__)
        else:
            traceback.print_exception(exc)

    def _controls(self):
        if not self.alive:
            return
        task, active, enabled = self._selected(), self.state.get("active"), self.can_mutate()
        for name, button in self.buttons.items():
            allowed = enabled
            if name in ("Rename task", "Assign project"):
                allowed &= task is not None
            if name == "Start":
                allowed &= task is not None and active is None
            if name == "Stop" or name == "Correct active start":
                allowed &= active is not None
            if name == "Switch":
                allowed &= task is not None and active is not None and task["task_id"] != active["task_id"]
            button.configure(state="normal" if allowed else "disabled")
        if self.pending is not None and not self.executing:
            self.retry_button.pack(side="left", padx=3)
            if self.closing:
                self.exit_button.pack(side="left", padx=3)
                self.cancel_close_button.pack(side="left", padx=3)
        else:
            for widget in (self.retry_button, self.exit_button, self.cancel_close_button):
                widget.pack_forget()
        if self.mini is not None:
            self.mini.render()

    def _selection_changed(self):
        self._controls()

    def _submit(self, operation, **arguments):
        if not self.can_mutate():
            return False
        try:
            accepted = to_us(self.now_utc())  # Exactly one action observation, on the Tk thread.
            request = Request.make(str(uuid4()), self.dataset_id, operation, accepted, **arguments)
        except Exception as exc:
            self.status.configure(text=f"Action rejected: {exc}")
            self._diagnose(exc)
            return False
        self.pending, self.executing = request, True
        self._token += 1
        self._pending_token = self._token
        # Invalidate any read that predates this accepted mutation.
        self._read_again = True
        self.worker.requests.put(Message("mutate", self._token, request))
        self.status.configure(text="Saving…")
        self._controls()
        return True

    def start(self):
        task = self._selected()
        if task and self.state.get("active") is None:
            return self._submit("start_timer", task_id=task["task_id"], entry_id=str(uuid4()), expected_task_version=task["version"])
        return False

    def stop(self):
        active = self.state.get("active")
        return self._submit("stop_timer", entry_id=active["entry_id"], expected_version=active["version"]) if active else False

    def switch(self):
        task, active = self._selected(), self.state.get("active")
        if not task or not active:
            return False
        return self._submit("switch_timer", expected_active_entry_id=active["entry_id"],
                            expected_active_version=active["version"], next_task_id=task["task_id"],
                            next_entry_id=str(uuid4()), expected_task_version=task["version"])

    def _ask_name(self, title, initial=""):
        if not self.can_mutate():
            return None
        # Native/toolkit dialog waits are guarded; no application-authored nested loop.
        self.executing = True
        self._controls()
        try:
            return simpledialog.askstring(title, "Name", initialvalue=initial, parent=self.root)
        finally:
            self.executing = False
            self._controls()

    def create_task(self):
        name = self._ask_name("Create task")
        if name is not None:
            self._submit("create_task", task_id=str(uuid4()), name=name, project_id=None)

    def rename_task(self):
        task = self._selected()
        if task:
            name = self._ask_name("Rename task", task["name"])
            if name is not None:
                self._submit("rename_task", task_id=task["task_id"], name=name, expected_version=task["version"])

    def create_project(self):
        name = self._ask_name("Create project")
        if name is not None:
            self._submit("create_project", project_id=str(uuid4()), name=name)

    def _choice(self, title, labels, apply):
        if not self.can_mutate() or self.editor is not None:
            return
        top = tk.Toplevel(self.root)
        self.editor = top
        top.title(title)
        top.transient(self.root)
        combo = ttk.Combobox(top, values=labels, state="readonly", width=55)
        combo.pack(padx=12, pady=12)
        def commit():
            index = combo.current()
            if index >= 0:
                self._close_editor(top)
                apply(index)
        ttk.Button(top, text="Apply", command=commit).pack(pady=8)
        self._present_editor(top)

    def rename_project(self):
        projects = list(self.state["projects"])
        def chosen(index):
            project = projects[index]
            name = self._ask_name("Rename project", project["name"])
            if name is not None:
                self._submit("rename_project", project_id=project["project_id"], name=name, expected_version=project["version"])
        self._choice("Rename project", [f"{p['name']} ({p['project_id']})" for p in projects], chosen)

    def assign_project(self):
        task = self._selected()
        if not task:
            return
        projects = [None] + list(self.state["projects"])
        self._choice("Assign project", ["Unassigned"] + [f"{p['name']} ({p['project_id']})" for p in projects[1:]],
                     lambda index: self._submit("assign_task_to_project", task_id=task["task_id"],
                                                project_id=projects[index]["project_id"] if projects[index] else None,
                                                expected_version=task["version"]))

    def _present_editor(self, top):
        top.protocol("WM_DELETE_WINDOW", lambda: self._close_editor(top))
        top.bind("<Escape>", lambda event: self._close_editor(top))
        top.bind("<Destroy>", lambda event: self._editor_destroyed(event, top), add="+")
        def mapped(event):
            if event.widget is not top or self.editor is not top:
                return
            grab = self.root.grab_current()
            if grab is not None and grab is not top:
                self._close_editor(top)
                return
            top.grab_set()
            top.focus_set()
        top.bind("<Map>", mapped, add="+")

    def _editor_destroyed(self, event, top):
        if event.widget is top and self.editor is top:
            self.editor = None

    def _close_editor(self, top):
        if self.editor is top and top.winfo_exists():
            if self.root.grab_current() is top:
                top.grab_release()
            top.destroy()

    def correct_active_start(self):
        if not self.can_mutate() or self.editor is not None or not self.state.get("active"):
            return
        active = deepcopy(self.state["active"])
        zone = self.zone
        local = from_us(active["start_utc_us"]).astimezone(zone)
        top = tk.Toplevel(self.root)
        self.editor = top
        top.title("Correct active start")
        top.transient(self.root)
        fields = []
        for label, initial in (("Actual start date (YYYY-MM-DD)", local.date().isoformat()),
                               ("Actual start time", local.strftime("%H:%M")), ("Optional comment", "")):
            ttk.Label(top, text=label).pack(anchor="w", padx=12)
            entry = ttk.Entry(top, width=40)
            entry.insert(0, initial)
            entry.pack(padx=12, pady=4)
            fields.append(entry)
        day, clock, comment = fields
        selector = ttk.Combobox(top, state="readonly", width=45)
        choices = {}
        error = ttk.Label(top, text="", wraplength=380)
        error.pack(padx=12, pady=6)
        def changed(day_text=None, clock_text=None):
            selector.set("")
            choices.clear()
            selector.pack_forget()
            try:
                candidates = local_minute_candidates(parse_date(day.get() if day_text is None else day_text),
                                                     clock.get() if clock_text is None else clock_text, zone)
                if len(candidates) == 2:
                    for index, candidate in enumerate(candidates):
                        text = from_us(candidate).astimezone(zone).strftime("%H:%M (UTC%z)")
                        choices[("First " if index == 0 else "Second ") + text] = ("first", "second")[index]
                    selector.configure(values=list(choices))
                    selector.pack(padx=12, pady=4)
            except ValueError:
                pass  # Invalid drafts remain for correction; Save validates authoritatively.
        # Entry validation also observes mouse paste and programmatic draft changes.
        day.configure(validate="key", validatecommand=(top.register(lambda value: changed(day_text=value) or True), "%P"))
        clock.configure(validate="key", validatecommand=(top.register(lambda value: changed(clock_text=value) or True), "%P"))
        changed()
        def save():
            selected = choices.get(selector.get())
            if choices and selected is None:
                error.configure(text="Select the first or second occurrence.")
                return
            # Freeze the draft in the request; keep it open on synchronous validation errors.
            if self._submit("correct_active_start", entry_id=active["entry_id"], expected_version=active["version"],
                            date_text=day.get(), time_text=clock.get(), occurrence=selected, comment=comment.get()):
                self._close_editor(top)
        ttk.Button(top, text="Correct start", command=save).pack(pady=8)
        self._present_editor(top)

    def open_mini(self):
        if not self.alive or self.closing:
            return
        if self.mini is None:
            self.mini = MiniModeWindow(self)
        else:
            self.mini.window.deiconify()
        self.mini.render()
        self.refresh()

    def mini_toggle(self):
        return self.stop() if self.state.get("active") else self.start()

    def refresh(self, *, cutoff_utc_us=None):
        if not self.alive or not self.ready or self.closing:
            return
        if self._read_inflight is not None or self.executing:
            self._read_again = True
            return
        try:
            cutoff = to_us(self.now_utc()) if cutoff_utc_us is None else cutoff_utc_us
        except Exception as exc:
            self._unavailable(exc)
            return
        self._token += 1
        self._read_inflight = self._token
        self._read_again = False
        self.worker.requests.put(Message("read", self._token, cutoff))

    def _unavailable(self, exc):
        self.state["report"] = None
        for key in self.tree.get_children():
            values = list(self.tree.item(key, "values"))
            self.tree.item(key, values=(values[0], "—", "—"))
        self.headline.configure(text="Today: —    This week: —")
        self.error.configure(text="Time totals unavailable. " + str(exc))
        self._diagnose(exc)
        self._controls()

    def _render(self, candidate):
        report = candidate["report"]
        projects = {p["project_id"]: p["name"] for p in candidate["projects"]}
        prepared = []
        for task in candidate["tasks"]:
            if not task["is_deleted"]:
                amounts = report["tasks"][task["task_id"]] if report else None
                prepared.append((task["task_id"], task["name"], (projects.get(task["project_id"], "Unassigned"),
                                  format_duration(amounts["today_us"]) if amounts else "—",
                                  format_duration(amounts["week_us"]) if amounts else "—")))
        headline = "Today: —    This week: —" if not report else (
            f"Today: {format_duration(report['application']['today_us'])}    This week: {format_duration(report['application']['week_us'])}")
        active = candidate["active"]
        active_text = "No active timer"
        if active:
            name = next(t["name"] for t in candidate["tasks"] if t["task_id"] == active["task_id"])
            started = from_us(active["start_utc_us"]).astimezone(self.zone)
            active_text = f"Running: {name} — since {started.isoformat()}"
        selected = self.selected_task_id()
        self.state = deepcopy(candidate)
        valid = {row[0] for row in prepared}
        for old in self.tree.get_children():
            if old not in valid:
                self.tree.delete(old)
        for key, name, values in prepared:
            if self.tree.exists(key):
                self.tree.item(key, text=name, values=values)
            else:
                self.tree.insert("", "end", iid=key, text=name, values=values)
        if selected in valid:
            self.tree.selection_set(selected)
        self.headline.configure(text=headline)
        self.active_label.configure(text=active_text)
        self.error.configure(text="" if report else "Time totals unavailable. " + (candidate["calculation_error"] or ""))
        if report:
            stamp = from_us(report["cutoff_utc_us"]).astimezone(self.zone)
            self.headline.configure(text=headline + f"    as of {stamp:%H:%M:%S}")
        self._controls()

    def _handle(self, message):
        if message.kind == "ready":
            self.ready = True
            self.dataset_id, self.timezone = message.value["dataset_id"], message.value["timezone"]
            self.zone = message.value["zone"]
            self.runtime = message.value["runtime"]
            self.status.configure(text=f"SQLite {self.runtime['sqlite']} — WAL / FULL / foreign keys")
            self._controls()
            self.refresh()
        elif message.kind == "startup_failed":
            self.status.configure(text=f"Unable to open dataset: {message.value}")
            self._diagnose(message.value)
        elif message.kind in ("mutate", "reconcile"):
            if self.pending is None or message.token != self._pending_token:
                return  # A duplicate completion cannot consume a newer accepted request.
            result = message.value
            self.executing = False
            if result.status == "unverified":
                self.status.configure(text="Registration not verified; operation may have committed. Retry/Reconcile uses the same request.")
            else:
                self.pending = None
                self._pending_token = None
                self.status.configure(text={"committed": "Saved.", "unchanged": "Unchanged; nothing written.",
                                            "rejected": "Action rejected.", "rolled_back": "Operation rolled back.",
                                            "unavailable": "Database unavailable; operation did not begin."}.get(result.status, result.status))
            if result.error:
                self.status.configure(text=self.status.cget("text") + " " + str(result.error))
                self._diagnose(result.error)
            self._controls()
            if self.closing:
                self._advance_close()
            else:
                self.refresh()
        elif message.kind == "read":
            if message.token != self._read_inflight:
                return
            self._read_inflight = None
            if message.token < self._token or self.executing:
                self._read_again = True
            elif isinstance(message.value, Outcome):
                self._unavailable(message.value.error)
            elif message.value.get("dataset_id") != self.dataset_id:
                return  # No results from another dataset/session may replace this owner's view.
            else:
                try:
                    self._render(message.value)
                except Exception as exc:
                    # Preserve newly authoritative identities/active state even if numeric preparation fails.
                    self.state = deepcopy(message.value)
                    self._unavailable(exc)
            if self._read_again:
                self.refresh()
        elif message.kind == "shutdown_failed":
            self._shutdown_sent = False
            self.status.configure(text=f"Worker cleanup failed: {message.value}")
            self._diagnose(message.value)
            self.retry_button.pack(side="left", padx=3)
        elif message.kind == "stopped":
            self._worker_stopped = True
            self.ready = False
            if self.closing:
                self.root.destroy()
            else:
                self.status.configure(text=self.status.cget("text") + " Worker stopped.")

    def _drain(self):
        self._drain_id = None
        if not self.alive:
            return
        deadline = time.monotonic() + .008
        for _ in range(32):
            if time.monotonic() >= deadline:
                break
            try:
                message = self.worker.results.get_nowait()
            except Empty:
                break
            try:
                self._handle(message)
            except Exception as exc:
                self._diagnose(exc)
            if not self.alive:
                return
        self._drain_id = self.root.after(20, self._drain)

    def _tick(self):
        self._tick_id = None
        if not self.alive:
            return
        if not self.closing:
            try:
                cutoff = to_us(self.now_utc())
                active = self.state.get("active")
                if active:
                    elapsed = cutoff - active["start_utc_us"]
                    if elapsed < 0:
                        raise ClockWarning("Observation precedes active start. Correct active start or check the clock.")
                    name = next(t["name"] for t in self.state["tasks"] if t["task_id"] == active["task_id"])
                    self.active_label.configure(text=f"Running: {name} — elapsed {format_duration(elapsed)}")
                self.refresh(cutoff_utc_us=cutoff)
            except Exception as exc:
                self._unavailable(exc)
        self._tick_id = self.root.after(1000, self._tick)

    def retry(self):
        if self.alive and self.closing and not self.executing and self.pending is None and not self._shutdown_sent:
            self.retry_button.pack_forget()
            self._advance_close()
            return True
        if not self.alive or self.executing or self.pending is None:
            return False
        self.executing = True
        self.worker.requests.put(Message("reconcile", self._pending_token, self.pending))
        self.status.configure(text="Reconciling the exact saved request…")
        self._controls()
        return True

    def request_close(self):
        if not self.alive or self.editor is not None:
            return
        if self.closing:
            if not self.executing and self.pending is None and not self._shutdown_sent:
                self._advance_close()
            return
        if self.executing and self.pending is None:
            return  # A toolkit dialog currently owns this action.
        self.closing = True
        self._controls()
        self._advance_close()

    def _advance_close(self):
        if self.executing:
            self.status.configure(text="Waiting for the accepted database operation before exit…")
        elif self.pending is not None:
            self.status.configure(text="Save is unresolved and may have committed. Retry/Reconcile, or explicitly exit and lose volatile retry context.")
            self._controls()
        elif self._worker_stopped:
            self.root.destroy()
        elif not self._shutdown_sent:
            self._shutdown_sent = True
            self.worker.requests.put(Message("shutdown"))

    def cancel_close(self):
        if not self.executing and not self._shutdown_sent:
            self.closing = False
            self._controls()

    def exceptional_exit(self):
        if not self.alive or self.executing or not self.closing or self.pending is None:
            return False
        self.executing = True
        try:
            confirmed = messagebox.askyesno("Unresolved save", "The operation may already have committed. Exit loses this session's retry inputs. No work or evidence is undone. Exit anyway?",
                                           parent=self.root, default=messagebox.NO)
        finally:
            self.executing = False
        if confirmed:
            # No executing operation is interrupted. The worker still closes orderly.
            self.pending = None
            self._advance_close()
        else:
            self._controls()
        return confirmed

    def _destroyed(self, event):
        if event.widget is self.root and self.alive:
            self.alive = False
            for token in (self._drain_id, self._tick_id):
                if token is not None:
                    self.root.after_cancel(token)
            if not self._shutdown_sent:
                self._shutdown_sent = True
                self.worker.requests.put(Message("shutdown"))
