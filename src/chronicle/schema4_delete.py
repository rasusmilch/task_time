"""Finite nested-project Delete proof; no receipts, writer or retry authority."""
from . import schema_profiles as schema,templates
from .schema4_evidence import verify_transaction
from .schema4_tasks import check
from .project_services import _facts,_ancestry
from .hierarchy import ProjectForest,task_paths,candidate_task_observations
from .records import uuid_text,integer,canonical,StaleState
from .deletion import protected_references,receipts

OPERATIONS=frozenset(('delete_project','delete_task','delete_template'))
PROJECT_ADMIN=frozenset(('create_project','create_child_project','rename_project','archive_project','unarchive_project'))
TASK_ADMIN=frozenset(('create_task','rename_task','assign_task_to_project','archive_task','unarchive_task'))
RETIRE=PROJECT_ADMIN|TASK_ADMIN|{'move_project_subtree','move_task_branch','apply_template'}


def survivors(facts,projects,tasks,retired,template=None):
    return {table:[r for r in rows if not(
        table=='projects' and r['project_id'] in projects or
        table=='tasks' and r['task_id'] in tasks or
        table=='committed_requests' and r['request_id'] in retired or
        table in ('template_definitions','template_nodes') and r['template_id']==template)] for table,rows in facts.items()}


def verify_survivors(facts):
    from .administration import verify_schema4_history
    verify_schema4_history(facts['projects'],facts['tasks'],facts['committed_requests'],facts['dataset_meta'][0]['dataset_id'],facts=facts)


def detached(row):
    return {k:(v.decode('utf-8') if type(v) is bytes else v) for k,v in row.items()}


def review_facts(facts,entity,identity):
    uuid_text(identity)
    forest=ProjectForest(facts['projects']);paths=task_paths(facts['tasks'])
    groups={r['project_id']:r for r in facts['projects']};known={r['task_id']:r for r in facts['tasks']}
    projects=set();tasks=set();context_tasks=[];parent=None;source_context=[]
    if entity=='template':
        definitions={d['template_id']:d for d in templates.from_facts(facts)}
        if identity not in definitions:raise StaleState('Template absent; presence is not historical Delete proof')
        selected=definitions[identity]
    elif entity=='project':
        if identity not in groups:raise StaleState('Project absent; presence is not historical Delete proof')
        selected=groups[identity];projects=set(forest.descendants(identity))
        tasks={t['task_id'] for t in known.values() if t['project_id'] in projects};parent=selected['parent_project_id']
    elif entity=='task':
        if identity not in known:raise StaleState('Task absent; presence is not historical Delete proof')
        selected=known[identity];tasks={k for k,path in paths.items() if identity in path}
        context_tasks=[known[k] for k in reversed(paths[identity][1:])];parent=selected['project_id']
    else:raise ValueError('Unknown Delete entity type')
    reasons=[];retired=[]
    def block(reason):
        if reason not in reasons:reasons.append(reason)
    if entity!='template':
        for table in ('work_entries','active_timer','timesheet_export_tasks','timesheet_export_week_basis','timesheet_export_cells','polr_confirmation_cells','polr_confirmed_current'):
            if any(r['task_id'] in tasks or table=='timesheet_export_tasks' and r['project_id'] in projects for r in facts[table]):block('Protected relationship: '+table)
        entries={r['entry_id'] for r in facts['work_entries'] if r['task_id'] in tasks}
        for table in ('work_revisions','active_start_corrections'):
            if any(r['entry_id'] in entries for r in facts[table]):block('Protected relationship: '+table)
    for row,request,result in receipts(facts):
        op,a=request.operation,request.args();owned=False
        if entity=='template' and op in ('apply_template','duplicate_template') and a.get('source_template_id',a.get('template_id'))==identity:
            source_context.append(detached(row))
        if row['receipt_class']=='protected':
            refs,project_refs=protected_references(request,facts)
            if refs & tasks or project_refs & projects:block('Protected request reference: '+request.request_id)
            continue
        if op in templates.MANAGEMENT:
            owned=entity=='template' and a['template_id']==identity
        elif op not in RETIRE:raise ValueError('Unclassified schema-4 administrative dependency')
        elif entity=='template':pass
        elif op in PROJECT_ADMIN:owned=a['project_id'] in projects
        elif op in TASK_ADMIN:owned=a['task_id'] in tasks
        elif op=='move_task_branch':
            members={r['task_id'] for r in a['reviewed_subtree']};changed={r['task_id'] for r in result['changed_tasks']}
            relevant=bool((members|changed)&tasks);owned=relevant and (members|changed)<=tasks
            if relevant and not owned:block('Movement receipt spans surviving tasks: '+request.request_id)
        elif op=='move_project_subtree':
            members={r['project_id'] for r in a['reviewed_projects']}|{result['project_id']}
            task_members={r['task_id'] for r in a['reviewed_tasks']}
            relevant=bool(members&projects or task_members&tasks)
            owned=relevant and members<=projects and task_members<=tasks
            if relevant and not owned:block('Project movement receipt spans surviving identities: '+request.request_id)
        elif op=='apply_template':
            members={r['task_id'] for r in result['created_tasks']};relevant=bool(members&tasks)
            owned=relevant and members<=tasks
            if relevant and not owned:block('Apply receipt spans surviving tasks: '+request.request_id)
        if owned:retired.append(detached(row))
    remaining=survivors(facts,projects,tasks,{r['request_id'] for r in retired},identity if entity=='template' else None)
    try:verify_survivors(remaining)
    except (ValueError,KeyError,StopIteration) as exc:block('Surviving history requires retained dependencies: '+str(exc))
    effective=(bool(selected['is_archived']) if entity=='template' else forest.effective_archived[identity] if entity=='project'
               else candidate_task_observations(facts['tasks'],facts['projects'])[identity]['effective_archived'])
    result=dict(dataset_id=facts['dataset_meta'][0]['dataset_id'],entity_type=entity,entity_id=identity,selected=dict(selected),
        projects=sorted([groups[k] for k in projects],key=lambda r:r['project_id']),
        tasks=sorted([known[k] for k in tasks],key=lambda r:r['task_id']),context_tasks=context_tasks,
        source_project_ancestry=_ancestry(forest,groups,parent),effective_archived=effective,
        project_count=len(projects),task_count=len(tasks),retire_receipts=retired,source_context=source_context,
        irreversible=True,eligible=not reasons,reasons=reasons)
    canonical(result);return result


def preview(c,context,entity,identity):
    verify_transaction(c)
    if schema._rows(c,'dataset_meta')[0]['dataset_id']!=context.dataset_id:raise ValueError('Wrong candidate dataset')
    return review_facts(_facts(c),entity,identity)


def apply_delete(c,request,context):
    check(c,request,context)
    if request.operation not in OPERATIONS:raise ValueError('Unknown candidate Delete operation')
    verify_transaction(c);before=_facts(c)
    entity=request.operation.removeprefix('delete_');field=entity+'_id';a=request.args()
    if set(a)!={field,'expected_version','review','confirmed_text'}:raise ValueError('Delete requires exact identity/version/review/confirmation fields')
    key=uuid_text(a[field]);integer(a['expected_version'],'Delete version',1,2**63-1)
    current=review_facts(before,entity,key)
    if current['selected']['version']!=a['expected_version'] or canonical(current)!=canonical(a['review']):raise StaleState('Delete review changed; obtain fresh review and typed confirmation')
    if type(a['confirmed_text']) is not str or a['confirmed_text']!='DELETE':raise ValueError('Type exactly DELETE')
    if not current['eligible']:raise ValueError('Delete refused: '+'; '.join(current['reasons']))
    projects={p['project_id'] for p in current['projects']};tasks={t['task_id'] for t in current['tasks']}
    retired={r['request_id'] for r in current['retire_receipts']}
    if entity=='template':
        c.execute('DELETE FROM template_nodes WHERE template_id=?',(key,));c.execute('DELETE FROM template_definitions WHERE template_id=?',(key,))
    else:
        paths=task_paths(before['tasks'])
        for identity in sorted(tasks,key=lambda k:(-len(paths[k]),k)):c.execute('DELETE FROM tasks WHERE task_id=?',(identity,))
        for identity in ProjectForest(before['projects']).reverse_order:
            if identity in projects:c.execute('DELETE FROM projects WHERE project_id=?',(identity,))
    for identity in sorted(retired):c.execute("DELETE FROM committed_requests WHERE request_id=? AND receipt_class='administrative'",(identity,))
    expected=survivors(before,projects,tasks,retired,key if entity=='template' else None)
    verify_transaction(c)
    if _facts(c)!=expected:raise ValueError('Delete changed unrelated/protected facts or sequence high water')
    return dict(entity_type=entity,entity_id=key,removed_projects=len(projects),removed_tasks=len(tasks),removed_administrative_receipts=len(retired))
