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

        # Classify before mkdir or file creation can hide lost journal evidence.
        # Even an empty subdirectory means this is not a fresh dataset.
        fresh = not self.data_dir.exists() or not any(self.data_dir.iterdir())
        if not fresh:
            for component in (self.active_path, self.manifest_path):
                if not component.is_file():
                    raise ValueError(
                        f"Authoritative journal component {component} is missing or not a regular file; "
                        "initialization refused to protect existing history"
                    )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.archives_dir.mkdir(parents=True, exist_ok=True)
        if fresh:
            self.active_path.write_text("", encoding="utf-8")
            self._atomic_write_json(self.manifest_path, {"archives": [], "next_sequence": 1})

    def append_event(self, event: dict[str, Any]) -> None:
        """Append one event line and durably flush it."""
        line = json.dumps(event, ensure_ascii=False)
        with self.active_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.rotate_if_needed()

    def load_manifest(self, *, strict: bool = False) -> dict[str, Any]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"),
                          object_pairs_hook=self._unique_json_fields if strict else None)

    def synchronize_journal(self) -> list[dict[str, Any]]:
        """Flush existing authoritative bytes for evidence-registration reuse/recovery.

        Serialized dataset ownership is required. This neither repairs the journal
        nor establishes directory-entry or universal power-loss durability.
        """
        self.iter_all_events(strict=True)
        manifest = self.load_manifest(strict=True)
        paths = [self.data_dir / segment["path"] for segment in manifest["archives"]]
        for path in [*paths, self.active_path, self.manifest_path]:
            with path.open("r+b") as handle:
                os.fsync(handle.fileno())
        return self.iter_all_events(strict=True)

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

    def iter_all_events(self, *, strict: bool = False) -> list[dict[str, Any]]:
        """Load all events from archived segments plus active segment."""
        manifest = self.load_manifest(strict=strict)
        if strict:
            if not isinstance(manifest, dict) or not isinstance(manifest.get("archives"), list):
                raise ValueError("Unreadable journal manifest")
            if type(manifest.get("next_sequence")) is not int or manifest["next_sequence"] < 1:
                raise ValueError("Invalid journal archive sequence")
            paths = []
            for segment in manifest["archives"]:
                path = segment.get("path") if isinstance(segment, dict) else None
                if not isinstance(path, str) or Path(path).parent != Path("archives"):
                    raise ValueError("Invalid journal archive reference")
                paths.append(self.data_dir / path)
            if len(set(paths)) != len(paths) or set(paths) != set(self.archives_dir.glob("*.jsonl")):
                raise ValueError("Journal archives are missing, duplicated or unindexed")
            if not self.active_path.is_file():
                raise ValueError("Journal active segment is missing")
        events: list[dict[str, Any]] = []
        read_sequence = 0
        for segment in manifest.get("archives", []):
            seg_path = self.data_dir / segment["path"]
            if strict or seg_path.exists():
                segment_events = self._read_jsonl(seg_path, strict=strict)
                if strict and segment.get("event_count") != len(segment_events):
                    raise ValueError("Journal archive event count mismatch")
                for event in segment_events:
                    event["_read_sequence"] = read_sequence
                    read_sequence += 1
                    events.append(event)
        for event in self._read_jsonl(self.active_path, strict=strict):
            event["_read_sequence"] = read_sequence
            read_sequence += 1
            events.append(event)
        events.sort(key=lambda item: (item["timestamp_utc"], item.get("_read_sequence", 0)))
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
    def _unique_json_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field in journal metadata or event")
            result[key] = value
        return result

    @staticmethod
    def _read_jsonl(path: Path, *, strict: bool = False) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        if not path.exists():
            if strict:
                raise ValueError("Journal segment is missing")
            return output
        with path.open("r", encoding="utf-8", newline="" if strict else None) as handle:
            for line in handle:
                if strict and not line.endswith("\n"):
                    raise ValueError("Journal has an incomplete JSONL record")
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line, object_pairs_hook=EventStorage._unique_json_fields) if strict else json.loads(line)
                if strict and (not isinstance(event, dict) or "_read_sequence" in event
                               or not {"event_id", "event_type", "task_id", "timestamp_utc", "payload"} <= event.keys()
                               or not isinstance(event["timestamp_utc"], str)):
                    raise ValueError("Invalid journal event envelope")
                output.append(event)
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
