from queue import Empty
import threading

from chronicle.records import Request
from chronicle.worker import DatabaseWorker, Message
from conftest import NOW, uid


def receive(worker, kind):
    while True:
        value = worker.results.get(timeout=5)
        if value.kind == kind:
            return value.value


def test_connection_thread_operation_reconcile_and_shutdown(tmp_path, monkeypatch):
    import chronicle.worker as module
    original = module.SQLiteStore
    threads = []
    class Observed(original):
        def __init__(self, *args, **kwargs):
            threads.append(("open", threading.get_ident()))
            super().__init__(*args, **kwargs)
        def transact(self, *args):
            threads.append(("mutation", threading.get_ident()))
            return super().transact(*args)
        def close(self):
            threads.append(("close", threading.get_ident()))
            return super().close()
    monkeypatch.setattr(module, "SQLiteStore", Observed)
    worker = DatabaseWorker(tmp_path / "new", create=True, timezone="UTC")
    worker.start()
    ready = receive(worker, "ready")
    frozen = Request.make(uid(), ready["dataset_id"], "create_task", NOW, task_id=uid(), name="Worker", project_id=None)
    worker.requests.put(Message("mutate", 1, frozen))
    result = receive(worker, "mutate")
    assert result.status == "committed"
    worker.requests.put(Message("reconcile", 2, frozen))
    assert receive(worker, "reconcile").result == result.result
    worker.requests.put(Message("shutdown"))
    receive(worker, "stopped")
    worker.join(timeout=5)  # Test thread; application never joins a running worker.
    assert not worker.is_alive()
    assert all(identity == worker.ident for _, identity in threads)
    assert worker.ident != threading.get_ident()


def test_startup_failure_reports_and_stops_without_creating_dataset(tmp_path):
    worker = DatabaseWorker(tmp_path / "missing")
    worker.start()
    assert isinstance(receive(worker, "startup_failed"), ValueError)
    receive(worker, "stopped")
    worker.join(timeout=5)
    assert not (tmp_path / "missing").exists()


def test_cleanup_failure_stays_on_owner_thread_until_explicit_retry(tmp_path, monkeypatch):
    import chronicle.worker as module
    original = module.SQLiteStore
    class FailCloseOnce(original):
        attempts = 0
        def close(self):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("cleanup fault")
            return super().close()
    monkeypatch.setattr(module, "SQLiteStore", FailCloseOnce)
    worker = DatabaseWorker(tmp_path / "new", create=True, timezone="UTC")
    worker.start()
    receive(worker, "ready")
    worker.requests.put(Message("shutdown"))
    assert "cleanup fault" in str(receive(worker, "shutdown_failed"))
    assert worker.is_alive()
    worker.requests.put(Message("shutdown"))
    receive(worker, "stopped")
    worker.join(timeout=5)
    assert not worker.is_alive()
