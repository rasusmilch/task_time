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
    nested = service.create_subtask(sub, "Nested", "")
    assert service.task_depth(nested) == 2
    with pytest.raises(ValueError, match="two nested subtask levels"):
        service.create_subtask(nested, "Too deep", "")


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


def test_reset_depth_one_only_leaves_nested_child_untouched(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    child = service.create_subtask(root, "Child", "")
    nested = service.create_subtask(child, "Nested", "")
    service.start_task(child)
    service.stop_task(child)
    service.start_task(nested)
    service.stop_task(nested)

    service.reset_task_only(child)

    assert service.state.tasks[child].last_reset_utc is not None
    assert service.state.tasks[nested].last_reset_utc is None


def test_reset_depth_one_tree_resets_nested_child(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    child = service.create_subtask(root, "Child", "")
    nested = service.create_subtask(child, "Nested", "")
    service.start_task(child)
    service.stop_task(child)
    service.start_task(nested)
    service.stop_task(nested)

    service.reset_task_tree(child)

    assert service.state.tasks[child].last_reset_utc is not None
    assert service.state.tasks[nested].last_reset_utc is not None


def test_delete_tree_depth_coverage(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    child = service.create_subtask(root, "Child", "")
    nested = service.create_subtask(child, "Nested", "")

    service.delete_task_tree(child)

    assert service.state.tasks[root].is_deleted is False
    assert service.state.tasks[child].is_deleted is True
    assert service.state.tasks[nested].is_deleted is True


def test_delete_depth_two_only_deletes_itself(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    child = service.create_subtask(root, "Child", "")
    nested = service.create_subtask(child, "Nested", "")

    service.delete_task_only(nested)

    assert service.state.tasks[root].is_deleted is False
    assert service.state.tasks[child].is_deleted is False
    assert service.state.tasks[nested].is_deleted is True


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
    service.add_manual_interval(
        parent, start_local=start_parent, stop_local=stop_parent, reason="p"
    )
    service.add_manual_interval(
        child, start_local=start_child, stop_local=stop_child, reason="c"
    )
    assert service.task_own_elapsed(parent) == 3600
    assert service.task_own_elapsed(child) == 1800
    assert service.task_tree_elapsed(parent) == 5400


def test_move_task_root_to_subtask_and_preserve_data(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "parent")
    task = service.create_task("Task", "notes", ["A"])
    start = datetime(2026, 1, 2, 9, 0, tzinfo=service.local_tz)
    stop = datetime(2026, 1, 2, 10, 0, tzinfo=service.local_tz)
    service.add_manual_interval(task, start, stop, "work")
    service.move_task(task, parent, "organize")

    moved = service.state.tasks[task]
    assert moved.parent_task_id == parent
    assert moved.task_id == task
    assert moved.notes == "notes"
    assert "a" in moved.tags
    assert service.task_own_elapsed(task) == 3600


def test_move_subtask_promote_and_reparent(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    p1 = service.create_task("P1", "")
    p2 = service.create_task("P2", "")
    child = service.create_subtask(p1, "Child", "")
    service.move_task(child, None)
    assert service.state.tasks[child].parent_task_id is None
    service.move_task(child, p2)
    assert service.state.tasks[child].parent_task_id == p2


def test_move_task_validation_errors(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    p1 = service.create_task("P1", "")
    p2 = service.create_task("P2", "")
    child = service.create_subtask(p1, "Child", "")

    with pytest.raises(ValueError, match="Task not found"):
        service.move_task("missing", p1)
    service.delete_task(child)
    with pytest.raises(ValueError, match="Task is deleted"):
        service.move_task(child, p2)

    child2 = service.create_subtask(p1, "Child2", "")
    with pytest.raises(ValueError, match="under itself or one of its descendants"):
        service.move_task(child2, child2)
    with pytest.raises(ValueError, match="Parent task not found"):
        service.move_task(child2, "missing")

    service.delete_task(p2)
    with pytest.raises(ValueError, match="under a deleted task"):
        service.move_task(child2, p2)

    nested_parent = service.create_subtask(child2, "Nested", "")
    with pytest.raises(ValueError, match="nested subtask"):
        service.move_task(p1, nested_parent)


def test_move_root_with_children_under_root_allowed(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    p1 = service.create_task("P1", "")
    p2 = service.create_task("P2", "")
    child = service.create_subtask(p1, "Child", "")
    service.move_task(p1, p2)
    assert service.state.tasks[p1].parent_task_id == p2
    assert service.state.tasks[child].parent_task_id == p1


def test_move_event_replays_and_snapshot(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    p1 = service.create_task("P1", "")
    p2 = service.create_task("P2", "")
    child = service.create_subtask(p1, "Child", "")
    service.move_task(child, p2)
    snap = service.snapshot_dict()
    assert snap["tasks"][child]["parent_task_id"] == p2

    rebuilt = TaskTimerService(EventStorage(tmp_path))
    assert rebuilt.state.tasks[child].parent_task_id == p2


def test_move_appends_event_without_rewriting_task_created(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    child = service.create_task("Child", "")
    before = list(service.storage.iter_all_events())
    created_before = [
        e for e in before if e["event_type"] == "task_created" and e["task_id"] == child
    ]
    service.move_task(child, parent)
    after = list(service.storage.iter_all_events())
    created_after = [
        e for e in after if e["event_type"] == "task_created" and e["task_id"] == child
    ]
    moved_after = [
        e for e in after if e["event_type"] == "task_moved" and e["task_id"] == child
    ]
    assert len(created_before) == 1
    assert len(created_after) == 1
    assert len(moved_after) == 1


def test_ancestor_descendant_and_direct_child_helpers(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    sub = service.create_subtask(root, "Sub", "")
    nested = service.create_subtask(sub, "Nested", "")

    ancestors = service.ancestor_tasks(nested)
    assert [t.task_id for t in ancestors] == [sub, root]
    descendants = service.descendant_tasks(root)
    assert [t.task_id for t in descendants] == [sub, nested]
    direct = service.direct_child_tasks(root)
    assert [t.task_id for t in direct] == [sub]


def test_delete_and_reset_tree_with_nested_subtasks(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    sub = service.create_subtask(root, "Sub", "")
    nested = service.create_subtask(sub, "Nested", "")

    service.delete_task_tree(sub)
    assert service.state.tasks[sub].is_deleted is True
    assert service.state.tasks[nested].is_deleted is True
    assert service.state.tasks[root].is_deleted is False

    root2 = service.create_task("Root2", "")
    sub2 = service.create_subtask(root2, "Sub2", "")
    nested2 = service.create_subtask(sub2, "Nested2", "")
    service.reset_task_tree(root2)
    assert service.state.tasks[root2].last_reset_utc is not None
    assert service.state.tasks[sub2].last_reset_utc is not None
    assert service.state.tasks[nested2].last_reset_utc is not None


def test_task_tree_elapsed_includes_nested_descendants(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    sub = service.create_subtask(root, "Sub", "")
    nested = service.create_subtask(sub, "Nested", "")

    service.add_manual_interval(
        root,
        datetime(2026, 1, 1, 9, 0, tzinfo=service.local_tz),
        datetime(2026, 1, 1, 10, 0, tzinfo=service.local_tz),
        "r",
    )
    service.add_manual_interval(
        sub,
        datetime(2026, 1, 1, 10, 0, tzinfo=service.local_tz),
        datetime(2026, 1, 1, 10, 30, tzinfo=service.local_tz),
        "s",
    )
    service.add_manual_interval(
        nested,
        datetime(2026, 1, 1, 10, 30, tzinfo=service.local_tz),
        datetime(2026, 1, 1, 10, 45, tzinfo=service.local_tz),
        "n",
    )

    assert service.task_tree_elapsed(root) == 6300
    assert service.task_tree_elapsed(sub) == 2700
    assert service.task_tree_elapsed(nested) == 900


def test_start_nested_subtask_stops_running_task(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    sub = service.create_subtask(root, "Sub", "")
    nested = service.create_subtask(sub, "Nested", "")
    other = service.create_task("Other", "")
    service.start_task(other)
    service.start_task(nested)
    assert service.state.running_task_id == nested
    assert service.state.tasks[other].is_running is False


def test_move_root_with_depth2_descendants_under_root_blocked(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    p1 = service.create_task("P1", "")
    p2 = service.create_task("P2", "")
    sub = service.create_subtask(p1, "Sub", "")
    service.create_subtask(sub, "Nested", "")
    with pytest.raises(ValueError, match="two-level subtask limit"):
        service.move_task(p1, p2)


def test_move_subtask_with_nested_children_and_promotions(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    p1 = service.create_task("P1", "")
    p2 = service.create_task("P2", "")
    sub = service.create_subtask(p1, "Sub", "")
    nested = service.create_subtask(sub, "Nested", "")
    service.move_task(sub, p2)
    assert service.state.tasks[sub].parent_task_id == p2
    assert service.state.tasks[nested].parent_task_id == sub
    service.move_task(sub, None)
    assert service.state.tasks[sub].parent_task_id is None
    service.move_task(nested, None)
    assert service.state.tasks[nested].parent_task_id is None


def test_move_nested_subtask_under_root_and_depth1_subtask(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    a = service.create_task("A", "")
    b = service.create_task("B", "")
    sub = service.create_subtask(a, "Sub", "")
    nested = service.create_subtask(sub, "Nested", "")
    service.move_task(nested, b)
    assert service.state.tasks[nested].parent_task_id == b
    other_sub = service.create_subtask(a, "OtherSub", "")
    service.move_task(nested, other_sub)
    assert service.state.tasks[nested].parent_task_id == other_sub


def test_move_under_descendant_blocked_and_invalid_replay_ignored(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    sub = service.create_subtask(root, "Sub", "")
    nested = service.create_subtask(sub, "Nested", "")
    with pytest.raises(ValueError, match="nested subtask"):
        service.move_task(root, nested)

    service._append(
        root, "task_moved", {"old_parent_task_id": None, "new_parent_task_id": nested}
    )
    rebuilt = TaskTimerService(EventStorage(tmp_path))
    assert rebuilt.state.tasks[root].parent_task_id is None


def test_movable_parent_targets_include_depth1_only_when_valid(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    r1 = service.create_task("R1", "")
    r2 = service.create_task("R2", "")
    sub = service.create_subtask(r1, "Sub", "")
    nested = service.create_subtask(sub, "Nested", "")
    targets = {t.task_id for t in service.movable_parent_targets(nested)}
    assert r1 in targets and r2 in targets and sub in targets
    assert nested not in targets
