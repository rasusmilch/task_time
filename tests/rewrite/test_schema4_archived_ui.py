"""Pure archive provenance, sibling sorting and complete Delete presentation."""
from copy import deepcopy
import pytest
from chronicle import project_ui as ui
from chronicle.timekeeping import load_zone,to_us
from datetime import datetime
from chronicle.archived_window import SORTS
from schema4_cases import adapter,project,task,lifecycle,dated,uid
from test_schema4_project_ui import state,Tree
from chronicle.tree_install import install


def test_independent_archived_child_retains_active_project_and_task_context(adapter):
    a=adapter;p=project(a);q=project(a,p);t=task(a,q);child=task(a,q,t);lifecycle(a,'task',child)
    s=state(a);before=deepcopy(s);rows,children=ui.archived_projection(s,SORTS[2],'Today',load_zone('UTC'))
    assert set(rows)=={ui.project_row(p),ui.project_row(q),ui.task_row(t),ui.task_row(child)}
    assert rows[ui.project_row(q)]['parent']==ui.project_row(p)
    assert rows[ui.task_row(child)]['parent']==ui.task_row(t)
    for key in (ui.project_row(p),ui.project_row(q),ui.task_row(t)):
        assert rows[key]['context'] and rows[key]['source'] is None and rows[key]['values'][0]==''
    assert rows[ui.task_row(child)]['source']['task_id']==child and not rows[ui.task_row(child)]['context']
    assert s==before


def test_task_archive_precedes_nearest_project_provenance_and_dst_offset(adapter):
    a=adapter;p=project(a);q=project(a,p);deep=project(a,q);t=task(a,deep);child=task(a,deep,t)
    lifecycle(a,'project',p);lifecycle(a,'project',q);lifecycle(a,'task',t)
    s=state(a);projects={p['project_id']:p for p in s['projects']};tasks={t['task_id']:t for t in s['tasks']}
    first=to_us(datetime.fromisoformat('2026-11-01T06:30:00+00:00'));second=to_us(datetime.fromisoformat('2026-11-01T07:30:00+00:00'))
    projects[p]['archived_at_utc_us']=first;projects[q]['archived_at_utc_us']=second;tasks[t]['archived_at_utc_us']=first
    rows,children=ui.archived_projection(s,SORTS[2],'Today',load_zone('America/Chicago'))
    assert rows[ui.project_row(deep)]['source']['project_id']==q
    assert rows[ui.task_row(child)]['source']['task_id']==t
    assert rows[ui.project_row(p)]['values'][0].endswith('UTC-0500')
    assert rows[ui.project_row(q)]['values'][0].endswith('UTC-0600')
    assert len(rows)==5 and len(set(ui.installation_order(children)))==5


@pytest.mark.parametrize('order',SORTS)
def test_all_archive_orders_keep_siblings_context_first_and_selection(adapter,order):
    a=adapter;p=project(a);q=project(a,p);r=project(a,p);t=task(a,q);child=task(a,q,t);lifecycle(a,'task',child);lifecycle(a,'project',r)
    s=state(a);rows,children=ui.archived_projection(s,order,'Today',load_zone('UTC'))
    assert set(children[ui.project_row(p)])=={ui.project_row(q),ui.project_row(r)}
    if order.startswith('Date'):assert children[ui.project_row(p)][0]==ui.project_row(q)
    tree=Tree();install(tree,rows,children);key=ui.task_row(child);tree.selection_set((key,));tree.item(ui.project_row(q),open=True)
    tree.events.clear();install(tree,rows,children)
    assert not tree.events and tree.selection()==(key,) and tree.item(ui.project_row(q),'open')


def test_unarchive_ancestor_keeps_independent_descendant_and_reparents_survivors(adapter):
    a=adapter;p=project(a);q=project(a,p);t=task(a,q);lifecycle(a,'project',p);lifecycle(a,'task',t)
    rows,children=ui.archived_projection(state(a),SORTS[2],'Today',load_zone('UTC'));tree=Tree();install(tree,rows,children)
    lifecycle(a,'project',p,'unarchive')
    rows,children=ui.archived_projection(state(a),SORTS[2],'Today',load_zone('UTC'));install(tree,rows,children)
    assert tree.parent(ui.project_row(q))==ui.project_row(p) and rows[ui.project_row(p)]['context']
    assert rows[ui.task_row(t)]['item']['is_archived']==1


@pytest.mark.parametrize('protected',[False,True])
def test_delete_model_displays_full_backend_scope_without_eligibility_inference(adapter,protected):
    a=adapter;p=project(a);deep=p
    for _ in range(5):deep=project(a,deep)
    t=task(a,p);child=task(a,p,t);leaf=task(a,deep)
    if protected:dated(a,leaf)
    reviewed=a.preview('project',p);frozen=deepcopy(reviewed)
    rows,children=ui.delete_projection(reviewed)
    assert len(rows)==reviewed['project_count']+reviewed['task_count']==9
    assert rows[ui.task_row(leaf)]['parent']==ui.project_row(deep)
    assert rows[ui.task_row(child)]['parent']==ui.task_row(t)
    assert reviewed['eligible'] is (not protected) and reviewed==frozen
    tree=Tree();install(tree,rows,children);assert len(tree.rows)==9
