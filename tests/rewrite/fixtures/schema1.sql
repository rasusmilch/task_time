-- Historical refusal fixture from f4828c4fcbc9354ffe439792a790d2fd46e41f7f; never runtime schema authority.

CREATE TABLE dataset_meta (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), dataset_id TEXT NOT NULL UNIQUE CHECK(length(dataset_id)=36 AND substr(dataset_id,9,1)='-' AND substr(dataset_id,14,1)='-' AND substr(dataset_id,19,1)='-' AND substr(dataset_id,24,1)='-' AND length(replace(dataset_id,'-',''))=32 AND replace(dataset_id,'-','') NOT GLOB '*[^0-9a-f]*'),
 timezone TEXT NOT NULL CHECK(length(timezone)>0),
 week_start INTEGER NOT NULL CHECK(week_start BETWEEN 0 AND 6),
 polr_reminder_dismissed_local_date TEXT CHECK(polr_reminder_dismissed_local_date IS NULL OR
   (length(polr_reminder_dismissed_local_date)=10 AND polr_reminder_dismissed_local_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'))
) STRICT;
CREATE TABLE projects (
 project_id TEXT PRIMARY KEY CHECK(length(project_id)=36 AND substr(project_id,9,1)='-' AND substr(project_id,14,1)='-' AND substr(project_id,19,1)='-' AND substr(project_id,24,1)='-' AND length(replace(project_id,'-',''))=32 AND replace(project_id,'-','') NOT GLOB '*[^0-9a-f]*'), name TEXT NOT NULL CHECK(length(trim(name))>0),
 version INTEGER NOT NULL CHECK(version>0), is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
 created_utc_us INTEGER NOT NULL CHECK(created_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 updated_utc_us INTEGER NOT NULL CHECK(updated_utc_us BETWEEN -62135596800000000 AND 253402300799999999)
) STRICT;
CREATE TABLE tasks (
 task_id TEXT PRIMARY KEY CHECK(length(task_id)=36 AND substr(task_id,9,1)='-' AND substr(task_id,14,1)='-' AND substr(task_id,19,1)='-' AND substr(task_id,24,1)='-' AND length(replace(task_id,'-',''))=32 AND replace(task_id,'-','') NOT GLOB '*[^0-9a-f]*'), project_id TEXT REFERENCES projects(project_id),
 name TEXT NOT NULL CHECK(length(trim(name))>0), version INTEGER NOT NULL CHECK(version>0),
 is_deleted INTEGER NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
 created_utc_us INTEGER NOT NULL CHECK(created_utc_us BETWEEN -62135596800000000 AND 253402300799999999),
 updated_utc_us INTEGER NOT NULL CHECK(updated_utc_us BETWEEN -62135596800000000 AND 253402300799999999)
) STRICT;
CREATE TABLE committed_requests (
 commit_seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE CHECK(length(request_id)=36 AND substr(request_id,9,1)='-' AND substr(request_id,14,1)='-' AND substr(request_id,19,1)='-' AND substr(request_id,24,1)='-' AND length(replace(request_id,'-',''))=32 AND replace(request_id,'-','') NOT GLOB '*[^0-9a-f]*'),
 operation TEXT NOT NULL, request_bytes BLOB NOT NULL, result_bytes BLOB NOT NULL,
 action_utc_us INTEGER NOT NULL CHECK(action_utc_us BETWEEN -62135596800000000 AND 253402300799999999)
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
CREATE TRIGGER immutable_committed_requests_update BEFORE UPDATE ON committed_requests BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
CREATE TRIGGER immutable_committed_requests_delete BEFORE DELETE ON committed_requests BEGIN SELECT RAISE(ABORT,'immutable evidence'); END;
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
