"""Actual ordinary StartupWindow/DatabaseWorker/Tk integration, never a bridge."""
import tkinter as tk
import pytest
from chronicle.app import ChronicleApp, backend_profile_matches
from chronicle.startup import StartupWindow
from chronicle.worker import DatabaseWorker, Message
from chronicle import launcher_selection as ls, project_ui as ui
from chronicle.sqlite_store import SQLiteStore
from test_app import root, pump
from test_main_explorer import settled, select
from test_schema4_project_modal import project, task, moving, submit
from test_backup_restore import logical
from runtime4_cases import NOW, uid


@pytest.fixture
def ordinary(root,tmp_path):
    places=ls.Locations(tmp_path/'local'/'Data',tmp_path/'local'/'launcher-selection.json')
    flow=StartupWindow(root,app_factory=ChronicleApp,worker_factory=DatabaseWorker,locations=places)
    try:
        pump(root,lambda:flow.discover_id is None)
        flow.begin(places.folder,create=True,timezone='America/Chicago')
        pump(root,lambda:flow.app is not None and flow.app.state.get('report') is not None)
        assert type(flow.worker) is DatabaseWorker
        assert flow.app.presentation_profile=='schema4' and not flow.app.candidate_presentation
        assert flow.app.schema4_presentation and flow.app.buttons['Backup Chronicle'].instate(['!disabled'])
        assert flow.app.state['schema_version']==4 and flow.app.state['ordinary_startup_permitted']
        assert ls.read_selection(places.record).directory==places.folder
        yield flow.app,flow.worker,places
    finally:
        if flow.app is not None and flow.app.alive:root.destroy()
        elif flow.worker is not None and flow.worker.is_alive():flow.worker.requests.put(Message('shutdown'))
        if flow.worker is not None:
            flow.worker.join(15);assert not flow.worker.is_alive()


def test_ordinary_ready_profile_is_fail_closed_and_distinct_from_candidate():
    good=dict(schema_version=4,semantic_verified=True,ordinary_startup_permitted=True)
    assert backend_profile_matches('schema4',good)
    for bad in ({},dict(good,schema_version=3),dict(good,semantic_verified=False),dict(good,ordinary_startup_permitted=False),dict(good,candidate_verified=True)):
        assert not backend_profile_matches('schema4',bad)
    assert not backend_profile_matches('schema4-candidate',good)
    assert not backend_profile_matches('schema3',good)


def test_normal_startup_tree_controls_project_move_and_real_history(ordinary,monkeypatch):
    app,worker,places=ordinary
    assert app.root.title()=='Chronicle' and app.root.grab_current() is None
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',lambda *a,**k:'Root')
    assert app.create_project();settled(app)
    p=app.state['projects'][0]['project_id'];select(app,ui.project_row(p))
    assert app.create_child_project();settled(app)
    child=next(x['project_id'] for x in app.state['projects'] if x['parent_project_id']==p)
    deep=project(app,project(app,child));leaf=task(app,deep);other=project(app)
    assert app.tree.parent(ui.project_row(child))==ui.project_row(p)
    assert app.tree.parent(ui.task_row(leaf))==ui.project_row(deep)
    before=logical(places.folder/'chronicle.sqlite3')
    dialog=moving(app,'project',child,ui.project_row(other))
    assert app.editor is dialog.window and not app.create_project()
    assert dialog.submit();settled(app)
    assert app._mutation_outcome.status=='committed'
    assert dialog.close()
    assert app.tree.parent(ui.project_row(child))==ui.project_row(other)
    assert logical(places.folder/'chronicle.sqlite3')['tasks']==before['tasks']
    select(app,ui.task_row(leaf));assert app.open_history()
    pump(app.root,lambda:app.history is not None and app.history.current)
    assert app.history.window.grab_current() is app.history.window
    assert app.history.close()
    assert not app.root.test_errors


def test_ordinary_timer_and_resize_keep_backend_and_frozen_identity(ordinary):
    app,worker,places=ordinary;p=project(app);key=task(app,p)
    select(app,ui.task_row(key))
    request=submit(app,'start_timer',task_id=key,entry_id=uid(),expected_task_version=1)
    active=app.state['active'].copy();before=logical(places.folder/'chronicle.sqlite3')
    app.root.geometry('720x420');app.root.update_idletasks()
    assert app.state['active']==active and logical(places.folder/'chronicle.sqlite3')==before
    assert app.tree.selection()==(ui.task_row(key),)
    submit(app,'stop_timer',entry_id=active['entry_id'],expected_version=1)
    assert app.state['active'] is None and not app.root.test_errors


@pytest.mark.parametrize('legacy',[False,True])
def test_remembered_source_launch_opens_only_semantically_verified_schema4(root,tmp_path,legacy):
    data=tmp_path/'existing';record=tmp_path/'local'/'selection.json'
    s=SQLiteStore(data,create=True,timezone='Etc/UTC',schema_version=3 if legacy else 4);identity=s.dataset_id;s.close()
    before=logical(data/'chronicle.sqlite3');ls.remember(record,data,None)
    flow=StartupWindow(root,app_factory=ChronicleApp,worker_factory=DatabaseWorker,
        locations=ls.Locations(tmp_path/'unused',record))
    try:
        if legacy:
            pump(root,lambda:flow.failure is not None and flow.worker is None)
            assert flow.app is None and 'schema 4' in str(flow.failure)
        else:
            pump(root,lambda:flow.app is not None and flow.app.state.get('report') is not None)
            assert flow.app.dataset_id==identity and flow.app.presentation_profile=='schema4'
        assert logical(data/'chronicle.sqlite3')==before
    finally:
        root.destroy()
        if flow.worker is not None:flow.worker.join(15);assert not flow.worker.is_alive()


def test_ordinary_templates_timesheet_history_and_compact_mini(ordinary):
    from types import SimpleNamespace
    from chronicle.timekeeping import from_us
    from test_schema4_project_modal import test_template_apply_review_and_direct_history_and_task_only_timesheet as workflow
    from test_schema4_project_modal import test_candidate_main_double_click_and_compact_mini_remain_existing_paths as timer
    app,worker,places=ordinary
    from test_app import Clock
    clock=Clock();app.now_utc=clock  # Coordinate the existing detached October work fixtures.
    workflow((app,worker,clock))  # The same actual UI assertions, now with the production worker.
    assert app.open_templates();pump(app.root,lambda:app.templates_window is not None and app.templates_window.window.winfo_ismapped())
    assert app.templates_window.close()
    timer((app,worker,clock))
    assert not app.root.test_errors


def test_ordinary_task_move_archive_nested_delete_and_backup_dialog(ordinary,tmp_path):
    from test_archived_items import window,choose
    from test_delete_ui import opened,authorize
    from test_backup_ui import open_backup,wait_backup
    from chronicle import backup_restore as br
    app,worker,places=ordinary;p=project(app);child=project(app,p);q=project(app);key=task(app,child)
    dialog=moving(app,'task',key,ui.project_row(q));assert dialog.arguments['reviewed_destination_project_ancestry']==ui.ancestry(app.state,q)
    assert dialog.submit();settled(app);assert app._mutation_outcome.status=='committed';assert dialog.close()
    assert next(t for t in app.state['tasks'] if t['task_id']==key)['project_id']==q
    submit(app,'archive_project',project_id=p,expected_version=1)
    view=window(app);choose(view,ui.project_row(child))
    assert view.unarchive_button.instate(['disabled']) and p in view.status.cget('text')
    choose(view,ui.project_row(p));assert view.unarchive();settled(app);assert view.close()
    dialog=opened(app,ui.project_row(p))
    assert dialog.review['project_count']==2 and dialog.review['task_count']==0
    # The retained task movement needs its source project history. Empty current
    # membership alone is not unused-only Delete permission.
    assert not dialog.review['eligible'] and not authorize(dialog) and dialog.close()
    unused=project(app);project(app,unused)
    dialog=opened(app,ui.project_row(unused))
    assert dialog.review['eligible'] and dialog.review['project_count']==2
    assert not dialog.submit() and authorize(dialog);settled(app)
    assert app._mutation_outcome.status=='committed' and dialog.close()
    assert not app.tree.exists(ui.project_row(unused)) and app.tree.exists(ui.project_row(p)) and app.tree.exists(ui.task_row(key))
    before=logical(places.folder/'chronicle.sqlite3')
    dialog=open_backup(app);target=tmp_path/'production-ui-backup.sqlite3';dialog.destination.set(str(target))
    assert dialog.create();result=wait_backup(app)
    assert result.verified and br.validate_image(target).dataset_id==app.dataset_id
    assert logical(target)==before and logical(places.folder/'chronicle.sqlite3')==before
    assert dialog.close() and not app.root.test_errors


@pytest.mark.parametrize('size',['720x420','850x550'])
def test_ordinary_schema4_retains_validated_compact_main_geometry(ordinary,size):
    from test_main_layout import geometry,assert_layout,identities
    app,worker,places=ordinary;widgets=identities(app);before=logical(places.folder/'chronicle.sqlite3')
    geometry(app,size);assert_layout(app)
    geometry(app,'850x550' if size=='720x420' else '720x420');assert_layout(app)
    assert identities(app)==widgets and logical(places.folder/'chronicle.sqlite3')==before
    assert app.buttons['Create project'].cget('text')=='New root project'


def test_ordinary_uncertain_delete_retains_request_and_blocks_retry_until_exit(ordinary,monkeypatch):
    from test_delete_ui import opened,authorize
    from test_runtime4_store import Fault
    from test_timesheet_save_ui import exit_settled
    from chronicle.schema4_runtime_service import Schema4RuntimeService
    app,worker,places=ordinary;p=project(app);dialog=opened(app,ui.project_row(p))
    original=SQLiteStore.delete_unused
    def lost(self,r):
        self.connection=Fault(self.connection,'after')
        return original(self,r)
    monkeypatch.setattr(SQLiteStore,'delete_unused',lost)
    assert authorize(dialog);accepted=app.pending
    pump(app.root,lambda:not app.executing)
    assert app.pending is accepted and app._mutation_outcome.status=='unverified'
    assert dialog.phase=='unverified' and not dialog.submit() and not dialog.refresh()
    assert not app.retry() and not app.create_project() and not app.open_backup()
    assert app.inspect_delete_state();pump(app.root,lambda:app._delete_inspection_token is None)
    assert 'ABSENT' in dialog.status.cget('text') and 'not historical proof' in dialog.status.cget('text')
    assert app.pending is accepted
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**k:True)
    assert app.exit_delete_uncertain();exit_settled(app);worker.join(15);assert not worker.is_alive()
    reopened=SQLiteStore(places.folder)
    try:
        service=Schema4RuntimeService(reopened)
        assert service.read_delete_presence('project',p)['historical_outcome_verified'] is False
        assert not service.read_delete_presence('project',p)['present']
        assert service.reconcile_request(accepted).status=='unverified'
    finally:reopened.close()


def test_explicit_relative_source_path_remains_supported_and_constructor_failure_closes_root(root,tmp_path,monkeypatch):
    from chronicle import bootstrap,startup
    captured=[]
    def failed(actual_root,**kw):
        captured.append((actual_root,kw));raise OSError('Startup construction failure')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bootstrap.tk,'Tk',lambda:root)
    monkeypatch.setattr(startup,'StartupWindow',failed)
    with pytest.raises(OSError,match='Startup construction failure'):
        bootstrap.main(['--data-dir','fresh','--create','--timezone','Etc/UTC'])
    assert captured[0][0] is root
    assert captured[0][1]['initial_selection']==(tmp_path/'fresh',True,'Etc/UTC')
    assert captured[0][1]['schema_version']==4 and captured[0][1]['remember_selection'] is False
    with pytest.raises(tk.TclError):root.winfo_exists()
    assert not (tmp_path/'fresh').exists()


def test_ordinary_schema4_backup_restore_fresh_root_worker(ordinary,tmp_path,monkeypatch):
    """Sequential real app sessions; backup/restore never substitutes a bridge."""
    from datetime import timedelta
    from chronicle import backup_restore as br
    from chronicle.dataset_lock import DatasetLock
    from test_app import Clock
    from test_chronicle_timesheet_ui import open_sheet,refresh
    from test_timesheet_save_ui import choose,exit_settled
    from test_polr_confirmation_ui import reviewed
    from test_backup_ui import open_backup,wait_backup
    from test_package_f_runtime4 import record
    app,worker,places=ordinary;clock=Clock();app.now_utc=clock
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',lambda *a,**k:'F1 duplicate name')
    assert app.create_project();settled(app)
    parent=app.state['projects'][0]['project_id'];select(app,ui.project_row(parent))
    assert app.create_child_project();settled(app)
    child=next(p['project_id'] for p in app.state['projects'] if p['parent_project_id']==parent)
    select(app,ui.project_row(child));assert app.create_task();settled(app)
    key=app.selected_task_id();assert key and app.tree.parent(ui.task_row(key))==ui.project_row(child)
    submit(app,'add_date_only_work',task_id=key,entry_id=uid(),work_date='2026-10-19',duration_text='0:15',comment='F1 GUI work')
    select(app,ui.task_row(key));assert app.open_history()
    pump(app.root,lambda:app.history.current)
    assert len(app.history.rows)==1 and app.history.close()
    sheet=open_sheet(app);candidate=refresh(app,sheet);report_path=tmp_path/'frozen.txt'
    choose(monkeypatch,sheet,str(report_path));assert sheet.save();settled(app)
    saved=app._timesheet_attempt.candidate
    assert report_path.read_bytes()==candidate.report_utf8==saved.report_utf8
    assert sheet.review_polr();reviewed(app,sheet)
    assert sheet.confirm_polr();reviewed(app,sheet)
    batch=app._polr_submission.outcome.result['batch_id']
    assert app._polr_submission.outcome.status=='committed' and sheet.close()
    select(app,ui.task_row(key));assert app.start();settled(app)
    active=app.state['active'].copy();assert active['task_id']==key
    backup=tmp_path/'gui-backup.sqlite3';dialog=open_backup(app);dialog.destination.set(str(backup))
    assert dialog.create();assert wait_backup(app).verified and dialog.close()
    facts=logical(places.folder/'chronicle.sqlite3');identity=app.dataset_id
    timezone,week_start=app.state['timezone'],app.state['week_start']
    assert logical(backup)==facts and not app.root.test_errors
    app.request_close();exit_settled(app);worker.join(15)
    assert not worker.is_alive() and app._worker_stopped
    with pytest.raises(tk.TclError):app.root.winfo_exists()
    lock=DatasetLock(places.folder)
    try:lock.acquire()
    finally:lock.close()
    source_bytes=(places.folder/'chronicle.sqlite3').read_bytes();backup_bytes=backup.read_bytes()
    assert br.validate_image(backup).dataset_id==identity
    restored=tmp_path/'restored';assert not restored.exists()
    assert br.restore_image(backup,restored).verified
    assert br.inspect_dataset(restored).ordinary_startup_permitted
    assert logical(restored/'chronicle.sqlite3')==facts
    fresh_root=tk.Tk();errors=[];fresh_root.test_errors=errors
    fresh_root.report_callback_exception=lambda *args:errors.append(args)
    fresh=None
    try:
        restored_places=ls.Locations(restored,tmp_path/'restored-profile'/'selection.json')
        def application(root,worker,**kwargs):
            return ChronicleApp(root,worker,now_utc=clock,**kwargs)
        flow=StartupWindow(fresh_root,app_factory=application,worker_factory=DatabaseWorker,locations=restored_places)
        pump(fresh_root,lambda:flow.app is not None and flow.app.state.get('report') is not None)
        fresh=flow.app;fresh_worker=flow.worker
        assert fresh_root is not app.root and fresh_worker is not worker and type(fresh_worker) is DatabaseWorker
        assert fresh.presentation_profile=='schema4' and not fresh.candidate_presentation
        assert fresh.dataset_id==identity and fresh.state['timezone']==timezone and fresh.state['week_start']==week_start
        assert fresh.state['active']==active and logical(restored/'chronicle.sqlite3')==facts
        assert fresh.pending is None and fresh.editor is None and fresh.history is None and fresh.timesheet is None
        assert fresh_root.grab_current() is None and not errors
        # Read through the fresh app owner; never compete for its result queue.
        from test_timesheet_save_ui import saved_reports
        sheet=open_sheet(fresh);saved_reports(fresh,sheet,saved.export_id)
        assert sheet.candidate.report_utf8==saved.report_utf8
        assert sheet.confirmation_history();reviewed(fresh,sheet)
        assert batch in sheet.polr_tree.get_children()
        assert sheet.close() and logical(restored/'chronicle.sqlite3')==facts
        clock.value+=timedelta(minutes=2)
        assert fresh.stop();settled(fresh)
        assert fresh.state['active'] is None
        select(fresh,ui.task_row(key));assert fresh.open_history()
        pump(fresh_root,lambda:fresh.history.current)
        timed=[r for r in fresh.history.rows if r['entry_id']==active['entry_id']]
        assert len(timed)==1 and timed[0]['duration_us']==120_000_000
        assert fresh.history.close()
        after=logical(restored/'chronicle.sqlite3')
        assert len([r for r in after['work_revisions'] if r[0]==active['entry_id']])==1
        assert after['timesheet_exports']==facts['timesheet_exports']
        assert after['polr_confirmation_cells']==facts['polr_confirmation_cells']
        assert (places.folder/'chronicle.sqlite3').read_bytes()==source_bytes and backup.read_bytes()==backup_bytes
        assert not errors
        fresh.request_close();exit_settled(fresh);fresh_worker.join(15)
        assert not fresh_worker.is_alive() and fresh._worker_stopped
        lock=DatasetLock(restored)
        try:lock.acquire()
        finally:lock.close()
        record(tmp_path/'gui-restore-evidence.json',dataset_id=identity,task_id=key,active=active,
               report_id=saved.export_id,confirmation_batch=batch,before=facts,after=after,
               original_worker_stopped=not worker.is_alive(),restored_worker_stopped=not fresh_worker.is_alive())
    finally:
        if fresh is not None and fresh.alive:fresh_root.destroy()
        else:
            try:fresh_root.destroy()
            except tk.TclError:pass
        if 'flow' in locals() and flow.worker is not None:
            if flow.worker.is_alive():flow.worker.requests.put(Message('shutdown'))
            flow.worker.join(15);assert not flow.worker.is_alive()


def test_ordinary_schema4_cancel_and_incompatible_startup_preserve_sources(root,tmp_path):
    from chronicle.timesheet_files import metadata
    from test_timesheet_save_ui import exit_settled
    from test_package_f_runtime4 import record
    workers=[]
    def factory(*args,**kwargs):
        worker=DatabaseWorker(*args,**kwargs);workers.append(worker);return worker
    places=ls.Locations(tmp_path/'fresh',tmp_path/'profile'/'selection.json')
    canceled=StartupWindow(root,app_factory=ChronicleApp,worker_factory=factory,locations=places)
    pump(root,lambda:canceled.discover_id is None)
    canceled.cancel()
    assert not workers and not places.folder.exists() and not places.record.exists()
    with pytest.raises(tk.TclError):root.winfo_exists()
    created_root=tk.Tk();errors=[];created_root.test_errors=errors
    created_root.report_callback_exception=lambda *args:errors.append(args)
    flow=None
    try:
        flow=StartupWindow(created_root,app_factory=ChronicleApp,worker_factory=factory,locations=places)
        pump(created_root,lambda:flow.discover_id is None)
        flow.begin(places.folder,create=True,timezone='America/Chicago')
        pump(created_root,lambda:flow.app is not None and flow.app.state.get('report') is not None)
        assert flow.app.presentation_profile=='schema4' and flow.app.state['semantic_verified']
        assert len(workers)==1 and workers[0].is_alive() and not errors
        flow.app.request_close();exit_settled(flow.app);workers[0].join(15)
        assert not workers[0].is_alive()
    finally:
        try:created_root.destroy()
        except tk.TclError:pass
        for worker in workers:
            if worker.is_alive():worker.requests.put(Message('shutdown'));worker.join(15)
    legacy=tmp_path/'legacy';store=SQLiteStore(legacy,create=True,timezone='Etc/UTC',schema_version=3)
    path=store.path;store.close();raw=path.read_bytes();identity=metadata(path.stat())
    bad_places=ls.Locations(tmp_path/'never-created',tmp_path/'legacy-profile'/'selection.json')
    ls.remember(bad_places.record,legacy,None);selection_bytes=bad_places.record.read_bytes()
    refused_root=tk.Tk();refused_errors=[];refused_root.test_errors=refused_errors
    refused_root.report_callback_exception=lambda *args:refused_errors.append(args)
    refused=None
    try:
        refused=StartupWindow(refused_root,app_factory=ChronicleApp,worker_factory=factory,locations=bad_places)
        pump(refused_root,lambda:refused.failure is not None and refused.worker is None)
        assert refused.app is None and 'require schema 4' in str(refused.failure)
        assert len(workers)==2 and all(not w.is_alive() for w in workers)
        assert path.read_bytes()==raw and metadata(path.stat())==identity
        assert bad_places.record.read_bytes()==selection_bytes and not bad_places.folder.exists()
        assert refused_root.grab_current() is None and not refused_errors
        record(tmp_path/'startup-evidence.json',cancel_created_nothing=True,workers=[dict(name=w.name,alive=w.is_alive()) for w in workers],
               incompatible_error=str(refused.failure),schema3_metadata=identity)
        refused.cancel()
    finally:
        try:refused_root.destroy()
        except tk.TclError:pass
        for worker in workers:
            if worker.is_alive():worker.requests.put(Message('shutdown'));worker.join(15)
        assert all(not w.is_alive() for w in workers)
