"""Package D real Tk/worker/SQLite hierarchy, frozen review and lifecycle evidence."""
from copy import deepcopy
from datetime import timedelta
from threading import Event

import pytest

from chronicle.records import Outcome, Request
from chronicle.services import TimerService
from chronicle.worker import Message, DatabaseWorker
from chronicle.app import ChronicleApp
from conftest import uid, NOW
from test_app import root, connected, click, keyboard, pump
from pathlib import Path
from test_backup_restore import logical

def evidence(worker):
    return logical(Path(worker.directory)/"chronicle.sqlite3")
from test_main_explorer import project, task, submit, select, settled
from test_archived_items import archive, child, window, choose
from test_delete_ui import opened, authorize
from test_timesheet_save_ui import exit_settled


def moving(app,key,destination=None):
    select(app,app.task_row(key));assert app.open_move()
    d=app.movement;pump(app.root,lambda:d.presented)
    if destination is not None:
        d.tree.selection_set(destination);d.selected()
    return d


def apply_move(app,key,destination):
    d=moving(app,key,destination);assert d.arguments is not None,d.status.cget('text')
    assert d.submit()
    assert d.request is app.pending and d.request.args()==d.arguments
    assert set(d.request.args())=={'task_id','expected_version','source_parent_task_id','source_project_id',
        'destination_parent_task_id','destination_project_id','expected_destination_parent_version',
        'expected_destination_project_version','reviewed_subtree'}
    settled(app)
    assert app._mutation_outcome.status in ('committed','unchanged'),app._mutation_outcome
    assert d.close();return app._mutation_outcome


def all_rows(tree,parent=''):
    return [key for child in tree.get_children(parent) for key in [child,*all_rows(tree,child)]]


def test_real_tk_nested_tree_accounting_archived_hidden_sort_and_unavailable(connected,monkeypatch):
    app,w,clock=connected;p=project(app,'Duplicate');empty=project(app,'Duplicate');a=task(app,'Same',p)
    submit(app,'add_date_only_work',task_id=a,entry_id=uid(),work_date='2026-10-19',duration_text='0:10',comment='parent history')
    b=child(app,a,p);c=child(app,b,p);u=task(app,'Same');v=child(app,u,None)
    submit(app,'add_date_only_work',task_id=c,entry_id=uid(),work_date='2026-10-19',duration_text='0:20',comment='leaf')
    assert app.tree.parent(app.task_row(c))==app.task_row(b) and app.tree.parent(app.task_row(b))==app.task_row(a)
    assert app.tree.parent(app.task_row(v))==app.task_row(u)
    assert app.tree.exists(app.project_row(empty))
    assert len(all_rows(app.tree))==len(set(all_rows(app.tree)))==8
    assert app.tree.item(app.task_row(a),'values')[1:]==('00:10','00:30')
    assert app.tree.item(app.task_row(b),'values')[1:]==('00:00','00:20')
    assert app.tree.item(app.project_row(p),'values')[2]=='00:30'
    assert app.headline.cget('text')=='Today: 00:30    This week: 00:30'
    select(app,app.task_row(b));app.tree.item(app.task_row(a),open=False);before=evidence(w)
    app.sort_alpha.set(True);app._presentation_changed();app.period.set('This Week');app._presentation_changed()
    assert app.selected_task_id()==b and not app.tree.item(app.task_row(a),'open') and evidence(w)==before
    # Formatter failure clears every visible depth without hiding active identities.
    original=__import__('chronicle.app',fromlist=['format_duration']).format_duration
    monkeypatch.setattr('chronicle.app.format_duration',lambda _:(_ for _ in ()).throw(ValueError('format fault')))
    app.refresh();settled(app)
    assert all(app.tree.item(row,'values')[1:]==('—','—') for row in all_rows(app.tree))
    monkeypatch.setattr('chronicle.app.format_duration',original);app.refresh();settled(app)
    assert app.tree.item(app.task_row(c),'values')[1:]==('00:20','00:20')
    archive(app,'task',b)
    assert not app.tree.exists(app.task_row(b)) and not app.tree.exists(app.task_row(c))
    assert app.tree.item(app.task_row(a),'values')[1:]==('00:10','00:30')
    view=window(app);assert view.tree.parent(app.task_row(c))==app.task_row(b)
    choose(view,app.task_row(b));assert view.unarchive();settled(app)
    assert app.tree.parent(app.task_row(c))==app.task_row(b)
    assert not app.root.test_errors[:-1] # Only the deliberately injected formatter diagnosis.


@pytest.mark.parametrize('reason',['depth','running','cancel','stale_parent','stale_project'])
def test_real_tk_new_child_review_guards_and_cancellation(connected,monkeypatch,reason):
    app,w,clock=connected;p=project(app);a=task(app,group=p);b=child(app,a,p);c=child(app,b,p)
    key=c if reason in ('depth','running') else a
    if reason=='running':key=task(app);select(app,app.task_row(key));assert app.start();settled(app)
    select(app,app.task_row(key));before=evidence(w);prompts=[]
    def ask(*args,**kwargs):
        prompts.append(args[1])
        if reason.startswith('stale'):
            entity='task' if reason=='stale_parent' else 'project';target=a if entity=='task' else p
            r=Request.make(uid(),app.dataset_id,'rename_'+entity,NOW,**{entity+'_id':target,'name':'Changed','expected_version':1})
            w.requests.put(Message('mutate',992,r))
        return None if reason=='cancel' else 'New child'
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',ask)
    accepted=app.create_task()
    if reason in ('depth','running'):
        assert not accepted and not prompts and evidence(w)==before
        assert ('level 3' if reason=='depth' else 'Stop or Switch') in app.new_task_hint.cget('text')
        assert app.buttons['New Task'].instate(['disabled']) and ('level 3' in app.status.cget('text') or 'Stop' in app.status.cget('text'))
    elif reason=='cancel':assert not accepted and evidence(w)==before
    else:
        assert accepted;settled(app);assert app._mutation_outcome.status=='rejected'
        assert not any(t['name']=='New child' for t in app.state['tasks'])
        assert a in prompts[0] and p in prompts[0]


def test_real_tk_new_child_nonleaf_history_versions_and_reveal(connected,monkeypatch):
    app,w,clock=connected;p=project(app);a=task(app,group=p)
    submit(app,'add_date_only_work',task_id=a,entry_id=uid(),work_date='2026-10-19',duration_text='0:10',comment='direct')
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',lambda *a,**k:'Same')
    children=[]
    for _ in range(2):
        select(app,app.task_row(a));app.tree.item(app.project_row(p),open=False)
        assert app.create_task();settled(app);children.append(app.selected_task_id())
        assert app.tree.parent(app.task_row(children[-1]))==app.task_row(a)
        assert app.tree.item(app.project_row(p),'open') and app.tree.item(app.task_row(a),'open')
    assert children[0]!=children[1]
    assert next(t for t in app.state['tasks'] if t['task_id']==a)['version']==1
    select(app,app.task_row(a));assert not app.start();assert app.open_history()
    pump(app.root,lambda:app.history.current)
    assert app.history.task['task_id']==a and len(app.history.snapshot['rows'])==1
    app.history.close()


@pytest.mark.parametrize('case',['root_project','root_unassigned','unassigned_project','subtree_project','subtree_unassigned','reparent','cross_parent','noop'])
def test_real_tk_move_destinations_preserve_work_versions_and_selection(connected,case):
    app,w,clock=connected;p=project(app);q=project(app);a=task(app,group=p);b=child(app,a,p);c=child(app,b,p);dest=task(app,group=q)
    u=task(app)
    submit(app,'add_date_only_work',task_id=c,entry_id=uid(),work_date='2026-10-19',duration_text='0:15',comment='immutable')
    root,target={'root_project':(a,app.project_row(q)),'root_unassigned':(a,app.project_row(None)),
       'unassigned_project':(u,app.project_row(p)),'subtree_project':(b,app.project_row(q)),
       'subtree_unassigned':(b,app.project_row(None)),'reparent':(c,app.task_row(a)),
       'cross_parent':(b,app.task_row(dest)),'noop':(b,app.task_row(a))}[case]
    before=evidence(w);amounts=deepcopy(app.state['report']);result=apply_move(app,root,target);after=evidence(w)
    for table in ('work_entries','work_revisions','active_timer','timesheet_exports','polr_confirmation_cells'):assert after[table]==before[table]
    assert app.state['report']['individual']==amounts['individual'] and app.state['report']['application']==amounts['application']
    assert app.selected_task_id()==root
    if case=='noop':assert result.status=='unchanged' and before==after
    else:
        assert app.tree.parent(app.task_row(root))==target
        assert app.tree.item(target,'open')
        assert len(after['committed_requests'])==len(before['committed_requests'])+1
    assert not app.root.test_errors


@pytest.mark.parametrize('case',['self','descendant','depth','running_destination','archived_destination','stale_source','stale_destination','new_child'])
def test_real_tk_move_advisory_and_transactional_stale_guards(connected,case):
    app,w,clock=connected;p=project(app);a=task(app,group=p);b=child(app,a,p);c=child(app,b,p);dest=task(app,group=p)
    if case=='running_destination':select(app,app.task_row(dest));assert app.start();settled(app)
    if case=='archived_destination':archive(app,'task',dest)
    target={'self':a,'descendant':b,'depth':c}.get(case,dest)
    source=b if case.startswith('stale') or case=='new_child' else a
    d=moving(app,source,app.task_row(target));before=evidence(w)
    if not case.startswith('stale') and case!='new_child':
        assert d.arguments is None and not d.submit() and d.confirm_button.instate(['disabled'])
        assert evidence(w)==before;d.close();return
    if case=='new_child':
        op='create_task';args=dict(task_id=uid(),name='Racing',project_id=p,parent_task_id=b,expected_parent_version=1)
    else:op='rename_task';args=dict(task_id=b if case=='stale_source' else dest,name='Racing',expected_version=1)
    w.requests.put(Message('mutate',991,Request.make(uid(),app.dataset_id,op,NOW,**args)))
    assert d.submit();settled(app)
    assert d.phase=='failed' and app._mutation_outcome.status=='rejected' and not d.submit()
    assert d.close()


def test_real_tk_active_nested_status_path_move_collapse_stop_and_reopen(connected,root):
    app,w,clock=connected;p=project(app);q=project(app);a=task(app,group=p);b=child(app,a,p);c=child(app,b,p)
    select(app,app.task_row(c));assert app.start();settled(app);active=deepcopy(app.state['active'])
    for key in (a,b):
        assert app.tree.item(app.task_row(key),'values')[0]=='▶ Running descendant'
        assert app.tree.item(app.task_row(key),'open')
    assert app.tree.item(app.task_row(c),'values')[0]=='▶ Running'
    app.tree.item(app.task_row(a),open=False);app.refresh();settled(app)
    assert not app.tree.item(app.task_row(a),'open')
    select(app,app.task_row(a))
    assert not app.buttons['New Task'].instate(['disabled']) # Parent a is not itself running.
    apply_move(app,a,app.project_row(q));assert app.state['active']==active
    assert app.tree.item(app.task_row(a),'open') and app.tree.item(app.project_row(q),'open')
    assert app.open_mini() and app.mini.name.cget('text')=='Same'
    select(app,app.project_row(q));assert not app.start() and not app.switch()
    clock.value+=timedelta(seconds=1)
    assert app.stop();settled(app);assert app.state['active'] is None
    # Reopen with a genuinely persisted nested active timer and a fresh owner/worker.
    select(app,app.task_row(c));assert app.start();settled(app);active=deepcopy(app.state['active'])
    app.mini.window.destroy();app.request_close();exit_settled(app);w.join(8)
    import tkinter as tk
    r=tk.Tk();errors=[];r.report_callback_exception=lambda *a:errors.append(a)
    worker=DatabaseWorker(w.directory);fresh=ChronicleApp(r,worker,now_utc=clock);worker.start()
    try:
        pump(r,lambda:fresh.ready and fresh.state['report'] is not None)
        assert fresh.state['active']==active
        for key in (a,b):assert fresh.tree.item(fresh.task_row(key),'open')
        assert fresh.tree.parent(fresh.task_row(c))==fresh.task_row(b)
        assert not errors
    finally:r.destroy();worker.join(8);assert not worker.is_alive()


@pytest.mark.parametrize('lost',['committed','absent','destroyed'])
def test_real_tk_move_uncertainty_exact_retry_and_destroyed_owner_context(connected,monkeypatch,lost):
    app,w,clock=connected;p=project(app);q=project(app);a=task(app,group=p);d=moving(app,a,app.project_row(q))
    original=TimerService.execute;calls=[]
    def uncertain(self,r):
        if r.operation!='move_task_branch':return original(self,r)
        calls.append(r)
        if len(calls)==1:
            if lost!='absent':assert original(self,r).status=='committed'
            return Outcome('unverified',error=OSError('lost move acknowledgement'))
        return original(self,r)
    monkeypatch.setattr(TimerService,'execute',uncertain)
    assert d.submit();pump(app.root,lambda:not app.executing);accepted=app.pending
    assert accepted and d.phase=='unverified' and not d.close() and not d.submit()
    assert not app.open_delete() and not app.start() and not app.open_mini()
    if lost=='destroyed':d.window.destroy();assert app.movement is None and app.pending is accepted
    assert app.retry();settled(app)
    assert app._mutation_outcome.status=='committed' and app.tree.parent(app.task_row(a))==app.project_row(q)
    assert all(r is accepted for r in calls) and len(evidence(w)['committed_requests'])==4
    if lost!='destroyed':assert d.phase=='complete' and d.close()


@pytest.mark.parametrize('modal',['history','timesheet','backup','delete','correction'])
def test_real_tk_move_modal_exclusion_and_frozen_destination(connected,modal):
    app,w,clock=connected;a=task(app);view=window(app);select(app,app.task_row(a))
    if modal=='history':assert app.open_history();pump(app.root,lambda:app.history.current)
    elif modal=='timesheet':assert app.open_timesheet();pump(app.root,lambda:app.timesheet.presented)
    elif modal=='backup':assert app.open_backup();pump(app.root,lambda:app.backup_dialog.presented)
    elif modal=='delete':opened(app,app.task_row(a))
    else:assert app.start();settled(app);app.correct_active_start();pump(app.root,lambda:app.editor is not None and app.root.grab_current() is app.editor)
    grab=app.root.grab_current();assert not app.open_move() and app.root.grab_current() is grab
    if modal=='history':app.history.close()
    elif modal=='timesheet':app.timesheet.close()
    elif modal=='backup':app.backup_dialog.close()
    else:app._close_editor(app.editor)
    d=moving(app,a);grab=app.root.grab_current()
    assert not app.open_history() and not app.open_delete() and not view.unarchive() and not view.delete()
    assert not app.open_mini() and not app.show_main() and app.root.grab_current() is grab
    assert d.close()


def test_real_tk_server_move_review_confirm_and_new_task_cancel(connected,click,keyboard):
    app,w,clock=connected;p=project(app);q=project(app);a=task(app,group=p);select(app,app.task_row(a))
    click(app.buttons['Move / Reparent']);pump(app.root,lambda:app.movement is not None and app.movement.presented)
    d=app.movement;d.tree.see(app.project_row(q));app.root.update_idletasks()
    x,y,width,height=d.tree.bbox(app.project_row(q));click(d.tree,(x+45,y+height//2))
    pump(app.root,lambda:d.arguments is not None);assert q in d.status.cget('text')
    click(d.confirm_button);pump(app.root,lambda:d.phase=='complete');settled(app)
    assert app.tree.parent(app.task_row(a))==app.project_row(q)
    click(d.close_button);before=evidence(w)
    # Real toolkit name dialog: inspect the actual reviewed path and cancel via Escape.
    from tkinter import simpledialog
    errors=[];shown=[]
    def descendants(widget):
        return [c for child in widget.winfo_children() for c in [child,*descendants(child)]]
    def cancel_name():
        dialog=next((w for w in app.root.winfo_children() if isinstance(w,simpledialog.Dialog)),None)
        if dialog is None:
            errors.append(AssertionError('Expected name dialog was not constructed'));return
        shown.append(dialog)
        try:
            text=' '.join(str(w.cget('text')) for w in descendants(dialog) if 'text' in w.keys())
            assert a in text and q in text
            keyboard[0]('Escape')
        except Exception as e:
            errors.append(e);dialog.cancel()
    def abort():
        for w in app.root.winfo_children():
            if isinstance(w,simpledialog.Dialog):
                errors.append(TimeoutError('Name dialog did not consume Escape'));w.cancel()
    timeout=app.root.after(2000,abort)
    app.root.after(150,cancel_name)
    try:click(app.buttons['New Task'])
    finally:app.root.after_cancel(timeout)
    assert shown and not errors and evidence(w)==before and app.pending is None


def test_real_tk_nested_refresh_no_churn_and_reparent_before_ancestor_removal(connected,monkeypatch):
    app,w,clock=connected;p=project(app);a=task(app,group=p);b=child(app,a,p);c=child(app,b,p)
    app.tree.item(app.task_row(a),open=True);app.tree.item(app.task_row(b),open=False)
    select(app,app.task_row(c));before=evidence(w);scroll=app.tree.yview();writes=[]
    for name in ('insert','move','delete','item'):
        original=getattr(app.tree,name)
        def spy(*args,_name=name,_original=original,**kwargs):
            if _name!='item' or kwargs:writes.append((_name,args,kwargs))
            return _original(*args,**kwargs)
        monkeypatch.setattr(app.tree,name,spy)
    app.refresh();settled(app)
    assert not writes and evidence(w)==before and app.selected_task_id()==c and app.tree.yview()==scroll
    app.period.set('This Week');app._presentation_changed()
    assert not writes and app.tree.item(app.task_row(a),'open') and not app.tree.item(app.task_row(b),'open')
    # One coalesced snapshot can move a survivor and archive its obsolete old ancestor.
    candidate=deepcopy(app.state)
    ta=next(t for t in candidate['tasks'] if t['task_id']==a);ta['effective_archived']=True;ta['is_archived']=1
    tb=next(t for t in candidate['tasks'] if t['task_id']==b);tb['parent_task_id']=None
    app._render(candidate)
    assert not app.tree.exists(app.task_row(a)) and app.tree.parent(app.task_row(b))==app.project_row(p)
    assert app.tree.parent(app.task_row(c))==app.task_row(b) and app.selected_task_id()==c
    assert not any(name=='delete' and app.task_row(b) in args for name,args,kw in writes)


def test_real_tk_move_preserves_frozen_confirmation_archived_flags_active_and_grouping(connected,tmp_path,monkeypatch):
    from test_polr_confirmation_ui import saved, reviewed
    app,w,clock=connected;p=project(app);q=project(app);a=task(app,group=p)
    select(app,app.task_row(a));_,sheet,candidate,dest=saved(app,tmp_path,monkeypatch)
    assert sheet.review_polr();reviewed(app,sheet);assert sheet.confirm_polr();reviewed(app,sheet)
    assert sheet.close();b=child(app,a,p);hidden=child(app,a,p);archive(app,'task',hidden);target=task(app,group=q)
    select(app,app.task_row(b));assert app.start();settled(app);active=deepcopy(app.state['active'])
    before=evidence(w);prior=deepcopy(app.state['report']);hidden_before=next(t for t in app.state['tasks'] if t['task_id']==hidden)
    view=window(app);view.tree.item(app.task_row(hidden),open=True);choose(view,app.task_row(hidden))
    result=apply_move(app,a,app.task_row(target));assert result.status=='committed'
    after=evidence(w)
    for table in before:
        if table not in ('tasks','committed_requests','sqlite_sequence'):assert after[table]==before[table],table
    assert dict(after['sqlite_sequence'])['committed_requests']==dict(before['sqlite_sequence'])['committed_requests']+1
    assert app.state['active']==active and dest.read_bytes()==candidate.report_utf8
    assert app.state['report']['individual']==prior['individual'] and app.state['report']['application']==prior['application']
    assert app.tree.item(app.project_row(p),'values')[2]=='00:00'
    assert app.tree.item(app.project_row(q),'values')[2]=='03:00'
    assert app.tree.item(app.task_row(target),'values')[1:]==('00:00','03:00')
    updated=next(t for t in app.state['tasks'] if t['task_id']==hidden)
    for key in ('is_archived','archived_at_utc_us','task_id','created_request_id'):assert updated[key]==hidden_before[key]
    assert not app.tree.exists(app.task_row(hidden)) and view.tree.exists(app.task_row(hidden))
    assert view.tree.item(app.task_row(hidden),'open') and view.tree.selection()==(app.task_row(hidden),)
    assert app.selected_task_id()==a and not app.start() # Parent is never a new work destination.


@pytest.mark.parametrize('destroy',[False,True])
def test_real_tk_pending_move_destroy_cancel_and_unrelated_delivery(connected,monkeypatch,destroy):
    app,w,clock=connected;p=project(app);a=task(app);d=moving(app,a,app.project_row(p))
    entered,release=Event(),Event();original=TimerService.execute
    def blocked(self,r):
        if r.operation=='move_task_branch':entered.set();assert release.wait(6)
        return original(self,r)
    monkeypatch.setattr(TimerService,'execute',blocked)
    try:
        assert d.submit();pump(app.root,entered.is_set);request=app.pending
        assert not d.close() and not d.submit() and not app.open_move()
        app._handle(Message('mutate',d.token+1,Outcome('committed',{}),request=request))
        assert app.pending is request and app.executing
        if destroy:d.window.destroy();assert app.movement is None and app.pending is request and not d.submit()
    finally:release.set()
    settled(app);assert app._mutation_outcome.status=='committed' and app.selected_task_id()==a
    if not destroy:assert d.close()
    # Old disposed view cannot submit or consume another accepted operation.
    assert not d.submit()


@pytest.mark.parametrize('where',['queue','presentation','worker_stop'])
def test_real_tk_move_failure_cleanup_and_explicit_unresolved_exit(connected,monkeypatch,where):
    app,w,clock=connected;p=project(app);a=task(app);d=moving(app,a,app.project_row(p));original=w.requests.put
    if where in ('queue','worker_stop'):
        def intercept(m):
            if m.kind=='mutate':
                if where=='queue':raise OSError('queue unavailable')
            else:original(m)
        monkeypatch.setattr(w.requests,'put',intercept)
    else:
        original_status=d.status.configure
        def fail(**kwargs):
            if kwargs.get('text','').startswith('Move committed'):raise RuntimeError('Move presentation failed')
            return original_status(**kwargs)
        monkeypatch.setattr(d.status,'configure',fail)
    accepted=d.submit()
    if where=='queue':
        assert not accepted and app.pending is None and not app.executing and d.phase=='failed' and d.close()
    elif where=='presentation':
        assert accepted;settled(app);assert app.pending is None and d.phase=='complete'
        assert app._mutation_outcome.status=='committed' and app.tree.parent(app.task_row(a))==app.project_row(p)
        assert d.close()
    else:
        assert accepted;request=app.pending;original(Message('shutdown'));w.join(8)
        pump(app.root,lambda:app._worker_stopped)
        assert app.pending is request and d.phase=='unverified' and not d.close()
        prompts=[]
        def no(*args,**kwargs):prompts.append(kwargs);return False
        monkeypatch.setattr('chronicle.app.messagebox.askyesno',no)
        assert not app.exit_move_uncertain() and app.pending is request and app.root.grab_current() is d.window
        assert prompts[0]['parent'] is d.window and prompts[0]['default']=='no'
        monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**k:True)
        assert app.exit_move_uncertain() and not app.alive


def test_real_tk_nested_sibling_sort_preserves_expansion_uuid_and_source_order(connected):
    app,w,clock=connected;p=project(app,'Z');q=project(app,'A');a=task(app,'Root',p)
    b=child(app,a,p,name='z');c=child(app,a,p,name='A');d=child(app,a,p,name='a')
    leaf=child(app,b,p,name='Bottom');source=app.tree.get_children(app.task_row(a))
    select(app,app.task_row(leaf));app.tree.item(app.task_row(a),open=True);app.tree.item(app.task_row(b),open=False)
    before=evidence(w);app.sort_alpha.set(True);app._presentation_changed()
    expected=tuple(app.task_row(key) for key in sorted((b,c,d),key=lambda key:(next(t['name'].casefold() for t in app.state['tasks'] if t['task_id']==key),key)))
    assert app.tree.get_children(app.task_row(a))==expected and app.selected_task_id()==leaf
    assert app.tree.parent(app.task_row(leaf))==app.task_row(b) and not app.tree.item(app.task_row(b),'open')
    assert app.tree.get_children().index(app.project_row(q))<app.tree.get_children().index(app.project_row(p))
    app.sort_alpha.set(False);app._presentation_changed()
    assert app.tree.get_children(app.task_row(a))==source and evidence(w)==before


def test_real_tk_nested_lifecycle_clears_hidden_selection_without_retargeting(connected,monkeypatch):
    app,w,clock=connected;p=project(app);a=task(app,group=p);b=child(app,a,p);c=child(app,b,p)
    select(app,app.task_row(b));archive(app,'task',b)
    assert not app.tree.selection() and app.selected_task_id() is None and not app.start()
    view=window(app);choose(view,app.task_row(b));assert view.unarchive();settled(app)
    assert not app.tree.selection() and app.tree.parent(app.task_row(c))==app.task_row(b)
    d=opened(app,app.task_row(b));assert authorize(d);settled(app);assert d.close()
    assert not app.tree.selection() and not app.tree.exists(app.task_row(b)) and app.selected_task_id() is None
    select(app,app.project_row(p));monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**k:True)
    assert app.archive_selected();settled(app)
    assert not app.tree.exists(app.project_row(p)) and not app.tree.selection()
    choose(view,app.project_row(p));assert view.unarchive();settled(app)
    assert app.tree.exists(app.project_row(p)) and not app.tree.selection()
    assert not app.root.test_errors


def test_real_tk_removed_nested_row_and_failed_numeric_render_clear_every_value(connected,monkeypatch):
    app,w,clock=connected;p=project(app);a=task(app,group=p);b=child(app,a,p);c=child(app,b,p)
    select(app,app.task_row(c))
    before=deepcopy(app.state);candidate=deepcopy(before);candidate['tasks']=[t for t in before['tasks'] if t['task_id']!=c]
    original=__import__('chronicle.app',fromlist=['format_duration']).format_duration
    monkeypatch.setattr('chronicle.app.format_duration',lambda _:(_ for _ in ()).throw(ValueError('presentation interrupted')))
    app._read_inflight=app._token+1;app._token+=1
    app._handle(Message('read',app._token,candidate))
    assert app.state['report'] is None
    assert all(app.tree.item(row,'values')[1:]==('—','—') for row in all_rows(app.tree))
    assert app.tree.item(app.task_row(c),'values')[0]=='Unavailable'
    assert not app.tree.selection() and app.selected_task_id() is None and not app.start()
    assert len(app.root.test_errors)==1 and 'presentation interrupted' in str(app.root.test_errors[0][1])
    monkeypatch.setattr('chronicle.app.format_duration',original)
    app.refresh();settled(app)
    assert app.tree.parent(app.task_row(c))==app.task_row(b)
