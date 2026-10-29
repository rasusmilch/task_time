"""Bounded derived observations of authoritative task adjacency; never cached."""

MAX_TASK_LEVELS = 3


def task_paths(tasks):
    """Reconstruct every path independently, including NULL project membership."""
    known = {t['task_id']: t for t in tasks}
    if len(known) != len(tasks):
        raise ValueError('Duplicate task identity in forest')
    paths = {}
    for key, task in known.items():
        path, cursor = [], key
        while cursor is not None:
            if cursor not in known:
                raise ValueError('Missing task parent in forest')
            if cursor in path:
                raise ValueError('Task forest contains a cycle')
            if len(path) == MAX_TASK_LEVELS:
                raise ValueError('Task forest exceeds three levels')
            ancestor = known[cursor]
            if ancestor.get('project_id') != task.get('project_id'):
                raise ValueError('Task forest crosses project membership')
            path.append(cursor)
            cursor = ancestor.get('parent_task_id')
        paths[key] = tuple(path)
    return paths


def task_observations(tasks, projects):
    """Detached depth/eligibility only, derived afresh from one read snapshot."""
    paths = task_paths(tasks)
    known = {t['task_id']: t for t in tasks}
    groups = {p['project_id']: p for p in projects}
    parents = {t['parent_task_id'] for t in tasks if t['parent_task_id'] is not None}
    result = {}
    for task in tasks:
        key, group = task['task_id'], task['project_id']
        if group is not None and group not in groups:
            raise ValueError('Task has no owning project')
        archived = bool(group is not None and groups[group]['is_archived']) or any(
            known[a]['is_archived'] for a in paths[key])
        result[key] = dict(depth=len(paths[key]), is_leaf=key not in parents,
                           effective_archived=archived)
    return result
