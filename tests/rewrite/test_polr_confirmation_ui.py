"""Actual owner/worker/SQLite confirmation paths; direct callbacks isolate failures."""
from copy import deepcopy
from datetime import timedelta
import gc
import threading
import tkinter as tk

import pytest

from chronicle.app import ChronicleApp
from chronicle.records import Outcome,Request,StaleState
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.worker import DatabaseWorker,Message
from conftest import NOW,uid
from test_app import root,connected,pump,create,evidence,click,keyboard
from test_chronicle_history_ui import mutation,selected_task
from test_chronicle_timesheet_ui import open_sheet,refresh
from test_timesheet_save_ui import choose,settled,saved_reports,exit_settled
from test_services import FaultConnection
from test_polr_confirmation import manual,source_args,submit,DAY


def reviewed(app,sheet):
    pump(app.root,lambda: not sheet.polr_tokens and not app.executing and app.pending is None and app._read_inflight is None)


def saved(app,tmp_path,monkeypatch,*,duration='3:00',tuesday_duration=None):
    task=app.selected_task_id() or selected_task(app)
    mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date=DAY,duration_text=duration,comment='original')
    if tuesday_duration is not None:mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date='2026-10-20',duration_text=tuesday_duration,comment='worked zero-suggestion day')
    sheet=open_sheet(app);c=refresh(app,sheet);dest=tmp_path/'report.txt';choose(monkeypatch,sheet,str(dest))
    assert sheet.save();settled(app);return task,sheet,c,dest


def manual_review(app,sheet,task,day=DAY):
    assert sheet.manual_polr()
    sheet.polr_task_control.current(sheet.polr_task_choices.index(task));sheet.polr_date.set(day)
    assert sheet.refresh_polr();reviewed(app,sheet)
    assert sheet.polr_ready


def test_real_tk_source_subset_manual_history_exact_frozen_work_and_restart(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);other=create(app,'Other')
    mutation(app,'add_timed_work',task_id=other,entry_id=uid(),start_date=DAY,start_time='9am',end_date=DAY,end_time='9:15am',start_occurrence=None,end_occurrence=None,comment='genuine timed')
    app.tree.selection_set(app.task_row(other));assert app.start();pump(root,lambda:app.pending is None and app.state['active'] is not None)
    active=deepcopy(app.state['active']);app.tree.selection_set(app.task_row(task))
    task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    sheet.close();mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date=DAY,duration_text='2:00',comment='later')
    sheet=open_sheet(app);saved_reports(app,sheet,c.export_id);before=evidence(worker)
    assert sheet.review_polr();reviewed(app,sheet)
    assert sheet.polr_selected=={(task,DAY),(other,DAY)}
    assert sheet.toggle_polr_cell((other,DAY))
    assert len(sheet.polr_mapping)==14 and sheet.polr_tree.cget('show')
    assert sheet.confirm_polr();request=app.pending
    assert request.operation=='confirm_polr_absolute' and not sheet.confirm_polr() and not sheet.defer_polr() and not sheet.close()
    reviewed(app,sheet);batch=app._polr_submission.outcome.result['batch_id']
    assert app._polr_submission.request is request and 'Committed confirmation' in sheet.polr_status.cget('text')
    assert 'Daily Delta: +2.00' in sheet.polr_detail.get('1.0','end')
    assert evidence(worker)['work_revisions']==before['work_revisions'] and app.state['active']==active and dest.read_bytes()==c.report_utf8
    manual_review(app,sheet,task);sheet.polr_hours.set('5.00');assert sheet.confirm_polr();reviewed(app,sheet)
    assert 'Daily Delta: 0.00' in sheet.polr_detail.get('1.0','end')
    assert sheet.confirmation_history();reviewed(app,sheet)
    assert len(sheet.polr_tree.get_children())==2
    sheet.polr_tree.selection_set(batch);assert sheet.load_polr_batch();reviewed(app,sheet)
    assert '3.00' in sheet.polr_detail.get('1.0','end') and str(sheet.polr_detail.cget('state'))=='disabled'
    sheet.close();moved=dest.with_name('moved-report.txt');dest.rename(moved)
    directory=worker.directory;root.destroy();worker.join(timeout=8);assert not worker.is_alive()
    other_root=tk.Tk();other_root.test_errors=[];other_root.report_callback_exception=lambda *a:other_root.test_errors.append(a)
    other_worker=DatabaseWorker(directory);other_app=ChronicleApp(other_root,other_worker,now_utc=clock);other_worker.start()
    try:
        pump(other_root,lambda:other_app.ready and other_app.state.get('report') is not None)
        fresh=open_sheet(other_app);saved_reports(other_app,fresh,c.export_id)
        assert fresh.review_polr();reviewed(other_app,fresh)
        r=next(r for r in fresh.polr_mapping.values() if (r['task_id'],r['work_date'])==(task,DAY))
        assert r['suggested_quarters']==12 and r['prior_quarters']==20 and r['requires_stale_acknowledgement']
        assert not fresh.polr_acks[(task,DAY)][0].get()
        assert not dest.exists() and moved.read_bytes()==c.report_utf8 # Missing preferred copy does not invalidate source review.
        manual_review(other_app,fresh,task);assert fresh.polr_context['confirmed_quarters']==20
        fresh.polr_hours.set('5.25');assert fresh.confirm_polr();reviewed(other_app,fresh)
        assert fresh.polr_context['confirmed_quarters']==21
        assert other_app.state['active']==active and moved.read_bytes()==c.report_utf8 and not other_root.test_errors
    finally:
        if other_app.alive:other_root.destroy()
        other_worker.join(timeout=8);assert not other_worker.is_alive();gc.collect()


def test_real_tk_case_F_zero_default_defer_and_manual_invalid_draft(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch,duration='0:03',tuesday_duration='0:03')
    before=evidence(worker);assert sheet.review_polr();reviewed(app,sheet)
    assert sheet.polr_selected=={(task,DAY)}
    assert sheet.defer_polr() and evidence(worker)==before
    assert sheet.review_polr();reviewed(app,sheet)
    assert sheet.toggle_polr_cell((task,DAY));assert not sheet.confirm_polr() and evidence(worker)==before
    assert sheet.toggle_polr_cell((task,'2026-10-20'));assert sheet.confirm_polr();reviewed(app,sheet)
    manual_review(app,sheet,task,'2026-10-20')
    assert sheet.polr_context['confirmed_quarters']==0 and '0.00 (confirmed)' in sheet.polr_detail.get('1.0','end')
    before=evidence(worker);sheet.polr_hours.set('2.30');assert not sheet.confirm_polr()
    assert sheet.polr_hours.get()=='2.30' and sheet.polr_ready and evidence(worker)==before
    sheet.polr_hours.set('2.50');assert sheet.confirm_polr();reviewed(app,sheet)
    assert sheet.polr_context['confirmed_quarters']==10


@pytest.mark.parametrize('same',[False,True])
def test_real_tk_stale_selected_prior_requires_explicit_refresh_no_retarget(connected,root,tmp_path,monkeypatch,same):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    manual_review(app,sheet,task);sheet.polr_hours.set('0.00');assert sheet.confirm_polr();reviewed(app,sheet)
    reviewed_id=sheet.polr_context['current_batch_id'];sheet.polr_hours.set('4.00')
    original=TimerService.execute;injected=[]
    def advance(self,r):
        if r.operation=='confirm_polr_absolute' and not injected:
            injected.append(True);a=manual(self,task,0 if same else 8)
            assert original(self,Request.make(uid(),r.dataset_id,r.operation,NOW,**a)).status=='committed'
        return original(self,r)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'execute',advance);assert sheet.confirm_polr();reviewed(app,sheet)
    assert app._polr_submission.outcome.status=='rejected' and isinstance(app._polr_submission.outcome.error,StaleState)
    assert sheet.polr_stale and sheet.polr_context['current_batch_id']==reviewed_id and not sheet.confirm_polr()
    assert sheet.refresh_polr();reviewed(app,sheet);assert sheet.polr_context['current_batch_id'] is not None
    assert sheet.confirm_polr();reviewed(app,sheet)
    assert sheet.polr_context['confirmed_quarters']==16


def test_real_tk_individual_acknowledgement_refresh_clears_consent(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    manual_review(app,sheet,task);sheet.polr_hours.set('5.00');assert sheet.confirm_polr();reviewed(app,sheet)
    assert sheet.review_polr();reviewed(app,sheet);k=(task,DAY)
    assert sheet.polr_acks[k][0].get() is False and not sheet.confirm_polr()
    sheet.polr_acks[k][0].set(True);sheet.toggle_polr_cell(k);assert not sheet.polr_acks
    sheet.toggle_polr_cell(k);assert not sheet.polr_acks[k][0].get()
    sheet.polr_acks[k][0].set(True);assert sheet.refresh_polr();reviewed(app,sheet)
    assert not sheet.polr_acks[k][0].get()
    sheet.polr_acks[k][0].set(True);assert sheet.confirm_polr();reviewed(app,sheet)
    assert app._polr_submission.outcome.status=='committed'
    assert not sheet.polr_acks and dest.read_bytes()==c.report_utf8


@pytest.mark.parametrize('status',['rolled_back','unavailable'])
def test_real_tk_known_failure_preserves_review_and_allows_new_explicit_submission(connected,root,tmp_path,monkeypatch,status):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    manual_review(app,sheet,task);sheet.polr_hours.set('2.50');original=TimerService.execute
    with monkeypatch.context() as m:
        m.setattr(TimerService,'execute',lambda self,r:Outcome(status,error=OSError(status)) if r.operation=='confirm_polr_absolute' else original(self,r))
        assert sheet.confirm_polr();reviewed(app,sheet)
    assert sheet.polr_ready and sheet.polr_hours.get()=='2.50' and app.pending is None
    assert sheet.confirm_polr();reviewed(app,sheet);assert sheet.polr_context['confirmed_quarters']==10


def test_real_tk_real_uncertain_commit_freezes_request_exact_retry_and_exit_cancel(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    manual_review(app,sheet,task);sheet.polr_hours.set('0.00');original=TimerService.execute;injected=[]
    def fault(self,r):
        if r.operation=='confirm_polr_absolute' and not injected:
            injected.append(True);self.store.connection=FaultConnection(self.store.connection,after=True)
        return original(self,r)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'execute',fault);m.setattr(SQLiteStore,'_probe',lambda *a:(_ for _ in ()).throw(OSError('probe unavailable')))
        assert sheet.confirm_polr();pump(root,lambda:not app.executing and app.pending is not None)
    r=app.pending;assert app._polr_submission.request is r
    assert not sheet.close() and not sheet.defer_polr() and not sheet.manual_polr() and not sheet.confirm_polr()
    assert sheet.polr_hours_control.instate(['disabled']) and sheet.polr_retry_button.instate(['!disabled'])
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**kw:False)
    app.request_close();assert app.pending is r and root.grab_current() is sheet.window
    assert sheet.retry_polr();reviewed(app,sheet)
    assert app._polr_submission.request is r and sheet.polr_context['confirmed_quarters']==0


def test_real_tk_postcommit_refresh_failure_and_presentation_preserve_known_success(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    manual_review(app,sheet,task);sheet.polr_hours.set('1.00')
    monkeypatch.setattr(TimerService,'read_polr_manual_context',lambda *a,**k:(_ for _ in ()).throw(OSError('context refresh unavailable')))
    assert sheet.confirm_polr();reviewed(app,sheet)
    result=app._polr_submission.outcome
    assert result.status=='committed' and result.result['batch_id'] in sheet.polr_status.cget('text') and not sheet.polr_ready
    assert sheet.close() and dest.read_bytes()==c.report_utf8


def test_real_tk_busy_destroyed_origin_and_late_delivery_preserve_committed_owner(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    manual_review(app,sheet,task);sheet.polr_hours.set('1.00');original=TimerService.execute;entered=threading.Event();gate=threading.Event()
    def slow(self,r):
        if r.operation=='confirm_polr_absolute':entered.set();assert gate.wait(5)
        return original(self,r)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'execute',slow);assert sheet.confirm_polr();pump(root,entered.is_set)
        r=app.pending;app._handle(Message('mutate',app._pending_token-1,Outcome('committed',{})))
        assert app.pending is r and not sheet.close() and not app.open_timesheet()
        app.request_close();assert app.alive and not app.closing
        sheet.window.destroy();assert app.timesheet is None and app.pending is r
        gate.set();settled(app)
    assert app._polr_submission is None and app.pending is None
    assert dest.read_bytes()==c.report_utf8


def test_real_tk_confirmation_thread_delivery_obsolete_reads_and_optional_context(connected,root,tmp_path,monkeypatch):
    import chronicle.accounting
    from tkinter import ttk
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    ui_thread=threading.get_ident();ui_seen=[];worker_seen=[]
    configure=ttk.Widget.configure;read=TimerService.read_polr_manual_context
    def ui(self,*a,**kw):
        assert threading.get_ident()==ui_thread;ui_seen.append(True);return configure(self,*a,**kw)
    def database(self,*a,**kw):worker_seen.append(threading.get_ident());return read(self,*a,**kw)
    with monkeypatch.context() as m:
        m.setattr(ttk.Widget,'configure',ui);m.setattr(TimerService,'read_polr_manual_context',database)
        fault=ValueError('Actual/suggestion unavailable')
        m.setattr(chronicle.accounting,'calculate_daily',lambda *a,**kw:(_ for _ in ()).throw(fault))
        manual_review(app,sheet,task)
        assert sheet.polr_ready and sheet.polr_context['actual_us'] is None
        assert 'Actual: Unavailable' in sheet.polr_detail.get('1.0','end')
        sheet.polr_hours.set('1.00');assert sheet.confirm_polr();reviewed(app,sheet)
        assert app._polr_submission.outcome.status=='committed' and sheet.polr_context['confirmed_quarters']==4
        # A stale delivery after leaving this review cannot install another context.
        old=sheet.polr_context;token=app._token
        sheet.defer_polr();sheet.receive_polr('polr_manual',token,{**old,'confirmed_quarters':999})
        assert sheet.polr_context==old
    assert ui_seen and worker_seen and set(worker_seen)=={worker.ident}


def test_real_tk_known_commit_survives_result_widget_failure(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    manual_review(app,sheet,task);sheet.polr_hours.set('1.00');fault=RuntimeError('result rendering failed')
    monkeypatch.setattr(sheet,'polr_result',lambda *a:(_ for _ in ()).throw(fault))
    assert sheet.confirm_polr();settled(app)
    assert app._polr_submission.outcome.status=='committed' and root.test_errors[-1][1] is fault
    assert sheet.manual_polr_button.instate(['!disabled']) and sheet.manual_polr()
    assert sheet.close() and dest.read_bytes()==c.report_utf8


def test_real_tk_unverified_confirmation_confirmed_exceptional_exit_preserves_evidence(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    manual_review(app,sheet,task);sheet.polr_hours.set('1.00');original=TimerService.execute
    def committed_lost(self,r):
        out=original(self,r)
        return Outcome('unverified',error=OSError('lost acknowledgement')) if r.operation=='confirm_polr_absolute' else out
    with monkeypatch.context() as m:
        m.setattr(TimerService,'execute',committed_lost)
        assert sheet.confirm_polr();pump(root,lambda:app.pending is not None and not app.executing)
    r=app.pending;calls=[]
    def yes(*args,**kw):calls.append(kw);assert not sheet.close() and not app.open_timesheet();return True
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',yes)
    app.request_close();exit_settled(app)
    assert calls[0]['parent'] is sheet.window and calls[0]['default']=='no' and dest.read_bytes()==c.report_utf8
    store=SQLiteStore(worker.directory)
    try:
        service=TimerService(store)
        assert service.reconcile_request(r).status=='committed'
        assert service.read_polr_current_cells([dict(task_id=task,work_date=DAY)])[0]['confirmed_quarters']==4
    finally:store.close()


@pytest.mark.parametrize('fault',['clock','queue'])
def test_real_tk_confirmation_prequeue_failure_preserves_editable_review(connected,root,tmp_path,monkeypatch,fault):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    manual_review(app,sheet,task);sheet.polr_hours.set('1.25');before=evidence(worker);error=RuntimeError(fault)
    with monkeypatch.context() as m:
        if fault=='clock':m.setattr(app,'now_utc',lambda:(_ for _ in ()).throw(error))
        else:m.setattr(worker.requests,'put',lambda *a:(_ for _ in ()).throw(error))
        assert not sheet.confirm_polr()
    assert app.pending is None and not app.executing and sheet.polr_ready and sheet.polr_hours.get()=='1.25'
    assert evidence(worker)==before and root.test_errors[-1][1] is error and fault in sheet.polr_status.cget('text')


def test_real_tk_manual_without_preview_or_export_and_cancel_has_no_effect(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);sheet=open_sheet(app);before=evidence(worker)
    assert sheet.candidate is None and app._timesheet_attempt is None
    manual_review(app,sheet,task);assert sheet.polr_context['confirmed_quarters'] is None
    sheet.polr_hours.set('1.25');assert sheet.defer_polr() and evidence(worker)==before
    manual_review(app,sheet,task);sheet.polr_hours.set('1.25');assert sheet.confirm_polr();reviewed(app,sheet)
    assert sheet.polr_context['confirmed_quarters']==5 and sheet.candidate is None and app._timesheet_attempt is None
    assert sheet.saved_reports();pump(root,lambda:sheet.saved_token is None)
    assert not sheet.saved_list.get_children()


def test_real_tk_changing_inline_mode_abandons_saved_read_without_stranding_controls(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    entered=threading.Event();gate=threading.Event();original=TimerService.list_registered_timesheet_exports
    def slow(self):entered.set();assert gate.wait(5);return original(self)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'list_registered_timesheet_exports',slow)
        assert sheet.saved_reports();pump(root,entered.is_set);old=sheet.saved_token
        assert old is not None and sheet.manual_polr() and sheet.saved_token is None
        gate.set();assert sheet.refresh_polr();reviewed(app,sheet)
    assert sheet.polr_ready and sheet.defer_polr()
    assert sheet.saved_button.instate(['!disabled']) and sheet.saved_reports()
    pump(root,lambda:sheet.saved_token is None);assert c.export_id in sheet.saved_list.get_children()
