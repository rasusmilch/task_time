"""Actual Tk/worker archived navigation, with separate server-input evidence."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from threading import Event
from types import SimpleNamespace

import pytest

from chronicle.archived_window import SORTS, projection
from chronicle.records import Outcome, Request
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import to_us
from chronicle.worker import Message
from conftest import NOW, uid
from test_app import root, connected, click, keyboard, pump, evidence
from test_main_explorer import project, task, select, submit, settled
from test_timesheet_save_ui import exit_settled
from test_chronicle_history_operator import native_confirmation


def child(app, parent, group=None, name='Same'):
    key=uid();row=next(t for t in app.state['tasks'] if t['task_id']==parent)
    submit(app,'create_task',task_id=key,name=name,project_id=group,parent_task_id=parent,expected_parent_version=row['version'])
    return key


def archive(app, entity, key):
    row=next(t for t in app.state[entity+'s'] if t[entity+'_id']==key)
    submit(app,'archive_'+entity,**{entity+'_id':key,'expected_version':row['version']})


def window(app):
    assert app.open_archived();settled(app)
    view=app.archived;pump(app.root,lambda:view.window.winfo_ismapped())
    return view


def choose(view, row):
    view.tree.selection_set(row);view.controls()


def test_real_tk_archived_project_three_levels_context_duplicates_and_empty(connected):
    app,worker,clock=connected
    p=project(app,'Same');empty=project(app,'Empty');a=task(app,'Same',p)
    b=child(app,a,p);c=child(app,b,p);other=task(app,'Same');nested=child(app,other)
    archive(app,'task',b);archive(app,'project',p);archive(app,'project',empty);archive(app,'task',nested)
    view=window(app)
    assert not app.open_archived() and app.root.grab_current() is None
    assert set(view.tree.get_children())=={app.project_row(p),app.project_row(empty),app.task_row(nested)}
    assert view.tree.parent(app.task_row(a))==app.project_row(p)
    assert view.tree.parent(app.task_row(b))==app.task_row(a)
    assert view.tree.parent(app.task_row(c))==app.task_row(b)
    assert len(view.rows)==6 and all(view.tree.exists(k) for k in view.rows)
    assert 'Unassigned → Same' in view.tree.item(app.task_row(nested),'text')
    assert view.tree.get_children(app.project_row(empty))==()
    assert not app.tree.exists(app.project_row(p)) and not app.tree.exists(app.task_row(nested))
    choose(view,app.task_row(c))
    assert view.unarchive_button.instate(['disabled']) and not view.unarchive()
    assert 'Same' in view.status.cget('text') and 'ancestor' in view.status.cget('text')
    assert b in view.status.cget('text')  # Duplicate names cannot obscure the hiding identity.
    assert all('Delete' not in str(w.cget('text')) for w in (view.unarchive_button,view.history_button,view.close_button))
    assert not app.root.test_errors


@pytest.mark.parametrize('order',SORTS)
def test_real_tk_sibling_sort_and_selection_expansion_retained_without_row_churn(connected,monkeypatch,order):
    app,worker,clock=connected;p=project(app);a=task(app,'z',p);b=task(app,'A',p);c=task(app,'A',p)
    archive(app,'project',p);view=window(app)
    view.tree.item(app.project_row(p),open=True);choose(view,app.task_row(c))
    view.sort.set(order);view.changed();view.period.set('This Week');view.changed()
    assert view.tree.item(app.project_row(p),'open') and view.tree.selection()==(app.task_row(c),)
    expected=sorted([a,b,c])
    names={a:'z',b:'A',c:'A'}
    if order in SORTS[:2]: expected.sort(key=lambda k:names[k].casefold(),reverse=order==SORTS[1])
    assert view.tree.get_children(app.project_row(p))==tuple(app.task_row(k) for k in expected)
    writes=[]
    for name in ('insert','delete','move','item'):
        original=getattr(view.tree,name)
        def observed(*args,_name=name,_original=original,**kwargs):
            if _name!='item' or kwargs:writes.append((_name,args,kwargs))
            return _original(*args,**kwargs)
        monkeypatch.setattr(view.tree,name,observed)
    before=evidence(worker);app.refresh();settled(app)
    assert writes==[] and evidence(worker)==before
    assert view.tree.item(app.project_row(p),'open') and view.tree.selection()==(app.task_row(c),)


def test_real_tk_selected_only_unarchive_sync_history_and_unavailable_amounts(connected):
    app,worker,clock=connected;p=project(app);a=task(app,group=p)
    submit(app,'add_date_only_work',task_id=a,entry_id=uid(),work_date='2026-10-19',duration_text='0:20',comment='parent')
    b=child(app,a,p)
    submit(app,'add_date_only_work',task_id=b,entry_id=uid(),work_date='2026-10-19',duration_text='0:10',comment='child')
    archive(app,'task',b);archive(app,'project',p);view=window(app)
    assert view.tree.item(app.task_row(a),'values')[1:]==('00:20','00:30')
    assert view.tree.item(app.project_row(p),'values')[1:]==('—','00:30')
    before=evidence(worker)
    choose(view,app.task_row(a));assert view.history();pump(app.root,lambda:app.history is not None and app.history.current)
    history=app.history;assert history.task['task_id']==a and {r['task_id'] for r in history.rows}=={a}
    assert app.root.grab_current() is history.window and view.unarchive_button.instate(['disabled'])
    assert not view.unarchive() and not view.close() and not app.open_mini()
    assert evidence(worker)==before
    history.close();pump(app.root,lambda:app.history is None)
    failed=deepcopy(app.state);failed['report']=None;failed['calculation_error']='test calculation failure'
    view.render(failed);assert view.tree.item(app.task_row(a),'values')[1:]==('—','—')
    assert 'unavailable' in view.status.cget('text')
    view.render(app.state)
    choose(view,app.project_row(p));assert view.unarchive();settled(app)
    assert app.tree.exists(app.task_row(a)) and not app.tree.exists(app.task_row(b))
    assert set(view.rows)=={app.task_row(b)} and view.tree.parent(app.task_row(b))==''
    assert 'Project' in view.tree.item(app.task_row(b),'text')
    final=evidence(worker)
    for table in ('work_entries','work_revisions','active_timer'):assert final[table]==before[table]
    assert app.headline.cget('text')=='Today: 00:30    This week: 00:30'
    view.close();assert app.archived is None and not view.unarchive() and not view.history()
    assert not app.root.test_errors


def test_real_tk_archive_confirmation_cancel_active_guard_and_service_completion(connected,monkeypatch):
    app,worker,clock=connected;p=project(app);a=task(app,group=p);b=child(app,a,p)
    prompts=[]
    def confirm(*args,**kwargs):
        prompts.append((args,kwargs));assert app.executing and not app.can_mutate();return False
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',confirm)
    select(app,app.project_row(p));before=evidence(worker);assert not app.archive_selected()
    assert evidence(worker)==before and '2' in prompts[0][0][1] and prompts[0][1]['default']=='no'
    submit(app,'start_timer',task_id=b,entry_id=uid(),expected_task_version=1)
    select(app,app.project_row(p));assert app.buttons['Archive'].instate(['disabled']) and not app.archive_selected()
    select(app,app.task_row(a));assert app.buttons['Archive'].instate(['disabled'])
    before=evidence(worker);assert len(prompts)==1
    assert not app.archive_selected() and evidence(worker)==before
    clock.value += timedelta(minutes=1)
    submit(app,'stop_timer',entry_id=app.state['active']['entry_id'],expected_version=1)
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**k:True)
    assert app.archive_selected();assert app.tree.exists(app.task_row(a))  # No optimistic hiding.
    settled(app);assert not app.tree.exists(app.task_row(a))
    select(app,app.project_row(None));assert app.buttons['Archive'].instate(['disabled']) and not app.archive_selected()


def test_real_tk_pending_unarchive_window_destroy_preserves_accepted_request(connected,monkeypatch):
    app,worker,clock=connected;a=task(app);archive(app,'task',a);view=window(app);choose(view,app.task_row(a))
    entered,release=Event(),Event();original=TimerService.execute
    def blocked(self,r):
        if r.operation=='unarchive_task':entered.set();assert release.wait(6)
        return original(self,r)
    monkeypatch.setattr(TimerService,'execute',blocked)
    try:
        assert view.unarchive();pump(app.root,entered.is_set);accepted=app.pending
        assert accepted.operation=='unarchive_task' and view.unarchive_button.instate(['disabled'])
        assert view.close() and app.archived is None and app.pending is accepted
        assert not view.unarchive()
    finally:release.set()
    settled(app);assert app.tree.exists(app.task_row(a)) and app.pending is None
    assert not app.root.test_errors


def test_real_tk_lost_ack_reconcile_stale_result_and_stale_review(connected,monkeypatch):
    app,worker,clock=connected;a=task(app);archive(app,'task',a);view=window(app);choose(view,app.task_row(a))
    original=SQLiteStore._probe
    def unavailable(self):raise OSError('receipt probe unavailable')
    execute=TimerService.execute
    def lost(self,r):
        if r.operation!='unarchive_task':return execute(self,r)
        real=self.store.connection
        class Commit:
            def __getattr__(self,n):return getattr(real,n)
            def execute(self,sql,*args):
                result=real.execute(sql,*args)
                if sql=='COMMIT':raise OSError('lost commit acknowledgement')
                return result
        self.store.connection=Commit();return execute(self,r)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'execute',lost);m.setattr(SQLiteStore,'_probe',unavailable)
        assert view.unarchive();pump(app.root,lambda:not app.executing)
    accepted=app.pending;assert accepted and app._mutation_outcome.status=='unverified'
    assert not view.unarchive() and not app.can_mutate()
    assert app.retry();settled(app);assert app.tree.exists(app.task_row(a))
    before=evidence(worker)
    app._handle(Message('mutate',999,Outcome('committed',{'task_id':a,'version':99}),accepted))
    assert evidence(worker)==before and app.pending is None
    # A detached review cannot submit against a different/closed owner.
    view.window.destroy();assert not view.unarchive() and app.archived is None


def test_real_tk_sort_dates_use_utc_across_repeated_local_hour(connected):
    app,worker,clock=connected;a=task(app,'Later');b=task(app,'Earlier')
    first=to_us(datetime(2026,11,1,6,50,tzinfo=timezone.utc));second=to_us(datetime(2026,11,1,7,10,tzinfo=timezone.utc))
    clock.value=datetime(2026,11,1,6,50,tzinfo=timezone.utc);archive(app,'task',b)
    clock.value=datetime(2026,11,1,7,10,tzinfo=timezone.utc);archive(app,'task',a)
    view=window(app)
    assert view.tree.get_children()==(app.task_row(a),app.task_row(b))
    assert '01:10' in view.tree.item(app.task_row(a),'values')[0] and '-0600' in view.tree.item(app.task_row(a),'values')[0]
    assert '01:50' in view.tree.item(app.task_row(b),'values')[0] and '-0500' in view.tree.item(app.task_row(b),'values')[0]
    view.sort.set(SORTS[3]);view.changed();assert view.tree.get_children()==(app.task_row(b),app.task_row(a))


def test_real_tk_server_archive_cancel_confirm_and_unarchive(connected,click,keyboard):
    app,worker,clock=connected;p=project(app);a=task(app,group=p)
    select(app,app.task_row(a));before=evidence(worker)
    # Actual toolkit confirmation and server mouse input; no automatic generic dialog response.
    native_confirmation(app.root,SimpleNamespace(window=app.root),click,keyboard,app.buttons['Archive'],False)
    settled(app);assert evidence(worker)==before
    native_confirmation(app.root,SimpleNamespace(window=app.root),click,keyboard,app.buttons['Archive'],True)
    settled(app);assert not app.tree.exists(app.task_row(a))
    click(app.buttons['Archived Items']);pump(app.root,lambda:app.archived is not None)
    view=app.archived;pump(app.root,lambda:view.window.winfo_ismapped())
    view.tree.see(app.task_row(a));pump(app.root,lambda:bool(view.tree.bbox(app.task_row(a))))
    x,y,w,h=view.tree.bbox(app.task_row(a));click(view.tree,(x+50,y+h//2))
    pump(app.root,lambda:view.tree.selection()==(app.task_row(a),))
    click(view.unarchive_button);settled(app);assert app.tree.exists(app.task_row(a)) and not view.rows
    click(view.close_button);assert app.archived is None and not app.root.test_errors


@pytest.mark.parametrize('modal',['history','timesheet','backup','correction'])
def test_real_tk_archived_management_respects_every_existing_owned_modal(connected,modal):
    app,worker,clock=connected;a=task(app);hidden=task(app)
    archive(app,'task',hidden);view=window(app);choose(view,app.task_row(hidden))
    select(app,app.task_row(a));app.open_mini();assert app.mini is not None
    if modal=='history':
        assert app.open_history();pump(app.root,lambda:app.history.current);owned=app.history.window
    elif modal=='timesheet':
        assert app.open_timesheet();pump(app.root,lambda:app.timesheet.presented);owned=app.timesheet.window
    elif modal=='backup':
        assert app.open_backup();pump(app.root,lambda:app.backup_dialog.presented);owned=app.backup_dialog.window
    else:
        submit(app,'start_timer',task_id=a,entry_id=uid(),expected_task_version=1)
        app.correct_active_start();pump(app.root,lambda:app.editor is not None and app.root.grab_current() is app.editor);owned=app.editor
    focus=app.root.focus_get();assert app.root.grab_current() is owned
    before=evidence(worker)
    assert not view.unarchive() and not view.history() and not view.close() and not app.open_archived()
    assert not app.archive_selected() and not app.show_main() and not app.open_mini()
    assert view.unarchive_button.instate(['disabled']) and view.history_button.instate(['disabled'])
    assert app.root.grab_current() is owned and app.root.focus_get() is focus and evidence(worker)==before
    if modal=='history':app.history.close()
    elif modal=='timesheet':app.timesheet.close()
    elif modal=='backup':app.backup_dialog.close()
    else:app._close_editor(owned)
    pump(app.root,lambda:app.root.grab_current() is None)
    assert view.current() and not app.root.test_errors


def test_real_tk_stale_unarchive_review_refreshes_without_optimistic_changes(connected):
    app,worker,clock=connected;a=task(app);archive(app,'task',a);view=window(app);choose(view,app.task_row(a))
    stale=deepcopy(app.state)
    submit(app,'rename_task',task_id=a,name='Later name',expected_version=2)
    view.render(stale);assert view.unarchive()
    settled(app)
    assert app._mutation_outcome.status=='rejected' and app.pending is None
    assert not app.tree.exists(app.task_row(a)) and view.tree.exists(app.task_row(a))
    assert view.rows[app.task_row(a)]['item']['version']==3
    assert not app.root.test_errors or all(isinstance(e[1],ValueError) for e in app.root.test_errors)


def test_real_tk_unarchive_child_under_archived_parent_keeps_it_hidden(connected):
    app,worker,clock=connected;p=project(app);a=task(app,group=p);b=child(app,a,p)
    archive(app,'task',b);archive(app,'project',p);view=window(app)
    choose(view,app.task_row(b));assert view.unarchive();settled(app)
    assert view.tree.exists(app.task_row(b)) and not app.tree.exists(app.task_row(b))
    assert view.unarchive_button.instate(['disabled'])
    row=view.rows[app.task_row(b)];assert not row['item']['is_archived'] and row['source']['project_id']==p
    assert 'ancestor' in view.status.cget('text')
    choose(view,app.project_row(p));assert view.unarchive();settled(app)
    assert view.rows=={} and app.tree.exists(app.task_row(b))


def test_real_tk_archive_presentation_failure_does_not_undo_commit(connected,monkeypatch):
    app,worker,clock=connected;a=task(app);view=window(app)
    original=app.status.configure
    def fail(**kw):
        if kw.get('text')=='Saved.':raise RuntimeError('known committed presentation failure')
        return original(**kw)
    monkeypatch.setattr(app.status,'configure',fail)
    submit(app,'archive_task',task_id=a,expected_version=1)
    assert app.pending is None and app._mutation_outcome.status=='committed'
    assert not app.tree.exists(app.task_row(a)) and view.tree.exists(app.task_row(a))
    assert app.root.test_errors and any('presentation' in str(e[1]) for e in app.root.test_errors)


def test_real_tk_nearest_archive_time_precedence_and_full_expansion_across_refresh(connected):
    app,worker,clock=connected;p=project(app);a=task(app,group=p);b=child(app,a,p);c=child(app,b,p)
    archive(app,'task',b);b_time=to_us(clock.value)
    clock.value+=timedelta(minutes=1);archive(app,'task',a);a_time=to_us(clock.value)
    clock.value+=timedelta(minutes=1);archive(app,'project',p);p_time=to_us(clock.value)
    view=window(app)
    assert view.rows[app.task_row(b)]['stamp']==view.rows[app.task_row(c)]['stamp']==b_time
    assert view.rows[app.task_row(a)]['stamp']==a_time and view.rows[app.project_row(p)]['stamp']==p_time
    for row in (app.project_row(p),app.task_row(a),app.task_row(b)):view.tree.item(row,open=True)
    choose(view,app.task_row(c));project(app,'Unrelated')
    view.sort.set(SORTS[0]);view.changed();view.period.set('This Week');view.changed()
    assert all(view.tree.item(row,'open') for row in (app.project_row(p),app.task_row(a),app.task_row(b)))
    assert view.tree.selection()==(app.task_row(c),)
    choose(view,app.task_row(b));assert view.unarchive();settled(app)
    assert view.rows[app.task_row(c)]['stamp']==a_time
    choose(view,app.task_row(a));assert view.unarchive();settled(app)
    assert all(view.rows[app.task_row(key)]['stamp']==p_time for key in (a,b,c))
    assert view.tree.parent(app.task_row(c))==app.task_row(b)


def test_real_tk_modeless_close_reopen_and_ordinary_shutdown_no_orphan(connected):
    app,worker,clock=connected;a=task(app);archive(app,'task',a);view=window(app)
    view.window.destroy();assert app.archived is None and not view.current()
    fresh=window(app);assert fresh is not view and fresh.tree.exists(app.task_row(a))
    app.request_close();exit_settled(app)
    worker.join(8);assert not worker.is_alive() and fresh.disposed and app.archived is None
    assert not app.root.test_errors


@pytest.mark.parametrize('shared_uuid',[False,True])
def test_mixed_archived_top_level_ties_use_uuid_before_row_type(store,service,shared_uuid):
    from conftest import archive as archive_entity
    p='ffffffff-ffff-4fff-8fff-ffffffffffff'
    t=p if shared_uuid else '00000000-0000-4000-8000-000000000001'
    assert service.create_project(p,'Same',request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.create_task(t,'Same',request_id=uid(),action_utc_us=NOW).status=='committed'
    archive_entity(service,'project',p);archive_entity(service,'task',t)
    state=service.read_current_state(cutoff_utc_us=NOW)
    for order in SORTS:
        rows,children=projection(state,order,'Today',store.zone)
        assert len(rows)==2
        expected=sorted(['project:'+p,'task:'+t],key=lambda key:(key.split(':',1)[1],key))
        assert children['']==expected
