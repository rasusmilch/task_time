"""Owned callback-driven mixed History, inline revisions and local calendars.

The application owns all reads and mutations. This view retains detached rows,
drafts and delivery tokens, never a connection or independent request coordinator.
"""

import calendar
from copy import deepcopy
from datetime import date, timedelta
import tkinter as tk
from tkinter import messagebox, ttk

from .history_display import clock_text, details_text, duration_text, prepare_rows
from .records import Outcome, StaleState
from .timekeeping import from_us, local_minute_candidates, parse_date


def widget_live(widget):
    """Object identity as well as Tcl liveness: reused widget paths are not revival."""
    if widget is None:
        return False
    if widget.master is not None and widget.master.children.get(widget._name) is not widget:
        return False
    return bool(widget.tk.call("namespace", "which", "-command", widget._w))


class HistoryWindow:
    def __init__(self, owner, task):
        self.owner, self.task = owner, deepcopy(task)
        self.zone = owner.zone
        self.window = None
        self.disposed = self.presented = self._constructed = False
        self._dialog_busy = False
        self.newest_first = owner._history_newest_first
        self.snapshot = None
        self.applied = {"period": "current_week"}
        self.load_state = "Not loaded"
        self.trusted = self.current = False
        self.rows, self.mapping = [], {}
        self._row_number = 0
        self.snapshot_token = self.details_token = None
        self.details_identity = None
        self.phase, self.request, self.token, self.outcome = "browsing", None, None, None
        self.reviewed = None
        self.edit_fields = {}
        self._disposal_primary = None
        self.picker = None
        try:
            self.window = tk.Toplevel(owner.root)
            self.window.withdraw()
            self.window.title(f"Work History — {task['name']}")
            self.window.transient(owner.root)
            self.window.geometry("1020x780")
            self.window.minsize(820, 680)
            self.window.columnconfigure(0, weight=1)
            self.window.rowconfigure(3, weight=1)
            self._build()
            self.window.protocol("WM_DELETE_WINDOW", self.close)
            self.window.bind("<Escape>", self._escape)
            self.window.bind("<Destroy>", self._destroyed, add="+")
            self.window.bind("<Map>", self._mapped, add="+")
            self._constructed = True
        except BaseException as primary:
            try:
                self.close(force=True)
            except BaseException as secondary:
                primary.add_note(f"History construction cleanup failed: {secondary!r}")
            raise

    def _build(self):
        ttk.Label(self.window, text=f"Task: {self.task['name']}   UUID: {self.task['task_id']}").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        bar = ttk.Frame(self.window)
        bar.grid(row=1, column=0, sticky="ew", padx=8)
        self.period = tk.StringVar(bar, "Current week")
        self.period_control = ttk.Combobox(bar, textvariable=self.period, state="readonly", values=("Current week", "Custom", "All"), width=15)
        self.period_control.grid(row=0, column=0, padx=3)
        self.period_control.bind("<<ComboboxSelected>>", lambda event: self.period_changed())
        self.start = tk.StringVar(bar, "")
        self.end = tk.StringVar(bar, "")
        self.date_controls = []
        for column, (label, variable) in enumerate((("Start date", self.start), ("End date", self.end))):
            base = 1 + column * 3
            ttk.Label(bar, text=label).grid(row=0, column=base)
            field = ttk.Entry(bar, textvariable=variable, width=12)
            field.grid(row=0, column=base+1, padx=3)
            button = ttk.Button(bar, text="Calendar", command=lambda v=variable: self.open_picker(v))
            button.grid(row=0, column=base+2, padx=3)
            self.date_controls.extend((field, button))
        self.apply_button = ttk.Button(bar, text="Apply", command=self.apply)
        self.apply_button.grid(row=1, column=0, pady=4)
        self.refresh_button = ttk.Button(bar, text="Refresh", command=self.refresh)
        self.refresh_button.grid(row=1, column=1, pady=4)
        self.calendar_area = ttk.Frame(bar)
        self.calendar_area.grid(row=2, column=0, columnspan=7, sticky="w")
        self.context = ttk.Label(self.window, text="Not loaded", wraplength=950)
        self.context.grid(row=2, column=0, sticky="w", padx=8)
        holder = ttk.Frame(self.window)
        holder.grid(row=3, column=0, sticky="nsew", padx=8)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        columns = ("link", "date", "kind", "start", "end", "duration")
        self.tree = ttk.Treeview(holder, columns=columns, show="headings", selectmode="browse", height=9)
        for name, label, width in zip(columns, ("Link", "Date", "Kind", "Start", "End / as of", "Duration"), (40, 100, 85, 210, 210, 95)):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, minwidth=width, stretch=name in ("start", "end"))
        self.tree.heading("date", text="Date ↓", command=self.sort_dates)
        self.tree.grid(row=0, column=0, sticky="nsew")
        for orient, row, column, command in (("vertical", 0, 1, self.tree.yview), ("horizontal", 1, 0, self.tree.xview)):
            scroll = ttk.Scrollbar(holder, orient=orient, command=command)
            scroll.grid(row=row, column=column, sticky="ns" if orient == "vertical" else "ew")
            self.tree.configure(**{("yscrollcommand" if orient == "vertical" else "xscrollcommand"): scroll.set})
        self.tree.tag_configure("related", background="#e1ecfa")
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        actions = ttk.Frame(self.window)
        actions.grid(row=4, column=0, sticky="w", padx=8, pady=5)
        self.edit_button = ttk.Button(actions, text="Edit", command=self.edit)
        self.delete_button = ttk.Button(actions, text="Delete", command=self.delete)
        self.details_button = ttk.Button(actions, text="Details", command=self.show_details)
        for column, button in enumerate((self.edit_button, self.delete_button, self.details_button)):
            button.grid(row=0, column=column, padx=3)
        self.detail_panel = ttk.LabelFrame(self.window, text="Immutable revision details")
        self.detail_panel.grid(row=5, column=0, sticky="ew", padx=8)
        self.detail_panel.columnconfigure(0, weight=1)
        ttk.Label(self.detail_panel, text="Deleted entries").grid(row=0, column=0, sticky="w")
        self.deleted_control = ttk.Combobox(self.detail_panel, state="readonly", width=90)
        self.deleted_control.grid(row=1, column=0, sticky="ew")
        self.deleted_control.bind("<<ComboboxSelected>>", lambda event: self._deleted_selected())
        self.deleted_choices = {}
        self.details_view = tk.Text(self.detail_panel, height=7, wrap="word", state="disabled")
        self.details_view.grid(row=2, column=0, sticky="ew")
        scroll = ttk.Scrollbar(self.detail_panel, orient="vertical", command=self.details_view.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.details_view.configure(yscrollcommand=scroll.set)
        self.detail_panel.grid_remove()
        self.editor_panel = ttk.LabelFrame(self.window, text="Edit complete work entry")
        self.editor_panel.grid(row=6, column=0, sticky="ew", padx=8)
        self.editor_panel.grid_remove()
        self.status = ttk.Label(self.window, text="", wraplength=950)
        self.status.grid(row=7, column=0, sticky="ew", padx=8, pady=4)
        footer = ttk.Frame(self.window)
        footer.grid(row=8, column=0, sticky="ew", padx=8, pady=5)
        self.retry_button = ttk.Button(footer, text="Retry/Reconcile", command=self.retry)
        self.exit_button = ttk.Button(footer, text="Exit despite unresolved save", command=self.exceptional_exit)
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.pack(side="right")
        self.controls()

    def present(self):
        self.window.deiconify()  # Acquisition occurs in Map, after intervening events.

    def restore_modal(self):
        if self.disposed or not self.presented or not widget_live(self.window):
            return False
        current = self.window.grab_current()
        if current is not None and (current is not self.window or current.grab_status() != "local"):
            return False
        if current is not self.window:
            self.window.grab_set()
            self.close_button.focus_set()
        return True

    def _mapped(self, event):
        if event.widget is not self.window or self.presented or self.disposed:
            return
        try:
            current = self.window.grab_current()
            if current is not None and (current not in (self.owner.root, self.window) or current.grab_status() != "local"):
                raise ValueError("History cannot replace an unrelated or global grab")
            if current is not self.window:
                self.window.grab_set()
            self.close_button.focus_set()
            self.presented = True
            self.owner._history_presented(self)
            self.refresh()
        except Exception as primary:
            self.owner._history_launch_failed(self, primary)

    def report(self, message, exc):
        try:
            if widget_live(self.window):
                self.status.configure(text=f"{message}: {exc}")
        except Exception as secondary:
            exc.add_note(f"History diagnostic presentation failed: {secondary!r}")
        self.owner._diagnose(exc)
        return False

    def idle(self):
        return not self.disposed and not self._dialog_busy and self.phase == "browsing" and self.owner.pending is None and not self.owner.executing

    def mutation_allowed(self):
        return not self.disposed and not self._dialog_busy and self.phase in ("browsing", "editing")

    def controls(self):
        if self.disposed:
            return
        idle = self.idle()
        custom = idle and self.period.get() == "Custom"
        self.period_control.configure(state="readonly" if idle else "disabled")
        self.refresh_button.configure(state="normal" if idle else "disabled")
        for widget in (*self.date_controls, self.apply_button):
            widget.configure(state="normal" if custom else "disabled")
        row = self.selected_row()
        eligible = bool(idle and self.current and row and not row["is_running"] and row["revision"] is not None)
        for widget in (self.edit_button, self.delete_button):
            widget.configure(state="normal" if eligible else "disabled")
        self.details_button.configure(state="normal" if idle else "disabled")
        self.deleted_control.configure(state="readonly" if idle else "disabled")
        for widget in (self.retry_button, self.exit_button):
            if self.phase == "unverified":
                widget.pack(side="left", padx=3)
            else:
                widget.pack_forget()
        if self.reviewed is not None and self.edit_fields and widget_live(self.editor_panel):
            editable = self.phase == "editing"
            for field in self.edit_fields.values():
                field.configure(state="normal" if editable else "disabled")
            for selector in self.occurrence_controls.values():
                selector.configure(state="readonly" if editable else "disabled")
            self.save_button.configure(state="normal" if editable else "disabled")
            self.cancel_button.configure(state="normal" if self.phase in ("editing", "stale") else "disabled")

    def selected_row(self):
        if not self.trusted:
            return None
        selected = self.tree.selection()
        return deepcopy(self.mapping.get(selected[0])) if selected else None

    def _selected(self, event=None):
        if not self.trusted:
            return
        row = self.selected_row()
        if row is None or row["entry_id"] != self.details_identity:
            self.details_token = self.details_identity = None
        primary = self.tree.selection()
        for handle, other in self.mapping.items():
            related = bool(row and row["link_identity"] and other["link_identity"] == row["link_identity"] and handle not in primary)
            self.tree.item(handle, tags=("related",) if related else ())
        self.controls()

    def period_changed(self):
        if not self.idle():
            return False
        self.close_picker()
        self.controls()
        if self.period.get() != "Custom":
            return self.load({"period": "current_week" if self.period.get() == "Current week" else "all"})
        return True

    def apply(self):
        if not self.idle() or self.period.get() != "Custom":
            return False
        try:
            first, last = parse_date(self.start.get()), parse_date(self.end.get())
            if first > last or last == date.max:
                raise ValueError("Require ordered inclusive dates with a representable end boundary")
        except Exception as exc:
            return self.report("Unable to apply Custom period", exc)
        return self.load({"period": "custom", "start_date": first.isoformat(), "end_date": last.isoformat()})

    def refresh(self):
        return self.load(dict(self.applied)) if self.idle() else False

    def load(self, spec):
        if not self.idle():
            return False
        self.load_state, self.current = "Loading", False
        self.snapshot_token = None  # Supersede even if this new dispatch cannot be queued.
        self.status.configure(text="Loading… Previous results, if any, remain at their last as-of observation.")
        self.controls()
        try:
            self.snapshot_token = self.owner._history_read(self, "history_snapshot", spec)
            return True
        except Exception as exc:
            self.load_state = "Load failed"
            return self.report("History load failed", exc)

    def _replace(self, prepared):
        try:
            self.trusted = self.current = False
            self.mapping = {}
            self.tree.delete(*self.tree.get_children())
            mapping = {}
            for row, values in prepared:
                self._row_number += 1
                handle = self.tree.insert("", "end", iid=f"row{self._row_number}", values=values)
                mapping[handle] = row
            self.tree.selection_remove(*self.tree.selection())
            self.tree.grid()
            self.mapping, self.rows = mapping, [row for row, _ in prepared]
            self.trusted = True
            self.details_token = self.details_identity = None
        except Exception as primary:
            self.mapping = {}
            try:
                self.tree.selection_remove(*self.tree.selection())
                self.tree.grid_remove()
            except Exception as secondary:
                primary.add_note(f"Unable to hide untrusted History table: {secondary!r}")
            raise

    def receive_snapshot(self, token, result):
        if self.disposed or token != self.snapshot_token:
            return
        self.snapshot_token = None
        replacing = False
        previous_label = "Not loaded"
        try:
            previous_label = self.context.cget("text")
            if isinstance(result, Outcome):
                raise result.error or ValueError("History read unavailable")
            if result["dataset_id"] != self.owner.dataset_id or result["task_id"] != self.task["task_id"]:
                raise ValueError("History snapshot identity mismatch")
            prepared = prepare_rows(result["rows"], self.task["task_id"], self.zone, self.newest_first)
            stamp = from_us(result["cutoff_utc_us"]).astimezone(self.zone).isoformat()
            label = f"{result['period']}: {result['start_date'] or 'All'} — {result['end_date'] or 'All'}; as of {stamp}; week starts {calendar.day_name[result['week_start']]}"
            deleted_choices = {self._deleted_label(row): row["entry_id"] for row in result["deleted_entries"]}
            replacing = True
            self._replace(prepared)
            self.context.configure(text=label)
            self.deleted_control.configure(values=tuple(deleted_choices))
            self.deleted_control.set("")
            self.deleted_choices = deleted_choices
            self.snapshot = deepcopy(result)
            self.applied = {key: result[key] for key in ("period", "start_date", "end_date") if key == "period" or result["period"] == "custom"}
            self.load_state = "Loaded with rows" if prepared else "Loaded and empty"
            self.current = True
            self.status.configure(text=self.load_state)
        except Exception as exc:
            self.load_state, self.current = "Load failed", False
            if replacing:
                self._invalidate_table(exc)
                try:
                    self.context.configure(text="Display unavailable. Last successful context: " + previous_label)
                except Exception as secondary:
                    exc.add_note(f"History context reporting failed: {secondary!r}")
            message = ("History load failed; previous as-of results only" if self.trusted else
                       "History unavailable; Refresh to recover")
            if self.outcome is not None and self.outcome.status == "committed":
                message = "Saved work remains committed. " + message
            self.report(message, exc)
        self.controls()

    def _invalidate_table(self, primary):
        self.trusted = self.current = False
        self.mapping = {}
        try:
            self.tree.selection_remove(*self.tree.selection())
            self.tree.grid_remove()
        except Exception as secondary:
            primary.add_note(f"Unable to hide untrusted History rows: {secondary!r}")

    def sort_dates(self):
        if not self.idle() or not self.trusted or self.load_state == "Loading":
            return False
        direction, was_current = not self.newest_first, self.current
        replacing = False
        try:
            prepared = prepare_rows(self.rows, self.task["task_id"], self.zone, direction)
            replacing = True
            self._replace(prepared)
            self.tree.heading("date", text="Date ↓" if direction else "Date ↑")
            self.newest_first, self.current = direction, was_current
        except Exception as exc:
            if replacing:
                self._invalidate_table(exc)
            self.controls()
            return self.report("Unable to sort History" if self.trusted else
                               "Unable to sort History; table unavailable, Refresh to recover", exc)
        try:
            self.owner._remember_history_direction(direction)
        except Exception as exc:
            self.report("Unable to remember session direction", exc)
        self.controls()
        return True

    def _deleted_label(self, row):
        values = (f"{row['work_date']} {duration_text(row['duration_us'])}" if row["kind"] == "date_only" else
                  f"{from_us(row['start_utc_us']).astimezone(self.zone).isoformat()} — {from_us(row['stop_utc_us']).astimezone(self.zone).isoformat()}")
        return f"{row['kind']} {values} — {row['entry_id']} (revision {row['revision']}, deleted)"

    def show_details(self):
        if not self.idle():
            return False
        self.detail_panel.grid()
        row = self.selected_row()
        if row:
            self._request_details(row["entry_id"])
        return True

    def _deleted_selected(self):
        if self.idle() and self.deleted_control.get() in self.deleted_choices:
            self._request_details(self.deleted_choices[self.deleted_control.get()])

    def _request_details(self, entry_id):
        self.details_identity = entry_id
        self.details_token = None
        self._details_text("Loading immutable details…")
        try:
            self.details_token = self.owner._history_read(self, "revisions", entry_id)
        except Exception as exc:
            self.report("Unable to load revision details", exc)

    def _details_text(self, text):
        try:
            self.details_view.configure(state="normal")
            self.details_view.delete("1.0", "end")
            self.details_view.insert("1.0", text)
        except BaseException as primary:
            try:
                self.details_view.configure(state="disabled")
                self.details_view.grid_remove()
            except Exception as secondary:
                primary.add_note(f"Revision detail cleanup failed: {secondary!r}")
            raise
        else:
            self.details_view.configure(state="disabled")
            self.details_view.grid()

    def receive_details(self, token, result):
        if self.disposed or token != self.details_token:
            return
        self.details_token = None
        try:
            if isinstance(result, Outcome):
                raise result.error or ValueError("Revision details unavailable")
            if result["entry"]["entry_id"] != self.details_identity or result["entry"]["task_id"] != self.task["task_id"]:
                raise ValueError("Revision detail identity mismatch")
            self._details_text(details_text(result))
        except Exception as exc:
            self.report("Unable to display revision details", exc)

    def _eligible(self):
        row = self.selected_row()
        return row if self.idle() and self.current and row and not row["is_running"] else None

    def edit(self):
        row = self._eligible()
        if row is None:
            return False
        self.close_picker()
        self.detail_panel.grid_remove()
        self.details_token = self.details_identity = None
        self.reviewed, self.phase = deepcopy(row), "editing"
        self.edit_fields, self.occurrences, self.occurrence_controls, self.occurrence_choices = {}, {}, {}, {}
        for child in self.editor_panel.winfo_children():
            child.destroy()
        try:
            def field(key, label, value, position):
                ttk.Label(self.editor_panel, text=label).grid(row=position, column=0, sticky="w")
                widget = ttk.Entry(self.editor_panel, width=36)
                widget.insert(0, value)
                widget.grid(row=position, column=1, sticky="w", padx=5)
                self.edit_fields[key] = widget
                return widget
            if row["kind"] == "timed":
                for number, (endpoint, value) in enumerate((("start", row["start_utc_us"]), ("end", row["stop_utc_us"]))):
                    local = from_us(value).astimezone(self.zone)
                    day = field(endpoint+"_date", endpoint.title()+" date", local.date().isoformat(), number*2)
                    clock = field(endpoint+"_time", endpoint.title()+" clock", local.strftime("%H:%M"), number*2+1)
                    selector = ttk.Combobox(self.editor_panel, state="readonly", width=37)
                    selector.grid(row=number*2+1, column=2, padx=5)
                    self.occurrence_controls[endpoint] = selector
                    def changed(day_text=None, clock_value=None, key=endpoint, day_field=day, clock_field=clock):
                        self._endpoint_changed(key, day_field.get() if day_text is None else day_text,
                                               clock_field.get() if clock_value is None else clock_value)
                    day.configure(validate="key", validatecommand=(self.window.register(lambda value, change=changed: change(day_text=value) or True), "%P"))
                    clock.configure(validate="key", validatecommand=(self.window.register(lambda value, change=changed: change(clock_value=value) or True), "%P"))
                    changed()
                    minute = value - local.second*1_000_000 - local.microsecond
                    candidates = local_minute_candidates(local.date(), local.strftime("%H:%M"), self.zone)
                    if len(candidates) == 2:
                        selector.current(0 if minute == candidates[0] else 1)
                comment_row = 4
            else:
                field("work_date", "Work date", row["work_date"], 0)
                minutes = row["duration_us"] // 60_000_000
                field("duration_text", "Duration H:MM", f"{minutes//60}:{minutes%60:02d}", 1)
                comment_row = 2
            field("comment", "Optional comment", row["comment"], comment_row)
            self.save_button = ttk.Button(self.editor_panel, text="Save", command=self.save)
            self.save_button.grid(row=comment_row+1, column=0, pady=4)
            self.cancel_button = ttk.Button(self.editor_panel, text="Cancel", command=self.cancel_edit)
            self.cancel_button.grid(row=comment_row+1, column=1, pady=4)
            self.editor_panel.grid()
            self.status.configure(text=f"Editing complete {row['kind']} entry {row['entry_id']}, reviewed revision {row['revision']}")
            self.controls()
            next(iter(self.edit_fields.values())).focus_set()
            return True
        except Exception as exc:
            self.reviewed, self.phase = None, "browsing"
            self.editor_panel.grid_remove()
            self.controls()
            return self.report("Unable to construct inline editor", exc)

    def _endpoint_changed(self, endpoint, day, clock):
        selector = self.occurrence_controls[endpoint]
        selector.set("")
        choices = {}
        try:
            candidates = local_minute_candidates(parse_date(day), clock, self.zone)
            if len(candidates) == 2:
                choices = {("First " if i == 0 else "Second ") + clock_text(value, day, self.zone): ("first", "second")[i] for i, value in enumerate(candidates)}
        except ValueError:
            pass  # Invalid drafts belong to the operator; Save is validated on the worker.
        self.occurrence_choices[endpoint] = choices
        selector.configure(values=tuple(choices))
        if choices:
            selector.grid()
        else:
            selector.grid_remove()

    def save(self):
        if self.disposed or self.phase != "editing" or self.owner.pending is not None or self._dialog_busy:
            return False
        arguments = {key: widget.get() for key, widget in self.edit_fields.items()}
        if self.reviewed["kind"] == "timed":
            for endpoint, choices in self.occurrence_choices.items():
                occurrence = choices.get(self.occurrence_controls[endpoint].get())
                if choices and occurrence is None:
                    self.status.configure(text="Select first or second occurrence for each repeated minute.")
                    return False
                arguments[endpoint+"_occurrence"] = occurrence
        return self._submit("edit_closed_timed_work" if self.reviewed["kind"] == "timed" else "edit_date_only_work", arguments)

    def _submit(self, operation, arguments):
        row = self.reviewed
        arguments.update(task_id=self.task["task_id"], entry_id=row["entry_id"], expected_revision=row["revision"])
        if not self.owner._history_submit(self, operation, arguments):
            self.status.configure(text=self.owner.status.cget("text"))
            self.controls()
            return False
        self.request, self.token = self.owner.pending, self.owner._pending_token
        self.phase, self.outcome = "executing", None
        self.status.configure(text="Saving; please wait for the authoritative result.")
        self.controls()
        return True

    def cancel_edit(self):
        if self.phase not in ("editing", "stale") or self.owner.pending is not None:
            return False
        self.reviewed, self.phase = None, "browsing"
        self.edit_fields = {}
        self.editor_panel.grid_remove()
        self.status.configure(text="Cancelled; browsing context unchanged.")
        self.controls()
        return True

    def delete(self):
        row = self._eligible()
        if row is None:
            return False
        self._dialog_busy = True
        primary = None
        try:
            if row["kind"] == "timed":
                start = from_us(row["start_utc_us"]).astimezone(self.zone)
                stop = from_us(row["stop_utc_us"]).astimezone(self.zone)
                last = from_us(row["stop_utc_us"]-1).astimezone(self.zone).date()
                text = f"Timed work {start.isoformat()} — {stop.isoformat()}."
                if start.date() != last:
                    text += f" Removes work across all affected dates {start.date().isoformat()} through {last.isoformat()}, including other dates."
            else:
                text = f"Date-only work {row['work_date']}, {duration_text(row['duration_us'])}."
            confirmed = messagebox.askyesno("Delete complete work entry", f"Task: {self.task['name']}\n{self.task['task_id']}\nEntry: {row['entry_id']}\n{text}\nDelete the complete entry? Earlier revisions remain available.", parent=self.window, default=messagebox.NO)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            self._dialog_busy = False
            try:
                self.restore_modal()
            except Exception as secondary:
                if primary is None:
                    raise
                primary.add_note(f"History confirmation return also failed: {secondary!r}")
        if not confirmed or self.disposed:
            return False
        self.reviewed = row
        self.edit_fields = {}
        return self._submit("delete_work_entry", {"comment": ""})

    def mutation_result(self, request, token, result):
        if self.disposed or self.request is not request or self.token != token:
            return
        self.outcome = result  # Authoritative outcome survives any subsequent widget fault.
        if result.status in ("committed", "unchanged"):
            self.request, self.reviewed, self.phase = None, None, "browsing"
            self.edit_fields = {}
            if result.status == "committed":
                self.current = False
            try:
                self.editor_panel.grid_remove()
                self.status.configure(text="Saved." if result.status == "committed" else "Unchanged; nothing written.")
                self.controls()
            finally:
                if result.status == "committed":
                    self.refresh()
        else:
            if result.status == "unverified":
                self.phase = "unverified"
                text = "Save unverified; it may have committed. Retry/Reconcile uses the identical request."
            else:
                self.request, self.token = None, None
                self.phase = "stale" if isinstance(result.error, StaleState) else "editing"
                text = ("Reviewed entry changed. Draft retained; Cancel, Refresh and select for fresh review."
                        if self.phase == "stale" else f"{result.status}; draft retained.")
                # A rejected delete has no text editor to resume; retain its reviewed
                # identity for explicit retry/cancel without silently selecting a successor.
                if request.operation == "delete_work_entry":
                    self.phase = "browsing"
                    self.reviewed = None
                    if isinstance(result.error, StaleState):
                        self.current = False
                        text += " Refresh before another deletion."
            self.status.configure(text=text + (f" {result.error}" if result.error else ""))
            self.controls()

    def retry(self):
        if self.phase != "unverified" or self.request is not self.owner.pending or self._dialog_busy:
            return False
        return self.owner.retry()

    def exceptional_exit(self):
        if self.phase != "unverified" or self.owner.executing or self._dialog_busy:
            return False
        was_closing = self.owner.closing
        self.owner.closing = True
        try:
            return self.owner.exceptional_exit()
        finally:
            if not self.owner._shutdown_sent:
                self.owner.closing = was_closing
            if not self.disposed:
                self.owner._controls()

    def open_picker(self, variable):
        if not self.idle() or self.period.get() != "Custom":
            return False
        try:
            seed = parse_date(variable.get())
        except ValueError:
            if self.snapshot is None:
                return self.report("Calendar needs a valid draft or successful observation", ValueError("No date seed available"))
            seed = from_us(self.snapshot["cutoff_utc_us"]).astimezone(self.zone).date()
        self.close_picker()
        self.picker = ttk.LabelFrame(self.calendar_area, text="Choose a draft date")
        self.picker.grid()
        self._picker_variable, self._picker_month = variable, seed.replace(day=1)
        self._draw_calendar()
        return True

    def _draw_calendar(self):
        for child in self.picker.winfo_children():
            child.destroy()
        month = self._picker_month
        self.previous_month = ttk.Button(self.picker, text="Previous month", command=lambda: self._move_month(-1))
        self.previous_month.grid(row=0, column=0, columnspan=2)
        ttk.Label(self.picker, text=f"{calendar.month_name[month.month]} {month.year:04d}").grid(row=0, column=2, columnspan=3)
        self.next_month = ttk.Button(self.picker, text="Next month", command=lambda: self._move_month(1))
        self.next_month.grid(row=0, column=5, columnspan=2)
        self.previous_month.configure(state="disabled" if month == date.min else "normal")
        self.next_month.configure(state="disabled" if (month.year, month.month) == (9999, 12) else "normal")
        for column, label in enumerate(calendar.day_abbr):
            ttk.Label(self.picker, text=label).grid(row=1, column=column)
        self.day_buttons = {}
        for row, week in enumerate(calendar.Calendar().monthdayscalendar(month.year, month.month), 2):
            for column, day in enumerate(week):
                if day:
                    button = ttk.Button(self.picker, text=str(day), width=4, command=lambda d=day: self._choose_day(d))
                    button.grid(row=row, column=column)
                    self.day_buttons[day] = button
        self.picker_cancel = ttk.Button(self.picker, text="Cancel", command=self.close_picker)
        self.picker_cancel.grid(row=8, column=0, columnspan=7)

    def _move_month(self, amount):
        if self.picker is None:
            return
        index = (self._picker_month.year-1)*12 + self._picker_month.month-1 + amount
        if 0 <= index < 9999*12:
            self._picker_month = date(index//12+1, index%12+1, 1)
            self._draw_calendar()

    def _choose_day(self, day):
        if self.picker is not None:
            self._picker_variable.set(self._picker_month.replace(day=day).isoformat())
            self.close_picker()

    def close_picker(self):
        if self.picker is not None:
            self.picker.destroy()
            self.picker = None

    def _escape(self, event=None):
        if self.picker is not None:
            self.close_picker()
        else:
            self.close()
        return "break"

    def close(self, *, force=False, primary=None):
        if self.disposed or self.window is None:
            return True
        if not force and (self._dialog_busy or self.owner.executing or self.request is not None):
            if self.request is not None and not self.owner.executing:
                self.status.configure(text="Save unverified. Retry/Reconcile or explicitly exit the application.")
            else:
                self.status.configure(text="Saving; please wait.")
            return False
        self._disposal_primary = primary
        release_error = None
        try:
            if self.window.grab_current() is self.window:
                self.window.grab_release()
        except Exception as exc:
            release_error = exc
        try:
            self.window.destroy()
        except Exception as exc:
            if release_error is None:
                raise
            release_error.add_note(f"History destruction also failed: {exc!r}")
        if release_error is not None:
            raise release_error
        return True

    def _destroyed(self, event):
        if event.widget is self.window and not self.disposed:
            self.disposed, self.presented, self.picker = True, False, None
            self.mapping, self.trusted, self.current = {}, False, False
            if self._constructed:
                self.owner._history_disposed(self, self._disposal_primary)
