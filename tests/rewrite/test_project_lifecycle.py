"""C1 lifecycle through real candidate transactions; protected fixtures are scoped."""
from copy import deepcopy
from dataclasses import replace
import json
import sqlite3

import pytest

from chronicle import schema_profiles as schema
from chronicle.administration import UnsupportedCandidateOperation, verify_schema4_history
from chronicle.hierarchy import (ProjectForest, candidate_task_observations, candidate_project_ancestry,
    candidate_project_destination, candidate_task_destination, candidate_active_in_project_subtree)
from chronicle.project_lifecycle import apply_lifecycle_operation, transition
from chronicle.project_services import CandidateProjectContext, apply_project_operation
from chronicle.records import canonical
from conftest import NOW, uid
from project_candidate import CandidateAdapter, facts
from test_project_movement import (adapter, populated, snapshot, create, review, request,
                                   assert_rejected_unchanged, moved)
from test_schema4_history import key
from test_schema4 import sql_work, sql_active


def lifecycle(a,entity,identity,operation='archive',version=None,now=NOW+200):
    if version is None:
        version=next(r['version'] for r in snapshot(a)[entity+'s'] if r[entity+'_id']==identity)
    return replace(request(a,operation+'_'+entity,**{entity+'_id':identity,'expected_version':version}),action_utc_us=now)


def applied(a,entity,identity,operation='archive'):
    frozen=lifecycle(a,entity,identity,operation)
    result=a.execute(frozen)
    assert result.status=='committed',result
    return frozen,result


def observations(a):
    state=snapshot(a)
    return ProjectForest(state['projects']),candidate_task_observations(state['tasks'],state['projects'])


@pytest.mark.parametrize('entity,identity',[('project',1),('project',3),('project',4),('task',101),('task',102)])
def test_selected_only_exact_lifecycle_receipt_retry_noop_and_unarchive(populated,entity,identity):
    a=populated;identity=key(identity);before=snapshot(a)
    frozen,result=applied(a,entity,identity)
    after=snapshot(a);field=entity+'_id';table=entity+'s'
    selected=next(r for r in before[table] if r[field]==identity)
    expected=dict(selected,is_archived=1,archived_at_utc_us=frozen.action_utc_us,
                  version=selected['version']+1,updated_utc_us=frozen.action_utc_us)
    assert sorted(after[table],key=repr)==sorted([expected if r[field]==identity else r for r in before[table]],key=repr)
    assert result.result=={field:identity,'version':2}
    for name in before.keys()-{table,'committed_requests','sqlite_sequence'}:assert after[name]==before[name]
    receipt=next(r for r in after['committed_requests'] if r['request_id']==frozen.request_id)
    assert receipt['request_bytes']==frozen.content() and receipt['result_bytes']==canonical(result.result)
    assert receipt['receipt_class']=='administrative'
    assert a.execute(lifecycle(a,entity,identity)).status=='unchanged'
    assert snapshot(a)==after
    assert_rejected_unchanged(a,replace(frozen,request_id=uid()))  # Stale no-op refuses.
    un,un_result=applied(a,entity,identity,'unarchive')
    restored=snapshot(a)
    row=next(r for r in restored[table] if r[field]==identity)
    assert row==dict(selected,is_archived=0,archived_at_utc_us=None,version=3,updated_utc_us=un.action_utc_us)
    assert un_result.result=={field:identity,'version':3}
    assert a.execute(lifecycle(a,entity,identity,'unarchive')).status=='unchanged'
    assert snapshot(a)==restored
    assert a.execute(frozen)==result and snapshot(a)==restored
    assert CandidateAdapter(a.path,a.context.dataset_id).inspect(frozen)==result
    assert_rejected_unchanged(a,replace(frozen,action_utc_us=frozen.action_utc_us+1))


def test_deep_archive_inheritance_preserves_independent_project_and_task_flags(populated):
    a=populated;parent=key(4)
    for i in range(5,10):
        create(a,identity=key(i),parent=parent);parent=key(i)
    applied(a,'project',key(7));applied(a,'task',key(102))
    flags=snapshot(a)
    applied(a,'project',key(1))
    forest,tasks=observations(a)
    assert all(forest.effective_archived[key(i)] for i in (1,3,4,5,6,7,8,9))
    assert all(v['effective_archived'] for v in tasks.values())
    assert all(v['project_effective_archived'] for v in tasks.values())
    applied(a,'project',key(1),'unarchive')
    forest,tasks=observations(a)
    assert not forest.effective_archived[key(4)] and forest.effective_archived[key(9)]
    assert not tasks[key(101)]['effective_archived'] and tasks[key(102)]['effective_archived']
    after=snapshot(a)
    for table,field,identity in (('projects','project_id',key(7)),('tasks','task_id',key(102))):
        assert next(r for r in flags[table] if r[field]==identity)==next(r for r in after[table] if r[field]==identity)
    # Explicitly unarchive a child under an archived ancestor; inheritance remains.
    applied(a,'project',key(4));applied(a,'project',key(7),'unarchive')
    forest,_=observations(a)
    assert forest.effective_archived[key(7)]
    assert not next(r for r in snapshot(a)['projects'] if r['project_id']==key(7))['is_archived']
    applied(a,'task',key(102),'unarchive')
    assert observations(a)[1][key(102)]['effective_archived']


def test_task_ancestor_archive_and_reusable_destination_observations(populated):
    a=populated;state=snapshot(a)
    assert candidate_project_ancestry(state['projects'],key(4))==(key(1),key(3),key(4))
    assert candidate_project_destination(state['projects'],None)
    assert candidate_task_destination(state['tasks'],state['projects'],key(101))
    assert not candidate_task_destination(state['tasks'],state['projects'],key(102),dict(task_id=key(102)))
    applied(a,'task',key(101));state=snapshot(a)
    value=candidate_task_observations(state['tasks'],state['projects'])[key(102)]
    assert value==dict(depth=2,is_leaf=True,explicit_archived=False,ancestor_task_archived=True,
                      project_effective_archived=False,effective_archived=True,eligible_for_new_work=False)
    assert not candidate_task_destination(state['tasks'],state['projects'],key(101))
    applied(a,'project',key(1));state=snapshot(a)
    assert not candidate_project_destination(state['projects'],key(4))
    for helper,args in ((candidate_project_ancestry,(state['projects'],uid())),
                        (candidate_project_destination,(state['projects'],uid())),
                        (candidate_task_destination,(state['tasks'],state['projects'],uid()))):
        with pytest.raises(ValueError):helper(*args)


@pytest.mark.parametrize('entity',['project','task'])
@pytest.mark.parametrize('bad',['missing','version','uuid','bool','extra','missing field','wrong dataset','unknown operation'])
def test_invalid_lifecycle_has_no_write(populated,entity,bad):
    a=populated;frozen=lifecycle(a,entity,key(3 if entity=='project' else 101));args=frozen.args()
    if bad=='missing':args[entity+'_id']=uid()
    if bad=='version':args['expected_version']=2
    if bad=='uuid':args[entity+'_id']='invalid'
    if bad=='bool':args['expected_version']=True
    if bad=='extra':args['archived_at_utc_us']=NOW
    if bad=='missing field':del args['expected_version']
    frozen=replace(frozen,arguments=canonical(args))
    if bad=='wrong dataset':frozen=replace(frozen,dataset_id=uid())
    if bad=='unknown operation':frozen=replace(frozen,operation='archive_everything')
    assert_rejected_unchanged(a,frozen)


@pytest.mark.parametrize('entity',['project','task'])
@pytest.mark.parametrize('operation',['archive','unarchive'])
def test_noop_validates_full_structure_and_issues_no_write(populated,entity,operation):
    a=populated;identity=key(3 if entity=='project' else 101)
    if operation=='archive':applied(a,entity,identity)
    frozen=lifecycle(a,entity,identity,operation)
    c=a.connect();trace=[];c.set_trace_callback(trace.append)
    try:
        with pytest.raises(ValueError,match='owned transaction'):apply_lifecycle_operation(c,frozen,a.context)
        c.execute('BEGIN IMMEDIATE');trace.clear();before=facts(c)
        assert apply_lifecycle_operation(c,frozen,a.context) is None
        assert c.in_transaction and facts(c)==before
        assert not any(s.upper().startswith(('UPDATE','INSERT','DELETE','COMMIT','ROLLBACK','BEGIN')) for s in trace)
        c.execute('ROLLBACK')
    finally:c.close()
    before=snapshot(a);raw=a.path.read_bytes()
    assert a.execute(frozen).status=='unchanged'
    assert snapshot(a)==before and a.path.read_bytes()==raw and a.inspect(frozen).status=='absent'


@pytest.mark.parametrize('target',[('project',4),('project',3),('project',1),('task',101),('task',102)])
def test_active_containment_blocks_complete_hierarchy_with_no_timer_mutation(populated,target):
    """Real structural SQL/service evidence; protected replay remains unsupported."""
    a=populated;entity,identity=target
    if target==('project',1):
        parent=None
        for i in range(5,10):
            create(a,identity=key(i),parent=parent);parent=key(i)
        moved(a,source=key(1),destination=parent)
    frozen=lifecycle(a,entity,key(identity));unrelated=lifecycle(a,'project',key(2));c=a.connect()
    try:
        c.execute('BEGIN IMMEDIATE');entry=sql_work(c,key(102));sql_active(c,key(102),entry)
        owner=c.execute('SELECT created_request_id FROM work_entries').fetchone()[0]
        c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                  (owner,'start_timer','protected',b'{}',b'{}',NOW))
        state=facts(c)
        assert candidate_active_in_project_subtree(state['tasks'],state['projects'],state['active_timer'][0],key(1))
        assert not candidate_active_in_project_subtree(state['tasks'],state['projects'],state['active_timer'][0],key(2))
        with pytest.raises(ValueError,match='running timer'):apply_lifecycle_operation(c,frozen,a.context)
        assert facts(c)==state
        assert apply_lifecycle_operation(c,unrelated,a.context)==dict(project_id=key(2),version=2)
        for table in state.keys()-{'projects'}:assert facts(c)[table]==state[table]
        with pytest.raises(ValueError):schema.verify_candidate_transaction(c)
        c.execute('ROLLBACK')
    finally:c.close()


def test_deep_active_containment_and_independent_task_depth():
    import sys
    from test_project_forest import project
    ids=[uid() for _ in range(sys.getrecursionlimit()+50)]
    projects=[project(k,ids[i-1] if i else None) for i,k in enumerate(ids)]
    tasks=[dict(task_id=key(i),parent_task_id=key(i-1) if i>101 else None,project_id=ids[-1],
                is_archived=0,version=1) for i in (101,102,103)]
    active=dict(task_id=key(103))
    assert candidate_active_in_project_subtree(tasks,projects,active,ids[0])
    with pytest.raises(ValueError,match='running timer'):
        transition('archive_project',dict(project_id=ids[0],expected_version=1),NOW,tasks,
                   [dict(p,version=1) for p in projects],active)
    assert not candidate_task_destination(tasks,projects,key(103))
    assert candidate_task_observations(tasks,projects)[key(103)]['depth']==3


@pytest.mark.parametrize('entity',['project','task'])
@pytest.mark.parametrize('fault',['sql','receipt','after_apply','after_receipt','final'])
def test_real_lifecycle_transaction_failures_roll_back(populated,entity,fault):
    a=populated;frozen=lifecycle(a,entity,key(3 if entity=='project' else 101));before=snapshot(a)
    connect=a.connect
    def opened(readonly=False):
        c=connect(readonly)
        if not readonly and fault in ('sql','receipt'):
            def authorize(action,table,*rest):
                if fault=='sql' and action==sqlite3.SQLITE_UPDATE and table==entity+'s':return sqlite3.SQLITE_DENY
                if fault=='receipt' and action==sqlite3.SQLITE_INSERT and table=='committed_requests':return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            c.set_authorizer(authorize)
        return c
    a.connect=opened
    def checkpoint(stage,c):
        if stage==fault:raise OSError('Injected '+stage)
        if stage=='after_receipt' and fault=='final':c.execute('UPDATE tasks SET name=? WHERE task_id=?',('Tampered',key(102)))
    a.checkpoint=checkpoint
    result=a.execute(frozen)
    assert result.status in ('rejected','rolled_back'),result
    assert snapshot(a)==before and a.inspect(frozen).status=='absent'


@pytest.mark.parametrize('entity',['project','task'])
def test_lost_lifecycle_ack_reconciles_original_request(populated,entity):
    a=populated;frozen=lifecycle(a,entity,key(3 if entity=='project' else 101))
    def checkpoint(stage,c):
        if stage=='after_commit':raise OSError('Lost acknowledgement')
    a.checkpoint=checkpoint;result=a.execute(frozen)
    assert result.status=='committed' and a.inspect(frozen)==result
    before=snapshot(a);a.checkpoint=lambda *args:None
    assert a.execute(frozen)==result and snapshot(a)==before


@pytest.mark.parametrize('damage',['request','result','version','timestamp','descendant flag','missing lifecycle','missing creation','noop','operation','fields','class'])
def test_independent_lifecycle_reconstruction_rejects_tampering(populated,damage):
    a=populated;frozen,_=applied(a,'project',key(3));state=deepcopy(snapshot(a));receipts=state['committed_requests']
    receipt=next(r for r in receipts if r['request_id']==frozen.request_id)
    if damage=='request':receipt['request_bytes']+=b' '
    if damage=='result':receipt['result_bytes']=canonical(dict(project_id=key(3),version=3))
    if damage=='version':next(r for r in state['projects'] if r['project_id']==key(3))['version']=3
    if damage=='timestamp':next(r for r in state['projects'] if r['project_id']==key(3))['archived_at_utc_us']+=1
    if damage=='descendant flag':next(r for r in state['projects'] if r['project_id']==key(4)).update(is_archived=1,archived_at_utc_us=NOW)
    if damage=='missing lifecycle':receipts.remove(receipt)
    if damage=='missing creation':receipts.remove(next(r for r in receipts if r['request_id']==key(1001)))
    if damage=='noop':
        receipt['operation']='unarchive_project'
        content=json.loads(receipt['request_bytes']);content['operation']=receipt['operation'];receipt['request_bytes']=canonical(content)
    if damage=='operation':receipt['operation']='archive_task'
    if damage=='fields':
        content=json.loads(receipt['request_bytes']);content['arguments']['extra']=None;receipt['request_bytes']=canonical(content)
    if damage=='class':receipt['receipt_class']='protected'
    with pytest.raises(ValueError):verify_schema4_history(state['projects'],state['tasks'],receipts,a.context.dataset_id)


def test_replay_does_not_call_authoritative_service_transition(populated,monkeypatch):
    import chronicle.project_lifecycle as module
    applied(populated,'project',key(3))
    def forbidden(*args):pytest.fail('Independent replay called service transition')
    monkeypatch.setattr(module,'transition',forbidden)
    c=populated.connect(readonly=True)
    try:assert schema.verify_candidate(c).administrative_history_verified
    finally:c.close()


def test_history_enforces_inherited_archive_after_lifecycle(populated):
    a=populated;applied(a,'project',key(1));before=snapshot(a)
    child_args=dict(project_id=uid(),name='Blocked',parent_project_id=key(4),expected_parent_version=1,
        reviewed_parent_ancestry=[dict(project_id=r['project_id'],expected_version=r['version'],parent_project_id=r['parent_project_id'])
            for r in sorted(before['projects'],key=lambda r:[key(1),key(3),key(4),key(2)].index(r['project_id'])) if r['project_id']!=key(2)])
    assert_rejected_unchanged(a,request(a,'create_child_project',**child_args))
    state=deepcopy(before);bad=request(a,'create_child_project',**child_args)
    state['committed_requests'].append(dict(commit_seq=8,request_id=bad.request_id,operation=bad.operation,receipt_class='administrative',request_bytes=bad.content(),
        result_bytes=canonical(dict(project_id=child_args['project_id'],version=1)),action_utc_us=bad.action_utc_us))
    with pytest.raises(ValueError,match='archived'):verify_schema4_history(state['projects'],state['tasks'],state['committed_requests'],a.context.dataset_id)


def test_candidate_lifecycle_requires_context_and_refuses_schema3(populated,store):
    a=populated;frozen=lifecycle(a,'project',key(3));c=a.connect()
    try:
        c.execute('BEGIN IMMEDIATE');before=facts(c)
        with pytest.raises(ValueError):apply_lifecycle_operation(c,frozen,None)
        with pytest.raises(ValueError):apply_lifecycle_operation(c,replace(frozen,dataset_id=uid()),a.context)
        assert facts(c)==before;c.execute('ROLLBACK')
    finally:c.close()
    c=store.connection;c.execute('BEGIN IMMEDIATE');before=facts(c)
    try:
        with pytest.raises(ValueError,match='schema-4'):apply_lifecycle_operation(c,frozen,CandidateProjectContext(store.dataset_id))
        assert facts(c)==before
    finally:c.execute('ROLLBACK')


@pytest.mark.parametrize('damage',['receipt','timestamp','missing lifecycle'])
def test_persisted_lifecycle_tampering_refuses_independent_readback(populated,damage):
    a=populated;frozen,_=applied(a,'project',key(3));c=a.connect()
    try:
        if damage=='timestamp':
            c.execute('UPDATE projects SET archived_at_utc_us=archived_at_utc_us+1 WHERE project_id=?',(key(3),))
        elif damage=='missing lifecycle':
            c.execute('DELETE FROM committed_requests WHERE request_id=?',(frozen.request_id,))
        else:
            trigger=c.execute("SELECT sql FROM sqlite_schema WHERE name='immutable_committed_requests_update'").fetchone()[0]
            c.execute('DROP TRIGGER immutable_committed_requests_update')
            c.execute('UPDATE committed_requests SET result_bytes=? WHERE request_id=?',(b'{}',frozen.request_id))
            c.execute(trigger)
    finally:c.close()
    before=a.path.read_bytes()
    assert a.inspect(frozen).status=='unverified' and a.execute(frozen).status=='unverified'
    assert a.path.read_bytes()==before


@pytest.mark.parametrize('entity',['project','task'])
@pytest.mark.parametrize('phase',['before_commit','after_commit'])
def test_lifecycle_process_death_reconciles_same_request(populated,entity,phase):
    import subprocess,sys
    from test_project_movement import child_env
    a=populated;frozen=lifecycle(a,entity,key(3 if entity=='project' else 101));before=snapshot(a)
    code=r'''
import json,os,sys
from chronicle.records import Request
from project_candidate import CandidateAdapter
path,dataset,raw,phase=sys.argv[1:]
x=json.loads(raw)
r=Request.make(x['request_id'],dataset,x['operation'],x['action_utc_us'],**x['arguments'])
def checkpoint(stage,c):
 if stage==phase:os._exit(37)
CandidateAdapter(path,dataset,checkpoint).execute(r)
raise AssertionError('Interruption checkpoint not reached')
'''
    content=dict(json.loads(frozen.content()),request_id=frozen.request_id)
    result=subprocess.run([sys.executable,'-B','-c',code,str(a.path),a.context.dataset_id,json.dumps(content),phase],
                          env=child_env(),capture_output=True,text=True,timeout=20)
    (a.path.parent/f'{entity}-{phase}-child.json').write_text(json.dumps(dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)))
    assert result.returncode==37 and not result.stderr
    observed=a.inspect(frozen)
    assert observed.status==('committed' if phase=='after_commit' else 'absent')
    if phase=='before_commit':assert snapshot(a)==before
    assert a.execute(frozen).status=='committed'
    committed=snapshot(a)
    assert a.execute(frozen).status=='committed' and snapshot(a)==committed


def test_sql_only_closed_work_frozen_bytes_and_confirmation_preservation(populated):
    """Specific immutable-row evidence, deliberately not full protected admission."""
    import hashlib
    a=populated;frozen=lifecycle(a,'project',key(3));c=a.connect()
    try:
        c.execute('BEGIN IMMEDIATE');entry=sql_work(c,key(102))
        owner=c.execute('SELECT created_request_id FROM work_entries').fetchone()[0]
        revision_owner,export_owner,confirmation_owner=uid(),uid(),uid()
        for identity,operation in ((owner,'start_timer'),(revision_owner,'stop_timer'),
                                   (export_owner,'register_timesheet_export'),(confirmation_owner,'confirm_polr_absolute')):
            c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                      (identity,operation,'protected',b'{}',b'{}',NOW))
        c.execute("INSERT INTO work_revisions(entry_id,revision,kind,start_utc_us,stop_utc_us,is_deleted,comment,audit_utc_us,request_id) VALUES(?,1,'timed',?,?,0,'retained',?,?)",
                  (entry,NOW,NOW+1,NOW+1,revision_owner))
        c.execute('UPDATE work_entries SET current_revision=1 WHERE entry_id=?',(entry,))
        blob=b'Frozen original project and task labels\n'
        c.execute('INSERT INTO timesheet_exports(export_id,created_request_id,registered_utc_us,cutoff_utc_us,start_date,end_date,timezone,week_start,scope_kind,selected_task_ids_json,preferred_destination,report_utf8,report_sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (uid(),export_owner,NOW,NOW,'2026-10-19','2026-10-19','UTC',6,'all','[]',None,blob,hashlib.sha256(blob).hexdigest()))
        c.execute("INSERT INTO polr_confirmation_batches(batch_id,created_request_id,audit_utc_us,source_export_id,mode) VALUES(?,?,?,NULL,'manual')",(uid(),confirmation_owner,NOW))
        before=facts(c)
        assert apply_lifecycle_operation(c,frozen,a.context)==dict(project_id=key(3),version=2)
        after=facts(c)
        for table in before.keys()-{'projects'}:assert after[table]==before[table]
        assert after['timesheet_exports'][0]['report_utf8']==blob
        with pytest.raises(ValueError):schema.verify_candidate_transaction(c)
        c.execute('ROLLBACK')
    finally:c.close()
