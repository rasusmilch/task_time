"""Connected preview controls/worker/service, with separately named server input evidence."""
from copy import deepcopy
from datetime import timedelta
import threading
import tkinter as tk

import pytest

from chronicle.records import Outcome
from chronicle.services import TimerService
from chronicle.timesheet_window import TimesheetWindow
from chronicle.worker import Message
from conftest import archive, NOW,uid
from test_app import root,connected,click,keyboard,pump,create,evidence
from test_chronicle_history_ui import mutation,selected_task,seed
from test_chronicle_history_operator import choose_combo


def open_sheet(app):
    assert app.open_timesheet()
    sheet=app.timesheet
    pump(app.root,lambda:sheet.presented and sheet.choices_token is None)
    assert app.root.grab_current() is sheet.window
    return sheet


def refresh(app,sheet):
    assert sheet.refresh_preview()
    pump(app.root,lambda:sheet.preview_token is None)
    assert sheet.current, sheet.status.cget('text')
    return sheet.candidate


def test_real_tk_preview_defaults_no_open_clock_read_only_exact_and_dirty(connected,root):
    app,worker,clock=connected;task=selected_task(app);seed(app,task)
    before=evidence(worker);calls=clock.calls
    sheet=open_sheet(app)
    assert clock.calls==calls and sheet.load_state=='Not previewed'
    assert sheet.period.get()=='This week' and sheet.scope.get()=='All tasks'
    assert sheet.get_prepared_export() is None and sheet.report.get('1.0','end-1c')==''
    assert not app.open_timesheet() and not app.open_history() and not app.start() and not app.add_timed_work()
    assert clock.calls==calls and app.timesheet is sheet
    c=refresh(app,sheet)
    assert clock.calls==calls+1 and sheet.report.get('1.0','end-1c')==c.report_text
    assert str(sheet.report.cget('state'))=='disabled'
    sheet.report.insert('1.0','forged');assert sheet.report.get('1.0','end-1c')==c.report_text
    assert 'Actual decimal | Suggested POL-R' in c.report_text
    assert 'Full week:' in c.report_text and 'not confirmed with POL-R' in c.report_text
    assert sheet.preview_button.cget('text')=='Refresh Preview'
    old=c.content(); token=app._token
    sheet.period.set('Last week');sheet.period.set('This week')
    assert not sheet.current and sheet.get_prepared_export() is None and app._token==token
    assert 'Previous preview' in sheet.context.cget('text') and sheet.candidate.content()==old
    c2=refresh(app,sheet)
    assert c2.export_id!=c.export_id and c.content()==old
    assert evidence(worker)==before
    assert not any(child.cget('text') in ('Save','Export','Confirm') for child in sheet.window.winfo_children() if isinstance(child,tk.ttk.Button))
    sheet.close();assert app.timesheet is None
    assert app.open_timesheet();fresh=app.timesheet
    pump(root,lambda:fresh.choices_token is None and fresh.presented)
    assert fresh is not sheet and fresh.candidate is None and fresh.load_state=='Not previewed'


def test_real_tk_selected_custom_uuid_scope_empty_rejection_and_calendar_draft_only(connected,root):
    app,worker,clock=connected;task=selected_task(app);second=create(app,'Same');seed(app,task)
    mutation(app,'add_date_only_work',task_id=second,entry_id=uid(),work_date='2026-10-20',duration_text='1:07',comment='')
    sheet=open_sheet(app);before=evidence(worker)
    sheet.scope.set('Selected tasks')
    calls=clock.calls
    assert not sheet.refresh_preview() and clock.calls==calls
    assert 'at least one' in sheet.status.cget('text')
    sheet.tasks.selection_set(second);sheet.period.set('Custom')
    sheet.start.set(' 2026-10-20 ');sheet.end.set('2026-10-20')
    c=refresh(app,sheet)
    assert c.selected_task_ids==(second,) and {x.task_id for x in c.cells}=={second}
    assert len(c.basis)==7 and len(c.cells)==1
    before_picker=app._token;assert sheet.open_picker(sheet.start)
    sheet._choose_day(21)
    assert sheet.start.get()=='2026-10-21' and app._token==before_picker and not sheet.current
    assert sheet.open_picker(sheet.end);draft=sheet.end.get();sheet._escape()
    assert sheet.end.get()==draft and sheet.picker is None and not sheet.disposed
    assert root.grab_current() is sheet.window and evidence(worker)==before
    assert sheet.refresh_preview();pump(root,lambda:sheet.preview_token is None)
    assert not sheet.current and sheet.start.get()=='2026-10-21' and sheet.candidate==c


def test_real_tk_empty_all_failure_recovery_and_original_diagnostics(connected,root,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app)
    empty=refresh(app,sheet)
    assert not empty.tasks and sheet.load_state=='Previewed empty All'
    fault=OSError('read fault')
    with monkeypatch.context() as m:
        m.setattr(TimerService,'prepare_timesheet_preview',lambda *a,**kw:(_ for _ in ()).throw(fault))
        assert sheet.refresh_preview();pump(root,lambda:sheet.preview_token is None)
    assert sheet.candidate==empty and not sheet.current and sheet.load_state=='Preview failed'
    assert root.test_errors[-1][1] is fault and 'Previous preview' in sheet.context.cget('text')
    assert refresh(app,sheet).export_id!=empty.export_id and sheet.current


def test_real_tk_render_failure_hides_partial_output_then_recovers(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);sheet=open_sheet(app);first=refresh(app,sheet)
    original=sheet.report.insert;fault=RuntimeError('partial widget failure')
    def broken(*a,**kw):original('1.0','partial');raise fault
    with monkeypatch.context() as m:
        m.setattr(sheet.report,'insert',broken)
        assert sheet.refresh_preview();pump(root,lambda:sheet.preview_token is None)
    assert not sheet.current and not sheet.report.winfo_ismapped() and sheet.candidate==first
    assert root.test_errors[-1][1] is fault
    fresh=refresh(app,sheet);assert sheet.report.winfo_ismapped()
    assert sheet.report.get('1.0','end-1c')==fresh.report_text


def test_real_tk_changed_drafts_and_closed_sessions_reject_late_read(connected,root,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app)
    # Return a real candidate but deliver it after this draft generation was invalidated.
    c=refresh(app,sheet);sheet.current=False
    sheet.preview_token=981;sheet.attempt={'export_id':c.export_id,'cutoff_utc_us':c.cutoff_utc_us}
    sheet.start.set('2026-10-01')
    sheet.receive_preview(981,c);assert not sheet.current
    sheet.close();fresh=open_sheet(app)
    app._handle(Message('timesheet_preview',981,c))
    assert fresh.candidate is None
    assert fresh.refresh_preview()
    token=fresh.preview_token;fresh.close()
    pump(root,lambda:app.timesheet is None and app._read_inflight is None)
    assert not app._timesheet_opening


@pytest.mark.parametrize('damage',['dataset','identity','cutoff'])
def test_real_tk_candidate_identity_must_match_request(connected,root,damage):
    app,worker,clock=connected;sheet=open_sheet(app);candidate=refresh(app,sheet)
    sheet.preview_token=888
    sheet.attempt=dict(export_id=candidate.export_id,cutoff_utc_us=candidate.cutoff_utc_us)
    # Modify expected delivery context; do not forge a candidate or skip structural validation.
    if damage=='dataset':app.dataset_id=uid()
    if damage=='identity':sheet.attempt['export_id']=uid()
    if damage=='cutoff':sheet.attempt['cutoff_utc_us']+=1
    sheet.current=False;sheet.receive_preview(888,candidate)
    assert not sheet.current and sheet.load_state=='Preview failed'


def test_real_tk_timesheet_origin_return_competing_grab_destroy_and_reentry(connected,root,monkeypatch):
    app,worker,clock=connected
    root.grab_set();app.tree.focus_set();pump(root,lambda:root.focus_get() is app.tree)
    sheet=open_sheet(app)
    assert app._timesheet_return==(root,root,app.tree)
    assert not app.open_timesheet()
    sheet.close();assert root.grab_current() is root
    pump(root,lambda:root.focus_get() is app.tree)
    sheet=open_sheet(app)
    other=tk.Toplevel(root);other.grab_set();other.focus_set()
    sheet.close();assert root.grab_current() is other
    assert not app.open_timesheet() and root.grab_current() is other
    other.destroy();root.grab_release()
    # Child destruction cannot dispose ownership; delayed callbacks cannot clear a newer one.
    fresh=open_sheet(app);label=tk.ttk.Label(fresh.window);label.destroy()
    assert app.timesheet is fresh
    app._timesheet_disposed(sheet);assert app.timesheet is fresh
    fresh.window.destroy();assert app.timesheet is None
    assert not app._timesheet_opening


@pytest.mark.parametrize('phase',['construct','present','map_grab'])
def test_real_tk_timesheet_launch_failures_cleanup_guard_and_reopen(connected,root,monkeypatch,phase):
    app,worker,clock=connected;fault=RuntimeError('launch failure')
    with monkeypatch.context() as m:
        if phase=='construct':m.setattr(TimesheetWindow,'_build',lambda s:(_ for _ in ()).throw(fault))
        elif phase=='present':m.setattr(TimesheetWindow,'present',lambda s:(_ for _ in ()).throw(fault))
        else:
            original=TimesheetWindow.present
            def conflict(s):
                s.window.grab_set=lambda:(_ for _ in ()).throw(fault)
                original(s)
            m.setattr(TimesheetWindow,'present',conflict)
        app.open_timesheet();pump(root,lambda:not app._timesheet_opening)
    assert app.timesheet is None and root.test_errors[-1][1] is fault
    assert root.grab_current() is None
    assert open_sheet(app)


def test_real_tk_map_competitor_not_stolen_and_root_shutdown_cleans_picker(connected,root):
    app,worker,clock=connected
    assert app.open_timesheet();sheet=app.timesheet
    other=tk.Toplevel(root);other.grab_set()
    pump(root,lambda:not app._timesheet_opening)
    assert app.timesheet is None and root.grab_current() is other
    other.destroy();sheet=open_sheet(app)
    sheet.period.set('Custom');sheet.start.set('2026-10-19');sheet.open_picker(sheet.start)
    app.request_close();assert app.alive and app.timesheet is sheet
    root.destroy();assert sheet.disposed and app.timesheet is None and sheet.picker is None
    worker.join(timeout=8);assert not worker.is_alive()


def test_real_tk_worker_routes_preview_registration_list_recovery_and_ui_thread(connected,root,monkeypatch):
    app,worker,clock=connected;selected_task(app);threads=[];original=TimerService.prepare_timesheet_preview
    def observe(*a,**kw):threads.append(threading.get_ident());return original(*a,**kw)
    monkeypatch.setattr(TimerService,'prepare_timesheet_preview',observe)
    sheet=open_sheet(app);candidate=refresh(app,sheet)
    assert threads==[worker.ident] and worker.ident!=threading.get_ident()
    sheet.close()
    # Registration is a real backend foundation, deliberately not a preview control.
    assert app._submit('register_timesheet_export',candidate=candidate.content())
    pump(root,lambda:app.pending is None and app._read_inflight is None)
    delivered=[];original_handle=app._handle
    def handle(msg):
        if msg.kind in ('timesheet_exports','timesheet_export'):delivered.append(msg)
        else:original_handle(msg)
    monkeypatch.setattr(app,'_handle',handle)
    worker.requests.put(Message('timesheet_exports',1024,None))
    worker.requests.put(Message('timesheet_export',1025,candidate.export_id))
    pump(root,lambda:len(delivered)==2)
    assert delivered[0].value[0]['export_id']==candidate.export_id and delivered[1].value==candidate


def test_real_tk_server_production_timesheet_preview_calendars_modal_and_timer(connected,root,click,keyboard):
    app,worker,clock=connected;task=selected_task(app);seed(app,task)
    clock.value-=timedelta(minutes=3)
    assert app.start();pump(root,lambda:app.pending is None and app.state['active'] is not None)
    clock.value+=timedelta(minutes=3)
    click(app.buttons['Mini mode']);mini=app.mini
    # Place enabled input probes in exposed main/mini regions, separate from disabled controls.
    hits=[]
    main_probe=tk.ttk.Button(root,text='Main input probe',command=lambda:hits.append('main'));main_probe.grid(row=8,column=0,sticky='w')
    mini_probe=tk.ttk.Button(mini.window,text='Mini input probe',command=lambda:hits.append('mini'));mini_probe.pack()
    root.geometry('950x650+0+0');mini.window.geometry('340x240+900+540')
    click(app.buttons['Timesheet / POL-R']);sheet=app.timesheet
    sheet.window.geometry('850x620+250+0')
    pump(root,lambda:sheet.presented and sheet.choices_token is None)
    before=evidence(worker);active=deepcopy(app.state['active'])
    assert sheet.candidate is None and root.grab_current() is sheet.window
    click(main_probe);click(mini_probe)
    assert hits==[] and app.state['active']==active
    tick=[];root.after(20,lambda:tick.append(True));pump(root,lambda:tick)
    click(sheet.preview_button);pump(root,lambda:sheet.current)
    c=sheet.candidate
    assert c.cutoff_utc_us==NOW and sheet.report.get('1.0','end-1c')==c.report_text
    clock.value+=timedelta(minutes=1)
    pump(root,lambda:app.state['cutoff_utc_us']==NOW+60_000_000)
    assert sheet.candidate is c and c.cutoff_utc_us==NOW and app.state['active']==active
    choose_combo(root,sheet.period_control,2,click,keyboard)
    keyboard[1](sheet.date_controls[0],'2026-10-19')
    keyboard[1](sheet.date_controls[2],'2026-10-20')
    click(sheet.date_controls[1]);pump(root,lambda:sheet.picker is not None)
    click(sheet.day_buttons[20]);assert sheet.start.get()=='2026-10-20'
    click(sheet.date_controls[3]);keyboard[0]('Escape');pump(root,lambda:sheet.picker is None)
    assert sheet.picker is None and not sheet.disposed and root.grab_current() is sheet.window
    assert not sheet.current and 'Previous preview' in sheet.context.cget('text')
    # Actual Selected scope pointer selection, not inferred task names.
    choose_combo(root,sheet.scope_control,1,click,keyboard)
    sheet.tasks.see(task);pump(root,lambda:bool(sheet.tasks.bbox(task)))
    x,y,w,h=sheet.tasks.bbox(task);click(sheet.tasks,(x+20,y+h//2))
    pump(root,lambda:sheet.tasks.selection()==(task,))
    click(sheet.preview_button);pump(root,lambda:sheet.current)
    assert sheet.candidate.selected_task_ids==(task,) and len(sheet.candidate.cells)==1
    assert sheet.candidate.export_id!=c.export_id and evidence(worker)==before
    click(sheet.close_button);assert app.timesheet is None
    click(main_probe);click(mini_probe);assert hits==['main','mini']
    assert not root.test_errors


def test_real_tk_choice_labels_deleted_tasks_and_last_week_drafts(connected,root,monkeypatch):
    app,worker,clock=connected;first=selected_task(app);second=create(app,'Duplicate')
    original=TimerService.read_timesheet_task_choices
    def retained(self):
        # Explicit fixture mutation on the real owning worker, never a GUI SQL call.
        if not self.store.connection.execute('SELECT is_archived FROM tasks WHERE task_id=?',(second,)).fetchone()[0]:
            archive(self, 'task', second, now=0)
        return original(self)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'read_timesheet_task_choices',retained)
        sheet=open_sheet(app)
    assert sheet.tasks.item(second,'values')[-1]=='Archived'
    assert second in sheet.tasks.item(second,'values')[0]
    sheet.start.set('invalid draft');sheet.end.set('another draft');sheet.period.set('Last week')
    c=refresh(app,sheet)
    assert c.start_date=='2026-10-11' and c.end_date=='2026-10-17'
    assert sheet.start.get()=='invalid draft' and sheet.end.get()=='another draft'
    sheet.scope.set('Selected tasks');sheet.tasks.selection_set(second)
    c=refresh(app,sheet)
    assert c.selected_task_ids==(second,) and not c.tasks[0].is_deleted


def test_real_tk_close_during_loading_and_newer_attempt_wins(connected,root,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app)
    entered,gate=threading.Event(),threading.Event()
    original=TimerService.prepare_timesheet_preview
    calls=[]
    def slow(self,**kw):
        calls.append(kw)
        if len(calls)==1:
            entered.set();assert gate.wait(5)
        return original(self,**kw)
    with monkeypatch.context() as m:
        m.setattr(TimerService,'prepare_timesheet_preview',slow)
        assert sheet.refresh_preview();first=sheet.attempt['export_id']
        assert entered.wait(2)
        sheet.period.set('Last week');assert sheet.refresh_preview();newest=sheet.attempt['export_id']
        assert newest!=first and sheet.load_state=='Loading'
        gate.set();pump(root,lambda:sheet.current)
        assert sheet.candidate.export_id==newest and len(calls)==2
        gate.clear();calls.clear();entered.clear()
        assert sheet.refresh_preview();assert entered.wait(2)
        sheet.close();fresh=None
        # Do not wait for task choices while the intentionally blocked read holds the worker.
        assert app.open_timesheet();fresh=app.timesheet
        gate.set();pump(root,lambda:fresh.presented and fresh.choices_token is None)
        assert fresh.candidate is None and fresh.load_state=='Not previewed'


def test_real_tk_global_grab_and_deleted_focus_origin_are_not_replaced(connected,root):
    app,worker,clock=connected
    other=tk.Toplevel(root);other.deiconify()
    pump(root,lambda:other.winfo_viewable())
    other.grab_set_global()
    assert not app.open_timesheet() and root.grab_current() is other and other.grab_status()=='global'
    other.destroy()
    field=tk.ttk.Entry(root);field.grid(row=8,column=0);field.focus_set()
    pump(root,lambda:root.focus_get() is field)
    sheet=open_sheet(app);field.destroy();sheet.close()
    pump(root,lambda:root.focus_get() is root)
    assert root.grab_current() is None


def test_real_tk_return_guard_and_primary_cleanup_diagnostics(connected,root,monkeypatch):
    app,worker,clock=connected;sheet=open_sheet(app)
    original=app._restore_timesheet_origin;seen=[]
    def return_context():
        assert app._timesheet_opening and app.timesheet is None
        seen.append(app.open_timesheet())
        original()
    monkeypatch.setattr(app,'_restore_timesheet_origin',return_context)
    sheet.close();assert seen==[False] and not app._timesheet_opening
    primary=RuntimeError('primary presentation failure');secondary=RuntimeError('cleanup failure')
    with monkeypatch.context() as m:
        m.setattr(TimesheetWindow,'present',lambda s:(_ for _ in ()).throw(primary))
        m.setattr(app,'_restore_timesheet_origin',lambda:(_ for _ in ()).throw(secondary))
        assert not app.open_timesheet()
    assert root.test_errors[-1][1] is primary
    assert any('cleanup failure' in note for note in primary.__notes__)
    assert app.timesheet is None and not app._timesheet_opening
