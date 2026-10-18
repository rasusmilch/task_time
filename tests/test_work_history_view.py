"""Standalone table wiring, real service rows and separate real-Tk smoke evidence."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone, tzinfo
from types import SimpleNamespace
import builtins
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from zoneinfo import ZoneInfo

import pytest

from task_timer import work_history_view as views
from task_timer import app as app_module
from task_timer.models import TaskState, IntervalRecord, DatedDurationRecord
from task_timer.work_history import build_task_work_history
from task_timer.settings import UISettingsStore
from test_mixed_accounting import setup, dated, local, MON, TUE, SAT, CUTOFF
from test_work_history import interval, capture

UTC = timezone.utc
CHICAGO = ZoneInfo("America/Chicago")


class Variable:
    def __init__(self, master, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Widget:
    def __init__(self, master, **options):
        self.options = options
        self.visible = False
        self.bindings = {}
        self.widgets = []
        if hasattr(master, "widgets"):
            master.widgets.append(self)

    def grid(self, **options):
        self.visible = True

    def grid_remove(self):
        self.visible = False

    def configure(self, **options):
        self.options.update(options)

    def bind(self, event, callback):
        self.bindings[event] = callback

    def set(self, *args):
        pass


class Tree(Widget):
    def __init__(self, master, **options):
        super().__init__(master, **options)
        self.headings, self.columns, self.rows, self.tags = {}, {}, {}, {}
        self.chosen = ()
        self.serial = 0
        self.fail_at = None

    def heading(self, key, **options):
        self.headings[key] = options

    def column(self, key, **options):
        self.columns[key] = options

    def tag_configure(self, key, **options):
        self.tags[key] = options

    def xview(self, *args):
        pass

    def yview(self, *args):
        pass

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *handles):
        for handle in handles:
            del self.rows[handle]
        self.chosen = tuple(h for h in self.chosen if h in self.rows)

    def insert(self, parent, index, *, values):
        self.serial += 1
        if self.serial == self.fail_at:
            raise tk.TclError("injected insertion failure")
        handle = f"widget-{self.serial}"
        self.rows[handle] = {"values": values, "tags": ()}
        return handle

    def selection(self):
        return self.chosen

    def selection_remove(self, *handles):
        self.chosen = tuple(h for h in self.chosen if h not in handles)

    def choose(self, handle):
        self.chosen = (handle,)
        self.bindings["<<TreeviewSelect>>"](None)

    def exists(self, handle):
        return handle in self.rows

    def item(self, handle, option=None, **options):
        self.rows[handle].update(options)
        return self.rows[handle][option] if option else self.rows[handle]


@pytest.fixture
def make_view(monkeypatch):
    monkeypatch.setattr(ttk.Frame, "__init__", Widget.__init__)
    for name in ("grid", "grid_remove", "configure"):
        monkeypatch.setattr(ttk.Frame, name, getattr(Widget, name))
    for name in ("grid_columnconfigure", "grid_rowconfigure"):
        monkeypatch.setattr(ttk.Frame, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(views, "StringVar", Variable)
    monkeypatch.setattr(ttk, "Treeview", Tree)
    monkeypatch.setattr(ttk, "Label", Widget)
    monkeypatch.setattr(ttk, "Scrollbar", Widget)
    monkeypatch.setattr(ttk, "Style", lambda *args: SimpleNamespace(lookup=lambda *args: "TkDefaultFont"))
    monkeypatch.setattr(views.font, "Font", lambda *args, **kwargs: SimpleNamespace(configure=lambda **kw: None))
    return lambda zone=CHICAGO: views.WorkHistoryFrame(object(), local_timezone=zone)


def values(frame):
    return [frame.tree.item(h, "values") for h in frame.tree.get_children()]


def rows(s, task, **kwargs):
    return s.get_task_work_history(task, cutoff_utc=CUTOFF, **kwargs)


def projected(first, last, zone=UTC, *, cutoff=CUTOFF, running=False):
    task = TaskState("task", "Task", "", False, False, CUTOFF, CUTOFF)
    if running:
        task.is_running = True
        task.currently_open_interval_start_utc = first
    else:
        task.intervals["original"] = IntervalRecord("original", "task", first, last, "timer")
    return build_task_work_history(task, zone, cutoff_utc=cutoff, newest_first=False)


@pytest.mark.parametrize("newest_first", [True, False])
def test_real_service_mixed_order_complete_metadata_and_detachment(setup, make_view, newest_first):
    s, a, _, _, _, _ = setup
    identity = interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated_id = dated(s, a, MON, 50400.125)
    supplied = rows(s, a, newest_first=newest_first)
    before, original = capture(s), deepcopy(supplied)
    frame = make_view()
    assert isinstance(frame, ttk.Frame)
    assert frame.tree.options["selectmode"] == "browse"
    assert [frame.tree.headings[c]["text"] for c in frame.tree.options["columns"]] == [
        "", "Date", "Kind", "Start", "End / as of", "Duration"]
    frame.display_rows(supplied)
    assert list(frame._rows_by_iid.values()) == original
    assert [v[1] for v in values(frame)] == [str(r["work_date"]) for r in original]
    by_kind_date = {(r["entry_kind"], r["work_date"]): v for r, v in zip(original, values(frame))}
    assert by_kind_date["interval", MON] == ("↔", str(MON), "Timed", "20:00", f"{TUE} 00:00", "4:00")
    assert by_kind_date["interval", TUE] == ("↔", str(TUE), "Timed", "00:00", "08:00", "8:00")
    assert by_kind_date["dated_duration", MON] == ("", str(MON), "Date only", "", "", "14:00")
    assert [r["entry_id"] for r in original].count(identity) == 2
    assert dated_id in [r["entry_id"] for r in original]
    assert len(set(frame._rows_by_iid)) == 3
    assert all(h not in (identity, dated_id) for h in frame._rows_by_iid)
    supplied[0]["reason"] = "caller mutation"
    supplied.clear()
    assert list(frame._rows_by_iid.values()) == original
    assert capture(s) == before


def test_within_day_order_not_sorted_by_formatted_clocks(setup, make_view):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 10), local(s, MON, 11))
    interval(s, a, local(s, MON, 8), local(s, MON, 9))
    dated(s, a, MON, 60)
    frame = make_view()
    for direction in (True, False):
        supplied = rows(s, a, newest_first=direction)
        frame.display_rows(supplied)
        assert [v[3] for v in values(frame)] == ["08:00", "10:00", ""]
        assert list(frame._rows_by_iid.values()) == supplied


def test_filtered_portion_retains_original_identity_and_continuations(setup, make_view):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    full = rows(s, a, newest_first=False)
    one = rows(s, a, start_date=TUE, end_date=TUE)
    frame = make_view()
    frame.display_rows(one)
    retained = next(iter(frame._rows_by_iid.values()))
    assert retained == full[1]
    assert retained["original_start_utc"] == full[0]["original_start_utc"]
    assert retained["continues_before"] and not retained["continues_after"]
    assert values(frame)[0][0] == "↔"


@pytest.mark.parametrize("day,hours", [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_dst_daily_portions_preserve_elapsed_not_wall_duration(make_view, day, hours):
    first = datetime.combine(day, datetime.min.time(), CHICAGO)
    supplied = projected(first.astimezone(UTC), (first + timedelta(days=1)).astimezone(UTC), CHICAGO)
    frame = make_view()
    frame.display_rows(supplied)
    assert values(frame)[0][3:] == ("00:00", f"{day + timedelta(days=1)} 00:00", f"{hours}:00")
    assert list(frame._rows_by_iid.values()) == supplied


@pytest.mark.parametrize("zone,first,last,start,end", [
    (CHICAGO, datetime(2026, 11, 1, 6, 30, tzinfo=UTC), datetime(2026, 11, 1, 7, 30, tzinfo=UTC),
     "01:30 (UTC-05:00)", "01:30 (UTC-06:00)"),
    (ZoneInfo("Australia/Lord_Howe"), datetime(2026, 4, 4, 14, 45, tzinfo=UTC), datetime(2026, 4, 4, 15, 15, tzinfo=UTC),
     "01:45 (UTC+11:00)", "01:45 (UTC+10:30)"),
    (timezone(timedelta(hours=5, minutes=45)), datetime(2026, 10, 12, 2, 15, tzinfo=UTC),
     datetime(2026, 10, 12, 3, 15, tzinfo=UTC), "08:00", "09:00"),
])
def test_repeated_hour_offsets_and_fixed_nonhour_zone(make_view, zone, first, last, start, end):
    supplied = projected(first, last, zone)
    frame = make_view(zone)
    frame.display_rows(supplied)
    assert values(frame)[0][3:5] == (start, end)
    assert list(frame._rows_by_iid.values()) == supplied


def test_running_cutoff_kind_and_boundary_not_recorded_stop(setup, make_view):
    s, a, _, _, _, clock = setup
    clock[0] = local(s, MON, 20).astimezone(UTC)
    s.start_task(a)
    cutoff = local(s, TUE, 8).astimezone(UTC)
    supplied = s.get_task_work_history(a, cutoff_utc=cutoff, newest_first=False)
    before = capture(s)
    frame = make_view()
    frame.display_rows(supplied)
    assert [v[2] for v in values(frame)] == ["Running", "Running"]
    assert values(frame)[-1][4] == "08:00"
    assert all(r["original_stop_utc"] is None and r["entry_id"] == "__open__" for r in frame._rows_by_iid.values())
    assert frame.tree.headings["end"]["text"] == "End / as of"
    assert capture(s) == before


@pytest.mark.parametrize("seconds,text", [(0.000001, "<1 min"), (59.999, "<1 min"),
    (60, "0:01"), (119.9, "0:01"), (120, "0:02"), (50400.125, "14:00"), (3600000, "1000:00"),
    (1e20, "27777777777777777:46")])
def test_duration_display_does_not_change_precise_dated_amount(setup, make_view, seconds, text):
    s, a, _, _, _, _ = setup
    dated(s, a, SAT, seconds)
    supplied = rows(s, a)
    frame = make_view()
    frame.display_rows(supplied)
    assert values(frame)[0][-1] == text
    assert next(iter(frame._rows_by_iid.values()))["duration_seconds"] == seconds


def test_zero_display_from_pure_projection_without_creating_invalid_lifecycle_work(make_view):
    task = TaskState("task", "Task", "", False, False, CUTOFF, CUTOFF)
    task.dated_durations["zero"] = DatedDurationRecord("zero", "task", SAT, 0, "Zero fixture",
                                                      CUTOFF, CUTOFF, "zero")
    supplied = build_task_work_history(task, UTC, cutoff_utc=CUTOFF)
    frame = make_view(UTC)
    frame.display_rows(supplied)
    assert values(frame)[0][-1] == "0:00"
    assert list(frame._rows_by_iid.values()) == supplied


def test_subminute_interval_keeps_seconds_without_using_clock_difference(make_view):
    first = datetime(2026, 10, 12, 8, 0, 17, 123456, tzinfo=UTC)
    supplied = projected(first, first + timedelta(seconds=1.123456))
    frame = make_view(UTC)
    frame.display_rows(supplied)
    assert values(frame)[0][3:] == ("08:00", "08:00", "<1 min")
    assert next(iter(frame._rows_by_iid.values())) == supplied[0]


def test_related_selection_is_visual_only_and_scoped_by_task_and_kind(setup, make_view):
    s, a, b, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated(s, a, MON, 60)
    supplied = rows(s, a, newest_first=False)
    # A different task with the same transient sentinel must not link.
    running = projected(local(s, MON, 20).astimezone(UTC), None, CHICAGO,
                        cutoff=local(s, TUE, 8).astimezone(UTC), running=True)
    for r in running:
        r["task_id"] = a
    other_task = deepcopy(running[0])
    other_task["task_id"] = b
    supplied += running + [other_task]
    frame = make_view()
    frame.display_rows(supplied)
    handles = list(frame._rows_by_iid)
    before = deepcopy(frame._rows_by_iid), capture(s)
    frame.tree.choose(handles[0])
    linked = [h for h in handles if frame.tree.item(h, "tags") == ("related",)]
    assert linked == [handles[2]] and frame.tree.selection() == (handles[0],)
    frame.tree.choose(handles[3])
    assert [h for h in handles if frame.tree.item(h, "tags")] == [handles[4]]
    assert frame.tree.selection() == (handles[3],)
    frame.tree.choose(handles[1])  # dated row clears all related feedback
    assert all(not frame.tree.item(h, "tags") for h in handles)
    frame.tree.choose("stale-handle")
    assert all(not frame.tree.item(h, "tags") for h in handles)
    assert (frame._rows_by_iid, capture(s)) == before


def test_replacement_empty_and_stale_selection_remove_obsolete_metadata(setup, make_view):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    frame = make_view()
    frame.display_rows(rows(s, a))
    old = frame._rows_by_iid.copy()
    frame.tree.choose(next(iter(old)))
    frame.display_rows(rows(s, a, start_date=TUE, end_date=TUE))
    assert not old.keys() & frame._rows_by_iid.keys()
    assert len(frame._rows_by_iid) == 1 and not frame.tree.selection()
    frame.tree.choose(next(iter(old)))
    assert all(not frame.tree.item(h, "tags") for h in frame._rows_by_iid)
    frame.display_rows([])
    assert frame.tree.get_children() == () and frame._rows_by_iid == {}
    assert frame.error_var.get() == "" and frame.table.visible


@pytest.mark.parametrize("change", [
    {"entry_kind": "duration"}, {"duration_seconds": -1}, {"duration_seconds": True},
    {"duration_seconds": float("nan")}, {"duration_seconds": float("inf")}, {"duration_seconds": "60"},
    {"segment_start_utc": None}, {"segment_stop_utc": datetime(2026, 10, 12)},
    {"segment_stop_utc": datetime.max.replace(tzinfo=UTC)}, {"work_date": "2026-10-12"},
    {"continues_after": 1}, {"original_stop_utc": None}, {"entry_id": None},
])
def test_malformed_later_row_preserves_successful_rows_and_shows_error(make_view, change):
    supplied = projected(datetime(2026, 10, 12, 8, tzinfo=UTC), datetime(2026, 10, 12, 9, tzinfo=UTC))
    frame = make_view(timezone(timedelta(hours=5, minutes=30)))
    frame.display_rows(supplied)
    before = deepcopy(frame._rows_by_iid), deepcopy(frame.tree.rows)
    bad = deepcopy(supplied[0])
    bad.update(change)
    with pytest.raises((ValueError, OverflowError)):
        frame.display_rows(supplied + [bad])
    assert (frame._rows_by_iid, frame.tree.rows) == before
    assert frame.table.visible and frame.error_label.visible
    assert "Previous results remain" in frame.error_var.get()
    frame.display_rows(supplied)
    assert frame.error_var.get() == "" and not frame.error_label.visible


def test_missing_field_fails_without_omission(make_view):
    supplied = projected(datetime(2026, 10, 12, 8, tzinfo=UTC), datetime(2026, 10, 12, 9, tzinfo=UTC))
    del supplied[0]["source"]
    frame = make_view()
    with pytest.raises(ValueError, match="missing"):
        frame.display_rows(supplied)
    assert frame._rows_by_iid == {} and frame.error_label.visible


def test_widget_failure_invalidates_partial_display_and_explicit_render_recovers(setup, make_view):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    supplied = rows(s, a)
    frame = make_view()
    frame.display_rows(supplied)
    frame.tree.choose(frame.tree.get_children()[0])
    frame.tree.fail_at = frame.tree.serial + 2
    with pytest.raises(tk.TclError, match="insertion failure"):
        frame.display_rows(supplied)
    assert len(frame.tree.rows) == 1  # no transactional rollback is claimed
    assert not frame.table.visible and not frame.tree.selection()
    assert frame._rows_by_iid == {} and not frame._display_valid
    assert "Table unavailable" in frame.error_var.get() and frame.error_label.visible
    frame.tree.bindings["<<TreeviewSelect>>"](None)
    frame.tree.fail_at = None
    frame.display_rows(supplied)
    assert frame.table.visible and frame._display_valid and len(frame._rows_by_iid) == 2
    assert frame.error_var.get() == "" and not frame.error_label.visible


@pytest.mark.parametrize("zone", [None, "UTC", True, tzinfo()])
def test_invalid_timezone_rejected_before_widget_construction(make_view, zone):
    with pytest.raises(ValueError):
        make_view(zone)


def test_render_and_selection_prohibit_domain_clock_files_and_scheduling(setup, make_view, monkeypatch):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated(s, a, SAT, 50400.125)
    supplied = rows(s, a)
    before, inputs = capture(s), deepcopy(supplied)
    def forbidden(*args, **kwargs):
        pytest.fail("Table attempted service, filesystem, clock, identity, settings or scheduled work")
    with monkeypatch.context() as m:
        for name in ("get_task_work_history", "_append", "_save_snapshot",
                     "read_task_for_timed_interval_correction", "calculate_date_window", "create_backup_now"):
            m.setattr(s, name, forbidden)
        for name in ("append_event", "iter_all_events", "save_snapshot", "synchronize_journal"):
            m.setattr(s.storage, name, forbidden)
        m.setattr(app_module, "utc_now", forbidden)
        m.setattr(app_module, "uuid4", forbidden)
        m.setattr(app_module.TaskTimerService, "__init__", forbidden)
        for name in ("__init__", "load", "save"):
            m.setattr(UISettingsStore, name, forbidden)
        class NoClockMeta(type):
            def __instancecheck__(cls, value):
                return isinstance(value, datetime)
        class NoClock(datetime, metaclass=NoClockMeta):
            now = utcnow = today = staticmethod(forbidden)
        m.setattr(views, "datetime", NoClock)
        m.setattr(builtins, "open", forbidden)
        for name in ("write_text", "write_bytes", "mkdir", "unlink"):
            m.setattr(Path, name, forbidden)
        for name in ("after", "after_idle", "after_cancel"):
            m.setattr(ttk.Frame, name, forbidden)
        frame = make_view()
        frame.display_rows(supplied)
        frame.tree.choose(frame.tree.get_children()[0])
        frame.display_rows([])
    assert capture(s) == before and supplied == inputs


@pytest.fixture
def real_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Real Tk/display unavailable: {exc}")
    root.withdraw()
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    try:
        yield root
    finally:
        root.destroy()
        assert callback_errors == []


def test_real_tk_service_rows_mapping_highlights_replacement_and_error(setup, real_root, monkeypatch):
    s, a, _, _, _, _ = setup
    interval(s, a, local(s, MON, 20), local(s, TUE, 8))
    dated(s, a, SAT, 50400.125)
    supplied = rows(s, a, newest_first=False)
    before = capture(s)
    frame = views.WorkHistoryFrame(real_root, local_timezone=s.local_tz)
    frame.grid()
    frame.display_rows(supplied)
    real_root.update()
    handles = frame.tree.get_children()
    assert list(frame._rows_by_iid.values()) == supplied
    assert frame.tree.item(handles[0], "values")[4] == f"{TUE} 00:00"
    frame.tree.selection_set(handles[0])
    real_root.update()
    assert frame.tree.selection() == (handles[0],)
    assert frame.tree.item(handles[1], "tags") == ("related",)
    assert not frame.tree.item(handles[2], "tags")
    bad = deepcopy(supplied[0])
    bad["duration_seconds"] = -1
    with pytest.raises(ValueError):
        frame.display_rows([bad])
    assert frame.tree.get_children() == handles and "Previous results remain" in frame.error_var.get()
    assert frame.error_label.winfo_manager() == "grid"
    frame.display_rows(supplied[1:])
    real_root.update()
    assert not set(handles) & set(frame.tree.get_children())
    assert list(frame._rows_by_iid.values()) == supplied[1:]
    assert not frame.tree.selection() and frame.error_var.get() == ""
    insert = frame.tree.insert
    calls = []
    def broken_insert(*args, **kwargs):
        calls.append(None)
        if len(calls) == 2:
            raise tk.TclError("injected real-widget insertion failure")
        return insert(*args, **kwargs)
    with monkeypatch.context() as m:
        m.setattr(frame.tree, "insert", broken_insert)
        with pytest.raises(tk.TclError, match="real-widget"):
            frame.display_rows(supplied)
    real_root.update()
    assert frame.table.winfo_manager() == "" and frame._rows_by_iid == {}
    assert not frame.tree.selection() and "Table unavailable" in frame.error_var.get()
    frame.display_rows(supplied)
    real_root.update()
    assert frame.table.winfo_manager() == "grid" and frame.error_var.get() == ""
    assert list(frame._rows_by_iid.values()) == supplied
    frame.display_rows([])
    real_root.update()
    assert frame.tree.get_children() == () and frame._rows_by_iid == {}
    assert capture(s) == before
