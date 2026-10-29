"""Connected portable recovery and delivery evidence; native qualification is separate."""
from dataclasses import replace
import sqlite3
import threading

import pytest

from chronicle.records import Outcome,Request
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.worker import Message,DatabaseWorker
from conftest import NOW,uid
from test_app import root,connected,click,keyboard,pump,create,evidence
from test_manual_entry_ui import select_task,fill
from test_backup_restore import logical,rich
from test_services import FaultConnection
from test_timesheet_save_ui import exit_settled


def test_main_presentation_fault_cannot_lose_committed_editor_outcome(connected,root,monkeypatch):
    app,worker,clock=connected;select_task(app);app.add_date_only_work();session=app._work_editor
    fill(session,('2026-10-19','0:15','reviewed'))
    session.save.invoke();request=app.pending;primary=RuntimeError('main status presentation failed')
    configure=app.status.configure
    def fail(**kwargs):
        if kwargs.get('text')=='Saved.':raise primary
        return configure(**kwargs)
    monkeypatch.setattr(app.status,'configure',fail)
    pump(root,lambda:app.pending is None and not app.executing)
    assert session.outcome is not None and session.outcome.status=='committed'
    assert session.phase=='complete' and app.editor is None
    assert any(e[1] is primary for e in root.test_errors)
    assert any(row[1]==request.request_id for row in evidence(worker)['committed_requests'])


def test_definitive_worker_stop_retains_uncertainty_without_queueing_dead_worker(connected,root,monkeypatch):
    app,worker,clock=connected;task=select_task(app)
    # Stop the actual owner after an ordinary clean session, then simulate the
    # delivery boundary where the UI accepted a request but receives no result.
    worker.requests.put(Message('shutdown'));worker.join(5);assert not worker.is_alive()
    request=Request.make(uid(),app.dataset_id,'start_timer',NOW,task_id=task,entry_id=uid(),expected_task_version=1)
    app.pending,app.executing,app._pending_token=request,True,900
    pump(root,lambda:app._worker_stopped)
    assert app.pending is request and not app.executing and not app.ready
    count=worker.requests.qsize();assert not app.retry() and worker.requests.qsize()==count
    assert 'may have committed' in app.status.cget('text') and app.retry_button.instate(['disabled'])
    app.request_close();assert app.closing and app.alive and app.pending is request
    decisions=[]
    def cancel(*args,**kwargs):decisions.append(kwargs);return False
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',cancel)
    assert not app.exceptional_exit() and app.alive and app.pending is request
    assert decisions[-1]['default']=='no'
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',lambda *a,**kw:True)
    assert app.exceptional_exit() and not app.alive
    reopened=SQLiteStore(worker.directory)
    try:
        assert TimerService(reopened).reconcile_request(request).status=='absent'
        assert not reopened.connection.execute('SELECT 1 FROM active_timer').fetchone()
    finally:reopened.close()


@pytest.mark.parametrize('operation',['edit','confirm','switch'])
@pytest.mark.parametrize('fault',['begin','fact','evidence','reference','receipt','final','commit_before','commit_after','probe'])
def test_complete_facts_and_receipts_under_transaction_faults(service,task,store,monkeypatch,operation,fault):
    from test_manual_work import dated,M
    from test_polr_confirmation import manual
    entry=dated(service,task,duration='0:21')
    if operation=='edit':
        op='edit_date_only_work';args=dict(task_id=task,entry_id=entry,work_date='2026-10-20',duration_text='0:22',expected_revision=1,comment='revised')
    elif operation=='confirm':op='confirm_polr_absolute';args=manual(service,task,0)
    else:
        other=uid();assert service.create_task(other,'Other',request_id=uid(),action_utc_us=NOW).status=='committed'
        active=uid();assert service.start_timer(task,active,expected_task_version=1,request_id=uid(),action_utc_us=NOW-M).status=='committed'
        op='switch_timer';args=dict(expected_active_entry_id=active,expected_active_version=1,next_task_id=other,next_entry_id=uid(),expected_task_version=1)
    request=Request.make(uid(),store.dataset_id,op,NOW,**args)
    before=logical(store.path);real=store.connection;fired=[];probe=store._probe
    primary=sqlite3.OperationalError('simulated SQLITE_FULL / ENOSPC boundary')
    class Fault:
        def __getattr__(self,name):return getattr(real,name)
        def execute(self,sql,*a):
            check=(fault=='begin' and sql=='BEGIN IMMEDIATE' or
                   fault=='fact' and sql.startswith(('UPDATE work_entries','INSERT INTO polr_confirmation_batches','DELETE FROM active_timer')) or
                   fault=='evidence' and sql.startswith(('INSERT INTO work_revisions','INSERT INTO polr_confirmation_cells')) or
                   fault=='reference' and sql.startswith(('UPDATE work_entries','INSERT INTO polr_confirmed_current','INSERT INTO active_timer')) or
                   fault=='receipt' and sql.startswith('INSERT INTO committed_requests'))
            if not fired and check:
                fired.append(True);raise primary
            if sql=='COMMIT' and fault in ('commit_before','commit_after','probe'):
                fired.append(True)
                if fault!='commit_before':real.execute(sql,*a)
                raise primary
            return real.execute(sql,*a)
    store.connection=Fault()
    original_final=store.assert_confirmations
    if fault=='final':
        def final(c):
            if c.execute('SELECT 1 FROM committed_requests WHERE request_id=?',(request.request_id,)).fetchone():
                fired.append(True);raise primary
            return original_final(c)
        monkeypatch.setattr(store,'assert_confirmations',final)
    if fault=='probe':
        def offline():raise OSError('independent committed lookup unavailable')
        monkeypatch.setattr(store,'_probe',offline)
    outcome=service.execute(request)
    assert fired,('fixture did not establish boundary',operation,fault)
    expected='committed' if fault=='commit_after' else 'unverified' if fault=='probe' else 'unavailable' if fault=='begin' else 'rolled_back'
    assert outcome.status==expected and outcome.error is primary
    monkeypatch.setattr(store,'_probe',probe);monkeypatch.setattr(store,'assert_confirmations',original_final)
    committed=fault in ('commit_after','probe')
    after=logical(store.path)
    if not committed:assert after==before
    else:
        assert after!=before
        assert sum(r[1]==request.request_id for r in after['committed_requests'])==1
    resolved=service.reconcile_request(request)
    assert resolved.status==('committed' if committed else 'absent')
    if committed:
        dated(service,task,duration='0:01',comment='newer work survives exact retry')
        after=logical(store.path)
        assert service.execute(request).status=='committed' and logical(store.path)==after
        changed=replace(request,action_utc_us=NOW+1)
        assert service.execute(changed).status=='rejected' and logical(store.path)==after


def test_wrong_request_and_operation_result_cannot_consume_pending_request(connected,root,monkeypatch):
    app,worker,clock=connected;task=select_task(app)
    enter,release=threading.Event(),threading.Event();execute=TimerService.execute
    def delay(self,request):
        enter.set();assert release.wait(5);return execute(self,request)
    monkeypatch.setattr(TimerService,'execute',delay)
    assert app.start();request=app.pending;token=app._pending_token
    try:
        pump(root,enter.is_set)
        wrong=replace(request,operation='stop_timer')
        for context in (None,wrong,replace(request,dataset_id=uid())):
            app._handle(Message('mutate',token,Outcome('committed'),request=context))
            assert app.pending is request and app.executing
    finally:release.set()
    pump(root,lambda:app.pending is None and app.state['active'] is not None)
    assert app._mutation_outcome.status=='committed'
    assert not root.test_errors


@pytest.mark.parametrize('kind',['start','stop','switch'])
def test_real_tk_server_accepted_timer_then_close_drains_exact_mutation(connected,root,click,monkeypatch,kind):
    from datetime import timedelta
    app,worker,clock=connected;task=select_task(app)
    if kind!='start':
        assert app.start();pump(root,lambda:app.pending is None and app.state['active'] is not None)
        clock.value+=timedelta(minutes=1)
    if kind=='switch':
        other=create(app,'Switch to');app.tree.selection_set(app.task_row(other))
    enter,release=threading.Event(),threading.Event();execute=TimerService.execute
    def delayed(self,r):
        enter.set();assert release.wait(5);return execute(self,r)
    monkeypatch.setattr(TimerService,'execute',delayed)
    click(app.buttons[kind.title()]);request=app.pending
    try:
        pump(root,enter.is_set)
        root.tk.call(root.protocol('WM_DELETE_WINDOW'))
        assert app.closing and app.alive and app.executing and not app._submit('create_project',project_id=uid(),name='blocked')
        beat=[];root.after(10,lambda:beat.append(True));pump(root,lambda:beat)
    finally:release.set()
    exit_settled(app);worker.join(5);assert not worker.is_alive()
    reopened=SQLiteStore(worker.directory)
    try:
        s=TimerService(reopened);assert s.reconcile_request(request).status=='committed'
        rows=logical(reopened.path)
        assert len(rows['active_timer'])==(kind!='stop')
        if kind=='switch':
            active=dict(reopened.connection.execute('SELECT * FROM active_timer').fetchone())
            closed=reopened.connection.execute('SELECT stop_utc_us FROM work_revisions WHERE entry_id=?',(request.args()['expected_active_entry_id'],)).fetchone()[0]
            assert active['start_utc_us']==closed==request.action_utc_us
    finally:reopened.close()
    assert not root.test_errors


def test_mismatched_file_context_cannot_consume_publication(connected,root,tmp_path,monkeypatch):
    from test_chronicle_timesheet_ui import open_sheet,refresh
    from test_timesheet_save_ui import choose,settled
    app,worker,clock=connected;sheet=open_sheet(app);candidate=refresh(app,sheet)
    destination=tmp_path/'exact.txt';choose(monkeypatch,sheet,str(destination))
    entered,release=threading.Event(),threading.Event()
    original=TimerService.materialize_registered_timesheet_export
    def delayed(self,*args,**kwargs):
        entered.set();assert release.wait(8);return original(self,*args,**kwargs)
    monkeypatch.setattr(TimerService,'materialize_registered_timesheet_export',delayed)
    assert sheet.save()
    try:
        pump(root,entered.is_set);attempt=app._timesheet_attempt;token=attempt.file_token
        for export_id,path in ((uid(),str(destination)),(candidate.export_id,str(tmp_path/'wrong.txt'))):
            app._handle(Message('timesheet_publish',token,dict(export_id=export_id,destination=path,result=None)))
            assert app.executing and attempt.file_token==token and attempt.saved_path is None
    finally:release.set()
    settled(app)
    assert attempt.saved_path==str(destination) and destination.read_bytes()==candidate.report_utf8
    assert len(root.test_errors)==2


def test_connected_uncertainty_backup_shutdown_cold_restore_fresh_session(store,task,rich,tmp_path,root,monkeypatch):
    import tkinter as tk
    from chronicle.app import ChronicleApp
    from chronicle import backup_restore as br
    from test_app import Clock
    from test_backup_ui import open_backup,wait_backup
    from test_timesheet_save_ui import settled
    # Reuse the complete Stage 4A logical-state fixture, including revisions,
    # active correction, exports, source/manual/zero confirmations and dismissal.
    from test_manual_work import dated
    from test_polr_confirmation import source_args,submit,ack
    service=TimerService(store);project,new_active=uid(),uid()
    assert service.create_project(project,'Second project',request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.assign_task_to_project(rich['second'],project,expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.switch_timer(rich['active'],task,new_active,expected_active_version=2,expected_task_version=2,request_id=uid(),action_utc_us=NOW).status=='committed'
    checked=source_args(service,rich['candidate'])
    checked['selected_keys']=[dict(task_id=task,work_date='2026-10-20')]
    checked['acknowledgements']=[ack(r) for r in checked['reviewed_rows'] if r['task_id']==task and r['work_date']=='2026-10-20' and r['requires_stale_acknowledgement']]
    assert submit(service,checked).status=='committed'
    dated(service,task,duration='0:17',comment='Actual changed after confirmation')
    reconciliation=service.read_polr_reconciliation(cutoff_utc_us=NOW)
    assert reconciliation['coverage']['MISMATCH']>0
    directory=store.directory;before=logical(store.path);store.close()
    worker=DatabaseWorker(directory);app=ChronicleApp(root,worker,now_utc=Clock());worker.start()
    try:
        pump(root,lambda:app.ready and app.state.get('report') is not None)
        active=dict(app.state['active']);dialog=open_backup(app);backup=tmp_path/'connected-backup'
        dialog.destination.set(str(backup));assert dialog.create();assert wait_backup(app).verified
        assert logical(backup)==before and app.state['active']==active;assert dialog.close()
        execute=TimerService.execute;seen=[]
        def uncertain(self,request):
            if request.operation=='add_date_only_work' and not seen:
                seen.append(request);self.store.connection=FaultConnection(self.store.connection,after=True)
                probe=self.store._probe
                def offline():raise OSError('independent lookup temporarily unavailable')
                self.store._probe=offline
                try:return execute(self,request)
                finally:self.store._probe=probe
            return execute(self,request)
        monkeypatch.setattr(TimerService,'execute',uncertain)
        app.tree.selection_set(app.task_row(task));app.add_date_only_work();session=app._work_editor
        fill(session,('2026-10-19','0:07','uncertain then reconciled'));session.save.invoke()
        request=app.pending;pump(root,lambda:not app.executing and app.pending is request)
        assert app._mutation_outcome.status=='unverified' and session.request is request
        assert app.retry();settled(app)
        assert app._mutation_outcome.status=='committed' and app.pending is None
        assert app.state['active']==active and logical(backup)==before
        # Queue a final mutation immediately before orderly application shutdown.
        assert app._submit('create_project',project_id=uid(),name='accepted before exit')
        final_request=app.pending;app.request_close();exit_settled(app);worker.join(8);assert not worker.is_alive()
        original=logical(directory/'chronicle.sqlite3');backup_bytes=backup.read_bytes()
        reopened=SQLiteStore(directory)
        try:
            assert TimerService(reopened).reconcile_request(request).status=='committed'
            assert TimerService(reopened).read_current_state(cutoff_utc_us=NOW)['active']==active
            assert any(r[1]==final_request.request_id for r in original['committed_requests'])
        finally:reopened.close()
        assert br.validate_image(backup).dataset_id==app.dataset_id
        restored=br.restore_image(backup,tmp_path/'restored-session');assert restored.verified
        recovered=SQLiteStore(tmp_path/'restored-session')
        try:assert TimerService(recovered).read_polr_reconciliation(cutoff_utc_us=NOW)==reconciliation
        finally:recovered.close()
        assert logical(restored.destination)==before
        fresh_root=tk.Tk();fresh_errors=[];fresh_root.report_callback_exception=lambda *a:fresh_errors.append(a)
        next_worker=DatabaseWorker(tmp_path/'restored-session')
        fresh=ChronicleApp(fresh_root,next_worker,now_utc=Clock());next_worker.start()
        try:
            pump(fresh_root,lambda:fresh.ready and fresh.state.get('report') is not None)
            assert fresh is not app and next_worker is not worker and fresh.pending is None
            assert fresh.state['active']==active and fresh._timesheet_attempt is None
            assert fresh._submit('add_date_only_work',task_id=task,entry_id=uid(),work_date='2026-10-19',duration_text='0:01',comment='restored future work')
            settled(fresh);assert logical(restored.destination)!=before
            fresh.request_close();exit_settled(fresh)
        finally:
            if fresh.alive:fresh_root.destroy()
            next_worker.join(8);assert not next_worker.is_alive()
        assert not fresh_errors and logical(directory/'chronicle.sqlite3')==original and backup.read_bytes()==backup_bytes
        assert (tmp_path/'report.txt').read_bytes()==rich['candidate'].report_utf8
    finally:
        if app.alive:root.destroy()
        worker.join(8);assert not worker.is_alive()
