"""Exact unused-only deletion against real schema-2 constraints and evidence."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from chronicle import backup_restore as br
from chronicle.records import Request, canonical
from chronicle.services import TimerService
from chronicle.sqlite_store import SQLiteStore, DATABASE
from chronicle.worker import DatabaseWorker, Message
from conftest import NOW, uid, archive
from test_hierarchy_foundation import create, group, verify, corrupt_with_original_guards
from test_branch_movement import review as move_review
from test_backup_restore import logical, rich
from test_manual_work import dated, timed, M
from test_polr_confirmation import manual, submit as confirm, source_args
from test_timesheet_candidate import preview as timesheet
from test_interruptions import paused_child
from test_worker import receive


def review(service, entity, key):
    return service.read_delete_preview(entity, key)


def request(store, review, text='DELETE'):
    entity=review['entity_type']
    return Request.make(uid(),store.dataset_id,'delete_'+entity,NOW,
                        **{entity+'_id':review['entity_id'],'expected_version':review['selected']['version'],
                           'review':deepcopy(review),'confirmed_text':text})


@pytest.mark.parametrize('scenario',['project','archived_project','task','archived_task','tree','unassigned','child_working_parent','duplicates'])
def test_unused_complete_scope_no_receipt_and_survivors_exact(store,service,scenario):
    p=group(service);a=create(service,p)
    if scenario in ('project','archived_project','tree'):
        key=p;entity='project'
        if scenario!='tree':key=group(service)
        else:b=create(service,p,a);create(service,p,b)
    else:
        key=a;entity='task'
        if scenario=='unassigned':key=create(service)
        if scenario=='child_working_parent':dated(service,a);key=create(service,p,a)
        if scenario=='duplicates':create(service,p);group(service)
    if scenario.startswith('archived'):archive(service,entity,key)
    r=review(service,entity,key);assert r['eligible'],r['reasons']
    amounts=service.read_current_state(cutoff_utc_us=NOW)['report']
    before=logical(store.path);scope={t['task_id'] for t in r['tasks']};retire={x['request_id'] for x in r['retire_receipts']}
    result=service.execute(request(store,r));assert result.status=='committed',result
    assert result.result==dict(entity_type=entity,entity_id=key,removed_projects=r['project_count'],removed_tasks=len(scope),removed_administrative_receipts=len(retire))
    after=logical(store.path)
    for table,rows in before.items():
        if table=='tasks':expected=[row for row in rows if row[0] not in scope]
        elif table=='projects':expected=[row for row in rows if not(entity=='project' and row[0]==key)]
        elif table=='committed_requests':expected=[row for row in rows if row[1] not in retire]
        else:expected=rows
        assert after[table]==expected
    report=service.read_current_state(cutoff_utc_us=NOW)['report']
    assert report['application']==amounts['application']
    for task_id in report['individual']:
        assert report['individual'][task_id]==amounts['individual'][task_id]
        assert report['cumulative'][task_id]==amounts['cumulative'][task_id]
    for project_id in report['projects']:assert report['projects'][project_id]==amounts['projects'][project_id]
    assert not store.connection.execute("SELECT 1 FROM committed_requests WHERE operation LIKE 'delete_%' AND operation!='delete_work_entry'").fetchone()
    verify(store)
    with pytest.raises(ValueError,match='absent'):review(service,entity,key)
    if scenario=='child_working_parent':
        assert service.start_timer(a,uid(),expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
        verify(store)
    fresh=uid()
    if entity=='task':assert service.create_task(fresh,'Duplicate',request_id=uid(),action_utc_us=NOW).status=='committed'
    else:assert service.create_project(fresh,'Duplicate',request_id=uid(),action_utc_us=NOW).status=='committed'
    assert fresh!=key;verify(store)


@pytest.mark.parametrize('kind',['timed','dated','deleted','active','correction','zero_export','confirmed_zero','prior_confirmation','frozen_project'])
def test_each_protected_boundary_refuses_without_changed_facts(store,service,kind):
    p=group(service);a=create(service,p);entity='task';key=a
    if kind in ('timed','deleted'):entry=timed(service,a)
    if kind=='dated':dated(service,a)
    if kind=='deleted':assert service.delete_work_entry(a,entry,expected_revision=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    if kind in ('active','correction'):
        entry=uid();assert service.start_timer(a,entry,expected_task_version=1,request_id=uid(),action_utc_us=NOW-M).status=='committed'
        if kind=='correction':assert service.correct_active_start(entry,'2026-10-19','09:58',expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    if kind in ('zero_export','frozen_project'):
        candidate=timesheet(service)
        assert service.register_timesheet_export(candidate,request_id=uid(),action_utc_us=NOW).status=='committed'
        if kind=='frozen_project':
            assert service.assign_task_to_project(a,None,expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
            entity='project';key=p
    if kind in ('confirmed_zero','prior_confirmation'):
        assert confirm(service,manual(service,a,0)).status=='committed'
        if kind=='prior_confirmation':assert confirm(service,manual(service,a,4)).status=='committed'
    before=logical(store.path);r=review(service,entity,key)
    assert not r['eligible'] and r['reasons']
    result=service.execute(request(store,r));assert result.status=='rejected'
    assert logical(store.path)==before;verify(store)
    if kind=='deleted':assert any('work_revisions' in reason for reason in r['reasons'])
    if kind=='correction':assert any('active_start_corrections' in reason for reason in r['reasons'])
    if kind=='zero_export':assert any('week_basis' in reason for reason in r['reasons'])
    if kind=='confirmed_zero':assert any('polr_confirmation_cells' in reason for reason in r['reasons'])


def test_one_protected_descendant_blocks_whole_project_but_unused_sibling_can_delete(store,service):
    p=group(service);a=create(service,p);b=create(service,p,a);dated(service,b);unused=create(service,p,a)
    before=logical(store.path);r=review(service,'project',p)
    assert not r['eligible'] and service.execute(request(store,r)).status=='rejected' and logical(store.path)==before
    r=review(service,'task',unused);assert r['eligible'] and service.execute(request(store,r)).status=='committed'
    verify(store)


@pytest.mark.parametrize('scenario',['single_history','internal_move','cross_project','shared_move','surviving_child','surviving_project_context'])
def test_finite_retirement_and_survivor_chronology(store,service,scenario):
    p=group(service);q=group(service);a=create(service,p);b=create(service,p,a)
    if scenario=='single_history':
        assert service.rename_task(b,'Renamed',expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
        archive(service,'task',b)
        assert service.unarchive_task(b,expected_version=3,request_id=uid(),action_utc_us=NOW).status=='committed'
        entity='task';key=b
    elif scenario in ('internal_move','cross_project','shared_move'):
        dest=q if scenario!='internal_move' else p
        if scenario=='internal_move':
            parent=create(service,p)
            assert service.move_task_branch(request_id=uid(),action_utc_us=NOW,**move_review(store,b,parent,p)).status=='committed'
            entity='project';key=p
        else:
            assert service.move_task_branch(request_id=uid(),action_utc_us=NOW,**move_review(store,a,project=dest)).status=='committed'
            entity='task';key=b if scenario=='shared_move' else a
    elif scenario=='surviving_child':
        assert service.move_task_branch(request_id=uid(),action_utc_us=NOW,**move_review(store,b,project=p)).status=='committed'
        entity='task';key=a
    else:
        assert service.move_task_branch(request_id=uid(),action_utc_us=NOW,**move_review(store,a,project=q)).status=='committed'
        entity='project';key=p
    before=logical(store.path);r=review(service,entity,key)
    blocked=scenario in ('shared_move','surviving_child','surviving_project_context')
    assert r['eligible']!=blocked,r['reasons']
    result=service.execute(request(store,r));assert result.status==('rejected' if blocked else 'committed'),result
    if blocked:assert logical(store.path)==before
    verify(store)


@pytest.mark.parametrize('change',['child','work','export','rename','archive','move','receipt'])
def test_full_frozen_review_stale_changes_refuse_entire_delete(store,service,change):
    p=group(service);a=create(service,p);r=review(service,'task',a);frozen=request(store,r)
    if change=='child':create(service,p,a)
    if change=='work':dated(service,a)
    if change=='export':assert service.register_timesheet_export(timesheet(service),request_id=uid(),action_utc_us=NOW).status=='committed'
    if change=='rename':assert service.rename_task(a,'Later',expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    if change=='archive':archive(service,'task',a)
    if change=='move':assert service.move_task_branch(request_id=uid(),action_utc_us=NOW,**move_review(store,a)).status=='committed'
    if change=='receipt':
        archive(service,'task',a)
        assert service.unarchive_task(a,expected_version=2,request_id=uid(),action_utc_us=NOW).status=='committed'
    before=logical(store.path)
    assert service.execute(frozen).status=='rejected' and logical(store.path)==before
    verify(store)


@pytest.mark.parametrize('bad',['wrong_text','text_spaces','wrong_version','extra','altered_review','missing','unassigned','existing_request_id'])
def test_request_identity_and_confirmation_no_write(store,service,bad):
    a=create(service);r=review(service,'task',a);req=request(store,r);args=req.args()
    if bad=='wrong_text':args['confirmed_text']='delete'
    if bad=='text_spaces':args['confirmed_text']=' DELETE '
    if bad=='wrong_version':args['expected_version']=2
    if bad=='extra':args['cleanup']=True
    if bad=='altered_review':args['review']['tasks']=[]
    if bad=='missing':args['task_id']=uid()
    if bad=='unassigned':args['task_id']=None
    if bad=='existing_request_id':req=replace(req,request_id=r['selected']['created_request_id'])
    req=replace(req,arguments=canonical(args));before=logical(store.path)
    assert service.execute(req).status=='rejected' and logical(store.path)==before;verify(store)


@pytest.mark.parametrize('phase',['task','project','receipt','final_validation','survivor_comparison','before_commit','after_commit','close'])
def test_delete_failures_atomic_or_truthfully_uncertain_and_never_retry(store,service,phase,monkeypatch):
    p=group(service);a=create(service,p);b=create(service,p,a);r=request(store,review(service,'project',p));before=logical(store.path)
    real=store.connection;calls=[];close_failure=[phase=='close']
    class Fault:
        def __getattr__(self,n):return getattr(real,n)
        def execute(self,sql,*args):
            calls.append(sql)
            hit=(phase=='task' and sql.startswith('DELETE FROM tasks') or phase=='project' and sql.startswith('DELETE FROM projects')
                 or phase=='receipt' and sql.startswith('DELETE FROM committed_requests')
                 or phase in ('before_commit','after_commit','close') and sql=='COMMIT')
            if hit:
                if phase in ('after_commit','close'):real.execute(sql,*args)
                raise OSError('Delete boundary fault')
            return real.execute(sql,*args)
        def close(self):
            if close_failure[0]:raise OSError('Delete close fault')
            return real.close()
    store.connection=Fault()
    if phase=='final_validation':
        original=store._verify_complete;count=[]
        def validate(c):
            count.append(1)
            if len(count)==2:raise ValueError('final validation fault')
            return original(c)
        monkeypatch.setattr(store,'_verify_complete',validate)
    if phase=='survivor_comparison':
        import chronicle.deletion as d
        original=d.capture;count=[]
        def changed(c):
            value=original(c);count.append(1)
            if len(count)==2:value['dataset_meta'][0]['timezone']='UTC'
            return value
        monkeypatch.setattr(d,'capture',changed)
    result=service.execute(r)
    uncertain=phase in ('before_commit','after_commit','close')
    assert result.status==('unverified' if uncertain else 'rejected' if phase in ('final_validation','survivor_comparison') else 'rolled_back'),result
    committed=phase in ('after_commit','close')
    if not committed:assert logical(store.path)==before
    if phase=='close':
        assert store._retired is not None
        with pytest.raises(OSError,match='close fault'):store.close()
        from chronicle.dataset_lock import DatasetLock
        competing=DatasetLock(store.directory)
        try:
            with pytest.raises(OSError):competing.acquire()
        finally:competing.close()
        # Retry the established close path, then prove ownership can be reacquired.
        close_failure[0]=False;store.close()
        competing.acquire();competing.close()
    before_retry=logical(store.path);assert service.reconcile_request(r).status=='unverified'
    assert logical(store.path)==before_retry
    if phase=='close':
        reopened=SQLiteStore(store.directory)
        try:verify(reopened)
        finally:reopened.close()
    elif phase not in ('final_validation','survivor_comparison'):verify(store)


def test_worker_uncertain_delete_blocks_retries_and_new_mutation_but_allows_presence(store,service,tmp_path,monkeypatch):
    a=create(service);r=request(store,review(service,'task',a));directory=store.directory;store.close()
    original=SQLiteStore.delete_unused
    def lost(self,req):
        real=self.connection
        class Fault:
            def __getattr__(self,n):return getattr(real,n)
            def execute(self,sql,*args):
                value=real.execute(sql,*args)
                if sql=='COMMIT':raise OSError('lost Delete acknowledgement')
                return value
        self.connection=Fault();return original(self,req)
    monkeypatch.setattr(SQLiteStore,'delete_unused',lost)
    w=DatabaseWorker(directory);w.start()
    try:
        assert w.results.get(timeout=10).kind=='ready'
        w.requests.put(Message('mutate',1,r));assert receive(w,'mutate').status=='unverified'
        after=logical(directory/DATABASE)
        for kind,req in [('reconcile',r),('mutate',r),('mutate',Request.make(uid(),r.dataset_id,'create_task',NOW,task_id=uid(),name='Blocked'))]:
            w.requests.put(Message(kind,2,req));assert receive(w,kind).status=='unverified'
        w.requests.put(Message('delete_presence',3,dict(entity_type='task',entity_id=a)))
        presence=receive(w,'delete_presence');assert not presence['present'] and presence['historical_outcome']=='unverified'
        assert logical(directory/DATABASE)==after
    finally:w.requests.put(Message('shutdown'));w.join(10);assert not w.is_alive()


def test_protected_names_are_not_uuid_dependency_keys(store,service):
    a=create(service);other=create(service);dated(service,other,comment=a)
    assert service.rename_task(other,a,expected_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    r=review(service,'task',a);assert r['eligible'] and service.execute(request(store,r)).status=='committed';verify(store)


def test_rich_survivors_backup_restore_reopen_continued_operation(store,service,rich,tmp_path):
    a=create(service);b=create(service,parent=a);archive(service,'task',b)
    before=logical(store.path);r=review(service,'task',a);result=service.execute(request(store,r));assert result.status=='committed',result
    after=logical(store.path)
    for table in before:
        if table not in ('tasks','committed_requests'):assert after[table]==before[table]
    retained=store.connection.execute("SELECT * FROM committed_requests WHERE operation='register_timesheet_export'").fetchone()
    content=json.loads(retained['request_bytes'])
    old=Request.make(retained['request_id'],content['dataset_id'],content['operation'],content['action_utc_us'],**content['arguments'])
    assert service.execute(old).result==json.loads(retained['result_bytes'])
    assert service.reconcile_request(old).result==json.loads(retained['result_bytes'])
    assert logical(store.path)==after
    directory=store.directory;store.close();assert br.inspect_dataset(directory).ordinary_startup_permitted
    reopened=SQLiteStore(directory)
    try:
        verify(reopened);backup=reopened.backup(tmp_path/'after-delete.sqlite3');assert backup.verified
    finally:reopened.close()
    target=tmp_path/'restore';assert br.restore_image(backup.destination,target).verified
    restored=SQLiteStore(target)
    try:
        verify(restored);s=TimerService(restored);new=create(s);dated(s,new);verify(restored)
        final=logical(restored.path)
        for table in ('work_entries','work_revisions','committed_requests'):
            assert all(row in final[table] for row in after[table])
    finally:restored.close()
    assert logical(directory/DATABASE)==after==logical(backup.destination)


CHILD=r'''
import json,sys
from chronicle.records import Request
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
s=SQLiteStore(sys.argv[1]);real=s.connection;phase=sys.argv[3]
class Barrier:
 def __getattr__(self,n):return getattr(real,n)
 def execute(self,sql,*a):
  result=real.execute(sql,*a)
  if phase=='task' and sql.startswith('DELETE FROM tasks') or phase=='receipt' and sql.startswith('DELETE FROM committed_requests') or phase=='commit' and sql=='COMMIT':
   print('BARRIER',flush=True);sys.stdin.readline()
  return result
s.connection=Barrier();assert TimerService(s).execute(Request.make(**json.loads(sys.argv[2]))).status=='committed'
'''
@pytest.mark.parametrize('phase',['task','receipt','commit'])
def test_process_death_delete_all_or_none_without_historical_receipt(store,service,phase):
    a=create(service);create(service,parent=a);r=request(store,review(service,'task',a));before=logical(store.path);directory=store.directory;store.close()
    args=dict(request_id=r.request_id,dataset_id=r.dataset_id,operation=r.operation,action_utc_us=NOW,**r.args())
    with paused_child(CHILD,directory,json.dumps(args),phase):pass
    reopened=SQLiteStore(directory)
    try:
        s=TimerService(reopened);verify(reopened)
        if phase=='commit':
            assert not reopened.connection.execute('SELECT 1 FROM tasks WHERE task_id=?',(a,)).fetchone()
            assert s.execute(r).status=='rejected'
        else:assert logical(reopened.path)==before
        assert s.reconcile_request(r).status=='unverified'
        verify(reopened)
    finally:reopened.close()


@pytest.mark.parametrize('damage',['unknown_operation','wrong_class','missing_creation','extra_fields'])
def test_invalid_or_unclassified_receipts_refuse_delete_without_repair(store,service,damage):
    a=create(service);frozen=request(store,review(service,'task',a));created=store.connection.execute("SELECT * FROM committed_requests WHERE operation='create_task'").fetchone()
    c=store.connection;guards=list(c.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger'"))
    c.execute('PRAGMA foreign_keys=OFF');c.execute('PRAGMA ignore_check_constraints=ON')
    try:
        for name,_ in guards:c.execute(f'DROP TRIGGER {name}')
        if damage=='unknown_operation':
            content=json.loads(created['request_bytes']);content['operation']='unknown_administration'
            c.execute("UPDATE committed_requests SET operation='unknown_administration',receipt_class='protected',request_bytes=?",(canonical(content),))
        if damage=='wrong_class':c.execute("UPDATE committed_requests SET receipt_class='protected'")
        if damage=='missing_creation':c.execute('DELETE FROM committed_requests')
        if damage=='extra_fields':
            content=json.loads(created['request_bytes']);content['arguments']['survivor']=uid()
            c.execute('UPDATE committed_requests SET request_bytes=?',(canonical(content),))
    finally:
        for _,ddl in guards:c.execute(ddl)
        c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA ignore_check_constraints=OFF')
    before=logical(store.path);assert service.execute(frozen).status=='rejected' and logical(store.path)==before


def test_protected_receipts_and_entity_creation_ownership_guards_stay_active(store,service):
    a=create(service);dated(service,a)
    c=store.connection;assert c.execute('PRAGMA foreign_keys').fetchone()[0]==1
    import sqlite3
    protected=c.execute("SELECT request_id FROM committed_requests WHERE receipt_class='protected'").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM committed_requests WHERE request_id=?',(protected,))
    with pytest.raises(sqlite3.IntegrityError):c.execute('UPDATE committed_requests SET action_utc_us=0')
    with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM tasks WHERE task_id=?',(a,))
    verify(store)


def test_malformed_canonical_delete_is_definitely_rejected_before_sql(store,service):
    a=create(service);r=request(store,review(service,'task',a));before=logical(store.path)
    bad=replace(r,arguments=b'{"not canonical": true }')
    assert service.execute(bad).status=='rejected' and logical(store.path)==before


def test_worker_delete_refuses_other_uncertain_request_until_exact_reconciliation(store,service,monkeypatch):
    from chronicle.records import Outcome
    a=create(service);p=group(service);r=request(store,review(service,'task',a));directory=store.directory
    ordinary=Request.make(uid(),store.dataset_id,'rename_project',NOW,project_id=p,name='Later',expected_version=1)
    store.close();original=TimerService.execute
    def lost(self,req):
        outcome=original(self,req)
        if req==ordinary:return Outcome('unverified',error=OSError('ordinary acknowledgement lost'))
        return outcome
    monkeypatch.setattr(TimerService,'execute',lost)
    w=DatabaseWorker(directory);w.start()
    try:
        assert w.results.get(timeout=10).kind=='ready'
        w.requests.put(Message('mutate',1,ordinary));assert receive(w,'mutate').status=='unverified'
        before=logical(directory/DATABASE)
        w.requests.put(Message('mutate',2,r));assert receive(w,'mutate').status=='unavailable' and logical(directory/DATABASE)==before
        w.requests.put(Message('reconcile',3,ordinary));assert receive(w,'reconcile').status=='committed'
        w.requests.put(Message('delete_preview',4,dict(entity_type='task',entity_id=a)));fresh=receive(w,'delete_preview')
        assert fresh['eligible']
        newer=Request.make(uid(),r.dataset_id,'delete_task',NOW,task_id=a,expected_version=1,review=fresh,confirmed_text='DELETE')
        w.requests.put(Message('mutate',5,newer));assert receive(w,'mutate').status=='committed'
    finally:w.requests.put(Message('shutdown'));w.join(10);assert not w.is_alive()
