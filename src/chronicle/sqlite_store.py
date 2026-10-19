"""Worker-owned SQLite authority and explicit transaction/reconciliation boundary."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import sqlite3
from uuid import uuid4

from .dataset_lock import DatasetLock
from .records import Outcome, Request, canonical, uuid_text
from .timekeeping import MIN_US, MAX_US, load_zone

SCHEMA_VERSION = 1
APPLICATION_ID = 0x4348524E
DATABASE = "chronicle.sqlite3"
BUSY_MS = 750
STAMP = f"BETWEEN {MIN_US} AND {MAX_US}"


def uuid_constraint(column):
    return (f"CHECK(length({column})=36 AND substr({column},9,1)='-' "
            f"AND substr({column},14,1)='-' AND substr({column},19,1)='-' "
            f"AND substr({column},24,1)='-' AND length(replace({column},'-',''))=32 "
            f"AND replace({column},'-','') NOT GLOB '*[^0-9a-f]*')")


class RequestConflict(ValueError):
    """Committed identity has different frozen content."""
SCHEMA = f"""
CREATE TABLE dataset_meta (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), dataset_id TEXT NOT NULL UNIQUE {uuid_constraint('dataset_id')},
 timezone TEXT NOT NULL CHECK(length(timezone)>0),
 week_start INTEGER NOT NULL CHECK(week_start BETWEEN 0 AND 6)
) STRICT;
CREATE TABLE projects (
 project_id TEXT PRIMARY KEY {uuid_constraint('project_id')}, name TEXT NOT NULL CHECK(length(trim(name))>0),
 version INTEGER NOT NULL CHECK(version>0), is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
 created_utc_us INTEGER NOT NULL CHECK(created_utc_us {STAMP}),
 updated_utc_us INTEGER NOT NULL CHECK(updated_utc_us {STAMP})
) STRICT;
CREATE TABLE tasks (
 task_id TEXT PRIMARY KEY {uuid_constraint('task_id')}, project_id TEXT REFERENCES projects(project_id),
 name TEXT NOT NULL CHECK(length(trim(name))>0), version INTEGER NOT NULL CHECK(version>0),
 is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
 created_utc_us INTEGER NOT NULL CHECK(created_utc_us {STAMP}),
 updated_utc_us INTEGER NOT NULL CHECK(updated_utc_us {STAMP})
) STRICT;
CREATE TABLE committed_requests (
 commit_seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE {uuid_constraint('request_id')},
 operation TEXT NOT NULL, request_bytes BLOB NOT NULL, result_bytes BLOB NOT NULL,
 action_utc_us INTEGER NOT NULL CHECK(action_utc_us {STAMP})
) STRICT;
CREATE TABLE work_entries (
 entry_id TEXT PRIMARY KEY {uuid_constraint('entry_id')}, task_id TEXT NOT NULL REFERENCES tasks(task_id),
 kind TEXT NOT NULL CHECK(kind='timed'),
 original_start_utc_us INTEGER NOT NULL CHECK(original_start_utc_us {STAMP}),
 current_revision INTEGER CHECK(current_revision>0),
 created_request_id TEXT NOT NULL REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(entry_id,task_id), UNIQUE(entry_id,kind),
 FOREIGN KEY(entry_id,current_revision,kind) REFERENCES work_revisions(entry_id,revision,kind)
 DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE work_revisions (
 entry_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 kind TEXT NOT NULL CHECK(kind='timed'),
 start_utc_us INTEGER NOT NULL CHECK(start_utc_us {STAMP}),
 stop_utc_us INTEGER NOT NULL CHECK(stop_utc_us {STAMP} AND stop_utc_us>start_utc_us),
 is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)), comment TEXT NOT NULL,
 audit_utc_us INTEGER NOT NULL CHECK(audit_utc_us {STAMP}),
 request_id TEXT NOT NULL REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 PRIMARY KEY(entry_id,revision), UNIQUE(entry_id,revision,kind),
 FOREIGN KEY(entry_id,kind) REFERENCES work_entries(entry_id,kind)
) STRICT;
CREATE TABLE active_timer (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), entry_id TEXT NOT NULL UNIQUE,
 task_id TEXT NOT NULL, start_utc_us INTEGER NOT NULL CHECK(start_utc_us {STAMP}),
 version INTEGER NOT NULL CHECK(version>0),
 FOREIGN KEY(entry_id,task_id) REFERENCES work_entries(entry_id,task_id)
) STRICT;
CREATE TABLE active_start_corrections (
 entry_id TEXT NOT NULL REFERENCES work_entries(entry_id), version INTEGER NOT NULL CHECK(version>1),
 prior_start_utc_us INTEGER NOT NULL CHECK(prior_start_utc_us {STAMP}),
 corrected_start_utc_us INTEGER NOT NULL CHECK(corrected_start_utc_us {STAMP}),
 audit_utc_us INTEGER NOT NULL CHECK(audit_utc_us {STAMP} AND corrected_start_utc_us<=audit_utc_us),
 comment TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id)
 DEFERRABLE INITIALLY DEFERRED, PRIMARY KEY(entry_id,version)
) STRICT;
CREATE INDEX tasks_project ON tasks(project_id);
CREATE INDEX work_task ON work_entries(task_id);
CREATE TRIGGER work_identity_immutable BEFORE UPDATE OF entry_id,task_id,kind,original_start_utc_us,created_request_id
 ON work_entries BEGIN SELECT RAISE(ABORT,'immutable work identity'); END;
CREATE TRIGGER work_identity_retained BEFORE DELETE ON work_entries
 BEGIN SELECT RAISE(ABORT,'retained work identity'); END;
CREATE TRIGGER active_only_open BEFORE INSERT ON active_timer
 WHEN EXISTS(SELECT 1 FROM work_entries WHERE entry_id=NEW.entry_id AND current_revision IS NOT NULL)
 BEGIN SELECT RAISE(ABORT,'entry already closed'); END;
CREATE TRIGGER active_identity_immutable BEFORE UPDATE OF entry_id,task_id,singleton ON active_timer
 BEGIN SELECT RAISE(ABORT,'immutable active identity'); END;
CREATE TRIGGER closed_not_active BEFORE UPDATE OF current_revision ON work_entries
 WHEN NEW.current_revision IS NOT NULL AND EXISTS(SELECT 1 FROM active_timer WHERE entry_id=NEW.entry_id)
 BEGIN SELECT RAISE(ABORT,'entry still active'); END;
"""
for _table in ("work_revisions", "active_start_corrections", "committed_requests"):
    for _verb in ("UPDATE", "DELETE"):
        SCHEMA += (f"CREATE TRIGGER immutable_{_table}_{_verb.lower()} BEFORE {_verb} ON {_table} "
                   "BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;\n")


def schema_statements():
    statement = ""
    for line in SCHEMA.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            yield statement.strip().rstrip(";")
            statement = ""
    if statement.strip():
        raise RuntimeError("Incomplete schema definition")


def runtime_info() -> dict:
    version = sqlite3.sqlite_version_info
    if version < (3, 37, 0):
        actual = ".".join(map(str, version))
        raise RuntimeError(f"SQLite {actual} is unsupported; require SQLite 3.37.0+ for STRICT tables")
    return {"python": sys.version, "sqlite": sqlite3.sqlite_version,
            "feature_floor": "3.37.0", "supported_floor": "3.37.0"}


class SQLiteStore:
    def __init__(self, directory: Path, *, create: bool = False, timezone: str | None = None):
        runtime_info()
        if type(create) is not bool:
            raise ValueError("Create must be boolean")
        self.directory = Path(directory).expanduser().resolve()
        self.path = self.directory / DATABASE
        self.connection = None
        self._retired = None
        self.lock = DatasetLock(self.directory)
        if create:
            if timezone is None:
                raise ValueError("Create requires an explicit IANA timezone")
            load_zone(timezone)
            if self.directory.exists() and (not self.directory.is_dir() or any(self.directory.iterdir())):
                raise ValueError("Create requires a new or genuinely empty directory")
            self.directory.mkdir(parents=True, exist_ok=True)
        elif not self.path.is_file() or self.path.is_symlink():
            raise ValueError("An existing Chronicle SQLite dataset is required")
        else:
            self._validate_existing(timezone)
        try:
            self.lock.acquire()
            if create:
                if any(p.name != self.lock.path.name for p in self.directory.iterdir()):
                    raise ValueError("Dataset changed before initialization; refusing overwrite")
                # Exclusive reservation: sqlite connect must never truncate another file.
                with self.path.open("xb"):
                    pass
                self.connection = self._connect()
                self._profile()
                self.connection.execute("BEGIN IMMEDIATE")
                for statement in schema_statements():
                    self.connection.execute(statement)
                self.connection.execute("INSERT INTO dataset_meta VALUES(1,?,?,6)", (str(uuid4()), timezone))
                self.connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                self.connection.execute("COMMIT")
            else:
                # Identify before configuring or otherwise writing to an unknown database.
                self._validate_existing(timezone)
                self.connection = self._connect()
                self._profile()
            self._verify(self.connection)
            row = self.connection.execute("SELECT * FROM dataset_meta").fetchone()
            self.dataset_id, self.timezone, self.week_start = row["dataset_id"], row["timezone"], row["week_start"]
            uuid_text(self.dataset_id)
            if timezone is not None and timezone != self.timezone:
                raise ValueError("Explicit timezone conflicts with this dataset")
            self.zone = load_zone(self.timezone)
            self.info = {**runtime_info(), "compile_options": [r[0] for r in self.connection.execute("PRAGMA compile_options")],
                         "source_id": self.connection.execute("SELECT sqlite_source_id()").fetchone()[0],
                         **self._profile_values()}
        except BaseException as primary:
            try:
                self.close()
            except Exception as secondary:
                primary.add_note(f"Initialization cleanup failed: {secondary!r}")
                # Constructor failure must not orphan a still-owned connection/lock.
                # The worker consumes this temporary handoff before delivering diagnostics.
                primary._chronicle_cleanup_store = self
            raise

    def _validate_existing(self, timezone):
        probe = self._probe()
        try:
            self._verify(probe)
            # Refuse unsupported development profiles; never convert an existing dataset.
            if probe.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise ValueError("Unsupported dataset journal mode; DELETE is required; no automatic conversion")
            if timezone is not None and probe.execute("SELECT timezone FROM dataset_meta").fetchone()[0] != timezone:
                raise ValueError("Explicit timezone conflicts with this dataset")
        except BaseException as primary:
            try:
                probe.close()
            except Exception as secondary:
                primary.add_note(f"Validation probe close failed: {secondary!r}")
                self._retired = probe
                primary._chronicle_cleanup_store = self
            raise
        else:
            try:
                probe.close()
            except Exception as primary:
                self._retired = probe
                primary._chronicle_cleanup_store = self
                raise  # A failed close is still a real startup failure.

    def _connect(self):
        conn = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True,
                               isolation_level=None, timeout=BUSY_MS / 1000)
        conn.row_factory = sqlite3.Row
        return conn

    def _probe(self):
        conn = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True,
                               isolation_level=None, timeout=BUSY_MS / 1000)
        conn.row_factory = sqlite3.Row
        return conn

    def _profile(self):
        c = self.connection
        if c.in_transaction:
            raise RuntimeError("SQLite profile cannot be configured inside a transaction")
        c.execute(f"PRAGMA busy_timeout={BUSY_MS}")
        c.execute("PRAGMA journal_mode=DELETE")
        c.execute("PRAGMA synchronous=EXTRA")
        c.execute("PRAGMA foreign_keys=ON")
        actual = self._profile_values()
        if actual != {"journal_mode": "delete", "synchronous": 3, "foreign_keys": 1}:
            raise RuntimeError(f"Unsupported SQLite profile: {actual}")

    def _profile_values(self):
        return {name: self.connection.execute(f"PRAGMA {name}").fetchone()[0]
                for name in ("journal_mode", "synchronous", "foreign_keys")}

    @staticmethod
    def _verify(c):
        if (c.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID or
                c.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION):
            raise ValueError("Not a supported Chronicle schema; no automatic repair/upgrade")
        if c.execute("PRAGMA quick_check").fetchone()[0] != "ok" or list(c.execute("PRAGMA foreign_key_check")):
            raise ValueError("Dataset integrity check failed")
        normalize = lambda text: " ".join(text.lower().split()).rstrip(";")
        definitions = {r[0]: normalize(r[1]) for r in c.execute("SELECT name,sql FROM sqlite_schema WHERE sql IS NOT NULL")}
        for statement in schema_statements():
            name = re.match(r"CREATE (?:TABLE|INDEX|TRIGGER) (\w+)", statement)[1]
            if definitions.get(name) != normalize(statement):
                raise ValueError(f"Schema definition differs: {name}")
        tables = {r[1]: r for r in c.execute("PRAGMA table_list")}
        for name in ("dataset_meta", "projects", "tasks", "committed_requests", "work_entries",
                     "work_revisions", "active_timer", "active_start_corrections"):
            if name not in tables or tables[name][5] != 1:
                raise ValueError(f"Missing STRICT table: {name}")
        required = {"work_identity_immutable", "work_identity_retained", "active_only_open",
                    "active_identity_immutable", "closed_not_active"}
        required |= {f"immutable_{table}_{verb}" for table in
                     ("work_revisions", "active_start_corrections", "committed_requests") for verb in ("update", "delete")}
        present = {r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='trigger'")}
        if not required <= present:
            raise ValueError("Required evidence/lifecycle guards are missing")
        meta = list(c.execute("SELECT * FROM dataset_meta"))
        if len(meta) != 1:
            raise ValueError("Dataset metadata is incomplete")
        uuid_text(meta[0]["dataset_id"])
        load_zone(meta[0]["timezone"])
        SQLiteStore.assert_lifecycle(c)

    @staticmethod
    def assert_lifecycle(c):
        bad = c.execute("""SELECT e.entry_id FROM work_entries e LEFT JOIN active_timer a USING(entry_id)
          WHERE (e.current_revision IS NULL AND a.entry_id IS NULL)
             OR (e.current_revision IS NOT NULL AND a.entry_id IS NOT NULL) LIMIT 1""").fetchone()
        if bad:
            raise ValueError(f"Invalid active/closed lifecycle: {bad[0]}")
        for table, key in (("tasks", "task_id"), ("projects", "project_id"), ("work_entries", "entry_id")):
            for row in c.execute(f"SELECT {key} FROM {table}"):
                uuid_text(row[0])
        for row in c.execute("SELECT * FROM active_timer"):
            corrections = list(c.execute("SELECT * FROM active_start_corrections WHERE entry_id=? ORDER BY version", (row["entry_id"],)))
            prior = c.execute("SELECT original_start_utc_us FROM work_entries WHERE entry_id=?", (row["entry_id"],)).fetchone()[0]
            version = 1
            for correction in corrections:
                version += 1
                if correction["version"] != version or correction["prior_start_utc_us"] != prior:
                    raise ValueError("Invalid active-start audit chain")
                prior = correction["corrected_start_utc_us"]
            if row["version"] != version or row["start_utc_us"] != prior:
                raise ValueError("Active start does not match immutable evidence")

    @staticmethod
    def _receipt(c, request, content):
        row = c.execute("SELECT * FROM committed_requests WHERE request_id=?", (request.request_id,)).fetchone()
        if row is None:
            return None
        if row["operation"] != request.operation or row["request_bytes"] != content:
            raise RequestConflict("Request identity already exists with different content")
        return json.loads(row["result_bytes"])

    def _recover_connection(self):
        if self._retired is not None:
            self._retired.close()
            self._retired = None
        if self.connection is None:
            self.connection = self._connect()
            try:
                self._profile()
                self._verify(self.connection)
            except BaseException as primary:
                c, self.connection = self.connection, None
                self._retired = c
                try:
                    c.close()
                    self._retired = None
                except Exception as secondary:
                    primary.add_note(f"Recovery connection close failed: {secondary!r}")
                raise

    def reconcile(self, request: Request) -> Outcome:
        content = request.content()
        if request.dataset_id != self.dataset_id:
            return Outcome("rejected", error=ValueError("Wrong dataset identity"))
        try:
            # Always independent, committed-state evidence; never a poisoned transaction view.
            c = self._probe()
            try:
                c.execute("BEGIN")
                self._verify(c)
                result = self._receipt(c, request, content)
                c.execute("ROLLBACK")
            except BaseException as primary:
                try:
                    c.close()
                except Exception as secondary:
                    primary.add_note(f"Reconciliation close failed: {secondary!r}")
                raise
            else:
                c.close()
            if result is not None:
                return Outcome("committed", result)
            if self._retired is not None or (self.connection is not None and self.connection.in_transaction):
                return Outcome("unverified", error=OSError("Prior transaction/connection cleanup is not established; absence is not conclusive"))
            return Outcome("absent")
        except RequestConflict as exc:
            return Outcome("rejected", error=exc)
        except Exception as exc:
            return Outcome("unverified", error=exc)

    def transact(self, request: Request, operation) -> Outcome:
        content = request.content()
        if request.dataset_id != self.dataset_id:
            return Outcome("rejected", error=ValueError("Wrong dataset identity"))
        try:
            self._recover_connection()
            self.connection.execute("BEGIN IMMEDIATE")
        except Exception as exc:
            if self.connection is not None:
                try:
                    active = self.connection.in_transaction
                except Exception as inspection:
                    exc.add_note(f"Transaction-state inspection failed: {inspection!r}")
                    active = True
                if active:
                    return self._failed(request, self.connection, exc)
            return Outcome("unverified" if self._retired is not None else "unavailable", error=exc)
        c = self.connection
        try:
            old = self._receipt(c, request, content)
            if old is not None:
                c.execute("ROLLBACK")
                return Outcome("committed", old)
            result = operation(c)
            if result is None:
                c.execute("ROLLBACK")
                return Outcome("unchanged")
            self.assert_lifecycle(c)  # Cross-table final invariant, before any commit.
            c.execute("INSERT INTO committed_requests(request_id,operation,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?)",
                      (request.request_id, request.operation, content, canonical(result), request.action_utc_us))
            c.execute("COMMIT")
            return Outcome("committed", result)
        except Exception as primary:
            return self._failed(request, c, primary)

    def _failed(self, request, c, primary):
        rejected = isinstance(primary, ValueError)
        cleaned = False
        try:
            if c.in_transaction:
                c.execute("ROLLBACK")
            cleaned = not c.in_transaction
        except Exception as secondary:
            primary.add_note(f"Rollback failed: {secondary!r}")
        self.connection, self._retired = None, c
        try:
            c.close()
            self._retired = None
            cleaned = True
        except Exception as secondary:
            primary.add_note(f"Connection close failed: {secondary!r}")
        evidence = self.reconcile(request)
        if evidence.status == "committed":
            primary.add_note("Independent committed receipt verified after the original failure")
            return Outcome("committed", evidence.result, primary)
        if evidence.status == "absent" and cleaned:
            return Outcome("rejected" if rejected else "rolled_back", error=primary)
        if evidence.status == "rejected":
            return Outcome("rejected", error=primary)
        if evidence.error:
            primary.add_note(f"Reconciliation: {evidence.error!r}")
        return Outcome("unverified", error=primary)

    def close(self):
        errors = []
        for c in (self.connection, self._retired):
            if c is not None:
                try:
                    c.close()
                except Exception as exc:
                    errors.append(exc)
        if errors:
            raise errors[0]  # Retain ownership if the connection could still be executing.
        self.connection = self._retired = None
        self.lock.close()
