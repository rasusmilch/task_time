from datetime import datetime
from pathlib import Path

from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage


def test_export_contains_corrections_notes_resets(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task A", "hello")
    start = datetime(2026, 1, 1, 10, 0).astimezone()
    stop = datetime(2026, 1, 1, 11, 0).astimezone()
    service.add_manual_interval(task_id, start, stop, "forgot")
    interval_id = next(iter(service.state.tasks[task_id].intervals))
    service.edit_interval(task_id, interval_id, start, datetime(2026, 1, 1, 12, 0).astimezone(), "fix")
    service.reset_task(task_id)

    output = tmp_path / "out.txt"
    service.export_report(output, reset_after=False)
    text = output.read_text(encoding="utf-8")
    assert "Task A" in text
    assert "hello" in text
    assert "interval_edited" in text
    assert "reset" in text
    assert "Source segments" in text


def test_export_no_reset_leaves_totals(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task A", "")
    service.add_manual_interval(
        task_id,
        datetime(2026, 1, 1, 10, 0).astimezone(),
        datetime(2026, 1, 1, 11, 0).astimezone(),
        "x",
    )
    before = service.task_elapsed(service.state.tasks[task_id])
    service.export_report(tmp_path / "a.txt", reset_after=False)
    after = service.task_elapsed(service.state.tasks[task_id])
    assert before == after


def test_export_yes_reset_new_zero_point(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task A", "")
    service.add_manual_interval(
        task_id,
        datetime(2026, 1, 1, 10, 0).astimezone(),
        datetime(2026, 1, 1, 11, 0).astimezone(),
        "x",
    )
    service.export_report(tmp_path / "a.txt", reset_after=True)
    assert service.task_elapsed(service.state.tasks[task_id]) == 0
