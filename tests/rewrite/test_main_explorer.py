"""Package A real-widget/worker/SQLite presentation and operator evidence."""
from copy import deepcopy
from datetime import timedelta

import pytest

from chronicle.app import ChronicleApp
from chronicle.services import TimerService
from conftest import NOW, uid
from test_app import root, connected, click, keyboard, pump, evidence


def settled(app):
    pump(app.root, lambda: app.pending is None and not app.executing and app._read_inflight is None)


def submit(app, operation, **args):
    assert app._submit(operation, **args)
    settled(app)


def project(app, name='Project', key=None):
    key = key or uid()
    submit(app, 'create_project', project_id=key, name=name)
    return key


def task(app, name='Task', group=None, key=None):
    key = key or uid()
    submit(app, 'create_task', task_id=key, name=name, project_id=group, expected_project_version=1 if group else None)
    return key


def select(app, row):
    app.tree.selection_set(row)
    app._selection_changed()


def test_real_tk_typed_groups_empty_projects_duplicates_and_organization(connected):
    app, worker, clock = connected
    p = project(app, 'Same'); empty = project(app, 'Same')
    a = task(app, 'Same', p, p); b = task(app, 'Same', p); c = task(app, 'Same')
    assert len({app.project_row(p), app.task_row(a), app.project_row(None)}) == 3
    assert set(app.tree.get_children()) == {app.project_row(p), app.project_row(empty), app.project_row(None)}
    assert app.tree.get_children(app.project_row(empty)) == ()
    assert app.tree.item(app.project_row(empty), 'values') == ('Group', '—', '00:00')
    assert set(app.tree.get_children(app.project_row(p))) == {app.task_row(a), app.task_row(b)}
    assert app.tree.parent(app.task_row(c)) == app.project_row(None)
    for row in (app.project_row(p), app.project_row(None)):
        select(app, app.task_row(a)); select(app, row)
        before = evidence(worker)
        assert app.selected_task_id() is None and not app.start() and not app.switch()
        app.rename_task(); app.assign_project(); app.add_timed_work(); app.add_date_only_work(); app.open_history()
        assert evidence(worker) == before and app.editor is None and app.history is None
        for label in ('Start','Switch','Rename task','Work History','Assign project'):
            assert app.buttons[label].instate(['disabled'])


@pytest.mark.parametrize('destination', ['project','task','unassigned','none'])
def test_real_tk_context_new_task_freezes_visible_flat_destination(connected, monkeypatch, destination):
    app, worker, clock = connected
    p = project(app); a = task(app, group=p)
    row = {'project':app.project_row(p), 'task':app.task_row(a), 'unassigned':app.project_row(None)}.get(destination)
    if row: select(app, row)
    else: app.tree.selection_remove(app.tree.selection())
    prompts=[]
    def ask(*args, **kwargs):
        prompts.append(args[1]);return 'Created'
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',ask)
    app.create_task();settled(app)
    created = next(t for t in app.state['tasks'] if t['name']=='Created')
    assert created['project_id'] == (p if destination in ('project','task') else None)
    assert 'Destination:' in prompts[0] and 'not a subtask' in prompts[0]
    assert ('Unassigned' in prompts[0]) == (destination in ('unassigned','none'))
    assert app.tree.parent(app.task_row(created['task_id'])) == app.project_row(created['project_id'])


def test_real_tk_selected_empty_project_rename_and_task_reassignment_preserve_work(connected, monkeypatch):
    app, worker, clock=connected
    p=project(app); target=project(app,'Empty');a=task(app,group=p)
    submit(app,'add_date_only_work',task_id=a,entry_id=uid(),work_date='2026-10-19',duration_text='1:30',comment='')
    original=evidence(worker)
    select(app,app.project_row(target))
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',lambda *a,**k:'Renamed')
    app.rename_project();settled(app)
    assert app.tree.item(app.project_row(target),'text')=='Renamed'
    select(app,app.task_row(a));app.assign_project()
    # Actual owned choice control and callback; no new database operation.
    combo=next(w for w in app.editor.winfo_children() if w.winfo_class()=='TCombobox')
    combo.current(1+next(i for i,p in enumerate(app.state['projects']) if p['project_id']==target))
    next(w for w in app.editor.winfo_children() if w.winfo_class()=='TButton').invoke();settled(app)
    assert app.tree.parent(app.task_row(a))==app.project_row(target)
    assert app.selected_task_id()==a
    current=evidence(worker)
    for key in ('work_entries','work_revisions','active_timer'):
        assert current[key]==original[key]


def test_real_tk_shared_period_totals_hidden_work_and_read_only_navigation(connected):
    app,worker,clock=connected
    p=project(app);a=task(app,group=p);b=task(app);hidden=task(app,group=p)
    for t,day,duration in ((a,'2026-10-19','1:30'),(a,'2026-10-24','2:00'),(b,'2026-10-19','0:20'),(hidden,'2026-10-19','0:10')):
        submit(app,'add_date_only_work',task_id=t,entry_id=uid(),work_date=day,duration_text=duration,comment='')
    before=evidence(worker)
    # Existing reader includes retained hidden identities; navigation is a projection only.
    snapshot=deepcopy(app.state);next(t for t in snapshot['tasks'] if t['task_id']==hidden)['effective_archived']=True
    app._render(snapshot)
    assert not app.tree.exists(app.task_row(hidden))
    assert app.tree.item(app.project_row(p),'values')[2]=='01:40'
    assert app.tree.item(app.task_row(a),'values')[1:]==('01:30','01:30')
    assert app.headline.cget('text')=='Today: 02:00    This week: 04:00'
    app.period.set('This Week');app._presentation_changed()
    assert app.tree.item(app.project_row(p),'values')[2]=='03:40'
    assert app.tree.item(app.task_row(a),'values')[1:]==('03:30','03:30')
    assert evidence(worker)==before
    failed=deepcopy(app.state);failed['report']=None;failed['calculation_error']='injected failure';app._render(failed)
    assert all(app.tree.item(row,'values')[2]=='—' for row in app.tree.get_children())
    assert app.tree.item(app.task_row(a),'values')[1:]==('—','—')
    select(app,app.task_row(a));assert not app.buttons['Start'].instate(['disabled'])
    app._render(snapshot);assert app.tree.item(app.project_row(p),'values')[2]=='03:40'


def test_real_tk_unchanged_refresh_no_row_or_label_writes_sort_selection_scroll(connected, monkeypatch):
    app,worker,clock=connected
    p=project(app,'Z');q=project(app,'A');a=task(app,'Z',p);b=task(app,'A',p)
    select(app,app.task_row(a));app.tree.item(app.project_row(q),open=False)
    app.tree.yview_moveto(0);before=evidence(worker);writes=[]
    for method in ('insert','delete','move','item'):
        original=getattr(app.tree,method)
        def observed(*args,_method=method,_original=original,**kwargs):
            if _method!='item' or kwargs:writes.append((_method,args,kwargs))
            return _original(*args,**kwargs)
        monkeypatch.setattr(app.tree,method,observed)
    for widget in (app.headline,app.active_label,app.error):
        original=widget.configure
        monkeypatch.setattr(widget,'configure',lambda *a,_original=original,**k:(writes.append(('label',k)),_original(*a,**k))[1])
    scroll=app.tree.yview()
    app._render(app.state);assert writes==[]
    app.sort_alpha.set(True);app._presentation_changed()
    assert app.tree.get_children(app.project_row(p))==(app.task_row(b),app.task_row(a))
    assert app.selected_task_id()==a and not app.tree.item(app.project_row(q),'open')
    app.period.set('This Week');app._presentation_changed();assert app.tree.yview()==scroll
    assert not app.tree.item(app.project_row(q),'open') and evidence(worker)==before


def test_real_tk_server_running_groups_stop_switch_and_mini_workflow(connected, root, click):
    app,worker,clock=connected
    p=project(app);a=task(app,'First',p);b=task(app,'Second')
    select(app,app.task_row(a));click(app.buttons['Start']);settled(app)
    assert app.tree.item(app.task_row(a),'tags')==('running',)
    assert 'Running' in app.tree.item(app.project_row(p),'values')[0]
    active=deepcopy(app.state['active'])
    # Retained tasks/work can outlive normal project navigation in schema-1 reads.
    current=deepcopy(app.state);retained=deepcopy(current);retained['projects']=[]
    prior=deepcopy(current);prior['active']=None;app._render(prior)
    app._render(retained)
    assert not app.tree.exists(app.project_row(p))
    assert app.state['report']==current['report'] and app.headline.cget('text')=='Today: 00:00    This week: 00:00'
    assert app.active_label.cget('text')=='▶ Running: First' and not app.buttons['Stop'].instate(['disabled'])
    app._render(current)
    click(app.buttons['Mini mode']);mini=app.mini
    assert mini.state_bar.cget('background')=='#08752c' and 'Running' in mini.state_bar.cget('text')
    assert not app.keep_mini_open.get()
    select(app,app.project_row(None));clock.value+=timedelta(minutes=2)
    click(mini.toggle);settled(app)
    assert app.state['active'] is None and app.tree.item(app.task_row(a),'tags')==('stopped',)
    assert mini.name.cget('text')=='No task selected'
    click(mini.show_main);assert app.mini is None
    select(app,app.task_row(a));click(app.buttons['Start']);settled(app)
    clock.value+=timedelta(seconds=1)
    select(app,app.task_row(b));click(app.buttons['Switch']);settled(app)
    assert app.state['active']['task_id']==b
    app.keep_mini_open.set(True);click(app.buttons['Mini mode']);mini=app.mini
    click(mini.show_main);assert app.mini is mini and mini.window.winfo_exists()
    assert mini.name.cget('text')=='Second' and active['entry_id']!=app.state['active']['entry_id']
    # Owned manual editor blocks direct main/mini presentation as well as real input.
    app.add_date_only_work();pump(root,lambda:root.grab_current() is app.editor)
    focus=root.focus_get();grab=root.grab_current();state=evidence(worker)
    assert not app.open_mini() and not app.show_main() and not app.mini_toggle()
    assert root.grab_current() is grab and root.focus_get() is focus
    assert not bool(mini.window.attributes('-topmost'))
    click(mini.show_main);assert root.grab_current() is grab and evidence(worker)==state
    app._close_editor(app.editor)
    assert root.test_errors==[]


def test_real_tk_observation_without_repaint_minute_midnight_clock_warning_and_recovery(connected, monkeypatch):
    app,worker,clock=connected
    a=task(app);select(app,app.task_row(a));assert app.start();settled(app)
    active=deepcopy(app.state['active']);before=evidence(worker)
    app.root.after_cancel(app._tick_id);app._tick_id=None
    writes=[];original=app.tree.item
    def item(*args,**kwargs):
        if kwargs:writes.append(kwargs)
        return original(*args,**kwargs)
    monkeypatch.setattr(app.tree,'item',item)
    def tick():
        app._tick();app.root.after_cancel(app._tick_id);app._tick_id=None;settled(app)
    clock.value+=timedelta(seconds=1);tick()
    assert app.state['report']['cutoff_utc_us']==NOW+1_000_000 and writes==[]
    assert 'as of' not in app.headline.cget('text') and 'since' not in app.active_label.cget('text')
    clock.value+=timedelta(seconds=59);tick()
    assert app.tree.item(app.task_row(a),'values')[1:]==('00:01','00:01')
    clock.value=clock.value.replace(day=20,hour=5,minute=1) # midnight in America/Chicago
    tick();assert app.state['report']['today']=='2026-10-20'
    assert app.tree.item(app.task_row(a),'values')[1:]==('00:01','00:01')
    clock.value=clock.value.replace(day=19,hour=14,minute=59);tick()
    assert app.state['report'] is None and 'Observation precedes active start' in app.error.cget('text')
    assert app.tree.item(app.task_row(a),'values')[1:]==('—','—')
    clock.value=clock.value.replace(hour=15,minute=2);tick()
    assert app.state['active']==active and app.tree.item(app.task_row(a),'values')[1:]==('00:02','00:02')
    assert evidence(worker)==before


def test_real_tk_actual_scroll_and_expansion_preserved_through_reads_and_period(connected):
    app,worker,clock=connected
    p=project(app)
    keys=[task(app,str(i),p) for i in range(26)]
    app.root.geometry('720x420')
    pump(app.root,lambda:app.root.winfo_width()==720 and app.root.winfo_height()==420)
    app.tree.see(app.task_row(keys[-1]));app.tree.yview_moveto(1)
    pump(app.root,lambda:app.tree.yview()[0]>0)
    select(app,app.task_row(keys[-1]));scroll=app.tree.yview()
    assert scroll[0]>0
    app.refresh();settled(app)
    assert app.tree.yview()==scroll and app.selected_task_id()==keys[-1]
    app.period.set('This Week');app._presentation_changed()
    assert app.tree.yview()==scroll and app.selected_task_id()==keys[-1]
    app.tree.item(app.project_row(p),open=False);app.refresh();settled(app)
    assert not app.tree.item(app.project_row(p),'open')


def test_real_tk_numeric_presentation_failure_clears_all_groups_and_recovers(connected, monkeypatch):
    app,worker,clock=connected
    p=project(app);a=task(app,group=p)
    import chronicle.app as module
    original=module.format_duration
    def fail(value):raise ValueError('numeric presentation failure')
    monkeypatch.setattr(module,'format_duration',fail)
    app.refresh();settled(app)
    assert app.state['report'] is None
    for row in (app.project_row(p),app.project_row(None),app.task_row(a)):
        assert app.tree.item(row,'values')[1:]==('—','—')
    monkeypatch.setattr(module,'format_duration',original)
    app.refresh();settled(app)
    assert app.state['report'] is not None and app.tree.item(app.task_row(a),'values')[1:]==('00:00','00:00')


def test_real_tk_period_failure_and_active_commit_keep_status_truthful(connected, monkeypatch):
    app,worker,clock=connected
    a=task(app);select(app,app.task_row(a));app.open_mini()
    import chronicle.app as module
    original=module.format_duration
    def fail(value):raise ValueError('period formatter')
    monkeypatch.setattr(module,'format_duration',fail)
    app.period.set('This Week');app._presentation_changed()
    assert app.state['report'] is None and app.tree.item(app.task_row(a),'values')[1:]==('—','—')
    assert app.start();settled(app)
    assert app.state['active']['task_id']==a and 'Running' in app.active_label.cget('text')
    assert app.tree.item(app.task_row(a),'tags')==('running',)
    assert 'Running' in app.mini.state_bar.cget('text') and app.mini.today.cget('text')=='Today: —'
    monkeypatch.setattr(module,'format_duration',original)
    app.refresh();settled(app)
    assert app.state['report'] is not None
