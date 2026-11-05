"""Schema-4 template management/Apply and erased self-contained source history."""
from copy import deepcopy
import pytest
from schema4_cases import *
from test_templates import nodes
from test_project_movement import review


def test_complete_management_duplicate_and_deep_apply(adapter):
    a=adapter;p=project(a);deep=p
    for _ in range(5):deep=project(a,deep)
    d=template(a,3)
    send(a,'edit_template',template_id=d['template_id'],expected_version=1,name='Edited',nodes=d['nodes'])
    d=definitions(a)[d['template_id']]
    copy=uid();send(a,'duplicate_template',template_id=copy,name='Copy',source_template_id=d['template_id'],expected_source_version=d['version'],reviewed_source=d,
        node_mapping=sorted([dict(node_id=n['node_id'],new_node_id=uid()) for n in d['nodes']],key=lambda x:x['node_id']))
    d2=definitions(a)[copy]
    send(a,'archive_template',template_id=copy,expected_version=1)
    send(a,'unarchive_template',template_id=copy,expected_version=2)
    d2=definitions(a)[copy];before=snapshot(a)
    _,result=send(a,'apply_template',**apply_args(a,d2,group=deep))
    created={r['task_id'] for r in result.result['created_tasks']};after=snapshot(a)
    assert len(created)==3 and all(t['project_id']==deep for t in after['tasks'])
    assert all(after[t]==before[t] for t in before.keys()-{'tasks','committed_requests','sqlite_sequence'})
    assert verified(a).semantic_verified


@pytest.mark.parametrize('bad',['archive ancestor','task ancestor','running parent','depth','stale ancestry','mapping','template version','name collision'])
def test_apply_management_refusals_are_atomic(adapter,bad):
    a=adapter;p=project(a);child=project(a,p);t=task(a,child);d=template(a,1)
    args=apply_args(a,d,parent=t)
    if bad=='archive ancestor':lifecycle(a,'project',p);args=apply_args(a,d,parent=t)
    if bad=='task ancestor':lifecycle(a,'task',t);args=apply_args(a,d,parent=t)
    if bad=='running parent':send(a,'start_timer',task_id=t,entry_id=uid(),expected_task_version=1)
    if bad=='depth':bottom=task(a,child,task(a,child,t));args=apply_args(a,d,parent=bottom)
    if bad=='stale ancestry':send(a,'rename_project',project_id=p,name='New',expected_version=1)
    if bad=='mapping':args['node_mapping'].append(dict(args['node_mapping'][0]))
    if bad=='template version':args['expected_template_version']=2
    op='apply_template'
    if bad=='name collision':op='create_template';args=dict(template_id=uid(),name=' blueprint ',nodes=nodes(1))
    before=snapshot(a);r=Request.make(uid(),a.context.dataset_id,op,NOW,**args)
    assert a.execute(r).status=='rejected' and snapshot(a)==before


def test_definition_delete_retains_applied_tasks_work_and_snapshot(adapter):
    a=adapter;p=project(a);d=template(a,2)
    frozen,result=send(a,'apply_template',**apply_args(a,d,group=p));root=result.result['created_tasks'][0]['task_id'];leaf=result.result['created_tasks'][1]['task_id']
    dated(a,leaf);before=snapshot(a)
    r=delete_request(a,'template',d['template_id']);assert r.args()['review']['eligible']
    assert a.delete(r).status=='committed';after=snapshot(a)
    assert after['tasks']==before['tasks'] and after['work_entries']==before['work_entries']
    assert next(x for x in after['committed_requests'] if x['request_id']==frozen.request_id)==next(x for x in before['committed_requests'] if x['request_id']==frozen.request_id)
    assert not definitions(a) and verified(a).semantic_verified
    # Reuse of a relinquished name is permitted after erased management history.
    template(a,1,name='Blueprint');assert verified(a).semantic_verified


def test_duplicate_snapshot_survives_source_definition_delete(adapter):
    a=adapter;d=template(a,1);identity=uid()
    send(a,'duplicate_template',template_id=identity,name='Survivor',source_template_id=d['template_id'],expected_source_version=1,reviewed_source=d,
        node_mapping=[dict(node_id=d['nodes'][0]['node_id'],new_node_id=uid())])
    r=delete_request(a,'template',d['template_id']);assert len(r.args()['review']['source_context'])==1
    assert a.delete(r).status=='committed'
    assert identity in definitions(a) and verified(a).semantic_verified
