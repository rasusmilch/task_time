"""Opt-in full-source Windows evidence wrapper, separate from frozen scopes.

Only stdlib plus installed pytest. Reuse the reviewed collector's Job Object,
watchdog, byte capture, JUnit/event reconciliation and exclusive archive mechanics.
No production imports or dataset discovery. Never qualify operator input or Sleep.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile
from uuid import uuid4

import qualification_pytest as q


class FullPlugin(q.QualificationPlugin):
    """Collect every original node; callbacks may create Tk, dialogs may not open."""
    def __init__(self, root):
        super().__init__(q.Events(Path(root)/'events.jsonl'), root, 'Stage4Full', enforce_manifest=False)

    def callback_allowed(self):
        return True

    def pytest_collectreport(self, report):
        self.events.emit('collection_report',nodeid=report.nodeid,outcome=report.outcome,
                         diagnostic=str(report.longrepr) if report.failed or report.skipped else None)

    def pytest_collection_modifyitems(self, session, config, items):
        super().pytest_collection_modifyitems(session, config, items)
        for row in self.manifest:
            row.update(category='audited-callback', reason='Full source regression; dialogs obstruct; native operator input is separate')
            self.categories[row['nodeid']]='audited-callback'
        self.manifest_record.write(self.manifest)


def pytest_child(root, collect_only=False, arguments=None):
    import pytest
    plugin=FullPlugin(root)
    # Capture inventory before pytest's built-in -k/mark filtering, if used by
    # controlled regression fixtures. Production supplies no selection filters.
    pytest.hookimpl(tryfirst=True)(FullPlugin.pytest_collection_modifyitems)
    for name in ('pytest_runtest_setup','pytest_runtest_call','pytest_runtest_teardown'):
        pytest.hookimpl(tryfirst=True)(getattr(q.QualificationPlugin,name))
    guard=q.DialogGuard(plugin.events,plugin.callback_allowed)
    guard.install()
    args=['-vv','-rA','-p','no:cacheprovider','-o','addopts=', '--basetemp',str(Path(root)/'pytest-temp')]
    args+=['--collect-only'] if collect_only else ['--junitxml',str(Path(root)/'junit.xml')]
    args+=arguments if arguments is not None else ['.']
    q.write_json(Path(root)/'pytest-arguments.json',args)
    try:
        return int(pytest.main(args,plugins=[plugin]))
    finally:
        guard.restore()
        if plugin.manifest_record:
            plugin.manifest_record.__exit__(*sys.exc_info())


def safe_directory(path):
    path=Path(path).absolute()
    if str(path).startswith(('//','\\\\')) or path.resolve()!=path or not path.is_dir():
        raise ValueError('Existing canonical local directory required: '+str(path))
    for p in (path,*path.parents):
        info=p.lstat()
        if p.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('Reparse/symlink directory refused: '+str(p))
        if (p/'chronicle.sqlite3').exists():
            raise ValueError('Output/source location overlaps Chronicle dataset: '+str(p))
    return path


def reserve(repo, parent):
    repo,parent=safe_directory(repo),safe_directory(parent)
    if parent.is_relative_to(repo) or repo.is_relative_to(parent):
        raise ValueError('Select a separate qualification parent, not repository/ancestor')
    cloud=[os.environ.get(n) for n in ('OneDrive','OneDriveConsumer','OneDriveCommercial','Dropbox')]
    for value in cloud:
        if value and parent.is_relative_to(Path(value).resolve()):
            raise ValueError('Cloud-synchronized output refused')
    if any(part.casefold() in ('onedrive','dropbox','google drive','icloud drive') or part.casefold().startswith('onedrive - ') for part in parent.parts):
        raise ValueError('Cloud-synchronized output refused')
    if os.name=='nt':q.ntfs_evidence(parent)
    root=parent/('Chronicle Stage4 '+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+' '+uuid4().hex)
    root.mkdir()  # Exclusive reservation; no existing directory may be reused.
    q.write_json(root/'owner.json',dict(kind='Stage4 full qualification',root=str(root),id=str(uuid4())))
    print('Evidence directory: '+str(root),flush=True)
    return root


def collection_result(root, raw):
    """Collection has no runtest/JUnit requirement, but must terminate completely."""
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    events,_=q.read_events(root/'events.jsonl',0)
    complete=[e for e in events if e['event']=='collection_complete']
    final=[e for e in events if e['event']=='session_finish']
    nodes=[r['nodeid'] for r in manifest]
    if (raw['process_exit_code']!=0 or len(complete)!=1 or len(final)!=1
            or final[0]['pytest_exit_code']!=0 or len(nodes)!=len(set(nodes)) or not nodes
            or complete[0]['selected']!=sum(r['selected'] for r in manifest)
            or not raw['cleanup'].get('verified') or not raw['cleanup'].get('streams_drained')
            or raw['termination_reason']):
        raise ValueError('Collection incomplete or cleanup/capture unverified')
    return manifest


def aggregate(collection, raw):
    """Raw execution, evidence, native gates and final delivery stay separate."""
    result=dict(automated_status='EVIDENCE_INCOMPLETE',test_execution_status=raw['test_execution_status'],
        pytest_exit_code=raw['pytest_exit_code'],process_exit_code=raw['process_exit_code'],
        evidence=raw['evidence'],cleanup=raw['cleanup'],progress=raw['progress'],
        F3='NOT RUN',F4='NOT RUN',diagnostics=[])
    if raw['evidence']['status']!='COMPLETE' or not raw['cleanup'].get('verified') or not raw['cleanup'].get('streams_drained'):
        result['diagnostics'].append('Execution evidence or owned cleanup is incomplete')
        return result
    manifest=json.loads((Path(raw['root'])/'manifest.json').read_text(encoding='utf-8'))
    events,_=q.read_events(Path(raw['root'])/'events.jsonl',0)
    collection_skips=[e for e in events if e['event']=='collection_report' and e['outcome']=='skipped']
    if Counter(r['nodeid'] for r in collection)!=Counter(r['nodeid'] for r in manifest):
        result['diagnostics'].append('Original collection and executed inventory differ')
        return result
    selected={r['nodeid'] for r in manifest if r['selected']}
    counts=raw['evidence']['counts']
    result.update(selected=len(selected),executed=raw['progress']['completed'],counts=counts,
                  not_run=[r for r in manifest if not r['selected']],collection_skips=collection_skips)
    # Skipped/xfailed evidence is retained distinctly. Any skip means the entire
    # source suite was not qualified: no blanket native PASS from partial coverage.
    if raw['test_execution_status']=='PASS' and selected and not result['not_run'] and not collection_skips:
        result['automated_status']='PASS' if not any(counts.get(k,0) for k in ('skipped','xfailed','xpassed')) else 'EVIDENCE_INCOMPLETE'
        if result['automated_status']!='PASS':result['diagnostics'].append('Skipped/expected-failure/native-deferred cases require independent applicability adjudication')
    else:
        result['automated_status']='FAIL' if counts.get('failed',0) or counts.get('error',0) else 'EVIDENCE_INCOMPLETE'
    return result


def deliver(root, raw):
    """ZIP beside root; reopen, CRC and exact expected member verification."""
    root=Path(root)
    summary=dict(raw,status='FINALIZING',archive_status='NOT COMPLETED')
    with q.JsonRecord(root/'summary.json') as record:
        record.write(summary)
        try:
            completed=dict(raw,status=raw['automated_status'],archive_status='VERIFIED')
            destination=archive(root,completed)
            with zipfile.ZipFile(destination) as delivered_zip:
                member_record=json.loads(delivered_zip.read('archive-members.json'))
                expected={Path(n).as_posix() for n in member_record['files']}
                if set(delivered_zip.namelist())!=expected or delivered_zip.testzip() is not None:
                    raise ValueError('Archive membership/CRC verification failed')
                if json.loads(delivered_zip.read('summary.json'))!=completed:
                    raise ValueError('Archive final summary differs')
            record.write(completed)
            print('Verified evidence directory: '+str(root),flush=True)
            print('Verified evidence ZIP: '+str(destination),flush=True)
            return 0 if completed['status']=='PASS' else 4
        except BaseException as exc:
            summary.update(raw,status='EVIDENCE_INCOMPLETE',archive_status='FAILED_OR_UNVERIFIED',archive_error=repr(exc))
            record.write(summary)
            print('Archive incomplete; evidence retained: '+str(root)+'; '+repr(exc),flush=True)
            return 4


def archive(root, completed):
    """Only a verified candidate is exclusively linked to the delivery name.

    Unverified candidates have a .partial.zip suffix and are never called delivery.
    No filesystem paths outside the owned root are traversed. Link exclusions are
    reported explicitly; their external targets are never archive members.
    """
    root=Path(root)
    destination=Path(str(root)+'.zip'); candidate=Path(str(root)+'.partial.zip')
    members=[];omitted=[]
    def traversal_error(error):raise error
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=traversal_error):
        for name in list(dirs):
            path=Path(directory)/name; info=path.lstat()
            if path.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
                omitted.append(path.relative_to(root).as_posix());dirs.remove(name)
        for name in files:
            import stat
            path=Path(directory)/name;info=path.lstat()
            if path.is_symlink() or not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                omitted.append(path.relative_to(root).as_posix());continue
            members.append(path)
    q.write_json(root/'archive-members.json',dict(files=sorted([p.relative_to(root).as_posix() for p in members]+['archive-members.json']),omitted=omitted))
    members.append(root/'archive-members.json')
    with zipfile.ZipFile(candidate,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(members):
            if path.name=='summary.json' and path.parent==root:z.writestr('summary.json',q.json_text(completed))
            else:z.write(path,path.relative_to(root).as_posix())
    with zipfile.ZipFile(candidate) as z:
        expected={p.relative_to(root).as_posix() for p in members}
        if set(z.namelist())!=expected or z.testzip() is not None:raise ValueError('Candidate membership/CRC differs')
    os.link(candidate,destination)  # Exclusive absent-target publication on local NTFS.
    return destination


def run(repo, parent, expected, limits):
    root=reserve(repo,parent)
    raw=dict(automated_status='BLOCKED',F2='NOT RUN',F3='NOT RUN',F4='NOT RUN',
             source_expected=expected,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        repo=Path(repo).resolve()
        if len(expected)!=40 or any(c not in '0123456789abcdefABCDEF' for c in expected):
            raise ValueError('BLOCKED: exact full 40-character expected revision required')
        source=q.checked_source(repo,expected)
        if source['branch']!='feature/chronicle-rewrite':raise RuntimeError('BLOCKED: wrong source branch')
        q.write_json(root/'source.json',source)
        if os.name!='nt' or sys.getwindowsversion().build<22000:
            raise RuntimeError('BLOCKED: native Windows 11 required')
        q.write_json(root/'tool-identities.json',{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__).resolve(),repo/'scripts/qualify_stage4_windows.ps1',repo/'scripts/qualification_pytest.py')})
        runtime=q.runtime_evidence()
        runtime['filesystem']=q.ntfs_evidence(root)
        runtime['windows']=platform.platform()
        runtime['powershell']=os.environ.get('CHRONICLE_QUALIFICATION_POWERSHELL','not supplied')
        runtime['host_observation']=json.loads(os.environ.get('CHRONICLE_QUALIFICATION_HOST','{}'))
        runtime['dependencies']={}
        for name in ('pytest','tkcalendar','tzlocal'):
            try:runtime['dependencies'][name]=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                runtime['dependencies'][name]=None;runtime['errors'].append('Missing installed test dependency: '+name)
        runtime['schema_required']=3
        q.write_json(root/'environment.json',runtime)
        if runtime['errors'] or sys.version_info<(3,11) or sqlite_version()< (3,37,0) or runtime.get('tzdata')!='2026.5':
            raise RuntimeError('BLOCKED: runtime prerequisites incomplete: '+repr(runtime))
        import _tkinter
        tk=_tkinter.create(None,'ChronicleStage4','ChronicleStage4',False,True,True,False,None)
        try:
            tk.call('wm','withdraw','.')
            q.write_json(root/'tk-runtime.json',dict(tcl=tk.call('info','patchlevel'),tk=tk.call('package','require','Tk')))
        finally:tk.call('destroy','.')
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTHONIOENCODING='utf-8',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
        env.pop('PYTEST_ADDOPTS',None);env.pop('PYTEST_PLUGINS',None)
        # No reads of operator launcher settings or Tk profile hooks from HOME.
        personal=root/'isolated-profile';personal.mkdir()
        env.update(HOME=str(personal),USERPROFILE=str(personal),LOCALAPPDATA=str(personal),XDG_DATA_HOME=str(personal))
        manifests=[]
        for name in ('collection','regression'):
            phase=root/name;phase.mkdir()
            args=[sys.executable,'-u','-B',str(Path(__file__).resolve()),'--child',str(phase)]
            if name=='collection':args+=['--collect-only']
            q.write_json(phase/'command.json',dict(executable=sys.executable,arguments=args,cwd=str(repo)))
            child=q.WindowsChild(args,repo,env)
            value=q.monitor(child,phase,limits)
            value['root']=str(phase)
            if name=='collection':
                manifests=collection_result(phase,value)
                q.write_json(phase/'collection-result.json',dict(status='PASS',purpose='Collection only, not test execution',
                    junit='NOT APPLICABLE',inventory=len(manifests),process_exit_code=value['process_exit_code'],cleanup=value['cleanup']))
            else:raw.update(aggregate(manifests,value),F2='EXECUTED')
        # Source must remain the exact reviewed clean checkout across execution.
        q.checked_source(repo,expected)
        q.write_json(root/'deferred-supervised.json',dict(F3='NOT RUN',F4='NOT RUN',runbook='docs/WINDOWS_OPERATOR_QUALIFICATION.md'))
    except BaseException as exc:
        raw.update(automated_status='EVIDENCE_INCOMPLETE' if raw.get('F2')=='EXECUTED' or isinstance(exc,KeyboardInterrupt) else 'BLOCKED',error=repr(exc),notes=getattr(exc,'__notes__',[]))
    raw['ended_utc']=datetime.now(timezone.utc).isoformat()
    q.write_json(root/'execution-result.json',raw)
    return deliver(root,raw)


def sqlite_version():
    import sqlite3
    return sqlite3.sqlite_version_info


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path)
    parser.add_argument('--output-parent',type=Path)
    parser.add_argument('--expected-revision')
    parser.add_argument('--child',type=Path)
    parser.add_argument('--collect-only',action='store_true')
    parser.add_argument('--collection-seconds',type=int,default=180)
    parser.add_argument('--test-seconds',type=int,default=240)
    parser.add_argument('--phase-seconds',type=int,default=7200)
    args=parser.parse_args()
    if args.child:return pytest_child(args.child,args.collect_only)
    if not args.repo or not args.output_parent or not args.expected_revision:
        parser.error('--repo, --output-parent and --expected-revision are required')
    if min(args.collection_seconds,args.test_seconds,args.phase_seconds)<=0:parser.error('Positive bounded limits required')
    return run(args.repo,args.output_parent,args.expected_revision,dict(q.LIMITS,collection=args.collection_seconds,test=args.test_seconds,phase=args.phase_seconds))


if __name__=='__main__':
    raise SystemExit(main())
