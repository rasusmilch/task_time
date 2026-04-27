from datetime import date

from task_timer.reminders import should_show_month_end_banner
from task_timer.settings import UISettings


def test_reminder_due_only_on_last_business_day_when_enabled() -> None:
    settings = UISettings(month_end_reminder_enabled=True)
    assert should_show_month_end_banner(settings, date(2026, 4, 30)) is True
    assert should_show_month_end_banner(settings, date(2026, 4, 29)) is False


def test_dismissed_date_suppresses_for_day_only() -> None:
    settings = UISettings(
        month_end_reminder_enabled=True,
        month_end_reminder_last_dismissed_local_date="2026-05-29",
    )
    assert should_show_month_end_banner(settings, date(2026, 5, 29)) is False
    assert should_show_month_end_banner(settings, date(2026, 6, 30)) is True
