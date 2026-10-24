"""Portable collector contracts; no native Windows/PowerShell claims."""
import importlib.util
import errno
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import zipfile

import pytest

HELPER=Path(__file__).resolve().parents[2]/'scripts/qualification_pytest.py'
spec=importlib.util.spec_from_file_location('chronicle_qualification_tests',HELPER)
q=importlib.util.module_from_spec(spec);sys.modules[spec.name]=q;spec.loader.exec_module(q)


def events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def run_fixture(tmp_path,source,extra=(),scope='Critical',enforce=False,name='fixture tests ü.py'):
    suite=tmp_path/name;suite.write_text(source)
    root=tmp_path/'evidence with spaces ü';root.mkdir()
    args=['-q','-p','no:cacheprovider','-o','addopts=','--basetemp',str(root/'temporary files'),
          '--junitxml',str(root/'junit.xml'),str(suite),*extra]
    code='import sys;sys.path.insert(0,sys.argv[1]);import qualification_pytest as q;raise SystemExit(q.run_pytest(sys.argv[2],sys.argv[3],__import__("json").loads(sys.argv[4]),enforce_manifest='+repr(enforce)+'))'
    command=[sys.executable,'-u','-B','-c',code,str(HELPER.parent),str(root),scope,json.dumps(args)]
    child=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30,
                         env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTEST_ADDOPTS':'','PYTHONIOENCODING':'utf-8'})
    return child,root


def test_collection_reports_parametrization_real_outcomes_and_one_completion(tmp_path):
    child,root=run_fixture(tmp_path,'''
import pytest
@pytest.mark.parametrize('value',[1,2])
def test_pass(value): assert value
def test_fail(): assert False
def test_skip(): pytest.skip('deliberate')
@pytest.mark.xfail(reason='deliberate')
def test_xfail(): assert False
@pytest.mark.xfail(reason='deliberate')
def test_xpass(): pass
@pytest.fixture
def broken(): raise RuntimeError('setup failed')
def test_setup(broken): pass
@pytest.fixture
def cleanup():
 yield
 raise RuntimeError('teardown failed')
def test_teardown(cleanup): pass
''')
    assert child.returncode==1,child.stderr
    log=events(root/'events.jsonl')
    assert log[0]['event']=='collection_start'
    assert next(e for e in log if e['event']=='collection_complete')['selected']==8
    finished=[e for e in log if e['event']=='node_finish']
    assert len(finished)==len({e['nodeid'] for e in finished})==8
    assert finished[-1]['counts']==dict(passed=2,failed=1,skipped=1,xfailed=1,xpassed=1,error=2)
    assert log[-1]['pytest_exit_code']==1
    assert q.junit_status(root/'junit.xml',True)=='complete'
    assert all(e['phase'] in ('setup','call','teardown') for e in log if e['event']=='phase')


def test_deselection_has_selected_totals_and_fixture_manifest(tmp_path):
    child,root=run_fixture(tmp_path,'def test_one(): pass\ndef test_two(): pass\n',('-k','one'))
    assert child.returncode==0,child.stderr
    log=events(root/'events.jsonl')
    assert next(e for e in log if e['event']=='collection_complete')['selected']==1
    assert sum(e['event']=='node_finish' for e in log)==1
    # Explicit plugin manifest audits every node it saw; pytest -k deselection
    # must also be captured in the final deselection record.
    assert (root/'manifest.json').is_file()
    manifest=json.loads((root/'manifest.json').read_text())
    assert sum(row['selected'] for row in manifest)==1
    assert any(row['status']=='NOT RUN' and 'filter' in row['reason'] for row in manifest)


@pytest.mark.parametrize('scope',['Critical','Storage','Extended'])
def test_manifest_excludes_supervised_and_hidden_gui_fixtures(scope):
    node='tests/rewrite/test_interruptions.py::test_genuine_hot_journal_native_startup_preserves_all_committed_evidence[False-store]'
    assert q.selection(scope,node,['request','store','hot_dataset'],())[0]
    assert not q.selection(scope,node,['request','store','connected'],())[0]
    assert not q.selection(scope,'tests/rewrite/test_app.py::test_innocent_name',['root'],())[0]
    assert not q.selection(scope,'tests/rewrite/test_schema.py::test_new_unaudited_test',[],())[0]
    callback='tests/rewrite/'+next(iter(q.CALLBACKS))
    accepted,reason,category=q.selection(scope,callback,['root','connected','tmp_path'],())
    assert accepted==(scope=='Extended')
    if accepted:assert category=='audited-callback' and 'cancel' in reason


def test_real_collected_fixture_closure_blocks_unaudited_autouse(tmp_path):
    child,root=run_fixture(tmp_path,'''
import pytest
@pytest.fixture(autouse=True)
def stealth_dialog(): raise AssertionError('must never execute')
def test_fresh_profile_and_reopen(): pass
''',scope='Storage',enforce=True,name='test_schema.py')
    assert child.returncode==5
    manifest=json.loads((root/'manifest.json').read_text())
    assert not manifest[0]['selected'] and manifest[0]['status']=='NOT RUN'
    assert 'stealth_dialog' in manifest[0]['fixtures']
    assert 'Unaudited fixture closure' in manifest[0]['reason']
    assert 'must never execute' not in child.stdout


def test_unexpected_root_and_dialog_are_obstructions_even_when_caught(tmp_path):
    child,root=run_fixture(tmp_path,'''
import pytest
def test_dialog():
 import tkinter.messagebox as mb
 with pytest.raises(RuntimeError): mb.askyesno('keep?','must never answer')
def test_root():
 import tkinter as tk
 with pytest.raises(RuntimeError): tk.Tk()
''')
    assert child.returncode==0,child.stderr
    blocked=[e for e in events(root/'events.jsonl') if e['event']=='obstructed']
    assert [e['detail'] for e in blocked]==['messagebox','Tk root construction']
    state=q.Progress(0,0)
    for event in blocked:state.accept(event,1)
    assert state.deadline_reason(1,q.LIMITS).startswith('OBSTRUCTED')


def test_audited_local_dialog_double_is_not_global_consent(tmp_path):
    child,root=run_fixture(tmp_path,'''
def test_controlled(monkeypatch):
 import tkinter.filedialog as fd
 monkeypatch.setattr(fd,'asksaveasfilename',lambda **kw:'')
 assert fd.asksaveasfilename()==''
''')
    assert child.returncode==0,child.stderr
    assert not any(e['event']=='obstructed' for e in events(root/'events.jsonl'))


def test_guard_blocks_direct_tcl_dialog_and_loadtk_without_display(tmp_path):
    emitter=q.Events(tmp_path/'events.jsonl');guard=q.DialogGuard(emitter)
    guard.install()
    try:
        import _tkinter
        tcl=_tkinter.create(None,'Fixture','Fixture',False,True,False,False,None)
        with pytest.raises(q.Obstructed):tcl.call('tk_getSaveFile')
        with pytest.raises(q.Obstructed):tcl.eval('tk_messageBox -message Keep')
        with pytest.raises(q.Obstructed):tcl.loadtk()
    finally:guard.restore()
    assert len(events(tmp_path/'events.jsonl'))==3


class FakeClock:
    def __init__(self):self.now=100.0
    def __call__(self):return self.now
    def sleep(self,duration):self.now+=duration;time.sleep(0.001)


class OwnedDouble:
    def __init__(self):
        self.stdout=io.BytesIO('live stdout ü\n'.encode());self.stderr=io.BytesIO(b'live stderr\n')
        self.killed=False;self.closed=False
    def poll(self):return 238 if self.killed else None
    def terminate_owned(self):self.killed=True
    def active_count(self):return 0 if self.killed else 2
    def close(self):self.closed=True


@pytest.mark.parametrize('phase',['collection','setup','call','teardown'])
def test_timeouts_heartbeat_warning_partial_xml_and_bounded_owned_cleanup(tmp_path,phase):
    clock=FakeClock();child=OwnedDouble();output=[];emitter=q.Events(tmp_path/'events.jsonl')
    emitter.emit('collection_start')
    if phase!='collection':
        emitter.emit('collection_complete',selected=1);emitter.emit('node_start',nodeid='test_x')
        emitter.emit('phase',nodeid='test_x',phase=phase)
    (tmp_path/'junit.xml').write_text('<testsuite>')
    result=q.monitor(child,tmp_path,dict(collection=3,test=3,phase=20,warning=1,cleanup=1),
                     clock=clock,sleep=clock.sleep,display=lambda value,**kw:output.append(value))
    assert result['status']=='TIMEOUT' and result['termination_reason']=='TIMEOUT: '+phase
    assert result['pytest_exit_code'] is None and result['process_exit_code']==238
    assert result['cleanup']['verified'] and child.killed and child.closed
    assert result['junit']=='partial/unreadable'
    assert any(line.startswith('WARNING:') for line in output)
    snapshots=[json.loads(line[19:]) for line in output if line.startswith('CHRONICLE_PROGRESS ')]
    assert len(snapshots)>=3 and max(s['elapsed'] for s in snapshots)>=2
    assert snapshots[0]['percent']==(None if phase=='collection' else 0)
    assert (tmp_path/'stdout.log').read_text()=='live stdout ü\n'
    assert (tmp_path/'stderr.log').read_text()=='live stderr\n'


def test_phase_limit_and_owned_window_obstruction_do_not_answer_dialogs(tmp_path):
    clock=FakeClock();child=OwnedDouble()
    child.visible_windows=lambda:[dict(pid=123,window_class='#32770',title='Keep?')]
    result=q.monitor(child,tmp_path,q.LIMITS,clock=clock,sleep=clock.sleep,display=lambda *a,**k:None)
    assert result['status']=='OBSTRUCTED' and child.killed
    assert result['last_event']['event']=='obstructed'
    state=q.Progress(0,0);state.selected=5
    assert state.deadline_reason(5,dict(q.LIMITS,phase=4))=='TIMEOUT: qualification phase'


class PortableOwnedChild:
    """Test-only POSIX session; never a Windows containment fallback."""
    def __init__(self,command):
        self.process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,
                                      env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTEST_ADDOPTS':'','PYTHONIOENCODING':'utf-8'})
        self.stdout,self.stderr=self.process.stdout,self.process.stderr
    def poll(self):return self.process.poll()
    def terminate_owned(self):
        try:os.killpg(self.process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        self.process.wait(timeout=3)
    def active_count(self):return int(self.process.poll() is None)
    def close(self):self.stdout.close();self.stderr.close()


@pytest.mark.skipif(os.name!='posix',reason='Portable POSIX test containment is not Windows Job Object evidence')
def test_real_concurrent_streams_abnormal_exit_and_actual_return_code(tmp_path):
    child=PortableOwnedChild([sys.executable,'-u','-B','-c',
        'import os,sys;os.write(1,b"o"*200000);os.write(2,b"e"*200000);sys.exit(7)'])
    result=q.monitor(child,tmp_path,q.LIMITS,display=lambda *a,**k:None)
    assert result['status']=='FAIL' and result['process_exit_code']==7 and result['pytest_exit_code'] is None
    assert (tmp_path/'stdout.log').stat().st_size==200000
    assert (tmp_path/'stderr.log').stat().st_size==200000
    assert result['cleanup']['streams_drained'] and result['junit']=='missing'


@pytest.mark.skipif(os.name!='posix',reason='Portable POSIX child death is separate from Windows containment')
def test_owned_child_descendant_is_terminated_without_touching_unrelated_process(tmp_path):
    pidfile=tmp_path/'child.pid'
    code='import subprocess,sys,time; c=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]);open(sys.argv[1],"w").write(str(c.pid));time.sleep(30)'
    child=PortableOwnedChild([sys.executable,'-u','-B','-c',code,str(pidfile)])
    unrelated=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(30)'])
    try:
        result=q.monitor(child,tmp_path,dict(q.LIMITS,collection=1),display=lambda *a,**k:None)
        assert result['status']=='TIMEOUT' and unrelated.poll() is None
        pid=int(pidfile.read_text());proc=Path(f'/proc/{pid}/stat')
        deadline=time.monotonic()+2
        while proc.exists() and proc.read_text().split()[2]!='Z' and time.monotonic()<deadline:time.sleep(.02)
        assert not proc.exists() or proc.read_text().split()[2]=='Z'
    finally:unrelated.terminate();unrelated.wait(timeout=3)


@pytest.mark.parametrize('with_link',[False,True])
def test_zip_membership_includes_hidden_and_excludes_links_and_self(tmp_path,with_link):
    root=tmp_path/'evidence';root.mkdir();(root/'.hidden').write_text('private fixture')
    (root/'summary.json').write_text('{}');outside=tmp_path/'unknown';outside.write_text('not ours')
    if with_link:
        try:(root/'alias').symlink_to(outside)
        except NotImplementedError as exc:pytest.skip(f'Native symlink setup unavailable: {exc}')
        except OSError as exc:
            if exc.errno in (errno.EPERM,errno.EACCES,errno.ENOSYS,errno.ENOTSUP) or getattr(exc,'winerror',None)==1314:
                pytest.skip(f'Native symlink setup unavailable: {exc}')
            raise
    archive=q.archive_evidence(root)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist())=={'.hidden','summary.json','archive-members.json'}
        assert 'unknown' not in z.namelist()
    assert archive.parent==root.parent and not archive.is_relative_to(root)
    with pytest.raises(FileExistsError):q.archive_evidence(root)


def test_metadata_probe_uses_only_new_owned_files_and_preserves_raw_fields(tmp_path):
    result=q.metadata_probe(tmp_path)
    assert result['status']=='OBSERVED'
    log=events(tmp_path/'metadata.jsonl')
    assert any(e.get('label')=='readonly after close' for e in log)
    assert any(e.get('label')=='writable after fsync' for e in log)
    mutations=[e for e in log if e['event']=='observation'][-2:]
    before,after=(e['observations']['lstat'] for e in mutations)
    assert before['st_size']==after['st_size'] and before['st_mtime_ns']==after['st_mtime_ns']
    assert mutations[0]['sha256']!=mutations[1]['sha256']
    with pytest.raises(FileExistsError):q.metadata_probe(tmp_path)


def git(repo,*args):
    return subprocess.run(['git','-C',str(repo),*args],text=True,capture_output=True,check=True).stdout.strip()


@pytest.fixture
def source_repo(tmp_path):
    repo=tmp_path/'source';repo.mkdir();git(repo,'init')
    for path in ('run_chronicle.py','scripts/qualify_windows.ps1','scripts/qualification_pytest.py','tests/rewrite/placeholder'):
        p=repo/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
    git(repo,'add','.');git(repo,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-m','Fixture')
    return repo


def test_dirty_source_and_expected_revision_fail_without_running_tests(source_repo):
    head=q.checked_source(source_repo)['revision']
    assert q.checked_source(source_repo,head[:12])['revision']==head
    with pytest.raises(RuntimeError,match='mismatch'):q.checked_source(source_repo,'0'*40)
    (source_repo/'unrelated').write_text('preserve')
    with pytest.raises(RuntimeError,match='dirty'):q.checked_source(source_repo)
    assert (source_repo/'unrelated').read_text()=='preserve'


def test_missing_dependency_is_blocked_with_evidence_and_no_test_process(source_repo,tmp_path,monkeypatch):
    root=tmp_path/'evidence';root.mkdir()
    q.write_json(root/'collector-owner.json',dict(kind='Chronicle qualification',root=str(root),id='d3e40067-6166-49bd-b199-285303dce545'))
    monkeypatch.setattr(q,'runtime_evidence',lambda:(_ for _ in ()).throw(ModuleNotFoundError('pytest prerequisite unavailable')))
    monkeypatch.setattr(q,'WindowsChild',lambda *a:pytest.fail('must not launch tests'))
    assert q.collect(source_repo,root,'Critical',None,q.LIMITS)==4
    result=json.loads((root/'summary.json').read_text())
    assert result['status']=='BLOCKED' and result['pytest_exit_code'] is None
    assert 'prerequisite unavailable' in result['error']
    assert Path(str(root)+'.zip').exists()


def test_unsafe_output_never_receives_even_failure_receipt(source_repo,tmp_path):
    root=tmp_path/'unknown';root.mkdir();(root/'chronicle.sqlite3').write_bytes(b'preserve')
    before={p.name:p.read_bytes() for p in root.iterdir()}
    assert q.collect(source_repo,root,'Critical',None,q.LIMITS)==4
    assert before=={p.name:p.read_bytes() for p in root.iterdir()}


def test_duplicate_finish_and_partial_event_lines_cannot_inflate_counts(tmp_path):
    emitter=q.Events(tmp_path/'events.jsonl')
    plugin=q.QualificationPlugin(emitter,tmp_path,'Critical',enforce_manifest=False)
    plugin.reports['node']=[dict(phase='call',outcome='passed',wasxfail=None)]
    plugin.pytest_runtest_logfinish('node',None);plugin.pytest_runtest_logfinish('node',None)
    log,offset=q.read_events(emitter.path,0)
    assert len(log)==1 and log[0]['completed']==1 and log[0]['counts']=={'passed':1}
    with emitter.path.open('ab') as stream:stream.write(b'{"event":')
    assert q.read_events(emitter.path,offset)==([],offset)


def test_cancellation_and_cleanup_failure_preserve_context(tmp_path):
    (tmp_path/'cancel.request').write_text('operator')
    child=OwnedDouble()
    def close():raise OSError('close cleanup failed')
    child.close=close
    result=q.monitor(child,tmp_path,q.LIMITS,display=lambda *a,**k:None)
    assert result['status']=='CANCELLED' and result['termination_reason']=='CANCELLED by operator'
    assert result['pytest_exit_code'] is None and not result['cleanup']['verified']
    assert 'close cleanup failed' in result['cleanup']['close_error']


@pytest.mark.skipif(os.name!='posix',reason='Portable monitored success is not Windows Job Object evidence')
def test_real_pytest_success_progress_and_exact_exit_through_monitor(tmp_path):
    suite=tmp_path/'small ü.py';suite.write_text('def test_one(): print("live body")\n')
    args=['-q','-s','-p','no:cacheprovider','-o','addopts=','--junitxml',str(tmp_path/'junit.xml'),str(suite)]
    code='import sys;sys.path.insert(0,sys.argv[1]);import qualification_pytest as q;raise SystemExit(q.run_pytest(sys.argv[2],"Critical",__import__("json").loads(sys.argv[3]),enforce_manifest=False))'
    child=PortableOwnedChild([sys.executable,'-u','-B','-c',code,str(HELPER.parent),str(tmp_path),json.dumps(args)])
    result=q.monitor(child,tmp_path,q.LIMITS,display=lambda *a,**k:None)
    assert result['status']=='PASS' and result['process_exit_code']==result['pytest_exit_code']==0
    assert result['progress']['completed']==result['progress']['selected']==1
    assert result['progress']['counts']=={'passed':1} and result['junit']=='complete'
    assert 'live body' in (tmp_path/'stdout.log').read_text()


def test_native_containment_is_not_silently_substituted_on_linux():
    if os.name=='nt':pytest.skip('Native Job Object execution requires approved isolated Windows run')
    with pytest.raises(RuntimeError,match='native Windows'):q.WindowsChild([],Path.cwd(),{})


def test_powershell_entry_static_contract_not_native_execution():
    text=(HELPER.parent/'qualify_windows.ps1').read_text()
    assert "[string]$Scope = 'MetadataProbe'" in text
    assert 'ReadLineAsync()' in text and 'Write-Progress' in text and 'Heartbeat:' in text
    assert 'Out-File' not in text and 'ExecutionPolicy' not in text
    assert "'--defer-archive'" in text and 'ReparsePoint' in text
    assert 'Kill()' in text and 'Stop-Process' not in text


def test_dynamic_fixture_requests_cannot_bypass_reviewed_closure(tmp_path):
    child,root=run_fixture(tmp_path,'''
import pytest
@pytest.fixture
def stealth(): raise AssertionError('unreviewed body must not execute')
def test_fresh_profile_and_reopen(request): request.getfixturevalue('stealth')
''',scope='Storage',enforce=True,name='test_schema.py')
    assert child.returncode==1
    assert any(e['event']=='obstructed' and e['detail']=='Unaudited dynamic fixture stealth'
               for e in events(root/'events.jsonl'))
    assert 'AssertionError: unreviewed body' not in child.stdout


@pytest.mark.skipif(os.name!='posix',reason='Actual portable pytest timeouts are not native Windows containment evidence')
@pytest.mark.parametrize('phase',['collection','setup','call','teardown'])
def test_actual_hung_pytest_boundary_is_observed_and_terminated(tmp_path,phase):
    source={
        'collection':'import time;time.sleep(30)\ndef test_hang():pass',
        'setup':'import pytest,time\n@pytest.fixture\ndef slow():time.sleep(30)\ndef test_hang(slow):pass',
        'call':'import time\ndef test_hang():time.sleep(30)',
        'teardown':'import pytest,time\n@pytest.fixture\ndef slow():\n yield\n time.sleep(30)\ndef test_hang(slow):pass',
    }[phase]
    suite=tmp_path/'hang.py';suite.write_text(source)
    args=['-q','-p','no:cacheprovider','-o','addopts=','--junitxml',str(tmp_path/'junit.xml'),str(suite)]
    code='import sys;sys.path.insert(0,sys.argv[1]);import qualification_pytest as q;raise SystemExit(q.run_pytest(sys.argv[2],"Critical",__import__("json").loads(sys.argv[3]),enforce_manifest=False))'
    child=PortableOwnedChild([sys.executable,'-u','-B','-c',code,str(HELPER.parent),str(tmp_path),json.dumps(args)])
    result=q.monitor(child,tmp_path,dict(collection=2,test=1,phase=10,warning=1,cleanup=2),display=lambda *a,**k:None)
    assert result['status']=='TIMEOUT' and result['termination_reason']=='TIMEOUT: '+phase
    assert result['pytest_exit_code'] is None and result['cleanup']['verified']
    assert result['junit']=='missing'


def test_archive_failure_retains_original_evidence(source_repo,tmp_path,monkeypatch):
    root=tmp_path/'evidence';root.mkdir()
    q.write_json(root/'collector-owner.json',dict(kind='Chronicle qualification',root=str(root),id='d3e40067-6166-49bd-b199-285303dce545'))
    monkeypatch.setattr(q,'runtime_evidence',lambda:(_ for _ in ()).throw(ImportError('missing prerequisite')))
    monkeypatch.setattr(q,'archive_evidence',lambda *a:(_ for _ in ()).throw(OSError('zip denied')))
    assert q.collect(source_repo,root,'Critical',None,q.LIMITS)==4
    assert json.loads((root/'summary.json').read_text())['status']=='ERROR'
    assert (root/'source.json').is_file() and (root/'collector-error.txt').is_file()
    assert 'zip denied' in (root/'archive-error.json').read_text()


def test_frozen_function_manifest_references_actual_source():
    import ast
    base=HELPER.parents[1]/'tests/rewrite'
    for module,names in {**q.STORAGE,**q.ADDITIONAL}.items():
        declared={n.name for n in ast.parse((base/module).read_bytes()).body if isinstance(n,ast.FunctionDef)}
        assert set(names)<=declared
    for key in q.CALLBACKS:
        module,name=key.split('::')
        declared={n.name for n in ast.parse((base/module).read_bytes()).body if isinstance(n,ast.FunctionDef)}
        assert name in declared


def test_prerequisite_evidence_records_missing_package_without_user_tk_profile(monkeypatch):
    import tkinter
    monkeypatch.setattr(tkinter.Tk,'readprofile',lambda *a:pytest.fail('must not read user Tk profile'))
    version=q.importlib.metadata.version
    def missing(name):
        if name=='tzdata':raise q.importlib.metadata.PackageNotFoundError('tzdata')
        return version(name)
    monkeypatch.setattr(q.importlib.metadata,'version',missing)
    result=q.runtime_evidence()
    assert result['python'] and result['sqlite'] and result['strict_supported'] and result['tcl']
    assert result['errors'] and 'tzdata' in result['errors'][0]
    assert result['tk_desktop'].startswith('NOT RUN')


def test_archive_cli_uses_same_membership_contract_as_operator(tmp_path):
    root=tmp_path/'evidence space ü';root.mkdir()
    q.write_json(root/'collector-owner.json',dict(kind='Chronicle qualification',root=str(root),id='d3e40067-6166-49bd-b199-285303dce545'))
    (root/'.hidden').write_text('retain')
    result=subprocess.run([sys.executable,'-B',str(HELPER),'--archive-evidence',str(root)],capture_output=True,text=True,encoding='utf-8',timeout=10,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    assert result.returncode==0,result.stderr
    with zipfile.ZipFile(Path(str(root)+'.zip')) as archive:
        assert set(archive.namelist())=={'collector-owner.json','.hidden','archive-members.json'}


@pytest.mark.parametrize('scope',['Critical','Storage','Extended'])
def test_actual_rewrite_collection_audits_selected_and_deferred_fixture_graphs(tmp_path,scope):
    repo=HELPER.parents[1]
    code='import sys;sys.path.insert(0,sys.argv[1]);import qualification_pytest as q;raise SystemExit(q.run_pytest(sys.argv[2],sys.argv[3],["--collect-only","-q","-p","no:cacheprovider","-o","addopts=","tests/rewrite/"]))'
    result=subprocess.run([sys.executable,'-B','-c',code,str(HELPER.parent),str(tmp_path),scope],cwd=repo,
                          capture_output=True,text=True,encoding='utf-8',timeout=30,
                          env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTEST_ADDOPTS':'','PYTHONIOENCODING':'utf-8'})
    assert result.returncode==0,result.stdout+result.stderr
    manifest=json.loads((tmp_path/'manifest.json').read_text())
    selected=[row for row in manifest if row['selected']]
    assert len(selected)>40
    assert all(row['fixture_definitions'] is not None for row in selected)
    assert all(not ({'click','keyboard'} & set(row['fixtures'])) for row in selected)
    callbacks=[row for row in selected if row['category']=='audited-callback']
    assert len(callbacks)==(2 if scope=='Extended' else 0)
    assert all(row['reason'] and row['status']=='NOT RUN' for row in manifest if not row['selected'])
    complete=next(e for e in events(tmp_path/'events.jsonl') if e['event']=='collection_complete')
    assert complete['selected']==len(selected)


@pytest.mark.skipif(os.name!='posix',reason='Portable incomplete-session test is not Windows containment evidence')
def test_zero_exit_cannot_claim_success_for_unfinished_selected_nodes(tmp_path):
    emitter=q.Events(tmp_path/'events.jsonl')
    emitter.emit('collection_complete',selected=3)
    emitter.emit('session_finish',pytest_exit_code=0,completed=0,counts={})
    child=PortableOwnedChild([sys.executable,'-B','-c','pass'])
    result=q.monitor(child,tmp_path,q.LIMITS,display=lambda *a,**k:None)
    assert result['process_exit_code']==result['pytest_exit_code']==0
    assert result['status']=='FAIL' and result['progress']['completed']==0


def test_existing_basetemp_is_never_passed_to_pytest_for_deletion(tmp_path):
    temporary=tmp_path/'pytest-temp';temporary.mkdir();(temporary/'keep').write_text('preserve')
    result=subprocess.run([sys.executable,'-B',str(HELPER),'--pytest-worker',str(tmp_path),'--scope','Critical'],
                          capture_output=True,text=True,encoding='utf-8',timeout=10,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    assert result.returncode!=0
    assert (temporary/'keep').read_text()=='preserve'
    assert any(e['event']=='obstructed' for e in events(tmp_path/'events.jsonl'))
    assert not (tmp_path/'junit.xml').exists()


@pytest.mark.skipif(not os.environ.get('DISPLAY'),reason='Real-Tk callback plugin evidence requires a usable display; Windows is separate')
def test_real_tk_audited_callback_plugin_runs_only_controlled_dialog_paths(tmp_path):
    repo=HELPER.parents[1];home=tmp_path/'home';home.mkdir()
    nodes=['tests/rewrite/test_backup_ui.py::'+key.split('::')[1] for key in q.CALLBACKS]
    args=['-q','-p','no:cacheprovider','-o','addopts=','--junitxml',str(tmp_path/'junit.xml'),*nodes]
    code='import sys;sys.path.insert(0,sys.argv[1]);import qualification_pytest as q;raise SystemExit(q.run_pytest(sys.argv[2],"Extended",__import__("json").loads(sys.argv[3])))'
    result=subprocess.run([sys.executable,'-u','-B','-c',code,str(HELPER.parent),str(tmp_path),json.dumps(args)],cwd=repo,
                          capture_output=True,text=True,encoding='utf-8',timeout=30,
                          env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTEST_ADDOPTS':'','PYTHONIOENCODING':'utf-8','HOME':str(home),'USERPROFILE':str(home)})
    assert result.returncode==0,result.stdout+result.stderr
    log=events(tmp_path/'events.jsonl')
    assert sum(e['event']=='node_finish' for e in log)==2
    assert log[-1]['counts']=={'passed':2}
    assert not any(e['event']=='obstructed' for e in log)
