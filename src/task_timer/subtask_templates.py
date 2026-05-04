"""Persistent reusable subtask template models and storage."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .tags import normalize_tag_list


@dataclass(slots=True)
class SubtaskTemplateItem:
    item_id: str
    name: str
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    sort_order: int = 0

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Template item name is required")
        self.notes = self.notes.strip()
        self.tags = normalize_tag_list(self.tags)

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "notes": self.notes,
            "tags": list(self.tags),
            "sort_order": self.sort_order,
        }


@dataclass(slots=True)
class SubtaskTemplate:
    template_id: str
    name: str
    notes: str = ""
    items: list[SubtaskTemplateItem] = field(default_factory=list)
    created_at_utc: str = ""
    updated_at_utc: str = ""

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Template name is required")
        self.notes = self.notes.strip()

    def to_dict(self) -> dict[str, object]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "notes": self.notes,
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
            "items": [item.to_dict() for item in self.items],
        }


class SubtaskTemplateStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / "subtask_templates.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def ensure_file_exists(self) -> None:
        if self.path.exists():
            return
        self.save([])

    def load(self) -> list[SubtaskTemplate]:
        self.ensure_file_exists()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            self._mark_corrupt_file()
            self.save([])
            return []
        templates_raw = payload.get("templates", []) if isinstance(payload, dict) else []
        output: list[SubtaskTemplate] = []
        try:
            for row in templates_raw:
                items = [
                    SubtaskTemplateItem(
                        item_id=str(item.get("item_id", str(uuid4()))),
                        name=str(item.get("name", "")),
                        notes=str(item.get("notes", "")),
                        tags=list(item.get("tags", [])),
                        sort_order=int(item.get("sort_order", 0)),
                    )
                    for item in row.get("items", [])
                ]
                items.sort(key=lambda item: item.sort_order)
                output.append(
                    SubtaskTemplate(
                        template_id=str(row.get("template_id", str(uuid4()))),
                        name=str(row.get("name", "")),
                        notes=str(row.get("notes", "")),
                        items=items,
                        created_at_utc=str(row.get("created_at_utc", "")),
                        updated_at_utc=str(row.get("updated_at_utc", "")),
                    )
                )
        except Exception:  # noqa: BLE001
            self._mark_corrupt_file()
            self.save([])
            return []
        return output

    def save(self, templates: list[SubtaskTemplate]) -> None:
        payload = {
            "schema_version": 1,
            "templates": [template.to_dict() for template in templates],
        }
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(self.path)

    def _mark_corrupt_file(self) -> None:
        if not self.path.exists():
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        corrupt_path = self.path.with_name(f"{self.path.name}.corrupt.{stamp}")
        self.path.replace(corrupt_path)
