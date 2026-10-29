"""Tk-thread application owner. Views submit values, never SQL or file I/O."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from queue import Empty
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from uuid import uuid4

from .mini_mode import MiniModeWindow, configure_changed
from .records import ClockWarning, Outcome, Request, StaleState
from .timekeeping import format_duration, from_us, local_date, local_minute_candidates, parse_date, to_us, utc_now
from .worker import Message

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass
class _WorkEditor:
    """One temporary draft, correlated with the owner's existing pending request."""
    window: object
    entry_id: str
    version: int
    fields: tuple
    selector: object
    choices: dict
    status: object
    save: object
    cancel: object
    retry: object
    exit: object
    phase: str = "editing"
    request: Request | None = None
    token: int | None = None
    outcome: Outcome | None = None
    purpose: str = "correct_active_start"
    task_id: str | None = None
    extra_selectors: tuple = ()


@dataclass
class _TimesheetAttempt:
    """One detached operation, never a second receipt/file authority."""
    candidate: object
    destination: str | None
    request: Request | None = None  # Alias of the owner's frozen pending request.
    registration: str = "not attempted"
    token: int | None = None
    file_token: int | None = None
    file_kind: str | None = None
    file_destination: str | None = None
    inspection: object = None
    saved_path: str | None = None
    error: Exception | None = None
    started: bool = True


@dataclass
class _PolrSubmission:
    request: Request
    token: int
    origin: object
    outcome: Outcome | None = None


@dataclass
class _BackupOperation:
    request_id: str
    token: int
    destination: str
    dialog: object
    result: object = None
    busy: bool = True


class ChronicleApp:
    def __init__(self, root, worker, *, now_utc=utc_now):
        self.root, self.worker, self.now_utc = root, worker, now_utc
        self.alive, self.ready, self.closing = True, False, False
        self.executing, self.pending = False, None
        self._pending_token = None
        self._mutation_outcome = None
        self.state = {"tasks": [], "projects": [], "active": None, "report": None}
        self.dataset_id = self.timezone = None
        self.zone = None
        self.runtime = None
        self.mini = self.editor = None
        self._work_editor = None
        self.history = None
        self.timesheet = None
        self._timesheet_opening = False
        self._timesheet_return = None
        self._timesheet_attempt = None
        self._polr_submission = None
        self.reminder = self._reminder_error = None
        self._reminder_dismissed_date = None  # Observed metadata only; SQLite remains authoritative.
        self._reminder_token = 0
        self._reminder_inflight = self._reminder_cutoff = self._reminder_date = None
        self._reminder_again = False
        self._timesheet_handoff = None
        self._timesheet_dialog_busy = False
        self._history_opening = False
        self._history_return = None
        self._history_newest_first = True
        self._token, self._read_inflight, self._read_again = 0, None, False
        self._drain_id = self._tick_id = None
        self._shutdown_sent = False
        self._worker_stopped = False
        self._cleanup_failed = False
        self.backup_dialog = None
        self._backup_opening = False
        self._backup_return = None
        self._backup_operation = None
        self._active_group = None
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
            ("New Task", self.create_task), ("Rename task", self.rename_task),
            ("Create project", self.create_project), ("Rename project", self.rename_project),
            ("Assign project", self.assign_project), ("Mini mode", self.open_mini))):
            button = ttk.Button(bar, text=label, command=callback)
            button.grid(row=0, column=column, padx=2)
            self.buttons[label] = button
        ttk.Label(bar, text="Week starts").grid(row=1, column=0, sticky="e", pady=(6,0))
        self.week_selector = ttk.Combobox(bar, values=WEEKDAYS, state="disabled", width=12)
        self.week_selector.current(6)
        self.week_selector.grid(row=1, column=1, sticky="w", pady=(6,0))
        self.week_selector.bind("<<ComboboxSelected>>", self._week_changed)
        self.period = tk.StringVar(self.root, "Today")
        self.period_selector = ttk.Combobox(bar, values=("Today", "This Week"),
                                          textvariable=self.period, state="readonly", width=12)
        self.period_selector.grid(row=1, column=2, padx=4)
        self.period_selector.bind("<<ComboboxSelected>>", self._presentation_changed)
        self.sort_alpha = tk.BooleanVar(self.root, False)
        self.sort_control = ttk.Checkbutton(bar, text="Sort A-Z", variable=self.sort_alpha,
                                            command=self._presentation_changed)
        self.sort_control.grid(row=1, column=3)
        self.keep_mini_open = tk.BooleanVar(self.root, False)
        self.keep_mini_control = ttk.Checkbutton(bar, text="Keep Mini Open", variable=self.keep_mini_open)
        self.keep_mini_control.grid(row=1, column=4, columnspan=2)
        self.headline = ttk.Label(self.root, text="Today: —    This week: —")
        self.headline.grid(row=1, column=0, sticky="w", padx=10)
        holder = ttk.Frame(self.root)
        holder.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(holder, columns=("state", "individual", "cumulative"), selectmode="browse")
        self.tree.heading("#0", text="Task")
        self.tree.column("#0", width=230, minwidth=100)
        for name, label, width in (("state", "Status", 170), ("individual", "Individual", 110), ("cumulative", "Cumulative", 110)):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, minwidth=80)
        self.tree.tag_configure("running", foreground="#08752c")
        self.tree.tag_configure("stopped", foreground="#ad2525")
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
        for column, (label, callback) in enumerate((("Add timed work", self.add_timed_work),
                                                     ("Add date-only work", self.add_date_only_work),
                                                     ("Work History", self.open_history),
                                                     ("Timesheet / POL-R", self.open_timesheet))):
            button = ttk.Button(actions, text=label, command=callback)
            button.grid(row=1, column=column, padx=3, pady=4)
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
        self.reminder_banner = ttk.Frame(self.root)
        self.reminder_banner.grid(row=8,column=0,sticky='ew',padx=8,pady=3)
        self.reminder_label=ttk.Label(self.reminder_banner,text='',wraplength=680)
        self.reminder_label.grid(row=0,column=0,columnspan=2,sticky='w')
        self.reminder_open=ttk.Button(self.reminder_banner,text='Open Timesheet',command=self.open_reminder_timesheet)
        self.reminder_dismiss=ttk.Button(self.reminder_banner,text='Dismiss for today',command=self.dismiss_polr_today)
        self.reminder_open.grid(row=1,column=0,sticky='w');self.reminder_dismiss.grid(row=1,column=1,sticky='w')
        self.reminder_banner.grid_remove()
        self.buttons['Recheck POL-R']=ttk.Button(actions,text='Recheck POL-R',command=self.recheck_polr)
        self.buttons['Recheck POL-R'].grid(row=2,column=0,sticky='w',padx=3)
        self.buttons['Backup Chronicle'] = ttk.Button(actions, text='Backup Chronicle', command=self.open_backup)
        self.buttons['Backup Chronicle'].grid(row=2, column=1, sticky='w', padx=3)
        self._controls()

    def can_mutate(self, *, origin=None):
        owns_editor = (origin is not None and origin is self._work_editor
                       and self.editor is origin.window and origin.phase == "editing")
        owns_history = origin is not None and origin is self.history and origin.mutation_allowed()
        owns_timesheet = origin is not None and origin is self.timesheet and origin.mutation_allowed()
        return (self.alive and self.ready and not self.closing and self.pending is None
                and not self.executing and not self._cleanup_failed and (self.editor is None or owns_editor)
                and not self._history_opening and (self.history is None or owns_history)
                and not self._backup_opening and self.backup_dialog is None and not self._backup_busy()
                and not self._timesheet_opening and (self.timesheet is None or owns_timesheet))

    def _backup_busy(self):
        operation = self._backup_operation
        return operation is not None and operation.busy

    def open_backup(self):
        if self._backup_opening or self.backup_dialog is not None or not self.can_mutate():
            return False
        from .history_window import widget_live
        self._backup_opening = True
        dialog = None
        try:
            if not widget_live(self.root):
                raise ValueError('Backup origin is no longer live')
            grab = self.root.grab_current()
            if grab is not None and (grab is not self.root or grab.grab_status() != 'local'):
                raise ValueError('Backup cannot replace an unrelated or global grab')
            self._backup_return = (grab, self.root.focus_get())
            dialog = BackupDialog(self)
            self.backup_dialog = dialog  # Publish before Map/ordinary event delivery.
            self._controls()
            dialog.window.deiconify()
            return True
        except Exception as primary:
            if dialog is not None:
                try:
                    dialog.close(force=True)
                except Exception as secondary:
                    primary.add_note(f'Backup construction cleanup failed: {secondary!r}')
            self._backup_opening = False
            self._backup_return = None
            try:
                if self.alive and widget_live(self.status):
                    self.status.configure(text=f'Unable to open Backup Chronicle: {primary}')
                self._controls()
            except Exception as secondary:
                primary.add_note(f'Backup launch-error presentation also failed: {secondary!r}')
            self._diagnose(primary)
            return False

    def _backup_disposed(self, dialog):
        if self.backup_dialog is not dialog:
            return
        self.backup_dialog = None
        self._backup_opening = True
        context, self._backup_return = self._backup_return, None
        try:
            from .history_window import widget_live
            if context is not None and self.alive and not self.closing and widget_live(self.root):
                previous, focus = context
                current = self.root.grab_current()
                if current is None or (current is self.root and current.grab_status() == 'local'):
                    if previous is self.root and current is not previous:
                        previous.grab_set()
                    target = focus if widget_live(focus) and focus.winfo_toplevel() is self.root else self.root
                    target.focus_set()
        except Exception as exc:
            self._diagnose(exc)
        finally:
            self._backup_opening = False
            try:
                if self.alive and widget_live(self.tree):
                    self._controls()
            except Exception as exc:
                self._diagnose(exc)

    def _start_backup(self, dialog):
        if (self.backup_dialog is not dialog or dialog.disposed or dialog._dialog_busy or self._backup_busy()
                or not self.alive or not self.ready or self.closing or self.pending is not None or self.executing):
            return False
        try:
            # Path shape only on Tk; filesystem inspection belongs to the worker.
            from .timesheet_files import destination_path
            destination = str(destination_path(dialog.destination.get()))
            self._token += 1
            operation = _BackupOperation(str(uuid4()), self._token, destination, dialog)
            self._backup_operation = operation
            dialog.controls()
            dialog.status.configure(text='Creating and independently validating backup; please wait…')
            self.worker.requests.put(Message('backup', operation.token,
                                           {'request_id': operation.request_id, 'destination': destination}))
        except Exception as exc:
            if self._backup_operation is not None and self._backup_operation.dialog is dialog:
                self._backup_operation.busy = False
                self._backup_operation.result = Outcome('unavailable', error=exc)
            try:
                if not dialog.disposed:
                    dialog.status.configure(text=f'Backup did not complete: {exc}')
                    dialog.controls()
            except Exception as secondary:
                exc.add_note(f'Backup submission-error presentation also failed: {secondary!r}')
            self._diagnose(exc)
            return False
        return True

    def _backup_result(self, message):
        operation = self._backup_operation
        if (operation is None or not operation.busy or operation.token != message.token
                or message.value['request_id'] != operation.request_id):
            return
        # Owner records completion before optional UI effects, even after destruction.
        result = message.value['result']
        operation.result, operation.busy = result, False
        error = result.error
        verified = getattr(result, 'verified', False)
        from .backup_restore import BackupPhase
        cleanup_failed = getattr(result, 'phase', None) == BackupPhase.VERIFIED and error is not None
        text = (f'Backup verified.\n{operation.destination}\nDataset: {result.image.dataset_id}\n'
                'No work or timer state was changed.' if verified else
                f'Backup not verified. {getattr(result, "phase", "NOT_STARTED")}\n{error or "Choose another destination."}')
        if cleanup_failed:
            text = f'Backup file verified; temporary cleanup did not complete.\n{operation.destination}\n{error}'
        try:
            self.status.configure(text=('Backup verified.' if verified else
                                       'Backup cleanup did not complete; review details.' if cleanup_failed else
                                       'Backup not verified; review backup details and diagnostics.'))
            dialog = operation.dialog
            if self.backup_dialog is dialog and not dialog.disposed:
                dialog.status.configure(text=text)
                dialog.controls()
            self._controls()
        except Exception as exc:
            exc.add_note(f'Backup operation outcome was recorded; verified completion: {verified}.')
            if error:
                error.add_note(f'Backup presentation also failed: {exc!r}')
            else:
                self._diagnose(exc)
        if error:
            self._diagnose(error)

    @staticmethod
    def task_row(task_id):
        return "task:" + task_id

    @staticmethod
    def project_row(project_id):
        return "project:" + project_id if project_id is not None else "group:unassigned"

    def selected_task_id(self):
        if not self.alive:
            return None
        selected = self.tree.selection()
        if not selected or not selected[0].startswith("task:"):
            return None
        key = selected[0][5:]
        return key if any(t["task_id"] == key and not t["is_deleted"] for t in self.state["tasks"]) else None

    def _selected_project(self):
        if not self.alive:
            return None
        selected = self.tree.selection()
        return next((p for p in self.state["projects"]
                     if selected and self.project_row(p["project_id"]) == selected[0]), None)

    def _presentation_changed(self, event=None):
        if self.alive and self.ready:
            try:
                self._render(self.state)
            except Exception as exc:
                self._unavailable(exc)

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
            if name in ("Rename task", "Assign project", "Add timed work", "Add date-only work", "Work History"):
                allowed &= task is not None
            if name == "Start":
                allowed &= task is not None and active is None
            if name == "Stop" or name == "Correct active start":
                allowed &= active is not None
            if name == "Switch":
                allowed &= task is not None and active is not None and task["task_id"] != active["task_id"]
            if name == "Rename project":
                allowed &= bool(self.state["projects"])
            configure_changed(button, state="normal" if allowed else "disabled")
        configure_changed(self.week_selector, state="readonly" if enabled else "disabled")
        configure_changed(self.period_selector, state="readonly" if enabled else "disabled")
        for control in (self.sort_control, self.keep_mini_control):
            configure_changed(control, state="normal" if enabled else "disabled")
        if (self.pending is not None or self._cleanup_failed) and not self.executing:
            self.retry_button.configure(state="disabled" if self._worker_stopped else "normal")
            self.retry_button.pack(side="left", padx=3)
            if self.closing and self.pending is not None:
                self.exit_button.pack(side="left", padx=3)
                self.cancel_close_button.pack(side="left", padx=3)
            else:
                self.exit_button.pack_forget()
                self.cancel_close_button.pack_forget()
        else:
            for widget in (self.retry_button, self.exit_button, self.cancel_close_button):
                widget.pack_forget()
        if self.mini is not None:
            self.mini.render()
        self._render_reminder()

    def _selection_changed(self):
        self._controls()

    def _submit(self, operation, *, _origin=None, **arguments):
        if not self.can_mutate(origin=_origin):
            return False
        try:
            accepted = to_us(self.now_utc())  # Exactly one action observation, on the Tk thread.
            if operation=='dismiss_polr_reminder_today':arguments=dict(local_date=local_date(accepted,self.zone).isoformat())
            request = Request.make(str(uuid4()), self.dataset_id, operation, accepted, **arguments)
        except Exception as exc:
            self.status.configure(text=f"Action rejected: {exc}")
            self._diagnose(exc)
            return False
        self.pending, self.executing = request, True
        self._mutation_outcome = None
        self._token += 1
        self._pending_token = self._token
        if _origin is not None and _origin is self.history:
            # Correlate before queue/UI effects: accepted work outlives widgets.
            _origin.request, _origin.token, _origin.phase = request, self._pending_token, "executing"
        if _origin is not None and _origin is self.timesheet and operation == 'confirm_polr_absolute':
            self._polr_submission = _PolrSubmission(request,self._pending_token,_origin)
        if _origin is not None and _origin is self.timesheet and operation == 'register_timesheet_export':
            attempt = self._timesheet_attempt
            attempt.request, attempt.token, attempt.registration = request, self._pending_token, "registering"
        # Invalidate any read that predates this accepted mutation.
        self._read_again = True
        if self._reminder_inflight is not None:self._reminder_again=True
        try:
            self.worker.requests.put(Message("mutate", self._token, request))
        except Exception as exc:
            self.pending, self.executing, self._pending_token = None, False, None
            if _origin is not None and _origin is self.history:
                _origin.request, _origin.token, _origin.phase = None, None, "editing" if _origin.edit_fields else "browsing"
            if _origin is not None and _origin is self.timesheet and operation == 'confirm_polr_absolute':
                self._polr_result(request,self._token,Outcome('unavailable',error=exc))
            if _origin is not None and _origin is self.timesheet and operation == 'register_timesheet_export':
                attempt.registration, attempt.error = "unavailable", exc
            self.status.configure(text=f"Action not submitted: {exc}")
            self._diagnose(exc)
            self._controls()
            return False
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

    def _ask_name(self, title, initial="", *, prompt="Name"):
        if not self.can_mutate():
            return None
        # Native/toolkit dialog waits are guarded; no application-authored nested loop.
        self.executing = True
        self._controls()
        try:
            return simpledialog.askstring(title, prompt, initialvalue=initial, parent=self.root)
        finally:
            self.executing = False
            self._controls()

    def create_task(self):
        if not self.can_mutate():
            return False
        project = self._selected_project()
        task = self._selected()
        project_id = project["project_id"] if project else task["project_id"] if task else None
        project = next((p for p in self.state["projects"] if p["project_id"] == project_id), None)
        destination = f"{project['name']} ({project_id})" if project else "Unassigned"
        name = self._ask_name("New Task", prompt=f"Destination: {destination}\nName (flat task, not a subtask)")
        if name is not None:
            self._submit("create_task", task_id=str(uuid4()), name=name, project_id=project_id)

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
        if not self.can_mutate():
            return False
        projects = list(self.state["projects"])
        def rename(project):
            name = self._ask_name("Rename project", project["name"])
            if name is not None:
                self._submit("rename_project", project_id=project["project_id"], name=name, expected_version=project["version"])
        selected = self._selected_project()
        if selected:
            rename(selected)
        else:
            self._choice("Rename project", [f"{p['name']} ({p['project_id']})" for p in projects],
                         lambda index: rename(projects[index]))

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
        self._controls()

    def _editor_destroyed(self, event, top):
        if event.widget is top and self.editor is top:
            self.editor = None
            if self._work_editor is not None and self._work_editor.window is top:
                self._work_editor = None  # The owner's pending request survives unexpected destruction.
            self._controls()

    def _close_editor(self, top):
        session = self._work_editor
        if self.editor is top and session is not None and session.window is top:
            if session.request is not None:
                session.status.configure(text=("Still processing; please wait." if self.executing else
                                               "Save may have committed. Retry/Reconcile or explicitly exit."))
                return False
        return self._dispose_editor(top)

    def _dispose_editor(self, top):
        if self.editor is top and top.winfo_exists():
            if self.root.grab_current() is top:
                top.grab_release()
            top.destroy()
        return True

    def _work_editor_controls(self, session):
        if self._work_editor is not session or self.editor is not session.window:
            return
        editable = session.phase == "editing" and not self.closing
        for field in session.fields:
            field.configure(state="normal" if editable else "disabled")
        for selector in (session.selector, *session.extra_selectors):
            if selector is not None:
                selector.configure(state="readonly" if editable else "disabled")
        session.save.configure(state="normal" if editable else "disabled")
        session.cancel.configure(state="normal" if session.request is None else "disabled")
        for button in (session.retry, session.exit):
            if session.phase == "unverified":
                button.pack(pady=4)
            else:
                button.pack_forget()

    def _work_editor_result(self, request, token, result):
        session = self._work_editor
        if (session is None or self.editor is not session.window
                or session.request is not request or session.token != token):
            return
        session.outcome = result
        if result.status in ("committed", "unchanged"):
            session.request = None
            session.phase = "complete"
            self._work_editor_controls(session)
            self._close_editor(session.window)
            return
        if result.status == "unverified":
            session.phase = "unverified"
            text = "Correction may already have committed. Retry/Reconcile uses the exact request."
        else:
            session.request, session.token = None, None
            session.phase = ("stale" if session.purpose == "correct_active_start"
                             and isinstance(result.error, StaleState) else "editing")
            text = {
                "rejected": "Correction rejected.",
                "rolled_back": "This attempted change did not commit; you may edit and save again.",
                "unavailable": "Storage unavailable; operation did not begin. Try Save later.",
            }.get(result.status, result.status)
            if session.phase == "stale":
                text = "The reviewed active timer changed. Close and reopen for fresh review; this draft was retained."
        if session.purpose != "correct_active_start":
            text = text.replace("Correction", "Work entry").replace("correction", "work entry")
        if result.error:
            text += " " + str(result.error)
        session.status.configure(text=text)
        self._work_editor_controls(session)

    def _work_editor_retry(self, session):
        if (self._work_editor is not session or self.editor is not session.window
                or session.phase != "unverified" or self.pending is not session.request):
            return False
        return self.retry()

    def _work_editor_exit(self, session):
        if (self._work_editor is not session or self.editor is not session.window
                or session.phase != "unverified" or self.executing
                or self.pending is not session.request):
            return False
        was_closing = self.closing
        self.closing = True
        try:
            return self.exceptional_exit()
        finally:
            if not self._shutdown_sent:
                self.closing = was_closing
            self._controls()

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
            if self._work_editor is not session or not self.can_mutate(origin=session):
                return False
            selected = choices.get(selector.get())
            if choices and selected is None:
                error.configure(text="Select the first or second occurrence.")
                return False
            if not self._submit("correct_active_start", _origin=session,
                                entry_id=session.entry_id, expected_version=session.version,
                                date_text=day.get(), time_text=clock.get(), occurrence=selected, comment=comment.get()):
                error.configure(text=self.status.cget("text"))
                return False
            session.request, session.token = self.pending, self._pending_token
            session.phase = "executing"
            session.outcome = None
            error.configure(text="Saving; waiting for the database result…")
            self._work_editor_controls(session)
            return True
        save_button = ttk.Button(top, text="Correct start", command=save)
        save_button.pack(pady=8)
        cancel = ttk.Button(top, text="Cancel", command=lambda: self._close_editor(top))
        cancel.pack(pady=4)
        retry = ttk.Button(top, text="Retry/Reconcile", command=lambda: self._work_editor_retry(session))
        exit_button = ttk.Button(top, text="Exit despite unresolved save", command=lambda: self._work_editor_exit(session))
        session = _WorkEditor(top, active["entry_id"], active["version"], tuple(fields),
                                     selector, choices, error, save_button, cancel, retry, exit_button)
        self._work_editor = session
        self._present_editor(top)

    def _week_changed(self, event=None):
        if not self.can_mutate():
            return False
        return self._submit("set_week_start", week_start=self.week_selector.current(),
                            expected_week_start=self.state["week_start"])

    def recheck_polr(self, *, cutoff_utc_us=None):
        """Coalesce latest observation; ticks call only on a local-date transition."""
        if not self.alive or not self.ready or self.closing:return False
        try:
            cutoff=to_us(self.now_utc()) if cutoff_utc_us is None else cutoff_utc_us
            self._reminder_date=local_date(cutoff,self.zone).isoformat()
            self._reminder_cutoff=cutoff
            self._reminder_again=True
            return self._queue_reminder() is not False
        except Exception as exc:return self._reminder_failure(exc)

    def _queue_reminder(self):
        if (not self.alive or self.closing or not self._reminder_again
                or self._reminder_inflight is not None or self.executing or self.pending is not None):return
        self._reminder_token+=1
        token=self._reminder_token
        self._reminder_again=False
        try:self.worker.requests.put(Message('polr_reminder',token,self._reminder_cutoff))
        except Exception as exc:return self._reminder_failure(exc)
        self._reminder_inflight=token
        return True

    def _receive_reminder(self, message):
        if not self.alive or message.token!=self._reminder_inflight:return
        self._reminder_inflight=None
        if self.closing:
            self._reminder_again=True  # A cancelled exit must not retain an already-delivered read token.
            return
        if self._reminder_again or self.executing or self.pending is not None:
            self._reminder_again=True
            self._queue_reminder()
            return
        value=message.value
        if isinstance(value,Outcome):return self._reminder_failure(value.error or ValueError('Reminder evaluation unavailable'))
        if value['dataset_id']!=self.dataset_id or value['cutoff_utc_us']!=self._reminder_cutoff:return
        self._reminder_dismissed_date=value['dismissed_local_date']
        if value['evaluation_status']!='AVAILABLE':return self._reminder_failure(value.get('calculation_error') or ValueError('Authoritative reminder evaluation unavailable'))
        self.reminder=deepcopy(value)
        self._reminder_error=None
        self._render_reminder()

    def _reminder_failure(self, exc):
        self._reminder_error=exc
        try:
            self.status.configure(text=f'POL-R reminder evaluation unavailable: {exc}. Recheck POL-R to retry.')
            self._render_reminder()
        except Exception as secondary:exc.add_note(f'Reminder diagnostic presentation failed: {secondary!r}')
        self._diagnose(exc)
        return False

    def _render_reminder(self):
        if not self.alive:return
        value=self.reminder
        if self._reminder_dismissed_date is not None and self._reminder_dismissed_date==self._reminder_date:
            if self.reminder_banner.winfo_manager(): self.reminder_banner.grid_remove()
            return
        if self._reminder_error is not None:
            text='POL-R reminder evaluation unavailable. Recheck POL-R to retry.'
            if value and value['reminder_due']:text+=f" Previous trusted warning remains (as of {from_us(value['cutoff_utc_us']).isoformat()} UTC): "+self._reminder_context(value)
        elif value and value['reminder_due']:
            text='POL-R reconciliation needs review. '+self._reminder_context(value)
        else:
            if self.reminder_banner.winfo_manager(): self.reminder_banner.grid_remove()
            return
        configure_changed(self.reminder_label, text=text)
        if not self.reminder_banner.winfo_manager(): self.reminder_banner.grid()
        enabled=self.can_mutate()
        configure_changed(self.reminder_open, state='normal' if enabled else 'disabled')
        configure_changed(self.reminder_dismiss, state='normal' if enabled else 'disabled')

    @staticmethod
    def _reminder_context(value):
        lines=[f"Previous week: {value['previous_week_outstanding_counts']['outstanding']} unresolved task/day cells"]
        if value['current_week_checked']:lines.append(f"Current week: {value['current_week_outstanding_counts']['outstanding']} unresolved task/day cells")
        return '; '.join(lines)

    def dismiss_polr_today(self):
        # The accepted action instant also supplies its date; no second clock capture.
        return self._submit('dismiss_polr_reminder_today')

    def open_reminder_timesheet(self):
        # Canonical ownership handles active, reentrant and stale references.
        value=self.reminder
        period='Last week' if value is None or value['previous_week_outstanding_counts']['outstanding'] else 'This week'
        if not self.open_timesheet():return False
        self.timesheet._reminder_period=period
        return True

    def open_timesheet(self):
        # Duplicate/reentrant requests do not inspect drafts, clocks or task arguments.
        if self._timesheet_opening:
            return False
        if self.timesheet is not None:
            from .timesheet_window import widget_live
            if not self.timesheet.disposed and widget_live(self.timesheet.window):
                return False
            self._timesheet_disposed(self.timesheet)
        if not self.can_mutate():
            return False
        self._timesheet_detach()
        from .timesheet_window import TimesheetWindow, widget_live
        self._timesheet_opening = True
        sheet = None
        try:
            if not widget_live(self.root):
                raise ValueError("Timesheet origin is no longer live")
            grab = self.root.grab_current()
            if grab is not None and (grab is not self.root or grab.grab_status() != "local"):
                raise ValueError("Timesheet cannot replace an unrelated or global grab")
            focus = self.root.focus_get()
            self._timesheet_return = (self.root, grab, focus)
            sheet = TimesheetWindow(self)
            self.timesheet = sheet  # Publish before any presentation event can run.
            self._controls()
            sheet.present()
            return True
        except Exception as primary:
            self._timesheet_launch_failed(sheet, primary)
            return False

    def _timesheet_presented(self, sheet):
        if self.timesheet is sheet:
            self._timesheet_opening = False
            self._controls()

    def _restore_timesheet_origin(self):
        from .timesheet_window import widget_live
        context, self._timesheet_return = self._timesheet_return, None
        if context is None or self.closing:
            return
        parent, grab, focus = context
        if not widget_live(self.root) or not widget_live(parent):
            return
        current = parent.grab_current()
        if current is not None and (current is not parent or current.grab_status() != "local"):
            return
        if grab is parent and current is not parent:
            parent.grab_set()
        target = focus if (widget_live(focus) and focus.winfo_toplevel() is parent) else parent
        target.focus_set()

    def _timesheet_disposed(self, sheet, primary=None):
        if self.timesheet is not sheet:
            return
        previous_guard = self._timesheet_opening
        self._timesheet_opening = True
        self.timesheet = None
        polr=getattr(self,'_polr_submission',None)
        if polr is not None and polr.origin is sheet and polr.request is not self.pending:self._polr_submission=None
        self._timesheet_detach()
        try:
            self._restore_timesheet_origin()
        except Exception as exc:
            if primary is not None:
                primary.add_note(f"Timesheet origin return failed: {exc!r}")
            else:
                self._diagnose(exc)
        finally:
            self._timesheet_opening = previous_guard
            from .timesheet_window import widget_live
            try:
                if self.alive and widget_live(self.tree):
                    self._controls()
            except Exception as exc:
                if primary is not None:
                    primary.add_note(f"Timesheet disposal controls failed: {exc!r}")
                else:
                    self._diagnose(exc)

    def _timesheet_launch_failed(self, sheet, primary):
        self._timesheet_opening = True
        try:
            if sheet is not None:
                try:
                    sheet.close(primary=primary)
                except Exception as secondary:
                    primary.add_note(f"Timesheet launch cleanup failed: {secondary!r}")
            if self.timesheet is None or self.timesheet is sheet:
                try:
                    self._restore_timesheet_origin()
                except Exception as secondary:
                    primary.add_note(f"Timesheet origin return failed: {secondary!r}")
            if self.alive:
                try:
                    self.status.configure(text=f"Unable to open Timesheet: {primary}")
                except Exception as secondary:
                    primary.add_note(f"Timesheet launch error presentation failed: {secondary!r}")
        finally:
            self._timesheet_opening = False
            try:
                if self.alive:
                    self._controls()
            except Exception as secondary:
                primary.add_note(f"Timesheet launch controls failed: {secondary!r}")
            self._diagnose(primary)

    def _timesheet_read(self, sheet, kind, value):
        if self.timesheet is not sheet or sheet.disposed or not self.alive or self.closing:
            raise ValueError("Timesheet session is no longer current")
        if kind not in ("timesheet_tasks", "timesheet_preview", "timesheet_exports", "timesheet_export", "polr_proposal", "polr_manual", "polr_history", "polr_batch", "polr_day", "polr_reconciliation"):
            raise ValueError("Unsupported Timesheet view read")
        self._token += 1
        if kind == "polr_reconciliation":
            value={**value,"cutoff_utc_us":to_us(self.now_utc())}
        if kind == "timesheet_preview":
            value = dict(value,export_id=str(uuid4()),cutoff_utc_us=to_us(self.now_utc()))
        self.worker.requests.put(Message(kind,self._token,value))
        return self._token,value

    def _polr_submit(self, sheet, arguments):
        if self.timesheet is not sheet or not sheet.polr_ready or not self.can_mutate(origin=sheet): return False
        submitted=self._submit('confirm_polr_absolute',_origin=sheet,**arguments)
        if not submitted and not self.executing:sheet.polr_status.configure(text=self.status.cget('text'))
        sheet.controls()
        return submitted

    def _polr_result(self, request, token, result):
        submission=self._polr_submission
        if submission is None or submission.request is not request or submission.token!=token:return
        submission.outcome=result  # Known commitment precedes all widget effects.
        if result.status=='committed' and not self.closing:self.recheck_polr()
        try:self.status.configure(text=f"Confirmation {result.status}: {result.result.get('batch_id','')}")
        except Exception as exc:
            exc.add_note('Authoritative confirmation outcome is already retained.')
            self._diagnose(exc)
        if result.error:self._diagnose(result.error)
        if self.timesheet is submission.origin and not submission.origin.disposed:
            try:submission.origin.polr_result(result)
            except Exception as exc:
                exc.add_note('Confirmation outcome remains retained independently of its presentation.')
                try:submission.origin.controls()
                except Exception as secondary:exc.add_note(f'Confirmation controls also failed: {secondary!r}')
                self._diagnose(exc)
        elif result.status!='unverified':self._polr_submission=None
        self._controls()
        if not self.closing:
            self.refresh()
            if result.status=='committed':
                if self.timesheet is not None:self.timesheet.reconciliation_committed()
            else:self._queue_reminder()

    def _timesheet_detach(self):
        attempt = self._timesheet_attempt
        if attempt is None or self.executing or self.pending is not None:
            return
        if attempt.registration == "committed" and attempt.started and attempt.saved_path is None:
            self._timesheet_handoff = (attempt.candidate.export_id, attempt.destination)
        elif attempt.saved_path is not None:
            self._timesheet_handoff = None
        self._timesheet_attempt = None

    def _timesheet_notify(self):
        sheet = self.timesheet
        if sheet is not None and not sheet.disposed:
            try: sheet.save_changed()
            except Exception as exc:
                exc.add_note("Registration/file outcome is retained independently of presentation.")
                self._diagnose(exc)

    def _timesheet_recover(self, candidate):
        if self.executing or self.pending is not None: return False
        from .timesheet import validate
        validate(candidate,check_render=False)
        if candidate.dataset_id != self.dataset_id: raise ValueError('Recovered report belongs to another dataset')
        destination = candidate.preferred_destination
        if self._timesheet_handoff is not None and self._timesheet_handoff[0] == candidate.export_id:
            destination = self._timesheet_handoff[1]
        self._timesheet_attempt = _TimesheetAttempt(candidate,destination,registration='committed',started=False)
        return True

    def _timesheet_begin_save(self, sheet, candidate, destination):
        if self.timesheet is not sheet or not self.can_mutate(origin=sheet):
            return False
        self._timesheet_attempt = _TimesheetAttempt(candidate,destination)
        submitted = self._submit('register_timesheet_export',_origin=sheet,candidate=candidate.content())
        if not submitted and self._timesheet_attempt.request is None:
            self._timesheet_attempt = None
        self._timesheet_notify()
        return submitted

    def _timesheet_registration_result(self, request, token, result):
        attempt = self._timesheet_attempt
        if attempt is None or attempt.request is not request or attempt.token != token:
            return
        attempt.registration, attempt.error = result.status, result.error
        if result.status == 'committed':
            if result.result != {'export_id':attempt.candidate.export_id,'report_sha256':attempt.candidate.report_sha256}:
                attempt.registration = 'unverified'
                self.pending, self._pending_token = request, token
                attempt.error = ValueError('Registration result did not verify the expected export identity/digest')
            else:
                self._timesheet_file('timesheet_publish')
        if result.error: self._diagnose(result.error)
        if attempt.error is not None and attempt.error is not result.error: self._diagnose(attempt.error)
        self._timesheet_notify()
        if self.timesheet is None: self._timesheet_detach()
        self._controls()
        if not self.closing: self.refresh()

    def _timesheet_retry_registration(self):
        attempt = self._timesheet_attempt
        if attempt is None or attempt.request is None or self.executing:
            return False
        if self.pending is not None and self.pending is not attempt.request:
            return False
        self.pending = attempt.request
        return self.retry()

    def _timesheet_file(self, kind, *, destination=None, confirmed_overwrite=False, expected_conflict=None):
        attempt = self._timesheet_attempt
        if (attempt is None or attempt.registration != 'committed' or self.executing
                or self.pending is not None or self.closing or not self.alive):
            return False
        if destination is not None: attempt.destination = destination
        if kind == 'timesheet_publish': attempt.started = True
        attempt.inspection, attempt.error = None, None  # Stale conflict cannot authorize another call.
        self._token += 1
        attempt.file_token, attempt.file_kind = self._token, kind
        attempt.file_destination = attempt.destination
        self.executing = True
        args = dict(export_id=attempt.candidate.export_id,destination=attempt.destination)
        if kind == 'timesheet_publish':
            args.update(confirmed_overwrite=confirmed_overwrite,expected_conflict=expected_conflict)
        try:
            self.worker.requests.put(Message(kind,self._token,args))
        except Exception as exc:
            attempt.file_token, self.executing, attempt.error = None, False, exc
            self._diagnose(exc)
            self._timesheet_notify()
            return False
        self._timesheet_notify()
        self._controls()
        return True

    def _timesheet_file_result(self, message):
        from .timesheet_files import Inspection, Publication
        attempt = self._timesheet_attempt
        if (attempt is None or attempt.file_token != message.token or attempt.file_kind != message.kind
                or not self.executing): return
        value = message.value
        if not isinstance(value,Outcome) and (value.get('export_id') != attempt.candidate.export_id
                or value.get('destination') != attempt.file_destination):
            self._diagnose(ValueError('File result identity/destination disagrees with this attempt'))
            return  # An unrelated reply cannot consume the accepted operation.
        attempt.file_token, self.executing = None, False
        if isinstance(value,Outcome):
            attempt.error = value.error or OSError('File operation unavailable')
        else:
            result = value['result']
            if message.kind == 'timesheet_publish' and type(result) is Publication:
                attempt.inspection, attempt.error = result.inspection, result.error
                if result.export_id != attempt.candidate.export_id:
                    attempt.error = ValueError('Publication returned another export identity')
                elif result.verified:
                    attempt.saved_path = result.destination  # Known completion precedes any widget effect.
                    self._timesheet_handoff = None
            elif message.kind == 'timesheet_status' and type(result) is Inspection:
                attempt.inspection, attempt.error = result, result.error
            else:
                attempt.error = ValueError('Invalid file operation result')
        if attempt.error: self._diagnose(attempt.error)
        self._timesheet_notify()
        if self.timesheet is None: self._timesheet_detach()
        self._controls()
        if not self.closing: self.refresh()

    def _timesheet_exit(self):
        if self.executing or self._timesheet_dialog_busy: return False
        previous = self.closing
        self.closing = True
        try: return self.exceptional_exit()
        finally:
            if not self._shutdown_sent: self.closing = previous
            self._controls()

    def _timesheet_exit_warning(self):
        """Registered evidence survives; only the current volatile path context is lost."""
        if self._timesheet_dialog_busy or self.executing: return False
        attempt = self._timesheet_attempt
        handoff = ((attempt.candidate.export_id,attempt.destination) if attempt is not None
                   and attempt.registration == 'committed' and attempt.started and attempt.saved_path is None else self._timesheet_handoff)
        if handoff is None: return True
        sheet = self.timesheet
        parent = sheet.window if sheet is not None and not sheet.disposed else self.root
        self._timesheet_dialog_busy = True
        self.executing = True
        try:
            decision = messagebox.askyesno('Unfinished Timesheet file save',
                f'File Save is unfinished for registered report {handoff[0]}. Exit loses the current session path/status context. '
                'The report remains in Saved Reports; evidence and any files are not undone. Exit anyway?',parent=parent,default=messagebox.NO)
        except BaseException as primary:
            if sheet is not None and not sheet.disposed:
                try: sheet.restore_modal()
                except Exception as secondary: primary.add_note(f'Timesheet modal return failed: {secondary!r}')
            raise
        else:
            if not decision and sheet is not None and not sheet.disposed: sheet.restore_modal()
            return decision
        finally:
            self.executing = False
            self._timesheet_dialog_busy = False

    def open_history(self):
        # Duplicate/reentrant requests do not inspect drafts, clocks or task arguments.
        if self._history_opening:
            return False
        if self.history is not None:
            from .history_window import widget_live
            if not self.history.disposed and widget_live(self.history.window):
                return False
            self._history_disposed(self.history)
        if not self.can_mutate() or self._selected() is None:
            return False
        from .history_window import HistoryWindow, widget_live
        self._history_opening = True
        history = None
        try:
            if not widget_live(self.root):
                raise ValueError("History origin is no longer live")
            grab = self.root.grab_current()
            if grab is not None and (grab is not self.root or grab.grab_status() != "local"):
                raise ValueError("History cannot replace an unrelated or global grab")
            focus = self.root.focus_get()
            self._history_return = (self.root, grab, focus)
            history = HistoryWindow(self, self._selected())
            self.history = history  # Publish before any presentation event can run.
            self._controls()
            history.present()
            return True
        except Exception as primary:
            self._history_launch_failed(history, primary)
            return False

    def _history_presented(self, history):
        if self.history is history:
            self._history_opening = False
            self._controls()

    def _remember_history_direction(self, newest_first):
        self._history_newest_first = newest_first

    def _restore_history_origin(self):
        from .history_window import widget_live
        context, self._history_return = self._history_return, None
        if context is None or self.closing:
            return
        parent, grab, focus = context
        if not widget_live(self.root) or not widget_live(parent):
            return
        current = parent.grab_current()
        if current is not None and (current is not parent or current.grab_status() != "local"):
            return
        if grab is parent and current is not parent:
            parent.grab_set()
        target = focus if (widget_live(focus) and focus.winfo_toplevel() is parent) else parent
        target.focus_set()

    def _history_disposed(self, history, primary=None):
        if self.history is not history:
            return
        previous_guard = self._history_opening
        self._history_opening = True
        self.history = None
        try:
            self._restore_history_origin()
        except Exception as exc:
            if primary is not None:
                primary.add_note(f"History origin return failed: {exc!r}")
            else:
                self._diagnose(exc)
        finally:
            self._history_opening = previous_guard
            from .history_window import widget_live
            try:
                if self.alive and widget_live(self.tree):
                    self._controls()
            except Exception as exc:
                if primary is not None:
                    primary.add_note(f"History disposal controls failed: {exc!r}")
                else:
                    self._diagnose(exc)

    def _history_launch_failed(self, history, primary):
        self._history_opening = True
        try:
            if history is not None:
                try:
                    history.close(force=True, primary=primary)
                except Exception as secondary:
                    primary.add_note(f"History launch cleanup failed: {secondary!r}")
            if self.history is None or self.history is history:
                try:
                    self._restore_history_origin()
                except Exception as secondary:
                    primary.add_note(f"History origin return failed: {secondary!r}")
            if self.alive:
                try:
                    self.status.configure(text=f"Unable to open Work History: {primary}")
                except Exception as secondary:
                    primary.add_note(f"History launch error presentation failed: {secondary!r}")
        finally:
            self._history_opening = False
            try:
                if self.alive:
                    self._controls()
            except Exception as secondary:
                primary.add_note(f"History launch controls failed: {secondary!r}")
            self._diagnose(primary)

    def _history_read(self, history, kind, value):
        if self.history is not history or history.disposed or not self.alive or self.closing:
            raise ValueError("History session is no longer current")
        self._token += 1
        if kind == "history_snapshot":
            value = dict(value, task_id=history.task["task_id"], cutoff_utc_us=to_us(self.now_utc()))
        self.worker.requests.put(Message(kind, self._token, value))
        return self._token

    def _history_submit(self, history, operation, arguments):
        row = history.reviewed
        if (self.history is not history or row is None or row["task_id"] != history.task["task_id"]
                or row["is_running"] or row["revision"] is None
                or arguments.get("entry_id") != row["entry_id"]
                or arguments.get("task_id") != row["task_id"]
                or arguments.get("expected_revision") != row["revision"]
                or operation not in ("edit_closed_timed_work", "edit_date_only_work", "delete_work_entry")
                or (operation == "edit_closed_timed_work" and row["kind"] != "timed")
                or (operation == "edit_date_only_work" and row["kind"] != "date_only")):
            return False
        return self._submit(operation, _origin=history, **arguments)

    def add_timed_work(self):
        return self._open_manual_work("add_timed_work")

    def add_date_only_work(self):
        return self._open_manual_work("add_date_only_work")

    def _open_manual_work(self, operation):
        task = self._selected()
        if task is None or not self.can_mutate():
            return False
        top = None
        try:
            # Initialization is an observation for drafts, never a saved work endpoint.
            initial_date = local_date(to_us(self.now_utc()), self.zone).isoformat()
            top = tk.Toplevel(self.root)
            self.editor = top
            top.title("Add timed work" if operation == "add_timed_work" else "Add date-only work")
            top.transient(self.root)
            ttk.Label(top, text=f"Task: {task['name']}\n{task['task_id']}").pack(padx=12, pady=8)
            fields, selectors, mappings = [], [], []

            def field(label, initial=""):
                ttk.Label(top, text=label).pack(anchor="w", padx=12)
                entry = ttk.Entry(top, width=42)
                entry.insert(0, initial)
                entry.pack(padx=12, pady=3)
                fields.append(entry)
                return entry

            def endpoint(label):
                day = field(label + " date (YYYY-MM-DD)", initial_date)
                clock = field(label + " time (minute precision)")
                selector = ttk.Combobox(top, state="readonly", width=42)
                choices = {}
                selectors.append(selector)
                mappings.append(choices)
                def changed(day_text=None, clock_text=None):
                    selector.set("")
                    choices.clear()
                    selector.pack_forget()
                    try:
                        candidates = local_minute_candidates(parse_date(day.get() if day_text is None else day_text),
                                                             clock.get() if clock_text is None else clock_text, self.zone)
                        if len(candidates) == 2:
                            for i, candidate in enumerate(candidates):
                                text = from_us(candidate).astimezone(self.zone).strftime("%H:%M (UTC%z)")
                                choices[("First " if i == 0 else "Second ") + text] = ("first", "second")[i]
                            selector.configure(values=list(choices))
                            selector.pack(padx=12, pady=3)
                    except ValueError:
                        pass  # Preserve invalid drafts; the worker validates Save.
                day.configure(validate="key", validatecommand=(top.register(lambda value: changed(day_text=value) or True), "%P"))
                clock.configure(validate="key", validatecommand=(top.register(lambda value: changed(clock_text=value) or True), "%P"))
                return day, clock

            if operation == "add_timed_work":
                start_day, start_clock = endpoint("Start")
                end_day, end_clock = endpoint("End")
            else:
                day = field("Work date (YYYY-MM-DD)", initial_date)
                duration = field("Duration (H:MM)")
            comment = field("Optional comment")
            status = ttk.Label(top, text="", wraplength=430)
            status.pack(padx=12, pady=6)
            def save():
                if self._work_editor is not session or not self.can_mutate(origin=session):
                    return False
                occurrences = [mapping.get(selector.get()) for mapping, selector in zip(mappings, selectors)]
                if any(mapping and value is None for mapping, value in zip(mappings, occurrences)):
                    status.configure(text="Select the first or second occurrence for each repeated minute.")
                    return False
                args = dict(task_id=session.task_id, entry_id=session.entry_id, comment=comment.get())
                if operation == "add_timed_work":
                    args.update(start_date=start_day.get(), start_time=start_clock.get(), end_date=end_day.get(),
                                end_time=end_clock.get(), start_occurrence=occurrences[0], end_occurrence=occurrences[1])
                else:
                    args.update(work_date=day.get(), duration_text=duration.get())
                if not self._submit(operation, _origin=session, **args):
                    status.configure(text=self.status.cget("text"))
                    return False
                session.request, session.token = self.pending, self._pending_token
                session.phase, session.outcome = "executing", None
                status.configure(text="Saving; waiting for the database result…")
                self._work_editor_controls(session)
                return True
            save_button = ttk.Button(top, text="Save", command=save)
            save_button.pack(pady=5)
            cancel = ttk.Button(top, text="Cancel", command=lambda: self._close_editor(top))
            cancel.pack(pady=4)
            retry = ttk.Button(top, text="Retry/Reconcile", command=lambda: self._work_editor_retry(session))
            exit_button = ttk.Button(top, text="Exit despite unresolved save", command=lambda: self._work_editor_exit(session))
            session = _WorkEditor(top, str(uuid4()), 0, tuple(fields), selectors[0] if selectors else None,
                                  mappings[0] if mappings else {}, status, save_button, cancel, retry, exit_button,
                                  purpose=operation, task_id=task["task_id"], extra_selectors=tuple(selectors[1:]))
            self._work_editor = session
            self._present_editor(top)
            return True
        except Exception as primary:
            if top is not None:
                try:
                    self._dispose_editor(top)
                    if self.editor is top:
                        self.editor = self._work_editor = None
                        self._controls()
                except Exception as secondary:
                    primary.add_note(f"Manual form construction cleanup failed: {secondary!r}")
            if self.alive:
                self.status.configure(text=f"Unable to open manual work: {primary}")
            self._diagnose(primary)
            return False

    def can_present_mini(self):
        return self.can_mutate() and self.root.grab_current() is None

    def open_mini(self):
        if not self.can_present_mini():
            return False
        if self.mini is None:
            self.mini = MiniModeWindow(self)
        else:
            self.mini.window.deiconify()
        self.mini.render()
        self.refresh()
        return True

    def show_main(self):
        if not self.can_present_mini():
            return False
        self.root.deiconify()
        self.root.lift()
        if self.mini is not None and not self.keep_mini_open.get():
            self.mini.window.destroy()
        return True

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
        self.state["calculation_error"] = str(exc)
        # Do not repeat a failing numeric formatter/row preparation to clear output.
        active = self.state.get("active")
        active_id = active["task_id"] if active else None
        task = next((t for t in self.state["tasks"] if t["task_id"] == active_id), None)
        for group in self.tree.get_children():
            for key in (group, *self.tree.get_children(group)):
                values = tuple(self.tree.item(key, "values"))
                tags = ()
                if key.startswith("task:"):
                    running = key == self.task_row(active_id) if active else False
                    status, tags = ("▶ Running", ("running",)) if running else ("■ Stopped", ("stopped",))
                else:
                    running = task is not None and group == self.project_row(task["project_id"])
                    status = "Group — ▶ Running task" if running else "Group"
                updates = {}
                if values != (status, "—", "—"):
                    updates["values"] = (status, "—", "—")
                if tuple(self.tree.item(key, "tags")) != tags:
                    updates["tags"] = tags
                if updates:
                    self.tree.item(key, **updates)
        configure_changed(self.active_label, text=f"▶ Running: {task['name']}" if task else "■ Stopped — no active timer")
        configure_changed(self.headline, text="Today: —    This week: —")
        configure_changed(self.error, text="Time totals unavailable. " + str(exc))
        self._controls()
        self._diagnose(exc)

    def _render(self, candidate):
        report = candidate["report"]
        field = "today_us" if self.period.get() == "Today" else "week_us"
        projects = {p["project_id"]: p["name"] for p in candidate["projects"]}
        groups = list(projects) + [None]
        if self.sort_alpha.get():
            groups.sort(key=lambda key: (projects.get(key, "Unassigned").casefold(), key or ""))
        active = candidate["active"]
        active_id = active["task_id"] if active else None
        active_group = next((t["project_id"] for t in candidate["tasks"] if t["task_id"] == active_id), None)
        rows, children = {}, {}
        for group in groups:
            key = self.project_row(group)
            members = [t for t in candidate["tasks"] if t["project_id"] == group]
            total = sum(report["tasks"][t["task_id"]][field] for t in members) if report else None
            running = active is not None and active_group == group
            rows[key] = ("", projects.get(group, "Unassigned"),
                         ("Group — ▶ Running task" if running else "Group", "—",
                          format_duration(total) if total is not None else "—"), ())
            children[key] = []
            visible = [t for t in members if not t["is_deleted"]]
            if self.sort_alpha.get():
                visible.sort(key=lambda t: (t["name"].casefold(), t["task_id"]))
            for task in visible:
                row = self.task_row(task["task_id"])
                amount = report["tasks"][task["task_id"]][field] if report else None
                value = format_duration(amount) if amount is not None else "—"
                running = task["task_id"] == active_id
                rows[row] = (key, task["name"], ("▶ Running" if running else "■ Stopped", value, value),
                             ("running" if running else "stopped",))
                children[key].append(row)
        selected, scroll = self.tree.selection(), self.tree.yview()
        previous_week = self.state.get("week_start")
        self.state = deepcopy(candidate)
        if candidate["week_start"] != previous_week:
            self.week_selector.current(candidate["week_start"])
        # Reparent surviving tasks before removing obsolete groups.
        for key, (parent, name, values, tags) in rows.items():
            if not self.tree.exists(key):
                self.tree.insert(parent, "end", iid=key, text=name, values=values, tags=tags, open=not parent)
            else:
                if self.tree.parent(key) != parent:
                    self.tree.move(key, parent, "end")
                old = self.tree.item(key)
                updates = {k: v for k, v in (("text", name), ("values", values), ("tags", tags))
                           if (tuple(old[k]) if k in ("values", "tags") else old[k]) != v}
                if updates:
                    self.tree.item(key, **updates)
        for group in self.tree.get_children():
            for child in self.tree.get_children(group):
                if child not in rows:
                    self.tree.delete(child)
            if group not in rows:
                self.tree.delete(group)
        for parent, ordered in [("", [self.project_row(g) for g in groups]), *children.items()]:
            if tuple(self.tree.get_children(parent)) != tuple(ordered):
                for index, key in enumerate(ordered):
                    self.tree.move(key, parent, index)
        # Expand only on active identity/group transitions, allowing ordinary collapse.
        marker = (active_id, active_group) if active else None
        if marker != self._active_group and active and self.tree.exists(self.project_row(active_group)):
            self.tree.item(self.project_row(active_group), open=True)
        self._active_group = marker
        surviving = tuple(key for key in selected if key in rows)
        if self.tree.selection() != surviving:
            self.tree.selection_set(surviving)
        if scroll and self.tree.yview() != scroll:
            self.tree.yview_moveto(scroll[0])
        headline = "Today: —    This week: —" if not report else (
            f"Today: {format_duration(report['application']['today_us'])}    This week: {format_duration(report['application']['week_us'])}")
        task = next((t for t in candidate["tasks"] if t["task_id"] == active_id), None)
        configure_changed(self.headline, text=headline)
        configure_changed(self.active_label, text=f"▶ Running: {task['name']}" if task else "■ Stopped — no active timer")
        configure_changed(self.error, text="" if report else "Time totals unavailable. " + (candidate.get("calculation_error") or ""))
        self._controls()

    def _handle(self, message):
        if message.kind == 'backup':
            self._backup_result(message)
        elif message.kind == "ready":
            self.ready = True
            self.dataset_id, self.timezone = message.value["dataset_id"], message.value["timezone"]
            self.zone = message.value["zone"]
            self.runtime = message.value["runtime"]
            self.state["week_start"] = message.value["week_start"]
            self.week_selector.current(self.state["week_start"])
            self.status.configure(text=(f"SQLite {self.runtime['sqlite']} — "
                                        f"{self.runtime['journal_mode'].upper()} / "
                                        f"synchronous={self.runtime['synchronous']} (EXTRA) / "
                                        f"foreign_keys={self.runtime['foreign_keys']}"))
            self._controls()
            self.refresh()
            self.recheck_polr()
        elif message.kind == "startup_failed":
            self.status.configure(text=f"Unable to open dataset: {message.value}")
            self._diagnose(message.value)
        elif message.kind in ("mutate", "reconcile"):
            if (self.pending is None or message.token != self._pending_token or not self.executing
                    or message.request != self.pending):
                return  # A duplicate completion cannot consume a newer accepted request.
            result = message.value
            request = self.pending
            self.executing = False
            self._mutation_outcome = result  # Authoritative matching delivery precedes all presentation.
            polr = getattr(self,'_polr_submission',None)
            if polr is not None and polr.request is request and request.operation == 'confirm_polr_absolute':
                if result.status != 'unverified': self.pending, self._pending_token = None, None
                self._polr_result(request,message.token,result)
                return
            attempt = self._timesheet_attempt
            if attempt is not None and attempt.request is request and request.operation == 'register_timesheet_export':
                if result.status != 'unverified': self.pending, self._pending_token = None, None
                self._timesheet_registration_result(request,message.token,result)
                return
            if result.status != 'unverified':
                self.pending, self._pending_token = None, None
            if result.error:
                self._diagnose(result.error)
            try:
                if result.status == "unverified":
                    self.status.configure(text="Registration not verified; operation may have committed. Retry/Reconcile uses the same request.")
                else:
                    if result.status in ('committed','unchanged') and request.operation!='register_timesheet_export' and not self.closing:
                        self.recheck_polr()  # Authoritative completion schedules reads before optional presentation.
                    self.status.configure(text={"committed": "Saved.", "unchanged": "Unchanged; nothing written.",
                                                "rejected": "Action rejected.", "rolled_back": "Operation rolled back.",
                                                "unavailable": "Database unavailable; operation did not begin."}.get(result.status, result.status))
                if request.operation == "set_week_start" and result.status not in ("committed", "unchanged", "unverified"):
                    self.week_selector.current(self.state["week_start"])
                if result.error:
                    self.status.configure(text=self.status.cget("text") + " " + str(result.error))
            except Exception as exc:
                exc.add_note(f'Authoritative mutation outcome remains {result.status}; status presentation failed.')
                self._diagnose(exc)
            try:
                self._work_editor_result(request, message.token, result)
                if self.history is not None:
                    self.history.mutation_result(request, message.token, result)
            except Exception as exc:
                exc.add_note(f"Authoritative work outcome remains {result.status}; presentation/cleanup failed.")
                self._diagnose(exc)
            try:
                self._controls()
            finally:
                if self.closing:
                    self._advance_close()
                else:
                    self.refresh()
                    if result.status in ('committed','unchanged') and request.operation!='register_timesheet_export':
                        if self.timesheet is not None:self.timesheet.reconciliation_committed()
                    else:self._queue_reminder()
        elif message.kind == 'polr_reminder':
            self._receive_reminder(message)
        elif message.kind in ("timesheet_status", "timesheet_publish"):
            self._timesheet_file_result(message)
        elif message.kind in ("timesheet_tasks", "timesheet_preview", "timesheet_exports", "timesheet_export", "polr_proposal", "polr_manual", "polr_history", "polr_batch", "polr_day", "polr_reconciliation"):
            sheet = self.timesheet
            if sheet is not None and not sheet.disposed:
                if message.kind == "timesheet_tasks":
                    sheet.receive_choices(message.token,message.value)
                elif message.kind == 'timesheet_preview':
                    sheet.receive_preview(message.token,message.value)
                elif message.kind=='polr_reconciliation':
                    sheet.receive_reconciliation(message.token,message.value)
                elif message.kind.startswith('polr_'):
                    sheet.receive_polr(message.kind,message.token,message.value)
                else:
                    sheet.receive_saved(message.kind,message.token,message.value)
        elif message.kind in ("history_snapshot", "revisions"):
            history = self.history
            if history is not None and not history.disposed:
                if message.kind == "history_snapshot":
                    history.receive_snapshot(message.token, message.value)
                else:
                    history.receive_details(message.token, message.value)
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
            self._cleanup_failed = True
            self.status.configure(text=f"Worker cleanup failed: {message.value}")
            self._diagnose(message.value)
            self._controls()
        elif message.kind == "stopped":
            self._worker_stopped = True
            self._cleanup_failed = False
            self.ready = False
            self.executing = False
            if self.pending is not None:
                result = Outcome('unverified', error=RuntimeError('Worker stopped before authoritative delivery; operation may have committed. Exit explicitly; this session cannot reconcile.'))
                self._mutation_outcome = result
                try:
                    self._work_editor_result(self.pending, self._pending_token, result)
                    if self.history is not None:
                        self.history.mutation_result(self.pending, self._pending_token, result)
                    if self._polr_submission is not None and self._polr_submission.request is self.pending:
                        self._polr_result(self.pending, self._pending_token, result)
                    if self._timesheet_attempt is not None and self._timesheet_attempt.request is self.pending:
                        self._timesheet_attempt.registration = 'unverified'
                        self._timesheet_attempt.error = result.error
                        self._timesheet_notify()
                finally:
                    self.status.configure(text=str(result.error))
                    self._controls()
            elif self.closing:
                self.root.destroy()
            else:
                self.status.configure(text=self.status.cget("text") + " Worker stopped; close and reopen the application.")
                self._controls()

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
                if self.ready and local_date(cutoff,self.zone).isoformat()!=self._reminder_date:
                    self.recheck_polr(cutoff_utc_us=cutoff)
                self._queue_reminder()
                active = self.state.get("active")
                if active:
                    elapsed = cutoff - active["start_utc_us"]
                    if elapsed < 0:
                        raise ClockWarning("Observation precedes active start. Correct active start or check the clock.")
                self.refresh(cutoff_utc_us=cutoff)
            except Exception as exc:
                self._unavailable(exc)
                self._reminder_failure(exc)
        self._tick_id = self.root.after(1000, self._tick)

    def retry(self):
        if self.alive and (self.closing or self._cleanup_failed) and not self.executing and self.pending is None and not self._shutdown_sent:
            self.retry_button.pack_forget()
            self._advance_close()
            return True
        if not self.alive or self.executing or self.pending is None or self._worker_stopped:
            return False
        self.executing = True
        self._token += 1
        self._pending_token = self._token  # Each delivery attempt rejects earlier/duplicate completions.
        session = self._work_editor
        if session is not None and session.request is self.pending:
            session.token = self._pending_token
            session.phase = "executing"
            session.status.configure(text="Reconciling the exact request; waiting for the database result…")
            self._work_editor_controls(session)
        history = self.history
        if history is not None and history.request is self.pending:
            history.token, history.phase = self._pending_token, "executing"
        polr = getattr(self,'_polr_submission',None)
        if polr is not None and polr.request is self.pending:
            polr.token, polr.outcome = self._pending_token, None
        attempt = self._timesheet_attempt
        if attempt is not None and attempt.request is self.pending:
            attempt.token, attempt.registration = self._pending_token, 'registering'
        try:
            self.worker.requests.put(Message("reconcile", self._pending_token, self.pending))
        except Exception as exc:
            self.executing = False
            if session is not None and session.request is self.pending:
                self._work_editor_result(self.pending, self._pending_token, Outcome("unverified", error=exc))
            if history is not None and history.request is self.pending:
                history.mutation_result(self.pending, self._pending_token, Outcome("unverified", error=exc))
            if polr is not None and polr.request is self.pending:
                self._polr_result(self.pending,self._pending_token,Outcome('unverified',error=exc))
            if attempt is not None and attempt.request is self.pending:
                attempt.registration, attempt.error = 'unverified', exc
                self._timesheet_notify()
            self.status.configure(text=f"Reconciliation not submitted; original request retained. {exc}")
            self._diagnose(exc)
            self._controls()
            return False
        if history is not None and history.request is self.pending:
            # Queue first: a presentation failure cannot claim executing I/O
            # which was never dispatched, or lose the correlated exact retry.
            history.status.configure(text="Reconciling the identical request; please wait.")
            history.controls()
        self._timesheet_notify()
        if polr is not None and self.timesheet is polr.origin: self.timesheet.polr_controls()
        self.status.configure(text="Reconciling the exact saved request…")
        self._controls()
        return True

    def request_close(self):
        if not self.alive:
            return
        if self._backup_opening or self._backup_busy() or self.backup_dialog is not None:
            return  # Close the owned dialog first; never interrupt accepted backup I/O.
        if self._history_opening or self._timesheet_opening:
            return
        if self._timesheet_dialog_busy: return
        if self.timesheet is not None:
            if self.executing: return
            polr = getattr(self,'_polr_submission',None)
            if polr is not None and polr.request is self.pending:
                self._timesheet_exit()
                return
            attempt = self._timesheet_attempt
            if attempt is not None and attempt.registration == 'unverified':
                self._timesheet_exit()
                return
            if attempt is None or attempt.registration != 'committed' or not attempt.started or attempt.saved_path is not None:
                return  # Close the modal Timesheet before ordinary root exit.
            if not self._timesheet_exit_warning(): return
            self.closing = True
            self.timesheet.close(force=True)
        elif self._timesheet_handoff is not None and not self.executing:
            if not self._timesheet_exit_warning(): return

        if self.history is not None:
            if self.history.phase == "unverified" and not self.executing:
                self.history.exceptional_exit()
            return  # As with a manual form, close owned History before ordinary exit.
        if self.editor is not None:
            session = self._work_editor
            if session is not None and session.phase == "unverified" and not self.executing:
                self._work_editor_exit(session)
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
            self._cleanup_failed = False
            self.worker.requests.put(Message("shutdown"))

    def cancel_close(self):
        # Only unresolved work can cancel before shutdown starts. A worker awaiting
        # cleanup retry has already left its operation loop and cannot resume edits.
        if self.closing and self.pending is not None and not self.executing and not self._shutdown_sent:
            self.closing = False
            self._controls()

    def exceptional_exit(self):
        if not self.alive or self.executing or not self.closing or self.pending is None:
            return False
        self.executing = True
        session = self._work_editor
        parent = session.window if session is not None and self.editor is session.window else self.root
        history = self.history
        sheet = self.timesheet
        if sheet is not None and not sheet.disposed: parent = sheet.window
        if history is not None and not history.disposed:
            parent = history.window
        try:
            confirmed = messagebox.askyesno("Unresolved save", "The operation may already have committed. Exit loses this session's retry inputs. No work or evidence is undone. Exit anyway?",
                                           parent=parent, default=messagebox.NO)
        except BaseException as primary:
            if sheet is not None and self.timesheet is sheet:
                try: sheet.restore_modal()
                except Exception as secondary: primary.add_note(f'Timesheet modal return also failed: {secondary!r}')
            if history is not None and self.history is history:
                try:
                    history.restore_modal()
                except Exception as secondary:
                    primary.add_note(f"History modal return also failed: {secondary!r}")
            raise
        finally:
            self.executing = False
        if confirmed:
            # No executing operation is interrupted. The worker still closes orderly.
            self.pending = None
            self._timesheet_attempt = None
            if sheet is not None and self.timesheet is sheet:
                try: sheet.close(force=True)
                except Exception as exc: self._diagnose(exc)
            if session is not None and self.editor is session.window:
                try:
                    self._dispose_editor(session.window)
                except Exception as exc:
                    self._diagnose(exc)
            if history is not None and self.history is history:
                try:
                    history.close(force=True)
                except Exception as exc:
                    self._diagnose(exc)
            self._advance_close()
        else:
            if sheet is not None and self.timesheet is sheet: sheet.restore_modal()
            if history is not None and self.history is history:
                history.restore_modal()
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


class BackupDialog:
    """Small owned backup view. The application retains accepted I/O/results."""

    def __init__(self, owner):
        self.owner = owner
        self.window = None
        self.disposed = self.presented = self._dialog_busy = False
        try:
            self.window = tk.Toplevel(owner.root)
            self.window.withdraw()
            self.window.title('Backup Chronicle')
            self.window.transient(owner.root)
            self.window.minsize(540, 270)
            self.window.columnconfigure(0, weight=1)
            ttk.Label(self.window, text='Capture committed SQLite data consistently.\nRunning timers continue; existing files are never overwritten.').grid(row=0, column=0, columnspan=2, padx=12, pady=12, sticky='w')
            self.destination = tk.StringVar(self.window, '')
            self.path_entry = ttk.Entry(self.window, textvariable=self.destination, width=65)
            self.path_entry.grid(row=1, column=0, sticky='ew', padx=12)
            self.choose_button = ttk.Button(self.window, text='Choose destination', command=self.choose)
            self.choose_button.grid(row=1, column=1, padx=8)
            self.create_button = ttk.Button(self.window, text='Create Backup', command=self.create)
            self.create_button.grid(row=2, column=0, sticky='w', padx=12, pady=8)
            self.status = ttk.Label(self.window, text='Choose a new backup file outside the dataset directory.', wraplength=570)
            self.status.grid(row=3, column=0, columnspan=2, sticky='w', padx=12, pady=8)
            self.close_button = ttk.Button(self.window, text='Close', command=self.close)
            self.close_button.grid(row=4, column=0, sticky='e', padx=12, pady=8)
            self.window.protocol('WM_DELETE_WINDOW', self.close)
            self.window.bind('<Escape>', lambda event: self.close())
            self.window.bind('<Map>', self._mapped, add='+')
            self.window.bind('<Destroy>', self._destroyed, add='+')
        except BaseException as primary:
            if self.window is not None:
                try:
                    self.close(force=True)
                except Exception as secondary:
                    primary.add_note(f'Backup dialog cleanup also failed: {secondary!r}')
            raise

    def _mapped(self, event):
        if event.widget is not self.window or self.disposed or self.presented:
            return
        try:
            if self.owner.backup_dialog is not self or not self.owner.alive:
                return
            if not self.restore_modal():
                raise ValueError('Backup modal ownership could not be acquired')
            self.presented = True
            self.owner._backup_opening = False
            self.owner._controls()
        except Exception as primary:
            try:
                self.close(force=True)
            except Exception as secondary:
                primary.add_note(f'Backup failed-presentation cleanup also failed: {secondary!r}')
            self.owner._backup_opening = False
            self.owner._diagnose(primary)

    def restore_modal(self):
        from .history_window import widget_live
        if (self.disposed or self.owner.backup_dialog is not self or not widget_live(self.window)
                or not widget_live(self.owner.root) or not self.window.winfo_ismapped()):
            return False
        grab = self.window.grab_current()
        if grab is not None and (grab not in (self.owner.root, self.window) or grab.grab_status() != 'local'):
            return False  # Never steal unrelated or global ownership.
        if grab is not self.window:
            self.window.grab_set()
        self.close_button.focus_set()
        return True

    def busy(self):
        return self._dialog_busy or self.owner._backup_busy()

    def controls(self):
        if self.disposed:
            return
        state = 'disabled' if self.busy() else 'normal'
        for widget in (self.path_entry, self.choose_button, self.create_button, self.close_button):
            widget.configure(state=state)

    def choose(self):
        if self.disposed or self.busy() or self.owner.backup_dialog is not self:
            return False
        self._dialog_busy = True
        primary = None
        try:
            self.controls()
            selected = filedialog.asksaveasfilename(parent=self.window, title='Choose a new Chronicle backup file',
                                                   defaultextension='.sqlite3', confirmoverwrite=False,
                                                   filetypes=(('SQLite backup', '*.sqlite3'), ('All files', '*')))
            if selected and not self.disposed:
                self.destination.set(selected)
            return bool(selected)
        except Exception as exc:
            primary = exc
            try:
                if not self.disposed:
                    self.status.configure(text=f'Unable to choose destination: {exc}')
            except Exception as secondary:
                exc.add_note(f'Backup chooser-error presentation also failed: {secondary!r}')
            self.owner._diagnose(exc)
            return False
        finally:
            self._dialog_busy = False
            try:
                self.restore_modal()
                self.controls()
            except Exception as secondary:
                if primary:
                    primary.add_note(f'Backup chooser modal return also failed: {secondary!r}')
                else:
                    self.owner._diagnose(secondary)

    def create(self):
        return self.owner._start_backup(self)

    def close(self, *, force=False):
        if self.disposed:
            return True
        if not force and self.busy():
            return False
        primary = None
        try:
            if self.window.grab_current() is self.window:
                self.window.grab_release()
        except Exception as exc:
            primary = exc
        try:
            self.window.destroy()
        except Exception as secondary:
            if primary is None:
                raise
            primary.add_note(f'Backup destruction also failed: {secondary!r}')
        if primary:
            raise primary
        return True

    def _destroyed(self, event):
        if event.widget is self.window and not self.disposed:
            self.disposed, self.presented = True, False
            self.owner._backup_disposed(self)
