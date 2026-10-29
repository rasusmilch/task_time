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


def test_powershell_static_boundary_and_optional_parser():
    script=SCRIPTS/'qualify_stage4_windows.ps1';text=script.read_text()
    assert 'qualify_windows.ps1' not in text and 'stage4_qualification.py' in text
    assert 'ReadLineAsync' in text and 'Write-Progress' in text and 'WaitForExit(10000)' in text
    assert 'Get-Process' not in text and 'Stop-Process' not in text and 'ExecutionPolicy' not in text
    shell=shutil.which('pwsh') or shutil.which('powershell')
    if shell is None:pytest.skip('PowerShell parser/runtime unavailable; static assertions only')
    code='$e=$null;$t=$null;[System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$t,[ref]$e)>$null;if($e){$e|Out-String|Write-Error;exit 1}'
    result=subprocess.run([shell,'-NoProfile','-Command',code,str(script)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
