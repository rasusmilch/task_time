"""Pilot input/presentation behavior; generated Tk and XTest evidence stay separate."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from queue import Queue
from types import SimpleNamespace

import pytest

from chronicle.app import ChronicleApp
from chronicle.mini_mode import MiniModeWindow
from chronicle.records import Outcome
from conftest import uid
from test_app import root, connected, pump, evidence, click
from test_main_explorer import task, project, select, settled
from tk_observation import wait_observed


class Control:
    def __init__(self, **values):self.values=values;self.manager='';self.writes=0
    def cget(self,key):return self.values.get(key,'')
    def configure(self,**values):self.values.update(values);self.writes+=1
    def winfo_width(self):return 230
    def winfo_manager(self):return self.manager
    def grid(self,**kw):self.manager='grid'
    def grid_remove(self):self.manager=''


class Tree:
    def __init__(self,row):
        self.row=row;self.region='tree';self.element='Treeitem.text';self.present=True
        self.selected=('task:old',);self.focused=None
    def identify_region(self,x,y):return self.region
    def identify_element(self,x,y):return self.element
    def identify_row(self,y):return self.row
    def exists(self,row):return self.present
    def selection(self):return self.selected
    def selection_set(self,row):self.selected=(row,)
    def focus(self,row):self.focused=row


def owner():
    app=ChronicleApp.__new__(ChronicleApp)
    app.alive=app.ready=True;app.closing=app.executing=app._cleanup_failed=app._worker_stopped=False
    app.pending=app._work_editor=app.editor=app.history=app.timesheet=app.template_dialog=None
    app.deletion=app.movement=app._backup_operation=app.backup_dialog=None
    app._history_opening=app._backup_opening=app._timesheet_opening=app._timesheet_dialog_busy=False
    app._reminder_inflight=app._reminder_error=app._mutation_outcome=None
    app._token=0;app._read_again=False
    app.dataset_id=uid();app.worker=SimpleNamespace(requests=Queue())
    app.root=SimpleNamespace(grab=None,deiconify=lambda:None,lift=lambda:None)
    app.root.grab_current=lambda:app.root.grab
    a,b=uid(),uid()
    app.state=dict(active=None,tasks=[dict(task_id=k,name='Duplicate',is_leaf=True,effective_archived=False,version=1) for k in (a,b)],report={'tasks':{a:{'today_us':180_000_000},b:{'today_us':60_000_000}}})
    app.tree=Tree(app.task_row(b));app._controls=lambda:None
    app._selection_changed=lambda:app._controls()
    app.status=Control(text='Routine Saved / Running text')
    app.observations=[]
    def now():app.observations.append(True);return datetime(2026,10,19,15,tzinfo=timezone.utc)
    app.now_utc=now
    return app,a,b


@pytest.mark.parametrize('active,operation',[('none','start_timer'),('same','stop_timer'),('other','switch_timer')])
def test_double_click_reuses_one_real_request_path_and_one_timestamp(active,operation):
    app,a,b=owner()
    if active!='none':app.state['active']=dict(task_id=b if active=='same' else a,entry_id=uid(),version=7)
    before=deepcopy(app.state['active'])
    assert app._task_double_click(SimpleNamespace(widget=app.tree,x=40,y=10))=='break'
    request=app.pending;message=app.worker.requests.get_nowait()
    assert message.kind=='mutate' and message.value is request and request.operation==operation
    assert app.tree.selection()==(app.task_row(b),) and len(app.observations)==1
    args=request.args()
    if operation=='start_timer':assert args['task_id']==b
    if operation=='stop_timer':assert args['entry_id']==before['entry_id'] and args['expected_version']==7
    if operation=='switch_timer':
        assert args['next_task_id']==b and args['expected_active_entry_id']==before['entry_id']
        assert args['next_entry_id']!=before['entry_id']
    app._task_double_click(SimpleNamespace(widget=app.tree,x=40,y=10))
    assert app.worker.requests.empty() and app.pending is request and len(app.observations)==1
    app.executing=False  # Unverified accepted request remains blocked, not retried.
    app._task_double_click(SimpleNamespace(widget=app.tree,x=40,y=10))
    assert app.worker.requests.empty() and app.pending is request and len(app.observations)==1


@pytest.mark.parametrize('blocked',['project','group','parent','archived','stale','missing','indicator','heading','empty',
                                   'foreign widget','pending','executing','modal','native dialog','foreign grab','closing','not ready','dead','cleanup'])
def test_ignored_double_click_never_allocates_or_observes_time(monkeypatch,blocked):
    app,a,b=owner()
    if blocked=='project':app.tree.row='project:'+uid()
    if blocked=='group':app.tree.row='group:unassigned'
    if blocked=='parent':app.state['tasks'][1]['is_leaf']=False
    if blocked=='archived':app.state['tasks'][1]['effective_archived']=True
    if blocked=='stale':app.tree.row='task:'+uid()
    if blocked=='missing':app.tree.present=False
    if blocked=='indicator':app.tree.element='Treeitem.indicator'
    if blocked=='heading':app.tree.region='heading'
    if blocked=='empty':app.tree.region='nothing';app.tree.row=''
    if blocked=='pending':app.pending=object()
    if blocked=='executing':app.executing=True
    if blocked=='modal':app.history=object()
    if blocked=='native dialog':app._timesheet_dialog_busy=True
    if blocked=='foreign grab':app.root.grab=object()
    if blocked=='closing':app.closing=True
    if blocked=='not ready':app.ready=False
    if blocked=='dead':app.alive=False
    if blocked=='cleanup':app._cleanup_failed=True
    def forbidden():raise AssertionError('Ignored event allocated a UUID')
    monkeypatch.setattr('chronicle.app.uuid4',forbidden)
    app._task_double_click(SimpleNamespace(widget=object() if blocked=='foreign widget' else app.tree,x=1,y=1))
    assert app.worker.requests.empty() and not app.observations and app.tree.selection()==('task:old',)


def test_selection_callback_invalidation_cannot_dispatch():
    app,a,b=owner()
    app._selection_changed=lambda:app.state['tasks'].clear()
    app._task_double_click(SimpleNamespace(widget=app.tree,x=20,y=20))
    assert not app.observations and app.worker.requests.empty()


@pytest.mark.parametrize('failure',['clock','queue'])
def test_synchronous_action_diagnostic_is_typed_and_clears_on_new_submission(failure):
    app,a,b=owner();app.tree.selection_set(app.task_row(b))
    error=ValueError('clock rejected') if failure=='clock' else OSError('queue refused')
    app._diagnose=lambda exc:None
    if failure=='clock':app.now_utc=lambda:(_ for _ in ()).throw(error)
    else:app.worker.requests.put=lambda message:(_ for _ in ()).throw(error)
    assert not app.start() and app.pending is None and not app.executing
    assert app._mutation_outcome.error is error and 'Action needs review' in app.mini_diagnostic()
    app.now_utc=lambda:datetime(2026,10,19,15,tzinfo=timezone.utc)
    app.worker.requests=Queue()
    assert app.start() and app.pending is not None and app._mutation_outcome is None


def mini_projection(app):
    mini=MiniModeWindow.__new__(MiniModeWindow);mini.owner=app
    for name in ('name','indicator','today','diagnostic','toggle','show_main'):setattr(mini,name,Control())
    mini._name_font=SimpleNamespace(measure=lambda text:len(text)*8)
    values={'-topmost':False}
    def attributes(key,*args):
        if args:values[key]=args[0]
        return values[key]
    mini.window=SimpleNamespace(attributes=attributes)
    app.mini=mini
    return mini


def test_mini_projection_is_individual_compact_and_never_reads_status_prose():
    app,a,b=owner();app.tree.selection_set(app.task_row(b));mini=mini_projection(app)
    app.state['active']=dict(task_id=a,entry_id=uid(),version=1)
    app.state['tasks'][0]['name']='W'*500
    saved=deepcopy(app.state)
    app.status.cget=lambda key:(_ for _ in ()).throw(AssertionError('Mini read arbitrary status text'))
    mini.render()
    assert mini.name.cget('text').endswith('…') and len(mini.name.cget('text'))<64
    assert mini.today.cget('text')=='Today: 00:03' and mini.toggle.cget('text')=='Stop'
    assert mini.indicator.cget('foreground')=='#08752c' and not mini.diagnostic.winfo_manager()
    writes=mini.name.writes;mini.render();assert mini.name.writes==writes
    assert app.state==saved and not app.observations and app.worker.requests.empty()
    app.state['active']=None;mini.render()
    assert mini.name.cget('text')=='Duplicate' and mini.toggle.cget('text')=='Start'
    assert mini.indicator.cget('foreground')=='#ad2525'
    app.state['tasks'][1]['is_leaf']=False;mini.render()
    assert mini.name.cget('text')=='No task selected' and mini.toggle.cget('state')=='disabled'


@pytest.mark.parametrize('problem,message',[('report','Time unavailable'),('calculation','Time unavailable'),
    ('pending','Action needs review'),('worker','Connection problem'),('cleanup','Connection problem'),
    ('reminder','POL-R needs review'),('mutation','Action needs review')])
def test_mini_diagnostics_derive_from_authority_and_clear(problem,message):
    app,a,b=owner();mini=mini_projection(app);original_report=app.state['report']
    if problem=='report':app.state['report']=None
    if problem=='calculation':app.state['calculation_error']='clock warning'
    if problem=='pending':app.pending=object()
    if problem=='worker':app._worker_stopped=True;app.ready=False
    if problem=='cleanup':app._cleanup_failed=True
    if problem=='reminder':app._reminder_error=ValueError('read failed')
    if problem=='mutation':app._mutation_outcome=Outcome('rejected',error=ValueError('rejected'))
    mini.render()
    assert message in mini.diagnostic.cget('text') and mini.diagnostic.winfo_manager()=='grid'
    assert mini.show_main.cget('state')=='normal'
    if problem=='report':assert mini.today.cget('text')=='Today: —'
    if problem in ('pending','worker','cleanup'):assert mini.toggle.cget('state')=='disabled'
    app.pending=app._reminder_error=app._mutation_outcome=None;app.ready=True
    app._worker_stopped=app._cleanup_failed=False;app.state['report']=original_report;app.state.pop('calculation_error',None)
    mini.render();assert not mini.diagnostic.winfo_manager() and mini.diagnostic.cget('text')==''


@pytest.mark.parametrize('keep',[False,True])
def test_show_main_is_read_only_during_uncertainty_and_preserves_request(keep):
    app,a,b=owner();app.pending=object();request=app.pending
    visited=[];app.root.deiconify=lambda:visited.append('show');app.root.lift=lambda:visited.append('raise')
    app.keep_mini_open=SimpleNamespace(get=lambda:keep)
    app.mini=SimpleNamespace(window=SimpleNamespace(destroy=lambda:visited.append('close mini')))
    assert not app.mini_toggle() and app.show_main()
    assert visited==['show','raise']+([] if keep else ['close mini'])
    assert app.pending is request and not app.worker.requests.qsize() and not app.observations


@pytest.mark.parametrize('modal',['editor','history','timesheet','backup_dialog','_timesheet_dialog_busy','grab'])
def test_show_main_and_mini_mutation_never_bypass_modal(modal):
    app,a,b=owner()
    app.tree.selection_set(app.task_row(b))
    if modal=='grab':app.root.grab=object()
    else:setattr(app,modal,True if modal.startswith('_') else object())
    assert not app.show_main() and not app.mini_toggle() and not app.can_show_main()
    mini=mini_projection(app);mini.render()
    assert mini.toggle.cget('state')=='disabled' and mini.show_main.cget('state')=='disabled'
    assert not mini.window.attributes('-topmost')
    assert app.worker.requests.empty() and not app.observations


@pytest.mark.parametrize('status',['rejected','rolled_back','unavailable','unverified'])
def test_typed_unsuccessful_outcome_needs_no_status_prose_or_exception(status):
    app,a,b=owner();app._mutation_outcome=Outcome(status)
    assert app.mini_diagnostic()=='Action needs review — Show Main'


def _row_point(app,key):
    row=app.task_row(key)
    # Normal test navigation, not foreground input assistance.
    app.tree.see(row)
    pump(app.root,lambda:bool(app.tree.bbox(row)))
    x,y,w,h=app.tree.bbox(row)
    return x+min(w-4,100),y+h//2


@pytest.mark.parametrize('delivery',['generated Tk','XTest'])
def test_real_tk_double_click_start_stop_atomic_switch_and_pending_exclusion(connected,request,monkeypatch,delivery):
    app,worker,clock=connected
    a=task(app,'Duplicate');b=task(app,'Duplicate')
    requests=[]
    from chronicle.services import TimerService
    execute=TimerService.execute
    def record(service,value):requests.append(value);return execute(service,value)
    monkeypatch.setattr(TimerService,'execute',record)
    event_time=[1000]
    def double(key):
        x,y=_row_point(app,key)
        # Separate gestures on the same row also move beyond Tk's multi-click
        # radius, so this is a second double-click rather than a quadruple-click.
        x+=20*((event_time[0]//1000)%2)
        if delivery=='XTest':
            delivered=request.getfixturevalue('click');delivered(app.tree,(x,y));delivered(app.tree,(x,y))
        else:
            for stamp in (event_time[0],event_time[0]+100):
                app.tree.event_generate('<ButtonPress-1>',x=x,y=y,time=stamp)
                app.tree.event_generate('<ButtonRelease-1>',x=x,y=y,time=stamp+10)
        event_time[0]+=1000
    select(app,app.task_row(b));double(a);settled(app)
    first=dict(app.state['active']);assert first['task_id']==a and app.selected_task_id()==a
    assert len(evidence(worker)['active_timer'])==1
    clock.value+=timedelta(minutes=1);double(b);settled(app)
    second=dict(app.state['active']);assert second['task_id']==b and second['entry_id']!=first['entry_id']
    assert len(evidence(worker)['active_timer'])==1
    clock.value+=timedelta(minutes=1);double(b);settled(app)
    assert app.state['active'] is None
    assert [r.operation for r in requests]==['start_timer','switch_timer','stop_timer']
    facts=evidence(worker)
    assert len(facts['work_entries'])==2 and not facts['active_timer']
    closed={r[0]:(r[3],r[4]) for r in facts['work_revisions']}
    assert closed[first['entry_id']]==(first['start_utc_us'],second['start_utc_us'])
    assert closed[second['entry_id']]==(second['start_utc_us'],second['start_utc_us']+60_000_000)
    # Direct dispatch while an accepted request is pending cannot add another.
    x,y=_row_point(app,a)
    assert app._task_double_click(SimpleNamespace(widget=app.tree,x=x,y=y))=='break'
    pending=app.pending
    app._task_double_click(SimpleNamespace(widget=app.tree,x=x,y=y))
    assert app.pending is pending;settled(app)
    assert len(requests)==4 and requests[-1].operation=='start_timer'
    assert app.add_date_only_work()
    pump(app.root,lambda:app.editor is not None and app.root.grab_current() is app.editor)
    before=evidence(worker);grab=app.root.grab_current()
    app._task_double_click(SimpleNamespace(widget=app.tree,x=x,y=y))
    if delivery=='XTest':
        delivered=request.getfixturevalue('click');delivered(app.tree,(x,y));delivered(app.tree,(x,y))
    else:double(b)
    assert evidence(worker)==before and app.root.grab_current() is grab
    app._close_editor(app.editor)


def test_real_tk_compact_mini_geometry_long_names_and_actionable_navigation(connected):
    app,worker,clock=connected
    a=task(app,'Long name '+'W'*300);select(app,app.task_row(a))
    assert app.open_mini();mini=app.mini
    wait_observed(app.root,lambda:mini.window.winfo_ismapped() and mini.toggle.winfo_ismapped()
        and mini.show_main.winfo_ismapped() and mini.name.winfo_width()>1,
        phase='Compact Mini layout',widgets=(mini.window,mini.name,mini.toggle,mini.show_main))
    width,height=mini.window.winfo_width(),mini.window.winfo_height()
    print('CHRONICLE_MINI_GEOMETRY',width,height,mini.window.tk.call('tk','scaling'))
    assert 280<=width<340 and 125<=height<205
    # Larger OS fonts/DPI may need more space; ordinary fonts must meet the
    # selected compact target as well as the old-footprint comparison.
    if mini._name_font.metrics('linespace')<=22 and sum(b.winfo_reqwidth() for b in (mini.toggle,mini.show_main))+16<=280:
        assert width<=300 and height<=150
    for button in (mini.toggle,mini.show_main):
        assert button.winfo_ismapped() and button.winfo_x()>=0
        assert button.winfo_rootx()+button.winfo_width()<=mini.window.winfo_rootx()+width
        assert button.winfo_rooty()+button.winfo_height()<=mini.window.winfo_rooty()+height
    assert mini.name.cget('text').endswith('…') and app.state['tasks'][0]['name']=='Long name '+'W'*300
    assert not hasattr(mini,'state_bar') and not mini.diagnostic.winfo_ismapped()
    mini.toggle.invoke()
    settled(app);assert app.state['active']['task_id']==a
    clock.value+=timedelta(minutes=1)
    mini.toggle.invoke();settled(app);assert app.state['active'] is None
    assert app.show_main() and app.mini is None


def test_real_tk_unverified_mini_navigation_retains_request_and_modal_owner(connected,monkeypatch):
    from chronicle.services import TimerService
    app,worker,clock=connected
    a=task(app);select(app,app.task_row(a));assert app.open_mini()
    mini=app.mini;app.keep_mini_open.set(True)
    execute=TimerService.execute;attempts=[]
    def uncertain(service,request):
        attempts.append(request)
        return Outcome('unverified',error=OSError('Injected indeterminate test write'))
    monkeypatch.setattr(TimerService,'execute',uncertain)
    before=evidence(worker);mini.toggle.invoke()
    pump(app.root,lambda:app.pending is not None and not app.executing)
    accepted=app.pending
    assert attempts==[accepted] and evidence(worker)==before
    assert 'Action needs review' in mini.diagnostic.cget('text')
    assert mini.toggle.instate(['disabled']) and mini.show_main.instate(['!disabled'])
    mini.show_main.invoke()
    assert app.root.state()=='normal' and app.mini is mini and app.pending is accepted
    assert app.retry_button.winfo_manager()=='pack' and not app.mini_toggle()
    assert evidence(worker)==before and attempts==[accepted]
    monkeypatch.setattr(TimerService,'execute',execute)
    assert app.retry();settled(app)
    assert app.state['active']['task_id']==a and mini.diagnostic.cget('text')==''
    assert mini.toggle.instate(['!disabled'])
    # The same retained Mini remains inert while an ordinary owned modal exists.
    assert app.add_date_only_work()
    pump(app.root,lambda:app.editor is not None and app.root.grab_current() is app.editor)
    grab=app.root.grab_current();before=evidence(worker)
    mini.render()
    assert mini.show_main.instate(['disabled']) and mini.toggle.instate(['disabled'])
    assert not bool(mini.window.attributes('-topmost'))
    assert not app.show_main() and not app.mini_toggle()
    assert app.root.grab_current() is grab and evidence(worker)==before
    app._close_editor(app.editor)


def test_real_tk_generated_ignored_targets_preserve_navigation_without_mutation(connected):
    from test_hierarchy_ui import child
    app,worker,clock=connected
    p=project(app);parent=task(app,group=p);child(app,parent,p)
    leaf=task(app);select(app,app.task_row(leaf))
    for row in (app.project_row(p),app.project_row(None),app.task_row(parent)):
        app.tree.see(row);pump(app.root,lambda:bool(app.tree.bbox(row)))
        x,y,w,h=app.tree.bbox(row);before=evidence(worker)
        for stamp in (1000,1100):
            app.tree.event_generate('<ButtonPress-1>',x=x+100,y=y+h//2,time=stamp)
            app.tree.event_generate('<ButtonRelease-1>',x=x+100,y=y+h//2,time=stamp+10)
        assert app.pending is None and app.state['active'] is None and evidence(worker)==before
    # Use actual theme hit testing to find a parent expansion indicator.
    row=app.task_row(parent);app.tree.see(row)
    pump(app.root,lambda:bool(app.tree.bbox(row)))
    x,y,w,h=app.tree.bbox(row);yy=y+h//2
    xx=next(i for i in range(x,x+w) if 'indicator' in app.tree.identify_element(i,yy).lower())
    opened=app.tree.item(row,'open');before=evidence(worker)
    app.tree.event_generate('<ButtonPress-1>',x=xx,y=yy,time=3000)
    app.tree.event_generate('<ButtonRelease-1>',x=xx,y=yy,time=3010)
    assert bool(app.tree.item(row,'open'))!=bool(opened)
    app._task_double_click(SimpleNamespace(widget=app.tree,x=xx,y=yy))
    assert app.pending is None and evidence(worker)==before
    # Coordinate regions come from Tk itself, not a fake or stale selection.
    for region in ('heading','nothing'):
        point=next(( (i,j) for j in range(app.tree.winfo_height()) for i in (10,100)
                     if app.tree.identify_region(i,j)==region ))
        assert app._task_double_click(SimpleNamespace(widget=app.tree,x=point[0],y=point[1])) is None
        assert app.pending is None and evidence(worker)==before
    from test_archived_items import archive
    archive(app,'task',leaf)
    assert next(t for t in app.state['tasks'] if t['task_id']==leaf)['effective_archived']
    # Model stale visible rows with real Treeview coordinates: one archived UUID
    # and one UUID absent from the authoritative snapshot.
    for key in (leaf,uid()):
        row=app.task_row(key)
        assert not app.tree.exists(row)
        app.tree.insert(app.project_row(None),'end',iid=row,text='Stale leaf')
        x,y=_row_point(app,key);before=evidence(worker)
        for stamp in (5000,5100):
            app.tree.event_generate('<ButtonPress-1>',x=x,y=y,time=stamp)
            app.tree.event_generate('<ButtonRelease-1>',x=x,y=y,time=stamp+10)
        assert app.pending is None and app.state['active'] is None and evidence(worker)==before
        app.tree.delete(row)
