from __future__ import annotations

import json
import zipfile

import pytest
from loguru import logger

from task_timer.service import TaskTimerService
from task_timer.backups import BackupManager
from task_timer.storage import EventStorage
from task_timer.subtask_templates import (
    SubtaskTemplate,
    SubtaskTemplateItem,
    SubtaskTemplateStore,
)


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


def test_corrupt_subtask_templates_file_logs_warning(tmp_path) -> None:
    path = tmp_path / "subtask_templates.json"
    path.write_text("{nope", encoding="utf-8")
    store = SubtaskTemplateStore(tmp_path)
    messages: list[str] = []
    sink = logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        assert store.load() == []
    finally:
        logger.remove(sink)
    assert any("Corrupt subtask template file detected" in msg for msg in messages)


@pytest.mark.parametrize(
    ("payload", "error_fragment"),
    [
        ([{"schema_version": 1}], "Payload must be a dictionary"),
        ({"schema_version": 1, "templates": "oops"}, "templates must be a list"),
        ({"schema_version": 1, "templates": ["oops"]}, "template row must be a dictionary"),
        (
            {"schema_version": 1, "templates": [{"name": "T", "items": ["oops"]}]},
            "template item row must be a dictionary",
        ),
        (
            {"schema_version": 1, "templates": [{"name": "   ", "items": []}]},
            "Template name is required",
        ),
        (
            {"schema_version": 1, "templates": [{"name": "T", "items": [{"name": "   "}]}]},
            "Template item name is required",
        ),
        (
            {
                "schema_version": 1,
                "templates": [
                    {"name": "T", "items": [{"name": "Item", "sort_order": "not-a-number"}]}
                ],
            },
            "invalid literal for int()",
        ),
    ],
)
def test_malformed_but_valid_subtask_templates_json_recovers(
    tmp_path, payload, error_fragment
) -> None:
    path = tmp_path / "subtask_templates.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    store = SubtaskTemplateStore(tmp_path)
    messages: list[str] = []
    sink = logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        loaded = store.load()
    finally:
        logger.remove(sink)

    assert loaded == []
    corrupt_files = list(tmp_path.glob("subtask_templates.json.corrupt.*"))
    assert len(corrupt_files) == 1
    assert any("Corrupt subtask template file detected" in msg for msg in messages)
    assert any(error_fragment in msg for msg in messages)

    replacement = json.loads(path.read_text(encoding="utf-8"))
    assert replacement == {"schema_version": 1, "templates": []}


def test_templates_save_load_round_trip_and_order_preserved(tmp_path) -> None:
    store = SubtaskTemplateStore(tmp_path)
    template = SubtaskTemplate(
        template_id="t1",
        name="Build flow",
        notes="n",
        items=[
            SubtaskTemplateItem(
                item_id="i2", name="Second", notes="", tags=[" Alpha "], sort_order=1
            ),
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

    (tmp_path / "subtask_templates.json").write_text(
        '{"schema_version":1,"templates":[]}', encoding="utf-8"
    )
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


def test_apply_one_template_creates_subtasks_under_parent(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    tid = service.create_subtask_template("Launch", "")
    service.update_subtask_template(
        tid,
        "Launch",
        "",
        [
            SubtaskTemplateItem(item_id="1", name="Prep", notes="n1", tags=["alpha"], sort_order=0),
            SubtaskTemplateItem(item_id="2", name="Ship", notes="n2", tags=["beta"], sort_order=1),
        ],
    )

    result = service.apply_subtask_templates(parent, [tid])
    children = service.child_tasks(parent)

    assert result.created_names == ["Prep", "Ship"]
    assert len(result.created_subtask_ids) == 2
    assert set(c.task_id for c in children) == set(result.created_subtask_ids)
    by_name = {c.name: c for c in children}
    assert set(by_name.keys()) == {"Prep", "Ship"}
    assert by_name["Prep"].notes == "n1"
    assert by_name["Ship"].notes == "n2"
    assert sorted(by_name["Prep"].tags) == ["alpha"]
    assert sorted(by_name["Ship"].tags) == ["beta"]


def test_apply_multiple_templates_preserves_selected_and_item_order(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    t1 = service.create_subtask_template("First", "")
    t2 = service.create_subtask_template("Second", "")
    service.update_subtask_template(
        t1,
        "First",
        "",
        [SubtaskTemplateItem(item_id="1", name="A", notes="", tags=[], sort_order=0)],
    )
    service.update_subtask_template(
        t2,
        "Second",
        "",
        [SubtaskTemplateItem(item_id="2", name="B", notes="", tags=[], sort_order=0)],
    )

    result = service.apply_subtask_templates(parent, [t2, t1])

    assert result.template_names == ["Second", "First"]
    assert result.created_names == ["B", "A"]


def test_apply_template_skips_duplicate_names_under_same_parent(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    service.create_subtask(parent, "Already There", "", [])
    tid = service.create_subtask_template("T", "")
    service.update_subtask_template(
        tid,
        "T",
        "",
        [
            SubtaskTemplateItem(
                item_id="1", name=" already there ", notes="", tags=[], sort_order=0
            ),
            SubtaskTemplateItem(item_id="2", name="New", notes="", tags=[], sort_order=1),
        ],
    )

    result = service.apply_subtask_templates(parent, [tid])
    assert result.skipped_duplicates == ["already there"]
    assert result.created_names == ["New"]
    assert sorted(c.name for c in service.child_tasks(parent)) == [
        "Already There",
        "New",
    ]


def test_apply_template_skips_duplicates_across_selected_templates(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    t1 = service.create_subtask_template("T1", "")
    t2 = service.create_subtask_template("T2", "")
    service.update_subtask_template(
        t1,
        "T1",
        "",
        [SubtaskTemplateItem(item_id="1", name="X", notes="", tags=[], sort_order=0)],
    )
    service.update_subtask_template(
        t2,
        "T2",
        "",
        [SubtaskTemplateItem(item_id="2", name="x", notes="", tags=[], sort_order=0)],
    )

    result = service.apply_subtask_templates(parent, [t1, t2])
    assert result.created_names == ["X"]
    assert result.skipped_duplicates == ["x"]


def test_apply_template_to_missing_deleted_or_subtask_parent_fails(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    child = service.create_subtask(parent, "Child", "")
    tid = service.create_subtask_template("T", "")

    with pytest.raises(ValueError, match="Parent task not found"):
        service.apply_subtask_templates("missing", [tid])
    service.apply_subtask_templates(child, [tid])
    nested = service.create_subtask(child, "Nested", "")
    with pytest.raises(ValueError, match="depth-2"):
        service.apply_subtask_templates(nested, [tid])
    service.delete_task(parent)
    with pytest.raises(ValueError, match="Parent task is deleted"):
        service.apply_subtask_templates(parent, [tid])


def test_apply_template_archived_tag_blocked(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    service.create_tag("alpha")
    service.archive_tag("alpha")
    tid = service.create_subtask_template("T", "")
    service.update_subtask_template(
        tid,
        "T",
        "",
        [SubtaskTemplateItem(item_id="1", name="X", notes="", tags=["alpha"], sort_order=0)],
    )

    with pytest.raises(ValueError, match="archived"):
        service.apply_subtask_templates(parent, [tid])


def test_edit_or_delete_template_later_does_not_modify_created_subtasks(
    tmp_path,
) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    parent = service.create_task("Parent", "")
    tid = service.create_subtask_template("T", "")
    service.update_subtask_template(
        tid,
        "T",
        "",
        [SubtaskTemplateItem(item_id="1", name="X", notes="n", tags=["alpha"], sort_order=0)],
    )
    service.apply_subtask_templates(parent, [tid])

    service.update_subtask_template(
        tid,
        "T",
        "",
        [
            SubtaskTemplateItem(
                item_id="1",
                name="Changed",
                notes="changed",
                tags=["beta"],
                sort_order=0,
            )
        ],
    )
    service.delete_subtask_template(tid)

    children = service.child_tasks(parent)
    assert len(children) == 1
    assert children[0].name == "X"
    assert children[0].notes == "n"
    assert sorted(children[0].tags) == ["alpha"]


def test_template_item_parent_round_trip(tmp_path) -> None:
    store = SubtaskTemplateStore(tmp_path)
    template = SubtaskTemplate(
        template_id="t",
        name="T",
        items=[
            SubtaskTemplateItem(item_id="p", name="Parent", sort_order=0),
            SubtaskTemplateItem(item_id="c", name="Child", parent_item_id="p", sort_order=1),
        ],
    )
    store.save([template])
    loaded = store.load()[0]
    assert loaded.items[1].parent_item_id == "p"


def test_timestamp_string_item_ids_remain_load_save_compatible(tmp_path) -> None:
    store = SubtaskTemplateStore(tmp_path)
    template = SubtaskTemplate(
        template_id="t-ts",
        name="Legacy IDs",
        notes="",
        items=[
            SubtaskTemplateItem(item_id="1735689600.123456", name="Parent", sort_order=0),
            SubtaskTemplateItem(
                item_id="1735689601.654321",
                name="Child",
                parent_item_id="1735689600.123456",
                sort_order=1,
            ),
        ],
    )
    store.save([template])

    loaded = store.load()[0]
    assert [item.item_id for item in loaded.items] == ["1735689600.123456", "1735689601.654321"]
    assert loaded.items[1].parent_item_id == "1735689600.123456"


def test_template_rejects_depth_greater_than_2(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    tid = service.create_subtask_template("T", "")
    with pytest.raises(ValueError, match="depth"):
        service.update_subtask_template(
            tid,
            "T",
            "",
            [
                SubtaskTemplateItem(item_id="a", name="A", sort_order=0),
                SubtaskTemplateItem(item_id="b", name="B", parent_item_id="a", sort_order=1),
                SubtaskTemplateItem(item_id="c", name="C", parent_item_id="b", sort_order=2),
            ],
        )


def test_apply_nested_template_creates_hierarchy_and_skips_duplicates(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    root = service.create_task("Root", "")
    existing = service.create_subtask(root, "Build", "")
    service.create_subtask(existing, "Plan", "")
    tid = service.create_subtask_template("Nested", "")
    service.update_subtask_template(
        tid,
        "Nested",
        "",
        [
            SubtaskTemplateItem(item_id="p1", name="Build", sort_order=0),
            SubtaskTemplateItem(item_id="c1", name="Plan", parent_item_id="p1", sort_order=1),
            SubtaskTemplateItem(item_id="c2", name="Execute", parent_item_id="p1", sort_order=2),
            SubtaskTemplateItem(item_id="p2", name="Review", sort_order=3),
        ],
    )
    result = service.apply_subtask_templates(root, [tid])
    children = {c.name: c for c in service.child_tasks(root)}
    assert set(children) == {"Build", "Review"}
    build_children = sorted(c.name for c in service.child_tasks(children["Build"].task_id))
    assert build_children == ["Execute", "Plan"]
    assert sorted(result.skipped_duplicates) == ["Build", "Plan"]
    assert "Execute" in result.created_names and "Review" in result.created_names
