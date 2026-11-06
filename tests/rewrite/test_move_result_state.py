"""Move owner/state fault boundary, separate from destination/business rules.

Connected controls use real Tk and the existing serialized C2 SQLite bridge.
Explicit synthetic deliveries below prove owner-state handling, not SQL rollback.
"""
from contextlib import closing
from dataclasses import replace
from threading import Event
from types import SimpleNamespace
import pytest

from chronicle.move_window import MoveWindow
from chronicle.records import Outcome,canonical
from chronicle.worker import Message
from chronicle import project_ui as ui
from schema4_cases import adapter
from test_app import root, pump
from test_backup_restore import logical
from test_main_explorer import settled
from test_schema4_project_modal import connected_candidate, project, task, moving


@pytest.fixture(params=['project','task'])
def move_case(connected_candidate,request):
    app,w,clock=connected_candidate
    p=project(app);q=project(app)
    key=p if request.param=='project' else task(app,p)
    d=moving(app,request.param,key,ui.project_row(q))
    return app,w,d,key,q


def fail(error):
    def throw(*args,**kwargs):raise error
    return throw


@pytest.mark.parametrize('status,phase',[
    ('committed','complete'),('unchanged','complete'),('rejected','failed'),
    ('rolled_back','failed'),('unavailable','failed'),('unverified','unverified')])
def test_accept_result_state_requires_only_plain_python_assignments(status,phase):
    value=SimpleNamespace()
    result=Outcome(status)
    MoveWindow.accept_result_state(value,result)
    assert vars(value)==dict(outcome=result,phase=phase)


@pytest.mark.parametrize('where',['record_result','status widget','controls','unrelated notification','secondary controls','secondary diagnostic'])
def test_real_committed_move_survives_presentation_fault_and_normal_close(move_case,monkeypatch,capsys,where):
    app,w,d,key,destination=move_case
    before=logical(w.adapter.path);primary=ValueError('Original Move presentation fault')
    secondary=RuntimeError('Secondary Move presentation fault')
    d.close_button.focus_set();pump(app.root,lambda:app.root.focus_get() is d.close_button)
    original_controls=d.controls
    def presentation(result):
        assert d.outcome is result and d.phase=='complete'
        raise primary
    if where in ('record_result','secondary controls','secondary diagnostic'):
        monkeypatch.setattr(d,'record_result',presentation)
    if where=='status widget':monkeypatch.setattr(d.status,'configure',fail(primary))
    if where in ('controls','secondary controls'):
        def controls():
            if d.phase=='complete':raise primary if where=='controls' else secondary
            return original_controls()
        monkeypatch.setattr(d,'controls',controls)
    if where=='unrelated notification':monkeypatch.setattr(app,'_template_result',fail(primary))
    diagnostics=[]
    if where=='secondary diagnostic':
        def diagnostic(error):diagnostics.append(error);raise secondary
        monkeypatch.setattr(app,'_diagnose',diagnostic)
    assert d.submit();accepted=app.pending;token=app._pending_token
    settled(app)
    assert app._mutation_outcome.status=='committed' and d.outcome is app._mutation_outcome
    assert d.phase=='complete' and d.request is accepted and d.token==token
    assert app.pending is None and app._move_submission is None
    assert app.root.grab_current() is d.window and d.window.grab_status()=='local'
    assert app.root.focus_get() is d.close_button
    errors=diagnostics+[args[1] for args in app.root.test_errors]
    assert primary in errors
    if where=='secondary controls':assert any('Secondary Move presentation fault' in n for n in primary.__notes__)
    if where=='secondary diagnostic':assert 'Original Move presentation fault' in capsys.readouterr().err
    after=logical(w.adapter.path)
    assert len(after['committed_requests'])==len(before['committed_requests'])+1
    with closing(w.adapter.connect(readonly=True)) as c:
        row=c.execute('SELECT request_bytes,result_bytes FROM committed_requests WHERE request_id=?',(accepted.request_id,)).fetchall()
    assert len(row)==1 and row[0][0]==accepted.content() and row[0][1]==canonical(d.outcome.result)
    assert sum(m.kind=='mutate' and m.value is accepted for _,m in w.handled)==1
    facts=app.state['projects'] if accepted.operation=='move_project_subtree' else app.state['tasks']
    field='project_id' if accepted.operation=='move_project_subtree' else 'task_id'
    relationship='parent_project_id' if accepted.operation=='move_project_subtree' else 'project_id'
    assert next(r for r in facts if r[field]==key)[relationship]==destination
    # Restore deliberately damaged widget methods, then use existing controls and
    # the actual Close button. No forced close/grab release or replacement widget.
    if where not in ('controls','secondary controls'):
        assert d.close_button.instate(['!disabled'])
    monkeypatch.undo()
    if where in ('controls','secondary controls'):d.controls()
    assert d.close_button.instate(['!disabled'])
    d.close_button.invoke()
    assert d.disposed and app.movement is None and app.root.grab_current() is None
    assert logical(w.adapter.path)==after
    project(app,name='Subsequent worker message')
    assert app._mutation_outcome.status=='committed' and app._drain_id is not None


@pytest.mark.parametrize('status,phase',[
    ('unchanged','complete'),('rejected','failed'),('rolled_back','failed'),('unverified','unverified')])
def test_real_widgets_settle_terminal_and_unverified_delivery_before_presentation(move_case,monkeypatch,status,phase):
    """Controlled delivery, not a claim that a mocked outcome proves a SQL commit."""
    app,w,d,key,destination=move_case
    before=logical(w.adapter.path);sent=[];put=w.requests.put
    def hold(message):
        if message.kind=='mutate':sent.append(message)
        else:put(message)
    monkeypatch.setattr(w.requests,'put',hold)
    primary=ValueError('Move status presentation failed')
    monkeypatch.setattr(d,'record_result',fail(primary))
    assert d.submit();accepted=app.pending;token=app._pending_token
    assert len(sent)==1 and sent[0].value is accepted
    result=Outcome(status)
    app._handle(Message('mutate',token,result,accepted))
    assert app._mutation_outcome is result and d.outcome is result and d.phase==phase
    assert d.request is accepted and d.token==token
    assert any(args[1] is primary for args in app.root.test_errors)
    assert app.root.grab_current() is d.window and logical(w.adapter.path)==before
    if status=='unverified':
        assert app.pending is accepted and app._move_submission.request is accepted
        assert not d.close() and d.close_button.instate(['disabled'])
        assert not app.can_mutate() and not d.submit()
        # Reconcile the very same previously undelivered request through the real
        # bridge: independent absence, then the actual C2 transaction and receipt.
        monkeypatch.setattr(w.requests,'put',put)
        assert d.retry();assert app.pending is accepted and app._pending_token!=token
        settled(app)
        assert d.phase=='complete' and d.outcome.status=='committed' and d.request is accepted
        assert len(logical(w.adapter.path)['committed_requests'])==len(before['committed_requests'])+1
    else:
        assert app.pending is None and app._move_submission is None
        assert logical(w.adapter.path)==before
    assert d.close() and app.root.grab_current() is None


@pytest.mark.parametrize('interruption',['stale token','equal different request','destroyed original'])
def test_real_move_exact_delivery_identity_destroyed_owner_and_newer_dialog(move_case,monkeypatch,interruption):
    app,w,d,key,destination=move_case
    entered=Event();release=Event()
    def checkpoint(stage,c):
        if stage=='before_commit':entered.set();assert release.wait(8)
    w.adapter.checkpoint=checkpoint
    assert d.submit();accepted=app.pending;token=app._pending_token
    try:
        pump(app.root,entered.is_set)
        if interruption=='destroyed original':
            d.window.destroy();assert d.disposed and app.movement is None
        else:
            delivered=replace(accepted) if interruption=='equal different request' else accepted
            assert delivered==accepted
            app._handle(Message('mutate',token-1 if interruption=='stale token' else token,Outcome('committed',{}),delivered))
            assert app.pending is accepted and app.executing and d.phase=='executing' and d.outcome is None
            # Check the private correlation boundary too, independently of _handle.
            app._move_result(delivered,token-1 if interruption=='stale token' else token,Outcome('committed',{}))
            assert d.phase=='executing' and app._move_submission.outcome is None
    finally:release.set()
    settled(app);assert app._mutation_outcome.status=='committed'
    if not d.disposed:assert d.close()
    original=app._mutation_outcome;before=logical(w.adapter.path)
    newer=moving(app,'project' if accepted.operation=='move_project_subtree' else 'task',key,'group:root' if accepted.operation=='move_project_subtree' else ui.UNASSIGNED)
    newer_state=(newer.phase,newer.outcome,newer.request)
    app._handle(Message('mutate',token,Outcome('rejected'),accepted))
    app._move_result(accepted,token,Outcome('rejected'))
    assert app._mutation_outcome is original and (newer.phase,newer.outcome,newer.request)==newer_state
    assert app.root.grab_current() is newer.window and logical(w.adapter.path)==before
    put=w.requests.put;sent=[]
    def hold(message):
        if message.kind=='mutate':sent.append(message)
        else:put(message)
    monkeypatch.setattr(w.requests,'put',hold)
    assert newer.submit();new_request=app.pending;new_token=app._pending_token
    app._handle(Message('mutate',token,Outcome('rejected'),accepted))
    app._move_result(accepted,token,Outcome('rejected'))
    assert app.pending is new_request and app.executing and app._pending_token==new_token
    assert app._move_submission.request is new_request and newer.phase=='executing' and newer.outcome is None
    assert logical(w.adapter.path)==before and len(sent)==1
    put(sent[0]);settled(app)
    assert newer.phase=='complete' and newer.outcome.status=='committed' and newer.close()


@pytest.mark.parametrize('mode',['unchanged','rejected'])
def test_real_backend_noncommit_remains_closable_after_presentation_failure(move_case,monkeypatch,mode):
    app,w,d,key,destination=move_case
    if mode=='unchanged':
        target='group:root' if d.operation=='move_project_subtree' else ui.project_row(next(t for t in app.state['tasks'] if t['task_id']==key)['project_id'])
        d.tree.selection_set(target);d.selected()
    else:
        # A serialized real rename establishes a stale reviewed version.
        from chronicle.records import Request
        from schema4_cases import uid,NOW
        op='rename_project' if d.operation=='move_project_subtree' else 'rename_task'
        field='project_id' if d.operation=='move_project_subtree' else 'task_id'
        r=Request.make(uid(),app.dataset_id,op,NOW,**{field:key,'expected_version':1,'name':'Changed review'})
        ready=Event();put=w.results.put
        def delivered(message):
            put(message)
            if message.request is r:ready.set()
        monkeypatch.setattr(w.results,'put',delivered)
        w.requests.put(Message('mutate',998,r))
        pump(app.root,ready.is_set)
    before=logical(w.adapter.path)
    monkeypatch.setattr(d,'record_result',fail(ValueError('Terminal result presentation failed')))
    assert d.submit();settled(app)
    assert d.outcome.status==mode and d.phase==('complete' if mode=='unchanged' else 'failed')
    assert logical(w.adapter.path)==before and d.close()
