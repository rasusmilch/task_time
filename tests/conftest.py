"""Current application fixtures; every database is disposable schema 5."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from chronicle.sqlite_store import SQLiteStore
from chronicle.services import RuntimeService
from chronicle.records import Request, canonical
from chronicle import project_ui as ui, schema
from chronicle.timekeeping import to_us

NOW = to_us(datetime(2026,10,19,15,tzinfo=timezone.utc))
M = 60_000_000


def uid():
    return str(uuid4())


class Client:
    """Request builder over the actual production owner, never a transaction adapter."""
    def __init__(self, store):
        self.store = store
        self.service = RuntimeService(store)
        self.now = NOW

    def facts(self):
        with self.store.read_transaction() as c:
            return {name: sorted(schema._rows(c,name),key=repr) for name, in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")}

    def state(self):
        return self.service.read_current_state(cutoff_utc_us=self.now)

    def request(self, operation, **args):
        self.now += 1_000_000
        return Request.make(uid(),self.store.dataset_id,operation,self.now,**args)

    def send(self, operation, expect='committed', **args):
        r = self.request(operation,**args)
        before = self.facts()
        outcome = self.service.execute(r)
        assert outcome.status == expect, outcome
        after = self.facts()
        if expect in ('rejected','unchanged','rolled_back'):
            assert after == before
        if expect == 'committed' and operation not in ('delete_task','delete_project','delete_template'):
            rows = [row for row in after['committed_requests'] if row['request_id']==r.request_id]
            assert len(rows)==1 and rows[0]['request_bytes']==r.content() and rows[0]['result_bytes']==canonical(outcome.result)
        return r,outcome

    def project(self, parent=None, name='Project'):
        key=uid();args=dict(project_id=key,name=name)
        if parent:
            state=self.state();p=next(p for p in state['projects'] if p['project_id']==parent)
            args.update(parent_project_id=parent,expected_parent_version=p['version'],reviewed_parent_ancestry=ui.ancestry(state,parent))
        self.send('create_child_project' if parent else 'create_project',**args)
        return key

    def task(self, project, parent=None, name='Task'):
        key=uid();self.send('create_task',task_id=key,name=name,**ui.new_task_review(self.state(),parent,project))
        return key

    def dated(self, task, duration='0:15', day='2026-10-19'):
        key=uid();self.send('add_date_only_work',task_id=task,entry_id=key,work_date=day,duration_text=duration,comment='Reviewed work')
        return key

    def lifecycle(self, entity, key, archive=True, expect='committed'):
        row=next(r for r in self.state()[entity+'s'] if r[entity+'_id']==key)
        return self.send(('archive_' if archive else 'unarchive_')+entity,expect=expect,**{entity+'_id':key,'expected_version':row['version']})

    def move_args(self, task, project, parent=None):
        from chronicle.movement import snapshot
        state=self.state();return ui.task_move_arguments(state,task,parent,project,snapshot(state['tasks'],task))[0]

    def template(self, depth=2):
        first=uid();nodes=[dict(node_id=first,parent_node_id=None,name='Root',position=0)]
        if depth==2:nodes.append(dict(node_id=uid(),parent_node_id=first,name='Child',position=1))
        key=uid();self.send('create_template',template_id=key,name='Blueprint',nodes=nodes)
        return next(t for t in self.state()['templates'] if t['template_id']==key)

    def apply_args(self, definition, project, parent=None):
        state=self.state();tasks={t['task_id']:t for t in state['tasks']};projects={p['project_id']:p for p in state['projects']}
        return dict(template_id=definition['template_id'],expected_template_version=definition['version'],reviewed_definition=definition,
            destination_project_id=project,destination_parent_task_id=parent,
            expected_destination_project_version=projects[project]['version'] if project else None,
            expected_destination_parent_version=tasks[parent]['version'] if parent else None,
            reviewed_destination_project_ancestry=ui.ancestry(state,project),
            node_mapping=[dict(node_id=n['node_id'],task_id=uid()) for n in definition['nodes']])

    def preview(self, task=None):
        return self.service.prepare_timesheet_preview(export_id=uid(),cutoff_utc_us=self.now,period='custom',start_date='2026-10-19',end_date='2026-10-20',
            scope_kind='selected' if task else 'all',task_ids=[task] if task else [])

    def export(self, task=None):
        value=self.preview(task);self.send('register_timesheet_export',candidate=value.content());return value

    def manual(self, task, quarters, day='2026-10-19'):
        prior=self.service.read_polr_manual_context(task,day,cutoff_utc_us=self.now)
        return self.send('confirm_polr_absolute',batch_id=uid(),mode='manual',source_export_id=None,source_metadata=None,
            reviewed_rows=[],selected_keys=[],acknowledgements=[],manual_cells=[dict(task_id=task,work_date=day,confirmed_quarters=quarters,
                prior_batch_id=prior['current_batch_id'],prior_quarters=prior['confirmed_quarters'])])


@pytest.fixture
def client(tmp_path):
    store=SQLiteStore(tmp_path/'current',create=True,timezone='America/Chicago')
    try:yield Client(store)
    finally:store.close()
