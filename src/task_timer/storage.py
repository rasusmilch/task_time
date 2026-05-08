"""Event-log storage and snapshot persistence."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from task_timer.time_utils import parse_utc_z


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
        self.corrupt_dir = self.data_dir / "corrupt"
        self.corrupt_events_path: Path | None = None
        self.corrupt_event_count = 0

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
        default_manifest = {"archives": [], "next_sequence": 1}
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            self._preserve_corrupt_manifest(reason=str(exc))
            self.save_manifest(default_manifest)
            return default_manifest
        if not self._is_valid_manifest_shape(manifest):
            self._preserve_corrupt_manifest(reason="Invalid manifest shape")
            self.save_manifest(default_manifest)
            return default_manifest
        return self._sanitize_manifest_archives(manifest)

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
        read_sequence = 0
        for segment in manifest.get("archives", []):
            seg_path = self.data_dir / segment["path"]
            if seg_path.exists():
                for event in self._read_jsonl(seg_path):
                    event["_read_sequence"] = read_sequence
                    read_sequence += 1
                    events.append(event)
        for event in self._read_jsonl(self.active_path):
            event["_read_sequence"] = read_sequence
            read_sequence += 1
            events.append(event)
        events.sort(key=lambda item: (item["timestamp_utc"], item.get("_read_sequence", 0)))
        if self.corrupt_event_count:
            logger.warning(
                "Chronicle skipped {} corrupt journal event lines during startup. A copy was saved for inspection.",
                self.corrupt_event_count,
            )
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

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        if not path.exists():
            return output
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Skipped corrupt event line in {}:{}: {}",
                        path,
                        line_number,
                        exc,
                    )
                    self._quarantine_corrupt_line(
                        source_path=path,
                        line_number=line_number,
                        raw_text=raw_line.rstrip("\n"),
                        error_message=str(exc),
                    )
                    continue
                invalid_reason = self._invalid_event_reason(event)
                if invalid_reason:
                    logger.warning(
                        "Skipped corrupt event line in {}:{}: {}",
                        path,
                        line_number,
                        invalid_reason,
                    )
                    self._quarantine_corrupt_line(
                        source_path=path,
                        line_number=line_number,
                        raw_text=raw_line.rstrip("\n"),
                        error_message=invalid_reason,
                    )
                    continue
                output.append(event)
        logger.info("Loaded {} valid events from {}", len(output), path)
        return output

    @staticmethod
    def _is_valid_event_shape(event: Any) -> bool:
        return EventStorage._invalid_event_reason(event) is None

    @staticmethod
    def _invalid_event_reason(event: Any) -> str | None:
        if not isinstance(event, dict):
            return "Event is not a JSON object"
        required_keys = {
            "schema_version",
            "event_id",
            "timestamp_utc",
            "task_id",
            "event_type",
            "payload",
        }
        if not required_keys.issubset(event):
            return "Missing required event keys"
        if not isinstance(event["event_id"], str) or not event["event_id"].strip():
            return "event_id must be a non-empty string"
        if not isinstance(event["timestamp_utc"], str):
            return "timestamp_utc must be a string"
        try:
            parse_utc_z(event["timestamp_utc"])
        except ValueError:
            return "timestamp_utc is not parseable as UTC Z time"
        if not isinstance(event["task_id"], str) or not event["task_id"].strip():
            return "task_id must be a non-empty string"
        if not isinstance(event["event_type"], str) or not event["event_type"].strip():
            return "event_type must be a non-empty string"
        if not isinstance(event["payload"], dict):
            return "payload must be a JSON object"
        return None

    def _preserve_corrupt_manifest(self, *, reason: str) -> None:
        try:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = self.manifest_path.with_name(f"{self.manifest_path.name}.corrupt.{stamp}")
            self.manifest_path.replace(backup_path)
            logger.warning(
                "Recovered from corrupt manifest at {} (reason: {}). Saved copy to {}",
                self.manifest_path,
                reason,
                backup_path,
            )
        except OSError as exc:
            logger.warning("Failed to preserve corrupt manifest at {}: {}", self.manifest_path, exc)

    @staticmethod
    def _is_valid_manifest_shape(manifest: Any) -> bool:
        return (
            isinstance(manifest, dict)
            and isinstance(manifest.get("archives"), list)
            and isinstance(manifest.get("next_sequence"), int)
            and manifest["next_sequence"] > 0
        )

    def _sanitize_manifest_archives(self, manifest: dict[str, Any]) -> dict[str, Any]:
        archives = manifest.get("archives", [])
        valid_archives: list[dict[str, Any]] = []
        for entry in archives:
            if not isinstance(entry, dict):
                logger.warning("Skipping malformed manifest archive entry (not object): {}", entry)
                continue
            path_value = entry.get("path")
            if not isinstance(path_value, str) or not self._is_safe_archive_path(path_value):
                logger.warning("Skipping malformed manifest archive entry path: {}", path_value)
                continue
            valid_archives.append(entry)
        manifest["archives"] = valid_archives
        return manifest

    @staticmethod
    def _is_safe_archive_path(path_value: str) -> bool:
        archive_path = Path(path_value)
        if archive_path.is_absolute():
            return False
        return ".." not in archive_path.parts

    def _quarantine_corrupt_line(
        self, *, source_path: Path, line_number: int, raw_text: str, error_message: str
    ) -> None:
        try:
            if self.corrupt_events_path is None:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                self.corrupt_dir.mkdir(parents=True, exist_ok=True)
                self.corrupt_events_path = self.corrupt_dir / f"corrupt_events_{stamp}.jsonl"
            payload = {
                "source_path": str(source_path),
                "line_number": line_number,
                "raw_text": raw_text,
                "error": error_message,
            }
            with self.corrupt_events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.corrupt_event_count += 1
        except OSError:
            logger.error("Failed to quarantine corrupt event line from {}", source_path)

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
