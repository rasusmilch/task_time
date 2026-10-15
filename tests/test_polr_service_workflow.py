"""Connected staged services on disposable data; no production workflow qualification."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from itertools import count

import pytest

from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage
from test_mixed_accounting import dated, files, MON, TUE, CUTOFF
from test_polr_confirmation_replay import cell, journal


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    now = datetime(2026, 10, 20, 14, tzinfo=timezone.utc)
    backup_ticks = count()
    monkeypatch.setattr("task_timer.app.utc_now", lambda: now)
    monkeypatch.setattr("task_timer.app.detect_local_timezone", lambda: timezone.utc)
    # Includes startup/safety/rebuild backups, each with its own timestamp.
    monkeypatch.setattr("task_timer.backups.utc_now", lambda: now + timedelta(seconds=next(backup_ticks)))
    service = TaskTimerService(EventStorage(tmp_path / "dataset"))
    a = service.create_task("A", "")
    b = service.create_task("B", "")
    entry = dated(service, a, MON, 10800)
    dated(service, b, MON, 3600)
    service.start_task(b)  # Outside the reporting window; must survive evidence operations.
    return service, a, b, entry


def work_state(service):
    return (deepcopy(service.state), service.snapshot_dict(), service.list_time_submissions(),
            service.find_active_export_checkpoint(),
            service.calculate_date_window(MON, TUE, cutoff_utc=CUTOFF, all_tasks=True))


def capture(service):
    return (work_state(service), deepcopy(service.events), journal(service), files(service),
            service.list_timesheet_export_snapshots(), service.get_effective_polr_confirmations())


def observe(service, operation):
    before = capture(service)
    try:
        return operation()
    finally:
        assert capture(service) == before


def register(service, event):
    """Exercise the public writer; only a new identity may append one frozen event."""
    original, before, work = deepcopy(event), journal(service), work_state(service)
    def nonjournal():
        return {name: data for name, data in files(service).items()
                if name not in {"active_events.jsonl", "log_manifest.json"}
                and not name.startswith("archives/")}
    surviving = nonjournal()
    if event["event_type"] == "timesheet_export_snapshot_created":
        identity = service.register_prepared_timesheet_export(event)
    else:
        assert event["event_type"] == "polr_confirmation_batch_recorded"
        identity = service.register_prepared_polr_confirmation_batch(event)
    assert identity == event["event_id"] and event == original
    expected = before if any(e["event_id"] == identity for e in before) else [*before, original]
    assert journal(service) == expected
    assert sum(e["event_id"] == identity for e in journal(service)) == 1
    assert work_state(service) == work and nonjournal() == surviving


def materialize(service, event, destination):
    assert not destination.is_relative_to(service.storage.data_dir)
    expected = event["payload"]["report_text"].encode("utf-8")
    assert observe(service, lambda: service.materialize_timesheet_export(event["event_id"], destination)) == destination
    assert destination.read_bytes() == expected
    assert sha256(destination.read_bytes()).hexdigest() == event["payload"]["report_sha256"]
    return expected


def initial_export(service, a, b, destination):
    event = observe(service, lambda: service.prepare_timesheet_export_snapshot(
        MON, TUE, cutoff_utc=CUTOFF, all_tasks=True, preferred_destination=str(destination)))
    frozen = deepcopy(event)
    register(service, event)
    content = materialize(service, event, destination)
    assert {(task["task_id"], day["work_date"]): (day["actual_seconds"], day["decimal_hundredths"])
            for task in event["payload"]["tasks"] for day in task["daily"]} == {
                (a, str(MON)): (10800, 300), (a, str(TUE)): (0, 0),
                (b, str(MON)): (3600, 100), (b, str(TUE)): (0, 0)}
    assert service.get_effective_polr_confirmations() == {}
    assert event == frozen
    return event, content


def reconciliation(service):
    return observe(service, lambda: service.calculate_polr_reconciliation(
        MON, TUE, cutoff_utc=CUTOFF, all_tasks=True))


def expected(actual, confirmed=None, identity=None, *, delta=None):
    return {"actual_hundredths": actual, "confirmed_hundredths": confirmed,
            "delta_hundredths": delta,
            "enter_hundredths": actual, "batch_event_id": identity}


def rows(proposal):
    return {(row["task_id"], row["work_date"]): row for row in proposal["cells"]}


def test_default_export_confirmation_absolute_replacement_and_replay(workflow, tmp_path):
    service, a, b, _ = workflow
    target = tmp_path / "original.txt"
    export, content = initial_export(service, a, b, target)
    original_export = deepcopy(export)
    unknown = reconciliation(service)
    unknown_copy = deepcopy(unknown)
    assert unknown["cells"] == {(a, str(MON)): expected(300), (b, str(MON)): expected(100),
                                (a, str(TUE)): expected(0), (b, str(TUE)): expected(0)}

    dated(service, a, MON, 7200)
    proposal = observe(service, lambda: service.propose_export_polr_confirmation(export["event_id"]))
    original_proposal = deepcopy(proposal)
    assert {key: row["proposed_hundredths"] for key, row in rows(proposal).items()} == {
        (a, str(MON)): 300, (b, str(MON)): 100, (a, str(TUE)): 0, (b, str(TUE)): 0}
    first = observe(service, lambda: service.prepare_export_polr_confirmation_batch(proposal))
    original_first = deepcopy(first)
    assert first["payload"]["cells"] == sorted(
        [cell(a, 300, source=export["event_id"]), cell(b, 100, source=export["event_id"])],
        key=lambda item: (item["task_id"], item["work_date"]))
    assert service.get_effective_polr_confirmations() == {}
    register(service, first)
    partial = reconciliation(service)
    partial_copy = deepcopy(partial)
    assert partial["cells"] == {
        (a, str(MON)): expected(500, 300, first["event_id"], delta=200),
        (b, str(MON)): expected(100, 100, first["event_id"], delta=0),
        (a, str(TUE)): expected(0), (b, str(TUE)): expected(0)}
    assert partial["actual"]["tasks"][a]["daily_seconds"][MON] == 18000

    manual_cells = [cell(a, 500, prior=first["event_id"])]
    original_cells = deepcopy(manual_cells)
    latest = observe(service, lambda: service.prepare_polr_confirmation_batch(manual_cells))
    original_latest = deepcopy(latest)
    assert latest["payload"]["cells"] == original_cells
    register(service, latest)
    final = reconciliation(service)
    final_copy = deepcopy(final)
    assert final["cells"] == partial["cells"] | {(a, str(MON)): expected(500, 500, latest["event_id"], delta=0)}
    assert manual_cells == original_cells

    physical = journal(service)
    work = work_state(service)
    service.storage.max_active_events = 1
    service.storage.rotate_if_needed()
    assert service.storage.load_manifest()["archives"]
    service = TaskTimerService(EventStorage(service.storage.data_dir))
    assert journal(service) == physical and work_state(service) == work
    assert reconciliation(service) == final
    assert service.state.tasks[b].is_running

    stale = observe(service, lambda: service.propose_export_polr_confirmation(export["event_id"]))
    stale_copy = deepcopy(stale)
    old_a = rows(stale)[a, str(MON)]
    assert (old_a["proposed_hundredths"], old_a["prior_confirmed_hundredths"],
            old_a["expected_prior_confirmation_id"], old_a["requires_stale_acknowledgement"]) == (
                300, 500, latest["event_id"], True)
    with pytest.raises(ValueError, match="Acknowledgements"):
        observe(service, lambda: service.prepare_export_polr_confirmation_batch(stale))
    assert stale == stale_copy

    before_retry = capture(service)
    register(service, export)
    register(service, first)
    assert capture(service) == before_retry and reconciliation(service) == final
    assert service.get_timesheet_export_snapshot(export["event_id"]) == original_export
    assert journal(service) == physical  # Earlier export and batches remain unchanged.
    assert export == original_export and first == original_first and proposal == original_proposal
    assert latest == original_latest and manual_cells == original_cells
    assert unknown == unknown_copy and partial == partial_copy and final == final_copy
    assert target.read_bytes() == content


def test_checked_zero_and_corrected_actual_survive_backup_restore(workflow, tmp_path):
    service, a, b, entry = workflow
    target = tmp_path / "checked.txt"
    export, content = initial_export(service, a, b, target)
    original_export = deepcopy(export)
    proposal = observe(service, lambda: service.propose_export_polr_confirmation(export["event_id"]))
    original_proposal = deepcopy(proposal)
    selected = [(a, str(MON)), (b, str(TUE))]
    first = observe(service, lambda: service.prepare_export_polr_confirmation_batch(
        proposal, selected_cells=selected))
    original_first = deepcopy(first)
    assert first["payload"]["cells"] == sorted(
        [cell(a, 300, source=export["event_id"]), cell(b, 0, day=TUE, source=export["event_id"])],
        key=lambda item: (item["task_id"], item["work_date"]))
    register(service, first)
    initial = reconciliation(service)
    initial_copy = deepcopy(initial)
    assert initial["cells"] == {
        (a, str(MON)): expected(300, 300, first["event_id"], delta=0),
        (b, str(MON)): expected(100), (a, str(TUE)): expected(0),
        (b, str(TUE)): expected(0, 0, first["event_id"], delta=0)}

    dated(service, a, MON, 9000, entry, "dated_duration_corrected")
    corrected = reconciliation(service)
    corrected_copy = deepcopy(corrected)
    assert corrected["cells"] == initial["cells"] | {(a, str(MON)): expected(250, 300, first["event_id"], delta=-50)}
    assert corrected["actual"]["tasks"][a]["daily_seconds"][MON] == 9000
    assert service.get_timesheet_export_snapshot(export["event_id"]) == original_export
    assert target.read_bytes() == content

    corrected_work = work_state(service)
    physical = journal(service)
    service.storage.max_active_events = 1
    service.storage.rotate_if_needed()
    assert service.storage.load_manifest()["archives"]
    backup = service.create_backup_now()
    backup_bytes = backup.read_bytes()
    dated(service, a, MON, 14400, entry, "dated_duration_corrected")
    later = observe(service, lambda: service.prepare_polr_confirmation_batch([
        cell(a, 400, prior=first["event_id"])]))
    register(service, later)
    changed = reconciliation(service)
    changed_copy = deepcopy(changed)
    assert changed["cells"][a, str(MON)] == expected(400, 400, later["event_id"], delta=0)
    assert changed["actual"]["tasks"][a]["daily_seconds"][MON] == 14400
    post_backup_ids = {event["event_id"] for event in journal(service)} - {event["event_id"] for event in physical}
    assert len(post_backup_ids) == 2 and later["event_id"] in post_backup_ids

    service.restore_from_backup(backup)
    assert backup.read_bytes() == backup_bytes
    service = TaskTimerService(EventStorage(service.storage.data_dir))
    service.rebuild_snapshot_from_journal()
    restored = reconciliation(service)
    assert restored == corrected and journal(service) == physical
    assert work_state(service) == corrected_work
    assert not post_backup_ids & {event["event_id"] for event in journal(service)}
    assert service.get_effective_polr_confirmations() == {
        (a, str(MON)): {"confirmed_hundredths": 300, "batch_event_id": first["event_id"]},
        (b, str(TUE)): {"confirmed_hundredths": 0, "batch_event_id": first["event_id"]}}
    assert service.state.tasks[b].is_running
    assert service.list_time_submissions() == [] and service.find_active_export_checkpoint() is None

    reopened = observe(service, lambda: service.propose_export_polr_confirmation(export["event_id"]))
    old_a = rows(reopened)[a, str(MON)]
    assert (old_a["proposed_hundredths"], old_a["prior_confirmed_hundredths"],
            old_a["expected_prior_confirmation_id"], old_a["requires_stale_acknowledgement"]) == (
                300, 300, first["event_id"], False)
    prepared = observe(service, lambda: service.prepare_export_polr_confirmation_batch(
        reopened, selected_cells=[(a, str(MON))]))
    assert prepared["payload"]["cells"] == [cell(a, 300, source=export["event_id"], prior=first["event_id"])]
    assert all(event["event_id"] != prepared["event_id"] for event in journal(service))
    second_target = tmp_path / "restored.txt"
    assert materialize(service, export, second_target) == content
    assert second_target.read_bytes() == target.read_bytes() == content
    assert service.get_timesheet_export_snapshot(export["event_id"]) == original_export
    assert export == original_export and first == original_first and proposal == original_proposal
    assert initial == initial_copy and corrected == corrected_copy and changed == changed_copy
    assert selected == [(a, str(MON)), (b, str(TUE))]
