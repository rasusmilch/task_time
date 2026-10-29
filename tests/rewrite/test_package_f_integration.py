"""Package F connected schema-3 qualification; real worker/SQLite, no native claims.

Expected amounts below are independently specified integers, not another allocator.
Every scenario owns one dataset and follows its evidence through reopen/restore.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import sqlite3

import pytest

from chronicle import backup_restore as br
from chronicle.movement import snapshot
from chronicle.records import Request
from chronicle.records import Outcome
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import to_us
from chronicle.worker import DatabaseWorker, Message
from conftest import uid
from test_backup_restore import logical

M = 60_000_000
H = 60 * M
OBS = to_us(datetime.fromisoformat('2026-10-26T15:00:00+00:00'))
SUNDAY = to_us(datetime.fromisoformat('2026-10-25T18:00:00+00:00'))


class Client:
    """Test-only queue client; it never obtains the worker's SQLite connection."""
    def __init__(self, worker, ready):
        self.worker, self.ready, self.token = worker, ready, 0

    def call(self, kind, value=None):
        self.token += 1
        self.worker.requests.put(Message(kind, self.token, value))
        message = self.worker.results.get(timeout=12)
        assert (message.kind, message.token) == (kind, self.token), message
        return message.value

    def request(self, op, now=OBS, **args):
        return Request.make(uid(), self.ready['dataset_id'], op, now, **args)

    def commit(self, op, now=OBS, **args):
        request = self.request(op, now, **args)
        result = self.call('mutate', request)
        assert result.status == 'committed', result
        return result.result

    def state(self, now=SUNDAY):
        return self.call('read', now)

    def project(self, name):
        key = uid()
        self.commit('create_project', project_id=key, name=name)
        return key

    def task(self, name, project=None, parent=None):
        state = self.state()
        p = next((p for p in state['projects'] if p['project_id'] == project), None)
        t = next((t for t in state['tasks'] if t['task_id'] == parent), None)
        key = uid()
        self.commit('create_task', task_id=key, name=name, project_id=project,
                    parent_task_id=parent, expected_project_version=p['version'] if p else None,
                    expected_parent_version=t['version'] if t else None)
        return key

    def dated(self, task, duration, day='2026-10-19'):
        key = uid()
        self.commit('add_date_only_work', task_id=task, entry_id=key, work_date=day,
                    duration_text=duration, comment='Package F disposable work')
        return key

    def archive(self, key, reverse=False):
        t = next(t for t in self.state()['tasks'] if t['task_id'] == key)
        return self.commit('unarchive_task' if reverse else 'archive_task', task_id=key,
                           expected_version=t['version'])

    def delete_review(self, entity, key):
        return self.call('delete_preview', dict(entity_type=entity, entity_id=key))

    def delete_request(self, entity, key, review):
        return self.request('delete_' + entity, **{entity+'_id': key,
            'expected_version': review['selected']['version'], 'review': review, 'confirmed_text': 'DELETE'})


@contextmanager
def owner(directory, create=False):
    worker = DatabaseWorker(directory, create=create, timezone='America/Chicago' if create else None)
    worker.start()
    try:
        message = worker.results.get(timeout=12)
        assert message.kind == 'ready', message
        yield Client(worker, message.value)
    finally:
        worker.requests.put(Message('shutdown'))
        worker.join(12)
        assert not worker.is_alive(), 'Test-owned worker failed to release ownership'


def blueprint(c, title='Design'):
    a, b, d = uid(), uid(), uid()
    nodes = [dict(node_id=a, parent_node_id=None, name='Root', position=0),
             dict(node_id=b, parent_node_id=a, name='Leaf', position=1),
             dict(node_id=d, parent_node_id=None, name='Leaf', position=2)]
    key = uid()
    c.commit('create_template', template_id=key, name=title, nodes=nodes)
    return next(d for d in c.state()['templates'] if d['template_id'] == key)


def apply(c, definition, project=None, parent=None):
    state = c.state()
    p = next((p for p in state['projects'] if p['project_id'] == project), None)
    t = next((t for t in state['tasks'] if t['task_id'] == parent), None)
    mapping = [dict(node_id=n['node_id'], task_id=uid()) for n in definition['nodes']]
    request = c.request('apply_template', template_id=definition['template_id'],
        expected_template_version=definition['version'], reviewed_definition=definition,
        destination_parent_task_id=parent, destination_project_id=project,
        expected_destination_parent_version=t['version'] if t else None,
        expected_destination_project_version=p['version'] if p else None, node_mapping=mapping)
    result = c.call('mutate', request)
    assert result.status == 'committed', result
    assert [r['task_id'] for r in result.result['created_tasks']] == [r['task_id'] for r in mapping]
    return [r['task_id'] for r in mapping], request


def manual(c, task, quarters, day='2026-10-19'):
    prior = c.call('polr_day', dict(task_id=task, work_date=day, cutoff_utc_us=OBS))
    return c.commit('confirm_polr_absolute', batch_id=uid(), mode='manual', source_export_id=None,
        source_metadata=None, reviewed_rows=[], selected_keys=[], acknowledgements=[],
        manual_cells=[dict(task_id=task, work_date=day, confirmed_quarters=quarters,
                           prior_batch_id=prior['current_batch_id'], prior_quarters=prior['confirmed_quarters'])])


def test_complete_hierarchy_template_record_report_confirm_correct_backup_restore(tmp_path):
    directory = tmp_path/'original Ω'
    report_path, image = tmp_path/'frozen.txt', tmp_path/'verified.sqlite3'
    with owner(directory, True) as c:
        initial = c.state()
        assert initial['tasks'] == initial['projects'] == initial['templates'] == []
        assert initial['active'] is None and c.ready['timezone'] == 'America/Chicago'
        assert {k:c.ready['runtime'][k] for k in ('journal_mode','synchronous','foreign_keys')} == dict(journal_mode='delete',synchronous=3,foreign_keys=1)
        with sqlite3.connect((directory/'chronicle.sqlite3').absolute().as_uri()+'?mode=ro',uri=True) as probe:
            assert probe.execute('PRAGMA application_id').fetchone()[0]==0x4348524E
            assert probe.execute('PRAGMA user_version').fetchone()[0]==3
        assert not logical(directory/'chronicle.sqlite3')['committed_requests']
        c.commit('set_week_start', week_start=0, expected_week_start=6)
        p, q = c.project('Project'), c.project('Project')
        parent = c.task('Same', p)
        c.dated(parent, '0:10')  # Direct work survives later parenthood.
        child = c.task('Same', p, parent)
        leaf = c.task('Same', p, child)
        unassigned = c.task('Same')
        unused = c.task('Unused', q)
        definition = blueprint(c)
        duplicate_id = uid()
        c.commit('duplicate_template', source_template_id=definition['template_id'],
            expected_source_version=1, reviewed_source=definition, template_id=duplicate_id,
            name='Independent', node_mapping=sorted([dict(node_id=n['node_id'], new_node_id=uid())
                for n in definition['nodes']], key=lambda r:r['node_id']))
        duplicate = next(t for t in c.state()['templates'] if t['template_id'] == duplicate_id)
        edited = deepcopy(duplicate['nodes']); edited[0]['name'] = 'Edited independent root'
        c.commit('edit_template', template_id=duplicate_id, expected_version=1, name='Edited', nodes=edited)
        first, apply_one = apply(c, definition, p)
        second, apply_two = apply(c, definition, None, unassigned)
        assert set(first).isdisjoint(second)
        state = c.state(); tasks = {t['task_id']:t for t in state['tasks']}
        assert tasks[unassigned]['version'] == tasks[parent]['version'] == 1
        assert state['active'] is None
        for key in first+second:
            assert state['report']['individual'][key]['week_us'] == 0
        assert len([r for r in logical(directory/'chronicle.sqlite3')['committed_requests']
                    if r[1] in (apply_one.request_id, apply_two.request_id)]) == 2
        a, b, small = first[1], first[2], second[1]
        a_entry = c.dated(a, '3:00'); b_entry = c.dated(b, '3:00')
        c.dated(small, '0:03'); c.dated(small, '0:03', '2026-10-20')
        deleted = c.dated(leaf, '0:09')
        c.commit('delete_work_entry', task_id=leaf, entry_id=deleted, expected_revision=1, comment='retained deletion')
        start = to_us(datetime.fromisoformat('2026-10-21T15:00:00+00:00'))
        active, switched = uid(), uid()
        c.commit('start_timer', start, task_id=leaf, entry_id=active, expected_task_version=1)
        c.commit('switch_timer', start+20*M, expected_active_entry_id=active, expected_active_version=1,
                 next_task_id=second[2], next_entry_id=switched, expected_task_version=1)
        c.commit('stop_timer', start+30*M, entry_id=switched, expected_version=1)
        timed = uid()
        c.commit('add_timed_work', task_id=leaf, entry_id=timed, start_date='2026-10-22', start_time='09:00',
                 end_date='2026-10-22', end_time='09:30', start_occurrence=None, end_occurrence=None, comment='manual interval')
        history = c.call('history', dict(task_id=leaf, cutoff_utc_us=OBS, period='all'))
        assert any(r['entry_id'] == timed for r in history)
        c.commit('edit_closed_timed_work', task_id=leaf, entry_id=timed, expected_revision=1,
                 start_date='2026-10-22', start_time='09:00', end_date='2026-10-22', end_time='09:25',
                 start_occurrence=None, end_occurrence=None, comment='direct History correction')
        revisions = c.call('revisions', deleted)
        assert [r['is_deleted'] for r in revisions['revisions']] == [0, 1]
        state = c.state(); r = state['report']
        assert r['individual'][parent]['week_us'] == 10*M
        assert r['cumulative'][parent]['week_us'] == 55*M
        assert r['application']['week_us'] == (6*60+10+45+10+6)*M
        assert sum(v['week_us'] for v in r['projects'].values()) == r['application']['week_us']
        for key in (parent, child):
            rejected = c.call('mutate', c.request('start_timer', task_id=key, entry_id=uid(), expected_task_version=1))
            assert rejected.status == 'rejected'
        c.archive(first[0]); archived = c.state()
        assert next(t for t in archived['tasks'] if t['task_id']==a)['effective_archived']
        assert c.call('mutate', c.request('add_date_only_work', task_id=a, entry_id=uid(), work_date='2026-10-19', duration_text='0:01', comment='blocked')).status == 'rejected'
        assert archived['report']['application'] == r['application']
        c.archive(first[0], True)
        candidate = c.call('timesheet_preview', dict(export_id=uid(), cutoff_utc_us=SUNDAY,
            period='custom', start_date='2026-10-19', end_date='2026-10-25', scope_kind='all', task_ids=()))
        partial = c.call('timesheet_preview', dict(export_id=uid(), cutoff_utc_us=SUNDAY,
            period='custom', start_date='2026-10-20', end_date='2026-10-20', scope_kind='selected', task_ids=(small,)))
        assert len(partial.basis)==7 and len(partial.cells)==1
        assert partial.cells[0].actual_us==3*M and partial.cells[0].actual_hundredths==5 and partial.cells[0].suggested_quarters==0
        assert [v.suggested_quarters for v in partial.basis[:2]]==[1,0]
        c.commit('register_timesheet_export', candidate=candidate.content())
        publication = c.call('timesheet_publish', dict(export_id=candidate.export_id, destination=str(report_path)))
        assert publication['result'].verified and report_path.read_bytes()==candidate.report_utf8
        proposal = c.call('polr_proposal', candidate.export_id)
        selected = sorted([dict(task_id=a, work_date='2026-10-19'), dict(task_id=small, work_date='2026-10-20')],
                          key=lambda v:(v['task_id'],v['work_date']))
        c.commit('confirm_polr_absolute', batch_id=uid(), mode='source', source_export_id=candidate.export_id,
                 **dict(proposal, selected_keys=selected), manual_cells=[], acknowledgements=[])
        manual(c, b, 12)
        confirmed_before = logical(directory/'chronicle.sqlite3')
        # Same task's opposing daily deltas must not hide behind a matching week sum.
        c.dated(a, '3:00', '2026-10-20'); manual(c, a, 12, '2026-10-20')
        c.commit('edit_date_only_work', task_id=a, entry_id=a_entry, work_date='2026-10-19',
                 duration_text='5:00', expected_revision=1, comment='A: +2 hours')
        tuesday = next(r['entry_id'] for r in c.call('history', dict(task_id=a, cutoff_utc_us=OBS, period='all')) if r.get('work_date')=='2026-10-20')
        c.commit('edit_date_only_work', task_id=a, entry_id=tuesday, work_date='2026-10-20',
                 duration_text='1:00', expected_revision=1, comment='opposing daily difference')
        c.commit('edit_date_only_work', task_id=b, entry_id=b_entry, work_date='2026-10-19',
                 duration_text='2:30', expected_revision=1, comment='B: -0.50 hours')
        reconciliation = c.call('polr_reconciliation', dict(cutoff_utc_us=SUNDAY, period='custom',
            start_date='2026-10-19', end_date='2026-10-25', source_export_id=candidate.export_id))
        cells = {(v['task_id'],v['work_date']):v for v in reconciliation['daily_cells']}
        assert (cells[a,'2026-10-19']['daily_delta_hundredths'], cells[a,'2026-10-19']['suggested_quarters']) == (200,20)
        assert (cells[b,'2026-10-19']['daily_delta_hundredths'], cells[b,'2026-10-19']['suggested_quarters']) == (-50,10)
        assert cells[small,'2026-10-19']['confirmed_quarters'] is None
        assert cells[small,'2026-10-20']['confirmed_quarters'] == 0
        assert not reconciliation['coverage']['complete'] and cells[a,'2026-10-20']['daily_delta_hundredths']==-200
        assert any(v['flags'] for v in reconciliation['source_comparison']['cells'])
        frozen = c.call('timesheet_export', candidate.export_id)
        assert frozen == candidate and report_path.read_bytes()==candidate.report_utf8
        # Move after frozen evidence exists; direct work/evidence cannot be rewritten.
        state = c.state(); source = next(t for t in state['tasks'] if t['task_id']==parent)
        facts_before_move = logical(directory/'chronicle.sqlite3')
        c.commit('move_task_branch', task_id=parent, expected_version=source['version'],
            source_parent_task_id=None, source_project_id=p, destination_parent_task_id=None,
            destination_project_id=q, expected_destination_parent_version=None,
            expected_destination_project_version=1, reviewed_subtree=snapshot(state['tasks'],parent))
        moved = c.state()
        assert moved['report']['individual']==state['report']['individual']
        assert moved['report']['application']==state['report']['application']
        after_move = logical(directory/'chronicle.sqlite3')
        for table in ('work_entries','work_revisions','timesheet_exports','timesheet_export_week_basis','polr_confirmation_cells'):
            assert after_move[table]==facts_before_move[table]
        c.archive(leaf); c.archive(parent); c.archive(parent, True)
        assert next(t for t in c.state()['tasks'] if t['task_id']==leaf)['is_archived']
        reminder = c.call('polr_reminder', OBS)
        assert reminder['reminder_due']
        c.commit('dismiss_polr_reminder_today', local_date='2026-10-26')
        assert not c.call('polr_reminder', OBS)['reminder_due']
        running = uid()
        c.commit('start_timer', task_id=second[2], entry_id=running, expected_task_version=1)
        cutoff = OBS+5*M
        original_state = c.state(cutoff)
        baseline = logical(directory/'chronicle.sqlite3')
        backup = c.call('backup', dict(destination=str(image), request_id=uid()))['result']
        assert backup.verified and logical(image)==baseline
        assert c.state(cutoff)==original_state
        assert all(row in baseline['polr_confirmation_cells'] for row in confirmed_before['polr_confirmation_cells'])
    assert br.validate_image(image).dataset_id == initial['dataset_id']
    source_bytes, image_bytes = (directory/'chronicle.sqlite3').read_bytes(), image.read_bytes()
    restored = tmp_path/'restored Ω'
    assert br.restore_image(image, restored).verified
    assert br.inspect_dataset(restored).ordinary_startup_permitted
    assert logical(restored/'chronicle.sqlite3')==baseline
    with owner(restored) as fresh:
        assert fresh.ready['dataset_id']==initial['dataset_id']
        assert fresh.state(cutoff)==original_state
        assert fresh.call('timesheet_export',candidate.export_id)==candidate
        assert fresh.call('reconcile',apply_one).result['created_tasks']
        assert logical(restored/'chronicle.sqlite3')==baseline  # Retry does not duplicate.
        fresh.commit('stop_timer', cutoff, entry_id=running, expected_version=1)
        fresh.dated(second[2], '0:01')
    assert br.inspect_dataset(restored).ordinary_startup_permitted
    assert (directory/'chronicle.sqlite3').read_bytes()==source_bytes and image.read_bytes()==image_bytes
    assert report_path.read_bytes()==candidate.report_utf8 and logical(directory/'chronicle.sqlite3')==baseline


def test_lifecycle_whole_apply_delete_erased_provenance_restore(tmp_path):
    directory = tmp_path/'lifecycle'
    with owner(directory, True) as c:
        d = blueprint(c, 'Reusable')
        protected_project = c.project('Protected'); protected, old_apply = apply(c,d,protected_project)
        c.dated(protected[1], '0:01')
        review = c.delete_review('project',protected_project)
        assert not review['eligible'] and c.call('mutate',c.delete_request('project',protected_project,review)).status=='rejected'
        unused_project = c.project('Unused'); unused, retired_apply = apply(c,d,unused_project)
        partial = c.delete_review('task',unused[0]); before=logical(directory/'chronicle.sqlite3')
        assert not partial['eligible'] and c.call('mutate',c.delete_request('task',unused[0],partial)).status=='rejected'
        assert logical(directory/'chronicle.sqlite3')==before
        stale = c.delete_review('project',unused_project)
        c.commit('rename_task',task_id=unused[0],expected_version=1,name='Changed after review')
        assert c.call('mutate',c.delete_request('project',unused_project,stale)).status=='rejected'
        review = c.delete_review('project',unused_project)
        before=logical(directory/'chronicle.sqlite3')
        cancelled=c.request('delete_project',project_id=unused_project,expected_version=review['selected']['version'],review=review,confirmed_text='')
        assert c.call('mutate',cancelled).status=='rejected' and logical(directory/'chronicle.sqlite3')==before
        assert c.call('mutate',c.delete_request('project',unused_project,review)).status=='committed'
        # Never resubmit Delete; inspect current presence, not historical outcome.
        presence = c.call('delete_presence',dict(entity_type='project',entity_id=unused_project))
        assert not presence['present'] and presence['historical_outcome']=='unverified'
        retained = logical(directory/'chronicle.sqlite3')
        assert not any(r[1]==retired_apply.request_id for r in retained['committed_requests'])
        assert any(r[1]==old_apply.request_id for r in retained['committed_requests'])
        c.commit('edit_template',template_id=d['template_id'],expected_version=1,name='Relinquished',nodes=d['nodes'])
        survivor = blueprint(c,'Reusable')
        c.commit('duplicate_template',source_template_id=d['template_id'],expected_source_version=2,
            reviewed_source=next(v for v in c.state()['templates'] if v['template_id']==d['template_id']),
            template_id=uid(),name='Snapshot survives',node_mapping=sorted([dict(node_id=n['node_id'],new_node_id=uid()) for n in d['nodes']],key=lambda n:n['node_id']))
        before=logical(directory/'chronicle.sqlite3'); review=c.delete_review('template',d['template_id'])
        assert review['eligible'] and c.call('mutate',c.delete_request('template',d['template_id'],review)).status=='committed'
        after=logical(directory/'chronicle.sqlite3')
        for table in ('tasks','work_entries','work_revisions'):assert after[table]==before[table]
        for r in before['committed_requests']:
            if b'"operation":"apply_template"' in r[4] or b'"operation":"duplicate_template"' in r[4]:assert r in after['committed_requests']
        assert any(v['template_id']==survivor['template_id'] for v in c.state()['templates'])
        image=tmp_path/'lifecycle.sqlite3'; assert c.call('backup',dict(destination=str(image),request_id=uid()))['result'].verified
    assert br.inspect_dataset(directory).ordinary_startup_permitted
    assert br.restore_image(image,tmp_path/'restored').verified
    with owner(tmp_path/'restored') as fresh:
        assert logical(tmp_path/'restored'/'chronicle.sqlite3')==after
        assert fresh.call('reconcile',old_apply).status=='committed'


@pytest.mark.parametrize('start,stop,days', [
    ('2026-10-25T23:30:00-05:00','2026-10-26T00:30:00-05:00',{'2026-10-25':30*M,'2026-10-26':30*M}),
    ('2026-03-08T01:30:00-06:00','2026-03-08T03:30:00-05:00',{'2026-03-08':H}),
    ('2026-11-01T01:30:00-05:00','2026-11-01T01:30:00-06:00',{'2026-11-01':H}),
    ('2026-10-19T09:00:00-05:00','2026-10-19T22:00:00-05:00',{'2026-10-19':13*H}),
])
def test_temporal_restart_without_tick_writes_or_simulated_sleep_claim(tmp_path,start,stop,days):
    begin,end=[to_us(datetime.fromisoformat(v)) for v in (start,stop)]
    directory=tmp_path/'temporal'
    with owner(directory,True) as c:
        c.commit('set_week_start',begin,week_start=0,expected_week_start=6)
        task=c.task('Leaf'); entry=uid()
        c.commit('start_timer',begin,task_id=task,entry_id=entry,expected_task_version=1)
        baseline=logical(directory/'chronicle.sqlite3')
    with owner(directory) as c:
        impossible=c.state(begin-1)
        assert impossible['report'] is None and impossible['calculation_error']
        for observation in (begin,end,begin,end):
            state=c.state(observation)
            assert state['active']['entry_id']==entry and state['active']['start_utc_us']==begin
            assert logical(directory/'chronicle.sqlite3')==baseline
        c.commit('stop_timer',end,entry_id=entry,expected_version=1)
        history=c.call('history',dict(task_id=task,cutoff_utc_us=end,period='all'))
        assert {r['work_date']:r['duration_us'] for r in history}==days
        assert sum(r['duration_us'] for r in history)==end-begin
        local_day=max(days)
        c.commit('dismiss_polr_reminder_today',end,local_date=local_day)
        reminder=c.call('polr_reminder',end)
        assert reminder['local_today']==reminder['dismissed_local_date']==local_day and not reminder['reminder_due']
        next_observation=c.call('polr_reminder',end+24*H)
        assert next_observation['local_today']!=local_day and next_observation['dismissed_local_date']==local_day
        final=logical(directory/'chronicle.sqlite3')
    with owner(directory) as c:
        assert c.state(end)['active'] is None and logical(directory/'chronicle.sqlite3')==final


@pytest.mark.parametrize('monday,tuesday,quarters,adjustment',[
    ('1:08','1:07',(5,4),0), ('1:08','1:08',(5,5),14*M),
    ('1:10','0:20',(5,1),0), ('0:03','0:03',(1,0),9*M),
    ('0:15','0:30',(1,2),0),
])
def test_contract_C_to_G_through_worker_frozen_registration_restore(tmp_path,monday,tuesday,quarters,adjustment):
    with owner(tmp_path/'source',True) as c:
        t=c.task('Contract example')
        c.dated(t,monday);c.dated(t,tuesday,'2026-10-20')
        candidate=c.call('timesheet_preview',dict(export_id=uid(),cutoff_utc_us=SUNDAY,period='custom',
            start_date='2026-10-19',end_date='2026-10-20',scope_kind='selected',task_ids=(t,)))
        assert tuple(v.suggested_quarters for v in candidate.cells)==quarters
        assert len(candidate.basis)==7
        assert sum(quarters)*15*M-sum(v.actual_us for v in candidate.basis)==adjustment
        c.commit('register_timesheet_export',candidate=candidate.content())
        image=tmp_path/'snapshot';assert c.call('backup',dict(destination=str(image),request_id=uid()))['result'].verified
    assert br.restore_image(image,tmp_path/'restored').verified
    with owner(tmp_path/'restored') as c:
        assert c.call('timesheet_export',candidate.export_id)==candidate


@pytest.mark.parametrize('operation',['apply_template','delete_template'])
def test_lost_delivery_retains_different_retry_contracts_after_worker_restart(tmp_path,monkeypatch,operation):
    directory=tmp_path/'uncertain';execute=TimerService.execute;seen=[]
    def lost(self,request):
        outcome=execute(self,request)
        if request.operation==operation and not seen:
            seen.append(request);assert outcome.status=='committed'
            return Outcome('unverified',error=OSError('COMMIT completed; delivery lost'))
        return outcome
    with owner(directory,True) as c:
        d=blueprint(c)
        monkeypatch.setattr(TimerService,'execute',lost)
        if operation=='apply_template':
            args=dict(template_id=d['template_id'],expected_template_version=1,reviewed_definition=d,
                destination_parent_task_id=None,destination_project_id=None,
                expected_destination_parent_version=None,expected_destination_project_version=None,
                node_mapping=[dict(node_id=n['node_id'],task_id=uid()) for n in d['nodes']])
            request=c.request(operation,**args)
        else:request=c.delete_request('template',d['template_id'],c.delete_review('template',d['template_id']))
        assert c.call('mutate',request).status=='unverified'
        committed=logical(directory/'chronicle.sqlite3')
        if operation=='apply_template':
            assert c.call('reconcile',request).status=='committed'
            assert c.call('mutate',replace(request,action_utc_us=OBS+1)).status=='rejected'
        else:
            assert c.call('reconcile',request).status=='unverified'
            assert len(seen)==1
            presence=c.call('delete_presence',dict(entity_type='template',entity_id=d['template_id']))
            assert not presence['present'] and presence['historical_outcome']=='unverified'
            assert c.call('mutate',c.request('create_project',project_id=uid(),name='blocked')).status=='unverified'
        assert logical(directory/'chronicle.sqlite3')==committed
    with owner(directory) as c:
        assert logical(directory/'chronicle.sqlite3')==committed
        c.project('Explicit new session')
    assert br.inspect_dataset(directory).ordinary_startup_permitted
