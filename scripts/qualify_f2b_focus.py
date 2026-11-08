"""Internal fixed F2b-Focus coordinator; invoked by the PowerShell entrypoint.

Reuse reviewed collector children, instrumentation, containment and archives.
This is not a general collector or a new native input implementation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile
from uuid import uuid4

import qualification_pytest as q
import stage4_qualification as s

REPO = Path(__file__).resolve().parents[1]
HISTORY = 'tests/rewrite/test_chronicle_history_modal.py'
SHEET = 'tests/rewrite/test_chronicle_timesheet_ui.py'
PRODUCTION = 'tests/rewrite/test_runtime4_native_focus.py'
CONTROL = 'tests/rewrite/test_win32_focus.py'
CONTROL_FUNCTION = 'test_native_ordinary_activation_and_independent_modal_return_control'
SUBJECTS = (
    *(HISTORY+'::test_real_tk_history_parent_grab_focus_return_identity_and_guard['+m+']'
      for m in ('local', 'none', 'missing', 'reused')),
    SHEET+'::test_real_tk_timesheet_origin_return_competing_grab_destroy_and_reentry',
    SHEET+'::test_real_tk_global_grab_and_deleted_focus_origin_are_not_replaced',
    *(PRODUCTION+'::test_ordinary_schema4_history_parent_grab_focus_return_identity_and_guard['+m+']'
      for m in ('local', 'none', 'missing', 'reused')),
    PRODUCTION+'::test_ordinary_schema4_timesheet_origin_return_competing_grab_destroy_and_reentry',
    PRODUCTION+'::test_ordinary_schema4_global_grab_and_deleted_focus_origin_are_not_replaced',
)
CONTROLS = tuple(CONTROL+'::'+CONTROL_FUNCTION+'['+flag+'-'+role+']'
                 for flag in ('False', 'True') for role in ('historical-schema3', 'production-schema4'))
NODES = CONTROLS+SUBJECTS
CONTROL_BINDINGS = {
    node: (SUBJECTS[1] if role == 'historical-schema3' else SUBJECTS[7], flag == 'True')
    for node, (flag, role) in zip(CONTROLS, ((a,b) for a in ('False','True')
                                          for b in ('historical-schema3','production-schema4')))
}
STATUS_EXIT = dict(PASS=0, FAIL=4, BLOCKED=4, EVIDENCE_INCOMPLETE=4)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _read_utf8(path):
    """Collector evidence is UTF-8 without conversion or locale fallback."""
    try:
        return Path(path).read_text(encoding='utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise ValueError('Invalid UTF-8 evidence: '+str(path)) from exc


def git(repo, *args, raw=False):
    try:
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                timeout=15, check=True, stdin=subprocess.DEVNULL,
                                env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never',
                                         SSH_ASKPASS_REQUIRE='never'))
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('Git admission failed: '+repr(args)+'; exit '+str(exc.returncode)
                           +'; stdout '+repr(exc.stdout)+'; stderr '+repr(exc.stderr)) from exc
    return result.stdout if raw else result.stdout.decode('utf-8', errors='strict').strip()


def source_admission(repo, expected, original=None):
    require(re.fullmatch(r'[0-9a-fA-F]{40}', expected), 'Full forty-character revision required')
    repo = s.safe_directory(repo)
    require(repo == REPO and Path(git(repo, 'rev-parse', '--show-toplevel')) == repo,
            'Wrong repository root or controller source')
    source = q.checked_source(repo, expected)
    require(source == dict(revision=expected.lower(), branch='feature/chronicle-rewrite'),
            'Exact source revision/branch mismatch')
    require(git(repo, 'remote', 'get-url', 'origin') in (
        'https://github.com/rasusmilch/task_time.git', 'git@github.com:rasusmilch/task_time.git'),
        'Wrong origin repository')
    remote = git(repo, 'ls-remote', 'origin', 'refs/heads/feature/chronicle-rewrite').split()
    require(remote == [source['revision'], 'refs/heads/feature/chronicle-rewrite'],
            'Local/remote source disagreement')
    filenames = git(repo, 'ls-files', '-z', raw=True)
    require(type(filenames) is bytes and filenames.endswith(b'\0'), 'Incomplete raw Git filename inventory')
    paths = [value.decode('utf-8', errors='strict') for value in filenames.split(b'\0')[:-1]]
    require(all(paths) and len(paths)==len(set(paths)), 'Invalid raw Git filename inventory')
    hashes = {}
    for name in paths:
        path = repo/name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts
                and path.resolve().is_relative_to(repo) and path.is_file() and not path.is_symlink()
                and not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400,
                'Unsuitable source file: '+name)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    value = dict(**source, tree=git(repo, 'rev-parse', 'HEAD^{tree}'), files=hashes)
    if original is not None:
        require(value == original, 'Source/hash drift during qualification')
    return value


def output_parent(repo, parent):
    """Admit the existing ancestor before creating a dedicated default parent."""
    path = Path(parent).absolute()
    existing = path
    while not existing.exists():
        require(not existing.is_symlink(), 'Dangling output link')
        existing = existing.parent
    s.safe_directory(existing)
    require(path.resolve() == path and not path.is_relative_to(repo)
            and not repo.is_relative_to(path), 'Output overlaps or aliases repository')
    for ancestor in (path, *path.parents):
        require(not any((ancestor/n).exists() for n in ('owner.json','collector-owner.json','chronicle.sqlite3')),
                'Output overlaps a dataset or an existing evidence run')
    for variable in ('OneDrive','OneDriveConsumer','OneDriveCommercial','Dropbox'):
        value = os.environ.get(variable)
        require(not value or not path.is_relative_to(Path(value).resolve()), 'Cloud output refused')
    require(not any(p.casefold() in ('onedrive','dropbox','google drive','icloud drive')
                    or p.casefold().startswith('onedrive - ') for p in path.parts), 'Cloud output refused')
    q.ntfs_evidence(existing)  # Actual fixed local NTFS, before any mkdir/evidence.
    path.mkdir(parents=True, exist_ok=True)
    s.safe_directory(path)
    q.ntfs_evidence(path)
    return path


def reserve(repo, parent):
    parent = output_parent(repo, parent)
    root = parent/('F2b-Focus-'+uuid4().hex)
    root.mkdir()  # Exclusive, no reuse and no cleanup of previous output.
    q.write_json(root/'owner.json', dict(kind='Chronicle F2b Focus', root=str(root), id=str(uuid4())))
    print('Evidence directory: '+str(root), flush=True)
    return root


def native_admission(repo):
    require(os.name == 'nt' and sys.platform == 'win32', 'Windows 11 client required')
    windows = sys.getwindowsversion()
    require(windows.build >= 22000 and windows.product_type == 1, 'Windows 11 client required')
    require(os.environ.get('CHRONICLE_FOCUS_POWERSHELL') == '5.1', 'Windows PowerShell 5.1 wrapper required')
    runtime = q.runtime_evidence()
    require(not runtime['errors'] and sys.version_info >= (3,11)
            and s.sqlite_version() >= (3,37,0) and runtime.get('tzdata') == '2026.5',
            'Incomplete Python/SQLite/Tcl/tzdata prerequisites: '+repr(runtime))
    runtime['dependencies'] = {n: importlib.metadata.version(n) for n in ('pytest','tkcalendar','tzlocal')}
    runtime['schema_required'] = s.ORDINARY_SCHEMA_REQUIRED
    require(int(runtime['dependencies']['pytest'].split('.')[0]) >= 8, 'pytest 8+ required')
    sys.path[:0] = [str(repo/'src'), str(repo/'tests/rewrite')]
    import chronicle
    import win32_focus as focus
    import test_win32_focus as controls
    require(Path(chronicle.__file__).resolve() == repo/'src/chronicle/__init__.py', 'Wrong imported Chronicle')
    require(set(focus.NODES) == set(SUBJECTS), 'Native subject authorization differs')
    runtime['chronicle'] = str(Path(chronicle.__file__).resolve())
    runtime['session'] = desktop_admission()
    executable, env, identity = controls._control_python(dict(os.environ))
    runtime['interpreter'] = identity
    # Actual Tk with no personal Tk()/profile loading; no input is generated.
    import _tkinter
    tk = _tkinter.create(None, 'ChronicleFocusAdmission', 'ChronicleFocusAdmission', False, True, True, False, None)
    try:
        tk.call('wm','withdraw','.')
        runtime['actual_tk'] = dict(tcl=tk.call('info','patchlevel'), tk=tk.call('package','require','Tk'))
    finally:
        tk.call('destroy','.')
    return runtime, executable, env


def desktop_admission():
    # Existing read-only native admission APIs; no new Win32 call/input mechanism.
    import win32_focus as focus
    api = focus.Win32API()
    value = dict(session=api.session(), desktop=api.desktop(api.kernel.GetCurrentThreadId()))
    api.keys()
    return value


def validate_inventory(rows, repo, nodes=NODES, original=None):
    require(len(rows) == len(nodes) and {r['nodeid'] for r in rows} == set(nodes),
            'Unexpected, missing or duplicate collected node')
    for row in rows:
        node = row['nodeid']; module = node.split('::')[0]
        require(row['source_path'] == str(repo/module) and row['selected'], 'Wrong source or deselection')
        expected = {'request','tmp_path','tmp_path_factory'}
        if node in CONTROLS:
            expected |= {'subject_node','failed_return'}
            params = {'subject_node','failed_return'}
        else:
            expected |= {'root', 'ordinary' if module == PRODUCTION else 'connected'}
            params = {'mode'} if node in SUBJECTS[:4]+SUBJECTS[6:10] else set()
            if params or node in (SUBJECTS[4],SUBJECTS[10]): expected.add('monkeypatch')
            expected |= params
        require(set(row['fixtures']) == expected and set(row['parameters']) == params,
                'Unexpected fixture/parameter closure: '+node)
        for name in expected-params-{'root','connected','ordinary','request'}:
            require(all(d['module'].startswith('_pytest.') for d in row['fixture_definitions'][name]),
                    'Unreviewed built-in fixture source: '+name)
        for name, source in (('root','test_app.py'),('connected','test_app.py'),('ordinary','test_runtime4_ui.py')):
            if name in expected:
                require(row['fixture_sources'][name] == str(repo/'tests/rewrite'/source),
                        'Changed fixture source: '+name)
                require(row['fixture_definitions'][name][-1] == dict(module=source[:-3],function=name),
                        'Changed fixture definition: '+name)
    if original is not None:
        keys = ('nodeid','source_path','fixtures','parameters','fixture_sources','fixture_definitions','junit','junit_prefix','selected')
        identity = lambda row: {k: sorted(row[k]) if k in ('fixtures','parameters') else row[k] for k in keys}
        require({r['nodeid']:identity(r) for r in rows} == {r['nodeid']:identity(r) for r in original},
                'Execution fixture/source inventory differs from original collection')


def pytest_collection_modifyitems(session, config, items):
    """Fixed-child guard, after the existing collector builds source-aware rows."""
    yield
    phase = Path(os.environ['CHRONICLE_FOCUS_PHASE'])
    original_path = phase/'selected-inventory.json'
    original = json.loads(_read_utf8(original_path)) if original_path.exists() else None
    nodes = tuple(r['nodeid'] for r in original) if original is not None else NODES
    validate_inventory(json.loads(_read_utf8(phase/'manifest.json')), REPO, nodes, original)


def pytest_runtest_makereport(item, call):
    """Retain the existing hook's actual diagnostics; never replace/suppress it."""
    import traceback
    phase = Path(os.environ['CHRONICLE_FOCUS_PHASE'])
    root = item.funcargs.get('root')
    errors = getattr(root,'test_errors',[]) if root is not None else []
    q.write_json(phase/(hashlib.sha256(item.nodeid.encode()).hexdigest()+'-'+call.when+'-callbacks.json'),
        dict(nodeid=item.nodeid,phase=call.when,root_present=root is not None,
             diagnostics=[dict(type=t.__name__,message=str(e),traceback=''.join(traceback.format_exception(t,e,b)))
                          for t,e,b in errors]))


def child(root, phase):
    import pytest
    import qualify_f2b_focus as plugin
    expected = os.environ['CHRONICLE_FOCUS_EXPECTED']
    source_admission(REPO,expected,json.loads(_read_utf8(root.parent/'source.json')))
    require(json.loads(_read_utf8(root.parent/'owner.json'))['kind']=='Chronicle F2b Focus',
            'Missing focus output ownership')
    # Hooks are local to this fixed child. Do not alter existing collector code.
    pytest.hookimpl(hookwrapper=True, tryfirst=True)(plugin.pytest_collection_modifyitems)
    os.environ['CHRONICLE_FOCUS_PHASE'] = str(root)
    inventory = json.loads(_read_utf8(root/'selected-inventory.json')) if phase != 'collection' else None
    nodes = CONTROLS if phase == 'controls' else SUBJECTS if phase == 'subjects' else NODES
    return s.pytest_child(root, phase == 'collection',
        arguments=[*nodes, '-p', 'qualify_f2b_focus', '--maxfail=1'], inventory=inventory)


def execute_phase(repo, root, label, executable, env, original=None):
    phase = root/label; phase.mkdir()
    if original is not None: q.write_json(phase/'selected-inventory.json', original)
    args = [executable,'-u','-B',str(Path(__file__).resolve()),'--child',str(phase),'--phase',label]
    q.write_json(phase/'command.json', dict(command=args,cwd=str(repo),started_utc=utc()))
    print('Qualification phase: '+label, flush=True)
    # Collection is already a contained capability check; no native input then.
    raw = s.phase_monitor(q.WindowsChild(args,repo,env),phase,dict(q.LIMITS),label)
    raw.update(root=str(phase), ended_utc=utc())
    q.write_json(phase/'process-result.json',raw)
    if label == 'collection':
        inventory = s.collection_result(phase,raw)
        validate_inventory(inventory,repo)
        events,_ = q.read_events(phase/'events.jsonl',0)
        require(not any(e['event']=='collection_report' and e['outcome']!='passed' for e in events),
                'Collection failed or skipped')
        return inventory
    rows = json.loads(_read_utf8(phase/'manifest.json'))
    validate_inventory(rows,repo,tuple(r['nodeid'] for r in original),original)
    value = qualify_phase(original,raw)
    value['raw'] = raw
    q.write_json(phase/'qualification-result.json',value)
    return value


def qualify_phase(original, raw):
    value = s.aggregate(original,raw)
    counts = raw['evidence'].get('counts',{})
    # No applicability waiver is available for this fixed native focus scope.
    if value['automated_status'] == 'PASS' and counts != {'passed':len(original)}:
        value['automated_status'] = 'EVIDENCE_INCOMPLETE'
    return value


def control_proof(root):
    import test_win32_focus as controls
    found = {}
    for path in regular_files(root/'controls'/'pytest-temp'):
        if path.name != 'config.json' or not path.parent.name.startswith('inert-'):continue
        config = json.loads(_read_utf8(path))
        key = (config['node'],config['failed_return'])
        require(type(key[1]) is bool and key in CONTROL_BINDINGS.values() and key not in found,
                'Wrong or duplicate control identity')
        final = controls._control_read(path.parent,'outer-final')
        require(final is not None, 'Missing control final evidence')
        controls._validate_control_result(path.parent,config['nonce'],final['code'],key[1],key[0])
        found[key] = str(path.parent)
    require(set(found) == set(CONTROL_BINDINGS.values()), 'Missing independent native controls')
    q.write_json(root/'independent-controls.json', [dict(subject=n,negative=f,directory=p) for (n,f),p in found.items()])


def subject_proof(root):
    import win32_focus as focus
    records = []
    for line in _read_utf8(root/'subjects'/'stdout.log').splitlines():
        if line.startswith('CHRONICLE_TK_OBSERVATION '):
            records.append(json.loads(line[len('CHRONICLE_TK_OBSERVATION '):]))
    for node in SUBJECTS:
        rows = [v for v in records if v.get('driver',{}).get('node') == node]
        require([r['phase'] for r in rows] == list(focus.NODES[node]), 'Missing native PRECONDITION/RESULT: '+node)
        require(all(r['driver']['state']=='DISARMED' and r['driver']['precondition_verified'] for r in rows),
                'Native focus evidence unverified: '+node)
    q.write_json(root/'native-observations.json',records)


def workflow(repo, root, expected, source, runtime, executable, env, raw):
    inventory = execute_phase(repo,root,'collection',executable,env)
    for label,nodes in (('controls',CONTROLS),('subjects',SUBJECTS)):
        source_admission(repo,expected,source)
        raw['desktop_'+label] = desktop_admission()
        selected = [r for r in inventory if r['nodeid'] in nodes]
        raw['execution_attempted'] = True
        result = execute_phase(repo,root,label,executable,env,selected)
        raw[label] = result
        raw['completed'] = raw.get('completed',0)+result.get('executed',
            result.get('raw',{}).get('progress',{}).get('completed',0))
        if result['automated_status'] != 'PASS':
            raw['automated_status'] = result['automated_status']
            return
        if label == 'controls':control_proof(root)
        else:subject_proof(root)
    source_admission(repo,expected,source)
    require(raw.get('completed')==16, 'Incomplete total execution count')
    raw.update(source_verified_after=True,automated_status='PASS')


def utc():
    return datetime.now(timezone.utc).isoformat()


def regular_files(root):
    def failure(error):raise error
    for directory, dirs, files in os.walk(root,followlinks=False,onerror=failure):
        dirs[:] = [n for n in dirs if not (Path(directory)/n).is_symlink()
                   and not getattr((Path(directory)/n).lstat(),'st_file_attributes',0)&0x400]
        for name in files:
            import stat
            path = Path(directory)/name
            info = path.lstat()
            if stat.S_ISREG(info.st_mode) and not path.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400:
                yield path


def deliver(root, raw):
    """Existing archive publication plus independent available-hash readback."""
    root = s.safe_directory(root)
    hashes = {}
    for path in regular_files(root):
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    q.write_json(root/'member-hashes.json',hashes)
    pending = dict(raw,status='EVIDENCE_INCOMPLETE',archive_status='NOT COMPLETED')
    with q.JsonRecord(root/'summary.json') as record:
        record.write(pending)
        try:
            complete = dict(raw,status=raw['automated_status'],archive_status='VERIFIED',
                            delivery_requires_successful_controller_acknowledgement=True)
            destination = s.archive(root,complete)
            with zipfile.ZipFile(destination) as archive:
                members = json.loads(archive.read('archive-members.json').decode('utf-8', errors='strict'))
                require(len(archive.namelist())==len(set(archive.namelist()))
                        and set(archive.namelist())==set(members['files']) and archive.testzip() is None,
                        'Archive members/CRC differ')
                require(json.loads(archive.read('summary.json').decode('utf-8', errors='strict'))==complete, 'Archive/source status disagreement')
                for name,h in hashes.items():
                    require(hashlib.sha256(archive.read(name)).hexdigest()==h, 'Archive member hash differs: '+name)
            record.write(complete)
            print('Evidence ZIP: '+str(destination),flush=True)
            return complete
        except BaseException as exc:
            pending.update(status='EVIDENCE_INCOMPLETE',archive_status='FAILED_OR_UNVERIFIED',archive_error=repr(exc))
            record.write(pending)
            print('Evidence ZIP unavailable or unverified: '+str(root)+'.zip',flush=True)
            return pending


def run(repo, parent, expected):
    root = None
    raw = dict(automated_status='BLOCKED',started_utc=utc(),source_expected=expected,
               expected=16,completed=0,F2_filesystem='NOT RUN',F3='NOT RUN',F4='NOT RUN')
    try:
        require(re.fullmatch(r'[0-9a-fA-F]{40}',expected) and s.safe_directory(repo)==REPO,
                'Exact reviewed source root/full SHA required')
        # No evidence directory is created on an untrusted output filesystem.
        root = reserve(repo,parent)
        q.write_json(root/'controller.json',dict(command=[sys.executable,*sys.argv],pid=os.getpid(),
            python=sys.version,executable=sys.executable,prefix=sys.prefix,base_prefix=sys.base_prefix,
            host=json.loads(os.environ.get('CHRONICLE_FOCUS_HOST','{}'))))
        source = source_admission(repo,expected)
        print('Reviewed source: '+source['revision']+' tree '+source['tree'],flush=True)
        q.write_json(root/'source.json',source)
        runtime, executable, env = native_admission(repo)
        runtime['host'] = json.loads(os.environ.get('CHRONICLE_FOCUS_HOST','{}'))
        runtime['filesystem'] = q.ntfs_evidence(root)
        q.write_json(root/'environment.json',runtime)
        profile = root/'isolated-profile';profile.mkdir()
        env.update(HOME=str(profile),USERPROFILE=str(profile),LOCALAPPDATA=str(profile),XDG_DATA_HOME=str(profile),
                   CHRONICLE_FOCUS_EXPECTED=expected,
                   PYTHONPATH=os.pathsep.join(str(repo/n) for n in ('src','tests/rewrite','scripts')),
                   PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONIOENCODING='utf-8',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
        env.pop('PYTEST_ADDOPTS',None);env.pop('PYTEST_PLUGINS',None)
        q.write_json(root/'environment-overrides.json',{k:env.get(k) for k in ('HOME','USERPROFILE','LOCALAPPDATA','XDG_DATA_HOME','PYTHONPATH','PYTHONDONTWRITEBYTECODE','PYTEST_DISABLE_PLUGIN_AUTOLOAD','__PYVENV_LAUNCHER__')})
        workflow(repo,root,expected,source,runtime,executable,env,raw)
    except BaseException as exc:
        raw.update(automated_status='EVIDENCE_INCOMPLETE' if raw.get('execution_attempted') else 'BLOCKED',
                   error=repr(exc),notes=getattr(exc,'__notes__',[]))
    if root is not None and raw.get('execution_attempted'):
        try:
            source_admission(repo,expected,source)
            raw['source_verified_after'] = True
        except BaseException as exc:
            raw.update(automated_status='EVIDENCE_INCOMPLETE',source_recheck_error=repr(exc))
        raw['demonstrated_failures'] = []
        for label in ('controls','subjects'):
            events,_ = q.read_events(root/label/'events.jsonl',0)
            raw['demonstrated_failures'].extend(dict(phase=label,report=e) for e in events
                                               if e['event']=='report' and e['outcome']=='failed')
    raw['ended_utc'] = utc()
    if root is None:
        print('Final status: BLOCKED — '+raw.get('error','Admission refused'),flush=True)
        print('No evidence directory or ZIP created',flush=True)
        return 4
    q.write_json(root/'execution-result.json',raw)
    try:
        final = deliver(root,raw)
    except BaseException as exc:
        final = dict(status='EVIDENCE_INCOMPLETE',delivery_error=repr(exc))
        print('Delivery incomplete; retained diagnostics: '+repr(exc),flush=True)
    print('Complete evidence directory: '+str(root),flush=True)
    print('Final status: '+final['status'],flush=True)
    return STATUS_EXIT[final['status']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=REPO)
    parser.add_argument('--output-parent',type=Path)
    parser.add_argument('--expected-revision')
    parser.add_argument('--child',type=Path)
    parser.add_argument('--phase',choices=('collection','controls','subjects'))
    args = parser.parse_args()
    if args.child:
        require(args.phase is not None, 'Fixed child phase required')
        return child(args.child,args.phase)
    require(args.output_parent is not None and args.expected_revision is not None, 'PowerShell entrypoint arguments required')
    return run(args.repo,args.output_parent,args.expected_revision)


if __name__ == '__main__':
    raise SystemExit(main())
