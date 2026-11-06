"""Real Main geometry and connected actions; X11 evidence is not Windows acceptance."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import pytest

from schema4_cases import adapter
from test_app import root,connected,pump
from test_schema4_project_modal import connected_candidate
from test_main_explorer import select,settled
from test_backup_restore import logical


PRIMARY=('New Task','Rename task','Create project','Rename project')
SECONDARY=('Move / Reparent','Mini mode','Delete','Templates...')
OTHER=('Start','Stop','Switch','Correct active start','Add timed work','Add date-only work',
       'Work History','Timesheet / POL-R','Recheck POL-R','Backup Chronicle','Archive','Archived Items')
CALLBACKS=('create_task','rename_task','create_project','rename_project','open_move','open_mini',
           'open_delete','open_templates')


@pytest.fixture(params=['schema3','schema4-candidate'])
def main(request):
    app,w,clock=request.getfixturevalue('connected_candidate' if request.param=='schema4-candidate' else 'connected')
    app.root.after_cancel(app._tick_id);app._tick_id=None
    settled(app)
    return app,w,clock


def facts(worker):
    return logical(worker.adapter.path if hasattr(worker,'adapter') else Path(worker.directory)/'chronicle.sqlite3')


def geometry(app,size):
    width,height=map(int,size.split('x'))
    app.root.geometry(size)
    pump(app.root,lambda:app.root.winfo_width()==width and app.root.winfo_height()==height)
    app.root.update_idletasks()
    done=[];app.root.after_idle(lambda:done.append(True));pump(app.root,lambda:done)
    app.root.update_idletasks()


def inside(widget,parent):
    assert widget.master is parent and widget.winfo_exists() and widget.winfo_ismapped()
    x,y,width,height=widget.winfo_x(),widget.winfo_y(),widget.winfo_width(),widget.winfo_height()
    assert x>=0 and y>=0 and width>0 and height>0
    assert x+width<=parent.winfo_width() and y+height<=parent.winfo_height(),(str(widget),x,y,width,height,parent.winfo_width(),parent.winfo_height())


def assert_layout(app):
    primary=app.buttons[PRIMARY[0]].master;secondary=app.buttons[SECONDARY[0]].master
    settings=app.week_selector.master;guidance=app.new_task_hint.master;outer=primary.master
    frames=(primary,secondary,settings,guidance)
    assert len(set(frames))==4
    inside(outer,app.root)
    for index,frame in enumerate(frames):
        inside(frame,outer)
        assert int(frame.grid_info()['row'])==index and int(frame.grid_info()['column'])==0
    label=next(w for w in settings.winfo_children() if w.winfo_class()=='TLabel' and w.cget('text')=='Week starts')
    groups=([app.buttons[k] for k in PRIMARY],
            [app.buttons[k] for k in SECONDARY]+([app.buttons['New child project']] if app.schema4_presentation else []),
            [label,app.week_selector,app.period_selector,app.sort_control,app.keep_mini_control],
            [app.new_task_hint])
    for frame,widgets in zip(frames,groups):
        assert set(frame.winfo_children())==set(widgets)
        previous=0
        for widget in widgets:
            inside(widget,frame)
            assert widget.winfo_x()>=previous
            previous=widget.winfo_x()+widget.winfo_width()
            assert widget.winfo_height()>=widget.winfo_reqheight()
    assert int(app.new_task_hint.cget('wraplength'))<=guidance.winfo_width()
    assert app.new_task_hint.cget('text')
    # The tree and lower action area must still fit vertically at 420, not merely
    # the toolbar. One ordinary row plus its heading has a usable viewport.
    inside(app.tree,app.tree.master);inside(app.tree.master,app.root)
    assert app.tree.winfo_height()>=40
    for button in app.buttons.values():
        inside(button,button.master)
        assert button.winfo_rooty()+button.winfo_height()<=app.root.winfo_rooty()+app.root.winfo_height()
    for widget in (app.headline,app.active_label,app.error,app.status):inside(widget,app.root)
    assert app.tree.column('individual')['minwidth']>=80 and app.tree.column('cumulative')['minwidth']>=80


def identities(app):
    # Tcl may compile an invoked command into a bytecode object; compare its
    # unchanged command name, not that internal representation's Python type.
    return dict(buttons=dict(app.buttons),commands={k:str(w.cget('command')) for k,w in app.buttons.items()},
                week=app.week_selector,period=app.period_selector,sort=app.sort_control,keep=app.keep_mini_control,
                hint=app.new_task_hint,week_binding=app.week_selector.bind('<<ComboboxSelected>>'),
                period_binding=app.period_selector.bind('<<ComboboxSelected>>'))


@pytest.mark.parametrize('size',['720x420','850x550'])
def test_actual_geometry_control_set_and_independent_rows(main,size):
    app,w,clock=main
    expected=set(PRIMARY+SECONDARY+OTHER)|({'New child project'} if app.schema4_presentation else set())
    assert set(app.buttons)==expected and len(set(app.buttons.values()))==len(expected)
    for key,callback in zip(PRIMARY+SECONDARY,CALLBACKS):assert app.buttons[key].cget('command').endswith(callback)
    assert app.buttons['Create project'].cget('text')==('New root project' if app.schema4_presentation else 'Create project')
    if app.schema4_presentation:assert app.buttons['New child project'].cget('command').endswith('create_child_project')
    assert app.root.minsize()==(720,420) and (app.root.winfo_width(),app.root.winfo_height())==(850,550)
    assert app.period.get()=='Today' and not app.sort_alpha.get() and not app.keep_mini_open.get()
    assert app.week_selector.current()==app.state['week_start']
    assert app.period_selector.cget('textvariable')==str(app.period)
    assert str(app.sort_control.cget('variable'))==str(app.sort_alpha)
    assert str(app.keep_mini_control.cget('variable'))==str(app.keep_mini_open)
    original=identities(app);before=facts(w);report=deepcopy(app.state['report']);calls=clock.calls
    geometry(app,size);assert_layout(app)
    geometry(app,'850x550' if size=='720x420' else '720x420');assert_layout(app)
    geometry(app,size)
    assert identities(app)==original and facts(w)==before and app.state['report']==report and clock.calls==calls
    assert app.pending is None and app.selected_task_id() is None
    assert app.buttons['Rename task'].instate(['disabled']) and app.buttons['Start'].instate(['disabled'])
    if app.schema4_presentation:assert app.buttons['New child project'].instate(['disabled'])


def created(app,key,attribute):
    before={r[attribute] for r in app.state['projects' if attribute=='project_id' else 'tasks']}
    app.buttons[key].invoke();settled(app)
    assert app._mutation_outcome.status=='committed'
    added={r[attribute] for r in app.state['projects' if attribute=='project_id' else 'tasks']}-before
    assert len(added)==1
    return added.pop()


def test_connected_controls_resize_preserves_timer_selection_facts_and_modal(main,monkeypatch):
    app,w,clock=main;names=iter(('Root','Child','Task'))
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',lambda *a,**k:next(names))
    original=identities(app)
    p=created(app,'Create project','project_id');select(app,app.project_row(p))
    if app.schema4_presentation:
        assert app.buttons['New child project'].instate(['!disabled'])
        child=created(app,'New child project','project_id')
        assert next(r for r in app.state['projects'] if r['project_id']==child)['parent_project_id']==p
        select(app,app.project_row(child))
    else:next(names)  # Same final task name across both presentation profiles.
    t=created(app,'New Task','task_id');select(app,app.task_row(t))
    app.period_selector.set('This Week');app.period_selector.event_generate('<<ComboboxSelected>>')
    pump(app.root,lambda:app.period.get()=='This Week');app.sort_control.invoke()
    assert app.sort_alpha.get() and app.buttons['Start'].instate(['!disabled'])
    app.buttons['Start'].invoke();settled(app)
    active=deepcopy(app.state['active']);assert active['task_id']==t
    before=facts(w);report=deepcopy(app.state['report']);calls=clock.calls
    for size in ('720x420','850x550','720x420'):geometry(app,size);assert_layout(app)
    assert app.selected_task_id()==t and app.state['active']==active and app.state['report']==report
    assert facts(w)==before and clock.calls==calls and identities(app)==original
    clock.value+=timedelta(seconds=1)  # Stop requires positive elapsed work.
    app.buttons['Stop'].invoke();settled(app);assert app.state['active'] is None
    app.buttons['Templates...'].invoke();pump(app.root,lambda:app.templates_window is not None)
    assert app.templates_window.close()
    app.buttons['Mini mode'].invoke();pump(app.root,lambda:app.mini is not None and app._read_inflight is None)
    assert app.show_main();pump(app.root,lambda:app.root.winfo_ismapped())
    select(app,app.task_row(t));app.buttons['Move / Reparent'].invoke()
    pump(app.root,lambda:app.movement is not None and app.movement.presented)
    dialog=app.movement;dialog.close_button.focus_set();pump(app.root,lambda:app.root.focus_get() is dialog.close_button)
    before=facts(w);calls=clock.calls
    geometry(app,'850x550');geometry(app,'720x420')
    assert app.root.grab_current() is dialog.window and app.root.focus_get() is dialog.close_button
    assert not app.can_mutate() and not app.create_task() and not app.start()
    assert app.pending is None and facts(w)==before and clock.calls==calls
    assert dialog.close() and app.root.grab_current() is None
    assert identities(app)==original and not app.root.test_errors


def test_pending_request_resize_retains_guards_and_widget_identity(main,monkeypatch):
    app,w,clock=main
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',lambda *a,**k:'Task')
    t=created(app,'New Task','task_id');select(app,app.task_row(t))
    from threading import Event
    entered=Event();put=w.requests.put
    def held(message):
        if message.kind=='mutate':entered.set();messages.append(message)
        else:put(message)
    messages=[];monkeypatch.setattr(w.requests,'put',held)
    app.buttons['Start'].invoke();assert entered.is_set()
    accepted=app.pending;before=facts(w);original=identities(app);calls=clock.calls
    geometry(app,'720x420');geometry(app,'850x550')
    assert app.pending is accepted and app.executing and not app.can_mutate()
    assert app.buttons['Start'].instate(['disabled']) and not app.open_move()
    assert len(messages)==1 and facts(w)==before and clock.calls==calls and identities(app)==original
    put(messages[0]);settled(app)
    assert app.state['active']['task_id']==t and app._mutation_outcome.status=='committed'
