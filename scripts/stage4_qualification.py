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
import threading
import time
import zipfile
from uuid import uuid4

import qualification_pytest as q


class OwnedEvents:
    """F2-only preowned append/health descriptors, independent of test patches.

    Successful writes are immediately visible to the monitor. Final fsync is
    explicit evidence finalization, not a hardware power-loss guarantee.
    """
    def __init__(self, root, *, write=None, sync=None, close=None):
        self.write = write or os.write
        self.sync = sync or os.fsync
        self.close_fd = close or os.close
        self.dumps = json.dumps
        self.monotonic = time.monotonic
        self.lock = threading.Lock()
        self.errors = []
        self.count = 0
        self.digest = hashlib.sha256()
        self.closed = False
        self.health_fd = self.fd = self.diagnostic_fd = None
        self.diagnostic_write, self.diagnostic_close = os.write, os.close
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | getattr(os, 'O_BINARY', 0)
        try:
            self.diagnostic_fd = os.dup(2)  # Parent-captured stderr, preowned before pytest capture/patches.
            self.fd = os.open(Path(root)/'events.jsonl', flags, 0o600)
            self.health_fd = os.open(Path(root)/'event-health.json', flags, 0o600)
        except BaseException as primary:
            for descriptor, closer in ((self.fd,self.close_fd),(self.diagnostic_fd,self.diagnostic_close)):
                if descriptor is not None:
                    try: closer(descriptor)
                    except BaseException as secondary: primary.add_note('Event reservation close: '+repr(secondary))
            raise

    def _all(self, fd, data):
        view = memoryview(data)
        while view:
            try: size = self.write(fd, view)
            except InterruptedError: continue
            if not isinstance(size, int) or size <= 0 or size > len(view):
                raise OSError('Invalid/zero instrumentation write')
            view = view[size:]

    def emit(self, event, **values):
        with self.lock:
            if self.closed or self.errors:
                raise RuntimeError('Event instrumentation already failed/closed: '+repr(self.errors))
            try:
                data = (self.dumps(dict(event=event, monotonic=self.monotonic(),
                    sequence=self.count+1, **values),ensure_ascii=False,sort_keys=True,
                    separators=(',', ':'),allow_nan=False)+'\n').encode('utf-8')
                self._all(self.fd, data)
                self.digest.update(data)
                self.count += 1
            except BaseException as exc:
                self.errors.append('event write: '+repr(exc))
                raise

    def finish(self, primary=None):
        with self.lock:
            if self.closed: return not self.errors
            self.closed = True
            if primary is not None: self.errors.append('primary: '+repr(primary))
            for operation in ('sync', 'close_fd'):
                try: getattr(self, operation)(self.fd)
                except BaseException as exc: self.errors.append(operation+': '+repr(exc))
            health = dict(status='FAILED' if self.errors or primary else 'FINALIZED',
                records=self.count,sha256=self.digest.hexdigest(),errors=list(self.errors),
                primary=repr(primary) if primary else None,requires_process_session_agreement=True)
            try:
                self._all(self.health_fd,(self.dumps(health,sort_keys=True)+'\n').encode('utf-8'))
                self.sync(self.health_fd)
            except BaseException as exc: self.errors.append('health write/sync: '+repr(exc))
            finally:
                try: self.close_fd(self.health_fd)
                except BaseException as exc: self.errors.append('health close: '+repr(exc))
            # Health-channel failures after its record was written are reported
            # on separately preowned stderr. Parent also requires process/session
            # agreement: this health record alone never proves child success.
            if self.errors:
                try:
                    data=('CHRONICLE_EVENT_HEALTH_FAILURE '+self.dumps(dict(errors=self.errors,
                        primary=repr(primary) if primary else None),sort_keys=True)+'\n').encode('utf-8')
                    view=memoryview(data)
                    while view:
                        try: size=self.diagnostic_write(self.diagnostic_fd,view)
                        except InterruptedError: continue
                        if size<=0: raise OSError('Zero diagnostic write')
                        view=view[size:]
                except BaseException as exc: self.errors.append('diagnostic write: '+repr(exc))
            try: self.diagnostic_close(self.diagnostic_fd)
            except BaseException as exc:
                self.errors.append('diagnostic close: '+repr(exc))
                # Best-effort final report to process stderr. Failure still
                # forces nonzero exit and cannot turn evidence into success.
                try: self.diagnostic_write(2,('CHRONICLE_EVENT_HEALTH_FAILURE '+repr(self.errors)+'\n').encode('utf-8'))
                except BaseException as secondary: self.errors.append('final diagnostic: '+repr(secondary))
            if primary is not None and self.errors:
                primary.add_note('Instrumentation finalization: '+repr(self.errors))
            return not self.errors and primary is None


def event_health(root):
    """Parent independently checks finalization and every exact event byte."""
    root = Path(root)
    try:
        health = json.loads((root/'event-health.json').read_text(encoding='utf-8'))
        data = (root/'events.jsonl').read_bytes()
        events = [json.loads(line) for line in data.splitlines()]
        if (health['status'] != 'FINALIZED' or health['errors'] or health['primary']
                or not data.endswith(b'\n') or health['records'] != len(events)
                or health['sha256'] != hashlib.sha256(data).hexdigest()
                or [e['sequence'] for e in events] != list(range(1,len(events)+1))
                or [e['monotonic'] for e in events] != sorted(e['monotonic'] for e in events)):
            raise ValueError('Event ordering/bytes/finalization differs')
        return dict(health,status='COMPLETE')
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return dict(status='EVIDENCE_INCOMPLETE',diagnostic=repr(exc))


def inventory_difference(expected, actual):
    """Exact observations; order is diagnostic, never an order-only refusal."""
    expected_nodes=[row['nodeid'] for row in expected]
    actual_nodes=[row['nodeid'] for row in actual]
    before,after=Counter(expected_nodes),Counter(actual_nodes)
    expected_sources,actual_sources={},{}
    for rows,sources in ((expected,expected_sources),(actual,actual_sources)):
        for row in rows:sources.setdefault(row['nodeid'],set()).add(row['source_path'])
    changes=[]
    for node in sorted(before.keys() & after.keys()):
        old,new=sorted(expected_sources[node]),sorted(actual_sources[node])
        if old!=new: changes.append(dict(nodeid=node,expected_sources=old,actual_sources=new))
    duplicates=lambda counts:[dict(nodeid=node,count=count) for node,count in sorted(counts.items()) if count>1]
    result=dict(expected_count=len(expected),actual_count=len(actual),expected=expected,actual=actual,
        missing=sorted(before.keys()-after.keys()),additional=sorted(after.keys()-before.keys()),
        duplicate_expected=duplicates(before),duplicate_actual=duplicates(after),changed_sources=changes,
        order_changed=expected_nodes!=actual_nodes,
        order_differences=[dict(index=i,expected=expected_nodes[i] if i<len(expected_nodes) else None,
            actual=actual_nodes[i] if i<len(actual_nodes) else None)
            for i in range(max(len(expected_nodes),len(actual_nodes)))
            if (expected_nodes[i] if i<len(expected_nodes) else None)!=(actual_nodes[i] if i<len(actual_nodes) else None)])
    result['mismatch']=bool(result['missing'] or result['additional'] or changes or
                            result['duplicate_expected'] or result['duplicate_actual'])
    return result


class FullPlugin(q.QualificationPlugin):
    """Keep full original identity, source and fixture evidence in each session."""
    def __init__(self, root, events, inventory=None):
        super().__init__(events, root, 'Stage4Full', enforce_manifest=False)
        self.inventory = inventory

    def callback_allowed(self): return True

    def pytest_collectreport(self, report):
        self.events.emit('collection_report',nodeid=report.nodeid,outcome=report.outcome,
                         diagnostic=str(report.longrepr) if report.failed or report.skipped else None)

    def pytest_collection_modifyitems(self, session, config, items):
        # Partition by actual source before hooks run. There is no basename or
        # name-based authorization. Compare the resulting exact nodes afterward.
        if self.inventory is not None:
            expected=[dict(nodeid=row['nodeid'],source_path=row['source_path']) for row in self.inventory]
            actual=[dict(nodeid=item.nodeid,source_path=str(item.path.resolve())) for item in items]
            difference=inventory_difference(expected,actual)
            if difference['mismatch']:
                primary=ValueError('Partition collection differs from original inventory')
                try: q.write_json(self.root/'inventory-mismatch.json',difference)
                except BaseException as secondary:
                    primary.add_note('Inventory diagnostic write also failed: '+repr(secondary))
                try:
                    summary={key:dict(count=len(difference[key]),entries=difference[key][:50],
                        truncated=len(difference[key])>50) for key in
                        ('missing','additional','duplicate_expected','duplicate_actual','changed_sources','order_differences')}
                    self.events.emit('inventory_mismatch',expected_count=len(expected),actual_count=len(actual),summary=summary)
                    print('INVENTORY_MISMATCH '+json.dumps(summary,ensure_ascii=False),flush=True)
                except BaseException as secondary:
                    primary.add_note('Inventory event/console diagnostic also failed: '+repr(secondary))
                raise primary
        super().pytest_collection_modifyitems(session, config, items)
        for row,item in zip(self.manifest,items):
            import inspect
            row['fixture_sources'] = {name:inspect.getsourcefile(values[-1].func)
                for name,values in item._fixtureinfo.name2fixturedefs.items() if values}
            row.update(category='audited-callback', reason='Full source regression; dialogs obstruct; native operator input is separate')
            self.categories[row['nodeid']]='audited-callback'
        self.manifest_record.write(self.manifest)


def pytest_child(root, collect_only=False, arguments=None, inventory=None):
    import pytest
    root = Path(root)
    events = OwnedEvents(root)
    plugin = FullPlugin(root, events, inventory)
    guard = q.DialogGuard(events, plugin.callback_allowed)
    code = 4
    primary = None
    try:
        pytest.hookimpl(tryfirst=True)(FullPlugin.pytest_collection_modifyitems)
        for name in ('pytest_runtest_setup','pytest_runtest_call','pytest_runtest_teardown'):
            pytest.hookimpl(tryfirst=True)(getattr(q.QualificationPlugin,name))
        guard.install()
        args=['-vv','-rA','-p','no:cacheprovider','-o','addopts=', '--basetemp',str(root/'pytest-temp')]
        args+=['--collect-only'] if collect_only else ['--junitxml',str(root/'junit.xml')]
        args+=arguments if arguments is not None else sorted({row['source_path'] for row in inventory}) if inventory is not None else ['.']
        q.write_json(root/'pytest-arguments.json',args)
        events.emit('pytest_begin',collect_only=collect_only)
        code = int(pytest.main(args,plugins=[plugin]))
    except BaseException as exc:
        primary = exc
        raise
    finally:
        cleanups=[guard.restore]
        if plugin.manifest_record:
            cleanups.append(lambda:plugin.manifest_record.__exit__(*sys.exc_info()))
        for cleanup in cleanups:
            try: cleanup()
            except BaseException as exc:
                if primary is None: primary = exc
                else: primary.add_note('Plugin cleanup: '+repr(exc))
        healthy = events.finish(primary)

    return code if healthy else 4


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
    if event_health(root)['status'] != 'COMPLETE': raise ValueError('Collection instrumentation incomplete')
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


# Reviewed retained JSONL inventory. A new top-level test is not automatically
# legacy: it remains UNCLASSIFIED until its runtime/dependencies are reviewed.
LEGACY_MODULES = frozenset({
    'test_actual_readers.py',
    'test_app_ui.py',
    'test_backups.py',
    'test_dated_durations.py',
    'test_decimal_timesheet_renderer.py',
    'test_export_file_status.py',
    'test_export_materialization.py',
    'test_export_snapshot_registration.py',
    'test_exporter.py',
    'test_history_access.py',
    'test_history_modal_return.py',
    'test_history_session_direction.py',
    'test_history_window.py',
    'test_mixed_accounting.py',
    'test_polr_confirmation_proposals.py',
    'test_polr_confirmation_replay.py',
    'test_polr_confirmation_writer.py',
    'test_polr_reconciliation.py',
    'test_polr_service_workflow.py',
    'test_projects.py',
    'test_reminders.py',
    'test_reset_ui_removal.py',
    'test_selected_export_post_actions.py',
    'test_selected_export_subtask_selection.py',
    'test_settings.py',
    'test_storage.py',
    'test_subtask_templates.py',
    'test_subtasks.py',
    'test_tag_dialogs.py',
    'test_tags_service.py',
    'test_time_utils.py',
    'test_timed_interval_corrections.py',
    'test_timed_interval_editor.py',
    'test_timed_interval_form.py',
    'test_timeline_corrections.py',
    'test_timesheet_access.py',
    'test_timesheet_overwrite.py',
    'test_timesheet_preview.py',
    'test_timesheet_renderer.py',
    'test_timesheet_save.py',
    'test_timesheet_service.py',
    'test_timesheet_window.py',
    'test_window_chrome.py',
    'test_work_entry_inputs.py',
    'test_work_history.py',
    'test_work_history_browser.py',
    'test_work_history_view.py',
})


def partition_inventory(inventory, repo):
    repo = Path(repo).resolve()
    result = {key:[] for key in ('SUPPORTED_RUNTIME','RETAINED_LEGACY','UNCLASSIFIED')}
    seen = set()
    for row in inventory:
        node = row['nodeid']
        if node in seen: raise ValueError('Duplicate original node: '+node)
        seen.add(node)
        try: path = Path(row['source_path']).resolve().relative_to(repo).as_posix()
        except (ValueError,KeyError): path = ''
        if ((path.startswith('tests/rewrite/') and '/' not in path[len('tests/rewrite/'):])
                or path == 'tests/test_root_launcher.py'):
            category = 'SUPPORTED_RUNTIME'
        elif path.startswith('tests/') and path[len('tests/'):] in LEGACY_MODULES:
            category = 'RETAINED_LEGACY'
        else: category = 'UNCLASSIFIED'
        result[category].append(dict(row,partition=category))
    if Counter(row['nodeid'] for rows in result.values() for row in rows) != Counter(seen):
        raise ValueError('Partition union differs from full inventory')
    return result


# Exact reviewed POSIX mechanisms. No matching on arbitrary diagnostic text.
WINDOWS_INAPPLICABLE = {
 'tests/rewrite/test_stage4_qualification.py': {
    'test_full_plugin_real_watchdog_keeps_partial_evidence_and_owned_cleanup',
    'test_real_full_inventory_two_owned_partitions_and_truthful_status',
    'test_source_mismatch_dirty_refusal_and_linux_gate_no_test_execution'},
 'tests/rewrite/test_qualification_collector.py': {
    'test_real_concurrent_streams_abnormal_exit_and_actual_return_code',
    'test_owned_child_descendant_is_terminated_without_touching_unrelated_process',
    'test_real_pytest_success_progress_and_exact_exit_through_monitor',
    'test_native_containment_is_not_silently_substituted_on_linux',
    'test_actual_hung_pytest_boundary_is_observed_and_terminated',
    'test_zero_exit_cannot_claim_success_for_unfinished_selected_nodes',
    'test_real_tk_audited_callback_plugin_runs_only_controlled_dialog_paths'},
 'tests/rewrite/test_operational_lifecycle.py': {
    'test_native_permission_refusal_does_not_damage_dataset',
    'test_native_readonly_database_refuses_mutation_and_releases_lock'},
}
WINDOWS_INAPPLICABLE_NODES = frozenset({
 'tests/rewrite/test_dataset_compatibility.py::test_unsafe_paths_never_open_sqlite_or_change_objects[fifo]',
 'tests/rewrite/test_dataset_compatibility.py::test_unsafe_paths_never_open_sqlite_or_change_objects[unreadable]',
 'tests/rewrite/test_backup_restore.py::test_backup_never_overwrites_objects_or_dataset_aliases[fifo]',
 'tests/rewrite/test_timesheet_files.py::test_unsuitable_objects_never_authorize_overwrite[fifo]',
})


def skip_applicability(row, reports, platform_name):
    node = row['nodeid']
    module, _, function = node.partition('::')
    function = function.split('[',1)[0]
    value = dict(nodeid=node,classification='UNRESOLVED',platform=platform_name,
        raw_reasons=[r.get('diagnostic') for r in reports if r['outcome']=='skipped'],
        rationale='No reviewed applicability rule',replacement_gate=None)
    if not any(r['outcome']=='skipped' for r in reports) or any(r.get('wasxfail') is not None for r in reports):
        return value
    if platform_name == 'win32' and (node in WINDOWS_INAPPLICABLE_NODES
            or function in WINDOWS_INAPPLICABLE.get(module, set())):
        value.update(classification='INAPPLICABLE',rationale='Exact reviewed POSIX/Linux-only fixture or Linux-only precondition test',
            replacement_gate='F2 native NTFS/Job/ACL evidence and F3 Windows operator evidence remain required')
    elif platform_name == 'win32':
        # Reviewed fixture + explicit metadata, never pytest's relocated
        # traceback or reason strings. A root/display skip before click has no
        # metadata and must still block required native desktop qualification.
        source = row.get('fixture_sources',{}).get('click')
        if source and Path(source).resolve() == Path(__file__).resolve().parents[1]/'tests/rewrite/test_app.py':
            definitions = row.get('fixture_definitions',{}).get('click',[])
            if definitions and definitions[-1] == dict(module='test_app',function='click'):
                if any(r['outcome']=='skipped' and r.get('applicability_metadata') ==
                        [['chronicle_skip_rule','linux_xtest_only']] for r in reports):
                    value.update(classification='INAPPLICABLE',rationale='Reviewed test_app.click explicit Linux X11/XTest platform metadata',
                                 replacement_gate='F3 actual Windows pointer/keyboard input NOT RUN')
        if value['classification']=='UNRESOLVED' and any(name in row.get('fixtures',[]) for name in ('root','tk_root','connected')):
            value.update(classification='BLOCKED_REQUIRED',rationale='Applicable Tk/desktop test prerequisite unavailable',replacement_gate='F2 focused native desktop reproduction')
    return value


def aggregate(collection, raw):
    """Raw execution, evidence, native gates and final delivery stay separate."""
    result=dict(automated_status='EVIDENCE_INCOMPLETE',test_execution_status=raw['test_execution_status'],
        pytest_exit_code=raw['pytest_exit_code'],process_exit_code=raw['process_exit_code'],
        evidence=raw['evidence'],cleanup=raw['cleanup'],progress=raw['progress'],
        F3='NOT RUN',F4='NOT RUN',diagnostics=[])
    health = event_health(raw['root'])
    result['instrumentation'] = health
    if health['status'] != 'COMPLETE' or raw['evidence']['status']!='COMPLETE' or not raw['cleanup'].get('verified') or not raw['cleanup'].get('streams_drained'):
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
    skipped = [row for row in manifest if any(e['event']=='node_finish' and e['nodeid']==row['nodeid']
               and e['outcome'] in ('skipped','xfailed','xpassed') for e in events)]
    result['applicability'] = [skip_applicability(row,
        [e for e in events if e['event']=='report' and e['nodeid']==row['nodeid']],sys.platform) for row in skipped]
    if raw['test_execution_status']=='PASS' and selected and not result['not_run'] and not collection_skips:
        result['automated_status']='PASS' if all(r['classification']=='INAPPLICABLE' for r in result['applicability']) else 'EVIDENCE_INCOMPLETE'
        if result['automated_status']!='PASS':result['diagnostics'].append('Required blocked/unresolved skip or expected outcome prevents qualification')
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
            if 'supported_runtime_execution' in raw:
                supported=raw['supported_runtime_execution']
                source_complete=(raw.get('source_verified_before') and raw.get('source_verified_after')
                    and raw.get('qualification_complete') and not raw.get('error'))
                completed['supported_runtime_automated']=supported if supported!='PASS' or source_complete else 'EVIDENCE_INCOMPLETE'
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
            summary.update(raw,status='EVIDENCE_INCOMPLETE',supported_runtime_automated='EVIDENCE_INCOMPLETE',archive_status='FAILED_OR_UNVERIFIED',archive_error=repr(exc))
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


def phase_monitor(child, root, limits, label):
    def display(value, **kwargs):
        if kwargs.get('end') == '':
            # Child tests can themselves run collector fixtures and print their
            # own progress records. Label every mirrored fragment so it cannot
            # impersonate controller progress or be parsed as a JSON envelope.
            # Exact original bytes remain in stdout.log/stderr.log.
            for line in value.splitlines(): print('PYTEST_OUTPUT '+line,flush=True)
            return
        if value.startswith('CHRONICLE_PROGRESS '):
            progress=json.loads(value[len('CHRONICLE_PROGRESS '):])
            progress['qualification_phase']=label
            value='CHRONICLE_PROGRESS '+json.dumps(progress,ensure_ascii=False)
        print(value,**kwargs,flush=True)
    return q.monitor(child,root,limits,display=display)


def execute_sessions(repo, root, env, limits, raw):
    """One original collection and two independently owned execution sessions."""
    phase=root/'collection';phase.mkdir()
    args=[sys.executable,'-u','-B',str(Path(__file__).resolve()),'--child',str(phase),'--collect-only']
    q.write_json(phase/'command.json',dict(executable=sys.executable,arguments=args,cwd=str(repo)))
    print('Qualification phase: collection',flush=True)
    collection=phase_monitor(q.WindowsChild(args,repo,env),phase,limits,'collection')
    collection['root']=str(phase)
    manifests=collection_result(phase,collection)
    q.write_json(phase/'collection-result.json',dict(status='PASS',purpose='Collection only, not test execution',
        junit='NOT APPLICABLE',inventory=len(manifests),process_exit_code=collection['process_exit_code'],cleanup=collection['cleanup']))
    collection_events,_=q.read_events(phase/'events.jsonl',0)
    raw['collection_skips']=[event for event in collection_events if event['event']=='collection_report' and event['outcome']=='skipped']
    partitions=partition_inventory(manifests,repo)
    q.write_json(root/'partitions.json',partitions)
    raw['partitions']={}
    for category,name in (('SUPPORTED_RUNTIME','supported-runtime'),('RETAINED_LEGACY','retained-legacy')):
        phase=root/name;phase.mkdir()
        inventory=partitions[category]
        q.write_json(phase/'selected-inventory.json',inventory)
        args=[sys.executable,'-u','-B',str(Path(__file__).resolve()),'--child',str(phase),
            '--inventory',str(phase/'selected-inventory.json')]
        q.write_json(phase/'command.json',dict(executable=sys.executable,arguments=args,cwd=str(repo)))
        if not inventory:
            raw['partitions'][category]=dict(automated_status='EVIDENCE_INCOMPLETE',diagnostics=['Empty partition'])
            continue
        raw['partitions'][category]=dict(automated_status='EVIDENCE_INCOMPLETE',execution='LAUNCHING')
        print('Qualification phase: '+category,flush=True)
        child=q.WindowsChild(args,repo,env)
        # A failed launch is NOT RUN. After launch, instrumentation uncertainty
        # must not be mistaken for an untouched prerequisite refusal.
        raw['execution_attempted']=True
        raw['F2']='STARTED_UNVERIFIED'
        value=phase_monitor(child,phase,limits,category)
        execution_events,_=q.read_events(phase/'events.jsonl',0)
        value['pytest_started']=any(e['event']=='pytest_begin' for e in execution_events)
        raw['pytest_started']=raw.get('pytest_started',False) or value['pytest_started']
        raw['F2']='EXECUTED' if raw['pytest_started'] else 'NOT RUN'
        value['root']=str(phase)
        result=aggregate(inventory,value)
        q.write_json(phase/'qualification-result.json',result)
        raw['partitions'][category]=result
    supported=raw['partitions']['SUPPORTED_RUNTIME']['automated_status']
    if (partitions['UNCLASSIFIED'] or raw['collection_skips']) and supported!='FAIL': supported='EVIDENCE_INCOMPLETE'
    raw['supported_runtime_execution']=supported
    legacy=raw['partitions']['RETAINED_LEGACY']['automated_status']
    raw['retained_legacy']=legacy
    raw['automated_status']='FAIL' if 'FAIL' in (supported,legacy) else 'PASS' if supported==legacy=='PASS' else 'EVIDENCE_INCOMPLETE'


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
        raw['source_verified_before']=True
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
        execute_sessions(repo,root,env,limits,raw)
        # Source must remain the exact reviewed clean checkout across execution.
        q.checked_source(repo,expected)
        raw['source_verified_after']=True
        q.write_json(root/'deferred-supervised.json',dict(F3='NOT RUN',F4='NOT RUN',runbook='docs/WINDOWS_OPERATOR_QUALIFICATION.md'))
        raw['qualification_complete']=True
    except BaseException as exc:
        raw.update(automated_status='EVIDENCE_INCOMPLETE' if raw.get('execution_attempted') or isinstance(exc,KeyboardInterrupt) else 'BLOCKED',error=repr(exc),notes=getattr(exc,'__notes__',[]))
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
    parser.add_argument('--inventory',type=Path)
    parser.add_argument('--collection-seconds',type=int,default=180)
    parser.add_argument('--test-seconds',type=int,default=240)
    parser.add_argument('--phase-seconds',type=int,default=7200)
    args=parser.parse_args()
    if args.child:return pytest_child(args.child,args.collect_only,inventory=json.loads(args.inventory.read_text(encoding='utf-8')) if args.inventory else None)
    if not args.repo or not args.output_parent or not args.expected_revision:
        parser.error('--repo, --output-parent and --expected-revision are required')
    if min(args.collection_seconds,args.test_seconds,args.phase_seconds)<=0:parser.error('Positive bounded limits required')
    return run(args.repo,args.output_parent,args.expected_revision,dict(q.LIMITS,collection=args.collection_seconds,test=args.test_seconds,phase=args.phase_seconds))


if __name__=='__main__':
    raise SystemExit(main())
