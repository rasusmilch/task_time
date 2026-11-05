"""Package B: real owned transactions, independent replay and immutable facts.

SQL-only archive/work fixtures below do not claim candidate runtime admission.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json
import os
from pathlib import Path
from queue import Queue
import sqlite3
import subprocess
import sys
from threading import Thread

import pytest

from chronicle import schema_profiles as schema, sqlite_store as runtime
from chronicle.administration import UnsupportedCandidateOperation
from chronicle.project_services import CandidateProjectContext, apply_project_operation, OPERATIONS
from chronicle.records import Request, canonical
from conftest import NOW, uid
from project_candidate import CandidateAdapter, facts
from test_schema4_history import History, key
from test_schema4 import sql_project, sql_task, sql_work, sql_active


@pytest.fixture
def adapter(tmp_path):
    path = tmp_path/'candidate.sqlite3'
    c = sqlite3.connect(path, isolation_level=None)
    dataset = uid()
    try:
        schema.create_candidate(c, dataset_id=dataset, timezone='UTC')
    finally:
        c.close()
    return CandidateAdapter(path, dataset)


@pytest.fixture
def populated(adapter):
    c = adapter.connect()
    try:
        h = History(c)
        h.install()
    finally:
        c.close()
    return adapter


def snapshot(adapter):
    c = adapter.connect(readonly=True)
    try:
        c.execute('BEGIN')
        value = facts(c)
        c.execute('ROLLBACK')
        return value
    finally:
        c.close()


def request(adapter, operation, **args):
    if operation=='create_task' and 'reviewed_destination_project_ancestry' not in args:
        state=snapshot(adapter);projects={p['project_id']:p for p in state['projects']}
        group=args.get('project_id')
        if args.get('parent_task_id') is not None:group=next(t['project_id'] for t in state['tasks'] if t['task_id']==args['parent_task_id'])
        args=dict(args,reviewed_destination_project_ancestry=ancestry(projects,group))
    return Request.make(uid(), adapter.context.dataset_id, operation, NOW+100, **args)


def ancestry(projects, parent):
    """Test review, constructed by following explicit persisted parent edges."""
    rows = []
    while parent is not None:
        row = projects[parent]
        rows.insert(0, dict(project_id=parent, expected_version=row['version'],
                            parent_project_id=row['parent_project_id']))
        parent = row['parent_project_id']
    return rows


def create(adapter, identity=None, parent=None, name=' Duplicate '):
    args = dict(project_id=identity or uid(), name=name)
    op = 'create_project'
    if parent is not None:
        projects = {r['project_id']:r for r in snapshot(adapter)['projects']}
        args.update(parent_project_id=parent, expected_parent_version=projects[parent]['version'],
                    reviewed_parent_ancestry=ancestry(projects, parent))
        op = 'create_child_project'
    frozen = request(adapter, op, **args)
    result = adapter.execute(frozen)
    assert result.status == 'committed', result
    return frozen


def review(adapter, source=key(3), destination=key(2)):
    state = snapshot(adapter)
    projects = {r['project_id']:r for r in state['projects']}
    row = projects[source]
    branch = {source}
    while True:
        extra = {r['project_id'] for r in projects.values() if r['parent_project_id'] in branch}
        if extra <= branch:
            break
        branch |= extra
    return dict(project_id=source, expected_version=row['version'], source_parent_project_id=row['parent_project_id'],
                destination_parent_project_id=destination,
                expected_destination_parent_version=projects[destination]['version'] if destination in projects else (None if destination is None else 1),
                reviewed_source_ancestry=ancestry(projects, row['parent_project_id']),
                reviewed_destination_ancestry=ancestry(projects, destination) if destination in projects else [],
                reviewed_projects=[dict(project_id=k, expected_version=projects[k]['version'], parent_project_id=projects[k]['parent_project_id']) for k in sorted(branch)],
                reviewed_tasks=sorted([dict(task_id=t['task_id'], expected_version=t['version'], parent_task_id=t['parent_task_id'], project_id=t['project_id'])
                                       for t in state['tasks'] if t['project_id'] in branch], key=lambda t:t['task_id']))


def moved(adapter, **kwargs):
    frozen = request(adapter, 'move_project_subtree', **review(adapter, **kwargs))
    result = adapter.execute(frozen)
    assert result.status == 'committed', result
    return frozen, result


def assert_rejected_unchanged(adapter, frozen):
    before = snapshot(adapter)
    result = adapter.execute(frozen)
    assert result.status == 'rejected', result
    assert snapshot(adapter) == before
    return result


def test_explicit_classification_preserves_exact_reviewed_ddls(monkeypatch):
    from chronicle import records
    expected3 = frozenset(('create_project','rename_project','create_task','rename_task',
        'assign_task_to_project','move_task_branch','archive_project','unarchive_project',
        'archive_task','unarchive_task','create_template','edit_template','duplicate_template',
        'archive_template','unarchive_template','apply_template'))
    assert records.ADMINISTRATIVE_OPERATIONS == expected3
    assert schema.ADMINISTRATIVE_OPERATIONS == expected3 | {'create_child_project','move_project_subtree'}
    assert hashlib.sha256(runtime.SCHEMA.encode()).hexdigest() == '9557130e5bfdc2d5ff8ffbe1b8a26f19d74546e65b59eb3c02217295e4f42f49'
    before = schema.SCHEMA
    assert hashlib.sha256(before.encode()).hexdigest() == 'ec4c8687cd13d5db79ad5031a7a3155bab7670ae1388f8b47bd468b7b4f1c467'
    with monkeypatch.context() as patch:
        patch.setattr(records, 'ADMINISTRATIVE_OPERATIONS', expected3 | {'future_runtime_operation'})
        importlib.reload(schema)
        assert schema.SCHEMA == before
        assert 'future_runtime_operation' not in schema.ADMINISTRATIVE_OPERATIONS
    importlib.reload(schema)


def test_root_child_depth_duplicate_names_and_exact_creation_receipts(adapter):
    root = create(adapter)
    parent = root.args()['project_id']
    accepted = [root]
    for _ in range(6):
        child = create(adapter, parent=parent)
        accepted.append(child)
        parent = child.args()['project_id']
    second = create(adapter)
    accepted.append(second)
    state = snapshot(adapter)
    assert len(state['projects']) == 8 and not state['tasks']
    assert {r['name'] for r in state['projects']} == {'Duplicate'}
    assert all(r['version'] == 1 for r in state['projects'])
    for frozen in accepted:
        row = next(r for r in state['projects'] if r['project_id'] == frozen.args()['project_id'])
        assert row == dict(project_id=frozen.args()['project_id'], name='Duplicate',
            parent_project_id=frozen.args().get('parent_project_id'), version=1, is_archived=0,
            archived_at_utc_us=None, created_request_id=frozen.request_id,
            created_utc_us=frozen.action_utc_us, updated_utc_us=frozen.action_utc_us)
        receipt = next(r for r in state['committed_requests'] if r['request_id'] == frozen.request_id)
        assert receipt['request_bytes'] == frozen.content()
        assert receipt['result_bytes'] == canonical(dict(project_id=row['project_id'], version=1))
        assert receipt['receipt_class'] == 'administrative'
    assert not state['active_timer'] and not state['work_entries']


@pytest.mark.parametrize('bad', ['unknown parent','parent version','ancestor version','ancestor parent','incomplete ancestry',
    'extra ancestry field','missing ancestry field','boolean version','malformed parent','duplicate uuid','empty name','wrong name type',
    'malformed uuid','extra field','missing field'])
def test_invalid_child_creation_has_no_durable_effect(populated, bad):
    a = populated
    projects = {r['project_id']:r for r in snapshot(a)['projects']}
    args = dict(project_id=uid(), name='New', parent_project_id=key(4), expected_parent_version=1,
                reviewed_parent_ancestry=ancestry(projects,key(4)))
    if bad == 'unknown parent': args['parent_project_id'] = uid()
    if bad == 'parent version': args['expected_parent_version'] = 2
    if bad == 'ancestor version': args['reviewed_parent_ancestry'][0]['expected_version'] = 2
    if bad == 'ancestor parent': args['reviewed_parent_ancestry'][0]['parent_project_id'] = key(2)
    if bad == 'incomplete ancestry': args['reviewed_parent_ancestry'].pop(0)
    if bad == 'extra ancestry field': args['reviewed_parent_ancestry'][0]['name'] = 'wrong'
    if bad == 'missing ancestry field': del args['reviewed_parent_ancestry'][0]['parent_project_id']
    if bad == 'boolean version': args['reviewed_parent_ancestry'][0]['expected_version'] = True
    if bad == 'malformed parent': args['parent_project_id'] = 'Unassigned'
    if bad == 'duplicate uuid': args['project_id'] = key(3)
    if bad == 'empty name': args['name'] = ' \n\t'
    if bad == 'wrong name type': args['name'] = 7
    if bad == 'malformed uuid': args['project_id'] = 'not-uuid'
    if bad == 'extra field': args['inferred_project'] = key(2)
    if bad == 'missing field': del args['reviewed_parent_ancestry']
    assert_rejected_unchanged(a, request(a,'create_child_project',**args))


@pytest.mark.parametrize('bad', ['uuid','name','duplicate','parent inference'])
def test_root_creation_refuses_invalid_fields(populated,bad):
    args = dict(project_id=uid(),name='Root')
    if bad == 'uuid': args['project_id'] = 'INVALID'
    if bad == 'name': args['name'] = ''
    if bad == 'duplicate': args['project_id'] = key(1)
    if bad == 'parent inference': args['parent_project_id'] = key(1)
    assert_rejected_unchanged(populated,request(populated,'create_project',**args))


@pytest.mark.parametrize('source,destination',[(1,2),(3,2),(3,0),(4,2),(4,1)])
def test_moves_preserve_complete_forest_task_identity_and_only_change_source(populated,source,destination):
    a = populated
    if source == 4 and destination == 2:
        create(a,identity=key(5),parent=key(2))
        destination = 5  # Child-to-deeper destination.
    before = snapshot(a)
    frozen, result = moved(a,source=key(source),destination=key(destination) if destination else None)
    after = snapshot(a)
    old = next(r for r in before['projects'] if r['project_id'] == key(source))
    expected = dict(old,parent_project_id=key(destination) if destination else None,version=old['version']+1,updated_utc_us=frozen.action_utc_us)
    assert result.result == dict(project_id=key(source),version=expected['version'],parent_project_id=expected['parent_project_id'])
    assert sorted(after['projects'],key=lambda r:r['project_id']) == sorted([expected if r['project_id']==key(source) else r for r in before['projects']],key=lambda r:r['project_id'])
    for table in before.keys()-{'projects','committed_requests','sqlite_sequence'}:
        assert after[table] == before[table]
    assert after['tasks'] == before['tasks']  # Includes nonleaf and child tasks.
    c = a.connect(readonly=True)
    try: assert schema.verify_candidate(c).administrative_history_verified
    finally: c.close()


def test_mixed_direct_tasks_and_child_projects_move_as_one_organization(populated):
    a = populated
    # Seed one additional existing supported creation receipt, not a new service.
    c = a.connect()
    frozen = request(a,'create_task',task_id=key(200),name='Direct',project_id=key(3),expected_project_version=1)
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT INTO tasks(task_id,project_id,parent_task_id,name,version,created_request_id,created_utc_us,updated_utc_us) VALUES(?,?,NULL,?,1,?,?,?)',
                  (key(200),key(3),'Direct',frozen.request_id,NOW+100,NOW+100))
        c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                  (frozen.request_id,frozen.operation,'administrative',frozen.content(),canonical(dict(task_id=key(200),version=1)),frozen.action_utc_us))
        schema.verify_candidate_transaction(c)
        c.execute('COMMIT')
    finally: c.close()
    args = review(a)
    assert {r['task_id'] for r in args['reviewed_tasks']} == {key(101),key(102),key(200)}
    before = snapshot(a)
    moved(a)
    after = snapshot(a)
    assert after['tasks'] == before['tasks']
    assert next(r for r in after['projects'] if r['project_id']==key(4)) == next(r for r in before['projects'] if r['project_id']==key(4))


@pytest.mark.parametrize('bad', ['source missing','source version','source parent','destination missing','destination version',
    'source ancestry version','source ancestry parent','destination ancestry','missing project','added project','project version',
    'project parent','missing task','added task','task version','task parent','task project','unsorted projects','duplicate projects',
    'unsorted tasks','duplicate tasks','self','descendant','root version','boolean version','null member id','extra member field','extra request field'])
def test_stale_malformed_cycle_and_incomplete_movement_refuse(populated,bad):
    a = populated
    args = review(a)
    if bad == 'source missing': args['project_id'] = uid()
    if bad == 'source version': args['expected_version'] = 2
    if bad == 'source parent': args['source_parent_project_id'] = key(2)
    if bad == 'destination missing': args['destination_parent_project_id'] = uid()
    if bad == 'destination version': args['expected_destination_parent_version'] = 2
    if bad == 'source ancestry version': args['reviewed_source_ancestry'][0]['expected_version'] = 2
    if bad == 'source ancestry parent': args['reviewed_source_ancestry'][0]['parent_project_id'] = key(2)
    if bad == 'destination ancestry': args['reviewed_destination_ancestry'] = []
    if bad == 'missing project': args['reviewed_projects'].pop()
    if bad == 'added project': args['reviewed_projects'].append(dict(project_id=key(2),expected_version=1,parent_project_id=None))
    if bad == 'project version': args['reviewed_projects'][1]['expected_version'] = 2
    if bad == 'project parent': args['reviewed_projects'][1]['parent_project_id'] = key(2)
    if bad == 'missing task': args['reviewed_tasks'].pop()
    if bad == 'added task': args['reviewed_tasks'].append(dict(task_id=uid(),expected_version=1,parent_task_id=None,project_id=key(4)))
    if bad == 'task version': args['reviewed_tasks'][0]['expected_version'] = 2
    if bad == 'task parent': args['reviewed_tasks'][1]['parent_task_id'] = None
    if bad == 'task project': args['reviewed_tasks'][0]['project_id'] = key(2)
    if bad == 'unsorted projects': args['reviewed_projects'].reverse()
    if bad == 'duplicate projects': args['reviewed_projects'].append(deepcopy(args['reviewed_projects'][0]))
    if bad == 'unsorted tasks': args['reviewed_tasks'].reverse()
    if bad == 'duplicate tasks': args['reviewed_tasks'].append(deepcopy(args['reviewed_tasks'][0]))
    if bad in ('self','descendant'): args = review(a,destination=key(3 if bad=='self' else 4))
    if bad == 'root version': args = review(a,destination=None);args['expected_destination_parent_version'] = 1
    if bad == 'boolean version': args['reviewed_projects'][0]['expected_version'] = True
    if bad == 'null member id': args['reviewed_projects'][0]['project_id'] = None
    if bad == 'extra member field': args['reviewed_tasks'][0]['extra'] = None
    if bad == 'extra request field': args['destination_customer_id'] = uid()
    assert_rejected_unchanged(a,request(a,'move_project_subtree',**args))


@pytest.mark.parametrize('change',['new child','moved descendant','changed descendant version','new ancestry','new destination'])
def test_actual_state_changes_after_review_are_stale(populated,change):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    if change == 'new child': create(a,parent=key(4))
    if change == 'moved descendant': moved(a,source=key(4),destination=key(2))
    if change == 'changed descendant version':
        # A separate accepted project move increments the descendant's version.
        moved(a,source=key(4),destination=key(1))
        moved(a,source=key(4),destination=key(3))
    if change == 'new ancestry': moved(a,source=key(1),destination=key(2))
    if change == 'new destination': moved(a,source=key(2),destination=key(4))
    assert_rejected_unchanged(a,frozen)


def test_noop_is_fully_reviewed_rolls_back_and_advances_nothing(populated):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a,destination=key(1)))
    before = snapshot(a)
    raw = a.path.read_bytes()
    for _ in range(2): assert a.execute(frozen).status == 'unchanged'
    assert snapshot(a) == before and a.path.read_bytes() == raw
    assert a.inspect(frozen).status == 'absent'
    stale = frozen.args();stale['reviewed_tasks'].pop()
    assert_rejected_unchanged(a,request(a,'move_project_subtree',**stale))
    c = a.connect();trace=[];c.set_trace_callback(trace.append)
    try:
        c.execute('BEGIN IMMEDIATE');trace.clear()
        assert apply_project_operation(c,frozen,a.context) is None
        assert not any(s.upper().startswith(('UPDATE','INSERT','DELETE')) for s in trace)
        c.execute('ROLLBACK')
    finally: c.close()


@pytest.mark.parametrize('operation',['create_project','create_child_project','move_project_subtree'])
def test_exact_retry_precedes_staleness_and_conflicting_uuid_refuses(populated,operation):
    a = populated
    if operation == 'create_project': frozen = create(a)
    elif operation == 'create_child_project': frozen = create(a,parent=key(3))
    else: frozen,_ = moved(a)
    original = a.inspect(frozen)
    moved(a,source=key(3),destination=None)
    before = snapshot(a)
    assert a.execute(frozen) == original
    assert snapshot(a) == before
    assert_rejected_unchanged(a,replace(frozen,action_utc_us=frozen.action_utc_us+1))
    reopened = CandidateAdapter(a.path,a.context.dataset_id)
    assert reopened.execute(frozen) == original


@pytest.mark.parametrize('stage',['after_apply','after_receipt','after_verify','before_commit'])
def test_failure_at_real_boundaries_rolls_back_every_table(populated,stage):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    before = snapshot(a)
    def fault(current,c):
        if current == stage: raise OSError('Injected '+stage)
    a.checkpoint = fault
    result = a.execute(frozen)
    assert result.status == 'rolled_back' and isinstance(result.error,OSError)
    assert snapshot(a) == before and a.inspect(frozen).status == 'absent'
    a.checkpoint = lambda *args:None
    assert a.execute(frozen).status == 'committed'  # Original request remains retryable.


@pytest.mark.parametrize('failure',['update','receipt','partial receipt','final structure','unexpected task','unexpected sequence'])
def test_sql_receipt_and_independent_final_verification_failures(populated,failure):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    before = snapshot(a)
    connect = a.connect
    def opened(readonly=False):
        c = connect(readonly)
        if not readonly and failure in ('update','receipt'):
            def authorize(action,table,column,*rest):
                if (failure=='update' and action==sqlite3.SQLITE_UPDATE and table=='projects' or
                    failure=='receipt' and action==sqlite3.SQLITE_INSERT and table=='committed_requests'):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            c.set_authorizer(authorize)
        return c
    a.connect = opened
    def fault(stage,c):
        if stage != 'after_receipt': return
        if failure == 'partial receipt': c.execute('DELETE FROM committed_requests WHERE request_id=?',(frozen.request_id,))
        if failure == 'final structure': c.execute('UPDATE projects SET version=version+1 WHERE project_id=?',(key(4),))
        if failure == 'unexpected task': c.execute('UPDATE tasks SET name=? WHERE task_id=?',('Tampered',key(101)))
        if failure == 'unexpected sequence': c.execute('UPDATE sqlite_sequence SET seq=seq+1')
    a.checkpoint = fault
    result = a.execute(frozen)
    assert result.status in ('rejected','rolled_back'), result
    assert snapshot(a) == before
    assert a.inspect(frozen).status == 'absent'


def test_history_verifier_is_independent_of_service_result(populated,monkeypatch):
    import project_candidate
    original = project_candidate.apply_project_operation
    def wrong(c,request,context):
        result = original(c,request,context)
        return dict(result,version=result['version']+1)
    monkeypatch.setattr(project_candidate,'apply_project_operation',wrong)
    frozen = request(populated,'move_project_subtree',**review(populated))
    assert_rejected_unchanged(populated,frozen)


def test_lost_acknowledgement_independently_recovers_exact_result(populated):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    def lost(stage,c):
        if stage == 'after_commit': raise OSError('Lost acknowledgement')
    a.checkpoint = lost
    outcome = a.execute(frozen)
    assert outcome.status == 'committed'
    assert outcome == CandidateAdapter(a.path,a.context.dataset_id).inspect(frozen)
    before = snapshot(a)
    a.checkpoint = lambda *args:None
    assert a.execute(frozen) == outcome and snapshot(a) == before


@pytest.mark.parametrize('when',['before','after'])
def test_commit_call_error_never_implies_absence(populated,when):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    before = snapshot(a)
    connect = a.connect
    class CommitFault:
        def __init__(self,c): self.inner=c
        def __getattr__(self,name): return getattr(self.inner,name)
        def execute(self,sql,*args):
            if sql != 'COMMIT': return self.inner.execute(sql,*args)
            if when == 'after': self.inner.execute(sql,*args)
            raise OSError('COMMIT response unavailable '+when)
    a.connect = lambda readonly=False: connect(True) if readonly else CommitFault(connect())
    result = a.execute(frozen)
    if when == 'before':
        assert result.status == 'rolled_back' and snapshot(a) == before
        assert a.inspect(frozen).status == 'absent'
    else:
        assert result.status == 'committed' and a.inspect(frozen) == result
        assert snapshot(a) != before
    a.connect = connect
    assert a.execute(frozen).status == 'committed'
    state = snapshot(a)
    assert a.execute(frozen).status == 'committed' and snapshot(a) == state


@pytest.mark.parametrize('failure',['rollback','close','independent validation'])
def test_uncertain_cleanup_or_evidence_never_claims_known_rejection(populated,failure):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    before = snapshot(a)
    def fault(stage,c):
        if stage == 'after_apply' or stage == failure: raise OSError('Injected '+stage)
    a.checkpoint = fault
    if failure == 'independent validation':
        original = a.connect
        def opened(readonly=False):
            if readonly: raise OSError('Independent evidence unavailable')
            return original()
        a.connect = opened
    try:
        result = a.execute(frozen)
        assert result.status == 'unverified'
        assert result.error is not None
        if failure == 'close':
            assert a.retired is not None
            assert a.execute(frozen).status == 'unverified'
            a.retired.close();a.retired = None  # Explicit test-owned handle cleanup.
    finally:
        if a.retired is not None: a.retired.close();a.retired = None
    a.checkpoint = lambda *args:None
    if failure == 'independent validation': a.connect = original
    assert snapshot(a) == before and a.inspect(frozen).status == 'absent'


CHILD = r'''
import json,sys
from chronicle.records import Request
from project_candidate import CandidateAdapter
path,dataset,raw,phase=sys.argv[1:]
x=json.loads(raw)
r=Request.make(x['request_id'],dataset,x['operation'],x['action_utc_us'],**x['arguments'])
def checkpoint(stage,c):
 if stage==phase:
  print('BARRIER',flush=True)
  sys.stdin.readline()
a=CandidateAdapter(path,dataset,checkpoint)
result=a.execute(r)
print(result.status,flush=True)
'''


def child_env():
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPATH'] = os.pathsep.join((str(Path('src').resolve()),str(Path('tests/rewrite').resolve())))
    return env


@pytest.mark.parametrize('phase',['after_apply','after_receipt','before_commit','after_commit'])
def test_process_interruption_and_restart_reconcile_original_request(populated,phase):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    raw = dict(json.loads(frozen.content()),request_id=frozen.request_id)
    before = snapshot(a)
    proc = subprocess.Popen([sys.executable,'-B','-c',CHILD,str(a.path),a.context.dataset_id,json.dumps(raw),phase],
                            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=child_env())
    lines = Queue()
    reader = Thread(target=lambda:lines.put(proc.stdout.readline()),daemon=True);reader.start()
    try:
        assert lines.get(timeout=15).strip() == 'BARRIER'
    finally:
        if proc.poll() is None: proc.kill()
        stdout,stderr = proc.communicate(timeout=10)
        reader.join(5)
        assert not reader.is_alive()
        (a.path.parent/f'{phase}-child.json').write_text(json.dumps(dict(returncode=proc.returncode,stdout=stdout,stderr=stderr)))
    assert proc.returncode != 0 and stderr == ''
    observed = CandidateAdapter(a.path,a.context.dataset_id).inspect(frozen)
    if phase == 'after_commit':
        assert observed.status == 'committed'
        assert next(r for r in snapshot(a)['projects'] if r['project_id']==key(3))['version'] == 2
    else:
        assert observed.status == 'absent' and snapshot(a) == before
    assert a.execute(frozen).status == 'committed'
    state = snapshot(a)
    assert a.execute(frozen).status == 'committed' and snapshot(a) == state


@pytest.mark.parametrize('damage',['receipt','dependency'])
def test_persisted_tampering_refuses_independently(populated,damage):
    a = populated
    frozen,_ = moved(a)
    c = a.connect()
    try:
        if damage == 'receipt':
            trigger = c.execute("SELECT sql FROM sqlite_schema WHERE name='immutable_committed_requests_update'").fetchone()[0]
            c.execute('DROP TRIGGER immutable_committed_requests_update')
            c.execute('UPDATE committed_requests SET result_bytes=? WHERE request_id=?',(b'{}',frozen.request_id))
            c.execute(trigger)
        else:
            c.execute('PRAGMA foreign_keys=OFF')
            c.execute('DELETE FROM committed_requests WHERE request_id=?',(key(1001),))
            c.execute('PRAGMA foreign_keys=ON')
    finally: c.close()
    before = a.path.read_bytes()
    assert a.inspect(frozen).status == 'unverified'
    assert a.execute(frozen).status == 'unverified'
    assert a.path.read_bytes() == before


@pytest.mark.parametrize('case',['child parent','child ancestor','source','source ancestor','destination','destination ancestor','noop'])
def test_archived_context_refusal_is_structural_service_evidence(populated,case):
    """Lifecycle replay is unsupported: only the structural service is exercised."""
    a = populated
    projects = {r['project_id']:r for r in snapshot(a)['projects']}
    if case.startswith('child'):
        frozen = request(a,'create_child_project',project_id=uid(),name='Child',parent_project_id=key(4),
                         expected_parent_version=1,reviewed_parent_ancestry=ancestry(projects,key(4)))
        archived = key(4 if case=='child parent' else 1)
    else:
        destination = key(1) if case=='noop' else key(4) if case=='destination ancestor' else key(2)
        source = key(2) if case=='destination ancestor' else key(3)
        frozen = request(a,'move_project_subtree',**review(a,source,destination))
        archived = key({'source':3,'source ancestor':1,'destination':2,'destination ancestor':1,'noop':1}[case])
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute('UPDATE projects SET is_archived=1,archived_at_utc_us=? WHERE project_id=?',(NOW,archived))
        before = facts(c)
        with pytest.raises(ValueError,match='archived'):
            apply_project_operation(c,frozen,a.context)
        assert facts(c) == before
        with pytest.raises(ValueError): schema.verify_candidate_transaction(c)
        c.execute('ROLLBACK')
    finally: c.close()


def test_archived_tasks_remain_in_complete_review_without_claiming_lifecycle_admission(populated):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute('UPDATE tasks SET is_archived=1,archived_at_utc_us=? WHERE task_id=?',(NOW,key(102)))
        tasks = facts(c)['tasks']
        result = apply_project_operation(c,frozen,a.context)
        assert result['version'] == 2 and facts(c)['tasks'] == tasks
        with pytest.raises(ValueError): schema.verify_candidate_transaction(c)
        c.execute('ROLLBACK')
    finally: c.close()


def test_sql_only_active_and_historical_work_preservation_and_archive_guards(populated):
    """No complete protected replay/admission: these in-flight facts are rolled back."""
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        entry = sql_work(c,key(102));sql_active(c,key(102),entry)
        # Fill deferred identity references with a protected receipt for structural
        # FK checking only; Package A deliberately cannot replay this work history.
        owner = c.execute('SELECT created_request_id FROM work_entries WHERE entry_id=?',(entry,)).fetchone()[0]
        c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                  (owner,'start_timer','protected',b'{}',b'{}',NOW))
        before = facts(c)
        result = apply_project_operation(c,frozen,a.context)
        assert result['version'] == 2
        for table in before.keys()-{'projects'}: assert facts(c)[table] == before[table]
        with pytest.raises(ValueError): schema.verify_candidate_transaction(c)
        with pytest.raises(sqlite3.IntegrityError,match='hide active timer'):
            c.execute('UPDATE projects SET is_archived=1,archived_at_utc_us=? WHERE project_id=?',(NOW,key(2)))
        blocked = sql_project(c,archived=1)
        with pytest.raises(sqlite3.IntegrityError,match='active'):
            c.execute('UPDATE projects SET parent_project_id=? WHERE project_id=?',(blocked,key(3)))
        assert c.execute('SELECT entry_id FROM active_timer').fetchone()[0] == entry
        assert facts(c)['work_entries'] == before['work_entries']
        c.execute('ROLLBACK')
    finally: c.close()
    assert a.inspect(frozen).status == 'absent'


def test_supported_adapter_refuses_nonempty_protected_scope(populated):
    a = populated
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        entry = sql_work(c,key(102));sql_active(c,key(102),entry)
        owner = c.execute('SELECT created_request_id FROM work_entries').fetchone()[0]
        c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                  (owner,'start_timer','protected',b'{}',b'{}',NOW))
        c.execute('COMMIT')
    finally: c.close()
    frozen = request(a,'move_project_subtree',**review(a))
    before = snapshot(a)
    assert a.execute(frozen).status == 'unverified'
    assert snapshot(a) == before


@pytest.mark.parametrize('change',['added','removed','version','parent','membership'])
def test_real_task_changes_invalidate_review_before_any_service_write(populated,change):
    """Parent/membership SQL observations do not claim Package C replay support."""
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        if change == 'added':
            identity = sql_task(c,project=key(3))
            owner = c.execute('SELECT created_request_id FROM tasks WHERE task_id=?',(identity,)).fetchone()[0]
            seed = Request.make(owner,a.context.dataset_id,'create_task',NOW,task_id=identity,name='Task',project_id=key(3),expected_project_version=1,reviewed_destination_project_ancestry=ancestry({p['project_id']:p for p in facts(c)['projects']},key(3)))
            c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                      (owner,seed.operation,'administrative',seed.content(),canonical(dict(task_id=identity,version=1)),NOW))
        if change == 'removed':
            c.execute('DELETE FROM tasks WHERE task_id=?',(key(102),))
            c.execute('DELETE FROM committed_requests WHERE request_id=?',(key(1006),))
        if change == 'version':
            seed = request(a,'rename_task',task_id=key(102),expected_version=1,name='Renamed')
            c.execute('UPDATE tasks SET name=?,version=2,updated_utc_us=? WHERE task_id=?',('Renamed',seed.action_utc_us,key(102)))
            c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                      (seed.request_id,seed.operation,'administrative',seed.content(),canonical(dict(task_id=key(102),version=2)),seed.action_utc_us))
        if change in ('parent','membership'):
            c.execute('UPDATE tasks SET parent_task_id=NULL WHERE task_id=?',(key(102),))
        if change == 'membership':
            c.execute('UPDATE tasks SET project_id=? WHERE task_id IN (?,?)',(key(2),key(101),key(102)))
            c.execute('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(key(101),key(102)))
        schema.verify_structure(c)
        if change in ('added','removed','version'):
            schema.verify_candidate_transaction(c)
        before = facts(c)
        with pytest.raises(ValueError,match='Reviewed coverage'):
            apply_project_operation(c,frozen,a.context)
        assert facts(c) == before
        c.execute('ROLLBACK')
    finally: c.close()


def test_retained_direct_parent_work_is_reviewed_and_unchanged_sql_scope(populated):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        child = next(t for t in schema._rows(c,'tasks') if t['task_id']==key(102))
        c.execute('DELETE FROM tasks WHERE task_id=?',(key(102),))
        entry = sql_work(c,key(101))  # Recorded while the task was a leaf.
        owner = c.execute('SELECT created_request_id FROM work_entries WHERE entry_id=?',(entry,)).fetchone()[0]
        revision_owner = uid()
        for identity,operation in ((owner,'start_timer'),(revision_owner,'stop_timer')):
            c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                      (identity,operation,'protected',b'{}',b'{}',NOW))
        c.execute("INSERT INTO work_revisions(entry_id,revision,kind,start_utc_us,stop_utc_us,is_deleted,comment,audit_utc_us,request_id) VALUES(?,1,'timed',?,?,0,'',?,?)",
                  (entry,NOW,NOW+1,NOW+1,revision_owner))
        c.execute('UPDATE work_entries SET current_revision=1 WHERE entry_id=?',(entry,))
        columns=tuple(child)
        c.execute('INSERT INTO tasks('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(child.values()))
        before = facts(c)
        assert {r['task_id'] for r in frozen.args()['reviewed_tasks']} == {key(101),key(102)}
        assert apply_project_operation(c,frozen,a.context)['version'] == 2
        after = facts(c)
        for table in before.keys()-{'projects'}: assert after[table] == before[table]
        with pytest.raises(ValueError): schema.verify_candidate_transaction(c)
        c.execute('ROLLBACK')
    finally: c.close()


def test_existing_commit_sequences_remain_authoritative_after_retirement_gap(populated):
    a = populated
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM tasks WHERE task_id=?',(key(102),))
        c.execute('DELETE FROM committed_requests WHERE request_id=?',(key(1006),))
        schema.verify_candidate_transaction(c)
        c.execute('COMMIT')
    finally: c.close()
    before = snapshot(a)
    frozen = create(a)
    after = snapshot(a)
    assert all(row in after['committed_requests'] for row in before['committed_requests'])
    assert next(r['commit_seq'] for r in after['committed_requests'] if r['request_id']==frozen.request_id) == 7


def test_candidate_scope_gate_is_read_only_and_requires_caller_transaction(populated):
    a = populated
    c = a.connect();trace=[];c.set_trace_callback(trace.append)
    try:
        with pytest.raises(ValueError,match='owned transaction'): schema.verify_candidate_transaction(c)
        c.execute('BEGIN IMMEDIATE');trace.clear();before=facts(c)
        result = schema.verify_candidate_transaction(c)
        assert result.administrative_history_verified and not result.ordinary_startup_permitted
        assert c.in_transaction and facts(c) == before
        assert not any(s.upper().startswith(('BEGIN','COMMIT','ROLLBACK','UPDATE','INSERT','DELETE')) for s in trace)
        c.execute('ROLLBACK')
    finally: c.close()


def test_caller_owns_transaction_connection_and_receipt(populated):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    before = snapshot(a)
    c = a.connect();trace=[];c.set_trace_callback(trace.append)
    try:
        with pytest.raises(ValueError,match='owned transaction'): apply_project_operation(c,frozen,a.context)
        c.execute('BEGIN IMMEDIATE');trace.clear()
        result = apply_project_operation(c,frozen,a.context)
        assert result['version'] == 2 and c.in_transaction
        assert not any(s.upper().startswith(('BEGIN','COMMIT','ROLLBACK','SAVEPOINT','RELEASE')) for s in trace)
        assert c.execute('SELECT count(*) FROM committed_requests WHERE request_id=?',(frozen.request_id,)).fetchone()[0] == 0
        c.execute('ROLLBACK')
        assert c.execute('SELECT 1').fetchone()[0] == 1
    finally: c.close()
    assert snapshot(a) == before


@pytest.mark.parametrize('bad',['context','request dataset','context dataset','operation'])
def test_explicit_candidate_identity_and_supported_operation_required(populated,bad):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a))
    context = a.context
    if bad == 'context': context = None
    if bad == 'context dataset': context = CandidateProjectContext(uid())
    if bad == 'request dataset': frozen = replace(frozen,dataset_id=uid())
    if bad == 'operation': frozen = replace(frozen,operation='move_task_branch')
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE');before=facts(c)
        with pytest.raises(ValueError): apply_project_operation(c,frozen,context)
        assert facts(c) == before
        c.execute('ROLLBACK')
    finally: c.close()


def test_candidate_operation_refuses_schema3_and_runtime_service_remains_unchanged(store,service):
    before = facts(store.connection)
    frozen = Request.make(uid(),store.dataset_id,'create_project',NOW,project_id=uid(),name='New')
    c = store.connection
    c.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(ValueError,match='schema-4'): apply_project_operation(c,frozen,CandidateProjectContext(store.dataset_id))
    finally: c.execute('ROLLBACK')
    assert facts(c) == before
    for op in ('create_child_project','move_project_subtree'):
        result = service.execute(Request.make(uid(),store.dataset_id,op,NOW))
        assert result.status == 'rejected'
    store._recover_connection()  # Ordinary rejection retires its old connection.
    assert facts(store.connection) == before and runtime.SCHEMA_VERSION == 3


def test_ordinary_worker_refuses_candidate_project_operations(tmp_path):
    from chronicle.worker import DatabaseWorker, Message
    from test_worker import receive
    directory = tmp_path/'ordinary'
    worker = DatabaseWorker(directory,create=True,timezone='UTC')
    worker.start()
    try:
        ready = receive(worker,'ready')
        for token,op in enumerate(('create_child_project','move_project_subtree')):
            frozen = Request.make(uid(),ready['dataset_id'],op,NOW)
            worker.requests.put(Message('mutate',token,frozen))
            assert receive(worker,'mutate').status == 'rejected'
    finally:
        worker.requests.put(Message('shutdown'))
        worker.join(10)
        assert not worker.is_alive()
    c = sqlite3.connect(directory/runtime.DATABASE)
    try:
        assert c.execute('PRAGMA user_version').fetchone()[0] == 3
        assert not list(c.execute('SELECT * FROM projects'))
        assert not list(c.execute('SELECT * FROM committed_requests'))
    finally: c.close()


def test_project_and_task_namespaces_are_independent(populated):
    frozen = create(populated,identity=key(101))
    state = snapshot(populated)
    assert frozen.args()['project_id'] == key(101)
    assert key(101) in {r['project_id'] for r in state['projects']}
    assert key(101) in {r['task_id'] for r in state['tasks']}


def test_corrupt_complete_forest_refuses_even_unrelated_noop(populated):
    a = populated
    frozen = request(a,'move_project_subtree',**review(a,source=key(2),destination=None))
    c = a.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        trigger = c.execute("SELECT sql FROM sqlite_schema WHERE name='projects_forest_update'").fetchone()[0]
        c.execute('DROP TRIGGER projects_forest_update')
        c.execute('UPDATE projects SET parent_project_id=? WHERE project_id=?',(key(4),key(3)))
        c.execute(trigger)
        before = facts(c)
        with pytest.raises(ValueError,match='cycle'): apply_project_operation(c,frozen,a.context)
        assert facts(c) == before
        c.execute('ROLLBACK')
    finally: c.close()


DEEP_CHILD = r'''
import sys
from pathlib import Path
from chronicle import schema_profiles as schema
from chronicle.records import Request
from project_candidate import CandidateAdapter
from test_project_movement import create,moved,snapshot
import sqlite3
path=Path(sys.argv[1]);dataset=sys.argv[2]
c=sqlite3.connect(path,isolation_level=None)
schema.create_candidate(c,dataset_id=dataset,timezone='UTC');c.close()
a=CandidateAdapter(path,dataset)
sys.setrecursionlimit(80)
parent=None
for i in range(100):
 r=create(a,parent=parent)
 parent=r.args()['project_id']
root=next(r['project_id'] for r in snapshot(a)['projects'] if r['parent_project_id'] is None)
other=create(a).args()['project_id']
r,result=moved(a,source=root,destination=other)
assert result.status=='committed'
r,result=moved(a,source=root,destination=None)
assert result.status=='committed'
print('DEEP 100 > recursion limit 80; complete creation/move replay passed')
'''


def test_deep_creation_and_complete_movement_do_not_use_python_recursion(tmp_path):
    result = subprocess.run([sys.executable,'-B','-c',DEEP_CHILD,str(tmp_path/'deep.sqlite3'),uid()],
                            env=child_env(),capture_output=True,text=True,timeout=120)
    (tmp_path/'deep-control.json').write_text(json.dumps(dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)))
    assert result.returncode == 0, result.stderr
    assert 'DEEP 100' in result.stdout
