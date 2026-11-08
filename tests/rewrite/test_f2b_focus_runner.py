"""Portable fixed-runner tests. Doubles never establish native acceptance."""
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

SCRIPTS = Path(__file__).resolve().parents[2]/'scripts'
sys.path.insert(0,str(SCRIPTS))
r = importlib.import_module('qualify_f2b_focus')
from test_stage4_qualification import child_run


def expected_nodes():
    h='tests/rewrite/test_chronicle_history_modal.py::test_real_tk_history_parent_grab_focus_return_identity_and_guard'
    p='tests/rewrite/test_runtime4_native_focus.py::test_ordinary_schema4_history_parent_grab_focus_return_identity_and_guard'
    return {*(h+'['+m+']' for m in ('local','none','missing','reused')),
            *(p+'['+m+']' for m in ('local','none','missing','reused')),
            'tests/rewrite/test_chronicle_timesheet_ui.py::test_real_tk_timesheet_origin_return_competing_grab_destroy_and_reentry',
            'tests/rewrite/test_chronicle_timesheet_ui.py::test_real_tk_global_grab_and_deleted_focus_origin_are_not_replaced',
            'tests/rewrite/test_runtime4_native_focus.py::test_ordinary_schema4_timesheet_origin_return_competing_grab_destroy_and_reentry',
            'tests/rewrite/test_runtime4_native_focus.py::test_ordinary_schema4_global_grab_and_deleted_focus_origin_are_not_replaced',
            *('tests/rewrite/test_win32_focus.py::test_native_ordinary_activation_and_independent_modal_return_control['+a+'-'+b+']'
              for a in ('False','True') for b in ('historical-schema3','production-schema4'))}


@pytest.fixture(scope='module')
def collected(tmp_path_factory):
    root=tmp_path_factory.mktemp('fixed-source-collection')
    code='''import sys,os,pytest
sys.path.insert(0,sys.argv[1])
import qualify_f2b_focus as r
pytest.hookimpl(hookwrapper=True,tryfirst=True)(r.pytest_collection_modifyitems)
os.environ['CHRONICLE_FOCUS_PHASE']=sys.argv[2]
raise SystemExit(r.s.pytest_child(sys.argv[2],True,[*r.NODES,'-p','qualify_f2b_focus']))
'''
    command=[sys.executable,'-B','-c',code,str(SCRIPTS),str(root)]
    result=subprocess.run(command,cwd=r.REPO,capture_output=True,text=True,timeout=30,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
                 PYTEST_ADDOPTS='',PYTHONPATH=str(r.REPO/'src')))
    (root/'command.json').write_text(json.dumps(dict(command=command,exit_code=result.returncode)))
    (root/'stdout.log').write_text(result.stdout);(root/'stderr.log').write_text(result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads((root/'manifest.json').read_text())


def test_exact_sixteen_real_collected_source_and_fixture_identities(collected):
    assert set(r.NODES)==expected_nodes() and len(r.NODES)==16
    assert len(r.SUBJECTS)==12 and len(r.CONTROLS)==4
    historical='tests/rewrite/test_chronicle_history_modal.py::test_real_tk_history_parent_grab_focus_return_identity_and_guard[none]'
    production='tests/rewrite/test_runtime4_native_focus.py::test_ordinary_schema4_history_parent_grab_focus_return_identity_and_guard[none]'
    assert set(r.CONTROL_BINDINGS.values()) == {(historical,False),(historical,True),(production,False),(production,True)}
    assert set(row['nodeid'] for row in collected)==expected_nodes()
    r.validate_inventory(collected,r.REPO)
    assert all(row['source_path'].startswith(str(r.REPO/'tests/rewrite')) for row in collected)
    assert all(('ordinary' in row['fixtures']) == row['nodeid'].startswith(r.PRODUCTION+'::') for row in collected)
    assert all(row['fixtures'].count('root')==1 for row in collected if row['nodeid'] in r.SUBJECTS)


@pytest.mark.parametrize('damage',['additional','missing','duplicate','source','fixture source','fixture closure','parameters','deselected','execution source'])
def test_inventory_refuses_any_unreviewed_identity_before_tests(collected,damage):
    rows=deepcopy(collected)
    if damage=='additional':rows.append(dict(rows[0],nodeid=rows[0]['nodeid']+'suffix'))
    if damage=='missing':rows.pop()
    if damage=='duplicate':rows[-1]=deepcopy(rows[0])
    if damage=='source':rows[0]['source_path']=str(r.REPO/'wrong.py')
    if damage=='fixture source':rows[-1]['fixture_sources']['ordinary']=str(r.REPO/'wrong.py')
    if damage=='fixture closure':rows[-1]['fixtures'].append('connected')
    if damage=='parameters':rows[0]['parameters'].append('other')
    if damage=='deselected':rows[0]['selected']=False
    if damage=='execution source':rows[0]['fixture_sources']['tmp_path']='changed.py'
    with pytest.raises(ValueError):r.validate_inventory(rows,r.REPO,original=collected)


@pytest.mark.parametrize('damage',['expected','dirty','branch','remote','hash'])
def test_actual_source_gate_refuses_mismatch_without_execution(monkeypatch,damage):
    sha='a'*40
    observed=dict(revision=sha,branch='feature/chronicle-rewrite',dirty=False)
    if damage=='dirty':observed['dirty']=True
    if damage=='branch':observed['branch']='main'
    monkeypatch.setattr(r.q,'source_observation',lambda repo:observed)
    def git(repo,*args):
        return {('rev-parse','--show-toplevel'):str(r.REPO),('remote','get-url','origin'):'https://github.com/rasusmilch/task_time.git',
                ('ls-remote','origin','refs/heads/feature/chronicle-rewrite'):('b'*40 if damage=='remote' else sha)+'\trefs/heads/feature/chronicle-rewrite',
                ('ls-files','-z'):'AGENTS.md\0',('rev-parse','HEAD^{tree}'):'c'*40}[args]
    monkeypatch.setattr(r,'git',git)
    original=None
    if damage=='hash':original=dict(revision=sha,branch=observed['branch'],tree='c'*40,files={'AGENTS.md':'0'*64})
    with pytest.raises((ValueError,RuntimeError)):
        r.source_admission(r.REPO,'b'*40 if damage=='expected' else sha,original)


@pytest.mark.parametrize('target',['repository','dataset','evidence run','cloud','link','filesystem'])
def test_output_admission_refuses_before_evidence_reservation(tmp_path,monkeypatch,target):
    repo=tmp_path/'repo';repo.mkdir();parent=tmp_path/'parent';parent.mkdir()
    monkeypatch.setattr(r.q,'ntfs_evidence',lambda path:dict(filesystem='NTFS',drive_type=3))
    if target=='repository':parent=repo/'inside'
    if target=='dataset':(parent/'chronicle.sqlite3').write_bytes(b'owned fixture marker')
    if target=='evidence run':(parent/'owner.json').write_text('{}')
    if target=='cloud':monkeypatch.setenv('OneDrive',str(parent))
    if target=='link':
        linked=tmp_path/'alias';linked.symlink_to(parent,target_is_directory=True);parent=linked
    if target=='filesystem':monkeypatch.setattr(r.q,'ntfs_evidence',lambda path:(_ for _ in ()).throw(RuntimeError('not NTFS')))
    with pytest.raises((ValueError,RuntimeError)):r.reserve(repo,parent)
    assert not list(tmp_path.rglob('F2b-Focus-*'))


@pytest.mark.parametrize('bad_phase',['none','controls','subjects','source drift'])
def test_serial_controls_gate_subjects_and_never_retry(tmp_path,monkeypatch,collected,bad_phase):
    calls=[]
    def source(*args):
        calls.append('source')
        if bad_phase=='source drift' and calls.count('source')==2:raise ValueError('source drift')
    monkeypatch.setattr(r,'source_admission',source)
    monkeypatch.setattr(r,'desktop_admission',lambda:dict(synthetic=True))
    def execute(repo,root,label,exe,env,original=None):
        calls.append(label)
        if label=='collection':return collected
        assert {v['nodeid'] for v in original}==set(r.CONTROLS if label=='controls' else r.SUBJECTS)
        return dict(automated_status='FAIL' if label==bad_phase else 'PASS',executed=len(original))
    monkeypatch.setattr(r,'execute_phase',execute)
    monkeypatch.setattr(r,'control_proof',lambda *a:calls.append('control-proof'))
    monkeypatch.setattr(r,'subject_proof',lambda *a:calls.append('subject-proof'))
    raw={}
    if bad_phase=='source drift':
        with pytest.raises(ValueError,match='source drift'):r.workflow(r.REPO,tmp_path,'a'*40,{}, {},sys.executable,{},raw)
    else:r.workflow(r.REPO,tmp_path,'a'*40,{}, {},sys.executable,{},raw)
    assert calls.count('controls')==1
    assert calls.count('subjects')==(0 if bad_phase in ('controls','source drift') else 1)
    if bad_phase=='none':assert raw['completed']==16 and raw['automated_status']=='PASS'
    if bad_phase in ('controls','subjects'):assert raw['automated_status']=='FAIL'


@pytest.fixture(scope='module')
def actual_evidence(tmp_path_factory):
    base=tmp_path_factory.mktemp('real-collector-protocol')
    return child_run(base,'def test_fixture():pass\n')[:2]


@pytest.mark.parametrize('damage',['none','failed','skip','xfail','xpass','junit','health','cleanup','streams','inventory'])
def test_existing_event_junit_cleanup_contract_cannot_be_bypassed(tmp_path,monkeypatch,actual_evidence,damage):
    source,raw=actual_evidence;phase=tmp_path/'evidence';shutil.copytree(source,phase)
    raw=deepcopy(raw);raw['root']=str(phase)
    inventory=json.loads((phase/'manifest.json').read_text())
    if damage in ('failed','skip','xfail','xpass'):
        # Only outcome policy is doubled; real evidence checks below remain separate.
        status={'failed':'FAIL','skip':'PASS','xfail':'PASS','xpass':'PASS'}[damage]
        monkeypatch.setattr(r.s,'aggregate',lambda *args:dict(automated_status=status))
        raw['evidence']['counts']={dict(failed='failed',skip='skipped',xfail='xfailed',xpass='xpassed')[damage]:1}
    if damage=='junit':(phase/'junit.xml').unlink();raw['evidence']=r.q.validate_test_evidence(phase,0,0)
    if damage=='health':(phase/'event-health.json').write_text('{}')
    if damage=='cleanup':raw['cleanup']['verified']=False
    if damage=='streams':raw['cleanup']['streams_drained']=False
    if damage=='inventory':inventory=[]
    result=r.qualify_phase(inventory,raw)
    assert (result['automated_status']=='PASS')==(damage=='none')


@pytest.mark.parametrize('failure',['none','archive','members','hash'])
def test_existing_archive_readback_and_delivery_status_agree(tmp_path,monkeypatch,failure):
    root=tmp_path/'evidence';root.mkdir();(root/'payload.txt').write_text('real portable evidence')
    archive=r.s.archive
    def broken(root,complete):
        if failure=='archive':raise OSError('exclusive archive publication failed')
        path=archive(root,complete)
        if failure in ('members','hash'):
            with zipfile.ZipFile(path) as z:records={n:z.read(n) for n in z.namelist()}
            if failure=='members':records['unreviewed.txt']=b'extra'
            else:records['payload.txt']=b'CRC-valid changed evidence'
            with zipfile.ZipFile(path,'w') as z:
                for n,b in records.items():z.writestr(n,b)
        return path
    monkeypatch.setattr(r.s,'archive',broken)
    final=r.deliver(root,dict(automated_status='PASS',completed=16))
    assert (final['status']=='PASS')==(failure=='none')
    assert json.loads((root/'summary.json').read_text())==final
    assert r.STATUS_EXIT[final['status']]==(0 if failure=='none' else 4)
    if failure=='none':
        with zipfile.ZipFile(str(root)+'.zip') as z:assert json.loads(z.read('summary.json'))==final


def test_failed_prerequisite_never_calls_workflow(tmp_path,monkeypatch):
    root=tmp_path/'evidence';root.mkdir();calls=[]
    monkeypatch.setattr(r,'source_admission',lambda *a:dict(revision='a'*40,tree='b'*40))
    monkeypatch.setattr(r,'reserve',lambda *a:root)
    monkeypatch.setattr(r,'native_admission',lambda *a:(_ for _ in ()).throw(RuntimeError('required desktop unavailable')))
    monkeypatch.setattr(r,'workflow',lambda *a:calls.append('unsafe execution'))
    assert r.run(r.REPO,tmp_path,'a'*40)==4
    assert not calls
    assert json.loads((root/'summary.json').read_text())['status']=='BLOCKED'


def test_powershell_fixed_entrypoint_and_no_policy_or_input_workaround():
    text=(SCRIPTS/'qualify_f2b_focus_windows.ps1').read_text()
    assert '$Repo = Split-Path -Parent $PSScriptRoot' in text
    assert "'.venv\\Scripts\\python.exe'" in text and 'Get-Command python -CommandType Application' in text
    assert 'ReadLineAsync' in text and 'Heartbeat:' in text and 'total ' in text
    assert "@('collection','controls','subjects')" in text
    assert not any(v in text for v in ('Read-Host','Set-ExecutionPolicy','-ExecutionPolicy','SendInput','SetForegroundWindow','pip install'))
    assert r.STATUS_EXIT==dict(PASS=0,FAIL=4,BLOCKED=4,EVIDENCE_INCOMPLETE=4)
    assert r.q.LIMITS==dict(collection=90,test=120,phase=900,warning=30,cleanup=5)


def test_missing_independent_proof_stops_before_subjects(tmp_path,monkeypatch,collected):
    calls=[]
    monkeypatch.setattr(r,'source_admission',lambda *a:None)
    monkeypatch.setattr(r,'desktop_admission',lambda:dict(synthetic=True))
    def execute(repo,root,label,*args):
        calls.append(label)
        return collected if label=='collection' else dict(automated_status='PASS')
    monkeypatch.setattr(r,'execute_phase',execute)
    monkeypatch.setattr(r,'control_proof',lambda *a:(_ for _ in ()).throw(ValueError('missing actual native proof')))
    with pytest.raises(ValueError,match='missing actual native proof'):
        r.workflow(r.REPO,tmp_path,'a'*40,{}, {},sys.executable,{}, {})
    assert calls==['collection','controls']


def test_callback_diagnostic_capture_preserves_existing_hook_collection(tmp_path,monkeypatch):
    from types import SimpleNamespace
    error=ValueError('original diagnostic');captured=[(ValueError,error,None)]
    root=SimpleNamespace(test_errors=captured)
    item=SimpleNamespace(nodeid=r.SUBJECTS[-1],funcargs=dict(root=root))
    monkeypatch.setenv('CHRONICLE_FOCUS_PHASE',str(tmp_path))
    r.pytest_runtest_makereport(item,SimpleNamespace(when='call'))
    result=json.loads(next(tmp_path.glob('*-callbacks.json')).read_text())
    assert result['diagnostics']==[dict(type='ValueError',message='original diagnostic',traceback='ValueError: original diagnostic\n')]
    assert root.test_errors is captured and captured==[(ValueError,error,None)]


def test_native_prerequisite_is_not_spoofed_on_portable_host():
    if os.name!='nt':
        with pytest.raises(ValueError,match='Windows 11 client required'):r.native_admission(r.REPO)
