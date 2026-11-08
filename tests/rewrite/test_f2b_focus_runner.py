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
    result=subprocess.run(command,cwd=r.REPO,capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=30,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
                 PYTEST_ADDOPTS='',PYTHONPATH=str(r.REPO/'src')))
    (root/'command.json').write_text(json.dumps(dict(command=command,exit_code=result.returncode)))
    (root/'stdout.log').write_text(result.stdout);(root/'stderr.log').write_text(result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads((root/'manifest.json').read_text(encoding='utf-8'))


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
    def git(repo,*args,raw=False):
        return {('rev-parse','--show-toplevel'):str(r.REPO),('remote','get-url','origin'):'https://github.com/rasusmilch/task_time.git',
                ('ls-remote','origin','refs/heads/feature/chronicle-rewrite'):('b'*40 if damage=='remote' else sha)+'\trefs/heads/feature/chronicle-rewrite',
                ('ls-files','-z'):b'AGENTS.md\0',('rev-parse','HEAD^{tree}'):'c'*40}[args]
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
    inventory=json.loads((phase/'manifest.json').read_text(encoding='utf-8'))
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
    assert json.loads((root/'summary.json').read_text(encoding='utf-8'))==final
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
    assert json.loads((root/'summary.json').read_text(encoding='utf-8'))['status']=='BLOCKED'


def test_powershell_fixed_entrypoint_and_no_policy_or_input_workaround():
    text=(SCRIPTS/'qualify_f2b_focus_windows.ps1').read_text(encoding='utf-8')
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
    result=json.loads(next(tmp_path.glob('*-callbacks.json')).read_text(encoding='utf-8'))
    assert result['diagnostics']==[dict(type='ValueError',message='original diagnostic',traceback='ValueError: original diagnostic\n')]
    assert root.test_errors is captured and captured==[(ValueError,error,None)]


def test_native_prerequisite_is_not_spoofed_on_portable_host():
    if os.name!='nt':
        with pytest.raises(ValueError,match='Windows 11 client required'):r.native_admission(r.REPO)


@pytest.fixture
def unicode_inventory(tmp_path,collected):
    """Detached real-shaped inventory, with actual Unicode source fixture files."""
    repo=tmp_path/'Repository ü Ω';fixture=tmp_path/'Fixtures ü Ω';phase=tmp_path/'Evidence ü Ω'
    repo.mkdir();fixture.mkdir();phase.mkdir()
    rows=deepcopy(collected)
    for row in rows:
        relative=Path(row['source_path']).relative_to(r.REPO)
        target=repo/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(Path(row['source_path']).read_bytes());row['source_path']=str(target)
        for name,source in row['fixture_sources'].items():
            if Path(source).is_relative_to(r.REPO):target=repo/Path(source).relative_to(r.REPO)
            else:target=fixture/Path(source).name
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():target.write_bytes(Path(source).read_bytes())
            row['fixture_sources'][name]=str(target)
    r.q.write_json(phase/'manifest.json',rows)
    return repo,phase,rows


def test_actual_writer_and_guard_preserve_unicode_under_ansi_default(unicode_inventory,monkeypatch):
    repo,phase,rows=unicode_inventory;path=phase/'manifest.json';raw=path.read_bytes()
    assert 'ü Ω'.encode('utf-8') in raw and b'\\u00fc' not in raw
    wrong=json.loads(raw.decode('cp1252'))
    assert wrong[0]['source_path']!=rows[0]['source_path']
    with pytest.raises(ValueError):r.validate_inventory(wrong,repo)
    real_read=Path.read_text
    def ansi_default(path,*args,**kwargs):
        kwargs.setdefault('encoding','cp1252')
        return real_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',ansi_default)
    loaded=json.loads(r._read_utf8(path))
    assert loaded==rows and '\ufffd' not in r._read_utf8(path)
    r.validate_inventory(loaded,repo,original=rows)
    monkeypatch.setattr(r,'REPO',repo);monkeypatch.setenv('CHRONICLE_FOCUS_PHASE',str(phase))
    guard=r.pytest_collection_modifyitems(None,None,[]);next(guard)
    with pytest.raises(StopIteration):next(guard)
    assert path.read_bytes()==raw
    assert {row['nodeid'] for row in loaded}==expected_nodes()


@pytest.mark.parametrize('name',['selected-inventory.json','manifest.json'])
def test_corrupt_collection_inventory_prevents_fixture_authorization(tmp_path,collected,monkeypatch,name):
    r.q.write_json(tmp_path/'manifest.json',collected)
    if name=='selected-inventory.json':r.q.write_json(tmp_path/name,collected)
    path=tmp_path/name;bad=b'{"bad":"\xff"}';path.write_bytes(bad)
    monkeypatch.setenv('CHRONICLE_FOCUS_PHASE',str(tmp_path))
    guard=r.pytest_collection_modifyitems(None,None,[]);next(guard)
    with pytest.raises(ValueError,match='Invalid UTF-8 evidence') as error:next(guard)
    assert str(path) in str(error.value) and isinstance(error.value.__cause__,UnicodeDecodeError)
    assert path.read_bytes()==bad


@pytest.mark.parametrize('name',['source.json','owner.json','selected-inventory.json'])
def test_corrupt_child_admission_never_starts_pytest(tmp_path,monkeypatch,name):
    phase=tmp_path/'controls';phase.mkdir()
    r.q.write_json(tmp_path/'source.json',{})
    r.q.write_json(tmp_path/'owner.json',dict(kind='Chronicle F2b Focus'))
    r.q.write_json(phase/'selected-inventory.json',[])
    path=(phase if name=='selected-inventory.json' else tmp_path)/name
    bad=b'\xff\xfe{"invalid":"UTF16 is not the contract"}';path.write_bytes(bad)
    monkeypatch.setenv('CHRONICLE_FOCUS_EXPECTED','a'*40)
    monkeypatch.setattr(r,'source_admission',lambda *a:None)
    started=[];monkeypatch.setattr(r.s,'pytest_child',lambda *a,**kw:started.append('unexpected execution'))
    with pytest.raises(ValueError,match='Invalid UTF-8 evidence'):r.child(phase,'controls')
    assert not started and path.read_bytes()==bad


def test_corrupt_execution_manifest_stops_before_subject_phase(tmp_path,collected,monkeypatch):
    original_execute=r.execute_phase;calls=[]
    monkeypatch.setattr(r,'source_admission',lambda *a:None)
    monkeypatch.setattr(r,'desktop_admission',lambda:dict(protocol_double=True))
    monkeypatch.setattr(r.q,'WindowsChild',lambda *a:object())
    bad=b'[{"source_path":"\xff"}]'
    def monitor(child,phase,*args):
        (phase/'manifest.json').write_bytes(bad)
        return dict()
    monkeypatch.setattr(r.s,'phase_monitor',monitor)
    def execute(repo,root,label,executable,env,original=None):
        calls.append(label)
        if label=='collection':return collected
        return original_execute(repo,root,label,executable,env,original)
    monkeypatch.setattr(r,'execute_phase',execute)
    with pytest.raises(ValueError,match='Invalid UTF-8 evidence'):
        r.workflow(r.REPO,tmp_path,'a'*40,{}, {},sys.executable,{}, {})
    assert calls==['collection','controls']
    assert (tmp_path/'controls'/'manifest.json').read_bytes()==bad


def test_corrupt_independent_control_evidence_is_not_validated(tmp_path,monkeypatch):
    import test_win32_focus as controls
    directory=tmp_path/'controls'/'pytest-temp'/'case'/'inert-owned';directory.mkdir(parents=True)
    path=directory/'config.json';bad=b'{"node":"\xff"}';path.write_bytes(bad)
    calls=[];monkeypatch.setattr(controls,'_validate_control_result',lambda *a:calls.append('unexpected validator'))
    with pytest.raises(ValueError,match='Invalid UTF-8 evidence'):r.control_proof(tmp_path)
    assert not calls and path.read_bytes()==bad


def test_corrupt_native_observation_bytes_are_never_partially_accepted(tmp_path):
    phase=tmp_path/'subjects';phase.mkdir();path=phase/'stdout.log'
    bad=b'CHRONICLE_TK_OBSERVATION {}\n\xff';path.write_bytes(bad)
    with pytest.raises(ValueError,match='Invalid UTF-8 evidence'):r.subject_proof(tmp_path)
    assert path.read_bytes()==bad and not (tmp_path/'native-observations.json').exists()


@pytest.mark.parametrize('member',['summary.json','archive-members.json'])
@pytest.mark.parametrize('bad',[b'{"status":"PASS","extra":"\xff"}',b'\xff\xfe{\x00}\x00',b'\xef\xbb\xbf{}'])
def test_corrupt_archive_metadata_cannot_produce_pass(tmp_path,monkeypatch,member,bad):
    root=tmp_path/'evidence';root.mkdir();archive=r.s.archive
    def corrupt(root,complete):
        path=archive(root,complete)
        with zipfile.ZipFile(path) as z:records={n:z.read(n) for n in z.namelist()}
        records[member]=bad
        with zipfile.ZipFile(path,'w') as z:
            for name,value in records.items():z.writestr(name,value)
        return path
    monkeypatch.setattr(r.s,'archive',corrupt)
    final=r.deliver(root,dict(automated_status='PASS',completed=16))
    assert final['status']=='EVIDENCE_INCOMPLETE' and r.STATUS_EXIT[final['status']]!=0
    with zipfile.ZipFile(str(root)+'.zip') as z:assert z.read(member)==bad


def test_powershell_summary_requires_strict_utf8_before_json():
    text=(SCRIPTS/'qualify_f2b_focus_windows.ps1').read_text(encoding='utf-8')
    assert '$StrictUtf8 = [Text.UTF8Encoding]::new($false,$true)' in text
    binary="$SummaryBytes = [IO.File]::ReadAllBytes((Join-Path $Evidence 'summary.json'))"
    decode='$SummaryText = $StrictUtf8.GetString($SummaryBytes)'
    parse='$Summary = $SummaryText | ConvertFrom-Json'
    assert text.index(binary)<text.index(decode)<text.index(parse)
    assert 'Get-Content' not in text and '0xFEFF' in text


@pytest.mark.parametrize('data',[b'ASCII\n','Repository ü Ω\n'.encode('utf-8')])
def test_git_text_uses_strict_utf8_and_original_no_prompt_budget(monkeypatch,data):
    from types import SimpleNamespace
    calls=[]
    def run(command,**kw):calls.append((command,kw));return SimpleNamespace(stdout=data)
    monkeypatch.setattr(r.subprocess,'run',run)
    assert r.git(r.REPO,'rev-parse','--show-toplevel')==data.decode('utf-8').strip()
    _,kw=calls[0]
    assert not kw.get('text') and kw['timeout']==15 and kw['stdin'] is subprocess.DEVNULL
    assert kw['env']['GIT_TERMINAL_PROMPT']=='0' and kw['env']['GCM_INTERACTIVE']=='Never'


def test_invalid_git_text_refuses_without_ansi_fallback(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(r.subprocess,'run',lambda *a,**k:SimpleNamespace(stdout=b'\xff'))
    with pytest.raises(UnicodeDecodeError):r.git(r.REPO,'rev-parse','HEAD')


@pytest.mark.parametrize('bad',[None,b'bad\xff.py\0',b'not-terminated',b'missing.py\0',b'../escape\0'])
def test_raw_nul_filenames_preserve_exact_unicode_or_refuse(tmp_path,monkeypatch,bad):
    from types import SimpleNamespace
    import hashlib
    repo=tmp_path/'Repository ü Ω';repo.mkdir();names=['ASCII.py','module ü Ω.py','space and name.py']
    for name in names:(repo/name).write_bytes(b'fixture source bytes')
    sha='a'*40
    monkeypatch.setattr(r,'REPO',repo)
    monkeypatch.setattr(r.q,'source_observation',lambda *a:dict(revision=sha,branch='feature/chronicle-rewrite',dirty=False))
    encoded=b''.join(n.encode('utf-8')+b'\0' for n in names) if bad is None else bad
    def run(command,**kw):
        assert not kw.get('text') and 'encoding' not in kw
        args=tuple(command[3:])
        value={('rev-parse','--show-toplevel'):str(repo).encode('utf-8'),
               ('remote','get-url','origin'):b'https://github.com/rasusmilch/task_time.git',
               ('ls-remote','origin','refs/heads/feature/chronicle-rewrite'):(sha+'\trefs/heads/feature/chronicle-rewrite').encode(),
               ('ls-files','-z'):encoded,('rev-parse','HEAD^{tree}'):b'b'*40}[args]
        return SimpleNamespace(stdout=value)
    monkeypatch.setattr(r.subprocess,'run',run)
    if bad is None:
        value=r.source_admission(repo,sha)
        assert value['files']=={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in names}
        assert list(value['files'])==names
    else:
        with pytest.raises((ValueError,UnicodeDecodeError)):r.source_admission(repo,sha)
    assert encoded==(bad if bad is not None else b''.join(n.encode('utf-8')+b'\0' for n in names))


def test_failed_git_command_preserves_raw_diagnostic_bytes(monkeypatch):
    def failed(command,**kwargs):raise subprocess.CalledProcessError(128,command,output=b'raw\xff',stderr=b'error\xfe')
    monkeypatch.setattr(r.subprocess,'run',failed)
    with pytest.raises(RuntimeError) as error:r.git(r.REPO,'ls-remote','origin')
    assert "b'raw\\xff'" in str(error.value) and "b'error\\xfe'" in str(error.value)
