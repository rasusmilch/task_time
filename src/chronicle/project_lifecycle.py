"""Current lifecycle operations on one caller-owned transaction."""
from .hierarchy import task_observations
from . import schema
from .hierarchy import ProjectForest, task_paths, active_in_project_subtree, _active
from .project_services import _facts
from .records import Request, StaleState, uuid_text, integer
from .timekeeping import instant
OPERATIONS = frozenset(('archive_project', 'unarchive_project', 'archive_task', 'unarchive_task'))

def transition(operation, arguments, action_utc_us, tasks, projects, active):
    """Authoritative pure selected-row transition, independent of history replay."""
    if operation not in OPERATIONS:
        raise ValueError('Unknown current lifecycle operation')
    entity = 'project' if operation.endswith('_project') else 'task'
    field = entity + '_id'
    if type(arguments) is not dict or set(arguments) != {field, 'expected_version'}:
        raise ValueError('Lifecycle requires exact identity and expected_version')
    key = uuid_text(arguments[field])
    version = integer(arguments['expected_version'], 'Reviewed version', 1, 2 ** 63 - 1)
    instant(action_utc_us)
    ProjectForest(projects)
    observations = task_observations(tasks, projects)
    _active(observations, active)
    selected = next((r for r in (projects if entity == 'project' else tasks) if r[field] == key), None)
    if selected is None or selected['version'] != version:
        raise StaleState('Reviewed lifecycle identity/version changed')
    archived = int(operation.startswith('archive_'))
    if selected['is_archived'] == archived:
        return None
    if archived and active is not None:
        contains = active_in_project_subtree(tasks, projects, active, key) if entity == 'project' else key in task_paths(tasks)[active['task_id']]
        if contains:
            raise StaleState('Archive refuses a subtree containing the running timer')
    return dict(selected, is_archived=archived, archived_at_utc_us=action_utc_us if archived else None, version=integer(version + 1, 'Lifecycle version', 1, 2 ** 63 - 1), updated_utc_us=action_utc_us)

def apply_lifecycle_operation(c, request: Request, dataset_id: str):
    """Return exact result or None; caller owns receipts, final verification/rollback.

    Full protected recording/reporting admission remains outside this service's
    structural scope. The SQLiteStore transaction owner must enforce that boundary.
    """
    request.content()
    if not c.in_transaction:
        raise ValueError('Explicit dataset identity and owned transaction required')
    schema.verify_structure(c)
    if request.dataset_id != dataset_id or request.dataset_id != c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0]:
        raise ValueError('Wrong dataset')
    if c.execute('SELECT 1 FROM committed_requests WHERE request_id=?', (request.request_id,)).fetchone():
        raise ValueError('Transaction owner must resolve committed requests first')
    before = _facts(c)
    active_rows = before['active_timer']
    changed = transition(request.operation, request.args(), request.action_utc_us, before['tasks'], before['projects'], active_rows[0] if active_rows else None)
    if changed is None:
        return None
    entity = 'project' if request.operation.endswith('_project') else 'task'
    table, field = (entity + 's', entity + '_id')
    expected = dict(before)
    expected[table] = sorted([changed if r[field] == changed[field] else r for r in before[table]], key=repr)
    cursor = c.execute(f'UPDATE {table} SET is_archived=?,archived_at_utc_us=?,version=?,updated_utc_us=? WHERE {field}=?', (changed['is_archived'], changed['archived_at_utc_us'], changed['version'], changed['updated_utc_us'], changed[field]))
    if cursor.rowcount != 1 or _facts(c) != expected:
        raise ValueError('Installed lifecycle differs from complete expected facts')
    schema.verify_structure(c)
    return {field: changed[field], 'version': changed['version']}
