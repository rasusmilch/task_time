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


class DatabaseWorker(Thread):
    def __init__(self, directory, *, create=False, timezone=None):
        super().__init__(name="Chronicle database", daemon=False)
        self.directory, self.create, self.timezone = directory, create, timezone
        self.requests, self.results = Queue(), Queue()

    def run(self):
        store = None
        try:
            store = SQLiteStore(self.directory, create=self.create, timezone=self.timezone)
            service = TimerService(store)
            unresolved = None
            self.results.put(Message("ready", value={"dataset_id": store.dataset_id,
                                                     "timezone": store.timezone, "zone": store.zone,
                                                     "runtime": store.info, "week_start": store.week_start}))
            while True:
                message = self.requests.get()
                if message.kind == "shutdown":
                    break
                try:
                    if message.kind == "read":
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
                        value = service.execute(message.value)
                    elif message.kind == "reconcile":
                        value = service.reconcile_request(message.value)
                        if value.status == "absent":
                            value = service.execute(message.value)  # Explicit retry, exact same request.
                    else:
                        raise ValueError("Unknown worker operation")
                    if message.kind in ('timesheet_status','timesheet_publish'):
                        value = {'export_id':message.value['export_id'],'destination':message.value.get('destination'),'result':value}
                except Exception as exc:
                    value = Outcome("unverified" if message.kind in ("mutate", "reconcile") else "unavailable", error=exc)
                if message.kind in ('mutate', 'reconcile'):
                    if value.status == 'unverified':
                        unresolved = message.value.request_id
                    elif unresolved == message.value.request_id:
                        unresolved = None
                if message.kind == 'backup':
                    value = {'request_id': message.value['request_id'], 'result': value}
                self.results.put(Message(message.kind, message.token, value))
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
