"""Transient daily reconciliation from calculated Actual and validated confirmations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .export_snapshots import work_dates
from .exporter import seconds_to_decimal_hundredths


def build_polr_reconciliation(report: dict[str, Any], confirmations: dict) -> dict[str, Any]:
    """Project included task/day cells only; neither input is mutated or retained."""
    cells = {}
    for task_id, task in report["tasks"].items():
        for day in work_dates(report["start_date"], report["end_date"]):
            key = task_id, day.isoformat()
            actual = seconds_to_decimal_hundredths(task["daily_seconds"].get(day, 0))
            prior = confirmations.get(key)
            confirmed = prior["confirmed_hundredths"] if prior is not None else None
            cells[key] = {
                "actual_hundredths": actual,
                "confirmed_hundredths": confirmed,
                "delta_hundredths": actual - confirmed if confirmed is not None else None,
                "enter_hundredths": actual,
                "batch_event_id": prior["batch_event_id"] if prior is not None else None,
            }
    return {"actual": deepcopy(report), "cells": cells}
