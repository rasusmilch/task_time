"""Real Tk/worker Delete preview, confirmation, uncertainty and operator input."""
from copy import deepcopy
from threading import Event

import pytest

from chronicle.records import Outcome, Request
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.worker import Message
from conftest import uid
from test_app import root, connected, click, keyboard, pump, evidence
from test_main_explorer import project, task, select, submit, settled
from test_archived_items import archive, child, window, choose
from test_timesheet_save_ui import exit_settled


def opened(app,row=None,origin=None):
    if row is not None:select(app,row)
    assert app.open_delete(_archived_origin=origin)
    dialog=app.deletion
    pump(app.root,lambda:dialog.phase in ('ready','blocked','failed'))
    assert dialog.presented and app.root.grab_current() is dialog.window
    return dialog


def authorize(dialog):
    dialog.confirmed.set('DELETE');dialog.controls();return dialog.submit()


@pytest.mark.parametrize('entity',['project','task','archived_task','inherited_task'])
def test_real_tk_actual_delete_preview_scope_and_successful_authoritative_refresh(connected,entity):
    app,worker,clock=connected;p=project(app);a=task(app,group=p);b=child(app,a,p);c=child(app,b,p)
    origin=None
    if entity in ('archived_task','inherited_task'):
        archive(app,'task',a);origin=window(app)
        choose(origin,app.task_row(a if entity=='archived_task' else b))
        dialog=opened(app,origin=origin)
    else:dialog=opened(app,app.project_row(p) if entity=='project' else app.task_row(a))
    expected=3 if entity!='inherited_task' else 2
    assert dialog.review['task_count']==expected
    assert len(dialog.tree.get_children())==1 and len(dialog.review['tasks'])==expected
    assert dialog.key in dialog.context.cget('text')
    assert 'Tasks: '+str(expected) in dialog.context.cget('text')
    assert not app.can_mutate() and not app.start() and not app.open_backup() and not app.open_mini()
    assert not app.open_delete() and dialog.delete_button.instate(['disabled'])
    before=evidence(worker);assert authorize(dialog)
    accepted=app.pending;assert accepted.args()['review']==dialog.review
    assert app.executing
    if origin is not None:assert origin.tree.exists(app.task_row(dialog.key))
    else:assert app.tree.exists(app.project_row(dialog.key) if entity=='project' else app.task_row(dialog.key))
    pump(app.root,lambda:not app.executing)
    assert app._mutation_outcome.status=='committed' and app.pending is None
    settled(app);assert dialog.phase=='complete'
    if entity in ('project','task'):assert not app.tree.exists(app.task_row(a))
    if origin is not None:
        for t in dialog.review['tasks']:assert not origin.tree.exists(app.task_row(t['task_id']))
    assert dialog.close() and app.deletion is None and app.editor is None
    assert not app.root.test_errors


@pytest.mark.parametrize('text',['','delete',' DELETE','DELETE '])
def test_real_tk_cancel_wrong_typed_confirmation_no_write(connected,text):
    app,worker,clock=connected;a=task(app);before=evidence(worker)
    dialog=opened(app,app.task_row(a));dialog.confirmed.set(text);dialog.controls()
    assert dialog.delete_button.instate(['disabled']) and not dialog.submit()
    assert evidence(worker)==before
    assert dialog.close() and app.pending is None and not app.root.test_errors


def test_real_tk_protected_refusal_and_new_preview_required_for_stale_review(connected,monkeypatch):
    app,worker,clock=connected;a=task(app)
    dialog=opened(app,app.task_row(a));before=deepcopy(dialog.review)
    # A real accepted change raced after the frozen worker preview, on that same worker.
    request=Request.make(uid(),app.dataset_id,'rename_task',before['selected']['created_utc_us'],task_id=a,name='Changed',expected_version=1)
    done=Event();original=TimerService.execute
    def raced(self,r):
        value=original(self,r)
        if r.request_id==request.request_id:done.set()
        return value
    monkeypatch.setattr(TimerService,'execute',raced)
    worker.requests.put(Message('mutate',991,request));pump(app.root,done.is_set)
    # Owner rejects the unrelated mutation delivery; final Delete still checks actual state.
    assert authorize(dialog);pump(app.root,lambda:not app.executing)
    assert app._mutation_outcome.status=='rejected' and dialog.phase=='failed' and app.pending is None
    assert not dialog.submit() and dialog.review==before
    assert dialog.refresh();pump(app.root,lambda:dialog.phase=='ready')
    assert dialog.review['selected']['name']=='Changed' and dialog.confirmed.get()==''
    dialog.close();settled(app)
    submit(app,'add_date_only_work',task_id=a,entry_id=uid(),work_date='2026-10-19',duration_text='0:01',comment='protected')
    frozen=evidence(worker);dialog=opened(app,app.task_row(a))
    assert dialog.phase=='blocked' and 'Archive' in dialog.status.cget('text') and dialog.delete_button.instate(['disabled'])
    assert not authorize(dialog) and evidence(worker)==frozen
    assert dialog.close()


def test_real_tk_pending_and_destroyed_windows_keep_accepted_delete_identity(connected,monkeypatch):
    app,worker,clock=connected;a=task(app);archive(app,'task',a);view=window(app);choose(view,app.task_row(a))
    dialog=opened(app,origin=view);entered,release=Event(),Event();original=SQLiteStore.delete_unused
    def slow(self,r):entered.set();assert release.wait(6);return original(self,r)
    monkeypatch.setattr(SQLiteStore,'delete_unused',slow)
    try:
        assert authorize(dialog);pump(app.root,entered.is_set);accepted=app.pending
        assert not dialog.close() and not dialog.submit() and not view.delete()
        view.window.destroy();dialog.window.destroy()
        assert app.pending is accepted and app.deletion is None and app.archived is None
        assert not dialog.submit() and not view.delete()
    finally:release.set()
    settled(app);assert app.pending is None and app._mutation_outcome.status=='committed'
    assert not app.tree.exists(app.task_row(a)) and not app.root.test_errors


@pytest.mark.parametrize('committed',[False,True])
def test_real_tk_uncertain_delete_never_retries_presence_not_historical_success(connected,monkeypatch,committed):
    app,worker,clock=connected;a=task(app);dialog=opened(app,app.task_row(a));original=SQLiteStore.delete_unused
    calls=[]
    def uncertain(self,r):
        calls.append(r)
        if committed:assert original(self,r).status=='committed'
        return Outcome('unverified',error=OSError('acknowledgement unavailable'))
    monkeypatch.setattr(SQLiteStore,'delete_unused',uncertain)
    assert authorize(dialog);pump(app.root,lambda:not app.executing)
    accepted=app.pending;assert accepted and dialog.phase=='unverified'
    assert not app.retry() and not dialog.submit() and not dialog.refresh() and not dialog.close()
    assert not app.start() and not app.open_backup() and not app.open_delete()
    assert not app.retry_button.winfo_manager() and app.delete_inspect_button.winfo_manager()
    assert app.inspect_delete_state();pump(app.root,lambda:app._delete_inspection_token is None)
    assert app.pending is accepted and len(calls)==1
    assert ('ABSENT' if committed else 'PRESENT') in dialog.status.cget('text')
    assert 'not historical proof' in dialog.status.cget('text') and app._mutation_outcome.status=='unverified'
    prompts=[]
    def cancel(*a,**k):prompts.append((a,k));return False
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',cancel)
    assert not app.exit_delete_uncertain() and app.pending is accepted
    assert prompts[0][1]['parent'] is dialog.window and prompts[0][1]['default']=='no'
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**k:True)
    assert app.exit_delete_uncertain();exit_settled(app);worker.join(8);assert not worker.is_alive()
    # Ordinary fresh reopen validates current facts but cannot reconstruct Delete's historical result.
    s=SQLiteStore(worker.directory)
    try:
        s._verify_complete(s.connection)
        assert bool(s.connection.execute('SELECT 1 FROM tasks WHERE task_id=?',(a,)).fetchone())!=committed
    finally:s.close()


@pytest.mark.parametrize('modal',['history','timesheet','backup','correction'])
def test_real_tk_delete_cannot_bypass_an_existing_owned_modal(connected,modal):
    app,worker,clock=connected;a=task(app);select(app,app.task_row(a))
    view=window(app)
    if modal=='history':assert app.open_history();pump(app.root,lambda:app.history.current)
    elif modal=='timesheet':assert app.open_timesheet();pump(app.root,lambda:app.timesheet.presented)
    elif modal=='backup':assert app.open_backup();pump(app.root,lambda:app.backup_dialog.presented)
    else:submit(app,'start_timer',task_id=a,entry_id=uid(),expected_task_version=1);app.correct_active_start();pump(app.root,lambda:app.root.grab_current() is app.editor)
    grab,focus=app.root.grab_current(),app.root.focus_get();before=evidence(worker)
    assert not app.open_delete() and not view.delete() and app.deletion is None
    assert app.root.grab_current() is grab and app.root.focus_get() is focus and evidence(worker)==before
    if modal=='history':app.history.close()
    elif modal=='timesheet':app.timesheet.close()
    elif modal=='backup':app.backup_dialog.close()
    else:app._close_editor(app.editor)


@pytest.mark.parametrize('where',['dialog','main'])
def test_real_tk_preview_closed_late_delivery_and_committed_presentation_error(connected,monkeypatch,where):
    app,worker,clock=connected;a=task(app);dialog=opened(app,app.task_row(a));old=dialog.preview_token;frozen=deepcopy(dialog.review)
    dialog.close();assert not dialog.submit()
    app._handle(Message('delete_preview',old,frozen));assert app.deletion is None
    dialog=opened(app,app.task_row(a));status=dialog.status if where=='dialog' else app.status;original=status.configure
    def fail(**kwargs):
        if kwargs.get('text','').startswith('Deleted'):raise RuntimeError('Delete presentation failure')
        return original(**kwargs)
    monkeypatch.setattr(status,'configure',fail)
    assert authorize(dialog);settled(app)
    assert app.pending is None and app._mutation_outcome.status=='committed' and dialog.phase=='complete'
    assert not app.tree.exists(app.task_row(a)) and any('presentation' in str(e[1]) for e in app.root.test_errors)
    assert 'Deleted' in (app.status if where=='dialog' else dialog.status).cget('text')
    dialog.close()


def test_real_tk_server_main_and_archived_delete_with_typed_confirmation(connected,click,keyboard):
    app,worker,clock=connected;a=task(app);select(app,app.task_row(a))
    click(app.buttons['Delete']);pump(app.root,lambda:app.deletion is not None and app.deletion.phase=='ready')
    dialog=app.deletion;before=evidence(worker)
    click(dialog.close_button);assert app.deletion is None and evidence(worker)==before
    archive(app,'task',a);view=window(app);view.tree.see(app.task_row(a));pump(app.root,lambda:bool(view.tree.bbox(app.task_row(a))))
    x,y,w,h=view.tree.bbox(app.task_row(a));click(view.tree,(x+45,y+h//2));pump(app.root,lambda:view.selected() is not None)
    click(view.delete_button);pump(app.root,lambda:app.deletion is not None and app.deletion.phase=='ready')
    dialog=app.deletion;click(dialog.entry);pump(app.root,lambda:app.root.focus_get() is dialog.entry)
    # Uppercase input through actual XTest keys, not StringVar assignment.
    for char in 'delete':keyboard[0](char,shift=True)
    pump(app.root,lambda:dialog.entry.get()=='DELETE' and not dialog.delete_button.instate(['disabled']))
    click(dialog.delete_button);pump(app.root,lambda:dialog.phase=='complete');settled(app)
    assert not view.tree.exists(app.task_row(a)) and not app.tree.exists(app.task_row(a))
    click(dialog.close_button);assert app.deletion is None
    assert not app.root.test_errors


def test_real_tk_worker_stop_before_delete_delivery_retains_uncertainty_and_exit(connected,monkeypatch):
    app,worker,clock=connected;a=task(app);dialog=opened(app,app.task_row(a))
    # Accepted request stays with the owner even if the worker cannot deliver it.
    original=worker.requests.put;queued=[]
    def intercept(message):
        if message.kind=='mutate':queued.append(message)
        else:original(message)
    monkeypatch.setattr(worker.requests,'put',intercept)
    assert authorize(dialog);accepted=app.pending
    original(Message('shutdown'));worker.join(8);assert not worker.is_alive()
    pump(app.root,lambda:app._worker_stopped)
    assert app.pending is accepted and dialog.phase=='unverified'
    assert not app.retry() and not app.inspect_delete_state() and not dialog.close()
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**k:True)
    assert app.exit_delete_uncertain();assert not app.alive


def test_real_tk_no_selection_or_virtual_group_has_no_delete(connected):
    app,worker,clock=connected;task(app);before=evidence(worker)
    for row in (None,app.project_row(None)):
        if row is None:app.tree.selection_remove(app.tree.selection());app._controls()
        else:select(app,row)
        assert app.buttons['Delete'].instate(['disabled']) and not app.open_delete()
    assert evidence(worker)==before and app.deletion is None
