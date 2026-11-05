"""Connected real Tk + serialized C2 SQLite controls; no native input claim."""
from copy import deepcopy
from datetime import timedelta
from threading import Event
import pytest

from chronicle.app import ChronicleApp
from chronicle.worker import Message
from chronicle.records import Request,Outcome
from chronicle import project_ui as ui
from schema4_ui_bridge import CandidateBridge
from schema4_cases import adapter,uid,NOW
from test_app import root,pump,Clock
from test_main_explorer import settled,select
from test_schema4_ui_bridge import exchange
from test_schema4_project_ui import state as backend_state


@pytest.fixture
def connected_candidate(root,adapter):
    worker=CandidateBridge(adapter);clock=Clock()
    app=ChronicleApp(root,worker,now_utc=clock,presentation_profile='schema4-candidate')
    worker.start()
    try:
        pump(root,lambda:app.ready and app.state.get('report') is not None)
        yield app,worker,clock
    finally:
        if app.alive:root.destroy()
        worker.requests.put(Message('shutdown'));worker.join(timeout=10)
        assert not worker.is_alive() and worker.adapter.retired is None


def submit(app,op,**args):
    assert app._submit(op,**args);settled(app)
    assert app._mutation_outcome.status in ('committed','unchanged'),app._mutation_outcome
    return app._mutation_outcome


def project(app,parent=None,name='Duplicate'):
    key=uid();args=dict(project_id=key,name=name)
    if parent:
        p=next(p for p in app.state['projects'] if p['project_id']==parent)
        args.update(parent_project_id=parent,expected_parent_version=p['version'],reviewed_parent_ancestry=ui.ancestry(app.state,parent))
    submit(app,'create_child_project' if parent else 'create_project',**args)
    return key


def task(app,group=None,parent=None):
    key=uid();submit(app,'create_task',task_id=key,name='Duplicate',**ui.new_task_review(app.state,parent,group));return key


def moving(app,entity,key,destination):
    select(app,entity+':'+key);assert app.open_move();d=app.movement
    pump(app.root,lambda:d.presented)
    d.tree.selection_set(destination);d.selected();return d


def owned(app):return len(app.state['projects']),len(app.state['tasks'])


@pytest.mark.parametrize('target',['root','child','deep','task selection','unassigned','cancel','empty','stale'])
def test_project_creation_controls_frozen_review_and_reveal(connected_candidate,monkeypatch,target):
    app,w,clock=connected_candidate;p=project(app);deep=project(app,project(app,p));t=task(app,p)
    selected=deep if target=='deep' else p
    select(app,ui.task_row(t) if target=='task selection' else ui.UNASSIGNED if target=='unassigned' else ui.project_row(selected))
    before=owned(app);calls=clock.calls;prompts=[]
    def prompt(*args,**kw):
        prompts.append(args[1])
        if target=='stale':
            r=Request.make(uid(),app.dataset_id,'rename_project',NOW,project_id=selected,name='Concurrent',expected_version=1)
            w.requests.put(Message('mutate',998,r))
        return None if target=='cancel' else '' if target=='empty' else 'Accepted'
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',prompt)
    accepted=app.create_project() if target in ('root','cancel','empty') else app.create_child_project()
    if target in ('task selection','unassigned','cancel'):
        assert not accepted and owned(app)==before and clock.calls==calls
        return
    assert accepted;request=app.pending
    if target not in ('root','empty'):
        assert request.args()['parent_project_id']==selected
        assert request.args()['reviewed_parent_ancestry']==ui.ancestry(app.state,selected)
        assert all(r['project_id'] in prompts[0] for r in request.args()['reviewed_parent_ancestry'])
    settled(app)
    if target in ('empty','stale'):assert app._mutation_outcome.status=='rejected' and owned(app)==before
    else:
        assert app._mutation_outcome.status=='committed'
        assert app.tree.selection()==(ui.project_row(request.args()['project_id']),)
        assert app.tree.exists(app.tree.selection()[0])


@pytest.mark.parametrize('target',['root beneath root','child elsewhere','deep subtree','back root','noop','self','descendant','archived','stale ancestry','changed members'])
def test_project_move_exact_scope_ownership_and_authoritative_outcome(connected_candidate,target):
    app,w,clock=connected_candidate;p=project(app);child=project(app,p);deep=project(app,child);q=project(app);t=task(app,deep)
    key=p if target=='root beneath root' else child
    if target=='archived':submit(app,'archive_project',project_id=q,expected_version=1)
    destination=(ui.project_row(key) if target=='self' else ui.project_row(deep) if target=='descendant' else
        'group:root' if target=='back root' else ui.project_row(p) if target=='noop' else ui.project_row(q))
    before=backend_state(w.adapter);d=moving(app,'project',key,destination)
    assert app.editor is d.window and d.window.grab_current() is d.window
    assert key in d.source_path
    assert not app.create_project() and not app.open_history()
    if target in ('self','descendant','archived'):
        assert d.arguments is None and not d.submit();assert d.close();return
    arguments=deepcopy(d.arguments)
    assert set(arguments)=={'project_id','expected_version','source_parent_project_id','destination_parent_project_id','expected_destination_parent_version',
        'reviewed_source_ancestry','reviewed_destination_ancestry','reviewed_projects','reviewed_tasks'}
    assert t in {r['task_id'] for r in arguments['reviewed_tasks']}
    if target in ('stale ancestry','changed members'):
        # Serialized competing test operation bypasses UI only to establish a
        # real stale review; no fabricated backend completion.
        if target=='stale ancestry':r=Request.make(uid(),app.dataset_id,'rename_project',NOW,project_id=q,name='Changed',expected_version=1)
        else:r=Request.make(uid(),app.dataset_id,'create_task',NOW,task_id=uid(),name='Added',**ui.new_task_review(app.state,None,deep))
        w.requests.put(Message('mutate',998,r))
    assert d.submit();accepted=app.pending
    assert accepted.args()==arguments and app._move_submission.request is accepted
    settled(app)
    if target in ('stale ancestry','changed members'):assert app._mutation_outcome.status=='rejected'
    else:
        assert app._mutation_outcome.status==('unchanged' if target=='noop' else 'committed')
        after=backend_state(w.adapter)
        assert after['tasks']==before['tasks'] and after['report']['application']==before['report']['application']
        assert d.outcome is app._mutation_outcome
    assert d.close();assert app.root.grab_current() is None


@pytest.mark.parametrize('target',['nested project','unassigned','task parent','depth','running','archived'])
def test_task_move_stays_separate_and_carries_project_ancestries(connected_candidate,target):
    app,w,clock=connected_candidate;p=project(app);deep=project(app,project(app,p));q=project(app)
    root_task=task(app,q);child=task(app,q,root_task);dest=task(app,deep)
    if target=='depth':dest=task(app,deep,task(app,deep,dest))
    if target=='running':select(app,ui.task_row(dest));assert app.start();settled(app)
    if target=='archived':submit(app,'archive_project',project_id=p,expected_version=1)
    destination=ui.UNASSIGNED if target=='unassigned' else ui.project_row(deep) if target in ('nested project','archived') else ui.task_row(dest)
    d=moving(app,'task',root_task,destination)
    if target in ('depth','running','archived'):
        assert d.arguments is None and not d.submit();assert d.close();return
    assert 'reviewed_source_project_ancestry' in d.arguments and 'reviewed_destination_project_ancestry' in d.arguments
    assert d.submit() and app.pending.operation=='move_task_branch';settled(app)
    assert app._mutation_outcome.status=='committed';assert d.close()
    assert {t['task_id'] for t in app.state['tasks']}=={root_task,child,dest}


@pytest.mark.parametrize('action',['archive','unarchive','delete protected','delete unused'])
def test_archived_context_and_delete_complete_nested_presentation(connected_candidate,monkeypatch,action):
    app,w,clock=connected_candidate;p=project(app);q=project(app,p);deep=project(app,q);t=task(app,deep)
    if action=='delete protected':submit(app,'add_date_only_work',task_id=t,entry_id=uid(),work_date='2026-10-19',duration_text='0:15',comment='Retained')
    if action in ('archive','unarchive'):
        submit(app,'archive_task',task_id=t,expected_version=1)
        select(app,ui.project_row(p));monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**k:True)
        assert app.archive_selected();settled(app);assert not app.tree.exists(ui.project_row(p))
        assert app.open_archived();view=app.archived
        assert view.tree.parent(ui.project_row(q))==ui.project_row(p)
        view.tree.selection_set(ui.project_row(q));view.controls()
        assert view.unarchive_button.instate(['disabled']) and p in view.status.cget('text')
        view.tree.selection_set(ui.project_row(p));assert view.unarchive();settled(app)
        assert app.tree.exists(ui.project_row(p)) and not app.tree.exists(ui.task_row(t))
        assert next(t for t in app.state['tasks'] if t['task_id']==view.rows[ui.task_row(t)]['item']['task_id'])['is_archived']==1
        assert view.close();return
    select(app,ui.project_row(p));assert app.open_delete();d=app.deletion
    pump(app.root,lambda:d.phase in ('ready','blocked'))
    assert len(d.review['projects'])==3 and len(d.review['tasks'])==1
    assert d.tree.parent(ui.task_row(t))==ui.project_row(deep) and d.tree.parent(ui.project_row(q))==ui.project_row(p)
    if action=='delete protected':assert d.phase=='blocked' and not d.submit()
    else:
        d.confirmed.set('delete');assert not d.submit()
        d.confirmed.set('DELETE');d.controls();assert d.submit();settled(app)
        assert app._mutation_outcome.status=='committed' and not app.state['projects'] and not app.state['tasks']
    assert d.close()


@pytest.mark.parametrize('case',['closed after acceptance','stale completion','lost acknowledgement','presentation failure'])
def test_movement_request_outlives_widgets_and_retains_exact_reconciliation(connected_candidate,monkeypatch,case):
    app,w,clock=connected_candidate;p=project(app);q=project(app);d=moving(app,'project',p,ui.project_row(q))
    entered=Event();release=Event()
    def checkpoint(stage,c):
        if stage=='before_commit':entered.set();assert release.wait(8)
        if stage=='after_commit' and case=='lost acknowledgement':raise OSError('Lost acknowledgement')
    w.adapter.checkpoint=checkpoint
    if case=='presentation failure':monkeypatch.setattr(d,'record_result',lambda r:(_ for _ in ()).throw(ValueError('Presentation failure')))
    assert d.submit();request=app.pending;token=app._pending_token
    try:
        pump(app.root,entered.is_set)
        if case=='closed after acceptance':d.window.destroy();assert app.pending is request and app._move_submission.request is request
        if case=='stale completion':
            app._handle(Message('mutate',token-1,Outcome('committed',{}),request));assert app.pending is request and app.executing
    finally:release.set()
    settled(app);assert app._mutation_outcome.status=='committed' and app.pending is None
    if case!='closed after acceptance':assert d.close()
    assert next(p for p in app.state['projects'] if p['project_id']==request.args()['project_id'])['parent_project_id']==q


def test_template_apply_review_and_direct_history_and_task_only_timesheet(connected_candidate):
    from test_templates import nodes
    app,w,clock=connected_candidate;p=project(app);deep=project(app,project(app,p));t=task(app,deep)
    submit(app,'add_date_only_work',task_id=t,entry_id=uid(),work_date='2026-10-19',duration_text='0:10',comment='Direct')
    template=uid();submit(app,'create_template',template_id=template,name='Blueprint',nodes=nodes(2))
    source=app.state['templates'][0];select(app,ui.project_row(deep));assert app.open_template_dialog('apply',source)
    d=app.template_dialog;pump(app.root,lambda:d.presented)
    assert len(d.arguments['reviewed_destination_project_ancestry'])==3
    mapping=deepcopy(d.mapping);assert d.submit();request=app.pending;settled(app)
    assert request.args()['node_mapping']==mapping and app.selected_task_id()==mapping[0]['task_id']
    assert d.close()
    select(app,ui.task_row(t));assert app.open_history();pump(app.root,lambda:app.history.current)
    assert len(app.history.snapshot['rows'])==1;assert app.history.close()
    select(app,ui.project_row(p));assert not app.open_history()
    assert app.open_timesheet();sheet=app.timesheet
    pump(app.root,lambda:sheet.choices_token is None)
    assert deep in sheet.tasks.item(t,'values')[1]
    assert sheet.close()


def test_candidate_main_double_click_and_compact_mini_remain_existing_paths(connected_candidate):
    from types import SimpleNamespace
    app,w,clock=connected_candidate;p=project(app);t=task(app,p);other=task(app,p)
    select(app,ui.task_row(t));assert app.open_mini();assert app.mini.owner is app
    assert app.mini.today.cget('text')=='Today: 00:00'
    # Actual real-widget hit coordinates; generated callback, not native input.
    app.tree.item(ui.project_row(p),open=True)
    pump(app.root,lambda:bool(app.tree.bbox(ui.task_row(t))))
    for identity,op in ((t,'start_timer'),(other,'switch_timer'),(other,'stop_timer')):
        app.tree.see(ui.task_row(identity));box=app.tree.bbox(ui.task_row(identity))
        assert app._task_double_click(SimpleNamespace(widget=app.tree,x=box[0]+100,y=box[1]+box[3]//2))=='break'
        assert app.pending.operation==op;settled(app);clock.value+=timedelta(seconds=1)
    assert app.mini.show_main.instate(['!disabled'])
