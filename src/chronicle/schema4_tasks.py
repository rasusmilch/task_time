"""Schema-4 task destinations and caller-owned task operations; no worker."""
from copy import deepcopy
from . import schema_profiles as schema
from .hierarchy import ProjectForest, candidate_task_observations, task_paths
from .records import uuid_text, integer, StaleState, canonical
from .project_services import CandidateProjectContext, _facts, _ancestry, _review, PROJECT_REVIEW
from .services import name_text

OPERATIONS=frozenset(('create_task','rename_task','rename_project','assign_task_to_project','move_task_branch'))


def ancestry_review(projects,parent,supplied):
    _review(supplied,_ancestry(ProjectForest(list(projects.values())),projects,parent),PROJECT_REVIEW)


def effective_projects(projects):
    forest=ProjectForest(projects)
    return [dict(p,is_archived=int(forest.effective_archived[p['project_id']])) for p in projects]


def task_move_plan(tasks,projects,active,args):
    from .movement import plan,FIELDS
    extensions={'reviewed_source_project_ancestry','reviewed_destination_project_ancestry'}
    if set(args)!=FIELDS|extensions:raise ValueError('Exact schema-4 task movement fields required')
    groups={p['project_id']:p for p in projects}
    ancestry_review(groups,args['source_project_id'],args['reviewed_source_project_ancestry'])
    ancestry_review(groups,args['destination_project_id'],args['reviewed_destination_project_ancestry'])
    return plan(tasks,effective_projects(projects),active,{k:v for k,v in args.items() if k not in extensions})


def check(c,request,context):
    request.content()
    if type(context) is not CandidateProjectContext or not c.in_transaction:
        raise ValueError('Explicit candidate context and owned transaction required')
    schema.verify_structure(c)
    if request.dataset_id!=context.dataset_id or request.dataset_id!=c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0]:
        raise ValueError('Wrong candidate dataset')
    if c.execute('SELECT 1 FROM committed_requests WHERE request_id=?',(request.request_id,)).fetchone():
        raise ValueError('Transaction owner must resolve committed requests first')


def install_move(c,request,args,tasks,final,result):
    if not result['changed_tasks']:return
    branch={r['task_id'] for r in args['reviewed_subtree']};root=args['task_id']
    old={t['task_id']:t for t in tasks}
    if args['source_project_id']!=args['destination_project_id']:
        for key in sorted(branch):c.execute('UPDATE tasks SET parent_task_id=NULL WHERE task_id=?',(key,))
        for key in sorted(branch):c.execute('UPDATE tasks SET project_id=? WHERE task_id=?',(args['destination_project_id'],key))
        c.execute('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(args['destination_parent_task_id'],root))
        paths=task_paths(final)
        for key in sorted(branch-{root},key=lambda k:(len(paths[k]),k)):
            c.execute('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(old[key]['parent_task_id'],key))
    else:c.execute('UPDATE tasks SET parent_task_id=? WHERE task_id=?',(args['destination_parent_task_id'],root))
    for row in result['changed_tasks']:
        c.execute('UPDATE tasks SET version=?,updated_utc_us=? WHERE task_id=?',(row['version'],request.action_utc_us,row['task_id']))


def apply_task_operation(c,request,context):
    check(c,request,context)
    before=_facts(c);a=request.args();op=request.operation;now=request.action_utc_us
    projects={p['project_id']:p for p in before['projects']};tasks={t['task_id']:dict(t) for t in before['tasks']}
    active=before['active_timer'][0] if before['active_timer'] else None
    if op not in OPERATIONS:raise ValueError('Unknown schema-4 task management operation')
    if op=='move_task_branch':
        final,result=task_move_plan(list(tasks.values()),list(projects.values()),active,a)
        if not result['changed_tasks']:return None
        changed={r['task_id'] for r in result['changed_tasks']}
        for t in final:
            if t['task_id'] in changed:t['updated_utc_us']=now
        install_move(c,request,a,list(tasks.values()),final,result)
        expected=dict(before,tasks=sorted(final,key=repr))
    else:
        entity='project' if op=='rename_project' else 'task';field=entity+'_id';table=entity+'s'
        rows=deepcopy(projects if entity=='project' else tasks)
        key=uuid_text(a.get(field))
        if op=='create_task':
            required={'task_id','name','reviewed_destination_project_ancestry'}
            if not required<=set(a) or not set(a)<=required|{'project_id','parent_task_id','expected_project_version','expected_parent_version'}:raise ValueError('Exact schema-4 task creation fields required')
            if key in tasks:raise ValueError('Duplicate task identity')
            parent=a.get('parent_task_id');group=a.get('project_id')
            observations=candidate_task_observations(list(tasks.values()),list(projects.values()))
            if parent is not None:
                uuid_text(parent);integer(a.get('expected_parent_version'),'Parent version',1,2**63-1)
                if parent not in tasks or tasks[parent]['version']!=a['expected_parent_version']:raise StaleState('Task parent changed')
                p=tasks[parent]
                if 'project_id' in a and group!=p['project_id']:raise ValueError('Task parent/project differs')
                group=p['project_id']
                if observations[parent]['effective_archived'] or observations[parent]['depth']>=3 or active and active['task_id']==parent:raise ValueError('Task parent ineligible or running')
            elif a.get('expected_parent_version') is not None:raise ValueError('Root task has no parent version')
            ancestry_review(projects,group,a['reviewed_destination_project_ancestry'])
            if group is not None:
                uuid_text(group)
                if group not in projects or ProjectForest(list(projects.values())).effective_archived[group]:raise StaleState('Project destination missing or archived')
                if parent is None or a.get('expected_project_version') is not None:
                    integer(a.get('expected_project_version'),'Project version',1,2**63-1)
                    if projects[group]['version']!=a['expected_project_version']:raise StaleState('Project version changed')
            elif a.get('expected_project_version') is not None:raise ValueError('Unassigned has no version')
            row=dict(task_id=key,project_id=group,parent_task_id=parent,name=name_text(a['name']),version=1,is_archived=0,
                     archived_at_utc_us=None,created_request_id=request.request_id,created_utc_us=now,updated_utc_us=now)
            rows[key]=row;columns=tuple(row)
            c.execute('INSERT INTO tasks('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(row.values()))
        else:
            extra={'reviewed_source_project_ancestry','reviewed_destination_project_ancestry'} if op=='assign_task_to_project' else set()
            if set(a)!={field,'expected_version',('project_id' if op=='assign_task_to_project' else 'name')}|extra:raise ValueError('Exact management fields required')
            integer(a['expected_version'],'Reviewed version',1,2**63-1)
            if key not in rows or rows[key]['version']!=a['expected_version']:raise StaleState('Entity identity/version changed')
            row=rows[key]
            if op=='assign_task_to_project':
                group=a['project_id']
                if group is not None:uuid_text(group)
                ancestry_review(projects,row['project_id'],a['reviewed_source_project_ancestry'])
                ancestry_review(projects,group,a['reviewed_destination_project_ancestry'])
                obs=candidate_task_observations(list(tasks.values()),list(projects.values()))[key]
                forest=ProjectForest(list(projects.values()))
                if row['parent_task_id'] is not None or any(t['parent_task_id']==key for t in tasks.values()):raise ValueError('Only standalone task assignment')
                if obs['effective_archived'] or group is not None and forest.effective_archived[group]:raise ValueError('Assignment context archived')
                if group==row['project_id']:return None
                row['project_id']=group
            else:
                name=name_text(a['name'])
                if name==row['name']:return None
                row['name']=name
            row.update(version=integer(row['version']+1,'New version',1,2**63-1),updated_utc_us=now)
            changed_field='project_id' if op=='assign_task_to_project' else 'name'
            c.execute(f'UPDATE {table} SET {changed_field}=?,version=?,updated_utc_us=? WHERE {field}=?',
                      (row[changed_field],row['version'],now,key))
        expected=dict(before,**{table:sorted(rows.values(),key=repr)})
        result={field:key,'version':rows[key]['version']}
    if _facts(c)!=expected:raise ValueError('Task operation changed unexpected logical facts')
    return result
