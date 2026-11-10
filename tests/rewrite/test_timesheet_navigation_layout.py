"""Production schema-4 navigation, exact evidence and mapped WM geometry."""
from copy import deepcopy
from datetime import timedelta
import json
import tkinter as tk
from tkinter import ttk
import pytest

from chronicle.records import Outcome
from chronicle.worker import DatabaseWorker
from chronicle import project_ui as ui
from conftest import uid
from test_app import root, pump, Clock
from test_runtime4_ui import ordinary
from test_schema4_project_modal import project, task, submit
from test_backup_restore import logical
from test_chronicle_timesheet_ui import open_sheet, refresh
from test_timesheet_save_ui import choose, settled, saved_reports
from test_polr_confirmation_ui import reviewed, manual_review
from test_reconciliation_ui import reconciled, row
from tk_observation import wait_observed

DAY='2026-10-19'


def seed(ordinary, count=1, long=False):
    app,worker,places=ordinary
    assert type(worker) is DatabaseWorker and worker.is_alive()
    assert app.presentation_profile=='schema4' and app.state['semantic_verified'] and app.state['ordinary_startup_permitted']
    clock=Clock();app.now_utc=clock
    group=project(app,project(app));keys=[]
    for i in range(count):
        key=task(app,group);keys.append(key)
        if long:submit(app,'rename_task',task_id=key,name='Duplicate ü Ω '+('Long task name '*12),expected_version=1)
        submit(app,'add_date_only_work',task_id=key,entry_id=uid(),work_date=DAY,duration_text='0:03',comment='navigation evidence')
        submit(app,'add_date_only_work',task_id=key,entry_id=uid(),work_date='2026-10-20',duration_text='0:03',comment='worked zero suggestion')
    return app,worker,places,keys,clock


def facts(places):return logical(places.folder/'chronicle.sqlite3')


def register(app, sheet, monkeypatch, tmp_path):
    c=refresh(app,sheet);choose(monkeypatch,sheet,str(tmp_path/'report.txt'))
    assert sheet.save();settled(app)
    assert app._timesheet_attempt.registration=='committed'
    return c


def exclusive(sheet):
    sheet.window.update_idletasks()
    panels=(sheet.timesheet_panel,sheet.saved_panel,sheet.polr_panel,sheet.reconciliation_panel)
    mapped=[p for p in panels if p.winfo_ismapped()]
    expected={'preview':sheet.timesheet_panel,'saved':sheet.saved_panel,'reconciliation':sheet.reconciliation_panel}.get(sheet.mode,sheet.polr_panel)
    assert mapped==[expected]
    assert sheet.window.grab_current() is sheet.window


def test_ordinary_defaults_manual_and_direct_reconciliation_have_no_report(ordinary):
    app,w,places,keys,clock=seed(ordinary);sheet=open_sheet(app);before=facts(places)
    assert sheet.mode=='preview' and sheet.period.get()=='This week' and sheet.scope.get()=='All tasks'
    assert sheet.candidate is None and app._timesheet_attempt is None
    sheet.reconciliation_button.invoke();result=reconciled(app,sheet);exclusive(sheet)
    assert result['source_comparison'] is None and result['coverage']['UNKNOWN']==2
    assert sheet.show_timesheet();manual_review(app,sheet,keys[0]);exclusive(sheet)
    assert sheet.candidate is None and app._timesheet_attempt is None
    assert sheet.defer_polr() and sheet.mode=='preview' and facts(places)==before
    assert not app.root.test_errors


def test_ordinary_applied_scope_drafts_selection_cancel_and_success_return(ordinary):
    app,w,places,keys,clock=seed(ordinary,2);sheet=open_sheet(app)
    assert sheet.open_reconciliation();reconciled(app,sheet)
    sheet.reconciliation_period.set('Custom');sheet.reconciliation_start.set(DAY);sheet.reconciliation_end.set(DAY)
    sheet.reconciliation_scope.set('Selected tasks');sheet.reconciliation_tasks.selection_set(keys[0])
    assert sheet.refresh_reconciliation();reconciled(app,sheet)
    handle,_=row(sheet,keys[0]);sheet.reconciliation_tree.selection_set(handle)
    before=facts(places);applied=deepcopy(sheet.reconciliation_applied)
    # Drafts deliberately disagree with the last applied result, including invalid dates.
    sheet.reconciliation_start.set('not an applied date');sheet.reconciliation_tasks.selection_set(keys[1])
    assert sheet.open_reconciliation() and sheet.reconciliation_applied==applied
    assert sheet.reconciliation_start.get()=='not an applied date'
    assert sheet.reconciliation_manual_action();reviewed(app,sheet)
    assert sheet.polr_manual_key==(keys[0],DAY)
    assert not sheet.close() and not sheet.show_timesheet() and not sheet.saved_reports()
    protocol=sheet.window.protocol('WM_DELETE_WINDOW');sheet.window.tk.call(protocol);sheet._escape()
    assert not sheet.disposed and sheet.mode=='confirmation_manual' and facts(places)==before
    assert sheet.defer_polr();r=reconciled(app,sheet)
    assert r['start_date']==DAY and r['selected_task_ids']==[keys[0]]
    assert sheet.reconciliation_start.get()=='not an applied date'
    assert sheet.reconciliation_tasks.selection()==(keys[1],)
    assert sheet._row_key()==(keys[0],DAY) and facts(places)==before
    assert sheet.reconciliation_applied['task_ids']==applied['task_ids']
    assert sheet.reconciliation_manual_action();reviewed(app,sheet)
    sheet.polr_hours.set('0.25');assert sheet.confirm_polr();reviewed(app,sheet)
    request=app._polr_submission.request;batch=app._polr_submission.outcome.result['batch_id'];after=facts(places)
    assert batch in sheet.polr_status.cget('text') and sheet.mode=='confirmation_manual'
    assert not sheet.confirm_polr() and app._polr_submission.request is request and facts(places)==after
    assert not sheet.open_reconciliation() and not sheet.confirmation_history()
    assert sheet.defer_polr();r=reconciled(app,sheet)
    assert sheet._row_key()==(keys[0],DAY) and row(sheet,keys[0])[1]['confirmed_quarters']==1
    assert sheet.reconciliation_start.get()=='not an applied date' and r['start_date']==DAY
    sheet.reconciliation_confirm.invoke();reviewed(app,sheet)
    assert sheet.polr_batch_id==batch and batch in sheet.polr_detail.get('1.0','end')
    assert sheet.defer_polr();reconciled(app,sheet);assert facts(places)==after
    # Reapplying a relative period after a week rollover removes the old row.
    sheet.reconciliation_period.set('This week');sheet.reconciliation_scope.set('All tasks')
    assert sheet.refresh_reconciliation();reconciled(app,sheet)
    h,_=row(sheet,keys[0]);sheet.reconciliation_tree.selection_set(h)
    assert sheet.reconciliation_manual_action();reviewed(app,sheet)
    clock.value+=timedelta(days=8)
    assert sheet.defer_polr();reconciled(app,sheet)
    assert not sheet.reconciliation_tree.selection() and facts(places)==after
    assert not app.root.test_errors


def test_ordinary_source_zero_frozen_return_and_read_generations(ordinary,tmp_path,monkeypatch):
    app,w,places,keys,clock=seed(ordinary);sheet=open_sheet(app);c=register(app,sheet,monkeypatch,tmp_path)
    before=facts(places);attempt=app._timesheet_attempt
    assert sheet.saved_reports();pump(app.root,lambda:sheet.saved_token is None)
    assert app._timesheet_attempt is attempt and facts(places)==before
    assert sheet.show_timesheet();assert sheet.review_polr();reviewed(app,sheet)
    assert c.export_id in sheet.polr_explanation.cget('text')
    assert sheet.polr_selected=={(keys[0],DAY)}
    assert not sheet.show_timesheet() and not sheet.saved_reports() and not sheet.new_preview() and not sheet.close()
    sheet._escape();assert not sheet.disposed and facts(places)==before
    old=deepcopy(sheet.polr_proposal);token=app._token
    assert sheet.defer_polr() and sheet.mode=='preview'
    sheet.receive_polr('polr_proposal',token,old);assert facts(places)==before
    assert sheet.review_polr();reviewed(app,sheet)
    assert sheet.toggle_polr_cell((keys[0],'2026-10-20'))
    assert sheet.confirm_polr();reviewed(app,sheet);after=facts(places)
    assert len(after['polr_confirmation_cells'])==2
    assert after['timesheet_exports']==before['timesheet_exports'] and c.report_utf8==(tmp_path/'report.txt').read_bytes()
    assert not sheet.confirm_polr() and sheet._polr_completed
    assert not sheet.mutation_allowed()
    assert not app._polr_submit(sheet,app._polr_submission.request.args())
    assert not sheet.toggle_polr_cell((keys[0],DAY)) and not sheet.polr_positive()
    assert sheet.defer_polr() and sheet.mode=='preview'
    assert not sheet.polr_ready
    assert sheet.open_reconciliation();r=reconciled(app,sheet)
    assert row(sheet,keys[0],'2026-10-20')[1]['confirmed_quarters']==0
    assert r['coverage']['UNKNOWN']==0 and facts(places)==after
    old=deepcopy(r);oldtoken=app._token
    assert sheet.saved_reports();pump(app.root,lambda:sheet.saved_token is None)
    sheet.receive_reconciliation(oldtoken,old);exclusive(sheet);assert facts(places)==after
    assert not app.root.test_errors


@pytest.mark.parametrize('failure',['read','render','result'])
def test_ordinary_known_commit_survives_followup_read_failure(ordinary,monkeypatch,failure):
    from chronicle.schema4_runtime_service import Schema4RuntimeService
    app,w,places,keys,clock=seed(ordinary);sheet=open_sheet(app);manual_review(app,sheet,keys[0])
    fault=ValueError('follow-up context unavailable')
    with monkeypatch.context() as m:
        target,name=(Schema4RuntimeService,'read_polr_manual_context') if failure=='read' else (sheet,'polr_result' if failure=='result' else '_show_day_status')
        m.setattr(target,name,lambda *a,**kw:(_ for _ in ()).throw(fault))
        sheet.polr_hours.set('1.25');assert sheet.confirm_polr();reviewed(app,sheet)
    batch=app._polr_submission.outcome.result['batch_id']
    assert batch in sheet.polr_explanation.cget('text') and app._polr_submission.outcome.status=='committed'
    assert not sheet.mutation_allowed()
    assert not sheet.confirm_polr() and sheet.defer_polr() and sheet.mode=='preview'
    assert app.root.test_errors[-1][1] is fault


def box(widget):return (widget.winfo_rootx(),widget.winfo_rooty(),widget.winfo_width(),widget.winfo_height())


def geometry(sheet,tree,records):
    sheet.window.update_idletasks();exclusive(sheet)
    panel=tree.master;bars=[w for w in panel.winfo_children() if isinstance(w,ttk.Scrollbar)]
    vertical=next(w for w in bars if str(w.cget('orient'))=='vertical')
    horizontal=next(w for w in bars if str(w.cget('orient'))=='horizontal')
    x,y,w,h=box(tree);vx,vy,vw,vh=box(vertical)
    assert tree.winfo_ismapped() and w>100 and h>40
    assert 0<=vx-(x+w)<=4 and abs(vy-y)<=4 and abs(vh-h)<=4
    assert horizontal.winfo_ismapped() and box(horizontal)[1]>=y+h
    wx,wy,ww,wh=box(sheet.window)
    for control in (sheet.navigation,sheet.content_host,sheet.footer,sheet.close_button,tree,vertical,horizontal):
        a,b,c,d=box(control);assert control.winfo_ismapped() and c>0 and d>0
        assert wx<=a and wy<=b and a+c<=wx+ww+4 and b+d<=wy+wh+4
    assert box(sheet.navigation)[1]+box(sheet.navigation)[3]<=box(sheet.content_host)[1]
    assert box(sheet.content_host)[1]+box(sheet.content_host)[3]<=box(sheet.footer)[1]
    def descendants(parent):
        for child in parent.winfo_children():
            yield child;yield from descendants(child)
    actions=[c for c in descendants(sheet.window) if isinstance(c,ttk.Button) and c.winfo_ismapped()]
    for control in actions+[sheet.status,sheet.saved_status,sheet.polr_status,sheet.reconciliation_status]:
        if not control.winfo_ismapped():continue
        a,b,c,d=box(control)
        assert wx<=a and wy<=b and a+c<=wx+ww+4 and b+d<=wy+wh+4,(str(control),box(control),box(sheet.window))
    rows={key:tree.item(key,'values') for key in tree.get_children()}
    tree.xview_moveto(1);sheet.window.update_idletasks()
    if tree.get_children():assert tree.bbox(tree.get_children()[0],tree['columns'][-1])
    assert {key:tree.item(key,'values') for key in tree.get_children()}==rows
    tree.xview_moveto(0)
    records.append(dict(mode=sheet.mode,window=box(sheet.window),host=box(sheet.content_host),table=box(tree),vertical=box(vertical),horizontal=box(horizontal),close=box(sheet.close_button)))


@pytest.mark.parametrize('size',['980x740','800x620'])
@pytest.mark.parametrize('many',[False,True])
def test_ordinary_mapped_geometry_scroll_and_exclusive_views(ordinary,tmp_path,monkeypatch,size,many):
    app,w,places,keys,clock=seed(ordinary,8 if many else 1,long=many)
    sheet=open_sheet(app);sheet.window.geometry(size)
    wait_observed(app.root,lambda:sheet.window.winfo_width()==int(size.split('x')[0]) and sheet.window.winfo_height()==int(size.split('x')[1]),phase='Timesheet exact test geometry',widgets=(sheet.window,))
    records=[];geometry(sheet,sheet.tasks,records)
    c=register(app,sheet,monkeypatch,tmp_path)
    # Real later confirmations create genuine, independently operable stale cells.
    if many:
        for key in keys:
            manual_review(app,sheet,key);sheet.polr_hours.set('1.00');assert sheet.confirm_polr();reviewed(app,sheet)
            assert sheet.defer_polr()
    before=facts(places)
    assert sheet.saved_reports();pump(app.root,lambda:sheet.saved_token is None);geometry(sheet,sheet.saved_list,records)
    sheet.saved_list.selection_set(c.export_id);assert sheet.load_saved();pump(app.root,lambda:sheet.saved_token is None)
    assert sheet.mode=='preview' and not sheet.current;exclusive(sheet)
    assert sheet.report.winfo_ismapped() and sheet.report.winfo_height()>40
    assert sheet.review_polr();reviewed(app,sheet);geometry(sheet,sheet.polr_tree,records)
    if many:
        assert len(sheet.polr_acks)==len(keys)
        canvas=sheet.polr_ack_frame.master
        for _,(var,button) in sheet.polr_acks.items():
            sheet.window.update_idletasks();canvas.yview_moveto(button.winfo_y()/max(1,sheet.polr_ack_frame.winfo_height()));canvas.xview_moveto(0)
            sheet.window.update_idletasks()
            bx,by,bw,bh=box(button);cx,cy,cw,ch=box(canvas)
            assert button.winfo_ismapped() and cx<=bx<cx+cw and cy<=by and by+bh<=cy+ch
            button.invoke();assert var.get();button.invoke();assert not var.get()
        canvas.xview_moveto(1);sheet.window.update_idletasks()
        assert canvas.canvasx(canvas.winfo_width())>=sheet.polr_ack_frame.winfo_width()-4
        assert canvas.xview()[0]>0 and canvas.yview()[0]>0  # Both axes genuinely scrolled to their far edge.
    assert sheet.defer_polr();assert sheet.open_reconciliation();reconciled(app,sheet);geometry(sheet,sheet.reconciliation_tree,records)
    assert sheet.reconciliation_tree.winfo_height()>sheet.reconciliation_summary.winfo_height()
    assert sheet.show_timesheet();manual_review(app,sheet,keys[0]);sheet.window.update_idletasks();exclusive(sheet)
    assert not sheet.polr_table_holder.winfo_ismapped() and sheet.polr_detail.winfo_height()>40
    assert sheet.defer_polr();assert sheet.confirmation_history();reviewed(app,sheet);geometry(sheet,sheet.polr_tree,records)
    if many:
        batch=sheet.polr_tree.get_children()[-1];sheet.polr_tree.selection_set(batch);assert sheet.load_polr_batch();reviewed(app,sheet)
        assert batch in sheet.polr_detail.get('1.0','end')
    previous=sheet.polr_tree.winfo_height();other='800x620' if size=='980x740' else '980x740'
    sheet.window.geometry(other)
    wait_observed(app.root,lambda:sheet.window.winfo_width()==int(other.split('x')[0]) and sheet.window.winfo_height()==int(other.split('x')[1]),phase='Timesheet resize growth',widgets=(sheet.window,))
    geometry(sheet,sheet.polr_tree,records)
    assert (sheet.polr_tree.winfo_height()-previous)*(int(other.split('x')[1])-int(size.split('x')[1]))>0
    assert facts(places)==before and not app.root.test_errors
    (tmp_path/'geometry.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')


def test_ordinary_pending_and_real_uncertainty_retain_exact_request(ordinary,monkeypatch):
    import threading
    from chronicle.sqlite_store import SQLiteStore
    from test_runtime4_store import Fault
    app,w,places,keys,clock=seed(ordinary);sheet=open_sheet(app);manual_review(app,sheet,keys[0])
    transact=SQLiteStore.transact;entered=threading.Event();release=threading.Event();fired=[]
    def failure(self,request,operation):
        if request.operation=='confirm_polr_absolute' and not fired:
            entered.set();assert release.wait(5);fired.append(request)
            self.connection=Fault(self.connection,'after')
        return transact(self,request,operation)
    with monkeypatch.context() as m:
        m.setattr(SQLiteStore,'transact',failure)
        m.setattr(SQLiteStore,'_probe',lambda *a:(_ for _ in ()).throw(OSError('independent receipt temporarily unavailable')))
        sheet.polr_hours.set('0.00');assert sheet.confirm_polr();pump(app.root,entered.is_set)
        request=app.pending
        try:
            assert not sheet.close() and not sheet.defer_polr() and not sheet.saved_reports() and not sheet.confirm_polr()
            sheet._escape();assert app.pending is request and not sheet.disposed
        finally:release.set()
        pump(app.root,lambda:not app.executing)
        assert app.pending is request and app._polr_submission.outcome.status=='unverified'
        assert not sheet.open_reconciliation() and not sheet.confirmation_history() and not sheet.show_timesheet()
        assert not sheet.close() and not sheet.defer_polr() and sheet.polr_hours_control.instate(['disabled'])
        committed=facts(places);assert len(committed['polr_confirmation_batches'])==1
    assert sheet.retry_polr();reviewed(app,sheet)
    assert app._polr_submission.request is request and app._polr_submission.outcome.status=='committed'
    assert facts(places)==committed and sheet.defer_polr()
    assert fired==[request]


def test_ordinary_restart_recovers_missing_file_without_preview_or_resave(ordinary,tmp_path,monkeypatch):
    from chronicle.startup import StartupWindow
    from chronicle.app import ChronicleApp
    from chronicle import launcher_selection as ls
    from test_timesheet_save_ui import exit_settled
    app,w,places,keys,clock=seed(ordinary);sheet=open_sheet(app);candidate=register(app,sheet,monkeypatch,tmp_path)
    expected=app._timesheet_attempt.candidate;before=facts(places)
    assert sheet.close();app.request_close();exit_settled(app);w.join(15);assert not w.is_alive()
    (tmp_path/'report.txt').unlink()
    fresh_root=tk.Tk();errors=[];fresh_root.test_errors=errors;fresh_root.report_callback_exception=lambda *args:errors.append(args)
    flow=None
    try:
        flow=StartupWindow(fresh_root,app_factory=lambda root,worker,**kw:ChronicleApp(root,worker,now_utc=clock,**kw),worker_factory=DatabaseWorker,locations=places)
        pump(fresh_root,lambda:flow.app is not None and flow.app.state.get('report') is not None)
        fresh=flow.app;assert fresh.presentation_profile=='schema4' and fresh.worker is not w
        sheet=open_sheet(fresh);assert sheet.mode=='preview' and sheet.candidate is None
        saved_reports(fresh,sheet,expected.export_id);exclusive(sheet)
        assert sheet.candidate==expected and sheet.report.get('1.0','end-1c')==candidate.report_text
        assert not (tmp_path/'report.txt').exists() and facts(places)==before
        assert sheet.review_polr();reviewed(fresh,sheet)
        assert sheet.polr_selected=={(keys[0],DAY)} and sheet.defer_polr()
        assert facts(places)==before and not errors
        assert sheet.close();fresh.request_close();exit_settled(fresh)
    finally:
        if flow is not None and flow.app is not None and flow.app.alive:fresh_root.destroy()
        if flow is not None and flow.worker is not None:flow.worker.join(15);assert not flow.worker.is_alive()


@pytest.mark.parametrize('registered',[False,True],ids=['preview','registered'])
def test_ordinary_saved_listing_read_failure_preserves_timesheet(ordinary,tmp_path,monkeypatch,registered):
    import threading
    from chronicle.schema4_runtime_service import Schema4RuntimeService
    app,worker,places,keys,clock=seed(ordinary);sheet=open_sheet(app)
    if registered:register(app,sheet,monkeypatch,tmp_path)
    else:refresh(app,sheet)
    candidate=sheet.candidate;attempt=app._timesheet_attempt;current=sheet.current
    text=sheet.report.get('1.0','end-1c');before=facts(places)
    file_bytes=(tmp_path/'report.txt').read_bytes() if registered else None
    save_ready=sheet.save_button.instate(['!disabled'])
    # A prior successful list must not remain loadable after a failed explicit refresh.
    assert sheet.saved_reports();pump(app.root,lambda:sheet.saved_token is None)
    assert sheet.show_timesheet() and not app.root.test_errors
    fault=OSError('authoritative registered-report listing unavailable');calls=[]
    def fail(service):
        assert type(service) is Schema4RuntimeService
        calls.append(threading.get_ident());raise fault
    with monkeypatch.context() as m:
        m.setattr(Schema4RuntimeService,'list_registered_timesheet_exports',fail)
        assert sheet.saved_reports();pump(app.root,lambda:sheet.saved_token is None)
    assert calls==[worker.ident] and app.root.test_errors==[(type(fault),fault,fault.__traceback__)]
    assert sheet.candidate is candidate and sheet.current is current
    assert sheet.report.winfo_manager()=='grid' and sheet.report.get('1.0','end-1c')==text
    assert str(fault) in sheet.saved_status.cget('text') and not sheet.saved_ready
    assert sheet.load_saved_button.instate(['disabled']) and not sheet.load_saved()
    assert sheet.show_timesheet();exclusive(sheet)
    assert sheet.candidate is candidate and sheet.current is current
    assert sheet.report.winfo_ismapped() and sheet.report.get('1.0','end-1c')==text
    assert app._timesheet_attempt is attempt and sheet.save_button.instate(['!disabled'])==save_ready
    assert facts(places)==before
    if registered:
        assert (tmp_path/'report.txt').read_bytes()==file_bytes==candidate.report_utf8
        assert sheet.review_polr_button.instate(['!disabled']) and sheet.review_polr()
        reviewed(app,sheet);assert sheet.polr_source_id==candidate.export_id and sheet.defer_polr()
    else:assert sheet.get_prepared_export() is candidate
    assert sheet.close() and facts(places)==before


@pytest.mark.parametrize('stage',['insert','columns'])
def test_ordinary_partial_saved_list_refuses_load_and_explicit_retry_recovers(ordinary,tmp_path,monkeypatch,stage):
    app,worker,places,keys,clock=seed(ordinary);sheet=open_sheet(app);exports=set();files={}
    for index in range(3):
        if index:assert sheet.new_preview()
        candidate=refresh(app,sheet);path=tmp_path/f'report-{index}.txt'
        choose(monkeypatch,sheet,str(path));assert sheet.save();settled(app)
        exports.add(candidate.export_id);files[path]=path.read_bytes()
    candidate=sheet.candidate;attempt=app._timesheet_attempt;current=sheet.current
    text=sheet.report.get('1.0','end-1c');before=facts(places)
    fault=RuntimeError('partial registered-report list presentation failed');inserted=[]
    insert=sheet.saved_list.insert;fit=sheet._fit_columns
    def populate(*args,**kw):
        result=insert(*args,**kw);inserted.append(result)
        if stage=='insert' and len(inserted)==2:raise fault
        return result
    def columns(tree):
        if tree is sheet.saved_list:raise fault
        return fit(tree)
    with monkeypatch.context() as m:
        m.setattr(sheet.saved_list,'insert',populate);m.setattr(sheet,'_fit_columns',columns)
        assert sheet.saved_reports();pump(app.root,lambda:sheet.saved_token is None)
    assert len(inserted)==(2 if stage=='insert' else 3)
    assert app.root.test_errors[-1][1] is fault and len(app.root.test_errors)==1
    assert str(fault) in sheet.saved_status.cget('text')
    assert not sheet.saved_ready and sheet.load_saved_button.instate(['disabled'])
    assert not sheet.load_saved() and not sheet.saved_list.winfo_ismapped()
    assert sheet.show_timesheet();exclusive(sheet)
    assert sheet.candidate is candidate and sheet.current is current and app._timesheet_attempt is attempt
    assert sheet.report.winfo_ismapped() and sheet.report.get('1.0','end-1c')==text
    assert facts(places)==before and all(path.read_bytes()==data for path,data in files.items())
    # Recovery is one new explicit worker read, never an automatic retry or Save.
    assert sheet.saved_reports();pump(app.root,lambda:sheet.saved_token is None)
    app.root.update_idletasks()
    assert sheet.saved_ready and sheet.saved_list.winfo_ismapped()
    assert set(sheet.saved_list.get_children())==exports and sheet.load_saved_button.instate(['!disabled'])
    sheet.saved_list.selection_set(sorted(exports)[0]);assert sheet.load_saved()
    pump(app.root,lambda:sheet.saved_token is None);exclusive(sheet)
    assert sheet.candidate.export_id==sorted(exports)[0] and not sheet.current
    assert app._timesheet_attempt.registration=='committed'
    assert sheet.report.get('1.0','end-1c')==sheet.candidate.report_text
    assert facts(places)==before and all(path.read_bytes()==data for path,data in files.items())
    assert len(app.root.test_errors)==1 and sheet.close()


@pytest.mark.parametrize('stage',['read','render'])
def test_ordinary_selected_report_failure_is_not_successful_recovery(ordinary,tmp_path,monkeypatch,stage):
    from chronicle.schema4_runtime_service import Schema4RuntimeService
    app,worker,places,keys,clock=seed(ordinary);sheet=open_sheet(app)
    register(app,sheet,monkeypatch,tmp_path);candidate=sheet.candidate;before=facts(places)
    frozen=app._timesheet_attempt.candidate
    original_bytes=(tmp_path/'report.txt').read_bytes()
    assert sheet.saved_reports();pump(app.root,lambda:sheet.saved_token is None)
    sheet.saved_list.selection_set(candidate.export_id)
    fault=RuntimeError('selected registered-report recovery failed')
    def fail(*args,**kw):raise fault
    with monkeypatch.context() as m:
        if stage=='read':m.setattr(Schema4RuntimeService,'read_registered_timesheet_export',fail)
        else:m.setattr(sheet.report,'insert',fail)
        assert sheet.load_saved();pump(app.root,lambda:sheet.saved_token is None)
    assert sheet.mode=='saved' and app._timesheet_attempt is None and not sheet.current
    assert not sheet.report.winfo_ismapped() and str(fault) in sheet.saved_status.cget('text')
    assert app.root.test_errors[-1][1] is fault and not sheet.review_polr()
    assert not sheet.retry_save() and not sheet.save_copy_as()
    assert sheet.load_saved();pump(app.root,lambda:sheet.saved_token is None);exclusive(sheet)
    assert sheet.candidate==frozen and app._timesheet_attempt.registration=='committed'
    assert facts(places)==before and (tmp_path/'report.txt').read_bytes()==original_bytes
    assert len(app.root.test_errors)==1
