"""Server-delivered Save/recovery interaction; callback fault tests live separately."""
from copy import deepcopy
from datetime import timedelta
import tkinter as tk

from chronicle.timesheet_files import FileState as S
from test_app import root,connected,click,keyboard,pump,evidence
from test_chronicle_history_operator import native_confirmation
from test_chronicle_history_ui import selected_task,seed,mutation
from test_timesheet_save_ui import settled


def test_real_tk_server_save_recover_status_retry_overwrite_and_fresh_preview(connected,root,click,keyboard,tmp_path,monkeypatch):
    app,worker,clock=connected;task=selected_task(app);seed(app,task)
    click(app.buttons['Start']);pump(root,lambda:app.pending is None and app.state['active'] is not None)
    active=deepcopy(app.state['active'])
    click(app.buttons['Mini mode']);pump(root,lambda:app.mini is not None)
    click(app.buttons['Timesheet / POL-R']);sheet=app.timesheet
    pump(root,lambda:sheet.presented and sheet.choices_token is None)
    sheet.window.geometry('800x740+450+0');app.mini.window.geometry('340x180+10+600')
    calls=[]
    main_probe=tk.Button(root,text='Input probe',command=lambda:calls.append('main'))
    mini_probe=tk.Button(app.mini.window,text='Input probe',command=lambda:calls.append('mini'))
    main_probe.place(x=4,y=4);mini_probe.place(x=4,y=4)
    app.mini.window.lift();click(main_probe);app.mini.window.lift();click(mini_probe)
    assert calls==[] and root.grab_current() is sheet.window
    events=[];root.after(10,lambda:events.append(True));clock.value+=timedelta(seconds=10)
    pump(root,lambda:events and app.state['report']['cutoff_utc_us'] is not None)
    click(sheet.preview_button);pump(root,lambda:sheet.current)
    candidate=sheet.candidate;before=evidence(worker)
    import chronicle.timesheet_window as module
    destinations=iter(['',str(tmp_path/'operator.txt'),'',str(tmp_path/'copy.txt')])
    monkeypatch.setattr(module.filedialog,'asksaveasfilename',lambda **kw:next(destinations))
    click(sheet.save_button);assert app._timesheet_attempt is None and sheet.current
    click(sheet.save_button);settled(app)
    attempt=app._timesheet_attempt;dest=tmp_path/'operator.txt'
    assert attempt.saved_path==str(dest) and dest.read_bytes()==candidate.report_utf8
    assert app.state['active']==active and root.grab_current() is sheet.window
    click(sheet.close_button);pump(root,lambda:app.timesheet is None)
    mutation(app,'rename_task',task_id=task,name='New task label',expected_version=1)
    click(app.buttons['Timesheet / POL-R']);sheet=app.timesheet;pump(root,lambda:sheet.presented)
    sheet.window.geometry('800x740+450+0')
    assert sheet.candidate is None and not sheet.current
    click(sheet.saved_button);pump(root,lambda:sheet.saved_token is None)
    sheet.saved_list.see(candidate.export_id)
    pump(root,lambda:bool(sheet.saved_list.bbox(candidate.export_id)))
    x,y,w,h=sheet.saved_list.bbox(candidate.export_id)
    click(sheet.saved_list,(x+30,y+h//2));click(sheet.load_saved_button)
    pump(root,lambda:sheet.saved_token is None)
    attempt=app._timesheet_attempt
    assert attempt.candidate.report_text==candidate.report_text and sheet.report.get('1.0','end-1c')==candidate.report_text
    click(sheet.check_button);settled(app);assert attempt.inspection.state==S.READY
    dest.unlink();click(sheet.check_button);settled(app);assert attempt.inspection.state==S.MISSING
    click(sheet.retry_save_button);settled(app);assert dest.read_bytes()==candidate.report_utf8
    dest.write_bytes(b'operator conflict');click(sheet.check_button);settled(app)
    assert attempt.inspection.conflict is not None
    native_confirmation(root,sheet,click,keyboard,sheet.overwrite_button,False)
    assert dest.read_bytes()==b'operator conflict' and root.grab_current() is sheet.window
    native_confirmation(root,sheet,click,keyboard,sheet.overwrite_button,True)
    settled(app);assert dest.read_bytes()==candidate.report_utf8
    click(sheet.copy_button);assert attempt.destination==str(dest) # Dialog cancellation changes nothing.
    click(sheet.copy_button);settled(app)
    assert (tmp_path/'copy.txt').read_bytes()==candidate.report_utf8 and attempt.candidate.export_id==candidate.export_id
    click(sheet.new_button);assert not sheet.current and sheet.candidate is None
    click(sheet.preview_button);pump(root,lambda:sheet.current)
    assert sheet.candidate.export_id!=candidate.export_id and sheet.candidate.tasks[0].name=='New task label'
    after=evidence(worker)
    assert after['work_entries']==before['work_entries'] and after['work_revisions']==before['work_revisions']
    assert app.state['active']==active and not root.test_errors
    click(sheet.close_button);pump(root,lambda:app.timesheet is None)
    click(main_probe);app.mini.window.lift();click(mini_probe);assert calls==['main','mini']
