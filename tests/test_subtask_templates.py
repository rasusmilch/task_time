from __future__ import annotations

import zipfile

import pytest

from task_timer.app import TaskTimerService
from task_timer.backups import BackupManager
from task_timer.storage import EventStorage
from task_timer.subtask_templates import SubtaskTemplate, SubtaskTemplateItem, SubtaskTemplateStore


def test_missing_subtask_templates_file_creates_default_empty_file(tmp_path) -> None:
    store = SubtaskTemplateStore(tmp_path)
    assert not (tmp_path / "subtask_templates.json").exists()
    assert store.load() == []
    assert (tmp_path / "subtask_templates.json").exists()


def test_corrupt_subtask_templates_file_does_not_crash(tmp_path) -> None:
    path = tmp_path / "subtask_templates.json"
    path.write_text("{nope", encoding="utf-8")
    store = SubtaskTemplateStore(tmp_path)
    assert store.load() == []
    assert list(tmp_path.glob("subtask_templates.json.corrupt.*"))


def test_templates_save_load_round_trip_and_order_preserved(tmp_path) -> None:
    store = SubtaskTemplateStore(tmp_path)
    template = SubtaskTemplate(
        template_id="t1",
        name="Build flow",
        notes="n",
        items=[
            SubtaskTemplateItem(item_id="i2", name="Second", notes="", tags=[" Alpha "], sort_order=1),
            SubtaskTemplateItem(item_id="i1", name="First", notes="", tags=["Beta"], sort_order=0),
        ],
        created_at_utc="2026-01-01T00:00:00Z",
        updated_at_utc="2026-01-01T00:00:00Z",
    )
    store.save([template])
    loaded = store.load()
    assert loaded[0].items[0].name == "First"
    assert loaded[0].items[1].name == "Second"
    assert loaded[0].items[0].tags == ["beta"]
    assert loaded[0].items[1].tags == ["alpha"]


def test_empty_template_and_item_names_rejected() -> None:
    with pytest.raises(ValueError):
        SubtaskTemplate(template_id="t", name="", notes="")
    with pytest.raises(ValueError):
        SubtaskTemplateItem(item_id="i", name="", notes="", tags=[])


def test_delete_template_does_not_affect_real_tasks_or_subtasks(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    child = service.create_subtask(parent, "Child", "")
    template_id = service.create_subtask_template("Reusable", "")
    service.delete_subtask_template(template_id)
    assert service.state.tasks[parent].is_deleted is False
    assert service.state.tasks[child].is_deleted is False


def test_backup_includes_subtask_templates_file(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    service.create_subtask_template("Checklist", "")

    manager = BackupManager(tmp_path)
    backup = manager.create_backup("son", "test templates")
    with zipfile.ZipFile(backup, "r") as zf:
        assert "subtask_templates.json" in set(zf.namelist())


def test_restore_restores_subtask_templates_file(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    service.create_subtask_template("Before", "")
    manager = BackupManager(tmp_path)
    backup = manager.create_backup("son", "seed")

    (tmp_path / "subtask_templates.json").write_text('{"schema_version":1,"templates":[]}', encoding="utf-8")
    manager.restore_backup(backup)

    restored = SubtaskTemplateStore(tmp_path).load()
    assert len(restored) == 1
    assert restored[0].name == "Before"


def test_update_template_item_tags_and_order_persist(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    tid = service.create_subtask_template("T", "")
    items = [
        SubtaskTemplateItem(item_id="2", name="Two", notes="", tags=["Beta"], sort_order=0),
        SubtaskTemplateItem(item_id="1", name="One", notes="", tags=[" Alpha "], sort_order=1),
    ]
    service.update_subtask_template(tid, "T2", "n", items)
    reloaded = TaskTimerService(EventStorage(tmp_path)).get_subtask_template(tid)
    assert [i.name for i in reloaded.items] == ["Two", "One"]
    assert reloaded.items[0].tags == ["beta"]
    assert reloaded.items[1].tags == ["alpha"]
