"""Standalone rendering of caller-supplied mixed work-history rows."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone, tzinfo
from math import isfinite
from tkinter import StringVar, TclError, font, ttk

from .work_entry_inputs import local_minute_candidates


_FIELDS = {
    "task_id", "entry_kind", "entry_id", "work_date", "segment_start_utc",
    "segment_stop_utc", "duration_seconds", "original_start_utc", "original_stop_utc",
    "is_running", "continues_before", "continues_after", "source", "reason",
}


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("History endpoints must be timezone-aware datetimes")


def _duration(seconds):
    if (type(seconds) not in (int, float) or seconds < 0
            or (type(seconds) is float and not isfinite(seconds))):
        raise ValueError("History duration must be finite, nonnegative seconds")
    if seconds == 0:
        return "0:00"
    if seconds < 60:
        return "<1 min"
    hours, minutes = divmod(int(seconds) // 60, 60)
    return f"{hours}:{minutes:02d}"


def _offset_text(offset):
    micros = (offset.days * 86400 + offset.seconds) * 1_000_000 + offset.microseconds
    sign = "+" if micros >= 0 else "-"
    seconds, fraction = divmod(abs(micros), 1_000_000)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    result = f"UTC{sign}{hours:02d}:{minutes:02d}"
    if seconds or fraction:
        result += f":{seconds:02d}"
        if fraction:
            result += f".{fraction:06d}".rstrip("0")
    return result


def _clock(instant, work_date, local_timezone):
    _aware(instant)
    local = instant.astimezone(local_timezone)
    clock = f"{local.hour:02d}:{local.minute:02d}"
    candidates = local_minute_candidates(local.date(), clock, local_timezone)
    text = clock if local.date() == work_date else f"{local.date().isoformat()} {clock}"
    if len(candidates) == 2:
        text += f" ({_offset_text(local.utcoffset())})"
    return text


def _display_values(row, local_timezone):
    if not isinstance(row, dict) or not _FIELDS <= row.keys():
        raise ValueError("History row is missing required data")
    if type(row["work_date"]) is not date:
        raise ValueError("History work date must be a calendar date")
    for key in ("task_id", "entry_id", "source", "reason"):
        if not isinstance(row[key], str) or (key in ("task_id", "entry_id") and not row[key]):
            raise ValueError(f"Invalid history {key}")
    for key in ("is_running", "continues_before", "continues_after"):
        if type(row[key]) is not bool:
            raise ValueError(f"Invalid history {key}")
    duration = _duration(row["duration_seconds"])
    if row["entry_kind"] == "dated_duration":
        if (any(row[key] is not None for key in ("segment_start_utc", "segment_stop_utc",
                                                 "original_start_utc", "original_stop_utc"))
                or any(row[key] for key in ("is_running", "continues_before", "continues_after"))):
            raise ValueError("Date-only history must have no endpoints or interval flags")
        return "", row["work_date"].isoformat(), "Date only", "", "", duration
    if row["entry_kind"] != "interval":
        raise ValueError("Unsupported history entry kind")
    _aware(row["original_start_utc"])
    if row["is_running"]:
        if row["original_stop_utc"] is not None:
            raise ValueError("Running history must not have a recorded stop")
    else:
        _aware(row["original_stop_utc"])
    return (
        "↔" if row["continues_before"] or row["continues_after"] else "",
        row["work_date"].isoformat(), "Running" if row["is_running"] else "Timed",
        _clock(row["segment_start_utc"], row["work_date"], local_timezone),
        _clock(row["segment_stop_utc"], row["work_date"], local_timezone), duration,
    )


class WorkHistoryFrame(ttk.Frame):
    """A render-only table; retained rows are detached, temporary UI metadata."""

    def __init__(self, parent, *, local_timezone):
        if not isinstance(local_timezone, tzinfo):
            raise ValueError("An explicit timezone object is required")
        try:
            datetime(2000, 1, 1, tzinfo=timezone.utc).astimezone(local_timezone)
        except (ValueError, TypeError, OverflowError, NotImplementedError) as exc:
            raise ValueError("Timezone cannot represent local endpoints") from exc
        super().__init__(parent)
        self.local_timezone = local_timezone
        self._rows_by_iid = {}
        self._display_valid = True
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.error_var = StringVar(self, value="")
        self.error_label = ttk.Label(self, textvariable=self.error_var, wraplength=700)
        self.error_label.grid(row=0, column=0, sticky="ew")
        self.error_label.grid_remove()
        self.table = ttk.Frame(self)
        self.table.grid(row=1, column=0, sticky="nsew")
        self.table.grid_columnconfigure(0, weight=1)
        self.table.grid_rowconfigure(0, weight=1)
        columns = ("link", "date", "kind", "start", "end", "duration")
        self.tree = ttk.Treeview(self.table, columns=columns, show="headings", selectmode="browse")
        for key, heading, width in zip(columns, ("", "Date", "Kind", "Start", "End / as of", "Duration"),
                                       (30, 100, 85, 215, 215, 90)):
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, minwidth=width, stretch=key in ("start", "end"),
                             anchor="e" if key == "duration" else "w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(self.table, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(self.table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        base_font = ttk.Style(self).lookup("Treeview", "font") or "TkDefaultFont"
        self._related_font = font.Font(self, font=base_font)
        self._related_font.configure(weight="bold")
        self.tree.tag_configure("related", font=self._related_font)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _show_error(self, message):
        self.error_var.set(message)
        self.error_label.grid()

    def display_rows(self, rows):
        """Prepare completely before replacement; never publish partial rendering as valid."""
        try:
            copied = deepcopy(list(rows))
            prepared = [(row, _display_values(row, self.local_timezone)) for row in copied]
        except Exception as exc:
            context = "Previous results remain." if self._display_valid else "Table remains unavailable."
            self._show_error(f"Unable to render work history: {exc}. {context}")
            raise
        try:
            self.tree.delete(*self.tree.get_children())
            mapping = {}
            for row, values in prepared:
                handle = self.tree.insert("", "end", values=values)
                mapping[handle] = row
            self.tree.selection_remove(*self.tree.selection())
            self.table.grid()
            self.error_var.set("")
            self.error_label.grid_remove()
            self._rows_by_iid = mapping
            self._display_valid = True
        except Exception as exc:
            self._rows_by_iid = {}
            self._display_valid = False
            for cleanup in (lambda: self.tree.selection_remove(*self.tree.selection()), self.table.grid_remove):
                try:
                    cleanup()
                except TclError:
                    pass  # A destroyed widget cannot be hidden; metadata is already invalid.
            self._show_error(f"Unable to update work history: {exc}. Table unavailable.")
            raise

    def _on_select(self, _event=None):
        for handle in self._rows_by_iid:
            if self.tree.exists(handle):
                self.tree.item(handle, tags=())
        selected = self.tree.selection()
        row = self._rows_by_iid.get(selected[0]) if selected else None
        if row is None or row["entry_kind"] != "interval":
            return
        identity = tuple(row[key] for key in ("task_id", "entry_kind", "entry_id"))
        for handle, other in self._rows_by_iid.items():
            if (handle != selected[0] and self.tree.exists(handle)
                    and tuple(other[key] for key in ("task_id", "entry_kind", "entry_id")) == identity):
                self.tree.item(handle, tags=("related",))
