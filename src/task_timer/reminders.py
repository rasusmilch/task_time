"""Month-end reminder helper logic."""

from __future__ import annotations

from datetime import date

from .settings import UISettings
from .time_utils import is_last_business_day


def should_show_month_end_banner(settings: UISettings, local_today: date) -> bool:
    """Return True when month-end banner should be visible for local_today."""
    if not settings.month_end_reminder_enabled:
        return False
    if not is_last_business_day(local_today):
        return False
    return settings.month_end_reminder_last_dismissed_local_date != local_today.isoformat()
