from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from task_timer.app import TaskTimerService
from task_timer.models import event_dict
from task_timer.storage import EventStorage
from task_timer.time_utils import parse_utc_z


def _append_event(
    storage: EventStorage,
    *,
    event_id: str,
    timestamp_utc: str,
    task_id: str,
    event_type: str,
    payload: dict,
) -> None:
    storage.append_event(
        event_dict(
            timestamp_utc=timestamp_utc,
            local_timezone="UTC",
            task_id=task_id,
            event_type=event_type,
            payload=payload,
            event_id=event_id,
        )
    )


def _seed_windowed_history(storage: EventStorage) -> None:
    _append_event(
        storage,
        event_id="e001",
        timestamp_utc="2026-01-01T00:00:00Z",
        task_id="t1",
        event_type="task_created",
        payload={"name": "Task A", "notes": "alpha"},
    )
    _append_event(
        storage,
        event_id="e002",
        timestamp_utc="2026-01-04T12:00:00Z",
        task_id="t1",
        event_type="manual_interval_added",
        payload={
            "interval_id": "i1",
            "start_utc": "2026-01-04T10:00:00Z",
            "stop_utc": "2026-01-04T11:00:00Z",
            "reason": "pre-checkpoint",
        },
    )
    _append_event(
        storage,
        event_id="e003",
        timestamp_utc="2026-01-05T00:00:00Z",
        task_id="__app__",
        event_type="export_checkpoint",
        payload={"path": "first.txt", "generated_at_utc": "2026-01-05T00:00:00Z", "reset_after": False},
    )
    _append_event(
        storage,
        event_id="e004",
        timestamp_utc="2026-01-06T08:00:00Z",
        task_id="t1",
        event_type="task_updated",
        payload={"name": "Task A+", "notes": "beta"},
    )
    _append_event(
        storage,
        event_id="e005",
        timestamp_utc="2026-01-06T13:00:00Z",
        task_id="t1",
        event_type="manual_interval_added",
        payload={
            "interval_id": "i2",
            "start_utc": "2026-01-06T11:00:00Z",
            "stop_utc": "2026-01-06T12:30:00Z",
            "reason": "after-checkpoint",
        },
    )
    _append_event(
        storage,
        event_id="e006",
        timestamp_utc="2026-01-13T13:00:00Z",
        task_id="t1",
        event_type="manual_interval_added",
        payload={
            "interval_id": "i3",
            "start_utc": "2026-01-13T11:00:00Z",
            "stop_utc": "2026-01-13T12:00:00Z",
            "reason": "second-week",
        },
    )


def test_export_without_prior_checkpoint_uses_full_history(tmp_path: Path, monkeypatch) -> None:
    storage = EventStorage(tmp_path)
    _append_event(
        storage,
        event_id="e001",
        timestamp_utc="2026-01-01T00:00:00Z",
        task_id="t1",
        event_type="task_created",
        payload={"name": "Task A", "notes": "hello"},
    )
    _append_event(
        storage,
        event_id="e002",
        timestamp_utc="2026-01-02T12:00:00Z",
        task_id="t1",
        event_type="manual_interval_added",
        payload={
            "interval_id": "i1",
            "start_utc": "2026-01-02T10:00:00Z",
            "stop_utc": "2026-01-02T11:00:00Z",
            "reason": "forgot",
        },
    )
    service = TaskTimerService(storage)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-03T00:00:00Z"))

    output = tmp_path / "out.txt"
    service.export_report(output, reset_after=False)
    text = output.read_text(encoding="utf-8")

    assert "Beginning of recorded history" in text
    assert "2026-01-02: 01:00:00" in text


def test_export_with_prior_checkpoint_starts_after_checkpoint(tmp_path: Path, monkeypatch) -> None:
    storage = EventStorage(tmp_path)
    _seed_windowed_history(storage)
    service = TaskTimerService(storage)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-15T00:00:00Z"))

    output = tmp_path / "out.txt"
    service.export_report(output, reset_after=False)
    text = output.read_text(encoding="utf-8")

    assert "Checkpoint window start (exclusive): 2026-01-05T00:00:00Z" in text
    assert "2026-01-04: 01:00:00" not in text
    assert "2026-01-06: 01:30:00" in text


def test_successful_export_appends_new_checkpoint_event(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-10T00:00:00Z"))

    service.export_report(tmp_path / "a.txt", reset_after=False)

    checkpoints = [e for e in service.events if e["task_id"] == "__app__" and e["event_type"] == "export_checkpoint"]
    assert checkpoints
    assert checkpoints[-1]["payload"]["path"].endswith("a.txt")
    assert checkpoints[-1]["payload"]["generated_at_utc"] == "2026-01-10T00:00:00Z"


def test_export_spans_multiple_sunday_start_weeks(tmp_path: Path, monkeypatch) -> None:
    storage = EventStorage(tmp_path)
    _seed_windowed_history(storage)
    service = TaskTimerService(storage)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-16T00:00:00Z"))

    service.export_report(tmp_path / "out.txt", reset_after=False)
    text = (tmp_path / "out.txt").read_text(encoding="utf-8")

    assert "2026-01-04 to 2026-01-10" in text
    assert "2026-01-11 to 2026-01-17" in text


def test_weekly_summary_table_includes_all_weeks(tmp_path: Path, monkeypatch) -> None:
    storage = EventStorage(tmp_path)
    _seed_windowed_history(storage)
    service = TaskTimerService(storage)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-16T00:00:00Z"))

    service.export_report(tmp_path / "out.txt", reset_after=False)
    text = (tmp_path / "out.txt").read_text(encoding="utf-8")

    assert "Epicor-friendly weekly summary" in text
    assert "Task A+" in text
    assert "2026-01-04 to 2026-01-10" in text
    assert "2026-01-11 to 2026-01-17" in text


def test_per_task_daily_and_weekly_totals_are_windowed(tmp_path: Path, monkeypatch) -> None:
    storage = EventStorage(tmp_path)
    _seed_windowed_history(storage)
    service = TaskTimerService(storage)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-16T00:00:00Z"))

    service.export_report(tmp_path / "out.txt", reset_after=False)
    text = (tmp_path / "out.txt").read_text(encoding="utf-8")

    assert "2026-01-06: 01:30:00" in text
    assert "2026-01-13: 01:00:00" in text
    assert "2026-01-04: 01:00:00" not in text
    assert "Overall total since checkpoint: 02:30:00" in text


def test_state_not_present_in_export_totals(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task A", "")
    service.add_manual_interval(
        task_id,
        datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc).astimezone(),
        datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc).astimezone(),
        "x",
    )
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-02T00:00:00Z"))

    service.export_report(tmp_path / "out.txt", reset_after=False)
    text = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "State:" not in text


def test_human_readable_audit_lines_known_events(tmp_path: Path, monkeypatch) -> None:
    storage = EventStorage(tmp_path)
    _append_event(
        storage,
        event_id="e001",
        timestamp_utc="2026-01-01T08:00:00Z",
        task_id="t1",
        event_type="task_created",
        payload={"name": "Task A", "notes": "n1"},
    )
    _append_event(
        storage,
        event_id="e002",
        timestamp_utc="2026-01-01T09:00:00Z",
        task_id="t1",
        event_type="task_updated",
        payload={"name": "Task A+", "notes": "n2"},
    )
    _append_event(
        storage,
        event_id="e003",
        timestamp_utc="2026-01-01T10:00:00Z",
        task_id="t1",
        event_type="started",
        payload={},
    )
    _append_event(
        storage,
        event_id="e004",
        timestamp_utc="2026-01-01T10:30:00Z",
        task_id="t1",
        event_type="stopped",
        payload={"interval_id": "i1"},
    )
    _append_event(
        storage,
        event_id="e005",
        timestamp_utc="2026-01-01T10:45:00Z",
        task_id="t1",
        event_type="manual_interval_added",
        payload={
            "interval_id": "i2",
            "start_utc": "2026-01-01T10:00:00Z",
            "stop_utc": "2026-01-01T10:10:00Z",
            "reason": "forgot",
        },
    )
    _append_event(
        storage,
        event_id="e006",
        timestamp_utc="2026-01-01T11:00:00Z",
        task_id="t1",
        event_type="interval_edited",
        payload={
            "interval_id": "i2",
            "new_interval_id": "i3",
            "start_utc": "2026-01-01T10:01:00Z",
            "stop_utc": "2026-01-01T10:12:00Z",
            "reason": "fix",
        },
    )
    _append_event(
        storage,
        event_id="e007",
        timestamp_utc="2026-01-01T11:05:00Z",
        task_id="t1",
        event_type="interval_deleted",
        payload={"interval_id": "i3", "reason": "remove"},
    )
    _append_event(
        storage,
        event_id="e008",
        timestamp_utc="2026-01-01T11:15:00Z",
        task_id="t1",
        event_type="reset",
        payload={},
    )
    service = TaskTimerService(storage)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-01T12:00:00Z"))
    service.export_report(tmp_path / "out.txt", reset_after=False)
    text = (tmp_path / "out.txt").read_text(encoding="utf-8")

    assert "payload={" not in text
    assert 'Created task "Task A"' in text
    assert 'Updated task "Task A" to "Task A+"' in text
    assert 'Started "Task A+"' in text
    assert 'Stopped "Task A+"' in text
    assert 'Added manual interval to "Task A+"' in text
    assert 'Edited interval for "Task A+"' in text
    assert 'Deleted interval from "Task A+"' in text
    assert 'Reset task "Task A+"' in text


def test_reset_after_export_still_resets_and_keeps_checkpoint_behavior(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task A", "")
    service.add_manual_interval(
        task_id,
        datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc).astimezone(),
        datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc).astimezone(),
        "x",
    )
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-02T00:00:00Z"))

    service.export_report(tmp_path / "out.txt", reset_after=True)
    assert service.task_elapsed(service.state.tasks[task_id], parse_utc_z("2026-01-02T00:00:00Z")) == 0
    checkpoints = [e for e in service.events if e["task_id"] == "__app__" and e["event_type"] == "export_checkpoint"]
    assert checkpoints[-1]["payload"]["reset_after"] is True


def test_manual_interval_before_checkpoint_rejected(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task A", "")
    service._append("__app__", "export_checkpoint", {"path": "x.txt"})  # noqa: SLF001
    checkpoint = service.find_last_export_checkpoint_utc()
    assert checkpoint is not None
    start = checkpoint.astimezone(timezone.utc) - timedelta(hours=2)
    stop = checkpoint.astimezone(timezone.utc) - timedelta(hours=1)
    try:
        service.add_manual_interval(task_id, start.astimezone(), stop.astimezone(), "too old")
    except ValueError as exc:
        assert "active export checkpoint" in str(exc)
    else:
        raise AssertionError("Expected rejection")


def test_manual_duration_checkpoint_validation_and_audit_line(tmp_path: Path, monkeypatch) -> None:
    storage = EventStorage(tmp_path)
    service = TaskTimerService(storage)
    task_id = service.create_task("Task A", "")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-01T00:00:00Z"))
    service._append("__app__", "export_checkpoint", {"path": "x.txt"})  # noqa: SLF001
    checkpoint_date = service.find_last_export_checkpoint_utc().astimezone(service.local_tz).date()  # type: ignore[union-attr]
    with pytest.raises(ValueError):
        service.add_manual_duration(task_id, checkpoint_date - timedelta(days=1), 1800, "too old")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-10T01:00:00Z"))
    service.add_manual_duration(task_id, checkpoint_date + timedelta(days=1), 5400, "forgot timer")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-10T02:00:00Z"))
    out = tmp_path / "out.txt"
    service.export_report(out, reset_after=False)
    text = out.read_text(encoding="utf-8")
    assert "Added manual duration to" in text


def test_voiding_latest_checkpoint_reverts_to_previous(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    service._append("__app__", "export_checkpoint", {"path": "a.txt"})  # noqa: SLF001
    first = service.find_active_export_checkpoint()
    service._append("__app__", "export_checkpoint", {"path": "b.txt"})  # noqa: SLF001
    second = service.find_active_export_checkpoint()
    assert second and second["event_id"] != first["event_id"]  # type: ignore[index]
    service.void_last_export_checkpoint("forgot entry")
    active = service.find_active_export_checkpoint()
    assert active and active["event_id"] == first["event_id"]  # type: ignore[index]
