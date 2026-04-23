"""Persistence helpers for lightweight UI preferences."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


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
