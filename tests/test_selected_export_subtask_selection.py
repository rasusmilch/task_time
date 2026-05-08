from datetime import datetime, timezone

from task_timer.service import TaskTimerService
from task_timer.storage import EventStorage


def _local(dt: str):
    return datetime.strptime(dt, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).astimezone()


def test_selected_subtask_alone_exports_only_subtask(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    child = service.create_subtask(parent, "C", "")
    service.add_manual_interval(parent, _local("2026-01-01 10:00"), _local("2026-01-01 11:00"), "p")
    service.add_manual_interval(child, _local("2026-01-01 12:00"), _local("2026-01-01 13:00"), "c")

    rows = service.compute_selected_task_totals(
        [child], None, _local("2026-01-02 00:00").astimezone(timezone.utc)
    )
    assert [r["task_id"] for r in rows] == [child]


def test_selected_parent_and_child_are_normalized_no_double_count_and_marker_records_inclusion(
    tmp_path,
) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    child = service.create_subtask(parent, "C", "")
    service.add_manual_interval(parent, _local("2026-01-01 10:00"), _local("2026-01-01 11:00"), "p")
    service.add_manual_interval(child, _local("2026-01-01 11:00"), _local("2026-01-01 12:00"), "c")

    output = tmp_path / "selected.txt"
    end = _local("2026-01-02 00:00").astimezone(timezone.utc)
    service.export_selected_tasks_report(
        output, [parent, child], None, end, mark_submitted=True, reason="done"
    )

    marker = [e for e in service.events if e["event_type"] == "time_submission_created"][-1]
    assert marker["payload"]["selected_task_ids"] == [parent]
    assert set(marker["payload"]["task_ids"]) == {parent, child}
    assert marker["payload"]["included_subtask_ids_by_parent"][parent] == [child]


def test_reset_and_delete_selected_parent_also_apply_to_subtasks(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    child = service.create_subtask(parent, "C", "")

    service.reset_selected_tasks([parent, child])
    assert service.state.tasks[parent].last_reset_utc is not None
    assert service.state.tasks[child].last_reset_utc is not None

    service.delete_selected_tasks([parent, child])
    assert service.state.tasks[parent].is_deleted is True
    assert service.state.tasks[child].is_deleted is True
