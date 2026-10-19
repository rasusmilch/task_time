import sqlite3

import pytest

from chronicle.sqlite_store import DATABASE, SQLiteStore, runtime_info
from conftest import NOW, uid


def test_fresh_profile_and_reopen(store):
    c = store.connection
    assert c.isolation_level is None
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert c.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    dataset = store.dataset_id
    directory = store.directory
    store.close()
    reopened = SQLiteStore(directory)
    try:
        assert reopened.dataset_id == dataset
        assert reopened.timezone == "America/Chicago"
    finally:
        reopened.close()


@pytest.mark.parametrize("name", ["active_events.jsonl", DATABASE, ".chronicle.lock", "other"])
def test_unknown_or_partial_create_is_refused_without_changes(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"original")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError):
        SQLiteStore(tmp_path, create=True, timezone="America/Chicago")
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_noncreating_open_and_invalid_zone(tmp_path):
    with pytest.raises(ValueError):
        SQLiteStore(tmp_path)
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        SQLiteStore(tmp_path, create=True, timezone="../bad")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("version,expected", [((3, 36, 0), "STRICT"), ((3, 51, 2), "WAL-reset"), ((3, 52, 0), "WAL-reset")])
def test_runtime_floor_and_withdrawn_release(monkeypatch, version, expected):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", version)
    with pytest.raises(RuntimeError, match=expected):
        runtime_info()


def test_direct_strict_check_unique_fk_guards(store, task, service):
    c = store.connection
    for statement, args in [
        ("UPDATE tasks SET version='wrong' WHERE task_id=?", (task,)),
        ("UPDATE tasks SET is_deleted=2 WHERE task_id=?", (task,)),
        ("UPDATE tasks SET created_utc_us=? WHERE task_id=?", (2**63 - 1, task)),
        ("UPDATE tasks SET project_id=? WHERE task_id=?", (uid(), task)),
        ("INSERT INTO tasks SELECT * FROM tasks", ()),
        ("INSERT INTO tasks VALUES('bad',NULL,'Invalid',1,0,0,0)", ()),
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(statement, args)
    entry = uid()
    service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=NOW)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO active_timer VALUES(2,?,?,?,1)", (uid(), task, NOW))
    with pytest.raises(sqlite3.IntegrityError, match="still active"):
        c.execute("UPDATE work_entries SET current_revision=1 WHERE entry_id=?", (entry,))
    service.stop_timer(entry, expected_version=1, request_id=uid(), action_utc_us=NOW + 1)
    with pytest.raises(sqlite3.IntegrityError, match="already closed"):
        c.execute("INSERT INTO active_timer VALUES(1,?,?,?,1)", (entry, task, NOW))
    for table in ("work_revisions", "committed_requests"):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            c.execute(f"DELETE FROM {table}")


def test_final_orphan_postcondition_rolls_back(store, make_request, task):
    frozen = make_request("test_orphan")
    def bad(c):
        c.execute("INSERT INTO work_entries VALUES(?,?,'timed',?,NULL,?)", (uid(), task, NOW, frozen.request_id))
        return {"unexpected": True}
    outcome = store.transact(frozen, bad)
    assert outcome.status == "rejected"
    probe = store._probe()
    try:
        assert list(probe.execute("SELECT * FROM work_entries")) == []
    finally:
        probe.close()
    assert store.reconcile(frozen).status == "absent"


def test_incomplete_guards_and_future_version_refused(store):
    path = store.directory
    store.connection.execute("PRAGMA user_version=999")
    store.close()
    with pytest.raises(ValueError, match="schema"):
        SQLiteStore(path)


def test_timezone_conflict_refused(store):
    path = store.directory
    store.close()
    with pytest.raises(ValueError, match="conflicts"):
        SQLiteStore(path, timezone="UTC")


def test_unknown_normal_open_does_not_add_files(tmp_path):
    (tmp_path / DATABASE).write_bytes(b"not a SQLite database")
    with pytest.raises(sqlite3.DatabaseError):
        SQLiteStore(tmp_path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == {DATABASE: b"not a SQLite database"}


def test_both_active_closed_and_orphan_direct_sql_are_refused_on_open(store, service, task):
    directory = store.directory
    entry = uid()
    service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=NOW)
    # A raw deletion cannot make a valid final service transaction or valid reopen state.
    store.connection.execute("DELETE FROM active_timer")
    store.close()
    with pytest.raises(ValueError, match="lifecycle"):
        SQLiteStore(directory)
