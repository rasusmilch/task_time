"""Frozen export evidence validation and journal-derived projection, not file export."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
import re
from typing import Any
from uuid import UUID

from .exporter import build_decimal_timesheet_text, seconds_to_decimal_hundredths
from .models import SCHEMA_VERSION

EXPORT_EVENT_TYPE = "timesheet_export_snapshot_created"


def same_export_event(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """JSON content equality, preserving int/float distinctions and list order."""
    return json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(second, sort_keys=True, allow_nan=False)


def validate_uuid(value: Any) -> None:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise ValueError("Export evidence requires canonical UUID strings") from None


def _fields(value: Any, names: str) -> None:
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError(f"Invalid export evidence fields: expected {names}")


def _text(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Export evidence requires nonempty text")
    value.encode("utf-8")


def _date(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("Export work dates must be canonical ISO calendar dates")
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
    except ValueError:
        raise ValueError("Export work dates must be canonical ISO calendar dates") from None
    return parsed


def _utc(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", value):
        raise ValueError("Export timestamps must be UTC ISO timestamps with Z suffix")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid export timestamp") from None


def _ids(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError("Export UUID collections must be arrays")
    for key in value:
        validate_uuid(key)
    if value != sorted(set(value)):
        raise ValueError("Export UUID arrays must be unique and sorted")


def work_dates(start: date, end: date):
    """Inclusive bounded calendar iteration, including date.max if preserved."""
    for ordinal in range(start.toordinal(), end.toordinal() + 1):
        yield date.fromordinal(ordinal)


def report_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct layout inputs from frozen cells only; never calculate Actual."""
    tasks = {
        row["task_id"]: {**row, "daily_seconds": {
            date.fromisoformat(cell["work_date"]): cell["actual_seconds"] for cell in row["daily"]
        }} for row in payload["tasks"]
    }
    return {
        "start_date": date.fromisoformat(payload["start_date"]),
        "end_date": date.fromisoformat(payload["end_date"]),
        "cutoff_utc": datetime.fromisoformat(payload["cutoff_utc"].replace("Z", "+00:00")),
        "local_timezone": payload["report_timezone"], "scope": payload["scope"],
        "include_deleted": payload["selection"]["include_deleted"], "tasks": tasks,
        "projects": {row["project_id"]: row for row in payload["projects"]},
        "unassigned": {"task_ids": [key for key, row in tasks.items() if row["project_id"] is None]},
        "application": {},
    }


def validate_export_snapshot(event: Any, *, known_tasks: set[str] | None = None,
                             known_projects: set[str] | None = None,
                             verify_rendering: bool = False) -> None:
    """Validate frozen integrity; replay deliberately never calls today's renderer."""
    _fields(event, "schema_version event_id timestamp_utc local_timezone task_id event_type payload")
    if type(event["schema_version"]) is not int or event["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported export event schema")
    if event["event_type"] != EXPORT_EVENT_TYPE or event["task_id"] != "__app__":
        raise ValueError("Export snapshots require the application event owner/type")
    validate_uuid(event["event_id"])
    _utc(event["timestamp_utc"])
    _text(event["local_timezone"])
    payload = event["payload"]
    _fields(payload, "start_date end_date cutoff_utc report_timezone week_start scope selection tasks projects report_text report_sha256 preferred_destination")
    start, end = _date(payload["start_date"]), _date(payload["end_date"])
    if end < start:
        raise ValueError("Reversed export work-date range")
    _utc(payload["cutoff_utc"])
    _text(payload["report_timezone"])
    if event["local_timezone"] != payload["report_timezone"]:
        raise ValueError("Export timezone metadata must agree")
    if type(payload["week_start"]) is not int or payload["week_start"] != 6:
        raise ValueError("Only Sunday-start export snapshots are currently supported")
    selection = payload["selection"]
    _fields(selection, "all_tasks task_ids project_ids include_unassigned include_deleted")
    if any(type(selection[name]) is not bool for name in ("all_tasks", "include_unassigned", "include_deleted")):
        raise ValueError("Export selection flags must be booleans")
    for name, known in (("task_ids", known_tasks), ("project_ids", known_projects)):
        _ids(selection[name])
        if known is not None and not set(selection[name]) <= known:
            raise ValueError("Unknown original export selection reference")
    if payload["scope"] != ("complete" if selection["all_tasks"] else "selected"):
        raise ValueError("Export scope must agree with its original selection")
    if not isinstance(payload["tasks"], list) or not isinstance(payload["projects"], list):
        raise ValueError("Export tasks/projects must be arrays")
    tasks, projects = {}, {}
    for row in payload["tasks"]:
        _fields(row, "task_id name project_id is_deleted daily")
        key = row["task_id"]
        validate_uuid(key)
        if key in tasks or (known_tasks is not None and key not in known_tasks):
            raise ValueError("Duplicate or unknown frozen task identity")
        _text(row["name"])
        if row["project_id"] is not None:
            validate_uuid(row["project_id"])
        if type(row["is_deleted"]) is not bool or (row["is_deleted"] and not selection["include_deleted"]):
            raise ValueError("Invalid frozen task deletion eligibility")
        if not isinstance(row["daily"], list) or len(row["daily"]) != end.toordinal() - start.toordinal() + 1:
            raise ValueError("Export daily cells must cover every included date exactly once")
        for cell, day in zip(row["daily"], work_dates(start, end)):
            _fields(cell, "work_date actual_seconds decimal_hundredths")
            if _date(cell["work_date"]) != day:
                raise ValueError("Export daily cells must be ordered, unique and within the date range")
            hundredths = cell["decimal_hundredths"]
            if type(hundredths) is not int or hundredths < 0:
                raise ValueError("Export decimal hundredths must be nonnegative integers")
            if seconds_to_decimal_hundredths(cell["actual_seconds"]) != hundredths:
                raise ValueError("Export rounded hundredths do not match actual seconds")
        tasks[key] = row
    for row in payload["projects"]:
        _fields(row, "project_id name scope task_ids")
        key = row["project_id"]
        validate_uuid(key)
        if key in projects or (known_projects is not None and key not in known_projects):
            raise ValueError("Duplicate or unknown frozen project identity")
        _text(row["name"])
        if row["scope"] not in ("full_project", "selected_tasks"):
            raise ValueError("Invalid frozen project scope")
        if (selection["all_tasks"] or key in selection["project_ids"]) and row["scope"] != "full_project":
            raise ValueError("Explicit project selection requires full-project scope")
        _ids(row["task_ids"])
        members = {task_id for task_id, task in tasks.items() if task["project_id"] == key}
        if set(row["task_ids"]) != members:
            raise ValueError("Frozen project membership references do not agree")
        projects[key] = row
    if set(tasks) & set(projects):
        raise ValueError("Project identities cannot be task identities")
    if not set(selection["project_ids"]) <= projects.keys():
        raise ValueError("Selected empty projects must remain in export evidence")
    for key, task in tasks.items():
        project_id = task["project_id"]
        if project_id is not None and project_id not in projects:
            raise ValueError("Missing frozen project reference")
        if not (selection["all_tasks"] or key in selection["task_ids"] or project_id in selection["project_ids"]
                or (selection["include_unassigned"] and project_id is None)):
            raise ValueError("Frozen task falls outside the original selection")
    for key in projects:
        if not (selection["all_tasks"] or key in selection["project_ids"] or projects[key]["task_ids"]):
            raise ValueError("Unrequested empty project in selected export")
    destination = payload["preferred_destination"]
    if destination is not None and (not isinstance(destination, str) or not destination or "\x00" in destination):
        raise ValueError("Preferred destination must be a nonempty path string or null")
    _text(payload["report_text"])
    if not payload["report_text"].endswith("\n"):
        raise ValueError("Export report text must retain its final newline")
    digest = payload["report_sha256"]
    if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
        raise ValueError("Invalid export SHA-256")
    if sha256(payload["report_text"].encode("utf-8")).hexdigest() != digest:
        raise ValueError("Export report text/digest mismatch")
    try:
        json.dumps(event, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Export evidence must be strict JSON serializable") from exc
    if verify_rendering and build_decimal_timesheet_text(report_from_payload(payload)) != payload["report_text"]:
        raise ValueError("Export structured cells and report text do not agree")


def collect_export_snapshots(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Validate/index evidence in physical journal order, independent of audit time."""
    ordered = sorted(enumerate(events), key=lambda pair: pair[1].get("_read_sequence", pair[0]))
    known_tasks = {event["task_id"] for event in events if event.get("event_type") == "task_created"}
    known_projects = {event["payload"].get("project_id") for event in events
                      if event.get("event_type") == "project_created"}
    exports, other_ids = {}, set()
    for _, loaded in ordered:
        event = {key: value for key, value in loaded.items() if key != "_read_sequence"}
        key = event.get("event_id")
        if event.get("event_type") != EXPORT_EVENT_TYPE:
            if isinstance(key, str):
                other_ids.add(key)
                if key in exports:
                    raise ValueError("Export identity collides with another event type")
            continue
        validate_export_snapshot(event, known_tasks=known_tasks, known_projects=known_projects)
        if key in other_ids or (key in exports and not same_export_event(exports[key], event)):
            raise ValueError("Conflicting duplicate export identity")
        exports.setdefault(key, deepcopy(event))
    return exports
