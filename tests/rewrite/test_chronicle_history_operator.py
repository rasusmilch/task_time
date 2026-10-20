"""Server-delivered production History workflow, separate from callback fault tests."""
from copy import deepcopy
from datetime import timedelta
import gc
import time
import tkinter as tk

from chronicle.app import ChronicleApp
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import from_us
from chronicle.worker import DatabaseWorker
from conftest import NOW
from test_app import root, connected, click, keyboard, pump, create, evidence
from test_manual_work import H, M
from test_chronicle_history_ui import selected_task, mutation, precise_closed


def choose_combo(root, widget, index, click, keyboard):
    click(widget,(widget.winfo_width()-8,widget.winfo_height()//2))
    popdown=root.tk.call('ttk::combobox::PopdownWindow',str(widget))
    pump(root,lambda:bool(root.tk.call('winfo','ismapped',popdown)))
    keyboard[0]('Home',control=True)
    for _ in range(index): keyboard[0]('Down')
    keyboard[0]('Return')
    pump(root,lambda:not bool(root.tk.call('winfo','ismapped',popdown)))


def click_row(history, entry, click, root, day=None):
    handle=next(h for h,r in history.mapping.items() if r['entry_id']==entry and (day is None or r['work_date']==day))
    history.tree.see(handle)
    pump(root,lambda:bool(history.tree.bbox(handle)))
    x,y,width,height=history.tree.bbox(handle)
    click(history.tree,(x+max(10,width//3),y+height//2))
    pump(root,lambda:history.tree.selection()==(handle,))
    return handle


def native_confirmation(root,history,click,keyboard,button,yes):
    import ctypes as c
    from ctypes.util import find_library
    x,xt=c.CDLL(find_library('X11')),c.CDLL(find_library('Xtst'))
    x.XOpenDisplay.argtypes,x.XOpenDisplay.restype=[c.c_char_p],c.c_void_p
    x.XCloseDisplay.argtypes=[c.c_void_p]; x.XSync.argtypes=[c.c_void_p,c.c_int]
    xt.XTestFakeMotionEvent.argtypes=[c.c_void_p,c.c_int,c.c_int,c.c_int,c.c_ulong]
    xt.XTestFakeButtonEvent.argtypes=[c.c_void_p,c.c_uint,c.c_int,c.c_ulong]
    display=x.XOpenDisplay(None); assert display
    shown=[]; errors=[]; scheduled=[]; deadline=time.monotonic()+4
    class NativeButton:
        # Toolkit-owned buttons have no Python widget object. Query their real
        # geometry, then use the same XTest pointer fixture as production controls.
        def __init__(self,path): self.path=path
        def winfo_ismapped(self): return int(root.tk.call('winfo','ismapped',self.path))
        def winfo_width(self): return int(root.tk.call('winfo','width',self.path))
        def winfo_height(self): return int(root.tk.call('winfo','height',self.path))
        def winfo_rootx(self): return int(root.tk.call('winfo','rootx',self.path))
        def winfo_rooty(self): return int(root.tk.call('winfo','rooty',self.path))
    def respond():
        grab=str(root.tk.call('grab','current',root._w))
        focus=str(root.tk.call('focus'))
        if grab and grab!=str(history.window) and focus.startswith(grab):
            shown.append(grab)
            try:
                target=grab+('.yes' if yes else '.no')
                assert root.tk.call('winfo','exists',target)
                widget=NativeButton(target)
                if widget.winfo_ismapped() and widget.winfo_width()>10 and widget.winfo_height()>10:
                    xx=widget.winfo_rootx()+widget.winfo_width()//2
                    yy=widget.winfo_rooty()+widget.winfo_height()//2
                    if str(root.tk.call('winfo','containing',xx,yy))==target:
                        assert xt.XTestFakeMotionEvent(display,-1,xx,yy,0)
                        assert xt.XTestFakeButtonEvent(display,1,True,0)
                        assert xt.XTestFakeButtonEvent(display,1,False,0)
                        x.XSync(display,False)  # No nested test mainloop inside the toolkit wait.
                # A window manager may consume an activation click. Continue
                # bounded server input only while this exact native dialog lives.
                if time.monotonic()<deadline:
                    scheduled.append(root.after(20,respond))
            except Exception as exc:
                errors.append(exc)
                abort()
        elif not shown and time.monotonic()<deadline:
            scheduled.append(root.after(10,respond))
    def abort():
        grab=str(root.tk.call('grab','current',root._w))
        if grab and grab!=str(history.window):
            errors.append(TimeoutError('Native confirmation did not consume server input'))
            root.tk.call('destroy',grab)
    timeout=root.after(5000,abort)
    scheduled.append(root.after(10,respond))
    try: click(button)
    finally:
        root.after_cancel(timeout)
        for token in scheduled: root.after_cancel(token)
        x.XCloseDisplay(display)
    assert shown,'Actual owned confirmation was not presented'
    if errors: raise errors[0]


def test_real_tk_server_history_to_inline_edit_delete_details_modal_return_and_restart(connected,root,click,keyboard):
    app,worker,clock=connected
    first=selected_task(app); second=create(app,'Second task')
    app.tree.selection_set(first)
    pump(root,lambda:app._selected()['task_id']==first)
    # Genuine recording captures precise endpoints on either side of local midnight.
    clock.value=from_us(NOW-11*H+123456)
    assert app.start(); pump(root,lambda:app.pending is None and app.state['active'] is not None)
    timed_id=app.state['active']['entry_id']
    start=app.state['active']['start_utc_us']
    clock.value=from_us(NOW-9*H+654321)
    assert app.stop(); pump(root,lambda:app.pending is None and app.state['active'] is None)
    stop=NOW-9*H+654321
    clock.value=from_us(NOW)
    # Use actual connected manual controls, then start an independent live timer.
    click(app.buttons['Add date-only work']); form=app._work_editor
    pump(root,lambda:root.grab_current() is form.window)
    keyboard[1](form.fields[1],'1:30'); click(form.save)
    pump(root,lambda:app.pending is None and app.editor is None)
    dated_id=next(row[0] for row in evidence(worker)['work_entries'] if row[2]=='date_only')
    click(app.buttons['Start']); pump(root,lambda:app.pending is None and app.state['active'] is not None)
    active=deepcopy(app.state['active'])
    click(app.buttons['Mini mode']); pump(root,lambda:app.mini is not None)
    app.tree.focus_set(); pump(root,lambda:root.focus_get() is app.tree)
    click(app.buttons['Work History']); history=app.history
    saved_focus=app._history_return[2]  # The native button press may legitimately move focus.
    pump(root,lambda:history.load_state=='Loaded with rows')
    history.window.geometry('820x740+450+0')
    app.mini.window.geometry('340x180+10+600')
    routed=[]
    main_probe=tk.Button(root,text='Input probe',command=lambda:routed.append('main'))
    mini_probe=tk.Button(app.mini.window,text='Input probe',command=lambda:routed.append('mini'))
    main_probe.place(x=4,y=4);mini_probe.place(x=4,y=4)
    pump(root,lambda:main_probe.winfo_ismapped() and mini_probe.winfo_ismapped())
    assert root.grab_current() is history.window
    assert {r['kind'] for r in history.rows}=={'timed','date_only'}
    assert any(r['is_running'] for r in history.rows)
    before=evidence(worker)
    app.mini.window.lift()  # Make the enabled probe exposed; local grab still owns input.
    click(main_probe)
    app.mini.window.lift()  # Expose mini after the attempted ancestor interaction.
    click(mini_probe)
    assert routed==[]  # Enabled controls outside History: actual grab routing, not disabled-button evidence.
    click(app.buttons['Stop']); click(app.mini.toggle)
    assert evidence(worker)==before and app.state['active']==active
    # Normal event processing remains alive while local modality blocks ancestors.
    events=[]; root.after(15,lambda:events.append(True)); clock.value+=timedelta(seconds=20)
    pump(root,lambda:events and app.state['report']['cutoff_utc_us']==NOW+20_000_000)
    click(history.tree,(90,10)); pump(root,lambda:not history.newest_first)
    choose_combo(root,history.period_control,1,click,keyboard)
    keyboard[1](history.date_controls[0],'2026-10-19')
    keyboard[1](history.date_controls[2],'2026-10-19')
    click(history.date_controls[1]); pump(root,lambda:history.picker is not None)
    click(history.day_buttons[18]); assert history.start.get()=='2026-10-18'
    assert history.snapshot['period']=='current_week'
    click(history.date_controls[3]); pump(root,lambda:history.picker is not None)
    click(history.picker_cancel); assert history.end.get()=='2026-10-19'
    click(history.date_controls[3]); pump(root,lambda:history.picker is not None)
    keyboard[0]('Escape'); pump(root,lambda:history.picker is None)
    assert root.grab_current() is history.window
    click(history.apply_button); pump(root,lambda:history.snapshot_token is None)
    keyboard[1](history.date_controls[0],'2026-10-17')
    drafts=(history.start.get(),history.end.get()); applied=dict(history.applied)
    click_row(history,timed_id,click,root,'2026-10-19')
    assert len([h for h in history.mapping if 'related' in history.tree.item(h,'tags')])==1
    click(history.edit_button); pump(root,lambda:history.phase=='editing')
    # Inline construction adds no Toplevel or clipped replacement identity.
    assert history.reviewed['entry_id']==timed_id and history.reviewed['start_utc_us']==start
    assert history.edit_fields['start_date'].get()=='2026-10-18'
    keyboard[1](history.edit_fields['start_time'],'22:30')
    click(history.cancel_button); pump(root,lambda:history.phase=='browsing')
    assert evidence(worker)==before
    click(history.edit_button); pump(root,lambda:history.phase=='editing')
    keyboard[1](history.edit_fields['start_time'],'22:30')
    click(history.save_button)
    pump(root,lambda:app.pending is None and history.snapshot_token is None and history.phase=='browsing' and app._read_inflight is None)
    assert history.outcome.status=='committed'
    assert (history.start.get(),history.end.get())==drafts and history.applied==applied and not history.newest_first
    revised=next(r for r in evidence(worker)['work_revisions'] if r[0]==timed_id and r[1]==2)
    assert revised[4]==stop and revised[3]!=start
    click_row(history,timed_id,click,root); click(history.details_button)
    pump(root,lambda:history.details_token is None)
    assert 'Correction — revision 2' in history.details_view.get('1.0','end')
    frozen=evidence(worker)
    native_confirmation(root,history,click,keyboard,history.delete_button,False)
    assert evidence(worker)==frozen and root.grab_current() is history.window
    native_confirmation(root,history,click,keyboard,history.delete_button,True)
    pump(root,lambda:app.pending is None and history.snapshot_token is None and history.outcome.status=='committed' and app._read_inflight is None
         and not any(r['entry_id']==timed_id for r in history.rows))
    assert not any(r['entry_id']==timed_id for r in history.rows)
    click(history.details_button)
    index=next(i for i,label in enumerate(history.deleted_control.cget('values')) if timed_id in label)
    choose_combo(root,history.deleted_control,index,click,keyboard)
    pump(root,lambda:history.details_token is None)
    assert 'Deletion — revision 3' in history.details_view.get('1.0','end')
    assert app.state['active']==active and app.state['report']['tasks'][first]['week_us']==90*M+20_000_000
    click(history.close_button); pump(root,lambda:app.history is None)
    assert root.grab_current() is None
    pump(root,lambda:root.focus_get() is saved_focus)
    click(main_probe)
    app.mini.window.lift()  # Origin focus return may legitimately raise main above mini.
    click(mini_probe)
    assert routed==['main','mini']
    before_restart=evidence(worker)
    app.request_close(); root.after(6000,root.quit); root.mainloop(); worker.join(timeout=6)
    assert not app.alive and not worker.is_alive() and not root.test_errors
    gc.collect()
    new_root=tk.Tk(); errors=[]; new_root.report_callback_exception=lambda *args:errors.append(args)
    new_worker=DatabaseWorker(worker.directory); new_app=ChronicleApp(new_root,new_worker,now_utc=clock)
    new_worker.start()
    try:
        pump(new_root,lambda:new_app.ready and new_app.state['report'] is not None)
        assert new_app.state['active']==active and new_app.state['week_start']==6
        new_app.tree.selection_set(first); assert new_app.open_history()
        fresh=new_app.history; pump(new_root,lambda:fresh.snapshot_token is None and fresh.current)
        assert fresh.newest_first and fresh.period.get()=='Current week' and fresh.start.get()==''
        assert timed_id in fresh.deleted_choices.values()
        assert evidence(new_worker)==before_restart and not errors
        keyboard[0]('Escape')
        pump(new_root,lambda:new_app.history is None)
    finally:
        if new_app.alive: new_root.destroy()
        new_worker.join(timeout=6); assert not new_worker.is_alive()
        gc.collect()
