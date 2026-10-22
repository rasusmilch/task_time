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
from .timekeeping import MIN_US, MAX_US, load_zone, parse_date

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
 week_start INTEGER NOT NULL CHECK(week_start BETWEEN 0 AND 6),
 polr_reminder_dismissed_local_date TEXT CHECK(polr_reminder_dismissed_local_date IS NULL OR
   (length(polr_reminder_dismissed_local_date)=10 AND polr_reminder_dismissed_local_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'))
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
 kind TEXT NOT NULL CHECK(kind IN ('timed','date_only')),
 original_start_utc_us INTEGER CHECK(original_start_utc_us {STAMP}),
 current_revision INTEGER CHECK(current_revision>0),
 created_request_id TEXT NOT NULL REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 CHECK((kind='timed' AND original_start_utc_us IS NOT NULL)
    OR (kind='date_only' AND original_start_utc_us IS NULL AND current_revision IS NOT NULL)),
 UNIQUE(entry_id,task_id), UNIQUE(entry_id,kind),
 FOREIGN KEY(entry_id,current_revision,kind) REFERENCES work_revisions(entry_id,revision,kind)
 DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE work_revisions (
 entry_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 kind TEXT NOT NULL CHECK(kind IN ('timed','date_only')),
 start_utc_us INTEGER CHECK(start_utc_us {STAMP}),
 stop_utc_us INTEGER CHECK(stop_utc_us {STAMP}),
 work_date TEXT, duration_us INTEGER,
 is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)), comment TEXT NOT NULL,
 audit_utc_us INTEGER NOT NULL CHECK(audit_utc_us {STAMP}),
 request_id TEXT NOT NULL REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 CHECK((kind='timed' AND start_utc_us IS NOT NULL AND stop_utc_us IS NOT NULL
        AND stop_utc_us>start_utc_us AND work_date IS NULL AND duration_us IS NULL)
    OR (kind='date_only' AND start_utc_us IS NULL AND stop_utc_us IS NULL
        AND work_date IS NOT NULL AND work_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND length(work_date)=10 AND duration_us IS NOT NULL AND duration_us>0)),
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
 WHEN EXISTS(SELECT 1 FROM work_entries WHERE entry_id=NEW.entry_id AND (kind!='timed' OR current_revision IS NOT NULL))
 BEGIN SELECT RAISE(ABORT,'entry already closed or not timed'); END;
CREATE TRIGGER active_identity_immutable BEFORE UPDATE OF entry_id,task_id,singleton ON active_timer
 BEGIN SELECT RAISE(ABORT,'immutable active identity'); END;
CREATE TRIGGER revision_successor BEFORE INSERT ON work_revisions
 WHEN NEW.revision != COALESCE((SELECT max(revision)+1 FROM work_revisions WHERE entry_id=NEW.entry_id),1)
   OR EXISTS(SELECT 1 FROM work_revisions WHERE entry_id=NEW.entry_id AND is_deleted=1)
   OR (NEW.is_deleted=1 AND NOT EXISTS(SELECT 1 FROM work_revisions p
       WHERE p.entry_id=NEW.entry_id AND p.revision=NEW.revision-1
         AND p.start_utc_us IS NEW.start_utc_us AND p.stop_utc_us IS NEW.stop_utc_us
         AND p.work_date IS NEW.work_date AND p.duration_us IS NEW.duration_us))
 BEGIN SELECT RAISE(ABORT,'invalid revision successor'); END;
CREATE TRIGGER current_revision_forward BEFORE UPDATE OF current_revision ON work_entries
 WHEN NEW.current_revision IS NOT OLD.current_revision
   AND (NEW.current_revision IS NULL OR NEW.current_revision != COALESCE(OLD.current_revision+1,1))
 BEGIN SELECT RAISE(ABORT,'current revision must advance by one'); END;
CREATE TRIGGER correction_active_only BEFORE INSERT ON active_start_corrections
 WHEN NOT EXISTS(SELECT 1 FROM active_timer a WHERE a.entry_id=NEW.entry_id
   AND a.version+1=NEW.version AND a.start_utc_us=NEW.prior_start_utc_us)
 BEGIN SELECT RAISE(ABORT,'correction must match active timer'); END;
CREATE TRIGGER closed_not_active BEFORE UPDATE OF current_revision ON work_entries
 WHEN NEW.current_revision IS NOT NULL AND EXISTS(SELECT 1 FROM active_timer WHERE entry_id=NEW.entry_id)
 BEGIN SELECT RAISE(ABORT,'entry still active'); END;
"""
SCHEMA += f"""
CREATE TABLE timesheet_exports (
 export_id TEXT PRIMARY KEY {uuid_constraint('export_id')},
 created_request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 registered_utc_us INTEGER NOT NULL CHECK(registered_utc_us {STAMP}),
 cutoff_utc_us INTEGER NOT NULL CHECK(cutoff_utc_us {STAMP}),
 start_date TEXT NOT NULL CHECK(length(start_date)=10), end_date TEXT NOT NULL CHECK(length(end_date)=10 AND end_date>=start_date),
 timezone TEXT NOT NULL CHECK(length(timezone)>0), week_start INTEGER NOT NULL CHECK(week_start BETWEEN 0 AND 6),
 scope_kind TEXT NOT NULL CHECK(scope_kind IN ('all','selected')), selected_task_ids_json TEXT NOT NULL,
 preferred_destination TEXT, report_utf8 BLOB NOT NULL, report_sha256 TEXT NOT NULL
 CHECK(length(report_sha256)=64 AND report_sha256 NOT GLOB '*[^0-9a-f]*')
) STRICT;
CREATE TABLE timesheet_export_tasks (
 export_id TEXT NOT NULL REFERENCES timesheet_exports(export_id) DEFERRABLE INITIALLY DEFERRED,
 task_id TEXT NOT NULL REFERENCES tasks(task_id), name TEXT NOT NULL,
 project_id TEXT REFERENCES projects(project_id), project_name TEXT NOT NULL,
 is_deleted INTEGER NOT NULL CHECK(is_deleted IN (0,1)), ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 PRIMARY KEY(export_id,task_id), UNIQUE(export_id,ordinal)
) STRICT;
CREATE TABLE timesheet_export_week_basis (
 export_id TEXT NOT NULL, task_id TEXT NOT NULL, week_start_date TEXT NOT NULL CHECK(length(week_start_date)=10),
 work_date TEXT NOT NULL CHECK(length(work_date)=10), actual_us INTEGER NOT NULL CHECK(actual_us>=0),
 suggested_quarters INTEGER NOT NULL CHECK(suggested_quarters>=0),
 PRIMARY KEY(export_id,task_id,week_start_date,work_date),
 FOREIGN KEY(export_id,task_id) REFERENCES timesheet_export_tasks(export_id,task_id) DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE timesheet_export_cells (
 export_id TEXT NOT NULL, task_id TEXT NOT NULL, work_date TEXT NOT NULL, week_start_date TEXT NOT NULL,
 actual_us INTEGER NOT NULL CHECK(actual_us>=0), actual_hundredths INTEGER NOT NULL CHECK(actual_hundredths>=0),
 suggested_quarters INTEGER NOT NULL CHECK(suggested_quarters>=0), PRIMARY KEY(export_id,task_id,work_date),
 FOREIGN KEY(export_id,task_id,week_start_date,work_date)
 REFERENCES timesheet_export_week_basis(export_id,task_id,week_start_date,work_date) DEFERRABLE INITIALLY DEFERRED
) STRICT;
"""
CONFIRMATION_TABLES = ("polr_confirmation_batches", "polr_confirmation_cells", "polr_confirmed_current")
SCHEMA += f"""
CREATE TABLE polr_confirmation_batches (
 batch_id TEXT PRIMARY KEY {uuid_constraint('batch_id')},
 created_request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 audit_utc_us INTEGER NOT NULL CHECK(audit_utc_us {STAMP}),
 source_export_id TEXT REFERENCES timesheet_exports(export_id),
 mode TEXT NOT NULL CHECK(mode IN ('source','manual')),
 CHECK((mode='source' AND source_export_id IS NOT NULL) OR (mode='manual' AND source_export_id IS NULL))
) STRICT;
CREATE TABLE polr_confirmation_cells (
 batch_id TEXT NOT NULL REFERENCES polr_confirmation_batches(batch_id),
 task_id TEXT NOT NULL REFERENCES tasks(task_id),
 work_date TEXT NOT NULL CHECK(length(work_date)=10 AND work_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
 confirmed_quarters INTEGER NOT NULL CHECK(confirmed_quarters BETWEEN 0 AND {((2**63)-1)//25}),
 expected_prior_batch_id TEXT, expected_prior_quarters INTEGER,
 stale_export_acknowledged INTEGER NOT NULL CHECK(stale_export_acknowledged IN (0,1)),
 CHECK((expected_prior_batch_id IS NULL AND expected_prior_quarters IS NULL)
    OR (expected_prior_batch_id IS NOT NULL AND expected_prior_quarters IS NOT NULL)),
 PRIMARY KEY(batch_id,task_id,work_date), UNIQUE(batch_id,task_id,work_date,confirmed_quarters),
 FOREIGN KEY(expected_prior_batch_id,task_id,work_date,expected_prior_quarters)
 REFERENCES polr_confirmation_cells(batch_id,task_id,work_date,confirmed_quarters)
) STRICT;
CREATE TABLE polr_confirmed_current (
 task_id TEXT NOT NULL REFERENCES tasks(task_id), work_date TEXT NOT NULL,
 batch_id TEXT NOT NULL,
 PRIMARY KEY(task_id,work_date),
 FOREIGN KEY(batch_id,task_id,work_date) REFERENCES polr_confirmation_cells(batch_id,task_id,work_date)
) STRICT;
CREATE TRIGGER sealed_polr_confirmation_cells BEFORE INSERT ON polr_confirmation_cells
 WHEN EXISTS(SELECT 1 FROM polr_confirmation_batches b JOIN committed_requests r
 ON r.request_id=b.created_request_id WHERE b.batch_id=NEW.batch_id)
 BEGIN SELECT RAISE(ABORT,'sealed confirmation'); END;
"""
EXPORT_TABLES = ("timesheet_exports", "timesheet_export_tasks", "timesheet_export_week_basis", "timesheet_export_cells")
for _table in EXPORT_TABLES[1:]:
    SCHEMA += (f"CREATE TRIGGER sealed_{_table} BEFORE INSERT ON {_table} "
               "WHEN EXISTS(SELECT 1 FROM timesheet_exports WHERE export_id=NEW.export_id) "
               "BEGIN SELECT RAISE(ABORT,'sealed export'); END;\n")
for _table in ("work_revisions", "active_start_corrections", "committed_requests", *EXPORT_TABLES, *CONFIRMATION_TABLES[:2]):
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
        self._reconciliation_probe = None
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
                self.connection.execute("INSERT INTO dataset_meta(singleton,dataset_id,timezone,week_start) VALUES(1,?,?,6)", (str(uuid4()), timezone))
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
            self.dataset_id, self.timezone = row["dataset_id"], row["timezone"]
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

    @property
    def week_start(self):
        """Read current metadata on the owning thread, never a cached setting."""
        return self.connection.execute("SELECT week_start FROM dataset_meta").fetchone()[0]

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

    def backup(self, destination):
        """Serialized worker operation; never recover an uncertain connection here."""
        if (self.connection is None or self._retired is not None or self._reconciliation_probe is not None
                or self.connection.in_transaction):
            raise RuntimeError('Backup requires a healthy connection with no unresolved transaction')
        from .backup_restore import backup_connection
        return backup_connection(self.connection, destination, self.directory)

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
        expected_names = set()
        for statement in schema_statements():
            name = re.match(r"CREATE (?:TABLE|INDEX|TRIGGER) (\w+)", statement)[1]
            expected_names.add(name)
            if definitions.get(name) != normalize(statement):
                raise ValueError(f"Schema definition differs: {name}")
        if {name for name in definitions if not name.startswith("sqlite_")} != expected_names:
            raise ValueError("Unexpected schema objects; no automatic repair/upgrade")
        tables = {r[1]: r for r in c.execute("PRAGMA table_list")}
        for name in ("dataset_meta", "projects", "tasks", "committed_requests", "work_entries",
                     "work_revisions", "active_timer", "active_start_corrections", *EXPORT_TABLES, *CONFIRMATION_TABLES):
            if name not in tables or tables[name][5] != 1:
                raise ValueError(f"Missing STRICT table: {name}")
        required = {"work_identity_immutable", "work_identity_retained", "active_only_open",
                    "active_identity_immutable", "closed_not_active", "revision_successor", "current_revision_forward", "correction_active_only"}
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
        SQLiteStore.dismissed_date(c)
        SQLiteStore.assert_lifecycle(c)
        for row in c.execute("SELECT export_id FROM timesheet_exports"):
            SQLiteStore.read_export(c, row[0])
        SQLiteStore.assert_confirmations(c)

    @staticmethod
    def verify_receipts(c):
        """Validate detached receipt content and persisted work associations.

        Export and confirmation whole-content validation remains in _verify;
        this adds no second renderer, replay authority or mutation path.
        """
        from .timekeeping import local_date, parse_duration, resolve_minute, resolve_start
        meta = c.execute('SELECT dataset_id,timezone FROM dataset_meta').fetchone()
        dataset, zone = meta[0], load_zone(meta[1])
        receipts = {}
        for row in c.execute('SELECT * FROM committed_requests ORDER BY commit_seq'):
            content = json.loads(row['request_bytes'])
            if (type(content) is not dict or set(content) != {'format','dataset_id','operation','action_utc_us','arguments'}
                    or type(content['format']) is not int or content['format'] != 1
                    or content['dataset_id'] != dataset or content['operation'] != row['operation']
                    or content['action_utc_us'] != row['action_utc_us'] or type(content['arguments']) is not dict):
                raise ValueError('Invalid committed request receipt content')
            request = Request.make(row['request_id'], dataset, row['operation'], row['action_utc_us'], **content['arguments'])
            result = json.loads(row['result_bytes'])
            if request.content() != row['request_bytes'] or type(result) is not dict or canonical(result) != row['result_bytes']:
                raise ValueError('Noncanonical committed request receipt')
            receipts[request.request_id] = (request, result)
            a, op = request.args(), request.operation
            for key in ('expected_version','expected_task_version','expected_active_version','expected_revision'):
                if key in a and (type(a[key]) is not int or not 1 <= a[key] <= 2**63-1):
                    raise ValueError('Invalid reviewed version in receipt')
            if op in ('create_task','rename_task','assign_task_to_project','create_project','rename_project'):
                entity = 'project' if op.endswith('project') and op != 'assign_task_to_project' else 'task'
                key = a.get(f'{entity}_id')
                expected = 1 if op.startswith('create_') else a['expected_version']+1
                fact = c.execute(f'SELECT version FROM {entity}s WHERE {entity}_id=?', (key,)).fetchone()
                if fact is None or fact[0] < expected or canonical(result) != canonical({f'{entity}_id':key,'version':expected}):
                    raise ValueError('Entity receipt relationship differs')
            elif op == 'set_week_start':
                if (type(a.get('week_start')) is not int or not 0 <= a['week_start'] <= 6
                        or type(a.get('expected_week_start')) is not int or not 0 <= a['expected_week_start'] <= 6
                        or canonical(result) != canonical({'week_start':a['week_start']})):
                    raise ValueError('Week setting receipt differs')
            elif op == 'dismiss_polr_reminder_today':
                if a != {'local_date':local_date(request.action_utc_us,zone).isoformat()} or result != a:
                    raise ValueError('Reminder receipt differs')
            elif op in ('register_timesheet_export','confirm_polr_absolute'):
                pass  # Complete content/coverage/prior validation is in _verify.
            elif op in ('start_timer','switch_timer','add_timed_work','add_date_only_work'):
                key = a.get('next_entry_id' if op == 'switch_timer' else 'entry_id')
                if c.execute('SELECT 1 FROM work_entries WHERE entry_id=? AND created_request_id=?',(key,request.request_id)).fetchone() is None:
                    raise ValueError('Creation receipt has no owning work identity')
            elif op in ('stop_timer','edit_closed_timed_work','edit_date_only_work','delete_work_entry'):
                if c.execute('SELECT 1 FROM work_revisions WHERE request_id=?',(request.request_id,)).fetchone() is None:
                    raise ValueError('Work receipt has no immutable revision')
            elif op == 'correct_active_start':
                if c.execute('SELECT 1 FROM active_start_corrections WHERE request_id=?',(request.request_id,)).fetchone() is None:
                    raise ValueError('Correction receipt has no audit evidence')
            else:
                raise ValueError('Unsupported committed receipt operation')
        for entry in c.execute('SELECT * FROM work_entries'):
            request, result = receipts[entry['created_request_id']]
            a = request.args()
            switched = request.operation == 'switch_timer'
            if (request.operation not in ('start_timer','switch_timer','add_timed_work','add_date_only_work')
                    or a.get('next_entry_id' if switched else 'entry_id') != entry['entry_id']
                    or a.get('next_task_id' if switched else 'task_id') != entry['task_id']
                    or result.get('entry_id') != entry['entry_id']):
                raise ValueError('Work identity/creation receipt relationship differs')
            if request.operation in ('start_timer','switch_timer'):
                if (entry['kind'] != 'timed' or entry['original_start_utc_us'] != request.action_utc_us
                        or canonical(result) != canonical({'entry_id':entry['entry_id'],'version':1,
                           **({'closed_entry_id':a['expected_active_entry_id']} if switched else {})})):
                    raise ValueError('Timer creation differs from accepted action')
        for row in c.execute('SELECT * FROM work_revisions'):
            request, result = receipts[row['request_id']]
            op, a = request.operation, request.args()
            expected_entry = a.get('expected_active_entry_id' if op == 'switch_timer' else 'entry_id')
            if (op not in ('stop_timer','switch_timer','add_timed_work','add_date_only_work',
                           'edit_closed_timed_work','edit_date_only_work','delete_work_entry')
                    or expected_entry != row['entry_id'] or request.action_utc_us != row['audit_utc_us']):
                raise ValueError('Work revision/receipt relationship differs')
            if op == 'switch_timer':
                if result.get('closed_entry_id') != row['entry_id'] or row['revision'] != 1:
                    raise ValueError('Switch revision receipt differs')
            elif canonical(result) != canonical({'entry_id':row['entry_id'], 'revision':row['revision']}):
                raise ValueError('Work revision result differs')
            if op.startswith('edit_') or op == 'delete_work_entry':
                if a.get('expected_revision') != row['revision']-1:
                    raise ValueError('Revision receipt prior differs')
            elif row['revision'] != 1:
                raise ValueError('Initial revision receipt differs')
            if bool(row['is_deleted']) != (op == 'delete_work_entry'):
                raise ValueError('Deleted revision receipt kind differs')
            if op not in ('stop_timer','switch_timer'):
                owner = c.execute('SELECT task_id FROM work_entries WHERE entry_id=?',(row['entry_id'],)).fetchone()[0]
                if a['task_id'] != owner or a.get('comment', '').strip() != row['comment']:
                    raise ValueError('Revision request ownership/comment differs')
            if op in ('stop_timer','switch_timer'):
                if row['stop_utc_us'] != request.action_utc_us or row['kind'] != 'timed':
                    raise ValueError('Stopped revision differs from accepted action')
            elif op != 'delete_work_entry':
                if row['kind'] == 'date_only':
                    if (row['work_date'],row['duration_us']) != (parse_date(a['work_date']).isoformat(),parse_duration(a['duration_text'])):
                        raise ValueError('Dated revision differs from frozen input')
                else:
                    prior = c.execute('SELECT * FROM work_revisions WHERE entry_id=? AND revision=?',
                                      (row['entry_id'],row['revision']-1)).fetchone()
                    start = resolve_minute(a['start_date'],a['start_time'],a['start_occurrence'],zone,
                                           original=prior['start_utc_us'] if prior else None)
                    stop = resolve_minute(a['end_date'],a['end_time'],a['end_occurrence'],zone,
                                          original=prior['stop_utc_us'] if prior else None)
                    if (start,stop) != (row['start_utc_us'],row['stop_utc_us']) or stop > request.action_utc_us:
                        raise ValueError('Timed revision differs from frozen input')
        for row in c.execute('SELECT * FROM active_start_corrections'):
            request, result = receipts[row['request_id']]
            a = request.args()
            if (request.operation != 'correct_active_start' or a.get('entry_id') != row['entry_id']
                    or a.get('expected_version') != row['version']-1 or request.action_utc_us != row['audit_utc_us']
                    or result != {'entry_id':row['entry_id'], 'version':row['version']}):
                raise ValueError('Active-start correction receipt differs')
            if (resolve_start(row['prior_start_utc_us'],a['date_text'],a['time_text'],a['occurrence'],zone)
                    != row['corrected_start_utc_us'] or row['comment'] != a['comment'].strip()):
                raise ValueError('Active-start evidence differs from frozen input')

    @staticmethod
    def dismissed_date(c):
        from .polr_allocation import civil
        value = c.execute('SELECT polr_reminder_dismissed_local_date FROM dataset_meta').fetchone()[0]
        if value is not None:
            civil(value)
        return value

    @staticmethod
    def assert_lifecycle(c):
        bad = c.execute("""SELECT e.entry_id FROM work_entries e LEFT JOIN active_timer a USING(entry_id)
          WHERE (a.entry_id IS NOT NULL AND e.kind!='timed')
             OR (e.current_revision IS NULL AND a.entry_id IS NULL)
             OR (e.current_revision IS NOT NULL AND a.entry_id IS NOT NULL) LIMIT 1""").fetchone()
        if bad:
            raise ValueError(f"Invalid active/closed lifecycle: {bad[0]}")
        for table, key in (("tasks", "task_id"), ("projects", "project_id"), ("work_entries", "entry_id")):
            for row in c.execute(f"SELECT {key} FROM {table}"):
                uuid_text(row[0])
        for entry in c.execute("SELECT * FROM work_entries"):
            revisions = list(c.execute("SELECT * FROM work_revisions WHERE entry_id=? ORDER BY revision", (entry["entry_id"],)))
            expected = entry["current_revision"] or 0
            if len(revisions) != expected or any(r["revision"] != i for i, r in enumerate(revisions, 1)):
                raise ValueError("Invalid current revision chain")
            previous = None
            for revision in revisions:
                if revision["kind"] != entry["kind"] or (previous is not None and previous["is_deleted"]):
                    raise ValueError("Invalid revision kind/deleted successor")
                if revision["kind"] == "date_only":
                    if parse_date(revision["work_date"]).isoformat() != revision["work_date"]:
                        raise ValueError("Invalid revision civil date")
                if revision["is_deleted"]:
                    if previous is None or any(revision[key] != previous[key] for key in
                                              ("start_utc_us", "stop_utc_us", "work_date", "duration_us")):
                        raise ValueError("Deletion must retain prior work values")
                previous = revision
            corrections = list(c.execute("SELECT * FROM active_start_corrections WHERE entry_id=? ORDER BY version", (entry["entry_id"],)))
            prior, version = entry["original_start_utc_us"], 1
            for correction in corrections:
                version += 1
                if (entry["kind"] != "timed" or correction["version"] != version
                        or correction["prior_start_utc_us"] != prior):
                    raise ValueError("Invalid active-start audit chain")
                prior = correction["corrected_start_utc_us"]
            active = c.execute("SELECT * FROM active_timer WHERE entry_id=?", (entry["entry_id"],)).fetchone()
            if active and (active["version"] != version or active["start_utc_us"] != prior):
                raise ValueError("Active start does not match immutable evidence")
            if revisions and entry["kind"] == "timed" and revisions[0]["start_utc_us"] != prior:
                raise ValueError("Initial closed revision does not match original/active-start evidence")

    @staticmethod
    def insert_export(c, candidate, request):
        """Validated children first, immutable master last, receipt owned by transact."""
        from .timesheet import validate
        value = validate(candidate)
        for task in value.tasks:
            c.execute("""INSERT INTO timesheet_export_tasks
              (export_id,task_id,name,project_id,project_name,is_deleted,ordinal) VALUES(?,?,?,?,?,?,?)""",
                      (value.export_id,task.task_id,task.name,task.project_id,task.project_name,int(task.is_deleted),task.ordinal))
        for row in value.basis:
            c.execute("""INSERT INTO timesheet_export_week_basis
              (export_id,task_id,week_start_date,work_date,actual_us,suggested_quarters) VALUES(?,?,?,?,?,?)""",
                      (value.export_id,row.task_id,row.week_start_date,row.work_date,row.actual_us,row.suggested_quarters))
        for row in value.cells:
            c.execute("""INSERT INTO timesheet_export_cells
              (export_id,task_id,work_date,week_start_date,actual_us,actual_hundredths,suggested_quarters) VALUES(?,?,?,?,?,?,?)""",
                      (value.export_id,row.task_id,row.work_date,row.week_start_date,row.actual_us,row.actual_hundredths,row.suggested_quarters))
        c.execute("""INSERT INTO timesheet_exports
          (export_id,created_request_id,registered_utc_us,cutoff_utc_us,start_date,end_date,timezone,week_start,
           scope_kind,selected_task_ids_json,preferred_destination,report_utf8,report_sha256)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (value.export_id,request.request_id,request.action_utc_us,value.cutoff_utc_us,value.start_date,value.end_date,
                   value.timezone,value.week_start,value.scope_kind,canonical(list(value.selected_task_ids)).decode(),
                   value.preferred_destination,value.report_utf8,value.report_sha256))
        # Compare the installed relational representation before allowing the receipt.
        if SQLiteStore.read_export(c,value.export_id,check_request=False) != value:
            raise ValueError("Installed frozen export differs from reviewed candidate")
        return {"export_id":value.export_id,"report_sha256":value.report_sha256}

    @staticmethod
    def read_export(c, export_id, *, check_request=True):
        from .timesheet import from_content
        uuid_text(export_id)
        row = c.execute("SELECT * FROM timesheet_exports WHERE export_id=?",(export_id,)).fetchone()
        if row is None:
            raise ValueError("Registered export is unknown")
        meta = c.execute("SELECT dataset_id,timezone FROM dataset_meta").fetchone()
        data = {key:row[key] for key in ("export_id","start_date","end_date","cutoff_utc_us","timezone","week_start",
                                       "scope_kind","preferred_destination","report_sha256")}
        data.update(dataset_id=meta['dataset_id'],selected_task_ids=json.loads(row['selected_task_ids_json']),
                    report_text=row['report_utf8'].decode('utf-8'))
        if canonical(data['selected_task_ids']).decode() != row['selected_task_ids_json']:
            raise ValueError('Noncanonical registered scope')
        data['tasks'] = [dict(r) for r in c.execute("""SELECT task_id,name,project_id,project_name,is_deleted,ordinal
          FROM timesheet_export_tasks WHERE export_id=? ORDER BY ordinal""",(export_id,))]
        for task in data['tasks']:
            if type(task['is_deleted']) is not int or task['is_deleted'] not in (0,1):
                raise ValueError('Invalid frozen deleted flag')
            task['is_deleted'] = bool(task['is_deleted'])
        for table,fields,key in (
            ('week_basis','b.task_id,b.week_start_date,b.work_date,b.actual_us,b.suggested_quarters','b.week_start_date,b.work_date'),
            ('cells','b.task_id,b.work_date,b.week_start_date,b.actual_us,b.actual_hundredths,b.suggested_quarters','b.work_date')):
            data['basis' if table=='week_basis' else 'cells'] = [dict(r) for r in c.execute(
                f"SELECT {fields} FROM timesheet_export_{table} b LEFT JOIN timesheet_export_tasks t USING(export_id,task_id) "
                f"WHERE b.export_id=? ORDER BY t.ordinal,{key}",(export_id,))]
        value = from_content(data,check_render=False)
        if row['timezone'] != meta['timezone']:
            raise ValueError("Registered export timezone/dataset association disagrees")
        if check_request:
            if list(c.execute('PRAGMA foreign_key_check')):
                raise ValueError('Frozen export relational integrity failed')
            receipt = c.execute("SELECT * FROM committed_requests WHERE request_id=?",(row['created_request_id'],)).fetchone()
            if receipt is None:
                raise ValueError("Export has no committed receipt")
            expected = Request.make(row['created_request_id'],meta['dataset_id'],'register_timesheet_export',
                                    row['registered_utc_us'],candidate=data)
            if (receipt['operation'] != expected.operation or receipt['request_bytes'] != expected.content()
                    or receipt['action_utc_us'] != row['registered_utc_us']
                    or json.loads(receipt['result_bytes']) != {'export_id':export_id,'report_sha256':value.report_sha256}):
                raise ValueError("Frozen export and committed request disagree")
        return value

    @staticmethod
    def confirmation_state(c):
        current, history = {}, {}
        for row in c.execute("""SELECT b.batch_id,v.task_id,v.work_date,v.confirmed_quarters,r.commit_seq
          FROM polr_confirmation_batches b JOIN committed_requests r ON r.request_id=b.created_request_id
          JOIN polr_confirmation_cells v USING(batch_id) ORDER BY r.commit_seq,v.task_id,v.work_date"""):
            k=(row['task_id'],row['work_date'])
            history[(row['batch_id'],*k)]=(row['confirmed_quarters'],row['commit_seq'])
        for row in c.execute('''SELECT p.task_id,p.work_date,p.batch_id,v.confirmed_quarters,r.commit_seq
          FROM polr_confirmed_current p JOIN polr_confirmation_cells v USING(batch_id,task_id,work_date)
          JOIN polr_confirmation_batches b USING(batch_id) JOIN committed_requests r ON r.request_id=b.created_request_id'''):
            current[(row['task_id'],row['work_date'])]=(row['batch_id'],row['confirmed_quarters'],row['commit_seq'])
        return current,history

    @staticmethod
    def assert_confirmations(c):
        """Prove receipts, complete batches, prior chains and latest pointers in commit order."""
        from .polr_confirmation import validate_batch
        meta=c.execute('SELECT dataset_id FROM dataset_meta').fetchone()
        tasks={r[0] for r in c.execute('SELECT task_id FROM tasks')}
        current,history={},{}
        batches=list(c.execute("""SELECT b.*,r.commit_seq,r.operation,r.request_bytes,r.result_bytes,r.action_utc_us
          FROM polr_confirmation_batches b LEFT JOIN committed_requests r ON r.request_id=b.created_request_id
          ORDER BY r.commit_seq"""))
        if len(batches)!=c.execute("SELECT count(*) FROM committed_requests WHERE operation='confirm_polr_absolute'").fetchone()[0]:
            raise ValueError('Confirmation batch/receipt coverage differs')
        for b in batches:
            if b['operation']!='confirm_polr_absolute' or b['commit_seq'] is None:raise ValueError('Confirmation has no committed receipt')
            content=json.loads(b['request_bytes'])
            if type(content) is not dict or set(content)!={'format','dataset_id','operation','action_utc_us','arguments'} or type(content['format']) is not int or content['format']!=1:
                raise ValueError('Invalid confirmation receipt format')
            a=content['arguments']
            expected=Request.make(b['created_request_id'],meta['dataset_id'],'confirm_polr_absolute',b['audit_utc_us'],**a)
            if expected.content()!=b['request_bytes'] or b['action_utc_us']!=b['audit_utc_us']:
                raise ValueError('Confirmation receipt identity/content differs')
            if a['batch_id']!=b['batch_id'] or a['mode']!=b['mode'] or a['source_export_id']!=b['source_export_id']:
                raise ValueError('Confirmation master differs from its request')
            source=None;source_seq=None
            if b['source_export_id'] is not None:
                source=SQLiteStore.read_export(c,b['source_export_id'])
                source_seq=c.execute("""SELECT r.commit_seq FROM timesheet_exports e JOIN committed_requests r
                 ON r.request_id=e.created_request_id WHERE e.export_id=?""",(source.export_id,)).fetchone()[0]
                if source_seq>=b['commit_seq']:raise ValueError('Confirmation source was not yet committed')
            cells=validate_batch(a,source=source,source_seq=source_seq,current=current,history=history,tasks=tasks)
            actual=[tuple(r) for r in c.execute("""SELECT task_id,work_date,confirmed_quarters,expected_prior_batch_id,
              expected_prior_quarters,stale_export_acknowledged FROM polr_confirmation_cells WHERE batch_id=? ORDER BY task_id,work_date""",(b['batch_id'],))]
            expected_cells=[(r.task_id,r.work_date,r.confirmed_quarters,r.expected_prior_batch_id,r.expected_prior_quarters,int(r.stale_export_acknowledged)) for r in cells]
            result={'batch_id':b['batch_id'],'cell_count':len(cells)}
            if actual!=expected_cells or b['result_bytes']!=canonical(result):raise ValueError('Confirmation cells/result differ from the whole committed request')
            for cell in cells:
                k=(cell.task_id,cell.work_date)
                current[k]=(b['batch_id'],cell.confirmed_quarters,b['commit_seq'])
                history[(b['batch_id'],*k)]=(cell.confirmed_quarters,b['commit_seq'])
        pointers={(r['task_id'],r['work_date']):r['batch_id'] for r in c.execute('SELECT * FROM polr_confirmed_current')}
        if pointers!={k:v[0] for k,v in current.items()}:raise ValueError('Current confirmation does not identify the latest committed cell')
        if list(c.execute('PRAGMA foreign_key_check')):raise ValueError('Confirmation relational integrity failed')

    @staticmethod
    def insert_confirmation(c, request, source, source_seq):
        from .polr_confirmation import validate_batch
        SQLiteStore.assert_confirmations(c)
        current,history=SQLiteStore.confirmation_state(c);a=request.args()
        cells=validate_batch(a,source=source,source_seq=source_seq,current=current,history=history,
                             tasks={r[0] for r in c.execute('SELECT task_id FROM tasks')})
        c.execute("""INSERT INTO polr_confirmation_batches(batch_id,created_request_id,audit_utc_us,source_export_id,mode)
          VALUES(?,?,?,?,?)""",(a['batch_id'],request.request_id,request.action_utc_us,a['source_export_id'],a['mode']))
        for cell in cells:
            c.execute("""INSERT INTO polr_confirmation_cells(batch_id,task_id,work_date,confirmed_quarters,
             expected_prior_batch_id,expected_prior_quarters,stale_export_acknowledged) VALUES(?,?,?,?,?,?,?)""",
             (a['batch_id'],cell.task_id,cell.work_date,cell.confirmed_quarters,cell.expected_prior_batch_id,cell.expected_prior_quarters,int(cell.stale_export_acknowledged)))
            c.execute("""INSERT INTO polr_confirmed_current(task_id,work_date,batch_id) VALUES(?,?,?)
              ON CONFLICT(task_id,work_date) DO UPDATE SET batch_id=excluded.batch_id""",(cell.task_id,cell.work_date,a['batch_id']))
        return {'batch_id':a['batch_id'],'cell_count':len(cells)}

    @staticmethod
    def _receipt(c, request, content):
        row = c.execute("SELECT * FROM committed_requests WHERE request_id=?", (request.request_id,)).fetchone()
        if row is None:
            return None
        if row["operation"] != request.operation or row["request_bytes"] != content:
            raise RequestConflict("Request identity already exists with different content")
        return json.loads(row["result_bytes"])

    def _recover_connection(self):
        if self._reconciliation_probe is not None:
            self._reconciliation_probe.close()
            self._reconciliation_probe = None
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
            if self._reconciliation_probe is not None:
                self._reconciliation_probe.close()
                self._reconciliation_probe = None
            c = self._probe()
            self._reconciliation_probe = c  # Retain cleanup ownership even after failed close.
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
                else:
                    self._reconciliation_probe = None
                raise
            else:
                c.close()
                self._reconciliation_probe = None
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
            self.assert_confirmations(c)
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
        for c in (self.connection, self._retired, self._reconciliation_probe):
            if c is not None:
                try:
                    c.close()
                except Exception as exc:
                    errors.append(exc)
        if errors:
            for secondary in errors[1:]:
                errors[0].add_note(f'Additional connection cleanup failed: {secondary!r}')
            raise errors[0]  # Retain ownership if the connection could still be executing.
        self.connection = self._retired = self._reconciliation_probe = None
        self.lock.close()
