from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone

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


def test_same_day_backups_not_trimmed_by_count_when_within_retention_days(tmp_path, monkeypatch) -> None:
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
    monkeypatch.setattr("task_timer.backups.utc_now", lambda: datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc))
    manager.create_backup("son", "recent")
    monkeypatch.setattr("task_timer.backups.utc_now", lambda: datetime(2026, 1, 7, 12, 0, tzinfo=timezone.utc))
    old_path = manager.create_backup("son", "old")
    monkeypatch.setattr("task_timer.backups.utc_now", lambda: datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc))
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
    assert manager.should_create_automatic_backup("automatic backup on app start", now_utc=base + timedelta(minutes=30)) is False
    assert manager.should_create_automatic_backup("automatic backup on app start", now_utc=base + timedelta(minutes=61)) is True


def test_retention_cleanup_deletes_old_father_and_grandfather_backups_by_age(tmp_path, monkeypatch) -> None:
    (tmp_path / "active_events.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "log_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "state_snapshot.json").write_text("{}", encoding="utf-8")
    manager = BackupManager(tmp_path)
    settings = manager.load_settings()
    settings.father_keep_days = 7
    settings.grandfather_keep_days = 30
    manager.save_settings(settings)

    monkeypatch.setattr("task_timer.backups.utc_now", lambda: datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc))
    manager.create_backup("father", "recent father")
    manager.create_backup("grandfather", "recent grandfather")
    monkeypatch.setattr("task_timer.backups.utc_now", lambda: datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
    old_father = manager.create_backup("father", "old father")
    old_grandfather = manager.create_backup("grandfather", "old grandfather")

    monkeypatch.setattr("task_timer.backups.utc_now", lambda: datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc))
    manager.apply_retention()
    assert not old_father.exists()
    assert not old_grandfather.exists()
