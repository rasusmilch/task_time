from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from task_timer.app import TaskTimerService
from task_timer.dialogs import EditTimelineDialog, TimelineEntryResult, _TimelineTimePicker, format_timeline_row
from task_timer.storage import EventStorage


def test_edit_timeline_methods_do_not_use_chained_askstring_for_entry() -> None:
    assert "askstring" not in inspect.getsource(EditTimelineDialog._add_interval)
    assert "askstring" not in inspect.getsource(EditTimelineDialog._add_duration)
    assert "askstring" not in inspect.getsource(EditTimelineDialog._edit_selected)
    assert "askstring" not in inspect.getsource(EditTimelineDialog._fix_running)


def test_edit_timeline_dialog_includes_local_timezone_label() -> None:
    assert "Times shown in local timezone:" in inspect.getsource(EditTimelineDialog.__init__)


def test_timeline_time_picker_normalizes_tuple_output() -> None:
    picker = _TimelineTimePicker.__new__(_TimelineTimePicker)
    assert picker._render_picker_value(("9", "5", "AM")) == "09:05"


def test_format_timeline_row_same_day_local_times() -> None:
    tz = ZoneInfo("America/New_York")
    interval = SimpleNamespace(
        interval_id="i1",
        start_utc=datetime(2026, 4, 24, 12, 30, tzinfo=timezone.utc),
        stop_utc=datetime(2026, 4, 24, 14, 15, tzinfo=timezone.utc),
        source="manual",
        entry_mode="interval",
        work_date_local=None,
        duration_seconds=None,
        edit_reason="seed",
    )
    row = format_timeline_row(interval, tz)
    assert row["date"] == "2026-04-24"
    assert row["start"] == "08:30 AM"
    assert row["stop"] == "10:15 AM"


def test_format_timeline_row_cross_midnight_shows_date_context() -> None:
    tz = ZoneInfo("America/New_York")
    interval = SimpleNamespace(
        interval_id="i2",
        start_utc=datetime(2026, 4, 24, 3, 30, tzinfo=timezone.utc),
        stop_utc=datetime(2026, 4, 24, 4, 30, tzinfo=timezone.utc),
        source="manual",
        entry_mode="interval",
        work_date_local=None,
        duration_seconds=None,
        edit_reason="seed",
    )
    row = format_timeline_row(interval, tz)
    assert row["start"].startswith("2026-04-23")
    assert row["stop"].startswith("2026-04-24")


def test_format_timeline_row_duration_hides_synthetic_times() -> None:
    tz = ZoneInfo("America/New_York")
    interval = SimpleNamespace(
        interval_id="i3",
        start_utc=datetime(2026, 4, 24, 16, 0, tzinfo=timezone.utc),
        stop_utc=datetime(2026, 4, 24, 17, 0, tzinfo=timezone.utc),
        source="manual_duration",
        entry_mode="duration",
        work_date_local="2026-04-24",
        duration_seconds=3600.0,
        edit_reason="forgot timer",
    )
    row = format_timeline_row(interval, tz)
    assert row["date"] == "2026-04-24"
    assert row["start"] == "--"
    assert row["stop"] == "--"
    assert row["source"] == "manual duration"


def test_service_exposes_real_local_timezone_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("task_timer.app.detect_local_timezone", lambda: ZoneInfo("America/Chicago"))
    service = TaskTimerService(EventStorage(tmp_path))
    assert service.local_tz_name == "America/Chicago"


def test_add_interval_uses_single_dialog_result(monkeypatch) -> None:
    captured: list[tuple] = []
    dlg = EditTimelineDialog.__new__(EditTimelineDialog)
    dlg.window = SimpleNamespace()
    dlg.task_id = "task"
    dlg.changed = False
    dlg._refresh_table = lambda: None
    dlg.service = SimpleNamespace(
        add_manual_interval=lambda task_id, start, stop, reason: captured.append((task_id, start, stop, reason)),
        add_manual_duration=lambda *_args: (_ for _ in ()).throw(AssertionError("wrong method")),
    )
    monkeypatch.setattr("task_timer.dialogs.messagebox.showerror", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task_timer.dialogs.TimelineEntryDialog",
        lambda *_args, **_kwargs: SimpleNamespace(
            result=TimelineEntryResult(
                mode="start_end",
                work_date=datetime(2026, 1, 1).date(),
                start_local=datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc),
                stop_local=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
                duration_seconds=None,
                reason="seed",
            )
        ),
    )
    EditTimelineDialog._add_interval(dlg)
    assert captured and captured[0][0] == "task"


def test_add_duration_uses_single_dialog_result(monkeypatch) -> None:
    captured: list[tuple] = []
    dlg = EditTimelineDialog.__new__(EditTimelineDialog)
    dlg.window = SimpleNamespace()
    dlg.task_id = "task"
    dlg.changed = False
    dlg._refresh_table = lambda: None
    dlg.service = SimpleNamespace(
        add_manual_interval=lambda *_args: (_ for _ in ()).throw(AssertionError("wrong method")),
        add_manual_duration=lambda task_id, work_date, duration_seconds, reason: captured.append((task_id, work_date, duration_seconds, reason)),
    )
    monkeypatch.setattr("task_timer.dialogs.messagebox.showerror", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task_timer.dialogs.TimelineEntryDialog",
        lambda *_args, **_kwargs: SimpleNamespace(
            result=TimelineEntryResult(
                mode="duration",
                work_date=datetime(2026, 1, 1).date(),
                start_local=None,
                stop_local=None,
                duration_seconds=3600.0,
                reason="seed",
            )
        ),
    )
    EditTimelineDialog._add_duration(dlg)
    assert captured and captured[0][2] == 3600.0


def test_edit_selected_uses_single_dialog_result(monkeypatch) -> None:
    captured: list[tuple] = []
    interval = SimpleNamespace(
        interval_id="i1",
        start_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        stop_utc=datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc),
        entry_mode="interval",
        work_date_local=None,
        duration_seconds=None,
    )
    dlg = EditTimelineDialog.__new__(EditTimelineDialog)
    dlg.window = SimpleNamespace()
    dlg.task_id = "task"
    dlg.changed = False
    dlg._refresh_table = lambda: None
    dlg._selected_interval_id = lambda: "i1"
    dlg.service = SimpleNamespace(
        local_tz=timezone.utc,
        state=SimpleNamespace(tasks={"task": SimpleNamespace(intervals={"i1": interval})}),
        edit_interval=lambda task_id, interval_id, start, stop, reason: captured.append((task_id, interval_id, start, stop, reason)),
        edit_duration_interval=lambda *_args: (_ for _ in ()).throw(AssertionError("wrong method")),
    )
    monkeypatch.setattr("task_timer.dialogs.messagebox.showerror", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task_timer.dialogs.TimelineEntryDialog",
        lambda *_args, **_kwargs: SimpleNamespace(
            result=TimelineEntryResult(
                mode="start_end",
                work_date=datetime(2026, 1, 1).date(),
                start_local=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                stop_local=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
                duration_seconds=None,
                reason="fix",
            )
        ),
    )
    EditTimelineDialog._edit_selected(dlg)
    assert captured and captured[0][1] == "i1"


def test_fix_running_uses_single_dialog_result(monkeypatch) -> None:
    captured: list[tuple] = []
    dlg = EditTimelineDialog.__new__(EditTimelineDialog)
    dlg.window = SimpleNamespace()
    dlg.task_id = "task"
    dlg.changed = False
    dlg._refresh_table = lambda: None
    dlg.service = SimpleNamespace(
        local_tz=timezone.utc,
        state=SimpleNamespace(
            tasks={"task": SimpleNamespace(is_running=True, currently_open_interval_start_utc=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))}
        ),
        correct_running_interval_stop=lambda task_id, corrected_stop, reason: captured.append((task_id, corrected_stop, reason)),
    )
    monkeypatch.setattr("task_timer.dialogs.messagebox.showerror", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task_timer.dialogs.TimelineEntryDialog",
        lambda *_args, **_kwargs: SimpleNamespace(
            result=TimelineEntryResult(
                mode="fix_stop",
                work_date=datetime(2026, 1, 1).date(),
                start_local=None,
                stop_local=datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc),
                duration_seconds=None,
                reason="forgot",
            )
        ),
    )
    EditTimelineDialog._fix_running(dlg)
    assert captured and captured[0][0] == "task"
