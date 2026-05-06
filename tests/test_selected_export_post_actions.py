from datetime import datetime, timezone

from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage


def _local(dt: str):
    return datetime.strptime(dt, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).astimezone()


def test_reset_and_delete_selected_tasks_are_scoped_and_append_only(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    t1 = service.create_task("AS-1", "selected")
    t2 = service.create_task("AS-2", "other")
    service.add_manual_interval(t1, _local("2026-01-01 10:00"), _local("2026-01-01 11:00"), "seed")
    service.add_manual_interval(t2, _local("2026-01-01 10:00"), _local("2026-01-01 11:00"), "seed")

    pre_events = len(service.events)
    service.reset_selected_tasks([t1])
    assert any(e["task_id"] == t1 and e["event_type"] == "reset" for e in service.events)
    assert not any(e["task_id"] == t2 and e["event_type"] == "reset" for e in service.events[pre_events:])
    assert not any(e["event_type"] == "export_checkpoint" for e in service.events[pre_events:])

    before_delete = len(service.events)
    service.delete_selected_tasks([t1])
    assert any(e["task_id"] == t1 and e["event_type"] == "task_deleted" for e in service.events[before_delete:])
    assert not any(e["task_id"] == t2 and e["event_type"] == "task_deleted" for e in service.events[before_delete:])
    assert service.state.tasks[t1].is_deleted is True
    assert service.state.tasks[t2].is_deleted is False


def test_delete_selected_tasks_parent_and_subtask_scope(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    child = service.create_subtask(parent, "Child", "")
    sibling = service.create_task("Sibling", "")

    affected_parent = service.delete_selected_tasks([parent])
    assert set(affected_parent) == {parent, child}
    assert service.state.tasks[parent].is_deleted is True
    assert service.state.tasks[child].is_deleted is True
    assert service.state.tasks[sibling].is_deleted is False


def test_delete_selected_tasks_subtask_only(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    child = service.create_subtask(parent, "Child", "")

    affected = service.delete_selected_tasks([child])
    assert affected == [child]
    assert service.state.tasks[parent].is_deleted is False
    assert service.state.tasks[child].is_deleted is True


def test_reset_selected_tasks_returns_only_changed_and_keeps_task(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    child = service.create_subtask(parent, "Child", "")

    affected = service.reset_selected_tasks([parent])
    assert set(affected) == {parent, child}
    assert service.state.tasks[parent].is_deleted is False
    assert service.state.tasks[child].is_deleted is False
    assert any(e["task_id"] == parent and e["event_type"] == "reset" for e in service.events)
    assert any(e["task_id"] == child and e["event_type"] == "reset" for e in service.events)
