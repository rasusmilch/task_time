"""Real production transaction faults and killed-child recovery, not power loss."""
import sqlite3
import pytest
from chronicle.sqlite_store import SQLiteStore
from chronicle.schema4_runtime_service import Schema4RuntimeService
from chronicle.records import Request
from chronicle import project_ui as ui
from chronicle.movement import snapshot
from runtime4_cases import Runtime,runtime,uid,NOW
from test_interruptions import TRANSACTION_CHILD,paused_child,frozen_json
from test_backup_restore import logical
from test_templates import nodes

FAMILIES=('project','task','project move','task move','work','lifecycle','template','configuration')


def prepare(h,family):
    p=h.project();q=h.project();key=h.task(p)
    if family=='project':op,args='create_child_project',dict(project_id=uid(),name='Child',parent_project_id=p,expected_parent_version=1,reviewed_parent_ancestry=ui.ancestry(h.state(),p))
    elif family=='task':op,args='create_task',dict(task_id=uid(),name='New',**ui.new_task_review(h.state(),None,p))
    elif family=='project move':op,args='move_project_subtree',ui.ProjectMoveReview(h.state(),p).arguments(q)
    elif family=='task move':op='move_task_branch';args,_=ui.task_move_arguments(h.state(),key,None,q,snapshot(h.state()['tasks'],key))
    elif family=='work':op,args='add_date_only_work',dict(task_id=key,entry_id=uid(),work_date='2026-10-19',duration_text='0:15',comment='Protected')
    elif family=='lifecycle':op,args='archive_project',dict(project_id=p,expected_version=1)
    elif family=='template':op,args='create_template',dict(template_id=uid(),name='Blueprint',nodes=nodes(2))
    else:op,args='set_week_start',dict(week_start=0,expected_week_start=6)
    return Request.make(uid(),h.store.dataset_id,op,h.now+1000000,**args)


@pytest.mark.parametrize('family',FAMILIES)
@pytest.mark.parametrize('phase',['before','begin','facts','receipt','commit_ready','committed'])
def test_process_death_exact_atomic_result_and_reconciliation(runtime,family,phase):
    h=runtime;r=prepare(h,family);before=h.facts();directory=h.store.directory;h.store.close()
    code=TRANSACTION_CHILD.replace('from chronicle.services import TimerService','from chronicle.schema4_runtime_service import Schema4RuntimeService as TimerService').replace('SQLiteStore(path, schema_version=3)','SQLiteStore(path)')
    code=code.replace("facts = sql.startswith(('INSERT INTO work_', 'INSERT INTO active_', 'UPDATE active_', 'DELETE FROM active_'))", "facts = sql.startswith(('INSERT INTO projects','INSERT INTO tasks','UPDATE projects','UPDATE tasks','INSERT INTO work_','INSERT INTO template_','UPDATE dataset_meta'))")
    with paused_child(code,directory,phase,frozen_json(r)):pass
    reopened=SQLiteStore(directory)
    try:
        service=Schema4RuntimeService(reopened);committed=phase=='committed'
        found=service.reconcile_request(r);assert found.status==('committed' if committed else 'absent')
        if not committed:assert logical(reopened.path)==before
        result=service.execute(r);assert result.status=='committed',result
        after=logical(reopened.path)
        assert service.execute(r).result==result.result and logical(reopened.path)==after
        assert len(after['committed_requests'])==len(before['committed_requests'])+1
    finally:reopened.close()


@pytest.mark.parametrize('family',FAMILIES)
@pytest.mark.parametrize('fault',['domain write','receipt','final verification','commit before','commit after'])
def test_sql_faults_roll_back_or_reconcile_the_original_request(runtime,monkeypatch,family,fault):
    h=runtime;r=prepare(h,family);before=h.facts();failure=OSError('Original '+fault);fired=[]
    inner=h.store.connection
    class Fault:
        def __getattr__(self,k):return getattr(inner,k)
        def execute(self,sql,*args):
            matches=(fault=='domain write' and sql.startswith(('INSERT INTO projects','INSERT INTO tasks','UPDATE projects','UPDATE tasks','INSERT INTO work_','INSERT INTO template_','UPDATE dataset_meta'))
                     or fault=='receipt' and sql.startswith('INSERT INTO committed_requests')
                     or fault.startswith('commit') and sql=='COMMIT')
            if matches and not fired:
                fired.append(True)
                if fault=='commit after':inner.execute(sql,*args)
                raise failure
            return inner.execute(sql,*args)
    h.store.connection=Fault()
    verify=h.store._verify_selected;calls=[]
    if fault=='final verification':
        def final(c,**kw):
            calls.append(True)
            if len(calls)==2:fired.append(True);raise failure
            return verify(c,**kw)
        monkeypatch.setattr(h.store,'_verify_selected',final)
    result=h.service.execute(r)
    assert fired and result.error is failure
    assert result.status==('committed' if fault=='commit after' else 'rolled_back')
    if fault!='commit after':assert h.facts()==before
    retained=h.facts();evidence=h.service.reconcile_request(r)
    assert evidence.status==('committed' if fault=='commit after' else 'absent')
    if fault=='commit after':assert h.service.execute(r).result==result.result and h.facts()==retained


@pytest.mark.parametrize('phase',['facts','commit_ready','committed'])
def test_delete_process_death_has_only_atomic_current_state_and_no_receipt(runtime,phase):
    h=runtime;p=h.project();review=h.service.read_delete_preview('project',p)
    r=Request.make(uid(),h.store.dataset_id,'delete_project',h.now+1,project_id=p,expected_version=1,review=review,confirmed_text='DELETE')
    directory=h.store.directory;before=h.facts();h.store.close()
    code=TRANSACTION_CHILD.replace('from chronicle.services import TimerService','from chronicle.schema4_runtime_service import Schema4RuntimeService as TimerService').replace('SQLiteStore(path, schema_version=3)','SQLiteStore(path)')
    code=code.replace("facts = sql.startswith(('INSERT INTO work_', 'INSERT INTO active_', 'UPDATE active_', 'DELETE FROM active_'))","facts = sql.startswith(('DELETE FROM projects','DELETE FROM committed_requests'))")
    with paused_child(code,directory,phase,frozen_json(r)):pass
    reopened=SQLiteStore(directory)
    try:
        service=Schema4RuntimeService(reopened)
        presence=service.read_delete_presence('project',p)
        assert presence['present']==(phase!='committed') and presence['historical_outcome_verified'] is False
        assert service.reconcile_request(r).status=='unverified'  # Never reconcile absence/reexecute Delete.
        after=logical(reopened.path)
        if phase!='committed':assert after==before
        else:assert not after['projects'] and not after['committed_requests']
        assert after['sqlite_sequence']==before['sqlite_sequence']
    finally:reopened.close()


@pytest.mark.parametrize('phase',['profile','schema','committed'])
def test_fresh_creation_process_death_never_reinitializes_partial_images(tmp_path,phase):
    directory=tmp_path/'fresh'
    code=r'''
import sys
from chronicle.sqlite_store import SQLiteStore
from chronicle import schema_profiles
path,phase=sys.argv[1:]
def barrier():print('BARRIER',flush=True);sys.stdin.readline()
if phase=='profile':
 original=SQLiteStore._profile
 def profile(self):original(self);barrier()
 SQLiteStore._profile=profile
elif phase=='schema':
 original=schema_profiles.schema_statements
 def statements():
  for i,s in enumerate(original()):
   yield s
   if i==0:barrier()
 schema_profiles.schema_statements=statements
else:
 original=SQLiteStore._connect
 class Connection:
  def __init__(self,c):self.c=c
  def __getattr__(self,k):return getattr(self.c,k)
  def execute(self,sql,*a):
   result=self.c.execute(sql,*a)
   if sql=='COMMIT':barrier()
   return result
 SQLiteStore._connect=lambda self:Connection(original(self))
SQLiteStore(path,create=True,timezone='Etc/UTC')
'''
    with paused_child(code,directory,phase):pass
    path=directory/'chronicle.sqlite3';raw=path.read_bytes()
    if phase=='committed':
        reopened=SQLiteStore(directory)
        try:assert reopened.schema_version==4 and not list(reopened.connection.execute('SELECT * FROM tasks'))
        finally:reopened.close()
    else:
        with pytest.raises((ValueError,sqlite3.DatabaseError)) as caught:SQLiteStore(directory)
        assert caught.value and path.read_bytes()==raw
    with pytest.raises(ValueError):SQLiteStore(directory,create=True,timezone='Etc/UTC')
    assert path.read_bytes()==raw


@pytest.mark.parametrize('kind',['backup','restore'])
@pytest.mark.parametrize('phase',['staging','before publication','after publication'])
def test_file_operation_process_death_preserves_source_and_published_output(runtime,tmp_path,kind,phase):
    h=runtime;p=h.project();key=h.task(p)
    h.send('add_date_only_work',task_id=key,entry_id=uid(),work_date='2026-10-19',duration_text='0:15',comment='Protected')
    h.send('start_timer',task_id=key,entry_id=uid(),expected_task_version=1)
    facts=h.facts();directory=h.store.directory
    source=tmp_path/'source.sqlite3';assert h.store.backup(source).verified
    raw=source.read_bytes();target=tmp_path/('backup.sqlite3' if kind=='backup' else 'restored')
    h.store.close()
    code=r'''
import sys
from pathlib import Path
from chronicle.sqlite_store import SQLiteStore
from chronicle import backup_restore as br
kind,phase,directory,source,target=sys.argv[1:]
def barrier():print('BARRIER',flush=True);sys.stdin.readline()
copy=br._copy;link=br.os.link
if phase=='staging':
 def copying(c,path):copy(c,path);barrier()
 br._copy=copying
else:
 def publishing(a,b):
  if phase=='before publication':barrier()
  result=link(a,b)
  if phase=='after publication':barrier()
  return result
 br.os.link=publishing
if kind=='backup':
 s=SQLiteStore(directory);s.backup(target);s.close()
else:br.restore_image(source,target)
'''
    with paused_child(code,kind,phase,directory,source,target):pass
    assert source.read_bytes()==raw
    final=target if kind=='backup' else target/'chronicle.sqlite3'
    assert final.exists()==(phase=='after publication')
    if final.exists():
        from chronicle.backup_restore import validate_image
        assert validate_image(final).dataset_id==h.store.dataset_id and logical(final)==facts
    reopened=SQLiteStore(directory)
    try:assert logical(reopened.path)==facts
    finally:reopened.close()
