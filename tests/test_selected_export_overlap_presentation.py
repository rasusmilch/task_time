"""Selected-export warning presentation over real submission intersections."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from task_timer import app as app_module
from test_history_session_direction import owner_factory
from test_mixed_accounting import setup, files
from test_reset_ui_removal import running, export_owner, evidence, assert_preserved


ZONES = [
    pytest.param(ZoneInfo("America/Chicago"), "2026-10-12 09:30 AM", "2026-10-20 11:45 AM", id="chicago"),
    pytest.param(timezone(-timedelta(hours=3, minutes=30)), "2026-10-12 11:00 AM", "2026-10-20 01:15 PM", id="negative-offset"),
    pytest.param(timezone.utc, "2026-10-12 02:30 PM", "2026-10-20 04:45 PM", id="utc"),
    pytest.param(timezone(timedelta(hours=5, minutes=30)), "2026-10-12 08:00 PM", "2026-10-20 10:15 PM", id="positive-offset"),
]
FINITE_START = datetime(2026, 10, 12, 14, 30, tzinfo=timezone.utc)
MARKER_END = datetime(2026, 10, 20, 16, 45, tzinfo=timezone.utc)


def exercise_export(running, export_owner, monkeypatch, tmp_path, *, zone,
                    marker_start, request_start, expected_start, expected_end, proceed):
    """Replace only UI decisions; calculate, export, back up and mark for real."""
    service, task_id, _, clock = running
    owner, refreshes = export_owner
    service.local_tz = zone
    service.local_tz_name = str(zone)
    reason = "Earlier reviewed entry"
    submission_id = service.create_time_submission_marker(
        [task_id], marker_start, MARKER_END, reason, None)
    earlier_submissions = deepcopy(service.list_time_submissions())
    overlaps = deepcopy(service.find_submission_overlaps([task_id], request_start, clock[0]))
    assert overlaps == [{
        "task_id": task_id, "task_name": "A", "existing_submission_id": submission_id,
        "overlap_start_utc": max(value for value in (marker_start, request_start,
                                                     datetime.min.replace(tzinfo=timezone.utc)) if value is not None),
        "overlap_end_utc": MARKER_END, "existing_reason": reason,
    }]
    monkeypatch.setattr(app_module, "SelectedTaskExportDialog", lambda *args: SimpleNamespace(
        result=SimpleNamespace(task_ids=[task_id], window_start_utc=request_start,
                               window_end_utc=clock[0], mark_submitted=True,
                               reason="New reviewed entry")))
    prompts, ui_calls = [], []

    def acknowledge(title, message):
        prompts.append((title, message))
        return proceed

    def forbidden(*args, **kwargs):
        pytest.fail("Declining overlap acknowledgement reached export or completion")

    target = tmp_path / "selected.txt"  # Outside the disposable dataset.

    def choose_file(**kwargs):
        assert len(prompts) == 1
        ui_calls.append("file")
        return str(target)

    def complete(parent):
        assert target.is_file() and len(service.list_time_submissions()) == 2
        ui_calls.append("leave")
        return SimpleNamespace(choice="leave")

    monkeypatch.setattr(app_module.messagebox, "askyesno", acknowledge)
    monkeypatch.setattr(app_module.filedialog, "asksaveasfilename", choose_file if proceed else forbidden)
    monkeypatch.setattr(app_module, "PostSelectedExportActionDialog", complete if proceed else forbidden)
    monkeypatch.setattr(app_module.messagebox, "showinfo",
                        (lambda *args: ui_calls.append(args)) if proceed else forbidden)
    if not proceed:
        monkeypatch.setattr(service, "export_selected_tasks_report", forbidden)
        monkeypatch.setattr(service.backups, "create_safety_backup", forbidden)

    before = evidence(service)
    dataset_before = files(service)
    assert owner.export_selected_tasks() is proceed
    assert prompts == [("Possible duplicate Epicor entry",
                        "Some selected time may already have been entered in Epicor.\n\nOverlaps:\n"
                        f"- A: {expected_start} to {expected_end} "
                        f"(submission {submission_id}, reason: {reason})"
                        "\n\nContinue and Mark Anyway?")]
    added = assert_preserved(service, before, ["time_submission_created"] if proceed else [])
    # The warning must neither change the intersection dictionaries nor earlier evidence.
    assert service.find_submission_overlaps([task_id], request_start, clock[0])[:1] == overlaps
    assert service.list_time_submissions()[:1] == earlier_submissions
    assert refreshes == [] and not owner.ui_settings_store.path.exists()
    if proceed:
        assert ui_calls == ["file", "leave", ("Export Selected Tasks", "Selected-task export complete.")]
        marker = service.list_time_submissions()[1]
        assert marker.submission_id != submission_id and marker.task_ids == {task_id}
        assert marker.window_start_utc == request_start and marker.window_end_utc == clock[0]
        assert marker.reason == "New reviewed entry" and marker.export_path == str(target)
        assert added[0]["payload"]["submission_id"] == marker.submission_id
        assert "A" in target.read_text(encoding="utf-8")
        assert {entry.reason for entry in service.list_managed_backups()} == {"safety: before selected export"}
    else:
        assert ui_calls == [] and not target.exists()
        assert files(service) == dataset_before


@pytest.mark.parametrize("zone,finite_text,end_text", ZONES)
@pytest.mark.parametrize("proceed", [False, True], ids=["cancel", "continue"])
def test_unbounded_overlap_warning_through_export_handler(
        running, export_owner, monkeypatch, tmp_path, zone, finite_text, end_text, proceed):
    exercise_export(running, export_owner, monkeypatch, tmp_path, zone=zone,
                    marker_start=None, request_start=None,
                    expected_start="Beginning of recorded history", expected_end=end_text, proceed=proceed)


@pytest.mark.parametrize("zone,finite_text,end_text", ZONES)
@pytest.mark.parametrize("marker_start,request_start", [
    pytest.param(None, FINITE_START, id="unbounded-submission"),
    pytest.param(FINITE_START, None, id="unbounded-request"),
    pytest.param(FINITE_START - timedelta(minutes=30), FINITE_START, id="finite-intersection"),
])
def test_finite_intersection_keeps_local_minute_format(
        running, export_owner, monkeypatch, tmp_path, zone, finite_text, end_text, marker_start, request_start):
    exercise_export(running, export_owner, monkeypatch, tmp_path, zone=zone,
                    marker_start=marker_start, request_start=request_start,
                    expected_start=finite_text, expected_end=end_text, proceed=False)
