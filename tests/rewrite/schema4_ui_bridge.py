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
        from chronicle.schema4_runtime_service import read_message
        with self.snapshot() as c:
            result = read_message(c,a.context,kind,value,dataset_directory=a.path.parent)
            return dict(result,schema_version=4,candidate_verified=True) if kind=='read' else result
