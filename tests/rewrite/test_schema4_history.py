"""Self-contained native-v4 receipt fixtures; no Package B service is simulated."""
from copy import deepcopy
from pathlib import Path

import pytest

from chronicle import schema_profiles as schema
from chronicle.administration import (candidate_move_result, verify_schema4_history,
                                      UnsupportedCandidateOperation)
from chronicle.records import Request, canonical
from conftest import NOW
from test_schema4 import candidate


def key(n):return f'00000000-0000-0000-0000-{n:012x}'


def image(c):
    return Path(next(r[2] for r in c.execute('PRAGMA database_list') if r[1]=='main')).read_bytes()


class History:
    """Fixed four-project/two-task oracle with explicitly known relationships."""
    def __init__(self,c):
        self.c=c;self.dataset=c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0]
        self.projects={};self.tasks={};self.receipts=[]
        for identity in (1,2):
            r=self.receipt('create_project',dict(project_id=key(identity),name='Duplicate'),dict(project_id=key(identity),version=1))
            self.projects[key(identity)]=self.row('project',key(identity),r,parent_project_id=None)
        for identity,parent,ancestry in ((3,1,[1]),(4,3,[1,3])):
            r=self.receipt('create_child_project',dict(project_id=key(identity),name='Duplicate',parent_project_id=key(parent),expected_parent_version=1,
                reviewed_parent_ancestry=[dict(project_id=key(i),expected_version=1,parent_project_id=key(1) if i==3 else None) for i in ancestry]),dict(project_id=key(identity),version=1))
            self.projects[key(identity)]=self.row('project',key(identity),r,parent_project_id=key(parent))
        for identity,parent in ((101,None),(102,101)):
            r=self.receipt('create_task',dict(task_id=key(identity),name='Duplicate',project_id=key(4),parent_task_id=key(parent) if parent else None,expected_project_version=1,expected_parent_version=1 if parent else None),dict(task_id=key(identity),version=1))
            self.tasks[key(identity)]=self.row('task',key(identity),r,project_id=key(4),parent_task_id=key(parent) if parent else None)

    @staticmethod
    def row(entity,identity,request,**context):
        return dict(**{entity+'_id':identity},name='Duplicate',version=1,is_archived=0,archived_at_utc_us=None,
                    created_request_id=request.request_id,created_utc_us=request.action_utc_us,updated_utc_us=request.action_utc_us,**context)

    def receipt(self,operation,args,result):
        if operation=='create_task':
            from chronicle.administration import _candidate_ancestry
            from chronicle.hierarchy import ProjectForest
            group=args.get('project_id')
            if args.get('parent_task_id') is not None:group=self.tasks[args['parent_task_id']]['project_id']
            args=dict(args,reviewed_destination_project_ancestry=_candidate_ancestry(ProjectForest(list(self.projects.values())),self.projects,group))
        seq=len(self.receipts)+1
        request=Request.make(key(1000+seq),self.dataset,operation,NOW+seq,**args)
        self.receipts.append(dict(commit_seq=seq,request_id=request.request_id,operation=operation,
                                 receipt_class='administrative' if operation in schema.ADMINISTRATIVE_OPERATIONS else 'protected',
                                 request_bytes=request.content(),result_bytes=canonical(result),action_utc_us=request.action_utc_us))
        return request

    def move_arguments(self,destination):
        source=self.projects[key(3)];parent=source['parent_project_id']
        return dict(project_id=key(3),expected_version=source['version'],source_parent_project_id=parent,
                    destination_parent_project_id=key(destination) if destination else None,
                    expected_destination_parent_version=1 if destination else None,
                    reviewed_source_ancestry=[] if parent is None else [dict(project_id=parent,expected_version=1,parent_project_id=None)],
                    reviewed_destination_ancestry=[] if destination is None else [dict(project_id=key(destination),expected_version=1,parent_project_id=None)],
                    reviewed_projects=[dict(project_id=key(3),expected_version=source['version'],parent_project_id=parent),dict(project_id=key(4),expected_version=1,parent_project_id=key(3))],
                    reviewed_tasks=[dict(task_id=key(101),expected_version=1,parent_task_id=None,project_id=key(4)),dict(task_id=key(102),expected_version=1,parent_task_id=key(101),project_id=key(4))])

    def move(self,destination):
        args=self.move_arguments(destination)
        result=dict(project_id=key(3),version=self.projects[key(3)]['version']+1,parent_project_id=key(destination) if destination else None)
        request=self.receipt('move_project_subtree',args,result)
        self.projects[key(3)].update(version=result['version'],parent_project_id=result['parent_project_id'],updated_utc_us=request.action_utc_us)

    def install(self):
        self.c.execute('BEGIN')
        try:
            for table,rows in (('committed_requests',self.receipts),('projects',self.projects.values()),('tasks',self.tasks.values())):
                for row in rows:
                    columns=tuple(row)
                    self.c.execute(f'INSERT INTO {table}('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(row.values()))
            self.c.execute('COMMIT')
        except BaseException:
            self.c.execute('ROLLBACK');raise


def test_root_child_and_task_creation_are_native_candidate_history(candidate):
    h=History(candidate);h.install();before=image(candidate)
    result=schema.verify_candidate(candidate)
    assert result.administrative_history_verified and not result.ordinary_startup_permitted
    assert image(candidate)==before
    assert candidate.execute('SELECT parent_project_id FROM projects WHERE project_id=?',(key(1),)).fetchone()[0] is None
    assert candidate.execute('SELECT parent_project_id FROM projects WHERE project_id=?',(key(4),)).fetchone()[0]==key(3)
    assert candidate.execute('SELECT count(DISTINCT name) FROM projects').fetchone()[0]==1


@pytest.mark.parametrize('destination',[None,2])
def test_reconstructed_movement_changes_only_source_project(candidate,destination):
    h=History(candidate);before=deepcopy((h.projects,h.tasks));h.move(destination);h.install()
    assert schema.verify_candidate(candidate).administrative_history_verified
    actual={r['project_id']:dict(r) for r in candidate.execute('SELECT * FROM projects')}
    assert actual[key(3)]['version']==2 and actual[key(3)]['parent_project_id']==(key(destination) if destination else None)
    assert actual[key(4)]['parent_project_id']==key(3)
    assert {k:v for k,v in actual.items() if k!=key(3)}=={k:v for k,v in before[0].items() if k!=key(3)}
    assert {r['task_id']:dict(r) for r in candidate.execute('SELECT * FROM tasks')}==before[1]


def test_chronological_move_to_branch_then_root_preserves_creation_ownership(candidate):
    h=History(candidate);owners={k:r['created_request_id'] for k,r in h.projects.items()}
    h.move(2);h.move(None);h.install()
    assert schema.verify_candidate(candidate).administrative_history_verified
    assert candidate.execute('SELECT version,parent_project_id FROM projects WHERE project_id=?',(key(3),)).fetchone()[:]==(3,None)
    assert {r['project_id']:r['created_request_id'] for r in candidate.execute('SELECT * FROM projects')}==owners


@pytest.mark.parametrize('damage',['missing creation','creation owner','duplicate project','contradictory parent','source version','source ancestry','destination ancestry','missing project','missing task','member version','task membership','result version','result parent','chronology','timestamp','request bytes','result bytes','extra argument','wrong dataset','wrong class','unknown operation','no-op receipt'])
def test_independent_history_refuses_inconsistent_complete_evidence(candidate,damage):
    import json
    h=History(candidate);h.move(2)
    projects,tasks,receipts=deepcopy((list(h.projects.values()),list(h.tasks.values()),h.receipts))
    move=receipts[-1];content=json.loads(move['request_bytes']);args=content['arguments'];result=json.loads(move['result_bytes'])
    if damage=='missing creation':receipts.pop(0)
    if damage=='creation owner':projects[0]['created_request_id']=key(1999)
    if damage=='duplicate project':projects.append(dict(projects[0]))
    if damage=='contradictory parent':projects[2]['parent_project_id']=key(1)
    if damage=='source version':args['expected_version']=2
    if damage=='source ancestry':args['reviewed_source_ancestry'][0]['expected_version']=2
    if damage=='destination ancestry':args['reviewed_destination_ancestry']=[]
    if damage=='missing project':args['reviewed_projects'].pop()
    if damage=='missing task':args['reviewed_tasks'].pop()
    if damage=='member version':args['reviewed_tasks'][0]['expected_version']=2
    if damage=='task membership':tasks[0]['project_id']=key(1)
    if damage=='result version':result['version']=3
    if damage=='result parent':result['parent_project_id']=None
    if damage=='chronology':receipts[0]['commit_seq'],move['commit_seq']=move['commit_seq'],receipts[0]['commit_seq']
    if damage=='timestamp':projects[2]['updated_utc_us']+=1
    if damage=='extra argument':args['inferred_parent']=key(2)
    if damage=='wrong dataset':content['dataset_id']=key(2000)
    if damage=='wrong class':move['receipt_class']='protected'
    if damage=='unknown operation':content['operation']=move['operation']='unknown_administrative'
    if damage=='no-op receipt':
        args.update(destination_parent_project_id=key(1),expected_destination_parent_version=1,
                    reviewed_destination_ancestry=[dict(project_id=key(1),expected_version=1,parent_project_id=None)])
    move['request_bytes']=canonical(content)+(b' ' if damage=='request bytes' else b'')
    move['result_bytes']=canonical(result)+(b' ' if damage=='result bytes' else b'')
    with pytest.raises(ValueError):verify_schema4_history(projects,tasks,receipts,h.dataset)


@pytest.mark.parametrize('damage',['project omitted','task omitted','wrong result','timestamp','request whitespace'])
def test_sqlite_candidate_rejects_tampering_after_exact_guards_are_restored(candidate,damage):
    import json
    h=History(candidate);h.move(2);h.install()
    row=h.receipts[-1];content=json.loads(row['request_bytes']);result=json.loads(row['result_bytes'])
    if damage=='project omitted':content['arguments']['reviewed_projects'].pop()
    if damage=='task omitted':content['arguments']['reviewed_tasks'].pop()
    if damage=='wrong result':result['version']=99
    if damage=='timestamp':content['action_utc_us']+=1
    raw=canonical(content)+(b' ' if damage=='request whitespace' else b'')
    trigger=candidate.execute("SELECT sql FROM sqlite_schema WHERE name='immutable_committed_requests_update'").fetchone()[0]
    candidate.execute('DROP TRIGGER immutable_committed_requests_update')
    candidate.execute('UPDATE committed_requests SET request_bytes=?,result_bytes=? WHERE request_id=?',(raw,canonical(result),row['request_id']))
    candidate.execute(trigger)
    schema.verify_schema(candidate)
    with pytest.raises(ValueError):schema.verify_candidate(candidate)
    assert not candidate.in_transaction


def test_validated_noop_has_no_effect_and_cannot_have_a_receipt(candidate):
    h=History(candidate);h.install();before=image(candidate)
    assert candidate_move_result(h.projects,h.tasks,h.move_arguments(1)) is None
    assert image(candidate)==before
    # No B service is called: the contract forbids persisting this unchanged case.
    h.receipt('move_project_subtree',h.move_arguments(1),dict(project_id=key(3),version=1,parent_project_id=key(1)))
    with pytest.raises(ValueError,match='No-op'):verify_schema4_history(list(h.projects.values()),list(h.tasks.values()),h.receipts,h.dataset)


@pytest.mark.parametrize('operation',['delete_project','move_task_branch','apply_template','start_timer','register_timesheet_export','confirm_polr_absolute'])
def test_invalid_or_unsupported_candidate_requests_fail_closed(candidate,operation):
    h=History(candidate);h.receipt(operation,{},{});h.install()
    with pytest.raises(ValueError):schema.verify_candidate(candidate)


@pytest.mark.parametrize('review',['cycle','archived source','archived destination','missing destination','root version','unsorted members','duplicate members','boolean version','unknown field'])
def test_project_move_contract_invalid_context_refuses_without_mutation(candidate,review):
    h=History(candidate);args=h.move_arguments(2)
    if review=='cycle':
        args.update(destination_parent_project_id=key(4),expected_destination_parent_version=1,
            reviewed_destination_ancestry=[dict(project_id=key(1),expected_version=1,parent_project_id=None),dict(project_id=key(3),expected_version=1,parent_project_id=key(1)),dict(project_id=key(4),expected_version=1,parent_project_id=key(3))])
    if review=='archived source':h.projects[key(1)]['is_archived']=1
    if review=='archived destination':h.projects[key(2)]['is_archived']=1
    if review=='missing destination':args['destination_parent_project_id']=key(999)
    if review=='root version':args.update(destination_parent_project_id=None,reviewed_destination_ancestry=[],expected_destination_parent_version=1)
    if review=='unsorted members':args['reviewed_projects'].reverse()
    if review=='duplicate members':args['reviewed_tasks'].append(dict(args['reviewed_tasks'][0]))
    if review=='boolean version':args['expected_version']=True
    if review=='unknown field':args['ignore_stale']=True
    before=deepcopy((h.projects,h.tasks))
    with pytest.raises(ValueError):candidate_move_result(h.projects,h.tasks,args)
    assert (h.projects,h.tasks)==before


@pytest.mark.parametrize('damage',['truncated ancestry','wrong parent version','wrong result','extra field'])
def test_child_creation_review_is_exact(candidate,damage):
    import json
    h=History(candidate);row=h.receipts[3];content=json.loads(row['request_bytes'])
    if damage=='truncated ancestry':content['arguments']['reviewed_parent_ancestry'].pop(0)
    if damage=='wrong parent version':content['arguments']['expected_parent_version']=2
    if damage=='wrong result':row['result_bytes']=canonical(dict(project_id=key(4),version=2))
    if damage=='extra field':content['arguments']['source_schema']=3
    row['request_bytes']=canonical(content)
    with pytest.raises(ValueError):verify_schema4_history(list(h.projects.values()),list(h.tasks.values()),h.receipts,h.dataset)


def test_complete_candidate_admits_exact_valid_active_evidence(candidate):
    from test_schema4 import sql_work,sql_active
    h=History(candidate);h.install();entry=key(500)
    request=Request.make(key(2000),h.dataset,'start_timer',NOW,task_id=key(102),entry_id=entry,expected_task_version=1)
    candidate.execute('BEGIN')
    # Fill exact deferred creation ownership; no Package B/C service is invoked.
    candidate.execute("INSERT INTO work_entries(entry_id,task_id,kind,original_start_utc_us,created_request_id) VALUES(?,?,'timed',?,?)",(entry,key(102),NOW,request.request_id))
    sql_active(candidate,key(102),entry)
    candidate.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                      (request.request_id,request.operation,'protected',request.content(),canonical(dict(entry_id=entry,version=1)),NOW))
    candidate.execute('COMMIT')
    schema.verify_structure(candidate)
    assert schema.verify_candidate(candidate).semantic_verified


def test_existing_rename_effects_remain_exact_native_candidate_history(candidate):
    h=History(candidate)
    for entity,identity in (('project',1),('task',101)):
        request=h.receipt('rename_'+entity,{entity+'_id':key(identity),'name':'Renamed','expected_version':1},{entity+'_id':key(identity),'version':2})
        (h.projects if entity=='project' else h.tasks)[key(identity)].update(name='Renamed',version=2,updated_utc_us=request.action_utc_us)
    h.install();assert schema.verify_candidate(candidate).administrative_history_verified


@pytest.mark.parametrize('configuration',['week_start','dismissed'])
def test_configuration_without_required_history_is_not_accepted(candidate,configuration):
    if configuration=='week_start':candidate.execute('UPDATE dataset_meta SET week_start=0')
    else:candidate.execute("UPDATE dataset_meta SET polr_reminder_dismissed_local_date='2026-10-19'")
    with pytest.raises(ValueError,match='Configuration'):schema.verify_candidate(candidate)
