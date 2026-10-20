"""Actual application/worker/SQLite History behavior and separate XTest interaction."""

from copy import deepcopy
from datetime import timedelta
import tkinter as tk

import pytest

from chronicle.app import ChronicleApp
from chronicle.history_window import HistoryWindow, widget_live
from chronicle.records import Outcome, StaleState
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import from_us
from chronicle.worker import DatabaseWorker, Message
from conftest import NOW, uid
from test_app import root, connected, click, keyboard, pump, create, evidence
from test_manual_work import H, M


def selected_task(app):
    task = create(app)
    app.tree.selection_set(task)
    pump(app.root, lambda: not app.buttons['Work History'].instate(['disabled']))
    return task


def mutation(app, operation, **arguments):
    assert app._submit(operation, **arguments)
    pump(app.root, lambda: app.pending is None and app._read_inflight is None)


def seed(app, task):
    timed_id, dated_id = uid(), uid()
    mutation(app, 'add_timed_work', task_id=task, entry_id=timed_id, start_date='2026-10-18', start_time='23:00',
             end_date='2026-10-19', end_time='01:00', start_occurrence=None, end_occurrence=None, comment='complete')
    mutation(app, 'add_date_only_work', task_id=task, entry_id=dated_id, work_date='2026-10-19', duration_text='1:30', comment='dated')
    return timed_id, dated_id


def open_history(app):
    assert app.open_history()
    history = app.history
    pump(app.root, lambda: history.load_state.startswith('Loaded'))
    assert app.root.grab_current() is history.window
    return history


def select(history, entry_id, day=None):
    handle = next(h for h, r in history.mapping.items() if r['entry_id']==entry_id and (day is None or r['work_date']==day))
    history.tree.selection_set(handle)
    history._selected()
    return handle


def fill(history, **values):
    for key, value in values.items():
        field = history.edit_fields[key]
        field.delete(0, 'end'); field.insert(0, value)
    return {key: field.get() for key, field in history.edit_fields.items()}


def settled(app, history):
    pump(app.root, lambda: app.pending is None and app._read_inflight is None and history.snapshot_token is None and history.phase=='browsing')


def test_real_tk_history_constructed_access_defaults_single_owner_purity_and_session_direction(connected, root):
    app, worker, clock = connected
    assert app.history is None and not app._history_opening and app._history_newest_first
    assert app.buttons['Work History'].instate(['disabled'])
    task = selected_task(app); a, b = seed(app, task)
    before = evidence(worker)
    app.buttons['Work History'].invoke()
    history = app.history
    assert history.load_state=='Not loaded' and app.history is history
    pump(root, lambda: history.load_state=='Loaded with rows')
    assert history.task['task_id']==task and history.period.get()=='Current week'
    assert history.snapshot['week_start']==6 and history.newest_first
    count = clock.calls; token = app._token
    assert not app.open_history() and not app.add_timed_work() and not app.start()
    assert app.history is history and clock.calls==count and app._token==token
    assert history.sort_dates() and not history.newest_first and not app._history_newest_first
    assert clock.calls==count and app._token==token and evidence(worker)==before
    history.show_details(); select(history, a); history.show_details()
    pump(root, lambda: history.details_token is None)
    assert a in history.details_view.get('1.0','end')
    assert history.close(); assert app.history is None and root.grab_current() is None
    other = create(app,'Another task'); app.tree.selection_set(other)
    pump(root, lambda: app._selected()['task_id']==other)
    later = open_history(app)
    assert not later.newest_first and later.task['task_id']==other
    assert later.load_state=='Loaded and empty'
    app._history_disposed(history)
    assert app.history is later
    later.close()
    assert root.test_errors==[]


def test_real_tk_history_period_drafts_calendar_applied_refresh_and_rollover(connected, root):
    app, worker, clock = connected; task=selected_task(app); seed(app,task)
    history=open_history(app); before=evidence(worker)
    initial=deepcopy(history.snapshot)
    history.period.set('Custom'); history.period_changed()
    history.start.set(' 2026-10-18 '); history.end.set('2026-10-19')
    assert history.snapshot==initial
    assert history.apply(); pump(root,lambda: history.snapshot_token is None)
    assert history.applied==dict(period='custom',start_date='2026-10-18',end_date='2026-10-19')
    history.start.set('invalid draft'); history.end.set('2026-10-20')
    assert not history.apply() and history.start.get()=='invalid draft'
    count=clock.calls; token=app._token
    assert history.open_picker(history.start)
    history._choose_day(5)
    assert history.start.get()=='2026-10-05' and clock.calls==count and app._token==token
    saved=history.start.get(); history.open_picker(history.start); history._escape()
    assert history.picker is None and history.start.get()==saved and root.grab_current() is history.window
    history.start.set('unapplied'); history.refresh(); pump(root,lambda: history.snapshot_token is None)
    assert history.snapshot['start_date']=='2026-10-18' and history.start.get()=='unapplied'
    history.period.set('All'); history.period_changed(); pump(root,lambda: history.snapshot_token is None)
    assert history.snapshot['period']=='all' and history.start.get()=='unapplied'
    clock.value += timedelta(days=7)
    history.period.set('Current week'); history.period_changed(); pump(root,lambda: history.snapshot_token is None)
    assert history.snapshot['start_date']=='2026-10-25' and history.snapshot['end_date']=='2026-10-31'
    assert history.start.get()=='unapplied' and evidence(worker)==before


def test_real_tk_history_whole_entry_inline_edit_details_delete_and_unchanged_timer(connected, root, monkeypatch):
    app,worker,clock=connected; task=selected_task(app); a,b=seed(app,task)
    assert app.start(); pump(root,lambda: app.pending is None and app.state['active'] is not None)
    active=deepcopy(app.state['active']); history=open_history(app)
    history.period.set('Custom'); history.period_changed(); history.start.set('2026-10-19'); history.end.set('2026-10-19')
    history.apply(); pump(root,lambda: history.snapshot_token is None)
    history.start.set('unapplied draft'); history.sort_dates()
    select(history,a); assert history.edit()
    assert history.edit_fields['start_date'].get()=='2026-10-18'
    assert history.edit_fields['end_date'].get()=='2026-10-19'
    before=evidence(worker)
    assert history.save(); settled(app,history)
    assert history.outcome.status=='unchanged' and evidence(worker)==before
    select(history,a); history.edit(); fill(history,start_time='22:00',comment='changed')
    assert history.save(); settled(app,history)
    assert history.outcome.status=='committed' and history.snapshot['start_date']=='2026-10-19'
    assert history.start.get()=='unapplied draft' and not history.newest_first
    assert app.state['active']==active
    assert app.state['report']['tasks'][task]['daily_us']['2026-10-18']==2*H
    select(history,a); history.show_details(); pump(root,lambda: history.details_token is None)
    text=history.details_view.get('1.0','end')
    assert 'Creation — revision 1' in text and 'Correction — revision 2' in text
    calls=[]
    def confirm(*args,**kwargs):
        calls.append((args,kwargs))
        assert kwargs['parent'] is history.window and kwargs['default']=='no'
        assert not history.close() and not history.delete() and not app.open_history()
        return True
    monkeypatch.setattr('chronicle.history_window.messagebox.askyesno',confirm)
    assert history.delete(); settled(app,history)
    assert 'other dates' in calls[0][0][1] and '2026-10-18' in calls[0][0][1]
    assert not any(r['entry_id']==a for r in history.rows)
    history.show_details()
    label=next(k for k,v in history.deleted_choices.items() if v==a)
    history.deleted_control.set(label); history._deleted_selected()
    pump(root,lambda: history.details_token is None)
    assert 'Deletion — revision 3' in history.details_view.get('1.0','end')
    assert app.state['active']==active
    assert app.state['report']['tasks'][task]['week_us']==90*M
    assert len(evidence(worker)['work_revisions'])==4
    history.close(); assert app.history is None
    assert root.test_errors==[]


@pytest.mark.parametrize('first_failure', [False, True])
def test_real_tk_history_read_failure_is_not_empty_or_unverified_and_refresh_recovers(connected, root, monkeypatch, first_failure):
    app,worker,clock=connected; task=selected_task(app); seed(app,task)
    original=TimerService.read_history_snapshot
    error=OSError('history storage unavailable')
    if first_failure:
        monkeypatch.setattr(TimerService,'read_history_snapshot',lambda *a,**kw: (_ for _ in ()).throw(error))
        assert app.open_history(); history=app.history
        pump(root,lambda:history.load_state=='Load failed')
        assert history.snapshot is None and not history.trusted and not history.current
    else:
        history=open_history(app)
        old=deepcopy(history.snapshot); applied=dict(history.applied)
        monkeypatch.setattr(TimerService,'read_history_snapshot',lambda *a,**kw: (_ for _ in ()).throw(error))
        history.period.set('All'); history.period_changed()
        pump(root,lambda:history.load_state=='Load failed')
        assert history.snapshot==old and history.applied==applied and history.trusted and not history.current
        assert 'previous as-of' in history.status.cget('text')
    assert app.pending is None and root.grab_current() is history.window
    assert any(args[1] is error for args in root.test_errors)
    monkeypatch.setattr(TimerService,'read_history_snapshot',original)
    history.refresh(); pump(root,lambda:history.load_state=='Loaded with rows')
    assert history.snapshot['period']=='current_week' and history.current


@pytest.mark.parametrize('fault',['prepare','insert','context'])
def test_real_tk_history_render_faults_preserve_context_or_invalidate_partial_rows(connected,root,monkeypatch,fault):
    import chronicle.history_window as module
    app,worker,clock=connected; task=selected_task(app); seed(app,task)
    history=open_history(app); old=deepcopy(history.snapshot); before=evidence(worker)
    error=ValueError(f'{fault} presentation fault')
    with monkeypatch.context() as m:
        if fault=='prepare':
            m.setattr(module,'prepare_rows',lambda *a: (_ for _ in ()).throw(error))
        elif fault=='insert':
            real=history.tree.insert; count=[]
            def partial(*args,**kwargs):
                count.append(True)
                if len(count)==2: raise error
                return real(*args,**kwargs)
            m.setattr(history.tree,'insert',partial)
        else:
            m.setattr(history.context,'configure',lambda **kw: (_ for _ in ()).throw(error))
        history.period.set('All'); history.period_changed()
        pump(root,lambda:history.load_state=='Load failed')
    assert history.snapshot==old and history.applied['period']=='current_week' and not history.current
    assert history.trusted==(fault=='prepare')
    if fault!='prepare':
        assert history.mapping=={} and history.selected_row() is None and not history.tree.winfo_manager()
    assert not history.edit() and evidence(worker)==before
    assert any(args[1] is error for args in root.test_errors)
    history.refresh(); pump(root,lambda:history.load_state=='Loaded with rows')
    assert history.current and history.trusted and history.tree.winfo_manager()


@pytest.mark.parametrize('fault',['prepare','render','notification'])
def test_real_tk_history_sort_failure_boundary_and_owner_notification(connected,root,monkeypatch,fault):
    import chronicle.history_window as module
    app,worker,clock=connected; task=selected_task(app); seed(app,task)
    history=open_history(app); before=evidence(worker); snapshot=deepcopy(history.snapshot)
    root.after_cancel(app._tick_id); app._tick_id=None
    history.start.set('unapplied draft')
    error=ValueError('sort fault'); count=clock.calls; token=app._token
    with monkeypatch.context() as m:
        if fault=='prepare': m.setattr(module,'prepare_rows',lambda *a: (_ for _ in ()).throw(error))
        elif fault=='render': m.setattr(history.tree,'insert',lambda *a,**kw: (_ for _ in ()).throw(error))
        else: m.setattr(app,'_remember_history_direction',lambda value: (_ for _ in ()).throw(error))
        assert history.sort_dates()==(fault=='notification')
    assert history.newest_first==(fault!='notification') and app._history_newest_first
    assert history.snapshot==snapshot and history.start.get()=='unapplied draft'
    assert clock.calls==count and app._token==token and evidence(worker)==before
    if fault=='notification': assert 'remember session direction' in history.status.cget('text') and history.current
    if fault=='render': assert history.mapping=={} and not history.trusted
    assert any(args[1] is error for args in root.test_errors)


@pytest.mark.parametrize('start,end',[('2026-02-30','2026-03-01'),('2026-10-20','2026-10-19'),('2026-10-19','9999-12-31'),('2026-1-01','2026-10-19')])
def test_real_tk_history_invalid_custom_is_apply_only_and_retains_exact_drafts(connected,root,start,end):
    app,worker,clock=connected; selected_task(app); history=open_history(app)
    root.after_cancel(app._tick_id); app._tick_id=None
    snapshot=deepcopy(history.snapshot); before=evidence(worker); count=clock.calls; token=app._token
    history.period.set('Custom'); history.period_changed(); history.start.set(start); history.end.set(end)
    history.date_controls[0].focus_set()
    assert not history.apply()
    assert history.start.get()==start and history.end.get()==end and history.snapshot==snapshot
    assert clock.calls==count and app._token==token and evidence(worker)==before


@pytest.mark.parametrize('weekday,first',[(0,'2026-10-19'),(1,'2026-10-13'),(2,'2026-10-14'),(3,'2026-10-15'),(4,'2026-10-16'),(5,'2026-10-17'),(6,'2026-10-18')])
def test_real_tk_history_snapshot_uses_committed_weekday(connected,root,weekday,first):
    app,worker,clock=connected; selected_task(app)
    mutation(app,'set_week_start',week_start=weekday,expected_week_start=6)
    history=open_history(app)
    assert history.snapshot['week_start']==weekday and history.snapshot['start_date']==first


def test_real_tk_history_selection_running_invalid_handles_and_details_delivery_identity(connected,root):
    app,worker,clock=connected; task=selected_task(app); a,b=seed(app,task)
    assert app.start(); pump(root,lambda:app.pending is None and app.state['active'] is not None)
    history=open_history(app); before=evidence(worker)
    assert not history.edit() and not history.delete()
    active=app.state['active']['entry_id']; select(history,active)
    assert not history.edit() and not history.delete()
    history.show_details(); old_token=history.details_token
    select(history,b)
    history.receive_details(old_token,{'bad':'stale result'})
    assert history.phase=='browsing' and history.reviewed is None
    handle=select(history,a,'2026-10-18')
    assert len(history.tree.selection())==1
    related=[h for h in history.mapping if 'related' in history.tree.item(h,'tags')]
    assert len(related)==1 and history.mapping[related[0]]['entry_id']==a
    returned=history.selected_row(); returned['entry_id']=uid()
    assert history.mapping[handle]['entry_id']==a
    history.mapping.pop(handle)
    assert not history.edit() and not history.delete()
    assert evidence(worker)==before


def precise_closed(app,clock,task):
    clock.value=from_us(NOW-H+123456); assert app.start()
    pump(app.root,lambda:app.pending is None and app.state['active'] is not None)
    entry=app.state['active']['entry_id']
    clock.value=from_us(NOW-M+654321); assert app.stop()
    pump(app.root,lambda:app.pending is None and app.state['active'] is None)
    clock.value=from_us(NOW)
    return entry


@pytest.mark.parametrize('change',['start','end','both','reverted','comment'])
def test_real_tk_history_timed_precision_full_entry_and_noop_drafts(connected,root,change):
    app,worker,clock=connected; task=selected_task(app); e=precise_closed(app,clock,task)
    history=open_history(app); select(history,e); history.edit()
    before=evidence(worker); original=before['work_revisions'][0]
    if change in ('start','both'): fill(history,start_time='08:30')
    if change in ('end','both'): fill(history,end_time='09:58')
    if change=='reverted': fill(history,start_time='08:30'); fill(history,start_time='09:00')
    fill(history,comment='comment alone does not change work')
    assert history.save(); settled(app,history)
    after=evidence(worker)
    if change in ('reverted','comment'):
        assert after==before and history.outcome.status=='unchanged'
    else:
        revised=after['work_revisions'][-1]
        assert revised[0]==e and revised[1]==2 and after['work_revisions'][0]==original
        if change=='start': assert revised[4]==original[4]
        if change=='end': assert revised[3]==original[3]
    assert root.grab_current() is history.window


@pytest.mark.parametrize('change',['date','duration','noop','comment','cancel','invalid'])
def test_real_tk_history_date_only_whole_amount_validation_noop_cancel(connected,root,change):
    app,worker,clock=connected; task=selected_task(app); a,b=seed(app,task)
    history=open_history(app); select(history,b); history.edit(); before=evidence(worker)
    if change=='date': fill(history,work_date='2026-10-20')
    if change=='duration': fill(history,duration_text='125:45')
    if change=='comment': fill(history,comment='only comment')
    if change=='cancel': fill(history,duration_text='4:00'); assert history.cancel_edit()
    else:
        if change=='invalid': draft=fill(history,duration_text='0:00')
        assert history.save()
        if change=='invalid':
            pump(root,lambda:history.phase=='editing' and app.pending is None)
            assert {key:w.get() for key,w in history.edit_fields.items()}==draft
            assert history.cancel_edit()
        else: settled(app,history)
    after=evidence(worker)
    if change in ('noop','comment','cancel','invalid'): assert after==before
    else:
        revised=next(row for row in after['work_revisions'] if row[0]==b and row[1]==2)
        assert revised[3] is revised[4] is None
        assert revised[5]==('2026-10-20' if change=='date' else '2026-10-19')
        assert revised[6]==(90*M if change=='date' else (125*60+45)*M)


@pytest.mark.parametrize('fault',['stale','rollback','unavailable'])
def test_real_tk_history_settled_failures_preserve_review_and_exact_draft(connected,root,monkeypatch,fault):
    from test_services import FaultConnection
    app,worker,clock=connected; task=selected_task(app); a,b=seed(app,task)
    history=open_history(app); select(history,b); history.edit()
    draft=fill(history,duration_text='2:00',comment='reviewed draft')
    before=evidence(worker); original=TimerService.execute; calls=[]
    def failed(service,request):
        calls.append(request)
        if len(calls)==1:
            if fault=='stale':
                service.edit_date_only_work(task,b,'2026-10-20','1:00',expected_revision=1,request_id=uid(),action_utc_us=NOW)
            elif fault=='rollback': service.store.connection=FaultConnection(service.store.connection,after=False)
            else: return Outcome('unavailable',error=OSError('storage did not begin'))
        return original(service,request)
    # Stale injection's own real mutation must use the original dispatcher.
    def inject(service,request):
        if fault=='stale' and not calls:
            with monkeypatch.context() as m:
                m.setattr(TimerService,'execute',original)
                service.edit_date_only_work(task,b,'2026-10-20','1:00',expected_revision=1,request_id=uid(),action_utc_us=NOW)
            calls.append(request)
            return original(service,request)
        return failed(service,request)
    monkeypatch.setattr(TimerService,'execute',inject)
    history.save(); pump(root,lambda:app.pending is None and history.phase in ('stale','editing'))
    assert {key:w.get() for key,w in history.edit_fields.items()}==draft
    assert history.reviewed['revision']==1 and history.reviewed['entry_id']==b
    if fault=='stale':
        assert history.phase=='stale' and history.save_button.instate(['disabled']) and not history.save()
        assert history.cancel_edit(); history.refresh(); pump(root,lambda:history.snapshot_token is None)
        assert next(r for r in history.rows if r['entry_id']==b)['revision']==2
    else:
        assert history.phase=='editing' and evidence(worker)==before
        history.save(); settled(app,history)
        assert calls[0].request_id!=calls[-1].request_id


@pytest.mark.parametrize('committed',[False,True])
def test_real_tk_history_unverified_frozen_request_reconcile_and_no_duplicate_completion(connected,root,monkeypatch,committed):
    from test_services import FaultConnection
    app,worker,clock=connected; task=selected_task(app); a,b=seed(app,task)
    history=open_history(app); select(history,b); history.edit()
    draft=fill(history,duration_text='2:00'); original=TimerService.execute; attempts=[]
    def uncertain(service,request):
        attempts.append(request)
        if len(attempts)==1:
            if committed:
                service.store.connection=FaultConnection(service.store.connection,after=True)
                with monkeypatch.context() as m:
                    m.setattr(service.store,'_probe',lambda: (_ for _ in ()).throw(OSError('committed lookup unavailable')))
                    result=original(service,request)
                assert result.status=='unverified'
                return result
            return Outcome('unverified',error=OSError('accepted request response unavailable'))
        return original(service,request)
    monkeypatch.setattr(TimerService,'execute',uncertain)
    assert history.save(); frozen=app.pending; token=app._pending_token
    pump(root,lambda:history.phase=='unverified')
    assert history.request is frozen and app.pending is frozen
    assert {key:w.get() for key,w in history.edit_fields.items()}==draft
    assert all(w.instate(['disabled']) for w in history.edit_fields.values())
    assert not history.close() and not history.save() and not app.open_history()
    assert history.retry(); retry_token=app._pending_token
    app._handle(Message('mutate',token,Outcome('committed')))
    assert app.pending is frozen and history.phase=='executing'
    settled(app,history)
    assert history.outcome.status=='committed'
    rows=evidence(worker)
    assert len([r for r in rows['work_revisions'] if r[0]==b])==2
    assert sum(r[1]==frozen.request_id for r in rows['committed_requests'])==1
    assert all(r is frozen for r in attempts)
    app._handle(Message('reconcile',retry_token,Outcome('committed')))
    assert evidence(worker)==rows


@pytest.mark.parametrize('where',['history','main','inline'])
def test_real_tk_history_commit_survives_refresh_or_inline_presentation_failure(connected,root,monkeypatch,where):
    app,worker,clock=connected; task=selected_task(app); a,b=seed(app,task)
    history=open_history(app); select(history,b); history.edit(); fill(history,duration_text='2:00')
    original_history=TimerService.read_history_snapshot
    if where=='history':
        monkeypatch.setattr(TimerService,'read_history_snapshot',lambda *a,**kw: (_ for _ in ()).throw(OSError('post-commit history read failure')))
    elif where=='main':
        monkeypatch.setattr('chronicle.app.format_duration',lambda value: (_ for _ in ()).throw(ValueError('post-commit main numeric fault')))
    history.save()
    if where=='inline':
        history.editor_panel.destroy()  # The already accepted request outlives its fields.
    pump(root,lambda:app.pending is None and history.outcome is not None and history.outcome.status=='committed' and history.snapshot_token is None)
    assert len([r for r in evidence(worker)['work_revisions'] if r[0]==b])==2
    assert history.request is None and history.phase=='browsing'
    if where=='history':
        assert history.load_state=='Load failed' and not history.current
        assert 'Saved work remains committed' in history.status.cget('text')
        monkeypatch.setattr(TimerService,'read_history_snapshot',original_history)
        history.refresh(); pump(root,lambda:history.current)
        assert next(r for r in history.rows if r['entry_id']==b)['duration_us']==2*H
    assert root.test_errors


def test_real_tk_history_executing_view_destruction_keeps_owner_request_and_discards_late_reads(connected,root,monkeypatch):
    from threading import Event
    app,worker,clock=connected; task=selected_task(app); a,b=seed(app,task)
    history=open_history(app); select(history,b); history.edit(); fill(history,duration_text='2:00')
    entered,release=Event(),Event(); original=TimerService.execute
    def held(service,request):
        if request.operation=='edit_date_only_work':
            entered.set(); assert release.wait(5)
        return original(service,request)
    monkeypatch.setattr(TimerService,'execute',held)
    history.save(); frozen=app.pending
    pump(root,lambda:entered.is_set())
    assert not history.close() and not app.open_history()
    app.request_close(); assert not app.closing
    stale_token=history.snapshot_token
    history.window.destroy()
    assert app.history is None and app.pending is frozen
    release.set(); pump(root,lambda:app.pending is None and app._read_inflight is None)
    later=open_history(app)
    new=deepcopy(later.snapshot)
    app._handle(Message('history_snapshot',stale_token,{'not':'a current session'}))
    app._history_disposed(history)
    assert app.history is later and later.snapshot==new
    assert len([r for r in evidence(worker)['work_revisions'] if r[0]==b])==2


@pytest.mark.parametrize('confirm',[False,True])
def test_real_tk_history_owned_unverified_exit_default_cancel_and_orderly_shutdown(connected,root,monkeypatch,confirm):
    app,worker,clock=connected; task=selected_task(app); a,b=seed(app,task)
    history=open_history(app); select(history,b); history.edit(); fill(history,duration_text='2:00')
    original=TimerService.execute
    def lost(service,request):
        result=original(service,request)
        return Outcome('unverified',error=OSError('lost committed response')) if request.operation=='edit_date_only_work' else result
    monkeypatch.setattr(TimerService,'execute',lost)
    history.save(); frozen=app.pending; pump(root,lambda:history.phase=='unverified')
    def decide(*args,**kwargs):
        assert kwargs['parent'] is history.window and kwargs['default']=='no'
        assert not history.close() and not app.open_history() and not app.retry()
        app.request_close()
        return confirm
    monkeypatch.setattr('chronicle.app.messagebox.askyesno',decide)
    app.request_close()
    if confirm:
        root.after(6000,root.quit); root.mainloop()
        assert not app.alive
        worker.join(timeout=5); assert not worker.is_alive()
        store=SQLiteStore(worker.directory)
        try: assert len(TimerService(store).read_work_entry_revisions(b)['revisions'])==2
        finally: store.close()
    else:
        assert app.pending is frozen and app.history is history and not app.closing
        assert root.grab_current() is history.window
        assert history.retry(); settled(app,history)


@pytest.mark.parametrize('start,end,needle',[
    ('02:30','04:00','does not exist'),
    ('08:00','08:00','strictly after'),
    ('08:00','11:00','accepted observation'),
    ('08:00:01','09:00','minute-only')])
def test_real_tk_history_timed_invalid_local_or_utc_drafts_remain_editable(connected,root,start,end,needle):
    app,worker,clock=connected;task=selected_task(app);a,b=seed(app,task)
    history=open_history(app);select(history,a);history.edit()
    if start=='02:30':
        draft=fill(history,start_date='2026-03-08',end_date='2026-03-08',start_time=start,end_time=end)
    else:
        draft=fill(history,start_date='2026-10-19',end_date='2026-10-19',start_time=start,end_time=end)
    before=evidence(worker);history.save();pump(root,lambda:app.pending is None and history.phase=='editing')
    assert {key:w.get() for key,w in history.edit_fields.items()}==draft
    assert needle in history.status.cget('text') and evidence(worker)==before


def test_real_tk_history_stored_ambiguous_occurrences_initialize_but_changed_draft_requires_choice(connected,root):
    app,worker,clock=connected;task=selected_task(app)
    clock.value=from_us(NOW)+timedelta(days=14)
    e=uid()
    mutation(app,'add_timed_work',task_id=task,entry_id=e,start_date='2026-11-01',start_time='01:45',
             end_date='2026-11-01',end_time='01:15',start_occurrence='first',end_occurrence='second',comment='repeat')
    history=open_history(app);select(history,e);history.edit();before=evidence(worker)
    assert history.occurrence_controls['start'].current()==0 and history.occurrence_controls['end'].current()==1
    history.save();settled(app,history);assert evidence(worker)==before
    select(history,e);history.edit();fill(history,start_time='01:30')
    assert history.occurrence_controls['start'].get()=='' and history.occurrence_controls['end'].current()==1
    assert not history.save() and app.pending is None
    history.occurrence_controls['start'].current(0)
    history.save();settled(app,history)
    assert next(r for r in history.rows if r['entry_id']==e)['duration_us']==45*M


def test_real_tk_history_calendar_boundaries_and_no_extra_observation(connected,root):
    app,worker,clock=connected;selected_task(app);history=open_history(app)
    root.after_cancel(app._tick_id);app._tick_id=None
    history.period.set('Custom');history.period_changed();before=evidence(worker);count=clock.calls;token=app._token
    history.start.set('0001-01-01');history.open_picker(history.start)
    assert history.previous_month.instate(['disabled'])
    history._move_month(-1);assert history._picker_month.isoformat()=='0001-01-01'
    history.close_picker();history.end.set('9999-12-31');history.open_picker(history.end)
    assert history.next_month.instate(['disabled'])
    history._move_month(1);assert history._picker_month.isoformat()=='9999-12-01'
    history.close_picker()
    assert clock.calls==count and app._token==token and evidence(worker)==before


def test_real_tk_history_midnight_exclusive_delete_warning_cancel_and_task_binding(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);second=create(app,'Other')
    app.tree.selection_set(task)
    e=uid();mutation(app,'add_timed_work',task_id=task,entry_id=e,start_date='2026-10-18',start_time='23:00',
                    end_date='2026-10-19',end_time='00:00',start_occurrence=None,end_occurrence=None,comment='midnight')
    history=open_history(app);app.tree.selection_set(second)
    select(history,e);before=evidence(worker);calls=[]
    def decline(*args,**kwargs):
        calls.append(args[1]);assert kwargs['default']=='no' and kwargs['parent'] is history.window
        return False
    monkeypatch.setattr('chronicle.history_window.messagebox.askyesno',decline)
    assert not history.delete() and 'other dates' not in calls[0]
    assert task in calls[0] and e in calls[0] and evidence(worker)==before
    assert history.task['task_id']==task


def test_real_tk_history_read_details_bad_identity_and_selection_change_reject_stale_result(connected,root):
    app,worker,clock=connected;task=selected_task(app);a,b=seed(app,task)
    history=open_history(app);select(history,a);history.show_details()
    token=history.details_token
    result={'entry':dict(entry_id=b,task_id=task),'revisions':[],'active_start_corrections':[]}
    history.receive_details(token,result)
    assert 'identity mismatch' in history.status.cget('text')
    history.show_details();token=history.details_token
    select(history,b)
    text=history.details_view.get('1.0','end')
    history.receive_details(token,result)
    assert history.details_view.get('1.0','end')==text


def test_real_tk_history_pending_correlation_survives_submission_presentation_failure(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);a,b=seed(app,task)
    history=open_history(app);select(history,b);history.edit();fill(history,duration_text='2:00')
    original=app.status.configure;error=RuntimeError('accepted request presentation failed')
    def failed(**kwargs):
        if kwargs.get('text')=='Saving…': raise error
        return original(**kwargs)
    with monkeypatch.context() as m:
        m.setattr(app.status,'configure',failed)
        with pytest.raises(RuntimeError) as raised:history.save()
        assert raised.value is error and app.pending is history.request and history.phase=='executing'
    settled(app,history)
    assert history.outcome.status=='committed' and len([r for r in evidence(worker)['work_revisions'] if r[0]==b])==2


def test_real_tk_history_widgets_remain_on_ui_thread_and_inline_edit_constructs_no_toplevel(connected,root,monkeypatch):
    import threading
    import ast
    from pathlib import Path
    app,worker,clock=connected;task=selected_task(app);a,b=seed(app,task)
    identity=threading.get_ident();calls=[];original=tk.Misc._configure
    def checked(self,*args,**kwargs):
        assert threading.get_ident()==identity
        calls.append(identity);return original(self,*args,**kwargs)
    monkeypatch.setattr(tk.Misc,'_configure',checked)
    history=open_history(app)
    monkeypatch.setattr(tk,'Toplevel',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('subordinate correction window')))
    select(history,b);history.edit();fill(history,duration_text='2:00');history.save();settled(app,history)
    assert calls and history.outcome.status=='committed'
    source=ast.parse(Path('src/chronicle/history_window.py').read_text())
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in
                   ('mainloop','wait_window','wait_visibility') for n in ast.walk(source))
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='update'
                   and isinstance(n.func.value,ast.Attribute) and n.func.value.attr in ('root','window')
                   for n in ast.walk(source))


def test_real_tk_history_retry_presentation_failure_cannot_strand_undispatched_io(connected,root,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);a,b=seed(app,task)
    history=open_history(app);select(history,b);history.edit();fill(history,duration_text='2:00')
    original=TimerService.execute;attempts=[]
    def uncertain(service,request):
        attempts.append(request)
        return Outcome('unverified',error=OSError('absent response')) if len(attempts)==1 else original(service,request)
    monkeypatch.setattr(TimerService,'execute',uncertain)
    history.save();pump(root,lambda:history.phase=='unverified');frozen=app.pending
    configure=history.status.configure;error=RuntimeError('retry presentation failed')
    def fail(**kwargs):
        if kwargs.get('text','').startswith('Reconciling'): raise error
        return configure(**kwargs)
    with monkeypatch.context() as m:
        m.setattr(history.status,'configure',fail)
        with pytest.raises(RuntimeError) as raised:history.retry()
        assert raised.value is error and app.pending is frozen and app.executing
    settled(app,history)
    assert attempts==[frozen,frozen] and history.outcome.status=='committed'


def test_real_tk_history_redated_entry_leaves_applied_custom_without_following_draft(connected,root):
    app,worker,clock=connected;task=selected_task(app);a,b=seed(app,task)
    history=open_history(app)
    history.period.set('Custom');history.period_changed()
    history.start.set('2026-10-19');history.end.set('2026-10-19');history.apply()
    pump(root,lambda:history.snapshot_token is None)
    history.start.set('unapplied draft');applied=dict(history.applied)
    select(history,b);history.edit();fill(history,work_date='2026-10-20')
    history.save();settled(app,history)
    assert history.outcome.status=='committed' and history.applied==applied
    assert history.start.get()=='unapplied draft' and not any(r['entry_id']==b for r in history.rows)
    assert app.state['report']['tasks'][task]['daily_us']['2026-10-20']==90*M
