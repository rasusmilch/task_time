"""Schema-3 templates: real transactions, retained/erased provenance and recovery."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json,sqlite3
import pytest
from chronicle.records import Request,canonical
from chronicle.templates import graph,read
from chronicle.sqlite_store import SQLiteStore,DATABASE,SCHEMA_VERSION
from chronicle.services import TimerService
from chronicle import backup_restore as br
from chronicle.worker import DatabaseWorker,Message
from conftest import uid,NOW
from test_backup_restore import logical,rich
from test_hierarchy_foundation import create,group,verify
from test_interruptions import paused_child
from test_worker import receive


def nodes(depth=2,roots=1):
    out=[]
    for _ in range(roots):
        parent=None
        for _ in range(depth):
            key=uid();out.append(dict(node_id=key,parent_node_id=parent,name='Same',position=len(out)));parent=key
    return out


def make(service,title='Blueprint',depth=2,roots=1):
    key=uid();r=service.create_template(key,title,nodes(depth,roots),request_id=uid(),action_utc_us=NOW)
    assert r.status=='committed',r;return read(service.store.connection)[key]


def apply_args(d,parent=None,project=None,parent_version=None,project_version=None):
    return dict(template_id=d['template_id'],expected_template_version=d['version'],reviewed_definition=deepcopy(d),destination_parent_task_id=parent,destination_project_id=project,expected_destination_parent_version=parent_version,expected_destination_project_version=project_version,node_mapping=[dict(node_id=n['node_id'],task_id=uid()) for n in d['nodes']])


def send(service,op,**args):return service.execute(Request.make(uid(),service.store.dataset_id,op,NOW,**args))


def duplicate(service,d,title='Copy'):
    args=dict(source_template_id=d['template_id'],expected_source_version=d['version'],reviewed_source=deepcopy(d),template_id=uid(),name=title,node_mapping=sorted([dict(node_id=n['node_id'],new_node_id=uid()) for n in d['nodes']],key=lambda r:r['node_id']))
    r=send(service,'duplicate_template',**args);assert r.status=='committed',r;return read(service.store.connection)[args['template_id']]


def delete(service,key,entity='template'):
    review=service.read_delete_preview(entity,key)
    return send(service,'delete_'+entity,**{entity+'_id':key,'expected_version':review['selected']['version'],'review':review,'confirmed_text':'DELETE'})


@pytest.mark.parametrize('depth,roots',[(1,1),(2,3),(3,2)])
def test_schema_graph_apply_exact_retry_and_future_independence(store,service,depth,roots):
    d=make(service,depth=depth,roots=roots);p=group(service);before=logical(store.path)
    args=apply_args(d,project=p,project_version=1);request=Request.make(uid(),store.dataset_id,'apply_template',NOW,**args)
    result=service.execute(request);assert result.status=='committed',result
    assert [r['task_id'] for r in result.result['created_tasks']]==[r['task_id'] for r in args['node_mapping']]
    assert len({r['created_request_id'] for r in store.connection.execute('SELECT * FROM tasks')})==1
    assert all(t['version']==1 for t in service.read_current_state(cutoff_utc_us=NOW)['tasks'])
    assert service.read_current_state(cutoff_utc_us=NOW)['report']['application']==dict(today_us=0,week_us=0)
    after=logical(store.path)
    for table in before:
        if table not in ('tasks','committed_requests','sqlite_sequence'):assert after[table]==before[table],table
    assert service.execute(request).result==result.result and logical(store.path)==after
    assert service.execute(replace(request,action_utc_us=NOW+1)).status=='rejected'
    changed=deepcopy(d['nodes']);changed[0]['name']='Edited'
    assert send(service,'edit_template',template_id=d['template_id'],expected_version=1,name='Renamed',nodes=changed).status=='committed'
    assert all(t['name']=='Same' for t in store.connection.execute('SELECT * FROM tasks'))
    leaf=result.result['created_tasks'][depth-1]['task_id']
    assert service.add_date_only_work(leaf,uid(),'2026-10-19','0:15',request_id=uid(),action_utc_us=NOW).status=='committed'
    verify(store)


@pytest.mark.parametrize('bad',['empty','gap','duplicate','self','missing','depth','not_preorder','extra','untrimmed'])
def test_graph_rejections_preserve_every_fact(store,service,bad):
    n=nodes(3,2)
    if bad=='empty':n=[]
    if bad=='gap':n[1]['position']=9
    if bad=='duplicate':n[1]['node_id']=n[0]['node_id']
    if bad=='self':n[0]['parent_node_id']=n[0]['node_id']
    if bad=='missing':n[0]['parent_node_id']=uid()
    if bad=='depth':n[3]['parent_node_id']=n[2]['node_id']
    if bad=='not_preorder':n[4]['parent_node_id']=n[0]['node_id']
    if bad=='extra':n[0]['depth']=1
    if bad=='untrimmed':n[0]['name']=' x '
    before=logical(store.path);r=send(service,'create_template',template_id=uid(),name='New',nodes=n)
    assert r.status=='rejected',r;assert logical(store.path)==before


@pytest.mark.parametrize('name',[' design ','DESIGN','Design'])
def test_name_collisions_archive_unarchive_edit_noop_and_node_reuse(store,service,name):
    d=make(service,'Design');before=logical(store.path)
    assert send(service,'create_template',template_id=uid(),name=name,nodes=nodes()).status=='rejected'
    assert logical(store.path)==before
    assert send(service,'edit_template',template_id=d['template_id'],expected_version=1,name='Design',nodes=d['nodes']).status=='unchanged'
    assert send(service,'archive_template',template_id=d['template_id'],expected_version=1).status=='committed'
    other=make(service,'Design');assert send(service,'unarchive_template',template_id=d['template_id'],expected_version=2).status=='rejected'
    edited=[dict(d['nodes'][0],name='Root')]
    assert send(service,'edit_template',template_id=d['template_id'],expected_version=2,name='Archived rename',nodes=edited).status=='committed'
    before=logical(store.path)
    assert send(service,'edit_template',template_id=d['template_id'],expected_version=3,name='Archived rename',nodes=d['nodes']).status=='rejected'
    assert logical(store.path)==before
    assert send(service,'unarchive_template',template_id=d['template_id'],expected_version=3).status=='committed';verify(store)


def test_unicode_uniqueness_and_relinquished_erased_name_history(store,service):
    a=make(service,'STRASSE');assert send(service,'create_template',template_id=uid(),name='Straße',nodes=nodes()).status=='rejected'
    assert send(service,'edit_template',template_id=a['template_id'],expected_version=1,name='Released',nodes=a['nodes']).status=='committed'
    b=make(service,'Straße');assert delete(service,a['template_id']).status=='committed'
    verify(store);assert read(store.connection)[b['template_id']]['name_key']=='strasse'
    assert send(service,'create_template',template_id=uid(),name='STRASSE',nodes=nodes()).status=='rejected'


@pytest.mark.parametrize('bad',['archived','depth','running','project_archived','parent_archived','template_version','parent_version','project_version','graph','mapping_missing','mapping_extra','mapping_duplicate'])
def test_apply_refusal_stale_context_no_partial_writes(store,service,bad):
    p=group(service);parent=create(service,p);d=make(service,depth=3 if bad=='depth' else 1);args=apply_args(d,parent,p,1,1)
    if bad=='archived':assert send(service,'archive_template',template_id=d['template_id'],expected_version=1).status=='committed'
    if bad=='running':assert service.start_timer(parent,uid(),expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed'
    if bad in ('project_archived','parent_archived'):
        from conftest import archive
        archive(service,'project' if bad=='project_archived' else 'task',p if bad=='project_archived' else parent)
    if bad=='template_version':args['expected_template_version']=2
    if bad=='parent_version':args['expected_destination_parent_version']=2
    if bad=='project_version':args['expected_destination_project_version']=2
    if bad=='graph':args['reviewed_definition']['nodes'][0]['name']='Forged'
    if bad=='mapping_missing':args['node_mapping']=[]
    if bad=='mapping_extra':args['node_mapping'].append(dict(node_id=uid(),task_id=uid()))
    if bad=='mapping_duplicate':args['node_mapping'][0]['task_id']=parent
    before=logical(store.path);assert send(service,'apply_template',**args).status=='rejected';assert logical(store.path)==before;verify(store)


@pytest.mark.parametrize('applies',[0,1,2])
def test_delete_source_preserves_apply_duplicate_and_all_protected_evidence(store,service,rich,tmp_path,applies):
    d=make(service);copy=duplicate(service,d);created=[]
    for _ in range(applies):
        r=send(service,'apply_template',**apply_args(d));assert r.status=='committed';created+=r.result['created_tasks']
    before=logical(store.path);assert delete(service,d['template_id']).status=='committed';verify(store);after=logical(store.path)
    for table in before:
        if table not in ('template_definitions','template_nodes','committed_requests'):assert before[table]==after[table]
    for row in before['committed_requests']:
        content=json.loads(row[4]);op=content['operation']
        if op in ('apply_template','duplicate_template'):assert row in after['committed_requests']
    assert read(store.connection)[copy['template_id']]==copy
    original=store.directory;store.close();assert br.inspect_dataset(original).ordinary_startup_permitted
    s=SQLiteStore(original)
    try:image=s.backup(tmp_path/'backup.sqlite3');assert image.verified
    finally:s.close()
    assert br.restore_image(image.destination,tmp_path/'restored').verified
    s=SQLiteStore(tmp_path/'restored')
    try:
        verify(s);v=TimerService(s);a=make(v,'After restore');assert send(v,'apply_template',**apply_args(a)).status=='committed'
        verify(s)
    finally:s.close()
    assert logical(original/DATABASE)==after==logical(image.destination)


def test_apply_batch_c2_partial_refusal_full_deletion_and_survivors(store,service):
    d=make(service,depth=1,roots=2);p=group(service)
    r=send(service,'apply_template',**apply_args(d,project=p,project_version=1));a=r.result['created_tasks'][0]['task_id'];before=logical(store.path)
    assert not service.read_delete_preview('task',a)['eligible']
    assert delete(service,a,'task').status=='rejected' and logical(store.path)==before
    assert delete(service,p,'project').status=='committed';verify(store)
    assert read(store.connection)[d['template_id']]==d


@pytest.mark.parametrize('change',['apply','edit','archive','review','confirmation'])
def test_template_delete_stale_review_and_confirmation(store,service,change):
    d=make(service);r=service.read_delete_preview('template',d['template_id']);args=dict(template_id=d['template_id'],expected_version=1,review=r,confirmed_text='DELETE')
    if change=='apply':assert send(service,'apply_template',**apply_args(d)).status=='committed'
    if change=='edit':assert send(service,'edit_template',template_id=d['template_id'],expected_version=1,name='Other',nodes=d['nodes']).status=='committed'
    if change=='archive':assert send(service,'archive_template',template_id=d['template_id'],expected_version=1).status=='committed'
    if change=='review':args['review']['retire_receipts']=[]
    if change=='confirmation':args['confirmed_text']='delete'
    before=logical(store.path);assert send(service,'delete_template',**args).status=='rejected' and logical(store.path)==before


@pytest.mark.parametrize('phase',['insert','receipt','commit','ack','close'])
def test_apply_and_delete_faults_atomicity_uncertainty(store,service,phase,monkeypatch):
    d=make(service);real=store.connection;before=logical(store.path);closed=[False]
    class Fault:
        def __getattr__(self,n):return getattr(real,n)
        def execute(self,sql,*a):
            if phase=='insert' and sql.startswith('INSERT INTO tasks'):raise OSError('partial insert')
            if phase=='receipt' and sql.startswith('INSERT INTO committed_requests'):raise OSError('receipt fault')
            if sql=='COMMIT' and phase in ('commit','ack','close'):
                if phase!='commit':real.execute(sql,*a)
                raise OSError('commit boundary')
            return real.execute(sql,*a)
        def close(self):
            if phase=='close' and not closed[0]:raise OSError('failed close')
            real.close()
    store.connection=Fault()
    request=Request.make(uid(),store.dataset_id,'apply_template',NOW,**apply_args(d));r=service.execute(request)
    if phase in ('insert','receipt','commit'):assert r.status=='rolled_back' and logical(store.path)==before
    else:
        assert r.status=='committed'
        if phase=='close':
            with pytest.raises(OSError):store._recover_connection()
            closed[0]=True
        assert service.execute(request).result==r.result
    closed[0]=True;verify(store)


CHILD='''
import sys,json
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
from chronicle.records import Request
s=SQLiteStore(sys.argv[1]);real=s.connection;phase=sys.argv[3]
class Barrier:
 def __getattr__(self,n):return getattr(real,n)
 def execute(self,sql,*a):
  r=real.execute(sql,*a)
  if phase=='insert' and sql.startswith('INSERT INTO tasks') or phase=='commit' and sql=='COMMIT':
   print('BARRIER',flush=True);sys.stdin.readline()
  return r
s.connection=Barrier();assert TimerService(s).execute(Request.make(**json.loads(sys.argv[2]))).status=='committed'
'''
@pytest.mark.parametrize('phase',['insert','commit'])
def test_apply_process_death_and_exact_reopen(store,service,phase):
    d=make(service);args=apply_args(d);r=Request.make(uid(),store.dataset_id,'apply_template',NOW,**args);directory=store.directory;before=logical(store.path);store.close()
    with paused_child(CHILD,directory,json.dumps(dict(request_id=r.request_id,dataset_id=r.dataset_id,operation=r.operation,action_utc_us=NOW,**args)),phase):pass
    s=SQLiteStore(directory)
    try:
        verify(s)
        if phase=='insert':assert logical(s.path)==before
        v=TimerService(s);assert v.reconcile_request(r).status==('absent' if phase=='insert' else 'committed')
        assert v.execute(r).status=='committed';after=logical(s.path);assert v.execute(r).status=='committed' and logical(s.path)==after
    finally:s.close()


@pytest.mark.parametrize('version',[1,2])
def test_real_old_schema_refuses_preserving_bytes_entries_and_metadata(tmp_path,version):
    directory=tmp_path/'old';directory.mkdir();path=directory/DATABASE
    c=sqlite3.connect(path);c.executescript((Path(__file__).parent/'fixtures'/f'schema{version}.sql').read_text());c.execute(f'PRAGMA application_id={0x4348524E}');c.execute(f'PRAGMA user_version={version}');c.execute("INSERT INTO dataset_meta(singleton,dataset_id,timezone,week_start) VALUES(1,?,'America/Chicago',0)",(uid(),));c.commit();c.close()
    # Identity alone is already incompatible: no schema recreation/initialization is attempted.
    from test_dataset_compatibility import preserved
    before=preserved(directory)
    inspected=br.inspect_dataset(directory);assert inspected.classification==br.Compatibility.OLDER_UNSUPPORTED
    assert preserved(directory)==before
    with pytest.raises(ValueError,match='supported|version'):SQLiteStore(directory)
    assert preserved(directory)==before
    target=tmp_path/'restore'
    with pytest.raises(ValueError,match='supported|version'):br.restore_image(path,target)
    assert not target.exists()
    assert preserved(directory)==before


@pytest.mark.parametrize('damage',['name_key','position','missing_creation','mapping','historical_collision','missing_node','result','archive','orphan'])
def test_corrupt_template_or_retained_history_refuses_independent_validation(store,service,damage):
    a=make(service,'Alpha');b=make(service,'Beta');assert send(service,'edit_template',template_id=a['template_id'],expected_version=1,name='Gamma',nodes=a['nodes']).status=='committed'
    d=read(store.connection)[a['template_id']];assert send(service,'apply_template',**apply_args(d)).status=='committed'
    c=store.connection;guards=list(c.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger'"));c.execute('PRAGMA foreign_keys=OFF')
    try:
        for name,sql in guards:c.execute('DROP TRIGGER '+name)
        if damage=='name_key':c.execute("UPDATE template_definitions SET name_key='wrong' WHERE template_id=?",(a['template_id'],))
        if damage=='position':c.execute('UPDATE template_nodes SET position=position+10 WHERE template_id=?',(a['template_id'],))
        if damage=='missing_creation':c.execute('DELETE FROM committed_requests WHERE request_id=?',(a['created_request_id'],))
        if damage=='missing_node':c.execute('DELETE FROM template_nodes WHERE node_id=?',(a['nodes'][-1]['node_id'],))
        if damage=='archive':c.execute('UPDATE template_definitions SET is_archived=1,archived_at_utc_us=? WHERE template_id=?',(NOW,a['template_id']))
        if damage in ('mapping','result','historical_collision','orphan'):
            op='create_template' if damage in ('historical_collision','orphan') else 'apply_template'
            row=c.execute('SELECT * FROM committed_requests WHERE operation=? ORDER BY commit_seq DESC',(op,)).fetchone();content=json.loads(row['request_bytes']);result=json.loads(row['result_bytes'])
            if damage=='mapping':content['arguments']['node_mapping'][0]['task_id']=uid()
            if damage=='result':result['created_tasks'][0]['version']=2
            if damage=='orphan':content['arguments']['template_id']=uid();result['template_id']=content['arguments']['template_id']
            if damage=='historical_collision':
                content['arguments']['name']='Alpha';c.execute("UPDATE template_definitions SET name='Alpha',name_key='alpha' WHERE template_id=?",(b['template_id'],))
            c.execute('UPDATE committed_requests SET request_bytes=?,result_bytes=? WHERE request_id=?',(canonical(content),canonical(result),row['request_id']))
    finally:
        for _,sql in guards:c.execute(sql)
        c.execute('PRAGMA foreign_keys=ON')
    before=logical(store.path)
    with pytest.raises((ValueError,KeyError)):store._verify_complete(c)
    assert logical(store.path)==before
    # Damaged evidence can also prevent independent absence reconciliation; never claim adoption.
    outcome=send(service,'create_template',template_id=uid(),name='No repair',nodes=nodes())
    assert outcome.status in ('rejected','unverified') and outcome.error is not None
    assert logical(store.path)==before


@pytest.mark.parametrize('operation',['create_template','edit_template'])
def test_partial_node_writes_rollback_complete_definition_and_receipt(store,service,operation):
    d=make(service);before=logical(store.path);real=store.connection
    class Fault:
        count=0
        def __getattr__(self,k):return getattr(real,k)
        def execute(self,sql,*a):
            if sql.startswith('INSERT INTO template_nodes'):
                self.count+=1
                if self.count==2:raise OSError('second node insertion failed')
            return real.execute(sql,*a)
    store.connection=Fault()
    args=dict(template_id=uid() if operation=='create_template' else d['template_id'],name='Changed',nodes=nodes(3))
    if operation=='edit_template':args['expected_version']=1
    assert send(service,operation,**args).status=='rolled_back'
    assert logical(store.path)==before;verify(store)


def test_worker_template_delete_commit_uncertainty_no_retry_and_readonly_presence(store,service):
    d=make(service);r=service.read_delete_preview('template',d['template_id']);request=Request.make(uid(),store.dataset_id,'delete_template',NOW,template_id=d['template_id'],expected_version=1,review=r,confirmed_text='DELETE');directory=store.directory;store.close()
    # Real worker and actual post-COMMIT exception; scope the injection to this disposable worker.
    from unittest.mock import patch
    original=SQLiteStore.delete_unused
    def lost(self,req):
        real=self.connection
        class Fault:
            def __getattr__(self,n):return getattr(real,n)
            def execute(self,sql,*a):
                value=real.execute(sql,*a)
                if sql=='COMMIT':raise OSError('Delete acknowledgement lost')
                return value
        self.connection=Fault();return original(self,req)
    with patch.object(SQLiteStore,'delete_unused',lost):
        worker=DatabaseWorker(directory);worker.start()
        try:
            assert worker.results.get(timeout=10).kind=='ready'
            worker.requests.put(Message('mutate',1,request));assert receive(worker,'mutate').status=='unverified';before=logical(directory/DATABASE)
            for kind in ('mutate','reconcile'):
                worker.requests.put(Message(kind,2,request));assert receive(worker,kind).status=='unverified'
            worker.requests.put(Message('delete_presence',3,dict(entity_type='template',entity_id=d['template_id'])))
            assert receive(worker,'delete_presence')['present'] is False and logical(directory/DATABASE)==before
        finally:worker.requests.put(Message('shutdown'));worker.join(10);assert not worker.is_alive()


@pytest.mark.parametrize('protected',['work','frozen_zero','confirmed_zero'])
def test_apply_created_scope_c2_protected_evidence_remains_intact(store,service,protected):
    from test_timesheet_candidate import preview
    from test_polr_confirmation import manual,submit as confirm
    d=make(service,depth=1);p=group(service);r=send(service,'apply_template',**apply_args(d,project=p,project_version=1));key=r.result['created_tasks'][0]['task_id']
    if protected=='work':assert service.add_date_only_work(key,uid(),'2026-10-19','0:10',request_id=uid(),action_utc_us=NOW).status=='committed'
    if protected=='frozen_zero':assert service.register_timesheet_export(preview(service),request_id=uid(),action_utc_us=NOW).status=='committed'
    if protected=='confirmed_zero':assert confirm(service,manual(service,key,0)).status=='committed'
    before=logical(store.path);assert delete(service,p,'project').status=='rejected' and logical(store.path)==before
    assert delete(service,d['template_id']).status=='committed';verify(store)
    for table in before:
        if table not in ('template_definitions','template_nodes','committed_requests'):assert logical(store.path)[table]==before[table],table


def test_erased_source_apply_duplicate_exact_old_results_and_archived_copy(store,service):
    d=make(service);assert send(service,'archive_template',template_id=d['template_id'],expected_version=1).status=='committed'
    d=read(store.connection)[d['template_id']];copied=duplicate(service,d)
    assert not copied['is_archived'] and copied['created_request_id']!=d['created_request_id']
    assert send(service,'unarchive_template',template_id=d['template_id'],expected_version=2).status=='committed';d=read(store.connection)[d['template_id']]
    r=Request.make(uid(),store.dataset_id,'apply_template',NOW,**apply_args(d));original=service.execute(r);assert original.status=='committed'
    row=store.connection.execute("SELECT * FROM committed_requests WHERE operation='duplicate_template'").fetchone();content=json.loads(row['request_bytes']);dup=Request.make(row['request_id'],store.dataset_id,'duplicate_template',content['action_utc_us'],**content['arguments'])
    assert delete(service,d['template_id']).status=='committed';before=logical(store.path)
    assert service.execute(r).result==original.result
    assert service.execute(dup).result==json.loads(row['result_bytes']) and logical(store.path)==before;verify(store)


@pytest.mark.parametrize('boundary',['nodes','definition','receipt','validation'])
def test_template_delete_specific_failures_restore_all_rows_and_evidence(store,service,boundary,monkeypatch):
    d=make(service);assert send(service,'apply_template',**apply_args(d)).status=='committed'
    preview=service.read_delete_preview('template',d['template_id']);before=logical(store.path);real=store.connection
    class Fault:
        def __getattr__(self,n):return getattr(real,n)
        def execute(self,sql,*args):
            prefix={'nodes':'DELETE FROM template_nodes','definition':'DELETE FROM template_definitions','receipt':'DELETE FROM committed_requests'}.get(boundary)
            if prefix and sql.startswith(prefix):raise OSError('Template Delete statement fault')
            return real.execute(sql,*args)
    store.connection=Fault()
    if boundary=='validation':
        original=store._verify_complete;count=[]
        def fail(c):
            count.append(1)
            if len(count)==2:raise ValueError('Post-Delete verification failed')
            return original(c)
        monkeypatch.setattr(store,'_verify_complete',fail)
    r=send(service,'delete_template',template_id=d['template_id'],expected_version=1,review=preview,confirmed_text='DELETE')
    assert r.status==('rejected' if boundary=='validation' else 'rolled_back') and logical(store.path)==before
    if boundary!='validation':verify(store)


def test_apply_parent_history_version_and_new_leaf_timer(store,service):
    p=group(service);parent=create(service,p)
    assert service.add_date_only_work(parent,uid(),'2026-10-19','0:13',request_id=uid(),action_utc_us=NOW).status=='committed'
    before=service.read_current_state(cutoff_utc_us=NOW)['report'];d=make(service,depth=1,roots=2)
    result=send(service,'apply_template',**apply_args(d,parent,p,1,1));assert result.status=='committed'
    state=service.read_current_state(cutoff_utc_us=NOW);row=next(t for t in state['tasks'] if t['task_id']==parent)
    assert row['version']==1 and not row['is_leaf']
    assert state['report']['application']==before['application'] and state['report']['individual'][parent]==before['individual'][parent]
    assert service.start_timer(parent,uid(),expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='rejected'
    child=result.result['created_tasks'][0]['task_id'];entry=uid()
    assert service.start_timer(child,entry,expected_task_version=1,request_id=uid(),action_utc_us=NOW).status=='committed';verify(store)
    assert service.stop_timer(entry,expected_version=1,request_id=uid(),action_utc_us=NOW+60_000_000).status=='committed';verify(store)
