from datetime import datetime, timezone
from uuid import uuid4

import pytest

from chronicle.records import Request
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import to_us


NOW = to_us(datetime(2026, 10, 19, 15, tzinfo=timezone.utc))


def uid():
    return str(uuid4())


@pytest.fixture
def store(tmp_path):
    value = SQLiteStore(tmp_path / "new", create=True, timezone="America/Chicago")
    yield value
    value.close()


@pytest.fixture
def service(store):
    return TimerService(store)


@pytest.fixture
def task(service):
    task_id = uid()
    assert service.create_task(task_id, "Example", request_id=uid(), action_utc_us=NOW).status == "committed"
    return task_id


@pytest.fixture
def make_request(store):
    def make(operation, now=NOW, **arguments):
        return Request.make(uid(), store.dataset_id, operation, now, **arguments)
    return make
