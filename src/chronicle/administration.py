"""Independent chronological administrative verification, never runtime state."""
from .records import canonical, uuid_text, integer
from .hierarchy import task_paths
from .movement import plan


def verify(c, receipts):
    # Only disposable validation state. Ordinary reads/mutations use SQLite rows.
    tasks,projects={},{}
    active=None
    def version(rows,key,wanted):
        integer(wanted,'Reviewed administrative version',1,2**63-1)
        if key not in rows or rows[key]['version']!=wanted:raise ValueError('Administrative reviewed version differs')
        return rows[key]
    for _,request_id in c.execute('SELECT commit_seq,request_id FROM committed_requests ORDER BY commit_seq'):
        request,result=receipts[request_id];op=request.operation;a=request.args();now=request.action_utc_us
        if op in ('start_timer','switch_timer'):
            active=dict(task_id=a['next_task_id' if op=='switch_timer' else 'task_id'])
        elif op=='stop_timer':
            active=None
        if op=='move_task_branch':
            final,expected=plan(list(tasks.values()),list(projects.values()),active,a)
            if not expected['changed_tasks']:raise ValueError('No-op move cannot have a receipt')
            if canonical(result)!=canonical(expected):raise ValueError('Move administrative effects differ')
            tasks={r['task_id']:r for r in final}
            for changed in expected['changed_tasks']:tasks[changed['task_id']]['updated_utc_us']=now
            continue
        if op not in ('create_project','create_task','rename_project','rename_task','assign_task_to_project'):continue
        entity='project' if op in ('create_project','rename_project') else 'task'
        rows=projects if entity=='project' else tasks
        key=uuid_text(a.get(entity+'_id'))
        required={entity+'_id','name'} if op.startswith('create_') else (
            {'task_id','project_id','expected_version'} if op=='assign_task_to_project' else {entity+'_id','name','expected_version'})
        allowed=required|({'project_id','parent_task_id','expected_project_version','expected_parent_version'} if op=='create_task' else set())
        if not required<=set(a) or not set(a)<=allowed:raise ValueError('Invalid administrative fields')
        if 'name' in a and (type(a['name']) is not str or not a['name'].strip()):raise ValueError('Invalid administrative name')
        if op.startswith('create_'):
            if key in rows:raise ValueError('Duplicate administrative creation')
            parent=a.get('parent_task_id');group=a.get('project_id')
            if entity=='task':
                if parent is not None:
                    uuid_text(parent);p=version(tasks,parent,a.get('expected_parent_version'))
                    if 'project_id' in a and group!=p['project_id']:raise ValueError('Child project context differs')
                    group=p['project_id']
                elif a.get('expected_parent_version') is not None:raise ValueError('Unexpected parent review')
                if group is not None:
                    uuid_text(group)
                    if parent is None or a.get('expected_project_version') is not None:version(projects,group,a.get('expected_project_version'))
                    elif group not in projects:raise ValueError('Unknown project')
                elif a.get('expected_project_version') is not None:raise ValueError('Unassigned has no version')
            row=dict(name=a['name'].strip(),version=1,created_request_id=request_id,created_utc_us=now,updated_utc_us=now,
                     is_archived=0,archived_at_utc_us=None)
            row[entity+'_id']=key
            if entity=='task':row.update(parent_task_id=parent,project_id=group)
            rows[key]=row
        else:
            row=version(rows,key,a['expected_version'])
            if op=='assign_task_to_project':
                group=a['project_id']
                if group is not None:uuid_text(group)
                if (group is not None and group not in projects or row['parent_task_id'] is not None
                    or any(t['parent_task_id']==key for t in tasks.values()) or row['project_id']==group):
                    raise ValueError('Invalid standalone administrative assignment')
                row['project_id']=group
            else:
                if row['name']==a['name'].strip():raise ValueError('No-op administrative rename')
                row['name']=a['name'].strip()
            row['version']+=1;row['updated_utc_us']=now
        if canonical(result)!=canonical({entity+'_id':key,'version':rows[key]['version']}):
            raise ValueError('Administrative result/version differs')
        task_paths(list(tasks.values()))
    for table,rows,key in (('projects',projects,'project_id'),('tasks',tasks,'task_id')):
        actual={r[key]:dict(r) for r in c.execute(f'SELECT * FROM {table}')}
        if set(actual)!=set(rows):raise ValueError('Administrative creation/survivor coverage differs')
        for identity,row in rows.items():
            # Current archive metadata is validated separately; no historical archive
            # operations exist yet, and B2 never changes these fields.
            for field,value in row.items():
                if field not in ('is_archived','archived_at_utc_us') and actual[identity][field]!=value:
                    raise ValueError('Current administrative effects differ')
