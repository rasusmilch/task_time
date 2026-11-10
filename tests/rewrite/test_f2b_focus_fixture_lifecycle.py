"""Portable generated-fixture lifecycle proof; no native control/input evidence."""
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
from xml.etree import ElementTree

import pytest

import test_win32_focus as controls


@pytest.mark.parametrize('role', ['historical-schema3', 'production-schema4'])
def test_exact_generated_control_dependency_and_hash_binding(role, tmp_path):
    source = controls._native_control_plugin(role)
    compile(source, 'native_focus_control.py', 'exec')
    tree = ast.parse(source)
    fixture = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    expected = ['root', 'monkeypatch', 'request']
    if role == 'production-schema4': expected.append('ordinary')
    assert [a.arg for a in fixture.args.args] == expected
    assert ast.unparse(fixture.decorator_list[0]) == 'pytest.fixture(autouse=True)'
    assert ast.unparse(fixture.body[0]) == 'yield from _controlled_origin(root, monkeypatch, request)'
    assert [n.name for n in tree.body if isinstance(n, ast.FunctionDef)] == ['controlled_origin']
    assert 'pytest_runtest_makereport = pytest.hookimpl(tryfirst=True)(_native_report)' in source
    assert source == controls._native_control_plugin(role)
    path = tmp_path/'native_focus_control.py';path.write_text(source, encoding='utf-8')
    assert path.read_bytes() == source.encode('utf-8')
    # The enclosing native launcher uses this generator and hashes its actual file.
    launcher = inspect.getsource(controls.test_native_ordinary_activation_and_independent_modal_return_control)
    assert "plugin.write_text(_native_control_plugin(subject_role), encoding='utf-8')" in launcher
    assert "plugin_sha256=hashlib.sha256(plugin.read_bytes()).hexdigest()" in launcher
    assert hashlib.sha256(path.read_bytes()).hexdigest() == hashlib.sha256(source.encode('utf-8')).hexdigest()


@pytest.mark.parametrize('role', [None, '', 'production-schema4-suffix', 'historical-schema3-suffix'])
def test_generated_control_refuses_unknown_role(role):
    with pytest.raises(controls.f.FocusBlocked, match='Unapproved native-control subject role'):
        controls._native_control_plugin(role)


class LifecycleProbe:
    """Disposable-child observer/body substitute; never loaded by native controls."""
    def __init__(self):
        from chronicle.startup import StartupWindow
        self.role = os.environ['CHRONICLE_LIFECYCLE_ROLE']
        self.negative = os.environ['CHRONICLE_LIFECYCLE_NEGATIVE'] == 'True'
        self.output = Path(os.environ['CHRONICLE_LIFECYCLE_EVIDENCE'])
        self.events = [];self.flows = [];self.root = self.ordinary = self.connected = None
        self.observations = {}
        self.worker = self.app = self.wrong = None
        self.original_init = StartupWindow.__init__
        self.original_body = controls._controlled_origin
        probe = self
        def observe_startup(flow, root, **kwargs):
            assert root is probe.root
            probe.observations['startup_root_id'] = id(root)
            probe.events.append('startup_enter')
            probe.original_init(flow, root, **kwargs)
            assert flow.frame.winfo_manager() == 'pack'
            probe.observations['startup_frame_manager'] = flow.frame.winfo_manager()
            probe.events.append('startup_packed');probe.flows.append(flow)
        StartupWindow.__init__ = observe_startup
        # Substitution precedes importing the exact generated plugin's alias.
        controls._controlled_origin = self.prepare

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_setup(self, fixturedef, request):
        outcome = yield
        if fixturedef.argname not in ('root', 'ordinary', 'connected'): return
        result = outcome.get_result()
        if fixturedef.argname == 'root':
            self.root = result;self.events.append('root_ready')
        else:
            setattr(self, fixturedef.argname, result)
            self.events.append(fixturedef.argname+'_ready')

    def prepare(self, root, monkeypatch, request):
        from chronicle.worker import DatabaseWorker
        from chronicle.history_window import widget_live
        from test_app import pump
        assert root is self.root and request.node.nodeid not in controls.f.NODES
        assert not hasattr(root, '_f2_focus_driver')
        self.observations.update(preparation_root_id=id(root),
            tcl=root.tk.call('info', 'patchlevel'), tk=root.tk.call('package', 'require', 'Tk'),
            portable_child_node=request.node.nodeid, native_driver_present=False)
        self.events.append('control_prepare')
        if self.role == 'production-schema4':
            assert self.ordinary is not None, 'ordinary must finish before control preparation'
            app, worker, places = self.ordinary
            assert len(self.flows) == 1
            flow = self.flows[0]
            assert flow.root is root and flow.app is app and flow.worker is worker
            assert not flow.alive and not flow.frame.winfo_exists()
            assert not root.pack_slaves() and root.grid_slaves()
            assert app.root is root and app.worker is worker
            assert type(worker) is DatabaseWorker and worker.is_alive()
            assert [t for t in threading.enumerate() if isinstance(t, DatabaseWorker)] == [worker]
            assert worker.directory == places.folder
            assert app.presentation_profile == 'schema4' and app.candidate_presentation is False
            assert app.state['schema_version'] == 4 and app.state['semantic_verified'] is True
            assert app.state['ordinary_startup_permitted'] is True
            assert app.dataset_id == app.state['dataset_id']
            self.observations.update(app_root_id=id(app.root), worker_id=id(worker),
                worker_type=type(worker).__name__, worker_thread=worker.ident,
                worker_alive=worker.is_alive(), sole_worker=True,
                packed_frame_exists=bool(flow.frame.winfo_exists()),
                packed_root_children=[str(w) for w in root.pack_slaves()],
                grid_root_children=[str(w) for w in root.grid_slaves()],
                schema_version=app.state['schema_version'],
                semantic_verified=app.state['semantic_verified'],
                ordinary_startup_permitted=app.state['ordinary_startup_permitted'],
                presentation_profile=app.presentation_profile, dataset_id=app.dataset_id)
            self.app, self.worker = app, worker
        else:
            assert self.role == 'historical-schema3' and self.ordinary is None and not self.flows
        assert not root.test_errors
        if self.negative:
            self.wrong = ttk.Entry(root, name='f2_wrong_return', takefocus=True)
            self.wrong.grid(row=10, column=0)
            pump(root, lambda: self.wrong.winfo_viewable())
            assert widget_live(self.wrong) and root.nametowidget(str(self.wrong)) is self.wrong
            assert self.wrong.winfo_toplevel() is root and not self.wrong.instate(['disabled'])
            self.wrong.focus_set()  # Portable focusability observation; no native input.
            pump(root, lambda: root.focus_get() is self.wrong)
            self.observations['wrong_target'] = dict(widget=str(self.wrong),
                manager=self.wrong.winfo_manager(), mapped=bool(self.wrong.winfo_ismapped()),
                live=widget_live(self.wrong), enabled=not self.wrong.instate(['disabled']),
                actual_focus=root.focus_get() is self.wrong, root_id=id(self.wrong.winfo_toplevel()))
            self.events.append('wrong_grid_mapped')
        try:
            yield
        finally:
            assert not root.test_errors
            self.events.append('control_teardown')

    def subject(self, app, worker, root):
        from chronicle.worker import DatabaseWorker
        assert root is self.root and app.root is root and app.worker is worker
        assert type(worker) is DatabaseWorker and worker.is_alive()
        assert [t for t in threading.enumerate() if isinstance(t, DatabaseWorker)] == [worker]
        assert not root.test_errors
        if self.role == 'production-schema4':
            assert self.ordinary[:2] == (app, worker) and self.connected is None
        else:
            assert self.ordinary is None and not self.flows
            assert app.presentation_profile == 'schema3' and worker.schema_version == 3
        assert (self.wrong is not None) == self.negative
        if self.wrong is not None:
            assert self.wrong is not app.tree and self.wrong.winfo_ismapped()
        self.app, self.worker = app, worker
        self.events.append('subject_call')

    def pytest_sessionfinish(self, session, exitstatus):
        from chronicle.worker import DatabaseWorker
        try: root_live = bool(self.root and self.root.winfo_exists())
        except tk.TclError: root_live = False
        value = dict(evidence_kind='PORTABLE_FIXTURE_LIFECYCLE_NOT_NATIVE', role=self.role,
            failed_return=self.negative, events=self.events, pytest_exit=int(exitstatus),
            startup_count=len(self.flows), root_disposed=not root_live,
            worker_stopped=self.worker is not None and not self.worker.is_alive(),
            remaining_workers=[t.name for t in threading.enumerate() if isinstance(t, DatabaseWorker)],
            callbacks=[repr(e[1]) for e in getattr(self.root, 'test_errors', [])],
            pid=os.getpid(), schema_version=None if self.worker is None else self.worker.schema_version,
            dataset_id=None if self.app is None else self.app.dataset_id)
        value['observations'] = self.observations
        self.output.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')

    def pytest_unconfigure(self, config):
        from chronicle.startup import StartupWindow
        StartupWindow.__init__ = self.original_init
        controls._controlled_origin = self.original_body


@pytest.mark.parametrize('role', ['historical-schema3', 'production-schema4'])
@pytest.mark.parametrize('negative', [False, True])
def test_real_tk_generated_control_fixture_handoff_and_role_isolation(tmp_path, role, negative):
    if sys.platform == 'linux' and not os.environ.get('DISPLAY'):
        pytest.skip('Managed Tk display required for portable fixture-lifecycle proof; native controls NOT RUN')
    wm = {}
    if sys.platform == 'linux':
        check = subprocess.run(['xprop','-root','_NET_SUPPORTING_WM_CHECK'], capture_output=True, text=True, timeout=5)
        assert check.returncode == 0 and 'window id #' in check.stdout, 'Managed window manager required'
        identity = subprocess.run(['xprop','-id',check.stdout.split('#')[-1].strip(),'_NET_WM_NAME'], capture_output=True, text=True, timeout=5)
        assert identity.returncode == 0 and ' = ' in identity.stdout
        wm = dict(root=check.stdout, manager=identity.stdout)
    repo = controls.f.REPO
    source = controls._native_control_plugin(role)
    plugin = tmp_path/'native_focus_control.py';plugin.write_text(source, encoding='utf-8')
    observer = tmp_path/'fixture_lifecycle_probe.py'
    observer.write_text('from test_f2b_focus_fixture_lifecycle import LifecycleProbe\n'
        'probe = LifecycleProbe()\n'
        'pytest_fixture_setup = probe.pytest_fixture_setup\n'
        'pytest_sessionfinish = probe.pytest_sessionfinish\n'
        'pytest_unconfigure = probe.pytest_unconfigure\n', encoding='utf-8')
    subject = tmp_path/'test_portable_subject.py'
    fixture = 'ordinary' if role == 'production-schema4' else 'connected'
    subject.write_text('from test_app import root, connected\nfrom test_runtime4_ui import ordinary\n'
        'from test_timesheet_save_ui import exit_settled\nimport fixture_lifecycle_probe as observation\n'
        f'def test_portable_lifecycle({fixture}, root):\n'
        f'    app, worker, extra = {fixture}\n'
        '    observation.probe.subject(app, worker, root)\n'
        '    app.request_close()\n    exit_settled(app)\n'
        '    assert not app.alive and app._worker_stopped\n', encoding='utf-8')
    output = tmp_path/'lifecycle.json'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
        PYTHONPATH=os.pathsep.join([str(tmp_path),str(repo/'tests/rewrite'),str(repo/'src')]),
        CHRONICLE_LIFECYCLE_ROLE=role, CHRONICLE_LIFECYCLE_NEGATIVE=str(negative),
        CHRONICLE_LIFECYCLE_EVIDENCE=str(output))
    env.pop('PYTEST_ADDOPTS', None);env.pop('PYTEST_PLUGINS', None);env.pop('F2_CONTROL_DIR', None)
    command = [sys.executable, '-B', '-m', 'pytest', '-q', '-ra', '-p', 'no:cacheprovider', '-o', 'addopts=',
        '-p', 'fixture_lifecycle_probe', '-p', 'native_focus_control', '-c', str(repo/'pyproject.toml'),
        '--rootdir', str(repo), str(subject), '--basetemp', str(tmp_path/'child-basetemp'),
        '--junitxml', str(tmp_path/'child.xml')]
    result = subprocess.run(command, cwd=repo, env=env, capture_output=True, timeout=30)
    (tmp_path/'stdout.bin').write_bytes(result.stdout);(tmp_path/'stderr.bin').write_bytes(result.stderr)
    (tmp_path/'command.json').write_text(json.dumps(dict(command=command, exit_code=result.returncode,
        cwd=str(repo), DISPLAY=env.get('DISPLAY'), WM=wm, role=role, failed_return=negative,
        plugin_sha256=hashlib.sha256(plugin.read_bytes()).hexdigest(),
        environment={k:env.get(k) for k in ('PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTEST_DISABLE_PLUGIN_AUTOLOAD',
            'CHRONICLE_LIFECYCLE_ROLE','CHRONICLE_LIFECYCLE_NEGATIVE','CHRONICLE_LIFECYCLE_EVIDENCE')}), indent=2)+'\n', encoding='utf-8')
    assert result.returncode == 0, result.stdout.decode('utf-8')+result.stderr.decode('utf-8')
    xml = ElementTree.parse(tmp_path/'child.xml')
    assert len(list(xml.iter('testcase'))) == 1
    assert not any(list(xml.iter(tag)) for tag in ('failure', 'error', 'skipped'))
    value = json.loads(output.read_text(encoding='utf-8'))
    assert value['role'] == role and value['failed_return'] is negative and value['pytest_exit'] == 0
    assert value['root_disposed'] and value['worker_stopped'] and not value['remaining_workers'] and not value['callbacks']
    events = value['events'];assert events.count('control_prepare') == 1 and events.count('subject_call') == 1
    if role == 'production-schema4':
        assert value['startup_count'] == 1 and value['schema_version'] == 4
        assert events.index('ordinary_ready') < events.index('control_prepare')
        assert events.index('startup_packed') < events.index('ordinary_ready')
    else:
        assert value['startup_count'] == 0 and value['schema_version'] == 3 and 'ordinary_ready' not in events
        assert events.index('control_prepare') < events.index('connected_ready')
    if negative:assert events.index('control_prepare') < events.index('wrong_grid_mapped') < events.index('subject_call')
    else:assert 'wrong_grid_mapped' not in events
