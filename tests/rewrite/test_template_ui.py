"""Template UI against real Tk/SQLite worker; operator input is separate."""
from copy import deepcopy
from pathlib import Path
from threading import Event
import pytest
from chronicle.records import Outcome,Request
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.worker import Message
from conftest import uid,NOW
from test_app import root,connected,click,keyboard,pump
from test_main_explorer import task,project,select,settled,submit
from test_backup_restore import logical
from test_templates import nodes
from test_timesheet_save_ui import exit_settled


def facts(w):return logical(Path(w.directory)/'chronicle.sqlite3')
def manager(app):
    assert app.open_templates();m=app.templates_window;pump(app.root,lambda:m.window.winfo_ismapped());return m

def choose(m,key):m.tree.selection_set('template:'+key);m.controls()
def ready(app):pump(app.root,lambda:app.template_dialog is not None and app.template_dialog.presented);return app.template_dialog

def seed(app,title='Design',depth=2,roots=1):
    key=uid();submit(app,'create_template',template_id=key,name=title,nodes=nodes(depth,roots));return key


def test_real_tk_create_edit_reparent_reorder_cancel_and_duplicate(connected,monkeypatch):
    app,w,clock=connected;m=manager(app);assert not app.open_templates();before=facts(w)
    assert m.edit(False);d=ready(app);d.title.set('Design')
    names=iter(['A','B','C']);monkeypatch.setattr('chronicle.template_window.simpledialog.askstring',lambda *a,**k:next(names))
    assert d.add(False);a=d.selected_node();assert d.add(True);b=d.selected_node();assert d.add(False);c=d.selected_node()
    d.tree.selection_set(b);d.parent_choice.current(d.parent_ids.index(c));assert d.reparent()
    assert next(n for n in d.nodes if n['node_id']==b)['parent_node_id']==c
    d.tree.selection_set(c);assert d.reorder(-1);assert d.nodes[0]['node_id']==c
    assert facts(w)==before;assert d.submit();settled(app);key=d.key;assert d.close()
    choose(m,key);assert m.edit(True);d=ready(app);old=deepcopy(d.nodes);d.tree.selection_set(c);assert d.remove();assert d.close()
    assert app.state['templates'][0]['nodes']==old
    choose(m,key);assert m.edit(True);d=ready(app);d.title.set('Edited')
    d.tree.selection_set(c);monkeypatch.setattr('chronicle.template_window.simpledialog.askstring',lambda *a,**k:'Renamed node')
    assert d.rename();assert d.reorder(1);assert d.submit();settled(app);assert d.close()
    edited=next(t for t in app.state['templates'] if t['template_id']==key)
    assert {n['node_id'] for n in edited['nodes']}=={n['node_id'] for n in old} and edited['version']==2
    assert m.tree.get_children('template:'+key)==tuple('node:'+n['node_id'] for n in edited['nodes'] if n['parent_node_id'] is None)
    choose(m,key);assert m.duplicate();d=ready(app);d.title.set('Independent')
    assert {n['node_id'] for n in old}.isdisjoint(n['node_id'] for n in d.nodes)
    assert d.submit();settled(app);assert d.close();assert len(app.state['templates'])==2
    assert not app.root.test_errors


@pytest.mark.parametrize('destination',['project','unassigned','task'])
def test_real_tk_apply_frozen_destination_and_reveal_independent_tasks(connected,destination):
    app,w,clock=connected;p=project(app);a=task(app,group=p);key=seed(app,depth=2);m=manager(app);choose(m,key)
    select(app,app.project_row(p) if destination=='project' else app.task_row(a) if destination=='task' else app.project_row(None))
    assert m.apply();d=ready(app);frozen=deepcopy(d.arguments);before=facts(w)
    assert frozen['destination_parent_task_id']==(a if destination=='task' else None)
    assert frozen['destination_project_id']==(p if destination!='unassigned' else None)
    assert not app.start() and not app.open_move() and not app.open_delete() and not app.open_mini()
    assert d.submit();accepted=app.pending;assert accepted.args()==frozen;settled(app)
    created=app._mutation_outcome.result['created_tasks'];assert d.close()
    assert app.selected_task_id()==created[0]['task_id']
    assert app.tree.item(app.task_row(created[0]['task_id']),'open')
    assert app.tree.parent(app.task_row(created[1]['task_id']))==app.task_row(created[0]['task_id'])
    for table in ('work_entries','work_revisions','active_timer','timesheet_exports','polr_confirmation_cells'):assert facts(w)[table]==before[table]
    assert not app.root.test_errors


@pytest.mark.parametrize('kind',['running','depth','archive'])
def test_real_tk_apply_invalid_destination_refuses(connected,kind):
    app,w,clock=connected;a=task(app);select(app,app.task_row(a))
    if kind=='running':assert app.start();settled(app)
    if kind=='archive':
        from test_archived_items import archive
        archive(app,'task',a)
    key=seed(app,depth=3 if kind=='depth' else 1);m=manager(app);choose(m,key);assert m.apply();d=ready(app)
    index=next(i for i,o in enumerate(d.options) if o['args']['destination_parent_task_id']==a)
    d.choice.current(index);d.selected();before=facts(w)
    assert d.arguments is None and d.confirm_button.instate(['disabled']) and not d.submit()
    assert facts(w)==before and d.close()


@pytest.mark.parametrize('operation',['apply_template','edit_template'])
def test_real_tk_uncertain_ordinary_template_request_exact_retry_and_destroyed_view(connected,monkeypatch,operation):
    app,w,clock=connected;key=seed(app);m=manager(app);choose(m,key)
    assert m.apply() if operation=='apply_template' else m.edit(True)
    d=ready(app)
    if operation=='edit_template':d.title.set('Changed')
    original=TimerService.execute;calls=[]
    def lost(self,r):
        result=original(self,r)
        if r.operation==operation and not calls:calls.append(r);return Outcome('unverified',error=OSError('lost acknowledgement'))
        return result
    monkeypatch.setattr(TimerService,'execute',lost);assert d.submit();pump(app.root,lambda:not app.executing)
    request=app.pending;assert d.phase=='unverified' and not d.close() and not d.submit()
    m.window.destroy();d.window.destroy();assert app.pending is request and app.template_dialog is None
    assert app.retry();settled(app);assert app._mutation_outcome.status=='committed' and calls[0] is request
    assert not d.submit()


@pytest.mark.parametrize('committed',[False,True])
def test_real_tk_template_delete_typed_preview_and_no_retry_uncertainty(connected,monkeypatch,committed):
    app,w,clock=connected;key=seed(app);m=manager(app);choose(m,key);assert m.delete()
    d=app.deletion;pump(app.root,lambda:d.phase=='ready')
    assert 'Nodes:' in d.context.cget('text') and len(d.tree.get_children())==1
    before=facts(w);d.confirmed.set('delete');assert not d.submit() and facts(w)==before
    original=SQLiteStore.delete_unused;calls=[]
    def lost(self,r):
        calls.append(r)
        if committed:assert original(self,r).status=='committed'
        return Outcome('unverified',error=OSError('uncertain Delete'))
    monkeypatch.setattr(SQLiteStore,'delete_unused',lost);d.confirmed.set('DELETE');assert d.submit();pump(app.root,lambda:not app.executing)
    request=app.pending;assert d.phase=='unverified' and not app.retry() and not d.close() and not m.apply()
    assert app.inspect_delete_state();pump(app.root,lambda:app._delete_inspection_token is None)
    assert ('ABSENT' if committed else 'PRESENT') in d.status.cget('text') and app.pending is request and len(calls)==1
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**k:True);assert app.exit_delete_uncertain();exit_settled(app)


def test_real_tk_manager_refresh_no_churn_and_modal_exclusions(connected,monkeypatch):
    app,w,clock=connected;key=seed(app);m=manager(app);choose(m,key);m.tree.item('template:'+key,open=True);writes=[]
    for method in ('insert','delete','move','item'):
        original=getattr(m.tree,method)
        def spy(*a,_method=method,_original=original,**k):
            if _method!='item' or k:writes.append((_method,a,k))
            return _original(*a,**k)
        monkeypatch.setattr(m.tree,method,spy)
    app.refresh();settled(app);assert not writes and m.tree.selection()==('template:'+key,) and m.tree.item('template:'+key,'open')
    a=task(app);select(app,app.task_row(a));assert app.open_backup();pump(app.root,lambda:app.backup_dialog.presented)
    grab=app.root.grab_current();assert not m.edit(False) and not m.apply() and not m.delete() and app.root.grab_current() is grab
    app.backup_dialog.close()


def test_real_tk_server_manager_apply_selection_and_confirmation(connected,click,keyboard):
    app,w,clock=connected;key=seed(app,depth=1)
    click(app.buttons['Templates...']);pump(app.root,lambda:app.templates_window is not None and app.templates_window.window.winfo_ismapped())
    m=app.templates_window;m.tree.see('template:'+key);app.root.update_idletasks();x,y,width,height=m.tree.bbox('template:'+key)
    click(m.tree,(x+45,y+height//2));pump(app.root,lambda:m.selected() is not None)
    click(m.buttons['Apply']);d=ready(app);assert d.arguments is not None
    click(d.confirm_button);pump(app.root,lambda:d.phase=='complete');settled(app)
    assert len(app.state['tasks'])==1 and app.selected_task_id()==d.mapping[0]['task_id']
    click(d.close_button);assert app.template_dialog is None
    assert not app.root.test_errors


def test_real_tk_archive_unarchive_name_collision_and_actual_delete(connected):
    app,w,clock=connected;key=seed(app);m=manager(app);choose(m,key)
    assert m.archive(True);settled(app)
    assert m.tree.item('template:'+key,'values')[2]=='Archived' and m.buttons['Apply'].instate(['disabled'])
    assert not m.apply();other=seed(app);choose(m,key)
    assert m.archive(False);settled(app);assert app._mutation_outcome.status=='rejected'
    assert m.tree.item('template:'+key,'values')[2]=='Archived'
    assert m.edit(True);d=ready(app);d.title.set('Available');assert d.submit();settled(app);assert d.close()
    choose(m,key);assert m.archive(False);settled(app)
    assert m.tree.item('template:'+key,'values')[2]=='Active'
    assert m.apply();d=ready(app);assert d.submit();settled(app);assert d.close();before=facts(w)
    choose(m,key);assert m.delete();d=app.deletion;pump(app.root,lambda:d.phase=='ready')
    assert d.review['application_count']==1;d.confirmed.set('DELETE');assert d.submit();settled(app);assert d.close()
    assert not m.tree.exists('template:'+key) and m.tree.exists('template:'+other)
    assert facts(w)['tasks']==before['tasks'] and len(app.state['tasks'])==2
    assert any('collision' in str(e[1]).lower() for e in app.root.test_errors)


def test_real_tk_template_pending_destruction_and_stale_delivery(connected,monkeypatch):
    app,w,clock=connected;m=manager(app);assert m.edit(False);d=ready(app)
    d.title.set('Pending');d.nodes=nodes();d.render();entered,release=Event(),Event();original=TimerService.execute
    def blocked(self,r):
        if r.operation=='create_template':entered.set();assert release.wait(6)
        return original(self,r)
    monkeypatch.setattr(TimerService,'execute',blocked)
    try:
        assert d.submit();pump(app.root,entered.is_set);request=app.pending
        assert not d.close() and not d.submit() and not app.open_templates() and not app.open_delete()
        app._handle(Message('mutate',d.token+1,Outcome('committed',{}),request=request));assert app.pending is request and app.executing
        m.window.destroy();d.window.destroy();assert app.pending is request and app.template_dialog is None
    finally:release.set()
    settled(app);assert app._mutation_outcome.status=='committed' and len(app.state['templates'])==1 and not d.submit()
    m=manager(app);assert m.tree.exists('template:'+d.key)
