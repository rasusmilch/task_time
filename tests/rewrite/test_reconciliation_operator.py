"""Actual XTest input through reminder, frozen Save, confirmation, correction and reconciliation."""
from copy import deepcopy
from datetime import timedelta
import tkinter as tk
import sqlite3
from pathlib import Path

from conftest import NOW,uid
from test_app import root,connected,click,keyboard,pump,create,evidence
from test_chronicle_history_ui import mutation,selected_task
from test_chronicle_history_operator import choose_combo
from test_chronicle_timesheet_ui import open_sheet
from test_timesheet_save_ui import choose,settled
from test_polr_confirmation_ui import reviewed
from test_polr_confirmation_operator import select_cell,type_hours
from test_reconciliation_ui import ready,reconciled,row


def select_reconciliation(root,sheet,task,day,click):
    handle,_=row(sheet,task,day);sheet.reconciliation_tree.see(handle)
    pump(root,lambda:bool(sheet.reconciliation_tree.bbox(handle)))
    x,y,w,h=sheet.reconciliation_tree.bbox(handle);click(sheet.reconciliation_tree,(x+20,y+h//2))


def test_real_tk_server_actual_export_confirm_correct_reconcile_reminder(connected,root,click,keyboard,tmp_path,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);other=create(app,'Other');entry=uid()
    mutation(app,'add_timed_work',task_id=task,entry_id=entry,start_date='2026-10-12',start_time='9am',end_date='2026-10-12',end_time='10am',start_occurrence=None,end_occurrence=None,comment='genuine')
    for t,day,duration in ((task,'2026-10-13','0:03'),(task,'2026-10-14','0:03'),(other,'2026-10-14','1:08')):
        mutation(app,'add_date_only_work',task_id=t,entry_id=uid(),work_date=day,duration_text=duration,comment='declared date')
    app.tree.selection_set(other);click(app.buttons['Start']);pump(root,lambda:app.pending is None and app.state['active'] is not None)
    active=deepcopy(app.state['active']);click(app.buttons['Mini mode']);app.mini.window.geometry('340x180+0+600')
    ready(app);assert app.reminder['reminder_due'];before=evidence(worker)
    click(app.reminder_open);sheet=app.timesheet
    pump(root,lambda:sheet is not None and sheet.presented and sheet.choices_token is None)
    sheet.window.geometry('800x740+450+0');r=reconciled(app,sheet)
    assert sheet.reconciliation_period.get()=='Last week' and not r['coverage']['complete']
    assert app.reminder['dismissed_local_date'] is None and evidence(worker)==before
    hits=[];main=tk.Button(root,text='Main probe',command=lambda:hits.append('main'));main.place(x=4,y=4)
    mini=tk.Button(app.mini.window,text='Mini probe',command=lambda:hits.append('mini'));mini.place(x=4,y=4)
    app.mini.window.lift();click(main);app.mini.window.lift();click(mini);assert not hits
    choose_combo(root,sheet.reconciliation_controls_list[0],2,click,keyboard)
    keyboard[1](sheet.reconciliation_date_controls[0],'2026-10-12')
    keyboard[1](sheet.reconciliation_date_controls[2],'2026-10-14')
    click(sheet.reconciliation_date_controls[1]);pump(root,lambda:sheet.picker is not None)
    click(sheet.day_buttons[12]);assert sheet.reconciliation_start.get()=='2026-10-12'
    click(sheet.reconciliation_date_controls[3]);keyboard[0]('Escape')
    pump(root,lambda:sheet.picker is None);assert root.grab_current() is sheet.window
    click(sheet.reconciliation_apply);r=reconciled(app,sheet)
    assert not r['task_weeks'][0]['full_scope'] and 'Partial scope' in sheet.reconciliation_summary.get('1.0','end')
    choose_combo(root,sheet.reconciliation_controls_list[1],1,click,keyboard)
    sheet.reconciliation_tasks.see(task);pump(root,lambda:bool(sheet.reconciliation_tasks.bbox(task)))
    x,y,w,h=sheet.reconciliation_tasks.bbox(task);click(sheet.reconciliation_tasks,(x+20,y+h//2))
    click(sheet.reconciliation_apply);r=reconciled(app,sheet)
    assert r['selected_task_ids']==[task] and all(c['task_id']==task for c in r['daily_cells'])
    select_reconciliation(root,sheet,task,'2026-10-14',click);click(sheet.reconciliation_copy)
    assert root.clipboard_get()=='0.00' # Worked day is still Unknown.
    click(sheet.reconciliation_return);choose_combo(root,sheet.period_control,1,click,keyboard)
    click(sheet.preview_button);pump(root,lambda:sheet.current);candidate=sheet.candidate
    destination=tmp_path/'frozen.txt';choose(monkeypatch,sheet,str(destination));click(sheet.save_button);settled(app)
    assert destination.read_bytes()==candidate.report_utf8 and app.reminder['dismissed_local_date'] is None
    click(sheet.review_polr_button);reviewed(app,sheet)
    # Only the timed Monday is confirmed. Other worked cells stay Unknown.
    for key in tuple(sheet.polr_selected):
        if key!=(task,'2026-10-12'):select_cell(root,sheet,key,click)
    click(sheet.polr_confirm_button);reviewed(app,sheet)
    click(sheet.reconciliation_button);reconciled(app,sheet)
    select_reconciliation(root,sheet,task,'2026-10-12',click);click(sheet.reconciliation_manual)
    reviewed(app,sheet);type_hours(root,sheet.polr_hours_control,'2.00',click,keyboard)
    click(sheet.polr_confirm_button);reviewed(app,sheet)
    click(sheet.reconciliation_button);sheet.reconciliation_period.set('Last week');click(sheet.reconciliation_apply);r=reconciled(app,sheet)
    assert row(sheet,task,'2026-10-12')[1]['classification']=='MISMATCH'
    select_reconciliation(root,sheet,task,'2026-10-12',click);click(sheet.reconciliation_confirm);reviewed(app,sheet)
    assert sheet.mode=='confirmation_history' and '2.00' in sheet.polr_detail.get('1.0','end')
    click(sheet.compare_reconciliation_button);r=reconciled(app,sheet)
    assert r['source_comparison']['export_id']==candidate.export_id
    assert any('NEWER_DIFFERING_CONFIRMATION' in c['flags'] for c in r['source_comparison']['cells'])
    frozen_before=destination.read_bytes()
    def confirmation_evidence():
        with sqlite3.connect(Path(worker.directory,'chronicle.sqlite3').as_uri()+'?mode=ro',uri=True) as c:
            return {name:c.execute(f'SELECT * FROM {name} ORDER BY 1,2').fetchall() for name in
                    ('polr_confirmation_batches','polr_confirmation_cells','polr_confirmed_current')}
    confirmations_before=confirmation_evidence()
    click(sheet.close_button);pump(root,lambda:app.timesheet is None)
    app.tree.selection_set(task);click(app.buttons['Work History']);history=app.history
    pump(root,lambda:history.current);choose_combo(root,history.period_control,2,click,keyboard)
    click(history.apply_button);pump(root,lambda:history.snapshot_token is None and history.current)
    handle=next(h for h,v in history.mapping.items() if v['entry_id']==entry)
    history.tree.see(handle);pump(root,lambda:bool(history.tree.bbox(handle)))
    x,y,w,h=history.tree.bbox(handle);click(history.tree,(x+30,y+h//2));click(history.edit_button)
    keyboard[1](history.edit_fields['end_time'],'9:30am');click(history.save_button)
    pump(root,lambda:history.phase=='browsing' and history.snapshot_token is None and app.pending is None)
    click(history.close_button);pump(root,lambda:app.history is None);ready(app)
    click(app.reminder_open);sheet=app.timesheet;pump(root,lambda:sheet.presented);r=reconciled(app,sheet)
    assert row(sheet,task,'2026-10-12')[1]['exact_actual_us']==30*60_000_000
    assert row(sheet,task,'2026-10-12')[1]['confirmed_quarters']==8
    assert 'Weekly upward POL-R rounding adjustment' in sheet.reconciliation_summary.get('1.0','end')
    assert destination.read_bytes()==frozen_before and app.state['active']==active
    assert confirmation_evidence()==confirmations_before
    click(sheet.close_button);pump(root,lambda:app.timesheet is None)
    # New scheduled processing continues, and only explicit Dismiss writes suppression.
    done=[];root.after(10,lambda:done.append(True));clock.value+=timedelta(seconds=5)
    pump(root,lambda:done and app.state['report']['cutoff_utc_us']==NOW+5_000_000)
    before=evidence(worker);click(app.reminder_dismiss);ready(app)
    after=evidence(worker)
    assert not app.reminder['reminder_due'] and app.reminder['dismissed_local_date']=='2026-10-19'
    assert all(after[k]==before[k] for k in before if k not in ('dataset_meta','committed_requests'))
    assert app.state['active']==active and destination.read_bytes()==frozen_before and not root.test_errors
    assert confirmation_evidence()==confirmations_before
