from datetime import datetime, timezone
import json
from pathlib import Path

from loguru import logger

from task_timer.service import TaskTimerService
from task_timer.storage import EventStorage


def test_restart_with_running_task(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path)
    service = TaskTimerService(storage)
    task_id = service.create_task("A", "note")
    service.start_task(task_id)

    service2 = TaskTimerService(EventStorage(tmp_path))
    assert service2.state.running_task_id == task_id
    assert service2.state.tasks[task_id].is_running


def test_auto_stop_prior_task_on_start(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    a = service.create_task("A", "")
    b = service.create_task("B", "")
    service.start_task(a)
    service.start_task(b)
    assert service.state.running_task_id == b
    assert not service.state.tasks[a].is_running


def test_rapid_start_stop_microseconds_produce_positive_duration(
    tmp_path: Path, monkeypatch
) -> None:
    from task_timer import service as service_module

    timestamps = iter(
        [
            datetime(2026, 1, 1, 0, 0, 0, 50000, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 0, 0, 0, 100000, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 0, 0, 0, 200000, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 0, 0, 0, 300000, tzinfo=timezone.utc),
        ]
    )
    monkeypatch.setattr(service_module, "utc_now", lambda: next(timestamps))

    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("A", "")
    service.start_task(task_id)
    service.stop_task(task_id)

    assert service.task_elapsed(service.state.tasks[task_id]) > 0


def test_reset_excludes_older_intervals(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("A", "")
    service.add_manual_interval(
        task_id,
        datetime(2026, 1, 1, 10, 0).astimezone(),
        datetime(2026, 1, 1, 11, 0).astimezone(),
        "missed",
    )
    before = service.task_elapsed(service.state.tasks[task_id])
    service.reset_task(task_id)
    after = service.task_elapsed(service.state.tasks[task_id])
    assert before >= 3600
    assert after == 0


def test_manual_interval_add_edit_delete(tmp_path: Path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("A", "")
    start = datetime(2026, 1, 1, 10, 0).astimezone()
    stop = datetime(2026, 1, 1, 11, 0).astimezone()
    service.add_manual_interval(task_id, start, stop, "add")
    interval_id = next(iter(service.state.tasks[task_id].intervals))
    service.edit_interval(
        task_id, interval_id, start, datetime(2026, 1, 1, 12, 0).astimezone(), "edit"
    )
    new_ids = [k for k, v in service.state.tasks[task_id].intervals.items() if not v.deleted]
    assert len(new_ids) == 1
    service.delete_interval(task_id, new_ids[0], "bad")
    assert all(v.deleted for v in service.state.tasks[task_id].intervals.values())


def test_rotation_and_rebuild_multi_segments(tmp_path: Path) -> None:
    storage = EventStorage(tmp_path, max_active_size_bytes=200, max_active_events=2)
    service = TaskTimerService(storage)
    t = service.create_task("A", "")
    service.start_task(t)
    service.stop_task(t)
    service.start_task(t)
    service.stop_task(t)

    manifest = storage.load_manifest()
    assert manifest["archives"]

    service2 = TaskTimerService(
        EventStorage(tmp_path, max_active_size_bytes=200, max_active_events=2)
    )
    assert service2.state.tasks[t].intervals


def test_corrupt_json_line_is_quarantined_and_valid_lines_still_load(
    tmp_path: Path,
) -> None:
    active = tmp_path / "active_events.jsonl"
    active.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": 1,
                        "event_id": "1",
                        "timestamp_utc": "2026-01-01T00:00:00Z",
                        "task_id": "t1",
                        "event_type": "task_created",
                        "payload": {"name": "A", "notes": ""},
                    }
                ),
                '{"broken_json":',
                json.dumps(
                    {
                        "schema_version": 1,
                        "event_id": "2",
                        "timestamp_utc": "2026-01-01T00:00:01Z",
                        "task_id": "t1",
                        "event_type": "started",
                        "payload": {},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    storage = EventStorage(tmp_path)
    events = storage.iter_all_events()
    assert [event["event_id"] for event in events] == ["1", "2"]
    assert storage.corrupt_event_count == 1
    assert storage.corrupt_events_path and storage.corrupt_events_path.exists()
    quarantined = storage.corrupt_events_path.read_text(encoding="utf-8")
    assert '"line_number": 2' in quarantined
    assert '"raw_text": "{\\"broken_json\\":"' in quarantined


def test_missing_required_keys_are_quarantined(tmp_path: Path) -> None:
    active = tmp_path / "active_events.jsonl"
    active.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event_id": "1",
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "task_id": "t1",
                "event_type": "task_created",
                "payload": {"name": "A", "notes": ""},
            }
        )
        + "\n"
        + json.dumps(
            {
                "schema_version": 1,
                "event_id": "bad",
                "timestamp_utc": "2026-01-01T00:00:01Z",
                "task_id": "t1",
                "event_type": "started",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    storage = EventStorage(tmp_path)
    events = storage.iter_all_events()
    assert [event["event_id"] for event in events] == ["1"]
    assert storage.corrupt_event_count == 1


def test_corrupt_warning_is_logged(tmp_path: Path) -> None:
    (tmp_path / "active_events.jsonl").write_text('{"oops":\n', encoding="utf-8")
    messages: list[str] = []
    sink_id = logger.add(lambda m: messages.append(str(m)), level="WARNING")
    try:
        EventStorage(tmp_path).iter_all_events()
    finally:
        logger.remove(sink_id)
    assert any(
        "Chronicle skipped 1 corrupt journal event lines during startup" in msg for msg in messages
    )
