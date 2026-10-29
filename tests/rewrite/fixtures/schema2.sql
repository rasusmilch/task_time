-- Historical refusal fixture from 393d906e15be8cc43b3ec907ef93838835f4f2ea; never runtime schema authority.

CREATE TABLE dataset_meta (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), dataset_id TEXT NOT NULL UNIQUE CHECK(length(dataset_id)=36 AND substr(dataset_id,9,1)='-' AND substr(dataset_id,14,1)='-' AND substr(dataset_id,19,1)='-' AND substr(dataset_id,24,1)='-' AND length(replace(dataset_id,'-',''))=32 AND replace(dataset_id,'-','') NOT GLOB '*[^0-9a-f]*'),
 timezone TEXT NOT NULL CHECK(length(timezone)>0),
 week_start INTEGER NOT NULL CHECK(week_start BETWEEN 0 AND 6),
 polr_reminder_dismissed_local_date TEXT CHECK(polr_reminder_dismissed_local_date IS NULL OR
   (length(polr_reminder_dismissed_local_date)=10 AND polr_reminder_dismissed_local_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'))
) STRICT;
CREATE TABLE projects (
 project_id TEXT PRIMARY KEY CHECK(length(project_id)=36 AND substr(project_id,9,1)='-' AND substr(project_id,14,1)='-' AND substr(project_id,19,1)='-' AND substr(project_id,24,1)='-' AND length(replace(project_id,'-',''))=32 AND replace(project_id,'-','') NOT GLOB '*[^0-9a-f]*'), name TEXT NOT NULL CHECK(length(trim(name))>0),
 version INTEGER NOT NULL CHECK(version>0), is_archived INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0,1)),
 archived_at_utc_us INTEGER CHECK(archived_at_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 created_request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 created_utc_us INTEGER NOT NULL CHECK(created_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 updated_utc_us INTEGER NOT NULL CHECK(updated_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 CHECK((is_archived=0 AND archived_at_utc_us IS NULL) OR (is_archived=1 AND archived_at_utc_us IS NOT NULL))
) STRICT;
CREATE TABLE tasks (
 task_id TEXT PRIMARY KEY CHECK(length(task_id)=36 AND substr(task_id,9,1)='-' AND substr(task_id,14,1)='-' AND substr(task_id,19,1)='-' AND substr(task_id,24,1)='-' AND length(replace(task_id,'-',''))=32 AND replace(task_id,'-','') NOT GLOB '*[^0-9a-f]*'), project_id TEXT REFERENCES projects(project_id),
 parent_task_id TEXT REFERENCES tasks(task_id) CHECK(parent_task_id IS NULL OR parent_task_id!=task_id),
 name TEXT NOT NULL CHECK(length(trim(name))>0), version INTEGER NOT NULL CHECK(version>0),
 is_archived INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0,1)),
 archived_at_utc_us INTEGER CHECK(archived_at_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 created_request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 created_utc_us INTEGER NOT NULL CHECK(created_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 updated_utc_us INTEGER NOT NULL CHECK(updated_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 CHECK((is_archived=0 AND archived_at_utc_us IS NULL) OR (is_archived=1 AND archived_at_utc_us IS NOT NULL))
) STRICT;
CREATE TABLE committed_requests (
 commit_seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE CHECK(length(request_id)=36 AND substr(request_id,9,1)='-' AND substr(request_id,14,1)='-' AND substr(request_id,19,1)='-' AND substr(request_id,24,1)='-' AND length(replace(request_id,'-',''))=32 AND replace(request_id,'-','') NOT GLOB '*[^0-9a-f]*'),
 operation TEXT NOT NULL, receipt_class TEXT NOT NULL CHECK(receipt_class IN ('administrative','protected')),
 request_bytes BLOB NOT NULL, result_bytes BLOB NOT NULL,
 action_utc_us INTEGER NOT NULL CHECK(action_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 CHECK(receipt_class=CASE WHEN operation IN ('archive_project','archive_task','assign_task_to_project','create_project','create_task','move_task_branch','rename_project','rename_task','unarchive_project','unarchive_task')
       THEN 'administrative' ELSE 'protected' END)
) STRICT;
CREATE TABLE work_entries (
 entry_id TEXT PRIMARY KEY CHECK(length(entry_id)=36 AND substr(entry_id,9,1)='-' AND substr(entry_id,14,1)='-' AND substr(entry_id,19,1)='-' AND substr(entry_id,24,1)='-' AND length(replace(entry_id,'-',''))=32 AND replace(entry_id,'-','') NOT GLOB '*[^0-9a-f]*'), task_id TEXT NOT NULL REFERENCES tasks(task_id),
 kind TEXT NOT NULL CHECK(kind IN ('timed','date_only')),
 original_start_utc_us INTEGER CHECK(original_start_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
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
 start_utc_us INTEGER CHECK(start_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 stop_utc_us INTEGER CHECK(stop_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 work_date TEXT, duration_us INTEGER,
 is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)), comment TEXT NOT NULL,
 audit_utc_us INTEGER NOT NULL CHECK(audit_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
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
 task_id TEXT NOT NULL, start_utc_us INTEGER NOT NULL CHECK(start_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 version INTEGER NOT NULL CHECK(version>0),
 FOREIGN KEY(entry_id,task_id) REFERENCES work_entries(entry_id,task_id)
) STRICT;
CREATE TABLE active_start_corrections (
 entry_id TEXT NOT NULL REFERENCES work_entries(entry_id), version INTEGER NOT NULL CHECK(version>1),
 prior_start_utc_us INTEGER NOT NULL CHECK(prior_start_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 corrected_start_utc_us INTEGER NOT NULL CHECK(corrected_start_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 audit_utc_us INTEGER NOT NULL CHECK(audit_utc_us BETWEEN -62135596800000000 AND 253402300799999999 AND corrected_start_utc_us<=audit_utc_us),
 comment TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id)
 DEFERRABLE INITIALLY DEFERRED, PRIMARY KEY(entry_id,version)
) STRICT;
CREATE INDEX tasks_project ON tasks(project_id);
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

CREATE TABLE timesheet_exports (
 export_id TEXT PRIMARY KEY CHECK(length(export_id)=36 AND substr(export_id,9,1)='-' AND substr(export_id,14,1)='-' AND substr(export_id,19,1)='-' AND substr(export_id,24,1)='-' AND length(replace(export_id,'-',''))=32 AND replace(export_id,'-','') NOT GLOB '*[^0-9a-f]*'),
 created_request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 registered_utc_us INTEGER NOT NULL CHECK(registered_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 cutoff_utc_us INTEGER NOT NULL CHECK(cutoff_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
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

CREATE TABLE polr_confirmation_batches (
 batch_id TEXT PRIMARY KEY CHECK(length(batch_id)=36 AND substr(batch_id,9,1)='-' AND substr(batch_id,14,1)='-' AND substr(batch_id,19,1)='-' AND substr(batch_id,24,1)='-' AND length(replace(batch_id,'-',''))=32 AND replace(batch_id,'-','') NOT GLOB '*[^0-9a-f]*'),
 created_request_id TEXT NOT NULL UNIQUE REFERENCES committed_requests(request_id) DEFERRABLE INITIALLY DEFERRED,
 audit_utc_us INTEGER NOT NULL CHECK(audit_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 source_export_id TEXT REFERENCES timesheet_exports(export_id),
 mode TEXT NOT NULL CHECK(mode IN ('source','manual')),
 CHECK((mode='source' AND source_export_id IS NOT NULL) OR (mode='manual' AND source_export_id IS NULL))
) STRICT;
CREATE TABLE polr_confirmation_cells (
 batch_id TEXT NOT NULL REFERENCES polr_confirmation_batches(batch_id),
 task_id TEXT NOT NULL REFERENCES tasks(task_id),
 work_date TEXT NOT NULL CHECK(length(work_date)=10 AND work_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
 confirmed_quarters INTEGER NOT NULL CHECK(confirmed_quarters BETWEEN 0 AND 368934881474191032),
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
CREATE TRIGGER sealed_timesheet_export_tasks BEFORE INSERT ON timesheet_export_tasks WHEN EXISTS(SELECT 1 FROM timesheet_exports WHERE export_id=NEW.export_id) BEGIN SELECT RAISE(ABORT,'sealed export'); END;
CREATE TRIGGER sealed_timesheet_export_week_basis BEFORE INSERT ON timesheet_export_week_basis WHEN EXISTS(SELECT 1 FROM timesheet_exports WHERE export_id=NEW.export_id) BEGIN SELECT RAISE(ABORT,'sealed export'); END;
CREATE TRIGGER sealed_timesheet_export_cells BEFORE INSERT ON timesheet_export_cells WHEN EXISTS(SELECT 1 FROM timesheet_exports WHERE export_id=NEW.export_id) BEGIN SELECT RAISE(ABORT,'sealed export'); END;
CREATE TRIGGER immutable_work_revisions_update BEFORE UPDATE ON work_revisions BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_work_revisions_delete BEFORE DELETE ON work_revisions BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_active_start_corrections_update BEFORE UPDATE ON active_start_corrections BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_active_start_corrections_delete BEFORE DELETE ON active_start_corrections BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_timesheet_exports_update BEFORE UPDATE ON timesheet_exports BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_timesheet_exports_delete BEFORE DELETE ON timesheet_exports BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_timesheet_export_tasks_update BEFORE UPDATE ON timesheet_export_tasks BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_timesheet_export_tasks_delete BEFORE DELETE ON timesheet_export_tasks BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_timesheet_export_week_basis_update BEFORE UPDATE ON timesheet_export_week_basis BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_timesheet_export_week_basis_delete BEFORE DELETE ON timesheet_export_week_basis BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_timesheet_export_cells_update BEFORE UPDATE ON timesheet_export_cells BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_timesheet_export_cells_delete BEFORE DELETE ON timesheet_export_cells BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_polr_confirmation_batches_update BEFORE UPDATE ON polr_confirmation_batches BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_polr_confirmation_batches_delete BEFORE DELETE ON polr_confirmation_batches BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_polr_confirmation_cells_update BEFORE UPDATE ON polr_confirmation_cells BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_polr_confirmation_cells_delete BEFORE DELETE ON polr_confirmation_cells BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;

CREATE TRIGGER immutable_committed_requests_update BEFORE UPDATE ON committed_requests
 BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_committed_requests_delete BEFORE DELETE ON committed_requests
 WHEN OLD.receipt_class='protected'
 BEGIN SELECT RAISE(ABORT,'immutable protected evidence'); END;
CREATE TRIGGER tasks_identity_immutable BEFORE UPDATE OF task_id,created_request_id,created_utc_us ON tasks BEGIN SELECT RAISE(ABORT,'immutable entity identity'); END;
CREATE TRIGGER projects_identity_immutable BEFORE UPDATE OF project_id,created_request_id,created_utc_us ON projects BEGIN SELECT RAISE(ABORT,'immutable entity identity'); END;

CREATE TRIGGER tasks_forest_insert BEFORE INSERT ON tasks
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

CREATE TRIGGER tasks_forest_update BEFORE UPDATE OF parent_task_id,project_id ON tasks
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

CREATE TRIGGER work_entries_eligible_task BEFORE INSERT ON work_entries
 BEGIN
 SELECT RAISE(ABORT,'new recording requires an active leaf') WHERE
   EXISTS(SELECT 1 FROM tasks WHERE parent_task_id=NEW.task_id) OR (
   WITH RECURSIVE path(task_id,parent_task_id,project_id,is_archived,n) AS (
     SELECT task_id,parent_task_id,project_id,is_archived,1 FROM tasks WHERE task_id=NEW.task_id
     UNION ALL SELECT p.task_id,p.parent_task_id,p.project_id,p.is_archived,a.n+1 FROM tasks p JOIN path a ON p.task_id=a.parent_task_id WHERE a.n<3
   ) SELECT EXISTS(SELECT 1 FROM path WHERE is_archived=1)
       OR EXISTS(SELECT 1 FROM path a JOIN projects p ON a.project_id=p.project_id WHERE p.is_archived=1)
 );
 END;

CREATE TRIGGER active_timer_eligible_task BEFORE INSERT ON active_timer
 BEGIN
 SELECT RAISE(ABORT,'new recording requires an active leaf') WHERE
   EXISTS(SELECT 1 FROM tasks WHERE parent_task_id=NEW.task_id) OR (
   WITH RECURSIVE path(task_id,parent_task_id,project_id,is_archived,n) AS (
     SELECT task_id,parent_task_id,project_id,is_archived,1 FROM tasks WHERE task_id=NEW.task_id
     UNION ALL SELECT p.task_id,p.parent_task_id,p.project_id,p.is_archived,a.n+1 FROM tasks p JOIN path a ON p.task_id=a.parent_task_id WHERE a.n<3
   ) SELECT EXISTS(SELECT 1 FROM path WHERE is_archived=1)
       OR EXISTS(SELECT 1 FROM path a JOIN projects p ON a.project_id=p.project_id WHERE p.is_archived=1)
 );
 END;

CREATE TRIGGER tasks_archive_active BEFORE UPDATE OF is_archived ON tasks WHEN NEW.is_archived=1
 BEGIN
 SELECT RAISE(ABORT,'archive would hide active timer') WHERE (
   WITH RECURSIVE branch(task_id,n) AS (
     SELECT NEW.task_id,1 UNION ALL SELECT t.task_id,b.n+1 FROM tasks t JOIN branch b ON t.parent_task_id=b.task_id WHERE b.n<3
   ) SELECT EXISTS(SELECT 1 FROM branch JOIN active_timer USING(task_id))
 );
 END;
CREATE TRIGGER projects_archive_active BEFORE UPDATE OF is_archived ON projects WHEN NEW.is_archived=1
 AND EXISTS(SELECT 1 FROM active_timer a JOIN tasks t USING(task_id) WHERE t.project_id=NEW.project_id)
 BEGIN SELECT RAISE(ABORT,'archive would hide active timer'); END;
