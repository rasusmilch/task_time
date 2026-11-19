"""Bounded derived observations of authoritative task adjacency; never cached."""
MAX_TASK_LEVELS = 3

def task_paths(tasks):
    """Reconstruct each path with mandatory real-project membership."""
    from .records import uuid_text
    for task in tasks:
        uuid_text(task['project_id'])
    known = {t['task_id']: t for t in tasks}
    if len(known) != len(tasks):
        raise ValueError('Duplicate task identity in forest')
    paths = {}
    for key, task in known.items():
        path, cursor = ([], key)
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

class ProjectForest:
    """Immutable, detached project observation; paths are built only on demand.

    Every current task belongs to one real node of this forest.
    All edges are visited once during construction, including disconnected cycles.
    """
    __slots__ = ('parents', 'children', 'roots', 'root_membership', 'order', 'reverse_order', 'effective_archived', '_sealed')

    def __setattr__(self, name, value):
        if getattr(self, '_sealed', False):
            raise AttributeError('Project forest observations are immutable')
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise AttributeError('Project forest observations are immutable')

    def __init__(self, projects):
        from types import MappingProxyType
        from .records import uuid_text, integer
        parents, archived = ({}, {})
        for row in projects:
            key = uuid_text(row['project_id'])
            parent = row['parent_project_id']
            if parent is not None:
                uuid_text(parent)
            if key in parents:
                raise ValueError('Duplicate project identity')
            if key == parent:
                raise ValueError('Project cannot parent itself')
            parents[key] = parent
            archived[key] = integer(row['is_archived'], 'Project archive flag', 0, 1)
        children = {key: [] for key in parents}
        roots = []
        for key, parent in parents.items():
            if parent is None:
                roots.append(key)
            elif parent not in parents:
                raise ValueError('Missing project parent')
            else:
                children[parent].append(key)
        children = {key: tuple(sorted(values)) for key, values in children.items()}
        roots = tuple(sorted(roots))
        stack, order, effective, membership = (list(reversed(roots)), [], {}, {})
        while stack:
            key = stack.pop()
            if key in effective or len(order) >= len(parents):
                raise ValueError('Invalid project forest coverage')
            parent = parents[key]
            effective[key] = bool(archived[key] or (parent is not None and effective[parent]))
            membership[key] = key if parent is None else membership[parent]
            order.append(key)
            stack.extend(reversed(children[key]))
        if len(order) != len(parents):
            raise ValueError('Project forest contains a cycle')
        self.parents = MappingProxyType(parents)
        self.children = MappingProxyType(children)
        self.roots = roots
        self.root_membership = MappingProxyType(membership)
        self.order = tuple(order)
        self.reverse_order = tuple(reversed(order))
        self.effective_archived = MappingProxyType(effective)
        self._sealed = True

    def ancestry(self, project_id):
        """Complete root-to-node path, including the requested project."""
        if project_id not in self.parents:
            raise ValueError('Unknown project identity')
        path, cursor = ([], project_id)
        while cursor is not None:
            if len(path) >= len(self.parents):
                raise ValueError('Project ancestry did not complete')
            path.append(cursor)
            cursor = self.parents[cursor]
        return tuple(reversed(path))

    def descendants(self, project_id):
        """Complete parent-first closure, including the requested project."""
        if project_id not in self.parents:
            raise ValueError('Unknown project identity')
        stack, values, visited = ([project_id], [], set())
        while stack:
            key = stack.pop()
            if key in visited or len(visited) >= len(self.parents):
                raise ValueError('Project descendant traversal did not complete')
            visited.add(key)
            values.append(key)
            stack.extend(reversed(self.children[key]))
        return tuple(values)

def task_observations(tasks, projects):
    """Current-only observations; task depth still counts task edges alone."""
    from .records import uuid_text, integer
    forest = ProjectForest(projects)
    for task in tasks:
        uuid_text(task['task_id'])
        uuid_text(task['project_id'])
        integer(task['is_archived'], 'Task archive flag', 0, 1)
        for field in ('parent_task_id', 'project_id'):
            if task[field] is not None:
                uuid_text(task[field])
    known = {t['task_id']: t for t in tasks}
    paths = task_paths(tasks)
    parents = {t['parent_task_id'] for t in tasks if t['parent_task_id'] is not None}
    if any((t['project_id'] not in forest.parents for t in tasks)):
        raise ValueError('Task requires an existing real project')
    values = {k: dict(depth=len(paths[k]), is_leaf=k not in parents, effective_archived=any((known[a]['is_archived'] for a in paths[k]))) for k in known}
    for task in tasks:
        key, group = (task['task_id'], task['project_id'])
        value = values[key]
        project_archive = forest.effective_archived[group]
        value.update(explicit_archived=bool(task['is_archived']), ancestor_task_archived=any((known[k]['is_archived'] for k in paths[key][1:])), project_effective_archived=project_archive)
        value['effective_archived'] |= project_archive
        value['eligible_for_new_work'] = value['is_leaf'] and (not value['effective_archived'])
    return values

def _active(observations, active):
    if active is not None:
        from .records import uuid_text
        key = uuid_text(active['task_id'])
        if key not in observations or not observations[key]['eligible_for_new_work']:
            raise ValueError('Active task must be an eligible leaf')

def active_in_project_subtree(tasks, projects, active, project_id):
    """Containment includes direct tasks at every task/project level."""
    forest = ProjectForest(projects)
    scope = set(forest.descendants(project_id))
    observations = task_observations(tasks, projects)
    _active(observations, active)
    if active is None:
        return False
    task = next((t for t in tasks if t['task_id'] == active['task_id']))
    return task['project_id'] in scope


def effective_projects(projects):
    forest = ProjectForest(projects)
    return [dict(p, is_archived=int(forest.effective_archived[p['project_id']])) for p in projects]
