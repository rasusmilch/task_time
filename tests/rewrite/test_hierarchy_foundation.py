"""Fresh-v2 forest, protected evidence and transaction-boundary regression."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3

import pytest

from chronicle import backup_restore as br
from chronicle.records import Request, ADMINISTRATIVE_OPERATIONS, canonical, receipt_class
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore, APPLICATION_ID, SCHEMA_VERSION, DATABASE
from chronicle.worker import DatabaseWorker, Message
from conftest import archive, NOW, uid
from test_backup_restore import logical, rich
from test_interruptions import paused_child
from test_manual_work import dated, timed, M
from test_worker import receive
from test_app import root, connected, pump


def group(service):
    key = uid()
    assert service.create_project(key,'Duplicate',request_id=uid(),action_utc_us=NOW).status=='committed'
    return key


def create(service, project=None, parent=None, **kwargs):
    key = kwargs.pop('task_id',uid())
    result = service.create_task(key,'Duplicate',project,parent_task_id=parent,
        expected_parent_version=1 if parent else None,
        expected_project_version=1 if project else None,
        request_id=uid(),action_utc_us=NOW,**kwargs)
    assert result.status=='committed',result
    return key


def verify(store):
    store._recover_connection()
    SQLiteStore._verify_complete(store.connection)
    assert store._profile_values()=={'journal_mode':'delete','synchronous':3,'foreign_keys':1}


@pytest.mark.parametrize('entity',['projects','tasks'])
@pytest.mark.parametrize('change',[
    'is_archived=1','archived_at_utc_us=0','is_archived=2',
    'is_archived=1,archived_at_utc_us=9223372036854775807'])
def test_fresh_v2_exact_shape_archive_constraints(store,service,entity,change):
    p=group(service);t=create(service,p)
    c=store.connection
    assert SCHEMA_VERSION==2 and c.execute('PRAGMA user_version').fetchone()[0]==2
    assert c.execute('PRAGMA application_id').fetchone()[0]==APPLICATION_ID==0x4348524E
    for table in ('projects','tasks'):
        fields={r[1] for r in c.execute(f'PRAGMA table_info({table})')}
        assert 'is_deleted' not in fields and {'created_request_id','is_archived','archived_at_utc_us'}<=fields
    assert 'parent_task_id' in {r[1] for r in c.execute('PRAGMA table_info(tasks)')}
    assert not any(any(word in r[0] for word in ('tombstone','closure','template','trash'))
                   for r in c.execute("SELECT name FROM sqlite_schema WHERE type='table'"))
    with pytest.raises(sqlite3.IntegrityError): c.execute(f'UPDATE {entity} SET {change}')
    verify(store)


@pytest.mark.parametrize('assigned',[False,True])
def test_three_levels_duplicate_names_parent_identity_and_depth_atomicity(store,service,assigned):
    p=group(service) if assigned else None
    a=create(service,p);before=logical(store.path)
    b=create(service,p,a);c=create(service,p,b)
    state=service.read_current_state(cutoff_utc_us=NOW)
    rows={t['task_id']:t for t in state['tasks']}
    assert [rows[k]['depth'] for k in (a,b,c)]==[1,2,3]
    assert [rows[k]['is_leaf'] for k in (a,b,c)]==[False,False,True]
    assert all(rows[k]['version']==1 and rows[k]['project_id']==p for k in (a,b,c))
    assert next(r for r in logical(store.path)['tasks'] if r[0]==a)==next(r for r in before['tasks'] if r[0]==a)
    before=logical(store.path)
    result=service.create_task(uid(),'Too deep',p,parent_task_id=c,expected_parent_version=1,
        expected_project_version=1 if p else None,request_id=uid(),action_utc_us=NOW)
    assert result.status=='rejected' and 'three' in str(result.error)
    assert logical(store.path)==before
    verify(store)


@pytest.mark.parametrize('bad',['project_version','parent_version','missing_parent','project_mismatch','self','extra_field'])
def test_creation_review_refusal_no_partial_structure(store,service,bad):
    p=group(service);other=group(service);a=create(service,p)
    args=dict(task_id=uid(),name='Child',project_id=p,parent_task_id=a,
              expected_parent_version=1,expected_project_version=1)
    if bad=='project_version':args.update(parent_task_id=None,expected_parent_version=None,expected_project_version=2)
    if bad=='parent_version':args['expected_parent_version']=2
    if bad=='missing_parent':args['parent_task_id']=uid()
    if bad=='project_mismatch':args['project_id']=other
    if bad=='self':args['task_id']=a
    if bad=='extra_field':args['receipt_class']='administrative'
    before=logical(store.path)
    result=service.execute(Request.make(uid(),store.dataset_id,'create_task',NOW,**args))
    assert result.status=='rejected' and logical(store.path)==before
    verify(store)


def test_child_inherits_only_when_project_argument_omitted_and_retries_before_review(store,service):
    p=group(service);a=create(service,p);child=uid();request=uid()
    result=service.create_task(child,'Child',parent_task_id=a,expected_parent_version=1,
        request_id=request,action_utc_us=NOW)
    assert result.status=='committed'
    assert service.rename_task(a,'Renamed',expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    before=logical(store.path)
    assert service.create_task(child,'Child',parent_task_id=a,expected_parent_version=1,
        request_id=request,action_utc_us=NOW).result==result.result
    assert service.create_task(child,'Changed',parent_task_id=a,expected_parent_version=1,
        request_id=request,action_utc_us=NOW).status=='rejected'
    assert service.create_task(uid(),'Explicit NULL mismatch',None,parent_task_id=a,expected_parent_version=2,
        request_id=uid(),action_utc_us=NOW).status=='rejected'
    assert logical(store.path)==before
    verify(store)


def test_parent_history_cumulative_conservation_and_direct_reporting(store,service):
    p=group(service);q=group(service);a=create(service,p)
    interval=timed(service,a);entry=dated(service,a,duration='0:20')
    work_before=logical(store.path)
    b=create(service,p,a);dated(service,b,duration='0:25')
    c=create(service,p,b);dated(service,c,duration='0:35')
    other=create(service,q);dated(service,other,duration='0:10')
    u=create(service);dated(service,u,duration='0:05')
    removed=dated(service,c,duration='0:17')
    assert service.delete_work_entry(c,removed,expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    state=service.read_current_state(cutoff_utc_us=NOW);r=state['report']
    assert [r['individual'][k]['today_us']//M for k in (a,b,c)]==[80,25,35]
    assert [r['cumulative'][k]['today_us']//M for k in (a,b,c)]==[140,60,35]
    assert r['projects'][p]['today_us']==140*M and r['projects'][q]['today_us']==10*M
    assert r['projects'][None]['today_us']==5*M and r['application']['today_us']==155*M
    assert r['application']['week_us']==155*M
    assert work_before['work_revisions']==[row for row in logical(store.path)['work_revisions'] if row[0] in (interval,entry)]
    assert service.read_work_entry_revisions(entry)['revisions'][0]['duration_us']==20*M
    frozen=service.prepare_timesheet_preview(export_id=uid(),cutoff_utc_us=NOW,scope_kind='selected',task_ids=(a,))
    assert [t.task_id for t in frozen.tasks]==[a] and not frozen.tasks[0].is_deleted
    assert sum(v.actual_us for v in frozen.cells)==80*M
    all_tasks=service.prepare_timesheet_preview(export_id=uid(),cutoff_utc_us=NOW)
    assert sum(v.actual_us for v in all_tasks.cells)==155*M
    assert service.register_timesheet_export(frozen,request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.edit_date_only_work(a,entry,'2026-10-19','0:30',expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.delete_work_entry(a,interval,expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.read_registered_timesheet_export(frozen.export_id)==frozen
    report=service.read_current_state(cutoff_utc_us=NOW)['report']
    assert report['individual'][a]['today_us']==30*M and report['cumulative'][a]['today_us']==90*M
    assert report['application']['today_us']==105*M
    verify(store)


@pytest.mark.parametrize('operation',['start_timer','switch_timer','add_timed_work','add_date_only_work'])
def test_new_parent_recording_refuses_without_stopping_active_leaf(store,service,operation):
    a=create(service);b=create(service,parent=a);entry=uid()
    assert service.start_timer(b,entry,expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    args=dict(task_id=a,entry_id=uid(),expected_task_version=1)
    if operation=='switch_timer':args=dict(expected_active_entry_id=entry,expected_active_version=1,next_task_id=a,next_entry_id=uid(),expected_task_version=1)
    if operation=='add_date_only_work':args=dict(task_id=a,entry_id=uid(),work_date='2026-10-19',duration_text='0:10',comment='')
    if operation=='add_timed_work':args=dict(task_id=a,entry_id=uid(),start_date='2026-10-19',start_time='08:00',end_date='2026-10-19',end_time='09:00',start_occurrence=None,end_occurrence=None,comment='')
    before=logical(store.path)
    result=service.execute(Request.make(uid(),store.dataset_id,operation,NOW+M,**args))
    assert result.status=='rejected' and logical(store.path)==before
    assert service.stop_timer(entry,expected_version=1,request_id=uid(),action_utc_us=NOW+M).status=='committed'
    verify(store)


def test_running_leaf_cannot_gain_child_and_switch_between_leaves_is_atomic(store,service):
    a=create(service);b=create(service);entry=uid()
    reviewed=Request.make(uid(),store.dataset_id,'create_task',NOW,task_id=uid(),name='Child',parent_task_id=a,expected_parent_version=1)
    assert service.start_timer(a,entry,expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    before=logical(store.path)
    result=service.execute(reviewed)
    assert result.status=='rejected' and logical(store.path)==before
    result=service.switch_timer(entry,b,uid(),expected_active_version=1,expected_task_version=1,request_id=uid(),action_utc_us=NOW+M)
    assert result.status=='committed'
    state=service.read_current_state(cutoff_utc_us=NOW+2*M)
    assert state['active']['task_id']==b and state['report']['application']['today_us']==2*M
    verify(store)


@pytest.mark.parametrize('where',['task','ancestor','project'])
@pytest.mark.parametrize('operation',['start_timer','switch_timer','add_timed_work','add_date_only_work','child'])
def test_effective_archive_refuses_new_recording_and_child(store,service,where,operation):
    p=group(service);a=create(service,p);b=create(service,p,a);other=create(service);active=uid()
    assert service.start_timer(other,active,expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    value = p if where=='project' else a if where=='ancestor' else b
    archive(service, 'project' if where=='project' else 'task', value)
    before=logical(store.path)
    base=dict(request_id=uid(),action_utc_us=NOW+M)
    if operation=='start_timer':result=service.start_timer(b,uid(),expected_task_version=2 if where=='task' else 1,**base)
    elif operation=='switch_timer':result=service.switch_timer(active,b,uid(),expected_active_version=1,expected_task_version=2 if where=='task' else 1,**base)
    elif operation=='add_timed_work':result=service.add_timed_work(b,uid(),'2026-10-19','08:00','2026-10-19','09:00',**base)
    elif operation=='add_date_only_work':result=service.add_date_only_work(b,uid(),'2026-10-19','0:10',**base)
    else:result=service.create_task(uid(),'Child',p,parent_task_id=b,expected_parent_version=2 if where=='task' else 1,**base)
    assert result.status=='rejected' and logical(store.path)==before
    verify(store)


@pytest.mark.parametrize('change',['cycle','depth','project','self','active_parent','archive_active'])
def test_sql_guards_reject_invalid_local_shapes(store,service,change):
    p=group(service);q=group(service);a=create(service,p);b=create(service,p,a);c=create(service,p,b);other=create(service,q);free=create(service,q)
    if change in ('active_parent','archive_active'):
        assert service.start_timer(other,uid(),expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    sql,args={
        'cycle':('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(c,a)),
        'depth':('UPDATE tasks SET project_id=?,parent_task_id=? WHERE task_id=?',(p,c,other)),
        'project':('UPDATE tasks SET project_id=? WHERE task_id=?',(q,b)),
        'self':('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(a,a)),
        'active_parent':('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(other,free)),
        'archive_active':('UPDATE projects SET is_archived=1,archived_at_utc_us=? WHERE project_id=?',(NOW,q)),
    }[change]
    before=logical(store.path)
    with pytest.raises(sqlite3.IntegrityError):store.connection.execute(sql,args)
    assert logical(store.path)==before
    verify(store)


def test_receipt_classes_immutable_protection_and_missing_version_detection(store,service):
    a=create(service);dated(service,a)
    assert service.rename_task(a,'Renamed',expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    c=store.connection
    for row in c.execute('SELECT * FROM committed_requests'):
        assert row['receipt_class']==receipt_class(row['operation'])
        with pytest.raises(sqlite3.IntegrityError):c.execute('UPDATE committed_requests SET receipt_class=? WHERE request_id=?',('protected',row['request_id']))
    for op in ADMINISTRATIVE_OPERATIONS:assert receipt_class(op)=='administrative'
    for op in ('start_timer','add_date_only_work','stop_timer','set_week_start','confirm_polr_absolute','unknown'):
        assert receipt_class(op)=='protected'
    with pytest.raises(sqlite3.IntegrityError,match='immutable'):
        c.execute("DELETE FROM committed_requests WHERE receipt_class='protected'")
    verify(store)
    c.execute("DELETE FROM committed_requests WHERE operation='rename_task'")
    with pytest.raises(ValueError,match='administrative'):SQLiteStore._verify_complete(c)
    directory=store.directory;store.close()
    before=logical(directory/DATABASE)
    with pytest.raises(ValueError):SQLiteStore(directory)
    assert logical(directory/DATABASE)==before


@pytest.mark.parametrize('operation',['move_task_branch','archive_project','unarchive_project','archive_task','unarchive_task','delete_task','delete_project'])
def test_reserved_operations_have_no_executable_service(store,service,operation):
    before=logical(store.path)
    assert service.execute(Request.make(uid(),store.dataset_id,operation,NOW)).status=='rejected'
    assert logical(store.path)==before


def test_nested_assignment_refuses_until_b2_but_standalone_assignment_survives(store,service):
    p=group(service);a=create(service);b=create(service,parent=a)
    for key in (a,b):
        before=logical(store.path)
        assert service.assign_task_to_project(key,p,expected_version=1,request_id=uid(),action_utc_us=NOW).status=='rejected'
        assert logical(store.path)==before
    standalone=create(service)
    assert service.assign_task_to_project(standalone,p,expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    verify(store)


@pytest.mark.parametrize('changed',['parent','project'])
def test_reviewed_destination_changes_before_child_transaction_rejects(store,service,changed):
    p=group(service);a=create(service,p)
    request=Request.make(uid(),store.dataset_id,'create_task',NOW,task_id=uid(),name='Reviewed',
        project_id=p,parent_task_id=a,expected_parent_version=1,expected_project_version=1)
    rename=service.rename_task if changed=='parent' else service.rename_project
    assert rename(a if changed=='parent' else p,'Changed',expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    before=logical(store.path)
    result=service.execute(request)
    assert result.status=='rejected' and logical(store.path)==before
    verify(store)


@pytest.mark.parametrize('after',[False,True])
def test_child_commit_ack_reconciliation_is_exact_and_retains_parent_work(store,service,after):
    from test_services import FaultConnection
    a=create(service);dated(service,a,duration='0:05')
    request=Request.make(uid(),store.dataset_id,'create_task',NOW,task_id=uid(),name='Child',
        parent_task_id=a,expected_parent_version=1)
    before=logical(store.path);store.connection=FaultConnection(store.connection,after=after)
    result=service.execute(request)
    assert result.status==('committed' if after else 'rolled_back')
    if not after:assert logical(store.path)==before
    saved=service.execute(request);assert saved.status=='committed'
    complete=logical(store.path)
    assert service.reconcile_request(request).result==saved.result
    assert service.execute(request).result==saved.result and logical(store.path)==complete
    assert complete['work_entries']==before['work_entries'] and complete['work_revisions']==before['work_revisions']
    verify(store)


def corrupt_with_original_guards(c,sql,args=()):
    """Negative fixture only: restore exact DDL before semantic verification."""
    guards=list(c.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger'"))
    c.execute('PRAGMA foreign_keys=OFF');c.execute('PRAGMA ignore_check_constraints=ON')
    try:
        for name,_ in guards:c.execute(f'DROP TRIGGER {name}')
        c.execute(sql,args)
    finally:
        for _,ddl in guards:c.execute(ddl)
        c.execute('PRAGMA ignore_check_constraints=OFF');c.execute('PRAGMA foreign_keys=ON')


@pytest.mark.parametrize('damage',[
    'cycle','depth','membership','active_parent','archived_active','missing_rename',
    'result_bool','receipt_class','orphan_receipt','creation_owner','name','version',
])
def test_independent_complete_validation_refuses_damaged_forest_and_admin_closure(store,service,tmp_path,damage):
    p=group(service);q=group(service);a=create(service,p);b=create(service,p,a);c=create(service,p,b)
    running=create(service);free=create(service)
    assert service.rename_task(a,'Renamed',expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    rename=store.connection.execute("SELECT request_id FROM committed_requests WHERE operation='rename_task'").fetchone()[0]
    assert service.start_timer(running,uid(),expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    sql,args={
        'cycle':('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(c,a)),
        'depth':('UPDATE tasks SET project_id=?,parent_task_id=? WHERE task_id=?',(p,c,free)),
        'membership':('UPDATE tasks SET project_id=? WHERE task_id=?',(q,b)),
        'active_parent':('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(running,free)),
        'archived_active':('UPDATE tasks SET is_archived=1,archived_at_utc_us=? WHERE task_id=?',(NOW,running)),
        'missing_rename':('DELETE FROM committed_requests WHERE request_id=?',(rename,)),
        'result_bool':('UPDATE committed_requests SET result_bytes=? WHERE request_id=(SELECT created_request_id FROM tasks WHERE task_id=?)',
                       (canonical(dict(task_id=a,version=True)),a)),
        'receipt_class':("UPDATE committed_requests SET receipt_class='protected' WHERE request_id=?",(rename,)),
        'creation_owner':('UPDATE tasks SET created_request_id=? WHERE task_id=?',(rename,a)),
        'name':("UPDATE tasks SET name='Unreceipted' WHERE task_id=?",(a,)),
        'version':('UPDATE tasks SET version=version+1 WHERE task_id=?',(a,)),
    }.get(damage,(None,None))
    if damage=='orphan_receipt':
        request=Request.make(uid(),store.dataset_id,'create_task',NOW,task_id=uid(),name='Orphan',project_id=None)
        sql='INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)'
        args=(request.request_id,'create_task','administrative',request.content(),canonical(dict(task_id=request.args()['task_id'],version=1)),NOW)
    corrupt_with_original_guards(store.connection,sql,args)
    with pytest.raises(ValueError):SQLiteStore._verify_complete(store.connection)
    directory=store.directory;store.close()
    def snapshot():
        return {f.name:(br.metadata(f.stat()),f.read_bytes()) for f in directory.iterdir()}
    before=snapshot()
    assert br.inspect_dataset(directory).classification==br.Compatibility.UNSAFE_OR_UNAVAILABLE
    with pytest.raises(ValueError):SQLiteStore(directory)
    with pytest.raises(ValueError):br.validate_image(directory/DATABASE)
    with pytest.raises(ValueError):br.restore_image(directory/DATABASE,tmp_path/'must-not-exist')
    worker=DatabaseWorker(directory);worker.start()
    try:
        assert worker.results.get(timeout=10).kind=='startup_failed'
        assert worker.results.get(timeout=10).kind=='stopped'
    finally:worker.join(10);assert not worker.is_alive()
    assert snapshot()==before and not (tmp_path/'must-not-exist').exists()


def test_v2_rich_nested_backup_restore_worker_and_independent_later_work(store,service,rich,tmp_path):
    parent=rich['task'];b=create(service)
    # Use the actual retained parent's current project/version, not frozen label ordering.
    row=store.connection.execute('SELECT * FROM tasks WHERE task_id=?',(parent,)).fetchone()
    child=uid()
    assert service.create_task(child,'Child',row['project_id'],parent_task_id=parent,expected_parent_version=row['version'],
        request_id=uid(),action_utc_us=NOW).status=='committed'
    dated(service,child,duration='0:07');grand=create(service,row['project_id'],child)
    dated(service,grand,duration='0:03')
    archive(service, 'task', child)
    baseline=logical(store.path);backup=store.backup(tmp_path/'hierarchy.sqlite3')
    assert backup.verified and logical(backup.destination)==baseline and logical(store.path)==baseline
    target=tmp_path/'restored';restored=br.restore_image(backup.destination,target)
    assert restored.verified and logical(target/DATABASE)==baseline
    assert br.inspect_dataset(target).classification==br.Compatibility.SUPPORTED_CURRENT
    worker=DatabaseWorker(target);worker.start()
    try:
        ready=worker.results.get(timeout=10);assert ready.kind=='ready'
        worker.requests.put(Message('read',1,NOW));value=receive(worker,'read')
        assert value['active']['entry_id']==rich['active']
        assert next(t for t in value['tasks'] if t['task_id']==grand)['effective_archived']
        request=Request.make(uid(),ready.value['dataset_id'],'add_date_only_work',NOW,task_id=b,entry_id=uid(),work_date='2026-10-19',duration_text='0:01',comment='after restore')
        worker.requests.put(Message('mutate',2,request));assert receive(worker,'mutate').status=='committed'
    finally:
        worker.requests.put(Message('shutdown'));worker.join(10);assert not worker.is_alive()
    final=logical(target/DATABASE)
    for table in ('timesheet_exports','timesheet_export_cells','polr_confirmation_batches','polr_confirmation_cells','polr_confirmed_current'):
        assert final[table]==baseline[table]
    assert logical(store.path)==baseline and logical(backup.destination)==baseline


CHILD = r'''
import json,sys
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
from chronicle.records import Request
store=SQLiteStore(sys.argv[1]);service=TimerService(store)
args=json.loads(sys.argv[2]);phase=sys.argv[3];real=store.connection
class Boundary:
    def __getattr__(self,n):return getattr(real,n)
    def execute(self,sql,*a):
        if (phase=='child' and sql.startswith('INSERT INTO tasks') or phase=='receipt' and sql.startswith('INSERT INTO committed_requests')):
            result=real.execute(sql,*a);print('BARRIER',flush=True);sys.stdin.readline();return result
        result=real.execute(sql,*a)
        if phase=='committed' and sql=='COMMIT':print('BARRIER',flush=True);sys.stdin.readline()
        return result
store.connection=Boundary()
result=service.execute(Request.make(**args))
assert result.status=='committed',result
'''


@pytest.mark.parametrize('phase',['child','receipt','committed'])
def test_child_creation_process_death_atomic_structure_receipt_and_retry(store,service,phase):
    a=create(service);dated(service,a,duration='0:05')
    request=Request.make(uid(),store.dataset_id,'create_task',NOW,task_id=uid(),name='Child',project_id=None,parent_task_id=a,expected_parent_version=1)
    directory=store.directory;before=logical(store.path);store.close()
    args=dict(request_id=request.request_id,dataset_id=request.dataset_id,operation=request.operation,action_utc_us=NOW,**request.args())
    with paused_child(CHILD,directory,json.dumps(args),phase):pass
    reopened=SQLiteStore(directory)
    try:
        service=TimerService(reopened);after=logical(reopened.path)
        if phase!='committed':assert after==before
        else:assert len(after['tasks'])==len(before['tasks'])+1 and len(after['committed_requests'])==len(before['committed_requests'])+1
        result=service.execute(request);assert result.status=='committed'
        installed=logical(reopened.path)
        assert service.execute(request).result==result.result and logical(reopened.path)==installed
        assert service.execute(replace(request,action_utc_us=NOW+1)).status=='rejected'
        assert installed['work_entries']==before['work_entries'] and installed['work_revisions']==before['work_revisions']
        verify(reopened)
    finally:reopened.close()


def test_real_tk_b1_parent_history_root_creation_and_leaf_controls(connected,monkeypatch):
    from test_main_explorer import project,task,submit,select,settled
    app,worker,clock=connected
    p=project(app);a=task(app,group=p)
    submit(app,'add_date_only_work',task_id=a,entry_id=uid(),work_date='2026-10-19',duration_text='0:10',comment='retained parent')
    b=uid();submit(app,'create_task',task_id=b,name='Child fixture',project_id=p,parent_task_id=a,expected_parent_version=1)
    submit(app,'add_date_only_work',task_id=b,entry_id=uid(),work_date='2026-10-19',duration_text='0:20',comment='leaf')
    assert app.tree.item(app.task_row(a),'values')[1:]==('00:10','00:30')
    assert app.tree.item(app.task_row(b),'values')[1:]==('00:20','00:20')
    assert app.tree.parent(app.task_row(b))==app.project_row(p) # B1 is not the nested GUI.
    assert app.tree.item(app.project_row(p),'values')[2]=='00:30'
    select(app,app.task_row(a))
    for label in ('Start','Add timed work','Add date-only work','Assign project'):
        assert app.buttons[label].instate(['disabled'])
    assert not app.buttons['Work History'].instate(['disabled'])
    assert app.open_history();pump(app.root,lambda:app.history.current)
    assert app.history.task['task_id']==a
    assert len(app.history.snapshot['rows'])==1
    app.history.close()
    app.open_mini();assert app.mini.name.cget('text')=='No task selected' and app.mini.toggle.instate(['disabled'])
    select(app,app.task_row(b));assert app.mini.today.cget('text')=='Today: 00:20'
    select(app,app.task_row(a))
    monkeypatch.setattr('chronicle.app.simpledialog.askstring',lambda *a,**kw:'New flat root')
    app.create_task();settled(app)
    created=next(t for t in app.state['tasks'] if t['name']=='New flat root')
    assert created['parent_task_id'] is None and created['project_id']==p
    assert app.tree.item(app.task_row(a),'values')[1:]==('00:10','00:30')
    assert not any(word in label.lower() for label in app.buttons for word in ('delete','template','subtask'))


@pytest.mark.parametrize('start,end,hours',[
    ('2026-03-08T00:00:00-06:00','2026-03-09T00:00:00-05:00',23),
    ('2026-11-01T00:00:00-05:00','2026-11-02T00:00:00-06:00',25),
])
def test_hierarchy_projection_keeps_exact_dst_cutoff_and_zero_direct_parent(store,service,start,end,hours):
    from test_manual_work import stamp,H
    begin,stop=stamp(start),stamp(end);a=create(service);entry=uid()
    assert service.start_timer(a,entry,expected_task_version=1,request_id=uid(),action_utc_us=begin).status=='committed'
    assert service.stop_timer(entry,expected_version=1,request_id=uid(),action_utc_us=stop).status=='committed'
    b=create(service,parent=a);dated(service,b,day=start[:10],duration='14:00')
    c=create(service,parent=b)
    report=service.read_current_state(cutoff_utc_us=stop-1)['report']
    assert report['individual'][a]['today_us']==hours*H-1
    assert report['cumulative'][a]['today_us']==hours*H-1+14*H
    assert report['individual'][c]['today_us']==report['cumulative'][c]['today_us']==0
    assert report['application']['today_us']==report['projects'][None]['today_us']==hours*H-1+14*H
    empty=create(service);leaf=create(service,parent=empty);dated(service,leaf,duration='0:05')
    report=service.read_current_state(cutoff_utc_us=NOW)['report']
    assert report['individual'][empty]['today_us']==0 and report['cumulative'][empty]['today_us']==5*M
    verify(store)
