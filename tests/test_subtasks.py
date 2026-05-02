from datetime import datetime

import pytest

from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage


def test_parent_task_created_has_no_parent(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Parent", "notes")
    assert service.state.tasks[task_id].parent_task_id is None


def test_create_subtask_stores_parent_and_replays(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    child = service.create_subtask(parent, "Child", "", ["A"])
    assert service.state.tasks[child].parent_task_id == parent

    rebuilt = TaskTimerService(EventStorage(tmp_path))
    assert rebuilt.state.tasks[child].parent_task_id == parent
    assert rebuilt.child_tasks(parent)[0].task_id == child


def test_snapshot_includes_parent_task_id(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    child = service.create_subtask(parent, "C", "")
    snap = service.snapshot_dict()
    assert snap["tasks"][child]["parent_task_id"] == parent


def test_create_subtask_parent_validation(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    child = service.create_subtask(parent, "C", "")
    service.delete_task(child)
    with pytest.raises(ValueError):
        service.create_subtask("missing", "X", "")
    service.delete_task(parent)
    with pytest.raises(ValueError):
        service.create_subtask(parent, "X", "")
    root = service.create_task("Root", "")
    sub = service.create_subtask(root, "Sub", "")
    with pytest.raises(ValueError):
        service.create_subtask(sub, "Too deep", "")


def test_delete_parent_deletes_subtasks_but_child_delete_keeps_parent(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    child = service.create_subtask(parent, "C", "")
    service.delete_task(child)
    assert service.state.tasks[parent].is_deleted is False

    parent2 = service.create_task("P2", "")
    child2 = service.create_subtask(parent2, "C2", "")
    service.delete_task(parent2)
    assert service.state.tasks[parent2].is_deleted is True
    assert service.state.tasks[child2].is_deleted is True


def test_reset_task_tree_resets_parent_and_subtasks(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    child = service.create_subtask(parent, "C", "")
    service.start_task(parent)
    service.stop_task(parent)
    service.start_task(child)
    service.stop_task(child)
    service.reset_task_tree(parent)
    assert service.state.tasks[parent].last_reset_utc is not None
    assert service.state.tasks[child].last_reset_utc is not None


def test_start_subtask_preserves_one_running_invariant(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    child = service.create_subtask(parent, "C", "")
    other = service.create_task("Other", "")
    service.start_task(parent)
    service.start_task(child)
    assert service.state.running_task_id == child
    assert service.state.tasks[parent].is_running is False
    service.start_task(other)
    assert service.state.running_task_id == other
    running = [t.task_id for t in service.state.tasks.values() if t.is_running]
    assert running == [other]


def test_task_tree_elapsed_and_own_elapsed(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    child = service.create_subtask(parent, "C", "")
    start_parent = datetime(2026, 1, 1, 10, 0, tzinfo=service.local_tz)
    stop_parent = datetime(2026, 1, 1, 11, 0, tzinfo=service.local_tz)
    start_child = datetime(2026, 1, 1, 11, 0, tzinfo=service.local_tz)
    stop_child = datetime(2026, 1, 1, 11, 30, tzinfo=service.local_tz)
    service.add_manual_interval(parent, start_local=start_parent, stop_local=stop_parent, reason="p")
    service.add_manual_interval(child, start_local=start_child, stop_local=stop_child, reason="c")
    assert service.task_own_elapsed(parent) == 3600
    assert service.task_own_elapsed(child) == 1800
    assert service.task_tree_elapsed(parent) == 5400
