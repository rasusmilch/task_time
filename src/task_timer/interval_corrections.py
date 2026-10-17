"""Structural validation for prepared genuine-interval corrections, not replay."""

from datetime import datetime, timezone
import re
from uuid import UUID

from .models import SCHEMA_VERSION


def canonical_uuid(value):
    if not isinstance(value, str):
        raise ValueError("Correction identities must be canonical UUID strings")
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise ValueError("Correction identities must be canonical UUID strings") from None


def aware_utc(value):
    try:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Correction endpoints must be representable aware datetimes") from exc


def utc_text(value):
    return aware_utc(value).isoformat().replace("+00:00", "Z")


def parse_endpoint(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{6})?Z", value,
    ):
        raise ValueError("Correction endpoints must be canonical UTC Z strings")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if utc_text(parsed) != value:
            raise ValueError
    except ValueError:
        raise ValueError("Correction endpoints must be canonical UTC Z strings") from None
    return parsed


def prior_label(first, last):
    return f"{utc_text(first)} to {utc_text(last)}"


def validate_prepared_interval_correction(event):
    if not isinstance(event, dict) or set(event) != {
        "schema_version", "event_id", "timestamp_utc", "local_timezone", "task_id", "event_type", "payload",
    }:
        raise ValueError("Invalid correction envelope fields")
    if type(event["schema_version"]) is not int or event["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported correction schema version")
    canonical_uuid(event["event_id"])
    canonical_uuid(event["task_id"])
    if event["event_type"] != "interval_edited":
        raise ValueError("Correction event type must be interval_edited")
    audit = event["timestamp_utc"]
    if not isinstance(audit, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", audit):
        raise ValueError("Correction audit timestamp must use canonical UTC seconds")
    parse_endpoint(audit)
    zone = event["local_timezone"]
    if type(zone) is not str or not zone or zone != zone.strip():
        raise ValueError("Correction timezone metadata must be nonempty text without surrounding whitespace")
    try:
        zone.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Correction timezone metadata must be valid UTF-8") from None
    if any(ord(char) < 0x20 or 0x7f <= ord(char) <= 0x9f for char in zone):
        raise ValueError("Correction timezone metadata must not contain control characters")
    payload = event["payload"]
    if not isinstance(payload, dict) or set(payload) != {
        "interval_id", "new_interval_id", "start_utc", "stop_utc", "entry_mode", "prior_interval_label", "reason",
    }:
        raise ValueError("Invalid correction payload fields")
    canonical_uuid(payload["interval_id"])
    canonical_uuid(payload["new_interval_id"])
    if payload["entry_mode"] != "interval":
        raise ValueError("Correction requires genuine interval mode")
    if parse_endpoint(payload["stop_utc"]) <= parse_endpoint(payload["start_utc"]):
        raise ValueError("Correction stop must be after start in UTC")
    if not isinstance(payload["reason"], str) or payload["reason"] != payload["reason"].strip():
        raise ValueError("Correction comment must be trimmed text, optionally empty")
    label = payload["prior_interval_label"]
    if not isinstance(label, str) or len(parts := label.split(" to ")) != 2:
        raise ValueError("Invalid original endpoint context")
    if parse_endpoint(parts[1]) <= parse_endpoint(parts[0]):
        raise ValueError("Invalid original endpoint context")
