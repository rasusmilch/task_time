"""Isolated real-SQLite structure; no schema-5 service or readiness claim.

SQL relationship fixtures deliberately leave deferred receipt/export references
unfilled inside transactions that are rolled back. They are not valid semantic
histories, registered reports or production mutation evidence.
"""
import hashlib
import inspect
from pathlib import Path
import re
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from chronicle import schema5_profiles as schema, schema_profiles as historical
from chronicle.app import backend_profile_matches
from chronicle.schema_policy import policy_for
from chronicle.schema4_runtime_service import Schema4RuntimeService
from chronicle.sqlite_store import SQLiteStore
from chronicle.startup import StartupWindow
from chronicle.worker import DatabaseWorker
from conftest import NOW, uid
from test_schema4 import sql_project, sql_task, sql_work, sql_active


@pytest.fixture
def candidate(tmp_path):
    path = tmp_path / 'candidate' / 'chronicle.sqlite3'
    path.parent.mkdir()
    c = sqlite3.connect(path, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        schema.create_candidate(c, dataset_id=uid(), timezone='America/Chicago')
        yield c
    finally:
        if c.in_transaction:
            c.execute('ROLLBACK')
        c.close()


@pytest.fixture
def inflight(candidate):
    candidate.execute('BEGIN')
    yield candidate
    candidate.execute('ROLLBACK')


def facts(c):
    return {name: sorted([tuple(r) for r in c.execute('SELECT * FROM ' + name)], key=repr)
            for name, in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")}


def refused(c, sql, values, diagnostic):
    before = facts(c)
    with pytest.raises(sqlite3.IntegrityError, match=diagnostic):
        c.execute(sql, values)
    assert facts(c) == before


def export_task(c, task, group):
    # No export is registered: the deferred parent is intentionally absent.
    c.execute('INSERT INTO timesheet_export_tasks VALUES(?,?,?,?,?,?,?)',
              (uid(), task, 'Frozen ü Ω', group, 'Historical project name', 0, 0))


def test_exact_fresh_identity_profile_strict_inventory_and_no_readiness(candidate):
    c = candidate
    proof = schema.verify_candidate(c)
    assert proof.schema_version == 5 and proof.structural_verified is True
    assert proof.semantic_verified is False and proof.ordinary_startup_permitted is False
    assert not c.in_transaction
    assert c.execute('PRAGMA application_id').fetchone()[0] == 0x4348524E
    assert c.execute('PRAGMA user_version').fetchone()[0] == 5
    assert tuple(c.execute('PRAGMA ' + p).fetchone()[0] for p in
                 ('journal_mode', 'synchronous', 'foreign_keys')) == ('delete', 3, 1)
    assert schema.verify_structure(c).roots == ()
    assert not facts(c)['tasks'] and not facts(c)['projects']
    assert not facts(c)['committed_requests'] and not facts(c)['timesheet_exports']
    tables = {r[1]: r[5] for r in c.execute('PRAGMA table_list')}
    assert all(tables[t] == 1 for t in tables if not t.startswith('sqlite_'))
    assert len(facts(c)['dataset_meta']) == 1
    for table in ('tasks', 'timesheet_export_tasks'):
        assert next(r for r in c.execute('PRAGMA table_info(' + table + ')')
                    if r[1] == 'project_id')[3] == 1
        assert ('projects', 'project_id', 'project_id') in {
            (r[2], r[3], r[4]) for r in c.execute('PRAGMA foreign_key_list(' + table + ')')}
    assert next(r for r in c.execute('PRAGMA table_info(projects)')
                if r[1] == 'parent_project_id')[3] == 0


def test_only_two_ownership_definitions_differ_and_historical_ddl_is_preserved(candidate):
    def definitions(statements):
        return {re.match(r'CREATE (?:UNIQUE )?(?:TABLE|INDEX|TRIGGER) (\w+)', s)[1]: s
                for s in statements}
    old, new = definitions(historical.schema_statements()), definitions(schema.schema_statements())
    assert old.keys() == new.keys()
    assert {k for k in old if old[k] != new[k]} == {'tasks', 'timesheet_export_tasks'}
    # Explicit, bounded expected differences, independently checked against every
    # statement. Production schema 5 never constructs SQL through replacement.
    for table in ('tasks', 'timesheet_export_tasks'):
        needle = 'project_id TEXT REFERENCES projects(project_id)'
        assert old[table].count(needle) == 1
        assert new[table] == old[table].replace(needle, 'project_id TEXT NOT NULL REFERENCES projects(project_id)')
    assert hashlib.sha256(historical.SCHEMA.encode()).hexdigest() == 'ec4c8687cd13d5db79ad5031a7a3155bab7670ae1388f8b47bd468b7b4f1c467'
    from chronicle.sqlite_store import SCHEMA
    assert hashlib.sha256(SCHEMA.encode()).hexdigest() == '9557130e5bfdc2d5ff8ffbe1b8a26f19d74546e65b59eb3c02217295e4f42f49'
    assert historical.SCHEMA_VERSION == 4 and schema.SCHEMA_VERSION == 5
    assert schema.ADMINISTRATIVE_OPERATIONS == historical.ADMINISTRATIVE_OPERATIONS
    assert {r[0] for r in candidate.execute("SELECT name FROM sqlite_schema WHERE type='table'")} == {
        k for k, sql in new.items() if sql.startswith('CREATE TABLE')} | {'sqlite_sequence'}


@pytest.mark.parametrize('group,diagnostic', [(None, 'NOT NULL'), ('missing', 'FOREIGN KEY'), ('invalid', 'FOREIGN KEY')])
def test_task_insert_refuses_absent_or_nonexistent_real_project(inflight, group, diagnostic):
    c = inflight
    owner = None if group is None else uid() if group == 'missing' else 'not-a-project-uuid'
    before = facts(c)
    with pytest.raises(sqlite3.IntegrityError, match=diagnostic):
        sql_task(c, owner)
    assert facts(c) == before


@pytest.mark.parametrize('target', ['null', 'missing', 'different parent', 'different children'])
def test_task_updates_cannot_remove_or_split_project_ownership(inflight, target):
    c = inflight
    p, q = sql_project(c), sql_project(c)
    root = sql_task(c, p)
    child = sql_task(c, p, root)
    standalone = sql_task(c, p)
    key = child if target == 'different parent' else root if target == 'different children' else standalone
    value = None if target == 'null' else uid() if target == 'missing' else q
    diagnostic = 'NOT NULL' if target == 'null' else 'FOREIGN KEY' if target == 'missing' else 'project'
    refused(c, 'UPDATE tasks SET project_id=? WHERE task_id=?', (value, key), diagnostic)


def test_valid_root_child_and_subsubtask_keep_one_real_project_and_depth(inflight):
    c = inflight
    p, q = sql_project(c), sql_project(c)
    a = sql_task(c, p)
    b = sql_task(c, p, a)
    leaf = sql_task(c, p, b)
    assert [r[0] for r in c.execute('SELECT DISTINCT project_id FROM tasks')] == [p]
    assert [(r['task_id'], r['parent_task_id']) for r in c.execute('SELECT * FROM tasks')] == [(a, None), (b, a), (leaf, b)]
    for group, parent, reason in ((q, a, 'parent/project'), (p, leaf, 'depth')):
        before = facts(c)
        with pytest.raises(sqlite3.IntegrityError, match=reason):
            sql_task(c, group, parent)
        assert facts(c) == before
    refused(c, 'UPDATE tasks SET parent_task_id=? WHERE task_id=?', (leaf, a), 'cycle|depth')


def test_deep_real_project_ancestry_is_independent_and_root_reparent_remains_valid(inflight):
    c = inflight
    first = sql_project(c)
    deep = first
    for _ in range(sys.getrecursionlimit() + 10):
        deep = sql_project(c, parent=deep)
    task = sql_task(c, deep)
    child = sql_task(c, deep, task)
    leaf = sql_task(c, deep, child)
    assert c.execute('SELECT count(*) FROM projects').fetchone()[0] == sys.getrecursionlimit() + 11
    c.execute('UPDATE projects SET parent_project_id=NULL WHERE project_id=?', (deep,))
    assert c.execute('SELECT project_id FROM tasks WHERE task_id=?', (leaf,)).fetchone()[0] == deep
    assert {r[0] for r in c.execute('SELECT project_id FROM projects WHERE parent_project_id IS NULL')} == {first, deep}


@pytest.mark.parametrize('bad', ['self', 'missing', 'cycle'])
def test_project_parent_refusal_preserves_forest(inflight, bad):
    c = inflight
    p = sql_project(c)
    q = sql_project(c, parent=p)
    target = p if bad == 'self' else uid() if bad == 'missing' else q
    refused(c, 'UPDATE projects SET parent_project_id=? WHERE project_id=?', (target, p), 'project parent|cycle')


@pytest.mark.parametrize('group', ['null', 'missing', 'valid'])
def test_frozen_export_task_requires_real_owner_without_registering_a_report(inflight, group):
    c = inflight
    p = sql_project(c)
    t = sql_task(c, p)
    before = facts(c)
    if group == 'valid':
        export_task(c, t, p)
        row = c.execute('SELECT * FROM timesheet_export_tasks').fetchone()
        assert row['project_id'] == p and row['project_name'] == 'Historical project name'
        assert row['task_id'] == t and row['ordinal'] == 0
        assert not facts(c)['timesheet_exports'] and not facts(c)['committed_requests']
        refused(c, "UPDATE timesheet_export_tasks SET project_name='Rewritten'", (), 'immutable evidence')
        refused(c, 'DELETE FROM timesheet_export_tasks', (), 'immutable evidence')
    else:
        with pytest.raises(sqlite3.IntegrityError, match='NOT NULL' if group == 'null' else 'FOREIGN KEY'):
            export_task(c, t, None if group == 'null' else uid())
        assert facts(c) == before


@pytest.mark.parametrize('operation', ['archive project', 'archive task', 'reparent project', 'reparent task', 'add child'])
def test_active_sql_guards_and_identity_survive(inflight, operation):
    c = inflight
    p = sql_project(c)
    deep = sql_project(c, parent=p)
    archived = sql_project(c, archived=1)
    task = sql_task(c, deep)
    entry = sql_work(c, task)
    sql_active(c, task, entry)
    before = facts(c)
    with pytest.raises(sqlite3.IntegrityError, match='active timer|running task'):
        if operation == 'archive project':
            c.execute('UPDATE projects SET is_archived=1,archived_at_utc_us=? WHERE project_id=?', (NOW, p))
        elif operation == 'archive task':
            c.execute('UPDATE tasks SET is_archived=1,archived_at_utc_us=? WHERE task_id=?', (NOW, task))
        elif operation == 'reparent project':
            c.execute('UPDATE projects SET parent_project_id=? WHERE project_id=?', (archived, p))
        elif operation == 'reparent task':
            c.execute('UPDATE tasks SET project_id=? WHERE task_id=?', (archived, task))
        else:
            sql_task(c, deep, task)
    assert facts(c) == before


@pytest.mark.parametrize('target', ['timed', 'date-only', 'active'])
def test_archived_project_ancestry_blocks_new_work_and_active_insert(inflight, target):
    c = inflight
    p = sql_project(c)
    q = sql_project(c, parent=p)
    task = sql_task(c, q)
    entry = sql_work(c, task) if target == 'active' else uid()
    c.execute('UPDATE projects SET is_archived=1,archived_at_utc_us=? WHERE project_id=?', (NOW, p))
    before = facts(c)
    with pytest.raises(sqlite3.IntegrityError, match='active leaf'):
        if target == 'active':
            sql_active(c, task, entry)
        elif target == 'timed':
            sql_work(c, task)
        else:
            c.execute("INSERT INTO work_entries(entry_id,task_id,kind,current_revision,created_request_id) VALUES(?,?,'date_only',1,?)", (entry, task, uid()))
    assert facts(c) == before


@pytest.mark.parametrize('damage', ['version', 'application', 'index', 'trigger', 'changed trigger', 'column', 'extra', 'sqlite-like extra', 'view', 'profile', 'journal', 'synchronous', 'strict'])
def test_exact_schema_verification_refuses_changed_identity_objects_and_profile(candidate, damage):
    c = candidate
    if damage == 'version': c.execute('PRAGMA user_version=4')
    elif damage == 'application': c.execute('PRAGMA application_id=123')
    elif damage == 'index': c.execute('DROP INDEX projects_parent')
    elif damage == 'trigger': c.execute('DROP TRIGGER tasks_forest_insert')
    elif damage == 'changed trigger':
        c.execute('DROP TRIGGER immutable_committed_requests_update')
        c.execute("CREATE TRIGGER immutable_committed_requests_update BEFORE UPDATE ON committed_requests BEGIN SELECT RAISE(ABORT,'Immutable evidence'); END")
    elif damage == 'column': c.execute('ALTER TABLE projects ADD COLUMN unexpected TEXT')
    elif damage in ('extra', 'sqlite-like extra'):
        c.execute('CREATE TABLE ' + ('other' if damage == 'extra' else 'sqliteXother') + '(x INTEGER) STRICT')
    elif damage == 'view': c.execute('CREATE VIEW extra_view AS SELECT * FROM tasks')
    elif damage == 'profile': c.execute('PRAGMA foreign_keys=OFF')
    elif damage == 'journal': c.execute('PRAGMA journal_mode=WAL')
    elif damage == 'synchronous': c.execute('PRAGMA synchronous=NORMAL')
    else:
        c.execute('PRAGMA writable_schema=ON')
        c.execute("UPDATE sqlite_schema SET sql=replace(sql,') STRICT',')') WHERE name='dataset_meta'")
        c.execute('PRAGMA writable_schema=RESET')
    with pytest.raises(ValueError):
        schema.verify_candidate(c)
    assert not c.in_transaction


@pytest.mark.parametrize('namespace', ['temp', 'attached'])
def test_shadow_or_attached_namespace_refuses(candidate, namespace, tmp_path):
    c = candidate
    if namespace == 'temp': c.execute('CREATE TEMP TABLE tasks(fake TEXT)')
    else: c.execute('ATTACH DATABASE ? AS other', (str(tmp_path / 'other.sqlite3'),))
    before = facts(c)
    with pytest.raises(ValueError, match='unshadowed, unattached'):
        schema.verify_candidate(c)
    assert facts(c) == before


@pytest.mark.parametrize('damage', ['missing metadata', 'timezone', 'reminder date'])
def test_basic_metadata_is_not_replaced_by_exact_ddl(candidate, damage):
    c = candidate
    if damage == 'missing metadata': c.execute('DELETE FROM dataset_meta')
    elif damage == 'timezone': c.execute("UPDATE dataset_meta SET timezone='Unknown/Zone'")
    else: c.execute("UPDATE dataset_meta SET polr_reminder_dismissed_local_date='2026-02-30'")
    with pytest.raises(ValueError): schema.verify_candidate(c)
    assert not c.in_transaction


def test_structural_verifier_does_not_ignore_unfilled_deferred_foreign_keys(inflight):
    sql_project(inflight)
    before = facts(inflight)
    with pytest.raises(ValueError, match='integrity or foreign key'):
        schema.verify_structure(inflight)
    assert inflight.in_transaction and facts(inflight) == before


def test_structural_snapshot_is_read_only_and_rejects_an_owned_transaction(candidate):
    c = candidate
    path = Path(c.execute('PRAGMA database_list').fetchone()[2])
    before = path.read_bytes(), facts(c)
    statements = []
    c.set_trace_callback(statements.append)
    try:
        schema.verify_candidate(c)
    finally:
        c.set_trace_callback(None)
    assert (path.read_bytes(), facts(c)) == before
    assert statements[0] == 'BEGIN' and statements[-1] == 'ROLLBACK'
    assert all(s.startswith(('SELECT', 'PRAGMA', 'BEGIN', 'ROLLBACK')) for s in statements)
    c.execute('BEGIN')
    try:
        with pytest.raises(ValueError, match='completed transaction'):
            schema.verify_candidate(c)
        assert c.in_transaction and facts(c) == before[1]
    finally:
        c.execute('ROLLBACK')


def test_version5_marker_does_not_admit_schema4_ddl(tmp_path):
    c = sqlite3.connect(tmp_path / 'v4.sqlite3', isolation_level=None)
    try:
        historical.create_candidate(c, dataset_id=uid(), timezone='UTC')
        c.execute('PRAGMA user_version=5')
        with pytest.raises(ValueError, match='definitions differ'): schema.verify_candidate(c)
        c.execute('PRAGMA user_version=4')
        assert historical.verify_candidate(c).schema_version == 4
    finally: c.close()


@pytest.mark.parametrize('occupied', ['table', 'version', 'application', 'transaction', 'schema3', 'schema4'])
def test_creation_refuses_occupied_database_before_mutation(tmp_path, occupied):
    directory = tmp_path / 'old'
    directory.mkdir()
    path = directory / 'chronicle.sqlite3'
    if occupied in ('schema3', 'schema4'):
        owner = SQLiteStore(directory, create=True, timezone='UTC', schema_version=int(occupied[-1]))
        owner.close()
    c = sqlite3.connect(path, isolation_level=None)
    try:
        if occupied == 'table': c.execute('CREATE TABLE retained(value TEXT)')
        elif occupied == 'version': c.execute('PRAGMA user_version=4')
        elif occupied == 'application': c.execute('PRAGMA application_id=123')
        elif occupied == 'transaction': c.execute('BEGIN')
        before = path.read_bytes(), facts(c), c.in_transaction
        with pytest.raises(ValueError, match='empty new database'):
            schema.create_candidate(c, dataset_id=uid(), timezone='UTC')
        assert (path.read_bytes(), facts(c), c.in_transaction) == before
    finally:
        if c.in_transaction: c.execute('ROLLBACK')
        c.close()


@pytest.mark.parametrize('kind', ['memory', 'bad uuid', 'absent timezone', 'invalid timezone'])
def test_candidate_requires_explicit_valid_identity_timezone_and_file(tmp_path, kind):
    c = sqlite3.connect(':memory:' if kind == 'memory' else tmp_path / 'empty.sqlite3', isolation_level=None)
    try:
        with pytest.raises(ValueError):
            schema.create_candidate(c, dataset_id='bad' if kind == 'bad uuid' else uid(),
                                    timezone=None if kind == 'absent timezone' else 'Unknown/Zone' if kind == 'invalid timezone' else 'UTC')
        assert not list(c.execute('SELECT name FROM sqlite_schema'))
        assert c.execute('PRAGMA user_version').fetchone()[0] == 0
    finally: c.close()


@pytest.mark.parametrize('phase', ['ddl', 'metadata', 'verify', 'commit', 'rollback'])
def test_failed_construction_rolls_back_and_retains_primary_error(tmp_path, phase):
    c = sqlite3.connect(tmp_path / 'failed.sqlite3', isolation_level=None)
    primary = OSError('original construction fault')
    class Fault:
        @property
        def in_transaction(self): return c.in_transaction
        def execute(self, sql, *args):
            if (phase in ('ddl', 'rollback') and sql.startswith('CREATE TABLE projects')
                    or phase == 'metadata' and sql.startswith('INSERT INTO dataset_meta')
                    or phase == 'verify' and sql == 'PRAGMA main.integrity_check'
                    or phase == 'commit' and sql == 'COMMIT'):
                raise primary
            if phase == 'rollback' and sql == 'ROLLBACK': raise OSError('rollback fault')
            return c.execute(sql, *args)
    try:
        with pytest.raises(OSError) as caught:
            schema.create_candidate(Fault(), dataset_id=uid(), timezone='UTC')
        assert caught.value is primary
        if phase == 'rollback':
            assert c.in_transaction and 'construction rollback also failed' in primary.__notes__[0]
            c.execute('ROLLBACK')
        assert not c.in_transaction and not list(c.execute('SELECT name FROM sqlite_schema'))
        assert c.execute('PRAGMA user_version').fetchone()[0] == 0
        assert c.execute('PRAGMA application_id').fetchone()[0] == 0
    finally: c.close()


def test_verification_rollback_failure_never_returns_structural_proof(candidate):
    class Fault:
        @property
        def in_transaction(self): return candidate.in_transaction
        def execute(self, sql, *args):
            if sql == 'ROLLBACK': raise OSError('verification close fault')
            return candidate.execute(sql, *args)
    with pytest.raises(OSError, match='verification close fault'): schema.verify_candidate(Fault())
    assert candidate.in_transaction


@pytest.mark.parametrize('version', [None, 5])
def test_current_runtime_defaults_and_policy_do_not_activate_schema5(candidate, version):
    for factory in (SQLiteStore, DatabaseWorker, StartupWindow):
        assert inspect.signature(factory).parameters['schema_version'].default == 4
    with pytest.raises(ValueError, match='explicit supported schema policy'): policy_for(5)
    with pytest.raises(ValueError, match='explicit schema-4 store'):
        Schema4RuntimeService(SimpleNamespace(schema_version=5))
    for profile in ('schema3', 'schema4', 'schema4-candidate'):
        assert not backend_profile_matches(profile, dict(schema_version=5,
            semantic_verified=True, ordinary_startup_permitted=True))
    path = Path(candidate.execute('PRAGMA database_list').fetchone()[2])
    before = path.read_bytes()
    with pytest.raises(ValueError, match='require schema 4'): SQLiteStore(path.parent)
    with pytest.raises(ValueError, match='explicit supported schema policy'):
        SQLiteStore(path.parent, schema_version=5)
    assert path.read_bytes() == before and not (path.parent / '.chronicle.lock').exists()
    worker = DatabaseWorker(path.parent, **({} if version is None else {'schema_version': version}))
    worker.start()
    try:
        first = worker.results.get(timeout=15)
        assert first.kind == 'startup_failed'
        assert ('require schema 4' if version is None else 'explicit supported schema policy') in str(first.value)
        assert worker.results.get(timeout=15).kind == 'stopped'
    finally:
        worker.join(15)
        assert not worker.is_alive()
    assert path.read_bytes() == before and not (path.parent / '.chronicle.lock').exists()
