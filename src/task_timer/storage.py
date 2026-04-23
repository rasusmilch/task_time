"""Event-log storage and snapshot persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class EventStorage:
    """Manage append-only event segments, manifest, and snapshot files."""

    def __init__(
        self,
        data_dir: Path,
        *,
        max_active_size_bytes: int = 2 * 1024 * 1024,
        max_active_events: int = 5000,
    ) -> None:
        self.data_dir = data_dir
        self.archives_dir = data_dir / "archives"
        self.active_path = data_dir / "active_events.jsonl"
        self.snapshot_path = data_dir / "state_snapshot.json"
        self.manifest_path = data_dir / "log_manifest.json"
        self.max_active_size_bytes = max_active_size_bytes
        self.max_active_events = max_active_events

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.archives_dir.mkdir(parents=True, exist_ok=True)
        if not self.active_path.exists():
            self.active_path.write_text("", encoding="utf-8")
        if not self.manifest_path.exists():
            self._atomic_write_json(self.manifest_path, {"archives": [], "next_sequence": 1})

    def append_event(self, event: dict[str, Any]) -> None:
        """Append one event line and durably flush it."""
        line = json.dumps(event, ensure_ascii=False)
        with self.active_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.rotate_if_needed()

    def load_manifest(self) -> dict[str, Any]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def load_snapshot(self) -> dict[str, Any] | None:
        if not self.snapshot_path.exists():
            return None
        try:
            return json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._atomic_write_json(self.snapshot_path, snapshot)

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        self._atomic_write_json(self.manifest_path, manifest)

    def iter_all_events(self) -> list[dict[str, Any]]:
        """Load all events from archived segments plus active segment."""
        manifest = self.load_manifest()
        events: list[dict[str, Any]] = []
        for segment in manifest.get("archives", []):
            seg_path = self.data_dir / segment["path"]
            if seg_path.exists():
                events.extend(self._read_jsonl(seg_path))
        events.extend(self._read_jsonl(self.active_path))
        events.sort(key=lambda item: item["timestamp_utc"])
        return events

    def source_segments(self) -> list[str]:
        """Return archive and active segment names for export metadata."""
        manifest = self.load_manifest()
        names = [entry["path"] for entry in manifest.get("archives", [])]
        names.append(self.active_path.name)
        return names

    def rotate_if_needed(self) -> None:
        """Seal active log into archive when thresholds are reached."""
        size = self.active_path.stat().st_size
        if size == 0:
            return
        active_count = self._line_count(self.active_path)
        if size < self.max_active_size_bytes and active_count < self.max_active_events:
            return
        events = self._read_jsonl(self.active_path)
        if not events:
            return
        manifest = self.load_manifest()
        seq = int(manifest.get("next_sequence", 1))
        start_ts = events[0]["timestamp_utc"].replace(":", "").replace("-", "")
        end_ts = events[-1]["timestamp_utc"].replace(":", "").replace("-", "")
        archive_name = f"events_{seq:06d}_{start_ts}_{end_ts}.jsonl"
        archive_rel = f"archives/{archive_name}"
        archive_path = self.archives_dir / archive_name
        self.active_path.replace(archive_path)
        self.active_path.write_text("", encoding="utf-8")

        manifest.setdefault("archives", []).append(
            {
                "sequence": seq,
                "path": archive_rel,
                "start_timestamp_utc": events[0]["timestamp_utc"],
                "end_timestamp_utc": events[-1]["timestamp_utc"],
                "event_count": len(events),
            }
        )
        manifest["next_sequence"] = seq + 1
        self.save_manifest(manifest)

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        if not path.exists():
            return output
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                output.append(json.loads(line))
        return output

    @staticmethod
    def _line_count(path: Path) -> int:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
