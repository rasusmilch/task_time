"""Isolated version-5 service boundary on an active caller-owned transaction.

The owner issues BEGIN IMMEDIATE, resolves receipts, commits/rolls back and handles
uncertainty. Services check active transaction/identity, never the original BEGIN
mode. No opener, transaction coordinator, worker or ordinary readiness lives here.
"""
from .project_services import CandidateProjectContext
from .schema4_tasks import check
from .schema4_services import _dispatch_operation
from .schema4_evidence import Rows
from .schema5_evidence import verify_transaction
from .records import Request, uuid_text


def admit(c, request, context):
    if type(context) is not CandidateProjectContext or context.schema_version != 5:
        raise ValueError('Schema-5 service requires an explicit version-5 context')
    if not isinstance(request, Request):
        raise ValueError('A canonical immutable Request is required')
    check(c, request, context)
    verify_transaction(c)


def validate_export(c, candidate):
    """Reviewed ownership at registration; existing frozen math stays authoritative."""
    from .timesheet import from_content
    value = from_content(candidate)
    tasks = {r['task_id']: r for r in Rows(c).execute('SELECT * FROM tasks')}
    projects = {r[0] for r in c.execute('SELECT project_id FROM projects')}
    if value.scope_kind == 'all' and {t.task_id for t in value.tasks} != set(tasks):
        raise ValueError('Frozen All scope must contain every reviewed task')
    for task in value.tasks:
        uuid_text(task.project_id)
        if (task.task_id not in tasks or task.project_id not in projects
                or tasks[task.task_id]['project_id'] != task.project_id):
            raise ValueError('Frozen task/project differs at registration')


def apply_operation(c, request, context):
    """Apply a new non-Delete Request; return canonical result or None unchanged."""
    admit(c, request, context)
    if request.operation in ('delete_task', 'delete_project', 'delete_template'):
        raise ValueError('Delete requires its separate no-receipt path')
    if request.operation == 'register_timesheet_export':
        validate_export(c, request.args().get('candidate'))
    return _dispatch_operation(c, request, context)


def preview_delete(c, context, entity, identity):
    if type(context) is not CandidateProjectContext or context.schema_version != 5:
        raise ValueError('Schema-5 Delete requires an explicit version-5 context')
    from .schema4_delete import preview
    return preview(c, context, entity, identity)


def apply_delete(c, request, context):
    admit(c, request, context)
    from .schema4_delete import apply_delete as shared_delete
    return shared_delete(c, request, context)
