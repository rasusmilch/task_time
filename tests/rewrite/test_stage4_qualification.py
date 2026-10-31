"""Portable full-wrapper contracts. Win32/PowerShell/native UI remain separate."""
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest
from test_app import root

SCRIPTS=Path(__file__).resolve().parents[2]/'scripts'
sys.path.insert(0,str(SCRIPTS))
try:
    f=importlib.import_module('stage4_qualification')
finally:
    sys.path.pop(0)


def child_run(tmp_path,source,collect=False):
    fixture=tmp_path/'case ü spaces.py';fixture.write_text(source,encoding='utf-8')
    root=tmp_path/('collection' if collect else 'regression');root.mkdir()
    command=[sys.executable,'-B','-c',
        'import sys;sys.path.insert(0,sys.argv[1]);import stage4_qualification as f;raise SystemExit(f.pytest_child(sys.argv[2],sys.argv[3]=="True",[sys.argv[4]]))',
        str(SCRIPTS),str(root),str(collect),str(fixture)]
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS='',PYTHONIOENCODING='utf-8'))
    events,_=f.q.read_events(root/'events.jsonl',0)
    final=next(e for e in events if e['event']=='session_finish')
    raw=dict(root=str(root),process_exit_code=result.returncode,pytest_exit_code=final['pytest_exit_code'],
        test_execution_status='PASS' if result.returncode==0 else 'FAIL',termination_reason=None,
        cleanup=dict(verified=True,streams_drained=True),progress=dict(completed=final['completed']))
    raw['evidence']=f.q.validate_test_evidence(root,result.returncode,final['pytest_exit_code'])
    return root,raw,result


def test_real_full_collection_and_parametrized_junit_success(tmp_path):
    source='import pytest\n@pytest.mark.parametrize("x",[1,2])\ndef test_one(x):print("live",flush=True);assert x\n'
    collection,raw,_=child_run(tmp_path,source,True)
    inventory=f.collection_result(collection,raw)
    assert len(inventory)==2 and raw['evidence']['junit']=='missing'
    root,run,process=child_run(tmp_path,source)
    assert b'live' in process.stdout  # -rA retains captured test output in the raw log.
    assert run['evidence']['status']=='COMPLETE'
    result=f.aggregate(inventory,run)
    assert result['automated_status']=='PASS' and result['selected']==result['executed']==2
    assert result['counts']==dict(passed=2) and result['F3']==result['F4']=='NOT RUN'


def test_outcome_counts_setup_teardown_xfail_skip_no_blanket_pass(tmp_path):
    source='''
import pytest
def test_ok():pass
@pytest.mark.skip(reason='supervised native gap')
def test_skip():pass
@pytest.mark.xfail(reason='known')
def test_xfail():assert False
@pytest.mark.xfail(reason='unexpected success')
def test_xpass():pass
@pytest.fixture
def bad():raise RuntimeError('setup')
def test_setup(bad):pass
@pytest.fixture
def cleanup():
 yield
 raise RuntimeError('teardown')
def test_both(cleanup):assert False
'''
    root,raw,_=child_run(tmp_path,source)
    inventory=json.loads((root/'manifest.json').read_text())
    assert raw['evidence']['status']=='COMPLETE'
    assert raw['evidence']['counts']==dict(passed=1,skipped=1,xfailed=1,xpassed=1,error=2)
    result=f.aggregate(inventory,raw)
    assert result['automated_status']=='FAIL' and result['executed']==6


@pytest.mark.parametrize('source',[
    'import pytest\n@pytest.mark.skip(reason="XTest unavailable")\ndef test_skip():pass\n',
    'import pytest\n@pytest.mark.xfail(reason="retained limitation")\ndef test_xfail():assert False\n'])
def test_skipped_or_expected_failure_not_full_qualification(tmp_path,source):
    root,raw,_=child_run(tmp_path,source)
    inventory=json.loads((root/'manifest.json').read_text())
    result=f.aggregate(inventory,raw)
    assert raw['process_exit_code']==0 and result['automated_status']=='EVIDENCE_INCOMPLETE'


@pytest.mark.parametrize('damage',['junit','manifest','events','inventory','cleanup','streams'])
def test_incomplete_evidence_cannot_pass(tmp_path,damage):
    root,raw,_=child_run(tmp_path,'def test_one():pass\n')
    inventory=json.loads((root/'manifest.json').read_text())
    if damage in ('junit','manifest','events'):
        (root/('junit.xml' if damage=='junit' else 'manifest.json' if damage=='manifest' else 'events.jsonl')).write_text('broken')
        raw['evidence']=f.q.validate_test_evidence(root,0,0)
    if damage=='inventory':inventory=[]
    if damage in ('cleanup','streams'):raw['cleanup']['verified' if damage=='cleanup' else 'streams_drained']=False
    assert f.aggregate(inventory,raw)['automated_status']=='EVIDENCE_INCOMPLETE'


def test_unexpected_native_dialog_obstructs_without_answer(tmp_path):
    root,raw,process=child_run(tmp_path,'''
def test_no_consent():
 import tkinter.messagebox as mb
 mb.askyesno('Overwrite?','must not appear')
''')
    assert process.returncode==1
    events,_=f.q.read_events(root/'events.jsonl',0)
    assert any(e['event']=='obstructed' for e in events)
    assert b'Unexpected unattended UI request' in process.stdout


def test_module_skip_is_retained_and_cannot_claim_full_qualification(tmp_path):
    root,raw,_=child_run(tmp_path,'import pytest\npytest.skip("module prerequisite unavailable",allow_module_level=True)\n')
    events,_=f.q.read_events(root/'events.jsonl',0)
    skipped=[e for e in events if e['event']=='collection_report' and e['outcome']=='skipped']
    assert len(skipped)==1 and 'module prerequisite unavailable' in skipped[0]['diagnostic']
    assert f.aggregate(json.loads((root/'manifest.json').read_text()),raw)['automated_status']=='EVIDENCE_INCOMPLETE'


def test_full_plugin_existing_real_tk_callback_path(tmp_path):
    root=tmp_path/'real callback';root.mkdir()
    node='tests/rewrite/test_template_ui.py::test_real_tk_manager_refresh_no_churn_and_modal_exclusions'
    command=[sys.executable,'-B','-c','import sys;sys.path.insert(0,sys.argv[1]);import stage4_qualification as f;raise SystemExit(f.pytest_child(sys.argv[2],False,[sys.argv[3]]))',str(SCRIPTS),str(root),node]
    process=subprocess.run(command,cwd=SCRIPTS.parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS=''))
    events,_=f.q.read_events(root/'events.jsonl',0)
    session=next(e for e in events if e['event']=='session_finish')
    if session['counts'].get('skipped'):
        reasons=[e.get('diagnostic') for e in events if e['event']=='report' and e['outcome']=='skipped']
        pytest.skip('Real Tk callback unavailable: '+repr(reasons))
    assert process.returncode==0,(process.stdout+process.stderr).decode(errors='replace')
    assert session['counts']==dict(passed=1)
    assert f.q.validate_test_evidence(root,0,0)['status']=='COMPLETE'


@pytest.mark.skipif(os.name!='posix',reason='POSIX process-group test is not native Windows containment')
@pytest.mark.parametrize('phase',['setup','call','teardown'])
def test_full_plugin_real_watchdog_keeps_partial_evidence_and_owned_cleanup(tmp_path,phase):
    from test_qualification_collector import PortableOwnedChild
    fixture=tmp_path/'hang.py'
    source='''
import pytest,time
@pytest.fixture
def controlled():
 SETUP
 yield
 TEARDOWN
def test_quiet(controlled):
 CALL
'''.replace('SETUP','time.sleep(10)' if phase=='setup' else 'pass').replace('TEARDOWN','time.sleep(10)' if phase=='teardown' else 'pass').replace('CALL','time.sleep(10)' if phase=='call' else 'pass')
    fixture.write_text(source)
    root=tmp_path/'run';root.mkdir()
    command=[sys.executable,'-B','-c','import sys;sys.path.insert(0,sys.argv[1]);import stage4_qualification as f;raise SystemExit(f.pytest_child(sys.argv[2],False,[sys.argv[3]]))',str(SCRIPTS),str(root),str(fixture)]
    child=PortableOwnedChild(command);live=[]
    raw=f.q.monitor(child,root,dict(f.q.LIMITS,test=.6,warning=.1,collection=5),display=lambda *a,**k:live.append(a))
    assert raw['status']=='TIMEOUT' and raw['progress']['phase']==phase
    assert raw['cleanup']['verified'] and raw['cleanup']['streams_drained'] and raw['pytest_exit_code'] is None
    assert raw['junit']=='missing' and (root/'events.jsonl').is_file() and (root/'stdout.log').is_file()
    assert any('WARNING' in str(v) for v in live) and any('CHRONICLE_PROGRESS' in str(v) for v in live)


def test_zip_reopen_membership_hidden_files_final_status_and_no_overwrite(tmp_path):
    root=tmp_path/'evidence';root.mkdir();(root/'.hidden').write_bytes(b'intended fixture')
    raw=dict(automated_status='PASS',pytest_exit_code=0,F3='NOT RUN',F4='NOT RUN')
    assert f.deliver(root,raw)==0
    assert json.loads((root/'summary.json').read_text())['archive_status']=='VERIFIED'
    with zipfile.ZipFile(str(root)+'.zip') as z:
        assert z.testzip() is None and set(z.namelist())=={'.hidden','summary.json','archive-members.json'}
        assert json.loads(z.read('summary.json'))['status']=='PASS'
    with pytest.raises(FileExistsError):f.deliver(root,raw)


@pytest.mark.parametrize('kind',['file','symlink'])
def test_reserved_archive_name_never_overwrites_sentinel(tmp_path,kind):
    root=tmp_path/'evidence';root.mkdir();outside=tmp_path/'sentinel';outside.write_bytes(b'outside')
    reserved=root/'archive-members.json'
    if kind=='file':reserved.write_bytes(b'reserved')
    else:
        from test_backup_restore import symlink
        symlink(outside,reserved)
    before=(outside.read_bytes(),outside.stat())
    assert f.deliver(root,dict(automated_status='PASS',pytest_exit_code=0))==4
    after=outside.stat()
    assert outside.read_bytes()==before[0] and (after.st_ino,after.st_mtime_ns,after.st_ctime_ns)==(before[1].st_ino,before[1].st_mtime_ns,before[1].st_ctime_ns)
    assert not Path(str(root)+'.zip').exists()
    assert json.loads((root/'summary.json').read_text())['status']=='EVIDENCE_INCOMPLETE'
    if kind=='file':assert reserved.read_bytes()==b'reserved'


@pytest.mark.parametrize('failure',['traverse','zip','link','verify'])
def test_delivery_failure_retains_execution_and_never_reports_success(tmp_path,monkeypatch,failure):
    root=tmp_path/'evidence';root.mkdir();(root/'execution-result.json').write_text('{"pytest_exit_code":0}')
    def fail(*a,**k):raise OSError('injected '+failure)
    if failure=='traverse':
        def walk(*a,**k):k['onerror'](PermissionError('unreadable child'));yield
        monkeypatch.setattr(f.os,'walk',walk)
    elif failure=='zip':monkeypatch.setattr(f.zipfile,'ZipFile',fail)
    elif failure=='link':monkeypatch.setattr(f.os,'link',fail)
    else:monkeypatch.setattr(f.zipfile.ZipFile,'testzip',lambda s:'corrupt member')
    assert f.deliver(root,dict(automated_status='PASS',pytest_exit_code=0))==4
    summary=json.loads((root/'summary.json').read_text())
    assert summary['automated_status']=='PASS' and summary['status']=='EVIDENCE_INCOMPLETE' and summary['pytest_exit_code']==0
    assert summary['archive_status']=='FAILED_OR_UNVERIFIED' and root.is_dir()
    assert not Path(str(root)+'.zip').exists()


def test_reservation_never_reuses_directory_or_dataset_or_source(tmp_path):
    repo=tmp_path/'source';repo.mkdir();parent=tmp_path/'output';parent.mkdir()
    a,b=f.reserve(repo,parent),f.reserve(repo,parent)
    assert a!=b and a.is_dir() and b.is_dir()
    for target in (repo, tmp_path):
        with pytest.raises(ValueError):f.reserve(repo,target)
    (parent/'chronicle.sqlite3').write_bytes(b'disposable dataset sentinel')
    with pytest.raises(ValueError,match='dataset'):f.reserve(repo,parent)


def test_source_mismatch_dirty_refusal_and_linux_gate_no_test_execution(tmp_path,monkeypatch):
    for observed in (dict(revision='a'*40,branch='feature/chronicle-rewrite',dirty=True),
                     dict(revision='b'*40,branch='feature/chronicle-rewrite',dirty=False)):
        with pytest.raises(RuntimeError):f.q.checked_source(tmp_path,'a'*40,observed=observed)
    if os.name=='nt':pytest.skip('Linux refusal is not a Windows prerequisite test')
    repo=tmp_path/'repo';repo.mkdir();parent=tmp_path/'out';parent.mkdir()
    monkeypatch.setattr(f.q,'checked_source',lambda *a:dict(revision='a'*40,branch='feature/chronicle-rewrite'))
    monkeypatch.setattr(f.q,'WindowsChild',lambda *a:pytest.fail('must not execute Windows test child'))
    assert f.run(repo,parent,'a'*40,dict(f.q.LIMITS))==4
    root=next(p for p in parent.iterdir() if p.is_dir())
    assert json.loads((root/'summary.json').read_text())['status']=='BLOCKED'


@pytest.mark.parametrize('shell',list(dict.fromkeys(p for p in (shutil.which('powershell'),shutil.which('pwsh')) if p)) or [None])
def test_powershell_static_boundary_and_optional_parser(tmp_path,shell):
    script=SCRIPTS/'qualify_stage4_windows.ps1';text=script.read_text()
    assert 'qualify_windows.ps1' not in text and 'stage4_qualification.py' in text
    assert 'ReadLineAsync' in text and 'Write-Progress' in text and 'WaitForExit(10000)' in text
    assert 'Get-Process' not in text and 'Stop-Process' not in text and 'ExecutionPolicy' not in text
    if shell is None:pytest.skip('PowerShell parser/runtime unavailable; static assertions only')
    import base64
    for filename,content,expected in (("valid space ü's.ps1",'$x = 1',0),
                                      ("invalid space ü's.ps1",'function {',1)):
        target=tmp_path/filename;target.write_text(content,encoding='utf-8-sig')
        # Bind the path inside the encoded script; -Command trailing arguments
        # are PowerShell syntax, not an argv contract on Windows PowerShell 5.1.
        quoted="'"+str(target).replace("'","''")+"'"
        code=("[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);$Target = "+quoted+"; Write-Output $Target; $e=$null;$t=$null;"
              "[System.Management.Automation.Language.Parser]::ParseFile($Target,[ref]$t,[ref]$e)>$null;"
              "if($e){$e|Out-String|Write-Error;exit 1};exit 0")
        encoded=base64.b64encode(code.encode('utf-16le')).decode('ascii')
        result=subprocess.run([shell,'-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,text=True,encoding='utf-8',timeout=15)
        assert result.returncode==expected,repr((result.args,result.returncode,result.stdout,result.stderr))
        assert str(target) in result.stdout
        if expected:assert result.stderr
    quoted="'"+str(script).replace("'","''")+"'"
    code="$Target="+quoted+";$e=$null;$t=$null;[System.Management.Automation.Language.Parser]::ParseFile($Target,[ref]$t,[ref]$e)>$null;if($e){$e|Out-String|Write-Error;exit 1};exit 0"
    result=subprocess.run([shell,'-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(code.encode('utf-16le')).decode()],capture_output=True,text=True,encoding='utf-8',timeout=15)
    assert result.returncode==0,repr((result.stdout,result.stderr))


def test_owned_sink_survives_filesystem_writer_monkeypatch_in_real_pytest(tmp_path):
    root,raw,process=child_run(tmp_path,'''\
from pathlib import Path
import os

def test_read_only(monkeypatch):
 def forbidden(*a,**k):raise AssertionError('ordinary writer intercepted')
 for owner,name in ((Path,'open'),(os,'open'),(os,'write'),(os,'fsync'),(os,'close')):
  monkeypatch.setattr(owner,name,forbidden)
 assert 2+2==4
''')
    assert process.returncode==0,repr((process.stdout,process.stderr))
    assert raw['evidence']['status']=='COMPLETE'
    health=f.event_health(root)
    assert health['status']=='COMPLETE' and health['records']>5
    assert f.aggregate(json.loads((root/'manifest.json').read_text()),raw)['automated_status']=='PASS'


@pytest.mark.parametrize('fault',['zero','write','sync','close','health_write','health_sync','health_close'])
def test_owned_sink_failures_latch_and_refuse_finalization(tmp_path,fault):
    real_write,real_sync,real_close=os.write,os.fsync,os.close
    closed=[]
    def write(fd,data):
        if fault=='write' or (fault=='health_write' and fd==writer.health_fd):raise OSError('primary write')
        if fault=='zero':return 0
        return real_write(fd,data)
    def sync(fd):
        if fault=='sync' or (fault=='health_sync' and fd==writer.health_fd):raise OSError('sync failure')
        return real_sync(fd)
    def close(fd):
        real_close(fd);closed.append(fd)
        if fault=='close' or (fault=='health_close' and fd==writer.health_fd):raise OSError('close acknowledgement failed')
    writer=f.OwnedEvents(tmp_path,write=write,sync=sync,close=close)
    if fault in ('zero','write'):
        with pytest.raises(OSError):writer.emit('collection_start')
        writer.write=real_write
        with pytest.raises(RuntimeError,match='already failed'):writer.emit('session_finish')
    else:writer.emit('collection_start')
    assert not writer.finish() and writer.errors
    assert closed==[writer.fd,writer.health_fd]
    # A health-sync/close failure can leave a readable record, but child exit remains
    # nonzero independently. No parent may infer success from health alone.
    if fault not in ('health_close','health_sync'):assert f.event_health(tmp_path)['status']=='EVIDENCE_INCOMPLETE'


def test_owned_sink_short_and_interrupted_writes_and_exclusive_reservation(tmp_path):
    real=os.write;calls=[]
    def short(fd,data):
        calls.append(len(data))
        if len(calls)==1:raise InterruptedError()
        return real(fd,data[:3])
    writer=f.OwnedEvents(tmp_path,write=short)
    writer.emit('collection_start');writer.emit('session_finish',pytest_exit_code=0)
    assert writer.finish() and len(calls)>5 and f.event_health(tmp_path)['status']=='COMPLETE'
    original=(tmp_path/'events.jsonl').read_bytes()
    with pytest.raises(FileExistsError):f.OwnedEvents(tmp_path)
    assert (tmp_path/'events.jsonl').read_bytes()==original


@pytest.mark.parametrize('damage',['missing','tail','order','digest','health'])
def test_parent_refuses_unfinalized_or_changed_event_bytes(tmp_path,damage):
    writer=f.OwnedEvents(tmp_path);writer.emit('collection_start');writer.emit('session_finish',pytest_exit_code=0)
    assert writer.finish()
    event=tmp_path/'events.jsonl';health=tmp_path/'event-health.json'
    if damage=='missing':health.unlink()
    elif damage=='tail':event.write_bytes(event.read_bytes()+b'{')
    elif damage=='order':event.write_bytes(b'\n'.join(reversed(event.read_bytes().splitlines()))+b'\n')
    elif damage=='digest':event.write_bytes(event.read_bytes().replace(b'collection_start',b'collection_begin'))
    else:health.write_text('{')
    assert f.event_health(tmp_path)['status']=='EVIDENCE_INCOMPLETE'


def test_event_writer_closes_after_collection_error_and_internal_exception(tmp_path):
    root,raw,result=child_run(tmp_path,'raise RuntimeError("collection failure")\n')
    assert result.returncode==2 and f.event_health(root)['status']=='COMPLETE'
    assert raw['evidence']['status']=='EVIDENCE_INCOMPLETE'  # Not a completed test run.


def test_partition_union_exact_sources_duplicates_and_unknowns(tmp_path):
    def row(node,path):return dict(nodeid=node,source_path=str(tmp_path/path))
    inventory=[row('::test_ü[1]','tests/rewrite/test_a.py'),
        row('::test_bridge','tests/test_root_launcher.py'),row('::test_legacy','tests/test_app_ui.py'),
        row('::test_unknown','tests/test_unreviewed.py'),row('::test_outside','../tests/rewrite/test_a.py')]
    partitions=f.partition_inventory(inventory,tmp_path)
    assert [len(partitions[k]) for k in ('SUPPORTED_RUNTIME','RETAINED_LEGACY','UNCLASSIFIED')]==[2,1,2]
    assert {r['nodeid'] for rows in partitions.values() for r in rows}=={r['nodeid'] for r in inventory}
    with pytest.raises(ValueError,match='Duplicate'):f.partition_inventory(inventory+[inventory[0]],tmp_path)


def test_partition_real_separate_pytest_sessions_preserve_legacy_failure(tmp_path):
    # Same fixture content separately collected, then exact original node/source
    # selection: passing supported session never conceals legacy failure.
    source='def test_supported():pass\ndef test_legacy():assert False\n'
    collection,raw,_=child_run(tmp_path,source,True)
    inventory=f.collection_result(collection,raw)
    for index,row in enumerate(inventory):
        root=tmp_path/('partition'+str(index));root.mkdir()
        fixture=tmp_path/'case ü spaces.py'
        code='import sys,json;sys.path.insert(0,sys.argv[1]);import stage4_qualification as f;raise SystemExit(f.pytest_child(sys.argv[2],False,[sys.argv[3]],json.loads(sys.argv[4])))'
        process=subprocess.run([sys.executable,'-B','-c',code,str(SCRIPTS),str(root),str(fixture)+'::'+row['nodeid'].split('::',1)[1],json.dumps([row])],capture_output=True,timeout=30,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS=''))
        assert process.returncode==index,repr((process.stdout,process.stderr))
        assert f.q.validate_test_evidence(root,index,index)['status']=='COMPLETE'
        events,_=f.q.read_events(root/'events.jsonl',0)
        assert [e['nodeid'] for e in events if e['event']=='node_finish']==[row['nodeid']]


def test_skip_applicability_is_exact_not_reason_text(tmp_path):
    row=dict(nodeid='tests/rewrite/test_operational_lifecycle.py::test_native_permission_refusal_does_not_damage_dataset',fixtures=[])
    reports=[dict(outcome='skipped',diagnostic='raw reason unchanged')]
    assert f.skip_applicability(row,reports,'win32')['classification']=='INAPPLICABLE'
    assert f.skip_applicability(row,reports,'linux')['classification']=='UNRESOLVED'
    row['nodeid']='tests/rewrite/test_unknown.py::test_looks_posix'
    reports[0]['diagnostic']='Linux XTest-only POSIX test safe to skip'
    assert f.skip_applicability(row,reports,'win32')['classification']=='UNRESOLVED'
    row['fixtures']=['root']
    assert f.skip_applicability(row,reports,'win32')['classification']=='BLOCKED_REQUIRED'


def test_tk_observer_distinguishes_focus_precondition_and_geometry(root,capsys):
    from tkinter import ttk
    from tk_observation import wait_observed,snapshot
    widget=ttk.Entry(root);widget.grid()
    wait_observed(root,lambda:widget.winfo_ismapped(),phase='geometry',widgets=(widget,))
    state=snapshot(root,(widget,))
    assert state['widgets'][0]['manager']=='grid' and state['widgets'][0]['mapped']
    with pytest.raises(AssertionError) as failure:
        wait_observed(root,lambda:False,phase='PRECONDITION controlled focus absence',widgets=(widget,),timeout=25)
    assert any('PRECONDITION' in note for note in failure.value.__notes__)
    with pytest.raises(AssertionError) as failure:
        wait_observed(root,lambda:False,phase='History actual return focus',widgets=(widget,),timeout=25)
    assert any('RESULT' in note for note in failure.value.__notes__)
    observations=[json.loads(line.removeprefix('CHRONICLE_TK_OBSERVATION '))
        for line in capsys.readouterr().out.splitlines() if line.startswith('CHRONICLE_TK_OBSERVATION ')]
    assert [row['observation_kind'] for row in observations]==['RESULT','PRECONDITION','RESULT']
    assert all(row['timeline'][0]['event']=='begin' and row['timeline'][-1]['event']=='end' for row in observations)
    widget_name=widget.winfo_name()
    widget.destroy()
    assert snapshot(root,(widget,))['widgets'][0]['live']==0
    replacement=ttk.Entry(root,name=widget_name);replacement.grid()
    old,new=snapshot(root,(widget,replacement))['widgets']
    assert old['path']==new['path'] and old['python_id']!=new['python_id']
    assert not old['live'] and new['live']


@pytest.mark.parametrize('fault',['write','sync','close','health_sync','health_close','cleanup'])
def test_failed_instrumentation_child_cannot_exit_successfully(tmp_path,fault):
    fixture=tmp_path/'test_simple.py';fixture.write_text('def test_ok():pass\n')
    root=tmp_path/'owned';root.mkdir()
    code='''
import sys
sys.path.insert(0,sys.argv[1])
import stage4_qualification as f
fault=sys.argv[4]
original=f.OwnedEvents
class Injected(original):
 def __init__(self,root):
  super().__init__(root)
  write,sync,close=self.write,self.sync,self.close_fd
  def badwrite(fd,data):
   if fault=='write':raise OSError('controlled write failure')
   return write(fd,data)
  def badsync(fd):
   if fault=='sync' or (fault=='health_sync' and fd==self.health_fd):raise OSError('controlled sync failure')
   return sync(fd)
  def badclose(fd):
   close(fd)
   if fault=='close' or (fault=='health_close' and fd==self.health_fd):raise OSError('controlled close failure')
  self.write,self.sync,self.close_fd=badwrite,badsync,badclose
f.OwnedEvents=Injected
if fault=='cleanup':
 def failed_restore(self):raise RuntimeError('controlled guard cleanup failure')
 f.q.DialogGuard.restore=failed_restore
raise SystemExit(f.pytest_child(sys.argv[2],False,[sys.argv[3]]))
'''
    result=subprocess.run([sys.executable,'-B','-c',code,str(SCRIPTS),str(root),str(fixture),fault],capture_output=True,timeout=30,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS=''))
    assert result.returncode!=0,repr((result.stdout,result.stderr))
    assert b'CHRONICLE_EVENT_HEALTH_FAILURE' in result.stderr
    events,_=f.q.read_events(root/'events.jsonl',0)
    session=next((e for e in events if e['event']=='session_finish'),{})
    assert f.q.validate_test_evidence(root,result.returncode,session.get('pytest_exit_code'))['status']=='EVIDENCE_INCOMPLETE'


def test_supported_delivery_stays_distinct_from_failed_legacy(tmp_path,monkeypatch):
    for failure in (False,True):
        root=tmp_path/str(failure);root.mkdir()
        raw=dict(automated_status='FAIL',supported_runtime_execution='PASS',retained_legacy='FAIL',F2='EXECUTED',
            source_verified_before=True,source_verified_after=True,qualification_complete=True)
        if failure:monkeypatch.setattr(f,'archive',lambda *a:(_ for _ in ()).throw(OSError('delivery failure')))
        assert f.deliver(root,raw)==4
        summary=json.loads((root/'summary.json').read_text())
        assert summary['supported_runtime_automated']==('EVIDENCE_INCOMPLETE' if failure else 'PASS')
        assert summary['retained_legacy']=='FAIL' and summary['supported_runtime_execution']=='PASS'
        assert summary['status']==('EVIDENCE_INCOMPLETE' if failure else 'FAIL')


def test_reviewed_partition_sources_do_not_cross_runtime_imports():
    import ast
    repo=SCRIPTS.parent
    actual={p.name for p in (repo/'tests').glob('test_*.py')}
    assert actual==f.LEGACY_MODULES|{'test_root_launcher.py'}
    def imports(path):
        result=set()
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Import):result.update(a.name for a in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:result.add(node.module)
        return result
    for name in f.LEGACY_MODULES:
        assert not any(m=='chronicle' or m.startswith('chronicle.') for m in imports(repo/'tests'/name)),name
    for path in (repo/'tests/rewrite').glob('*.py'):
        assert not any(m=='task_timer' or m.startswith('task_timer.') for m in imports(path)),path
    assert 'chronicle.bootstrap' in (repo/'run_chronicle.py').read_text()


def test_xtest_classification_requires_exact_fixture_and_explicit_metadata():
    source=SCRIPTS.parent/'tests/rewrite/test_app.py'
    row=dict(nodeid='tests/rewrite/test_app.py::test_real_tk_clock_warning_recovery_preserves_original_start',
        fixtures=['root','click'],fixture_sources={'click':str(source)},
        fixture_definitions={'click':[dict(module='test_app',function='click')]})
    reports=[dict(outcome='skipped',diagnostic='unchanged raw skip',
        applicability_metadata=[['chronicle_skip_rule','linux_xtest_only']])]
    result=f.skip_applicability(row,reports,'win32')
    assert result['classification']=='INAPPLICABLE' and result['replacement_gate'].startswith('F3')
    reports[0]['applicability_metadata']=[]  # Root failure before click cannot waive desktop.
    assert f.skip_applicability(row,reports,'win32')['classification']=='BLOCKED_REQUIRED'
    reports[0]['wasxfail']='unexpected retained failure'
    assert f.skip_applicability(row,reports,'win32')['classification']=='UNRESOLVED'


@pytest.mark.skipif(os.name!='posix',reason='Portable process-group orchestration is not native Windows Job evidence')
@pytest.mark.parametrize('unknown',[False,True])
def test_real_full_inventory_two_owned_partitions_and_truthful_status(tmp_path,monkeypatch,unknown):
    from test_qualification_collector import PortableOwnedChild
    repo=tmp_path/'repo ü';(repo/'tests/rewrite').mkdir(parents=True)
    (repo/'tests/rewrite/test_supported.py').write_text('def test_ok():pass\n')
    (repo/'tests/test_app_ui.py').write_text('def test_legacy():assert False\n')
    if unknown:(repo/'tests/test_unknown.py').write_text('def test_unknown():pass\n')
    root=tmp_path/'evidence';root.mkdir()
    class ScopedChild(PortableOwnedChild):
        def __init__(self,command,cwd,env):
            self.process=subprocess.Popen(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            self.stdout,self.stderr=self.process.stdout,self.process.stderr
    monkeypatch.setattr(f.q,'WindowsChild',ScopedChild)
    raw=dict(F2='NOT RUN')
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS='')
    f.execute_sessions(repo,root,env,dict(f.q.LIMITS,collection=15,test=10,phase=30),raw)
    assert raw['F2']=='EXECUTED' and raw['retained_legacy']=='FAIL' and raw['automated_status']=='FAIL'
    assert raw['supported_runtime_execution']==('EVIDENCE_INCOMPLETE' if unknown else 'PASS')
    partitions=json.loads((root/'partitions.json').read_text())
    original=json.loads((root/'collection/manifest.json').read_text())
    assert len(original)==2+unknown and len(partitions['UNCLASSIFIED'])==unknown
    assert sum(len(rows) for rows in partitions.values())==len(original)
    for name,code in (('supported-runtime',0),('retained-legacy',1)):
        result=raw['partitions']['SUPPORTED_RUNTIME' if code==0 else 'RETAINED_LEGACY']
        assert result['process_exit_code']==result['pytest_exit_code']==code
        assert result['cleanup']['verified'] and result['cleanup']['streams_drained']
        assert result['evidence']['status']=='COMPLETE' and result['executed']==1
        assert f.event_health(root/name)['status']=='COMPLETE'
        assert (root/name/'junit.xml').is_file() and (root/name/'stdout.log').is_file()
    raw.update(source_verified_before=True,source_verified_after=True,qualification_complete=True)
    assert f.deliver(root,raw)==4
    summary=json.loads((root/'summary.json').read_text())
    assert summary['supported_runtime_automated']==raw['supported_runtime_execution'] and summary['archive_status']=='VERIFIED'


def test_event_reservation_keeps_primary_and_secondary_diagnostic(tmp_path):
    (tmp_path/'event-health.json').write_bytes(b'existing health sentinel')
    def closed_then_failed(fd):
        os.close(fd)
        raise OSError('secondary reservation close failure')
    with pytest.raises(FileExistsError) as failure:f.OwnedEvents(tmp_path,close=closed_then_failed)
    assert any('secondary reservation close failure' in note for note in failure.value.__notes__)
    assert (tmp_path/'event-health.json').read_bytes()==b'existing health sentinel'


@pytest.mark.parametrize('missing',['source_verified_before','source_verified_after','qualification_complete','error'])
def test_supported_pass_cannot_survive_unverified_final_source_or_finalization(tmp_path,missing):
    raw=dict(automated_status='EVIDENCE_INCOMPLETE',supported_runtime_execution='PASS',
        source_verified_before=True,source_verified_after=True,qualification_complete=True)
    if missing=='error':raw['error']='final source changed'
    else:raw[missing]=False
    assert f.deliver(tmp_path,raw)==4
    summary=json.loads((tmp_path/'summary.json').read_text())
    assert summary['supported_runtime_execution']=='PASS' and summary['supported_runtime_automated']=='EVIDENCE_INCOMPLETE'


def test_actual_pytest_carries_explicit_fixture_applicability_metadata(tmp_path):
    root,raw,result=child_run(tmp_path,f'''
import sys
sys.path.insert(0,{str(SCRIPTS.parent/'tests/rewrite')!r})
from test_app import skip_non_linux_server_input

def test_platform_fixture(request):
 skip_non_linux_server_input(request,'win32')
''')
    assert result.returncode==0 and raw['evidence']['status']=='COMPLETE'
    events,_=f.q.read_events(root/'events.jsonl',0)
    skip=next(e for e in events if e['event']=='report' and e['outcome']=='skipped')
    assert skip['applicability_metadata']==[['chronicle_skip_rule','linux_xtest_only']]
    assert 'Server-input fixture requires Linux X11/XTest' in skip['diagnostic']
    from types import SimpleNamespace
    from test_app import skip_non_linux_server_input
    properties=[]
    request=SimpleNamespace(node=SimpleNamespace(user_properties=properties))
    assert skip_non_linux_server_input(request,'linux') is None and properties==[]
    with pytest.raises(pytest.skip.Exception):skip_non_linux_server_input(request,'win32')
    assert properties==[('chronicle_skip_rule','linux_xtest_only')]


def test_mirrored_nested_progress_cannot_impersonate_controller_events(tmp_path,monkeypatch,capsys):
    def monitor(child,root,limits,display):
        display('CHRONICLE_PROGRESS not json\nCHRONICLE_PROGRESS {"completed":999}',end='')
        display('CHRONICLE_PRO',end='')
        display('GRESS {"completed":999}',end='')
        display('CHRONICLE_PROGRESS '+json.dumps(dict(completed=2,selected=3)))
        return 'retained raw result'
    monkeypatch.setattr(f.q,'monitor',monitor)
    assert f.phase_monitor(None,tmp_path,{},'SUPPORTED_RUNTIME')=='retained raw result'
    lines=capsys.readouterr().out.splitlines()
    progress=[line for line in lines if line.startswith('CHRONICLE_PROGRESS ')]
    assert len(progress)==1
    assert json.loads(progress[0][len('CHRONICLE_PROGRESS '):])==dict(completed=2,selected=3,qualification_phase='SUPPORTED_RUNTIME')
    assert all(line.startswith('PYTEST_OUTPUT ') for line in lines[:-1])
    assert 'not json' in lines[0]  # Diagnostic text is visible, never parsed.


@pytest.mark.parametrize('damage',['missing','additional','duplicate_actual','duplicate_expected','source'])
def test_inventory_mismatch_refuses_before_execution_and_keeps_exact_evidence(tmp_path,damage):
    from types import SimpleNamespace
    actual=[dict(nodeid='::test_one',source_path=str((tmp_path/'case ü.py').resolve()))]
    expected=[dict(actual[0])]
    if damage=='missing':expected.append(dict(nodeid='::missing',source_path=actual[0]['source_path']))
    elif damage=='additional':expected=[]
    elif damage=='duplicate_actual':actual.append(dict(actual[0]))
    elif damage=='duplicate_expected':expected.append(dict(expected[0]))
    else:expected[0]['source_path']=str(tmp_path/'other.py')
    items=[SimpleNamespace(nodeid=row['nodeid'],path=Path(row['source_path'])) for row in actual]
    writer=f.OwnedEvents(tmp_path);plugin=f.FullPlugin(tmp_path,writer,expected)
    try:
        with pytest.raises(ValueError,match='Partition collection differs'):
            plugin.pytest_collection_modifyitems(None,None,items)
    finally:writer.finish()
    evidence=json.loads((tmp_path/'inventory-mismatch.json').read_text())
    assert evidence['expected']==expected and evidence['actual']==actual
    assert evidence['expected_count']==len(expected) and evidence['actual_count']==len(actual)
    assert evidence['mismatch'] and not (tmp_path/'manifest.json').exists()
    events,_=f.q.read_events(tmp_path/'events.jsonl',0)
    assert not any(e['event']=='node_start' for e in events)
    assert events[-1]['event']=='inventory_mismatch'


def test_inventory_diagnostic_failure_preserves_primary_and_reserved_object(tmp_path,monkeypatch):
    from types import SimpleNamespace
    reserved=tmp_path/'inventory-mismatch.json';reserved.write_bytes(b'preserve')
    writer=f.OwnedEvents(tmp_path);plugin=f.FullPlugin(tmp_path,writer,[])
    item=SimpleNamespace(nodeid='::new',path=tmp_path/'new.py')
    try:
        with pytest.raises(ValueError,match='Partition collection differs') as failure:
            plugin.pytest_collection_modifyitems(None,None,[item])
        assert any('diagnostic write also failed' in note for note in failure.value.__notes__)
        assert reserved.read_bytes()==b'preserve'
        assert not (tmp_path/'manifest.json').exists()
    finally:writer.finish()


def test_inventory_order_alone_does_not_refuse_and_summary_is_bounded(tmp_path,capsys):
    from types import SimpleNamespace
    rows=[dict(nodeid='::test_'+str(i),source_path=str(tmp_path/'case.py')) for i in range(60)]
    difference=f.inventory_difference(rows,list(reversed(rows)))
    assert difference['order_changed'] and len(difference['order_differences'])==60 and not difference['mismatch']
    writer=f.OwnedEvents(tmp_path);plugin=f.FullPlugin(tmp_path,writer,rows)
    try:
        with pytest.raises(ValueError):plugin.pytest_collection_modifyitems(None,None,[])
    finally:writer.finish()
    complete=json.loads((tmp_path/'inventory-mismatch.json').read_text())
    assert complete['missing']==sorted(r['nodeid'] for r in rows)
    output=capsys.readouterr().out
    summary=json.loads(next(line.split(' ',1)[1] for line in output.splitlines() if line.startswith('INVENTORY_MISMATCH ')))
    assert summary['missing']['count']==60 and summary['missing']['truncated'] and len(summary['missing']['entries'])==50


@pytest.mark.parametrize('foreground,pid,expected',[(22,'own',True),(11,'own',False),(33,'own',False),(22,'foreign',True),(0,'own',False)])
def test_windows_foreground_observation_distinguishes_client_top_and_other_owned_windows(foreground,pid,expected):
    from types import SimpleNamespace
    from tk_observation import windows_foreground
    def ancestor(client,kind):assert (client,kind)==(11,2);return 22
    def window():return foreground
    def process(hwnd,value):value._obj.value=os.getpid() if pid=='own' else os.getpid()+100;return 1
    result=windows_foreground(SimpleNamespace(winfo_id=lambda:11),SimpleNamespace(
        GetAncestor=ancestor,GetForegroundWindow=window,GetWindowThreadProcessId=process))
    assert result['client_hwnd']==11 and result['root_hwnd']==22
    assert result['root_is_foreground'] is expected and result['owned']==(pid=='own')


@pytest.mark.parametrize('damage',['missing','additional','duplicate','source','write'])
def test_real_pytest_inventory_refusal_never_runs_nodes(tmp_path,damage):
    sentinel=tmp_path/'body must not run'
    source=f'from pathlib import Path\ndef test_one():Path({str(sentinel)!r}).write_text("unsafe")\ndef test_two():pass\n'
    collection,raw,_=child_run(tmp_path,source,True)
    inventory=f.collection_result(collection,raw)
    if damage=='missing':inventory.append(dict(inventory[0],nodeid='::missing'))
    elif damage=='additional':inventory.pop()
    elif damage=='duplicate':inventory.append(dict(inventory[0]))
    elif damage=='source':inventory[0]['source_path']=str(tmp_path/'foreign.py')
    else:inventory.pop()
    root=tmp_path/'refused';root.mkdir()
    if damage=='write':(root/'inventory-mismatch.json').write_bytes(b'preserve reserved')
    code='import sys,json;sys.path.insert(0,sys.argv[1]);import stage4_qualification as f;raise SystemExit(f.pytest_child(sys.argv[2],False,[sys.argv[3]],json.loads(sys.argv[4])))'
    result=subprocess.run([sys.executable,'-B','-c',code,str(SCRIPTS),str(root),str(tmp_path/'case ü spaces.py'),json.dumps(inventory)],capture_output=True,timeout=30,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS=''))
    assert result.returncode!=0,repr((result.stdout,result.stderr))
    assert not sentinel.exists() and not (root/'manifest.json').exists()
    events,_=f.q.read_events(root/'events.jsonl',0)
    assert not any(e['event']=='node_start' for e in events)
    final=next((e for e in events if e['event']=='session_finish'),{})
    assert f.q.validate_test_evidence(root,result.returncode,final.get('pytest_exit_code'))['status']=='EVIDENCE_INCOMPLETE'
    diagnostic=root/'inventory-mismatch.json'
    if damage=='write':
        assert diagnostic.read_bytes()==b'preserve reserved'
        assert b'diagnostic write also failed' in result.stdout+result.stderr
    else:
        value=json.loads(diagnostic.read_text())
        assert value['mismatch'] and len(value['expected'])==len(inventory) and len(value['actual'])==2


def test_real_legacy_collection_repeats_exact_identities_and_sources_across_hash_seeds(tmp_path):
    inventories=[]
    modules=['tests/'+name for name in sorted(f.LEGACY_MODULES)]
    for seed in ('11','37'):
        root=tmp_path/seed;root.mkdir()
        code='import sys,json;sys.path.insert(0,sys.argv[1]);import stage4_qualification as f;raise SystemExit(f.pytest_child(sys.argv[2],True,json.loads(sys.argv[3])))'
        process=subprocess.run([sys.executable,'-B','-c',code,str(SCRIPTS),str(root),json.dumps(modules)],cwd=SCRIPTS.parent,
            capture_output=True,timeout=30,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS='',PYTHONHASHSEED=seed))
        assert process.returncode==0,repr((process.stdout,process.stderr))
        manifest=json.loads((root/'manifest.json').read_text())
        observations=[dict(nodeid=r['nodeid'],source_path=r['source_path'],junit=r['junit']) for r in manifest]
        assert observations and len({r['nodeid'] for r in observations})==len(observations)
        assert f.event_health(root)['status']=='COMPLETE'
        partitions=f.partition_inventory(manifest,SCRIPTS.parent)
        assert partitions['RETAINED_LEGACY']==[dict(r,partition='RETAINED_LEGACY') for r in manifest]
        assert not partitions['SUPPORTED_RUNTIME'] and not partitions['UNCLASSIFIED']
        inventories.append(observations)
    assert inventories[0]==inventories[1]


def test_real_inventory_order_only_difference_does_not_refuse_execution(tmp_path):
    collection,raw,_=child_run(tmp_path,'def test_one():pass\ndef test_two():pass\n',True)
    inventory=f.collection_result(collection,raw)
    root=tmp_path/'reordered';root.mkdir()
    code='import sys,json;sys.path.insert(0,sys.argv[1]);import stage4_qualification as f;raise SystemExit(f.pytest_child(sys.argv[2],False,[sys.argv[3]],json.loads(sys.argv[4])))'
    result=subprocess.run([sys.executable,'-B','-c',code,str(SCRIPTS),str(root),str(tmp_path/'case ü spaces.py'),json.dumps(list(reversed(inventory)))],
        capture_output=True,timeout=30,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS=''))
    assert result.returncode==0,repr((result.stdout,result.stderr))
    evidence=f.q.validate_test_evidence(root,0,0)
    assert evidence['status']=='COMPLETE' and evidence['counts']==dict(passed=2)
    assert not (root/'inventory-mismatch.json').exists()
