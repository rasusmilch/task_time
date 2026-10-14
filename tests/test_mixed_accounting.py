"""Behavioral contract for the isolated mixed date-window service API."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from task_timer.accounting import UnsupportedLegacyDurationError
from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage

MON = date(2026, 10, 12)
TUE = date(2026, 10, 13)
SAT = date(2026, 10, 17)
SUN = date(2026, 10, 18)
WEEK = date(2026, 10, 11)
CUTOFF = datetime(2027, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    clock = [datetime(2026, 10, 20, 14, tzinfo=timezone.utc)]
    monkeypatch.setattr("task_timer.app.utc_now", lambda: clock[0])
    monkeypatch.setattr("task_timer.app.detect_local_timezone", lambda: ZoneInfo("America/Chicago"))
    service = TaskTimerService(EventStorage(tmp_path / "fresh"))
    p = service.create_project("P")
    q = service.create_project("Q")
    a = service.create_task("A", "", project_id=p)
    b = service.create_task("B", "", project_id=p)
    return service, a, b, p, q, clock


def local(service, day, hour=0, minute=0):
    return datetime.combine(day, datetime.min.time(), service.local_tz) + timedelta(hours=hour, minutes=minute)


def timed(service, task, day, seconds, hour=9):
    start = local(service, day, hour).astimezone(timezone.utc)
    service.add_manual_interval(task, start, start + timedelta(seconds=seconds), "Timed work")
    return next(reversed(service.state.tasks[task].intervals))


def dated(service, task, day, seconds, entry=None, kind="dated_duration_added"):
    entry = entry or str(uuid4())
    service._append(task, kind, {"entry_id": entry, "work_date_local": day.isoformat(),
                              "duration_seconds": seconds, "reason": "Declared work"})
    return entry


def report(service, start=MON, end=SUN, **selection):
    return service.calculate_date_window(start, end, cutoff_utc=CUTOFF, **selection)


def files(service):
    root = service.storage.data_dir
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def pure_report(service, start=MON, end=SUN, **options):
    before = deepcopy(service.state), deepcopy(service.events), files(service)
    result = report(service, start, end, **options)
    assert (service.state, service.events, files(service)) == before
    assert_conservation(result)
    return result


def assert_conservation(result):
    app = result["application"]
    assert sum(row["window_seconds"] for row in result["tasks"].values()) == app["window_seconds"]
    assert sum(row["window_seconds"] for row in result["projects"].values()) + result["unassigned"]["window_seconds"] == app["window_seconds"]
    for row in [*result["tasks"].values(), *result["projects"].values(), result["unassigned"], app, *result["tags"].values()]:
        assert sum(row["daily_seconds"].values()) == row["window_seconds"]
        assert sum(row["weekly_seconds"].values()) == row["window_seconds"]
    for day, seconds in app["daily_seconds"].items():
        assert sum(row["daily_seconds"].get(day, 0) for row in result["tasks"].values()) == seconds
        assert sum(row["daily_seconds"].get(day, 0) for row in result["projects"].values()) + result["unassigned"]["daily_seconds"].get(day, 0) == seconds
    for week, seconds in app["weekly_seconds"].items():
        assert sum(row["weekly_seconds"].get(week, 0) for row in result["tasks"].values()) == seconds


def test_independent_tasks_projects_and_application_do_not_double_count(setup):
    s, a, b, p, _, _ = setup
    timed(s, a, MON, 3600)
    timed(s, b, MON, 7200)
    dated(s, a, TUE, 5400)
    dated(s, b, TUE, 1800)
    r = pure_report(s, all_tasks=True)
    assert r["tasks"][a]["weekly_seconds"] == r["tasks"][b]["weekly_seconds"] == {WEEK: 9000}
    assert r["projects"][p]["daily_seconds"] == {MON: 10800, TUE: 7200}
    assert r["projects"][p]["weekly_seconds"] == {WEEK: 18000}
    assert r["application"]["window_seconds"] == 18000


@pytest.mark.parametrize("day,seconds", [(TUE, 12600), (SAT, 50400)])
def test_dated_amount_is_whole_on_declared_date_regardless_of_audit_time(setup, day, seconds):
    s, a, _, _, _, _ = setup
    dated(s, a, day, seconds)
    r = pure_report(s, all_tasks=True)
    assert r["tasks"][a]["daily_seconds"] == {day: seconds}
    assert r["tasks"][a]["weekly_seconds"] == {WEEK: seconds}
    for adjacent in [day - timedelta(days=1), day + timedelta(days=1)]:
        assert pure_report(s, adjacent, adjacent, all_tasks=True)["application"]["window_seconds"] == 0
    assert s.state.tasks[a].intervals == {}
    assert report(s, SUN, SUN + timedelta(days=6), all_tasks=True)["application"]["window_seconds"] == 0


def test_mixed_contributions_and_individually_recorded_overlap(setup):
    s, a, _, _, _, _ = setup
    timed(s, a, MON, 3600)
    dated(s, a, MON, 12600)
    assert pure_report(s, all_tasks=True)["tasks"][a]["daily_seconds"] == {MON: 16200}
    timed(s, a, MON, 1800)  # separately recorded overlap still counts
    assert pure_report(s, all_tasks=True)["tasks"][a]["window_seconds"] == 18000


def test_midnight_splits_into_sunday_weeks_and_partial_ranges(setup):
    s, a, _, _, _, _ = setup
    s.add_manual_interval(a, local(s, SAT, 23, 30), local(s, SUN, 1, 30), "Across midnight")
    r = pure_report(s, SAT, SUN, all_tasks=True)
    assert r["tasks"][a]["daily_seconds"] == {SAT: 1800, SUN: 5400}
    assert r["tasks"][a]["weekly_seconds"] == {WEEK: 1800, SUN: 5400}
    assert pure_report(s, SAT, SAT, all_tasks=True)["application"]["window_seconds"] == 1800
    assert pure_report(s, SUN, SUN, all_tasks=True)["application"]["window_seconds"] == 5400


@pytest.mark.parametrize("day,hours", [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_chicago_dst_uses_utc_elapsed_and_preserves_dated_amount(setup, day, hours):
    s, a, _, _, _, _ = setup
    s.add_manual_interval(a, local(s, day), local(s, day + timedelta(days=1)), "DST day")
    dated(s, a, day, 12600)
    r = pure_report(s, day, day, all_tasks=True)
    assert r["tasks"][a]["daily_seconds"] == {day: hours * 3600 + 12600}


def test_duration_correction_date_move_and_deletion_preserve_evidence(setup):
    s, a, _, _, _, _ = setup
    entry = dated(s, a, SAT, 7200)
    original = deepcopy(s.events)
    dated(s, a, SAT, 10800, entry, "dated_duration_corrected")
    assert pure_report(s, all_tasks=True)["tasks"][a]["window_seconds"] == 10800
    dated(s, a, SUN, 10800, entry, "dated_duration_corrected")
    r = pure_report(s, all_tasks=True)
    assert r["tasks"][a]["daily_seconds"] == {SUN: 10800}
    assert r["tasks"][a]["weekly_seconds"] == {SUN: 10800}
    s._append(a, "dated_duration_deleted", {"entry_id": entry, "reason": "Void"})
    assert pure_report(s, all_tasks=True)["tasks"][a]["window_seconds"] == 0
    assert s.events[:len(original)] == original
    assert [e["event_type"] for e in s.events[-4:]] == ["dated_duration_added", "dated_duration_corrected", "dated_duration_corrected", "dated_duration_deleted"]
    assert len(s.state.tasks[a].dated_durations) == 1


def test_running_cutoff_is_shared_and_calculation_is_pure(setup):
    s, a, b, _, _, clock = setup
    clock[0] = local(s, MON, 9).astimezone(timezone.utc)
    s.start_task(a)
    timed(s, b, MON, 7200)  # closed record also cannot contribute past cutoff
    cutoff = local(s, MON, 10).astimezone(timezone.utc)
    before = deepcopy(s.state), deepcopy(s.events), files(s)
    r = s.calculate_date_window(MON, MON, all_tasks=True, cutoff_utc=cutoff)
    assert r["tasks"][a]["window_seconds"] == r["tasks"][b]["window_seconds"] == 3600
    assert r["application"]["window_seconds"] == 7200
    assert (s.state, s.events, files(s)) == before
    assert s.state.tasks[a].is_running
    assert s.calculate_date_window(MON, MON, all_tasks=True, cutoff_utc=clock[0] - timedelta(seconds=1))["application"]["window_seconds"] == 0


def test_interval_replacement_and_deletion(setup):
    s, a, _, _, _, _ = setup
    old = timed(s, a, MON, 3600)
    s.edit_interval(a, old, local(s, MON, 9), local(s, MON, 10, 30), "Correction")
    assert pure_report(s, all_tasks=True)["tasks"][a]["window_seconds"] == 5400
    replacement = next(reversed(s.state.tasks[a].intervals))
    s.delete_interval(a, replacement, "Void")
    assert pure_report(s, all_tasks=True)["tasks"][a]["window_seconds"] == 0
    assert len(s.state.tasks[a].intervals) == 2


def test_historical_reset_preserves_both_types_without_changing_current_counter(setup):
    s, a, _, _, _, clock = setup
    timed(s, a, MON, 3600)
    dated(s, a, MON, 12600)
    clock[0] = local(s, MON, 10).astimezone(timezone.utc)
    s.reset_task(a)
    timed(s, a, MON, 1800, hour=11)
    assert s.task_elapsed(s.state.tasks[a], CUTOFF) == 1800
    assert pure_report(s, all_tasks=True)["tasks"][a]["window_seconds"] == 18000


def test_reassignment_regroups_current_membership_without_changing_work(setup):
    s, a, b, p, q, _ = setup
    timed(s, a, MON, 3600)
    dated(s, b, MON, 7200)
    before = pure_report(s, all_tasks=True)
    contributions = deepcopy(s.state.tasks[b].dated_durations), deepcopy(s.state.tasks[b].intervals)
    s.assign_task_to_project(b, q)
    after = pure_report(s, all_tasks=True)
    assert after["tasks"][b]["daily_seconds"] == before["tasks"][b]["daily_seconds"]
    assert after["projects"][p]["window_seconds"] == 3600
    assert after["projects"][q]["window_seconds"] == 7200
    assert after["application"] == before["application"]
    assert (s.state.tasks[b].dated_durations, s.state.tasks[b].intervals) == contributions


def test_selection_union_empty_unassigned_and_partial_project_labels(setup):
    s, a, b, p, _, _ = setup
    u = s.create_task("Unassigned", "")
    for task, amount in [(a, 3600), (b, 7200), (u, 1800)]:
        dated(s, task, MON, amount)
    assert pure_report(s)["tasks"] == {}
    assert pure_report(s, task_ids=(), project_ids=())["application"]["window_seconds"] == 0
    union = pure_report(s, project_ids=(p, p), task_ids=(a, a))
    assert union["application"]["window_seconds"] == 10800
    assert union["projects"][p]["scope"] == "full_project"
    single = pure_report(s, task_ids=(a,))
    assert set(single["tasks"]) == {a}
    assert single["projects"][p]["scope"] == "selected_tasks"
    assert single["projects"][p]["eligible_task_count"] == 2
    unassigned = pure_report(s, include_unassigned=True)
    assert set(unassigned["tasks"]) == {u}
    assert unassigned["unassigned"]["window_seconds"] == 1800
    assert unassigned["projects"] == {}
    assert pure_report(s, project_ids=(p,), include_unassigned=True)["application"]["window_seconds"] == 12600


def test_duplicate_names_are_independent_uuid_keys(setup):
    s, a, b, p, q, _ = setup
    s.update_task(a, "Same", "")
    s.update_task(b, "Same", "")
    c = s.create_task("Same", "", project_id=q)
    for task, amount in [(a, 1), (b, 2), (c, 3)]:
        dated(s, task, MON, amount)
    r = pure_report(s, all_tasks=True)
    assert set(r["tasks"]) == {a, b, c}
    assert [r["tasks"][key]["window_seconds"] for key in [a, b, c]] == [1, 2, 3]
    assert r["projects"][p]["window_seconds"] == r["projects"][q]["window_seconds"] == 3


def test_deleted_task_history_is_explicit(setup):
    s, a, _, p, _, _ = setup
    timed(s, a, MON, 3600)
    dated(s, a, MON, 7200)
    s.delete_task_only(a)
    assert a not in pure_report(s, all_tasks=True)["tasks"]
    assert pure_report(s, task_ids=(a,))["tasks"] == {}
    historical = pure_report(s, project_ids=(p,), include_deleted=True)
    assert historical["tasks"][a]["is_deleted"] is True
    assert historical["tasks"][a]["window_seconds"] == 10800
    assert historical["include_deleted"] is True


def test_inclusive_window_clips_intervals_and_excludes_outside_dated_work(setup):
    s, a, _, _, _, _ = setup
    s.add_manual_interval(a, local(s, MON - timedelta(days=1), 23), local(s, TUE + timedelta(days=1), 1), "Long real interval")
    for day in [MON - timedelta(days=1), MON, TUE, TUE + timedelta(days=1)]:
        dated(s, a, day, 12600)
    r = pure_report(s, MON, TUE, all_tasks=True)
    assert r["tasks"][a]["daily_seconds"] == {MON: 99000, TUE: 99000}
    assert r["tasks"][a]["window_seconds"] == 198000


def test_legacy_synthetic_duration_has_explicit_scope_boundary(setup):
    s, a, b, _, _, _ = setup
    s.add_manual_duration(a, SAT, 50400, "Legacy")
    before = deepcopy(s.state), deepcopy(s.events), files(s)
    for start, end in [(SAT, SAT), (SUN, SUN), (MON, SUN)]:
        with pytest.raises(UnsupportedLegacyDurationError):
            report(s, start, end, all_tasks=True)
    assert (s.state, s.events, files(s)) == before
    assert s.task_elapsed(s.state.tasks[a], CUTOFF) == 50400
    assert pure_report(s, MON, MON, all_tasks=True)["application"]["window_seconds"] == 0
    assert pure_report(s, SAT, SUN, task_ids=(b,))["application"]["window_seconds"] == 0
    legacy = next(iter(s.state.tasks[a].intervals))
    s.delete_interval(a, legacy, "Void")
    assert pure_report(s, all_tasks=True)["application"]["window_seconds"] == 0


def test_tags_are_nonexclusive_and_use_same_mixed_rows(setup):
    s, a, b, _, _, _ = setup
    s.update_task_tags(a, ["one", "two"])
    s.update_task_tags(b, ["two"])
    u = s.create_task("Untagged", "")
    named = s.create_task("Literal tag", "", tags=["untagged"])
    timed(s, a, MON, 3600)
    dated(s, a, MON, 12600)
    dated(s, b, MON, 1800)
    dated(s, u, MON, 600)
    dated(s, named, MON, 300)
    r = pure_report(s, all_tasks=True)
    assert r["tags"]["one"]["window_seconds"] == 16200
    assert r["tags"]["two"]["window_seconds"] == 18000
    assert r["tags"][None]["window_seconds"] == 600
    assert r["tags"]["untagged"]["window_seconds"] == 300
    assert r["application"]["window_seconds"] == 18900


def test_submission_evidence_never_adds_actual_work(setup):
    s, a, _, _, _, _ = setup
    timed(s, a, MON, 3600)
    dated(s, a, MON, 12600)
    before = pure_report(s, all_tasks=True)
    s.create_time_submission_marker([a], None, CUTOFF, "Submitted", None)
    marker = s.events[-1]
    assert marker["payload"]["submitted_overall_totals_by_task"][a] == 3600  # legacy reader stays unchanged
    assert pure_report(s, all_tasks=True) == before


@pytest.mark.parametrize("options", [
    {"task_ids": ("missing",)}, {"project_ids": ("missing",)},
    {"task_ids": "not-a-list"}, {"project_ids": None}, {"all_tasks": 1},
])
def test_invalid_selection_has_no_effect(setup, options):
    s, _, _, _, _, _ = setup
    before = deepcopy(s.state), deepcopy(s.events), files(s)
    with pytest.raises(ValueError):
        report(s, **options)
    assert (s.state, s.events, files(s)) == before


@pytest.mark.parametrize("start,end", [(TUE, MON), ("2026-10-12", TUE), (MON, date.max), (datetime(2026, 10, 12), TUE)])
def test_invalid_date_windows_rejected(setup, start, end):
    with pytest.raises(ValueError):
        report(setup[0], start, end, all_tasks=True)


def test_invalid_cross_domain_refs_and_cutoff_rejected_before_accounting(setup):
    s, a, _, p, _, _ = setup
    for options in [{"task_ids": (p,)}, {"project_ids": (a,)}]:
        with pytest.raises(ValueError):
            report(s, **options)
    with pytest.raises(ValueError):
        s.calculate_date_window(MON, TUE, all_tasks=True, cutoff_utc=datetime(2026, 10, 20))


def test_negative_recorded_span_rejected_and_zero_span_safe(setup):
    s, a, _, _, _, _ = setup
    interval = s.state.tasks[a].intervals[timed(s, a, MON, 3600)]
    interval.stop_utc = interval.start_utc - timedelta(seconds=1)
    with pytest.raises(ValueError, match="Negative interval"):
        report(s, all_tasks=True)
    interval.stop_utc = interval.start_utc
    assert pure_report(s, all_tasks=True)["application"]["window_seconds"] == 0


def test_fractional_seconds_are_not_rounded_and_returned_maps_are_detached(setup):
    s, a, _, _, _, _ = setup
    dated(s, a, MON, 1.25)
    dated(s, a, TUE, 2.5)
    r = pure_report(s, all_tasks=True)
    assert r["tasks"][a]["window_seconds"] == 3.75
    r["tasks"][a]["daily_seconds"][MON] = 999
    assert report(s, all_tasks=True)["tasks"][a]["daily_seconds"][MON] == 1.25


def test_restart_snapshot_rebuild_and_backup_restore_keep_calculated_results(setup):
    s, a, _, _, _, _ = setup
    timed(s, a, MON, 3600)
    entry = dated(s, a, SAT, 7200)
    dated(s, a, SUN, 10800, entry, "dated_duration_corrected")
    expected = pure_report(s, all_tasks=True)
    backup = s.create_backup_now("Mixed calculation fixture")
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert pure_report(restarted, all_tasks=True) == expected
    restarted.rebuild_snapshot_from_journal()
    assert pure_report(restarted, all_tasks=True) == expected
    restarted._append(a, "dated_duration_deleted", {"entry_id": entry, "reason": "Void"})
    restarted.restore_from_backup(backup)
    assert pure_report(restarted, all_tasks=True) == expected


def test_cutoff_never_becomes_a_clock_position_for_dated_work(setup):
    s, a, _, _, _, _ = setup
    dated(s, a, SAT, 50400)
    r = s.calculate_date_window(SAT, SUN, task_ids=(a,), cutoff_utc=local(s, SAT).astimezone(timezone.utc))
    assert r["tasks"][a]["daily_seconds"] == {SAT: 50400}


def test_unknown_references_are_validated_before_selected_legacy_records(setup):
    s, a, _, _, _, _ = setup
    s.add_manual_duration(a, MON, 3600, "Legacy")
    with pytest.raises(ValueError, match="Unknown project reference"):
        report(s, all_tasks=True, project_ids=(str(uuid4()),))


def test_no_new_ancestor_tag_or_selection_inheritance(setup):
    s, a, _, p, _, _ = setup
    s.update_task_tags(a, ["parent"])
    child = s.create_subtask(a, "Child", "")
    dated(s, child, MON, 3600)
    assert report(s, task_ids=(a,))["application"]["window_seconds"] == 0
    assert child not in report(s, project_ids=(p,))["tasks"]
    r = pure_report(s, task_ids=(child,))
    assert r["tags"][None]["window_seconds"] == 3600
    assert "parent" not in r["tags"]


def test_archive_rotation_and_fresh_start_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr("task_timer.app.utc_now", lambda: CUTOFF)
    s = TaskTimerService(EventStorage(tmp_path / "old-home" / ".task_timer_data", max_active_events=2))
    a = s.create_task("Archived", "")
    timed(s, a, MON, 3600)
    entry = dated(s, a, SAT, 7200)
    dated(s, a, SUN, 10800, entry, "dated_duration_corrected")
    expected = pure_report(s, all_tasks=True)
    assert len(s.storage.load_manifest()["archives"]) == 2
    original_files = files(s)
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert pure_report(restarted, all_tasks=True) == expected
    assert files(s) == original_files
    from pathlib import Path
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "old-home")
    fresh = TaskTimerService(EventStorage(tmp_path / "fresh-installation"))
    assert pure_report(fresh, all_tasks=True)["application"]["window_seconds"] == 0
    assert fresh.state.tasks == fresh.state.projects == {}
    assert fresh.events == []
    assert files(s) == original_files


@pytest.mark.parametrize('all_tasks,include_deleted', [(False, False), (False, True), (True, False), (True, True)])
def test_report_metadata_derives_from_request_and_calculation_timezone(setup, all_tasks, include_deleted):
    s, a, _, p, _, _ = setup
    dated(s, a, MON, 12600)
    r = pure_report(s, task_ids=(a,), project_ids=(p,), all_tasks=all_tasks, include_deleted=include_deleted)
    assert r['scope'] == ('complete' if all_tasks else 'selected')
    assert r['include_deleted'] is include_deleted
    assert r['local_timezone'] == 'America/Chicago'
    assert r['tasks'][a]['window_seconds'] == 12600
    s.local_tz = ZoneInfo('UTC')
    assert pure_report(s, all_tasks=all_tasks)['local_timezone'] == 'UTC'
