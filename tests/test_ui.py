"""Actual schema-5 StartupWindow/worker/Tk tests on an available display."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import time
import tkinter as tk
from tkinter import ttk

import pytest
from chronicle.app import ChronicleApp
from chronicle.startup import StartupWindow
from chronicle.worker import DatabaseWorker,Message
from chronicle import launcher_selection as ls, project_ui as ui
from chronicle.timekeeping import from_us
from conftest import NOW,uid


def pump(root,condition=lambda:True,timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        root.update()
        if condition():return
        time.sleep(.005)
    raise AssertionError('Tk condition deadline; callback errors: '+repr(root.errors))


def settled(app):
    pump(app.root,lambda:app.pending is None and not app.executing and app._read_inflight is None and not app._read_again)
    assert not app.root.errors,app.root.errors


def select(app,key=None):
    app.tree.selection_remove(*app.tree.selection())
    if key:
        app.tree.selection_set(key);app.tree.focus(key);app.tree.see(key)
    app.root.update()


def submit(app,operation,**args):
    assert app._submit(operation,**args)
    request=app.pending;settled(app)
    assert app._mutation_outcome.status=='committed',app._mutation_outcome
    return request


def project(app,parent=None,name='Project'):
    key=uid();args=dict(project_id=key,name=name)
    if parent:
        row=next(p for p in app.state['projects'] if p['project_id']==parent)
        args.update(parent_project_id=parent,expected_parent_version=row['version'],reviewed_parent_ancestry=ui.ancestry(app.state,parent))
    submit(app,'create_child_project' if parent else 'create_project',**args)
    return key


def task(app,group,parent=None,name='Task'):
    select(app,ui.task_row(parent) if parent else ui.project_row(group))
    assert app.create_task();dialog=app.task_creation
    pump(app.root,lambda:dialog.window.winfo_viewable())
    dialog.name.insert(0,name);assert dialog.submit();request=app.pending;settled(app)
    assert app._mutation_outcome.status=='committed',app._mutation_outcome
    return request.args()['task_id']


def facts(app):
    path=Path(app.worker.directory)/'chronicle.sqlite3'
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None)
    try:
        c.execute('BEGIN')
        result={name:list(c.execute('SELECT * FROM '+name+' ORDER BY rowid')) for name, in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        c.execute('ROLLBACK');return result
    finally:c.close()


@pytest.fixture
def root():
    try:value=tk.Tk()
    except tk.TclError as exc:pytest.skip('Real Tk display unavailable: '+str(exc))
    value.errors=[]
    value.report_callback_exception=lambda typ,error,tb:value.errors.append(error)
    try:yield value
    finally:
        try:value.destroy()
        except tk.TclError:pass


@pytest.fixture
def ordinary(root,tmp_path):
    places=ls.Locations(tmp_path/'local'/'Data',tmp_path/'local'/'selection.json')
    flow=StartupWindow(root,app_factory=ChronicleApp,worker_factory=DatabaseWorker,locations=places)
    try:
        pump(root,lambda:flow.discover_id is None)
        flow.begin(places.folder,create=True,timezone='America/Chicago')
        pump(root,lambda:flow.app is not None and flow.app.state.get('report') is not None)
        app=flow.app;tick=[NOW]
        def clock():tick[0]+=1_000_000;return from_us(tick[0])
        app.now_utc=clock;app.refresh();settled(app)
        assert type(flow.worker) is DatabaseWorker and flow.worker.is_alive()
        assert app.state['schema_version']==5 and app.state['semantic_verified'] and app.state['ordinary_startup_permitted']
        assert app.dataset_id==app.state['dataset_id']
        yield app,flow,places
    finally:
        if flow.worker is not None and flow.worker.is_alive():flow.worker.requests.put(Message('shutdown'))
        try:root.destroy()
        except tk.TclError:pass
        if flow.worker is not None:flow.worker.join(15);assert not flow.worker.is_alive()


def test_actual_startup_empty_real_projects_and_no_implicit_destination(ordinary):
    app,flow,places=ordinary
    assert app.root.title()=='Chronicle' and app.root.grab_current() is None
    assert app.tree.get_children()==() and not app.state['tasks']
    assert ls.read_selection(places.record).directory==places.folder
    p=project(app,name='Duplicate Ω');deep=project(app,p,name='Duplicate Ω');other=project(app,name='Duplicate Ω')
    assert app.tree.parent(ui.project_row(deep))==ui.project_row(p)
    select(app);before=facts(app);assert app.create_task();d=app.task_creation
    pump(app.root,lambda:d.window.winfo_viewable())
    assert d.project_id is None and d.tree.selection()==() and d.create_button.instate(['disabled'])
    assert {p,deep,other}=={d.tree.item(row,'values')[0] for row in (ui.project_row(p),ui.project_row(deep),ui.project_row(other))}
    d.tree.selection_set(ui.project_row(deep));pump(app.root,lambda:d.project_id==deep)
    assert p in d.path.get() and deep in d.path.get() and 'Duplicate Ω' in d.path.get()
    d.name.insert(0,'Explicit root');assert d.submit();request=app.pending;settled(app)
    assert request.args()['project_id']==deep and app.tree.parent(ui.task_row(request.args()['task_id']))==ui.project_row(deep)
    assert len(facts(app)['committed_requests'])==len(before['committed_requests'])+1


@pytest.mark.parametrize('close',['cancel','escape','x'])
def test_task_dialog_cancel_x_escape_purity_focus_and_grab(ordinary,close):
    app,_,_=ordinary;p=project(app);origin=ttk.Entry(app.root);origin.grid(row=8,column=0);origin.focus_set();app.root.update()
    select(app,ui.project_row(p));before=facts(app);assert app.create_task();d=app.task_creation
    pump(app.root,lambda:d.window.winfo_viewable() and app.root.grab_current() is d.window)
    d.name.insert(0,'Discard this draft')
    if close=='cancel':d.cancel_button.invoke()
    elif close=='escape':d.window.event_generate('<Escape>')
    else:app.root.tk.call(d.window.protocol('WM_DELETE_WINDOW'))
    pump(app.root,lambda:app.task_creation is None)
    assert app.editor is None and app.root.grab_current() is None and facts(app)==before
    assert app.root.focus_get() is origin and not app.root.errors


def test_selected_project_can_change_but_child_inherits_readonly_and_depth_limit(ordinary):
    app,_,_=ordinary;p=project(app);q=project(app);select(app,ui.project_row(p))
    assert app.create_task();d=app.task_creation;pump(app.root,lambda:d.window.winfo_viewable())
    assert d.project_id==p;d.tree.selection_set(ui.project_row(q));pump(app.root,lambda:d.project_id==q)
    d.name.insert(0,'Changed destination');assert d.submit();r=app.pending;settled(app);parent=r.args()['task_id']
    select(app,ui.task_row(parent));assert app.create_task();d=app.task_creation;pump(app.root,lambda:d.window.winfo_viewable())
    assert d.parent_id==parent and d.project_id==q
    d.tree.selection_set(ui.project_row(p));pump(app.root,lambda:d.tree.selection()==(ui.project_row(q),))
    d.name.insert(0,'Child');assert d.submit();child=app.pending.args()['task_id'];settled(app)
    leaf=task(app,q,child);select(app,ui.task_row(leaf));before=facts(app)
    assert not app.create_task() and facts(app)==before and 'level 3' in app.status.cget('text')


def test_no_projects_has_create_project_route_without_task_or_stacked_modal(ordinary,monkeypatch):
    app,_,_=ordinary;assert app.create_task();d=app.task_creation;pump(app.root,lambda:d.window.winfo_viewable())
    assert d.project_button.winfo_ismapped() and 'real project' in d.status.cget('text')
    observed=[]
    def name(*args,**kwargs):
        observed.append((app.task_creation,app.editor,app.root.grab_current()))
        return 'Explicitly created'
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',name)
    assert d.create_project();settled(app)
    assert observed==[(None,None,None)] and len(app.state['projects'])==1 and not app.state['tasks']


def test_stale_destination_refuses_and_modal_blocks_other_mutation(ordinary):
    app,_,_=ordinary;p=project(app);select(app,ui.project_row(p));assert app.create_task();d=app.task_creation
    pump(app.root,lambda:d.window.winfo_viewable())
    assert not app._submit('create_project',project_id=uid(),name='Competing')
    d.state['projects'][0]['version']+=1;d.name.insert(0,'Stale reviewed project')
    before=facts(app);assert d.submit();pump(app.root,lambda:app.pending is None and not app.executing)
    assert app._mutation_outcome.status=='rejected' and facts(app)==before and app.task_creation is None
    from chronicle.records import StaleState
    assert len(app.root.errors)==1 and type(app.root.errors[0]) is StaleState
    assert str(app.root.errors[0])=='Reviewed coverage, relationships or versions changed'


def test_running_parent_refuses_and_mini_stop_uses_same_worker(ordinary):
    app,_,_=ordinary;p=project(app);key=task(app,p);select(app,ui.task_row(key))
    r=submit(app,'start_timer',task_id=key,entry_id=uid(),expected_task_version=1)
    assert not app.create_task();before=facts(app)
    assert app.open_mini();pump(app.root,lambda:app.mini is not None and app.mini.window.winfo_viewable())
    assert app.state['active']['entry_id']==r.args()['entry_id'] and facts(app)==before
    app.mini_toggle();settled(app);assert app.state['active'] is None
    app.show_main();pump(app.root,lambda:app.root.winfo_viewable())


@pytest.mark.parametrize('mode',['local','none','missing','reused'])
def test_current_history_focus_identity_return_and_no_database_mutation(ordinary,mode):
    app,_,_=ordinary;p=project(app);key=task(app,p);select(app,ui.task_row(key))
    origin=ttk.Entry(app.root,name='history_origin');origin.grid(row=8,column=0);app.root.update();origin.focus_set();app.root.update()
    if mode=='local':app.root.grab_set()
    before=facts(app);assert app.open_history();pump(app.root,lambda:app.history is not None and app.history.current)
    history=app.history
    if mode in ('missing','reused'):
        origin.destroy()
        if mode=='reused':
            replacement=ttk.Entry(app.root,name='history_origin');replacement.grid(row=8,column=0);app.root.update()
            assert replacement is not origin
    assert history.close();pump(app.root,lambda:app.history is None)
    assert app.root.focus_get() is (origin if mode in ('local','none') else app.root)
    assert app.root.grab_current() is (app.root if mode=='local' else None)
    if mode=='local':app.root.grab_release()
    assert facts(app)==before and not app.root.errors


def sheet(app):
    assert app.open_timesheet();pump(app.root,lambda:app.timesheet is not None and app.timesheet.presented and app.timesheet.choices_token is None)
    return app.timesheet


def test_timesheet_four_sections_manual_return_and_draft_scope(ordinary):
    app,_,_=ordinary;p=project(app);key=task(app,p);submit(app,'add_date_only_work',task_id=key,entry_id=uid(),work_date='2026-10-19',duration_text='0:15',comment='Recorded')
    before=facts(app);s=sheet(app)
    assert s.mode=='preview' and s.candidate is None and len(s.primary_buttons)==4
    assert s.open_reconciliation();pump(app.root,lambda:s.reconciliation_current)
    applied=deepcopy(s.reconciliation_applied)
    row=next(handle for handle,value in s.reconciliation_mapping.items() if value['task_id']==key and value['work_date']=='2026-10-19')
    s.reconciliation_tree.selection_set(row);app.root.update();semantic=s._row_key()
    s.reconciliation_period.set('Custom');s.reconciliation_start.set('2026-10-01');s.reconciliation_end.set('2026-10-02')
    assert s.reconciliation_manual_action();pump(app.root,lambda:s.mode=='confirmation_manual' and s.polr_ready)
    assert not s.close() and not s.saved_reports() and not s.show_timesheet()
    assert s.defer_polr();pump(app.root,lambda:s.mode=='reconciliation' and s.reconciliation_current)
    assert {k:v for k,v in s.reconciliation_applied.items() if k!='cutoff_utc_us'}=={k:v for k,v in applied.items() if k!='cutoff_utc_us'} and s._row_key()==semantic
    assert s.reconciliation_start.get()=='2026-10-01' and facts(app)==before
    assert s.close() and not app.root.errors


@pytest.mark.parametrize('size',['980x740','800x620'])
def test_timesheet_exclusive_expanding_views_and_accessible_footer(ordinary,size,tmp_path):
    app,_,_=ordinary;p=project(app);task(app,p,name='長い名前 Ω '*12);s=sheet(app)
    s.window.geometry(size);app.root.update()
    assert s.close_button.winfo_ismapped() and s.close_button.winfo_rooty()+s.close_button.winfo_height()<=s.window.winfo_rooty()+s.window.winfo_height()
    geometry=[]
    def box(w):return [w.winfo_rootx(),w.winfo_rooty(),w.winfo_width(),w.winfo_height()]
    for action,mode in ((s.saved_reports,'saved'),(s.open_reconciliation,'reconciliation'),(s.confirmation_history,'confirmation_history'),(s.show_timesheet,'preview')):
        assert action();pump(app.root,lambda:s.mode==mode)
        app.root.update()
        assert sum(bool(p.winfo_ismapped()) for p in (s.timesheet_panel,s.saved_panel,s.reconciliation_panel,s.polr_panel))==1
        assert s.close_button.winfo_ismapped() and all(b.winfo_ismapped() for b in s.primary_buttons)
        table={'saved':s.saved_list,'reconciliation':s.reconciliation_tree,'confirmation_history':s.polr_tree,'preview':s.report}[mode]
        bars={str(w.cget('orient')):w for w in table.master.winfo_children() if isinstance(w,ttk.Scrollbar)}
        t,v,h=map(box,(table,bars['vertical'],bars['horizontal']));window=box(s.window)
        geometry.append(dict(mode=mode,table=t,vertical=v,horizontal=h,window=window,footer=box(s.close_button)))
        assert table.winfo_ismapped() and t[2]>100 and t[3]>20
        assert 0<=v[0]-t[0]-t[2]<=4 and abs(v[1]-t[1])<=4 and abs(v[3]-t[3])<=4
        assert 0<=h[1]-t[1]-t[3]<=4
        for button in (*s.primary_buttons,s.close_button):
            x,y,width,height=box(button)
            assert x>=window[0] and y>=window[1] and x+width<=window[0]+window[2] and y+height<=window[1]+window[3]
    (tmp_path/'timesheet-geometry.json').write_text(json.dumps(geometry,indent=2)+'\n',encoding='utf-8')
    assert s.close() and not app.root.errors


def test_manual_zero_committed_receipt_remains_until_explicit_return_and_history(ordinary):
    app,_,_=ordinary;p=project(app);key=task(app,p);s=sheet(app);before=facts(app)
    assert s.manual_polr();assert s.refresh_polr();pump(app.root,lambda:s.polr_ready)
    s.polr_hours.set('0.00');assert s.confirm_polr();request=app.pending
    pump(app.root,lambda:app.pending is None and s._polr_completed and not s.polr_tokens)
    batch=request.args()['batch_id']
    assert s.mode=='confirmation_manual' and batch in s.polr_status.cget('text')
    assert batch in s.polr_detail.get('1.0','end')
    assert not s.confirm_polr()
    after=facts(app);assert len(after['polr_confirmation_batches'])==len(before['polr_confirmation_batches'])+1
    assert after['polr_confirmation_cells'][0][3]==0
    assert s.defer_polr() and s.mode=='preview'
    assert s.confirmation_history();pump(app.root,lambda:not s.polr_tokens)
    assert s.polr_tree.exists(batch);s.polr_tree.selection_set(batch);assert s.load_polr_batch();pump(app.root,lambda:not s.polr_tokens)
    assert batch in s.polr_detail.get('1.0','end') and facts(app)==after
    assert s.close() and not app.root.errors


def test_registered_report_saved_loaded_exclusively_after_real_restart_without_file(ordinary,monkeypatch,tmp_path):
    app,flow,places=ordinary;p=project(app);key=task(app,p)
    submit(app,'add_date_only_work',task_id=key,entry_id=uid(),work_date='2026-10-19',duration_text='1:08',comment='Frozen source')
    s=sheet(app);assert s.refresh_preview();pump(app.root,lambda:s.current)
    candidate=s.candidate;target=tmp_path/'report.txt'
    monkeypatch.setattr('chronicle.timesheet_window.filedialog.asksaveasfilename',lambda **kw:str(target))
    assert s.save();pump(app.root,lambda:app._timesheet_attempt is not None and app._timesheet_attempt.saved_path is not None)
    assert target.read_bytes()==candidate.report_utf8
    before=facts(app);assert s.close();identity=app.dataset_id
    app.request_close();pump(app.root,lambda:not app.alive);flow.worker.join(15);assert not flow.worker.is_alive()
    target.unlink();fresh_root=tk.Tk();fresh_root.errors=[]
    fresh_root.report_callback_exception=lambda typ,error,tb:fresh_root.errors.append(error)
    fresh=StartupWindow(fresh_root,app_factory=ChronicleApp,worker_factory=DatabaseWorker,locations=places)
    try:
        pump(fresh_root,lambda:fresh.app is not None and fresh.app.state.get('report') is not None)
        assert fresh.app.dataset_id==identity and fresh.app.worker is not flow.worker
        loaded=sheet(fresh.app);assert loaded.candidate is None and loaded.saved_reports()
        pump(fresh_root,lambda:loaded.saved_ready)
        loaded.saved_list.selection_set(candidate.export_id);assert loaded.load_saved()
        pump(fresh_root,lambda:loaded.mode=='preview' and loaded.candidate is not None)
        assert loaded.candidate==replace(candidate,preferred_destination=str(target))
        assert loaded.candidate.report_utf8==candidate.report_utf8 and loaded.candidate.report_sha256==candidate.report_sha256
        assert not loaded.saved_panel.winfo_ismapped()
        assert candidate.export_id in loaded.context.cget('text') and not target.exists()
        assert facts(fresh.app)==before
        assert loaded.review_polr();pump(fresh_root,lambda:loaded.polr_ready)
        assert loaded.polr_selected and all(r['suggested_quarters']>0 for k,r in ((k,r) for k,r in loaded.polr_mapping.items()) if (r['task_id'],r['work_date']) in loaded.polr_selected)
        assert loaded.defer_polr();assert loaded.close();assert not fresh_root.errors
    finally:
        if fresh.worker is not None and fresh.worker.is_alive():fresh.worker.requests.put(Message('shutdown'))
        fresh_root.destroy()
        if fresh.worker:fresh.worker.join(15);assert not fresh.worker.is_alive()


def test_project_root_move_task_move_template_apply_and_archived_real_ancestry(ordinary,monkeypatch):
    app,_,_=ordinary;p=project(app);deep=project(app,p);q=project(app);root=task(app,deep);leaf=task(app,deep,root)
    submit(app,'add_date_only_work',task_id=leaf,entry_id=uid(),work_date='2026-10-19',duration_text='0:20',comment='Preserved')
    before=facts(app);select(app,ui.task_row(root));assert app.open_move();move=app.movement
    pump(app.root,lambda:move.presented)
    assert 'group:unassigned' not in move.destinations and 'group:root' not in move.destinations
    move.tree.selection_set(ui.project_row(q));app.root.update();assert move.submit();settled(app)
    assert move.phase=='complete' and move.close()
    assert facts(app)['work_entries']==before['work_entries'] and app.tree.parent(ui.task_row(root))==ui.project_row(q)
    select(app,ui.project_row(deep));assert app.open_move();move=app.movement;pump(app.root,lambda:move.presented)
    assert 'group:root' in move.destinations;move.tree.selection_set('group:root');app.root.update()
    assert move.submit();settled(app);assert move.close() and app.tree.parent(ui.project_row(deep))==''
    node=uid();definition=uid();submit(app,'create_template',template_id=definition,name='Current blueprint',nodes=[dict(node_id=node,parent_node_id=None,name='Fresh task',position=0)])
    select(app);source=next(d for d in app.state['templates'] if d['template_id']==definition)
    assert app.open_template_dialog('apply',source);dialog=app.template_dialog;pump(app.root,lambda:dialog.window.winfo_viewable())
    assert not dialog.destination_tree.selection() and not dialog.arguments
    assert all(row['destination'][1] is not None for row in dialog.destinations.values())
    dialog.destination_tree.selection_set(ui.project_row(deep));app.root.update();assert dialog.submit();request=app.pending;settled(app)
    assert dialog.phase=='complete' and dialog.close()
    created=app._mutation_outcome.result['created_tasks'][0]['task_id'];assert app.tree.parent(ui.task_row(created))==ui.project_row(deep)
    def confirm_archive(title,text,**kwargs):
        assert title=='Archive project' and q in text and kwargs['parent'] is app.root
        return True
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',confirm_archive)
    select(app,ui.project_row(q));assert app.archive_selected();settled(app)
    assert app.open_archived();pump(app.root,lambda:app.archived is not None and app.archived.window.winfo_viewable())
    archived=app.archived
    assert archived.tree.exists(ui.project_row(q)) and archived.tree.parent(ui.task_row(root))==ui.project_row(q)
    assert not archived.tree.exists('group:unassigned') and archived.close() and not app.root.errors


def test_timesheet_root_grab_origin_return_and_refused_reentry_are_read_only(ordinary):
    app,_,_=ordinary;p=project(app);task(app,p)
    app.root.grab_set();app.tree.focus_set();app.root.update();before=facts(app)
    s=sheet(app)
    assert app._timesheet_return==(app.root,app.root,app.tree)
    assert app.root.grab_current() is s.window and s.window.grab_status()=='local'
    assert not app.open_timesheet()
    assert s.close();pump(app.root,lambda:app.timesheet is None)
    assert app.root.focus_get() is app.tree and app.root.grab_current() is app.root
    app.root.grab_release()
    assert facts(app)==before and not app.root.errors


def test_timesheet_global_grab_refusal_exact_diagnostic_then_destroyed_origin_fallback(ordinary):
    app,_,_=ordinary;p=project(app);task(app,p);before=facts(app)
    assert not app.root.errors
    competitor=tk.Toplevel(app.root);ttk.Label(competitor,text='Competing owned modal').pack()
    pump(app.root,lambda:competitor.winfo_viewable());competitor.grab_set_global()
    assert not app.open_timesheet() and app.timesheet is None and app.editor is None
    assert app.root.grab_current() is competitor and competitor.grab_status()=='global'
    assert len(app.root.errors)==1 and type(app.root.errors[0]) is ValueError
    assert str(app.root.errors[0])=='Timesheet cannot replace an unrelated or global grab'
    assert facts(app)==before
    competitor.destroy();app.root.update();assert app.root.grab_current() is None
    origin=ttk.Entry(app.root);origin.grid(row=8,column=0);pump(app.root,lambda:origin.winfo_viewable())
    origin.focus_set();app.root.update();s=sheet(app);origin.destroy()
    assert s.close();pump(app.root,lambda:app.timesheet is None)
    assert app.root.focus_get() is app.root and app.root.grab_current() is None and app.editor is None
    assert len(app.root.errors)==1 and facts(app)==before


@pytest.mark.parametrize('size',['720x540','600x440'])
def test_new_task_mapped_geometry_expansion_scrolling_and_action_visibility(ordinary,size,tmp_path):
    app,_,_=ordinary;p=project(app,name='長い名前 Ω '*20);project(app,p,name='Duplicate ü Ω')
    select(app);before=facts(app);assert app.create_task();d=app.task_creation
    d.window.geometry(size);pump(app.root,lambda:d.window.winfo_viewable());app.root.update()
    def box(w):return [w.winfo_rootx(),w.winfo_rooty(),w.winfo_width(),w.winfo_height()]
    table,vertical,horizontal=map(box,(d.tree,d.vertical,d.horizontal));client=box(d.window)
    observation=dict(size=size,client=client,table=table,vertical=vertical,horizontal=horizontal,
                     create=box(d.create_button),cancel=box(d.cancel_button),scaling=app.root.tk.call('tk','scaling'))
    (tmp_path/'mapped-geometry.json').write_text(json.dumps(observation,indent=2)+'\n',encoding='utf-8')
    assert d.tree.winfo_ismapped() and table[2]>100 and table[3]>30
    assert 0<=vertical[0]-table[0]-table[2]<=4 and abs(vertical[1]-table[1])<=4 and abs(vertical[3]-table[3])<=4
    assert 0<=horizontal[1]-table[1]-table[3]<=4 and abs(horizontal[0]-table[0])<=4
    for w in (d.name,d.path_entry,d.create_button,d.cancel_button):
        x,y,width,height=box(w)
        assert w.winfo_ismapped() and x>=client[0] and y>=client[1] and x+width<=client[0]+client[2] and y+height<=client[1]+client[3]
    d.tree.xview_moveto(1);app.root.update();assert d.tree.xview()[1]==1
    assert d.close() and facts(app)==before and not app.root.errors


def test_new_task_construction_failure_cleans_owned_widgets_and_preserves_facts(ordinary,monkeypatch):
    app,_,_=ordinary;p=project(app);select(app,ui.project_row(p));before=facts(app)
    owned=set(app.root.winfo_children())
    def failed(*args,**kw):raise RuntimeError('Test-owned Treeview construction failure')
    with monkeypatch.context() as patch:
        patch.setattr('chronicle.task_creation_window.ttk.Treeview',failed)
        assert not app.create_task()
    app.root.update()
    assert set(app.root.winfo_children())==owned and app.task_creation is None and app.editor is None
    assert app.root.grab_current() is None and facts(app)==before
    assert len(app.root.errors)==1 and type(app.root.errors[0]) is RuntimeError
    assert str(app.root.errors[0])=='Test-owned Treeview construction failure'
    assert app.create_task();d=app.task_creation;pump(app.root,lambda:d.window.winfo_viewable())
    assert d.close() and facts(app)==before and len(app.root.errors)==1


def test_actual_manual_date_only_editor_and_history_revision_readback(ordinary):
    app,_,_=ordinary;p=project(app);key=task(app,p);select(app,ui.task_row(key))
    assert app.add_date_only_work();editor=app._work_editor
    pump(app.root,lambda:editor.window.winfo_viewable())
    assert app.root.grab_current() is editor.window and app.pending is None
    assert len(editor.fields)==3
    for field,text in zip(editor.fields,('2026-10-19','0:25','Actual owned editor Ω')):
        field.delete(0,'end');field.insert(0,text)
    editor.save.invoke();request=app.pending;settled(app)
    assert request.operation=='add_date_only_work' and request.args()['task_id']==key
    assert app.editor is None and app._work_editor is None and not app.root.errors
    stored=facts(app);assert len(stored['work_entries'])==len(stored['work_revisions'])==1
    assert app.open_history();pump(app.root,lambda:app.history is not None and app.history.current)
    assert len(app.history.rows)==1
    assert app.history.rows[0]['entry_id']==request.args()['entry_id']
    assert app.history.close() and facts(app)==stored
