"""Managed automatic backup and restore helpers."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import BackupSettings, BackupSettingsStore
from .time_utils import utc_now


@dataclass(slots=True)
class BackupEntry:
    path: Path
    backup_type: str
    created_utc: str
    reason: str
    app_version: str | None


class BackupManager:
    """Creates/retains GFS-style backups under the managed data directory."""

    def __init__(self, data_dir: Path, app_version: str | None = None) -> None:
        self.data_dir = data_dir
        self.backups_dir = data_dir / "backups"
        self.sons_dir = self.backups_dir / "sons"
        self.fathers_dir = self.backups_dir / "fathers"
        self.grandfathers_dir = self.backups_dir / "grandfathers"
        self.settings_store = BackupSettingsStore(data_dir)
        self.app_version = app_version
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.sons_dir.mkdir(parents=True, exist_ok=True)
        self.fathers_dir.mkdir(parents=True, exist_ok=True)
        self.grandfathers_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, backup_type: str, reason: str) -> Path:
        now = utc_now()
        target_dir = self._backup_dir(backup_type)
        timestamp = now.astimezone(timezone.utc).strftime("%Y-%m-%d_%H%M%S_%f")
        zip_path = target_dir / f"task_timer_{backup_type}_{timestamp}.zip"
        included = self._build_backup_archive(zip_path)
        manifest = {
            "backup_created_utc": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "backup_type": backup_type,
            "app_version": self.app_version,
            "source_data_directory": str(self.data_dir),
            "included_files": included,
            "reason": reason,
            "schema_version": 1,
        }
        with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("backup_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

        if backup_type == "son":
            self._maybe_promote_periodic(now, reason)
        self.apply_retention()
        return zip_path

    def create_safety_backup(self, reason: str) -> Path:
        return self.create_backup("son", f"safety: {reason}")

    def apply_retention(self) -> None:
        settings = self.settings_store.load()
        self._trim_dir(self.sons_dir, settings.son_keep_count)
        self._trim_dir(self.fathers_dir, settings.father_keep_count)
        self._trim_dir(self.grandfathers_dir, settings.grandfather_keep_count)

    def list_backups(self) -> list[BackupEntry]:
        entries: list[BackupEntry] = []
        for backup_type, backup_dir in (("son", self.sons_dir), ("father", self.fathers_dir), ("grandfather", self.grandfathers_dir)):
            for path in backup_dir.glob("*.zip"):
                manifest = self._read_manifest(path)
                entries.append(
                    BackupEntry(
                        path=path,
                        backup_type=backup_type,
                        created_utc=str(manifest.get("backup_created_utc", "")),
                        reason=str(manifest.get("reason", "")),
                        app_version=manifest.get("app_version"),
                    )
                )
        entries.sort(key=lambda item: item.created_utc, reverse=True)
        return entries

    def restore_backup(self, backup_zip: Path) -> None:
        manifest = self._read_manifest(backup_zip)
        if not manifest:
            raise ValueError("Invalid backup zip: missing backup_manifest.json")
        self.create_safety_backup("before restore")
        temp_dir = self.data_dir.parent / f".restore_tmp_{os.getpid()}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(backup_zip, "r") as zf:
                zf.extractall(temp_dir)
            if not (temp_dir / "active_events.jsonl").exists():
                raise ValueError("Backup archive is missing active_events.jsonl")
            for entry in self.data_dir.iterdir():
                if entry.name == "backups":
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink(missing_ok=True)
            for extracted in temp_dir.iterdir():
                if extracted.name == "backup_manifest.json":
                    continue
                destination = self.data_dir / extracted.name
                if extracted.is_dir():
                    shutil.copytree(extracted, destination)
                else:
                    shutil.copy2(extracted, destination)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def open_backup_folder(self) -> Path:
        return self.backups_dir

    def _build_backup_archive(self, zip_path: Path) -> list[str]:
        included_files: list[str] = []
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for child in sorted(self.data_dir.iterdir(), key=lambda p: p.name):
                if child.name == "backups":
                    continue
                rel = child.relative_to(self.data_dir)
                if child.is_dir():
                    for nested in sorted(child.rglob("*")):
                        if nested.is_file():
                            arcname = str(nested.relative_to(self.data_dir))
                            zf.write(nested, arcname=arcname)
                            included_files.append(arcname)
                elif child.is_file():
                    zf.write(child, arcname=str(rel))
                    included_files.append(str(rel))
        return included_files

    def _maybe_promote_periodic(self, now: datetime, reason: str) -> None:
        if now.weekday() == 6:
            self.create_backup("father", f"weekly promotion: {reason}")
        if now.day == 1:
            self.create_backup("grandfather", f"monthly promotion: {reason}")

    @staticmethod
    def _trim_dir(directory: Path, keep_count: int) -> None:
        backups = sorted(directory.glob("*.zip"), key=lambda p: p.name, reverse=True)
        for path in backups[keep_count:]:
            path.unlink(missing_ok=True)

    @staticmethod
    def _read_manifest(path: Path) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(path, "r") as zf:
                with zf.open("backup_manifest.json") as handle:
                    return json.loads(handle.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _backup_dir(self, backup_type: str) -> Path:
        if backup_type == "son":
            return self.sons_dir
        if backup_type == "father":
            return self.fathers_dir
        if backup_type == "grandfather":
            return self.grandfathers_dir
        raise ValueError(f"Unknown backup type: {backup_type}")
