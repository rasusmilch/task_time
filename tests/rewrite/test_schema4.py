"""Real SQLite candidate safeguards; in-flight SQL fixtures are not service evidence."""
import hashlib
import re
import sqlite3
import sys
from datetime import timezone
from types import SimpleNamespace

import pytest

from chronicle import schema_profiles as candidate_schema
from chronicle import sqlite_store as runtime
from chronicle.records import Request, canonical, receipt_class, Outcome
from chronicle.services import TimerService
from conftest import NOW, uid


@pytest.fixture
def candidate(tmp_path):
    path=tmp_path/'candidate'/runtime.DATABASE;path.parent.mkdir()
    c=sqlite3.connect(path,isolation_level=None);c.row_factory=sqlite3.Row
    try:
        candidate_schema.create_candidate(c,dataset_id=uid(),timezone='UTC')
        yield c
    finally:
        if c.in_transaction:c.execute('ROLLBACK')
        c.close()


def sql_project(c,key=None,parent=None,archived=0):
    """In-flight rows; the caller rolls back unfilled deferred receipt references."""
    key=key or uid()
    c.execute('INSERT INTO projects(project_id,parent_project_id,name,version,is_archived,archived_at_utc_us,created_request_id,created_utc_us,updated_utc_us) VALUES(?,?,?,1,?,?,?,?,?)',
              (key,parent,'Duplicate',archived,NOW if archived else None,uid(),NOW,NOW))
    return key


def sql_task(c,project=None,parent=None,key=None,archived=0):
    key=key or uid()
    c.execute('INSERT INTO tasks(task_id,project_id,parent_task_id,name,version,is_archived,archived_at_utc_us,created_request_id,created_utc_us,updated_utc_us) VALUES(?,?,?, ?,1,?,?,?,?,?)',
              (key,project,parent,'Task',archived,NOW if archived else None,uid(),NOW,NOW))
    return key


def sql_work(c,task,entry=None):
    entry=entry or uid()
    c.execute("INSERT INTO work_entries(entry_id,task_id,kind,original_start_utc_us,current_revision,created_request_id) VALUES(?,?,'timed',?,NULL,?)",(entry,task,NOW,uid()))
    return entry


def sql_active(c,task,entry):
    c.execute('INSERT INTO active_timer(singleton,entry_id,task_id,start_utc_us,version) VALUES(1,?,?,?,1)',(entry,task,NOW))


def test_exact_empty_candidate_and_scoped_verification_are_not_runtime_readiness(candidate):
    c=candidate
    result=candidate_schema.verify_candidate(c)
    assert result.schema_version==4 and result.structural_verified and result.administrative_history_verified
    assert result.ordinary_startup_permitted is False and not c.in_transaction
    assert c.execute('PRAGMA application_id').fetchone()[0]==0x4348524E
    assert tuple(c.execute(f'PRAGMA {name}').fetchone()[0] for name in ('journal_mode','synchronous','foreign_keys'))==('delete',3,1)
    assert 'parent_project_id' in {r[1] for r in c.execute('PRAGMA table_info(projects)')}
    assert ('projects', 'parent_project_id', 'project_id') in {(r[2],r[3],r[4]) for r in c.execute('PRAGMA foreign_key_list(projects)')}
    assert [r[2] for r in c.execute('PRAGMA index_info(projects_parent)')]==['parent_project_id']
    tables={r[1]:r[5] for r in c.execute('PRAGMA table_list')}
    assert all(v==1 for k,v in tables.items() if not k.startswith('sqlite_'))
    assert not any(word in k.lower() for k in tables for word in ('customer','closure','transition','migration','project_work'))


@pytest.mark.parametrize('damage',['version','application','index','trigger','table','extra','sqlite-like extra','quoted literal','profile'])
def test_candidate_exact_admission_refuses_changed_schema_or_profile(candidate,damage):
    c=candidate
    if damage=='version':c.execute('PRAGMA user_version=3')
    if damage=='application':c.execute('PRAGMA application_id=1')
    if damage=='index':c.execute('DROP INDEX projects_parent')
    if damage=='trigger':c.execute('DROP TRIGGER immutable_committed_requests_update')
    if damage=='table':c.execute('ALTER TABLE projects ADD COLUMN unexpected TEXT')
    if damage=='extra':c.execute('CREATE TABLE other(x INTEGER) STRICT')
    if damage=='sqlite-like extra':c.execute('CREATE TABLE sqliteXother(x INTEGER) STRICT')
    if damage=='quoted literal':
        c.execute('DROP TRIGGER immutable_committed_requests_update')
        c.execute("CREATE TRIGGER immutable_committed_requests_update BEFORE UPDATE ON committed_requests BEGIN SELECT RAISE(ABORT,'Immutable evidence'); END")
    if damage=='profile':c.execute('PRAGMA foreign_keys=OFF')
    with pytest.raises(ValueError):candidate_schema.verify_candidate(c)


@pytest.mark.parametrize('bad',['self','missing','uuid','cycle'])
def test_direct_sql_project_edges_refuse(candidate,bad):
    c=candidate;c.execute('BEGIN')
    a=sql_project(c);b=sql_project(c,parent=a)
    if bad=='self':statement,args='UPDATE projects SET parent_project_id=? WHERE project_id=?',(a,a)
    if bad=='missing':statement,args='UPDATE projects SET parent_project_id=? WHERE project_id=?',(uid(),b)
    if bad=='uuid':statement,args='UPDATE projects SET parent_project_id=? WHERE project_id=?',('bad',b)
    if bad=='cycle':statement,args='UPDATE projects SET parent_project_id=? WHERE project_id=?',(b,a)
    before=[tuple(r) for r in c.execute('SELECT * FROM projects ORDER BY project_id')]
    with pytest.raises(sqlite3.IntegrityError):c.execute(statement,args)
    assert [tuple(r) for r in c.execute('SELECT * FROM projects ORDER BY project_id')]==before


def test_sql_deep_ancestor_recording_guard_and_cycle_walk_are_complete(candidate):
    c=candidate;c.execute('BEGIN');keys=[]
    for i in range(sys.getrecursionlimit()+20):
        keys.append(sql_project(c,parent=keys[-1] if keys else None,archived=int(i==0)))
    task=sql_task(c,keys[-1])
    with pytest.raises(sqlite3.IntegrityError,match='active leaf'):sql_work(c,task)
    with pytest.raises(sqlite3.IntegrityError,match='cycle'):c.execute('UPDATE projects SET parent_project_id=? WHERE project_id=?',(keys[-1],keys[0]))
    assert c.execute('SELECT count(*) FROM projects').fetchone()[0]==len(keys)
    assert not list(c.execute('SELECT * FROM work_entries'))


@pytest.mark.parametrize('target',['work_entries','date-only work','active_timer'])
def test_sql_recording_and_active_insert_reject_inherited_archive(candidate,target):
    c=candidate;c.execute('BEGIN')
    a=sql_project(c);b=sql_project(c,parent=a);t=sql_task(c,b)
    entry=sql_work(c,t) if target=='active_timer' else uid()
    c.execute('UPDATE projects SET is_archived=1,archived_at_utc_us=? WHERE project_id=?',(NOW,a))
    with pytest.raises(sqlite3.IntegrityError,match='active leaf'):
        if target=='active_timer':sql_active(c,t,entry)
        elif target=='date-only work':
            c.execute("INSERT INTO work_entries(entry_id,task_id,kind,current_revision,created_request_id) VALUES(?,?,'date_only',1,?)",(entry,t,uid()))
        else:sql_work(c,t,entry)
    assert not list(c.execute('SELECT * FROM active_timer'))


@pytest.mark.parametrize('bad',['self','missing','invalid parent UUID'])
def test_direct_sql_project_insert_rejects_invalid_parent(candidate,bad):
    candidate.execute('BEGIN');identity=uid()
    parent=identity if bad=='self' else uid() if bad=='missing' else 'invalid'
    with pytest.raises(sqlite3.IntegrityError):sql_project(candidate,key=identity,parent=parent)
    assert not list(candidate.execute('SELECT * FROM projects'))


@pytest.mark.parametrize('operation',['archive ancestor','reparent ancestor','reparent task','reparent under archived task'])
def test_sql_active_task_cannot_be_hidden(candidate,operation):
    c=candidate;c.execute('BEGIN')
    a=sql_project(c);b=sql_project(c,parent=a);z=sql_project(c,archived=1)
    t=sql_task(c,b);e=sql_work(c,t);sql_active(c,t,e)
    before=tuple(c.execute('SELECT * FROM active_timer').fetchone())
    with pytest.raises(sqlite3.IntegrityError):
        if operation=='archive ancestor':c.execute('UPDATE projects SET is_archived=1,archived_at_utc_us=? WHERE project_id=?',(NOW,a))
        if operation=='reparent ancestor':c.execute('UPDATE projects SET parent_project_id=? WHERE project_id=?',(z,a))
        if operation=='reparent task':c.execute('UPDATE tasks SET project_id=? WHERE task_id=?',(z,t))
        if operation=='reparent under archived task':
            parent=sql_task(c,b,archived=1)
            c.execute('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(parent,t))
    assert tuple(c.execute('SELECT * FROM active_timer').fetchone())==before
    assert c.execute('SELECT project_id FROM tasks WHERE task_id=?',(t,)).fetchone()[0]==b


def test_sql_safe_reparent_preserves_active_identity_and_task_membership(candidate):
    c=candidate;c.execute('BEGIN');a=sql_project(c);b=sql_project(c,parent=a);z=sql_project(c)
    t=sql_task(c,b);e=sql_work(c,t);sql_active(c,t,e)
    before=[tuple(r) for r in c.execute('SELECT * FROM active_timer')]
    c.execute('UPDATE projects SET parent_project_id=? WHERE project_id=?',(z,a))
    assert [tuple(r) for r in c.execute('SELECT * FROM active_timer')]==before
    assert c.execute('SELECT project_id FROM tasks WHERE task_id=?',(t,)).fetchone()[0]==b


def test_three_task_levels_remain_separate_from_projects(candidate):
    c=candidate;c.execute('BEGIN');p=None
    for _ in range(8):p=sql_project(c,parent=p)
    a=sql_task(c,p);b=sql_task(c,p,a);leaf=sql_task(c,p,b)
    with pytest.raises(sqlite3.IntegrityError,match='depth'):sql_task(c,p,leaf)
    with pytest.raises(sqlite3.IntegrityError,match='active leaf'):sql_work(c,a)
    entry=sql_work(c,leaf);sql_active(c,leaf,entry)
    assert c.execute('SELECT task_id FROM active_timer').fetchone()[0]==leaf


def test_existing_protected_receipt_work_and_active_identity_guards(candidate):
    c=candidate;c.execute('BEGIN');p=sql_project(c);t=sql_task(c,p);entry=sql_work(c,t);sql_active(c,t,entry)
    request=Request.make(uid(),c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0],'set_week_start',NOW,week_start=0,expected_week_start=6)
    c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
              (request.request_id,request.operation,'protected',request.content(),canonical({'week_start':0}),NOW))
    for sql,args in [('UPDATE committed_requests SET action_utc_us=? WHERE request_id=?',(NOW+1,request.request_id)),
                     ('DELETE FROM committed_requests WHERE request_id=?',(request.request_id,)),
                     ('DELETE FROM work_entries WHERE entry_id=?',(entry,)),
                     ('UPDATE work_entries SET task_id=? WHERE entry_id=?',(uid(),entry)),
                     ('UPDATE active_timer SET task_id=? WHERE entry_id=?',(uid(),entry))]:
        with pytest.raises(sqlite3.IntegrityError):c.execute(sql,args)
    assert c.execute('SELECT count(*) FROM work_entries').fetchone()[0]==1


def test_all_unchanged_schema3_evidence_definitions_are_identical():
    def definitions(statements):
        return {re.match(r'CREATE (?:UNIQUE )?(?:TABLE|INDEX|TRIGGER) (\w+)',s)[1]:s for s in statements}
    old,new=definitions(runtime.schema_statements()),definitions(candidate_schema.schema_statements())
    changed={'projects','committed_requests','work_entries_eligible_task','active_timer_eligible_task','projects_archive_active'}
    assert all(new[name]==definition for name,definition in old.items() if name not in changed)
    assert set(new)-set(old)=={'projects_parent','projects_forest_insert','projects_forest_update','projects_parent_active','tasks_active_ancestry'}
    assert set(old)<=set(new)


def test_candidate_is_not_ordinary_startup_and_never_creates_owner_lock(candidate):
    path=next(r[2] for r in candidate.execute('PRAGMA database_list') if r[1]=='main')
    from pathlib import Path
    directory=Path(path).parent;before=Path(path).read_bytes()
    with pytest.raises(ValueError,match='require version 3'):runtime.SQLiteStore(directory, schema_version=3)
    assert Path(path).read_bytes()==before and not (directory/'.chronicle.lock').exists()


def test_schema3_definition_classification_and_service_dispatch_stay_isolated(tmp_path):
    c=sqlite3.connect(tmp_path/'ordinary-sql.sqlite3',isolation_level=None)
    try:
        for statement in runtime.schema_statements():c.execute(statement)
        runtime.SQLiteStore._verify_schema(c)
        assert hashlib.sha256(runtime.SCHEMA.encode()).hexdigest()=='9557130e5bfdc2d5ff8ffbe1b8a26f19d74546e65b59eb3c02217295e4f42f49'
        assert runtime.SCHEMA_VERSION==3 and candidate_schema.SCHEMA_VERSION==4
        assert not {'create_child_project','move_project_subtree'} & runtime.ADMINISTRATIVE_OPERATIONS
        # A real v3 SQL boundary plus a narrow transaction double: no calendar
        # dependency or claim of complete runtime startup in this dispatch test.
        def transact(request,operation):
            before=c.total_changes;c.execute('BEGIN IMMEDIATE')
            try:operation(c)
            except ValueError as exc:
                assert c.total_changes==before
                return Outcome('rejected',error=exc)
            finally:c.execute('ROLLBACK')
            raise AssertionError('Candidate operation reached schema-3 execution')
        service=TimerService(SimpleNamespace(zone=timezone.utc,transact=transact))
        for operation in ('create_child_project','move_project_subtree'):
            assert receipt_class(operation)=='protected'
            request=Request.make(uid(),uid(),operation,NOW)
            result=service.execute(request)
            assert result.status=='rejected' and 'Unknown operation' in str(result.error)
            with pytest.raises(sqlite3.IntegrityError):
                c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                          (request.request_id,operation,'administrative',request.content(),canonical({}),NOW))
        assert not list(c.execute('SELECT * FROM committed_requests'))
    finally:c.close()


def test_candidate_constructor_refuses_schema3_without_changing_it(tmp_path):
    path=tmp_path/'ordinary.sqlite3'
    c=sqlite3.connect(path,isolation_level=None)
    try:
        for statement in runtime.schema_statements():c.execute(statement)
        c.execute('PRAGMA user_version=3');c.execute(f'PRAGMA application_id={runtime.APPLICATION_ID}')
        before=path.read_bytes()
        with pytest.raises(ValueError,match='empty new'):candidate_schema.create_candidate(c,dataset_id=uid(),timezone='UTC')
        assert path.read_bytes()==before
    finally:c.close()


def test_native_schema3_creation_receipt_still_passes_existing_independent_verifier(tmp_path):
    c=sqlite3.connect(tmp_path/'v3-history.sqlite3',isolation_level=None);c.row_factory=sqlite3.Row
    try:
        c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA synchronous=EXTRA')
        for statement in runtime.schema_statements():c.execute(statement)
        dataset,project=uid(),uid()
        request=Request.make(uid(),dataset,'create_project',NOW,project_id=project,name='Ordinary v3')
        result=dict(project_id=project,version=1)
        c.execute('BEGIN')
        c.execute('INSERT INTO dataset_meta(singleton,dataset_id,timezone,week_start) VALUES(1,?,?,6)',(dataset,'UTC'))
        c.execute('INSERT INTO projects(project_id,name,version,created_request_id,created_utc_us,updated_utc_us) VALUES(?,?,1,?,?,?)',
                  (project,'Ordinary v3',request.request_id,NOW,NOW))
        c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                  (request.request_id,request.operation,'administrative',request.content(),canonical(result),NOW))
        c.execute('PRAGMA user_version=3');c.execute(f'PRAGMA application_id={runtime.APPLICATION_ID}')
        c.execute('COMMIT')
        runtime.SQLiteStore._verify_schema(c)
        runtime.SQLiteStore.verify_administration(c,{request.request_id:(request,result)})
        assert not list(c.execute('PRAGMA foreign_key_check'))
        assert 'parent_project_id' not in {r[1] for r in c.execute('PRAGMA table_info(projects)')}
    finally:c.close()


@pytest.mark.parametrize('namespace',['temp','attached'])
def test_candidate_cannot_validate_shadow_tables_or_attached_authorities(candidate,namespace):
    if namespace=='temp':candidate.execute('CREATE TEMP TABLE projects(project_id TEXT)')
    else:candidate.execute("ATTACH DATABASE ':memory:' AS other")
    with pytest.raises(ValueError,match='unshadowed'):candidate_schema.verify_candidate(candidate)


def test_damaged_cycle_is_refused_and_sql_traversal_terminates(candidate):
    from test_schema4_history import History,key
    h=History(candidate);h.install()
    guard=candidate.execute("SELECT sql FROM sqlite_schema WHERE name='projects_forest_update'").fetchone()[0]
    candidate.execute('DROP TRIGGER projects_forest_update')
    candidate.execute('UPDATE projects SET parent_project_id=? WHERE project_id=?',(key(4),key(1)))
    candidate.execute(guard)
    candidate_schema.verify_schema(candidate)
    with pytest.raises(ValueError,match='cycle'):candidate_schema.verify_structure(candidate)
    # A finite progress watchdog would fail this test if UNION ever became an
    # unbounded cyclic walk. It is not a product project-depth limit.
    ticks=[]
    candidate.set_progress_handler(lambda:ticks.append(True) or int(len(ticks)>100),100)
    try:
        candidate.execute('BEGIN')
        with pytest.raises(sqlite3.IntegrityError,match='cycle'):sql_project(candidate,parent=key(3))
        assert len(ticks)<=100
    finally:
        candidate.set_progress_handler(None,0)


@pytest.mark.parametrize('fault',['ddl','rollback'])
def test_candidate_construction_failure_never_leaves_a_supported_schema(tmp_path,fault):
    c=sqlite3.connect(tmp_path/'partial.sqlite3',isolation_level=None)
    error=OSError('Candidate DDL fault')
    class Fault:
        @property
        def in_transaction(self):return c.in_transaction
        def execute(self,sql,*args):
            if sql.startswith('CREATE TABLE projects'):raise error
            if sql=='ROLLBACK' and fault=='rollback':raise OSError('Rollback fault')
            return c.execute(sql,*args)
    try:
        with pytest.raises(OSError) as caught:candidate_schema.create_candidate(Fault(),dataset_id=uid(),timezone='UTC')
        assert caught.value is error and c.execute('PRAGMA user_version').fetchone()[0]==0
        if fault=='rollback':assert 'rollback also failed' in error.__notes__[0]
        if c.in_transaction:c.execute('ROLLBACK')
        assert not list(c.execute("SELECT name FROM sqlite_schema WHERE type='table'"))
    finally:c.close()


@pytest.mark.parametrize('invalid',[False,True])
def test_candidate_verification_cleanup_failure_never_reports_success(candidate,invalid):
    if invalid:candidate.execute('PRAGMA user_version=3')
    failure=OSError('verification rollback fault')
    class Fault:
        @property
        def in_transaction(self):return candidate.in_transaction
        def execute(self,sql,*args):
            if sql=='ROLLBACK':raise failure
            return candidate.execute(sql,*args)
    with pytest.raises(ValueError if invalid else OSError) as caught:
        candidate_schema.verify_candidate(Fault())
    if invalid:assert 'verification rollback also failed' in caught.value.__notes__[0]
    else:assert caught.value is failure
    assert candidate.in_transaction
