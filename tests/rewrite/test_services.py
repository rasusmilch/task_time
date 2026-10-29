from dataclasses import replace
from datetime import datetime, timezone
import sqlite3

import pytest

from chronicle.records import Request, canonical
from chronicle.timekeeping import to_us
from conftest import archive, NOW, uid


def start(service, task, now=NOW):
    entry = uid()
    assert service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=now).status == "committed"
    return entry


def test_project_duplicate_names_independent_membership(service, task, store):
    p, second = uid(), uid()
    assert service.create_project(p, "Example", request_id=uid(), action_utc_us=NOW).status == "committed"
    assert service.create_task(second, "Example", p, expected_project_version=1, request_id=uid(), action_utc_us=NOW).status == "committed"
    assert service.assign_task_to_project(task, p, expected_version=1, request_id=uid(), action_utc_us=NOW).status == "committed"
    assert service.rename_project(p, "Renamed", expected_version=1, request_id=uid(), action_utc_us=NOW).status == "committed"
    assert service.rename_task(second, "Renamed", expected_version=1, request_id=uid(), action_utc_us=NOW).status == "committed"
    assert service.assign_task_to_project(task, None, expected_version=2, request_id=uid(), action_utc_us=NOW).status == "committed"
    assert len(service.read_current_state(cutoff_utc_us=NOW)["tasks"]) == 2
    assert service.rename_task(task, "Example", expected_version=3, request_id=uid(), action_utc_us=NOW).status == "unchanged"
    assert store.connection.execute("SELECT count(*) FROM committed_requests").fetchone()[0] == 7


def test_exact_reuse_before_stale_check_and_collision(service, task, make_request):
    frozen = make_request("start_timer", task_id=task, entry_id=uid(), expected_task_version=1)
    original = service.execute(frozen)
    entry = original.result["entry_id"]
    service.stop_timer(entry, expected_version=1, request_id=uid(), action_utc_us=NOW + 5)
    service.rename_task(task, "New", expected_version=1, request_id=uid(), action_utc_us=NOW + 8)
    assert service.execute(frozen).result == original.result
    collision = replace(frozen, action_utc_us=NOW + 1)
    assert service.execute(collision).status == "rejected"
    assert service.read_current_state(cutoff_utc_us=NOW + 9)["active"] is None
    assert service.reconcile_request(frozen).result == original.result


def test_atomic_switch_and_bad_new_identity_roll_back(service, task, store):
    second = uid()
    service.create_task(second, "Second", request_id=uid(), action_utc_us=NOW)
    first = start(service, task)
    # Failure occurs after old close, when the new work identity collides.
    failed = service.switch_timer(first, second, first, expected_active_version=1, expected_task_version=1,
                                 request_id=uid(), action_utc_us=NOW + 100)
    assert failed.status == "rolled_back"
    view = service.read_current_state(cutoff_utc_us=NOW + 100)
    assert view["active"]["entry_id"] == first
    assert store.connection.execute("SELECT count(*) FROM work_revisions").fetchone()[0] == 0
    new = uid()
    assert service.switch_timer(first, second, new, expected_active_version=1, expected_task_version=1,
                                request_id=uid(), action_utc_us=NOW + 100).status == "committed"
    row = store.connection.execute("SELECT * FROM work_revisions").fetchone()
    active = store.connection.execute("SELECT * FROM active_timer").fetchone()
    assert row["stop_utc_us"] == active["start_utc_us"] == NOW + 100
    assert row["entry_id"] == first and active["entry_id"] == new


@pytest.mark.parametrize("offset", [0, -1, -10**12])
def test_nonpositive_stop_switch_reject_without_work(service, task, store, offset):
    entry = start(service, task)
    assert service.stop_timer(entry, expected_version=1, request_id=uid(), action_utc_us=NOW + offset).status == "rejected"
    assert service.read_current_state(cutoff_utc_us=NOW)["active"]["entry_id"] == entry


@pytest.mark.parametrize("bad", [True, 1.0, float("nan"), "1", None])
def test_invalid_integer_inputs(service, task, bad):
    if type(bad) is float:
        with pytest.raises(ValueError, match="no floats"):
            service.start_timer(task, uid(), expected_task_version=bad, request_id=uid(), action_utc_us=NOW)
        return
    outcome = service.start_timer(task, uid(), expected_task_version=bad, request_id=uid(), action_utc_us=NOW)
    assert outcome.status == "rejected"


def test_bad_id_owner_deleted_task_and_stale_version(service, task, store):
    for target in ("bad", uid()):
        assert service.start_timer(target, uid(), expected_task_version=1, request_id=uid(), action_utc_us=NOW).status == "rejected"
    assert service.start_timer(task, uid(), expected_task_version=2, request_id=uid(), action_utc_us=NOW).status == "rejected"
    store._recover_connection()
    archive(service, 'task', task, now=0)
    assert service.start_timer(task, uid(), expected_task_version=2, request_id=uid(), action_utc_us=NOW).status == "rejected"


def test_active_start_audit_precision_noop_stale_and_stop(service, task, store):
    original = NOW + 123456
    entry = start(service, task, original)
    before = store.connection.execute("SELECT count(*) FROM committed_requests").fetchone()[0]
    assert service.correct_active_start(entry, "2026-10-19", "10am", expected_version=1,
                                        request_id=uid(), action_utc_us=NOW + 60_000_000).status == "unchanged"
    assert store.connection.execute("SELECT count(*) FROM committed_requests").fetchone()[0] == before
    result = service.correct_active_start(entry, "2026-10-19", "9am", expected_version=1, comment="  actual start  ",
                                          request_id=uid(), action_utc_us=NOW + 60_000_000)
    assert result.status == "committed"
    row = store.connection.execute("SELECT * FROM active_start_corrections").fetchone()
    assert row["prior_start_utc_us"] == original
    assert row["comment"] == "actual start"
    assert store.connection.execute("SELECT original_start_utc_us FROM work_entries").fetchone()[0] == original
    assert service.correct_active_start(entry, "2026-10-19", "8am", expected_version=1,
                                        request_id=uid(), action_utc_us=NOW).status == "rejected"
    assert service.stop_timer(entry, expected_version=2, request_id=uid(), action_utc_us=NOW).status == "committed"
    closed = store.connection.execute("SELECT * FROM work_revisions").fetchone()
    assert closed["entry_id"] == entry and closed["start_utc_us"] == row["corrected_start_utc_us"]
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute("DELETE FROM active_start_corrections")


class FaultConnection:
    def __init__(self, connection, *, after=False, rollback=False, close=False):
        self.inner, self.after, self.rollback, self.close_fault = connection, after, rollback, close
    def __getattr__(self, name):
        return getattr(self.inner, name)
    def execute(self, statement, *args):
        if statement == "COMMIT":
            self.transaction_at_commit = self.inner.in_transaction
            self.receipts_at_commit = self.inner.execute("SELECT count(*) FROM committed_requests").fetchone()[0]
            if self.after:
                self.inner.execute(statement)
            raise sqlite3.OperationalError("commit acknowledgement fault")
        if statement == "ROLLBACK" and self.rollback:
            raise sqlite3.OperationalError("rollback fault")
        return self.inner.execute(statement, *args)
    def close(self):
        if self.close_fault:
            raise sqlite3.OperationalError("close fault")
        return self.inner.close()


@pytest.mark.parametrize("after,expected", [(False, "rolled_back"), (True, "committed")])
def test_commit_ack_with_open_transaction_is_not_own_receipt_evidence(service, store, task, make_request, after, expected):
    frozen = make_request("start_timer", task_id=task, entry_id=uid(), expected_task_version=1)
    poisoned = FaultConnection(store.connection, after=after)
    store.connection = poisoned
    result = service.execute(frozen)
    assert result.status == expected
    assert poisoned.transaction_at_commit and poisoned.receipts_at_commit == 2
    assert result.error is not None and "acknowledgement fault" in str(result.error)
    truth = service.reconcile_request(frozen)
    assert truth.status == ("committed" if after else "absent")
    assert store.connection is None
    assert service.execute(frozen).status == "committed"
    assert store.connection is not poisoned


def test_persistent_unreadable_reconcile_retains_exact_request(service, store, task, make_request, monkeypatch):
    frozen = make_request("start_timer", task_id=task, entry_id=uid(), expected_task_version=1)
    store.connection = FaultConnection(store.connection, after=True)
    original = store._probe
    def unavailable():
        raise sqlite3.OperationalError("storage unavailable")
    monkeypatch.setattr(store, "_probe", unavailable)
    result = service.execute(frozen)
    assert result.status == "unverified"
    assert "storage unavailable" in " ".join(result.error.__notes__)
    assert service.reconcile_request(frozen).status == "unverified"
    monkeypatch.setattr(store, "_probe", original)
    assert service.execute(frozen).status == "committed"
    assert store.connection.execute("SELECT count(*) FROM active_timer").fetchone()[0] == 1


def test_failed_rollback_close_preserves_diagnostics_and_no_poisoned_reuse(service, store, task, make_request):
    frozen = make_request("start_timer", task_id=task, entry_id=uid(), expected_task_version=1)
    poisoned = FaultConnection(store.connection, rollback=True, close=True)
    store.connection = poisoned
    result = service.execute(frozen)
    assert result.status == "unverified"
    assert "Rollback failed" in " ".join(result.error.__notes__)
    assert "close failed" in " ".join(result.error.__notes__)
    assert store.connection is None
    assert service.reconcile_request(frozen).status == "unverified"
    assert service.execute(frozen).status == "unverified"
    poisoned.close_fault = False
    poisoned.rollback = False
    assert service.execute(frozen).status == "committed"


def test_busy_transaction_is_bounded_and_does_not_begin(service, store, task):
    other = sqlite3.connect(store.path, isolation_level=None)
    other.execute("BEGIN IMMEDIATE")
    try:
        outcome = service.start_timer(task, uid(), expected_task_version=1, request_id=uid(), action_utc_us=NOW)
        assert outcome.status == "unavailable"
        assert not store.connection.in_transaction
    finally:
        other.execute("ROLLBACK")
        other.close()


def test_failed_begin_acknowledgement_cleans_open_transaction(service, store, task, make_request):
    class FailedBegin(FaultConnection):
        def execute(self, statement, *args):
            if statement == "BEGIN IMMEDIATE":
                self.inner.execute(statement)
                raise sqlite3.OperationalError("lost BEGIN acknowledgement")
            return self.inner.execute(statement, *args)
    frozen = make_request("start_timer", task_id=task, entry_id=uid(), expected_task_version=1)
    poisoned = FailedBegin(store.connection)
    store.connection = poisoned
    result = service.execute(frozen)
    assert result.status == "rolled_back"
    assert store.connection is None
    assert service.reconcile_request(frozen).status == "absent"
    assert service.execute(frozen).status == "committed"


def test_uncommitted_same_connection_receipt_never_proves_commit(service, store, make_request):
    frozen = make_request("create_project", project_id=uid(), name="Not committed")
    c = store.connection
    c.execute("BEGIN IMMEDIATE")
    c.execute("INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,'administrative',?,?,?)",
              (frozen.request_id, frozen.operation, frozen.content(), canonical({"not": "committed"}), NOW))
    assert store._receipt(c, frozen, frozen.content()) == {"not": "committed"}
    assert service.reconcile_request(frozen).status == "unverified"
    c.execute("ROLLBACK")
    assert service.reconcile_request(frozen).status == "absent"


def test_active_correction_gap_repeat_future_and_multiple_audits(service, task, store):
    entry = start(service, task, to_us(datetime(2026, 11, 1, 8, tzinfo=timezone.utc)))
    observation = to_us(datetime(2026, 11, 1, 10, tzinfo=timezone.utc))
    for day, clock, occurrence in (("2026-03-08", "02:30", None), ("2026-11-01", "01:30", None),
                                   ("2026-11-02", "01:30", None), ("2026-11-01", "01:30:01", "first")):
        assert service.correct_active_start(entry, day, clock, expected_version=1, occurrence=occurrence,
                                            request_id=uid(), action_utc_us=observation).status == "rejected"
    assert service.correct_active_start(entry, "2026-11-01", "01:30", expected_version=1, occurrence="second",
                                        request_id=uid(), action_utc_us=observation).status == "committed"
    assert service.correct_active_start(entry, "2026-11-01", "01:30", expected_version=2, occurrence="first",
                                        request_id=uid(), action_utc_us=observation).status == "committed"
    row = service.read_current_state(cutoff_utc_us=observation)["active"]
    assert row["version"] == 3
    audits = list(store.connection.execute("SELECT * FROM active_start_corrections ORDER BY version"))
    assert audits[1]["prior_start_utc_us"] == audits[0]["corrected_start_utc_us"]


def test_rollback_journal_commit_busy_cannot_publish_own_receipt(service, store, task, make_request):
    frozen = make_request("start_timer", task_id=task, entry_id=uid(), expected_task_version=1)
    # A real shared reader lets BEGIN IMMEDIATE/write proceed but blocks COMMIT.
    reader = store._probe()
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM tasks").fetchall()
    try:
        result = service.execute(frozen)
        assert result.status == "rolled_back"
        assert isinstance(result.error, sqlite3.OperationalError)
        assert "locked" in str(result.error)
        assert store.connection is None
        assert service.reconcile_request(frozen).status == "absent"
        assert not (store.directory / (store.path.name + "-journal")).exists()
    finally:
        reader.close()
    assert service.execute(frozen).status == "committed"
    assert service.execute(frozen).result == service.reconcile_request(frozen).result
    assert store.connection.execute("SELECT count(*) FROM active_timer").fetchone()[0] == 1


def test_reconciliation_probe_close_failure_retains_dataset_ownership(store,service,task,make_request,monkeypatch):
    from chronicle.dataset_lock import DatasetLock
    request=make_request('start_timer',task_id=task,entry_id=uid(),expected_task_version=1)
    assert service.execute(request).status=='committed'
    probe=store._probe();original=store._probe;blocked=[True]
    class Probe:
        def __getattr__(self,name):return getattr(probe,name)
        def close(self):
            if blocked[0]:raise OSError('probe ownership still uncertain')
            probe.close()
    monkeypatch.setattr(store,'_probe',lambda:Probe())
    try:
        assert store.reconcile(request).status=='unverified'
        with pytest.raises(OSError,match='probe ownership'):store.close()
        competitor=DatasetLock(store.directory)
        with pytest.raises(OSError):competitor.acquire()
    finally:
        blocked[0]=False;monkeypatch.setattr(store,'_probe',original)
        store.close()
    with pytest.raises(sqlite3.ProgrammingError):probe.execute('SELECT 1')
    competitor.acquire();competitor.close()
