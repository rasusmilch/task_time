"""Schema-4 project operations on a caller-owned authoritative transaction.

No path, connection factory, worker, receipt coordinator or runtime registration.
The transaction owner resolves exact receipts first and must verify supported
candidate history before execution and again after inserting the new receipt.
Structural validation here is not admission of protected recording history.
"""
from dataclasses import dataclass

from . import schema_profiles as schema
from .hierarchy import ProjectForest, candidate_task_observations
from .records import Request, StaleState, canonical, integer, uuid_text
from .services import name_text


OPERATIONS = frozenset(('create_project', 'create_child_project', 'move_project_subtree'))
PROJECT_REVIEW = frozenset(('project_id', 'expected_version', 'parent_project_id'))
TASK_REVIEW = frozenset(('task_id', 'expected_version', 'parent_task_id', 'project_id'))
MOVE_FIELDS = frozenset((
    'project_id', 'expected_version', 'source_parent_project_id',
    'destination_parent_project_id', 'expected_destination_parent_version',
    'reviewed_source_ancestry', 'reviewed_destination_ancestry',
    'reviewed_projects', 'reviewed_tasks',
))


@dataclass(frozen=True)
class CandidateProjectContext:
    """Explicit isolated candidate identity; never permission for ordinary startup."""
    dataset_id: str

    def __post_init__(self):
        uuid_text(self.dataset_id)


def _facts(c):
    # Schema has already been checked: names are the exact declared tables.
    return {name: sorted(schema._rows(c, name), key=repr) for name, in c.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'")}


def _review(supplied, expected, fields):
    if type(supplied) is not list:
        raise ValueError('Complete ordered project review required')
    for row in supplied:
        if type(row) is not dict or set(row) != fields:
            raise ValueError('Incorrect reviewed member fields')
        integer(row['expected_version'], 'Reviewed version', 1, 2**63-1)
        for field in fields - {'expected_version'}:
            if row[field] is not None or field == 'task_id' or fields == PROJECT_REVIEW and field == 'project_id':
                uuid_text(row[field])
    if canonical(supplied) != canonical(expected):
        raise StaleState('Reviewed coverage, relationships or versions changed')


def _ancestry(forest, projects, parent):
    return [dict(project_id=k, expected_version=projects[k]['version'],
                 parent_project_id=projects[k]['parent_project_id'])
            for k in (() if parent is None else forest.ancestry(parent))]


def _version(projects, key, expected):
    integer(expected, 'Reviewed project version', 1, 2**63-1)
    if key not in projects or projects[key]['version'] != expected:
        raise StaleState('Reviewed project identity/version changed')
    return projects[key]


def apply_project_operation(c, request: Request, context: CandidateProjectContext):
    """Apply one new operation; return canonical result dict, or None for no-op.

    Requires an already owned transaction and an exact schema-4 connection.
    The caller owns rollback on *any* exception, including post-write verification
    failure. This function never commits, rolls back, opens or closes a connection.
    Receipt insertion and full supported chronological verification remain the
    caller's responsibility, including deferred creation receipt references.
    """
    request.content()
    if type(context) is not CandidateProjectContext or not c.in_transaction:
        raise ValueError('Explicit candidate context and owned transaction required')
    schema.verify_structure(c)
    if (request.dataset_id != context.dataset_id or request.dataset_id !=
            c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0]):
        raise ValueError('Wrong candidate dataset')
    if request.operation not in OPERATIONS:
        raise ValueError('Unsupported candidate project operation')
    if c.execute('SELECT 1 FROM committed_requests WHERE request_id=?',
                 (request.request_id,)).fetchone():
        raise ValueError('Transaction owner must resolve committed requests first')
    before = _facts(c)
    projects = {r['project_id']: dict(r) for r in before['projects']}
    tasks = before['tasks']
    forest = ProjectForest(list(projects.values()))
    candidate_task_observations(tasks, list(projects.values()))
    a, now, op = request.args(), request.action_utc_us, request.operation
    if op in ('create_project', 'create_child_project'):
        fields = {'project_id', 'name'}
        if op == 'create_child_project':
            fields |= {'parent_project_id', 'expected_parent_version', 'reviewed_parent_ancestry'}
        if set(a) != fields:
            raise ValueError('Incorrect project creation fields')
        key, name = uuid_text(a['project_id']), name_text(a['name'])
        if key in projects:
            raise ValueError('Project identity already exists')
        parent = None
        if op == 'create_child_project':
            parent = uuid_text(a['parent_project_id'])
            _version(projects, parent, a['expected_parent_version'])
            _review(a['reviewed_parent_ancestry'], _ancestry(forest, projects, parent), PROJECT_REVIEW)
            if forest.effective_archived[parent]:
                raise StaleState('Child destination is effectively archived')
        row = dict(project_id=key, parent_project_id=parent, name=name, version=1,
                   is_archived=0, archived_at_utc_us=None, created_request_id=request.request_id,
                   created_utc_us=now, updated_utc_us=now)
        projects[key] = row
        result = dict(project_id=key, version=1)
    else:
        if set(a) != MOVE_FIELDS:
            raise ValueError('Incorrect project movement fields')
        key = uuid_text(a['project_id'])
        for field in ('source_parent_project_id', 'destination_parent_project_id'):
            if a[field] is not None:
                uuid_text(a[field])
        source = _version(projects, key, a['expected_version'])
        if source['parent_project_id'] != a['source_parent_project_id']:
            raise StaleState('Reviewed source parent changed')
        destination = a['destination_parent_project_id']
        if destination is None:
            if a['expected_destination_parent_version'] is not None:
                raise ValueError('Root destination has no version')
        else:
            _version(projects, destination, a['expected_destination_parent_version'])
        _review(a['reviewed_source_ancestry'],
                _ancestry(forest, projects, source['parent_project_id']), PROJECT_REVIEW)
        _review(a['reviewed_destination_ancestry'],
                _ancestry(forest, projects, destination), PROJECT_REVIEW)
        branch = set(forest.descendants(key))
        _review(a['reviewed_projects'], [dict(project_id=k,
                expected_version=projects[k]['version'], parent_project_id=projects[k]['parent_project_id'])
                for k in sorted(branch)], PROJECT_REVIEW)
        _review(a['reviewed_tasks'], sorted([dict(task_id=t['task_id'], expected_version=t['version'],
                parent_task_id=t['parent_task_id'], project_id=t['project_id'])
                for t in tasks if t['project_id'] in branch], key=lambda t: t['task_id']), TASK_REVIEW)
        if destination in branch:
            raise ValueError('Project movement would create a cycle')
        if forest.effective_archived[key] or destination is not None and forest.effective_archived[destination]:
            raise StaleState('Project movement context is effectively archived')
        if source['parent_project_id'] == destination:
            return None  # Only after the entire review and eligibility validation.
        source.update(parent_project_id=destination,
                      version=integer(source['version']+1, 'Moved version', 1, 2**63-1),
                      updated_utc_us=now)
        result = dict(project_id=key, version=source['version'], parent_project_id=destination)

    # Validate the complete proposed forest/active eligibility before writing.
    ProjectForest(list(projects.values()))
    observations = candidate_task_observations(tasks, list(projects.values()))
    for task, in c.execute('SELECT task_id FROM active_timer'):
        if not observations[task]['is_leaf'] or observations[task]['effective_archived']:
            raise ValueError('Project operation would make active work ineligible')
    expected = dict(before, projects=sorted(projects.values(), key=repr))
    if op == 'move_project_subtree':
        changed = c.execute('UPDATE projects SET parent_project_id=?,version=?,updated_utc_us=? WHERE project_id=?',
                            (destination, result['version'], now, key))
    else:
        columns = tuple(row)
        changed = c.execute('INSERT INTO projects ('+','.join(columns)+') VALUES ('+
                            ','.join('?' for _ in columns)+')', tuple(row.values()))
    if changed.rowcount != 1 or _facts(c) != expected:
        raise ValueError('Installed project operation differs from complete expected facts')
    return result
