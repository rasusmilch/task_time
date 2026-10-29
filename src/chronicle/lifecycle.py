"""Selected-node archive validation over detached authoritative observations."""

from .hierarchy import task_paths
from .records import StaleState, integer, uuid_text
from .timekeeping import instant


OPERATIONS = frozenset(('archive_project', 'unarchive_project', 'archive_task', 'unarchive_task'))


def transition(operation, arguments, action_utc_us, tasks, projects, active):
    """Return the one changed row, or None for a reviewed explicit-state no-op."""
    if operation not in OPERATIONS:
        raise ValueError('Unknown archive operation')
    entity = 'project' if operation.endswith('_project') else 'task'
    field = entity + '_id'
    if set(arguments) != {field, 'expected_version'}:
        raise ValueError('Archive requires exactly entity UUID and expected_version')
    key = uuid_text(arguments[field])
    version = integer(arguments['expected_version'], 'Reviewed version', 1, 2**63 - 1)
    instant(action_utc_us)
    row = next((r for r in (projects if entity == 'project' else tasks) if r[field] == key), None)
    if row is None or row['version'] != version:
        raise StaleState('Reviewed archive identity/version changed')
    archived = int(operation.startswith('archive_'))
    if row['is_archived'] == archived:
        return None
    if archived and active:
        contains = (next(t for t in tasks if t['task_id'] == active['task_id'])['project_id'] == key
                    if entity == 'project' else key in task_paths(tasks)[active['task_id']])
        if contains:
            raise StaleState('Archive refuses a branch containing the running timer; Stop explicitly first')
    return dict(row, is_archived=archived, archived_at_utc_us=action_utc_us if archived else None,
                version=integer(version + 1, 'New version', 1, 2**63 - 1), updated_utc_us=action_utc_us)
