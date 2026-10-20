"""Exact full-week POL-R allocation; no I/O, Actual mutation or float units."""
from datetime import timedelta

from .records import integer
from .timekeeping import parse_date

MAX_AMOUNT = 2**63 - 1
Q = 900_000_000


def amount(value, label="Amount"):
    return integer(value, label, 0, MAX_AMOUNT)


def civil(value):
    day = parse_date(value)
    if day.isoformat() != value:
        raise ValueError("A canonical civil date is required")
    return day


def complete_week(first):
    day = civil(first)
    try:
        dates = tuple((day + timedelta(days=i)).isoformat() for i in range(7))
        day + timedelta(days=7)  # Required exclusive calendar boundary.
    except OverflowError as exc:
        raise ValueError("Complete week is unrepresentable") from exc
    return dates


def actual_hundredths(microseconds):
    return amount((amount(microseconds) + 18_000_000) // 36_000_000)


def decimal_text(hundredths):
    value = amount(hundredths)
    return f"{value // 100}.{value % 100:02d}"


def quarter_text(quarters):
    return decimal_text(amount(amount(quarters) * 25))


def allocate_week(first: str, daily: tuple[tuple[str, int], ...]) -> tuple[tuple[str, int], ...]:
    """Seven unique canonical dates; result order is always ascending civil date."""
    dates = complete_week(first)
    if type(daily) is not tuple or len(daily) != 7:
        raise ValueError("Require exactly seven date/Actual pairs")
    values = {}
    for pair in daily:
        if type(pair) is not tuple or len(pair) != 2:
            raise ValueError("Require immutable date/Actual pairs")
        day, value = pair
        civil(day)
        if day in values:
            raise ValueError("Duplicate date")
        values[day] = amount(value, "Exact Actual")
    if set(values) != set(dates):
        raise ValueError("Missing or out-of-week date")
    total = amount(sum(values.values()), "Weekly Actual")
    target = (total + Q - 1) // Q
    amount(target * Q, "Converted weekly target")
    result = {d: values[d] // Q for d in dates}
    eligible = sorted((d for d in dates if values[d] % Q),
                      key=lambda d: (-(values[d] % Q), d))
    for day in eligible[:target - sum(result.values())]:
        result[day] += 1
    return tuple((d, result[d]) for d in dates)
