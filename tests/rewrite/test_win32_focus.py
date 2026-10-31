"""Portable protocol faults; actual desktop acceptance is explicitly separate."""
from contextlib import nullcontext
import json
import os
import sys
import time
from types import SimpleNamespace

import pytest

import win32_focus as f


class Widget:
    def __init__(self, root=None, name='.'):
        self.root = root or self
        self.name = name
        self.alive = self.viewable = True
        self.focus_calls = 0
        if root is None:
            self.widgets = {'.': self}
            self.focus = None
        self.root.widgets[name] = self

    def __str__(self): return self.name
    def winfo_exists(self): return self.alive
    def winfo_viewable(self): return self.viewable
    def winfo_toplevel(self): return self.root
    def winfo_id(self): return 10
    def nametowidget(self, name): return self.root.widgets[name]
    def focus_get(self): return self.root.focus
    def focus_set(self): self.focus_calls += 1; self.root.focus = self
    def grab_current(self): return None


class API:
    def __init__(self, *, foreground=20, inserted=3, error=None, return_foreground=20):
        self.foreground, self.inserted = foreground, inserted
        self.error, self.return_foreground = error, return_foreground
        self.input = []
        self.unbound = []
        self.threads = []
        self.focus_inside = True
        self.confirm_error = None

    def bind_target(self, client): return dict(client=client, top=20, pid=1, thread=2)
    def inspect(self, target, deadline):
        import threading
        self.threads.append(threading.get_ident())
        if self.error: raise self.error
        return dict(monotonic=time.monotonic(), foreground=self.foreground, point=(50, 5))
    def confirm(self, target, value):
        if self.confirm_error: raise self.confirm_error
    def focus_state(self, target):
        return dict(foreground=self.return_foreground, focus_inside=self.focus_inside)
    def click(self, point, deadline): self.input.append(point); return self.inserted, 0
    def unbind_target(self, target): self.unbound.append(target)


def item(node, path=None):
    return SimpleNamespace(nodeid=node, path=path or f.REPO/node.split('::')[0],
                           session=SimpleNamespace(shouldstop=False))


def driver(api=None, node=None):
    node = node or next(iter(f.NODES))
    value = f.FocusPreconditionDriver.for_node(item(node), platform='win32', api=api or API())
    root = Widget(); widget = Widget(root, '.origin')
    value.attach(root)
    return value, root, widget


def run(value, widget, *, deadline=None):
    deadline = deadline or time.monotonic()+1
    while not value.prepare(widget, deadline):
        # Only portable test synchronization; the real fixture pumps Tk.
        time.sleep(.001)


@pytest.mark.parametrize('node', list(f.NODES))
def test_exact_six_nodes_and_source_authorization(node):
    assert len(f.NODES) == 6
    assert f.FocusPreconditionDriver.for_node(item(node), platform='win32', api=API()).node == node
    with pytest.raises(f.FocusBlocked, match='source'):
        f.FocusPreconditionDriver.for_node(item(node, f.REPO/'wrong.py'), platform='win32', api=API())
    assert f.FocusPreconditionDriver.for_node(item(node+'extra'), platform='win32', api=API()) is None
    assert f.FocusPreconditionDriver.for_node(item(node), platform='linux', api=API()) is None
    with pytest.raises(f.FocusBlocked, match='Unapproved'):
        f.FocusPreconditionDriver(node+'extra', f.REPO/node.split('::')[0], API())


def test_single_click_then_ordinary_focus_and_terminal_disarming():
    import threading
    api = API(foreground=99)
    value, root, widget = driver(api)
    run(value, widget)
    assert api.input == [(50, 5)] and widget.focus_calls == 1
    assert api.threads == [value.worker.ident] and api.threads[0] != threading.get_ident()
    assert value.state == 'DISARMED' and value.observe(widget)
    with pytest.raises(f.FocusBlocked, match='disarmed'):
        value.prepare(widget, time.monotonic()+1)
    assert len(api.input) == 1 and widget.focus_calls == 1
    value.close()


def test_already_ready_injects_nothing_and_does_not_set_focus():
    api = API(); value, root, widget = driver(api); root.focus = widget
    run(value, widget)
    assert not api.input and widget.focus_calls == 0
    assert value.observe(widget)


def test_queued_widget_mapping_uses_original_budget_without_early_input():
    value, root, widget = driver(API(foreground=99))
    widget.viewable = False
    deadline = time.monotonic()+1
    assert not value.prepare(widget, deadline)
    assert value.state == 'PREPARING' and value.target is None and not value.api.input
    widget.viewable = True
    run(value, widget, deadline=deadline)
    assert len(value.api.input) == 1


def test_unobservable_input_outcome_stops_qualification_without_retry():
    api = API(foreground=99)
    def unknown(point, deadline): api.input.append(point); raise OSError('controlled post-insertion failure')
    api.click = unknown
    value, root, widget = driver(api)
    with pytest.raises(f.FocusFailed, match='outcome unavailable'):
        run(value, widget)
    assert value.session.shouldstop and value.state == 'DISARMED' and len(api.input) == 1


@pytest.mark.parametrize('reason', ['locked', 'disconnected', 'noninteractive', 'obstructed',
                                   'disabled', 'not HTCAPTION', 'wrong PID/thread', 'same-PID top-level'])
def test_native_inspection_refusal_is_terminal_and_sends_nothing(reason):
    api = API(error=f.FocusBlocked(reason)); value, root, widget = driver(api)
    with pytest.raises(f.FocusBlocked, match=reason): run(value, widget)
    assert value.state == 'DISARMED' and not api.input and not widget.focus_calls


@pytest.mark.parametrize('damage', ['root_destroyed', 'widget_destroyed', 'widget_reused', 'root_reused', 'outside'])
def test_live_tk_object_identity_is_required(damage):
    value, root, widget = driver()
    if damage == 'root_destroyed': root.alive = False
    if damage == 'widget_destroyed': widget.alive = False
    if damage == 'widget_reused': Widget(root, '.origin')
    if damage == 'root_reused': root.widgets['.'] = Widget()
    if damage == 'outside': widget.root = Widget()
    with pytest.raises(f.FocusBlocked): run(value, widget)
    assert value.state == 'DISARMED' and not value.api.input


@pytest.mark.parametrize('foreground', [99, 21])
def test_wrong_foreground_cannot_pass_or_cause_another_click(foreground):
    api = API(foreground=99, return_foreground=foreground)
    value, root, widget = driver(api)
    deadline=time.monotonic()+2
    while not api.input:
        assert not value.prepare(widget, deadline)
        time.sleep(.001)
    with pytest.raises(f.FocusFailed, match='deadline'):
        value.prepare(widget, time.monotonic()-1)
    assert len(api.input) == 1 and widget.focus_calls == 0 and value.state == 'DISARMED'


@pytest.mark.parametrize('inserted', [0, 1, 2])
def test_refused_or_partial_input_never_retries_or_releases_foreign_buttons(inserted):
    api = API(foreground=99, inserted=inserted); value, root, widget = driver(api)
    with pytest.raises(f.FocusFailed, match='complete'): run(value, widget)
    assert len(api.input) == 1 and not widget.focus_calls and value.state == 'DISARMED'
    assert bool(value.session.shouldstop) == (inserted > 1)
    assert value.events[-2]['status'] == 'FAIL'


def test_stale_native_response_refuses_input():
    api = API(foreground=99)
    original = api.inspect
    def stale(*args):
        value = original(*args); value['monotonic'] -= 1; return value
    api.inspect = stale
    value, root, widget = driver(api)
    with pytest.raises(f.FocusBlocked, match='Stale'): run(value, widget)
    assert not api.input


def test_changed_target_before_input_refuses_without_retry():
    api = API(foreground=99); api.confirm_error = f.FocusBlocked('Input target changed')
    value, root, widget = driver(api)
    with pytest.raises(f.FocusBlocked, match='changed'): run(value, widget)
    assert not api.input and not widget.focus_calls


def test_result_is_read_only_even_when_return_focus_fails():
    api = API(foreground=99); value, root, widget = driver(api)
    run(value, widget); before = (len(api.input), widget.focus_calls)
    root.focus = root
    assert not value.observe(widget)
    api.return_foreground = 99
    assert not value.observe(root)
    assert (len(api.input), widget.focus_calls) == before


def test_deadline_exhaustion_and_late_observation_cannot_activate():
    import threading
    gate = threading.Event()
    api = API(foreground=99); original = api.inspect
    def slow(*args): gate.wait(1); return original(*args)
    api.inspect = slow
    value, root, widget = driver(api)
    try:
        assert not value.prepare(widget, time.monotonic()+2)
        with pytest.raises(f.FocusBlocked, match='deadline'):
            value.prepare(widget, time.monotonic()-1)
        assert value.state == 'DISARMED' and not api.input
        with pytest.raises(f.FocusBlocked, match='still active'): value.close()
        assert value.session.shouldstop
    finally:
        gate.set(); value.worker.join(1)
    assert not api.input


@pytest.mark.parametrize('key', [1, 2, 4, 5, 6, 0x10, 0x11, 0x12, 0x5b, 0x5c])
def test_native_adapter_refuses_held_buttons_and_modifiers(key):
    api = object.__new__(f.Win32API)
    api.user = SimpleNamespace(GetAsyncKeyState=lambda value: 0x8000 if value == key else 0)
    with pytest.raises(f.FocusBlocked, match='already held'): api.keys()


@pytest.mark.parametrize('damage', ['destroyed', 'reused', 'owner', 'ancestor'])
def test_native_identity_marker_refuses_handle_reuse(damage):
    api = object.__new__(f.Win32API)
    api.user = SimpleNamespace(IsWindow=lambda h: damage != 'destroyed',
        GetPropW=lambda h, n: 0 if damage == 'reused' else 50,
        GetAncestor=lambda h, flag: 21 if damage == 'ancestor' else 20)
    api.owner = lambda h: (9, 2) if damage == 'owner' else (1, 2)
    with pytest.raises(f.FocusBlocked):
        api.marker(dict(client=10, top=20, pid=1, thread=2, property='owned', token=50))


def test_observer_keeps_primary_when_root_and_secondary_diagnostics_fail(monkeypatch):
    import tk_observation as o
    import test_app
    primary = AssertionError('original modal return failure')
    class Root:
        alive = True
        def winfo_exists(self): return self.alive
        def bind(self, *args, **kw): return 'token'
        def unbind(self, *args): raise RuntimeError('unbind secondary')
    root = Root()
    monkeypatch.setattr(o, 'snapshot', lambda *args: {} if root.alive else (_ for _ in ()).throw(RuntimeError('snapshot secondary')))
    def broken(*args, **kw): root.alive = False; raise primary
    monkeypatch.setattr(test_app, 'pump', broken)
    with pytest.raises(AssertionError) as failure:
        o.wait_observed(root, lambda: False, phase='History actual return focus')
    assert failure.value is primary
    assert any('snapshot secondary' in note for note in primary.__notes__)
    assert any('unbind secondary' in note for note in primary.__notes__)


def test_snapshot_never_queries_native_foreground_after_root_destruction(monkeypatch):
    import tkinter as tk
    import tk_observation as o
    class Dead:
        def winfo_exists(self): return 0
        def __getattr__(self, name):
            return lambda *a: (_ for _ in ()).throw(tk.TclError('destroyed'))
    calls = []
    monkeypatch.setattr(o.sys, 'platform', 'win32')
    monkeypatch.setattr(o, 'windows_foreground', lambda root: calls.append(root))
    result = o.snapshot(Dead())
    assert not calls and result['observation_errors']


def test_observation_uncertainty_cannot_pass(monkeypatch):
    import tk_observation as o
    import test_app
    root = SimpleNamespace(bind=lambda *a, **k: 'token', unbind=lambda *a: None)
    monkeypatch.setattr(o, 'snapshot', lambda *a: {'observation_errors': ['native unavailable']})
    monkeypatch.setattr(test_app, 'pump', lambda *a, **kw: None)
    with pytest.raises(RuntimeError, match='observation'):
        o.wait_observed(root, lambda: True, phase='RESULT')


def test_observer_shares_deadline_and_never_prepares_during_result(monkeypatch):
    import tk_observation as o
    import test_app
    now = [0.0]
    prepared, budgets, disarms = [], [], []
    node = next(iter(f.NODES))
    native = SimpleNamespace(node=node, sent=False,
        prepare=lambda widget, deadline: prepared.append(deadline) or True,
        observe=lambda widget: True, disarm=lambda: disarms.append(True), evidence=lambda: {})
    root = SimpleNamespace(_f2_focus_driver=native, bind=lambda *a, **kw: 'token', unbind=lambda *a: None)
    monkeypatch.setattr(o.time, 'monotonic', lambda: now[0])
    def snapshot(*args): now[0] += 2; return {}
    monkeypatch.setattr(o, 'snapshot', snapshot)
    def pump(root, predicate, timeout): budgets.append(timeout); assert predicate()
    monkeypatch.setattr(test_app, 'pump', pump)
    o.wait_observed(root, lambda: True, phase=f.NODES[node][0], widgets=(object(),), foreground=True)
    assert prepared == [8.0] and budgets == [6000] and disarms == [True]
    o.wait_observed(root, lambda: True, phase=f.NODES[node][1], widgets=(object(),))
    assert prepared == [8.0] and disarms == [True]


def test_native_hit_test_never_runs_on_the_tk_thread():
    api = object.__new__(f.Win32API)
    api.kernel = SimpleNamespace(GetCurrentThreadId=lambda: 12)
    with pytest.raises(f.FocusBlocked, match='input queue'):
        api.inspect({'thread': 12}, time.monotonic()+1)
    # Enumeration must also count invisible windows: they cannot make the
    # immediate pre-input confirmation iterate without its explicit cap.
    seen=[]
    api.ENUM=lambda callback: callback
    def enumerate_windows(callback, unused):
        for hwnd in range(1000):
            seen.append(hwnd)
            if not callback(hwnd, 0):break
        return 0
    api.user=SimpleNamespace(EnumWindows=enumerate_windows, IsWindowVisible=lambda hwnd: False)
    with pytest.raises(f.FocusBlocked, match='safety bound'):
        api.competing({'top': 20}, (50, 5))
    assert len(seen)==257


@pytest.mark.parametrize('caption_answer', [0, 1, 2, 3, 8, 9, 20])
def test_native_inspection_requires_bounded_caption_hit_on_separate_queue(caption_answer):
    import ctypes
    api = object.__new__(f.Win32API)
    messages = []
    api.kernel = SimpleNamespace(GetCurrentThreadId=lambda: 3)
    api.dpi = nullcontext
    api.marker = lambda t: None
    api.session = lambda: {'session_id': 7}
    api.desktop = lambda tid: {'input_desktop': 'Default'}
    api.keys = lambda: None
    api.gui = lambda *a: SimpleNamespace(capture=0)
    api.geometry = lambda t: (20, 20, 970, 620)
    api.owner = lambda h: (99, 9)
    api.competing = lambda target, point: []
    api.c = SimpleNamespace(byref=lambda v: v, sizeof=lambda v: 4,
        c_size_t=lambda: SimpleNamespace(value=0),
        create_unicode_buffer=lambda n: ctypes.create_unicode_buffer('ConsoleWindowClass', n))
    api.w = SimpleNamespace(DWORD=lambda: SimpleNamespace(value=0),
        POINT=lambda x, y: SimpleNamespace(x=x, y=y))
    def screen(hwnd, point): point.y = 60; return 1
    def hit(hwnd, message, wp, lp, flags, timeout, answer):
        messages.append((message, flags, timeout))
        answer.value = caption_answer
        return 1
    api.user = SimpleNamespace(GetForegroundWindow=lambda: 99, GetClassNameW=lambda *a: 1,
        ClientToScreen=screen, WindowFromPoint=lambda p: 20, SendMessageTimeoutW=hit)
    api.dwm = SimpleNamespace(DwmGetWindowAttribute=lambda *a: 0)
    target = dict(thread=2, top=20, client=10, pid=1)
    if caption_answer == 2:
        assert api.inspect(target, time.monotonic()+1)['point'] == (495, 40)
    else:
        with pytest.raises(f.FocusBlocked, match='HTCAPTION'):
            api.inspect(target, time.monotonic()+1)
    assert len(messages) == 1 and messages[0][0] == 0x84 and 0 < messages[0][2] <= 50


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows foreground/return controls NOT RUN')
@pytest.mark.parametrize('failed_return', [False, True])
def test_native_ordinary_activation_and_independent_modal_return_control(tmp_path, failed_return):
    """Run an original authorized node, never grant this control activation rights.

    A disposable foreign Tk window is presented normally to establish real
    background origin. If Windows does not activate it, this control fails;
    no force-foreground API or fabricated observation is substituted.
    """
    import threading
    sys.path.insert(0, str(f.REPO/'scripts'))
    import qualification_pytest as q
    plugin = tmp_path/'native_focus_control.py'
    evidence = tmp_path/'native-control.json'
    plugin.write_text('''
import json, os, subprocess, sys, time
from pathlib import Path
import pytest
@pytest.fixture(autouse=True)
def controlled_origin(root, monkeypatch, request):
    driver=root._f2_focus_driver
    original=driver.api.inspect
    children=[]
    def inspect(target, deadline):
        child=subprocess.Popen([sys.executable,'-B','-c',
            "import tkinter as t; r=t.Tk(); r.title('F2 owned inert control'); "
            "r.geometry('240x120+1000+650'); r.after(15000,r.destroy); r.mainloop()"],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        children.append(child)
        until=min(deadline,time.monotonic()+2)
        while time.monotonic()<until:
            hwnd=driver.api.user.GetForegroundWindow()
            if hwnd and driver.api.owner(hwnd)[0]==child.pid:break
            time.sleep(.01)
        else:raise RuntimeError('Native control could not establish real foreign foreground through ordinary presentation')
        return original(target,deadline)
    monkeypatch.setattr(driver.api,'inspect',inspect)
    if os.environ['F2_CONTROL_FAILED_RETURN']=='1':
        from chronicle.history_window import HistoryWindow
        close=HistoryWindow.close
        def wrong_return(view):
            close(view)
            root.focus_set() # Deliberate real return defect, outside the driver.
        monkeypatch.setattr(HistoryWindow,'close',wrong_return)
    try:yield
    finally:
        Path(os.environ['F2_CONTROL_EVIDENCE']).write_text(json.dumps(driver.evidence()),encoding='utf-8')
        for child in children:
            if child.poll() is None:child.terminate()
            child.wait(timeout=5)
''', encoding='utf-8')
    node = f.HISTORY+'::test_real_tk_history_parent_grab_focus_return_identity_and_guard[none]'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               PYTHONPATH=os.pathsep.join([str(tmp_path), str(f.REPO/'src'), str(f.REPO/'tests/rewrite')]),
               F2_CONTROL_EVIDENCE=str(evidence), F2_CONTROL_FAILED_RETURN='1' if failed_return else '0')
    env.pop('PYTEST_ADDOPTS', None); env.pop('PYTEST_PLUGINS', None)
    profile=tmp_path/'profile';profile.mkdir()
    env.update(HOME=str(profile),USERPROFILE=str(profile),LOCALAPPDATA=str(profile))
    child = q.WindowsChild([sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        '-p', 'native_focus_control', '-o', 'addopts=', '--capture=tee-sys', node,
        '--basetemp', str(tmp_path/'child-temp'), '--junitxml', str(tmp_path/'native.xml')], f.REPO, env)
    streams = {}
    def drain(name, stream): streams[name] = stream.read()
    threads = [threading.Thread(target=drain, args=(n,s), daemon=True)
               for n,s in (('stdout',child.stdout),('stderr',child.stderr))]
    for thread in threads: thread.start()
    cleanup_verified = False
    try:
        deadline = time.monotonic()+45
        while child.poll() is None and time.monotonic()<deadline:time.sleep(.01)
        code=child.poll()
        assert code is not None, 'Bounded native control timed out'
    finally:
        if child.active_count():child.terminate_owned()
        deadline=time.monotonic()+5
        while child.active_count() and time.monotonic()<deadline:time.sleep(.01)
        cleanup_verified=child.active_count()==0
        for thread in threads:thread.join(timeout=max(0,deadline-time.monotonic()))
        child.close()
        for name,data in streams.items():(tmp_path/(name+'.bin')).write_bytes(data)
    assert cleanup_verified and all(not t.is_alive() for t in threads)
    assert set(streams)=={'stdout','stderr'}
    assert code == (1 if failed_return else 0), streams
    record=json.loads(evidence.read_text(encoding='utf-8'))
    assert record['precondition_verified'] and record['state']=='DISARMED'
    inputs=[event for event in record['events'] if event['event']=='SendInput']
    assert len(inputs)==1 and inputs[0]['inserted']==3
    disarmed=next(i for i,e in enumerate(record['events']) if e['event']=='disarmed')
    assert not any(e['event'] in ('SendInput','ordinary_Tk_focus_set') for e in record['events'][disarmed+1:])
    if failed_return:assert b'observation failed during RESULT' in streams['stdout']
