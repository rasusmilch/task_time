"""Real schema-2 lifecycle transactions, chronological evidence and recovery."""
from dataclasses import replace
import json

import pytest

from chronicle import backup_restore as br
from chronicle.records import Request, canonical
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore
from chronicle.worker import DatabaseWorker, Message
from conftest import NOW, uid, archive
from test_backup_restore import logical, rich
from test_branch_movement import review
from test_hierarchy_foundation import create, group, verify
from test_interruptions import paused_child
from test_manual_work import dated, M
from test_worker import receive


def request(store, entity, key, operation='archive', version=1, now=NOW):
    return Request.make(uid(), store.dataset_id, operation + '_' + entity, now,
                        **{entity + '_id': key, 'expected_version': version})


@pytest.mark.parametrize('entity', ['task', 'project'])
def test_chronology_selected_only_timestamp_noop_retry_and_conflict(store, service, entity):
    p = group(service); a = create(service, p); b = create(service, p, a)
    key = a if entity == 'task' else p
    original = logical(store.path)
    r = request(store, entity, key)
    first = service.execute(r)
    assert first.status == 'committed' and first.result == {entity + '_id': key, 'version': 2}
    selected = dict(store.connection.execute(f'SELECT * FROM {entity}s WHERE {entity}_id=?', (key,)).fetchone())
    assert selected['is_archived'] == 1 and selected['archived_at_utc_us'] == selected['updated_utc_us'] == NOW
    before = logical(store.path)
    assert service.execute(request(store, entity, key, version=2, now=NOW+M)).status == 'unchanged'
    assert logical(store.path) == before
    un = request(store, entity, key, 'unarchive', 2, NOW+2*M)
    assert service.execute(un).result == {entity + '_id': key, 'version': 3}
    after = logical(store.path)
    assert service.execute(request(store, entity, key, 'unarchive', 3)).status == 'unchanged'
    assert logical(store.path) == after
    assert service.execute(request(store, entity, key, version=3, now=NOW+3*M)).status == 'committed'
    row = store.connection.execute(f'SELECT * FROM {entity}s WHERE {entity}_id=?', (key,)).fetchone()
    assert row['archived_at_utc_us'] == NOW+3*M and row['version'] == 4
    after = logical(store.path)
    assert service.execute(r).result == first.result and service.reconcile_request(r).result == first.result
    assert service.execute(replace(r, action_utc_us=NOW+1)).status == 'rejected'
    assert logical(store.path) == after
    for table in original:
        if table not in (entity+'s', 'committed_requests', 'sqlite_sequence'):
            assert original[table] == after[table]
    verify(store)


@pytest.mark.parametrize('entity', ['task', 'project'])
@pytest.mark.parametrize('bad', ['missing', 'stale', 'bad_uuid', 'extra', 'timestamp', 'bool_version'])
def test_strict_contract_and_stale_refusal_change_nothing(store, service, entity, bad):
    key = group(service) if entity == 'project' else create(service)
    r = request(store, entity, key)
    args = r.args()
    if bad == 'missing': args[entity+'_id'] = uid()
    if bad == 'stale': args['expected_version'] = 2
    if bad == 'bad_uuid': args[entity+'_id'] = 'invalid'
    if bad == 'extra': args['descendants'] = []
    if bad == 'timestamp': args['archived_at_utc_us'] = NOW
    if bad == 'bool_version': args['expected_version'] = True
    before = logical(store.path)
    r = replace(r, arguments=canonical(args))
    assert service.execute(r).status == 'rejected'
    assert logical(store.path) == before
    verify(store)


@pytest.mark.parametrize('selected', ['leaf', 'parent', 'project', 'grandparent'])
def test_running_containing_branch_refuses_without_timer_or_work_changes(store, service, selected):
    p = group(service); a = create(service, p); b = create(service, p, a); c = create(service, p, b)
    assert service.start_timer(c, uid(), expected_task_version=1, request_id=uid(), action_utc_us=NOW).status == 'committed'
    before = logical(store.path)
    r = request(store, 'project' if selected == 'project' else 'task',
                {'project':p, 'parent':b, 'grandparent':a, 'leaf':c}[selected])
    result = service.execute(r)
    assert result.status == 'rejected' and 'running timer' in str(result.error)
    assert logical(store.path) == before
    verify(store)


def test_inheritance_independent_flags_history_recording_and_move_chronology(store, service):
    p = group(service); q = group(service); a = create(service, p)
    entry = dated(service, a, duration='0:20'); b = create(service, p, a); c = create(service, p, b)
    archive(service, 'task', b, NOW+M)
    archive(service, 'project', p, NOW+2*M)
    archive(service, 'task', c, NOW+3*M)  # Explicit archive beneath an archived ancestor is legal.
    assert service.unarchive_project(p, expected_version=2, request_id=uid(), action_utc_us=NOW+4*M).status == 'committed'
    assert service.unarchive_task(c, expected_version=2, request_id=uid(), action_utc_us=NOW+5*M).status == 'committed'
    state = service.read_current_state(cutoff_utc_us=NOW+6*M)
    rows = {t['task_id']:t for t in state['tasks']}
    assert rows[c]['effective_archived'] and not rows[c]['is_archived'] and rows[b]['archived_at_utc_us'] == NOW+M
    for operation, args in [('start_timer',dict(task_id=c,entry_id=uid(),expected_task_version=3)),
                            ('add_date_only_work',dict(task_id=c,entry_id=uid(),work_date='2026-10-19',duration_text='0:01',comment=''))]:
        assert service.execute(Request.make(uid(),store.dataset_id,operation,NOW+6*M,**args)).status == 'rejected'
    assert service.edit_date_only_work(a,entry,'2026-10-19','0:21',expected_revision=1,request_id=uid(),action_utc_us=NOW).status == 'committed'
    assert service.delete_work_entry(a,entry,expected_revision=2,request_id=uid(),action_utc_us=NOW).status == 'committed'
    assert len(service.read_work_entry_revisions(entry)) == 3
    # Archive state at move time must be reconstructed, even though unarchived later.
    assert service.move_task_branch(request_id=uid(),action_utc_us=NOW,**review(store,a,project=q)).status == 'committed'
    assert service.unarchive_task(b,expected_version=3,request_id=uid(),action_utc_us=NOW).status == 'committed'
    verify(store)
    assert not any(t['effective_archived'] for t in service.read_current_state(cutoff_utc_us=NOW)['tasks'])


@pytest.mark.parametrize('stage', ['update','receipt','before_commit','after_commit','lost_ack'])
def test_archive_faults_atomicity_and_exact_reconciliation(store, service, stage):
    a = create(service); r = request(store,'task',a); real = store.connection; before = logical(store.path)
    class Fault:
        def __getattr__(self,n): return getattr(real,n)
        def execute(self,sql,*args):
            hit = (stage=='update' and sql.startswith('UPDATE tasks SET is_archived=')
                   or stage=='receipt' and sql.startswith('INSERT INTO committed_requests')
                   or stage in ('before_commit','after_commit','lost_ack') and sql=='COMMIT')
            if hit:
                if stage in ('after_commit','lost_ack'): real.execute(sql,*args)
                raise OSError('archive boundary fault')
            return real.execute(sql,*args)
    store.connection = Fault()
    if stage == 'lost_ack':
        original = store._probe
        store._probe = lambda: (_ for _ in ()).throw(OSError('independent probe unavailable'))
    result = service.execute(r)
    assert result.status == ('unverified' if stage=='lost_ack' else 'committed' if stage=='after_commit' else 'rolled_back')
    if stage not in ('after_commit','lost_ack'): assert logical(store.path) == before
    if stage == 'lost_ack': store._probe = original
    if result.status == 'unverified': assert service.reconcile_request(r).status == 'committed'
    assert service.execute(r).status == 'committed'
    after = logical(store.path)
    assert service.execute(r).result == {'task_id':a,'version':2} and logical(store.path) == after
    verify(store)


@pytest.mark.parametrize('damage', ['missing','result','timestamp','final','class','extra_fields','ordering'])
def test_corrupt_archive_evidence_refuses_startup_inspection_backup_restore(store,service,tmp_path,damage):
    a = create(service); r = request(store,'task',a); assert service.execute(r).status == 'committed'
    def change(c):
        if damage=='missing': c.execute('DELETE FROM committed_requests WHERE request_id=?',(r.request_id,))
        if damage=='result': c.execute('UPDATE committed_requests SET result_bytes=? WHERE request_id=?',(canonical(dict(task_id=a,version=3)),r.request_id))
        if damage=='timestamp': c.execute('UPDATE tasks SET archived_at_utc_us=? WHERE task_id=?',(NOW+1,a))
        if damage=='final': c.execute('UPDATE tasks SET is_archived=0,archived_at_utc_us=NULL WHERE task_id=?',(a,))
        if damage=='class': c.execute("UPDATE committed_requests SET receipt_class='protected' WHERE request_id=?",(r.request_id,))
        if damage=='ordering':
            content=json.loads(r.content());content['action_utc_us']=NOW+1
            c.execute('UPDATE committed_requests SET action_utc_us=?,request_bytes=? WHERE request_id=?',(NOW+1,canonical(content),r.request_id))
        if damage=='extra_fields':
            content=json.loads(r.content());content['arguments']['archived_at_utc_us']=NOW
            c.execute('UPDATE committed_requests SET request_bytes=? WHERE request_id=?',(canonical(content),r.request_id))
    c = store.connection
    guards = list(c.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger'"))
    c.execute('PRAGMA foreign_keys=OFF')
    c.execute('PRAGMA ignore_check_constraints=ON')
    try:
        for name, _ in guards: c.execute(f'DROP TRIGGER {name}')
        change(c)
    finally:
        for _, ddl in guards: c.execute(ddl)
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA ignore_check_constraints=OFF')
    with pytest.raises(ValueError): verify(store)
    if damage == 'class':
        with pytest.raises(ValueError): store.backup(tmp_path/'invalid-backup.sqlite3')
    else:
        assert not store.backup(tmp_path/'invalid-backup.sqlite3').verified
    assert not (tmp_path/'invalid-backup.sqlite3').exists()
    directory=store.directory;store.close();before=directory.joinpath('chronicle.sqlite3').read_bytes()
    assert not br.inspect_dataset(directory).ordinary_startup_permitted
    with pytest.raises(ValueError): SQLiteStore(directory)
    target=tmp_path/'never-created'
    with pytest.raises(ValueError): br.restore_image(directory/'chronicle.sqlite3',target)
    assert not target.exists() and directory.joinpath('chronicle.sqlite3').read_bytes()==before


def test_rich_lifecycle_worker_backup_restore_fresh_operation(store,service,rich,tmp_path):
    a=rich['task'];before=logical(store.path);current=store.connection.execute('SELECT version FROM tasks WHERE task_id=?',(a,)).fetchone()[0]
    assert service.archive_task(a,expected_version=current,request_id=uid(),action_utc_us=NOW).status=='committed'
    frozen=logical(store.path)
    for table in before:
        if table not in ('tasks','committed_requests','sqlite_sequence'): assert frozen[table]==before[table]
    backup=store.backup(tmp_path/'archive.sqlite3');assert backup.verified and logical(backup.destination)==frozen
    target=tmp_path/'restore';assert br.restore_image(backup.destination,target).verified
    directory=store.directory;store.close()
    worker=DatabaseWorker(target);worker.start()
    try:
        ready=worker.results.get(timeout=10);assert ready.kind=='ready'
        r=Request.make(uid(),ready.value['dataset_id'],'unarchive_task',NOW+M,task_id=a,expected_version=current+1)
        worker.requests.put(Message('mutate',1,r));assert receive(worker,'mutate').status=='committed'
        worker.requests.put(Message('read',2,NOW+M));state=receive(worker,'read')
        assert not next(t for t in state['tasks'] if t['task_id']==a)['effective_archived']
        r=Request.make(uid(),ready.value['dataset_id'],'add_date_only_work',NOW+M,task_id=a,entry_id=uid(),work_date='2026-10-19',duration_text='0:01',comment='after restore')
        worker.requests.put(Message('mutate',3,r));assert receive(worker,'mutate').status=='committed'
    finally: worker.requests.put(Message('shutdown'));worker.join(10);assert not worker.is_alive()
    restored=SQLiteStore(target)
    try: verify(restored)
    finally: restored.close()
    assert logical(directory/'chronicle.sqlite3')==frozen==logical(backup.destination)
    final=logical(target/'chronicle.sqlite3')
    for table in ('timesheet_exports','timesheet_export_tasks','timesheet_export_week_basis','timesheet_export_cells','polr_confirmation_batches','polr_confirmation_cells','polr_confirmed_current'):
        assert final[table]==frozen[table]


CHILD=r'''
import sys,json
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
from chronicle.records import Request
s=SQLiteStore(sys.argv[1]);real=s.connection;phase=sys.argv[3]
class Boundary:
 def __getattr__(self,n):return getattr(real,n)
 def execute(self,sql,*a):
  result=real.execute(sql,*a)
  if phase=='update' and sql.startswith('UPDATE tasks SET is_archived=') or phase=='receipt' and sql.startswith('INSERT INTO committed_requests') or phase=='commit' and sql=='COMMIT':
   print('BARRIER',flush=True);sys.stdin.readline()
  return result
s.connection=Boundary();assert TimerService(s).execute(Request.make(**json.loads(sys.argv[2]))).status=='committed'
'''
@pytest.mark.parametrize('phase',['update','receipt','commit'])
def test_archive_child_process_death_preserves_exact_boundary(store,service,phase):
    a=create(service);r=request(store,'task',a);directory=store.directory;before=logical(store.path);store.close()
    args=dict(request_id=r.request_id,dataset_id=r.dataset_id,operation=r.operation,action_utc_us=r.action_utc_us,**r.args())
    with paused_child(CHILD,directory,json.dumps(args),phase):pass
    reopened=SQLiteStore(directory)
    try:
        if phase!='commit': assert logical(reopened.path)==before
        service=TimerService(reopened);assert service.execute(r).status=='committed'
        after=logical(reopened.path);assert service.execute(r).status=='committed' and logical(reopened.path)==after
        verify(reopened)
    finally:reopened.close()


def test_forged_archive_while_running_refuses_even_when_final_timer_is_stopped(store,service):
    p=group(service);a=create(service,p);entry=uid()
    assert service.start_timer(a,entry,expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    r=Request.make(uid(),store.dataset_id,'rename_project',NOW+M,project_id=p,expected_version=1,name='Renamed')
    assert service.execute(r).status=='committed'
    assert service.stop_timer(entry,expected_version=1,request_id=uid(),action_utc_us=NOW+2*M).status=='committed'
    forged=Request.make(r.request_id,store.dataset_id,'archive_project',NOW+M,project_id=p,expected_version=1)
    from test_hierarchy_foundation import corrupt_with_original_guards
    corrupt_with_original_guards(store.connection,
        'UPDATE committed_requests SET operation=?,request_bytes=? WHERE request_id=?',
        ('archive_project',forged.content(),r.request_id))
    store.connection.execute('UPDATE projects SET name=?,is_archived=1,archived_at_utc_us=? WHERE project_id=?',('Duplicate',NOW+M,p))
    with pytest.raises(ValueError,match='running timer'):verify(store)


def test_move_archive_unarchive_mixed_chronology_validates_historical_context(store,service):
    p=group(service);q=group(service);a=create(service,p);b=create(service,p,a)
    # Parent eligible; independent archived child travels and keeps its own accepted instant.
    archive(service,'task',b,NOW)
    assert service.move_task_branch(request_id=uid(),action_utc_us=NOW,**review(store,a,project=q)).status=='committed'
    archive(service,'project',q,NOW+M)
    assert service.unarchive_task(b,expected_version=3,request_id=uid(),action_utc_us=NOW+2*M).status=='committed'
    assert service.unarchive_project(q,expected_version=2,request_id=uid(),action_utc_us=NOW+3*M).status=='committed'
    assert service.move_task_branch(request_id=uid(),action_utc_us=NOW,**review(store,a,project=p)).status=='committed'
    archive(service,'task',a,NOW+4*M)
    verify(store)


@pytest.mark.parametrize('operation',['create_task','assign_task_to_project'])
def test_forged_administrative_destination_under_historical_archive_refuses(store,service,operation):
    p=group(service)
    if operation=='create_task':
        a=create(service,p)
    else:
        a=create(service)
        assert service.assign_task_to_project(a,p,expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    target=store.connection.execute('SELECT request_id,commit_seq,request_bytes FROM committed_requests WHERE operation=? ORDER BY commit_seq DESC',(operation,)).fetchone()
    archived=archive(service,'project',p)
    archive_row=store.connection.execute("SELECT request_id,commit_seq FROM committed_requests WHERE operation='archive_project'").fetchone()
    assert service.unarchive_project(p,expected_version=2,request_id=uid(),action_utc_us=NOW).status=='committed'
    from test_hierarchy_foundation import corrupt_with_original_guards
    changes=[('UPDATE committed_requests SET commit_seq=100000 WHERE request_id=?',(target['request_id'],)),
             ('UPDATE committed_requests SET commit_seq=? WHERE request_id=?',(target['commit_seq'],archive_row['request_id'])),
             ('UPDATE committed_requests SET commit_seq=? WHERE request_id=?',(archive_row['commit_seq'],target['request_id']))]
    if operation=='create_task':
        content=json.loads(target['request_bytes']);content['arguments']['expected_project_version']=2
        changes.append(('UPDATE committed_requests SET request_bytes=? WHERE request_id=?',(canonical(content),target['request_id'])))
    for sql,args in changes:corrupt_with_original_guards(store.connection,sql,args)
    with pytest.raises(ValueError,match='archived'):verify(store)
