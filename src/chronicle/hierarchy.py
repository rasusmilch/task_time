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


class ProjectForest:
    """Immutable, detached candidate observation; paths are built only on demand.

    Ordinary schema-3 task observations above deliberately do not use this model.
    All edges are visited once during construction, including disconnected cycles.
    """

    __slots__ = ('parents', 'children', 'roots', 'root_membership', 'order',
                 'reverse_order', 'effective_archived', '_sealed')

    def __setattr__(self, name, value):
        if getattr(self, '_sealed', False):
            raise AttributeError('Project forest observations are immutable')
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise AttributeError('Project forest observations are immutable')

    def __init__(self, projects):
        from types import MappingProxyType
        from .records import uuid_text, integer
        parents, archived = {}, {}
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
        stack, order, effective, membership = list(reversed(roots)), [], {}, {}
        while stack:
            key = stack.pop()
            if key in effective or len(order) >= len(parents):
                raise ValueError('Invalid project forest coverage')
            parent = parents[key]
            effective[key] = bool(archived[key] or parent is not None and effective[parent])
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
        path, cursor = [], project_id
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
        stack, values, visited = [project_id], [], set()
        while stack:
            key = stack.pop()
            if key in visited or len(visited) >= len(self.parents):
                raise ValueError('Project descendant traversal did not complete')
            visited.add(key)
            values.append(key)
            stack.extend(reversed(self.children[key]))
        return tuple(values)


def candidate_task_observations(tasks, projects):
    """Schema-4-only observations; task depth still counts task edges alone."""
    from .records import uuid_text
    forest = ProjectForest(projects)
    for task in tasks:
        uuid_text(task['task_id'])
        for field in ('parent_task_id', 'project_id'):
            if task[field] is not None:
                uuid_text(task[field])
    values = task_observations(tasks, projects)
    for task in tasks:
        group = task['project_id']
        if group is not None:
            values[task['task_id']]['effective_archived'] |= forest.effective_archived[group]
    return values
