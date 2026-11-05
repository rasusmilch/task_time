"""Isolated schema-4 candidate, never ordinary startup or mutation authority.

This explicit DDL retains the reviewed relational/evidence model. It is not
built by modifying schema-3 SQL at runtime. Later packages must complete service,
lifecycle, reporting and startup integration before production admission exists.
"""
from dataclasses import dataclass
import re
import sqlite3

from .sqlite_store import APPLICATION_ID, BUSY_MS, STAMP, uuid_constraint, runtime_info

SCHEMA_VERSION = 4
# Version-specific: future runtime classifications must not change candidate DDL.
ADMINISTRATIVE_OPERATIONS = frozenset({
    'create_project', 'rename_project', 'create_task', 'rename_task',
    'assign_task_to_project', 'move_task_branch',
    'archive_project', 'unarchive_project', 'archive_task', 'unarchive_task',
    'create_template', 'edit_template', 'duplicate_template', 'archive_template',
    'unarchive_template', 'apply_template', 'create_child_project', 'move_project_subtree',
})

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
 parent_project_id TEXT REFERENCES projects(project_id) {uuid_constraint('parent_project_id')}
   CHECK(parent_project_id IS NULL OR parent_project_id!=project_id),
 version INTEGER NOT NULL CHECK(version>0), is_archived INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0,1)),
 archived_at_utc_us INTEGER CHECK(archived_at_utc_us {STAMP}),
 created_request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 created_utc_us INTEGER NOT NULL CHECK(created_utc_us {STAMP}),
 updated_utc_us INTEGER NOT NULL CHECK(updated_utc_us {STAMP}),
 CHECK((is_archived=0 AND archived_at_utc_us IS NULL) OR (is_archived=1 AND archived_at_utc_us IS NOT NULL))
) STRICT;
CREATE TABLE tasks (
 task_id TEXT PRIMARY KEY {uuid_constraint('task_id')}, project_id TEXT REFERENCES projects(project_id),
 parent_task_id TEXT REFERENCES tasks(task_id) CHECK(parent_task_id IS NULL OR parent_task_id!=task_id),
 name TEXT NOT NULL CHECK(length(trim(name))>0), version INTEGER NOT NULL CHECK(version>0),
 is_archived INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0,1)),
 archived_at_utc_us INTEGER CHECK(archived_at_utc_us {STAMP}),
 created_request_id TEXT NOT NULL REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 created_utc_us INTEGER NOT NULL CHECK(created_utc_us {STAMP}),
 updated_utc_us INTEGER NOT NULL CHECK(updated_utc_us {STAMP}),
 CHECK((is_archived=0 AND archived_at_utc_us IS NULL) OR (is_archived=1 AND archived_at_utc_us IS NOT NULL))
) STRICT;
CREATE INDEX tasks_creation_request ON tasks(created_request_id);
CREATE TABLE template_definitions (
 template_id TEXT PRIMARY KEY {uuid_constraint('template_id')},
 name TEXT NOT NULL CHECK(length(trim(name))>0 AND name=trim(name)), name_key TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version>0), is_archived INTEGER NOT NULL CHECK(is_archived IN (0,1)),
 archived_at_utc_us INTEGER CHECK(archived_at_utc_us {STAMP}),
 created_request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 created_utc_us INTEGER NOT NULL CHECK(created_utc_us {STAMP}), updated_utc_us INTEGER NOT NULL CHECK(updated_utc_us {STAMP}),
 CHECK((is_archived=0 AND archived_at_utc_us IS NULL) OR (is_archived=1 AND archived_at_utc_us IS NOT NULL))
) STRICT;
CREATE UNIQUE INDEX active_template_name ON template_definitions(name_key) WHERE is_archived=0;
CREATE TABLE template_nodes (
 node_id TEXT PRIMARY KEY {uuid_constraint('node_id')}, template_id TEXT NOT NULL REFERENCES template_definitions(template_id),
 parent_node_id TEXT CHECK(parent_node_id IS NULL OR parent_node_id!=node_id) {uuid_constraint('parent_node_id')},
 name TEXT NOT NULL CHECK(length(trim(name))>0 AND name=trim(name)), position INTEGER NOT NULL CHECK(position>=0),
 UNIQUE(template_id,node_id), UNIQUE(template_id,position),
 FOREIGN KEY(template_id,parent_node_id) REFERENCES template_nodes(template_id,node_id) DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE committed_requests (
 commit_seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE {uuid_constraint('request_id')},
 operation TEXT NOT NULL, receipt_class TEXT NOT NULL CHECK(receipt_class IN ('administrative','protected')),
 request_bytes BLOB NOT NULL, result_bytes BLOB NOT NULL,
 action_utc_us INTEGER NOT NULL CHECK(action_utc_us {STAMP}),
 CHECK(receipt_class=CASE WHEN operation IN ({','.join(repr(op) for op in sorted(ADMINISTRATIVE_OPERATIONS))})
       THEN 'administrative' ELSE 'protected' END)
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
CREATE INDEX projects_parent ON projects(parent_project_id);
CREATE INDEX tasks_parent ON tasks(parent_task_id);
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

for _table in ("work_revisions", "active_start_corrections", *EXPORT_TABLES, *CONFIRMATION_TABLES[:2]):
    for _verb in ("UPDATE", "DELETE"):
        SCHEMA += (f"CREATE TRIGGER immutable_{_table}_{_verb.lower()} BEFORE {_verb} ON {_table} "
                   "BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;\n")

SCHEMA += """
CREATE TRIGGER immutable_committed_requests_update BEFORE UPDATE ON committed_requests
 BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_committed_requests_delete BEFORE DELETE ON committed_requests
 WHEN OLD.receipt_class='protected'
 BEGIN SELECT RAISE(ABORT,'immutable protected evidence'); END;
"""

for _table, _key in (("tasks", "task_id"), ("projects", "project_id")):
    SCHEMA += (f"CREATE TRIGGER {_table}_identity_immutable BEFORE UPDATE OF {_key},created_request_id,created_utc_us ON {_table} "
               "BEGIN SELECT RAISE(ABORT,'immutable entity identity'); END;\n")

for _event in ("INSERT", "UPDATE OF parent_task_id,project_id"):
    _suffix = "insert" if _event == "INSERT" else "update"
    SCHEMA += f"""
CREATE TRIGGER tasks_forest_{_suffix} BEFORE {_event} ON tasks
 BEGIN
 SELECT RAISE(ABORT,'invalid task parent/project') WHERE NEW.parent_task_id IS NOT NULL AND
   NOT EXISTS(SELECT 1 FROM tasks p WHERE p.task_id=NEW.parent_task_id AND p.project_id IS NEW.project_id);
 SELECT RAISE(ABORT,'task children have different project') WHERE
   EXISTS(SELECT 1 FROM tasks ch WHERE ch.parent_task_id=NEW.task_id AND ch.project_id IS NOT NEW.project_id);
 SELECT RAISE(ABORT,'running task cannot become a parent') WHERE
   EXISTS(SELECT 1 FROM active_timer WHERE task_id=NEW.parent_task_id);
 SELECT RAISE(ABORT,'task cycle or depth overflow') WHERE (
   WITH RECURSIVE ancestors(task_id,parent_task_id,n) AS (
     SELECT task_id,parent_task_id,1 FROM tasks WHERE task_id=NEW.parent_task_id
     UNION ALL SELECT p.task_id,p.parent_task_id,a.n+1 FROM tasks p JOIN ancestors a ON p.task_id=a.parent_task_id WHERE a.n<3
   ), descendants(task_id,n) AS (
     SELECT NEW.task_id,1 UNION ALL SELECT ch.task_id,d.n+1 FROM tasks ch JOIN descendants d ON ch.parent_task_id=d.task_id WHERE d.n<4
   ) SELECT EXISTS(SELECT 1 FROM ancestors WHERE task_id=NEW.task_id)
       OR COALESCE((SELECT max(n) FROM ancestors),0)+(SELECT max(n) FROM descendants)>3
 );
 END;
"""

for _table in ("work_entries", "active_timer"):
    SCHEMA += f"""
CREATE TRIGGER {_table}_eligible_task BEFORE INSERT ON {_table}
 BEGIN
 SELECT RAISE(ABORT,'new recording requires an active leaf') WHERE
   EXISTS(SELECT 1 FROM tasks WHERE parent_task_id=NEW.task_id) OR (
   WITH RECURSIVE path(task_id,parent_task_id,project_id,is_archived,n) AS (
     SELECT task_id,parent_task_id,project_id,is_archived,1 FROM tasks WHERE task_id=NEW.task_id
     UNION ALL SELECT p.task_id,p.parent_task_id,p.project_id,p.is_archived,a.n+1 FROM tasks p JOIN path a ON p.task_id=a.parent_task_id WHERE a.n<3
   ), project_path(project_id,parent_project_id,is_archived) AS (
     SELECT p.project_id,p.parent_project_id,p.is_archived FROM projects p
       JOIN tasks t ON t.project_id=p.project_id WHERE t.task_id=NEW.task_id
     UNION SELECT p.project_id,p.parent_project_id,p.is_archived FROM projects p
       JOIN project_path a ON p.project_id=a.parent_project_id
   ) SELECT EXISTS(SELECT 1 FROM path WHERE is_archived=1)
       OR EXISTS(SELECT 1 FROM project_path WHERE is_archived=1)
       OR (EXISTS(SELECT 1 FROM tasks WHERE task_id=NEW.task_id AND project_id IS NOT NULL)
           AND NOT EXISTS(SELECT 1 FROM project_path WHERE parent_project_id IS NULL))
 );
 END;
"""

SCHEMA += """
CREATE TRIGGER tasks_archive_active BEFORE UPDATE OF is_archived ON tasks WHEN NEW.is_archived=1
 BEGIN
 SELECT RAISE(ABORT,'archive would hide active timer') WHERE (
   WITH RECURSIVE branch(task_id,n) AS (
     SELECT NEW.task_id,1 UNION ALL SELECT t.task_id,b.n+1 FROM tasks t JOIN branch b ON t.parent_task_id=b.task_id WHERE b.n<3
   ) SELECT EXISTS(SELECT 1 FROM branch JOIN active_timer USING(task_id))
 );
 END;
CREATE TRIGGER projects_archive_active BEFORE UPDATE OF is_archived ON projects WHEN NEW.is_archived=1
 BEGIN
 SELECT RAISE(ABORT,'archive would hide active timer') WHERE (
   WITH RECURSIVE branch(project_id) AS (
     SELECT NEW.project_id UNION SELECT p.project_id FROM projects p
       JOIN branch b ON p.parent_project_id=b.project_id
   ) SELECT EXISTS(SELECT 1 FROM active_timer a JOIN tasks t USING(task_id)
       JOIN branch b ON t.project_id=b.project_id)
 );
 END;
"""

# UNION visits a finite set of existing identities, even if a damaged input
# already contains a cycle. No product-level project depth bound is imposed.
for _event, _suffix in (('INSERT', 'insert'), ('UPDATE OF parent_project_id', 'update')):
    SCHEMA += f"""
CREATE TRIGGER projects_forest_{_suffix} BEFORE {_event} ON projects
 WHEN NEW.parent_project_id IS NOT NULL
 BEGIN
 SELECT RAISE(ABORT,'invalid project parent or cycle') WHERE (
   WITH RECURSIVE path(project_id,parent_project_id) AS (
     SELECT project_id,parent_project_id FROM projects WHERE project_id=NEW.parent_project_id
     UNION SELECT p.project_id,p.parent_project_id FROM projects p
       JOIN path a ON p.project_id=a.parent_project_id
   ) SELECT NOT EXISTS(SELECT 1 FROM path WHERE parent_project_id IS NULL)
       OR EXISTS(SELECT 1 FROM path WHERE project_id=NEW.project_id OR parent_project_id=NEW.project_id)
 );
 END;
"""

SCHEMA += """
CREATE TRIGGER projects_parent_active BEFORE UPDATE OF parent_project_id ON projects
 BEGIN
 SELECT RAISE(ABORT,'reparent would hide active timer') WHERE (
   WITH RECURSIVE branch(project_id) AS (
     SELECT NEW.project_id UNION SELECT p.project_id FROM projects p
       JOIN branch b ON p.parent_project_id=b.project_id
   ), path(project_id,parent_project_id,is_archived) AS (
     SELECT project_id,parent_project_id,is_archived FROM projects WHERE project_id=NEW.parent_project_id
     UNION SELECT p.project_id,p.parent_project_id,p.is_archived FROM projects p
       JOIN path a ON p.project_id=a.parent_project_id
   ) SELECT EXISTS(SELECT 1 FROM active_timer a JOIN tasks t USING(task_id)
                     JOIN branch b ON t.project_id=b.project_id)
       AND (NEW.is_archived=1 OR EXISTS(SELECT 1 FROM path WHERE is_archived=1))
 );
 END;
CREATE TRIGGER tasks_active_ancestry BEFORE UPDATE OF parent_task_id,project_id ON tasks
 BEGIN
 SELECT RAISE(ABORT,'task reparent would hide active timer') WHERE (
   WITH RECURSIVE branch(task_id) AS (
     SELECT NEW.task_id UNION SELECT t.task_id FROM tasks t JOIN branch b ON t.parent_task_id=b.task_id
   ), task_path(task_id,parent_task_id,is_archived) AS (
     SELECT task_id,parent_task_id,is_archived FROM tasks WHERE task_id=NEW.parent_task_id
     UNION SELECT t.task_id,t.parent_task_id,t.is_archived FROM tasks t
       JOIN task_path a ON t.task_id=a.parent_task_id
   ), project_path(project_id,parent_project_id,is_archived) AS (
     SELECT project_id,parent_project_id,is_archived FROM projects WHERE project_id=NEW.project_id
     UNION SELECT p.project_id,p.parent_project_id,p.is_archived FROM projects p
       JOIN project_path a ON p.project_id=a.parent_project_id
   ) SELECT EXISTS(SELECT 1 FROM branch JOIN active_timer USING(task_id))
       AND (NEW.is_archived=1 OR EXISTS(SELECT 1 FROM task_path WHERE is_archived=1)
            OR EXISTS(SELECT 1 FROM project_path WHERE is_archived=1))
 );
 END;
"""


def schema_statements():
    statement = ''
    for line in SCHEMA.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            yield statement.strip().rstrip(';')
            statement = ''
    if statement.strip():
        raise RuntimeError('Incomplete candidate schema definition')


def create_candidate(c, *, dataset_id, timezone):
    """Build only a fresh caller-owned test/candidate image; no path-based open.

    This does not validate calendar rules or publish worker readiness. It refuses
    existing schemas, including schema 3, before any profile or data changes.
    """
    from .records import uuid_text
    runtime_info()
    uuid_text(dataset_id)
    if type(timezone) is not str or not timezone.strip():
        raise ValueError('Explicit candidate timezone label required')
    _verify_namespace(c)
    if (c.in_transaction or list(c.execute('SELECT name FROM sqlite_schema'))
            or c.execute('PRAGMA user_version').fetchone()[0] != 0
            or c.execute('PRAGMA application_id').fetchone()[0] != 0):
        raise ValueError('Candidate construction requires an empty new database')
    if not c.execute('PRAGMA database_list').fetchone()[2]:
        raise ValueError('Use a disposable file-backed candidate for DELETE journaling')
    c.execute(f'PRAGMA busy_timeout={BUSY_MS}')
    c.execute('PRAGMA journal_mode=DELETE')
    c.execute('PRAGMA synchronous=EXTRA')
    c.execute('PRAGMA foreign_keys=ON')
    _verify_profile(c)
    c.execute('BEGIN IMMEDIATE')
    try:
        for statement in schema_statements():
            c.execute(statement)
        c.execute('INSERT INTO dataset_meta(singleton,dataset_id,timezone,week_start) VALUES(1,?,?,6)',
                  (dataset_id, timezone))
        c.execute(f'PRAGMA application_id={APPLICATION_ID}')
        c.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        c.execute('COMMIT')
    except BaseException as primary:
        try:
            c.execute('ROLLBACK')
        except Exception as secondary:
            primary.add_note(f'Candidate construction rollback also failed: {secondary!r}')
        raise


def _verify_profile(c):
    if tuple(c.execute(f'PRAGMA {name}').fetchone()[0] for name in
             ('journal_mode', 'synchronous', 'foreign_keys')) != ('delete', 3, 1):
        raise ValueError('Candidate requires DELETE/EXTRA/foreign_keys=ON')


def _verify_namespace(c):
    if (any(r[1] not in ('main', 'temp') for r in c.execute('PRAGMA database_list'))
            or list(c.execute('SELECT name FROM sqlite_temp_schema'))):
        raise ValueError('Candidate requires an unshadowed, unattached main database')


def verify_schema(c):
    """Exact candidate DDL/profile authority, independent of v3 admission."""
    _verify_namespace(c)
    _verify_profile(c)
    if (c.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
            or c.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION):
        raise ValueError('Not an exact schema-4 candidate')
    def normalize(sql):
        tokens = re.findall(r"'(?:(?:'')|[^'])*'|\"(?:(?:\"\")|[^\"])*\"|`(?:(?:``)|[^`])*`|\[[^]]*\]|\w+|[^\s]",
                            sql.strip().rstrip(';'))
        return tuple(t if t.startswith(("'", '"', '`', '[')) else t.lower() for t in tokens)
    expected = {}
    for statement in schema_statements():
        name = re.match(r'CREATE (?:UNIQUE )?(?:TABLE|INDEX|TRIGGER) (\w+)', statement)[1]
        expected[name] = normalize(statement)
    actual = {name: normalize(sql) for name, sql in c.execute(
        'SELECT name,sql FROM sqlite_schema WHERE sql IS NOT NULL') if not name.startswith('sqlite_')}
    if actual != expected:
        raise ValueError('Candidate schema definitions differ')
    strict = {r[1]: r[5] for r in c.execute('PRAGMA table_list')}
    for statement in schema_statements():
        match = re.match(r'CREATE TABLE (\w+)', statement)
        if match and strict.get(match[1]) != 1:
            raise ValueError('Candidate table is not STRICT')


def _rows(c, table):
    cursor = c.execute(f'SELECT * FROM {table}')
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor]


def verify_structure(c):
    """Structural scope only; not complete recording/reporting admission."""
    from .hierarchy import ProjectForest, candidate_task_observations
    from .records import uuid_text, integer
    from .timekeeping import instant, parse_date
    verify_schema(c)
    if [r[0] for r in c.execute('PRAGMA integrity_check')] != ['ok'] or list(c.execute('PRAGMA foreign_key_check')):
        raise ValueError('Candidate integrity or foreign key check failed')
    meta = _rows(c, 'dataset_meta')
    if len(meta) != 1:
        raise ValueError('Incomplete candidate metadata')
    uuid_text(meta[0]['dataset_id'])
    if meta[0]['polr_reminder_dismissed_local_date'] is not None:
        parse_date(meta[0]['polr_reminder_dismissed_local_date'])
    projects, tasks = _rows(c, 'projects'), _rows(c, 'tasks')
    forest = ProjectForest(projects)
    for row in projects + tasks:
        uuid_text(row['created_request_id'])
        integer(row['version'], 'Entity version', 1, 2**63-1)
        instant(row['created_utc_us']); instant(row['updated_utc_us'])
        integer(row['is_archived'], 'Archive flag', 0, 1)
        if bool(row['is_archived']) != (row['archived_at_utc_us'] is not None):
            raise ValueError('Invalid candidate archive metadata')
        if row['archived_at_utc_us'] is not None:
            instant(row['archived_at_utc_us'])
    observations = candidate_task_observations(tasks, projects)
    for task_id, in c.execute('SELECT task_id FROM active_timer'):
        if task_id not in observations or not observations[task_id]['is_leaf'] or observations[task_id]['effective_archived']:
            raise ValueError('Candidate active task is not an eligible leaf')
    return forest


@dataclass(frozen=True)
class CandidateVerification:
    schema_version: int = SCHEMA_VERSION
    structural_verified: bool = True
    administrative_history_verified: bool = True

    @property
    def ordinary_startup_permitted(self):
        return False


def verify_candidate(c):
    """Read-only supported administrative verification; no ordinary admission.

    No timezone calculation, protected-work replay, template, Delete,
    reporting, backup or runtime eligibility is claimed by this candidate API.
    """
    if c.in_transaction:
        raise ValueError('Candidate verification requires a separate completed transaction')
    c.execute('BEGIN')
    try:
        verify_candidate_transaction(c)
    except BaseException as primary:
        try:
            c.execute('ROLLBACK')
        except Exception as secondary:
            primary.add_note(f'Candidate verification rollback also failed: {secondary!r}')
        raise
    else:
        c.execute('ROLLBACK')
        return CandidateVerification()


def verify_candidate_transaction(c):
    """Read-only supported-scope gate inside a caller-owned transaction.

    Owns no BEGIN/COMMIT/ROLLBACK. The separate-snapshot API above retains its
    original contract. Supported administrative replay includes C1 lifecycle;
    protected work, templates, configuration and reporting remain refused.
    """
    from .administration import verify_schema4_history, UnsupportedCandidateOperation
    if not c.in_transaction:
        raise ValueError('Candidate scope verification requires an owned transaction')
    verify_structure(c)
    supported_tables = {'dataset_meta', 'projects', 'tasks', 'committed_requests', 'sqlite_sequence'}
    for table, in c.execute("SELECT name FROM sqlite_schema WHERE type='table'"):
        if table not in supported_tables and c.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
            raise UnsupportedCandidateOperation('Candidate integration not implemented: ' + table)
    dataset_id = c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0]
    meta = c.execute('SELECT week_start,polr_reminder_dismissed_local_date FROM dataset_meta').fetchone()
    if tuple(meta) != (6, None):
        raise UnsupportedCandidateOperation('Candidate configuration history not implemented')
    verify_schema4_history(_rows(c, 'projects'), _rows(c, 'tasks'),
                          _rows(c, 'committed_requests'), dataset_id)
    return CandidateVerification()
