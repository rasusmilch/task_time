"""Detached candidate forest behavior; no calendar or database dependency."""
from copy import deepcopy
import sys

import pytest

from chronicle.hierarchy import ProjectForest, candidate_task_observations, MAX_TASK_LEVELS
from conftest import uid


def project(key=None, parent=None, archived=0):
    return dict(project_id=key or uid(), parent_project_id=parent, is_archived=archived, name='Duplicate')


def test_complete_order_children_roots_ancestry_and_detached_immutable_snapshot():
    a,z,b,c=[uid() for _ in range(4)]
    rows=[project(c,b),project(b,a),project(z),project(a)]
    saved=deepcopy(rows);forest=ProjectForest(rows)
    assert forest.roots==tuple(sorted((a,z)))
    assert forest.parents[c]==b and forest.children[a]==(b,) and forest.children[c]==()
    assert forest.root_membership[c]==a and forest.root_membership[z]==z
    assert forest.ancestry(c)==(a,b,c) and forest.descendants(a)==(a,b,c)
    assert forest.descendants(c)==(c,) and forest.ancestry(z)==(z,)
    assert set(forest.order)=={a,z,b,c} and forest.reverse_order==tuple(reversed(forest.order))
    assert forest.order.index(a)<forest.order.index(b)<forest.order.index(c)
    rows[0]['parent_project_id']=None;rows.clear()
    assert forest.ancestry(c)==(a,b,c) and saved[0]['parent_project_id']==b
    with pytest.raises(TypeError):forest.parents[c]=None
    with pytest.raises(AttributeError):forest.order=()
    with pytest.raises(AttributeError):del forest._sealed


def test_empty_and_single_root_are_complete():
    assert ProjectForest([]).order==()
    a=uid();forest=ProjectForest([project(a)])
    assert forest.order==(a,) and forest.roots==(a,) and not forest.effective_archived[a]


def test_deep_projects_exceed_python_recursion_without_cached_paths():
    count=sys.getrecursionlimit()+200
    keys=[uid() for _ in range(count)]
    rows=[project(key,keys[i-1] if i else None) for i,key in enumerate(keys)]
    forest=ProjectForest(reversed(rows))
    assert forest.order==tuple(keys) and forest.reverse_order==tuple(reversed(keys))
    assert forest.ancestry(keys[-1])==tuple(keys)
    assert forest.descendants(keys[0])==tuple(keys)
    assert forest.root_membership[keys[-1]]==keys[0]
    assert not hasattr(forest,'paths') and rows[-1]['parent_project_id']==keys[-2]


@pytest.mark.parametrize('bad',['uuid','uppercase','parent uuid','duplicate','self','cycle','disconnected cycle','missing','archive type','archive value','missing parent field'])
def test_invalid_complete_snapshot_refuses(bad):
    a,b,c=uid(),uid(),uid();rows=[project(a),project(b,a),project(c,b)]
    if bad=='uuid':rows[0]['project_id']='not-a-uuid'
    if bad=='uppercase':rows[0]['project_id']='ABCDEFAB-1234-1234-1234-123456789abc'
    if bad=='parent uuid':rows[1]['parent_project_id']='parent'
    if bad=='duplicate':rows.append(dict(rows[0]))
    if bad=='self':rows[0]['parent_project_id']=a
    if bad=='cycle':rows[0]['parent_project_id']=c
    if bad=='disconnected cycle':rows.extend([project('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002'),project('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001')])
    if bad=='missing':rows[1]['parent_project_id']=uid()
    if bad=='archive type':rows[0]['is_archived']=True
    if bad=='archive value':rows[0]['is_archived']=2
    if bad=='missing parent field':del rows[0]['parent_project_id']
    with pytest.raises((ValueError,KeyError)):ProjectForest(rows)


def test_archive_inheritance_preserves_independent_flags_and_recomputes():
    a,b,c,z=[uid() for _ in range(4)]
    rows=[project(a,archived=1),project(b,a),project(c,b,1),project(z)]
    forest=ProjectForest(rows)
    assert dict(forest.effective_archived)=={key:key!=z for key in (a,b,c,z)}
    assert [r['is_archived'] for r in rows]==[1,0,1,0]
    rows[0]['is_archived']=0;updated=ProjectForest(rows)
    assert not updated.effective_archived[a] and not updated.effective_archived[b]
    assert updated.effective_archived[c] and forest.effective_archived[a]


def test_mixed_project_and_task_forest_has_independent_depth_and_namespaces():
    keys=[uid() for _ in range(7)]
    projects=[project(key,keys[i-1] if i else None) for i,key in enumerate(keys)]
    # A task may share a UUID's text with a project; typed identity remains distinct.
    a,b,c=keys[0],uid(),uid()
    tasks=[dict(task_id=key,parent_task_id=parent,project_id=keys[-1],is_archived=0)
           for key,parent in ((a,None),(b,a),(c,b))]
    tasks.append(dict(task_id=uid(),parent_task_id=None,project_id=keys[1],is_archived=0))
    observations=candidate_task_observations(tasks,projects)
    assert MAX_TASK_LEVELS==3 and [observations[k]['depth'] for k in (a,b,c)]==[1,2,3]
    assert observations[c]['is_leaf'] and not observations[a]['is_leaf']
    assert tasks[0]['project_id']==keys[-1] and ProjectForest(projects).children[keys[1]]==(keys[2],)
    projects[1]['is_archived']=1
    assert all(v['effective_archived'] for v in candidate_task_observations(tasks,projects).values())
    fourth=dict(task_id=uid(),parent_task_id=c,project_id=keys[-1],is_archived=0)
    with pytest.raises(ValueError,match='three levels'):candidate_task_observations(tasks+[fourth],projects)


@pytest.mark.parametrize('method',['ancestry','descendants'])
def test_unknown_traversal_identity_refuses(method):
    with pytest.raises(ValueError,match='Unknown project'):getattr(ProjectForest([]),method)(uid())
