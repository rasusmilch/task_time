"""Detached use-case values. No Tk or database dependencies."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from uuid import UUID


ADMINISTRATIVE_OPERATIONS = frozenset({
    'create_project', 'rename_project', 'create_task', 'rename_task', 'assign_task_to_project', 'move_task_branch',
    # Classified now, deliberately not executable until separately approved packages.
    'archive_project', 'unarchive_project', 'archive_task', 'unarchive_task',
})


def receipt_class(operation):
    return 'administrative' if operation in ADMINISTRATIVE_OPERATIONS else 'protected'


class StaleState(ValueError):
    """Reviewed identity/version is no longer current."""


class ClockWarning(ValueError):
    """The current observation cannot describe the active timer."""


def uuid_text(value: str) -> str:
    if type(value) is not str:
        raise ValueError("Identity must be a canonical UUID string")
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValueError("Identity must be a canonical UUID string") from exc
    return value


def integer(value: int, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def canonical(value: object) -> bytes:
    def check(item):
        if item is None or type(item) in (str, int, bool):
            return
        if type(item) is list:
            for member in item:
                check(member)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for member in item.values():
                check(member)
            return
        raise ValueError("Request content must contain only strict JSON values; no floats")
    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class Request:
    request_id: str
    dataset_id: str
    operation: str
    action_utc_us: int
    arguments: bytes

    @classmethod
    def make(cls, request_id: str, dataset_id: str, operation: str,
             action_utc_us: int, **arguments) -> Request:
        from .timekeeping import instant
        uuid_text(request_id)
        uuid_text(dataset_id)
        if type(operation) is not str:
            raise ValueError("Operation must be text")
        instant(action_utc_us)
        return cls(request_id, dataset_id, operation, action_utc_us, canonical(arguments))

    def content(self) -> bytes:
        # Revalidate even a directly constructed Request, before database acquisition.
        from .timekeeping import instant
        uuid_text(self.request_id)
        uuid_text(self.dataset_id)
        instant(self.action_utc_us)
        if type(self.arguments) is not bytes or type(self.operation) is not str:
            raise ValueError("Invalid frozen request")
        args = json.loads(self.arguments)
        if type(args) is not dict or canonical(args) != self.arguments:
            raise ValueError("Arguments must be a canonical object")
        return canonical({"format": 1, "dataset_id": self.dataset_id,
                          "operation": self.operation, "action_utc_us": self.action_utc_us,
                          "arguments": args})

    def args(self) -> dict:
        return json.loads(self.arguments)


@dataclass(frozen=True)
class Outcome:
    status: str
    result: dict = field(default_factory=dict)
    error: Exception | None = None

    def detached(self) -> Outcome:
        return Outcome(self.status, deepcopy(self.result), self.error)
