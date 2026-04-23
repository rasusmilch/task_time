"""Core data models for the task timer app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


SCHEMA_VERSION = 1
NOTES_MAX_LENGTH = 160


@dataclass(slots=True)
class IntervalRecord:
    """A closed time interval belonging to a task."""

    interval_id: str
    task_id: str
    start_utc: datetime
    stop_utc: datetime
    source: str
    replaced_interval_id: str | None = None
    edit_reason: str | None = None
    deleted: bool = False


@dataclass(slots=True)
class TaskState:
    """Derived task state from replaying events."""

    task_id: str
    name: str
    notes: str
    is_deleted: bool
    is_running: bool
    created_at_utc: datetime
    updated_at_utc: datetime
    display_color: str = "neutral"
    currently_open_interval_start_utc: datetime | None = None
    last_reset_utc: datetime | None = None
    intervals: dict[str, IntervalRecord] = field(default_factory=dict)


@dataclass(slots=True)
class AppState:
    """Whole application derived state."""

    tasks: dict[str, TaskState] = field(default_factory=dict)
    running_task_id: str | None = None


def event_dict(
    *,
    timestamp_utc: str,
    local_timezone: str,
    task_id: str,
    event_type: str,
    payload: dict[str, Any],
    event_id: str,
) -> dict[str, Any]:
    """Build a stable event dictionary."""
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "timestamp_utc": timestamp_utc,
        "local_timezone": local_timezone,
        "task_id": task_id,
        "event_type": event_type,
        "payload": payload,
    }
