import sqlite3

import pytest

from chronicle.sqlite_store import BUSY_MS, DATABASE, SQLiteStore, runtime_info
from conftest import NOW, uid


def test_ordinary_admission_reads_only_bounded_header_without_image_fingerprint(store, monkeypatch):
    import chronicle.sqlite_store as module
    from chronicle import backup_restore
    directory = store.directory
    store.close()
    original = module.os.read
    reads = []
    def observe(fd, count):
        reads.append(count)
        return original(fd, count)
    def forbidden(*a): pytest.fail('Ordinary startup used a full cold-image fingerprint')
    monkeypatch.setattr(backup_restore, '_fingerprint', forbidden)
    monkeypatch.setattr(module.os, 'read', observe)
    reopened = SQLiteStore(directory)
    try:
        assert reads and set(reads) == {100}
    finally:
        reopened.close()


@pytest.mark.parametrize('changed', ['wal', 'foreign'])
def test_startup_rechecks_candidate_after_ownership_before_adoption(store, monkeypatch, changed):
    from chronicle.dataset_lock import DatasetLock
    directory, path = store.directory, store.path
    store.close()
    lock_path = directory / '.chronicle.lock'
    lock_bytes = lock_path.read_bytes()
    acquire = DatasetLock.acquire
    observed, owners = [], []
    def database_files():
        # Windows protects the lock file's first byte while ownership is held.
        # Include every other file, including any SQLite sidecars, without skips.
        return {p.name: p.read_bytes() for p in directory.iterdir() if p != lock_path}
    def changed_after_lock(self):
        acquire(self)
        owners.append(self)
        # Test-only competing change at the admission/ownership boundary.
        c = sqlite3.connect(path, isolation_level=None)
        try:
            c.execute('PRAGMA journal_mode=WAL' if changed == 'wal' else 'PRAGMA application_id=123')
        finally:
            c.close()
        observed.append(database_files())
    def forbidden(*a): pytest.fail('Incompatible candidate reached runtime configuration')
    with monkeypatch.context() as patch:
        patch.setattr(DatasetLock, 'acquire', changed_after_lock)
        patch.setattr(SQLiteStore, '_profile', forbidden)
        diagnostic = 'DELETE journal profile' if changed == 'wal' else 'Not a supported Chronicle schema'
        with pytest.raises(ValueError, match=diagnostic): SQLiteStore(directory)
    assert len(owners) == 1 and owners[0].file is None
    assert observed == [database_files()]
    assert lock_path.read_bytes() == lock_bytes
    next_owner = DatasetLock(directory)
    try:
        next_owner.acquire()
        assert next_owner.file is not None
        assert observed == [database_files()]
    finally:
        next_owner.close()
    assert next_owner.file is None
    assert lock_path.read_bytes() == lock_bytes
    assert observed == [database_files()]


def test_fresh_profile_and_reopen(store):
    c = store.connection
    assert c.isolation_level is None
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_MS
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert c.execute("PRAGMA synchronous").fetchone()[0] == 3
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    dataset = store.dataset_id
    directory = store.directory
    store.close()
    reopened = SQLiteStore(directory)
    try:
        assert reopened.dataset_id == dataset
        assert reopened.timezone == "America/Chicago"
        assert reopened.connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert reopened.connection.execute("PRAGMA synchronous").fetchone()[0] == 3
        assert reopened.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert reopened.info["journal_mode"] == "delete"
        assert reopened.info["synchronous"] == 3 and reopened.info["foreign_keys"] == 1
        assert reopened.info["python"] and reopened.info["source_id"]
        assert reopened.info["sqlite"] == sqlite3.sqlite_version
        assert reopened.info["compile_options"]
        assert not (directory / (DATABASE + "-journal")).exists()
        assert not (directory / (DATABASE + "-wal")).exists()
        assert not (directory / (DATABASE + "-shm")).exists()
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


def test_runtime_rejects_old_strict_version_with_actual_and_minimum(monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 36, 9))
    with pytest.raises(RuntimeError, match=r"3\.36\.9.*3\.37\.0.*STRICT"):
        runtime_info()


@pytest.mark.parametrize("version", [(3, 37, 0), (3, 40, 1), (3, 51, 2), (3, 52, 0)])
def test_runtime_version_gate_accepts_strict_floor_and_later(monkeypatch, version):
    # Only the gate is simulated. Real STRICT/profile behavior uses the linked runtime.
    monkeypatch.setattr(sqlite3, "sqlite_version_info", version)
    assert runtime_info()["supported_floor"] == "3.37.0"


@pytest.mark.parametrize("setting,value", [("journal_mode", "memory"), ("synchronous", 2), ("foreign_keys", 0)])
def test_profile_rejects_unfulfilled_settings(store, setting, value):
    real = store.connection
    class RefusedSetting:
        def __getattr__(self, name): return getattr(real, name)
        def execute(self, sql, *args):
            if sql == f"PRAGMA {setting}":
                class Result:
                    def fetchone(self): return (value,)
                return Result()
            return real.execute(sql, *args)
    store.connection = RefusedSetting()
    with pytest.raises(RuntimeError, match="Unsupported SQLite profile"):
        store._profile()


def test_profile_never_reconfigures_inside_transaction(store):
    store.connection.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(RuntimeError, match="transaction"):
            store._profile()
    finally:
        store.connection.execute("ROLLBACK")


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


def test_existing_unsupported_journal_profile_is_refused_without_conversion(store, monkeypatch):
    directory = store.directory
    store.close()
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    original = SQLiteStore._probe
    class UnsupportedProfile:
        def __init__(self, inner): self.inner = inner
        def __getattr__(self, name): return getattr(self.inner, name)
        def execute(self, sql, *args):
            if sql == "PRAGMA journal_mode":
                class Result:
                    def fetchone(self): return ("wal",)
                return Result()
            return self.inner.execute(sql, *args)
    monkeypatch.setattr(SQLiteStore, "_probe", lambda self: UnsupportedProfile(original(self)))
    def forbidden(self):
        pytest.fail("Unsupported profile must be rejected before writable connection/profile changes")
    monkeypatch.setattr(SQLiteStore, "_connect", forbidden)
    with pytest.raises(ValueError, match="no automatic conversion"):
        SQLiteStore(directory)
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
