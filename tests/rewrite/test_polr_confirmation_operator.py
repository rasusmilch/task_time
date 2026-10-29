"""Server-delivered Timesheet confirmation, individual consent and manual/history UI."""
from copy import deepcopy
from datetime import timedelta
import tkinter as tk

from conftest import NOW,uid
from test_app import root,connected,click,keyboard,pump,create,evidence
from test_chronicle_history_ui import selected_task,mutation
from test_chronicle_history_operator import choose_combo
from test_timesheet_save_ui import choose,settled
from test_polr_confirmation_ui import reviewed,DAY


def select_cell(root,sheet,key,click):
    handle=next(k for k,r in sheet.polr_mapping.items() if (r['task_id'],r['work_date'])==key)
    sheet.polr_tree.see(handle);pump(root,lambda:bool(sheet.polr_tree.bbox(handle)))
    x,y,w,h=sheet.polr_tree.bbox(handle);click(sheet.polr_tree,(x+25,y+h//2))


def type_hours(root,entry,text,click,keyboard):
    # The existing clock fixture maps ':'; decimal input needs the named X keysym.
    click(entry);pump(root,lambda:root.focus_get() is entry)
    keyboard[0]('Home');keyboard[0]('End',shift=True);keyboard[0]('BackSpace')
    for char in text:keyboard[0]('period' if char=='.' else char)
    pump(root,lambda:entry.get()==text)


def test_real_tk_server_frozen_source_checked_zero_manual_stale_ack_history_modal(connected,root,click,keyboard,tmp_path,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);other=create(app,'Other')
    mutation(app,'add_timed_work',task_id=other,entry_id=uid(),start_date=DAY,start_time='9am',end_date=DAY,end_time='9:15am',start_occurrence=None,end_occurrence=None,comment='genuine interval')
    app.tree.selection_set(app.task_row(task))
    click(app.buttons['Add date-only work']);form=app._work_editor
    pump(root,lambda:root.grab_current() is form.window)
    keyboard[1](form.fields[1],'3:00');click(form.save);pump(root,lambda:app.pending is None and app.editor is None)
    click(app.buttons['Start']);pump(root,lambda:app.pending is None and app.state['active'] is not None)
    active=deepcopy(app.state['active']);click(app.buttons['Mini mode']);pump(root,lambda:app.mini is not None)
    click(app.buttons['Timesheet / POL-R']);sheet=app.timesheet;pump(root,lambda:sheet.presented and sheet.choices_token is None)
    sheet.window.geometry('800x740+450+0');app.mini.window.geometry('340x180+10+600')
    routes=[];main=tk.Button(root,text='Main input probe',command=lambda:routes.append('main'));main.place(x=4,y=4)
    mini=tk.Button(app.mini.window,text='Mini input probe',command=lambda:routes.append('mini'));mini.place(x=4,y=4)
    app.mini.window.lift();click(main);app.mini.window.lift();click(mini);assert not routes
    click(sheet.preview_button);pump(root,lambda:sheet.current);candidate=sheet.candidate
    path=tmp_path/'frozen.txt';choose(monkeypatch,sheet,str(path));click(sheet.save_button);settled(app)
    assert app._polr_submission is None and path.read_bytes()==candidate.report_utf8
    before=evidence(worker);click(sheet.review_polr_button);reviewed(app,sheet)
    assert sheet.polr_selected=={(task,DAY),(other,DAY)}
    click(sheet.polr_defer_button);assert evidence(worker)==before
    click(sheet.review_polr_button);reviewed(app,sheet)
    select_cell(root,sheet,(other,DAY),click)
    select_cell(root,sheet,(task,'2026-10-20'),click) # Explicit checked zero; never default-selected.
    click(sheet.polr_confirm_button);reviewed(app,sheet)
    assert app._polr_submission.outcome.status=='committed' and app._polr_submission.outcome.result['cell_count']==2
    click(sheet.manual_polr_button)
    choose_combo(root,sheet.polr_task_control,sheet.polr_task_choices.index(task),click,keyboard)
    click(sheet.polr_context_button);reviewed(app,sheet)
    assert sheet.polr_context['confirmed_quarters']==12
    type_hours(root,sheet.polr_hours_control,'2.30',click,keyboard)
    before=evidence(worker);click(sheet.polr_confirm_button)
    assert evidence(worker)==before and sheet.polr_hours.get()=='2.30' and sheet.polr_ready
    assert isinstance(root.test_errors[-1][1],ValueError);root.test_errors.clear()
    type_hours(root,sheet.polr_hours_control,'5.00',click,keyboard);click(sheet.polr_confirm_button);reviewed(app,sheet)
    assert sheet.polr_context['confirmed_quarters']==20
    click(sheet.review_polr_button);reviewed(app,sheet)
    key=(task,DAY);assert key in sheet.polr_acks and not sheet.polr_acks[key][0].get()
    assert (other,DAY) in sheet.polr_selected # Positive default remains, even untouched Unknown or equal.
    select_cell(root,sheet,(other,DAY),click)
    before=evidence(worker);click(sheet.polr_confirm_button)
    assert evidence(worker)==before and isinstance(root.test_errors[-1][1],ValueError);root.test_errors.clear()
    click(sheet.polr_acks[key][1],(12,12));assert sheet.polr_acks[key][0].get()
    click(sheet.polr_confirm_button);reviewed(app,sheet)
    batch=app._polr_submission.outcome.result['batch_id']
    assert app._polr_submission.outcome.status=='committed' and not sheet.polr_acks
    click(sheet.polr_history_button);reviewed(app,sheet)
    sheet.polr_tree.see(batch);pump(root,lambda:bool(sheet.polr_tree.bbox(batch)))
    x,y,w,h=sheet.polr_tree.bbox(batch);click(sheet.polr_tree,(x+40,y+h//2));click(sheet.polr_load_button);reviewed(app,sheet)
    text=sheet.polr_detail.get('1.0','end');assert '3.00' in text and 'stale acknowledgement True' in text
    assert str(sheet.polr_detail.cget('state'))=='disabled' and app.state['active']==active and path.read_bytes()==candidate.report_utf8
    events=[];root.after(10,lambda:events.append(True));clock.value+=timedelta(seconds=5)
    pump(root,lambda:events and app.state['report']['cutoff_utc_us']==NOW+5_000_000)
    app.mini.window.lift();click(main);app.mini.window.lift();click(mini);assert not routes and root.grab_current() is sheet.window
    click(sheet.close_button);pump(root,lambda:app.timesheet is None)
    click(main);app.mini.window.lift();click(mini);assert routes==['main','mini']
    assert not root.test_errors
