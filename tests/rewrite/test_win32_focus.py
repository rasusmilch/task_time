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


@pytest.mark.parametrize('initial_foreground,logical_cached', [(99, False), (20, True)])
def test_native_focus_can_enter_client_only_after_ordinary_tk_request(monkeypatch, initial_foreground, logical_cached):
    api = API(foreground=initial_foreground, return_foreground=initial_foreground)
    api.focus_inside = False
    value, root, widget = driver(api)
    if logical_cached:root.focus = widget
    events = []
    click = api.click
    sample = api.focus_state
    def activate(point, deadline):
        result = click(point, deadline)
        api.return_foreground = 20
        events.append('activated')
        return result
    def native(target):
        state = sample(target)
        events.append(('native', state['foreground'], state['focus_inside']))
        return state
    def focus():
        assert api.return_foreground == 20 and not api.focus_inside
        events.append('tk_request')
        Widget.focus_set(widget)
        api.focus_inside = True
    monkeypatch.setattr(api, 'click', activate)
    monkeypatch.setattr(api, 'focus_state', native)
    monkeypatch.setattr(widget, 'focus_set', focus)
    deadline = time.monotonic()+2
    assert not value.prepare(widget, deadline)
    value.worker.join(timeout=1)
    assert not value.worker.is_alive()
    assert value.prepare(widget, deadline)
    request = events.index('tk_request')
    assert ('native', 20, False) in events[:request]
    assert ('native', 20, True) in events[request+1:]
    assert len(api.input) == (1 if initial_foreground != 20 else 0)
    assert widget.focus_calls == 1 and root.focus_get() is widget
    assert value.verified and value.state == 'DISARMED'
    assert value.observe(widget)
    before = (len(api.input), widget.focus_calls)
    with pytest.raises(f.FocusBlocked, match='disarmed'):
        value.prepare(widget, time.monotonic()+2)
    assert (len(api.input), widget.focus_calls) == before
    value.close()


@pytest.mark.parametrize('missing', ['native', 'logical', 'foreground'])
def test_focus_request_does_not_pass_until_both_postconditions_hold(monkeypatch, missing):
    api = API(foreground=99, return_foreground=99)
    api.focus_inside = False
    value, root, widget = driver(api)
    click = api.click
    def activate(point, deadline):
        result = click(point, deadline)
        api.return_foreground = 20
        return result
    def focus():
        assert api.return_foreground == 20
        widget.focus_calls += 1
        if missing != 'logical':root.focus = widget
        api.focus_inside = missing != 'native'
        if missing == 'foreground':api.return_foreground = 21
    monkeypatch.setattr(api, 'click', activate)
    monkeypatch.setattr(widget, 'focus_set', focus)
    deadline = time.monotonic()+2
    assert not value.prepare(widget, deadline)
    value.worker.join(timeout=1)
    assert not value.worker.is_alive()
    assert not value.prepare(widget, deadline)
    assert value.focus_called and widget.focus_calls == 1 and len(api.input) == 1
    assert not value.verified and value.state == 'PREPARING'
    assert not value.prepare(widget, deadline)  # Another pump cannot retry either operation.
    with pytest.raises(f.FocusFailed, match='deadline'):
        value.prepare(widget, time.monotonic()-1)
    assert value.state == 'DISARMED' and not value.verified
    api.return_foreground = 20; api.focus_inside = True; root.focus = widget
    with pytest.raises(f.FocusBlocked, match='disarmed'):
        value.prepare(widget, time.monotonic()+2)
    assert widget.focus_calls == 1 and len(api.input) == 1
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
    # snapshot() is not the only platform boundary: ready() also observes
    # foreground ownership on Windows. This root deliberately has no HWND.
    monkeypatch.setattr(o, 'windows_foreground', lambda observed: dict(
        client_hwnd=10, root_hwnd=20, hwnd=20, pid=1, owned=True,
        root_is_foreground=observed is root, observation_error=None))
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


# The following helpers are private to this test fixture. They do not change
# subject-driver authority, WindowsChild, or any qualification implementation.
def _executable(path):
    from pathlib import Path
    import hashlib
    f.require(isinstance(path, str) and os.path.isabs(path), 'Missing/relative Python executable')
    value = Path(path).resolve(strict=True)
    f.require(value.is_file() and os.access(value, os.X_OK), 'Python executable is not executable')
    before = value.stat(); digest = hashlib.sha256(value.read_bytes()).hexdigest(); after = value.stat()
    f.require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
              (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Python executable changed while inspected')
    return dict(path=os.path.normcase(str(value)), sha256=digest, bytes=after.st_size)


def _python_facts():
    from pathlib import Path
    import hashlib
    cfg = Path(sys.prefix)/'pyvenv.cfg'
    venv_cfg = None
    if sys.prefix != sys.base_prefix:
        venv_cfg = dict(path=str(cfg))
        try:venv_cfg['sha256'] = hashlib.sha256(cfg.read_bytes()).hexdigest()
        except OSError as exc:venv_cfg['error'] = repr(exc)
    return dict(executable=sys.executable, base_executable=getattr(sys, '_base_executable', None),
        prefix=sys.prefix, base_prefix=sys.base_prefix, implementation=sys.implementation.name,
        version=sys.version, version_info=list(sys.version_info[:3]), frozen=bool(getattr(sys, 'frozen', False)),
        venv_cfg=venv_cfg)


def _control_python(env, *, facts=None, platform=None, image=None):
    """CPython multiprocessing's Windows venv launch mechanism; no discovery."""
    facts = _python_facts() if facts is None else facts
    platform = sys.platform if platform is None else platform
    executable = _executable(facts['executable'])
    selected, child_env = facts['executable'], dict(env)
    if platform == 'win32':
        f.require(facts['implementation'] == 'cpython' and not facts['frozen'] and
                  facts['version_info'] >= [3, 11, 0], 'Unsupported native-control Python runtime')
        base = _executable(facts['base_executable'])
        different = os.path.normcase(facts['executable']) != os.path.normcase(facts['base_executable'])
        venv = facts['prefix'] != facts['base_prefix']
        f.require(not different or venv, 'Unexpected base executable outside a CPython venv')
        if different:
            f.require(facts['venv_cfg'] is not None and 'sha256' in facts['venv_cfg'], 'Missing CPython virtual-environment identity')
            selected = facts['base_executable']
            child_env['__PYVENV_LAUNCHER__'] = facts['executable']
        else:
            f.require(not venv, 'Unsupported venv without a distinct environment executable')
            f.require('__PYVENV_LAUNCHER__' not in child_env, 'Unexpected inherited Python launcher binding')
        if image is None:image = _process_stamp(f.Win32API(), os.getpid())['image']
        f.require(_executable(image) == base, 'Base executable differs from the actual native Python image')
    return selected, child_env, dict(python=facts, image=_executable(selected), environment_executable=executable)


def _runtime_dependencies():
    import importlib
    import importlib.metadata as metadata
    result = {}
    for name in ('pytest', 'tzdata', 'tkcalendar', 'tzlocal'):
        try:
            module = importlib.import_module(name)
            result[name] = dict(version=metadata.version(name), module_version=getattr(module, '__version__', None),
                                origin=os.path.normcase(os.path.realpath(module.__file__)))
        except Exception as exc:result[name] = dict(error=repr(exc))
    return result


def _runtime_observation(api, deadline, node):
    from pathlib import Path
    import hashlib
    import subprocess
    observed = dict(pid=os.getpid(), node=node, argv=sys.argv, errors={})
    for key, read in (
        ('python', _python_facts), ('process', lambda:_process_stamp(api, os.getpid())),
        ('dependencies', _runtime_dependencies),
        ('chronicle', lambda:os.path.normcase(os.path.realpath(__import__('chronicle').__file__))),
        ('revision', lambda:subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=f.REPO, text=True,
            timeout=max(.001, deadline-time.monotonic())).strip()),
        ('files', lambda:{str(p.relative_to(f.REPO)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (Path(__file__).resolve(), Path(f.__file__).resolve())})):
        try:
            f.require(time.monotonic() < deadline, 'Runtime probe deadline exhausted')
            observed[key] = read()
        except Exception as exc:observed['errors'][key] = repr(exc)
    return observed


def _verify_runtime(observed, expected, *, node, pid=None, creation=None, membership=None):
    f.require(not observed.get('errors'), 'Runtime observations incomplete: '+repr(observed.get('errors')))
    f.require(observed['python'] == expected['python'], 'Python/virtual-environment identity differs')
    f.require(_executable(observed['process']['image']) == expected['image'], 'Unexpected native executable identity')
    f.require(observed['process']['live'] is True and observed['pid'] == observed['process']['pid'], 'Runtime process is not live/exact')
    if pid is not None:f.require(observed['pid'] == pid, 'Launched PID differs from actual runtime PID')
    if creation is not None:f.require(observed['process']['creation'] == creation, 'Runtime process creation identity differs')
    if membership is not None:
        f.require(membership['pid'] == observed['pid'] and membership['creation'] == observed['process']['creation']
                  and membership['live'] is True and membership['member'] is True, 'Runtime outside exact owned Job')
        f.require(_executable(membership['image']) == expected['image'], 'Independent native image differs')
    deps = observed['dependencies']
    f.require(deps == expected['dependencies'] and set(deps) == {'pytest','tzdata','tkcalendar','tzlocal'}
              and all('error' not in value for value in deps.values())
              and deps['tzdata']['version'] == deps['tzdata']['module_version'] == '2026.5'
              and deps['pytest']['version'] == deps['pytest']['module_version']
              and int(deps['pytest']['version'].split('.')[0]) >= 8, 'Required pytest/tzdata environment unavailable or different')
    f.require(observed['node'] == node, 'Wrong runtime test identity')
    f.require(observed['revision'] == expected['source']['revision'] and observed['files'] == expected['source']['files'],
              'Runtime source identity differs')
    f.require(observed['chronicle'] == os.path.normcase(str((f.REPO/'src/chronicle/__init__.py').resolve())),
              'Runtime imported another Chronicle source')
    f.require(_executable(observed['python']['executable']) == expected['environment_executable'],
              'Environment executable identity changed')
    return True


def _runtime_probe(directory, role, api, config, deadline, node):
    record = dict(nonce=config['nonce'], role=role, verified=False, observed=None, utc=_utc())
    primary = None
    try:
        record['observed'] = _runtime_observation(api, deadline, node)
        _verify_runtime(record['observed'], config['runtime'], node=node)
        f.require(time.monotonic() < deadline, 'Runtime probe exceeded original deadline')
        record['verified'] = True
    except BaseException as exc:
        primary = exc; record['error'] = repr(exc); raise
    finally:
        try:_control_write(directory, role+'-runtime', record)
        except BaseException as exc:
            if primary is None:raise
            primary.add_note('Runtime diagnostic also failed: '+repr(exc))
    return record


def _accept_runtime(record, expected, nonce, role, node, launch, membership, target):
    f.require(record is not None and record.get('verified') is True and record.get('nonce') == nonce
              and record.get('role') == role, 'Missing/exact runtime probe: '+role)
    _verify_runtime(record['observed'], expected, node=node, pid=launch['pid'],
                    creation=launch['creation'], membership=membership)
    f.require(record['observed']['pid'] == target['pid'], 'Runtime/Tk HWND owner differs')


def _control_write(directory, name, value):
    from pathlib import Path
    directory = Path(directory)
    payload = json.dumps(value, ensure_ascii=True, allow_nan=False).encode('utf-8')
    with (directory/(name+'.json')).open('xb') as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    # Readers never parse an in-progress JSON write. Both names are exclusive.
    with (directory/(name+'.done')).open('xb'):
        pass


def _control_read(directory, name):
    from pathlib import Path
    directory = Path(directory)
    if not (directory/(name+'.done')).exists():return None
    data = (directory/(name+'.json')).read_bytes()
    f.require(len(data) <= 262144, 'Control record exceeds diagnostic bound')
    value = json.loads(data)
    f.require(isinstance(value, dict), 'Malformed control record')
    return value


def _control_wait(directory, name, nonce, deadline, child, *, clock=time.monotonic, sleep=time.sleep):
    while clock() < deadline:
        code = child.poll()
        f.require(code is None, f'Inert child exited before {name}: {code}')
        error = _control_read(directory, 'inert-error')
        if error:
            f.require(error.get('nonce') == nonce, 'Wrong error-record nonce')
            raise f.FocusFailed('Inert setup failed: '+error.get('error', 'unknown'),
                                unsafe_input=error.get('unsafe_input', False))
        value = _control_read(directory, name)
        if value is not None:
            f.require(value.get('nonce') == nonce, 'Wrong control-record nonce')
            return value
        sleep(min(.005, max(0, deadline-clock())))
    raise f.FocusBlocked('Control setup deadline exhausted waiting for '+name)


def _launch_control(directory, nonce, command, context, started, cwd, stamp, *, env=None):
    from pathlib import Path
    import subprocess
    directory = Path(directory)
    launch = dict(nonce=nonce, command=command, cwd=str(cwd), utc=_utc(), started=started, pid=None,
                  launcher_binding=env.get('__PYVENV_LAUNCHER__') if env is not None else None)
    try:
        out = (directory/'inert-stdout.bin').open('xb'); context['streams'].append(out)
        err = (directory/'inert-stderr.bin').open('xb'); context['streams'].append(err)
        child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        context['children'].append(child)
        launch['pid'] = child.pid
        launch.update({k:v for k,v in stamp(child.pid).items() if k != 'pid'})
        launch['poll_after_creation'] = child.poll()
    except BaseException as primary:
        launch['startup_error'] = repr(primary)
        try:_control_write(directory, 'launch', launch)
        except BaseException as secondary:primary.add_note('Launch diagnostic also failed: '+repr(secondary))
        raise
    _control_write(directory, 'launch', launch)
    return child


def _inside(rect, area):
    return area[0] <= rect[0] < rect[2] <= area[2] and area[1] <= rect[1] < rect[3] <= area[3]


def _separate(a, b):
    return a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def _control_placement(areas, subject, width, height):
    f.require(width > 100 and height > 30, 'Invalid inert window dimensions')
    for area in areas:
        # Physical coordinates, including negative monitor origins. Never move
        # the subject or another application to make a candidate work.
        for x, y in ((subject[2]+12, area[1]+12), (area[0]+12, subject[3]+12),
                     (subject[0]-width-12, area[1]+12), (area[0]+12, subject[1]-height-12)):
            rect = (x, y, x+width, y+height)
            if _inside(rect, area) and _separate(rect, subject):return rect
    raise f.FocusBlocked('No visible disjoint inert-window placement')


def _work_areas(api):
    c, w, user = api.c, api.w, api.user
    class MONITOR(c.Structure):
        _fields_ = [('size', w.DWORD), ('monitor', w.RECT), ('work', w.RECT), ('flags', w.DWORD)]
    callback = c.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, c.POINTER(w.RECT), w.LPARAM)
    user.EnumDisplayMonitors.argtypes = [w.HDC, c.POINTER(w.RECT), callback, w.LPARAM]
    user.EnumDisplayMonitors.restype = w.BOOL
    user.GetMonitorInfoW.argtypes = [w.HANDLE, c.POINTER(MONITOR)]
    user.GetMonitorInfoW.restype = w.BOOL
    areas, errors = [], []
    @callback
    def visit(handle, dc, rect, unused):
        try:
            f.require(len(areas) < 32, 'Monitor enumeration exceeds safety bound')
            info = MONITOR(); info.size = c.sizeof(info)
            api.checked(user.GetMonitorInfoW(handle, c.byref(info)))
            areas.append((info.work.left, info.work.top, info.work.right, info.work.bottom))
            return True
        except BaseException as exc:errors.append(exc); return False
    ok = user.EnumDisplayMonitors(None, None, visit, 0)
    if errors:raise errors[0]
    api.checked(ok); f.require(areas, 'No display work area')
    return areas


def _process_stamp(api, pid, job=None):
    c, w, k = api.c, api.w, api.kernel
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]; k.CloseHandle.restype = w.BOOL
    k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]; k.WaitForSingleObject.restype = w.DWORD
    k.GetProcessTimes.argtypes = [w.HANDLE, *([c.POINTER(w.FILETIME)]*4)]
    k.GetProcessTimes.restype = w.BOOL
    k.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, c.POINTER(w.BOOL)]
    k.IsProcessInJob.restype = w.BOOL
    k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
    k.QueryFullProcessImageNameW.restype = w.BOOL
    handle = api.checked(k.OpenProcess(0x1000 | 0x100000, False, pid))
    primary = None
    try:
        times = [w.FILETIME() for _ in range(4)]
        api.checked(k.GetProcessTimes(handle, *[c.byref(t) for t in times]))
        value = dict(pid=pid, creation=(times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                     live=k.WaitForSingleObject(handle, 0) == 258)
        image = c.create_unicode_buffer(32768); size = w.DWORD(len(image))
        api.checked(k.QueryFullProcessImageNameW(handle, 0, image, c.byref(size)))
        value['image'] = image.value
        if job is not None:
            member = w.BOOL(); api.checked(k.IsProcessInJob(handle, job, c.byref(member)))
            value['member'] = bool(member.value)
        return value
    except BaseException as exc:primary = exc; raise
    finally:
        try:api.checked(k.CloseHandle(handle))
        except BaseException as exc:
            if primary is None:raise
            primary.add_note('Process identity handle close also failed: '+repr(exc))


def _window_probe(api, target):
    with api.dpi():
        api.marker(target)
        rectangle = api.geometry(target)
        sid = api.w.DWORD()
        api.checked(api.kernel.ProcessIdToSessionId(target['pid'], api.c.byref(sid)))
        environment = {**api.session(), **api.desktop(target['thread'])}
        f.require(sid.value == environment['session_id'], 'Foreign process session mismatch')
        return dict(target=target, rectangle=rectangle, environment=environment, visible=True, enabled=True,
                    foreground=api.user.GetForegroundWindow(), focus=api.focus_state(target))


def _accept_ready(ready, launch, nonce, probe, membership, areas, subject, expected_environment=None):
    f.require(ready.get('nonce') == launch.get('nonce') == nonce, 'Wrong readiness nonce')
    target = ready.get('target', {})
    for key in ('pid', 'thread', 'client', 'top', 'token'):
        f.require(type(target.get(key)) is int and target[key] > 0, 'Invalid readiness '+key)
    f.require(target['pid'] == launch.get('pid') and ready.get('mapped') is True, 'Wrong PID or unmapped child')
    f.require(isinstance(target.get('property'), str) and target['property'].startswith('ChronicleF2-'), 'Missing window identity marker')
    f.require(membership.get('live') is True and membership.get('member') is True,
              'Inert child is not live in the exact owned Job')
    f.require(membership.get('pid') == target['pid'] and
              membership.get('creation') == launch.get('creation') == ready.get('creation'), 'Reused process identity')
    f.require(probe.get('target') == target and probe.get('environment') == ready.get('environment'), 'Window/thread/session observation mismatch')
    if expected_environment is not None:
        f.require(probe['environment'] == expected_environment, 'Subject/inert session or desktop mismatch')
    f.require(probe.get('visible') is True and probe.get('enabled') is True, 'Inert window hidden or disabled')
    rect = probe.get('rectangle')
    f.require(rect == tuple(ready.get('rectangle', ())), 'Actual child geometry changed')
    f.require(_separate(rect, subject) and any(_inside(rect, a) for a in areas), 'Invalid or overlapping actual placement')
    return dict(nonce=nonce, pid=target['pid'], creation=membership['creation'], exact_job=True,
                target=target, observation=probe, monotonic=time.monotonic())


class _InertBootstrap:
    """Fixture-only input for its own inert HWND; never a subject driver."""
    def __init__(self, root, api, target, before_input=lambda point: None):
        self.root, self.api, self.target = root, api, target
        self.before_input = before_input
        self.state, self.verified = 'ARMED', False
        self.reply = __import__('queue').Queue(maxsize=1)
        self.worker = None
        self.sent = self.focus_called = False
        self.events = []
        self.last_state = None

    def step(self, deadline):
        try:
            f.require(self.state != 'DISARMED', 'Inert bootstrap is terminally disarmed')
            f.require(time.monotonic() < deadline, 'Inert bootstrap setup deadline exhausted')
            f.require(self.root.winfo_exists() and self.root.nametowidget(str(self.root)) is self.root
                      and self.root.winfo_viewable(), 'Inert Tk root is not live/viewable')
            if self.worker is None:
                self.state = 'INSPECTING'
                def inspect():
                    try:value = self.api.inspect(self.target, deadline)
                    except BaseException as exc:value = exc
                    self.reply.put(value)
                self.worker = __import__('threading').Thread(target=inspect, daemon=True, name='inert-native-inspection')
                self.worker.start(); return False
            if self.state == 'INSPECTING':
                try:value = self.reply.get_nowait()
                except __import__('queue').Empty:return False
                if isinstance(value, BaseException):raise value
                self.events.append(dict(event='inspection', observation=value))
                f.require(time.monotonic()-value['monotonic'] <= .100, 'Stale bootstrap observation')
                if value['foreground'] != self.target['top']:
                    self.before_input(value['point'])
                    self.api.confirm(self.target, value)
                    f.require(time.monotonic() < deadline and time.monotonic()-value['monotonic'] <= .100,
                              'Bootstrap target confirmation expired')
                    self.sent = True
                    try:count, error = self.api.click(value['point'], deadline)
                    except BaseException as exc:
                        raise f.FocusFailed('Bootstrap input outcome unavailable: '+repr(exc), unsafe_input=True) from exc
                    self.events.append(dict(event='SendInput', expected=3, inserted=count, last_error=error))
                    if count != 3:raise f.FocusFailed('Incomplete bootstrap input', unsafe_input=count > 1)
                else:self.events.append(dict(event='already_foreground'))
                self.state = 'VERIFYING'
            state = self.api.focus_state(self.target)
            if state != self.last_state:
                self.events.append(dict(event='native_focus', observation=state, monotonic=time.monotonic()))
            self.last_state = state
            if state['foreground'] != self.target['top']:return False
            if not self.focus_called and (self.sent or not state['focus_inside'] or self.root.focus_get() is not self.root):
                f.require(time.monotonic() < deadline, 'Bootstrap focus deadline exhausted')
                self.focus_called = True
                self.events.append(dict(event='ordinary_Tk_focus_set', monotonic=time.monotonic()))
                self.root.focus_set()
            state = self.api.focus_state(self.target)
            if state != self.last_state:
                self.events.append(dict(event='native_focus', observation=state, monotonic=time.monotonic()))
            self.last_state = state
            if not state['focus_inside'] or state['foreground'] != self.target['top'] or self.root.focus_get() is not self.root:return False
            f.require(time.monotonic() < deadline, 'Bootstrap verification exceeded deadline')
            self.verified = True; self.disarm(); return True
        except BaseException:
            self.disarm(); raise

    def disarm(self):
        if self.state != 'DISARMED':
            self.state = 'DISARMED'; self.events.append(dict(event='disarmed', monotonic=time.monotonic()))

    def evidence(self):
        return dict(state=self.state, verified=self.verified, events=self.events, native=self.last_state,
                    attempted=self.sent, last_input=getattr(self.api, 'last_input', None))


def _finish_control(primary, actions, publish):
    """Diagnostic failure cannot short-circuit owned cleanup or mask primary."""
    errors = []
    for label, action in actions:
        try:action()
        except BaseException as exc:errors.append(label+': '+repr(exc))
    try:publish(errors)
    except BaseException as exc:errors.append('diagnostic finalization: '+repr(exc))
    if errors:
        if primary is not None:
            for error in errors:primary.add_note(error)
        else:raise RuntimeError('Control cleanup/evidence incomplete: '+repr(errors))
    return errors


def _utc():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _inert_main(directory):
    """Bare fixture window. No Chronicle root, worker or dataset is created."""
    import tkinter as tk
    import traceback
    config = _control_read(directory, 'config'); subject = _control_read(directory, 'subject')
    nonce = config['nonce']; deadline = subject['setup_deadline']
    root = None; target = None; bootstrap = None; api = None
    code, reason, failure = 0, 'parent cleanup', None
    try:
        f.require(config['node'] in f.NODES and subject['nonce'] == nonce, 'Wrong inert control context')
        api = f.Win32API()
        f.require(sys.argv[1:] == ['--inert-control', str(directory)], 'Wrong inert runtime entry point')
        _runtime_probe(directory, 'inert', api, config, deadline, config['node'])
        root = tk.Tk(); root.title('F2 owned inert control')
        root.geometry('360x140')
        creation = _process_stamp(api, os.getpid())['creation']
        def tick():
            nonlocal target, bootstrap, code, reason, failure
            try:
                if time.monotonic() >= subject['started']+15:
                    raise f.FocusBlocked('Inert child lifetime guard expired')
                if bootstrap is not None and bootstrap.verified:
                    root.after(5, tick); return  # Permanently no input after FOREIGN_READY.
                f.require(time.monotonic() < deadline, 'Control setup deadline exhausted')
                if target is None:
                    if not root.winfo_viewable():root.after(5, tick); return
                    target = api.bind_target(int(root.winfo_id()))
                    with api.dpi():
                        original = api.geometry(target); areas = _work_areas(api)
                        rect = _control_placement(areas, subject['rectangle'], original[2]-original[0], original[3]-original[1])
                        user, w = api.user, api.w
                        user.SetWindowPos.argtypes = [w.HWND, w.HWND, w.INT, w.INT, w.INT, w.INT, w.UINT]
                        user.SetWindowPos.restype = w.BOOL
                        # Move only this owned fixture frame, without activation
                        # or z-order changes. Negative monitor coordinates work.
                        api.checked(user.SetWindowPos(target['top'], None, rect[0], rect[1], 0, 0, 0x215))
                    probe = _window_probe(api, target)
                    f.require(_separate(probe['rectangle'], subject['rectangle']) and
                              any(_inside(probe['rectangle'], a) for a in areas), 'Actual mapped placement unsafe')
                    _control_write(directory, 'window-ready', dict(nonce=nonce, target=target, mapped=True,
                        creation=creation, rectangle=probe['rectangle'], environment=probe['environment'],
                        work_areas=areas, python=sys.version, executable=sys.executable,
                        tcl=root.tk.call('info', 'patchlevel'), tk=root.tk.call('package', 'require', 'Tk'),
                        monotonic=time.monotonic(), utc=_utc()))
                job = _control_read(directory, 'job-verified')
                if job is None:root.after(5, tick); return
                f.require(job.get('nonce') == nonce and job.get('pid') == os.getpid() and
                          job.get('creation') == creation and job.get('exact_job') is True, 'Invalid Job arming acknowledgement')
                if bootstrap is None:
                    def before_input(point):
                        _control_write(directory, 'bootstrap-attempt', dict(nonce=nonce, point=point, expected=3, monotonic=time.monotonic()))
                    bootstrap = _InertBootstrap(root, api, target, before_input)
                if bootstrap.step(deadline):
                    _control_write(directory, 'foreign-ready', dict(nonce=nonce, target=target,
                        bootstrap=bootstrap.evidence(), monotonic=time.monotonic(), utc=_utc()))
                root.after(5, tick)
            except BaseException as exc:
                code, reason, failure = 4, 'setup/lifetime failure', exc
                if bootstrap is not None:bootstrap.disarm()
                try:_control_write(directory, 'inert-error', dict(nonce=nonce, error=repr(exc),
                    unsafe_input=getattr(exc, 'unsafe_input', False), bootstrap=bootstrap.evidence() if bootstrap else None,
                    monotonic=time.monotonic(), utc=_utc()))
                except BaseException as secondary:exc.add_note('Inert diagnostic also failed: '+repr(secondary))
                traceback.print_exception(exc)
                root.destroy()
        root.after(0, tick); root.mainloop()
    except BaseException as exc:
        code, reason, failure = 4, 'startup failure', exc
        traceback.print_exception(exc)
    finally:
        if bootstrap is not None:bootstrap.disarm()
        def destroy():
            if root is not None:
                try:root.destroy()
                except tk.TclError:pass
        def publish(errors):
            _control_write(directory, 'inert-exit', dict(nonce=nonce, code=code, reason=reason,
                error=repr(failure) if failure else None, cleanup_errors=errors, monotonic=time.monotonic(), utc=_utc()))
        errors = _finish_control(failure, [
            ('inert marker', lambda:api.unbind_target(target) if target is not None else None),
            ('inert root', destroy)], publish)
        if errors:code = 4
    return code


def _native_report(item, call):
    # Registered only by the generated plugin, not by ordinary module collection.
    context = getattr(item, '_f2_control_context', None)
    if context is None or call.when != 'call':return
    primary = call.excinfo.value if call.excinfo is not None else None
    context['primary'] = primary
    driver, root = context['driver'], context['root']
    try:
        import tk_observation as observation
        native = driver.api.focus_state(driver.target) if driver.target is not None else None
        state = observation.snapshot(root, (driver.widget,) if driver.widget is not None else ())
        f.require(not state.get('observation_errors'), 'Uncertain RESULT observation')
        # Match tk_observation's logger: grid_info() can contain real Tk objects.
        state = json.loads(json.dumps(state, default=str))
        _control_write(context['directory'], 'result', dict(nonce=context['nonce'], failed=primary is not None,
            primary=repr(primary), notes=getattr(primary, '__notes__', []), unsafe_input=getattr(primary, 'unsafe_input', False),
            native=native, logical_origin=root.focus_get() is driver.widget,
            snapshot=state, driver=driver.evidence(), monotonic=time.monotonic()))
    except BaseException as exc:
        context['diagnostic_errors'].append('RESULT observation: '+repr(exc))
        if primary is not None:primary.add_note('Control RESULT diagnostic also failed: '+repr(exc))


def _controlled_origin(root, monkeypatch, request):
    from pathlib import Path
    directory = Path(os.environ['F2_CONTROL_DIR']); config = _control_read(directory, 'config')
    nonce = config['nonce']; driver = root._f2_focus_driver
    f.require(request.node.nodeid == config['node'], 'Wrong native-control subject node')
    context = dict(directory=directory, nonce=nonce, driver=driver, root=root, primary=None,
                   children=[], streams=[], diagnostic_errors=[])
    request.node._f2_control_context = context
    _runtime_probe(directory, 'subject', driver.api, config, config['control_deadline'], request.node.nodeid)
    original_inspect, original_prepare = driver.api.inspect, driver.prepare
    versions = dict(tcl=root.tk.call('info', 'patchlevel'), tk=root.tk.call('package', 'require', 'Tk'))
    def inspect(target, deadline):
        f.require(not context['children'], 'Native setup cannot retry')
        started = time.monotonic(); until = min(deadline, started+2)
        with driver.api.dpi():rectangle = driver.api.geometry(target)
        _control_write(directory, 'subject', dict(nonce=nonce, target=target, rectangle=rectangle,
            environment={**driver.api.session(), **driver.api.desktop(target['thread'])},
            started=started, setup_deadline=until, versions=versions))
        executable, child_env, selected = _control_python(os.environ, image=_process_stamp(driver.api, os.getpid())['image'])
        f.require(all(selected[k] == config['runtime'][k] for k in selected), 'Inert runtime selection differs from subject')
        command = [executable, '-u', '-B', str(Path(__file__).resolve()), '--inert-control', str(directory)]
        child = _launch_control(directory, nonce, command, context, started, f.REPO,
                                lambda pid:_process_stamp(driver.api, pid), env=child_env)
        foreign = _control_wait(directory, 'foreign-ready', nonce, until, child)
        window = _control_read(directory, 'window-ready'); job = _control_read(directory, 'job-verified')
        f.require(window is not None and job is not None and
                  foreign['target'] == window['target'] == job['target'], 'Bootstrap changed the identified native root')
        f.require(foreign['bootstrap']['verified'] and foreign['bootstrap']['state'] == 'DISARMED', 'Bootstrap was not disarmed')
        actual = _window_probe(driver.api, foreign['target'])
        f.require(actual['foreground'] == foreign['target']['top'] and actual['focus']['focus_inside'],
                  'Independent observation did not confirm foreign foreground')
        inspected = original_inspect(target, deadline)
        f.require(inspected['foreground'] == foreign['target']['top'] and
                  inspected['foreground_owner'][0] == child.pid, 'Foreign foreground became stale before subject inspection')
        _control_write(directory, 'subject-inspection', dict(nonce=nonce, actual_foreign=actual, subject=inspected))
        return inspected
    def prepare(widget, deadline):
        ready = original_prepare(widget, deadline)
        if ready:
            foreign = _control_read(directory, 'foreign-ready')
            f.require(foreign is not None and foreign['bootstrap']['state'] == 'DISARMED', 'No disarmed bootstrap')
            f.require(context['children'][0].poll() is None, 'Inert child exited before subject readiness')
            native = driver.api.focus_state(driver.target)
            f.require(driver.state == 'DISARMED' and driver.verified and native['foreground'] == driver.target['top']
                      and native['focus_inside'] and root.focus_get() is widget, 'Subject focus precondition not verified')
            _control_write(directory, 'subject-ready', dict(nonce=nonce, driver=driver.evidence(), native=native,
                logical_origin=True, monotonic=time.monotonic()))
            f.require(time.monotonic() < deadline, 'Subject evidence exhausted original precondition budget')
        return ready
    monkeypatch.setattr(driver.api, 'inspect', inspect)
    monkeypatch.setattr(driver, 'prepare', prepare)
    if config['failed_return']:
        from tkinter import ttk
        from test_app import pump
        from chronicle.history_window import HistoryWindow
        wrong = ttk.Entry(root, name='f2_wrong_return', takefocus=True)
        wrong.grid(row=10, column=0)
        close = HistoryWindow.close
        def wrong_return(view):
            ready = _control_read(directory, 'subject-ready'); foreign = _control_read(directory, 'foreign-ready')
            f.require(ready is not None and driver.verified and driver.state == 'DISARMED' and
                      foreign['bootstrap']['state'] == 'DISARMED', 'Cannot inject return fault before valid setup')
            close(view)
            until = time.monotonic()+1  # Fault setup only; RESULT keeps its original eight seconds.
            def available():
                return (wrong.winfo_exists() and root.nametowidget(str(wrong)) is wrong and
                        wrong.winfo_viewable() and not wrong.instate(['disabled']) and
                        driver.api.focus_state(driver.target)['foreground'] == driver.target['top'])
            pump(root, available, timeout=max(1, int((until-time.monotonic())*1000)))
            f.require(wrong is not driver.widget and available() and time.monotonic() < until,
                      'Return-fault target is not live/mapped/distinct within its budget')
            wrong.focus_set()  # One deliberate test fault, never a driver repair.
            def established():
                native = driver.api.focus_state(driver.target)
                return (root.focus_get() is wrong and native['foreground'] == driver.target['top'] and native['focus_inside'])
            pump(root, established, timeout=max(1, int((until-time.monotonic())*1000)))
            native = driver.api.focus_state(driver.target)
            f.require(time.monotonic() < until and native['foreground'] == driver.target['top']
                      and native['focus_inside'] and root.focus_get() is wrong,
                      'Return fault did not establish the intended real wrong focus')
            _control_write(directory, 'return-fault', dict(nonce=nonce, applied=True, native=native,
                wrong_focus=str(root.focus_get()), origin=str(driver.widget), focus_requests=1,
                mapped=bool(wrong.winfo_ismapped()), monotonic=time.monotonic()))
        monkeypatch.setattr(HistoryWindow, 'close', wrong_return)
    try:yield
    finally:
        primary = context['primary']
        deadline = time.monotonic()+5
        starts = dict(nonce=nonce, started=time.monotonic(), deadline=deadline,
                      natural_exits=[c.poll() for c in context['children']])
        # This publication itself cannot be allowed to bypass cleanup.
        errors = list(context['diagnostic_errors'])
        try:_control_write(directory, 'cleanup-start', starts)
        except BaseException as exc:errors.append('cleanup-start diagnostic: '+repr(exc))
        def stop(child):
            code = child.poll()
            if driver.verified:f.require(code is None, 'Inert child expired before modal completion')
            if code is None:child.terminate()
        actions = []
        for child in context['children']:
            # A premature-exit assertion must not suppress the wait/reap action.
            actions.extend([('terminate inert', lambda c=child: stop(c)),
                            ('wait inert', lambda c=child: c.wait(timeout=max(.001, deadline-time.monotonic())))])
        actions.extend(('close inert stream', stream.close) for stream in context['streams'])
        def publish(cleanup_errors):
            _control_write(directory, 'inner-final', dict(nonce=nonce, driver=driver.evidence(),
                errors=errors+cleanup_errors, natural_exits=starts['natural_exits'],
                final_exits=[c.poll() for c in context['children']], primary=repr(primary),
                unsafe_input=getattr(primary, 'unsafe_input', False), monotonic=time.monotonic()))
        extra = _finish_control(primary, actions, publish)
        if errors or extra:
            if primary is not None:
                for error in errors:primary.add_note(error)
            else:raise RuntimeError('Control evidence incomplete: '+repr(errors+extra))


def _validate_control_result(directory, nonce, code, failed_return):
    from xml.etree import ElementTree
    foreign = _control_read(directory, 'foreign-ready'); subject = _control_read(directory, 'subject-ready')
    result = _control_read(directory, 'result'); final = _control_read(directory, 'inner-final')
    job = _control_read(directory, 'job-verified')
    for value in (foreign, subject, result, final, job):
        f.require(value is not None and value.get('nonce') == nonce, 'Missing/mismatched native control evidence')
    f.require(job.get('exact_job') is True and job.get('pid') == foreign['target']['pid']
              and job.get('target') == foreign['target'], 'Exact Job/window proof absent')
    f.require(not final['errors'] and all(c is not None for c in final['final_exits']), 'Incomplete inner cleanup/diagnostics')
    bootstrap = foreign['bootstrap']
    f.require(bootstrap['verified'] and bootstrap['state'] == 'DISARMED', 'Bootstrap precondition absent')
    inputs = [e for e in bootstrap['events'] if e['event'] == 'SendInput']
    f.require(len(inputs) <= 1 and all(e['inserted'] == 3 for e in inputs), 'Invalid bootstrap input evidence')
    before, after = subject['driver'], result['driver']
    expected_node = f.HISTORY+'::test_real_tk_history_parent_grab_focus_return_identity_and_guard[none]'
    f.require(before.get('node') == after.get('node') == expected_node, 'Wrong subject node evidence')
    f.require(before['precondition_verified'] and before['state'] == after['state'] == 'DISARMED', 'Subject was not ready/disarmed')
    inputs = [e for e in before['events'] if e['event'] == 'SendInput']
    f.require(len(inputs) == 1 and inputs[0]['inserted'] == 3, 'No genuine one-shot subject activation')
    f.require(before['events'] == after['events'] == final['driver']['events']
              and final['driver']['state'] == 'DISARMED', 'Driver mutated during modal RESULT/cleanup')
    f.require(subject['native']['foreground'] == before['target']['top'] and subject['native']['focus_inside']
              and subject['logical_origin'], 'Invalid native/Tk subject precondition')
    xml = ElementTree.parse(__import__('pathlib').Path(directory)/'native.xml').getroot()
    cases = list(xml.iter('testcase'))
    f.require(len(cases) == 1 and not list(xml.iter('error')) and not list(xml.iter('skipped')), 'Native JUnit incomplete or setup/cleanup failed')
    expected_class = f.HISTORY[:-3].replace('/', '.')
    f.require((cases[0].get('classname'), cases[0].get('name')) == (expected_class, expected_node.split('::')[1]), 'Wrong native JUnit identity')
    if failed_return:
        fault = _control_read(directory, 'return-fault')
        f.require(code == 1 and result['failed'] and fault is not None and fault['applied']
                  and len(list(xml.iter('failure'))) == 1, 'Expected independent return failure absent')
        f.require(any('observation failed during RESULT' in n for n in result['notes']), 'Failure was not during RESULT')
        f.require(fault['monotonic'] > subject['monotonic'] and not result['logical_origin']
                  and result['native']['foreground'] == before['target']['top'], 'Wrong/obstructed return-fault observation')
        f.require(fault['wrong_focus'] != fault['origin'] and fault['mapped'] and fault['focus_requests'] == 1
                  and fault['native']['foreground'] == before['target']['top'] and fault['native']['focus_inside'],
                  'Unverified deliberate wrong-focus injection')
    else:
        f.require(code == 0 and not result['failed'] and not list(xml.iter('failure'))
                  and result['logical_origin'] and result['native']['foreground'] == before['target']['top']
                  and result['native']['focus_inside'], 'Normal modal return failed')


@pytest.mark.skipif(sys.platform != 'win32', reason='Native Windows foreground/return controls NOT RUN')
@pytest.mark.parametrize('failed_return', [False, True])
def test_native_ordinary_activation_and_independent_modal_return_control(tmp_path, failed_return, request):
    from pathlib import Path
    import hashlib
    import platform
    import subprocess
    import threading
    from uuid import uuid4
    sys.path.insert(0, str(f.REPO/'scripts'))
    import qualification_pytest as q
    node = f.HISTORY+'::test_real_tk_history_parent_grab_focus_return_identity_and_guard[none]'
    nonce = uuid4().hex; directory = tmp_path/('inert-'+nonce); directory.mkdir()
    plugin = tmp_path/'native_focus_control.py'
    plugin.write_text('''import pytest
from test_win32_focus import _controlled_origin, _native_report
pytest_runtest_makereport = pytest.hookimpl(tryfirst=True)(_native_report)
@pytest.fixture(autouse=True)
def controlled_origin(root, monkeypatch, request):
    yield from _controlled_origin(root, monkeypatch, request)
''', encoding='utf-8')
    def source():
        return dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=f.REPO,text=True).strip(),
            branch=subprocess.check_output(['git','branch','--show-current'],cwd=f.REPO,text=True).strip(),
            status=subprocess.check_output(['git','status','--porcelain=v1'],cwd=f.REPO,text=True),
            files={str(p.relative_to(f.REPO)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (Path(__file__).resolve(), Path(f.__file__).resolve())})
    original_source = source()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
        PYTHONPATH=os.pathsep.join([str(tmp_path),str(f.REPO/'src'),str(f.REPO/'tests/rewrite')]), F2_CONTROL_DIR=str(directory))
    env.pop('PYTEST_ADDOPTS',None);env.pop('PYTEST_PLUGINS',None)
    profile=tmp_path/'profile';profile.mkdir()
    env.update(HOME=str(profile),USERPROFILE=str(profile),LOCALAPPDATA=str(profile))
    api=f.Win32API(); control_deadline=time.monotonic()+45
    try:
        executable, env, runtime = _control_python(env)
    except BaseException as exc:
        try:_control_write(directory,'python-selection-error',dict(error=repr(exc),python=_python_facts(),utc=_utc()))
        except BaseException as secondary:exc.add_note('Selection diagnostic also failed: '+repr(secondary))
        raise
    runtime.update(source=original_source,dependencies=_runtime_dependencies())
    config=dict(nonce=nonce,node=node,failed_return=failed_return,source=original_source,runtime=runtime,
        control_deadline=control_deadline,python=sys.version,executable=sys.executable,windows=platform.platform(),
        launcher_binding=env.get('__PYVENV_LAUNCHER__'),
        plugin_sha256=hashlib.sha256(plugin.read_bytes()).hexdigest(),utc=_utc())
    _control_write(directory, 'config', config)
    _runtime_probe(directory, 'controller', api, config, control_deadline, request.node.nodeid)
    command=[executable,'-B','-m','pytest','-q','-p','no:cacheprovider','-p','native_focus_control',
        '-o','addopts=','--capture=tee-sys',node,'--basetemp',str(tmp_path/'child-temp'),
        '--junitxml',str(directory/'native.xml')]
    _control_write(directory,'command',dict(command=command,cwd=str(f.REPO),utc=_utc()))
    child=None; primary=None; code=None; threads=[]; errors=[]; cleanup=None
    try:
        child=q.WindowsChild(command,f.REPO,env)
        def drain(name,stream):
            try:
                with (directory/(name+'.bin')).open('xb') as output:
                    while True:
                        data=stream.read(65536)
                        if not data:break
                        output.write(data)
            except BaseException as exc:errors.append(name+' capture: '+repr(exc))
        threads=[threading.Thread(target=drain,args=(n,s),daemon=True) for n,s in (('stdout',child.stdout),('stderr',child.stderr))]
        for thread in threads:thread.start()
        subject_launch=_process_stamp(api,child.pid,child.job)
        _control_write(directory,'subject-launch',dict(nonce=nonce,process=subject_launch,utc=_utc()))
        until=control_deadline
        while child.poll() is None:
            f.require(time.monotonic()<until,'Outer native-control deadline exhausted')
            start=_control_read(directory,'cleanup-start')
            if start:
                cleanup=start['deadline'];f.require(time.monotonic()<cleanup,'Shared control cleanup deadline exhausted')
            ready=_control_read(directory,'window-ready');launch=_control_read(directory,'launch');subject=_control_read(directory,'subject')
            if ready and launch and subject and _control_read(directory,'job-verified') is None:
                member=_process_stamp(api,launch['pid'],child.job)
                parent=_process_stamp(api,child.pid,child.job)
                f.require(parent.get('member') is True and parent['live'],'Subject not in exact owned Job')
                f.require(subject['target']['pid'] == child.pid, 'Wrong subject process identity')
                for role, started_process, membership, target in (
                    ('subject',subject_launch,parent,subject['target']), ('inert',launch,member,ready['target'])):
                    _accept_runtime(_control_read(directory,role+'-runtime'),runtime,nonce,role,node,
                                    started_process,membership,target)
                with api.dpi():
                    api.marker(subject['target']);areas=_work_areas(api);subject_now=api.geometry(subject['target'])
                acknowledgement=_accept_ready(ready,launch,nonce,_window_probe(api,ready['target']),member,areas,subject_now,subject['environment'])
                f.require(time.monotonic()<subject['setup_deadline'],'Job/readiness verification exceeded shared setup budget')
                _control_write(directory,'job-verified',acknowledgement)
            f.require(not errors,'Native raw capture failed: '+repr(errors))
            time.sleep(.005)
        code=child.poll()
    except BaseException as exc:primary=exc;raise
    finally:
        # The inner finalizer may have started and finished between outer polls.
        # Do not silently grant another cleanup period in that case.
        try:
            start=_control_read(directory,'cleanup-start')
            if start:cleanup=start['deadline']
        except BaseException as exc:errors.append('cleanup deadline diagnostic: '+repr(exc))
        until=min(time.monotonic()+5,cleanup if cleanup is not None else float('inf'))
        cleanup_state={}
        def stop():
            if child is not None and child.active_count():child.terminate_owned()
        def verify():
            if child is None:return
            while child.active_count() and time.monotonic()<until:time.sleep(.005)
            cleanup_state['active_count']=child.active_count()
            f.require(cleanup_state['active_count']==0,'Owned Job cleanup unverified')
            for thread in threads:thread.join(timeout=max(0,until-time.monotonic()))
            f.require(all(not t.is_alive() for t in threads),'Native streams not drained')
        def publish(extra):
            unsafe=False; records={}
            for name in ('inert-error','inner-final','result','bootstrap-attempt','foreign-ready','subject-ready'):
                try:
                    value=_control_read(directory,name)
                    records[name]=value
                    unsafe=unsafe or bool(value and value.get('unsafe_input'))
                except BaseException as exc:
                    errors.append('input safety diagnostic: '+repr(exc));unsafe=True
                    if primary is not None:primary.add_note('Input safety diagnostic also failed: '+repr(exc))
            if records.get('bootstrap-attempt') and not records.get('foreign-ready'):unsafe=True
            if records.get('foreign-ready') and not records.get('subject-ready') and not records.get('inner-final'):unsafe=True
            if unsafe:request.session.shouldstop='Uncertain synthetic input state; qualification blocked'
            hashes={}
            for path in directory.iterdir():
                if path.is_file() and path.suffix in ('.bin','.xml','.json'):
                    hashes[path.name]=dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            _control_write(directory,'outer-final',dict(nonce=nonce,code=code,primary=repr(primary),
                cleanup=cleanup_state,errors=errors+extra,unsafe_input=unsafe,
                evidence_hashes=hashes,source_after=source(),utc=_utc()))
        extra=_finish_control(primary,[('terminate Job',stop),('verify Job/streams',verify),
            ('close Job',lambda:child.close() if child is not None else None)],publish)
        if extra:errors.extend(extra)
    assert not errors and cleanup_state.get('active_count')==0
    assert source()==original_source,'Source changed during native control'
    _validate_control_result(directory,nonce,code,failed_return)


@pytest.mark.parametrize('platform', ['linux', 'win32'])
def test_observer_isolation_exercises_both_platform_branches(monkeypatch, platform):
    import tk_observation as observation
    import test_app  # Load actual modules before selecting a portable fake branch.
    monkeypatch.setattr(observation.sys, 'platform', platform)
    test_observer_shares_deadline_and_never_prepares_during_result(monkeypatch)


def _ready_records():
    target=dict(pid=42,thread=7,client=10,top=20,property='ChronicleF2-owned',token=50)
    environment=dict(session_id=3,station='WinSta0',thread_desktop='Default',input_desktop='Default')
    ready=dict(nonce='n',target=dict(target),mapped=True,creation=100,rectangle=[1012,12,1372,192],environment=dict(environment))
    launch=dict(nonce='n',pid=42,creation=100)
    probe=dict(target=dict(target),rectangle=tuple(ready['rectangle']),environment=dict(environment),visible=True,enabled=True)
    membership=dict(pid=42,creation=100,live=True,member=True)
    return ready,launch,probe,membership


@pytest.mark.parametrize('damage', ['nonce','pid','hwnd','thread','marker','mapping','visible','enabled','session','creation','job'])
def test_control_readiness_refuses_unverified_identity(damage):
    ready,launch,probe,membership=_ready_records()
    if damage=='nonce':ready['nonce']='wrong'
    if damage=='pid':ready['target']['pid']=43
    if damage=='hwnd':ready['target']['top']=99
    if damage=='thread':ready['target']['thread']=8
    if damage=='marker':ready['target']['property']=''
    if damage=='mapping':ready['mapped']=False
    if damage=='visible':probe['visible']=False
    if damage=='enabled':probe['enabled']=False
    if damage=='session':probe['environment']['session_id']=4
    if damage=='creation':membership['creation']=101
    if damage=='job':membership['member']=False
    with pytest.raises(f.FocusBlocked):
        _accept_ready(ready,launch,'n',probe,membership,[(0,0,1920,1080)],(0,0,1000,600))


def test_control_readiness_requires_exact_live_job_and_safe_placement():
    ready,launch,probe,membership=_ready_records()
    acknowledged=_accept_ready(ready,launch,'n',probe,membership,[(0,0,1920,1080)],(0,0,1000,600))
    assert acknowledged['exact_job'] and acknowledged['pid']==42
    membership['live']=False
    with pytest.raises(f.FocusBlocked,match='live'):
        _accept_ready(ready,launch,'n',probe,membership,[(0,0,1920,1080)],(0,0,1000,600))
    membership['live']=True
    with pytest.raises(f.FocusBlocked,match='placement'):
        _accept_ready(ready,launch,'n',probe,membership,[(0,0,1920,1080)],(1000,0,1500,600))


def test_control_placement_handles_negative_monitors_and_refuses_no_space():
    area=(-1920,0,0,1080);subject=(-1900,20,-1000,620)
    rect=_control_placement([area],subject,360,180)
    assert _inside(rect,area) and _separate(rect,subject)
    with pytest.raises(f.FocusBlocked,match='placement'):
        _control_placement([(0,0,800,600)],(0,0,800,600),360,180)


def test_control_wait_uses_one_deadline_and_rejects_partial_or_malformed_records(tmp_path):
    now=[0.0]
    child=SimpleNamespace(poll=lambda:None)
    def sleep(seconds):now[0]+=seconds
    # An incomplete writer is not READY, even if the JSON bytes already exist.
    (tmp_path/'window-ready.json').write_text('{"nonce":"n"}')
    with pytest.raises(f.FocusBlocked,match='deadline'):
        _control_wait(tmp_path,'window-ready','n',.01,child,clock=lambda:now[0],sleep=sleep)
    assert .01<=now[0]<.02
    (tmp_path/'window-ready.done').write_bytes(b'')
    (tmp_path/'window-ready.json').write_text('{broken')
    with pytest.raises(json.JSONDecodeError):_control_wait(tmp_path,'window-ready','n',time.monotonic()+1,child)
    (tmp_path/'window-ready.json').write_text('{"nonce":"other"}')
    with pytest.raises(f.FocusBlocked,match='nonce'):_control_wait(tmp_path,'window-ready','n',time.monotonic()+1,child)


def test_control_startup_exit_retains_real_raw_child_streams(tmp_path):
    context=dict(children=[],streams=[])
    command=[sys.executable,'-u','-B','-c',"import os;os.write(1,b'startup-out');os.write(2,b'startup-error\\x00\\xff');raise SystemExit(9)"]
    child=_launch_control(tmp_path,'n',command,context,time.monotonic(),tmp_path,
                          lambda pid:dict(pid=pid,creation=100,live=True))
    try:
        assert child.wait(timeout=2)==9
        with pytest.raises(f.FocusBlocked,match='exited.*9'):
            _control_wait(tmp_path,'window-ready','n',time.monotonic()+1,child)
    finally:
        _finish_control(None,[('stop',lambda:child.terminate() if child.poll() is None else None),
            ('reap',lambda:child.wait(timeout=5)),*[(str(i),s.close) for i,s in enumerate(context['streams'])]],lambda errors:None)
    assert (tmp_path/'inert-stdout.bin').read_bytes()==b'startup-out'
    assert (tmp_path/'inert-stderr.bin').read_bytes()==b'startup-error\x00\xff'
    assert _control_read(tmp_path,'launch')['command']==command


def test_launch_diagnostic_failure_preserves_startup_exception_and_closes_streams(monkeypatch,tmp_path):
    context=dict(children=[],streams=[])
    def broken(*args):raise OSError('controlled diagnostic write failure')
    monkeypatch.setattr(sys.modules[__name__], '_control_write', broken)
    try:
        with pytest.raises(FileNotFoundError) as failed:
            _launch_control(tmp_path,'n',[str(tmp_path/'absent-python')],context,time.monotonic(),tmp_path,lambda pid:{})
        assert any('diagnostic write failure' in note for note in failed.value.__notes__)
    finally:
        _finish_control(None,[(str(i),s.close) for i,s in enumerate(context['streams'])],lambda errors:None)
    assert all(s.closed for s in context['streams']) and not context['children']


@pytest.mark.parametrize('damage', ['occluded','held input','expired session'])
def test_bootstrap_inspection_failure_disarms_without_input(damage):
    api=API(foreground=99,error=f.FocusBlocked(damage));root=Widget()
    bootstrap=_InertBootstrap(root,api,api.bind_target(10))
    deadline=time.monotonic()+2
    assert not bootstrap.step(deadline)
    bootstrap.worker.join(timeout=1)
    with pytest.raises(f.FocusBlocked,match=damage):bootstrap.step(deadline)
    assert bootstrap.state=='DISARMED' and not api.input and not root.focus_calls


@pytest.mark.parametrize('inserted', [0,1,2,3])
def test_bootstrap_input_is_one_shot_and_terminal(inserted):
    api=API(foreground=99,inserted=inserted);root=Widget()
    bootstrap=_InertBootstrap(root,api,api.bind_target(10))
    deadline=time.monotonic()+2
    assert not bootstrap.step(deadline);bootstrap.worker.join(timeout=1)
    if inserted==3:assert bootstrap.step(deadline)
    else:
        with pytest.raises(f.FocusFailed,match='input') as failed:bootstrap.step(deadline)
        assert failed.value.unsafe_input==(inserted>1)
    assert bootstrap.state=='DISARMED' and len(api.input)==1
    count=root.focus_calls
    with pytest.raises(f.FocusBlocked,match='disarmed'):bootstrap.step(deadline)
    assert len(api.input)==1 and root.focus_calls==count


def test_bootstrap_refuses_stale_foreground_without_second_click():
    api=API(foreground=99);root=Widget()
    def moved(*args):raise f.FocusBlocked('stale foreground')
    api.confirm=moved
    bootstrap=_InertBootstrap(root,api,api.bind_target(10))
    deadline=time.monotonic()+2
    assert not bootstrap.step(deadline);bootstrap.worker.join(timeout=1)
    with pytest.raises(f.FocusBlocked,match='stale'):bootstrap.step(deadline)
    assert not api.input and bootstrap.state=='DISARMED'


def test_bootstrap_already_foreground_needs_no_input_and_stays_disarmed():
    api=API(foreground=20);root=Widget();root.focus=root
    bootstrap=_InertBootstrap(root,api,api.bind_target(10))
    deadline=time.monotonic()+2
    assert not bootstrap.step(deadline);bootstrap.worker.join(timeout=1)
    assert bootstrap.step(deadline) and bootstrap.verified
    assert not api.input and not root.focus_calls
    assert any(e['event']=='already_foreground' for e in bootstrap.events)
    with pytest.raises(f.FocusBlocked,match='disarmed'):bootstrap.step(deadline)
    assert not api.input and not root.focus_calls


@pytest.mark.parametrize('foreground,inside', [(99,True),(20,False)])
def test_bootstrap_failed_native_focus_keeps_original_deadline_and_observations(monkeypatch,foreground,inside):
    api=API(foreground=99,return_foreground=foreground);api.focus_inside=inside;root=Widget()
    bootstrap=_InertBootstrap(root,api,api.bind_target(10))
    deadline=time.monotonic()+2
    assert not bootstrap.step(deadline);bootstrap.worker.join(timeout=1)
    assert not bootstrap.step(deadline)
    assert bootstrap.last_state==dict(foreground=foreground,focus_inside=inside)
    assert len(api.input)==1 and root.focus_calls==(foreground==20)
    monkeypatch.setattr(time,'monotonic',lambda:deadline)
    with pytest.raises(f.FocusBlocked,match='deadline'):bootstrap.step(deadline)
    assert bootstrap.state=='DISARMED' and not bootstrap.verified and len(api.input)==1


def test_cleanup_runs_all_actions_and_retains_primary_on_diagnostic_failure():
    called=[];primary=AssertionError('original failure')
    def bad_cleanup():called.append('terminate');raise OSError('cleanup fault')
    def bad_publish(errors):called.append('publish');raise OSError('write fault')
    errors=_finish_control(primary,[('terminate',bad_cleanup),('close',lambda:called.append('close'))],bad_publish)
    assert called==['terminate','close','publish'] and len(errors)==2
    assert any('cleanup fault' in n for n in primary.__notes__)
    assert any('write fault' in n for n in primary.__notes__)
    with pytest.raises(RuntimeError,match='evidence incomplete'):
        _finish_control(None,[('close',lambda:called.append('closed again'))],bad_publish)
    assert 'closed again' in called


def _synthetic_result_records(tmp_path,damage=None,failed_return=False):
    import copy
    from xml.etree import ElementTree as E
    node=f.HISTORY+'::test_real_tk_history_parent_grab_focus_return_identity_and_guard[none]'
    events=[dict(event='SendInput',inserted=3),dict(event='ordinary_Tk_focus_set'),dict(event='disarmed')]
    evidence=dict(node=node,target=dict(top=20),precondition_verified=True,state='DISARMED',events=events)
    records={
        'job-verified':dict(nonce='n',pid=42,target=dict(pid=42),exact_job=True),
        'foreign-ready':dict(nonce='n',target=dict(pid=42),bootstrap=dict(verified=True,state='DISARMED',events=[])),
        'subject-ready':dict(nonce='n',driver=copy.deepcopy(evidence),native=dict(foreground=20,focus_inside=True),logical_origin=True,monotonic=1),
        'result':dict(nonce='n',driver=copy.deepcopy(evidence),failed=failed_return,logical_origin=not failed_return,
                      native=dict(foreground=20,focus_inside=True),notes=['observation failed during RESULT'] if failed_return else []),
        'inner-final':dict(nonce='n',errors=[],final_exits=[1],driver=copy.deepcopy(evidence)),
        'return-fault':dict(nonce='n',applied=True,monotonic=2,wrong_focus='.wrong',origin='.origin',
                            mapped=True,focus_requests=1,native=dict(foreground=20,focus_inside=True)),
    }
    if damage=='subject input':records['subject-ready']['driver']['events'][0]['inserted']=2
    if damage=='stale foreground':records['subject-ready']['native']['foreground']=99
    if damage=='after disarming':records['result']['driver']['events'].append(dict(event='SendInput',inserted=3))
    if damage=='cleanup input':records['inner-final']['driver']['events'].append(dict(event='SendInput',inserted=3))
    if damage=='cleanup':records['inner-final']['errors']=['cleanup uncertain']
    if damage=='Job':records['job-verified']['exact_job']=False
    if damage=='wrong phase':records['result']['notes']=['observation failed during PRECONDITION']
    if damage=='native focus':records['result']['native']['focus_inside']=False
    if damage=='fault not applied':records['return-fault']['applied']=False
    if damage=='fault same origin':records['return-fault']['wrong_focus']='.origin'
    if damage=='fault wrong foreground':records['return-fault']['native']['foreground']=99
    if damage=='fault repeated':records['return-fault']['focus_requests']=2
    suite=E.Element('testsuite');case=E.SubElement(suite,'testcase',classname=f.HISTORY[:-3].replace('/','.'),name=node.split('::')[1])
    if damage=='setup':E.SubElement(case,'error',message='setup failure')
    elif failed_return:E.SubElement(case,'failure',message='controlled return failure')
    E.ElementTree(suite).write(tmp_path/'native.xml',encoding='utf-8')
    for name,value in records.items():
        if damage=='missing result' and name=='result':continue
        _control_write(tmp_path,name,value)


@pytest.mark.parametrize('damage', ['subject input','stale foreground','after disarming','cleanup input','cleanup','Job','setup','native focus'])
def test_fixture_result_validation_rejects_incomplete_evidence(tmp_path,damage):
    _synthetic_result_records(tmp_path,damage)
    with pytest.raises(f.FocusBlocked):_validate_control_result(tmp_path,'n',0,False)


def test_defect_control_requires_valid_setup_and_actual_result_failure(tmp_path):
    _synthetic_result_records(tmp_path,'wrong phase',failed_return=True)
    with pytest.raises(f.FocusBlocked,match='RESULT'):_validate_control_result(tmp_path,'n',1,True)


@pytest.mark.parametrize('failed_return',[False,True])
def test_result_protocol_accepts_complete_records_without_claiming_native_execution(tmp_path,failed_return):
    _synthetic_result_records(tmp_path,failed_return=failed_return)
    _validate_control_result(tmp_path,'n',int(failed_return),failed_return)


def _runtime_case(tmp_path):
    import copy
    launcher=tmp_path/'env-python.exe';base=tmp_path/'base-python.exe'
    for path in (launcher,base):path.write_bytes(path.name.encode());path.chmod(0o700)
    facts=dict(executable=str(launcher),base_executable=str(base),prefix=str(tmp_path/'venv'),base_prefix=str(tmp_path/'base'),
        implementation='cpython',version='controlled CPython',version_info=[3,12,0],frozen=False,
        venv_cfg=dict(path=str(tmp_path/'venv/pyvenv.cfg'),sha256='controlled'))
    executable,env,expected=_control_python({'PYTHONPATH':'reviewed-source'},facts=facts,platform='win32',image=str(base))
    expected.update(source=dict(revision='reviewed',files={'reviewed.py':'digest'}),
        dependencies={name:dict(version=version,module_version=version,origin=str(tmp_path/name))
                      for name,version in (('pytest','9.1.1'),('tzdata','2026.5'),('tkcalendar','1.6.1'),('tzlocal','5.4.4'))})
    observed=dict(pid=42,process=dict(pid=42,creation=100,live=True,image=str(base)),python=copy.deepcopy(facts),
        dependencies=copy.deepcopy(expected['dependencies']),node='exact-node',revision='reviewed',files={'reviewed.py':'digest'},
        chronicle=os.path.normcase(str((f.REPO/'src/chronicle/__init__.py').resolve())))
    return executable,env,expected,observed


def test_control_python_venv_uses_base_with_explicit_launcher_and_preserves_environment(tmp_path):
    executable,env,expected,observed=_runtime_case(tmp_path)
    assert executable==expected['python']['base_executable']
    assert env=={'PYTHONPATH':'reviewed-source','__PYVENV_LAUNCHER__':expected['python']['executable']}
    assert _verify_runtime(observed,expected,node='exact-node',pid=42,creation=100)


@pytest.mark.parametrize('platform',['linux','win32'])
def test_control_python_nonvenv_keeps_direct_executable_and_environment(tmp_path,platform):
    _,_,expected,_=_runtime_case(tmp_path);facts=dict(expected['python'])
    facts.update(executable=facts['base_executable'],prefix=facts['base_prefix'],venv_cfg=None)
    original={'PYTHONPATH':'source','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
    executable,env,_=_control_python(original,facts=facts,platform=platform,image=facts['base_executable'])
    assert executable==facts['executable'] and env==original and env is not original
    assert '__PYVENV_LAUNCHER__' not in env


@pytest.mark.parametrize('damage',['missing','directory','not executable','different image','missing cfg','unsupported'])
def test_control_python_refuses_invalid_base_without_fallback(tmp_path,monkeypatch,damage):
    _,_,expected,_=_runtime_case(tmp_path);facts=dict(expected['python']);image=facts['base_executable']
    if damage=='missing':facts['base_executable']=str(tmp_path/'missing.exe')
    if damage=='directory':facts['base_executable']=str(tmp_path)
    if damage=='not executable':monkeypatch.setattr(os,'access',lambda *a:False)
    if damage=='different image':image=facts['executable']
    if damage=='missing cfg':facts['venv_cfg']=dict(error='missing')
    if damage=='unsupported':facts['implementation']='unapproved'
    with pytest.raises((f.FocusBlocked,OSError)):
        _control_python({},facts=facts,platform='win32',image=image)


@pytest.mark.parametrize('damage',['prefix','base prefix','executable','image','pytest','tzdata','missing dependency',
                                  'source','node','nonce','pid','HWND owner','creation','Job','exit'])
def test_runtime_probe_gate_refuses_inexact_environment_and_ownership(tmp_path,damage):
    _,_,expected,observed=_runtime_case(tmp_path)
    launch=dict(pid=42,creation=100);target=dict(pid=42)
    membership=dict(observed['process'],member=True)
    record=dict(nonce='n',role='subject',verified=True,observed=observed)
    if damage=='prefix':observed['python']['prefix']='another-env'
    if damage=='base prefix':observed['python']['base_prefix']='another-base'
    if damage=='executable':observed['python']['executable']=observed['python']['base_executable']
    if damage=='image':observed['process']['image']=observed['python']['executable']
    if damage=='pytest':observed['dependencies']['pytest']['origin']='another-pytest'
    if damage=='tzdata':observed['dependencies']['tzdata']['version']='2026.4'
    if damage=='missing dependency':
        observed['dependencies']['tzdata']={'error':'missing'}
        expected['dependencies']['tzdata']={'error':'missing'}
    if damage=='source':observed['revision']='unreviewed'
    if damage=='node':observed['node']='other-node'
    if damage=='nonce':record['nonce']='other'
    if damage=='pid':launch['pid']=43
    if damage=='HWND owner':target['pid']=43
    if damage=='creation':launch['creation']=101
    if damage=='Job':membership['member']=False
    if damage=='exit':membership['live']=False
    with pytest.raises(f.FocusBlocked):
        _accept_runtime(record,expected,'n','subject','exact-node',launch,membership,target)


def test_runtime_probe_records_failed_identity_and_preserves_primary_on_write_fault(tmp_path,monkeypatch):
    _,_,expected,observed=_runtime_case(tmp_path)
    observed['python']['prefix']='wrong-env'
    config=dict(nonce='n',runtime=expected)
    monkeypatch.setattr(sys.modules[__name__],'_runtime_observation',lambda *a:observed)
    with pytest.raises(f.FocusBlocked,match='environment'):
        _runtime_probe(tmp_path,'subject',None,config,time.monotonic()+2,'exact-node')
    record=_control_read(tmp_path,'subject-runtime')
    assert not record['verified'] and record['observed']['python']['prefix']=='wrong-env'
    def broken(*args):raise OSError('diagnostic write fault')
    monkeypatch.setattr(sys.modules[__name__],'_control_write',broken)
    with pytest.raises(f.FocusBlocked) as failed:
        _runtime_probe(tmp_path,'inert',None,config,time.monotonic()+2,'exact-node')
    assert any('diagnostic write fault' in note for note in failed.value.__notes__)


def test_runtime_probe_cannot_extend_setup_deadline(tmp_path,monkeypatch):
    _,_,expected,observed=_runtime_case(tmp_path)
    deadline=time.monotonic()
    monkeypatch.setattr(sys.modules[__name__],'_runtime_observation',lambda *a:observed)
    with pytest.raises(f.FocusBlocked,match='deadline'):
        _runtime_probe(tmp_path,'inert',None,dict(nonce='n',runtime=expected),deadline,'exact-node')
    assert not _control_read(tmp_path,'inert-runtime')['verified']


def test_runtime_observation_preserves_partial_facts_when_native_query_is_denied(monkeypatch):
    def denied(*args):raise f.FocusBlocked('native image denied')
    monkeypatch.setattr(sys.modules[__name__],'_process_stamp',denied)
    actual=_runtime_observation(None,time.monotonic()+2,'exact-node')
    assert actual['pid']==os.getpid() and actual['python']==_python_facts()
    assert 'native image denied' in actual['errors']['process'] and 'dependencies' in actual
    with pytest.raises(f.FocusBlocked,match='incomplete'):
        _verify_runtime(actual,{},node='exact-node')


def test_portable_control_launch_reports_real_pid_environment_and_source(tmp_path):
    # Real subprocess evidence is separate from native GUI/Job acceptance.
    executable,env,expected=_control_python(dict(os.environ,PYTHONDONTWRITEBYTECODE='1',
        PYTHONPATH=str(f.REPO/'src')))
    context=dict(children=[],streams=[])
    command=[executable,'-B','-c',
        'import os,sys,json,pytest,chronicle;print(json.dumps(dict(pid=os.getpid(),prefix=sys.prefix,executable=sys.executable,source=chronicle.__file__,pytest=pytest.__version__)))']
    child=_launch_control(tmp_path,'n',command,context,time.monotonic(),f.REPO,lambda pid:{},env=env)
    try:assert child.wait(timeout=2)==0
    finally:
        _finish_control(None,[('stop',lambda:child.terminate() if child.poll() is None else None),
            ('reap',lambda:child.wait(timeout=5)),*[(str(i),s.close) for i,s in enumerate(context['streams'])]],lambda errors:None)
    actual=json.loads((tmp_path/'inert-stdout.bin').read_bytes())
    assert actual['pid']==child.pid and actual['prefix']==expected['python']['prefix']
    assert actual['executable']==expected['python']['executable'] and actual['pytest']==pytest.__version__
    assert os.path.realpath(actual['source'])==str((f.REPO/'src/chronicle/__init__.py').resolve())
    assert (tmp_path/'inert-stderr.bin').read_bytes()==b'' and all(s.closed for s in context['streams'])


@pytest.mark.parametrize('failed',[False,True])
def test_native_report_serializes_real_tk_references_without_losing_observations(tmp_path,monkeypatch,failed):
    import tkinter as tk
    import tk_observation as observation
    # Tcl() is windowless, but returns a real Tk object such as grid_info()['in'].
    interpreter=tk.Tcl()
    value,root,widget=driver();run(value,widget)
    state=dict(root=dict(path='.',grid={'in':interpreter}),widgets=[dict(object=widget)],
               observation_errors=[],retained_error=repr(tk.TclError('retained diagnostic')),native=dict(hwnd=20))
    with pytest.raises(TypeError):json.dumps(state)
    monkeypatch.setattr(observation,'snapshot',lambda *args:state)
    primary=AssertionError('actual return failure') if failed else None
    if primary:primary.add_note('observation failed during RESULT')
    context=dict(directory=tmp_path,nonce='n',driver=value,root=root,diagnostic_errors=[])
    _native_report(SimpleNamespace(_f2_control_context=context),SimpleNamespace(when='call',
        excinfo=SimpleNamespace(value=primary) if primary is not None else None))
    result=_control_read(tmp_path,'result')
    assert result['snapshot']==json.loads(json.dumps(state,default=str))
    assert result['snapshot']['root']['grid']['in']==str(interpreter)
    assert result['snapshot']['retained_error']==repr(tk.TclError('retained diagnostic'))
    assert result['failed']==failed and result['logical_origin'] and not context['diagnostic_errors']
    assert context['primary'] is primary and result['native']==value.api.focus_state(value.target)
    # Conversion is local to RESULT; the shared evidence writer stays strict.
    with pytest.raises(TypeError):_control_write(tmp_path,'strict',dict(object=interpreter))


@pytest.mark.parametrize('damage',['observation error','conversion error','write error'])
def test_native_report_diagnostic_failure_stays_visible_and_never_writes_success(tmp_path,monkeypatch,damage):
    import tk_observation as observation
    class Unprintable:
        def __str__(self):raise RuntimeError('actual conversion failure')
    value,root,widget=driver();run(value,widget)
    state=dict(observation_errors=['actual observation failure'] if damage=='observation error' else [])
    if damage=='conversion error':state['object']=Unprintable()
    if damage=='write error':
        def denied(*args):raise OSError('actual evidence write failure')
        monkeypatch.setattr(sys.modules[__name__],'_control_write',denied)
    monkeypatch.setattr(observation,'snapshot',lambda *args:state)
    primary=AssertionError('original RESULT failure')
    context=dict(directory=tmp_path,nonce='n',driver=value,root=root,diagnostic_errors=[])
    item=SimpleNamespace(_f2_control_context=context)
    _native_report(item,SimpleNamespace(when='call',excinfo=SimpleNamespace(value=primary)))
    assert _control_read(tmp_path,'result') is None and context['primary'] is primary
    assert len(context['diagnostic_errors'])==1 and len(primary.__notes__)==1
    # A teardown report cannot replace the missing call evidence.
    _native_report(item,SimpleNamespace(when='teardown',excinfo=None))
    assert _control_read(tmp_path,'result') is None and len(context['diagnostic_errors'])==1


@pytest.mark.parametrize('failed_return',[False,True])
def test_missing_result_record_cannot_qualify(tmp_path,failed_return):
    _synthetic_result_records(tmp_path,'missing result',failed_return=failed_return)
    with pytest.raises(f.FocusBlocked,match='evidence'):
        _validate_control_result(tmp_path,'n',int(failed_return),failed_return)


@pytest.mark.parametrize('damage',['fault not applied','fault same origin','fault wrong foreground','fault repeated'])
def test_negative_control_requires_verified_distinct_one_shot_fault(tmp_path,damage):
    _synthetic_result_records(tmp_path,damage,failed_return=True)
    with pytest.raises(f.FocusBlocked):_validate_control_result(tmp_path,'n',1,True)


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--inert-control':
    raise SystemExit(_inert_main(sys.argv[2]))
