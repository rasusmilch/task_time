from datetime import datetime, timedelta, timezone

import pytest

from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage


def _local(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M").astimezone()


def test_service_can_edit_and_delete_any_selected_interval_not_only_last(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task", "")
    service.add_manual_interval(task_id, _local("2026-01-02 09:00"), _local("2026-01-02 10:00"), "a")
    service.add_manual_interval(task_id, _local("2026-01-03 09:00"), _local("2026-01-03 10:00"), "b")
    sorted_ids = [i.interval_id for i in sorted(service.state.tasks[task_id].intervals.values(), key=lambda i: i.start_utc)]
    first_id = sorted_ids[0]
    second_id = sorted_ids[1]

    service.edit_interval(task_id, first_id, _local("2026-01-02 08:30"), _local("2026-01-02 09:30"), "fix")
    service.delete_interval(task_id, second_id, "wrong task")

    active = [i for i in service.state.tasks[task_id].intervals.values() if not i.deleted]
    assert len(active) == 1


def test_edit_delete_and_missed_stop_require_reason(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task", "")
    service.add_manual_interval(task_id, _local("2026-01-02 09:00"), _local("2026-01-02 10:00"), "seed")
    interval_id = next(iter(service.state.tasks[task_id].intervals))

    with pytest.raises(ValueError):
        service.edit_interval(task_id, interval_id, _local("2026-01-02 09:00"), _local("2026-01-02 10:00"), "")
    with pytest.raises(ValueError):
        service.delete_interval(task_id, interval_id, "")
    service.start_task(task_id)
    with pytest.raises(ValueError):
        service.correct_running_interval_stop(task_id, _local("2026-01-02 12:00"), "")


def test_missed_stop_correction_closes_running_interval(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task", "")
    service.start_task(task_id)
    start = service.state.tasks[task_id].currently_open_interval_start_utc
    assert start is not None

    corrected_stop = start.astimezone(service.local_tz) + timedelta(hours=2)
    service.correct_running_interval_stop(task_id, corrected_stop, "forgot stop")

    task = service.state.tasks[task_id]
    assert not task.is_running
    assert task.currently_open_interval_start_utc is None
    interval = next(iter(task.intervals.values()))
    assert interval.stop_utc == corrected_stop.astimezone(timezone.utc)


def test_checkpoint_protection_blocks_interval_corrections(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task", "")
    service._append("__app__", "export_checkpoint", {"path": "x.txt"})  # noqa: SLF001
    checkpoint = service.find_last_export_checkpoint_utc()
    assert checkpoint is not None

    before_start = (checkpoint - timedelta(hours=2)).astimezone(service.local_tz)
    before_stop = (checkpoint - timedelta(hours=1)).astimezone(service.local_tz)
    with pytest.raises(ValueError):
        service.add_manual_interval(task_id, before_start, before_stop, "old")

    service.add_manual_interval(
        task_id,
        (checkpoint + timedelta(hours=1)).astimezone(service.local_tz),
        (checkpoint + timedelta(hours=2)).astimezone(service.local_tz),
        "new",
    )
    interval_id = next(iter(service.state.tasks[task_id].intervals))

    with pytest.raises(ValueError):
        service.edit_interval(task_id, interval_id, before_start, before_stop, "move old")


def test_out_of_order_manual_events_bucket_by_interval_time_not_append_order(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task", "")
    # append a newer date first, then a prior date
    service.add_manual_interval(task_id, _local("2026-01-10 10:00"), _local("2026-01-10 11:00"), "today")
    service.add_manual_interval(task_id, _local("2026-01-09 10:00"), _local("2026-01-09 12:00"), "yesterday")

    rows = service.compute_windowed_task_totals(None, datetime(2026, 1, 11, tzinfo=timezone.utc))
    daily = dict(rows[0]["daily_totals"])
    assert daily["2026-01-09"] == 7200
    assert daily["2026-01-10"] == 3600
