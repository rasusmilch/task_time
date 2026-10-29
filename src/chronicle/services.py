"""Complete task/project/timer use cases over the worker-owned SQLite adapter."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, time, timedelta

from .accounting import calculate
from .records import Outcome, Request, StaleState, integer, uuid_text
from .sqlite_store import SQLiteStore
from .timekeeping import instant, local_date, resolve_start, resolve_minute, parse_date, parse_duration, week_dates, to_us


def name_text(value: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError("A nonempty name is required")
    return value.strip()


_UNSPECIFIED_PROJECT = object()


class TimerService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def _make(self, operation: str, request_id: str, action_utc_us: int, arguments: dict) -> Outcome:
        return self.execute(Request.make(request_id, self.store.dataset_id, operation, action_utc_us, **arguments))

    def create_task(self, task_id: str, name: str, project_id=_UNSPECIFIED_PROJECT, *,
                    parent_task_id: str | None = None, expected_project_version: int | None = None,
                    expected_parent_version: int | None = None,
                    request_id: str, action_utc_us: int) -> Outcome:
        arguments = dict(task_id=task_id, name=name, parent_task_id=parent_task_id,
                         expected_project_version=expected_project_version, expected_parent_version=expected_parent_version)
        if project_id is not _UNSPECIFIED_PROJECT:
            arguments['project_id'] = project_id
        elif parent_task_id is None:
            arguments['project_id'] = None
        return self._make('create_task', request_id, action_utc_us, arguments)

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

    def archive_project(self, project_id: str, *, expected_version: int,
                       request_id: str, action_utc_us: int) -> Outcome:
        return self._make('archive_project', request_id, action_utc_us,
                          dict(project_id=project_id, expected_version=expected_version))

    def unarchive_project(self, project_id: str, *, expected_version: int,
                       request_id: str, action_utc_us: int) -> Outcome:
        return self._make('unarchive_project', request_id, action_utc_us,
                          dict(project_id=project_id, expected_version=expected_version))

    def archive_task(self, task_id: str, *, expected_version: int,
                       request_id: str, action_utc_us: int) -> Outcome:
        return self._make('archive_task', request_id, action_utc_us,
                          dict(task_id=task_id, expected_version=expected_version))

    def unarchive_task(self, task_id: str, *, expected_version: int,
                       request_id: str, action_utc_us: int) -> Outcome:
        return self._make('unarchive_task', request_id, action_utc_us,
                          dict(task_id=task_id, expected_version=expected_version))

    def move_task_branch(self, task_id: str, *, expected_version: int,
                         source_parent_task_id: str | None, source_project_id: str | None,
                         destination_parent_task_id: str | None, destination_project_id: str | None,
                         expected_destination_parent_version: int | None,
                         expected_destination_project_version: int | None,
                         reviewed_subtree: list[dict], request_id: str, action_utc_us: int) -> Outcome:
        return self._make('move_task_branch',request_id,action_utc_us,
            dict(task_id=task_id,expected_version=expected_version,
                 source_parent_task_id=source_parent_task_id,source_project_id=source_project_id,
                 destination_parent_task_id=destination_parent_task_id,destination_project_id=destination_project_id,
                 expected_destination_parent_version=expected_destination_parent_version,
                 expected_destination_project_version=expected_destination_project_version,
                 reviewed_subtree=reviewed_subtree))

    def _move_task_branch(self, c, request, arguments):
        from .movement import plan
        from .hierarchy import task_paths
        tasks=[dict(r) for r in c.execute('SELECT * FROM tasks')]
        projects=[dict(r) for r in c.execute('SELECT * FROM projects')]
        row=c.execute('SELECT * FROM active_timer').fetchone()
        active=dict(row) if row else None
        final,result=plan(tasks,projects,active,arguments)
        if not result['changed_tasks']:return None
        branch={r['task_id'] for r in arguments['reviewed_subtree']}
        original={r['task_id']:r for r in tasks}
        expected={r['task_id']:r for r in final}
        root=arguments['task_id']
        if arguments['source_project_id']!=arguments['destination_project_id']:
            for key in sorted(branch):
                c.execute('UPDATE tasks SET parent_task_id=NULL WHERE task_id=?',(key,))
            for key in sorted(branch):
                c.execute('UPDATE tasks SET project_id=? WHERE task_id=?',(arguments['destination_project_id'],key))
            c.execute('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(arguments['destination_parent_task_id'],root))
            paths=task_paths(final)
            for key in sorted(branch-{root},key=lambda k:(len(paths[k]),k)):
                c.execute('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(original[key]['parent_task_id'],key))
        else:
            c.execute('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(arguments['destination_parent_task_id'],root))
        for changed in result['changed_tasks']:
            key=changed['task_id']
            c.execute('UPDATE tasks SET version=?,updated_utc_us=? WHERE task_id=?',(changed['version'],request.action_utc_us,key))
            expected[key]['updated_utc_us']=request.action_utc_us
        self.store.assert_structure(c)
        actual={r['task_id']:dict(r) for r in c.execute('SELECT * FROM tasks')}
        if actual!=expected or (dict(c.execute('SELECT * FROM active_timer').fetchone()) if active else None)!=active:
            raise ValueError('Installed move differs from validated final state')
        return result

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
            self._recordable(c, a['task_id'])
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
        row = c.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise StaleState("Task is missing")
        integer(version, "Task version", 1, 2**63 - 1)
        if row["version"] != version:
            raise StaleState("Task changed; refresh before trying again")
        return row

    @staticmethod
    def _project(c, project_id, expected_version=None):
        if project_id is None:
            if expected_version is not None: raise ValueError('Unassigned has no project version')
            return None
        uuid_text(project_id)
        row = c.execute('SELECT * FROM projects WHERE project_id=?',(project_id,)).fetchone()
        if row is None or row['is_archived']:
            raise StaleState('Project is missing or archived')
        if expected_version is not None:
            integer(expected_version,'Project version',1,2**63-1)
            if row['version'] != expected_version: raise StaleState('Reviewed project version changed')
        return row

    @staticmethod
    def _active_path(c, task_id):
        """Bounded transactional ancestry; no cached hierarchy may authorize work."""
        uuid_text(task_id)
        rows = list(c.execute("""WITH RECURSIVE path(task_id,parent_task_id,project_id,is_archived,n) AS (
          SELECT task_id,parent_task_id,project_id,is_archived,1 FROM tasks WHERE task_id=?
          UNION ALL SELECT p.task_id,p.parent_task_id,p.project_id,p.is_archived,a.n+1
          FROM tasks p JOIN path a ON p.task_id=a.parent_task_id WHERE a.n<4
        ) SELECT * FROM path""",(task_id,)))
        if not rows: raise StaleState('Task is missing')
        if len(rows)>3 or rows[-1]['parent_task_id'] is not None or len({r['task_id'] for r in rows})!=len(rows):
            raise ValueError('Invalid task ancestry')
        if any(r['project_id'] != rows[0]['project_id'] for r in rows): raise ValueError('Task project ancestry differs')
        if any(r['is_archived'] for r in rows): raise StaleState('Task is effectively archived')
        TimerService._project(c,rows[0]['project_id'])
        return rows

    @staticmethod
    def _recordable(c, task_id):
        TimerService._active_path(c,task_id)
        if c.execute('SELECT 1 FROM tasks WHERE parent_task_id=?',(task_id,)).fetchone():
            raise StaleState('New recording requires a leaf task')

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

    def prepare_timesheet_preview(self, *, export_id: str, cutoff_utc_us: int, period: str = "this_week",
                                  start_date: str | None = None, end_date: str | None = None,
                                  scope_kind: str = "all", task_ids: tuple[str, ...] = ()):
        from .timesheet import prepare
        instant(cutoff_utc_us)
        uuid_text(export_id)
        with self._read_transaction() as c:
            tasks = [dict(r) for r in c.execute("SELECT * FROM tasks ORDER BY task_id")]
            projects = [dict(r) for r in c.execute("SELECT * FROM projects ORDER BY project_id")]
            work = [dict(r) for r in c.execute("""SELECT e.task_id,r.* FROM work_entries e
              JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0""")]
            row = c.execute("SELECT * FROM active_timer").fetchone()
            active = dict(row) if row else None
            weekday = self.store.week_start
            dataset_id, timezone = self.store.dataset_id, self.store.timezone
        return prepare(export_id=export_id,dataset_id=dataset_id,cutoff_utc_us=cutoff_utc_us,
                       timezone=timezone,week_start=weekday,tasks=tasks,projects=projects,work=work,active=active,
                       period=period,start_date=start_date,end_date=end_date,scope_kind=scope_kind,task_ids=task_ids)

    def read_timesheet_task_choices(self):
        with self._read_transaction() as c:
            rows = [dict(r) for r in c.execute("""SELECT t.task_id,t.name,t.is_archived,t.project_id,
              COALESCE(p.name,'Unassigned') AS project_name FROM tasks t LEFT JOIN projects p USING(project_id)
              ORDER BY project_name,t.name,t.task_id""")]
            structure = self.store.assert_structure(c)
            rows = [{**r, **structure[r['task_id']]} for r in rows]
        return {"dataset_id":self.store.dataset_id,"tasks":rows}

    def register_timesheet_export(self, candidate, *, request_id: str, action_utc_us: int) -> Outcome:
        from .timesheet import Candidate
        content = candidate.content() if type(candidate) is Candidate else candidate
        return self._make('register_timesheet_export',request_id,action_utc_us,dict(candidate=content))

    def list_registered_timesheet_exports(self):
        with self._read_transaction() as c:
            result = []
            for row in c.execute("SELECT export_id,registered_utc_us FROM timesheet_exports ORDER BY registered_utc_us,export_id"):
                value = self.store.read_export(c,row['export_id'])
                result.append({"export_id":value.export_id,"registered_utc_us":row['registered_utc_us'],
                               "start_date":value.start_date,"end_date":value.end_date,"cutoff_utc_us":value.cutoff_utc_us,
                               "timezone":value.timezone,"week_start":value.week_start,"scope_kind":value.scope_kind,
                               "tasks":value.tasks,"preferred_destination":value.preferred_destination})
            return result

    def read_registered_timesheet_export(self, export_id: str):
        with self._read_transaction() as c:
            return self.store.read_export(c,export_id)

    def inspect_registered_export_destination(self, export_id: str, destination=None):
        from .timesheet_files import destination_path, inspect, protect
        candidate = self.read_registered_timesheet_export(export_id)
        selected = candidate.preferred_destination if destination is None else destination
        target = destination_path(selected) if selected is not None else None
        if target is not None: protect(target,self.store.directory)
        return inspect(target,candidate.report_utf8,candidate.report_sha256)

    def materialize_registered_timesheet_export(self, export_id: str, destination, *,
                                              confirmed_overwrite=False, expected_conflict=None):
        from .timesheet_files import destination_path, materialize
        candidate = self.read_registered_timesheet_export(export_id)
        return materialize(export_id,destination_path(destination),candidate.report_utf8,candidate.report_sha256,
                           self.store.directory,confirmed_overwrite=confirmed_overwrite,expected_conflict=expected_conflict)

    def confirm_polr_absolute(self, *, batch_id: str, mode: str, source_export_id: str | None,
                              source_metadata: dict | None, reviewed_rows: list, selected_keys: list,
                              manual_cells: list, acknowledgements: list, request_id: str, action_utc_us: int) -> Outcome:
        return self._make('confirm_polr_absolute',request_id,action_utc_us,
                         dict(batch_id=batch_id,mode=mode,source_export_id=source_export_id,source_metadata=source_metadata,
                              reviewed_rows=reviewed_rows,selected_keys=selected_keys,manual_cells=manual_cells,acknowledgements=acknowledgements))

    @staticmethod
    def _export_sequence(c, export_id):
        return c.execute("""SELECT r.commit_seq FROM timesheet_exports e JOIN committed_requests r
          ON r.request_id=e.created_request_id WHERE e.export_id=?""",(export_id,)).fetchone()[0]

    def read_polr_confirmation_proposal(self, export_id: str) -> dict:
        from .polr_confirmation import proposal
        with self._read_transaction() as c:
            source=self.store.read_export(c,export_id)
            current,_=self.store.confirmation_state(c)
            return proposal(source,current,self._export_sequence(c,export_id))

    def read_polr_current_cells(self, task_date_keys: list) -> list[dict]:
        from .polr_confirmation import ordered
        keys=ordered(task_date_keys,'task_id work_date')
        with self._read_transaction() as c:
            current,_=self.store.confirmation_state(c)
            result=[]
            for task,day in keys:
                if c.execute('SELECT 1 FROM tasks WHERE task_id=?',(task,)).fetchone() is None:raise ValueError('Unknown task')
                prior=current.get((task,day))
                result.append(dict(task_id=task,work_date=day,current_batch_id=prior[0] if prior else None,
                                   confirmed_quarters=prior[1] if prior else None))
            return result

    def _polr_day_status(self, c, task_id, work_date, cutoff):
        from .accounting import calculate_daily
        from .polr_allocation import allocate_week,actual_hundredths,civil,complete_week,Q
        uuid_text(task_id);day=civil(work_date);instant(cutoff)
        task=c.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()
        if task is None:raise ValueError('Unknown retained task UUID')
        first=day-timedelta(days=(day.weekday()-self.store.week_start)%7)
        last=civil(complete_week(first.isoformat())[-1])
        tasks=[dict(r) for r in c.execute('SELECT * FROM tasks')]
        work=[dict(r) for r in c.execute("""SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r
          ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0""")]
        row=c.execute('SELECT * FROM active_timer').fetchone()
        daily=calculate_daily(tasks,work,dict(row) if row else None,cutoff,self.store.zone,first,last)[task_id]
        values=tuple(((first+timedelta(days=i)).isoformat(),daily.get((first+timedelta(days=i)).isoformat(),0)) for i in range(7))
        allocation=dict(allocate_week(first.isoformat(),values));actual=daily.get(work_date,0);hundredths=actual_hundredths(actual)
        current,_=self.store.confirmation_state(c);prior=current.get((task_id,work_date));confirmed=prior[1] if prior else None
        return dict(task_id=task_id,task_name=task['name'],is_archived=bool(task['is_archived']),work_date=work_date,
                    cutoff_utc_us=cutoff,timezone=self.store.timezone,week_start=self.store.week_start,
                    actual_us=actual,actual_hundredths=hundredths,suggested_quarters=allocation[work_date],
                    confirmed_quarters=confirmed,current_batch_id=prior[0] if prior else None,
                    daily_delta_hundredths=hundredths-25*confirmed if prior else None,
                    suggested_entry_gap_quarters=allocation[work_date]-confirmed if prior else None,
                    full_week_adjustment_us=sum(allocation.values())*Q-sum(v for _,v in values))

    def read_polr_day_status(self, task_id: str, work_date: str, *, cutoff_utc_us: int) -> dict:
        with self._read_transaction() as c:return self._polr_day_status(c,task_id,work_date,cutoff_utc_us)

    def read_polr_manual_context(self, task_id: str, work_date: str, *, cutoff_utc_us: int) -> dict:
        from .polr_confirmation import key
        key(dict(task_id=task_id,work_date=work_date));instant(cutoff_utc_us)
        with self._read_transaction() as c:
            task=c.execute('SELECT * FROM tasks WHERE task_id=?',(task_id,)).fetchone()
            if task is None:raise ValueError('Unknown retained task UUID')
            current,_=self.store.confirmation_state(c);prior=current.get((task_id,work_date))
            try:return self._polr_day_status(c,task_id,work_date,cutoff_utc_us)
            except (ValueError,OverflowError) as exc:
                return dict(task_id=task_id,task_name=task['name'],is_archived=bool(task['is_archived']),work_date=work_date,
                    cutoff_utc_us=cutoff_utc_us,timezone=self.store.timezone,week_start=self.store.week_start,
                    actual_us=None,actual_hundredths=None,suggested_quarters=None,
                    confirmed_quarters=prior[1] if prior else None,current_batch_id=prior[0] if prior else None,
                    daily_delta_hundredths=None,suggested_entry_gap_quarters=None,full_week_adjustment_us=None,calculation_error=exc)

    @staticmethod
    def _confirmation_batch(c,batch_id):
        uuid_text(batch_id)
        row=c.execute("""SELECT b.*,r.commit_seq FROM polr_confirmation_batches b
          JOIN committed_requests r ON r.request_id=b.created_request_id WHERE b.batch_id=?""",(batch_id,)).fetchone()
        if row is None:raise ValueError('Unknown confirmation batch')
        return {**dict(row),'cells':[dict(r) for r in c.execute(
            'SELECT * FROM polr_confirmation_cells WHERE batch_id=? ORDER BY task_id,work_date',(batch_id,))]}

    def list_polr_confirmation_batches(self) -> list[dict]:
        with self._read_transaction() as c:
            return [self._confirmation_batch(c,r[0]) for r in c.execute("""SELECT b.batch_id FROM polr_confirmation_batches b
              JOIN committed_requests r ON r.request_id=b.created_request_id ORDER BY r.commit_seq""")]

    def read_polr_confirmation_batch(self, batch_id: str) -> dict:
        with self._read_transaction() as c:return self._confirmation_batch(c,batch_id)

    def _reconciliation_facts(self, c):
        tasks=[dict(r) for r in c.execute('SELECT * FROM tasks ORDER BY task_id')]
        projects=[dict(r) for r in c.execute('SELECT * FROM projects ORDER BY project_id')]
        work=[dict(r) for r in c.execute('''SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r
          ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0''')]
        row=c.execute('SELECT * FROM active_timer').fetchone()
        current={}
        for r in c.execute('''SELECT p.task_id,p.work_date,p.batch_id,v.confirmed_quarters,r.commit_seq
          FROM polr_confirmed_current p JOIN polr_confirmation_cells v USING(batch_id,task_id,work_date)
          JOIN polr_confirmation_batches b USING(batch_id) JOIN committed_requests r ON r.request_id=b.created_request_id'''):
            current[(r['task_id'],r['work_date'])]=dict(batch_id=r['batch_id'],quarters=r['confirmed_quarters'],seq=r['commit_seq'])
        return dict(dataset_id=self.store.dataset_id,timezone=self.store.timezone,week_start=self.store.week_start,
                    tasks=tasks,projects=projects,work=work,active=dict(row) if row else None,current=current)

    def read_polr_reconciliation(self, *, cutoff_utc_us: int, period: str='this_week',
                                 start_date: str | None=None, end_date: str | None=None,
                                 scope_kind: str='all', task_ids: tuple[str,...]=(),
                                 source_export_id: str | None=None) -> dict:
        from .reconciliation import project
        instant(cutoff_utc_us)
        with self._read_transaction() as c:
            facts=self._reconciliation_facts(c)
            source=self.store.read_export(c,source_export_id) if source_export_id is not None else None
            seq=self._export_sequence(c,source_export_id) if source is not None else None
        return project(**facts,cutoff_utc_us=cutoff_utc_us,period=period,start_date=start_date,
                       end_date=end_date,scope_kind=scope_kind,task_ids=task_ids,source=source,source_seq=seq)

    def read_polr_reminder_status(self, *, cutoff_utc_us: int) -> dict:
        from .reconciliation import project,reminder_periods,reminder_status,reminder_context
        instant(cutoff_utc_us)
        with self._read_transaction() as c:
            facts=self._reconciliation_facts(c)
            dismissed=self.store.dismissed_date(c)
        today,previous,end,first,last,checked=reminder_periods(cutoff_utc_us,self.store.zone,facts['week_start'])
        context=reminder_context(dataset_id=facts['dataset_id'],cutoff_utc_us=cutoff_utc_us,
            timezone=facts['timezone'],week_start=facts['week_start'],dismissed_local_date=dismissed)
        try:
            report=project(**facts,cutoff_utc_us=cutoff_utc_us,period='custom',start_date=previous.isoformat(),
                           end_date=(last if checked else end).isoformat())
        except (ValueError,OverflowError) as exc:
            context['calculation_error']=exc
            return context
        return reminder_status(report,dismissed)

    def dismiss_polr_reminder_today(self, local_date: str, *, request_id: str, action_utc_us: int) -> Outcome:
        return self._make('dismiss_polr_reminder_today',request_id,action_utc_us,dict(local_date=local_date))

    def execute(self, request: Request) -> Outcome:
        # The transaction resolves exact receipts before calling this current-state validator.
        def operation(c):
            a, op, now = request.args(), request.operation, request.action_utc_us
            local_date(now, self.store.zone)
            from .lifecycle import OPERATIONS, transition
            if op in OPERATIONS:
                tasks = [dict(r) for r in c.execute('SELECT * FROM tasks')]
                projects = [dict(r) for r in c.execute('SELECT * FROM projects')]
                active = c.execute('SELECT * FROM active_timer').fetchone()
                changed = transition(op, a, now, tasks, projects, active)
                if changed is None:
                    return None
                entity = 'project' if op.endswith('_project') else 'task'
                key = changed[entity + '_id']
                c.execute(f'UPDATE {entity}s SET is_archived=?,archived_at_utc_us=?,version=?,updated_utc_us=? WHERE {entity}_id=?',
                          (changed['is_archived'], changed['archived_at_utc_us'], changed['version'], now, key))
                self.store.assert_lifecycle(c)
                return {entity + '_id': key, 'version': changed['version']}
            if op == 'move_task_branch':
                return self._move_task_branch(c,request,a)
            if op == 'dismiss_polr_reminder_today':
                from .polr_allocation import civil
                if set(a)!={'local_date'}:raise ValueError('Dismissal requires one local date')
                day=civil(a['local_date'])
                if day!=local_date(now,self.store.zone):raise StaleState('Dismissal date differs from accepted dataset-local observation')
                if self.store.dismissed_date(c)==day.isoformat():return None
                c.execute('UPDATE dataset_meta SET polr_reminder_dismissed_local_date=? WHERE singleton=1',(day.isoformat(),))
                return dict(local_date=day.isoformat())
            if op == 'confirm_polr_absolute':
                from .polr_confirmation import fields,REQUEST_FIELDS
                fields(a,REQUEST_FIELDS)
                source=self.store.read_export(c,a['source_export_id']) if a['source_export_id'] is not None else None
                seq=self._export_sequence(c,source.export_id) if source else None
                return self.store.insert_confirmation(c,request,source,seq)
            if op == 'register_timesheet_export':
                from .timesheet import from_content
                if set(a) != {'candidate'}:
                    raise ValueError("Registration requires complete frozen candidate")
                candidate = from_content(a['candidate'])
                if candidate.dataset_id != self.store.dataset_id or candidate.timezone != self.store.timezone:
                    raise ValueError("Wrong candidate dataset/timezone")
                return self.store.insert_export(c,candidate,request)
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
            if op == 'create_task':
                required = {'task_id','name'}
                allowed = required | {'project_id','parent_task_id','expected_project_version','expected_parent_version'}
                if not required <= set(a) or not set(a) <= allowed:
                    raise ValueError('Incorrect create_task fields')
            elif op not in expected or set(a) != expected[op]:
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
                if entity == 'task':
                    parent, parent_version = a.get('parent_task_id'), a.get('expected_parent_version')
                    group, project_version = a.get('project_id'), a.get('expected_project_version')
                    if parent is not None:
                        if parent == key: raise ValueError('Task cannot parent itself')
                        row = self._task(c,parent,parent_version)
                        path = self._active_path(c,parent)
                        if len(path)>=3: raise ValueError('Maximum three task levels')
                        if 'project_id' in a and group != row['project_id']:
                            raise ValueError('Child project must match parent project exactly')
                        group = row['project_id']
                        if c.execute('SELECT 1 FROM active_timer WHERE task_id=?',(parent,)).fetchone():
                            raise StaleState('Running task cannot become a parent')
                    elif parent_version is not None:
                        raise ValueError('Root task has no reviewed parent version')
                    if group is not None and parent is None:
                        integer(project_version,'Reviewed project version',1,2**63-1)
                    self._project(c,group,project_version)
                    c.execute("""INSERT INTO tasks(task_id,project_id,parent_task_id,name,version,created_request_id,created_utc_us,updated_utc_us)
                      VALUES(?,?,?,?,1,?,?,?)""",(key,group,parent,name,request.request_id,now,now))
                else:
                    c.execute("""INSERT INTO projects(project_id,name,version,created_request_id,created_utc_us,updated_utc_us)
                      VALUES(?,?,1,?,?,?)""",(key,name,request.request_id,now,now))
                return {f"{entity}_id": key, "version": 1}
            if op in ("rename_task", "rename_project"):
                entity = "task" if op == "rename_task" else "project"
                key = uuid_text(a[f"{entity}_id"])
                version = integer(a["expected_version"], "Version", 1, 2**63 - 1)
                row = c.execute(f"SELECT * FROM {entity}s WHERE {entity}_id=?", (key,)).fetchone()
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
                self._active_path(c,a['task_id'])
                if row['parent_task_id'] is not None or c.execute('SELECT 1 FROM tasks WHERE parent_task_id=?',(row['task_id'],)).fetchone():
                    raise ValueError('Nested branch assignment requires separately approved structural movement')
                c.execute("UPDATE tasks SET project_id=?,version=version+1,updated_utc_us=? WHERE task_id=?", (a["project_id"], now, a["task_id"]))
                return {"task_id": a["task_id"], "version": row["version"] + 1}
            if op == "start_timer":
                self._task(c, a["task_id"], a["expected_task_version"])
                self._recordable(c, a['task_id'])
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
                self._recordable(c, a['next_task_id'])
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
            self.store.assert_confirmations(c)
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
            projects = [dict(r) for r in c.execute("SELECT * FROM projects ORDER BY name,project_id")]
            rows = [dict(r) for r in c.execute("""SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r
              ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0""")]
            row = c.execute("SELECT * FROM active_timer").fetchone()
            active = dict(row) if row else None
            weekday = self.store.week_start
            structure = self.store.assert_structure(c)
            tasks = [{**t, **structure[t['task_id']]} for t in tasks]
        # Calculation failure must not hide the current identities or disable recovery controls.
        try:
            report = calculate(tasks, rows, active, cutoff_utc_us, self.store.zone, weekday)
            for project in projects:
                report['projects'].setdefault(project['project_id'],dict(today_us=0,week_us=0))
            error = None
        except (ValueError, OverflowError) as exc:
            report, error = None, str(exc)
        return {"dataset_id": self.store.dataset_id, "timezone": self.store.timezone,
                "tasks": tasks, "projects": projects, "active": active, "report": report,
                "calculation_error": error, "cutoff_utc_us": cutoff_utc_us, "week_start": weekday}


    def read_task_work_history(self, task_id: str, *, cutoff_utc_us: int, period: str = "current_week",
                               start_date: str | None = None, end_date: str | None = None) -> list[dict]:
        """Current effective daily rows, newest date first; never an audit-clock replay."""
        return self.read_history_snapshot(task_id, cutoff_utc_us=cutoff_utc_us, period=period,
                                          start_date=start_date, end_date=end_date)["rows"]

    def read_history_snapshot(self, task_id: str, *, cutoff_utc_us: int, period: str = "current_week",
                              start_date: str | None = None, end_date: str | None = None) -> dict:
        """Detached History rows, deleted identities and their one-transaction context."""
        from .work_history import build_history
        uuid_text(task_id)
        instant(cutoff_utc_us)
        with self._read_transaction() as c:
            if not c.execute("SELECT 1 FROM tasks WHERE task_id=?", (task_id,)).fetchone():
                raise ValueError("Task identity is unknown")
            weekday = self.store.week_start
            if period == "current_week" and start_date is None and end_date is None:
                _, first, last = week_dates(cutoff_utc_us, self.store.zone, weekday)
            elif period == "all" and start_date is None and end_date is None:
                first = last = None
            elif period == "custom":
                first, last = parse_date(start_date), parse_date(end_date)
                from datetime import date
                if last < first or last == date.max:
                    raise ValueError("Require ordered inclusive dates with a representable end boundary")
            else:
                raise ValueError("Period must be current_week, custom with both dates, or all without bounds")
            if first is not None:
                # Validate even an empty/date-only result: absence of intervals
                # does not make an unrepresentable calendar boundary acceptable.
                to_us(datetime.combine(first, time(), self.store.zone))
                to_us(datetime.combine(last + timedelta(days=1), time(), self.store.zone))
            rows = [dict(r) for r in c.execute("""SELECT e.task_id,e.original_start_utc_us,e.created_request_id,r.*
              FROM work_entries e JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision
              WHERE e.task_id=? AND r.is_deleted=0""", (task_id,))]
            deleted = [dict(r) for r in c.execute("""SELECT e.task_id,e.entry_id,r.kind,r.revision,r.is_deleted,
              r.start_utc_us,r.stop_utc_us,r.work_date,r.duration_us FROM work_entries e
              JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision
              WHERE e.task_id=? AND r.is_deleted=1 ORDER BY e.entry_id""", (task_id,))]
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
        return {"dataset_id": self.store.dataset_id, "task_id": task_id, "cutoff_utc_us": cutoff_utc_us,
                "period": period, "start_date": first.isoformat() if first else None,
                "end_date": last.isoformat() if last else None, "week_start": weekday,
                "rows": build_history(rows, active, cutoff_utc_us, self.store.zone, first, last),
                "deleted_entries": deleted}

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
