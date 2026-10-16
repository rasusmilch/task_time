"""Detached mixed daily history; isolated services and explicit pure model cases."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from math import fsum
from zoneinfo import ZoneInfo

import pytest

from task_timer import app as app_module
from task_timer.accounting import UnsupportedLegacyDurationError
from task_timer.app import TaskTimerService
from task_timer.models import DatedDurationRecord, IntervalRecord, TaskState
from task_timer.storage import EventStorage
from task_timer.work_history import build_task_work_history
from test_mixed_accounting import setup, dated, local, files, MON, TUE, SAT, SUN, CUTOFF


UTC = timezone.utc
FIELDS = {"task_id", "entry_kind", "entry_id", "work_date", "segment_start_utc", "segment_stop_utc",
          "duration_seconds", "original_start_utc", "original_stop_utc", "is_running",
          "continues_before", "continues_after", "source", "reason"}


def capture(s):
    return (deepcopy(s.state), deepcopy(s.events), s.snapshot_dict(), files(s),
            s.get_effective_polr_confirmations(), s.list_timesheet_export_snapshots(), s.list_time_submissions())


def history(s, task, monkeypatch, **options):
    options.setdefault("cutoff_utc", CUTOFF)
    before, inputs = capture(s), deepcopy(options)
    def forbidden(*args, **kwargs):
        pytest.fail("History attempted a write, journal/accounting read, clock/identity capture or state installation")
    try:
        with monkeypatch.context() as m:
            for name in ("append_event", "save_snapshot", "synchronize_journal", "iter_all_events",
                         "load_snapshot", "save_manifest", "rotate_if_needed", "_atomic_write_json"):
                m.setattr(s.storage, name, forbidden)
            for name in ("_append", "_save_snapshot", "_rebuild_state", "_install_export_journal",
                         "calculate_date_window", "_all_intervals", "_effective_intervals", "create_backup_now"):
                m.setattr(s, name, forbidden)
            m.setattr(s.backups, "create_backup", forbidden)
            m.setattr(app_module, "utc_now", forbidden)
            m.setattr(app_module, "uuid4", forbidden)
            result = s.get_task_work_history(task, **options)
        for row in result:
            assert set(row) == FIELDS
            assert type(row["work_date"]) is date
            for name in ("segment_start_utc", "segment_stop_utc", "original_start_utc", "original_stop_utc"):
                assert row[name] is None or row[name].tzinfo is UTC
        return result
    finally:
        assert capture(s) == before and options == inputs


def interval(s, task, first, last, reason="Genuine work"):
    s.add_manual_interval(task, first, last, reason)
    return next(reversed(s.state.tasks[task].intervals))


def model():
    return TaskState("task", "Task", "", False, False, CUTOFF, CUTOFF)


def test_empty_identity_and_known_deleted_task_reading(setup, monkeypatch):
    s, a, b, project, _, _ = setup
    assert history(s, a, monkeypatch) == []
    identity = dated(s, a, MON, 3600)
    assert history(s, b, monkeypatch) == []
    for invalid in (project, "missing", None, True, []):
        with pytest.raises(ValueError): history(s, invalid, monkeypatch)
    s.delete_task_only(a)
    rows = history(s, a, monkeypatch)
    assert [(r["task_id"], r["entry_id"], r["duration_seconds"]) for r in rows] == [(a, identity, 3600)]


@pytest.mark.parametrize("options", [
    {"start_date": MON}, {"end_date": TUE}, {"start_date": TUE, "end_date": MON},
    {"start_date": str(MON), "end_date": TUE}, {"start_date": MON, "end_date": datetime(2026, 10, 13)},
    {"start_date": MON, "end_date": date.max}, {"start_date": True, "end_date": TUE},
    {"newest_first": 1}, {"newest_first": None}, {"newest_first": "false"},
    {"cutoff_utc": None}, {"cutoff_utc": datetime(2026, 10, 20)}, {"cutoff_utc": "2026-10-20Z"},
])
def test_invalid_requests_are_pure(setup, monkeypatch, options):
    s, a, _, _, _, _ = setup
    with pytest.raises(ValueError): history(s, a, monkeypatch, **options)


def test_cutoff_is_required(setup):
    s, a, _, _, _, _ = setup
    before = capture(s)
    with pytest.raises(TypeError): s.get_task_work_history(a)
    assert capture(s) == before


def test_linked_overnight_rows_filters_cutoff_and_complete_endpoints(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    first, last = local(s, MON, 20), local(s, TUE, 8)
    identity = interval(s, a, first, last)
    rows = history(s, a, monkeypatch, newest_first=False)
    assert [r["work_date"] for r in rows] == [MON, TUE]
    assert [r["duration_seconds"] for r in rows] == [14400, 28800]
    assert [(r["continues_before"], r["continues_after"]) for r in rows] == [(False, True), (True, False)]
    assert rows[0]["segment_stop_utc"] == rows[1]["segment_start_utc"] == local(s, TUE).astimezone(UTC)
    for row in rows:
        assert row["entry_kind"] == "interval" and row["entry_id"] == identity
        assert row["original_start_utc"] == first.astimezone(UTC)
        assert row["original_stop_utc"] == last.astimezone(UTC)
        assert row["source"] == "manual" and row["reason"] == "Genuine work" and not row["is_running"]
    for day, row in zip((MON, TUE), rows):
        assert history(s, a, monkeypatch, start_date=day, end_date=day) == [row]
    cutoff = local(s, TUE, 2).astimezone(timezone(timedelta(hours=5, minutes=30)))
    limited = history(s, a, monkeypatch, cutoff_utc=cutoff, newest_first=False)
    assert [r["duration_seconds"] for r in limited] == [14400, 7200]
    assert limited[-1]["original_stop_utc"] == last.astimezone(UTC)
    assert limited[-1]["segment_stop_utc"] == cutoff.astimezone(UTC)
    assert not limited[-1]["continues_after"]
    assert history(s, a, monkeypatch, cutoff_utc=first) == []


@pytest.mark.parametrize("days", [1, 3])
def test_midnight_end_has_no_zero_following_day(setup, monkeypatch, days):
    s, a, _, _, _, _ = setup
    first = local(s, MON)
    interval(s, a, first, first + timedelta(days=days))
    rows = history(s, a, monkeypatch, newest_first=False)
    assert [r["work_date"] for r in rows] == [MON + timedelta(days=i) for i in range(days)]
    assert [r["duration_seconds"] for r in rows] == [86400] * days
    assert not rows[0]["continues_before"] and not rows[-1]["continues_after"]


@pytest.mark.parametrize("zone,day,hours", [
    (ZoneInfo("America/Chicago"), date(2026, 3, 8), 23),
    (ZoneInfo("America/Chicago"), date(2026, 11, 1), 25),
    (timezone(timedelta(hours=5, minutes=30)), MON, 24),
    (timezone(timedelta(hours=-5)), MON, 24),
])
def test_daily_segments_use_utc_elapsed_across_timezone_boundaries(setup, monkeypatch, zone, day, hours):
    s, a, _, _, _, _ = setup
    s.local_tz = zone
    first = datetime.combine(day, datetime.min.time(), zone)
    interval(s, a, first, first + timedelta(days=2))
    rows = history(s, a, monkeypatch, newest_first=False)
    assert [r["duration_seconds"] for r in rows] == [hours * 3600, 86400]
    report = s.calculate_date_window(day, day + timedelta(days=1), cutoff_utc=CUTOFF, task_ids=(a,))
    assert {r["work_date"]: r["duration_seconds"] for r in rows} == report["tasks"][a]["daily_seconds"]


def test_running_projection_boundaries_never_record_a_stop(setup, monkeypatch):
    s, a, _, _, _, clock = setup
    clock[0] = local(s, MON, 20).astimezone(UTC)
    s.start_task(a)
    cutoff = local(s, TUE, 8).astimezone(UTC)
    rows = history(s, a, monkeypatch, cutoff_utc=cutoff, newest_first=False)
    assert [r["duration_seconds"] for r in rows] == [14400, 28800]
    assert all(r["entry_id"] == "__open__" and r["is_running"] and r["source"] == "open"
               and r["reason"] == "" and r["original_stop_utc"] is None for r in rows)
    assert all(r["original_start_utc"] == clock[0] for r in rows)
    assert rows[-1]["segment_stop_utc"] == cutoff
    for earlier in (clock[0], clock[0] - timedelta(seconds=1)):
        assert history(s, a, monkeypatch, cutoff_utc=earlier) == []
    assert s.state.tasks[a].is_running and s.state.tasks[a].intervals == {}


def test_date_only_whole_saturday_fractional_precision_and_cutoff_independence(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    identity = dated(s, a, SAT, 50400.125)
    rows = history(s, a, monkeypatch, cutoff_utc=local(s, MON), start_date=SAT, end_date=SAT)
    assert rows == [{"task_id": a, "entry_kind": "dated_duration", "entry_id": identity,
                     "work_date": SAT, "segment_start_utc": None, "segment_stop_utc": None,
                     "duration_seconds": 50400.125, "original_start_utc": None, "original_stop_utc": None,
                     "is_running": False, "continues_before": False, "continues_after": False,
                     "source": "dated_duration", "reason": "Declared work"}]
    assert history(s, a, monkeypatch, start_date=SUN, end_date=SUN) == []
    task = model()
    start = CUTOFF - timedelta(seconds=1, microseconds=123456)
    task.intervals["fraction"] = IntervalRecord("fraction", task.task_id, start, CUTOFF, "timer")
    assert build_task_work_history(task, UTC, cutoff_utc=CUTOFF)[0]["duration_seconds"] == 1.123456


def test_order_is_date_direction_then_chronological_intervals_then_dated_ids():
    task = model()
    first = datetime(2026, 10, 12, 8, tzinfo=UTC)
    for identity, hour, length in (("z", 8, 2), ("b", 8, 1), ("a", 8, 1), ("early", 7, 1)):
        task.intervals[identity] = IntervalRecord(identity, task.task_id, first.replace(hour=hour),
                                                  first.replace(hour=hour) + timedelta(hours=length), "timer")
    for identity, day, audit in (("z-date", MON, CUTOFF), ("a-date", MON, first), ("next", TUE, first)):
        task.dated_durations[identity] = DatedDurationRecord(identity, task.task_id, day, 60, "Reason",
                                                           audit, audit, identity)
    before = deepcopy(task)
    ascending = build_task_work_history(task, UTC, cutoff_utc=CUTOFF, newest_first=False)
    descending = build_task_work_history(task, UTC, cutoff_utc=CUTOFF)
    assert [r["entry_id"] for r in ascending] == ["early", "a", "b", "z", "a-date", "z-date", "next"]
    assert [r["entry_id"] for r in descending] == ["next", "early", "a", "b", "z", "a-date", "z-date"]
    task.intervals = dict(reversed(list(task.intervals.items())))
    task.dated_durations = dict(reversed(list(task.dated_durations.items())))
    assert build_task_work_history(task, UTC, cutoff_utc=CUTOFF) == descending
    assert list(before.intervals) == ["z", "b", "a", "early"]


def test_effective_corrections_deletions_detachment_and_restart(setup, monkeypatch):
    s, a, _, _, _, clock = setup
    identity = dated(s, a, MON, 3600)
    old_interval = interval(s, a, local(s, MON, 8), local(s, MON, 9))
    old = history(s, a, monkeypatch)
    saved = deepcopy(old)
    earlier_events = deepcopy(s.events)
    earlier_bytes = s.storage.active_path.read_bytes()
    clock[0] += timedelta(seconds=1)
    s._append(a, "dated_duration_corrected", {
        "entry_id": identity, "work_date_local": str(TUE),
        "duration_seconds": 7200, "reason": "Corrected declared work"})
    s.edit_interval(a, old_interval, local(s, MON, 9), local(s, MON, 10, 30), "Correction")
    current = history(s, a, monkeypatch)
    assert [(r["work_date"], r["duration_seconds"], r["reason"]) for r in current] == [
        (TUE, 7200, "Corrected declared work"), (MON, 5400, "Correction")]
    assert current[1]["entry_id"] != old_interval and current[1]["source"] == "edit"
    assert old == saved and s.events[:len(earlier_events)] == earlier_events
    assert s.storage.active_path.read_bytes().startswith(earlier_bytes)
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert history(restarted, a, monkeypatch) == current
    saved_current = deepcopy(current)
    current[0]["duration_seconds"] = 999
    current.pop()
    assert history(s, a, monkeypatch) == saved_current
    assert history(restarted, a, monkeypatch) == saved_current
    s._append(a, "dated_duration_deleted", {"entry_id": identity, "reason": "Void"})
    s.delete_interval(a, saved_current[1]["entry_id"], "Void interval")
    assert history(s, a, monkeypatch) == []
    assert history(restarted, a, monkeypatch)[0]["duration_seconds"] == 7200


def test_reset_grouping_and_confirmation_never_change_history(setup, monkeypatch):
    s, a, b, p, q, _ = setup
    dated(s, a, MON, 3600)
    dated(s, b, MON, 7200)
    interval(s, a, local(s, MON, 8), local(s, MON, 9))
    before = history(s, a, monkeypatch)
    s.reset_task(a)
    s.update_task(b, "A", "")
    s.assign_task_to_project(a, q)
    prepared = s.prepare_polr_confirmation_batch([{
        "task_id": a, "work_date": str(MON), "confirmed_hundredths": 999999,
        "source_export_id": None, "expected_prior_confirmation_id": None, "stale_export_acknowledged": False}])
    s.register_prepared_polr_confirmation_batch(prepared)
    assert history(s, a, monkeypatch) == before
    assert fsum(r["duration_seconds"] for r in before) == 7200
    assert fsum(r["duration_seconds"] for r in history(s, b, monkeypatch)) == 7200
    assert {r["task_id"] for r in before} == {a} and all(r["task_id"] != p for r in before)


@pytest.mark.parametrize("scope", ["all", "declared", "spillover", "outside", "deleted", "invalid-date"])
def test_legacy_synthetic_refusal_matches_accounting(setup, monkeypatch, scope):
    s, a, _, _, _, _ = setup
    s.add_manual_duration(a, SAT, 50400, "Legacy synthetic")  # noon Saturday through Sunday 02:00
    options = {} if scope == "all" else {"start_date": SAT, "end_date": SAT}
    if scope == "spillover": options = {"start_date": SUN, "end_date": SUN}
    if scope in ("outside", "invalid-date"): options = {"start_date": MON, "end_date": TUE}
    if scope == "deleted":
        s.delete_interval(a, next(iter(s.state.tasks[a].intervals)), "Delete legacy fixture")
    if scope == "invalid-date":
        # Pure corrupted-model fixture, never persisted as a lifecycle event.
        task = deepcopy(s.state.tasks[a])
        next(iter(task.intervals.values())).work_date_local = "invalid"
        with pytest.raises(UnsupportedLegacyDurationError):
            build_task_work_history(task, s.local_tz, cutoff_utc=CUTOFF, **options)
    elif scope in ("outside", "deleted"):
        assert history(s, a, monkeypatch, **options) == []
    else:
        with pytest.raises(UnsupportedLegacyDurationError): history(s, a, monkeypatch, **options)


@pytest.mark.parametrize("fault", ["naive-start", "naive-stop", "negative", "unsupported", "zero", "deleted"])
def test_interval_integrity_is_checked_before_scope_clipping(fault):
    task = model()
    first = datetime(2026, 10, 12, tzinfo=UTC)
    record = IntervalRecord("entry", task.task_id, first, first + timedelta(hours=1), "timer")
    if fault == "naive-start": record.start_utc = first.replace(tzinfo=None)
    elif fault == "naive-stop": record.stop_utc = record.stop_utc.replace(tzinfo=None)
    elif fault == "negative": record.stop_utc = first - timedelta(seconds=1)
    elif fault == "unsupported": record.entry_mode = "other"
    elif fault == "zero": record.stop_utc = first
    else:
        record.deleted = True
        record.start_utc = first.replace(tzinfo=None)
    task.intervals[record.interval_id] = record
    original = deepcopy(task)
    if fault in ("zero", "deleted"):
        assert build_task_work_history(task, UTC, cutoff_utc=CUTOFF) == []
    else:
        with pytest.raises(ValueError):
            build_task_work_history(task, UTC, cutoff_utc=CUTOFF, start_date=TUE, end_date=TUE)
    assert task == original


def test_daily_row_sums_agree_with_mixed_accounting(setup, monkeypatch):
    s, a, _, _, _, clock = setup
    interval(s, a, local(s, SAT, 20), local(s, SUN, 8))
    dated(s, a, SAT, 50400.125)
    clock[0] = local(s, SUN, 10).astimezone(UTC)
    s.start_task(a)
    cutoff = local(s, SUN, 11).astimezone(UTC)
    for start, end in ((SAT, SUN), (SAT, SAT), (SUN, SUN)):
        rows = history(s, a, monkeypatch, start_date=start, end_date=end, cutoff_utc=cutoff)
        daily = {day: fsum(r["duration_seconds"] for r in rows if r["work_date"] == day)
                 for day in {r["work_date"] for r in rows}}
        report = s.calculate_date_window(start, end, cutoff_utc=cutoff, task_ids=(a,))
        assert daily == report["tasks"][a]["daily_seconds"]
        assert fsum(daily.values()) == report["application"]["window_seconds"]
