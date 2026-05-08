from __future__ import annotations

import pytest

from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage


def test_create_task_with_archived_tag_creates_no_task(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    service.create_tag("alpha")
    service.archive_tag("alpha")
    before = len(service.state.tasks)
    with pytest.raises(ValueError, match="archived"):
        service.create_task("T", "", ["alpha"])
    assert len(service.state.tasks) == before


def test_create_subtask_with_archived_tag_creates_no_subtask(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("P", "")
    service.create_tag("alpha")
    service.archive_tag("alpha")
    with pytest.raises(ValueError, match="archived"):
        service.create_subtask(parent, "C", "", ["alpha"])
    assert service.child_tasks(parent) == []


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_task_name_rejected(tmp_path, name):
    service = TaskTimerService(EventStorage(tmp_path))
    with pytest.raises(ValueError, match="Task name is required"):
        service.create_task(name, "")


def test_service_missing_and_deleted_validation(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path))
    t1 = service.create_task("A", "")
    deleted = service.create_task("B", "")
    service.delete_task_only(deleted)

    for fn in [
        lambda: service.start_task("missing"),
        lambda: service.stop_task("missing"),
        lambda: service.reset_task_only("missing"),
        lambda: service.delete_task_only("missing"),
        lambda: service.update_task("missing", "x", "y"),
        lambda: service.move_task("missing", None),
        lambda: service.get_task_timeline("missing"),
    ]:
        with pytest.raises(ValueError, match="Task not found"):
            fn()

    with pytest.raises(ValueError, match="Task is deleted"):
        service.start_task(deleted)

    with pytest.raises(ValueError, match="Parent task not found"):
        service.apply_subtask_templates("missing", ["x"])

    with pytest.raises(ValueError):
        service.apply_subtask_templates(t1, ["missing-template"])
