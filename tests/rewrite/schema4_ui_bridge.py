"""Test-only serialized Message bridge over C2's disposable CandidateAdapter.

No launcher, production worker registration or alternative mutation logic.
The adapter exclusively owns the test file after handoff to this thread.
"""
from contextlib import contextmanager
from queue import Queue
from threading import Thread, get_ident
import sqlite3

from chronicle import schema_profiles as schema
from chronicle.schema4_evidence import Rows
from chronicle.schema4_services import read_state, history, reconciliation, reminder
from chronicle.sqlite_store import SQLiteStore
from chronicle.records import Outcome
from chronicle.worker import Message
from chronicle.timekeeping import load_zone
from chronicle.hierarchy import candidate_task_observations


class CandidateBridge(Thread):
    presentation_profile = 'schema4-candidate'

    def __init__(self, adapter):
        super().__init__(name='Chronicle candidate UI test', daemon=False)
        self.adapter = adapter
        self.requests, self.results = Queue(), Queue()
        self.handled = []
        self.unresolved = None

    @contextmanager
    def snapshot(self):
        if self.adapter.retired is not None:raise RuntimeError('Candidate read cleanup remains unverified')
        c = self.adapter.connect(readonly=True)
        primary = None
        try:
            c.execute('BEGIN');schema.verify_candidate_transaction(c)
            yield Rows(c)
            c.execute('ROLLBACK')
        except BaseException as exc:
            primary = exc
            raise
        finally:
            try:c.close()
            except Exception as secondary:
                self.adapter.retired = c
                if primary is None:raise
                primary.add_note('Candidate read close also failed: ' + repr(secondary))

    def run(self):
        try:
            with self.snapshot() as c:
                meta = dict(c.execute('SELECT * FROM dataset_meta').fetchone())
                if meta['dataset_id'] != self.adapter.context.dataset_id:raise ValueError('Wrong candidate bridge dataset')
                runtime = dict(sqlite=sqlite3.sqlite_version,journal_mode=c.execute('PRAGMA journal_mode').fetchone()[0],
                    synchronous=c.execute('PRAGMA synchronous').fetchone()[0],foreign_keys=c.execute('PRAGMA foreign_keys').fetchone()[0])
            self.results.put(Message('ready',value=dict(dataset_id=meta['dataset_id'],timezone=meta['timezone'],zone=load_zone(meta['timezone']),
                runtime=runtime,week_start=meta['week_start'],schema_version=4,candidate_verified=True)))
            while True:
                message = self.requests.get()
                if message.kind == 'shutdown':break
                self.handled.append((get_ident(), message))
                try:value = self.dispatch(message)
                except Exception as exc:value = Outcome('unverified' if message.kind in ('mutate','reconcile') else 'unavailable',error=exc)
                if message.kind in ('mutate','reconcile'):
                    if value.status == 'unverified':self.unresolved = message.value
                    elif self.unresolved == message.value:self.unresolved = None
                if message.kind in ('timesheet_status','timesheet_publish'):
                    value = dict(export_id=message.value['export_id'],destination=message.value.get('destination'),result=value)
                self.results.put(Message(message.kind,message.token,value,message.value if message.kind in ('mutate','reconcile') else None))
        except Exception as exc:self.results.put(Message('startup_failed',value=exc))
        finally:
            # Failed-close ownership is retained until an explicit cleanup request.
            while self.adapter.retired is not None:
                try:self.adapter.retired.close();self.adapter.retired=None
                except Exception as exc:
                    self.results.put(Message('shutdown_failed',value=exc))
                    while self.requests.get().kind != 'shutdown':pass
            self.results.put(Message('stopped'))

    def dispatch(self, message):
        kind, value = message.kind, message.value
        a = self.adapter
        if kind in ('mutate','reconcile') and self.unresolved is not None and self.unresolved != value:
            return Outcome('unverified',error=RuntimeError('Another exact candidate request remains unresolved'))
        if kind == 'mutate':
            return a.delete(value) if value.operation in ('delete_project','delete_task','delete_template') else a.execute(value)
        if kind == 'reconcile':
            result = a.inspect(value)
            return a.execute(value) if result.status == 'absent' else result
        if kind == 'delete_preview':return a.preview(value['entity_type'],value['entity_id'])
        if kind == 'delete_presence':return dict(a.presence(value['entity_type'],value['entity_id']),dataset_id=a.context.dataset_id)
        with self.snapshot() as c:
            if kind == 'read':return dict(read_state(c,a.context,cutoff_utc_us=value),schema_version=4,candidate_verified=True)
            if kind == 'history_snapshot':return history(c,a.context,**value)
            if kind == 'revisions':
                entry=c.execute('SELECT * FROM work_entries WHERE entry_id=?',(value,)).fetchone()
                if entry is None:raise ValueError('Unknown work identity')
                return dict(entry=dict(entry),revisions=[dict(r) for r in c.execute('SELECT * FROM work_revisions WHERE entry_id=? ORDER BY revision',(value,))],
                    active_start_corrections=[dict(r) for r in c.execute('SELECT * FROM active_start_corrections WHERE entry_id=? ORDER BY version',(value,))])
            if kind == 'polr_reconciliation':return reconciliation(c,a.context,**value)
            if kind == 'polr_reminder':return reminder(c,a.context,cutoff_utc_us=value)
            meta=dict(c.execute('SELECT * FROM dataset_meta').fetchone())
            tasks=schema._rows(c,'tasks');projects=schema._rows(c,'projects')
            if kind == 'timesheet_tasks':
                obs=candidate_task_observations(tasks,projects);groups={p['project_id']:p for p in projects}
                return dict(dataset_id=a.context.dataset_id,projects=projects,
                    tasks=[dict(t,**obs[t['task_id']],project_name=groups[t['project_id']]['name'] if t['project_id'] else 'Unassigned') for t in tasks])
            if kind == 'timesheet_preview':
                from chronicle.timesheet import prepare
                work=[dict(r) for r in c.execute('SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0')]
                active=c.execute('SELECT * FROM active_timer').fetchone()
                return prepare(dataset_id=a.context.dataset_id,timezone=meta['timezone'],week_start=meta['week_start'],tasks=tasks,projects=projects,
                    work=work,active=dict(active) if active else None,**value)
            if kind == 'timesheet_export':return SQLiteStore.read_export(c,value)
            if kind == 'timesheet_exports':
                exports=[]
                for row in c.execute('SELECT export_id,registered_utc_us FROM timesheet_exports ORDER BY registered_utc_us,export_id'):
                    e=SQLiteStore.read_export(c,row['export_id'])
                    exports.append(dict(export_id=e.export_id,registered_utc_us=row['registered_utc_us'],start_date=e.start_date,end_date=e.end_date,
                        cutoff_utc_us=e.cutoff_utc_us,timezone=e.timezone,week_start=e.week_start,scope_kind=e.scope_kind,tasks=e.tasks,preferred_destination=e.preferred_destination))
                return exports
            if kind == 'polr_proposal':
                from chronicle.polr_confirmation import proposal
                from chronicle.services import TimerService
                current,_=SQLiteStore.confirmation_state(c)
                return proposal(SQLiteStore.read_export(c,value),current,TimerService._export_sequence(c,value))
            if kind in ('polr_day','polr_manual'):
                # Reuse the existing version-independent read calculation with
                # explicit verified metadata, never instantiate/admit a v3 store.
                from types import SimpleNamespace
                from chronicle.services import TimerService
                reads = SimpleNamespace(store=SimpleNamespace(week_start=meta['week_start'],timezone=meta['timezone'],
                    zone=load_zone(meta['timezone']),confirmation_state=SQLiteStore.confirmation_state))
                try:return TimerService._polr_day_status(reads,c,value['task_id'],value['work_date'],value['cutoff_utc_us'])
                except (ValueError,OverflowError) as exc:
                    if kind != 'polr_manual':raise
                    task=next(t for t in tasks if t['task_id']==value['task_id']);current,_=SQLiteStore.confirmation_state(c)
                    prior=current.get((value['task_id'],value['work_date']))
                    return dict(task_id=task['task_id'],task_name=task['name'],is_archived=bool(task['is_archived']),work_date=value['work_date'],
                        cutoff_utc_us=value['cutoff_utc_us'],timezone=meta['timezone'],week_start=meta['week_start'],
                        actual_us=None,actual_hundredths=None,suggested_quarters=None,confirmed_quarters=prior[1] if prior else None,current_batch_id=prior[0] if prior else None,
                        daily_delta_hundredths=None,suggested_entry_gap_quarters=None,full_week_adjustment_us=None,calculation_error=exc)
            if kind in ('polr_history','polr_batch'):
                from chronicle.services import TimerService
                if kind == 'polr_batch':return TimerService._confirmation_batch(c,value)
                return [TimerService._confirmation_batch(c,row[0]) for row in c.execute('SELECT b.batch_id FROM polr_confirmation_batches b JOIN committed_requests r ON r.request_id=b.created_request_id ORDER BY r.commit_seq')]
            if kind in ('timesheet_status','timesheet_publish'):
                from chronicle.timesheet_files import destination_path, inspect, protect, materialize
                e=SQLiteStore.read_export(c,value['export_id'])
                target=destination_path(value.get('destination') or e.preferred_destination) if value.get('destination') or e.preferred_destination else None
                if target is not None:protect(target,a.path.parent)
                if kind == 'timesheet_status':return inspect(target,e.report_utf8,e.report_sha256)
                return materialize(e.export_id,target,e.report_utf8,e.report_sha256,a.path.parent,
                    confirmed_overwrite=value.get('confirmed_overwrite',False),expected_conflict=value.get('expected_conflict'))
        raise ValueError('Unsupported candidate UI test message: ' + kind)
