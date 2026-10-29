"""Finite unused-entity dependency review. No persisted deletion authority."""

import json

from .administration import verify_records
from .hierarchy import task_paths, task_observations
from .templates import from_facts
from .records import Request, canonical, integer, uuid_text, StaleState

OPERATIONS = frozenset(('delete_task', 'delete_project', 'delete_template'))
PROJECT_ADMIN = frozenset(('create_project', 'rename_project', 'archive_project', 'unarchive_project'))
TASK_ADMIN = frozenset(('create_task', 'rename_task', 'assign_task_to_project', 'archive_task', 'unarchive_task'))
RETIRE_OPERATIONS = PROJECT_ADMIN | TASK_ADMIN | {'move_task_branch'}
WORK_OPERATIONS = frozenset(('start_timer','stop_timer','switch_timer','correct_active_start',
    'add_timed_work','add_date_only_work','edit_closed_timed_work','edit_date_only_work','delete_work_entry'))


def capture(c):
    """Complete logical transaction observations, including immutable byte contents."""
    return {name: sorted((dict(r) for r in c.execute(f'SELECT * FROM {name}')), key=repr)
            for name, in c.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")}


def receipts(facts):
    for row in sorted(facts['committed_requests'], key=lambda r:r['commit_seq']):
        content = json.loads(row['request_bytes'])
        request = Request.make(row['request_id'], content['dataset_id'], content['operation'],
                               content['action_utc_us'], **content['arguments'])
        if request.content() != row['request_bytes'] or canonical(json.loads(row['result_bytes'])) != row['result_bytes']:
            raise ValueError('Invalid canonical deletion dependency receipt')
        yield row, request, json.loads(row['result_bytes'])


def protected_references(request, facts):
    """Typed UUID references only; names, comments and arbitrary strings are never keys."""
    a, op = request.args(), request.operation
    tasks, projects = set(), set()
    if op in WORK_OPERATIONS:
        for field in ('task_id', 'next_task_id'):
            if a.get(field) is not None: tasks.add(uuid_text(a[field]))
        entries = {r['entry_id']:r['task_id'] for r in facts['work_entries']}
        for field in ('entry_id', 'expected_active_entry_id'):
            if a.get(field) in entries: tasks.add(entries[a[field]])
    elif op == 'register_timesheet_export':
        from .timesheet import from_content
        candidate = from_content(a['candidate'])
        tasks.update(t.task_id for t in candidate.tasks)
        projects.update(t.project_id for t in candidate.tasks if t.project_id is not None)
        tasks.update(candidate.selected_task_ids)
        tasks.update(r.task_id for r in candidate.basis)
        tasks.update(r.task_id for r in candidate.cells)
    elif op == 'confirm_polr_absolute':
        for field in ('reviewed_rows', 'selected_keys', 'manual_cells', 'acknowledgements'):
            tasks.update(uuid_text(r['task_id']) for r in a[field])
        metadata = a['source_metadata']
        if metadata is not None:
            tasks.update(uuid_text(t) for t in metadata['selected_task_ids'])
            tasks.update(uuid_text(t['task_id']) for t in metadata['source_tasks'])
            projects.update(uuid_text(t['project_id']) for t in metadata['source_tasks'] if t['project_id'] is not None)
    elif op not in ('set_week_start', 'dismiss_polr_reminder_today'):
        raise ValueError('Unclassified protected deletion dependency: ' + op)
    return tasks, projects


def survivors(facts, task_ids, project_ids, request_ids):
    return {table: [row for row in rows if not (
        table == 'tasks' and row['task_id'] in task_ids or
        table == 'projects' and row['project_id'] in project_ids or
        table == 'committed_requests' and row['request_id'] in request_ids)]
        for table, rows in facts.items()}


def preview(facts, entity, key):
    if entity == 'template':return template_preview(facts,key)
    if entity not in ('project', 'task'): raise ValueError('Delete requires project or task identity')
    uuid_text(key)
    tasks, projects = facts['tasks'], facts['projects']
    known = {t['task_id']:t for t in tasks}; groups = {p['project_id']:p for p in projects}
    selected = (groups if entity == 'project' else known).get(key)
    if selected is None: raise StaleState('Delete target is absent; absence does not prove a previous Delete')
    paths = task_paths(tasks)
    scope = {t['task_id'] for t in tasks if (t['project_id'] == key if entity == 'project' else key in paths[t['task_id']])}
    project_ids = {key} if entity == 'project' else set()
    reasons = []
    def block(reason):
        if reason not in reasons: reasons.append(reason)
    # Relational references independently block even zero-valued frozen/confirmation facts.
    for table in ('work_entries', 'active_timer', 'timesheet_export_tasks', 'timesheet_export_week_basis',
                  'timesheet_export_cells', 'polr_confirmation_cells', 'polr_confirmed_current'):
        if any(r['task_id'] in scope or table == 'timesheet_export_tasks' and r['project_id'] in project_ids
               for r in facts[table]): block('Protected relationship: ' + table)
    work_ids = {r['entry_id'] for r in facts['work_entries'] if r['task_id'] in scope}
    for table in ('work_revisions', 'active_start_corrections'):
        if any(r['entry_id'] in work_ids for r in facts[table]): block('Protected relationship: ' + table)
    ordered = list(receipts(facts)); retire = []
    for row, request, result in ordered:
        op, a = request.operation, request.args()
        if row['receipt_class'] == 'protected':
            refs, project_refs = protected_references(request, facts)
            if refs & scope or project_refs & project_ids:
                block('Protected request reference: ' + request.request_id + ' (' + op + ')')
            continue
        from .templates import MANAGEMENT
        if row['receipt_class']=='administrative' and op in MANAGEMENT:continue
        if row['receipt_class'] != 'administrative' or op not in RETIRE_OPERATIONS | {'apply_template'}:
            raise ValueError('Unclassified administrative deletion dependency')
        if op == 'apply_template':
            members={r['task_id'] for r in result['created_tasks']}
            relevant=bool(members & scope);owned=relevant and members<=scope
            if relevant and not owned:block('Apply receipt spans surviving tasks: '+request.request_id)
        elif op in PROJECT_ADMIN:
            owned = a['project_id'] in project_ids
        elif op in TASK_ADMIN:
            owned = a['task_id'] in scope
        else:
            members = {r['task_id'] for r in a['reviewed_subtree']}
            changed = {r['task_id'] for r in result['changed_tasks']}
            relevant = bool((members | changed) & scope)
            owned = relevant and members <= scope and changed <= scope
            if relevant and not owned: block('Movement receipt spans surviving tasks: ' + request.request_id)
        if owned:
            retire.append(dict(request_id=request.request_id, commit_seq=row['commit_seq'], operation=op,
                               receipt_class=row['receipt_class'], action_utc_us=row['action_utc_us'],
                               request_content=row['request_bytes'].decode('utf-8'),
                               result_content=row['result_bytes'].decode('utf-8')))
    retired = {r['request_id'] for r in retire}
    remaining = survivors(facts, scope, project_ids, retired)
    try:
        verify_records(remaining['projects'], remaining['tasks'],
                       [(r['request_id'], request, result) for r, request, result in ordered if r['request_id'] not in retired],
                       from_facts(remaining))
    except (ValueError, KeyError, StopIteration) as exc:
        block('Surviving administrative history requires retained dependencies: ' + str(exc))
    observations = task_observations(tasks, projects)
    context_tasks = [known[a] for a in paths[key][1:]] if entity == 'task' else []
    group = groups.get(selected['project_id']) if entity == 'task' else None
    review = dict(dataset_id=facts['dataset_meta'][0]['dataset_id'], entity_type=entity, entity_id=key,
                  selected=dict(selected), effective_archived=bool(selected['is_archived']) if entity == 'project' else observations[key]['effective_archived'],
                  tasks=sorted((dict(known[t]) for t in scope), key=lambda r:r['task_id']),
                  context_tasks=context_tasks, context_project=dict(group) if group else None,
                  project_count=len(project_ids), task_count=len(scope), retire_receipts=retire,
                  eligible=not reasons, reasons=reasons)
    canonical(review)  # Detached strict canonical values, never an opaque digest authority.
    return review


def apply(c, request, facts):
    if request.operation=='delete_template':return apply_template_delete(c,request,facts)
    entity = 'project' if request.operation == 'delete_project' else 'task'
    a = request.args();field = entity + '_id'
    if set(a) != {field, 'expected_version', 'review', 'confirmed_text'}:
        raise ValueError('Delete requires exact UUID/version/review/confirmed_text fields')
    key = uuid_text(a[field]);integer(a['expected_version'], 'Reviewed Delete version', 1, 2**63-1)
    current = preview(facts, entity, key)
    if current['selected']['version'] != a['expected_version'] or canonical(current) != canonical(a['review']):
        raise StaleState('Delete review changed; obtain a fresh preview and confirmation')
    if a['confirmed_text'] != 'DELETE': raise ValueError('Type exactly DELETE; no deletion was authorized')
    if not current['eligible']: raise ValueError('Delete refused: ' + '; '.join(current['reasons']))
    scope = {t['task_id'] for t in current['tasks']};project_ids={key} if entity == 'project' else set()
    retired = {r['request_id'] for r in current['retire_receipts']}
    paths = task_paths(facts['tasks'])
    for task_id in sorted(scope, key=lambda t:(-len(paths[t]), t)):
        c.execute('DELETE FROM tasks WHERE task_id=?', (task_id,))
    if entity == 'project': c.execute('DELETE FROM projects WHERE project_id=?', (key,))
    for row in current['retire_receipts']:
        c.execute('DELETE FROM committed_requests WHERE request_id=? AND receipt_class=?', (row['request_id'], 'administrative'))
    return (dict(entity_type=entity, entity_id=key, removed_projects=len(project_ids),
                 removed_tasks=len(scope), removed_administrative_receipts=len(retired)),
            survivors(facts, scope, project_ids, retired))


def template_preview(facts,key):
    from .templates import from_facts, MANAGEMENT
    uuid_text(key);definitions=from_facts(facts)
    selected=next((d for d in definitions if d['template_id']==key),None)
    if selected is None:raise StaleState('Template absent; absence is not proof of historical Delete')
    ordered=list(receipts(facts));retire=[];context=[]
    for row,request,result in ordered:
        a=request.args()
        if request.operation in MANAGEMENT and a['template_id']==key:retire.append(dict(row))
        elif request.operation in ('apply_template','duplicate_template') and a.get('source_template_id',a.get('template_id'))==key:context.append(dict(row))
    # Complete exact bytes remain JSON-safe canonical strings in the detached review.
    def detached(row):return {k:(v.decode('utf-8') if type(v) is bytes else v) for k,v in row.items()}
    retired={r['request_id'] for r in retire};remaining=template_survivors(facts,key,retired);reasons=[]
    try:verify_records(remaining['projects'],remaining['tasks'],[(r['request_id'],request,result) for r,request,result in ordered if r['request_id'] not in retired],from_facts(remaining))
    except (ValueError,KeyError,StopIteration) as exc:reasons.append('Surviving template/task dependency: '+str(exc))
    return dict(dataset_id=facts['dataset_meta'][0]['dataset_id'],entity_type='template',entity_id=key,
                selected=selected,nodes=selected['nodes'],tasks=[],project_count=0,task_count=0,node_count=len(selected['nodes']),
                effective_archived=bool(selected['is_archived']),retire_receipts=[detached(r) for r in retire],
                application_count=sum(r['operation']=='apply_template' for r in context),source_context=[detached(r) for r in context],eligible=not reasons,reasons=reasons)


def template_survivors(facts,key,retired):
    return {table:[r for r in rows if not(table in ('template_definitions','template_nodes') and r['template_id']==key or table=='committed_requests' and r['request_id'] in retired)] for table,rows in facts.items()}


def apply_template_delete(c,request,facts):
    from .templates import fields
    a=request.args();fields(a,{'template_id','expected_version','review','confirmed_text'})
    key=uuid_text(a['template_id']);integer(a['expected_version'],'Template version',1,2**63-1)
    current=template_preview(facts,key)
    if canonical(current)!=canonical(a['review']) or current['selected']['version']!=a['expected_version']:raise StaleState('Template Delete review changed')
    if a['confirmed_text']!='DELETE' or not current['eligible']:raise ValueError('Template Delete requires eligible exact review and typed DELETE')
    retired={r['request_id'] for r in current['retire_receipts']}
    c.execute('DELETE FROM template_nodes WHERE template_id=?',(key,))
    c.execute('DELETE FROM template_definitions WHERE template_id=?',(key,))
    for key in sorted(retired):c.execute("DELETE FROM committed_requests WHERE request_id=? AND receipt_class='administrative'",(key,))
    return dict(template_id=a['template_id'],removed_nodes=current['node_count'],removed_administrative_receipts=len(retired)),template_survivors(facts,a['template_id'],retired)
