from datetime import datetime, timezone

import pytest

from chronicle.accounting import calculate
from chronicle.records import ClockWarning
from chronicle.timekeeping import load_zone, to_us
from conftest import archive, NOW, uid


def stamp(text):
    return to_us(datetime.fromisoformat(text))


@pytest.mark.parametrize("start,stop,expected", [
    ("2026-03-08T01:30:00-06:00", "2026-03-08T03:30:00-05:00", 3_600_000_000),
    ("2026-11-01T01:30:00-05:00", "2026-11-01T01:30:00-06:00", 3_600_000_000),
    ("2026-10-19T23:59:59.999999-05:00", "2026-10-20T00:00:00.000001-05:00", 2),
])
def test_dst_and_midnight_exact(start, stop, expected):
    task_id = uid()
    report = calculate([{"task_id": task_id}], [{"task_id": task_id, "kind": "timed", "start_utc_us": stamp(start), "stop_utc_us": stamp(stop)}], None,
                       stamp(stop), load_zone("America/Chicago"))
    assert report["application"]["week_us"] == expected
    if expected == 2:
        assert report["tasks"][task_id]["daily_us"] == {"2026-10-19": 1, "2026-10-20": 1}


def test_own_tasks_deleted_work_and_no_project_double_count(service, task, store):
    from test_services import start
    entry = start(service, task)
    service.stop_timer(entry, expected_version=1, request_id=uid(), action_utc_us=NOW + 1234567)
    second = uid()
    service.create_task(second, "Child label is independent", request_id=uid(), action_utc_us=NOW)
    archive(service, 'task', task, now=0)
    state = service.read_current_state(cutoff_utc_us=NOW + 5_000_000)
    assert state["report"]["tasks"][task]["today_us"] == 1234567
    assert state["report"]["tasks"][second]["today_us"] == 0
    assert state["report"]["application"]["today_us"] == 1234567


def test_sleep_forward_jump_capped_running_and_invalid_observation(service, task, store):
    from test_services import start
    entry = start(service, task)
    before = store.connection.total_changes
    view = service.read_current_state(cutoff_utc_us=NOW + 8 * 3_600_000_000)
    assert view["report"]["application"]["today_us"] == 8 * 3_600_000_000
    invalid = service.read_current_state(cutoff_utc_us=NOW - 1)
    assert invalid["report"] is None and "precedes" in invalid["calculation_error"]
    assert invalid["active"]["entry_id"] == entry
    assert store.connection.total_changes == before


def test_local_week_and_utc_date_difference():
    task = uid()
    cutoff = stamp("2026-10-19T00:30:00+00:00")
    report = calculate([{"task_id": task}], [], None, cutoff, load_zone("America/Chicago"))
    assert report["today"] == report["week_start"] == "2026-10-18"
    assert report["week_end"] == "2026-10-24"


def test_non_hour_dst_and_closed_cutoff():
    task = uid()
    first, last = stamp("2026-10-04T01:45:00+10:30"), stamp("2026-10-04T03:00:00+11:00")
    report = calculate([{"task_id": task}], [{"task_id": task, "kind": "timed", "start_utc_us": first, "stop_utc_us": last}], None,
                       last - 900_000_000, load_zone("Australia/Lord_Howe"))
    assert report["application"]["today_us"] == 1_800_000_000


def test_detached_reads_cannot_mutate_work_or_metadata(service, task, store):
    before = store.connection.total_changes
    view = service.read_current_state(cutoff_utc_us=NOW)
    view["tasks"][0]["name"] = "not persisted"
    view["report"]["tasks"][task]["today_us"] = 10**12
    again = service.read_current_state(cutoff_utc_us=NOW)
    assert again["tasks"][0]["name"] == "Example"
    assert again["report"]["tasks"][task]["today_us"] == 0
    assert store.connection.total_changes == before
