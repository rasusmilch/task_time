"""Real schema-2 subtree transactions and retained multi-entity evidence."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from chronicle import backup_restore as br
from chronicle.records import Request,canonical
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.movement import snapshot
from chronicle.worker import DatabaseWorker,Message
from conftest import NOW,uid
from test_hierarchy_foundation import create,group,verify,corrupt_with_original_guards
from test_backup_restore import logical,rich
from test_manual_work import dated,M
from test_services import FaultConnection
from test_interruptions import paused_child
from test_worker import receive


def review(store,root,parent=None,project=None):
    store._recover_connection();tasks=[dict(r) for r in store.connection.execute('SELECT * FROM tasks')]
    known={r['task_id']:r for r in tasks};r=known[root]
    return dict(task_id=root,expected_version=r['version'],source_parent_task_id=r['parent_task_id'],source_project_id=r['project_id'],
        destination_parent_task_id=parent,destination_project_id=project,
        expected_destination_parent_version=known[parent]['version'] if parent else None,
        expected_destination_project_version=store.connection.execute('SELECT version FROM projects WHERE project_id=?',(project,)).fetchone()[0] if project else None,
        reviewed_subtree=snapshot(tasks,root))


def execute(service,args):
    return service.move_task_branch(request_id=uid(),action_utc_us=NOW+M,**args)


@pytest.mark.parametrize('scenario',['project','unassigned','under_parent','child_other_root','same_parent','child_unassigned'])
def test_moves_keep_uuid_work_and_exact_version_effects(store,service,scenario):
    p=group(service);q=group(service);a=create(service,p);dated(service,a,duration='0:10')
    b=create(service,p,a);dated(service,b,duration='0:20');c=create(service,q)
    root=b if scenario.startswith('child') or scenario=='same_parent' else a
    parent=None;dest=q
    if scenario in ('unassigned','child_unassigned'):dest=None
    if scenario=='under_parent':parent=c
    if scenario=='same_parent':parent=create(service,p);dest=p
    args=review(store,root,parent,dest);before=logical(store.path)
    direct=service.read_current_state(cutoff_utc_us=NOW+M)['report']['individual']
    result=execute(service,args);assert result.status=='committed',result
    expected=[dict(task_id=r['task_id'],version=r['expected_version']+1) for r in args['reviewed_subtree'] if r['project_id']!=dest or r['task_id']==root and r['parent_task_id']!=parent]
    assert result.result==dict(task_id=root,changed_tasks=expected)
    rows={r['task_id']:dict(r) for r in store.connection.execute('SELECT * FROM tasks')}
    for r in args['reviewed_subtree']:
        new=rows[r['task_id']]
        assert new['project_id']==dest and new['parent_task_id']==(parent if r['task_id']==root else r['parent_task_id'])
        assert new['version']==r['expected_version']+(r['project_id']!=dest or r['task_id']==root and r['parent_task_id']!=parent)
    report=service.read_current_state(cutoff_utc_us=NOW+M)['report']
    assert report['individual']==direct and report['application']['today_us']==30*M
    assert report['cumulative'][a]['today_us']==(10*M if root==b else 30*M)
    if parent is not None:
        assert report['cumulative'][parent]['today_us']==(20*M if root==b else 30*M)
    moved=20*M if root==b else 30*M
    assert report['projects'][dest]['today_us']==(30*M if dest==p else moved)
    if dest!=p:assert report['projects'][p]['today_us']==30*M-moved
    for table in ('work_entries','work_revisions','active_timer','active_start_corrections'):assert logical(store.path)[table]==before[table]
    verify(store)
    if scenario=='unassigned':assert execute(service,review(store,a,project=p)).status=='committed';verify(store)


@pytest.mark.parametrize('bad',['source_version','source_parent','source_project','destination_version','destination_project_version','missing','extra','member_version','member_parent','unsorted','duplicate','cycle','depth','unknown_source','unknown_parent','unknown_project'])
def test_stale_or_invalid_moves_change_nothing(store,service,bad):
    p=group(service);q=group(service);a=create(service,p);b=create(service,p,a);c=create(service,p,b);d=create(service,q)
    args=review(store,a,d,q)
    if bad=='source_version':args['expected_version']=2
    if bad=='source_parent':args['source_parent_task_id']=d
    if bad=='source_project':args['source_project_id']=q
    if bad=='destination_version':args['expected_destination_parent_version']=2
    if bad=='destination_project_version':args['expected_destination_project_version']=2
    if bad=='missing':args['reviewed_subtree'].pop()
    if bad=='extra':args['reviewed_subtree']=sorted(args['reviewed_subtree']+review(store,d)['reviewed_subtree'],key=lambda r:r['task_id'])
    if bad=='member_version':args['reviewed_subtree'][0]['expected_version']+=1
    if bad=='member_parent':args['reviewed_subtree'][0]['parent_task_id']=uid()
    if bad=='unsorted':args['reviewed_subtree'].reverse()
    if bad=='duplicate':args['reviewed_subtree'].append(deepcopy(args['reviewed_subtree'][0]))
    if bad=='cycle':args=review(store,a,c,p)
    if bad=='unknown_source':args['task_id']=uid()
    if bad=='unknown_parent':args['destination_parent_task_id']=uid()
    if bad=='unknown_project':args['destination_project_id']=uid()
    # The entire height-three source cannot fit below a depth-one destination.
    before=logical(store.path)
    assert execute(service,args).status=='rejected'
    assert logical(store.path)==before
    verify(store)


def test_new_descendant_after_review_and_noop_exact_retry(store,service):
    p=group(service);a=create(service);args=review(store,a,project=p)
    create(service,parent=a);before=logical(store.path)
    assert execute(service,args).status=='rejected' and logical(store.path)==before
    assert execute(service,review(store,a)).status=='unchanged' and logical(store.path)==before
    request=Request.make(uid(),store.dataset_id,'move_task_branch',NOW+M,**review(store,a,project=p))
    first=service.execute(request);assert first.status=='committed'
    assert service.rename_task(a,'Later',expected_version=2,request_id=uid(),action_utc_us=NOW+2*M).status=='committed'
    after=logical(store.path)
    assert service.execute(request).result==first.result and service.reconcile_request(request).result==first.result
    assert service.execute(replace(request,action_utc_us=NOW+3*M)).status=='rejected'
    assert logical(store.path)==after;verify(store)


@pytest.mark.parametrize('where',['source','source_project','destination','destination_project','source_ancestor','destination_ancestor','active_destination'])
def test_ineligible_context_refuses(store,service,where):
    p=group(service);q=group(service);a=create(service,p);d=create(service,q)
    target=a if where=='source' else d
    if where.endswith('ancestor'):
        target=a if where=='source_ancestor' else d
        if where=='source_ancestor':a=create(service,p,target)
        else:d=create(service,q,target)
    if where=='active_destination':assert service.start_timer(d,uid(),expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    elif where.endswith('project'):
        store.connection.execute('UPDATE projects SET is_archived=1,archived_at_utc_us=? WHERE project_id=?',(NOW,p if where=='source_project' else q))
    else:store.connection.execute('UPDATE tasks SET is_archived=1,archived_at_utc_us=? WHERE task_id=?',(NOW,target))
    args=review(store,a,d,q);before=logical(store.path)
    assert execute(service,args).status=='rejected' and logical(store.path)==before;verify(store)


def test_active_leaf_and_independent_archived_descendant_preserved(store,service):
    p=group(service);q=group(service);a=create(service,p);b=create(service,p,a);arch=create(service,p,a)
    store.connection.execute('UPDATE tasks SET is_archived=1,archived_at_utc_us=? WHERE task_id=?',(NOW,arch))
    assert service.start_timer(b,uid(),expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    active=dict(store.connection.execute('SELECT * FROM active_timer').fetchone());archive=dict(store.connection.execute('SELECT * FROM tasks WHERE task_id=?',(arch,)).fetchone())
    assert execute(service,review(store,a,project=q)).status=='committed'
    assert dict(store.connection.execute('SELECT * FROM active_timer').fetchone())==active
    row=store.connection.execute('SELECT * FROM tasks WHERE task_id=?',(arch,)).fetchone()
    assert (row['is_archived'],row['archived_at_utc_us'])==(archive['is_archived'],archive['archived_at_utc_us'])
    verify(store)


@pytest.mark.parametrize('stage',['detach','project','attach','version','receipt','before_commit','after_commit'])
def test_failures_are_atomic_and_exact_retry(store,service,stage):
    p=group(service);q=group(service);a=create(service,p);b=create(service,p,a);d=create(service,q)
    request=Request.make(uid(),store.dataset_id,'move_task_branch',NOW+M,**review(store,a,d,q))
    real=store.connection;before=logical(store.path)
    class Fault:
        def __getattr__(self,n):return getattr(real,n)
        def execute(self,sql,*args):
            hit=(stage=='detach' and sql.startswith('UPDATE tasks SET parent_task_id=NULL') or stage=='project' and sql.startswith('UPDATE tasks SET project_id=') or stage=='attach' and sql.startswith('UPDATE tasks SET parent_task_id=?') or stage=='version' and sql.startswith('UPDATE tasks SET version=') or stage=='receipt' and sql.startswith('INSERT INTO committed_requests') or stage in ('before_commit','after_commit') and sql=='COMMIT')
            if hit:
                if stage=='after_commit':real.execute(sql,*args)
                raise OSError('move boundary fault')
            return real.execute(sql,*args)
    store.connection=Fault();result=service.execute(request)
    assert result.status==('committed' if stage=='after_commit' else 'rolled_back')
    if stage!='after_commit':assert logical(store.path)==before
    assert service.execute(request).status=='committed';verify(store)


@pytest.mark.parametrize('damage',['missing_member','extra_result','wrong_version','source','deleted_receipt'])
def test_corrupt_multi_entity_evidence_refuses_complete_validation(store,service,damage):
    p=group(service);a=create(service);b=create(service,parent=a)
    request=Request.make(uid(),store.dataset_id,'move_task_branch',NOW+M,**review(store,a,project=p))
    result=service.execute(request);assert result.status=='committed'
    if damage=='deleted_receipt':store.connection.execute('DELETE FROM committed_requests WHERE request_id=?',(request.request_id,))
    else:
        args=request.args();out=deepcopy(result.result)
        if damage=='missing_member':args['reviewed_subtree'].pop()
        if damage=='source':args['source_parent_task_id']=uid()
        if damage=='extra_result':out['changed_tasks'].append(dict(task_id=uid(),version=2))
        if damage=='wrong_version':out['changed_tasks'][0]['version']=8
        altered=Request.make(request.request_id,request.dataset_id,request.operation,request.action_utc_us,**args)
        corrupt_with_original_guards(store.connection,'UPDATE committed_requests SET request_bytes=?,result_bytes=? WHERE request_id=?',(altered.content(),canonical(out),request.request_id))
    with pytest.raises(ValueError):SQLiteStore._verify_complete(store.connection)
    directory=store.directory;store.close()
    with pytest.raises(ValueError):SQLiteStore(directory)


def test_worker_move_frozen_evidence_accounting_backup_restore(store,service,rich,tmp_path):
    root=rich['task'];p=group(service);q=group(service)
    # Rich root already has direct work and frozen/confirmed evidence.
    before=logical(store.path);old=service.read_current_state(cutoff_utc_us=NOW)['report'];args=review(store,root,project=q)
    dataset=store.dataset_id;directory=store.directory;store.close()
    worker=DatabaseWorker(directory);worker.start()
    try:
        assert worker.results.get(timeout=10).kind=='ready'
        request=Request.make(uid(),dataset,'move_task_branch',NOW,**args)
        worker.requests.put(Message('mutate',1,request));assert receive(worker,'mutate').status=='committed'
        worker.requests.put(Message('read',2,NOW));report=receive(worker,'read')['report']
        assert report['individual']==old['individual'] and report['application']==old['application']
        assert report['projects'][q]==old['individual'][root]
        worker.requests.put(Message('backup',3,dict(request_id=uid(),destination=str(tmp_path/'image.sqlite3'))))
        assert receive(worker,'backup')['result'].verified
    finally:worker.requests.put(Message('shutdown'));worker.join(10);assert not worker.is_alive()
    after=logical(directory/'chronicle.sqlite3')
    assert all(row in after['committed_requests'] for row in before['committed_requests'])
    for table in before:
        if table not in ('tasks','committed_requests','sqlite_sequence'):assert after[table]==before[table]
    target=tmp_path/'restore';assert br.restore_image(tmp_path/'image.sqlite3',target).verified
    reopened=SQLiteStore(target)
    try:
        verify(reopened);assert logical(reopened.path)==after
        s=TimerService(reopened);assert s.execute(request).status=='committed'
        current=s.prepare_timesheet_preview(export_id=uid(),cutoff_utc_us=NOW)
        assert next(t for t in current.tasks if t.task_id==root).project_id==q
    finally:reopened.close()


CHILD=r'''
import sys,json
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
from chronicle.records import Request
s=SQLiteStore(sys.argv[1]);real=s.connection;phase=sys.argv[3]
class Boundary:
 def __getattr__(self,n):return getattr(real,n)
 def execute(self,sql,*a):
  result=real.execute(sql,*a)
  if phase=='detach' and sql.startswith('UPDATE tasks SET parent_task_id=NULL') or phase=='receipt' and sql.startswith('INSERT INTO committed_requests') or phase=='commit' and sql=='COMMIT':
   print('BARRIER',flush=True);sys.stdin.readline()
  return result
s.connection=Boundary();r=TimerService(s).execute(Request.make(**json.loads(sys.argv[2])))
assert r.status=='committed',r
'''
@pytest.mark.parametrize('phase',['detach','receipt','commit'])
def test_move_process_death_preserves_atomic_forest_and_receipt(store,service,phase):
    p=group(service);a=create(service);b=create(service,parent=a);request=Request.make(uid(),store.dataset_id,'move_task_branch',NOW,**review(store,a,project=p))
    before=logical(store.path);directory=store.directory;store.close()
    args=dict(request_id=request.request_id,dataset_id=request.dataset_id,operation=request.operation,action_utc_us=NOW,**request.args())
    with paused_child(CHILD,directory,json.dumps(args),phase):pass
    reopened=SQLiteStore(directory)
    try:
        if phase!='commit':assert logical(reopened.path)==before
        s=TimerService(reopened);assert s.execute(request).status=='committed'
        after=logical(reopened.path);assert s.execute(request).status=='committed' and logical(reopened.path)==after
        verify(reopened)
    finally:reopened.close()
