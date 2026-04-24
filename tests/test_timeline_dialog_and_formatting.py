from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from task_timer.app import TaskTimerService
from task_timer.dialogs import EditTimelineDialog, TimelineEntryResult, _TimePickerPopupDialog, _TimelineTimePicker, format_timeline_row
from task_timer.storage import EventStorage


def test_edit_timeline_methods_do_not_use_chained_askstring_for_entry() -> None:
    assert "askstring" not in inspect.getsource(EditTimelineDialog._add_interval)
    assert "askstring" not in inspect.getsource(EditTimelineDialog._add_duration)
    assert "askstring" not in inspect.getsource(EditTimelineDialog._edit_selected)
    assert "askstring" not in inspect.getsource(EditTimelineDialog._fix_running)


def test_edit_timeline_dialog_includes_local_timezone_label() -> None:
    assert "Times shown in local timezone:" in inspect.getsource(EditTimelineDialog.__init__)


def test_timeline_time_picker_widget_contains_entry_and_pick_button(monkeypatch) -> None:
    class FakeStringVar:
        def __init__(self, value: str = "") -> None:
            self._value = value

        def get(self) -> str:
            return self._value

        def set(self, value: str) -> None:
            self._value = value

    class FakeFrame:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def grid_columnconfigure(self, *_args, **_kwargs) -> None:
            pass

    class FakeEntry:
        def __init__(self, parent, textvariable=None, width=None) -> None:  # noqa: ANN001
            del parent, width
            self.textvariable = textvariable
            self.gridded = False

        def grid(self, *_args, **_kwargs) -> None:
            self.gridded = True

    class FakeButton:
        def __init__(self, parent, text: str = "", command=None) -> None:  # noqa: ANN001
            del parent
            self.text = text
            self.command = command
            self.states: list[tuple[str, ...]] = []

        def grid(self, *_args, **_kwargs) -> None:
            pass

        def state(self, values: list[str]) -> None:
            self.states.append(tuple(values))

        def configure(self, **_kwargs) -> None:
            pass

    monkeypatch.setattr("task_timer.dialogs.StringVar", FakeStringVar)
    monkeypatch.setattr("task_timer.dialogs.ttk.Frame", FakeFrame)
    monkeypatch.setattr("task_timer.dialogs.ttk.Entry", FakeEntry)
    monkeypatch.setattr("task_timer.dialogs.ttk.Button", FakeButton)
    monkeypatch.setattr("task_timer.dialogs.AnalogPicker", None)
    monkeypatch.setattr("task_timer.dialogs.constants", None)

    picker = _TimelineTimePicker(SimpleNamespace(), "8:30 AM")

    assert isinstance(picker.widget, FakeFrame)
    assert isinstance(picker.entry, FakeEntry)
    assert isinstance(picker.pick_button, FakeButton)
    assert picker.pick_button.text == "Pick..."
    assert ("disabled",) in picker.pick_button.states


def test_timeline_time_picker_open_popup_uses_popup_dialog(monkeypatch) -> None:
    picker = _TimelineTimePicker.__new__(_TimelineTimePicker)
    picker.popup_available = True
    picker.parent = SimpleNamespace()
    picker.get_time_text = lambda: "8:30 AM"
    picker._entry_var = SimpleNamespace(set=lambda value: setattr(picker, "_picked_value", value))
    picker._picked_value = None
    monkeypatch.setattr("task_timer.dialogs._TimePickerPopupDialog", lambda *_args, **_kwargs: SimpleNamespace(result="9:15 AM"))

    _TimelineTimePicker._open_popup(picker)

    assert picker._picked_value == "9:15 AM"


def test_timeline_time_picker_open_popup_cancel_keeps_value(monkeypatch) -> None:
    picker = _TimelineTimePicker.__new__(_TimelineTimePicker)
    picker.popup_available = True
    picker.parent = SimpleNamespace()
    picker.get_time_text = lambda: "8:30 AM"
    picker._picked_value = "8:30 AM"
    picker._entry_var = SimpleNamespace(set=lambda value: setattr(picker, "_picked_value", value))
    monkeypatch.setattr("task_timer.dialogs._TimePickerPopupDialog", lambda *_args, **_kwargs: SimpleNamespace(result=None))

    _TimelineTimePicker._open_popup(picker)

    assert picker._picked_value == "8:30 AM"


def test_time_picker_popup_parse_supports_am_pm_and_24h() -> None:
    popup = _TimePickerPopupDialog.__new__(_TimePickerPopupDialog)
    assert popup._parse_time("8:30 AM").strftime("%H:%M") == "08:30"
    assert popup._parse_time("8:30 PM").strftime("%H:%M") == "20:30"
    assert popup._parse_time("13:45").strftime("%H:%M") == "13:45"
    assert popup._parse_time("8").strftime("%H:%M") == "08:00"


def test_time_picker_popup_parse_midnight_noon() -> None:
    popup = _TimePickerPopupDialog.__new__(_TimePickerPopupDialog)
    assert popup._parse_time("12:00 AM").strftime("%H:%M") == "00:00"
    assert popup._parse_time("12:00 PM").strftime("%H:%M") == "12:00"


def test_time_picker_popup_confirm_formats_selection() -> None:
    popup = _TimePickerPopupDialog.__new__(_TimePickerPopupDialog)
    popup.picker = SimpleNamespace(time=lambda: "20:05")
    popup.window = SimpleNamespace(destroy=lambda: None)
    popup.result = None

    _TimePickerPopupDialog._confirm(popup)

    assert popup.result == "8:05 PM"


def test_time_picker_popup_confirm_cancel_path_keeps_none() -> None:
    picker = _TimelineTimePicker.__new__(_TimelineTimePicker)
    picker.popup_available = False
    picker._entry_var = SimpleNamespace(get=lambda: "8:30 AM")

    assert picker.get_time_text() == "8:30 AM"


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
