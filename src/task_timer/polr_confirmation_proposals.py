"""Transient frozen-export proposals and explicit selection; no I/O or event creation."""

from __future__ import annotations

from datetime import date
from typing import Any

from .export_snapshots import collect_export_snapshots, validate_uuid
from .polr_confirmations import collect_polr_confirmations, requires_stale_export_acknowledgement


def build_export_confirmation_proposal(events: list[dict], export_id: str) -> dict[str, Any]:
    """Derive frozen cells and latest priors from validated physical journal evidence."""
    validate_uuid(export_id)
    exports = collect_export_snapshots(events)
    confirmations = collect_polr_confirmations(events)
    if export_id not in exports:
        raise ValueError("Unknown timesheet export identity")
    positions = {}
    ordered = sorted(enumerate(events), key=lambda pair: pair[1].get("_read_sequence", pair[0]))
    for position, (_, event) in enumerate(ordered):
        if isinstance(event.get("event_id"), str):
            positions.setdefault(event["event_id"], position)
    cells = []
    for task in sorted(exports[export_id]["payload"]["tasks"], key=lambda row: row["task_id"]):
        for daily in sorted(task["daily"], key=lambda row: row["work_date"]):
            prior = confirmations.get((task["task_id"], daily["work_date"]))
            amount = prior["confirmed_hundredths"] if prior is not None else None
            identity = prior["batch_event_id"] if prior is not None else None
            cells.append({
                "task_id": task["task_id"], "work_date": daily["work_date"],
                "task_name": task["name"], "proposed_hundredths": daily["decimal_hundredths"],
                "prior_confirmed_hundredths": amount, "expected_prior_confirmation_id": identity,
                "requires_stale_acknowledgement": requires_stale_export_acknowledgement(
                    positions[export_id], positions.get(identity), amount, daily["decimal_hundredths"],
                ),
            })
    return {"source_export_id": export_id, "cells": cells}


def _key(task_id, work_date):
    validate_uuid(task_id)
    if type(work_date) is not str:
        raise ValueError("Proposal work date must be canonical ISO text")
    try:
        if date.fromisoformat(work_date).isoformat() != work_date:
            raise ValueError
    except ValueError:
        raise ValueError("Proposal work date must be a canonical ISO calendar date") from None
    return task_id, work_date


def validate_export_confirmation_proposal(proposal) -> None:
    """Validate reviewed value shape; current evidence relationships follow separately."""
    if type(proposal) is not dict or set(proposal) != {"source_export_id", "cells"}:
        raise ValueError("Invalid export confirmation proposal fields")
    validate_uuid(proposal["source_export_id"])
    if type(proposal["cells"]) is not list:
        raise ValueError("Proposal cells must be a list")
    keys = []
    for row in proposal["cells"]:
        if type(row) is not dict or set(row) != {
            "task_id", "work_date", "task_name", "proposed_hundredths", "prior_confirmed_hundredths",
            "expected_prior_confirmation_id", "requires_stale_acknowledgement",
        }:
            raise ValueError("Invalid export confirmation proposal row fields")
        keys.append(_key(row["task_id"], row["work_date"]))
        if type(row["task_name"]) is not str:
            raise ValueError("Proposal task name must be text")
        try:
            row["task_name"].encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Proposal task name must be valid UTF-8") from None
        for field in ("proposed_hundredths", "prior_confirmed_hundredths"):
            value = row[field]
            if field == "prior_confirmed_hundredths" and value is None:
                continue
            if type(value) is not int or value < 0:
                raise ValueError("Proposal amounts must be nonnegative integers")
        identity = row["expected_prior_confirmation_id"]
        if identity is not None:
            validate_uuid(identity)
        if (row["prior_confirmed_hundredths"] is None) != (identity is None):
            raise ValueError("Proposal prior amount and identity must both be known or Unknown")
        if type(row["requires_stale_acknowledgement"]) is not bool:
            raise ValueError("Proposal stale flag must be boolean")
    if keys != sorted(set(keys)):
        raise ValueError("Proposal rows must be unique and in canonical task/date order")


def _selected_keys(values, known):
    if type(values) not in (list, tuple):
        raise ValueError("Cell keys must be a list or tuple of two-tuples")
    keys = set()
    for value in values:
        if type(value) is not tuple or len(value) != 2:
            raise ValueError("Each cell key must be a task/date two-tuple")
        key = _key(*value)
        if key in keys or key not in known:
            raise ValueError("Duplicate or unknown proposal cell key")
        keys.add(key)
    return keys


def select_export_confirmation_cells(
    proposal, current, *, selected_cells=None, acknowledged_cells=(),
) -> list[dict[str, Any]]:
    """Validate frozen coverage and selected reviewed priors, returning existing-format cells."""
    validate_export_confirmation_proposal(proposal)
    validate_export_confirmation_proposal(current)
    if proposal["source_export_id"] != current["source_export_id"]:
        raise ValueError("Proposal source export does not match current evidence")
    frozen_fields = ("task_id", "work_date", "task_name", "proposed_hundredths")
    if [[row[field] for field in frozen_fields] for row in proposal["cells"]] != [
        [row[field] for field in frozen_fields] for row in current["cells"]
    ]:
        raise ValueError("Proposal coverage or frozen cells differ from registered export")
    rows = {(row["task_id"], row["work_date"]): row for row in proposal["cells"]}
    selected = ({key for key, row in rows.items() if row["proposed_hundredths"] > 0}
                if selected_cells is None else _selected_keys(selected_cells, rows))
    if not selected:
        raise ValueError("Select at least one export confirmation cell")
    acknowledged = _selected_keys(acknowledged_cells, rows)
    required = {key for key in selected if rows[key]["requires_stale_acknowledgement"]}
    if acknowledged != required:
        raise ValueError("Acknowledgements must exactly identify selected stale conflicts")
    reviewed_fields = ("prior_confirmed_hundredths", "expected_prior_confirmation_id",
                       "requires_stale_acknowledgement")
    cells = []
    for fresh in current["cells"]:
        key = fresh["task_id"], fresh["work_date"]
        if key not in selected:
            continue
        row = rows[key]
        if any(row[field] != fresh[field] for field in reviewed_fields):
            raise ValueError("Selected proposal prior or stale classification changed; renewed review required")
        cells.append({
            "task_id": row["task_id"], "work_date": row["work_date"],
            "confirmed_hundredths": row["proposed_hundredths"],
            "source_export_id": proposal["source_export_id"],
            "expected_prior_confirmation_id": row["expected_prior_confirmation_id"],
            "stale_export_acknowledged": key in acknowledged,
        })
    return cells
