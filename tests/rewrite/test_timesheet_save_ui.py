"""Connected SQLite/worker Save and widget-independent recovery, separate from server input."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import gc
import hashlib
import threading
import tkinter as tk

import pytest

from chronicle.app import ChronicleApp
from chronicle.records import Outcome
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timesheet_files import FileState as S
from chronicle.worker import DatabaseWorker,Message
from conftest import NOW,uid
from test_app import root,connected,click,keyboard,pump,create,evidence
from test_chronicle_history_ui import selected_task,seed,mutation
from test_chronicle_timesheet_ui import open_sheet,refresh
from test_services import FaultConnection


def settled(app):
    pump(app.root,lambda:not app.executing and app.pending is None and app._read_inflight is None)


def exit_settled(app):
    if app.alive:
        app.root.after(8000,app.root.quit)
        app.root.mainloop()  # Bounded test driver; root destruction terminates this wait.
    assert not app.alive and app._worker_stopped


def choose(monkeypatch,sheet,path):
    import chronicle.timesheet_window as module
    calls=[]
    def dialog(**kw):
        calls.append(kw)
        assert sheet.is_busy() and not sheet.close() and not sheet.save() and not sheet.owner.open_timesheet()
        sheet.owner.request_close();assert sheet.owner.alive
        return path
    monkeypatch.setattr(module.filedialog,'asksaveasfilename',dialog)
    return calls


def saved_reports(app,sheet,export_id):
    assert sheet.saved_reports()
    pump(app.root,lambda:sheet.saved_token is None)
    sheet.saved_list.selection_set(export_id)
    assert sheet.load_saved();pump(app.root,lambda:sheet.saved_token is None)
    assert app._timesheet_attempt.candidate.export_id==export_id


def test_real_tk_exact_registration_before_publish_controls_and_completion(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);seed(app,task)
    sheet=open_sheet(app);assert sheet.save_button.instate(['disabled']) and not sheet.save()
    c=refresh(app,sheet);before=evidence(worker);dest=tmp_path/'report.txt'
    dialogs=choose(monkeypatch,sheet,str(dest));calls=[]
    original=TimerService.materialize_registered_timesheet_export
    def publish(self,export_id,*a,**kw):
        frozen=self.read_registered_timesheet_export(export_id)
        calls.append((frozen,threading.get_ident()))
        assert self.store.connection.execute('SELECT count(*) FROM timesheet_exports').fetchone()[0]==1
        assert frozen.preferred_destination==str(dest)
        return original(self,export_id,*a,**kw)
    monkeypatch.setattr(TimerService,'materialize_registered_timesheet_export',publish)
    assert sheet.save();attempt=app._timesheet_attempt;request=app.pending
    assert attempt.request is request and request.args()['candidate']['preferred_destination']==str(dest)
    assert not sheet.refresh_preview() and not sheet.open_picker(sheet.start)
    settled(app)
    assert attempt.saved_path==str(dest) and dest.read_bytes()==c.report_utf8
    assert attempt.candidate.report_sha256==c.report_sha256 and attempt.candidate.export_id==c.export_id
    assert attempt.candidate.basis==c.basis and attempt.candidate.cells==c.cells
    assert calls[0][1]==worker.ident and calls[0][0]==attempt.candidate
    assert dialogs[0]['parent'] is sheet.window and dialogs[0]['confirmoverwrite'] is False
    assert 'Save complete' in sheet.status.cget('text') and not sheet.retry_save()
    after=evidence(worker)
    assert all(after[k]==before[k] for k in before if k!='committed_requests')
    assert len(after['committed_requests'])==len(before['committed_requests'])+1
    sheet.close();assert app.timesheet is None and app._timesheet_handoff is None
    fresh=open_sheet(app);assert fresh.candidate is None and fresh.period.get()=='This week'


@pytest.mark.parametrize('path',[None,'','bad\x00path',42])
def test_real_tk_initial_path_cancel_invalid_no_registration(connected,root,tmp_path,monkeypatch,path):
    app,worker,clock=connected;selected_task(app);sheet=open_sheet(app);c=refresh(app,sheet)
    before=evidence(worker);choose(monkeypatch,sheet,path)
    assert not sheet.save() and app._timesheet_attempt is None and app.pending is None
    assert sheet.current and sheet.get_prepared_export()==c and not sheet.is_locked()
    assert evidence(worker)==before


def test_real_tk_dialog_draft_change_and_original_error_grab_return(connected,root,monkeypatch,tmp_path):
    app,worker,clock=connected;sheet=open_sheet(app);refresh(app,sheet);before=evidence(worker)
    def change(**kw):sheet.start.set('changed while dialog');return str(tmp_path/'not-created.txt')
    import chronicle.timesheet_window as module
    monkeypatch.setattr(module.filedialog,'asksaveasfilename',change)
    assert not sheet.save() and app.pending is None and evidence(worker)==before
    assert root.grab_current() is sheet.window and not sheet.current
    refresh(app,sheet);fault=RuntimeError('native dialog failure')
    def fail(**kw):sheet.window.grab_release();raise fault
    monkeypatch.setattr(module.filedialog,'asksaveasfilename',fail)
    assert not sheet.save() and root.test_errors[-1][1] is fault
    assert root.grab_current() is sheet.window and not app.executing


@pytest.mark.parametrize('committed',[False,True])
def test_real_tk_uncertain_registration_exact_request_no_publication_before_reconciliation(connected,root,tmp_path,monkeypatch,committed):
    app,worker,clock=connected;task=selected_task(app);seed(app,task)
    sheet=open_sheet(app);c=refresh(app,sheet);dest=tmp_path/'after-reconcile.txt';choose(monkeypatch,sheet,str(dest))
    original=TimerService.execute;seen=[]
    def uncertain(self,request):
        if request.operation=='register_timesheet_export' and not seen:
            seen.append(request)
            if committed:
                result=original(self,request);assert result.status=='committed'
            return Outcome('unverified',error=OSError('lost registration acknowledgement'))
        return original(self,request)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'execute',uncertain)
        assert sheet.save();pump(root,lambda:app.pending is not None and not app.executing)
    frozen=app.pending;a=app._timesheet_attempt
    assert frozen is seen[0] and a.registration=='unverified' and not dest.exists()
    assert not sheet.close() and not sheet.new_preview() and not sheet.saved_reports()
    assert not sheet.refresh_preview() and a.candidate.export_id==c.export_id
    # Direct draft writes cannot replace the owner-retained request on Retry.
    sheet.start.set('unapplied');assert sheet.retry_save();settled(app)
    assert a.request is frozen and a.saved_path==str(dest) and dest.read_bytes()==c.report_utf8
    assert len([r for r in evidence(worker)['committed_requests'] if r[2]=='register_timesheet_export'])==1


@pytest.mark.parametrize('status',['rejected','rolled_back','unavailable'])
def test_real_tk_known_registration_failure_never_publishes_and_explicit_retry(connected,root,tmp_path,monkeypatch,status):
    app,worker,clock=connected;sheet=open_sheet(app);refresh(app,sheet);dest=tmp_path/'later.txt';choose(monkeypatch,sheet,str(dest))
    original=TimerService.execute;seen=[]
    def fail(self,request):
        if request.operation=='register_timesheet_export' and not seen:
            seen.append(request);return Outcome(status,error=OSError(status))
        return original(self,request)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'execute',fail);assert sheet.save();settled(app)
    a=app._timesheet_attempt
    assert not dest.exists() and a.registration==status and a.request is seen[0]
    assert sheet.retry_save();settled(app)
    assert a.saved_path==str(dest) and a.request is seen[0]


def test_real_tk_conflict_overwrite_cancel_reentry_one_call_and_alternate_path(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);seed(app,task)
    sheet=open_sheet(app);c=refresh(app,sheet);dest=tmp_path/'conflict.txt';dest.write_bytes(b'old')
    choose(monkeypatch,sheet,str(dest));assert sheet.save();settled(app)
    a=app._timesheet_attempt;request=a.request;assert a.inspection.conflict and not a.saved_path
    import chronicle.timesheet_window as module
    decisions=[]
    def no(title,message,**kw):
        decisions.append((title,message,kw));assert sheet.is_busy() and not sheet.overwrite() and not sheet.close()
        assert not app.open_timesheet();return False
    monkeypatch.setattr(module.messagebox,'askyesno',no)
    assert not sheet.overwrite() and dest.read_bytes()==b'old' and a.request is request
    assert decisions[-1][0]=='Overwrite existing timesheet?' and str(dest) in decisions[-1][1]
    assert decisions[-1][2]['default']=='no' and decisions[-1][2]['parent'] is sheet.window
    monkeypatch.setattr(module.messagebox,'askyesno',lambda *a,**kw:True)
    assert sheet.overwrite();settled(app);assert dest.read_bytes()==c.report_utf8
    dest.write_bytes(b'new conflict');assert sheet.check_file_status();settled(app)
    assert a.inspection.state==S.CONFLICT
    # Ordinary retry does not inherit the previous consent.
    a.saved_path=None;assert sheet.retry_save();settled(app);assert dest.read_bytes()==b'new conflict'
    alternate=tmp_path/'copy.txt';choose(monkeypatch,sheet,str(alternate))
    assert sheet.save_copy_as();settled(app)
    assert alternate.read_bytes()==c.report_utf8 and dest.read_bytes()==b'new conflict'
    assert a.candidate.preferred_destination==str(dest) and a.request is request


def test_real_tk_saved_reports_recovery_after_actual_application_restart(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);seed(app,task)
    sheet=open_sheet(app);c=refresh(app,sheet);dest=tmp_path/'saved.txt';choose(monkeypatch,sheet,str(dest))
    assert sheet.save();settled(app);sheet.close()
    mutation(app,'rename_task',task_id=task,name='Later name',expected_version=1)
    mutation(app,'add_date_only_work',task_id=task,entry_id=uid(),work_date='2026-10-19',duration_text='2:00',comment='later')
    directory=worker.directory
    root.destroy();worker.join(timeout=8);assert not worker.is_alive()
    # New owner/worker/Tk root: no old widget or in-memory candidate is needed.
    other=tk.Tk();other.geometry('950x650+0+0');errors=[];other.report_callback_exception=lambda *args:errors.append(args)
    other.test_errors=errors
    next_worker=DatabaseWorker(directory);next_app=ChronicleApp(other,next_worker,now_utc=clock)
    next_worker.start()
    try:
        pump(other,lambda:next_app.ready and next_app.state.get('report') is not None)
        fresh=open_sheet(next_app);assert fresh.candidate is None
        before=evidence(next_worker)
        saved_reports(next_app,fresh,c.export_id)
        a=next_app._timesheet_attempt
        assert a.candidate.report_utf8==c.report_utf8 and a.candidate.tasks[0].name!='Later name'
        assert fresh.report.get('1.0','end-1c')==c.report_text and not a.saved_path
        assert fresh.check_file_status();settled(next_app);assert a.inspection.state==S.READY
        dest.unlink();assert fresh.check_file_status();settled(next_app);assert a.inspection.state==S.MISSING
        assert fresh.retry_save();settled(next_app)
        assert dest.read_bytes()==c.report_utf8 and evidence(next_worker)==before
        assert fresh.new_preview() and fresh.current is False and fresh.candidate is None
        newer=refresh(next_app,fresh);assert newer.export_id!=c.export_id and newer.tasks[0].name=='Later name'
    finally:
        if next_app.alive:other.destroy()
        next_worker.join(timeout=8);assert not next_worker.is_alive()


def test_real_tk_unfinished_registered_close_handoff_default_no_fresh_open_and_exit(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app);c=refresh(app,sheet);dest=tmp_path/'conflict.txt';dest.write_bytes(b'old')
    choose(monkeypatch,sheet,str(dest));assert sheet.save();settled(app)
    import chronicle.timesheet_window as module
    calls=[]
    def no(*args,**kw):calls.append((args,kw));return False
    monkeypatch.setattr(module.messagebox,'askyesno',no)
    assert not sheet.close() and app.timesheet is sheet and root.grab_current() is sheet.window
    assert calls[-1][1]['default']=='no' and c.export_id in calls[-1][0][1]
    monkeypatch.setattr(module.messagebox,'askyesno',lambda *a,**kw:True)
    assert sheet.close() and app.timesheet is None and app._timesheet_attempt is None
    assert app._timesheet_handoff==(c.export_id,str(dest))
    fresh=open_sheet(app);assert fresh.candidate is None and fresh.period.get()=='This week'
    fresh.close()
    monkeypatch.setattr(module.messagebox,'askyesno',no)
    app.request_close();assert app.alive and not app.closing
    monkeypatch.setattr(module.messagebox,'askyesno',lambda *a,**kw:True)
    app.request_close();exit_settled(app)
    assert dest.read_bytes()==b'old'


def test_real_tk_unverified_exit_warning_cancel_then_confirm(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app);refresh(app,sheet);choose(monkeypatch,sheet,str(tmp_path/'none.txt'))
    original=TimerService.execute
    monkeypatch.setattr(TimerService,'execute',lambda self,r:Outcome('unverified',error=OSError('unknown')) if r.operation=='register_timesheet_export' else original(self,r))
    assert sheet.save();pump(root,lambda:app.pending is not None and not app.executing)
    frozen=app.pending
    import chronicle.app as module
    choices=[]
    def no(*a,**kw):choices.append(kw);return False
    monkeypatch.setattr(module.messagebox,'askyesno',no)
    app.request_close();assert app.pending is frozen and app.alive and not app.closing
    assert choices[0]['parent'] is sheet.window and choices[0]['default']=='no'
    assert root.grab_current() is sheet.window
    monkeypatch.setattr(module.messagebox,'askyesno',lambda *a,**kw:True)
    app.request_close();exit_settled(app)


def test_real_tk_save_result_tokens_busy_and_destroyed_view_do_not_lose_completion(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app);c=refresh(app,sheet);dest=tmp_path/'still-saved.txt';choose(monkeypatch,sheet,str(dest))
    original=TimerService.materialize_registered_timesheet_export;gate,entered=threading.Event(),threading.Event()
    def slow(*args,**kw):entered.set();assert gate.wait(5);return original(*args,**kw)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'materialize_registered_timesheet_export',slow)
        assert sheet.save();pump(root,lambda:entered.is_set())
        a=app._timesheet_attempt;token=a.file_token
        app._handle(Message('timesheet_publish',token-1,Outcome('unavailable',error=OSError('late'))))
        assert app.executing and not sheet.close() and not sheet.retry_save()
        app.request_close();assert not app.closing
        sheet.window.destroy();assert app.timesheet is None and app._timesheet_attempt is a
        gate.set();settled(app)
    assert dest.read_bytes()==c.report_utf8 and a.saved_path==str(dest)
    assert app._timesheet_attempt is None
    fresh=open_sheet(app);assert fresh.candidate is None


def test_real_tk_known_save_completion_survives_presentation_error(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app);c=refresh(app,sheet);dest=tmp_path/'verified.txt';choose(monkeypatch,sheet,str(dest))
    original=sheet.save_changed;fault=RuntimeError('success label failed')
    def broken():
        if app._timesheet_attempt.saved_path:raise fault
        original()
    monkeypatch.setattr(sheet,'save_changed',broken)
    assert sheet.save();settled(app)
    assert app._timesheet_attempt.saved_path==str(dest) and dest.read_bytes()==c.report_utf8
    assert root.test_errors[-1][1] is fault and sheet.close()


def test_real_tk_dialog_primary_diagnostics_and_competing_grab_are_preserved(connected,root,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app);refresh(app,sheet)
    fault=RuntimeError('dialog primary');secondary=RuntimeError('return secondary')
    with monkeypatch.context() as m:
        m.setattr(sheet,'restore_modal',lambda *a:(_ for _ in ()).throw(secondary))
        with pytest.raises(RuntimeError) as caught:
            sheet.dialog(lambda:(_ for _ in ()).throw(fault))
        assert caught.value is fault and any('return secondary' in note for note in fault.__notes__)
    competitor=tk.Toplevel(root);competitor.transient(sheet.window)
    pump(root,lambda:competitor.winfo_viewable())
    def competing():competitor.grab_set();competitor.focus_set();return 'cancel'
    assert sheet.dialog(competing)=='cancel'
    assert root.grab_current() is competitor and not sheet.is_busy() and not app.executing
    competitor.destroy();assert sheet.restore_modal()


def test_real_tk_recovered_render_failure_cannot_offer_unreviewed_publication(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app);c=refresh(app,sheet)
    choose(monkeypatch,sheet,str(tmp_path/'reviewed.txt'));assert sheet.save();settled(app)
    assert sheet.saved_reports();pump(root,lambda:sheet.saved_token is None)
    sheet.saved_list.selection_set(c.export_id)
    original=sheet.report.insert;fault=RuntimeError('recovery report installation failed')
    monkeypatch.setattr(sheet.report,'insert',lambda *a,**kw:(_ for _ in ()).throw(fault))
    assert sheet.load_saved();pump(root,lambda:sheet.saved_token is None)
    assert app._timesheet_attempt is None and not sheet.report.winfo_ismapped()
    assert not sheet.retry_save() and not sheet.save_copy_as() and root.test_errors[-1][1] is fault
    monkeypatch.setattr(sheet.report,'insert',original)
    assert sheet.load_saved();pump(root,lambda:sheet.saved_token is None)
    assert app._timesheet_attempt.candidate.export_id==c.export_id


def test_real_tk_actual_commit_then_failed_independent_probe_cannot_publish(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app);c=refresh(app,sheet);dest=tmp_path/'uncertain.txt'
    choose(monkeypatch,sheet,str(dest));original=TimerService.execute;probe=SQLiteStore._probe;injected=[]
    def execute(self,request):
        if request.operation=='register_timesheet_export' and not injected:
            injected.append(True);self.store.connection=FaultConnection(self.store.connection,after=True)
        return original(self,request)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'execute',execute)
        m.setattr(SQLiteStore,'_probe',lambda *a:(_ for _ in ()).throw(OSError('independent probe unavailable')))
        assert sheet.save();pump(root,lambda:app.pending is not None and not app.executing)
        request=app.pending
        assert app._timesheet_attempt.registration=='unverified' and not dest.exists()
    assert sheet.retry_save();settled(app)
    assert app._timesheet_attempt.request is request and dest.read_bytes()==c.report_utf8
    assert app._timesheet_attempt.candidate.export_id==c.export_id


def test_real_tk_modal_return_error_remains_primary_when_controls_also_fail(connected,root,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app)
    primary=RuntimeError('modal return failed');secondary=RuntimeError('controls failed afterward')
    original=sheet.controls;calls=[]
    def controls():
        calls.append(True)
        if len(calls)>1:raise secondary
        original()
    with monkeypatch.context() as m:
        m.setattr(sheet,'restore_modal',lambda *a:(_ for _ in ()).throw(primary))
        m.setattr(sheet,'controls',controls)
        with pytest.raises(RuntimeError) as caught:sheet.dialog(lambda:None)
        assert caught.value is primary and any('controls failed afterward' in note for note in primary.__notes__)
    assert not sheet.is_busy() and not app.executing
