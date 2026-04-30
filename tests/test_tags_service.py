from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage
from task_timer.tags import normalize_tag, normalize_tag_list


def test_normalize_tag_and_list() -> None:
    assert normalize_tag("  Foo\t  Bar  ") == "foo bar"
    assert normalize_tag_list(["  Foo ", "bar\n baz"]) == ["bar baz", "foo"]


def test_task_created_and_updated_tags_replay(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("T", "", [" Alpha ", "Beta"])
    service.update_task_tags(task_id, ["Gamma"])

    rebuilt = TaskTimerService(EventStorage(tmp_path))
    assert rebuilt.state.tasks[task_id].tags == {"gamma"}
    assert set(rebuilt.state.global_tags) >= {"alpha", "beta", "gamma"}


def test_tag_lifecycle_and_constraints(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("T", "", ["alpha"])
    assert service.assigned_tags_for_task(task_id) == ["alpha"]
    assert service.available_tags_for_task(task_id) == ["alpha"]

    service.rename_tag("alpha", "omega")
    assert service.assigned_tags_for_task(task_id) == ["omega"]
    try:
        service.create_tag("omega")
        assert False
    except ValueError:
        pass
    service.create_tag("zeta")
    try:
        service.rename_tag("omega", "zeta")
        assert False
    except ValueError:
        pass
    try:
        service.archive_tag("omega")
        assert False
    except ValueError:
        pass

    service.update_task_tags(task_id, [])
    service.archive_tag("omega")
    service.unarchive_tag("omega")
    service.archive_tag("omega")
    try:
        service.delete_tag("zeta")
        assert False
    except ValueError:
        pass
    service.archive_tag("zeta")
    service.delete_tag("zeta")


def test_rename_appends_event_and_keeps_journal_lines(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("T", "", ["alpha"])
    _ = task_id
    before = (tmp_path / "active_events.jsonl").read_text(encoding="utf-8")
    service.rename_tag("alpha", "beta")
    after = (tmp_path / "active_events.jsonl").read_text(encoding="utf-8")
    assert before in after
    assert '"event_type": "tag_renamed"' in after


def test_delete_appends_event_and_keeps_journal_lines(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    service.create_tag("alpha")
    service.archive_tag("alpha")
    before = (tmp_path / "active_events.jsonl").read_text(encoding="utf-8")
    service.delete_tag("alpha")
    after = (tmp_path / "active_events.jsonl").read_text(encoding="utf-8")
    assert before in after
    assert '"event_type": "tag_deleted"' in after


def test_same_timestamp_replay_order_deterministic(tmp_path) -> None:
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
    for e in events:
        storage.append_event(e)
    rebuilt = TaskTimerService(storage)
    assert rebuilt.state.tasks["t1"].tags == {"b"}
