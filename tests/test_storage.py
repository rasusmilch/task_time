from datetime import datetime
from pathlib import Path

from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage


def test_restart_with_running_task(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)
    service = TaskTimerService(storage)
    task_id = service.create_task("A", "note")
    service.start_task(task_id)

    service2 = TaskTimerService(EventStorage(tmp_path))
    assert service2.state.running_task_id == task_id
    assert service2.state.tasks[task_id].is_running


def test_auto_stop_prior_task_on_start(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    a = service.create_task("A", "")
    b = service.create_task("B", "")
    service.start_task(a)
    service.start_task(b)
    assert service.state.running_task_id == b
    assert not service.state.tasks[a].is_running


def test_reset_excludes_older_intervals(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("A", "")
    service.add_manual_interval(
        task_id,
        datetime(2026, 1, 1, 10, 0).astimezone(),
        datetime(2026, 1, 1, 11, 0).astimezone(),
        "missed",
    )
    before = service.task_elapsed(service.state.tasks[task_id])
    service.reset_task(task_id)
    after = service.task_elapsed(service.state.tasks[task_id])
    assert before >= 3600
    assert after == 0


def test_manual_interval_add_edit_delete(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("A", "")
    start = datetime(2026, 1, 1, 10, 0).astimezone()
    stop = datetime(2026, 1, 1, 11, 0).astimezone()
    service.add_manual_interval(task_id, start, stop, "add")
    interval_id = next(iter(service.state.tasks[task_id].intervals))
    service.edit_interval(task_id, interval_id, start, datetime(2026, 1, 1, 12, 0).astimezone(), "edit")
    new_ids = [k for k, v in service.state.tasks[task_id].intervals.items() if not v.deleted]
    assert len(new_ids) == 1
    service.delete_interval(task_id, new_ids[0], "bad")
    assert all(v.deleted for v in service.state.tasks[task_id].intervals.values())


def test_rotation_and_rebuild_multi_segments(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path, max_active_size_bytes=200, max_active_events=2)
    service = TaskTimerService(storage)
    t = service.create_task("A", "")
    service.start_task(t)
    service.stop_task(t)
    service.start_task(t)
    service.stop_task(t)

    manifest = storage.load_manifest()
    assert manifest["archives"]

    service2 = TaskTimerService(EventStorage(tmp_path, max_active_size_bytes=200, max_active_events=2))
    assert service2.state.tasks[t].intervals
