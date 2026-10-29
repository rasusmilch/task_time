"""Connected Tk/worker/manual entry; XTest cases are actual operator evidence."""
from datetime import timedelta
from threading import Event

import pytest

from chronicle.app import ChronicleApp
from chronicle.records import Outcome
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import from_us
from chronicle.worker import DatabaseWorker, Message
from conftest import NOW, uid
from test_manual_work import H, M
from test_app import root, connected, click, keyboard, pump, create, evidence, Clock


def select_task(app):
    task=create(app)
    app.tree.selection_set(app.task_row(task))
    pump(app.root,lambda: not app.buttons["Add timed work"].instate(["disabled"]))
    return task


def fill(session, values):
    for entry,value in zip(session.fields,values):
        entry.delete(0,'end');entry.insert(0,value)
    return tuple(e.get() for e in session.fields)


def settled(app,root):
    pump(root,lambda: app.pending is None and app.editor is None and app._read_inflight is None)


def test_real_tk_manual_controls_mixed_totals_modal_blocking_and_week_selection(connected,root,click,keyboard):
    app,worker,clock=connected
    task=select_task(app)
    click(app.buttons['Mini mode']);pump(root,lambda:app.mini is not None and app._read_inflight is None)
    before=evidence(worker)
    click(app.buttons['Add date-only work'])
    session=app._work_editor
    pump(root,lambda:root.grab_current() is session.window)
    assert [e.get() for e in session.fields]==['2026-10-19','','']
    assert session.task_id==task and app.state['active'] is None
    _,type_text=keyboard
    type_text(session.fields[1],'1:30')
    # These are server-delivered clicks; modal ownership prevents ancestor actions.
    click(app.buttons['Start']);click(app.mini.toggle)
    assert evidence(worker)==before and app.state['active'] is None
    click(session.save);settled(app,root)
    assert app.tree.item(app.task_row(task),'values')[1:]==('01:30','01:30')
    assert app.mini.today.cget('text')=='Today: 01:30'
    click(app.buttons['Add timed work']);session=app._work_editor
    pump(root,lambda:root.grab_current() is session.window)
    assert [e.get() for e in session.fields]==['2026-10-19','','2026-10-19','','']
    type_text(session.fields[1],'08:00');type_text(session.fields[3],'09:00')
    click(session.save);settled(app,root)
    assert app.tree.item(app.task_row(task),'values')[1:]==('02:30','02:30')
    assert app.mini.today.cget('text')=='Today: 02:30'
    click(app.buttons['Add date-only work']);session=app._work_editor
    pump(root,lambda:root.grab_current() is session.window)
    type_text(session.fields[0],'2026-10-24');type_text(session.fields[1],'14:00')
    click(session.save);settled(app,root)
    assert app.state['report']['tasks'][task]['daily_us']['2026-10-24']==14*H
    assert app.tree.item(app.task_row(task),'values')[1:]==('02:30','02:30')
    app.period.set('This Week');app._presentation_changed()
    assert app.tree.item(app.task_row(task),'values')[1:]==('16:30','16:30')
    app.period.set('Today');app._presentation_changed()
    # Real combobox keyboard selection, not a direct settings callback.
    click(app.week_selector,(app.week_selector.winfo_width()-8,app.week_selector.winfo_height()//2))
    popdown=root.tk.call('ttk::combobox::PopdownWindow',str(app.week_selector))
    pump(root,lambda:bool(root.tk.call('winfo','ismapped',popdown)))
    keyboard[0]('Home',control=True);keyboard[0]('Return')
    pump(root,lambda:app.state.get('week_start')==0 and app.pending is None and app._read_inflight is None)
    assert app.week_selector.get()=='Monday' and app.state['report']['week_start']=='2026-10-19'
    assert app.state['report']['application']['today_us']==150*M
    assert len(evidence(worker)['work_revisions'])==3
    assert root.test_errors==[]


def test_real_tk_cancel_fixed_identity_clock_and_reader_purity(connected,root,click):
    app,worker,clock=connected
    task=select_task(app)
    second=create(app,'Other')
    app.tree.selection_set(app.task_row(task))
    root.after_cancel(app._tick_id);app._tick_id=None
    before=evidence(worker)
    click(app.buttons['Add date-only work']);session=app._work_editor
    pump(root,lambda:root.grab_current() is session.window)
    app.tree.selection_set(app.task_row(second))  # Programmatic selection cannot retarget the owned form.
    values=fill(session,['2026-10-19','1:00','draft'])
    assert session.task_id==task and evidence(worker)==before
    click(session.cancel)
    pump(root,lambda:app.editor is None)
    assert evidence(worker)==before
    reads=[];original=TimerService.read_current_state
    # One explicit refresh observation supplies main and mini; no independent numeric clock.
    def observe(s,**kwargs):
        reads.append(kwargs['cutoff_utc_us']);return original(s,**kwargs)
    # Patch explicitly, leaving all worker reads real.
    from unittest.mock import patch
    with patch.object(TimerService,'read_current_state',observe):
        count=clock.calls;app.open_mini();pump(root,lambda:app._read_inflight is None)
        assert clock.calls==count+1 and reads==[NOW]
        assert app.state['report']['cutoff_utc_us']==reads[0]
    assert evidence(worker)==before


@pytest.mark.parametrize('kind,values,needle',[
    ('Add date-only work',['2026-10-19','0:00','kept'],'Duration'),
    ('Add timed work',['2026-10-19','08:00','2026-10-19','11:00','kept'],'accepted observation')])
def test_real_tk_invalid_manual_draft_is_retained_then_successful(connected,root,kind,values,needle):
    app,worker,clock=connected;task=select_task(app)
    app.buttons[kind].invoke();session=app._work_editor
    saved=fill(session,values);before=evidence(worker)
    session.save.invoke();pump(root,lambda:session.outcome is not None)
    assert session.phase=='editing' and needle in session.status.cget('text')
    assert tuple(e.get() for e in session.fields)==saved and evidence(worker)==before
    assert app.editor is session.window and session.task_id==task
    if kind=='Add date-only work': fill(session,['2026-10-19','1:00','kept'])
    else: fill(session,['2026-10-19','08:00','2026-10-19','09:00','kept'])
    session.save.invoke();settled(app,root)
    assert len(evidence(worker)['work_revisions'])==1
    assert app.state['report']['application']['today_us']==H


@pytest.mark.parametrize('committed',[False,True])
def test_real_tk_manual_uncertainty_keeps_exact_request_and_worker_retry(connected,root,monkeypatch,committed):
    app,worker,clock=connected;task=select_task(app)
    original=TimerService.execute;attempts=[]
    def uncertain(s,r):
        attempts.append(r)
        if len(attempts)==1:
            if committed: assert original(s,r).status=='committed'
            return Outcome('unverified',error=OSError('acknowledgement unavailable'))
        return original(s,r)
    monkeypatch.setattr(TimerService,'execute',uncertain)
    app.add_date_only_work();session=app._work_editor
    values=fill(session,['2026-10-19','1:00','frozen'])
    session.save.invoke();frozen=app.pending
    session.save.invoke()  # Disabled/direct duplicate cannot allocate another request.
    pump(root,lambda:session.phase=='unverified')
    assert app.pending is frozen and session.request is frozen
    assert tuple(e.get() for e in session.fields)==values
    assert not app._close_editor(session.window)
    assert not app.add_timed_work()
    session.retry.invoke();settled(app,root)
    assert len(evidence(worker)['work_revisions'])==1
    assert app.state['report']['application']['today_us']==H
    assert session.outcome.status=='committed'
    assert len({r.request_id for r in attempts})==1
    assert all(r is frozen for r in attempts)


def test_real_tk_destroyed_manual_form_does_not_lose_pending_evidence(connected,root,monkeypatch):
    app,worker,clock=connected;select_task(app)
    original=TimerService.execute;entered,release=Event(),Event()
    def held(s,r):
        if r.operation=='add_date_only_work':
            entered.set();assert release.wait(5)
        return original(s,r)
    monkeypatch.setattr(TimerService,'execute',held)
    app.add_date_only_work();session=app._work_editor
    fill(session,['2026-10-19','1:00','kept']);session.save.invoke();frozen=app.pending
    pump(root,lambda:entered.is_set())
    session.window.destroy()
    assert app.editor is None and app.pending is frozen
    release.set();pump(root,lambda:app.pending is None and app._read_inflight is None)
    assert len(evidence(worker)['work_entries'])==1 and app.state['report']['application']['today_us']==H


def test_real_tk_running_timer_week_change_midnight_and_restart(connected,root):
    app,worker,clock=connected;task=select_task(app)
    assert app.start();pump(root,lambda:app.pending is None and app.state['active'] is not None)
    active=dict(app.state['active']);clock.value+=timedelta(minutes=10)
    app.add_timed_work();session=app._work_editor
    fill(session,['2026-10-18','23:00','2026-10-19','01:00','midnight'])
    session.save.invoke();settled(app,root)
    assert app.state['active']==active
    assert app.state['report']['tasks'][task]['daily_us']=={'2026-10-18':H,'2026-10-19':H+10*M}
    app.week_selector.current(0);app.week_selector.event_generate('<<ComboboxSelected>>')
    pump(root,lambda:app.pending is None and app.state.get('week_start')==0 and app._read_inflight is None)
    assert app.state['report']['application']['week_us']==H+10*M
    before=evidence(worker)
    app.request_close();root.after(8000,root.quit);root.mainloop();worker.join(timeout=5)
    assert not app.alive and not worker.is_alive()
    # Reopen the actual application owner/worker, not only a storage probe.
    import gc
    import tkinter as tk
    gc.collect()
    reopened_root=tk.Tk();errors=[]
    reopened_root.report_callback_exception=lambda *args:errors.append(args)
    reopened_worker=DatabaseWorker(worker.directory)
    reopened_app=ChronicleApp(reopened_root,reopened_worker,now_utc=clock)
    reopened_worker.start()
    try:
        pump(reopened_root,lambda:reopened_app.ready and reopened_app.state['report'] is not None)
        assert reopened_app.state['week_start']==0 and reopened_app.state['active']==active
        assert reopened_app.week_selector.get()=='Monday'
        assert reopened_app.tree.item(reopened_app.task_row(task),'values')[1:]==('01:10','01:10')
        reopened_app.open_mini();pump(reopened_root,lambda:reopened_app._read_inflight is None)
        assert reopened_app.mini.today.cget('text')=='Today: 01:10'
        assert evidence(reopened_worker)==before and not errors
    finally:
        if reopened_app.alive:reopened_root.destroy()
        reopened_worker.join(timeout=8)
        assert not reopened_worker.is_alive()
        gc.collect()


def test_real_tk_timed_repeated_endpoint_choices_and_no_capture_on_drafts(connected,root):
    app,worker,clock=connected;select_task(app)
    clock.value=from_us(NOW)+timedelta(days=14)
    app.add_timed_work();session=app._work_editor
    fill(session,['2026-11-01','01:30','2026-11-01','01:30','repeat'])
    count=clock.calls;before=evidence(worker)
    assert session.choices and session.extra_selectors[0].cget('values')
    session.save.invoke()
    assert app.pending is None and clock.calls==count and evidence(worker)==before
    session.selector.current(0);session.extra_selectors[0].current(1)
    session.save.invoke();settled(app,root)
    rows=evidence(worker)['work_revisions']
    assert len(rows)==1 and rows[0][4]-rows[0][3]==H


def test_real_tk_manual_commit_survives_later_refresh_failure_and_recovers(connected,root,monkeypatch):
    app,worker,clock=connected;select_task(app)
    import chronicle.app as module
    original=module.format_duration
    app.add_date_only_work();session=app._work_editor
    fill(session,['2026-10-19','1:00','saved'])
    monkeypatch.setattr(module,'format_duration',lambda value: (_ for _ in ()).throw(ValueError('numeric presentation fault')))
    session.save.invoke();pump(root,lambda:app.pending is None and app.editor is None and app.state['report'] is None)
    assert 'Saved' in app.status.cget('text') and len(evidence(worker)['work_revisions'])==1
    assert str(app.buttons['Start'].cget('state'))=='normal'
    monkeypatch.setattr(module,'format_duration',original)
    # Normal scheduled refresh, not a rapid retry loop.
    pump(root,lambda:app.state['report'] is not None,timeout=5000)
    assert app.state['report']['application']['today_us']==H and app._tick_id is not None


@pytest.mark.parametrize('status',['rejected','rolled_back','unavailable'])
def test_real_tk_settled_manual_failures_keep_editable_draft_and_allow_new_save(connected,root,monkeypatch,status):
    from chronicle.records import StaleState
    app,worker,clock=connected;select_task(app)
    original=TimerService.execute;requests=[]
    error=StaleState('selected task changed') if status=='rejected' else OSError('settled storage fault')
    def fail_once(service,request):
        requests.append(request)
        return Outcome(status,error=error) if len(requests)==1 else original(service,request)
    monkeypatch.setattr(TimerService,'execute',fail_once)
    app.add_date_only_work();session=app._work_editor
    values=fill(session,['2026-10-19','1:00','retained'])
    before=evidence(worker)
    session.save.invoke();pump(root,lambda:session.outcome is not None)
    assert session.phase=='editing' and session.request is None
    assert tuple(e.get() for e in session.fields)==values and evidence(worker)==before
    assert any(args[1] is error for args in root.test_errors)
    session.save.invoke();settled(app,root)
    assert len(requests)==2 and requests[0].request_id!=requests[1].request_id
    assert requests[0].args()['entry_id']==requests[1].args()['entry_id']
    assert len(evidence(worker)['work_entries'])==1


@pytest.mark.parametrize('confirm',[False,True])
def test_real_tk_manual_unverified_exit_warning_is_owned_and_default_cancel(connected,root,monkeypatch,confirm):
    import chronicle.app as module
    app,worker,clock=connected;select_task(app)
    original=TimerService.execute
    def lost(service,request):
        result=original(service,request)
        assert result.status=='committed'
        return Outcome('unverified',error=OSError('lost save response'))
    monkeypatch.setattr(TimerService,'execute',lost)
    app.add_date_only_work();session=app._work_editor
    values=fill(session,['2026-10-19','1:00','frozen'])
    session.save.invoke();frozen=app.pending
    pump(root,lambda:session.phase=='unverified')
    calls=[]
    def decide(*args,**kwargs):
        calls.append(kwargs)
        assert kwargs['parent'] is session.window and kwargs['default']=='no'
        assert not app.retry() and not app.exceptional_exit() and not app.add_timed_work()
        app.request_close()
        return confirm
    monkeypatch.setattr(module.messagebox,'askyesno',decide)
    app.request_close();assert len(calls)==1
    if confirm:
        root.after(6000,root.quit);root.mainloop();worker.join(timeout=5)
        assert not app.alive and not worker.is_alive()
        store=SQLiteStore(worker.directory)
        try:
            assert store.connection.execute('SELECT count(*) FROM work_entries').fetchone()[0]==1
        finally:store.close()
    else:
        assert app.pending is frozen and root.grab_current() is session.window and not app.closing
        assert tuple(e.get() for e in session.fields)==values
        session.retry.invoke();settled(app,root)
        assert len(evidence(worker)['work_entries'])==1


@pytest.mark.parametrize("fault",["construction","presentation"])
def test_real_tk_form_construction_failure_preserves_diagnostics_and_allows_reopen(connected,root,monkeypatch,fault):
    import chronicle.app as module
    app,worker,clock=connected;select_task(app)
    before=evidence(worker);error=OSError(f'{fault} fault')
    with monkeypatch.context() as m:
        if fault=='construction':
            m.setattr(module.ttk,'Entry',lambda *args,**kwargs: (_ for _ in ()).throw(error))
        else:
            m.setattr(app,'_present_editor',lambda top: (_ for _ in ()).throw(error))
        assert not app.add_timed_work()
    assert app.editor is None and app._work_editor is None and app.can_mutate()
    assert any(args[1] is error for args in root.test_errors)
    assert evidence(worker)==before
    assert app.add_date_only_work();app._work_editor.cancel.invoke()
    pump(root,lambda:app.editor is None)


def test_real_tk_manual_local_default_and_tk_thread_delivery(connected,root,monkeypatch):
    import threading
    import tkinter as tk
    app,worker,clock=connected;select_task(app)
    clock.value=from_us(NOW)-timedelta(hours=14,minutes=30)
    root.after_cancel(app._tick_id);app._tick_id=None
    owner=threading.get_ident();seen=[]
    for cls,method in ((tk.Misc,'_configure'),(tk.Entry,'get'),(tk.Entry,'insert'),(tk.Toplevel,'destroy')):
        original=getattr(cls,method)
        def check(*args,_original=original,**kwargs):
            assert threading.get_ident()==owner
            seen.append(threading.get_ident())
            return _original(*args,**kwargs)
        monkeypatch.setattr(cls,method,check)
    assert app.add_date_only_work();session=app._work_editor
    assert session.fields[0].get()=='2026-10-18'
    fill(session,['2026-10-18','1:00','local date'])
    session.save.invoke();settled(app,root)
    assert seen and app.state['report']['today']=='2026-10-18'
    assert app.state['report']['application']['today_us']==H


def test_real_tk_week_choice_survives_read_delivery_and_rejected_write_restores_metadata(connected,root,monkeypatch):
    from copy import deepcopy
    app,worker,clock=connected
    root.after_cancel(app._tick_id);app._tick_id=None
    # Read delivery between a control edit and its queued selection callback must not erase the choice.
    app.week_selector.current(0)
    app._render(deepcopy(app.state))
    assert app.week_selector.current()==0 and app.state['week_start']==6
    app.week_selector.event_generate('<<ComboboxSelected>>')
    pump(root,lambda:app.pending is None and app.state['week_start']==0 and app._read_inflight is None)
    before=evidence(worker);original=TimerService.execute
    error=OSError('week update unavailable')
    def unavailable(service,request):
        return Outcome('unavailable',error=error) if request.operation=='set_week_start' else original(service,request)
    monkeypatch.setattr(TimerService,'execute',unavailable)
    app.week_selector.current(2);app.week_selector.event_generate('<<ComboboxSelected>>')
    pump(root,lambda:app.pending is None and app._read_inflight is None and 'unavailable' in app.status.cget('text'))
    assert app.week_selector.current()==0 and app.state['week_start']==0
    assert evidence(worker)==before and any(args[1] is error for args in root.test_errors)
