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


def test_exception_delivery_then_exact_absent_reconciliation_and_queued_reads(tmp_path, monkeypatch):
    from chronicle.services import TimerService
    original, accepted = TimerService.execute, []
    def fail_once(service, request):
        accepted.append(request)
        if len(accepted) == 1:
            raise OSError('worker operation failed before response')
        return original(service, request)
    monkeypatch.setattr(TimerService, 'execute', fail_once)
    worker = DatabaseWorker(tmp_path / 'worker', create=True, timezone='UTC')
    worker.start()
    try:
        ready = receive(worker, 'ready')
        frozen = Request.make(uid(), ready['dataset_id'], 'create_task', NOW,
                              task_id=uid(), name='Retried', project_id=None)
        worker.requests.put(Message('mutate', 1, frozen))
        first = receive(worker, 'mutate')
        assert first.status == 'unverified' and 'before response' in str(first.error)
        worker.requests.put(Message('reconcile', 2, frozen))
        assert receive(worker, 'reconcile').status == 'committed'
        assert accepted == [frozen, frozen] and accepted[0] is accepted[1]
        for token in range(3, 6): worker.requests.put(Message('read', token, NOW))
        worker.requests.put(Message('shutdown'))
        messages = [worker.results.get(timeout=5) for _ in range(4)]
        assert [m.kind for m in messages] == ['read', 'read', 'read', 'stopped']
        assert all(m.value['tasks'][0]['task_id'] == frozen.args()['task_id'] for m in messages[:3])
    finally:
        worker.requests.put(Message('shutdown'))
        worker.join(timeout=8)
        assert not worker.is_alive()


def test_failed_startup_cleanup_remains_on_worker_until_explicit_retry(tmp_path, monkeypatch):
    import chronicle.worker as module
    original = module.SQLiteStore
    attempts = []
    primary = OSError('startup profile failed')
    class FailedStartup(original):
        def _profile(self):
            super()._profile()
            raise primary
        def close(self):
            attempts.append(threading.get_ident())
            if len(attempts) <= 2:
                raise OSError('startup close not established')
            return super().close()
    monkeypatch.setattr(module, 'SQLiteStore', FailedStartup)
    worker = DatabaseWorker(tmp_path / 'startup', create=True, timezone='UTC')
    worker.start()
    try:
        assert receive(worker, 'startup_failed') is primary
        result = worker.results.get(timeout=5)
        assert result.kind == 'shutdown_failed', 'Failed initialization cleanup must not report stopped'
        assert worker.is_alive()
        worker.requests.put(Message('shutdown'))
        receive(worker, 'stopped')
    finally:
        worker.requests.put(Message('shutdown'))
        worker.join(timeout=8)
        assert not worker.is_alive()
    assert len(attempts) == 3 and all(identity == worker.ident for identity in attempts)
    from chronicle.dataset_lock import DatasetLock
    lock = DatasetLock(worker.directory)
    lock.acquire(); lock.close()


def test_failed_validation_probe_cleanup_is_not_reported_stopped(tmp_path, monkeypatch):
    import chronicle.worker as module
    original = module.SQLiteStore
    directory = tmp_path / 'existing'
    store = original(directory, create=True, timezone='UTC')
    store.close()
    attempts = []
    primary = ValueError('inspected dataset validation failed')
    class CloseFault:
        def __init__(self, connection): self.inner = connection
        def __getattr__(self, name): return getattr(self.inner, name)
        def close(self):
            attempts.append(threading.get_ident())
            if len(attempts) < 3: raise OSError('read probe close failed')
            self.inner.close()
    class FailedValidation(original):
        def _probe(self): return CloseFault(super()._probe())
        @staticmethod
        def _verify(connection): raise primary
    monkeypatch.setattr(module, 'SQLiteStore', FailedValidation)
    worker = DatabaseWorker(directory)
    worker.start()
    try:
        assert receive(worker, 'startup_failed') is primary
        assert worker.results.get(timeout=5).kind == 'shutdown_failed'
        assert worker.is_alive()
        worker.requests.put(Message('shutdown'))
        receive(worker, 'stopped')
    finally:
        worker.requests.put(Message('shutdown'))
        worker.join(timeout=8)
        assert not worker.is_alive()
    assert attempts == [worker.ident] * 3
