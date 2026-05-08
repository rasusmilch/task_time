from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone

from loguru import logger

from task_timer.backups import BackupManager
from task_timer.settings import BackupSettings, BackupSettingsStore


def test_create_backup_contains_manifest_and_core_files(tmp_path) -> None:
    (tmp_path / "active_events.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "log_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state_snapshot.json").write_text("{}", encoding="utf-8")
    (tmp_path / "archives").mkdir()
    (tmp_path / "archives" / "seg.jsonl").write_text("{}\n", encoding="utf-8")

    manager = BackupManager(tmp_path)
    backup = manager.create_backup("son", "test")

    with zipfile.ZipFile(backup, "r") as zf:
        names = set(zf.namelist())
        assert "active_events.jsonl" in names
        assert "archives/seg.jsonl" in names
        assert "log_manifest.json" in names
        assert "state_snapshot.json" in names
        manifest = json.loads(zf.read("backup_manifest.json").decode("utf-8"))
        assert manifest["backup_type"] == "son"
        assert manifest["reason"] == "test"


def test_same_day_backups_not_trimmed_by_count_when_within_retention_days(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "active_events.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "log_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state_snapshot.json").write_text("{}", encoding="utf-8")
    manager = BackupManager(tmp_path)
    settings = manager.load_settings()
    settings.son_keep_days = 14
    manager.save_settings(settings)
    base = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    counter = {"i": 0}

    def _tick():
        counter["i"] += 1
        return base + timedelta(minutes=counter["i"])

    monkeypatch.setattr("task_timer.backups.utc_now", _tick)
    manager.create_backup("son", "a")
    manager.create_backup("son", "b")
    manager.create_backup("son", "c")
    backups = list((tmp_path / "backups" / "sons").glob("*.zip"))
    assert len(backups) == 3


def test_retention_cleanup_deletes_old_son_backups_by_age(tmp_path, monkeypatch) -> None:
    (tmp_path / "active_events.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "log_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state_snapshot.json").write_text("{}", encoding="utf-8")
    manager = BackupManager(tmp_path)
    settings = manager.load_settings()
    settings.son_keep_days = 2
    manager.save_settings(settings)
    monkeypatch.setattr(
        "task_timer.backups.utc_now",
        lambda: datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc),
    )
    manager.create_backup("son", "recent")
    monkeypatch.setattr(
        "task_timer.backups.utc_now",
        lambda: datetime(2026, 1, 7, 12, 0, tzinfo=timezone.utc),
    )
    old_path = manager.create_backup("son", "old")
    monkeypatch.setattr(
        "task_timer.backups.utc_now",
        lambda: datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc),
    )
    manager.apply_retention()
    assert not old_path.exists()


def test_corrupt_backup_settings_falls_back_to_defaults(tmp_path) -> None:
    (tmp_path / "backup_settings.json").write_text("not-json", encoding="utf-8")
    loaded = BackupSettingsStore(tmp_path).load()
    assert loaded.son_keep_days == 14
    assert loaded.father_keep_days == 56
    assert loaded.grandfather_keep_days == 365


def test_backup_manager_initialization_creates_backup_settings_file(tmp_path) -> None:
    assert not (tmp_path / "backup_settings.json").exists()
    BackupManager(tmp_path)
    assert (tmp_path / "backup_settings.json").exists()


def test_backup_settings_persist_and_reload(tmp_path) -> None:
    manager = BackupManager(tmp_path)
    settings = BackupSettings(son_keep_days=3, father_keep_days=4, grandfather_keep_days=5)
    manager.save_settings(settings)
    reloaded = manager.load_settings()
    assert reloaded.son_keep_days == 3
    assert reloaded.father_keep_days == 4
    assert reloaded.grandfather_keep_days == 5


def test_restore_failure_logs_error(tmp_path) -> None:
    manager = BackupManager(tmp_path)
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("backup_manifest.json", json.dumps({"app_name": "Chronicle"}))
        zf.writestr("active_events.jsonl", "{}\n")
    original = manager._extract_zip_safely

    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    manager._extract_zip_safely = _boom  # type: ignore[assignment]
    messages: list[str] = []
    sink = logger.add(lambda m: messages.append(str(m)), level="ERROR")
    try:
        try:
            manager.restore_backup(broken)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected restore to fail")
    finally:
        manager._extract_zip_safely = original  # type: ignore[assignment]
        logger.remove(sink)
    assert any("Restore failed for backup" in msg for msg in messages)


def test_restore_rejects_invalid_backup_zip(tmp_path) -> None:
    manager = BackupManager(tmp_path)
    invalid_zip = tmp_path / "backups" / "sons" / "bad.zip"
    invalid_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(invalid_zip, "w") as zf:
        zf.writestr("something.txt", "x")
    try:
        manager.restore_backup(invalid_zip)
    except ValueError as exc:
        assert "Invalid backup zip" in str(exc)
    else:
        raise AssertionError("Expected restore rejection")


def test_should_create_automatic_backup_respects_min_interval(tmp_path, monkeypatch) -> None:
    manager = BackupManager(tmp_path)
    settings = manager.load_settings()
    settings.auto_backup_min_interval_minutes = 60
    manager.save_settings(settings)
    assert manager.should_create_automatic_backup("automatic backup on app start") is True

    base = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("task_timer.backups.utc_now", lambda: base)
    manager.create_backup("son", "seed")
    assert (
        manager.should_create_automatic_backup(
            "automatic backup on app start", now_utc=base + timedelta(minutes=30)
        )
        is False
    )
    assert (
        manager.should_create_automatic_backup(
            "automatic backup on app start", now_utc=base + timedelta(minutes=61)
        )
        is True
    )


def test_retention_cleanup_deletes_old_father_and_grandfather_backups_by_age(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "active_events.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "log_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state_snapshot.json").write_text("{}", encoding="utf-8")
    manager = BackupManager(tmp_path)
    settings = manager.load_settings()
    settings.father_keep_days = 7
    settings.grandfather_keep_days = 30
    manager.save_settings(settings)

    monkeypatch.setattr(
        "task_timer.backups.utc_now",
        lambda: datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
    )
    manager.create_backup("father", "recent father")
    manager.create_backup("grandfather", "recent grandfather")
    monkeypatch.setattr(
        "task_timer.backups.utc_now",
        lambda: datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    old_father = manager.create_backup("father", "old father")
    old_grandfather = manager.create_backup("grandfather", "old grandfather")

    monkeypatch.setattr(
        "task_timer.backups.utc_now",
        lambda: datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc),
    )
    manager.apply_retention()
    assert not old_father.exists()
    assert not old_grandfather.exists()


def _seed_data_dir(tmp_path) -> None:
    (tmp_path / "active_events.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "log_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state_snapshot.json").write_text("{}", encoding="utf-8")
    (tmp_path / "subtask_templates.json").write_text("[]", encoding="utf-8")


def test_new_backup_uses_chronicle_prefix(tmp_path) -> None:
    _seed_data_dir(tmp_path)
    backup = BackupManager(tmp_path).create_backup("son", "test")
    assert backup.name.startswith("chronicle_son_")


def test_old_task_timer_backup_still_listed_and_restored(tmp_path) -> None:
    _seed_data_dir(tmp_path)
    manager = BackupManager(tmp_path)
    backup = manager.create_backup("son", "seed")
    legacy = backup.with_name(backup.name.replace("chronicle_", "task_timer_"))
    backup.rename(legacy)

    listed = manager.list_backups()
    assert any(item.path == legacy for item in listed)

    (tmp_path / "active_events.jsonl").write_text('{"changed":true}\n', encoding="utf-8")
    manager.restore_backup(legacy)
    assert (tmp_path / "active_events.jsonl").read_text(encoding="utf-8") == "{}\n"


def test_old_manifest_without_app_name_is_accepted(tmp_path) -> None:
    _seed_data_dir(tmp_path)
    manager = BackupManager(tmp_path)
    backup = manager.create_backup("son", "seed")
    with zipfile.ZipFile(backup, "a") as zf:
        manifest = json.loads(zf.read("backup_manifest.json").decode("utf-8"))
        manifest.pop("app_name", None)
        zf.writestr("backup_manifest.json", json.dumps(manifest))
    manager.restore_backup(backup)


def test_restore_rejects_unsafe_parent_path(tmp_path, caplog) -> None:
    manager = BackupManager(tmp_path)
    bad = tmp_path / "bad_parent.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("backup_manifest.json", json.dumps({"app_name": "Chronicle"}))
        zf.writestr("../evil.txt", "x")
        zf.writestr("active_events.jsonl", "{}\n")
    try:
        manager.restore_backup(bad)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected unsafe zip to be rejected")


def test_restore_rejects_unsafe_absolute_path(tmp_path) -> None:
    manager = BackupManager(tmp_path)
    bad = tmp_path / "bad_absolute.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("backup_manifest.json", json.dumps({"app_name": "Chronicle"}))
        zf.writestr("/tmp/evil.txt", "x")
        zf.writestr("active_events.jsonl", "{}\n")
    try:
        manager.restore_backup(bad)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected unsafe zip to be rejected")


def test_restore_rejects_drive_letter_path(tmp_path) -> None:
    manager = BackupManager(tmp_path)
    bad = tmp_path / "bad_drive.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("backup_manifest.json", json.dumps({"app_name": "Chronicle"}))
        zf.writestr("C:/evil.txt", "x")
        zf.writestr("active_events.jsonl", "{}\n")
    try:
        manager.restore_backup(bad)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected unsafe zip to be rejected")


def test_restore_failure_does_not_wipe_current_data(tmp_path) -> None:
    _seed_data_dir(tmp_path)
    manager = BackupManager(tmp_path)
    manager.create_backup("son", "seed")
    (tmp_path / "active_events.jsonl").write_text('{"local":"keep"}\n', encoding="utf-8")

    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("backup_manifest.json", json.dumps({"app_name": "Chronicle"}))
        zf.writestr("state_snapshot.json", "{}")

    try:
        manager.restore_backup(broken)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected restore to fail")
    assert (tmp_path / "active_events.jsonl").read_text(encoding="utf-8") == '{"local":"keep"}\n'
