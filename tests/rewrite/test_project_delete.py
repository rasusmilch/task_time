"""Nested unused-only Delete: real survivors, finite retirement and no retry."""
from copy import deepcopy
from dataclasses import replace
import json,sqlite3,subprocess,sys
import pytest
from schema4_cases import *
from test_project_movement import review,child_env
from project_candidate import CandidateAdapter


@pytest.mark.parametrize('scope',['root','child','deep','mixed','archived','task'])
def test_complete_unused_scope_and_exact_survivors(adapter,scope):
    a=adapter;p=project(a);child=project(a,p);outside=task(a,p)
    entity='project';identity=p
    if scope=='child':identity=child
    if scope in ('deep','mixed','archived'):
        cursor=child
        for _ in range(5):cursor=project(a,cursor)
        identity=child
    if scope in ('mixed','archived'):
        root=task(a,child);task(a,child,root);task(a,cursor)
    if scope=='archived':lifecycle(a,'project',child)
    if scope=='task':entity='task';identity=task(a,child);task(a,child,identity)
    before=snapshot(a);r=delete_request(a,entity,identity);reviewed=r.args()['review']
    assert reviewed['eligible'] and reviewed['irreversible']
    projects={x['project_id'] for x in reviewed['projects']};tasks={x['task_id'] for x in reviewed['tasks']};retired={x['request_id'] for x in reviewed['retire_receipts']}
    assert reviewed['project_count']==len(projects) and reviewed['task_count']==len(tasks)
    assert reviewed['projects']==sorted(reviewed['projects'],key=lambda p:p['project_id'])
    assert a.delete(r).status=='committed';after=snapshot(a)
    assert after['projects']==[x for x in before['projects'] if x['project_id'] not in projects]
    assert after['tasks']==[x for x in before['tasks'] if x['task_id'] not in tasks]
    assert after['committed_requests']==[x for x in before['committed_requests'] if x['request_id'] not in retired]
    assert after['sqlite_sequence']==before['sqlite_sequence']
    for table in before.keys()-{'projects','tasks','committed_requests'}:assert after[table]==before[table]
    assert verified(a).semantic_verified
    assert a.execute(r).status=='rejected' and a.inspect(r).status=='unverified'


@pytest.mark.parametrize('text',['delete',' DELETE','DELETE ','',None,True])
def test_exact_confirmation_only(adapter,text):
    a=adapter;p=project(a);r=delete_request(a,'project',p,text);before=snapshot(a)
    assert a.delete(r).status=='rejected' and snapshot(a)==before


@pytest.mark.parametrize('change',['child','task','version','move','review','dataset'])
def test_stale_complete_review_refuses_without_writes(adapter,change):
    a=adapter;p=project(a);child=project(a,p);q=project(a);r=delete_request(a,'project',p)
    if change=='child':project(a,child)
    if change=='task':task(a,child)
    if change=='version':send(a,'rename_project',project_id=child,name='Renamed',expected_version=1)
    if change=='move':send(a,'move_project_subtree',**review(a,source=child,destination=q))
    if change=='review':
        args=r.args();args['review']['irreversible']=False;r=replace(r,arguments=__import__('chronicle.records',fromlist=['canonical']).canonical(args))
    if change=='dataset':r=replace(r,dataset_id=uid())
    before=snapshot(a);assert a.delete(r).status=='rejected' and snapshot(a)==before


@pytest.mark.parametrize('protected',['timed','dated','deleted','active','frozen zero','confirmed zero','frozen project after move'])
def test_one_protected_descendant_blocks_entire_project_scope(adapter,protected):
    a=adapter;p=project(a);child=project(a,p);q=project(a);t=task(a,child)
    if protected=='timed':
        e=uid();send(a,'start_timer',task_id=t,entry_id=e,expected_task_version=1,now=NOW-M);send(a,'stop_timer',entry_id=e,expected_version=1)
    if protected in ('dated','deleted'):
        e=dated(a,t)
        if protected=='deleted':send(a,'delete_work_entry',task_id=t,entry_id=e,expected_revision=1,comment='Retained')
    if protected=='active':send(a,'start_timer',task_id=t,entry_id=uid(),expected_task_version=1)
    if protected in ('frozen zero','frozen project after move'):
        export(a)
        if protected=='frozen project after move':send(a,'move_task_branch',**move_args(a,t,group=q))
    if protected=='confirmed zero':manual(a,t)
    before=snapshot(a);r=delete_request(a,'project',p)
    assert not r.args()['review']['eligible'] and r.args()['review']['reasons']
    assert a.delete(r).status=='rejected' and snapshot(a)==before
    assert verified(a).semantic_verified


def test_unused_child_can_delete_beside_parent_work(adapter):
    a=adapter;p=project(a);t=task(a,p);dated(a,t);child=project(a,p);unused=task(a,p,t)
    for entity,identity in (('project',child),('task',unused)):
        r=delete_request(a,entity,identity);assert r.args()['review']['eligible'];assert a.delete(r).status=='committed'
    assert snapshot(a)['work_entries'] and verified(a).semantic_verified


@pytest.mark.parametrize('kind',['project movement','task movement','apply'])
def test_cross_survivor_receipts_block_partial_retirement(adapter,kind):
    a=adapter;p=project(a);q=project(a);child=project(a,p);root=task(a,child);leaf=task(a,child,root)
    if kind=='project movement':send(a,'move_project_subtree',**review(a,source=child,destination=q));entity='task';identity=leaf
    elif kind=='task movement':send(a,'move_task_branch',**move_args(a,root,group=q));entity='task';identity=leaf
    else:
        d=template(a,2);_,result=send(a,'apply_template',**apply_args(a,d,group=p));entity='task';identity=result.result['created_tasks'][1]['task_id']
    r=delete_request(a,entity,identity);before=snapshot(a)
    assert not r.args()['review']['eligible'] and a.delete(r).status=='rejected' and snapshot(a)==before


@pytest.mark.parametrize('kind',['project movement','task movement','apply'])
def test_full_owned_move_or_apply_receipt_can_retire(adapter,kind):
    a=adapter;p=project(a);q=project(a);child=project(a,p);root=task(a,child);task(a,child,root)
    if kind=='project movement':send(a,'move_project_subtree',**review(a,source=child,destination=q));entity='project';identity=child;op='move_project_subtree'
    elif kind=='task movement':send(a,'move_task_branch',**move_args(a,root,group=q));entity='task';identity=root;op='move_task_branch'
    else:
        d=template(a,2);_,result=send(a,'apply_template',**apply_args(a,d,group=p));entity='task';identity=result.result['created_tasks'][0]['task_id'];op='apply_template'
    r=delete_request(a,entity,identity)
    assert op in {x['operation'] for x in r.args()['review']['retire_receipts']}
    assert r.args()['review']['eligible'] and a.delete(r).status=='committed' and verified(a).semantic_verified


@pytest.mark.parametrize('fault',['retirement','final','before_commit','close'])
def test_delete_failure_rolls_back_or_blocks_unverified_cleanup(adapter,fault):
    a=adapter;p=project(a);task(a,p);r=delete_request(a,'project',p);before=snapshot(a)
    connect=a.connect
    if fault=='retirement':
        def opened(readonly=False):
            c=connect(readonly)
            if not readonly:c.set_authorizer(lambda action,table,*rest:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_DELETE and table=='committed_requests' else sqlite3.SQLITE_OK)
            return c
        a.connect=opened
    def checkpoint(stage,c):
        if stage=='after_apply' and fault=='final':c.execute('UPDATE sqlite_sequence SET seq=seq+1')
        if stage=='before_commit' and fault in ('before_commit','close'):raise OSError('Original Delete failure')
        if stage=='close' and fault=='close':raise OSError('Close unavailable')
    a.checkpoint=checkpoint
    try:
        result=a.delete(r)
        assert result.status==('unverified' if fault=='close' else 'rolled_back' if fault in ('retirement','before_commit') else 'rejected'),result
        if fault=='close':
            assert a.unresolved_delete is r and a.delete(r).status=='unverified'
            with pytest.raises(RuntimeError):a.preview('project',p)
            a.retired.close();a.retired=None
        assert snapshot(a)==before
    finally:
        if a.retired is not None:a.retired.close();a.retired=None


def test_lost_delete_ack_never_reconciles_or_retries(adapter):
    a=adapter;p=project(a);r=delete_request(a,'project',p)
    def checkpoint(stage,c):
        if stage=='after_commit':raise OSError('Lost Delete acknowledgement')
    a.checkpoint=checkpoint;result=a.delete(r)
    assert result.status=='unverified' and a.unresolved_delete is r
    assert a.delete(r).status=='unverified' and a.inspect(r).status=='unverified'
    assert a.execute(Request.make(uid(),a.context.dataset_id,'create_project',NOW,project_id=uid(),name='Blocked')).status=='unverified'
    presence=a.presence('project',p);assert not presence['present'] and not presence['historical_outcome_verified']
    with pytest.raises(RuntimeError):a.preview('project',p)
    fresh=CandidateAdapter(a.path,a.context.dataset_id)  # Explicit exit/reopen boundary.
    assert verified(fresh).semantic_verified
    with pytest.raises(ValueError):fresh.preview('project',p)


@pytest.mark.parametrize('phase',['before_commit','after_commit'])
def test_real_delete_process_interruption_and_current_presence_only(adapter,phase):
    a=adapter;p=project(a);task(a,p);r=delete_request(a,'project',p);before=snapshot(a)
    code=r'''
import json,os,sys
from chronicle.records import Request
from project_candidate import CandidateAdapter
path,dataset,raw,phase=sys.argv[1:];x=json.loads(raw)
r=Request.make(x['request_id'],dataset,x['operation'],x['action_utc_us'],**x['arguments'])
def checkpoint(stage,c):
 if stage==phase:os._exit(39)
CandidateAdapter(path,dataset,checkpoint).delete(r)
raise AssertionError('Checkpoint not reached')
'''
    raw=dict(json.loads(r.content()),request_id=r.request_id)
    child=subprocess.run([sys.executable,'-B','-c',code,str(a.path),a.context.dataset_id,json.dumps(raw),phase],env=child_env(),capture_output=True,text=True,timeout=20)
    (a.path.parent/f'delete-{phase}-child.json').write_text(json.dumps(dict(returncode=child.returncode,stdout=child.stdout,stderr=child.stderr)))
    assert child.returncode==39 and not child.stderr
    a.unresolved_delete=r
    assert a.delete(r).status=='unverified'
    presence=a.presence('project',p);assert presence['present']==(phase=='before_commit') and not presence['historical_outcome_verified']
    fresh=CandidateAdapter(a.path,a.context.dataset_id);assert verified(fresh).semantic_verified
    if phase=='before_commit':
        assert snapshot(fresh)==before
        new=delete_request(fresh,'project',p);assert new.request_id!=r.request_id
        assert fresh.delete(new).status=='committed'
