"""Full candidate task management with reviewed project ancestry and work."""
from copy import deepcopy
from dataclasses import replace
import pytest
from schema4_cases import *
from test_project_movement import review


@pytest.mark.parametrize('destination',['root project','deep project','unassigned','task parent'])
def test_complete_task_branch_movement_preserves_work_and_frozen_evidence(adapter,destination):
    a=adapter;p=project(a);q=project(a);deep=project(a,project(a,project(a,q)))
    root=task(a,p);dated(a,root);child=task(a,p,root);dated(a,child);grand=task(a,p,child)
    leaf=task(a,q);frozen=export(a);before=snapshot(a)
    parent=leaf if destination=='task parent' else None
    identity=child if parent else root
    group={'root project':q,'deep project':deep,'unassigned':None,'task parent':q}[destination]
    req,result=send(a,'move_task_branch',**move_args(a,identity,parent,group))
    after=snapshot(a)
    members={r['task_id'] for r in req.args()['reviewed_subtree']}
    assert result.result['task_id']==identity and result.result['changed_tasks']
    for row in after['tasks']:
        old=next(t for t in before['tasks'] if t['task_id']==row['task_id'])
        if row['task_id'] in members:
            assert row['project_id']==group and row['version']==old['version']+1
        else:assert row==old
    for table in before.keys()-{'tasks','committed_requests','sqlite_sequence'}:assert after[table]==before[table]
    assert a.execute(req)==result and verified(a).semantic_verified


@pytest.mark.parametrize('bad',['source ancestry','destination ancestry','source version','member version','missing member','duplicate member','running parent','depth','archived destination','archived source'])
def test_task_move_refusal_and_no_partial_updates(adapter,bad):
    a=adapter;p=project(a);q=project(a);root=task(a,p);child=task(a,p,root);dest=task(a,q)
    args=move_args(a,root,group=q)
    if bad=='source ancestry':args['reviewed_source_project_ancestry']=[]
    if bad=='destination ancestry':args['reviewed_destination_project_ancestry']=[]
    if bad=='source version':args['expected_version']=2
    if bad=='member version':args['reviewed_subtree'][0]['expected_version']=2
    if bad=='missing member':args['reviewed_subtree'].pop()
    if bad=='duplicate member':args['reviewed_subtree'].append(deepcopy(args['reviewed_subtree'][0]))
    if bad=='running parent':
        send(a,'start_timer',task_id=dest,entry_id=uid(),expected_task_version=1);args=move_args(a,root,parent=dest)
    if bad=='depth':
        last=task(a,q,dest);bottom=task(a,q,last);args=move_args(a,root,parent=bottom)
    if bad=='archived destination':lifecycle(a,'project',q);args=move_args(a,root,group=q)
    if bad=='archived source':lifecycle(a,'project',p);args=move_args(a,root,group=q)
    before=snapshot(a);r=Request.make(uid(),a.context.dataset_id,'move_task_branch',NOW,**args)
    assert a.execute(r).status=='rejected' and snapshot(a)==before


def test_stale_ancestor_move_after_review_and_exact_retry(adapter):
    a=adapter;p=project(a);child=project(a,p);q=project(a);t=task(a,child)
    old=Request.make(uid(),a.context.dataset_id,'move_task_branch',NOW,**move_args(a,t,group=q))
    send(a,'move_project_subtree',**review(a,source=p,destination=q))
    before=snapshot(a)
    assert a.execute(old).status=='rejected' and snapshot(a)==before
    fresh,result=send(a,'move_task_branch',**move_args(a,t,group=q))
    send(a,'rename_task',task_id=t,name='Later',expected_version=2)
    assert a.execute(fresh)==result


def test_assignment_create_child_ancestry_active_and_noop(adapter):
    a=adapter;p=project(a);deep=project(a,project(a,p));t=task(a)
    groups={r['project_id']:r for r in snapshot(a)['projects']}
    req,result=send(a,'assign_task_to_project',task_id=t,project_id=deep,expected_version=1,
        reviewed_source_project_ancestry=[],reviewed_destination_project_ancestry=ancestry(groups,deep))
    args=dict(req.args(),expected_version=2,reviewed_source_project_ancestry=ancestry(groups,deep))
    before=snapshot(a);noop=Request.make(uid(),a.context.dataset_id,'assign_task_to_project',NOW,**args)
    assert a.execute(noop).status=='unchanged' and snapshot(a)==before
    child=task(a,deep,t);bottom=task(a,deep,child)
    assert verified(a).semantic_verified
    invalid=Request.make(uid(),a.context.dataset_id,'create_task',NOW,task_id=uid(),name='Too deep',parent_task_id=bottom,expected_parent_version=1,
        reviewed_destination_project_ancestry=ancestry(groups,deep))
    assert a.execute(invalid).status=='rejected'


def test_active_task_survives_safe_task_and_project_movement(adapter):
    a=adapter;p=project(a);q=project(a);t=task(a,p);entry=uid()
    send(a,'start_timer',task_id=t,entry_id=entry,expected_task_version=1)
    before=snapshot(a)
    send(a,'move_task_branch',**move_args(a,t,group=q))
    send(a,'move_project_subtree',**review(a,source=q,destination=p))
    after=snapshot(a)
    for table in ('active_timer','work_entries','work_revisions'):assert after[table]==before[table]
    assert verified(a).semantic_verified


@pytest.mark.parametrize('operation',['create_task','assign_task_to_project'])
def test_ancestor_rename_invalidates_exact_new_task_destination_review(adapter,operation):
    a=adapter;p=project(a);child=project(a,p);q=project(a);groups={r['project_id']:r for r in snapshot(a)['projects']}
    if operation=='create_task':args=dict(task_id=uid(),name='Reviewed',project_id=child,expected_project_version=1,reviewed_destination_project_ancestry=ancestry(groups,child))
    else:
        t=task(a,child);args=dict(task_id=t,project_id=q,expected_version=1,reviewed_source_project_ancestry=ancestry(groups,child),reviewed_destination_project_ancestry=ancestry(groups,q))
    frozen=Request.make(uid(),a.context.dataset_id,operation,NOW,**args)
    send(a,'rename_project',project_id=p,name='Ancestor changed',expected_version=1)
    before=snapshot(a);assert a.execute(frozen).status=='rejected' and snapshot(a)==before


def test_unassigned_task_creation_requires_explicit_empty_project_review(adapter):
    a=adapter;r=Request.make(uid(),a.context.dataset_id,'create_task',NOW,task_id=uid(),name='No review')
    before=snapshot(a);assert a.execute(r).status=='rejected' and snapshot(a)==before
    task(a);assert verified(a).semantic_verified


def test_task_movement_preserves_independent_descendant_archive_flags(adapter):
    a=adapter;p=project(a);q=project(a);root=task(a,p);child=task(a,p,root)
    lifecycle(a,'task',child);before=snapshot(a)
    send(a,'move_task_branch',**move_args(a,root,group=q));after=snapshot(a)
    old=next(t for t in before['tasks'] if t['task_id']==child);new=next(t for t in after['tasks'] if t['task_id']==child)
    assert (old['is_archived'],old['archived_at_utc_us'])==(new['is_archived'],new['archived_at_utc_us'])
    assert new['parent_task_id']==root and new['version']==old['version']+1 and verified(a).semantic_verified
