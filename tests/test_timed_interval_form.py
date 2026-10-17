"""Construct the staged form, exercise its wiring, and smoke-test real Tk separately."""

from copy import deepcopy
from datetime import date, timedelta, timezone
from pathlib import Path
import builtins
import os
import tkinter as tk
from tkinter import ttk
from zoneinfo import ZoneInfo

import pytest

from task_timer import timed_interval_form as forms
from task_timer import time_utils
from task_timer.work_entry_inputs import resolve_timed_interval_input


DAY = date(2026, 1, 12)
REPEAT = date(2026, 11, 1)
CHICAGO = ZoneInfo("America/Chicago")
FIRST = "First 01:30 (UTC-05:00)"
SECOND = "Second 01:30 (UTC-06:00)"


class Variable:
    def __init__(self, master, value=""):
        self.value = value
        self.callbacks = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = str(value)
        for callback in self.callbacks:
            callback("variable", "", "write")

    def trace_add(self, mode, callback):
        assert mode == "write"
        self.callbacks.append(callback)


class Widget:
    def __init__(self, master, **options):
        self.options = options
        self.visible = False
        self.bindings = {}
        master.widgets.append(self)

    def grid(self, **options):
        self.visible = True

    def grid_remove(self):
        self.visible = False

    def configure(self, **options):
        self.options.update(options)

    def bind(self, event, callback):
        self.bindings[event] = callback

    def select(self, label):
        assert self.visible and self.options["state"] == "readonly"
        assert label in self.options["values"]
        self.options["textvariable"].set(label)
        self.bindings["<<ComboboxSelected>>"](None)


@pytest.fixture
def make_form(monkeypatch):
    def initialise(frame, parent):
        frame.widgets = []
        frame.parent = parent
    monkeypatch.setattr(ttk.Frame, "__init__", initialise)
    monkeypatch.setattr(ttk.Frame, "grid_columnconfigure", lambda *args, **kwargs: None)
    monkeypatch.setattr(forms, "StringVar", Variable)
    for name in ("Entry", "Label", "Combobox"):
        monkeypatch.setattr(ttk, name, Widget)
    def forbidden(*args, **kwargs):
        pytest.fail("The input frame must not construct Save/mutation actions")
    monkeypatch.setattr(ttk, "Button", forbidden)
    def create(**options):
        defaults = dict(local_timezone=CHICAGO, start_date=DAY, end_date=DAY, start_time="8", end_time="9")
        return forms.TimedIntervalInputFrame(object(), **(defaults | options))
    return create


def repeated(make_form):
    return make_form(start_date=REPEAT, end_date=REPEAT, start_time="1:30", end_time="1:30")


def test_actual_constructor_initial_values_fields_and_timezone(make_form):
    end = DAY + timedelta(days=1)
    frame = make_form(end_date=end, start_time="20", end_time="8")
    assert isinstance(frame, ttk.Frame)
    assert frame.start_date_var.get() == "2026-01-12"
    assert frame.end_date_var.get() == "2026-01-13"
    assert frame.start_time_var.get() == "20" and frame.end_time_var.get() == "8"
    assert frame.timezone_label.options["text"] == "Timezone: America/Chicago"
    labels = {widget.options.get("text") for widget in frame.widgets}
    assert {"Start date", "Start time", "End date", "End time"} <= labels
    assert frame.start_date_entry.options["textvariable"] is frame.start_date_var
    assert frame.end_time_entry.options["textvariable"] is frame.end_time_var
    assert not frame.start_occurrence_selector.visible and not frame.end_occurrence_selector.visible
    assert frame.resolve_input() == resolve_timed_interval_input(DAY, "20", end, "8", CHICAGO)


@pytest.mark.parametrize("clock", ["8", "8am", "08:30", "8:30am", "13:45", " 1 : 45 PM "])
def test_ordinary_minute_formats(make_form, clock):
    frame = make_form(start_time=clock, end_time="20")
    assert frame.resolve_input() == resolve_timed_interval_input(DAY, clock, DAY, "20", CHICAGO)


@pytest.mark.parametrize("field,value", [
    ("start_time", "8:30:00"), ("end_time", "9:00:00.5"), ("start_time", "25"),
    ("end_time", ""), ("start_date", "20260112"), ("end_date", "2026-1-12"),
    ("start_date", "2026-W03-1"), ("end_date", "2026-02-30"), ("start_date", ""),
])
def test_invalid_drafts_are_retained_callbacks_do_not_raise(make_form, field, value):
    frame = make_form()
    getattr(frame, f"{field}_var").set(value)
    endpoint = field.split("_")[0]
    assert getattr(frame, f"{endpoint}_error_var").get().startswith(endpoint.title())
    assert not getattr(frame, f"{endpoint}_occurrence_selector").visible
    with pytest.raises(ValueError, match=endpoint.title()):
        frame.resolve_input()
    assert getattr(frame, f"{field}_var").get() == value
    assert frame.error_var.get()


def test_canonical_date_after_whitespace_trimming_is_not_rewritten(make_form):
    frame = make_form()
    frame.start_date_var.set(" 2026-01-12 ")
    assert frame.resolve_input()["duration_seconds"] == 3600
    assert frame.start_date_var.get() == " 2026-01-12 "


@pytest.mark.parametrize("stop", ["8", "7"])
def test_equal_reversed_endpoints_show_interval_error_without_rollover(make_form, stop):
    frame = make_form(end_time=stop)
    with pytest.raises(ValueError, match="Interval:.*after start in UTC"):
        frame.resolve_input()
    assert frame.end_time_var.get() == stop and frame.end_date_var.get() == str(DAY)


def test_gap_error_can_be_corrected_and_old_errors_clear(make_form):
    gap = date(2026, 3, 8)
    frame = make_form(start_date=gap, end_date=gap, start_time="2:30", end_time="3:30")
    assert not frame.start_occurrence_selector.visible
    with pytest.raises(ValueError, match="Start:.*does not exist"):
        frame.resolve_input()
    frame.start_time_var.set("1:30")
    assert frame.resolve_input()["duration_seconds"] == 3600
    assert not any(var.get() for var in (frame.error_var, frame.start_error_var, frame.end_error_var))


def test_repeat_choices_are_explicit_chronological_and_utc_ordered(make_form):
    frame = repeated(make_form)
    assert frame.start_occurrence_selector.options["values"] == (FIRST, SECOND)
    assert frame.end_occurrence_selector.options["values"] == (FIRST, SECOND)
    assert frame.start_occurrence_var.get() == frame.end_occurrence_var.get() == ""
    with pytest.raises(ValueError, match="Start:.*Select first or second"):
        frame.resolve_input()
    frame.start_occurrence_selector.select(FIRST)
    assert not frame.start_error_var.get()
    with pytest.raises(ValueError, match="End:.*Select first or second"):
        frame.resolve_input()
    frame.end_occurrence_selector.select(SECOND)
    assert frame.resolve_input()["duration_seconds"] == 3600
    frame.start_time_var.set("1:45")
    frame.end_time_var.set("1:15")
    frame.start_occurrence_selector.select("First 01:45 (UTC-05:00)")
    frame.end_occurrence_selector.select("Second 01:15 (UTC-06:00)")
    assert frame.resolve_input()["duration_seconds"] == 1800
    frame.start_occurrence_selector.select("Second 01:45 (UTC-06:00)")
    frame.end_occurrence_selector.select("First 01:15 (UTC-05:00)")
    with pytest.raises(ValueError, match="Interval:.*after start in UTC"):
        frame.resolve_input()


@pytest.mark.parametrize("endpoint", ["start", "end"])
@pytest.mark.parametrize("field,value,ambiguous", [
    ("date", "2026-11-02", False), ("time", "1:45", True),
    ("time", "2:30", False), ("time", "1:30:00", False), ("date", "bad", False),
])
def test_endpoint_changes_clear_only_its_choice(make_form, endpoint, field, value, ambiguous):
    frame = repeated(make_form)
    frame.start_occurrence_selector.select(FIRST)
    frame.end_occurrence_selector.select(SECOND)
    untouched = "end" if endpoint == "start" else "start"
    previous = getattr(frame, f"{untouched}_occurrence_var").get()
    getattr(frame, f"{endpoint}_{field}_var").set(value)
    assert getattr(frame, f"{endpoint}_occurrence_var").get() == ""
    assert getattr(frame, f"{endpoint}_occurrence_selector").visible is ambiguous
    assert getattr(frame, f"{untouched}_occurrence_var").get() == previous
    if not ambiguous:
        assert getattr(frame, f"{endpoint}_occurrence_selector").options["state"] == "disabled"


def test_returning_to_ambiguous_draft_never_restores_a_previous_choice(make_form):
    frame = repeated(make_form)
    frame.start_occurrence_selector.select(FIRST)
    frame.start_date_var.set("2026-11-02")
    frame.start_date_var.set(str(REPEAT))
    assert frame.start_occurrence_selector.visible and frame.start_occurrence_var.get() == ""


def test_non_hour_transition_offsets_and_fixed_timezone_label(make_form):
    frame = make_form(local_timezone=ZoneInfo("Australia/Lord_Howe"),
                      start_date=date(2026, 4, 5), end_date=date(2026, 4, 5), start_time="1:45", end_time="1:45")
    choices = ("First 01:45 (UTC+11:00)", "Second 01:45 (UTC+10:30)")
    assert frame.start_occurrence_selector.options["values"] == choices
    frame.start_occurrence_selector.select(choices[0])
    frame.end_occurrence_selector.select(choices[1])
    assert frame.resolve_input()["duration_seconds"] == 1800
    fixed = make_form(local_timezone=timezone(timedelta(hours=5, minutes=30)))
    assert fixed.timezone_label.options["text"] == "Timezone: UTC+05:30"
    assert fixed.resolve_input()["duration_seconds"] == 3600


def test_every_resolve_uses_current_values_and_returns_fresh_result(make_form, monkeypatch):
    frame = make_form()
    calls = []
    def resolve(*args, **kwargs):
        calls.append((args, kwargs))
        return resolve_timed_interval_input(*args, **kwargs)
    monkeypatch.setattr(forms, "resolve_timed_interval_input", resolve)
    old = frame.resolve_input()
    saved = deepcopy(old)
    frame.end_time_var.set("10")
    current = frame.resolve_input()
    assert current["duration_seconds"] == 7200 and old == saved
    current["duration_seconds"] = -1
    assert frame.resolve_input()["duration_seconds"] == 7200
    assert len(calls) == 3 and calls[-1][0][3] == "10"


def test_construction_and_resolution_need_no_external_operations(make_form, monkeypatch, tmp_path):
    initial = dict(local_timezone=CHICAGO, start_date=DAY, end_date=DAY, start_time="8", end_time="9")
    before = deepcopy(initial)
    def forbidden(*args, **kwargs):
        pytest.fail("Form attempted clock capture, service access or persistence")
    with monkeypatch.context() as patch:
        patch.setattr(time_utils, "utc_now", forbidden)
        patch.setattr(time_utils, "detect_local_timezone", forbidden)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(os, "open", forbidden)
        for name in ("write_text", "write_bytes", "mkdir", "unlink", "rename", "replace"):
            patch.setattr(Path, name, forbidden)
        frame = make_form(**initial)
        assert frame.resolve_input()["duration_seconds"] == 3600
        frame.start_time_var.set("bad")
        with pytest.raises(ValueError):
            frame.resolve_input()
    assert initial == before and list(tmp_path.iterdir()) == []


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
        assert not callback_errors


@pytest.mark.parametrize("zone,day,seconds", [
    (CHICAGO, REPEAT, 3600), (ZoneInfo("Australia/Lord_Howe"), date(2026, 4, 5), 1800),
])
def test_real_tk_construction_callbacks_selection_and_resolution(real_root, zone, day, seconds):
    frame = forms.TimedIntervalInputFrame(real_root, local_timezone=zone, start_date=day, end_date=day)
    frame.grid()
    real_root.update_idletasks()
    assert frame.start_date_var.get() == frame.end_date_var.get() == str(day)
    frame.start_time_var.set("1:45")
    frame.end_time_var.set("1:45")
    assert frame.start_occurrence_selector.winfo_manager() == "grid"
    assert len(frame.start_occurrence_selector.cget("values")) == 2
    assert frame.start_occurrence_var.get() == ""
    frame.start_occurrence_selector.current(0)
    frame.start_occurrence_selector.event_generate("<<ComboboxSelected>>")
    frame.end_occurrence_selector.current(1)
    frame.end_occurrence_selector.event_generate("<<ComboboxSelected>>")
    real_root.update()
    assert frame.resolve_input()["duration_seconds"] == seconds
    end_choice = frame.end_occurrence_var.get()
    frame.start_date_var.set(str(day + timedelta(days=1)))
    assert frame.start_occurrence_selector.winfo_manager() == ""
    assert frame.start_occurrence_var.get() == "" and frame.end_occurrence_var.get() == end_choice
    with pytest.raises(ValueError, match="Interval"):
        frame.resolve_input()
    frame.start_date_var.set(str(day))
    assert frame.start_occurrence_var.get() == ""
    frame.start_occurrence_selector.current(0)
    frame.start_occurrence_selector.event_generate("<<ComboboxSelected>>")
    assert frame.resolve_input()["duration_seconds"] == seconds
    assert frame.error_var.get() == ""
    frame.start_time_var.set("1:45:00")
    real_root.update()
    assert frame.start_occurrence_selector.winfo_manager() == ""
    with pytest.raises(ValueError, match="Start"):
        frame.resolve_input()
    frame.start_time_var.set("1:45")
    assert frame.start_occurrence_var.get() == ""
    assert frame.end_occurrence_var.get() == end_choice
    frame.start_occurrence_selector.current(0)
    frame.start_occurrence_selector.event_generate("<<ComboboxSelected>>")
    assert frame.resolve_input()["duration_seconds"] == seconds
    assert frame.error_var.get() == frame.start_error_var.get() == ""
