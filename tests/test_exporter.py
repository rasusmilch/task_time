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
    assert "2026-01-02: 01:00 (1.00 h)" in text


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
    assert "2026-01-06: 01:30 (1.50 h)" in text


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

    assert "2026-01-06: 01:30 (1.50 h)" in text
    assert "2026-01-13: 01:00 (1.00 h)" in text
    assert "2026-01-04: 01:00:00" not in text
    assert "Overall total since checkpoint: 02:30 (2.50 h)" in text


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


def test_tag_sections_include_disclaimer_and_non_exclusive_totals(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    alpha = service.create_task("Alpha task", "")
    beta = service.create_task("Beta task with very long name for truncation checks", "")
    gamma = service.create_task("Gamma", "")
    empty = service.create_task("No Time Task", "")
    delta = service.create_task("Delta", "")
    epsilon = service.create_task("Epsilon", "")
    service.update_task_tags(alpha, ["backend"])
    service.update_task_tags(beta, ["backend", "ops"])
    service.update_task_tags(delta, ["backend"])
    service.update_task_tags(epsilon, ["backend"])
    service.add_manual_interval(
        alpha,
        datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc).astimezone(),
        datetime(2026, 1, 5, 11, 0, tzinfo=timezone.utc).astimezone(),
        "a",
    )
    service.add_manual_interval(
        beta,
        datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc).astimezone(),
        datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc).astimezone(),
        "b",
    )
    service.add_manual_duration(gamma, datetime(2026, 1, 6, tzinfo=timezone.utc).date(), 1800, "duration")
    service.add_manual_interval(
        delta,
        datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc).astimezone(),
        datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc).astimezone(),
        "d",
    )
    service.add_manual_interval(
        epsilon,
        datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc).astimezone(),
        datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc).astimezone(),
        "e",
    )
    service.delete_task(empty)

    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-08T00:00:00Z"))
    out = tmp_path / "out.txt"
    service.export_report(out, reset_after=False)
    text = out.read_text(encoding="utf-8")

    assert "Tag totals by week" in text
    assert "Tag totals by day" in text
    assert "Tag totals are non-exclusive label totals" in text
    assert "backend" in text and "04:00 (4.00 h)" in text
    assert "ops" in text and "02:00 (2.00 h)" in text
    assert "untagged" in text and "00:30 (0.50 h)" in text
    assert "Overall total since checkpoint: 04:00:00" not in text
    assert "No Time Task" not in text
    assert "Beta task with very long name" in text
    assert "+" in text and "more" in text


def test_tag_totals_respect_checkpoint_reset_deleted_and_interval_edits(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Edited Task", "")
    service.update_task_tags(task_id, ["tag1"])
    service.add_manual_interval(
        task_id,
        datetime(2026, 1, 4, 23, 30, tzinfo=timezone.utc).astimezone(),
        datetime(2026, 1, 5, 0, 30, tzinfo=timezone.utc).astimezone(),
        "x",
    )
    interval_id = next(iter(service.state.tasks[task_id].intervals))
    service.edit_interval(
        task_id,
        interval_id,
        datetime(2026, 1, 4, 23, 45, tzinfo=timezone.utc).astimezone(),
        datetime(2026, 1, 5, 0, 30, tzinfo=timezone.utc).astimezone(),
        "fix",
    )
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-05T00:00:00Z"))
    service.export_report(tmp_path / "first.txt", reset_after=False)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-06T00:00:00Z"))
    service.add_manual_duration(task_id, datetime(2026, 1, 6, tzinfo=timezone.utc).date(), 3600, "d")
    service.delete_task(task_id)
    daily, weekly = service.compute_tag_totals(parse_utc_z("2026-01-05T00:00:00Z"), parse_utc_z("2026-01-08T00:00:00Z"))

    assert "2026-01-06" in daily
    assert daily["2026-01-06"]["tag1"]["seconds"] == 3600
    assert "2026-01-04" not in daily
    assert any("2026-01-04 to 2026-01-10" == wk for wk in weekly)

def test_create_time_submission_marker_appends_event_without_checkpoint_or_reset(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("A", "n")
    service.add_manual_interval(task_id, datetime(2026, 1, 10, 10, tzinfo=timezone.utc).astimezone(), datetime(2026, 1, 10, 11, tzinfo=timezone.utc).astimezone(), "r")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-31T00:00:00Z"))
    sid = service.create_time_submission_marker([task_id], None, parse_utc_z("2026-01-31T00:00:00Z"), "job closing", None)
    assert sid
    assert any(e["event_type"] == "time_submission_created" for e in service.events)
    assert not any(e["event_type"] == "export_checkpoint" and e["payload"].get("reason") == "job closing" for e in service.events)


def test_export_selected_tasks_report_mark_submitted_behavior(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    t1 = service.create_task("A", "")
    t2 = service.create_task("B", "")
    service.add_manual_interval(t1, datetime(2026, 1, 10, 10, tzinfo=timezone.utc).astimezone(), datetime(2026, 1, 10, 11, tzinfo=timezone.utc).astimezone(), "r")
    service.add_manual_interval(t2, datetime(2026, 1, 10, 12, tzinfo=timezone.utc).astimezone(), datetime(2026, 1, 10, 13, tzinfo=timezone.utc).astimezone(), "r")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: parse_utc_z("2026-01-31T00:00:00Z"))

    out = tmp_path / "selected.txt"
    service.export_selected_tasks_report(out, [t1], None, parse_utc_z("2026-01-31T00:00:00Z"), mark_submitted=False, reason="")
    text = out.read_text(encoding="utf-8")
    assert "- A" in text
    assert "- B" not in text
    assert not any(e["event_type"] == "time_submission_created" for e in service.events)

    service.export_selected_tasks_report(out, [t1], None, parse_utc_z("2026-01-31T00:00:00Z"), mark_submitted=True, reason="closing")
    assert any(e["event_type"] == "time_submission_created" for e in service.events)


def test_normal_export_marks_submitted_week(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    t1 = service.create_task("A", "")
    service.add_manual_interval(t1, datetime(2026, 1, 10, 10, tzinfo=timezone.utc).astimezone(), datetime(2026, 1, 10, 11, tzinfo=timezone.utc).astimezone(), "r")
    end = parse_utc_z("2026-12-31T00:00:00Z")
    service.create_time_submission_marker([t1], None, end, "closing", None)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    out = tmp_path / "out.txt"
    service.export_report(out, reset_after=False)
    text = out.read_text(encoding="utf-8")
    assert "* = fully already entered" in text or "~ = partially already entered" in text
    assert "01:00 (1.00 h)" in text


def test_time_submission_audit_line_human_readable(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    t1 = service.create_task("A", "")
    end = parse_utc_z("2026-12-31T00:00:00Z")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    service.create_time_submission_marker([t1], None, end, "job closing", None)
    out = tmp_path / "out.txt"
    service.export_report(out, reset_after=False)
    text = out.read_text(encoding="utf-8")
    assert "Marked selected task time as entered" in text

def test_selected_export_text_header_and_marking(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    t1 = service.create_task("A", "n")
    t2 = service.create_task("B", "n")
    service.add_manual_interval(t1, datetime(2026, 1, 10, 10, tzinfo=timezone.utc).astimezone(), datetime(2026, 1, 10, 11, tzinfo=timezone.utc).astimezone(), "r")
    service.add_manual_interval(t2, datetime(2026, 1, 11, 10, tzinfo=timezone.utc).astimezone(), datetime(2026, 1, 11, 11, tzinfo=timezone.utc).astimezone(), "r")
    end = parse_utc_z("2026-01-31T00:00:00Z")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    out = tmp_path / "selected.txt"
    service.export_selected_tasks_report(out, [t1], None, end, mark_submitted=True, reason="Job closing")
    text = out.read_text(encoding="utf-8")
    assert "Chronicle Selected Task Export" in text
    assert "This selected export was marked as already entered into Epicor." in text
    assert "Reason: Job closing" in text
    assert "- A" in text
    assert "- B" not in text
    assert "Selected task audit history" in text


def test_selected_export_audit_history_is_scoped_to_selected_tasks(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    selected = service.create_task("AS-0433-001", "selected")
    other = service.create_task("ZZ-9999-001", "other")
    service.update_task(selected, "AS-0433-001", "updated selected")
    service.update_task(other, "ZZ-9999-001", "updated other")
    service.reset_task(selected)
    service.reset_task(other)
    service.delete_task(other)
    other_active = service.create_task("ZZ-8888-001", "other active")
    service.add_manual_interval(selected, datetime(2026, 1, 10, 10, tzinfo=timezone.utc).astimezone(), datetime(2026, 1, 10, 11, tzinfo=timezone.utc).astimezone(), "sel")
    service.add_manual_interval(other, datetime(2026, 1, 10, 12, tzinfo=timezone.utc).astimezone(), datetime(2026, 1, 10, 13, tzinfo=timezone.utc).astimezone(), "other")
    end = parse_utc_z("2026-12-31T00:00:00Z")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    service.create_time_submission_marker([other_active], None, end, "unrelated", None)
    service.create_time_submission_marker([selected], None, end, "selected submission", None)

    out = tmp_path / "selected-audit.txt"
    service.export_selected_tasks_report(out, [selected], None, end, mark_submitted=True, reason="Job closing / entered into Epicor")
    text = out.read_text(encoding="utf-8")

    assert 'Reset task "AS-0433-001"' in text
    assert 'Added manual interval to "AS-0433-001"' in text
    assert 'Updated task "AS-0433-001"' in text
    assert "Marked selected task time as entered: AS-0433-001" in text
    assert "Reason: selected submission" in text

    assert 'Reset task "ZZ-9999-001"' not in text
    assert 'Deleted task "ZZ-9999-001"' not in text
    assert 'Added manual interval to "ZZ-9999-001"' not in text
    assert 'Updated task "ZZ-9999-001"' not in text
    assert "Reason: unrelated" not in text


def test_normal_export_submission_marker_legend_present(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    t1 = service.create_task("A", "")
    end = parse_utc_z("2026-01-31T00:00:00Z")
    service.add_manual_interval(t1, datetime(2026, 1, 10, 10, tzinfo=timezone.utc).astimezone(), datetime(2026, 1, 10, 14, tzinfo=timezone.utc).astimezone(), "r")
    service.create_time_submission_marker([t1], None, end, "closing", None)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    out = tmp_path / "out.txt"
    service.export_report(out, reset_after=False)
    text = out.read_text(encoding="utf-8")
    assert "* = already entered through selected-task export" in text


def test_find_submission_overlaps_cases(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    t1 = service.create_task("A", "")
    t2 = service.create_task("B", "")
    mark_end = parse_utc_z("2026-01-31T00:00:00Z")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: mark_end)
    service.create_time_submission_marker([t1], parse_utc_z("2026-01-10T00:00:00Z"), parse_utc_z("2026-01-20T00:00:00Z"), "closing", None)

    no_overlap = service.find_submission_overlaps([t1], parse_utc_z("2026-01-20T00:00:00Z"), parse_utc_z("2026-01-21T00:00:00Z"))
    assert no_overlap == []

    same_task_overlap = service.find_submission_overlaps([t1], parse_utc_z("2026-01-15T00:00:00Z"), parse_utc_z("2026-01-16T00:00:00Z"))
    assert len(same_task_overlap) == 1
    assert same_task_overlap[0]["task_id"] == t1

    different_task_overlap = service.find_submission_overlaps([t2], parse_utc_z("2026-01-15T00:00:00Z"), parse_utc_z("2026-01-16T00:00:00Z"))
    assert different_task_overlap == []


def test_global_export_includes_selected_submitted_task_even_if_deleted_or_reset(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("AS-0433-001", "EBJI63222-18")
    start = parse_utc_z("2026-05-01T00:00:00Z")
    end = parse_utc_z("2026-05-02T00:00:00Z")
    service.add_manual_interval(task_id, parse_utc_z("2026-05-01T10:00:00Z").astimezone(), parse_utc_z("2026-05-01T12:10:28Z").astimezone(), "r")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    service.create_time_submission_marker([task_id], start, end, "submit", None)
    service.reset_task(task_id)
    service.delete_task(task_id)
    out = tmp_path / "out.txt"
    service.export_report(out, reset_after=False)
    text = out.read_text(encoding="utf-8")
    assert "AS-0433-001" in text
    assert "already entered through selected export" in text
    assert "task later deleted" in text
    assert "task later reset" in text
    assert "* = already entered through selected-task export" in text


def test_time_submission_marker_stores_daily_weekly_and_overall_totals(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("A", "n")
    service.add_manual_interval(task_id, parse_utc_z("2026-01-10T10:00:00Z").astimezone(), parse_utc_z("2026-01-10T11:00:00Z").astimezone(), "r")
    end = parse_utc_z("2026-01-31T00:00:00Z")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    service.create_time_submission_marker([task_id], None, end, "closing", None)
    marker = [e for e in service.events if e["event_type"] == "time_submission_created"][-1]["payload"]
    assert marker["submitted_daily_totals_by_task"][task_id]["2026-01-10"] == 3600
    assert marker["submitted_weekly_totals_by_task"][task_id]
    assert marker["submitted_overall_totals_by_task"][task_id] == 3600

def test_parent_export_aggregates_subtasks_and_formats_decimal(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("AS-0123", "Create test for assembly")
    child1 = service.create_subtask(parent, "Create test adapter", "")
    child2 = service.create_subtask(parent, "Research specifications", "")
    service.add_manual_interval(parent, parse_utc_z("2026-01-10T10:00:00Z").astimezone(), parse_utc_z("2026-01-10T11:15:00Z").astimezone(), "p")
    service.add_manual_interval(child1, parse_utc_z("2026-01-10T11:30:00Z").astimezone(), parse_utc_z("2026-01-10T14:30:00Z").astimezone(), "c1")
    service.add_manual_interval(child2, parse_utc_z("2026-01-10T15:00:00Z").astimezone(), parse_utc_z("2026-01-10T17:10:00Z").astimezone(), "c2")
    end = parse_utc_z("2026-01-31T00:00:00Z")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    out = tmp_path / "out.txt"
    service.export_report(out, reset_after=False)
    text = out.read_text(encoding="utf-8")
    assert "06:25 (6.42 h)" in text
    assert "Parent/general: 01:15 (1.25 h)" in text
    assert "Create test adapter: 03:00 (3.00 h)" in text
    assert "Research specifications: 02:10 (2.17 h)" in text


def test_selected_parent_includes_subtasks_and_no_double_count(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    child = service.create_subtask(parent, "Child", "")
    service.add_manual_interval(parent, parse_utc_z("2026-01-10T10:00:00Z").astimezone(), parse_utc_z("2026-01-10T11:00:00Z").astimezone(), "p")
    service.add_manual_interval(child, parse_utc_z("2026-01-10T11:00:00Z").astimezone(), parse_utc_z("2026-01-10T12:00:00Z").astimezone(), "c")
    end = parse_utc_z("2026-01-31T00:00:00Z")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    out = tmp_path / "sel.txt"
    service.export_selected_tasks_report(out, [parent, child], None, end, mark_submitted=False, reason="")
    text = out.read_text(encoding="utf-8")
    assert "- Parent" in text
    assert "Selected parent tasks include their subtasks." in text
    assert "02:00 (2.00 h)" in text


def test_subtask_alone_selected_does_not_include_parent_and_inherits_parent_tags(tmp_path: Path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    child = service.create_subtask(parent, "Child", "")
    service.update_task_tags(parent, ["alpha"])
    service.update_task_tags(child, ["beta"])
    service.add_manual_interval(child, parse_utc_z("2026-01-10T11:00:00Z").astimezone(), parse_utc_z("2026-01-10T12:00:00Z").astimezone(), "c")
    end = parse_utc_z("2026-01-31T00:00:00Z")
    monkeypatch.setattr("task_timer.app.utc_now", lambda: end)
    out = tmp_path / "sel.txt"
    service.export_selected_tasks_report(out, [child], None, end, mark_submitted=False, reason="")
    text = out.read_text(encoding="utf-8")
    assert "- Child" in text and "- Parent" not in text
    service.export_report(tmp_path / "global.txt", reset_after=False)
    g = (tmp_path / "global.txt").read_text(encoding="utf-8")
    assert "alpha" in g and "beta" in g
