"""Project/task domain boundaries, durable membership, and fresh-start isolation."""

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from task_timer.app import TaskTimerService
from task_timer.models import ProjectState, event_dict
from task_timer.storage import EventStorage


START = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    value = [START]
    monkeypatch.setattr("task_timer.app.utc_now", lambda: value[0])
    return value


@pytest.fixture
def service(tmp_path, clock):
    return TaskTimerService(EventStorage(tmp_path / "fresh"))


def _files(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _add_minutes(service, task_id, minutes):
    service.add_manual_interval(task_id, START - timedelta(hours=4), START - timedelta(hours=4) + timedelta(minutes=minutes), "work")


def test_projects_have_independent_identity_and_no_time_state(service, clock):
    first = service.create_project(" Project ")
    second = service.create_project("Project", "Notes")
    task_id = service.create_task("Project", "", project_id=first)
    assert len({first, second, task_id}) == 3
    assert all(UUID(identifier).version == 4 for identifier in (first, second, task_id))
    assert set(service.state.projects) == {first, second}
    assert set(service.state.tasks) == {task_id}
    project = service.state.projects[first]
    assert isinstance(project, ProjectState)
    assert project.name == "Project" and project.notes == ""
    assert project.created_at_utc == project.updated_at_utc == START
    for field in ("intervals", "is_running", "last_reset_utc", "elapsed_seconds"):
        with pytest.raises(AttributeError):
            setattr(project, field, 0)
    assert len(service.events) == 3
    assert sorted(project.project_id for project in service.list_projects()) == sorted([first, second])
    assert set(service.snapshot_dict()["projects"][first]) == {
        "project_id", "name", "notes", "created_at_utc", "updated_at_utc"
    }


def test_assignment_move_and_unassignment_preserve_direct_time_and_other_tasks(service):
    first = service.create_project("P")
    second = service.create_project("Q")
    a = service.create_task("A", "", project_id=first)
    b = service.create_task("B", "", project_id=first)
    unassigned = service.create_task("Unassigned", "")
    assert service.state.tasks[unassigned].project_id is None
    _add_minutes(service, a, 60)
    _add_minutes(service, b, 120)
    intervals = deepcopy(service.state.tasks[a].intervals)
    original_events = deepcopy(service.events)
    original_log = service.storage.active_path.read_bytes()
    assert len(original_events) == 7
    for index, destination in enumerate((second, None, first), start=1):
        if destination is None:
            service.unassign_task_from_project(a)
        else:
            service.assign_task_to_project(a, destination)
        assert len(service.events) == 7 + index
        assert service.events[-1]["event_type"] == "task_project_assigned"
        assert service.events[-1]["payload"] == {"project_id": destination}
        assert service.state.tasks[a].task_id == a
        assert service.state.tasks[a].project_id == destination
        assert service.state.tasks[a].intervals == intervals
        assert service.task_elapsed(service.state.tasks[a], START) == 3600
        assert service.task_elapsed(service.state.tasks[b], START) == 7200
        assert service.state.tasks[b].project_id == first
        assert service.state.tasks[unassigned].project_id is None
    assert service.events[:7] == original_events
    assert service.storage.active_path.read_bytes().startswith(original_log)
    rows = service.compute_windowed_task_totals(None, START)
    assert {row["task_id"]: row["overall_seconds"] for row in rows} == {a: 3600, b: 7200, unassigned: 0}
    service.assign_task_to_project(a, first)
    service.unassign_task_from_project(unassigned)
    assert len(service.events) == 10  # unchanged assignments are no-ops


def test_project_update_preserves_membership_and_task_time(service, clock):
    project_id = service.create_project("Original", "Original notes")
    task_id = service.create_task("Task", "", project_id=project_id)
    _add_minutes(service, task_id, 60)
    task_before = asdict(service.state.tasks[task_id])
    clock[0] += timedelta(days=1)
    service.rename_project(project_id, "Renamed")
    service.update_project(project_id, notes="Updated\nnotes")
    assert len(service.events) == 5
    project = service.state.projects[project_id]
    assert project.name == "Renamed" and project.notes == "Updated notes"
    assert project.created_at_utc == START
    assert project.updated_at_utc == clock[0]
    assert asdict(service.state.tasks[task_id]) == task_before
    assert service.task_elapsed(service.state.tasks[task_id], clock[0]) == 3600


def test_duplicate_task_names_never_merge_and_rename_preserves_intervals(service):
    p = service.create_project("P")
    q = service.create_project("Q")
    ids = [service.create_task("Documentation", "", project_id=project) for project in (p, p, q, None)]
    for task_id, minutes in zip(ids, (30, 60, 90, 120)):
        _add_minutes(service, task_id, minutes)
    assert len(set(ids)) == len(service.state.tasks) == 4
    before = deepcopy(service.state.tasks[ids[0]].intervals)
    service.update_task(ids[0], "Renamed", "Context")
    assert service.state.tasks[ids[0]].intervals == before
    assert [service.task_elapsed(service.state.tasks[task_id], START) for task_id in ids] == [1800, 3600, 5400, 7200]
    assert len(service.events) == 11


TIME_OPERATIONS = [
    lambda s, target, running: s.start_task(target),
    lambda s, target, running: s.stop_task(target),
    lambda s, target, running: s.add_manual_interval(target, START, START + timedelta(hours=1), "work"),
    lambda s, target, running: s.add_manual_duration(target, START.date(), 3600, "work"),
    lambda s, target, running: s.edit_interval(target, "missing", START, START + timedelta(hours=1), "fix"),
    lambda s, target, running: s.edit_duration_interval(target, "missing", START.date(), 3600, "fix"),
    lambda s, target, running: s.delete_interval(target, "missing", "fix"),
    lambda s, target, running: s.correct_running_interval_stop(target, START + timedelta(minutes=5), "fix"),
    lambda s, target, running: s.reset_task(target),
    lambda s, target, running: s.reset_task_only(target),
    lambda s, target, running: s.reset_task_tree(target),
    lambda s, target, running: s.delete_task(target),
    lambda s, target, running: s.delete_task_only(target),
    lambda s, target, running: s.delete_task_tree(target),
    lambda s, target, running: s.reset_selected_tasks([running, target]),
    lambda s, target, running: s.delete_selected_tasks([running, target]),
]


@pytest.mark.parametrize("operation", TIME_OPERATIONS, ids=[
    "start", "stop", "add-interval", "add-duration", "edit-interval", "edit-duration",
    "delete-interval", "correct-stop", "reset", "reset-only", "reset-tree",
    "delete", "delete-only", "delete-tree", "reset-selected", "delete-selected",
])
@pytest.mark.parametrize("target_kind", ["project", "unknown", "non-string"])
def test_invalid_time_targets_have_no_side_effects(service, clock, operation, target_kind):
    project_id = service.create_project("P")
    running = service.create_task("Running", "")
    service.start_task(running)
    clock[0] += timedelta(minutes=10)
    target = {"project": project_id, "unknown": str(uuid4()), "non-string": []}[target_kind]
    before = service.snapshot_dict()
    files_before = _files(service.storage.data_dir)
    with pytest.raises(ValueError):
        operation(service, target, running)
    assert len(service.events) == len(service.storage.iter_all_events()) == 3
    assert service.snapshot_dict() == before
    assert _files(service.storage.data_dir) == files_before
    assert service.state.running_task_id == running
    assert service.state.tasks[running].is_running
    assert service.state.tasks[running].intervals == {}
    assert service.task_elapsed(service.state.tasks[running], clock[0]) == 600


def test_valid_timer_switch_and_running_reassignment_preserve_elapsed(service, clock):
    p = service.create_project("P")
    q = service.create_project("Q")
    a = service.create_task("A", "", project_id=p)
    b = service.create_task("B", "", project_id=p)
    service.start_task(a)
    clock[0] += timedelta(minutes=30)
    service.assign_task_to_project(a, q)
    assert service.state.running_task_id == a
    assert service.state.tasks[a].currently_open_interval_start_utc == START
    assert service.task_elapsed(service.state.tasks[a], clock[0]) == 1800
    service.start_task(b)
    assert len(service.events) == 8
    assert service.state.running_task_id == b
    assert not service.state.tasks[a].is_running
    assert service.task_elapsed(service.state.tasks[a], clock[0]) == 1800
    clock[0] += timedelta(minutes=15)
    service.stop_task(b)
    assert len(service.events) == 9
    assert service.state.running_task_id is None
    assert service.task_elapsed(service.state.tasks[b], clock[0]) == 900


@pytest.mark.parametrize("action", [
    lambda s, p, t: s.create_project(" "),
    lambda s, p, t: s.create_project("P", []),
    lambda s, p, t: s.rename_project(p, ""),
    lambda s, p, t: s.update_project(p, notes=[]),
    lambda s, p, t: s.update_project(t, name="Wrong kind"),
    lambda s, p, t: s.create_task("Task", "", project_id=t),
    lambda s, p, t: s.create_task("Task", "", project_id=str(uuid4())),
    lambda s, p, t: s.assign_task_to_project(t, str(uuid4())),
    lambda s, p, t: s.assign_task_to_project(str(uuid4()), p),
    lambda s, p, t: s.assign_task_to_project(p, p),
    lambda s, p, t: s.unassign_task_from_project(p),
])
def test_invalid_project_operations_append_nothing(service, clock, action):
    p = service.create_project("P")
    t = service.create_task("Task", "")
    service.start_task(t)
    before = service.snapshot_dict()
    files_before = _files(service.storage.data_dir)
    with pytest.raises(ValueError):
        action(service, p, t)
    assert len(service.events) == 3
    assert service.snapshot_dict() == before
    assert _files(service.storage.data_dir) == files_before


@pytest.mark.parametrize("event_type,payload", [
    ("project_created", {}),
    ("project_created", {"project_id": "bad", "name": "P"}),
    ("project_created", {"project_id": [], "name": "P"}),
    ("project_created", {"project_id": "NEW", "name": ""}),
    ("project_created", {"project_id": "NEW", "name": 4}),
    ("project_created", {"project_id": "NEW", "name": "P", "notes": None}),
    ("project_created", {"project_id": "NEW", "name": "P", "elapsed_seconds": 60}),
    ("project_created", {"project_id": "PROJECT", "name": "Duplicate ID"}),
    ("project_created", {"project_id": "TASK", "name": "Colliding ID"}),
    ("project_updated", {"project_id": "PROJECT"}),
    ("project_updated", {"project_id": "NEW", "name": "Unknown"}),
    ("project_updated", []),
    ("task_project_assigned", {}),
    ("task_project_assigned", {"project_id": "NEW"}),
    ("task_project_assigned", {"project_id": "TASK"}),
    ("task_project_assigned", {"project_id": "PROJECT", "intervals": []}),
])
def test_malformed_project_events_rejected_before_append_and_replay(service, event_type, payload):
    project_id = service.create_project("P")
    task_id = service.create_task("Task", "")
    if isinstance(payload, dict):
        substitutions = {"NEW": str(uuid4()), "PROJECT": project_id, "TASK": task_id}
        payload = {key: substitutions.get(value, value) if isinstance(value, str) else value for key, value in payload.items()}
    envelope_id = task_id if event_type == "task_project_assigned" else "__app__"
    before = service.snapshot_dict()
    files_before = _files(service.storage.data_dir)
    with pytest.raises(ValueError):
        service._append(envelope_id, event_type, payload)
    event = event_dict(timestamp_utc="2026-01-05T09:00:00Z", local_timezone="UTC", task_id=envelope_id, event_type=event_type, payload=payload, event_id=str(uuid4()))
    with pytest.raises(ValueError):
        service._apply_event(event)
    assert service.snapshot_dict() == before
    assert len(service.events) == 2
    assert _files(service.storage.data_dir) == files_before


@pytest.mark.parametrize("changes", [
    {"project_id": "UNKNOWN"},
    {"project_id": []},
    {"name": " "},
    {"notes": None},
    {"tags": "invalid"},
    {"parent_task_id": "TASK"},
    {"intervals": []},
])
def test_malformed_project_task_creation_has_no_effects(service, changes):
    project_id = service.create_project("P")
    existing = service.create_task("Existing", "")
    substitutions = {"UNKNOWN": str(uuid4()), "TASK": existing}
    payload = {"name": "New", "notes": "", "tags": [], "parent_task_id": None, "project_id": project_id}
    payload.update({key: substitutions.get(value, value) if isinstance(value, str) else value for key, value in changes.items()})
    before = service.snapshot_dict()
    files_before = _files(service.storage.data_dir)
    with pytest.raises(ValueError):
        service._append(str(uuid4()), "task_created", payload)
    assert service.snapshot_dict() == before
    assert len(service.events) == 2
    assert _files(service.storage.data_dir) == files_before


def test_invalid_project_envelope_and_corrupt_journal_are_rejected(service):
    task_id = service.create_task("Task", "")
    payload = {"project_id": str(uuid4()), "name": "P"}
    with pytest.raises(ValueError, match="application envelope"):
        service._append(task_id, "project_created", payload)
    assert len(service.events) == 1
    malformed = event_dict(timestamp_utc="2026-01-05T09:00:00Z", local_timezone="UTC", task_id="__app__", event_type="project_created", payload={"project_id": "invalid", "name": "P"}, event_id=str(uuid4()))
    service.storage.append_event(malformed)
    journal_before = service.storage.active_path.read_bytes()
    with pytest.raises(ValueError, match="UUID"):
        TaskTimerService(EventStorage(service.storage.data_dir))
    assert service.storage.active_path.read_bytes() == journal_before


@pytest.mark.parametrize("payload", [None, []])
def test_non_object_task_creation_is_rejected_without_writing(service, payload):
    before = _files(service.storage.data_dir)
    with pytest.raises(ValueError, match="payload object"):
        service._append(str(uuid4()), "task_created", payload)
    assert service.events == []
    assert _files(service.storage.data_dir) == before


def test_deleted_task_cannot_start_or_change_membership(service):
    p = service.create_project("P")
    deleted = service.create_task("Deleted", "")
    service.delete_task(deleted)
    running = service.create_task("Running", "")
    service.start_task(running)
    before = service.snapshot_dict()
    with pytest.raises(ValueError, match="deleted"):
        service.start_task(deleted)
    with pytest.raises(ValueError, match="deleted"):
        service.assign_task_to_project(deleted, p)
    assert service.snapshot_dict() == before
    assert len(service.events) == 5


def test_archive_replay_and_snapshot_rebuild_restore_projects_and_membership(tmp_path, clock):
    storage = EventStorage(tmp_path, max_active_events=2)
    service = TaskTimerService(storage)
    p = service.create_project("P")
    q = service.create_project("Q")
    a = service.create_task("A", "", project_id=p)
    b = service.create_task("B", "")
    _add_minutes(service, a, 60)
    _add_minutes(service, b, 120)
    service.assign_task_to_project(a, q)
    service.rename_project(q, "Renamed")
    service.assign_task_to_project(b, p)
    service.unassign_task_from_project(b)
    service.create_project("Empty")
    expected = service.snapshot_dict()
    assert len(service.events) == 11
    assert len(storage.load_manifest()["archives"]) == 5
    archive_before = _files(storage.archives_dir)
    storage.snapshot_path.write_text('{"projects": {}, "tasks": {}}', encoding="utf-8")
    rebuilt = TaskTimerService(EventStorage(tmp_path, max_active_events=2))
    assert rebuilt.snapshot_dict() == expected
    assert rebuilt.state.tasks[a].project_id == q
    assert rebuilt.state.tasks[b].project_id is None
    assert rebuilt.task_elapsed(rebuilt.state.tasks[a], START) == 3600
    assert rebuilt.task_elapsed(rebuilt.state.tasks[b], START) == 7200
    rebuilt.state.projects.clear()
    rebuilt.state.tasks[a].project_id = None
    rebuilt.rebuild_snapshot_from_journal()
    assert rebuilt.snapshot_dict() == expected
    assert storage.load_snapshot() == expected
    assert _files(storage.archives_dir) == archive_before
    assert len(storage.iter_all_events()) == 11


def test_backup_restore_retains_project_identity_and_assignment(service):
    p = service.create_project("P")
    q = service.create_project("Q")
    t = service.create_task("Task", "", project_id=p)
    _add_minutes(service, t, 60)
    expected = service.snapshot_dict()
    backup = service.backups.create_backup("son", "before changes")
    service.assign_task_to_project(t, q)
    service.rename_project(p, "Changed")
    service.restore_from_backup(backup)
    assert service.snapshot_dict() == expected
    assert service.state.tasks[t].task_id == t
    assert service.state.tasks[t].project_id == p
    assert service.task_elapsed(service.state.tasks[t], START) == 3600
    assert len(service.events) == 4


def test_empty_directory_does_not_import_or_modify_unrelated_history(tmp_path, clock, monkeypatch):
    old_home = tmp_path / "old-home"
    old_dir = old_home / ".task_timer_data"
    old_service = TaskTimerService(EventStorage(old_dir))
    old_task = old_service.create_task("Old task", "")
    _add_minutes(old_service, old_task, 60)
    old_service.create_time_submission_marker([old_task], None, START, "entered", None)
    old_service.subtask_template_store.path.write_text('{"templates": [{"name": "Old template", "items": []}]}', encoding="utf-8")
    old_files = _files(old_dir)
    monkeypatch.setattr(Path, "home", lambda: old_home)
    fresh = TaskTimerService(EventStorage(tmp_path / "new-installation"))
    assert fresh.state.projects == fresh.state.tasks == fresh.state.global_tags == {}
    assert fresh.state.running_task_id is None
    assert fresh.events == fresh.storage.iter_all_events() == []
    assert fresh.subtask_templates == fresh.list_time_submissions() == []
    assert fresh.find_active_export_checkpoint() is None
    assert fresh.storage.load_snapshot()["projects"] == {}
    assert fresh.storage.load_snapshot()["tasks"] == {}
    assert _files(old_dir) == old_files
