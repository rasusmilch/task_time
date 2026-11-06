"""One serialized I/O worker; it never imports or calls Tk."""

from dataclasses import dataclass
from queue import Queue
from threading import Thread

from .records import Outcome, Request
from .services import TimerService
from .sqlite_store import SQLiteStore


@dataclass(frozen=True)
class Message:
    kind: str
    token: int = 0
    value: object = None
    request: Request | None = None


class DatabaseWorker(Thread):
    def __init__(self, directory, *, create=False, timezone=None, schema_version=4):
        super().__init__(name="Chronicle database", daemon=False)
        self.directory, self.create, self.timezone = directory, create, timezone
        self.schema_version = schema_version
        self.requests, self.results = Queue(), Queue()

    def run(self):
        store = None
        try:
            store = SQLiteStore(self.directory, create=self.create, timezone=self.timezone,
                                schema_version=self.schema_version)
            if store.schema_version == 4:
                from .schema4_runtime_service import Schema4RuntimeService
                service = Schema4RuntimeService(store)
            else: service = TimerService(store)
            unresolved = None
            unresolved_delete = None
            verified = (dict(schema_version=4,semantic_verified=True,ordinary_startup_permitted=True)
                        if store.schema_version == 4 else dict(schema_version=3))
            self.results.put(Message("ready", value={**verified,"dataset_id": store.dataset_id,
                                                     "timezone": store.timezone, "zone": store.zone,
                                                     "runtime": store.info, "week_start": store.week_start}))
            while True:
                message = self.requests.get()
                if message.kind == "shutdown":
                    break
                processed_request = False
                try:
                    if message.kind in ('mutate', 'reconcile') and unresolved_delete is not None:
                        value = Outcome('unavailable' if self.schema_version == 4 else 'unverified', error=RuntimeError('Delete outcome unresolved; mutation/retry blocked. Inspect current presence, then exit and reopen.'))
                    elif (self.schema_version == 4 and unresolved is not None
                          and (message.kind == 'mutate'
                               or message.kind == 'reconcile' and message.value is not unresolved)):
                        value = Outcome('unavailable', error=RuntimeError('An accepted request is unresolved; only explicit reconciliation of the original Request object is permitted'))
                    elif (self.schema_version == 4 and message.kind in ('mutate','reconcile')
                          and not isinstance(message.value, Request)):
                        value = Outcome('unavailable', error=ValueError('Mutation/reconciliation requires an accepted Request'))
                    elif message.kind == 'mutate' and message.value.operation in ('delete_task','delete_project','delete_template') and unresolved is not None:
                        value = Outcome('unavailable', error=RuntimeError('Delete refused while another accepted request is unresolved'))
                    elif message.kind == 'delete_preview':
                        value = service.read_delete_preview(**message.value)
                    elif message.kind == 'delete_presence':
                        value = service.read_delete_presence(**message.value)
                    elif message.kind == "read":
                        value = service.read_current_state(cutoff_utc_us=message.value)
                    elif message.kind == "history":
                        value = service.read_task_work_history(**message.value)
                    elif message.kind == "history_snapshot":
                        value = service.read_history_snapshot(**message.value)
                    elif message.kind == "revisions":
                        value = service.read_work_entry_revisions(message.value)
                    elif message.kind == "timesheet_tasks":
                        value = service.read_timesheet_task_choices()
                    elif message.kind == "timesheet_preview":
                        value = service.prepare_timesheet_preview(**message.value)
                    elif message.kind == "timesheet_exports":
                        value = service.list_registered_timesheet_exports()
                    elif message.kind == "timesheet_export":
                        value = service.read_registered_timesheet_export(message.value)
                    elif message.kind == "timesheet_status":
                        value = service.inspect_registered_export_destination(**message.value)
                    elif message.kind == "timesheet_publish":
                        value = service.materialize_registered_timesheet_export(**message.value)
                    elif message.kind == "polr_proposal":
                        value = service.read_polr_confirmation_proposal(message.value)
                    elif message.kind == "polr_manual":
                        value = service.read_polr_manual_context(**message.value)
                    elif message.kind == "polr_day":
                        value = service.read_polr_day_status(**message.value)
                    elif message.kind == "polr_history":
                        value = service.list_polr_confirmation_batches()
                    elif message.kind == "polr_batch":
                        value = service.read_polr_confirmation_batch(message.value)
                    elif message.kind == 'polr_reconciliation':
                        value = service.read_polr_reconciliation(**message.value)
                    elif message.kind == 'polr_reminder':
                        value = service.read_polr_reminder_status(cutoff_utc_us=message.value)
                    elif message.kind == 'backup':
                        from .records import uuid_text
                        uuid_text(message.value['request_id'])
                        if unresolved is not None:
                            raise RuntimeError('Backup refused while a mutation is unresolved')
                        value = store.backup(message.value['destination'])
                    elif message.kind == "mutate":
                        processed_request = True
                        value = service.execute(message.value)
                    elif message.kind == "reconcile":
                        processed_request = True
                        value = service.reconcile_request(message.value)
                        if value.status == "absent":
                            value = service.execute(message.value)  # Explicit retry, exact same request.
                    else:
                        raise ValueError("Unknown worker operation")
                    if message.kind in ('timesheet_status','timesheet_publish'):
                        value = {'export_id':message.value['export_id'],'destination':message.value.get('destination'),'result':value}
                except Exception as exc:
                    value = Outcome("unverified" if message.kind in ("mutate", "reconcile") else "unavailable", error=exc)
                if self.schema_version == 4 and processed_request:
                    # Only authorized service processing can acquire/settle ownership.
                    # Equal UUID/content is not this live session's accepted object.
                    if value.status == 'unverified':
                        if unresolved is None:
                            unresolved = message.value
                        if message.value.operation in ('delete_task','delete_project','delete_template') and unresolved_delete is None:
                            unresolved_delete = message.value
                    elif unresolved is message.value:
                        unresolved = None
                elif self.schema_version == 3 and message.kind in ('mutate', 'reconcile'):
                    if value.status == 'unverified':
                        unresolved = message.value.request_id
                        if message.value.operation in ('delete_task', 'delete_project', 'delete_template') and unresolved_delete is None:
                            unresolved_delete = message.value
                    elif unresolved == message.value.request_id:
                        unresolved = None
                if message.kind == 'backup':
                    value = {'request_id': message.value['request_id'], 'result': value}
                self.results.put(Message(message.kind, message.token, value,
                                         message.value if message.kind in ('mutate','reconcile') else None))
        except Exception as exc:
            partial = getattr(exc, "_chronicle_cleanup_store", None)
            if partial is not None:
                store = partial
                del exc._chronicle_cleanup_store  # Keep the explicit cleanup handoff worker-private.
            self.results.put(Message("startup_failed", value=exc))
        finally:
            if store is not None:
                while True:
                    try:
                        store.close()
                        break
                    except Exception as exc:
                        self.results.put(Message("shutdown_failed", value=exc))
                        # Remain the owning thread. Only an explicit cleanup retry may proceed.
                        while self.requests.get().kind != "shutdown":
                            pass
            self.results.put(Message("stopped"))
