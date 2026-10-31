"""Portable collector contracts; no native Windows/PowerShell claims."""
import importlib.util
import errno
import hashlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import signal
import shutil
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


def process_diagnostic(result):
    # Keep absence explicit rather than masking the real exit with TypeError.
    return dict(command=result.args,exit_code=result.returncode,
                stdout=result.stdout,stderr=result.stderr,diagnostic_path=getattr(result,'diagnostic_path',None))


def run_fixture(tmp_path,source,extra=(),scope='Critical',enforce=False,name='fixture tests ü.py'):
    suite=tmp_path/'tests'/'rewrite'/name
    suite.parent.mkdir(parents=True);suite.write_text(source)
    root=tmp_path/'evidence with spaces ü';root.mkdir()
    args=['-q','-p','no:cacheprovider','-o','addopts=','--basetemp',str(root/'temporary files'),
          '--junitxml',str(root/'junit.xml'),str(suite),*extra]
    code='import sys;sys.path.insert(0,sys.argv[1]);import qualification_pytest as q;raise SystemExit(q.run_pytest(sys.argv[2],sys.argv[3],__import__("json").loads(sys.argv[4]),enforce_manifest='+repr(enforce)+',source_root=sys.argv[5]))'
    command=[sys.executable,'-u','-B','-c',code,str(HELPER.parent),str(root),scope,json.dumps(args),str(tmp_path)]
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
    assert q.validate_test_evidence(root,1,1)['status']=='COMPLETE'
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
    mutations=[next(e for e in log if e.get('label')==label) for label in
               ('before same-size mutation','same-size mutation restored mtime')]
    before,after=(e['observations']['lstat'] for e in mutations)
    assert before['st_size']==after['st_size'] and before['st_mtime_ns']==after['st_mtime_ns']
    assert mutations[0]['sha256']!=mutations[1]['sha256']
    for label in ('same-size mutation open descriptor restored mtime','same-size mutation fresh descriptor'):
        observation=next(e for e in log if e.get('label')==label)['observations']
        assert observation['stat']['st_ino']==observation['fstat']['st_ino']
        assert observation['fstat']['st_size']=='8'
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
    assert result.returncode==0,process_diagnostic(result)
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
    assert result.returncode==0,process_diagnostic(result)
    log=events(tmp_path/'events.jsonl')
    assert sum(e['event']=='node_finish' for e in log)==2
    assert log[-1]['counts']=={'passed':2}
    assert not any(e['event']=='obstructed' for e in log)


def protected_snapshot(path):
    info=path.stat()
    return (path.read_bytes(),info.st_dev,info.st_ino,info.st_mode,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


@pytest.mark.parametrize('kind',['symlink','file','directory','hardlink','dangling'])
def test_reserved_archive_manifest_is_exclusive_and_preserves_outside_sentinel(tmp_path,kind):
    root=tmp_path/'evidence';root.mkdir()
    outside=tmp_path/'outside sentinel';outside.write_bytes(b'unchanged outside')
    before=protected_snapshot(outside)
    reserved=root/'archive-members.json'
    try:
        if kind=='symlink':reserved.symlink_to(outside)
        elif kind=='dangling':reserved.symlink_to(tmp_path/'absent')
        elif kind=='hardlink':os.link(outside,reserved)
        elif kind=='directory':reserved.mkdir()
        else:reserved.write_bytes(b'preexisting record')
    except (OSError,NotImplementedError) as exc:
        if isinstance(exc,NotImplementedError) or getattr(exc,'winerror',None)==1314 or getattr(exc,'errno',None) in (errno.EPERM,errno.EACCES,errno.ENOSYS,errno.ENOTSUP):
            pytest.skip('Native link setup unavailable: '+str(exc))
        raise
    # Creating a hardlink itself can change sentinel ctime: refusal must preserve
    # the state after fixture setup, rather than attributing setup to the archive.
    before=protected_snapshot(outside)
    with pytest.raises((FileExistsError,IsADirectoryError,PermissionError)):
        q.archive_evidence(root)
    assert protected_snapshot(outside)==before
    assert root.is_dir() and reserved.lstat()
    if kind=='file':assert reserved.read_bytes()==b'preexisting record'
    assert not Path(str(root)+'.zip').exists()
    assert not (tmp_path/'absent').exists()


@pytest.mark.parametrize('where',['root','child'])
def test_archive_traversal_errors_are_not_silent_partial_success(tmp_path,monkeypatch,where):
    root=tmp_path/'evidence';root.mkdir();(root/'keep').write_bytes(b'evidence')
    child=root/'unreadable';child.mkdir();(child/'hidden failure evidence').write_bytes(b'keep')
    original=os.scandir
    def denied(path):
        if Path(path)==(root if where=='root' else child):raise PermissionError('controlled enumeration failure')
        return original(path)
    monkeypatch.setattr(q.os,'scandir',denied)
    with pytest.raises(PermissionError,match='controlled enumeration failure'):q.archive_evidence(root)
    assert (root/'keep').read_bytes()==b'evidence'
    assert (child/'hidden failure evidence').read_bytes()==b'keep'
    assert not Path(str(root)+'.zip').exists()


@pytest.fixture
def complete_evidence(tmp_path):
    child,root=run_fixture(tmp_path,'def test_pass(): pass\n')
    assert child.returncode==0,child.stderr
    assert q.validate_test_evidence(root,0,0)['status']=='COMPLETE'
    return root


class CompletedDouble(OwnedDouble):
    def poll(self):return 0


@pytest.mark.parametrize('damage',['missing_xml','truncated_xml','invalid_xml','missing_manifest','invalid_manifest',
                                    'missing_case','wrong_case','wrong_outcome','duplicate_finish','missing_report','partial_event'])
def test_successful_exit_requires_consistent_complete_evidence(complete_evidence,damage):
    root=complete_evidence
    xml=root/'junit.xml';manifest=root/'manifest.json';event_file=root/'events.jsonl'
    if damage=='missing_xml':xml.unlink()
    elif damage=='truncated_xml':xml.write_text('<testsuites><testsuite>')
    elif damage=='invalid_xml':xml.write_text('<not-junit/>')
    elif damage=='missing_manifest':manifest.unlink()
    elif damage=='invalid_manifest':manifest.write_text('{}')
    elif damage in ('missing_case','wrong_case','wrong_outcome'):
        from xml.etree import ElementTree as ET
        tree=ET.parse(xml);suite=tree.getroot().find('testsuite');case=suite.find('testcase')
        if damage=='missing_case':suite.remove(case)
        elif damage=='wrong_case':case.set('name','another test')
        else:ET.SubElement(case,'failure',message='fabricated')
        tree.write(xml)
    else:
        log=events(event_file)
        if damage=='duplicate_finish':log.insert(-1,next(e for e in log if e['event']=='node_finish'))
        elif damage=='missing_report':log=[e for e in log if not (e['event']=='report' and e['phase']=='teardown')]
        event_file.write_text(''.join(json.dumps(e)+'\n' for e in log))
        if damage=='partial_event':
            with event_file.open('a') as stream:stream.write('{"event":')
    result=q.monitor(CompletedDouble(),root,q.LIMITS,display=lambda *a,**kw:None)
    assert result['status']=='EVIDENCE_INCOMPLETE'
    assert result['test_execution_status']=='PASS'
    assert result['process_exit_code']==result['pytest_exit_code']==0
    assert result['evidence']['status']=='EVIDENCE_INCOMPLETE' and result['evidence']['diagnostics']


def test_valid_junit_suite_root_and_prefix_mapping(complete_evidence):
    from xml.etree import ElementTree as ET
    xml=complete_evidence/'junit.xml';tree=ET.parse(xml)
    ET.ElementTree(tree.getroot().find('testsuite')).write(xml)
    assert q.validate_test_evidence(complete_evidence,0,0)['status']=='COMPLETE'


def test_real_junit_double_outcomes_and_parametrized_xfail_xpass(tmp_path):
    child,root=run_fixture(tmp_path,'''
import pytest
@pytest.mark.parametrize('value',[1,2])
def test_pass(value):pass
@pytest.mark.skip(reason='skip')
def test_skip():pass
@pytest.mark.xfail(reason='xfail')
def test_xfail():assert False
@pytest.mark.xfail(reason='xpass')
def test_xpass():pass
@pytest.fixture
def bad_teardown():
 yield
 raise RuntimeError('teardown')
def test_double_failure(bad_teardown):assert False
@pytest.fixture
def both(request):
 request.addfinalizer(lambda: (_ for _ in ()).throw(RuntimeError('cleanup')))
 raise RuntimeError('setup')
def test_two_errors(both):pass
''',extra=('--junitprefix','qualification'))
    assert child.returncode==1,child.stderr
    evidence=q.validate_test_evidence(root,1,1)
    assert evidence['status']=='COMPLETE',evidence
    assert evidence['counts']==dict(passed=2,skipped=1,xfailed=1,xpassed=1,error=2)
    assert len([e for e in events(root/'events.jsonl') if e['event']=='node_finish'])==7


@pytest.mark.parametrize('raw_status',['PASS','FAIL','OBSERVED','CANCELLED'])
@pytest.mark.parametrize('archive_failure',[False,True])
def test_final_delivery_preserves_raw_status_and_agrees_with_exit(tmp_path,monkeypatch,raw_status,archive_failure):
    root=tmp_path/'evidence';root.mkdir()
    raw=dict(status=raw_status,pytest_exit_code=None if raw_status=='OBSERVED' else int(raw_status=='FAIL'))
    q.write_json(root/'collector-result.json',raw)
    before=(root/'collector-result.json').read_bytes()
    if archive_failure:
        def fail(*args):raise TimeoutError('archive exceeded controlled deadline')
        monkeypatch.setattr(q,'archive_evidence',fail)
        with pytest.raises(TimeoutError,match='controlled deadline'):q.finalize_evidence(root,raw)
        code=4
    else:code=q.finalize_evidence(root,raw)
    summary=json.loads((root/'summary.json').read_text())
    result=json.loads((root/'launcher-result.json').read_text())
    assert summary['status']==result['status']
    assert result['exit_code']==code and result['success']==(code==0)
    assert summary['collector_status']==result['collector_status']==raw_status
    assert (root/'collector-result.json').read_bytes()==before
    if archive_failure:
        assert summary['status']=='ERROR' and result['archive_status']=='FAILED_OR_UNVERIFIED'
        assert (root/'archive-error.json').is_file() and root.is_dir()
    else:
        with zipfile.ZipFile(Path(str(root)+'.zip')) as z:
            assert json.loads(z.read('summary.json'))==summary
            assert json.loads(z.read('launcher-result.json'))==result
            assert json.loads(z.read('collector-result.json'))==raw


def test_partial_zip_and_secondary_diagnostic_failure_never_promote_success(tmp_path,monkeypatch):
    root=tmp_path/'evidence';root.mkdir();raw=dict(status='PASS')
    def fail(root,completion):
        Path(str(root)+'.zip').write_bytes(b'partial ZIP')
        raise OSError('primary archive failure')
    original=q.write_json
    def diagnostic(path,value):
        if Path(path).name=='archive-error.json':raise OSError('secondary diagnostic failure')
        return original(path,value)
    monkeypatch.setattr(q,'archive_evidence',fail);monkeypatch.setattr(q,'write_json',diagnostic)
    with pytest.raises(OSError,match='primary archive failure') as caught:q.finalize_evidence(root,raw)
    assert any('secondary diagnostic' in note for note in caught.value.__notes__)
    assert json.loads((root/'launcher-result.json').read_text())['success'] is False
    assert Path(str(root)+'.zip').read_bytes()==b'partial ZIP'


@pytest.mark.parametrize('name',['test-result.json','summary.json','launcher-result.json','collector-result.json','archive-error.json'])
def test_post_test_reserved_json_never_follows_existing_link(tmp_path,name):
    root=tmp_path/'evidence';root.mkdir();outside=tmp_path/'outside';outside.write_bytes(b'protected')
    try:(root/name).symlink_to(outside)
    except (NotImplementedError,OSError) as exc:
        if isinstance(exc,NotImplementedError) or getattr(exc,'winerror',None)==1314 or getattr(exc,'errno',None) in (errno.EPERM,errno.EACCES,errno.ENOSYS,errno.ENOTSUP):pytest.skip(str(exc))
        raise
    before=protected_snapshot(outside)
    with pytest.raises(FileExistsError):q.write_json(root/name,dict(status='PASS'))
    assert protected_snapshot(outside)==before


def test_metadata_only_completion_requires_no_junit_or_test_process(source_repo,tmp_path,monkeypatch):
    root=tmp_path/'probe';root.mkdir()
    q.write_json(root/'collector-owner.json',dict(kind='Chronicle qualification',root=str(root),id='d3e40067-6166-49bd-b199-285303dce545'))
    monkeypatch.setattr(q,'prepare',lambda *a:dict(revision='fixture'))
    monkeypatch.setattr(q,'WindowsChild',lambda *a:pytest.fail('MetadataProbe cannot start pytest'))
    assert q.collect(source_repo,root,'MetadataProbe',None,q.LIMITS)==0
    raw=json.loads((root/'collector-result.json').read_text())
    assert raw['status']=='OBSERVED' and raw['junit'].startswith('NOT APPLICABLE')
    assert not (root/'junit.xml').exists()


def test_powershell_exclusive_creation_and_finalization_static_contract():
    text=(HELPER.parent/'qualify_windows.ps1').read_text()
    save=text.split('function Save-Json',1)[1].split('function New-EvidenceZip',1)[0]
    assert '[IO.FileMode]::CreateNew' in save and 'WriteAllText' not in save
    archive=text.split('function New-EvidenceZip',1)[1].split('function New-PythonEvidenceZip',1)[0]
    assert 'Save-Json $MembershipPath' in archive and 'EnumerateFileSystemEntries' in archive
    assert 'ReparsePoint' in archive and 'catch { $Primary = $_; throw }' in archive
    finish=text.split('function Complete-QualificationEvidence',1)[1].split('\ntry {\n    $Repo =',1)[0]
    assert finish.count('[IO.FileMode]::CreateNew')==2
    assert "archive_status = 'FAILED_OR_UNVERIFIED'" in finish
    assert '$Result.success = $false' in finish and '$Result.exit_code = 4' in finish
    assert finish.index('New-PythonEvidenceZip $Root')<finish.index('Write-JsonRecord $SummaryStream $Summary',finish.index('New-PythonEvidenceZip $Root'))
    assert 'collector-result.json' in text and '--archive-completion' in text
    assert 'Cancellation receipt unavailable; continuing owned cleanup' in text
    assert 'Launcher failure diagnostic also failed' in text
    assert 'Cleanup diagnostic also failed' in text


POWERSHELL=shutil.which('pwsh') or shutil.which('powershell')


def capture_process(command, directory, *, script=None, cwd=None, timeout=20):
    """Test-only observation. Never instrument the script or reinterpret exits."""
    directory=Path(directory)
    diagnostic=directory/'subprocess.json'
    value=dict(command=list(command),executable=command[0],cwd=str(Path(cwd or Path.cwd()).resolve()),
        python=dict(executable=sys.executable,version=sys.version),
        powershell=dict(executable=command[0],runtime_identity='UNVERIFIED; separate native probe required') if script else None,
        started_utc=datetime.now(timezone.utc).isoformat(),timeout_seconds=timeout,timed_out=False,
        script=None,exit_code=None,capture_failures=[])
    if script is not None:
        data=Path(script).read_bytes()
        value['script']=dict(path=str(Path(script).resolve()),sha256=hashlib.sha256(data).hexdigest(),
            encoding='utf-8-sig',bom=data.startswith(b'\xef\xbb\xbf'),bytes=len(data))
    primary=result=None
    stdout=stderr=None
    # Reserve diagnostics before launch; no unknown existing object is replaced.
    try:
        with q.JsonRecord(diagnostic) as record:
            record.write(dict(value,status='STARTING'))
            try:
                result=subprocess.run(command,capture_output=True,cwd=cwd,timeout=timeout)
                stdout,stderr=result.stdout,result.stderr
                value['exit_code']=result.returncode
            except subprocess.TimeoutExpired as exc:
                primary=exc;value['timed_out']=True
                stdout,stderr=exc.stdout,exc.stderr
            except BaseException as exc: primary=exc
            value.update(ended_utc=datetime.now(timezone.utc).isoformat(),
                         process_error=repr(primary) if primary else None)
            def retain(name,data):
                if data is None:
                    value['capture_failures'].append(name+' unavailable despite requested PIPE')
                    return dict(status='ABSENT',bytes=None,raw_file=None,text=None)
                if not isinstance(data,bytes):raise TypeError(name+' capture is not bytes: '+repr(type(data)))
                path=directory/(name+'.bin')
                with path.open('xb') as stream:stream.write(data)
                return dict(status='CAPTURED' if data else 'EMPTY',bytes=len(data),raw_file=str(path),
                            text=data.decode('utf-8',errors='backslashreplace'))
            secondary=[]
            for name,data in (('stdout',stdout),('stderr',stderr)):
                try:value[name]=retain(name,data)
                except BaseException as exc:secondary.append(exc);value['capture_failures'].append(name+': '+repr(exc))
            value['status']='CAPTURE_INCOMPLETE' if value['capture_failures'] else 'CAPTURED'
            try:record.write(value)
            except BaseException as exc:secondary.append(exc)
            if secondary:
                if primary is None:primary=secondary.pop(0)
                for exc in secondary:primary.add_note('Subprocess diagnostic also failed: '+repr(exc))
            if primary is not None:
                primary.add_note('Original subprocess observation: '+repr(value))
                raise primary
    except BaseException as exc:
        exc.add_note('Capture command/result: '+repr(dict(command=command,exit_code=value['exit_code'],
            timed_out=value['timed_out'],diagnostic_path=str(diagnostic))))
        raise
    # Keep the helper's existing text result interface and exact process exit.
    result.stdout=None if stdout is None else stdout.decode('utf-8',errors='backslashreplace')
    result.stderr=None if stderr is None else stderr.decode('utf-8',errors='backslashreplace')
    result.diagnostic_path=str(diagnostic)
    return result


def run_powershell_functions(tmp_path,body):
    prefix=(HELPER.parent/'qualify_windows.ps1').read_text().split('\ntry {\n    $Repo =',1)[0]
    script=tmp_path/'collector functions ü.ps1';script.write_text(prefix+'\n'+body,encoding='utf-8-sig')
    return capture_process([POWERSHELL,'-NoProfile','-NonInteractive','-File',str(script),
                            '-Repo',str(HELPER.parent.parent.resolve())],
                           tmp_path,script=script,timeout=20)


@pytest.mark.skipif(not POWERSHELL,reason='PowerShell unavailable: explicit Repo binding NOT RUN')
def test_actual_powershell_explicit_repo_parameter_binding(tmp_path):
    # Separate binding control: never instrument the eight original fixtures.
    result=run_powershell_functions(tmp_path,
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n"
        "[Console]::Out.WriteLine(($PSBoundParameters.ContainsKey('Repo')))\n"
        "[Console]::Out.WriteLine($Repo)\nexit 0")
    assert result.returncode==0,process_diagnostic(result)
    lines=result.stdout.splitlines()
    assert lines==['True',str(HELPER.parent.parent.resolve())]
    record=json.loads((tmp_path/'subprocess.json').read_text())
    assert record['command'][-2:]==['-Repo',str(HELPER.parent.parent.resolve())]
    assert record['script']['bom'] and record['timeout_seconds']==20


@pytest.mark.skipif(not POWERSHELL,reason='PowerShell unavailable: fallback runtime remains UNVERIFIED')
def test_actual_powershell_fallback_reserved_manifest(tmp_path):
    root=tmp_path/'evidence with spaces ü';root.mkdir()
    reserved=root/'archive-members.json';reserved.write_bytes(b'keep')
    body='$Root = '+"'"+str(root).replace("'","''")+"'\ntry { New-EvidenceZip $Root; exit 0 } catch { exit 4 }"
    result=run_powershell_functions(tmp_path,body)
    assert result.returncode==4,process_diagnostic(result)
    assert reserved.read_bytes()==b'keep' and not Path(str(root)+'.zip').exists()


@pytest.mark.skipif(not POWERSHELL,reason='PowerShell unavailable: launcher failure/runtime checks remain UNVERIFIED')
@pytest.mark.parametrize('fault',['none','python','fallback','timeout','status','cancel'])
def test_actual_powershell_final_status_after_archive_outcome(tmp_path,fault):
    root=tmp_path/'evidence ü';root.mkdir()
    quoted="'"+str(root).replace("'","''")+"'"
    body=f'$Root = {quoted}\n$Python = $null\n$Helper = $null\n'
    if fault in ('python','timeout'):
        body+='$Python = $PSHOME\n$Helper = $PSHOME\nfunction New-PythonEvidenceZip([string]$Root) { throw "controlled Python archive '+fault+'" }\n'
    if fault=='fallback':body+='function New-EvidenceZip([string]$Root,$Completion) { throw "controlled fallback failure" }\n'
    if fault=='status':
        body+='function Write-JsonRecord([IO.Stream]$Stream,$Value) { throw "controlled status finalization failure" }\n'
    failure="'operator cancellation'" if fault=='cancel' else "''"
    body+=f"$Code = Complete-QualificationEvidence $Root @{{status='PASS';pytest_exit_code=0}} 0 {failure} $false\nexit $Code"
    result=run_powershell_functions(tmp_path,body)
    assert result.returncode==(0 if fault=='none' else 4),process_diagnostic(result)
    if fault!='status':
        summary=json.loads((root/'summary.json').read_text())
        final=json.loads((root/'launcher-result.json').read_text())
        assert summary['status']==final['status'] and final['exit_code']==result.returncode
        assert final['success']==(result.returncode==0)


def test_final_status_write_failure_keeps_raw_and_fails_closed(tmp_path,monkeypatch):
    root=tmp_path/'evidence';root.mkdir();raw=dict(status='PASS',pytest_exit_code=0)
    q.write_json(root/'collector-result.json',raw)
    original=q.JsonRecord.write
    failed=False
    def write(record,value):
        nonlocal failed
        if Path(record.stream.name).name=='summary.json' and value.get('archive_status')=='VERIFIED' and not failed:
            failed=True
            raise OSError('controlled final status failure')
        return original(record,value)
    monkeypatch.setattr(q.JsonRecord,'write',write)
    with pytest.raises(OSError,match='controlled final status failure'):q.finalize_evidence(root,raw)
    assert json.loads((root/'collector-result.json').read_text())==raw
    for name in ('summary.json','launcher-result.json'):
        assert json.loads((root/name).read_text())['status']=='ERROR'
    assert json.loads((root/'launcher-result.json').read_text())['exit_code']==4
    # A ZIP may have closed before acknowledgement/status failed. It is retained,
    # never claimed as completed delivery or deleted as a rollback action.
    assert Path(str(root)+'.zip').exists()


def test_exclusive_record_keeps_primary_when_close_also_fails(tmp_path):
    record=q.JsonRecord(tmp_path/'record.json')
    record.stream.close()
    class CloseFailure:
        def close(self):raise OSError('secondary close failure')
    record.stream=CloseFailure()
    with pytest.raises(ValueError,match='primary write failure') as caught:
        with record:raise ValueError('primary write failure')
    assert any('secondary close failure' in note for note in caught.value.__notes__)


@pytest.mark.skipif(not POWERSHELL,reason='PowerShell unavailable: native reserved-link fallback remains UNVERIFIED')
def test_actual_powershell_fallback_manifest_link_preserves_sentinel(tmp_path):
    root=tmp_path/'evidence';root.mkdir();outside=tmp_path/'outside';outside.write_bytes(b'sentinel')
    try:(root/'archive-members.json').symlink_to(outside)
    except (NotImplementedError,OSError) as exc:
        if isinstance(exc,NotImplementedError) or getattr(exc,'winerror',None)==1314 or getattr(exc,'errno',None) in (errno.EPERM,errno.EACCES,errno.ENOSYS,errno.ENOTSUP):pytest.skip(str(exc))
        raise
    before=protected_snapshot(outside)
    body="$Root = '"+str(root).replace("'","''")+"'\ntry { New-EvidenceZip $Root; exit 0 } catch { exit 4 }"
    result=run_powershell_functions(tmp_path,body)
    assert result.returncode==4,process_diagnostic(result)
    assert protected_snapshot(outside)==before and not Path(str(root)+'.zip').exists()


@pytest.mark.skipif(not POWERSHELL,reason='PowerShell unavailable: sequential failed-builder preservation remains UNVERIFIED')
def test_actual_powershell_failed_python_then_failed_fallback_preserves_raw(tmp_path):
    root=tmp_path/'evidence';root.mkdir();raw=dict(status='PASS',pytest_exit_code=0)
    (root/'collector-result.json').write_text(json.dumps(raw))
    body="$Root = '"+str(root).replace("'","''")+"'\n"
    body+='''
$Python = $PSHOME
$Helper = $PSHOME
function New-PythonEvidenceZip([string]$Root) { throw 'primary Python archive failure' }
$Code = Complete-QualificationEvidence $Root @{status='PASS';pytest_exit_code=0} 0 '' $false
# No automatic fallback is performed after possible publication. A later explicit
# attempt must also refuse a reserved-object collision, never erase evidence.
Save-Json (Join-Path $Root 'archive-members.json') @{existing='preserve'}
try { New-EvidenceZip $Root; exit 0 } catch { exit $Code }
'''
    result=run_powershell_functions(tmp_path,body)
    assert result.returncode==4,process_diagnostic(result)
    assert json.loads((root/'collector-result.json').read_text())==raw
    assert json.loads((root/'launcher-result.json').read_text())['success'] is False
    assert 'primary Python archive failure' in (root/'archive-error.json').read_text()


def test_archive_cli_serializes_proposed_receipts_without_optimistic_directory_success(tmp_path):
    root=tmp_path/'evidence space ü';root.mkdir()
    q.write_json(root/'collector-owner.json',dict(kind='Chronicle qualification',root=str(root),id='d3e40067-6166-49bd-b199-285303dce545'))
    pending=dict(status='FINALIZING',success=False,exit_code=4)
    completion={'summary.json':dict(status='OBSERVED',archive_status='VERIFIED'),
                'launcher-result.json':dict(status='OBSERVED',success=True,exit_code=0,archive_status='VERIFIED')}
    for name in completion:q.write_json(root/name,pending)
    proposed=root/'archive-completion.json'
    proposed.write_text(json.dumps(dict(purpose='Proposed; not actual delivery',records=completion)),encoding='utf-8-sig')
    result=subprocess.run([sys.executable,'-B',str(HELPER),'--archive-evidence',str(root),'--archive-completion',str(proposed)],
                          capture_output=True,text=True,encoding='utf-8',timeout=10)
    assert result.returncode==0,result.stderr
    with zipfile.ZipFile(Path(str(root)+'.zip')) as archive:
        for name,value in completion.items():
            assert json.loads(archive.read(name))==value
            assert json.loads((root/name).read_text())==pending


@pytest.mark.parametrize('where',['root','child'])
def test_traversal_failure_is_recorded_as_delivery_failure(tmp_path,monkeypatch,where):
    root=tmp_path/'evidence';root.mkdir();child=root/'child';child.mkdir()
    raw=dict(status='PASS',pytest_exit_code=0)
    q.write_json(root/'collector-result.json',raw)
    original=os.scandir
    def denied(path):
        if Path(path)==(root if where=='root' else child):raise PermissionError('archive tree unavailable')
        return original(path)
    monkeypatch.setattr(q.os,'scandir',denied)
    with pytest.raises(PermissionError,match='archive tree unavailable'):q.finalize_evidence(root,raw)
    assert json.loads((root/'collector-result.json').read_text())==raw
    assert json.loads((root/'summary.json').read_text())['status']=='ERROR'
    assert json.loads((root/'launcher-result.json').read_text())['exit_code']==4
    assert 'archive tree unavailable' in (root/'archive-error.json').read_text()
    assert not Path(str(root)+'.zip').exists()


def test_xfail_and_xpass_without_reason_are_still_expected_outcomes(tmp_path):
    child,root=run_fixture(tmp_path,'''
import pytest
@pytest.mark.xfail
def test_expected(): assert False
@pytest.mark.xfail
def test_unexpected_pass(): pass
''')
    assert child.returncode==0,child.stderr
    result=q.validate_test_evidence(root,0,0)
    assert result['status']=='COMPLETE',result
    assert result['counts']==dict(xfailed=1,xpassed=1)


def test_probe_preparation_reserves_each_record_once(source_repo,tmp_path,monkeypatch):
    root=tmp_path/'probe';root.mkdir()
    # Exercise the actual record-building path with explicit prerequisite doubles;
    # this is not native Windows/Tk/NTFS evidence.
    monkeypatch.setattr(q,'runtime_evidence',lambda:dict(errors=[]))
    monkeypatch.setattr(q,'ntfs_evidence',lambda path:dict(filesystem='NTFS',qualification='synthetic prerequisite'))
    monkeypatch.setattr(q.sys,'getwindowsversion',lambda:SimpleNamespace(build=22000,product_type=1),raising=False)
    monkeypatch.setattr(q.importlib.metadata,'version',lambda name:'2026.5' if name=='tzdata' else '9.1.1')
    source=q.prepare(source_repo,root,'MetadataProbe',None)
    assert source['revision']==q.checked_source(source_repo)['revision']
    assert json.loads((root/'manifest.json').read_text())==[]
    assert set(json.loads((root/'deferred.json').read_text()))=={'legacy','rewrite'}


def test_external_nodeid_selection_uses_collected_path_not_basename(tmp_path):
    reviewed=tmp_path/'reviewed ü root';reviewed.mkdir()
    source=reviewed/'tests/rewrite/test_schema.py';source.parent.mkdir(parents=True);source.write_text('')
    unusual='::test_fresh_profile_and_reopen'
    assert q.selection('Storage',unusual,[],source_path=source,source_root=reviewed)[0]
    external=tmp_path/'test_schema.py';external.write_text('')
    assert not q.selection('Storage','tests/rewrite/test_schema.py::test_fresh_profile_and_reopen',[],source_path=external,source_root=reviewed)[0]
    assert not q.selection('Storage',unusual,['stealth_dialog'],source_path=source,source_root=reviewed)[0]
    assert not q.selection('Storage','::test_unknown',[],source_path=source,source_root=reviewed)[0]


@pytest.mark.parametrize('stdout,stderr',[(None,None),('out',None),(None,'error')])
def test_none_safe_subprocess_diagnostics_preserve_primary_failure(stdout,stderr):
    result=subprocess.CompletedProcess(['exact','command ü'],19,stdout,stderr)
    diagnostic=process_diagnostic(result)
    assert diagnostic==dict(command=result.args,exit_code=19,stdout=stdout,stderr=stderr,diagnostic_path=None)
    with pytest.raises(AssertionError) as failure:
        assert result.returncode==0,diagnostic
    assert '19' in str(failure.value) and 'exact' in str(failure.value)


@pytest.mark.parametrize('prefix',[None,'qualification ü'])
def test_real_empty_junit_classname_and_exact_serialization(tmp_path,prefix):
    # An external explicit initial file with an unrelated rootdir has an empty
    # filesystem node component on POSIX too: exercise actual pytest serialization.
    unrelated=tmp_path/'unrelated root';unrelated.mkdir()
    extra=['--rootdir',str(unrelated)]
    if prefix:extra+=['--junitprefix',prefix]
    child,root=run_fixture(tmp_path,'import pytest\n@pytest.mark.parametrize("x",[1,2])\ndef test_fresh_profile_and_reopen(x):pass\n',extra=extra)
    assert child.returncode==0,process_diagnostic(child)
    manifest=json.loads((root/'manifest.json').read_text())
    assert all(row['nodeid'].startswith('::') for row in manifest)
    assert all(row['junit']['classname']==(prefix+'.' if prefix else '') for row in manifest)
    assert q.validate_test_evidence(root,0,0)['status']=='COMPLETE'
    manifest[0]['junit']['classname']='fabricated'
    (root/'manifest.json').write_text(json.dumps(manifest))
    assert q.validate_test_evidence(root,0,0)['status']=='EVIDENCE_INCOMPLETE'


def test_real_unknown_external_module_is_not_allowed_by_audited_filename(tmp_path):
    suite=tmp_path/'test_schema.py';suite.write_text('def test_fresh_profile_and_reopen():raise AssertionError("must not execute")\n')
    root=tmp_path/'evidence';root.mkdir()
    code='import sys;sys.path.insert(0,sys.argv[1]);import qualification_pytest as q;raise SystemExit(q.run_pytest(sys.argv[2],"Storage",[sys.argv[3],"-p","no:cacheprovider","-o","addopts="]))'
    result=subprocess.run([sys.executable,'-B','-c',code,str(HELPER.parent),str(root),str(suite)],capture_output=True,text=True,timeout=30,
        env=dict(os.environ,PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS=''))
    assert result.returncode==5,process_diagnostic(result)
    manifest=json.loads((root/'manifest.json').read_text())
    assert len(manifest)==1 and not manifest[0]['selected']
    assert 'outside reviewed' in manifest[0]['reason'] and 'must not execute' not in result.stdout


def test_capture_control_keeps_distinct_bytes_and_nonzero_exit(tmp_path):
    command=[sys.executable,'-B','-c','import os;os.write(1,b"out\\x00\\xff");os.write(2,b"err\\n");raise SystemExit(7)']
    result=capture_process(command,tmp_path)
    assert result.returncode==7 and result.stderr=='err\n'
    assert (tmp_path/'stdout.bin').read_bytes()==b'out\x00\xff'
    assert (tmp_path/'stderr.bin').read_bytes()==b'err\n'
    record=json.loads((tmp_path/'subprocess.json').read_text())
    assert record['command']==command and record['exit_code']==7 and not record['timed_out']
    assert record['stdout']['bytes']==5 and record['stderr']['bytes']==4 and not record['capture_failures']


def test_capture_timeout_retains_partial_streams_and_original_exception(tmp_path):
    command=[sys.executable,'-u','-B','-c','import os,time;os.write(1,b"partial out");os.write(2,b"partial err");time.sleep(5)']
    with pytest.raises(subprocess.TimeoutExpired) as failure:capture_process(command,tmp_path,timeout=.3)
    record=json.loads((tmp_path/'subprocess.json').read_text())
    assert record['timed_out'] and record['exit_code'] is None
    assert (tmp_path/'stdout.bin').read_bytes()==b'partial out' and (tmp_path/'stderr.bin').read_bytes()==b'partial err'
    assert failure.value.cmd==command


@pytest.mark.parametrize('missing',[False,True])
def test_capture_distinguishes_empty_from_unavailable_streams(tmp_path,monkeypatch,missing):
    monkeypatch.setattr(subprocess,'run',lambda *a,**kw:subprocess.CompletedProcess(a[0],1,b'',None if missing else b''))
    result=capture_process(['fixture'],tmp_path)
    record=json.loads((tmp_path/'subprocess.json').read_text())
    assert result.returncode==1 and record['stdout']['status']=='EMPTY'
    assert record['stderr']['status']==('ABSENT' if missing else 'EMPTY')
    assert record['stderr']['bytes']==(None if missing else 0)
    assert bool(record['capture_failures']) is missing


def test_capture_diagnostic_failure_keeps_process_exit_and_timeout_context(tmp_path,monkeypatch):
    original=q.JsonRecord.write
    def broken(record,value):
        if value.get('status')!='STARTING':raise OSError('diagnostic failure')
        return original(record,value)
    monkeypatch.setattr(q.JsonRecord,'write',broken)
    with pytest.raises(OSError,match='diagnostic failure') as failure:
        capture_process([sys.executable,'-B','-c','raise SystemExit(9)'],tmp_path)
    assert any("'exit_code': 9" in note for note in failure.value.__notes__)


@pytest.mark.skipif(not POWERSHELL,reason='PowerShell unavailable: independent native capture/identity probe NOT RUN')
def test_actual_powershell_capture_identity_control(tmp_path):
    script=tmp_path/"capture probe ü's.ps1"
    script.write_text('''[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::Out.WriteLine(($PSVersionTable | ConvertTo-Json -Compress))
[Console]::Error.WriteLine('capture error control')
exit 7
''',encoding='utf-8-sig')
    result=capture_process([POWERSHELL,'-NoProfile','-NonInteractive','-File',str(script)],tmp_path,script=script)
    assert result.returncode==7,process_diagnostic(result)
    assert 'PSVersion' in result.stdout and 'capture error control' in result.stderr
    record=json.loads((tmp_path/'subprocess.json').read_text())
    assert record['script']['bom'] and record['script']['sha256']==hashlib.sha256(script.read_bytes()).hexdigest()


def test_capture_close_failure_retains_original_process_observation(tmp_path,monkeypatch):
    original=q.JsonRecord.__exit__
    def close(record,*args):original(record,*args);raise OSError('controlled close failure')
    monkeypatch.setattr(q.JsonRecord,'__exit__',close)
    with pytest.raises(OSError,match='controlled close failure') as failure:
        capture_process([sys.executable,'-B','-c','raise SystemExit(9)'],tmp_path)
    assert any("'exit_code': 9" in note for note in failure.value.__notes__)
    assert json.loads((tmp_path/'subprocess.json').read_text())['exit_code']==9


def test_capture_partial_timeout_with_diagnostic_failure_preserves_primary(tmp_path,monkeypatch):
    original=q.JsonRecord.write
    def broken(record,value):
        if value.get('status')!='STARTING':raise OSError('secondary diagnostic failure')
        return original(record,value)
    monkeypatch.setattr(q.JsonRecord,'write',broken)
    command=[sys.executable,'-u','-B','-c','import os,time;os.write(1,b"partial");time.sleep(5)']
    with pytest.raises(subprocess.TimeoutExpired) as failure:capture_process(command,tmp_path,timeout=.3)
    assert (tmp_path/'stdout.bin').read_bytes()==b'partial'
    assert any('secondary diagnostic failure' in note for note in failure.value.__notes__)
    assert any("'timed_out': True" in note for note in failure.value.__notes__)


def test_capture_stream_failure_retains_other_stream_and_process_result(tmp_path):
    (tmp_path/'stdout.bin').write_bytes(b'preserve existing diagnostics')
    command=[sys.executable,'-B','-c','import os;os.write(1,b"out");os.write(2,b"err");raise SystemExit(9)']
    with pytest.raises(FileExistsError) as failure:capture_process(command,tmp_path)
    assert (tmp_path/'stdout.bin').read_bytes()==b'preserve existing diagnostics'
    assert (tmp_path/'stderr.bin').read_bytes()==b'err'
    record=json.loads((tmp_path/'subprocess.json').read_text())
    assert record['exit_code']==9 and record['status']=='CAPTURE_INCOMPLETE'
    assert any("'exit_code': 9" in note for note in failure.value.__notes__)
