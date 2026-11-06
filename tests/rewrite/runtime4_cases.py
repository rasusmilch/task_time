"""Fresh production components only; no candidate transaction/worker adapters."""
from pathlib import Path
from uuid import uuid4
import pytest
from chronicle.sqlite_store import SQLiteStore
from chronicle.schema4_runtime_service import Schema4RuntimeService
from chronicle.records import Request
from chronicle import project_ui
from conftest import NOW
from test_backup_restore import logical

M=60_000_000
def uid(): return str(uuid4())


class Runtime:
    def __init__(self,store):
        self.store=store;self.service=Schema4RuntimeService(store);self.now=NOW
        self.requests=[]

    def send(self,op,expect='committed',**args):
        self.now+=1_000_000
        request=Request.make(uid(),self.store.dataset_id,op,self.now,**args)
        self.requests.append(request)
        outcome=self.service.execute(request)
        assert outcome.status==expect,outcome
        return request,outcome

    def state(self):return self.service.read_current_state(cutoff_utc_us=self.now)
    def facts(self):return logical(self.store.path)

    def project(self,parent=None,name='Project'):
        key=uid();args=dict(project_id=key,name=name)
        if parent is not None:
            state=self.state();row=next(p for p in state['projects'] if p['project_id']==parent)
            args.update(parent_project_id=parent,expected_parent_version=row['version'],reviewed_parent_ancestry=project_ui.ancestry(state,parent))
        self.send('create_child_project' if parent else 'create_project',**args)
        return key

    def task(self,group=None,parent=None,name='Task'):
        key=uid();self.send('create_task',task_id=key,name=name,**project_ui.new_task_review(self.state(),parent,group));return key

    def lifecycle(self,entity,key,op='archive',expect='committed'):
        row=next(r for r in self.state()[entity+'s'] if r[entity+'_id']==key)
        return self.send(op+'_'+entity,expect=expect,**{entity+'_id':key,'expected_version':row['version']})


@pytest.fixture
def runtime(tmp_path):
    store=SQLiteStore(tmp_path/'production',create=True,timezone='America/Chicago')
    try:yield Runtime(store)
    finally:store.close()
