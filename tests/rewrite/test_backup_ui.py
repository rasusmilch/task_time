"""Application-owned Backup: real worker/SQLite, callback faults and XTest input."""
from dataclasses import replace
import threading
import tkinter as tk

import pytest

from chronicle import backup_restore as br
from chronicle.records import Outcome, Request
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.worker import Message
from conftest import NOW,uid
from test_app import root,connected,click,pump,create
from test_backup_restore import logical
from test_chronicle_history_ui import selected_task,mutation
from test_chronicle_timesheet_ui import open_sheet,refresh
from test_timesheet_save_ui import choose,settled,exit_settled


def open_backup(app):
    assert app.open_backup()
    dialog=app.backup_dialog
    pump(app.root,lambda:dialog.presented)
    assert app.root.grab_current() is dialog.window
    return dialog


def wait_backup(app):
    pump(app.root,lambda:app._backup_operation is not None and not app._backup_operation.busy)
    return app._backup_operation.result


def test_owned_callback_chooser_cancel_reentry_and_no_constructor_io(connected,root,monkeypatch):
    app,worker,clock=connected;before=logical(worker.directory/'chronicle.sqlite3')
    dialog=open_backup(app)
    assert dialog.destination.get()=='' and app._backup_operation is None
    assert not app.open_backup() and not app.open_timesheet() and not app.open_history()
    def canceled(**kw):
        assert kw['parent'] is dialog.window and not kw['confirmoverwrite']
        assert not dialog.close() and not dialog.create() and not dialog.choose()
        app.request_close();assert app.alive and not app.closing
        return ''
    monkeypatch.setattr('chronicle.app.filedialog.asksaveasfilename',canceled)
    assert not dialog.choose() and dialog.destination.get()==''
    assert app._backup_operation is None and logical(worker.directory/'chronicle.sqlite3')==before
    assert root.grab_current() is dialog.window and dialog.close()
    assert app.backup_dialog is None and root.grab_current() is None
    assert not root.test_errors


def test_guarded_open_during_editor_history_timesheet_pending_shutdown_and_competitor(connected,root):
    app,worker,clock=connected;task=selected_task(app)
    assert app.open_history();pump(root,lambda:app.history.presented)
    assert not app.open_backup();app.history.close()
    sheet=open_sheet(app);assert not app.open_backup();sheet.close()
    app.pending=Request.make(uid(),app.dataset_id,'create_project',NOW,project_id=uid(),name='pending')
    assert not app.open_backup();app.pending=None
    app.executing=True;assert not app.open_backup();app.executing=False
    app.closing=True;assert not app.open_backup();app.closing=False
    top=tk.Toplevel(root);pump(root,lambda:top.winfo_ismapped());top.grab_set()
    assert not app.open_backup() and root.grab_current() is top
    assert root.test_errors and 'unrelated' in str(root.test_errors[-1][1])
    top.destroy()


def test_slow_backup_busy_responsive_destroyed_dialog_owner_result_and_following_mutation(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;task=selected_task(app)
    app.tree.selection_set(task);assert app.start()
    pump(root,lambda:app.pending is None and app.state['active'] is not None)
    active=dict(app.state['active']);before=logical(worker.directory/'chronicle.sqlite3')
    entered,release=threading.Event(),threading.Event();copy=br._copy;threads=[]
    def slow(source,stage):
        threads.append(threading.get_ident());entered.set()
        assert release.wait(5)
        copy(source,stage)
    monkeypatch.setattr(br,'_copy',slow)
    dialog=open_backup(app);dialog.destination.set(str(tmp_path/'backup'))
    assert dialog.create();operation=app._backup_operation
    try:
        pump(root,entered.is_set)
        assert not dialog.create() and not dialog.choose() and not dialog.close()
        assert all(w.instate(['disabled']) for w in (dialog.create_button,dialog.choose_button,dialog.close_button,dialog.path_entry))
        app.request_close();assert not app.closing
        clock.value+=__import__('datetime').timedelta(seconds=2)
        calls_before=clock.calls
        heartbeat=[];root.after(1200,lambda:heartbeat.append(True));pump(root,lambda:heartbeat)
        assert app.state['active']==active and '00:00:02' not in app.active_label.cget('text')
        assert 'elapsed 00:00' in app.active_label.cget('text') and clock.calls>calls_before
        dialog.window.destroy()
        assert app.backup_dialog is None and app._backup_operation is operation and operation.busy
        assert not app.open_backup() and not app.stop()
    finally:release.set()
    result=wait_backup(app)
    assert result.verified and operation.result is result and threads==[worker.ident]
    assert logical(worker.directory/'chronicle.sqlite3')==before
    assert 'Backup verified' in app.status.cget('text')
    app._handle(Message('backup',operation.token,{'request_id':operation.request_id,'result':Outcome('unavailable',error=OSError('duplicate'))}))
    assert operation.result is result and not operation.busy
    assert app.stop();pump(root,lambda:app.pending is None and app.state['active'] is None)
    assert not root.test_errors


def test_backup_failure_retains_path_primary_diagnostic_stale_completion_and_explicit_validation(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;dialog=open_backup(app);target=tmp_path/'existing';target.write_bytes(b'keep')
    dialog.destination.set(str(target));assert dialog.create()
    result=wait_backup(app)
    assert not result.verified and target.read_bytes()==b'keep'
    assert dialog.destination.get()==str(target) and 'not verified' in dialog.status.cget('text')
    assert root.test_errors[-1][1] is result.error
    old=app._backup_operation;assert dialog.close()
    new=open_backup(app);assert new.destination.get()==''
    app._handle(Message('backup',old.token,{'request_id':old.request_id,'result':result}))
    assert new.destination.get()=='' and 'Choose a new' in new.status.cget('text')
    new.destination.set(str(tmp_path/'good'));assert new.create();assert wait_backup(app).verified
    assert new.close()


def test_real_tk_server_input_backup_modal_main_mini_blocking_success_and_shutdown(connected,root,click,tmp_path,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);app.tree.selection_set(task)
    click(app.buttons['Start']);pump(root,lambda:app.pending is None and app.state['active'] is not None)
    active=dict(app.state['active']);clock.value+=__import__('datetime').timedelta(minutes=1)
    app.open_mini();mini=app.mini
    click(app.buttons['Backup Chronicle']);dialog=app.backup_dialog
    pump(root,lambda:dialog.presented)
    assert root.grab_current() is dialog.window
    assert not app.open_backup()
    chooser=[]
    def choose_file(**kw):
        chooser.append(kw);assert kw['parent'] is dialog.window
        return '' if len(chooser)==1 else str(tmp_path/'actual.sqlite3')
    monkeypatch.setattr('chronicle.app.filedialog.asksaveasfilename',choose_file)
    click(dialog.choose_button);assert dialog.destination.get()==''
    click(dialog.choose_button);assert dialog.destination.get()==str(tmp_path/'actual.sqlite3')
    pump(root,lambda:app._read_inflight is None)
    probes=[]
    original_stop=app.buttons['Stop'].cget('command');original_toggle=mini.toggle.cget('command')
    # Enabled probes distinguish server grab routing from disabled-control safety.
    app.buttons['Stop'].configure(state='normal',command=lambda:probes.append('main'))
    mini.toggle.configure(state='normal',command=lambda:probes.append('mini'))
    mini.window.geometry('340x180+10+600');mini.window.lift()
    click(app.buttons['Stop']);mini.window.lift();click(mini.toggle)
    assert probes==[]
    app.buttons['Stop'].configure(state='disabled',command=original_stop)
    mini.toggle.configure(state='disabled',command=original_toggle)
    dialog.window.lift()
    assert app.state['active']==active and app.pending is None and root.grab_current() is dialog.window
    before=logical(worker.directory/'chronicle.sqlite3')
    click(dialog.create_button);result=wait_backup(app)
    assert result.verified and logical(result.destination)==before==logical(worker.directory/'chronicle.sqlite3')
    assert 'Backup verified' in dialog.status.cget('text')
    click(dialog.close_button);assert app.backup_dialog is None and root.grab_current() is None
    mini.window.lift()
    click(mini.toggle);pump(root,lambda:app.pending is None and app.state['active'] is None)
    app.request_close();exit_settled(app)
    assert not root.test_errors


def test_connected_saved_confirmed_dismissed_backup_and_cold_recovery(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;first=selected_task(app);second=create(app,'Second')
    mutation(app,'add_timed_work',task_id=first,entry_id=uid(),start_date='2026-10-19',start_time='08:00',end_date='2026-10-19',end_time='09:00',start_occurrence=None,end_occurrence=None,comment='timed')
    entry=uid()
    mutation(app,'add_date_only_work',task_id=first,entry_id=entry,work_date='2026-10-19',duration_text='0:20',comment='dated')
    mutation(app,'edit_date_only_work',task_id=first,entry_id=entry,expected_revision=1,work_date='2026-10-19',duration_text='0:21',comment='corrected')
    app.tree.selection_set(second);assert app.start();settled(app);active=dict(app.state['active'])
    sheet=open_sheet(app);candidate=refresh(app,sheet)
    choose(monkeypatch,sheet,str(tmp_path/'report.txt'));assert sheet.save();settled(app)
    saved=app._timesheet_attempt.candidate
    # Existing source/manual confirmation controls route through the owner; use
    # their authoritative worker boundary with freshly reviewed receipt inputs.
    assert sheet.close()
    from test_worker import receive
    worker.requests.put(Message('polr_proposal',901,saved.export_id));p=receive(worker,'polr_proposal')
    mutation(app,'confirm_polr_absolute',batch_id=uid(),mode='source',source_export_id=saved.export_id,**p,manual_cells=[],acknowledgements=[])
    for key,value,day in ((first,9,'2026-10-19'),(second,0,'2026-10-20')):
        worker.requests.put(Message('polr_manual',902,dict(task_id=key,work_date=day,cutoff_utc_us=NOW)))
        # Current prior is independently read; all mutations remain normal requests.
        context=receive(worker,'polr_manual')
        assert not isinstance(context,Outcome)
        # Use an independent readonly query only in this test to review the prior.
        import sqlite3
        c=sqlite3.connect((worker.directory/'chronicle.sqlite3').as_uri()+'?mode=ro',uri=True)
        try:r=c.execute('SELECT p.batch_id,c.confirmed_quarters FROM polr_confirmed_current p JOIN polr_confirmation_cells c USING(batch_id,task_id,work_date) WHERE p.task_id=? AND p.work_date=?',(key,day)).fetchone()
        finally:c.close()
        mutation(app,'confirm_polr_absolute',batch_id=uid(),mode='manual',source_export_id=None,source_metadata=None,reviewed_rows=[],selected_keys=[],manual_cells=[dict(task_id=key,work_date=day,confirmed_quarters=value,prior_batch_id=r[0] if r else None,prior_quarters=r[1] if r else None)],acknowledgements=[])
    assert app.dismiss_polr_today();settled(app)
    before=logical(worker.directory/'chronicle.sqlite3');original=(worker.directory/'chronicle.sqlite3').read_bytes()
    dialog=open_backup(app);dialog.destination.set(str(tmp_path/'backup.sqlite3'));assert dialog.create();assert wait_backup(app).verified
    assert app.state['active']==active and dialog.close()
    app.request_close();exit_settled(app)
    backup=tmp_path/'backup.sqlite3';raw=backup.read_bytes()
    assert br.validate_image(backup).dataset_id==app.dataset_id
    restored=br.restore_image(backup,tmp_path/'restore');assert restored.verified
    assert logical(restored.destination)==before
    recovered=SQLiteStore(tmp_path/'restore')
    try:
        s=TimerService(recovered)
        assert s.read_current_state(cutoff_utc_us=NOW)['active']==active
        assert s.read_registered_timesheet_export(saved.export_id)==saved
        assert s.read_polr_reconciliation(cutoff_utc_us=NOW)['dataset_id']==app.dataset_id
        assert recovered.dismissed_date(recovered.connection)=='2026-10-19'
        assert s.add_date_only_work(first,uid(),'2026-10-19','0:01',request_id=uid(),action_utc_us=NOW).status=='committed'
    finally:recovered.close()
    assert backup.read_bytes()==raw and (worker.directory/'chronicle.sqlite3').read_bytes()==original
    assert (tmp_path/'report.txt').read_bytes()==saved.report_utf8
    assert not root.test_errors


@pytest.mark.parametrize('global_grab',[False,True])
def test_presentation_rechecks_competing_grab_after_construction(connected,root,global_grab):
    app,worker,clock=connected
    top=tk.Toplevel(root);pump(root,lambda:top.winfo_ismapped())
    assert app.open_backup()
    if global_grab:top.grab_set_global()
    else:top.grab_set()
    pump(root,lambda:app.backup_dialog is None)
    assert root.grab_current() is top
    assert top.grab_status()==('global' if global_grab else 'local')
    assert app._backup_operation is None and not app._backup_opening
    assert root.test_errors and 'ownership' in str(root.test_errors[-1][1])
    top.destroy()


def test_known_completion_survives_presentation_fault(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;dialog=open_backup(app);dialog.destination.set(str(tmp_path/'backup'))
    primary=RuntimeError('presentation fault')
    def fail(**kw):raise primary
    monkeypatch.setattr(dialog.status,'configure',fail)
    # Submit before the injected post-result presentation failure.
    monkeypatch.undo()
    assert dialog.create()
    monkeypatch.setattr(dialog.status,'configure',fail)
    result=wait_backup(app)
    assert result.verified and not app._backup_operation.busy
    assert root.test_errors[-1][1] is primary
    monkeypatch.undo()
    assert dialog.close()


def test_real_tk_server_failure_busy_close_and_explicit_recovery(connected,root,click,tmp_path,monkeypatch):
    app,worker,clock=connected
    click(app.buttons['Backup Chronicle']);dialog=app.backup_dialog;pump(root,lambda:dialog.presented)
    target=tmp_path/'existing';target.write_bytes(b'keep')
    monkeypatch.setattr('chronicle.app.filedialog.asksaveasfilename',lambda **kw:str(target))
    click(dialog.choose_button);click(dialog.create_button)
    result=wait_backup(app);assert not result.verified and target.read_bytes()==b'keep'
    assert dialog.destination.get()==str(target) and root.test_errors[-1][1] is result.error
    entered,release=threading.Event(),threading.Event();copy=br._copy
    def slow(source,stage):
        entered.set();assert release.wait(5);copy(source,stage)
    monkeypatch.setattr(br,'_copy',slow)
    target=tmp_path/'recovered';click(dialog.choose_button);click(dialog.create_button)
    try:
        pump(root,entered.is_set)
        click(dialog.close_button);assert not dialog.disposed
        assert not dialog.create() and not dialog.choose()
        root.tk.call(root.protocol('WM_DELETE_WINDOW'))
        assert app.alive and not app.closing and root.grab_current() is dialog.window
    finally:release.set()
    assert wait_backup(app).verified
    click(dialog.close_button);assert app.backup_dialog is None
    app.request_close();exit_settled(app)


def test_constructor_and_cleanup_faults_preserve_primary_and_release_guards(connected,root,monkeypatch):
    app,worker,clock=connected
    primary=RuntimeError('construction failure')
    def fail(*a):raise primary
    with monkeypatch.context() as m:
        m.setattr('chronicle.app.BackupDialog',fail)
        assert not app.open_backup()
    assert root.test_errors[-1][1] is primary and app.backup_dialog is None and not app._backup_opening
    dialog=open_backup(app)
    cleanup=RuntimeError('grab release failure')
    def release():raise cleanup
    monkeypatch.setattr(dialog.window,'grab_release',release)
    with pytest.raises(RuntimeError) as error:dialog.close()
    assert error.value is cleanup and dialog.disposed and app.backup_dialog is None and root.grab_current() is None
    assert not app._backup_opening and app.can_mutate()


def test_source_root_destroyed_during_construction_diagnoses_original(connected,root,monkeypatch):
    app,worker,clock=connected;primary=RuntimeError('root disappeared during construction');diagnostics=[]
    def construction(owner):
        root.destroy()
        raise primary
    monkeypatch.setattr('chronicle.app.BackupDialog',construction)
    monkeypatch.setattr(app,'_diagnose',diagnostics.append)
    assert not app.open_backup() and diagnostics==[primary]
    assert not app.alive and not app._backup_opening


def test_root_destruction_queues_shutdown_after_accepted_backup(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;dialog=open_backup(app);target=tmp_path/'backup'
    dialog.destination.set(str(target));entered,release=threading.Event(),threading.Event();copy=br._copy
    def slow(source,stage):
        entered.set();assert release.wait(5);copy(source,stage)
    monkeypatch.setattr(br,'_copy',slow)
    assert dialog.create();operation=app._backup_operation
    try:
        pump(root,entered.is_set)
        root.destroy();assert not app.alive and app._shutdown_sent
    finally:release.set()
    # No UI remains; the owning worker completes accepted I/O before its queued
    # shutdown. The test reads the final message without installing old callbacks.
    from test_worker import receive
    result=receive(worker,'backup')
    assert result['request_id']==operation.request_id and result['result'].verified
    receive(worker,'stopped');worker.join(5)
    assert not worker.is_alive() and br.validate_image(target).dataset_id==app.dataset_id
    assert not root.test_errors


def test_verified_file_cleanup_failure_is_not_reported_as_unverified_content(connected,root,tmp_path,monkeypatch):
    app,worker,clock=connected;dialog=open_backup(app);target=tmp_path/'backup'
    dialog.destination.set(str(target));primary=OSError('owned staging cleanup fault')
    def fail(*a):raise primary
    monkeypatch.setattr(br,'_remove_owned',fail)
    assert dialog.create();result=wait_backup(app)
    assert result.phase is br.BackupPhase.VERIFIED and result.error is primary and not result.verified
    assert br.validate_image(target).dataset_id==app.dataset_id
    assert 'Backup file verified; temporary cleanup did not complete.' in dialog.status.cget('text')
    assert root.test_errors[-1][1] is primary and dialog.close()
