"""Pure candidate presentation/review and iterative Treeview-contract controls."""
from copy import deepcopy
import sys
import pytest

from chronicle import project_ui as ui
from chronicle.tree_install import install
from chronicle.schema4_services import read_state
from chronicle.project_accounting import project_report
from chronicle.accounting import calculate
from chronicle.timekeeping import load_zone
from schema4_cases import adapter, project, task, dated, send, snapshot, lifecycle, uid, NOW, M
from test_project_forest import project as project_fact


def state(a):
    c=a.connect(readonly=True)
    try:
        c.execute('BEGIN');result=read_state(c,a.context,cutoff_utc_us=NOW);c.execute('ROLLBACK');return result
    finally:c.close()


class Tree:
    """Deterministic widget-contract double, never native/widget acceptance."""
    def __init__(self):self.rows={};self.children={'':[]};self.selected=();self.scroll=(0.2,0.7);self.events=[]
    def selection(self):return self.selected
    def selection_set(self,keys):self.selected=tuple(keys);self.events.append(('select',self.selected))
    def yview(self):return self.scroll
    def yview_moveto(self,value):self.scroll=(value,self.scroll[1]);self.events.append(('scroll',value))
    def get_children(self,key=''):return tuple(self.children[key])
    def exists(self,key):return key in self.rows
    def parent(self,key):return self.rows[key]['parent']
    def index(self,key):return self.children[self.parent(key)].index(key)
    def insert(self,parent,index,*,iid,**fields):
        assert iid not in self.rows and (not parent or parent in self.rows)
        self.rows[iid]=dict(parent=parent,**fields);self.children[iid]=[];self.children[parent].append(iid);self.events.append(('insert',iid))
    def item(self,key,field=None,**fields):
        if fields:self.rows[key].update(fields);self.events.append(('item',key,fields))
        result=self.rows[key]
        return result[field] if field else result
    def move(self,key,parent,index):
        cursor=parent
        while cursor:
            assert cursor!=key
            cursor=self.parent(cursor)
        self.children[self.parent(key)].remove(key);self.rows[key]['parent']=parent
        siblings=self.children[parent]
        siblings.insert(len(siblings) if index=='end' else index,key);self.events.append(('move',key,parent))
    def delete(self,key):
        # Production installer removes obsolete rows individually, deepest first.
        assert not self.children[key]
        self.children[self.parent(key)].remove(key);del self.rows[key];del self.children[key];self.events.append(('delete',key))


def test_mixed_forest_typed_ids_independent_time_and_unassigned(adapter):
    a=adapter;p=project(a);child=project(a,p);empty=project(a);t=task(a,p);dated(a,t,'0:10');c=task(a,p,t);g=task(a,p,c);dated(a,g,'0:20');other=task(a,child);dated(a,other,'0:30');u=task(a);dated(a,u,'0:05')
    before=snapshot(a);observed=state(a);rows,children,path=ui.main_projection(observed)
    assert rows[ui.project_row(child)]['parent']==ui.project_row(p)
    assert rows[ui.task_row(t)]['parent']==ui.project_row(p) and rows[ui.task_row(g)]['parent']==ui.task_row(c)
    assert rows[ui.project_row(p)]['values'][1:]==('—','01:00')
    assert rows[ui.project_row(empty)]['values'][1:]==('—','00:00')
    assert rows[ui.task_row(t)]['values'][1:]==('00:10','00:30')
    assert rows[ui.UNASSIGNED]['values'][2]=='00:05' and rows[ui.task_row(u)]['parent']==ui.UNASSIGNED
    assert observed['report']['application']['today_us']==65*M
    assert len(list(ui.installation_order(children)))==len(rows)==len(set(rows)) and path is None
    assert snapshot(a)==before


@pytest.mark.parametrize('period',['Today','This Week'])
def test_archived_work_stays_in_parent_totals_and_missing_is_not_zero(adapter,period):
    a=adapter;p=project(a);child=project(a,p);t=task(a,child);dated(a,t);lifecycle(a,'project',child)
    s=state(a);rows,_,_=ui.main_projection(s,period=period)
    assert ui.project_row(child) not in rows and ui.task_row(t) not in rows
    assert rows[ui.project_row(p)]['values'][2]=='00:15'
    s['report']=None;rows,_,_=ui.main_projection(s,period=period)
    assert all(r['values'][1:]==('—','—') for r in rows.values())


def test_sibling_sort_duplicate_names_and_active_complete_path(adapter):
    a=adapter;p=project(a);q=project(a,p);deep=project(a,q);t=task(a,deep);child=task(a,deep,t)
    send(a,'rename_project',project_id=p,name='Zulu',expected_version=1)
    send(a,'rename_project',project_id=q,name='Alpha',expected_version=1)
    send(a,'start_timer',task_id=child,entry_id=uid(),expected_task_version=1)
    s=state(a);rows,children,path=ui.main_projection(s,alpha=True)
    assert path==(ui.project_row(p),ui.project_row(q),ui.project_row(deep),ui.task_row(t),ui.task_row(child))
    assert all('Running descendant' in rows[ui.project_row(k)]['values'][0] for k in (p,q,deep))
    assert rows[ui.task_row(child)]['values'][0]=='▶ Running'
    assert children[ui.project_row(p)]==[ui.project_row(q)]
    for keys in children.values():assert keys==sorted(keys,key=lambda k:(rows[k]['text'].casefold(),k))


def test_depth_beyond_python_recursion_and_incremental_survivor_installation():
    keys=[uid() for _ in range(sys.getrecursionlimit()+200)]
    projects=[project_fact(k,keys[i-1] if i else None) for i,k in enumerate(keys)]
    s=dict(projects=projects,tasks=[],active=None)
    s['report']=project_report(calculate([],[],None,NOW,load_zone('UTC'),6),[],projects)
    rows,children,_=ui.main_projection(s);tree=Tree();install(tree,rows,children,open_roots=True)
    leaf=ui.project_row(keys[-1]);tree.selection_set((leaf,));tree.item(leaf,open=True)
    tree.events.clear();install(tree,rows,children,open_roots=True)
    assert not tree.events and tree.selection()==(leaf,) and tree.yview()==(0.2,0.7)
    # A surviving child must be moved out before its former ancestry is erased.
    wanted={leaf:dict(parent='',text='Moved',values=('Group','—','00:00'),tags=())}
    install(tree,wanted,ui.ordered(wanted))
    assert list(tree.rows)==[leaf] and tree.selection()==(leaf,) and tree.item(leaf,'open')
    assert tree.events[0][0]=='move'
    install(tree,{}, {'':[]});assert tree.selection()==() and not tree.rows


def test_project_move_freezes_one_complete_source_and_selected_destination_only(adapter,monkeypatch):
    a=adapter;p=project(a);child=project(a,p);deep=project(a,child);q=project(a);t=task(a,child);sub=task(a,child,t)
    lifecycle(a,'task',sub)
    s=state(a);frozen=deepcopy(s);review=ui.ProjectMoveReview(s,child)
    calls=[];original=ui.ancestry
    def observed(s,key):calls.append(key);return original(s,key)
    monkeypatch.setattr(ui,'ancestry',observed)
    rows,children=ui.destination_rows(s,project_only=True)
    assert not calls and ui.UNASSIGNED not in rows and 'group:root' in rows
    args=review.arguments(q)
    assert calls==[q] and args['reviewed_source_ancestry'][-1]['project_id']==p
    assert {r['project_id'] for r in args['reviewed_projects']}=={child,deep}
    assert {r['task_id'] for r in args['reviewed_tasks']}=={t,sub}
    assert args['reviewed_projects']==sorted(args['reviewed_projects'],key=lambda p:p['project_id'])
    assert review.reason(child) and review.reason(deep) and review.reason(uid())
    assert review.arguments(None)['reviewed_destination_ancestry']==[]
    assert s==frozen


def test_task_creation_and_movement_reviews_retain_all_ancestry(adapter):
    from chronicle.movement import snapshot as branch
    a=adapter;p=project(a);deep=p
    for _ in range(5):deep=project(a,deep)
    q=project(a);t=task(a,deep);child=task(a,deep,t)
    s=state(a);args=ui.new_task_review(s,child)
    assert len(args['reviewed_destination_project_ancestry'])==6 and args['parent_task_id']==child
    assert ui.new_task_review(s)['reviewed_destination_project_ancestry']==[]
    moved,unchanged=ui.task_move_arguments(s,t,None,q,branch(s['tasks'],t))
    assert not unchanged and len(moved['reviewed_source_project_ancestry'])==6
    assert moved['reviewed_destination_project_ancestry'][-1]['project_id']==q
    assert {r['task_id'] for r in moved['reviewed_subtree']}=={t,child}
    label=ui.path_label(s,'task',child)
    assert all(k in label for k in (p,deep,t,child))


@pytest.mark.parametrize('profile,version,verified',[('schema3',4,True),('schema4-candidate',3,False),('schema4-candidate',4,False)])
def test_profile_readiness_mismatch_refuses_before_any_read_or_request(profile,version,verified):
    from chronicle.app import ChronicleApp
    from chronicle.worker import Message
    app=ChronicleApp.__new__(ChronicleApp);app.presentation_profile=profile;app.ready=False
    with pytest.raises(ValueError,match='do not match'):
        app._handle(Message('ready',value=dict(schema_version=version,candidate_verified=verified)))
    assert app.ready is False


@pytest.mark.parametrize('op,args',[('create_child_project',{}),('move_project_subtree',{}),('create_task',{'reviewed_destination_project_ancestry':[]})])
def test_schema3_owner_never_queues_schema4_requests(op,args):
    from test_pilot_usability import owner
    app,_,_=owner()
    assert not app._submit(op,**args)
    assert app.worker.requests.empty() and not app.observations and app.pending is None


@pytest.mark.parametrize('operation',['move_task_branch','move_project_subtree'])
def test_candidate_move_requires_exact_owned_dialog_before_allocating_identity(operation):
    from test_pilot_usability import owner
    app,_,_=owner();app.presentation_profile='schema4-candidate'
    assert not app._submit(operation) and app.worker.requests.empty() and not app.observations


def test_invalid_partial_presentation_has_no_installation_authority():
    tree=Tree();rows={'task:x':dict(parent='project:missing',text='Never install',values=())}
    with pytest.raises(ValueError):ui.ordered(rows)
    assert not tree.rows
    cyclic={'a':dict(parent='b',text='A'),'b':dict(parent='a',text='B')}
    with pytest.raises(ValueError):install(tree,cyclic,ui.ordered(cyclic))
    assert not tree.events


def test_candidate_unrelated_grab_blocks_direct_mutation_and_name_prompt():
    from test_pilot_usability import owner
    app,_,_=owner();app.presentation_profile='schema4-candidate';app.root.grab=object()
    assert app._ask_name('Must not open') is None
    assert not app._submit('create_project',project_id=uid(),name='Blocked')
    assert app.worker.requests.empty() and not app.observations
