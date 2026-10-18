"""Isolated dated-entry replay; production duration writers remain legacy."""

from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import json
import zipfile

import pytest

from task_timer.app import TaskTimerService
from task_timer.models import DatedDurationRecord, IntervalRecord, event_dict
from task_timer.storage import EventStorage


STAMP = datetime(2026, 10, 13, 9, tzinfo=timezone.utc)
WORK_DATE = "2026-10-13"


@pytest.fixture
def clock(monkeypatch):
    value = [STAMP]
    monkeypatch.setattr("task_timer.app.utc_now", lambda: value[0])
    monkeypatch.setattr("task_timer.app.detect_local_timezone", lambda: ZoneInfo("America/Chicago"))
    return value


@pytest.fixture
def setup(tmp_path, clock):
    service = TaskTimerService(EventStorage(tmp_path / "fresh"))
    project = service.create_project("P")
    owner = service.create_task("Owner", "", project_id=project)
    other = service.create_task("Other", "")
    return service, owner, other, project


def _payload(entry_id, seconds=12600, work_date=WORK_DATE, reason="Recorded work"):
    return {"entry_id": entry_id, "work_date_local": work_date, "duration_seconds": seconds, "reason": reason}


def _append(service, owner, kind, payload):
    # The existing private append path is used only with isolated test storage.
    service._append(owner, kind, payload)
    return service.events[-1]


def _event(owner, kind, payload):
    return event_dict(
        timestamp_utc="2026-10-13T09:00:00Z", local_timezone="America/Chicago",
        task_id=owner, event_type=kind, payload=payload, event_id=str(uuid4()),
    )


def _files(root: Path):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _reject(service, event, *, check_append=True):
    state = deepcopy(service.state)
    events = deepcopy(service.events)
    files = _files(service.storage.data_dir)
    with pytest.raises(ValueError):
        service._apply_event(event)
    assert service.state == state
    if check_append:
        with pytest.raises(ValueError):
            service._append(event["task_id"], event["event_type"], event["payload"])
    assert service.state == state
    assert service.events == events
    assert _files(service.storage.data_dir) == files


@pytest.mark.parametrize("seconds", [12600, 50400])
def test_creation_is_one_endpoint_free_record_on_its_work_date(setup, clock, seconds):
    service, owner, other, project = setup
    clock[0] += timedelta(days=3)  # audit date is not the work date
    entry_id = str(uuid4())
    event = _append(service, owner, "dated_duration_added", _payload(entry_id, seconds))
    task = service.state.tasks[owner]
    assert list(task.dated_durations) == [entry_id]
    entry = task.dated_durations[entry_id]
    assert isinstance(entry, DatedDurationRecord)
    assert not isinstance(entry, IntervalRecord)
    assert entry.entry_id == entry_id and entry.task_id == owner
    assert entry.work_date_local == date(2026, 10, 13)
    assert entry.duration_seconds == seconds
    assert entry.reason == "Recorded work"
    assert entry.created_at_utc == entry.updated_at_utc == clock[0]
    assert entry.revision_event_id == event["event_id"]
    assert entry.deleted is False
    assert task.intervals == {}
    assert service.state.tasks[other].dated_durations == {}
    for field in ("start_utc", "stop_utc"):
        assert not hasattr(entry, field)
        with pytest.raises(AttributeError):
            setattr(entry, field, clock[0])
    assert len(service.events) == 4
    snapshot = service.storage.load_snapshot()["tasks"][owner]
    assert snapshot["dated_durations"] == [{
        "entry_id": entry_id, "task_id": owner, "work_date_local": WORK_DATE,
        "duration_seconds": seconds, "reason": "Recorded work",
        "created_at_utc": "2026-10-16T09:00:00Z", "updated_at_utc": "2026-10-16T09:00:00Z",
        "revision_event_id": event["event_id"], "deleted": False,
    }]
    assert snapshot["intervals"] == []
    assert snapshot["project_id"] == project
    assert not {"start_utc", "stop_utc"} & event["payload"].keys()


def test_correction_redating_and_deletion_preserve_identity_and_history(setup, clock):
    service, owner, _, _ = setup
    entry_id = str(uuid4())
    added = _append(service, owner, "dated_duration_added", _payload(entry_id, 7200))
    original = deepcopy(added)
    journal = service.storage.active_path.read_bytes()
    clock[0] += timedelta(seconds=1)
    corrected = _append(service, owner, "dated_duration_corrected", _payload(entry_id, 10800, reason="Correct amount"))
    entry = service.state.tasks[owner].dated_durations[entry_id]
    assert list(service.state.tasks[owner].dated_durations) == [entry_id]
    assert entry.duration_seconds == 10800 and entry.deleted is False
    assert entry.work_date_local == date(2026, 10, 13)
    assert entry.created_at_utc == STAMP and entry.updated_at_utc == clock[0]
    assert entry.revision_event_id == corrected["event_id"]
    clock[0] += timedelta(seconds=1)
    moved = _append(service, owner, "dated_duration_corrected", _payload(entry_id, 10800, "2026-10-14", "Correct date"))
    assert entry.work_date_local == date(2026, 10, 14)
    assert entry.task_id == owner and entry.entry_id == entry_id
    assert entry.duration_seconds == 10800 and entry.revision_event_id == moved["event_id"]
    clock[0] += timedelta(seconds=1)
    deleted = _append(service, owner, "dated_duration_deleted", {"entry_id": entry_id, "reason": "Remove duplicate"})
    assert entry.deleted is True
    assert entry.reason == "Remove duplicate"
    assert entry.duration_seconds == 10800 and entry.work_date_local == date(2026, 10, 14)
    assert entry.created_at_utc == STAMP and entry.updated_at_utc == clock[0]
    assert entry.revision_event_id == deleted["event_id"]
    assert service.events[3] == original
    assert service.storage.active_path.read_bytes().startswith(journal)
    history = service.storage.iter_all_events()[3:]
    assert [event["event_type"] for event in history] == [
        "dated_duration_added", "dated_duration_corrected", "dated_duration_corrected", "dated_duration_deleted"
    ]
    assert history[0]["payload"]["duration_seconds"] == 7200
    assert history[1]["payload"]["duration_seconds"] == 10800
    assert len(service.events) == 7
    expected = service.snapshot_dict()
    service._rebuild_state(service.events)
    assert service.snapshot_dict() == expected
    restarted = TaskTimerService(EventStorage(service.storage.data_dir))
    assert restarted.snapshot_dict() == expected
    assert asdict(restarted.state.tasks[owner].dated_durations[entry_id]) == asdict(entry)


@pytest.mark.parametrize("kind", ["dated_duration_added", "dated_duration_corrected"])
@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf"), -float("inf"), True, "12600", None, 10**400])
def test_invalid_amount_rejected_without_any_state_or_file_change(setup, kind, seconds):
    service, owner, _, _ = setup
    existing = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(existing, 7200))
    entry_id = existing if kind == "dated_duration_corrected" else str(uuid4())
    _reject(service, _event(owner, kind, _payload(entry_id, seconds)))
    assert len(service.events) == 4


@pytest.mark.parametrize("changes", [
    {"work_date_local": "2026-02-30"}, {"work_date_local": "2026-13-01"},
    {"work_date_local": "20261013"}, {"work_date_local": "2026-W42-2"},
    {"work_date_local": None}, {"work_date_local": date(2026, 10, 13)},
    {"reason": ""}, {"reason": " \t\n "}, {"reason": None}, {"reason": 7},
    {"entry_id": "invalid"}, {"entry_id": None}, {"entry_id": []},
    {"entry_id": "01234567-89AB-4CDE-8FAB-0123456789AB"},
    {"start_utc": "2026-10-13T12:00:00Z"}, {"stop_utc": None},
    {"interval_id": "unexpected"}, {"task_id": "unexpected"}, {"notes": "unsupported"},
])
@pytest.mark.parametrize("kind", ["dated_duration_added", "dated_duration_corrected"])
def test_malformed_payload_rejected_atomically(setup, kind, changes):
    service, owner, _, _ = setup
    existing = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(existing, 7200))
    payload = _payload(existing if kind == "dated_duration_corrected" else str(uuid4()))
    payload.update(changes)
    _reject(service, _event(owner, kind, payload))
    assert len(service.events) == 4


@pytest.mark.parametrize("kind", ["dated_duration_added", "dated_duration_corrected", "dated_duration_deleted"])
@pytest.mark.parametrize("payload", [None, [], {}])
def test_invalid_payload_object_or_missing_fields_rejected(setup, kind, payload):
    service, owner, _, _ = setup
    _reject(service, _event(owner, kind, payload))
    assert len(service.events) == 3


@pytest.mark.parametrize("kind", ["dated_duration_added", "dated_duration_corrected", "dated_duration_deleted"])
@pytest.mark.parametrize("owner_kind", ["project", "unknown", "non-uuid", "non-string"])
def test_invalid_owners_cannot_mutate_or_interrupt_running_work(setup, clock, kind, owner_kind):
    service, owner, _, project = setup
    entry_id = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(entry_id))
    service.start_task(owner)
    clock[0] += timedelta(minutes=10)
    target = {"project": project, "unknown": str(uuid4()), "non-uuid": "bad", "non-string": []}[owner_kind]
    payload = {"entry_id": entry_id, "reason": "Remove"} if kind == "dated_duration_deleted" else _payload(entry_id)
    _reject(service, _event(target, kind, payload))
    assert service.state.running_task_id == owner
    assert sum((stop - start).total_seconds() for start, stop in service._windowed_intervals(service.state.tasks[owner], None, clock[0])) == 600
    assert len(service.events) == 5


@pytest.mark.parametrize("kind", ["dated_duration_corrected", "dated_duration_deleted"])
def test_missing_cross_task_and_deleted_references_are_rejected(setup, kind):
    service, owner, other, _ = setup
    entry_id = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(entry_id, 7200))
    def payload(identifier):
        return {"entry_id": identifier, "reason": "Remove"} if kind == "dated_duration_deleted" else _payload(identifier)
    _reject(service, _event(owner, kind, payload(str(uuid4()))))
    _reject(service, _event(other, kind, payload(entry_id)))
    _append(service, owner, "dated_duration_deleted", {"entry_id": entry_id, "reason": "Remove"})
    _reject(service, _event(owner, kind, payload(entry_id)))
    assert len(service.events) == 5


@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.parametrize("same_owner", [False, True])
def test_duplicate_entry_identity_is_rejected_across_tasks_and_tombstones(setup, deleted, same_owner):
    service, owner, other, _ = setup
    entry_id = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(entry_id))
    if deleted:
        _append(service, owner, "dated_duration_deleted", {"entry_id": entry_id, "reason": "Remove"})
    _reject(service, _event(owner if same_owner else other, "dated_duration_added", _payload(entry_id)))
    assert len(service.events) == 4 + int(deleted)


def test_dated_entry_cannot_alias_an_existing_interval_identity(setup):
    service, owner, other, _ = setup
    service.add_manual_interval(owner, STAMP - timedelta(hours=2), STAMP - timedelta(hours=1), "Real work")
    interval_id = next(iter(service.state.tasks[owner].intervals))
    _reject(service, _event(other, "dated_duration_added", _payload(interval_id)))
    assert service.state.tasks[other].dated_durations == {}
    assert sum((stop - start).total_seconds() for start, stop in service._windowed_intervals(service.state.tasks[owner], None, STAMP)) == 3600
    assert len(service.events) == 4


@pytest.mark.parametrize("field,value", [
    ("event_id", "invalid"), ("event_id", None),
    ("timestamp_utc", "invalid"), ("timestamp_utc", None),
    ("timestamp_utc", "2026-10-13T09:00:00"),
    ("timestamp_utc", "2026-10-13T09:00:00.5Z"),
])
def test_invalid_audit_metadata_is_rejected_before_record_or_task_updates(setup, field, value):
    service, owner, _, _ = setup
    entry_id = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(entry_id, 7200))
    event = _event(owner, "dated_duration_corrected", _payload(entry_id))
    event[field] = value
    _reject(service, event, check_append=False)
    assert len(service.events) == 4


@pytest.mark.parametrize("field", ["event_id", "timestamp_utc", "task_id", "payload"])
def test_missing_envelope_fields_rejected_without_partial_application(setup, field):
    service, owner, _, _ = setup
    event = _event(owner, "dated_duration_added", _payload(str(uuid4())))
    del event[field]
    _reject(service, event, check_append=False)


def test_invalid_journal_fails_without_rewriting_events_or_snapshot(setup):
    service, owner, _, _ = setup
    event = _event(owner, "dated_duration_added", _payload(str(uuid4()), float("nan")))
    service.storage.append_event(event)  # corrupt input fixture, never a public writer
    before = _files(service.storage.data_dir)
    with pytest.raises(ValueError, match="finite positive"):
        TaskTimerService(EventStorage(service.storage.data_dir))
    assert _files(service.storage.data_dir) == before


def test_equal_second_replay_uses_read_order_not_revision_uuid_sort_order(setup):
    service, owner, _, _ = setup
    entry_id = str(uuid4())
    added = _event(owner, "dated_duration_added", _payload(entry_id, 7200))
    first = _event(owner, "dated_duration_corrected", _payload(entry_id, 10800))
    last = _event(owner, "dated_duration_corrected", _payload(entry_id, 14400, "2026-10-14", "Last correction"))
    first["event_id"] = "ffffffff-ffff-4fff-8fff-ffffffffffff"
    last["event_id"] = "00000000-0000-4000-8000-000000000001"
    for event in (added, first, last):
        service.storage.append_event(event)
    events = service.storage.iter_all_events()
    assert len(events) == 6
    assert len({event["timestamp_utc"] for event in events}) == 1
    service._rebuild_state(list(reversed(events)))  # stored read sequence remains authoritative
    record = service.state.tasks[owner].dated_durations[entry_id]
    assert record.duration_seconds == 14400
    assert record.work_date_local == date(2026, 10, 14)
    assert record.reason == "Last correction" and record.revision_event_id == last["event_id"]
    assert record.created_at_utc == record.updated_at_utc == STAMP
    restarted = TaskTimerService(EventStorage(service.storage.data_dir))
    assert asdict(restarted.state.tasks[owner].dated_durations[entry_id]) == asdict(record)


def test_equal_second_correction_after_restart_replays_after_loaded_events(setup):
    service, owner, _, _ = setup
    entry_id = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(entry_id, 7200))
    restarted = TaskTimerService(EventStorage(service.storage.data_dir))
    corrected = _append(restarted, owner, "dated_duration_corrected", _payload(entry_id, 10800))
    expected = restarted.snapshot_dict()
    assert "_read_sequence" in restarted.events[0]
    assert "_read_sequence" not in corrected
    assert len({event["timestamp_utc"] for event in restarted.events}) == 1
    restarted._rebuild_state(restarted.events)
    assert restarted.snapshot_dict() == expected
    assert restarted.state.tasks[owner].dated_durations[entry_id].revision_event_id == corrected["event_id"]
    assert restarted.state.tasks[owner].dated_durations[entry_id].duration_seconds == 10800


def test_archive_rotation_restart_and_snapshot_reconstruction(tmp_path, clock):
    storage = EventStorage(tmp_path / "fresh", max_active_events=2)
    service = TaskTimerService(storage)
    project = service.create_project("P")
    owner = service.create_task("Owner", "", project_id=project)
    service.add_manual_interval(owner, STAMP - timedelta(hours=2), STAMP - timedelta(hours=1), "Real work")
    interval_before = deepcopy(service.state.tasks[owner].intervals)
    entry_id = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(entry_id, 7200))
    clock[0] += timedelta(seconds=1)
    _append(service, owner, "dated_duration_corrected", _payload(entry_id, 10800, "2026-10-14"))
    deleted_id = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(deleted_id, 50400))
    _append(service, owner, "dated_duration_deleted", {"entry_id": deleted_id, "reason": "Remove"})
    assert len(service.events) == 7
    assert len(storage.load_manifest()["archives"]) == 3
    archives_before = _files(storage.archives_dir)
    expected = service.snapshot_dict()
    storage.snapshot_path.write_text('{"tasks": {}, "projects": {}}', encoding="utf-8")
    restarted = TaskTimerService(EventStorage(storage.data_dir))
    assert restarted.snapshot_dict() == expected
    assert restarted.state.tasks[owner].intervals == interval_before
    assert restarted.state.tasks[owner].dated_durations[entry_id].duration_seconds == 10800
    assert restarted.state.tasks[owner].dated_durations[deleted_id].deleted is True
    restarted.state.tasks[owner].dated_durations.clear()
    restarted.rebuild_snapshot_from_journal()
    assert restarted.snapshot_dict() == expected == storage.load_snapshot()
    assert _files(storage.archives_dir) == archives_before
    assert len(storage.iter_all_events()) == 7


def test_backup_restore_preserves_events_and_effective_projection(setup, clock):
    service, owner, _, _ = setup
    entry_id = str(uuid4())
    added = _append(service, owner, "dated_duration_added", _payload(entry_id, 7200))
    expected = service.snapshot_dict()
    backup = service.create_backup_now("Before correction")
    with zipfile.ZipFile(backup) as archive:
        events = [json.loads(line) for line in archive.read("active_events.jsonl").decode().splitlines()]
        assert events[-1] == added
        assert json.loads(archive.read("state_snapshot.json")) == expected
    clock[0] += timedelta(seconds=1)
    _append(service, owner, "dated_duration_corrected", _payload(entry_id, 10800, "2026-10-14"))
    _append(service, owner, "dated_duration_deleted", {"entry_id": entry_id, "reason": "Remove"})
    service.restore_from_backup(backup)
    assert service.snapshot_dict() == expected
    assert len(service.events) == 4
    assert service.state.tasks[owner].dated_durations[entry_id].revision_event_id == added["event_id"]
    assert service.state.tasks[owner].dated_durations[entry_id].deleted is False
    assert service.storage.iter_all_events()[-1]["event_id"] == added["event_id"]


def test_dated_records_never_enter_legacy_clipping_replacement_or_reset_paths(setup, clock):
    service, owner, _, _ = setup
    service.add_manual_interval(owner, STAMP - timedelta(hours=2), STAMP - timedelta(hours=1), "Real work")
    intervals_before = deepcopy(service.state.tasks[owner].intervals)
    entry_id = str(uuid4())
    _append(service, owner, "dated_duration_added", _payload(entry_id))
    dated_before = deepcopy(service.state.tasks[owner].dated_durations)
    assert service.state.tasks[owner].intervals == intervals_before
    assert [record.interval_id for record in service._all_intervals(service.state.tasks[owner], STAMP)] == list(intervals_before)
    assert service._windowed_intervals(service.state.tasks[owner], None, STAMP) == [(STAMP - timedelta(hours=2), STAMP - timedelta(hours=1))]
    assert sum((stop - start).total_seconds() for start, stop in service._windowed_intervals(service.state.tasks[owner], None, STAMP)) == 3600  # Retained export-window reader remains interval-only.
    files_before = _files(service.storage.data_dir)
    for operation in (
        lambda: service.edit_interval(owner, entry_id, STAMP, STAMP + timedelta(hours=1), "Wrong kind"),
        lambda: service.edit_duration_interval(owner, entry_id, date(2026, 10, 13), 10800, "Wrong kind"),
        lambda: service.delete_interval(owner, entry_id, "Wrong kind"),
    ):
        with pytest.raises(ValueError, match="Interval not found"):
            operation()
    assert _files(service.storage.data_dir) == files_before
    assert len(service.events) == 5
    clock[0] += timedelta(hours=1)
    service.reset_task(owner)
    assert sum((stop - start).total_seconds() for start, stop in service._windowed_intervals(service.state.tasks[owner], None, clock[0])) == 0
    assert service.state.tasks[owner].dated_durations == dated_before
    assert service.state.tasks[owner].intervals == intervals_before


def test_legacy_duration_writer_and_correction_are_not_switched_to_dated_events(setup):
    service, owner, _, _ = setup
    service.add_manual_duration(owner, date(2026, 10, 13), 7200, "Legacy work")
    task = service.state.tasks[owner]
    old_id = next(iter(task.intervals))
    interval = task.intervals[old_id]
    assert interval.entry_mode == "duration"
    assert interval.start_utc.astimezone(service.local_tz).hour == 12
    assert interval.stop_utc - interval.start_utc == timedelta(seconds=7200)
    assert task.dated_durations == {}
    service.edit_duration_interval(owner, old_id, date(2026, 10, 14), 10800, "Legacy correction")
    assert task.intervals[old_id].deleted is True
    assert len(task.intervals) == 2 and task.dated_durations == {}
    assert [record.duration_seconds for record in task.intervals.values() if not record.deleted] == [10800]
    assert [event["event_type"] for event in service.events[3:]] == ["manual_duration_added", "interval_edited"]


def test_empty_directory_does_not_import_dated_or_legacy_records(tmp_path, clock, monkeypatch):
    old_home = tmp_path / "old-home"
    old_dir = old_home / ".task_timer_data"
    old_service = TaskTimerService(EventStorage(old_dir))
    owner = old_service.create_task("Old", "")
    old_service.add_manual_duration(owner, date(2026, 10, 13), 7200, "Legacy work")
    _append(old_service, owner, "dated_duration_added", _payload(str(uuid4())))
    before = _files(old_dir)
    monkeypatch.setattr(Path, "home", lambda: old_home)
    fresh = TaskTimerService(EventStorage(tmp_path / "new-installation"))
    assert fresh.state.tasks == fresh.state.projects == {}
    assert fresh.events == []
    assert _files(old_dir) == before
