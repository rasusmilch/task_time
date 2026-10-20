"""Complete task/project/timer use cases over the worker-owned SQLite adapter."""

from __future__ import annotations

from contextlib import contextmanager

from .accounting import calculate
from .records import Outcome, Request, StaleState, integer, uuid_text
from .sqlite_store import SQLiteStore
from .timekeeping import instant, local_date, resolve_start, resolve_minute, parse_date, parse_duration, week_dates


def name_text(value: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError("A nonempty name is required")
    return value.strip()


class TimerService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def _make(self, operation: str, request_id: str, action_utc_us: int, arguments: dict) -> Outcome:
        return self.execute(Request.make(request_id, self.store.dataset_id, operation, action_utc_us, **arguments))

    def create_task(self, task_id: str, name: str, project_id: str | None = None, *,
                    request_id: str, action_utc_us: int) -> Outcome:
        return self._make("create_task", request_id, action_utc_us, dict(task_id=task_id, name=name, project_id=project_id))

    def rename_task(self, task_id: str, name: str, *, expected_version: int,
                    request_id: str, action_utc_us: int) -> Outcome:
        return self._make("rename_task", request_id, action_utc_us, dict(task_id=task_id, name=name, expected_version=expected_version))

    def create_project(self, project_id: str, name: str, *, request_id: str, action_utc_us: int) -> Outcome:
        return self._make("create_project", request_id, action_utc_us, dict(project_id=project_id, name=name))

    def rename_project(self, project_id: str, name: str, *, expected_version: int,
                       request_id: str, action_utc_us: int) -> Outcome:
        return self._make("rename_project", request_id, action_utc_us, dict(project_id=project_id, name=name, expected_version=expected_version))

    def assign_task_to_project(self, task_id: str, project_id: str | None, *, expected_version: int,
                               request_id: str, action_utc_us: int) -> Outcome:
        return self._make("assign_task_to_project", request_id, action_utc_us,
                          dict(task_id=task_id, project_id=project_id, expected_version=expected_version))

    def start_timer(self, task_id: str, entry_id: str, *, expected_task_version: int,
                    request_id: str, action_utc_us: int) -> Outcome:
        return self._make("start_timer", request_id, action_utc_us,
                          dict(task_id=task_id, entry_id=entry_id, expected_task_version=expected_task_version))

    def stop_timer(self, entry_id: str, *, expected_version: int, request_id: str, action_utc_us: int) -> Outcome:
        return self._make("stop_timer", request_id, action_utc_us,
                          dict(entry_id=entry_id, expected_version=expected_version))

    def switch_timer(self, expected_active_entry_id: str, next_task_id: str, next_entry_id: str, *,
                     expected_active_version: int, expected_task_version: int,
                     request_id: str, action_utc_us: int) -> Outcome:
        return self._make("switch_timer", request_id, action_utc_us,
                          dict(expected_active_entry_id=expected_active_entry_id,
                               expected_active_version=expected_active_version, next_task_id=next_task_id,
                               next_entry_id=next_entry_id, expected_task_version=expected_task_version))

    def correct_active_start(self, entry_id: str, date_text: str, time_text: str, *, expected_version: int,
                             occurrence: str | None = None, comment: str = "",
                             request_id: str, action_utc_us: int) -> Outcome:
        return self._make("correct_active_start", request_id, action_utc_us,
                          dict(entry_id=entry_id, expected_version=expected_version, date_text=date_text,
                               time_text=time_text, occurrence=occurrence, comment=comment))

    def add_timed_work(self, task_id: str, entry_id: str, start_date: str, start_time: str,
                       end_date: str, end_time: str, *, start_occurrence: str | None = None,
                       end_occurrence: str | None = None, comment: str = "",
                       request_id: str, action_utc_us: int) -> Outcome:
        return self._make("add_timed_work", request_id, action_utc_us,
                          dict(task_id=task_id, entry_id=entry_id, start_date=start_date, start_time=start_time,
                               end_date=end_date, end_time=end_time, start_occurrence=start_occurrence,
                               end_occurrence=end_occurrence, comment=comment))

    def add_date_only_work(self, task_id: str, entry_id: str, work_date: str, duration_text: str, *,
                           comment: str = "", request_id: str, action_utc_us: int) -> Outcome:
        return self._make("add_date_only_work", request_id, action_utc_us,
                          dict(task_id=task_id, entry_id=entry_id, work_date=work_date,
                               duration_text=duration_text, comment=comment))

    def edit_closed_timed_work(self, task_id: str, entry_id: str, start_date: str, start_time: str,
                               end_date: str, end_time: str, *, expected_revision: int,
                               start_occurrence: str | None = None, end_occurrence: str | None = None,
                               comment: str = "", request_id: str, action_utc_us: int) -> Outcome:
        return self._make("edit_closed_timed_work", request_id, action_utc_us,
                          dict(task_id=task_id, entry_id=entry_id, start_date=start_date, start_time=start_time,
                               end_date=end_date, end_time=end_time, start_occurrence=start_occurrence,
                               end_occurrence=end_occurrence, comment=comment, expected_revision=expected_revision))

    def edit_date_only_work(self, task_id: str, entry_id: str, work_date: str, duration_text: str, *,
                            expected_revision: int, comment: str = "", request_id: str, action_utc_us: int) -> Outcome:
        return self._make("edit_date_only_work", request_id, action_utc_us,
                          dict(task_id=task_id, entry_id=entry_id, work_date=work_date, duration_text=duration_text,
                               expected_revision=expected_revision, comment=comment))

    def delete_work_entry(self, task_id: str, entry_id: str, *, expected_revision: int,
                          comment: str = "", request_id: str, action_utc_us: int) -> Outcome:
        return self._make("delete_work_entry", request_id, action_utc_us,
                          dict(task_id=task_id, entry_id=entry_id, expected_revision=expected_revision, comment=comment))

    def set_week_start(self, week_start: int, *, expected_week_start: int,
                       request_id: str, action_utc_us: int) -> Outcome:
        return self._make("set_week_start", request_id, action_utc_us,
                          dict(week_start=week_start, expected_week_start=expected_week_start))

    @staticmethod
    def _reviewed_work(c, task_id, entry_id, expected_revision, kind=None):
        uuid_text(task_id)
        uuid_text(entry_id)
        integer(expected_revision, "Revision", 1, 2**63 - 1)
        entry = c.execute("SELECT * FROM work_entries WHERE entry_id=? AND task_id=?", (entry_id, task_id)).fetchone()
        if (entry is None or entry["current_revision"] != expected_revision
                or (kind is not None and entry["kind"] != kind)):
            raise StaleState("Reviewed work identity, kind or revision changed; active work is not closed work")
        row = c.execute("SELECT * FROM work_revisions WHERE entry_id=? AND revision=?", (entry_id, expected_revision)).fetchone()
        if row is None or row["is_deleted"]:
            raise StaleState("Work is missing or deleted")
        return dict(row)

    @staticmethod
    def _append_revision(c, request, entry_id, revision, kind, start, stop, day, duration, deleted, comment):
        c.execute("""INSERT INTO work_revisions
          (entry_id,revision,kind,start_utc_us,stop_utc_us,work_date,duration_us,is_deleted,comment,audit_utc_us,request_id)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                  (entry_id, revision, kind, start, stop, day, duration, deleted, comment.strip(),
                   request.action_utc_us, request.request_id))
        c.execute("UPDATE work_entries SET current_revision=? WHERE entry_id=?", (revision, entry_id))
        return {"entry_id": entry_id, "revision": revision}

    def _work_mutation(self, c, request, a):
        op = request.operation
        if type(a["comment"]) is not str:
            raise ValueError("Work comment must be text")
        adding = op.startswith("add_")
        kind = "timed" if op in ("add_timed_work", "edit_closed_timed_work") else "date_only"
        if adding:
            uuid_text(a["task_id"])
            uuid_text(a["entry_id"])
            if not c.execute("SELECT 1 FROM tasks WHERE task_id=? AND is_deleted=0", (a["task_id"],)).fetchone():
                raise StaleState("Task is missing or deleted")
            old, revision = None, 1
        else:
            old = self._reviewed_work(c, a["task_id"], a["entry_id"], a["expected_revision"],
                                      None if op == "delete_work_entry" else kind)
            kind, revision = old["kind"], old["revision"] + 1
        if op == "delete_work_entry":
            return self._append_revision(c, request, a["entry_id"], revision, kind,
                                         old["start_utc_us"], old["stop_utc_us"], old["work_date"],
                                         old["duration_us"], 1, a["comment"])
        start = stop = day = duration = None
        if kind == "timed":
            start = resolve_minute(a["start_date"], a["start_time"], a["start_occurrence"], self.store.zone,
                                   original=old["start_utc_us"] if old else None)
            stop = resolve_minute(a["end_date"], a["end_time"], a["end_occurrence"], self.store.zone,
                                  original=old["stop_utc_us"] if old else None)
            if old and (start, stop) == (old["start_utc_us"], old["stop_utc_us"]):
                return None
            if stop <= start:
                raise ValueError("End must be strictly after start in UTC")
            if stop > request.action_utc_us:
                raise ValueError("Timed work end cannot be later than the accepted observation")
        else:
            day, duration = parse_date(a["work_date"]).isoformat(), parse_duration(a["duration_text"])
            if old and (day, duration) == (old["work_date"], old["duration_us"]):
                return None
        if adding:
            c.execute("""INSERT INTO work_entries
              (entry_id,task_id,kind,original_start_utc_us,current_revision,created_request_id) VALUES(?,?,?,?,1,?)""",
                      (a["entry_id"], a["task_id"], kind, start, request.request_id))
        return self._append_revision(c, request, a["entry_id"], revision, kind,
                                     start, stop, day, duration, 0, a["comment"])

    @staticmethod
    def _task(c, task_id, version):
        uuid_text(task_id)
        row = c.execute("SELECT * FROM tasks WHERE task_id=? AND is_deleted=0", (task_id,)).fetchone()
        if row is None:
            raise StaleState("Task is missing or deleted")
        integer(version, "Task version", 1, 2**63 - 1)
        if row["version"] != version:
            raise StaleState("Task changed; refresh before trying again")
        return row

    @staticmethod
    def _project(c, project_id):
        if project_id is None:
            return
        uuid_text(project_id)
        if not c.execute("SELECT 1 FROM projects WHERE project_id=? AND is_deleted=0", (project_id,)).fetchone():
            raise StaleState("Project is missing or deleted")

    @staticmethod
    def _active(c, entry_id, version):
        uuid_text(entry_id)
        integer(version, "Active version", 1, 2**63 - 1)
        active = c.execute("SELECT * FROM active_timer").fetchone()
        if not active or active["entry_id"] != entry_id or active["version"] != version:
            raise StaleState("The reviewed active timer changed or stopped")
        return active

    @staticmethod
    def _open(c, task_id, entry_id, request):
        uuid_text(entry_id)
        c.execute("INSERT INTO work_entries(entry_id,task_id,kind,original_start_utc_us,current_revision,created_request_id) VALUES(?,?,'timed',?,NULL,?)",
                  (entry_id, task_id, request.action_utc_us, request.request_id))
        c.execute("INSERT INTO active_timer(singleton,entry_id,task_id,start_utc_us,version) VALUES(1,?,?,?,1)", (entry_id, task_id, request.action_utc_us))

    @staticmethod
    def _close(c, active, request):
        if request.action_utc_us <= active["start_utc_us"]:
            raise ValueError("Stop must be strictly after the effective start; check the clock or correct active start")
        c.execute("DELETE FROM active_timer WHERE entry_id=?", (active["entry_id"],))
        c.execute("INSERT INTO work_revisions(entry_id,revision,kind,start_utc_us,stop_utc_us,is_deleted,comment,audit_utc_us,request_id) VALUES(?,1,'timed',?,?,0,'',?,?)",
                  (active["entry_id"], active["start_utc_us"], request.action_utc_us,
                   request.action_utc_us, request.request_id))
        c.execute("UPDATE work_entries SET current_revision=1 WHERE entry_id=?", (active["entry_id"],))

    def execute(self, request: Request) -> Outcome:
        # The transaction resolves exact receipts before calling this current-state validator.
        def operation(c):
            a, op, now = request.args(), request.operation, request.action_utc_us
            local_date(now, self.store.zone)
            expected = {
                "create_task": {"task_id", "name", "project_id"},
                "rename_task": {"task_id", "name", "expected_version"},
                "create_project": {"project_id", "name"},
                "rename_project": {"project_id", "name", "expected_version"},
                "assign_task_to_project": {"task_id", "project_id", "expected_version"},
                "start_timer": {"task_id", "entry_id", "expected_task_version"},
                "stop_timer": {"entry_id", "expected_version"},
                "switch_timer": {"expected_active_entry_id", "expected_active_version", "next_task_id", "next_entry_id", "expected_task_version"},
                "correct_active_start": {"entry_id", "expected_version", "date_text", "time_text", "occurrence", "comment"},
            }
            timed_fields = {"task_id", "entry_id", "start_date", "start_time", "end_date", "end_time",
                            "start_occurrence", "end_occurrence", "comment"}
            dated_fields = {"task_id", "entry_id", "work_date", "duration_text", "comment"}
            expected.update({"add_timed_work": timed_fields, "add_date_only_work": dated_fields,
                             "edit_closed_timed_work": timed_fields | {"expected_revision"},
                             "edit_date_only_work": dated_fields | {"expected_revision"},
                             "delete_work_entry": {"task_id", "entry_id", "expected_revision", "comment"},
                             "set_week_start": {"week_start", "expected_week_start"}})
            if op not in expected or set(a) != expected[op]:
                raise ValueError("Unknown operation or incorrect request fields")
            if op in ("add_timed_work", "add_date_only_work", "edit_closed_timed_work", "edit_date_only_work", "delete_work_entry"):
                return self._work_mutation(c, request, a)
            if op == "set_week_start":
                new = integer(a["week_start"], "Week start", 0, 6)
                prior = integer(a["expected_week_start"], "Reviewed week start", 0, 6)
                if self.store.week_start != prior:
                    raise StaleState("Reviewed week start changed; refresh before trying again")
                if new == prior:
                    return None
                c.execute("UPDATE dataset_meta SET week_start=? WHERE singleton=1", (new,))
                return {"week_start": new}
            if op in ("create_task", "create_project"):
                entity = "task" if op == "create_task" else "project"
                key, name = uuid_text(a[f"{entity}_id"]), name_text(a["name"])
                if entity == "task":
                    self._project(c, a["project_id"])
                    c.execute("INSERT INTO tasks(task_id,project_id,name,version,is_deleted,created_utc_us,updated_utc_us) VALUES(?,?,?,1,0,?,?)", (key, a["project_id"], name, now, now))
                else:
                    c.execute("INSERT INTO projects(project_id,name,version,is_deleted,created_utc_us,updated_utc_us) VALUES(?,?,1,0,?,?)", (key, name, now, now))
                return {f"{entity}_id": key, "version": 1}
            if op in ("rename_task", "rename_project"):
                entity = "task" if op == "rename_task" else "project"
                key = uuid_text(a[f"{entity}_id"])
                version = integer(a["expected_version"], "Version", 1, 2**63 - 1)
                row = c.execute(f"SELECT * FROM {entity}s WHERE {entity}_id=? AND is_deleted=0", (key,)).fetchone()
                if row is None or row["version"] != version:
                    raise StaleState("Reviewed identity/version changed")
                name = name_text(a["name"])
                if name == row["name"]:
                    return None
                c.execute(f"UPDATE {entity}s SET name=?, version=version+1, updated_utc_us=? WHERE {entity}_id=?", (name, now, key))
                return {f"{entity}_id": key, "version": version + 1}
            if op == "assign_task_to_project":
                row = self._task(c, a["task_id"], a["expected_version"])
                self._project(c, a["project_id"])
                if row["project_id"] == a["project_id"]:
                    return None
                c.execute("UPDATE tasks SET project_id=?,version=version+1,updated_utc_us=? WHERE task_id=?", (a["project_id"], now, a["task_id"]))
                return {"task_id": a["task_id"], "version": row["version"] + 1}
            if op == "start_timer":
                self._task(c, a["task_id"], a["expected_task_version"])
                if c.execute("SELECT 1 FROM active_timer").fetchone():
                    raise StaleState("Another timer is active; use Switch")
                self._open(c, a["task_id"], a["entry_id"], request)
                return {"entry_id": a["entry_id"], "version": 1}
            if op == "stop_timer":
                active = self._active(c, a["entry_id"], a["expected_version"])
                self._close(c, active, request)
                return {"entry_id": active["entry_id"], "revision": 1}
            if op == "switch_timer":
                active = self._active(c, a["expected_active_entry_id"], a["expected_active_version"])
                self._task(c, a["next_task_id"], a["expected_task_version"])
                if active["task_id"] == a["next_task_id"]:
                    raise ValueError("Switch requires a different task")
                self._close(c, active, request)
                self._open(c, a["next_task_id"], a["next_entry_id"], request)
                return {"closed_entry_id": active["entry_id"], "entry_id": a["next_entry_id"], "version": 1}
            active = self._active(c, a["entry_id"], a["expected_version"])
            if type(a["comment"]) is not str:
                raise ValueError("Correction comment must be text")
            corrected = resolve_start(active["start_utc_us"], a["date_text"], a["time_text"], a["occurrence"], self.store.zone)
            if corrected == active["start_utc_us"]:
                return None
            if corrected > now:
                raise ValueError("Corrected start cannot be later than the accepted observation")
            version = active["version"] + 1
            c.execute("INSERT INTO active_start_corrections(entry_id,version,prior_start_utc_us,corrected_start_utc_us,audit_utc_us,comment,request_id) VALUES(?,?,?,?,?,?,?)",
                      (active["entry_id"], version, active["start_utc_us"], corrected, now, a["comment"].strip(), request.request_id))
            c.execute("UPDATE active_timer SET start_utc_us=?,version=? WHERE entry_id=?", (corrected, version, active["entry_id"]))
            return {"entry_id": active["entry_id"], "version": version}
        return self.store.transact(request, operation)

    def reconcile_request(self, request: Request) -> Outcome:
        evidence = self.store.reconcile(request)
        if evidence.status == "unverified" and self.store._retired is not None:
            try:
                self.store._recover_connection()  # Explicit reconciliation may retry cleanup, never a new mutation.
            except Exception as exc:
                if evidence.error:
                    exc.add_note(f"Independent evidence: {evidence.error!r}")
                return Outcome("unverified", error=exc)
            return self.store.reconcile(request)
        return evidence

    @contextmanager
    def _read_transaction(self):
        self.store._recover_connection()
        c = self.store.connection
        try:
            c.execute("BEGIN")
            self.store.assert_lifecycle(c)
            yield c
            c.execute("COMMIT")
        except BaseException as primary:
            try:
                if c.in_transaction:
                    c.execute("ROLLBACK")
            except Exception as secondary:
                primary.add_note(f"Read rollback failed: {secondary!r}")
            self.store.connection, self.store._retired = None, c
            try:
                c.close()
                self.store._retired = None
            except Exception as secondary:
                primary.add_note(f"Read close failed: {secondary!r}")
            raise

    def read_current_state(self, *, cutoff_utc_us: int) -> dict:
        instant(cutoff_utc_us)
        with self._read_transaction() as c:
            tasks = [dict(r) for r in c.execute("SELECT * FROM tasks ORDER BY created_utc_us,task_id")]
            projects = [dict(r) for r in c.execute("SELECT * FROM projects WHERE is_deleted=0 ORDER BY name,project_id")]
            rows = [dict(r) for r in c.execute("""SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r
              ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0""")]
            row = c.execute("SELECT * FROM active_timer").fetchone()
            active = dict(row) if row else None
            weekday = self.store.week_start
        # Calculation failure must not hide the current identities or disable recovery controls.
        try:
            report = calculate(tasks, rows, active, cutoff_utc_us, self.store.zone, weekday)
            error = None
        except (ValueError, OverflowError) as exc:
            report, error = None, str(exc)
        return {"dataset_id": self.store.dataset_id, "timezone": self.store.timezone,
                "tasks": tasks, "projects": projects, "active": active, "report": report,
                "calculation_error": error, "cutoff_utc_us": cutoff_utc_us, "week_start": weekday}


    def read_task_work_history(self, task_id: str, *, cutoff_utc_us: int, period: str = "current_week",
                               start_date: str | None = None, end_date: str | None = None) -> list[dict]:
        """Current effective daily rows, newest date first; never an audit-clock replay."""
        from .work_history import build_history
        uuid_text(task_id)
        instant(cutoff_utc_us)
        with self._read_transaction() as c:
            if not c.execute("SELECT 1 FROM tasks WHERE task_id=?", (task_id,)).fetchone():
                raise ValueError("Task identity is unknown")
            if period == "current_week" and start_date is None and end_date is None:
                _, first, last = week_dates(cutoff_utc_us, self.store.zone, self.store.week_start)
            elif period == "all" and start_date is None and end_date is None:
                first = last = None
            elif period == "custom":
                first, last = parse_date(start_date), parse_date(end_date)
                from datetime import date
                if last < first or last == date.max:
                    raise ValueError("Require ordered inclusive dates with a representable end boundary")
            else:
                raise ValueError("Period must be current_week, custom with both dates, or all without bounds")
            rows = [dict(r) for r in c.execute("""SELECT e.task_id,e.original_start_utc_us,e.created_request_id,r.*
              FROM work_entries e JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision
              WHERE e.task_id=? AND r.is_deleted=0""", (task_id,))]
            row = c.execute("""SELECT a.*,e.original_start_utc_us,e.created_request_id FROM active_timer a
              JOIN work_entries e USING(entry_id) WHERE a.task_id=?""", (task_id,)).fetchone()
            active = dict(row) if row else None
            if active:
                audit = c.execute("SELECT comment,audit_utc_us,request_id FROM active_start_corrections WHERE entry_id=? ORDER BY version DESC LIMIT 1",
                                  (active["entry_id"],)).fetchone()
                if audit:
                    active.update(dict(audit))
                else:
                    audit = c.execute("SELECT action_utc_us FROM committed_requests WHERE request_id=?", (active["created_request_id"],)).fetchone()
                    active.update(comment="", audit_utc_us=audit[0], request_id=active["created_request_id"])
        return build_history(rows, active, cutoff_utc_us, self.store.zone, first, last)

    def read_work_entry_revisions(self, entry_id: str) -> dict:
        """Detached identity, immutable closed/date-only revisions and active-start audits."""
        uuid_text(entry_id)
        with self._read_transaction() as c:
            row = c.execute("SELECT * FROM work_entries WHERE entry_id=?", (entry_id,)).fetchone()
            if row is None:
                raise ValueError("Work identity is unknown")
            return {"entry": dict(row),
                    "revisions": [dict(r) for r in c.execute(
                        "SELECT * FROM work_revisions WHERE entry_id=? ORDER BY revision", (entry_id,))],
                    "active_start_corrections": [dict(r) for r in c.execute(
                        "SELECT * FROM active_start_corrections WHERE entry_id=? ORDER BY version", (entry_id,))]}
