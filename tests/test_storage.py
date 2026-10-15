from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import pytest

from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage


def _tree(root: Path):
    """Include empty directories as well as all surviving file bytes."""
    return {str(path.relative_to(root)): None if path.is_dir() else path.read_bytes()
            for path in root.rglob('*')}


@pytest.mark.parametrize('existing_empty', [False, True])
def test_fresh_directory_initializes_and_restarts(tmp_path, existing_empty):
    root = tmp_path / 'fresh'
    if existing_empty:
        root.mkdir()
    storage = EventStorage(root)
    assert storage.active_path.read_bytes() == b''
    assert storage.archives_dir.is_dir()
    assert storage.load_manifest() == {'archives': [], 'next_sequence': 1}
    service = TaskTimerService(storage)
    task = service.create_task('Fresh task', '')
    journal, manifest = storage.active_path.read_bytes(), storage.manifest_path.read_bytes()
    restarted = TaskTimerService(EventStorage(root))
    assert restarted.state.tasks[task].name == 'Fresh task'
    assert len(restarted.events) == 1
    assert storage.active_path.read_bytes() == journal
    assert storage.manifest_path.read_bytes() == manifest


def test_healthy_existing_empty_journal_is_not_missing(tmp_path):
    service = TaskTimerService(EventStorage(tmp_path / 'empty'))
    manifest = service.storage.manifest_path.read_bytes()
    restarted = TaskTimerService(EventStorage(service.storage.data_dir))
    assert restarted.events == [] and restarted.state.tasks == {}
    assert restarted.storage.active_path.read_bytes() == b''
    assert restarted.storage.manifest_path.read_bytes() == manifest


@pytest.mark.parametrize('component', ['active_events.jsonl', 'log_manifest.json'])
@pytest.mark.parametrize('rotated', [False, True])
def test_missing_authoritative_component_refuses_restart_without_mutation(tmp_path, component, rotated):
    root = tmp_path / 'history'
    service = TaskTimerService(EventStorage(root))
    task = service.create_task('Recorded task', '')
    start = datetime(2026, 10, 12, 9, tzinfo=timezone.utc)
    service.add_manual_interval(task, start, start + timedelta(hours=1), 'Real recorded work')
    if rotated:
        service.storage.max_active_events = 1
        service.storage.rotate_if_needed()
        assert service.storage.load_manifest()['archives']
    assert service.storage.snapshot_path.is_file()
    service.create_backup_now()
    (root / 'unrelated.txt').write_bytes(b'preserve unrelated data')
    (root / 'subtask_templates.json').write_text('{"templates": []}', encoding='utf-8')
    (root / component).unlink()
    before = _tree(root)
    with pytest.raises(ValueError, match='initialization refused to protect existing history') as error:
        TaskTimerService(EventStorage(root))
    assert component in str(error.value)
    assert not (root / component).exists()
    assert _tree(root) == before


@pytest.mark.parametrize('seed', ['state_snapshot.json', 'unrelated.txt', 'archives', 'backups'])
def test_nonempty_directory_without_journal_is_not_a_fresh_dataset(tmp_path, seed):
    root = tmp_path / 'existing'
    root.mkdir()
    if seed in ('archives', 'backups'):
        (root / seed).mkdir()  # even one empty subdirectory disqualifies freshness
    else:
        (root / seed).write_text(json.dumps({'preserve': 'existing content'}), encoding='utf-8')
    before = _tree(root)
    with pytest.raises(ValueError, match='initialization refused to protect existing history') as error:
        TaskTimerService(EventStorage(root))
    assert 'active_events.jsonl' in str(error.value)
    assert not (root / 'active_events.jsonl').exists()
    assert not (root / 'log_manifest.json').exists()
    assert _tree(root) == before


@pytest.mark.parametrize('component', ['active_events.jsonl', 'log_manifest.json'])
def test_authoritative_components_must_be_regular_files_before_any_writes(tmp_path, component):
    root = tmp_path / 'existing'
    EventStorage(root)
    (root / component).unlink()
    (root / component).mkdir()
    (root / 'archives').rmdir()  # rejection must not recreate even this directory
    before = _tree(root)
    with pytest.raises(ValueError, match='not a regular file') as error:
        EventStorage(root)
    assert component in str(error.value)
    assert _tree(root) == before


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
    service.edit_interval(task_id, interval_id, start, datetime(2026, 1, 1, 12, 0).astimezone(), "edit")
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

    service2 = TaskTimerService(EventStorage(tmp_path, max_active_size_bytes=200, max_active_events=2))
    assert service2.state.tasks[t].intervals
