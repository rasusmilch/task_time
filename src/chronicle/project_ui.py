"""Pure schema-4 display/review projections; no storage, clocks or UI owner."""
from copy import deepcopy

from .hierarchy import ProjectForest, candidate_task_observations, task_paths
from .timekeeping import format_duration, from_us


UNASSIGNED = 'group:unassigned'


def project_row(key):
    return 'project:' + key if key is not None else UNASSIGNED


def task_row(key):
    return 'task:' + key


def context(state):
    projects = {p['project_id']: p for p in state['projects']}
    tasks = {t['task_id']: t for t in state['tasks']}
    forest = ProjectForest(state['projects'])
    observations = candidate_task_observations(state['tasks'], state['projects'])
    return projects, tasks, forest, observations


def ancestry(state, key):
    projects, _, forest, _ = context(state)
    return [dict(project_id=k, expected_version=projects[k]['version'],
                 parent_project_id=projects[k]['parent_project_id'])
            for k in (() if key is None else forest.ancestry(key))]


def path_label(state, entity, key):
    projects, tasks, forest, _ = context(state)
    group = key if entity == 'project' else tasks[key]['project_id']
    pieces = ([f"{projects[k]['name']} ({k})" for k in forest.ancestry(group)]
              if group is not None else ['Unassigned'])
    if entity == 'task':
        pieces += [f"{tasks[k]['name']} ({k})" for k in reversed(task_paths(state['tasks'])[key])]
    return ' → '.join(pieces)


def ordered(rows, mode=None):
    children = {'': []}
    for key, row in rows.items():
        if row['parent'] and row['parent'] not in rows:
            raise ValueError('Incomplete presentation ancestry')
        children.setdefault(row['parent'], []).append(key)
        children.setdefault(key, [])
    for siblings in children.values():
        if mode == 'alpha':
            siblings.sort(key=lambda k: (rows[k]['text'].casefold(), k))
        elif mode is not None:
            # Stable UUID ties, including equal local dates during DST folds.
            siblings.sort(key=lambda k: (k.split(':', 1)[1], k))
            if mode.startswith('Name'):
                siblings.sort(key=lambda k: rows[k]['text'].casefold(), reverse='Z to A' in mode)
            else:
                dated = [k for k in siblings if rows[k]['stamp'] is not None]
                undated = [k for k in siblings if rows[k]['stamp'] is None]
                dated.sort(key=lambda k: rows[k]['stamp'], reverse='Newest' in mode)
                siblings[:] = undated + dated
    return children


def installation_order(children):
    """Parent-first order at arbitrary project depth, with complete coverage."""
    seen = set()
    stack = list(reversed(children['']))
    while stack:
        key = stack.pop()
        if key in seen:
            raise ValueError('Cyclic or duplicate presentation row')
        seen.add(key)
        yield key
        stack.extend(reversed(children[key]))
    if seen != set(children) - {''}:
        raise ValueError('Unreachable presentation rows')


def main_projection(state, alpha=False, period='Today'):
    projects, tasks, forest, observations = context(state)
    report = state['report']
    field = 'today_us' if period == 'Today' else 'week_us'
    active = state['active']; active_id = active['task_id'] if active else None
    paths = task_paths(state['tasks'])
    active_projects = set(forest.ancestry(tasks[active_id]['project_id'])) if active and tasks[active_id]['project_id'] is not None else set()
    rows = {}
    def amount(group, key):
        return format_duration(report[group][key][field]) if report is not None else '—'
    for key in forest.order:
        p = projects[key]
        if forest.effective_archived[key]:
            continue
        rows[project_row(key)] = dict(parent=project_row(p['parent_project_id']) if p['parent_project_id'] else '',
            text=p['name'], values=('Group — Running descendant' if key in active_projects else 'Group', '—', amount('projects', key)), tags=())
    rows[UNASSIGNED] = dict(parent='', text='Unassigned', values=(
        'Group — Running task' if active and tasks[active_id]['project_id'] is None else 'Group', '—', amount('projects', None)), tags=())
    for key, t in tasks.items():
        obs = observations[key]
        if obs['effective_archived']:
            continue
        running = key == active_id
        descendant = active is not None and key in paths[active_id][1:]
        status = ('▶ Running' if running else '▶ Running descendant' if descendant else
                  '■ Stopped' if obs['is_leaf'] else 'Parent — Stopped')
        rows[task_row(key)] = dict(parent=task_row(t['parent_task_id']) if t['parent_task_id'] else project_row(t['project_id']),
            text=t['name'], values=(status, amount('individual', key), amount('cumulative', key)),
            tags=('running' if running or descendant else 'stopped',))
    active_path = None
    if active:
        group = tasks[active_id]['project_id']
        active_path = tuple([project_row(k) for k in forest.ancestry(group)] if group is not None else [UNASSIGNED])
        active_path += tuple(task_row(k) for k in reversed(paths[active_id]))
    return rows, ordered(rows, 'alpha' if alpha else None), active_path


def archived_projection(state, order, period, zone):
    projects, tasks, forest, observations = context(state)
    paths = task_paths(state['tasks']); sources = {}; rows = {}
    project_set = set(); task_set = set(); task_sources = {}
    # Nearest explicit project provenance, in one parent-first pass.
    for key in forest.order:
        p = projects[key]
        sources[key] = p if p['is_archived'] else sources.get(p['parent_project_id'])
        if sources[key] is not None:
            project_set.add(key)
    for key, t in tasks.items():
        source = next((tasks[a] for a in paths[key] if tasks[a]['is_archived']), sources.get(t['project_id']))
        task_sources[key] = source
        if observations[key]['effective_archived']:
            for ancestor in paths[key]:
                task_set.add(ancestor)
            if t['project_id'] is not None:
                project_set.add(t['project_id'])
    # Mark context without repeatedly materializing full paths per row.
    for key in tuple(project_set):
        parent = projects[key]['parent_project_id']
        while parent is not None and parent not in project_set:
            project_set.add(parent); parent = projects[parent]['parent_project_id']
    report = state['report']; field = 'today_us' if period == 'Today' else 'week_us'
    def add(entity, item, parent, source):
        key = item[entity + '_id']; stamp = source['archived_at_utc_us'] if source else None
        date = from_us(stamp).astimezone(zone).strftime('%Y-%m-%d %H:%M:%S.%f UTC%z') if stamp is not None else ''
        individual = format_duration(report['individual'][key][field]) if report and entity == 'task' else '—'
        cumulative = format_duration(report['projects' if entity == 'project' else 'cumulative'][key][field]) if report else '—'
        rows[entity + ':' + key] = dict(parent=parent, text=item['name'], values=(date, individual, cumulative),
            item=item, entity=entity, stamp=stamp, source=source, context=source is None)
    for key in forest.order:
        if key in project_set:
            p = projects[key]; add('project', p, project_row(p['parent_project_id']) if p['parent_project_id'] else '', sources[key])
    if any(tasks[k]['project_id'] is None for k in task_set):
        rows[UNASSIGNED] = dict(parent='', text='Unassigned', values=('', '—', '—'), item=None,
            entity='group', stamp=None, source=None, context=True)
    for key in tasks:
        if key in task_set:
            t = tasks[key]
            add('task', t, task_row(t['parent_task_id']) if t['parent_task_id'] else project_row(t['project_id']), task_sources[key])
    return rows, ordered(rows, order)


def new_task_review(state, task_id=None, project_id=None):
    projects, tasks, forest, observations = context(state)
    parent = tasks[task_id] if task_id is not None else None
    if parent:
        obs = observations[task_id]
        if obs['effective_archived'] or obs['depth'] >= 3 or state['active'] and state['active']['task_id'] == task_id:
            raise ValueError('Task parent is archived, running or at level 3')
        project_id = parent['project_id']
    if project_id is not None and forest.effective_archived[project_id]:
        raise ValueError('Project destination is effectively archived')
    return dict(project_id=project_id, parent_task_id=task_id,
        expected_parent_version=parent['version'] if parent else None,
        expected_project_version=projects[project_id]['version'] if project_id else None,
        reviewed_destination_project_ancestry=ancestry(state, project_id))


class ProjectMoveReview:
    """One detached source closure; only selection builds a destination review."""
    def __init__(self, state, source):
        self.state = deepcopy(state)
        projects, tasks, forest, _ = context(self.state)
        item = projects[source]; branch = set(forest.descendants(source))
        self.source = source; self.projects = projects; self.forest = forest
        self.base = dict(project_id=source, expected_version=item['version'], source_parent_project_id=item['parent_project_id'],
            reviewed_source_ancestry=ancestry(self.state, item['parent_project_id']),
            reviewed_projects=[dict(project_id=k, expected_version=projects[k]['version'], parent_project_id=projects[k]['parent_project_id']) for k in sorted(branch)],
            reviewed_tasks=sorted([dict(task_id=k, expected_version=t['version'], parent_task_id=t['parent_task_id'], project_id=t['project_id']) for k,t in tasks.items() if t['project_id'] in branch], key=lambda t:t['task_id']))
        self.branch = branch

    def reason(self, destination):
        if self.forest.effective_archived[self.source]:return 'Source is effectively archived'
        if destination in self.branch:return 'Self or descendant destination would create a cycle'
        if destination is not None:
            if destination not in self.projects:return 'Destination is missing'
            if self.forest.effective_archived[destination]:return 'Destination is effectively archived'
        return None

    def arguments(self, destination):
        reason = self.reason(destination)
        if reason:raise ValueError(reason)
        args = dict(deepcopy(self.base), destination_parent_project_id=destination,
            expected_destination_parent_version=self.projects[destination]['version'] if destination is not None else None,
            reviewed_destination_ancestry=ancestry(self.state, destination))
        from .administration import candidate_move_result
        candidate_move_result(self.projects, {t['task_id']:t for t in self.state['tasks']}, args)
        return args


def task_move_arguments(state, source, parent, group, members):
    from .schema4_tasks import task_move_plan
    projects, tasks, _, _ = context(state)
    item = tasks[source]
    args = dict(task_id=source, expected_version=item['version'], source_parent_task_id=item['parent_task_id'], source_project_id=item['project_id'],
        destination_parent_task_id=parent, destination_project_id=group,
        expected_destination_parent_version=tasks[parent]['version'] if parent else None,
        expected_destination_project_version=projects[group]['version'] if group else None,
        reviewed_subtree=deepcopy(members), reviewed_source_project_ancestry=ancestry(state, item['project_id']),
        reviewed_destination_project_ancestry=ancestry(state, group))
    _, result = task_move_plan(state['tasks'], state['projects'], state['active'], args)
    return args, not result['changed_tasks']


def destination_rows(state, *, project_only=False):
    """Compact forest labels, with complete paths computed only on selection."""
    projects, tasks, forest, observations = context(state); rows = {}
    root = 'group:root' if project_only else UNASSIGNED
    rows[root] = dict(parent='', text='Root' if project_only else 'Unassigned', values=('Root' if project_only else 'Virtual Unassigned',), destination=(None, None))
    for key in forest.order:
        p = projects[key]
        rows[project_row(key)] = dict(parent=project_row(p['parent_project_id']) if p['parent_project_id'] else '',
            text=p['name'], values=(key,), destination=(None, key))
    if not project_only:
        for key,t in tasks.items():
            rows[task_row(key)] = dict(parent=task_row(t['parent_task_id']) if t['parent_task_id'] else project_row(t['project_id']),
                text=t['name'], values=(key,), destination=(key,t['project_id']))
    return rows, ordered(rows)


def delete_projection(review):
    """Render the backend's complete scope; never determine Delete eligibility."""
    projects = {p['project_id']:p for p in review.get('projects', [])}
    tasks = {t['task_id']:t for t in review['tasks']}; rows = {}
    from .records import uuid_text
    if len(projects)!=len(review.get('projects', [])) or len(tasks)!=len(review['tasks']):raise ValueError('Duplicate Delete scope identity')
    for key in (*projects,*tasks):uuid_text(key)
    selected = review['entity_id']
    if review['entity_type'] == 'project':
        if selected not in projects or any(t['project_id'] not in projects for t in tasks.values()):raise ValueError('Incomplete project Delete scope')
        forest = ProjectForest([dict(p,parent_project_id=None) if key==selected else p for key,p in projects.items()])
        if set(forest.descendants(selected))!=set(projects):raise ValueError('Disconnected project Delete scope')
        task_paths(list(tasks.values()))
    elif review['entity_type'] == 'task':
        if projects or selected not in tasks:raise ValueError('Incorrect task Delete scope')
        paths = task_paths([dict(t,parent_task_id=None) if key==selected else t for key,t in tasks.items()])
        if any(selected not in path for path in paths.values()):raise ValueError('Disconnected task Delete scope')
    else:raise ValueError('Unknown structure Delete scope')
    # Scope root may retain an outside parent; only display in-scope edges.
    for key,p in projects.items():
        rows[project_row(key)] = dict(parent=project_row(p['parent_project_id']) if p['parent_project_id'] in projects else '',
            text=p['name'], values=(key,p['version'],bool(p['is_archived'])))
    for key,t in tasks.items():
        parent = task_row(t['parent_task_id']) if t['parent_task_id'] in tasks else project_row(t['project_id']) if t['project_id'] in projects else ''
        rows[task_row(key)] = dict(parent=parent,text=t['name'],values=(key,t['version'],bool(t['is_archived'])))
    return rows, ordered(rows)
