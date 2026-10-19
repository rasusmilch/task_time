"""Actual local ownership, safe refusal and calendar-continuity experiments."""
from datetime import datetime
from pathlib import Path
import os
import sqlite3

import pytest

from chronicle.dataset_lock import DatasetLock
from chronicle.services import TimerService
from chronicle.sqlite_store import DATABASE, SQLiteStore
from chronicle.timekeeping import to_us
from conftest import NOW, uid
from test_bootstrap import child
from test_interruptions import paused_child, rows


@pytest.mark.parametrize('start,cutoff,today,week', [
    ('2026-10-19T23:30:00-05:00', '2026-10-20T00:30:00-05:00', 1_800_000_000, 3_600_000_000),
    ('2026-10-17T23:30:00-05:00', '2026-10-18T00:30:00-05:00', 1_800_000_000, 1_800_000_000),
    ('2026-03-08T01:30:00-06:00', '2026-03-08T03:30:00-05:00', 3_600_000_000, 3_600_000_000),
    ('2026-11-01T01:30:00-05:00', '2026-11-01T01:30:00-06:00', 3_600_000_000, 3_600_000_000),
])
def test_reopened_active_calendar_boundaries_without_startup_or_tick_writes(tmp_path, start, cutoff, today, week):
    start, cutoff = [to_us(datetime.fromisoformat(text)) for text in (start, cutoff)]
    directory = tmp_path / 'spaces and unicode Ω'
    store = SQLiteStore(directory, create=True, timezone='America/Chicago')
    service = TimerService(store)
    task, entry = uid(), uid()
    service.create_task(task, 'Work', request_id=uid(), action_utc_us=start)
    service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=start)
    before = rows(store)
    store.close()
    store = SQLiteStore(directory)
    try:
        for _ in range(3):
            state = TimerService(store).read_current_state(cutoff_utc_us=cutoff)
            assert state['active']['entry_id'] == entry and state['active']['start_utc_us'] == start
            assert state['report']['tasks'][task]['today_us'] == today
            assert state['report']['application'] == {'today_us': today, 'week_us': week}
            assert sum(t['week_us'] for t in state['report']['tasks'].values()) == week
            assert rows(store) == before
    finally:
        store.close()


@pytest.mark.parametrize('operation', ['stop', 'switch'])
def test_long_sleep_gap_explicit_action_and_stale_rejections(tmp_path, operation):
    store = SQLiteStore(tmp_path / 'sleep', create=True, timezone='America/Chicago')
    try:
        service = TimerService(store)
        task, other, entry, next_entry = [uid() for _ in range(4)]
        for key in (task, other): service.create_task(key, 'Work', request_id=uid(), action_utc_us=NOW)
        service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=NOW)
        before = rows(store)
        assert service.stop_timer(entry, expected_version=1, request_id=uid(), action_utc_us=NOW).status == 'rejected'
        assert rows(store) == before
        after_sleep = NOW + 13 * 3_600_000_000 + 123456
        if operation == 'stop':
            result = service.stop_timer(entry, expected_version=1, request_id=uid(), action_utc_us=after_sleep)
        else:
            result = service.switch_timer(entry, other, next_entry, expected_active_version=1,
                                          expected_task_version=1, request_id=uid(), action_utc_us=after_sleep)
        assert result.status == 'committed'
        current = rows(store)
        assert current['work_revisions'][0][3:5] == (NOW, after_sleep)
        assert service.stop_timer(entry, expected_version=1, request_id=uid(), action_utc_us=after_sleep + 1).status == 'rejected'
        assert service.switch_timer(entry, other, uid(), expected_active_version=1, expected_task_version=1,
                                    request_id=uid(), action_utc_us=after_sleep + 1).status == 'rejected'
        assert rows(store) == current
    finally:
        store.close()


def test_multiple_corrections_reopen_then_stop_preserves_audits(tmp_path):
    directory = tmp_path / 'corrected'
    store = SQLiteStore(directory, create=True, timezone='America/Chicago')
    service = TimerService(store)
    task, entry = uid(), uid()
    service.create_task(task, 'Work', request_id=uid(), action_utc_us=NOW)
    service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=NOW + 123456)
    for version, clock in [(1, '09:00'), (2, '08:00')]:
        assert service.correct_active_start(entry, '2026-10-19', clock, expected_version=version,
                                            comment='reviewed', request_id=uid(), action_utc_us=NOW + 60_000_000).status == 'committed'
    before = rows(store)
    store.close()
    store = SQLiteStore(directory)
    try:
        service = TimerService(store)
        assert rows(store) == before
        active = service.read_current_state(cutoff_utc_us=NOW + 60_000_000)['active']
        assert active['entry_id'] == entry and active['version'] == 3
        assert service.stop_timer(entry, expected_version=3, request_id=uid(), action_utc_us=NOW + 120_000_000).status == 'committed'
        current = rows(store)
        assert current['active_start_corrections'] == before['active_start_corrections']
        assert current['work_entries'][0][3] == NOW + 123456
        assert current['work_revisions'][0][3] == NOW - 2 * 3_600_000_000
    finally:
        store.close()


OWNER = r'''
from chronicle.sqlite_store import SQLiteStore
import sys
store = SQLiteStore(sys.argv[1], create=sys.argv[2]=='create', timezone='UTC' if sys.argv[2]=='create' else None)
print('BARRIER', flush=True); sys.stdin.readline()
store.close()
'''


def test_separate_owner_crash_stale_lock_and_orderly_release(tmp_path):
    directory = tmp_path / 'owned'
    with paused_child(OWNER, directory, 'create'):
        refused = child("from chronicle.sqlite_store import SQLiteStore; import sys; SQLiteStore(sys.argv[1])", directory)
        assert refused.returncode != 0 and ('Error' in refused.stderr)
    assert (directory / '.chronicle.lock').exists()
    # Both another process and the local owner can acquire after process death.
    with paused_child(OWNER, directory, 'open') as process:
        process.stdin.write('\n'); process.stdin.flush()
        assert process.wait(timeout=10) == 0
    store = SQLiteStore(directory)
    store.close()


def test_concurrent_first_creation_refused_before_overwrite(tmp_path):
    directory = tmp_path / 'race'
    code = r'''
from chronicle.dataset_lock import DatasetLock
from chronicle.sqlite_store import SQLiteStore
import sys
original = DatasetLock.acquire
def acquire(self):
    original(self)
    print('BARRIER', flush=True); sys.stdin.readline()
DatasetLock.acquire = acquire
store = SQLiteStore(sys.argv[1], create=True, timezone='UTC')
store.close()
'''
    with paused_child(code, directory) as process:
        refused = child("from chronicle.sqlite_store import SQLiteStore; import sys; SQLiteStore(sys.argv[1],create=True,timezone='UTC')", directory)
        assert refused.returncode != 0
        process.stdin.write('\n'); process.stdin.flush()
        assert process.wait(timeout=10) == 0
    store = SQLiteStore(directory)
    store.close()


def test_create_race_preserves_file_appearing_after_initial_inspection(tmp_path):
    directory = tmp_path / 'race'
    code = r'''
from chronicle.dataset_lock import DatasetLock
from chronicle.sqlite_store import SQLiteStore
import sys
original = DatasetLock.acquire
def acquire(self):
    original(self); print('BARRIER', flush=True); sys.stdin.readline()
DatasetLock.acquire = acquire
try: SQLiteStore(sys.argv[1],create=True,timezone='UTC')
except ValueError as exc: assert 'refusing overwrite' in str(exc)
else: raise AssertionError('Overwrote a newly observed file')
'''
    with paused_child(code, directory) as process:
        sentinel = directory / DATABASE
        sentinel.write_bytes(b'NOT Chronicle; preserve')
        process.stdin.write('\n'); process.stdin.flush()
        assert process.wait(timeout=10) == 0
        assert sentinel.read_bytes() == b'NOT Chronicle; preserve'


@pytest.mark.parametrize('fault', ['schema', 'profile'])
def test_initialization_failure_releases_os_ownership_without_deleting_partial(tmp_path, monkeypatch, fault):
    import chronicle.sqlite_store as module
    directory = tmp_path / fault
    def fail(*args): raise OSError('initialization fault')
    original = module.schema_statements
    def partial_schema():
        yield next(original())  # Fail after actual transactional DDL, not only before execution.
        raise OSError('initialization fault')
    with monkeypatch.context() as patch:
        patch.setattr(module if fault == 'schema' else SQLiteStore,
                      'schema_statements' if fault == 'schema' else '_profile',
                      partial_schema if fault == 'schema' else fail)
        with pytest.raises(OSError, match='initialization fault'):
            SQLiteStore(directory, create=True, timezone='UTC')
    assert (directory / DATABASE).exists()
    lock = DatasetLock(directory)
    lock.acquire(); lock.close()
    with pytest.raises(ValueError): SQLiteStore(directory, create=True, timezone='UTC')


@pytest.mark.parametrize('damage', ['header', 'identity', 'future', 'partial'])
def test_damaged_dataset_refusal_preserves_main_file(tmp_path, damage):
    directory = tmp_path / damage
    store = SQLiteStore(directory, create=True, timezone='UTC')
    path = store.path
    if damage == 'identity': store.connection.execute('PRAGMA application_id=1')
    if damage == 'future': store.connection.execute('PRAGMA user_version=999')
    store.close()
    if damage == 'header': path.write_bytes(b'invalid SQLite header')
    if damage == 'partial': path.write_bytes(b'')
    before = path.read_bytes()
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        SQLiteStore(directory)
    assert path.read_bytes() == before


def test_unknown_jsonl_and_file_parent_are_never_replaced(tmp_path):
    directory = tmp_path / 'old'
    directory.mkdir()
    for name in ('active_events.jsonl', 'manifest.json', 'notes'):
        (directory / name).write_bytes(b'untouched')
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    for create in (False, True):
        with pytest.raises(ValueError): SQLiteStore(directory, create=create, timezone='UTC' if create else None)
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
    file_parent = tmp_path / 'file'
    file_parent.write_bytes(b'keep')
    with pytest.raises(OSError): SQLiteStore(file_parent / 'dataset', create=True, timezone='UTC')
    assert file_parent.read_bytes() == b'keep'


def test_native_permission_refusal_does_not_damage_dataset(tmp_path):
    if os.name != 'posix' or os.geteuid() == 0:
        pytest.skip('Requires native POSIX permission enforcement; Windows ACL evidence is separate')
    parent = tmp_path / 'protected'
    parent.mkdir()
    parent.chmod(0o500)
    try:
        with pytest.raises(PermissionError): SQLiteStore(parent / 'new', create=True, timezone='UTC')
        assert not (parent / 'new').exists()
    finally:
        parent.chmod(0o700)


def test_original_validation_error_survives_probe_cleanup_failure(tmp_path, monkeypatch):
    directory = tmp_path / 'bad'
    store = SQLiteStore(directory, create=True, timezone='UTC')
    store.close()
    primary = ValueError('original schema validation failure')
    original = SQLiteStore._probe
    class CloseFault:
        def __init__(self, connection): self.inner = connection
        def __getattr__(self, name): return getattr(self.inner, name)
        def close(self):
            self.inner.close()
            raise OSError('probe close failure')
    monkeypatch.setattr(SQLiteStore, '_probe', lambda self: CloseFault(original(self)))
    def invalid(c): raise primary
    monkeypatch.setattr(SQLiteStore, '_verify', staticmethod(invalid))
    with pytest.raises(ValueError, match='original schema validation') as caught:
        SQLiteStore(directory)
    assert caught.value is primary
    assert any('probe close failure' in note for note in primary.__notes__)


def test_native_readonly_database_refuses_mutation_and_releases_lock(tmp_path):
    if os.name != 'posix' or os.geteuid() == 0:
        pytest.skip('Requires native POSIX file permissions; Windows ACLs need native qualification')
    directory = tmp_path / 'readonly'
    store = SQLiteStore(directory, create=True, timezone='UTC')
    path = store.path
    store.close()
    before = path.read_bytes()
    path.chmod(0o400)
    try:
        readonly = SQLiteStore(directory)  # SQLite may open a valid WAL dataset read-only.
        try:
            result = TimerService(readonly).create_project(uid(), 'Refused', request_id=uid(), action_utc_us=NOW)
            assert result.status in ('unavailable', 'rolled_back') and isinstance(result.error, sqlite3.OperationalError)
            assert readonly.connection is None or not readonly.connection.in_transaction
        finally:
            readonly.close()
        assert path.read_bytes() == before
        lock = DatasetLock(directory)
        lock.acquire(); lock.close()
    finally:
        path.chmod(0o600)
