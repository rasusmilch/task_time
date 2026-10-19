"""Complete task/project/timer use cases over the worker-owned SQLite adapter."""

from __future__ import annotations

from .accounting import calculate
from .records import Outcome, Request, StaleState, integer, uuid_text
from .sqlite_store import SQLiteStore
from .timekeeping import instant, local_date, resolve_start


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
        c.execute("INSERT INTO work_entries VALUES(?,?,'timed',?,NULL,?)",
                  (entry_id, task_id, request.action_utc_us, request.request_id))
        c.execute("INSERT INTO active_timer VALUES(1,?,?,?,1)", (entry_id, task_id, request.action_utc_us))

    @staticmethod
    def _close(c, active, request):
        if request.action_utc_us <= active["start_utc_us"]:
            raise ValueError("Stop must be strictly after the effective start; check the clock or correct active start")
        c.execute("DELETE FROM active_timer WHERE entry_id=?", (active["entry_id"],))
        c.execute("INSERT INTO work_revisions VALUES(?,1,'timed',?,?,0,'',?,?)",
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
            if op not in expected or set(a) != expected[op]:
                raise ValueError("Unknown operation or incorrect request fields")
            if op in ("create_task", "create_project"):
                entity = "task" if op == "create_task" else "project"
                key, name = uuid_text(a[f"{entity}_id"]), name_text(a["name"])
                if entity == "task":
                    self._project(c, a["project_id"])
                    c.execute("INSERT INTO tasks VALUES(?,?,?,1,0,?,?)", (key, a["project_id"], name, now, now))
                else:
                    c.execute("INSERT INTO projects VALUES(?,?,1,0,?,?)", (key, name, now, now))
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
            c.execute("INSERT INTO active_start_corrections VALUES(?,?,?,?,?,?,?)",
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

    def read_current_state(self, *, cutoff_utc_us: int) -> dict:
        instant(cutoff_utc_us)
        self.store._recover_connection()
        c = self.store.connection
        try:
            c.execute("BEGIN")
            self.store.assert_lifecycle(c)
            tasks = [dict(r) for r in c.execute("SELECT * FROM tasks ORDER BY created_utc_us,task_id")]
            projects = [dict(r) for r in c.execute("SELECT * FROM projects WHERE is_deleted=0 ORDER BY name,project_id")]
            rows = [dict(r) for r in c.execute("""SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r
              ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0""")]
            row = c.execute("SELECT * FROM active_timer").fetchone()
            active = dict(row) if row else None
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
        # Calculation failure must not hide the current identities or disable recovery controls.
        try:
            report = calculate(tasks, rows, active, cutoff_utc_us, self.store.zone, self.store.week_start)
            error = None
        except (ValueError, OverflowError) as exc:
            report, error = None, str(exc)
        return {"dataset_id": self.store.dataset_id, "timezone": self.store.timezone,
                "tasks": tasks, "projects": projects, "active": active, "report": report,
                "calculation_error": error, "cutoff_utc_us": cutoff_utc_us}
