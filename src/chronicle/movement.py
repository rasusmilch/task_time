"""Typed subtree movement planning over detached transaction observations."""
from copy import deepcopy

from .hierarchy import task_paths, task_observations
from .records import uuid_text, integer, StaleState

FIELDS = frozenset(('task_id','expected_version','source_parent_task_id','source_project_id',
                    'destination_parent_task_id','destination_project_id',
                    'expected_destination_parent_version','expected_destination_project_version','reviewed_subtree'))
MEMBER_FIELDS = frozenset(('task_id','expected_version','parent_task_id','project_id'))


def snapshot(tasks, root):
    paths = task_paths(tasks)
    return sorted((dict(task_id=t['task_id'],expected_version=t['version'],
                        parent_task_id=t['parent_task_id'],project_id=t['project_id'])
                   for t in tasks if root in paths[t['task_id']]), key=lambda r:r['task_id'])


def plan(tasks, projects, active, args):
    if set(args)!=FIELDS: raise ValueError('Move requires exact frozen fields')
    for key in ('task_id','source_parent_task_id','source_project_id','destination_parent_task_id','destination_project_id'):
        if args[key] is not None or key=='task_id': uuid_text(args[key])
    integer(args['expected_version'],'Root version',1,2**63-1)
    reviewed=args['reviewed_subtree']
    if type(reviewed) is not list or not reviewed: raise ValueError('Complete reviewed subtree required')
    for row in reviewed:
        if type(row) is not dict or set(row)!=MEMBER_FIELDS: raise ValueError('Invalid subtree member')
        uuid_text(row['task_id']);integer(row['expected_version'],'Member version',1,2**63-1)
        for key in ('parent_task_id','project_id'):
            if row[key] is not None:uuid_text(row[key])
    if [r['task_id'] for r in reviewed]!=sorted({r['task_id'] for r in reviewed}):
        raise ValueError('Subtree must be uniquely UUID-sorted')
    known={t['task_id']:t for t in tasks};groups={p['project_id']:p for p in projects}
    root=known.get(args['task_id'])
    if root is None:raise StaleState('Source task missing')
    if (root['version'],root['parent_task_id'],root['project_id'])!=(args['expected_version'],args['source_parent_task_id'],args['source_project_id']):
        raise StaleState('Reviewed source changed')
    members=snapshot(tasks,root['task_id'])
    if members!=reviewed:raise StaleState('Reviewed subtree membership or versions changed')
    branch={r['task_id'] for r in members}
    parent=args['destination_parent_task_id'];group=args['destination_project_id']
    for key,version,rows in ((parent,args['expected_destination_parent_version'],known),
                             (group,args['expected_destination_project_version'],groups)):
        if key is None:
            if version is not None:raise ValueError('Absent destination has no version')
        else:
            integer(version,'Destination version',1,2**63-1)
            if key not in rows or rows[key]['version']!=version:raise StaleState('Reviewed destination changed')
    if parent in branch:raise ValueError('Destination is in moving subtree')
    if parent is not None and known[parent]['project_id']!=group:raise ValueError('Destination parent/project disagree')
    observations=task_observations(tasks,projects)
    if observations[root['task_id']]['effective_archived']:raise StaleState('Source effectively archived')
    if group is not None and groups[group]['is_archived']:raise StaleState('Destination project archived')
    if parent is not None and observations[parent]['effective_archived']:raise StaleState('Destination parent archived')
    if active and active['task_id']==parent:raise StaleState('Running destination cannot become parent')
    final=deepcopy(tasks);changed=[]
    for row in final:
        if row['task_id'] not in branch:continue
        new_parent=parent if row['task_id']==root['task_id'] else row['parent_task_id']
        if (row['parent_task_id'],row['project_id'])!=(new_parent,group):
            row['parent_task_id'],row['project_id']=new_parent,group
            row['version']=integer(row['version']+1,'Changed version',1,2**63-1)
            changed.append(dict(task_id=row['task_id'],version=row['version']))
    after=task_observations(final,projects)
    if active:
        value=after[active['task_id']]
        if not value['is_leaf'] or value['effective_archived']:raise ValueError('Move makes active task ineligible')
    return final,dict(task_id=root['task_id'],changed_tasks=sorted(changed,key=lambda r:r['task_id']))
