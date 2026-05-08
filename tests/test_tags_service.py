from __future__ import annotations

import json

import pytest

from task_timer.service import TaskTimerService
from task_timer.storage import EventStorage
from task_timer.tags import normalize_tag


def test_normalize_tag_trims_casefolds_and_collapses_ws() -> None:
    assert normalize_tag("  Foo\t  Bar  ") == "foo bar"


@pytest.mark.parametrize("value", ["", "\t\n", "x\x01y"])
def test_normalize_tag_rejects_empty_and_control(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_tag(value)


def test_task_created_with_tags_replays(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("T", "", [" Alpha ", "Beta"])

    rebuilt = TaskTimerService(EventStorage(tmp_path))
    assert rebuilt.state.tasks[task_id].tags == {"alpha", "beta"}
    assert set(rebuilt.state.global_tags) >= {"alpha", "beta"}


def test_task_tags_updated_replays(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("T", "", ["alpha"])
    service.update_task_tags(task_id, ["Gamma"])

    rebuilt = TaskTimerService(EventStorage(tmp_path))
    assert rebuilt.state.tasks[task_id].tags == {"gamma"}
    assert set(rebuilt.state.global_tags) >= {"alpha", "gamma"}


def test_create_tag_works(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    service.create_tag(" Alpha ")
    assert "alpha" in service.state.global_tags


def test_rename_tag_appends_event(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    service.create_tag("alpha")
    service.rename_tag("alpha", "beta")
    lines = (tmp_path / "active_events.jsonl").read_text(encoding="utf-8")
    assert '"event_type": "tag_renamed"' in lines


def test_rename_tag_updates_current_assignments(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("T", "", ["alpha"])
    service.rename_tag("alpha", "omega")
    assert service.state.tasks[task_id].tags == {"omega"}


def test_rename_collision_blocked(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    service.create_tag("alpha")
    service.create_tag("beta")
    with pytest.raises(ValueError):
        service.rename_tag("alpha", "beta")


def test_archive_in_use_blocked(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    _task_id = service.create_task("T", "", ["alpha"])
    with pytest.raises(ValueError):
        service.archive_tag("alpha")


def test_archive_unused_succeeds(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("T", "", ["alpha"])
    service.update_task_tags(task_id, [])
    service.archive_tag("alpha")
    assert service.state.global_tags["alpha"].archived is True


def test_unarchive_succeeds(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    service.create_tag("alpha")
    service.archive_tag("alpha")
    service.unarchive_tag("alpha")
    assert service.state.global_tags["alpha"].archived is False


def test_delete_in_use_blocked(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    _task_id = service.create_task("T", "", ["alpha"])
    with pytest.raises(ValueError):
        service.delete_tag("alpha")


def test_delete_archived_unused_succeeds(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    service.create_tag("alpha")
    service.archive_tag("alpha")
    service.delete_tag("alpha")
    assert "alpha" not in service.state.global_tags


def test_raw_journal_not_rewritten_during_rename(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    _task_id = service.create_task("T", "", ["alpha"])
    before = (tmp_path / "active_events.jsonl").read_text(encoding="utf-8")
    service.rename_tag("alpha", "beta")
    after = (tmp_path / "active_events.jsonl").read_text(encoding="utf-8")
    assert before in after


def test_rebuild_restores_tags_and_global_metadata(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("T", "", ["alpha"])
    service.rename_tag("alpha", "omega")
    service.update_task_tags(task_id, [])
    service.archive_tag("omega")

    rebuilt = TaskTimerService(EventStorage(tmp_path))
    assert rebuilt.state.tasks[task_id].tags == set()
    assert rebuilt.state.global_tags["omega"].archived is True


def test_deterministic_replay_equal_timestamps(tmp_path) -> None:
    storage = EventStorage(tmp_path)
    ts = "2026-01-01T00:00:00Z"
    events = [
        {
            "schema_version": 1,
            "event_id": "1",
            "timestamp_utc": ts,
            "local_timezone": "UTC",
            "task_id": "t1",
            "event_type": "task_created",
            "payload": {"name": "T", "notes": "", "tags": ["a"]},
        },
        {
            "schema_version": 1,
            "event_id": "2",
            "timestamp_utc": ts,
            "local_timezone": "UTC",
            "task_id": "t1",
            "event_type": "task_tags_updated",
            "payload": {"tags": ["b"]},
        },
    ]
    for event in events:
        storage.append_event(event)

    rebuilt = TaskTimerService(storage)
    assert rebuilt.state.tasks["t1"].tags == {"b"}

    raw_lines = (tmp_path / "active_events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    payloads = [json.loads(line) for line in raw_lines]
    assert [row["event_id"] for row in payloads] == ["1", "2"]
