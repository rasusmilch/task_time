"""Connected Chronicle app/worker/SQLite; callbacks isolate faults, operator case uses XTest."""
from copy import deepcopy
from datetime import timedelta
import threading
import sqlite3
import tkinter as tk

import pytest

from chronicle.app import ChronicleApp
from chronicle.records import Outcome
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.worker import DatabaseWorker,Message
from conftest import NOW,uid
from test_app import root,connected,pump,create,evidence,click,keyboard,Clock
from test_chronicle_history_ui import mutation,selected_task
from test_chronicle_timesheet_ui import open_sheet,refresh,choose_combo
from test_timesheet_save_ui import choose,settled,saved_reports,exit_settled
from test_polr_confirmation_ui import saved,manual_review,reviewed
from test_services import FaultConnection

DAY='2026-10-19'


def ready(app):
    pump(app.root,lambda:app.pending is None and not app.executing and app._read_inflight is None and app._reminder_inflight is None and not app._reminder_again)


def reconciled(app,sheet):
    pump(app.root,lambda:sheet.reconciliation_token is None)
    assert sheet.reconciliation_current,sheet.reconciliation_status.cget('text')
    return sheet.reconciliation_result


def row(sheet,task,day=DAY):
    return next((k,r) for k,r in sheet.reconciliation_mapping.items() if (r['task_id'],r['work_date'])==(task,day))


def test_real_tk_current_defaults_explicit_custom_drafts_calendars_copy_and_no_writes(connected,root):
    app,worker,clock=connected;task=selected_task(app)
    mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date=DAY,duration_text='1:08',comment='')
    sheet=open_sheet(app);before=evidence(worker)
    assert sheet.open_reconciliation();r=reconciled(app,sheet)
    assert sheet.reconciliation_period.get()=='This week' and sheet.reconciliation_scope.get()=='All tasks'
    assert r['coverage']['UNKNOWN']==1 and 'not Actual work' in sheet.reconciliation_summary.get('1.0','end')
    k,c=row(sheet,task);sheet.reconciliation_tree.selection_set(k)
    assert sheet.copy_suggested() and root.clipboard_get()=='1.25'
    assert c['classification']=='UNKNOWN' and sheet.candidate is None and evidence(worker)==before
    calls=clock.calls;old=deepcopy(r)
    sheet.reconciliation_period.set('Custom');sheet.reconciliation_start.set(DAY);sheet.reconciliation_end.set(DAY)
    assert not sheet.reconciliation_current and clock.calls==calls
    assert sheet.open_picker(sheet.reconciliation_start);sheet._choose_day(20)
    assert sheet.reconciliation_start.get()=='2026-10-20' and not sheet.reconciliation_current
    assert sheet.open_picker(sheet.reconciliation_end);sheet._escape()
    assert not sheet.disposed and sheet.picker is None and root.grab_current() is sheet.window
    assert sheet.refresh_reconciliation();pump(root,lambda:sheet.reconciliation_token is None)
    assert not sheet.reconciliation_current and sheet.reconciliation_result==old
    assert sheet.reconciliation_start.get()=='2026-10-20' and sheet.reconciliation_end.get()==DAY
    sheet.reconciliation_start.set(DAY);assert sheet.refresh_reconciliation();r=reconciled(app,sheet)
    assert not r['task_weeks'][0]['full_scope'] and 'Partial scope' in sheet.reconciliation_summary.get('1.0','end')
    assert sheet.leave_reconciliation() and sheet.mode=='preview' and not sheet.current
    assert evidence(worker)==before and not root.test_errors[:-1] # Invalid range retains original diagnostic.


def test_real_tk_saved_comparison_manual_navigation_and_confirmation_refresh(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task,sheet,c,dest=saved(app,tmp_path,monkeypatch)
    assert sheet.open_reconciliation(compare=True);r=reconciled(app,sheet)
    assert r['source_comparison']['export_id']==c.export_id and not any(x['flags'] for x in r['source_comparison']['cells'])
    assert not sheet.saved_token and sheet.mode=='reconciliation'
    k,_=row(sheet,task);sheet.reconciliation_tree.selection_set(k)
    assert sheet.reconciliation_manual_action();reviewed(app,sheet)
    sheet.polr_hours.set('2.50');assert sheet.confirm_polr();reviewed(app,sheet)
    assert sheet.open_reconciliation(compare=True);r=reconciled(app,sheet)
    v=next(v for v in r['daily_cells'] if (v['task_id'],v['work_date'])==(task,DAY))
    assert v['confirmed_quarters']==10 and v['daily_delta_hundredths']==50 and v['classification']=='MISMATCH'
    assert 'NEWER_DIFFERING_CONFIRMATION' in r['source_comparison']['cells'][1]['flags']
    assert dest.read_bytes()==c.report_utf8
    assert sheet.saved_reports();pump(root,lambda:sheet.saved_token is None)
    assert sheet.mode=='saved' and sheet.saved_panel.winfo_ismapped()
    saved_reports(app,sheet,c.export_id);assert sheet.candidate.export_id==c.export_id and sheet.candidate.report_utf8==c.report_utf8
    assert not root.test_errors


def test_real_tk_reconciliation_read_render_failure_recovery_and_obsolete_delivery(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);sheet=open_sheet(app)
    assert sheet.open_reconciliation();old=deepcopy(reconciled(app,sheet));fault=OSError('reconciliation read failed')
    with monkeypatch.context() as m:
        m.setattr(TimerService,'read_polr_reconciliation',lambda *a,**k:(_ for _ in ()).throw(fault))
        assert sheet.refresh_reconciliation();pump(root,lambda:sheet.reconciliation_token is None)
    assert not sheet.reconciliation_current and sheet.reconciliation_result==old and root.test_errors[-1][1] is fault
    assert 'unavailable' in sheet.reconciliation_status.cget('text')
    original=sheet.reconciliation_tree.insert;render_fault=RuntimeError('partial table')
    with monkeypatch.context() as m:
        def broken(*a,**k):original(*a,**k);raise render_fault
        m.setattr(sheet.reconciliation_tree,'insert',broken)
        assert sheet.refresh_reconciliation();pump(root,lambda:sheet.reconciliation_token is None)
    assert not sheet.reconciliation_tree.master.winfo_ismapped() and not sheet.reconciliation_current
    assert root.test_errors[-1][1] is render_fault
    assert sheet.refresh_reconciliation();reconciled(app,sheet)
    assert sheet.reconciliation_tree.master.winfo_ismapped()
    sheet.reconciliation_token=991;sheet.reconciliation_period.set('Last week')
    sheet.receive_reconciliation(991,old);assert not sheet.reconciliation_current
    sheet.close();sheet.receive_reconciliation(991,old)
    fresh=open_sheet(app);fresh.receive_reconciliation(991,old);assert fresh.reconciliation_result is None


def test_real_tk_reminder_schedule_coalesces_ticks_mutations_failures_and_rollover(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);ready(app)
    counts=[];original=TimerService.read_polr_reminder_status
    def counted(service,**kw):counts.append(kw['cutoff_utc_us']);return original(service,**kw)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'read_polr_reminder_status',counted)
        for _ in range(5):app._tick();root.after_cancel(app._tick_id)
        ready(app);assert counts==[] # Numeric refresh ticks do not evaluate reconciliation again.
        mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date='2026-10-12',duration_text='1:00',comment='previous')
        ready(app);assert len(counts)==1 and app.reminder['reminder_due']
        assert app.reminder_banner.winfo_ismapped() and 'Previous week: 1' in app.reminder_label.cget('text')
        assert app.recheck_polr();assert app.recheck_polr();assert app.recheck_polr();ready(app)
        assert len(counts)==3 # At most one in flight and one latest follow-up.
        trusted=deepcopy(app.reminder);fault=ValueError('read unavailable')
        m.setattr(TimerService,'read_polr_reminder_status',lambda *a,**k:(_ for _ in ()).throw(fault))
        app.recheck_polr();ready(app)
        assert app.reminder==trusted and app._reminder_error is fault and 'Previous trusted warning' in app.reminder_label.cget('text')
        assert str(app.buttons['Start'].cget('state'))=='normal'
        m.setattr(TimerService,'read_polr_reminder_status',counted)
        clock.value+=timedelta(days=1);app._tick();root.after_cancel(app._tick_id);ready(app)
        assert app.reminder['local_today']=='2026-10-20' and not app.reminder['current_week_checked'] and app._reminder_error is None
        assert not app.executing and app.pending is None


def test_real_tk_dismiss_commit_not_queue_exact_retry_uncertain_and_restart(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app)
    mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date='2026-10-12',duration_text='0:03',comment='')
    ready(app);assert app.reminder['reminder_due']
    original=SQLiteStore.transact;probe=SQLiteStore._probe;requests=[]
    def uncertain(store,request,operation):
        if request.operation=='dismiss_polr_reminder_today':
            requests.append(request);store.connection=FaultConnection(store.connection,after=True)
        return original(store,request,operation)
    def unavailable(store):raise sqlite3.OperationalError('independent probe unavailable')
    with monkeypatch.context() as m:
        m.setattr(SQLiteStore,'transact',uncertain);m.setattr(SQLiteStore,'_probe',unavailable)
        assert app.dismiss_polr_today();request=app.pending
        assert app.reminder['reminder_due'] # Queue acceptance is not success.
        pump(root,lambda:not app.executing)
        assert app.pending is request and app.reminder['reminder_due']
        assert not app.dismiss_polr_today() and str(app.retry_button.cget('state'))!='disabled'
    assert app.retry();ready(app)
    assert requests==[request] and app.reminder['dismissed_local_date']==DAY and not app.reminder['reminder_due']
    directory=worker.directory;root.destroy();worker.join(8);assert not worker.is_alive()
    other=tk.Tk();other.test_errors=[];other.report_callback_exception=lambda *a:other.test_errors.append(a)
    fresh_worker=DatabaseWorker(directory);fresh=ChronicleApp(other,fresh_worker,now_utc=clock);fresh_worker.start()
    try:
        pump(other,lambda:fresh.ready and fresh.reminder is not None);ready(fresh)
        assert not fresh.reminder['reminder_due'] and fresh.reminder['dismissed_local_date']==DAY
        clock.value+=timedelta(days=1);fresh._tick();other.after_cancel(fresh._tick_id);ready(fresh)
        assert fresh.reminder['reminder_due'] and fresh.reminder['local_today']=='2026-10-20'
    finally:other.destroy();fresh_worker.join(8);assert not fresh_worker.is_alive()


def test_real_tk_banner_navigation_previous_preferred_current_only_and_no_dismiss(connected,root):
    app,worker,clock=connected;task=selected_task(app)
    for day in ('2026-10-12',DAY):mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date=day,duration_text='1:00',comment='')
    ready(app);before=evidence(worker);assert app.open_reminder_timesheet()
    sheet=app.timesheet;pump(root,lambda:sheet.presented and sheet.choices_token is None);r=reconciled(app,sheet)
    assert sheet.reconciliation_period.get()=='Last week' and app.reminder['reminder_due']
    assert not app.open_reminder_timesheet() and evidence(worker)==before and root.grab_current() is sheet.window
    assert sheet.leave_reconciliation();assert sheet.manual_polr();reviewed(app,sheet)
    sheet.polr_task_control.current(sheet.polr_task_choices.index(task));sheet.polr_date.set('2026-10-12')
    sheet.refresh_polr();reviewed(app,sheet);sheet.polr_hours.set('1.00');sheet.confirm_polr();reviewed(app,sheet);ready(app)
    assert app.reminder['previous_week_outstanding_counts']['outstanding']==0 and app.reminder['current_week_outstanding_counts']['outstanding']==1
    sheet.close();assert app.open_reminder_timesheet();sheet=app.timesheet
    pump(root,lambda:sheet.presented and sheet.choices_token is None);reconciled(app,sheet)
    assert sheet.reconciliation_period.get()=='This week' and app.reminder['dismissed_local_date'] is None


def test_real_tk_old_reminder_results_and_clock_failures_do_not_claim_clean(connected,root,monkeypatch):
    app,worker,clock=connected;ready(app);old=deepcopy(app.reminder)
    app._receive_reminder(Message('polr_reminder',-99,{**old,'reminder_due':True}))
    assert app.reminder==old
    def bad():raise OverflowError('calendar unavailable')
    monkeypatch.setattr(app,'now_utc',bad)
    assert not app.recheck_polr() and app.reminder==old and 'unavailable' in app.reminder_label.cget('text')
    assert root.test_errors[-1][1].args==('calendar unavailable',)


def test_real_tk_ui_thread_reads_and_closed_view_shutdown_are_safe(connected,root,monkeypatch):
    app,worker,clock=connected;ready(app);ident=threading.get_ident();threads=[]
    original=TimerService.read_polr_reconciliation
    def read(service,**kw):threads.append(threading.get_ident());return original(service,**kw)
    monkeypatch.setattr(TimerService,'read_polr_reconciliation',read)
    sheet=open_sheet(app);assert sheet.open_reconciliation();sheet.close()
    ready(app);assert threads and all(t!=ident for t in threads) and not root.test_errors
    app.request_close();exit_settled(app)


def test_real_tk_dismissal_resolving_after_date_rollover_does_not_suppress_new_day(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app)
    mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date='2026-10-12',duration_text='1:00',comment='')
    ready(app);execute=TimerService.execute
    with monkeypatch.context() as m:
        def unknown(service,request):
            return Outcome('unverified',error=OSError('lost response')) if request.operation=='dismiss_polr_reminder_today' else execute(service,request)
        m.setattr(TimerService,'execute',unknown)
        assert app.dismiss_polr_today();request=app.pending
        pump(root,lambda:not app.executing)
        clock.value+=timedelta(days=1);app._tick();root.after_cancel(app._tick_id)
        assert app.pending is request and app.reminder['reminder_due']
    assert app.retry();ready(app)
    assert app.reminder['dismissed_local_date']==DAY and app.reminder['local_today']=='2026-10-20' and app.reminder['reminder_due']


def test_real_tk_known_dismissal_rollback_and_postcommit_presentation_failure(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app)
    mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date='2026-10-12',duration_text='1:00',comment='')
    ready(app);transact=SQLiteStore.transact
    with monkeypatch.context() as m:
        def rollback(store,request,operation):
            if request.operation=='dismiss_polr_reminder_today':store.connection=FaultConnection(store.connection,after=False)
            return transact(store,request,operation)
        m.setattr(SQLiteStore,'transact',rollback)
        app.dismiss_polr_today();ready(app)
        assert app.reminder['reminder_due'] and app.reminder['dismissed_local_date'] is None
    configure=app.status.configure;fault=RuntimeError('postcommit status failure')
    with monkeypatch.context() as m:
        def fail(**kw):
            if kw.get('text')=='Saved.':raise fault
            return configure(**kw)
        m.setattr(app.status,'configure',fail)
        app.dismiss_polr_today();pump(root,lambda:not app.executing and app.pending is None)
        assert root.test_errors[-1][1] is fault
    ready(app) # The committed result schedules its authoritative reread before failing presentation.
    assert not app.reminder['reminder_due'] and app.reminder['dismissed_local_date']==DAY


def test_real_tk_read_failure_does_not_override_dismissed_date(connected,root,monkeypatch):
    app,worker,clock=connected;ready(app)
    assert app.dismiss_polr_today();ready(app)
    assert not app.reminder_banner.winfo_ismapped()
    fault=OSError('later calculation unavailable')
    with monkeypatch.context() as m:
        m.setattr(TimerService,'read_polr_reminder_status',lambda *a,**k:(_ for _ in ()).throw(fault))
        app.recheck_polr();ready(app)
    assert not app.reminder_banner.winfo_ismapped() and app._reminder_error is fault
    assert 'unavailable' in app.status.cget('text') and root.test_errors[-1][1] is fault


def test_real_tk_reminder_queue_failure_is_explicit_not_automatic_retry(connected,root,monkeypatch):
    app,worker,clock=connected;ready(app);put=worker.requests.put;calls=[];fault=OSError('queue unavailable')
    def enqueue(message):
        if message.kind=='polr_reminder':calls.append(message);raise fault
        return put(message)
    with monkeypatch.context() as m:
        m.setattr(worker.requests,'put',enqueue)
        assert not app.recheck_polr() and not app._reminder_again and app._reminder_inflight is None
        for _ in range(3):app._tick();root.after_cancel(app._tick_id)
        assert len(calls)==1 and root.test_errors[-1][1] is fault
    assert app.recheck_polr();ready(app)
    assert app._reminder_error is None


def test_real_tk_manual_cancel_after_reconciliation_restores_valid_timesheet_view(connected,root):
    app,worker,clock=connected;task=selected_task(app);sheet=open_sheet(app)
    assert sheet.open_reconciliation();reconciled(app,sheet)
    before=evidence(worker)
    assert sheet.reconciliation_manual_action() and sheet.mode=='confirmation_manual'
    assert sheet.defer_polr() and sheet.mode=='preview'
    pump(root,lambda:sheet.report.master.winfo_ismapped())
    assert sheet.report.master.winfo_ismapped() and not sheet.reconciliation_panel.winfo_ismapped()
    assert sheet.open_reconciliation();reconciled(app,sheet)
    assert evidence(worker)==before and root.grab_current() is sheet.window and not root.test_errors


@pytest.mark.parametrize('have_trusted_status',[False,True])
def test_real_tk_explicit_dismiss_suppresses_even_when_calculation_unavailable(connected,root,monkeypatch,have_trusted_status):
    app,worker,clock=connected;ready(app)
    if not have_trusted_status:app.reminder=None
    fault=ValueError('current reconciliation cannot be calculated')
    with monkeypatch.context() as m:
        m.setattr('chronicle.timesheet.calculate_daily',lambda *a,**k:(_ for _ in ()).throw(fault))
        app.recheck_polr();ready(app)
        assert app.reminder_banner.winfo_ismapped() and app.reminder_dismiss.instate(['!disabled'])
        before=evidence(worker);app.reminder_dismiss.invoke();ready(app)
        assert app._reminder_dismissed_date==DAY and not app.reminder_banner.winfo_ismapped()
        assert app._reminder_error is fault and app.pending is None
        after=evidence(worker)
        assert all(after[k]==before[k] for k in before if k!='committed_requests')
    app.recheck_polr();ready(app)
    assert app.reminder['dismissed_local_date']==DAY and not app.reminder['reminder_due']


def test_real_tk_startup_dismissal_stays_suppressed_when_only_calculation_fails(root,tmp_path,monkeypatch):
    directory=tmp_path/'existing';store=SQLiteStore(directory,create=True,timezone='America/Chicago')
    service=TimerService(store);service.dismiss_polr_reminder_today(DAY,request_id=uid(),action_utc_us=NOW);store.close()
    fault=ValueError('accounting currently unavailable')
    worker=DatabaseWorker(directory);clock=Clock();app=ChronicleApp(root,worker,now_utc=clock)
    with monkeypatch.context() as m:
        m.setattr('chronicle.timesheet.calculate_daily',lambda *a,**k:(_ for _ in ()).throw(fault))
        worker.start()
        try:
            pump(root,lambda:app.ready and app._reminder_error is not None)
            assert app._reminder_dismissed_date==DAY and not app.reminder_banner.winfo_ismapped()
            assert app.reminder is None and 'unavailable' in app.status.cget('text')
            assert root.test_errors[-1][1] is fault
        finally:root.destroy();worker.join(8);assert not worker.is_alive()


def test_real_tk_reminder_completion_during_exit_does_not_strand_read_token(connected,root):
    app,worker,clock=connected;ready(app);old=deepcopy(app.reminder)
    app._reminder_inflight=987;app.closing=True
    app._receive_reminder(Message('polr_reminder',987,Outcome('unavailable',error=OSError('discarded during close'))))
    assert app._reminder_inflight is None and app._reminder_again and app.reminder==old
    app.closing=False;app.recheck_polr();ready(app)
    assert app._reminder_inflight is None and not app._reminder_again and not root.test_errors


def test_real_tk_review_known_zero_current_batch_without_source_export(connected,root):
    app,worker,clock=connected;task=selected_task(app);sheet=open_sheet(app)
    manual_review(app,sheet,task);sheet.polr_hours.set('0.00');assert sheet.confirm_polr();reviewed(app,sheet)
    batch=app._polr_submission.outcome.result['batch_id']
    assert app._timesheet_attempt is None and sheet.open_reconciliation();reconciled(app,sheet)
    handle,value=row(sheet,task);assert value['current_batch_id']==batch and value['confirmed_quarters']==0
    before=evidence(worker);sheet.reconciliation_tree.selection_set(handle)
    pump(root,lambda:sheet.reconciliation_confirm.instate(['!disabled']))
    sheet.reconciliation_confirm.invoke();reviewed(app,sheet)
    assert sheet.mode=='confirmation_history' and sheet.polr_batch_id==batch
    assert batch in sheet.polr_detail.get('1.0','end') and '0.00' in sheet.polr_detail.get('1.0','end')
    assert evidence(worker)==before and root.grab_current() is sheet.window and not root.test_errors


def test_real_tk_banner_uses_canonical_stale_owner_cleanup(connected,root):
    app,worker,clock=connected;ready(app);old=open_sheet(app);old.close()
    app.timesheet=old # Isolate stale bookkeeping; the actual old widget is destroyed.
    assert app.open_reminder_timesheet();fresh=app.timesheet
    pump(root,lambda:fresh.presented and fresh.choices_token is None)
    reconciled(app,fresh)
    assert fresh is not old and fresh.mode=='reconciliation' and fresh.candidate is None
    assert root.grab_current() is fresh.window and not root.test_errors
