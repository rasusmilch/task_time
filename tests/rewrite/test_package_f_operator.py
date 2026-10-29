"""Connected real-Tk qualification. Callback and XTest evidence stay distinct."""
from datetime import timedelta
from dataclasses import replace
from pathlib import Path
import tkinter as tk

from chronicle import backup_restore as br
from chronicle.app import ChronicleApp
from chronicle.worker import DatabaseWorker
from conftest import uid, NOW
from test_app import root, connected, click, keyboard, pump, Clock
from test_main_explorer import project, task, submit, select, settled
from test_hierarchy_ui import apply_move
from test_archived_items import archive, window, choose as choose_archived
from test_delete_ui import opened, authorize
from test_template_ui import manager, ready as template_ready, choose as choose_template
from test_chronicle_history_ui import open_history, select as select_history, fill, settled as history_settled
from test_chronicle_timesheet_ui import open_sheet, refresh
from test_polr_confirmation_ui import reviewed
from test_reconciliation_ui import reconciled
from test_timesheet_save_ui import choose, exit_settled
from test_backup_ui import open_backup, wait_backup
from test_backup_restore import logical


def workflow(app, worker, clock, tmp_path, monkeypatch, activate):
    """One dataset across real controls; chooser/name responses explicitly doubled.

    activate is either Button.invoke or existing server-delivered pointer input.
    All SQLite use remains worker-owned; independent reads only collect evidence.
    """
    p, q = project(app,'Original'), project(app,'Destination')
    parent = task(app,'Parent',p)
    entry=uid()
    submit(app,'add_date_only_work',task_id=parent,entry_id=entry,work_date='2026-10-19',duration_text='0:10',comment='retained parent work')
    select(app,app.task_row(parent))
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',lambda *a,**k:'Child')
    activate(app.buttons['New Task']);settled(app)
    child=app.selected_task_id()
    assert app.tree.parent(app.task_row(child))==app.task_row(parent)
    assert next(t for t in app.state['tasks'] if t['task_id']==parent)['version']==1
    select(app,app.task_row(parent));activate(app.buttons['Work History'])
    pump(app.root,lambda:app.history is not None and app.history.current)
    h=app.history;assert {r['entry_id'] for r in h.mapping.values()}=={entry}
    select_history(h,entry);activate(h.edit_button);fill(h,duration_text='0:15');activate(h.save_button)
    history_settled(app,h);activate(h.close_button);settled(app)
    assert app.tree.item(app.task_row(parent),'values')[1:]==('00:15','00:15')
    m=manager(app);before=logical(Path(worker.directory)/'chronicle.sqlite3')
    assert m.edit(False);editor=template_ready(app);editor.title.set('Blueprint')
    names=iter(['Template root','Template leaf'])
    monkeypatch.setattr('chronicle.template_window.simpledialog.askstring',lambda *a,**k:next(names))
    activate(editor.draft_buttons['Add root']);activate(editor.draft_buttons['Add child'])
    assert logical(Path(worker.directory)/'chronicle.sqlite3')==before
    activate(editor.confirm_button);settled(app);key=editor.key;assert editor.close()
    choose_template(m,key);assert m.edit(True);editor=template_ready(app);editor.title.set('Cancelled change')
    assert editor.close();assert next(t for t in app.state['templates'] if t['template_id']==key)['name']=='Blueprint'
    select(app,app.project_row(p));choose_template(m,key);activate(m.buttons['Apply']);d=template_ready(app)
    assert not app.start() and not app.open_mini() and not app.open_backup()
    activate(d.confirm_button);settled(app);created=app._mutation_outcome.result['created_tasks'];assert d.close()
    leaf=created[-1]['task_id'];branch=created[0]['task_id']
    assert app.tree.parent(app.task_row(leaf))==app.task_row(branch)
    assert m.close()
    apply_move(app,branch,app.project_row(q))
    assert app.tree.parent(app.task_row(branch))==app.project_row(q)
    select(app,app.task_row(leaf));activate(app.buttons['Start']);settled(app)
    active=dict(app.state['active']);activate(app.buttons['Mini mode']);assert app.mini is not None
    assert 'Running' in app.mini.state_bar.cget('text') and not app.keep_mini_open.get()
    assert app.open_history();pump(app.root,lambda:app.history.presented)
    grab=app.root.grab_current();assert not app.mini_toggle() and not app.open_templates() and app.root.grab_current() is grab
    app.history.close();app.show_main();assert app.mini is None
    clock.value+=timedelta(minutes=3);activate(app.buttons['Stop']);settled(app)
    assert app.state['active'] is None
    archive(app,'task',branch);view=window(app)
    assert view.tree.parent(app.task_row(leaf))==app.task_row(branch)
    choose_archived(view,app.task_row(branch));assert view.unarchive();settled(app);assert view.close()
    assert app.tree.parent(app.task_row(leaf))==app.task_row(branch)
    blocked=opened(app,app.task_row(branch));assert not blocked.review['eligible'] and blocked.close()
    unused=task(app,'Unused');d=opened(app,app.task_row(unused));assert d.review['eligible']
    assert authorize(d);settled(app);assert d.close() and not app.tree.exists(app.task_row(unused))
    select(app,app.task_row(leaf));sheet=open_sheet(app);candidate=refresh(app,sheet)
    report=tmp_path/'frozen.txt';choose(monkeypatch,sheet,str(report));activate(sheet.save_button);settled(app)
    candidate=replace(candidate,preferred_destination=str(report))  # Registration freezes this field.
    assert report.read_bytes()==candidate.report_utf8
    activate(sheet.review_polr_button);reviewed(app,sheet)
    activate(sheet.polr_confirm_button);reviewed(app,sheet)
    activate(sheet.reconciliation_button);reconciliation=reconciled(app,sheet)
    assert any(c['task_id']==leaf and c['confirmed_quarters'] is not None for c in reconciliation['daily_cells'])
    activate(sheet.close_button);pump(app.root,lambda:app.timesheet is None)
    # Recover the same report without the discarded preview widget.
    sheet=open_sheet(app);assert sheet.saved_reports();pump(app.root,lambda:sheet.saved_token is None)
    sheet.saved_list.selection_set(candidate.export_id);assert sheet.load_saved()
    pump(app.root,lambda:sheet.saved_token is None)
    assert sheet.candidate==candidate and sheet.report.get('1.0','end-1c')==candidate.report_text
    # The service evidence, not an old widget, supplies exact original bytes.
    assert any(r[0]==candidate.export_id for r in logical(Path(worker.directory)/'chronicle.sqlite3')['timesheet_exports'])
    sheet.close()
    select(app,app.task_row(leaf));assert app.start();settled(app);active=dict(app.state['active'])
    backup=tmp_path/'online.sqlite3';d=open_backup(app);d.destination.set(str(backup));assert d.create();assert wait_backup(app).verified;assert d.close()
    original=logical(Path(worker.directory)/'chronicle.sqlite3');assert logical(backup)==original
    app.request_close();exit_settled(app);worker.join(8);assert not worker.is_alive()
    restored=tmp_path/'restored';assert br.validate_image(backup).dataset_id==app.dataset_id
    assert br.restore_image(backup,restored).verified
    original_bytes=Path(worker.directory,'chronicle.sqlite3').read_bytes();image_bytes=backup.read_bytes()
    # The first root has been destroyed by normal Close before creating this root.
    fresh_root=tk.Tk();errors=[];fresh_root.report_callback_exception=lambda *e:errors.append(e)
    fresh_worker=DatabaseWorker(restored);fresh=ChronicleApp(fresh_root,fresh_worker,now_utc=clock);fresh_worker.start()
    try:
        pump(fresh_root,lambda:fresh.ready and fresh.state.get('report') is not None)
        assert fresh.dataset_id==app.dataset_id and fresh.state['active']==active and fresh.pending is None
        assert fresh._timesheet_attempt is None and fresh.template_dialog is None
        assert logical(restored/'chronicle.sqlite3')==original
        clock.value+=timedelta(minutes=1);assert fresh.stop();settled(fresh)
        assert len(logical(restored/'chronicle.sqlite3')['work_entries'])==len(original['work_entries'])
        for table in ('timesheet_exports','timesheet_export_cells','polr_confirmation_batches','polr_confirmation_cells','template_definitions','template_nodes'):
            assert logical(restored/'chronicle.sqlite3')[table]==original[table]
        fresh.request_close();exit_settled(fresh)
    finally:
        if fresh.alive:fresh_root.destroy()
        fresh_worker.join(8);assert not fresh_worker.is_alive()
    assert not errors and not app.root.test_errors
    assert Path(worker.directory,'chronicle.sqlite3').read_bytes()==original_bytes and backup.read_bytes()==image_bytes
    assert report.read_bytes()==candidate.report_utf8 and br.inspect_dataset(restored).ordinary_startup_permitted


def test_real_tk_connected_callback_workflow_restore_fresh_owner(connected,tmp_path,monkeypatch):
    app,worker,clock=connected
    workflow(app,worker,clock,tmp_path,monkeypatch,lambda button:button.invoke())


def test_real_tk_connected_server_input_workflow_restore_fresh_owner(connected,click,keyboard,tmp_path,monkeypatch):
    app,worker,clock=connected
    def activate(button):
        button.winfo_toplevel().lift()
        app.root.update_idletasks()
        click(button)
    workflow(app,worker,clock,tmp_path,monkeypatch,activate)
