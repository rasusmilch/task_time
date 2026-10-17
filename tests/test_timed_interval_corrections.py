"""Staged closed-work corrections: real replay, isolated journals and injected failures."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from task_timer import app as app_module
from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage
from test_mixed_accounting import setup, timed, dated, local, files, MON, TUE, CUTOFF
from test_polr_confirmation_replay import cell, journal


def capture(s):
    return (deepcopy(s.state), deepcopy(s.events), deepcopy(s._timesheet_exports),
            s.get_effective_polr_confirmations(), files(s))


def fail(*args, **kwargs):
    raise OSError("injected failure")


def forbidden(*args, **kwargs):
    pytest.fail("unexpected write or backup")


def seed(s, a, *, fractional=False):
    if not fractional:
        return timed(s, a, MON, 3600)
    identity = str(uuid4())
    first = local(s, MON, 9).astimezone(timezone.utc) + timedelta(seconds=12, microseconds=345678)
    last = first + timedelta(hours=1, seconds=3, microseconds=111111)
    s._append(a, "manual_interval_added", {"interval_id": identity,
        "start_utc": first.isoformat().replace("+00:00", "Z"),
        "stop_utc": last.isoformat().replace("+00:00", "Z"), "reason": "Recorded precision"})
    return identity


def candidate(s, a, old, **kwargs):
    return s.prepare_timed_interval_correction(a, old, stop_utc=local(s, MON, 11), **kwargs)


def assert_registered(s, event, result):
    assert set(result) == {"event_id", "replacement_interval_id", "projection_installed", "snapshot_saved", "warnings"}
    assert result["event_id"] == event["event_id"]
    assert result["replacement_interval_id"] == event["payload"]["new_interval_id"]
    assert type(result["warnings"]) is tuple
    assert [e for e in journal(s) if e["event_id"] == event["event_id"]] == [event]


@pytest.mark.parametrize("comment", ["", " \t ", "  Corrected timing  "])
@pytest.mark.parametrize("endpoint", ["start", "stop"])
def test_prepare_and_register_preserve_other_endpoint_precision_and_audit(setup, monkeypatch, comment, endpoint):
    s, a, _, _, _, _ = setup
    old = seed(s, a, fractional=True)
    prior = deepcopy(s.state.tasks[a].intervals[old])
    changed = local(s, MON, 8 if endpoint == "start" else 11)
    endpoints = {endpoint + "_utc": changed}
    if comment == "":
        # Explicitly unchanged endpoints retain precision just like omitted ones.
        other = "stop" if endpoint == "start" else "start"
        endpoints[other + "_utc"] = getattr(prior, other + "_utc")
    before = capture(s)
    s.local_tz_name = "UTC-05:00"
    with monkeypatch.context() as m:
        for name in ("append_event", "save_snapshot", "synchronize_journal"):
            m.setattr(s.storage, name, forbidden)
        m.setattr(s, "_create_risky_operation_backup", forbidden)
        event = s.prepare_timed_interval_correction(a, old, **endpoints, comment=comment)
    assert capture(s) == before
    assert event["local_timezone"] == "UTC-05:00"
    assert event["timestamp_utc"] == "2026-10-20T14:00:00Z"
    assert event["payload"]["reason"] == comment.strip()
    assert event["payload"]["prior_interval_label"] == "2026-10-12T14:00:12.345678Z to 2026-10-12T15:00:15.456789Z"
    original = deepcopy(event)
    result = s.register_prepared_timed_interval_correction(event)
    assert_registered(s, event, result)
    assert result["projection_installed"] and result["snapshot_saved"] and not result["warnings"]
    new = s.state.tasks[a].intervals[result["replacement_interval_id"]]
    assert new.start_utc == (changed.astimezone(timezone.utc) if endpoint == "start" else prior.start_utc)
    assert new.stop_utc == (changed.astimezone(timezone.utc) if endpoint == "stop" else prior.stop_utc)
    assert new.source == "edit" and new.replaced_interval_id == old and new.edit_reason == comment.strip()
    assert s.state.tasks[a].intervals[old].deleted and event == original
    assert before[0].tasks[a].intervals[old] == prior  # earlier detached evidence stays intact
    result["warnings"] = ("caller modification",)
    assert s.state.tasks[a].intervals[new.interval_id] == new


def test_no_change_has_no_audit_capture_backup_or_comment_event(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    old = seed(s, a, fractional=True)
    prior = s.state.tasks[a].intervals[old]
    before = capture(s)
    monkeypatch.setattr(app_module, "utc_now", forbidden)
    # Existing work replay may allocate unused legacy default IDs; no new correction ID is stored.
    for name in ("append_event", "save_snapshot", "synchronize_journal"):
        monkeypatch.setattr(s.storage, name, forbidden)
    monkeypatch.setattr(s, "_create_risky_operation_backup", forbidden)
    assert s.prepare_timed_interval_correction(a, old, comment="comment alone") is None
    assert s.prepare_timed_interval_correction(a, old, start_utc=prior.start_utc,
                                             stop_utc=prior.stop_utc) is None
    assert capture(s) == before


@pytest.mark.parametrize("fault", ["task-type", "task-unknown", "project", "deleted-task", "id-type", "open",
    "dated", "synthetic", "deleted", "superseded", "comment", "naive", "endpoint-type", "seconds", "fraction", "span"])
def test_invalid_requests_reject_before_backup_or_work_writes(setup, monkeypatch, fault):
    s, a, b, p, _, _ = setup
    old = seed(s, a)
    owner, identity, kwargs = a, old, {"stop_utc": local(s, MON, 11)}
    if fault == "task-type": owner = None
    elif fault == "task-unknown": owner = str(uuid4())
    elif fault == "project": owner = p
    elif fault == "deleted-task": s.delete_task(a)
    elif fault == "id-type": identity = 12
    elif fault == "open": identity = "__open__"
    elif fault == "dated": identity = dated(s, a, MON, 3600)
    elif fault == "synthetic":
        s.add_manual_duration(a, MON, 3600, "Legacy")
        identity = next(reversed(s.state.tasks[a].intervals))
    elif fault == "deleted": s.delete_interval(a, old, "Removed")
    elif fault == "superseded": s.edit_interval(a, old, local(s, MON, 9), local(s, MON, 10, 30), "Prior edit")
    elif fault == "comment": kwargs["comment"] = None
    elif fault == "naive": kwargs["stop_utc"] = datetime(2026, 10, 12, 11)
    elif fault == "endpoint-type": kwargs["start_utc"] = "2026-10-12T14:00:00Z"
    elif fault == "seconds": kwargs["stop_utc"] += timedelta(seconds=1)
    elif fault == "fraction": kwargs["stop_utc"] += timedelta(microseconds=1)
    elif fault == "span": kwargs["stop_utc"] = local(s, MON, 8)
    before = capture(s)
    monkeypatch.setattr(s, "_create_risky_operation_backup", forbidden)
    monkeypatch.setattr(s.storage, "append_event", forbidden)
    with pytest.raises(ValueError):
        s.prepare_timed_interval_correction(owner, identity, **kwargs)
    assert capture(s) == before


@pytest.mark.parametrize("fault", ["envelope", "schema", "event-id", "task-id", "event-type", "audit", "zone",
    "payload", "old-id", "new-id", "mode", "start", "span", "label", "reason", "collision-interval",
    "collision-dated", "wrong-owner", "wrong-context", "nonminute", "nochange"])
def test_malformed_or_inapplicable_candidate_never_appends(setup, monkeypatch, fault):
    s, a, b, _, _, _ = setup
    old = seed(s, a)
    other = timed(s, b, MON, 1800)
    tombstone = dated(s, b, MON, 12)
    s._append(b, "dated_duration_deleted", {"entry_id": tombstone, "reason": "removed"})
    event = candidate(s, a, old)
    payload = event["payload"]
    if fault == "envelope": event["extra"] = 1
    elif fault == "schema": event["schema_version"] = True
    elif fault == "event-id": event["event_id"] = "bad"
    elif fault == "task-id": event["task_id"] = "__app__"
    elif fault == "event-type": event["event_type"] = "started"
    elif fault == "audit": event["timestamp_utc"] += " "
    elif fault == "zone": event["local_timezone"] = "UTC\x00"
    elif fault == "payload": payload["extra"] = 1
    elif fault == "old-id": payload["interval_id"] = "__open__"
    elif fault == "new-id": payload["new_interval_id"] = str(uuid4()).upper()
    elif fault == "mode": payload["entry_mode"] = "duration"
    elif fault == "start": payload["start_utc"] = "2026-10-12T14:00:00+00:00"
    elif fault == "span": payload["stop_utc"] = payload["start_utc"]
    elif fault == "label": payload["prior_interval_label"] = "unparseable"
    elif fault == "reason": payload["reason"] = " untrimmed "
    elif fault == "collision-interval": payload["new_interval_id"] = other
    elif fault == "collision-dated": payload["new_interval_id"] = tombstone
    elif fault == "wrong-owner": event["task_id"] = b
    elif fault == "wrong-context": payload["prior_interval_label"] = "2026-10-11T14:00:00Z to 2026-10-11T15:00:00Z"
    elif fault == "nonminute": payload["stop_utc"] = "2026-10-12T16:00:01Z"
    elif fault == "nochange": payload["stop_utc"] = "2026-10-12T15:00:00Z"
    before, original = capture(s), deepcopy(event)
    monkeypatch.setattr(s, "_create_risky_operation_backup", forbidden)
    monkeypatch.setattr(s.storage, "append_event", forbidden)
    with pytest.raises(ValueError): s.register_prepared_timed_interval_correction(event)
    assert capture(s) == before and event == original


@pytest.mark.parametrize("when,accepted", [("equal", True), ("before-creation", False), ("between-creation-and-work", False)])
def test_audit_order_is_not_rewritten_to_force_effects(setup, monkeypatch, when, accepted):
    s, a, _, _, _, clock = setup
    if when == "between-creation-and-work": clock[0] += timedelta(hours=2)
    old = seed(s, a)
    if when == "before-creation": clock[0] -= timedelta(days=1)
    elif when == "between-creation-and-work": clock[0] -= timedelta(hours=1)
    before = capture(s)
    if accepted:
        event = candidate(s, a, old)
        s.register_prepared_timed_interval_correction(event)
        assert s.state.tasks[a].updated_at_utc == clock[0]
    else:
        with pytest.raises(ValueError, match="replay ordering"): candidate(s, a, old)
        assert capture(s) == before


def test_backdated_but_effectively_equivalent_correction_preserves_later_attributes(setup):
    s, a, _, _, _, clock = setup
    old = seed(s, a)
    event = candidate(s, a, old)
    clock[0] += timedelta(hours=1)
    s.update_task(a, "Later name", "")
    s.register_prepared_timed_interval_correction(event)
    assert s.state.tasks[a].name == "Later name" and s.state.tasks[a].updated_at_utc == clock[0]


@pytest.mark.parametrize("phase", ["preparation", "registration", "backup-hook"])
def test_fresh_authority_rejects_superseded_prior_despite_stale_cache(setup, monkeypatch, phase):
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    event = candidate(s, a, old)
    stale = deepcopy(s.state)
    def supersede():
        other = TaskTimerService(EventStorage(s.storage.data_dir))
        other.edit_interval(a, old, local(s, MON, 9), local(s, MON, 10, 30), "Other correction")
    if phase == "backup-hook": monkeypatch.setattr(s, "_create_risky_operation_backup", lambda *args: supersede())
    else:
        supersede()
        assert s.state == stale
        monkeypatch.setattr(s, "_create_risky_operation_backup", forbidden)
    before = files(s)
    with pytest.raises(ValueError, match="effective"):
        if phase == "preparation": candidate(s, a, old)
        else: s.register_prepared_timed_interval_correction(event)
    if phase != "backup-hook": assert files(s) == before
    assert event["event_id"] not in [e["event_id"] for e in journal(s)]


@pytest.mark.parametrize("fault", ["before", "noop", "partial", "complete", "rotation-manifest"])
def test_append_outcomes_preserve_identity_and_never_false_success(setup, monkeypatch, fault):
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    event, append = candidate(s, a, old), s.storage.append_event
    original, before, calls = deepcopy(event), capture(s), []
    # Isolate append effects; configured real backup behavior is covered separately.
    backups = []
    monkeypatch.setattr(s, "_create_risky_operation_backup", lambda reason: backups.append(reason))
    def append_fault(value):
        calls.append(deepcopy(value))
        if fault == "before": raise OSError("before append")
        if fault == "noop": return
        if fault == "partial":
            with s.storage.active_path.open("a", encoding="utf-8") as handle: handle.write('{"event_id":')
            raise OSError("partial append")
        append(value)
        if fault == "complete": raise OSError("after complete append")
    with monkeypatch.context() as m:
        m.setattr(s.storage, "append_event", append_fault)
        if fault == "rotation-manifest":
            s.storage.max_active_events = 1
            m.setattr(s.storage, "save_manifest", fail)
        if fault == "complete":
            result = s.register_prepared_timed_interval_correction(event)
            assert_registered(s, event, result)
            assert result["snapshot_saved"] and "after complete append" in result["warnings"][0]
        else:
            with pytest.raises((OSError, ValueError)):
                s.register_prepared_timed_interval_correction(event)
            assert s.state == before[0] and s.events == before[1]
    assert calls == [original] and event == original
    assert backups == ["before timed interval correction"]
    if fault in {"before", "noop"}:
        assert capture(s) == before
        result = s.register_prepared_timed_interval_correction(event)
        assert_registered(s, event, result)
    elif fault in {"partial", "rotation-manifest"}:
        damaged = files(s)
        with pytest.raises((OSError, ValueError)):
            s.register_prepared_timed_interval_correction(event)
        assert files(s) == damaged  # no repair or second append


@pytest.mark.parametrize("committed", [False, True])
@pytest.mark.parametrize("fault", ["sync", "open", "close", "fsync", "reread", "projection"])
def test_recovery_and_reuse_require_successful_flush_close_and_full_validation(setup, monkeypatch, committed, fault):
    s, a, _, _, _, _ = setup
    event = candidate(s, a, seed(s, a))
    if committed: s.register_prepared_timed_interval_correction(event)
    append, real_open = s.storage.append_event, Path.open
    before, calls = capture(s), []
    def complete_error(value):
        calls.append(1)
        append(value)
        raise OSError("append uncertainty")
    with monkeypatch.context() as m:
        m.setattr(s.storage, "append_event", forbidden if committed else complete_error)
        if fault == "sync": m.setattr(s.storage, "synchronize_journal", fail)
        elif fault == "open":
            def denied_open(path, *args, **kwargs):
                if args and args[0] == "r+b": raise PermissionError("synchronization open denied")
                return real_open(path, *args, **kwargs)
            m.setattr(Path, "open", denied_open)
        elif fault == "fsync":
            # Inject only synchronization, not the initial append's flush.
            sync = s.storage.synchronize_journal
            def sync_failure():
                with monkeypatch.context() as inner:
                    inner.setattr("task_timer.storage.os.fsync", fail)
                    return sync()
            m.setattr(s.storage, "synchronize_journal", sync_failure)
        elif fault == "close":
            class BadClose:
                def __init__(self, handle): self.handle = handle
                def __enter__(self): return self.handle
                def __exit__(self, *args):
                    self.handle.close()
                    raise OSError("sync close failure")
            def open_file(path, *args, **kwargs):
                handle = real_open(path, *args, **kwargs)
                return BadClose(handle) if args and args[0] == "r+b" else handle
            m.setattr(Path, "open", open_file)
        elif fault == "reread":
            sync = s.storage.synchronize_journal
            def sync_then_inspection_failure():
                sync()
                m.setattr(s.storage, "iter_all_events", fail)
            m.setattr(s.storage, "synchronize_journal", sync_then_inspection_failure)
        elif fault == "projection":
            sync = s.storage.synchronize_journal
            def sync_then_projection_failure():
                result = sync()
                m.setattr(s, "_derive_timed_correction_journal", fail)
                return result
            m.setattr(s.storage, "synchronize_journal", sync_then_projection_failure)
        with pytest.raises(OSError): s.register_prepared_timed_interval_correction(event)
        assert s.state == before[0] and s.events == before[1]
        if fault in {"sync", "open", "close", "fsync"}:
            # A persistent failure on exact retry is still not success.
            with pytest.raises(OSError): s.register_prepared_timed_interval_correction(event)
    assert calls == ([] if committed else [1])
    result = s.register_prepared_timed_interval_correction(event)
    assert_registered(s, event, result)
    assert result["projection_installed"] and result["snapshot_saved"]


@pytest.mark.parametrize("persistent", [False, True])
def test_real_append_fsync_failure_requires_synchronization_before_success(setup, monkeypatch, persistent):
    import os
    s, a, _, _, _, _ = setup
    event = candidate(s, a, seed(s, a))
    fsync, calls = os.fsync, []
    monkeypatch.setattr(s, "_create_risky_operation_backup", lambda *args: None)
    def failed_flush(fd):
        calls.append(fd)
        if persistent or len(calls) == 1: raise OSError("append/sync fsync failure")
        fsync(fd)
    with monkeypatch.context() as m:
        m.setattr(os, "fsync", failed_flush)
        if persistent:
            before = deepcopy(s.state)
            with pytest.raises(OSError): s.register_prepared_timed_interval_correction(event)
            assert s.state == before
            with pytest.raises(OSError): s.register_prepared_timed_interval_correction(event)
        else:
            result = s.register_prepared_timed_interval_correction(event)
            assert result["snapshot_saved"] and "fsync failure" in result["warnings"][0]
    assert len(calls) >= 3
    monkeypatch.setattr(s.storage, "append_event", forbidden)
    assert_registered(s, event, s.register_prepared_timed_interval_correction(event))


@pytest.mark.parametrize("fault", ["backup", "install", "snapshot"])
def test_registered_vs_unregistered_failure_results(setup, monkeypatch, fault):
    s, a, _, _, _, _ = setup
    event = candidate(s, a, seed(s, a))
    before = capture(s)
    with monkeypatch.context() as m:
        if fault == "backup":
            m.setattr(s, "_create_risky_operation_backup", fail)
            m.setattr(s.storage, "append_event", forbidden)
            with pytest.raises(OSError): s.register_prepared_timed_interval_correction(event)
            assert capture(s) == before
        else:
            m.setattr(s, "_install_timed_correction_journal" if fault == "install" else "_save_snapshot", fail)
            if fault == "install": m.setattr(s, "_save_snapshot", forbidden)
            result = s.register_prepared_timed_interval_correction(event)
            assert_registered(s, event, result)
            assert result["projection_installed"] is (fault == "snapshot")
            assert result["snapshot_saved"] is False and "registered" in result["warnings"][0]
            assert files(s)["state_snapshot.json"] == before[4]["state_snapshot.json"]
    result = s.register_prepared_timed_interval_correction(event)
    assert_registered(s, event, result)
    assert result["snapshot_saved"]


@pytest.mark.parametrize("fault", ["duplicate", "conflict", "cross-type", "active-missing", "manifest-missing", "malformed-confirmation"])
def test_unhealthy_or_conflicting_evidence_fails_closed_without_repair(setup, monkeypatch, fault):
    s, a, _, _, _, _ = setup
    event = candidate(s, a, seed(s, a))
    s.register_prepared_timed_interval_correction(event)
    if fault in {"duplicate", "conflict"}:
        extra = deepcopy(event)
        if fault == "conflict": extra["payload"]["reason"] = "conflicting"
        s.storage.append_event(extra)
    elif fault == "cross-type":
        # One occurrence belonging to another type, independently of duplicate count.
        event["event_id"] = journal(s)[0]["event_id"]
    elif fault == "active-missing": s.storage.active_path.unlink()
    elif fault == "manifest-missing": s.storage.manifest_path.unlink()
    else:
        bad = deepcopy(event)
        bad.update(event_id=str(uuid4()), task_id="__app__", event_type="polr_confirmation_batch_recorded", payload={"cells": []})
        s.storage.append_event(bad)
    before = capture(s)
    monkeypatch.setattr(s.storage, "append_event", forbidden)
    with pytest.raises((OSError, ValueError)): s.register_prepared_timed_interval_correction(event)
    assert capture(s) == before


def test_exact_retry_installs_latest_work_and_confirmation_without_rollback(setup, tmp_path, monkeypatch):
    s, a, b, _, _, clock = setup
    old = seed(s, a)
    timed(s, b, TUE, 900)
    export = s.prepare_timesheet_export_snapshot(MON, TUE, cutoff_utc=CUTOFF, all_tasks=True)
    s.register_prepared_timesheet_export(export)
    path = tmp_path / "frozen.txt"
    s.materialize_timesheet_export(export["event_id"], path)
    confirm = s.prepare_polr_confirmation_batch([cell(a)])
    s.register_prepared_polr_confirmation_batch(confirm)
    s.start_task(b)
    before, frozen = deepcopy(s.state), path.read_bytes()
    event = candidate(s, a, old)
    s.register_prepared_timed_interval_correction(event)
    first_state, first_event = deepcopy(s.state), deepcopy(event)
    clock[0] += timedelta(minutes=1)
    newer = s.prepare_timed_interval_correction(a, event["payload"]["new_interval_id"], stop_utc=local(s, MON, 12))
    # Another serialized instance leaves this instance's caches stale.
    other = TaskTimerService(EventStorage(s.storage.data_dir))
    other.register_prepared_timed_interval_correction(newer)
    latest = other.prepare_polr_confirmation_batch([cell(a, 500, prior=confirm["event_id"])])
    other.register_prepared_polr_confirmation_batch(latest)
    expected = deepcopy(other.state), other.get_effective_polr_confirmations()
    before_retry = journal(s)
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    monkeypatch.setattr(s.storage, "append_event", forbidden)
    monkeypatch.setattr(s, "_create_risky_operation_backup", forbidden)
    result = s.register_prepared_timed_interval_correction(event)
    assert_registered(s, event, result)
    assert (s.state, s.get_effective_polr_confirmations()) == expected
    assert journal(s) == before_retry and path.read_bytes() == frozen
    assert s.state.tasks[b] == before.tasks[b] and s.list_time_submissions() == []
    assert s._timesheet_exports[export["event_id"]] == export
    assert first_state.tasks[a].intervals[event["payload"]["new_interval_id"]].deleted is False
    assert event == first_event and s.state.tasks[a].last_reset_utc == before.tasks[a].last_reset_utc
    assert s.state.tasks[b].is_running


@pytest.mark.parametrize("enabled", [False, True])
def test_configured_safety_backup_precedes_append_and_contains_original_work(setup, monkeypatch, enabled):
    s, a, _, _, _, clock = setup
    event = candidate(s, a, seed(s, a))
    settings = s.load_backup_settings()
    settings.auto_backup_before_risky_operations = enabled
    s.save_backup_settings(settings)
    monkeypatch.setattr("task_timer.backups.utc_now", lambda: clock[0])
    before = set(files(s))
    append, observed = s.storage.append_event, []
    def append_after_backup(value):
        observed.append(set(files(s)) - before)
        append(value)
    monkeypatch.setattr(s.storage, "append_event", append_after_backup)
    s.register_prepared_timed_interval_correction(event)
    assert len(observed) == 1
    assert bool(observed[0]) is enabled
    if enabled:
        import zipfile
        backup = next(s.storage.data_dir / name for name in observed[0] if name.endswith(".zip"))
        with zipfile.ZipFile(backup) as saved:
            assert event["event_id"].encode() not in saved.read("active_events.jsonl")
            assert event["payload"]["interval_id"].encode() in saved.read("active_events.jsonl")


@pytest.mark.parametrize("label", ["America/Chicago", "UTC", "UTC-05:00", "CDT", "Unknown/Timezone"])
def test_timezone_is_offline_metadata_and_preparation_never_constructs_service(setup, monkeypatch, label):
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    s.local_tz_name = label
    from test_polr_confirmation_replay import forbid_timezone_lookup_and_network
    lookups = forbid_timezone_lookup_and_network(monkeypatch)
    monkeypatch.setattr(TaskTimerService, "__init__", forbidden)
    event = candidate(s, a, old)
    assert event["local_timezone"] == label
    s.register_prepared_timed_interval_correction(event)
    assert lookups == []


@pytest.mark.parametrize("label", [None, True, 12, "", " ", " UTC", "UTC ", "UTC\n", "UTC\u0080", "\ud800"])
def test_malformed_timezone_metadata_rejects_without_writes(setup, monkeypatch, label):
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    s.local_tz_name = label
    before = capture(s)
    monkeypatch.setattr(s, "_create_risky_operation_backup", forbidden)
    with pytest.raises(ValueError): candidate(s, a, old)
    assert capture(s) == before


def test_inspection_failure_after_complete_append_never_installs_or_reappends(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    event = candidate(s, a, seed(s, a))
    before, append = capture(s), s.storage.append_event
    with monkeypatch.context() as m:
        def append_then_lost_inspection(value):
            append(value)
            m.setattr(s.storage, "iter_all_events", fail)
        m.setattr(s.storage, "append_event", append_then_lost_inspection)
        with pytest.raises(OSError) as caught: s.register_prepared_timed_interval_correction(event)
        assert "uncertain" in " ".join(caught.value.__notes__)
        assert s.state == before[0] and s.events == before[1]
    monkeypatch.setattr(s.storage, "append_event", forbidden)
    assert_registered(s, event, s.register_prepared_timed_interval_correction(event))


def test_older_closed_correction_preserves_same_task_running_work_and_legacy_markers(setup, tmp_path, monkeypatch):
    s, a, b, _, _, _ = setup
    old = seed(s, a)
    dated(s, a, TUE, 123.456)
    timed(s, b, MON, 900)
    s.reset_task(a)
    s.create_time_submission_marker([a], None, CUTOFF, "Legacy marker", None)
    legacy_file = tmp_path / "legacy.txt"
    s.export_report(legacy_file, reset_after=False)
    s.start_task(a)
    before = deepcopy(s.state)
    submissions, checkpoint, frozen = s.list_time_submissions(), s.find_active_export_checkpoint(), legacy_file.read_bytes()
    with monkeypatch.context() as m:
        m.setattr(s, "find_last_export_checkpoint_utc", forbidden)
        m.setattr(s, "find_submission_overlaps", forbidden)
        m.setattr(s.storage, "synchronize_journal", forbidden)  # ordinary append already flushes
        event = candidate(s, a, old)
        result = s.register_prepared_timed_interval_correction(event)
    expected = deepcopy(before)
    expected.tasks[a].intervals[old] = deepcopy(s.state.tasks[a].intervals[old])
    expected.tasks[a].intervals[result["replacement_interval_id"]] = deepcopy(s.state.tasks[a].intervals[result["replacement_interval_id"]])
    assert s.state == expected
    assert s.state.tasks[a].is_running and s.state.running_task_id == a
    # Fresh strict reads add physical read metadata, not persisted checkpoint fields.
    current_checkpoint = {key: value for key, value in s.find_active_export_checkpoint().items() if key != "_read_sequence"}
    assert (s.list_time_submissions(), current_checkpoint, legacy_file.read_bytes()) == (submissions, checkpoint, frozen)
    assert_registered(s, event, result)


def test_locally_unrepresentable_changed_endpoint_is_value_error_without_writes(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    old = seed(s, a)
    before = capture(s)
    monkeypatch.setattr(s, "_create_risky_operation_backup", forbidden)
    with pytest.raises(ValueError, match="representable locally"):
        s.prepare_timed_interval_correction(a, old, start_utc=datetime.min.replace(tzinfo=timezone.utc))
    assert capture(s) == before


@pytest.mark.parametrize("day", [MON, date(2026, 3, 8), date(2026, 11, 1)])
def test_midnight_dst_history_accounting_restart_rebuild_restore(setup, monkeypatch, day):
    s, a, _, _, _, clock = setup
    first, last = local(s, day - timedelta(days=1), 20), local(s, day, 8)
    s.add_manual_interval(a, first, last, "Across dates")
    old = next(reversed(s.state.tasks[a].intervals))
    event = s.prepare_timed_interval_correction(a, old, stop_utc=local(s, day, 9))
    s.register_prepared_timed_interval_correction(event)
    expected = deepcopy(s.state)
    rows = s.get_task_work_history(a, cutoff_utc=CUTOFF)
    report = s.calculate_date_window(day - timedelta(days=1), day, cutoff_utc=CUTOFF, all_tasks=True)
    assert sum(row["duration_seconds"] for row in rows) == (local(s, day, 9).astimezone(timezone.utc) - first.astimezone(timezone.utc)).total_seconds()
    for work_date, seconds in report["tasks"][a]["daily_seconds"].items():
        assert sum(row["duration_seconds"] for row in rows if row["work_date"] == work_date) == seconds
    s.storage.max_active_events = 1
    s.storage.rotate_if_needed()
    monkeypatch.setattr("task_timer.backups.utc_now", lambda: clock[0])
    backup = s.create_backup_now("Corrected work")
    restarted = TaskTimerService(EventStorage(s.storage.data_dir))
    assert restarted.state == expected
    restarted.rebuild_snapshot_from_journal()
    assert restarted.state == expected
    clock[0] += timedelta(hours=1)
    restarted.delete_interval(a, event["payload"]["new_interval_id"], "Later deletion")
    restarted.restore_from_backup(backup)
    final = TaskTimerService(EventStorage(s.storage.data_dir))
    assert final.state == expected and final.get_task_work_history(a, cutoff_utc=CUTOFF) == rows
    assert_registered(final, event, final.register_prepared_timed_interval_correction(event))


def test_authoritative_reader_is_detached_pure_and_includes_known_deleted_tasks(setup, monkeypatch):
    s, a, _, _, _, _ = setup
    seed(s, a, fractional=True)
    stale = deepcopy(s.state)
    other = TaskTimerService(EventStorage(s.storage.data_dir))
    other.update_task(a, 'Authoritative name', '')
    other.delete_task(a)
    before = capture(s)
    monkeypatch.setattr(TaskTimerService, '__init__', forbidden)
    monkeypatch.setattr(app_module, 'utc_now', forbidden)
    for name in ('append_event', 'save_snapshot', 'synchronize_journal'):
        monkeypatch.setattr(s.storage, name, forbidden)
    monkeypatch.setattr(s, '_create_risky_operation_backup', forbidden)
    task = s.read_task_for_timed_interval_correction(a)
    assert task.is_deleted and task.name == 'Authoritative name' and s.state == stale
    task.name = 'Caller mutation'
    task.intervals.clear()
    fresh = s.read_task_for_timed_interval_correction(a)
    assert fresh.name == 'Authoritative name' and fresh.intervals
    assert capture(s) == before


@pytest.mark.parametrize('fault', ['project', 'unknown', 'type', 'active', 'manifest', 'incomplete'])
def test_authoritative_reader_rejects_missing_owners_or_uncertain_journal_without_mutation(setup, fault):
    s, a, _, p, _, _ = setup
    owner = a
    if fault == 'project': owner = p
    elif fault == 'unknown': owner = str(uuid4())
    elif fault == 'type': owner = None
    elif fault == 'active': s.storage.active_path.unlink()
    elif fault == 'manifest': s.storage.manifest_path.unlink()
    else:
        with s.storage.active_path.open('a', encoding='utf-8') as handle: handle.write('{')
    before = capture(s)
    with pytest.raises((ValueError, OSError)): s.read_task_for_timed_interval_correction(owner)
    assert capture(s) == before
