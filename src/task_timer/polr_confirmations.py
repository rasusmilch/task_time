"""Pure immutable confirmation validation/replay; service owns batch registration."""

from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from .export_snapshots import EXPORT_EVENT_TYPE, collect_export_snapshots, same_export_event, validate_uuid
from .models import SCHEMA_VERSION

CONFIRMATION_EVENT_TYPE = "polr_confirmation_batch_recorded"


def requires_stale_export_acknowledgement(
    export_position: int | None, confirmation_position: int | None,
    confirmed_hundredths: int | None, proposed_hundredths: int,
) -> bool:
    """One cell's conflict, using first physical occurrences of validated evidence."""
    return (export_position is not None and confirmation_position is not None
            and confirmation_position > export_position
            and confirmed_hundredths != proposed_hundredths)


def _fields(value: Any, names: str) -> None:
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError(f"Invalid confirmation fields: expected {names}")


def validate_polr_confirmation_batch(event: Any) -> None:
    """Validate exact persisted shape/types; journal relationships follow in replay."""
    _fields(event, "schema_version event_id timestamp_utc local_timezone task_id event_type payload")
    if type(event["schema_version"]) is not int or event["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported confirmation schema version")
    validate_uuid(event["event_id"])
    if event["task_id"] != "__app__" or event["event_type"] != CONFIRMATION_EVENT_TYPE:
        raise ValueError("Confirmation batches require the application event owner/type")
    timestamp = event["timestamp_utc"]
    if not isinstance(timestamp, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", timestamp):
        raise ValueError("Confirmation audit timestamp must use canonical UTC seconds with Z suffix")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid confirmation audit timestamp") from None
    zone = event["local_timezone"]
    if type(zone) is not str or not zone or zone != zone.strip():
        raise ValueError("Confirmation timezone metadata must be nonempty text without surrounding whitespace")
    try:
        zone.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Confirmation timezone metadata must be valid UTF-8") from None
    if any(ord(char) < 0x20 or 0x7f <= ord(char) <= 0x9f for char in zone):
        raise ValueError("Confirmation timezone metadata must not contain control characters")
    _fields(event["payload"], "cells")
    cells = event["payload"]["cells"]
    if not isinstance(cells, list) or not cells:
        raise ValueError("Confirmation batch must contain one or more cells")
    keys = set()
    for cell in cells:
        _fields(cell, "task_id work_date confirmed_hundredths source_export_id expected_prior_confirmation_id stale_export_acknowledged")
        validate_uuid(cell["task_id"])
        work_date = cell["work_date"]
        try:
            if not isinstance(work_date, str) or date.fromisoformat(work_date).isoformat() != work_date:
                raise ValueError
        except ValueError:
            raise ValueError("Confirmation work date must be a canonical ISO calendar date") from None
        key = cell["task_id"], work_date
        if key in keys:
            raise ValueError("Duplicate task/day in confirmation batch")
        keys.add(key)
        amount = cell["confirmed_hundredths"]
        if type(amount) is not int or amount < 0:
            raise ValueError("Confirmed hundredths must be a nonnegative integer")
        for name in ("source_export_id", "expected_prior_confirmation_id"):
            if cell[name] is not None:
                validate_uuid(cell[name])
        if type(cell["stale_export_acknowledged"]) is not bool:
            raise ValueError("Stale-export acknowledgement must be boolean")


def collect_polr_confirmations(events: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Pure whole-journal validation and effective task/day projection in physical order."""
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError("Confirmation replay requires journal event objects")
    exports = collect_export_snapshots(events)
    ordered = sorted(enumerate(events), key=lambda pair: pair[1].get("_read_sequence", pair[0]))
    known_tasks, other_ids = set(), set()
    batches, source_cells, export_positions = {}, {}, {}
    effective, confirmation_positions = {}, {}
    for position, (_, loaded) in enumerate(ordered):
        event = {name: value for name, value in loaded.items() if name != "_read_sequence"}
        identity = event.get("event_id")
        if event.get("event_type") != CONFIRMATION_EVENT_TYPE:
            if isinstance(identity, str):
                if identity in batches:
                    raise ValueError("Confirmation identity collides with another event type")
                other_ids.add(identity)
            if event.get("event_type") == "task_created":
                known_tasks.add(event["task_id"])
            if event.get("event_type") == EXPORT_EVENT_TYPE and identity not in source_cells:
                source_cells[identity] = {
                    (task["task_id"], cell["work_date"]): cell["decimal_hundredths"]
                    for task in exports[identity]["payload"]["tasks"] for cell in task["daily"]
                }
                export_positions[identity] = position
            continue
        validate_polr_confirmation_batch(event)
        if identity in other_ids:
            raise ValueError("Confirmation identity collides with another event type")
        if identity in batches:
            if not same_export_event(batches[identity], event):
                raise ValueError("Conflicting duplicate confirmation identity")
            continue  # exact retry cannot roll back cells changed by a newer batch
        pending = {}
        for cell in event["payload"]["cells"]:
            key = cell["task_id"], cell["work_date"]
            if cell["task_id"] not in known_tasks:
                raise ValueError("Confirmation task must have preceding creation evidence")
            prior = effective.get(key)
            expected_prior = prior["batch_event_id"] if prior is not None else None
            if cell["expected_prior_confirmation_id"] != expected_prior:
                raise ValueError("Confirmation expected prior identity does not match latest task/day batch")
            source = cell["source_export_id"]
            if source is not None:
                if source not in source_cells or key not in source_cells[source]:
                    raise ValueError("Confirmation requires a preceding registered export task/day cell")
                if cell["confirmed_hundredths"] != source_cells[source][key]:
                    raise ValueError("Confirmation amount differs from the frozen export cell")
            stale = requires_stale_export_acknowledgement(
                export_positions.get(source), confirmation_positions.get(key),
                prior["confirmed_hundredths"] if prior is not None else None,
                cell["confirmed_hundredths"],
            )
            if cell["stale_export_acknowledged"] != stale:
                raise ValueError("Stale-export acknowledgement must match this cell's applicable conflict")
            pending[key] = {"confirmed_hundredths": cell["confirmed_hundredths"], "batch_event_id": identity}
        effective.update(pending)
        confirmation_positions.update({key: position for key in pending})
        batches[identity] = event
    return effective
