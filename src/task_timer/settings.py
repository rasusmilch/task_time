"""Persistence helpers for lightweight UI preferences."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class UISettings:
    """Small set of UI-only preferences."""

    sort_alphabetically: bool = False


class UISettingsStore:
    """Read/write ui_settings.json in the app data directory."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "ui_settings.json"
        data_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> UISettings:
        if not self.path.exists():
            return UISettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return UISettings()
        return UISettings(sort_alphabetically=bool(payload.get("sort_alphabetically", False)))

    def save(self, settings: UISettings) -> None:
        self._atomic_write_json({"sort_alphabetically": settings.sort_alphabetically})

    def _atomic_write_json(self, payload: dict[str, bool]) -> None:
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(self.path)


@dataclass(slots=True)
class BackupSettings:
    son_keep_count: int = 14
    father_keep_count: int = 8
    grandfather_keep_count: int = 12
    auto_backup_before_risky_operations: bool = True
    auto_backup_on_app_start: bool = False
    auto_backup_min_interval_minutes: int = 60

    def to_payload(self) -> dict[str, Any]:
        return {
            "son_keep_count": self.son_keep_count,
            "father_keep_count": self.father_keep_count,
            "grandfather_keep_count": self.grandfather_keep_count,
            "auto_backup_before_risky_operations": self.auto_backup_before_risky_operations,
            "auto_backup_on_app_start": self.auto_backup_on_app_start,
            "auto_backup_min_interval_minutes": self.auto_backup_min_interval_minutes,
        }


class BackupSettingsStore:
    """Read/write backup_settings.json with safe defaults."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "backup_settings.json"
        data_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> BackupSettings:
        if not self.path.exists():
            defaults = BackupSettings()
            self.save(defaults)
            return defaults
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            defaults = BackupSettings()
            self.save(defaults)
            return defaults
        settings = BackupSettings(
            son_keep_count=self._positive_int(payload.get("son_keep_count"), 14),
            father_keep_count=self._positive_int(payload.get("father_keep_count"), 8),
            grandfather_keep_count=self._positive_int(payload.get("grandfather_keep_count"), 12),
            auto_backup_before_risky_operations=bool(payload.get("auto_backup_before_risky_operations", True)),
            auto_backup_on_app_start=bool(payload.get("auto_backup_on_app_start", False)),
            auto_backup_min_interval_minutes=self._positive_int(payload.get("auto_backup_min_interval_minutes"), 60),
        )
        return settings

    def save(self, settings: BackupSettings) -> None:
        self._atomic_write_json(settings.to_payload())

    @staticmethod
    def _positive_int(value: Any, fallback: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return parsed if parsed > 0 else fallback

    def _atomic_write_json(self, payload: dict[str, Any]) -> None:
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(self.path)
