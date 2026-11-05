"""Independent chronological administrative verification, never runtime state."""
from .records import canonical, uuid_text, integer
from .hierarchy import task_paths, task_observations
from .movement import plan
from .lifecycle import OPERATIONS, transition


def verify(c, receipts):
    actual_projects = [dict(r) for r in c.execute('SELECT * FROM projects')]
    actual_tasks = [dict(r) for r in c.execute('SELECT * FROM tasks')]
    ordered = [(key, *receipts[key]) for _, key in c.execute(
        'SELECT commit_seq,request_id FROM committed_requests ORDER BY commit_seq')]
    from .templates import read
    verify_records(actual_projects, actual_tasks, ordered, list(read(c).values()))


def verify_records(actual_projects, actual_tasks, ordered, actual_templates=()):
    """Strict independent survivor verification; also used for volatile Delete review."""
    # No missing-entity exception: every supplied survivor and retained effect must agree.
    from .templates import OPERATIONS as TEMPLATE_OPS, effect, unique
    tasks,projects={},{}
    templates, used = {}, {}
    surviving_templates={d["template_id"] for d in actual_templates}
    erased={request.args().get("source_template_id",request.args().get("template_id")) for _,request,_ in ordered if request.operation in ("apply_template","duplicate_template")} - surviving_templates
    active=None
    def version(rows,key,wanted):
        integer(wanted,'Reviewed administrative version',1,2**63-1)
        if key not in rows or rows[key]['version']!=wanted:raise ValueError('Administrative reviewed version differs')
        return rows[key]
    for request_id, request, result in ordered:
        op=request.operation;a=request.args();now=request.action_utc_us
        if op in ('start_timer','switch_timer'):
            active=dict(task_id=a['next_task_id' if op=='switch_timer' else 'task_id'])
        elif op=='stop_timer':
            active=None
        if op in TEMPLATE_OPS:
            expected=effect(op,a,templates,tasks,projects,active,used,request_id,now,erased)
            if expected is None or canonical(expected)!=canonical(result):raise ValueError('Template administrative effects differ')
            continue
        if op in OPERATIONS:
            changed = transition(op, a, now, list(tasks.values()), list(projects.values()), active)
            if changed is None:
                raise ValueError('No-op archive operation cannot have a receipt')
            entity = 'project' if op.endswith('_project') else 'task'
            key = changed[entity + '_id']
            if canonical(result) != canonical({entity + '_id': key, 'version': changed['version']}):
                raise ValueError('Archive administrative result/version differs')
            (projects if entity == 'project' else tasks)[key] = changed
            continue
        if op=='move_task_branch':
            final,expected=plan(list(tasks.values()),list(projects.values()),active,a)
            if not expected['changed_tasks']:raise ValueError('No-op move cannot have a receipt')
            if canonical(result)!=canonical(expected):raise ValueError('Move administrative effects differ')
            tasks={r['task_id']:r for r in final}
            for changed in expected['changed_tasks']:tasks[changed['task_id']]['updated_utc_us']=now
            continue
        if op not in ('create_project','create_task','rename_project','rename_task','assign_task_to_project'):continue
        entity='project' if op in ('create_project','rename_project') else 'task'
        rows=projects if entity=='project' else tasks
        key=uuid_text(a.get(entity+'_id'))
        required={entity+'_id','name'} if op.startswith('create_') else (
            {'task_id','project_id','expected_version'} if op=='assign_task_to_project' else {entity+'_id','name','expected_version'})
        allowed=required|({'project_id','parent_task_id','expected_project_version','expected_parent_version'} if op=='create_task' else set())
        if not required<=set(a) or not set(a)<=allowed:raise ValueError('Invalid administrative fields')
        if 'name' in a and (type(a['name']) is not str or not a['name'].strip()):raise ValueError('Invalid administrative name')
        if op.startswith('create_'):
            if key in rows:raise ValueError('Duplicate administrative creation')
            parent=a.get('parent_task_id');group=a.get('project_id')
            if entity=='task':
                if parent is not None:
                    uuid_text(parent);p=version(tasks,parent,a.get('expected_parent_version'))
                    if 'project_id' in a and group!=p['project_id']:raise ValueError('Child project context differs')
                    group=p['project_id']
                    context=task_observations(list(tasks.values()),list(projects.values()))[parent]
                    if context['effective_archived'] or context['depth']>=3 or active and active['task_id']==parent:
                        raise ValueError('Administrative creation destination was ineligible')
                elif a.get('expected_parent_version') is not None:raise ValueError('Unexpected parent review')
                if group is not None:
                    uuid_text(group)
                    if parent is None or a.get('expected_project_version') is not None:version(projects,group,a.get('expected_project_version'))
                    elif group not in projects:raise ValueError('Unknown project')
                elif a.get('expected_project_version') is not None:raise ValueError('Unassigned has no version')
                if group is not None and projects[group]['is_archived']:
                    raise ValueError('Administrative creation project was archived')
            row=dict(name=a['name'].strip(),version=1,created_request_id=request_id,created_utc_us=now,updated_utc_us=now,
                     is_archived=0,archived_at_utc_us=None)
            row[entity+'_id']=key
            if entity=='task':row.update(parent_task_id=parent,project_id=group)
            rows[key]=row
        else:
            row=version(rows,key,a['expected_version'])
            if op=='assign_task_to_project':
                group=a['project_id']
                if group is not None:uuid_text(group)
                if (group is not None and group not in projects or row['parent_task_id'] is not None
                    or any(t['parent_task_id']==key for t in tasks.values()) or row['project_id']==group):
                    raise ValueError('Invalid standalone administrative assignment')
                context=task_observations(list(tasks.values()),list(projects.values()))[key]
                if context['effective_archived'] or group is not None and projects[group]['is_archived']:
                    raise ValueError('Administrative assignment context was archived')
                row['project_id']=group
            else:
                if row['name']==a['name'].strip():raise ValueError('No-op administrative rename')
                row['name']=a['name'].strip()
            row['version']+=1;row['updated_utc_us']=now
        if canonical(result)!=canonical({entity+'_id':key,'version':rows[key]['version']}):
            raise ValueError('Administrative result/version differs')
        task_paths(list(tasks.values()))
    for observations,rows,key in ((actual_projects,projects,'project_id'),(actual_tasks,tasks,'task_id')):
        actual={r[key]:dict(r) for r in observations}
        if set(actual)!=set(rows):raise ValueError('Administrative creation/survivor coverage differs')
        for identity,row in rows.items():
            for field,value in row.items():
                if actual[identity][field]!=value:
                    raise ValueError('Current administrative effects differ')

    unique(templates)
    if canonical(sorted(templates.values(),key=lambda d:d['template_id'])) != canonical(sorted(actual_templates,key=lambda d:d['template_id'])):raise ValueError('Template creation/history/current coverage differs')


class UnsupportedCandidateOperation(ValueError):
    """Later schema-4 integration is absent, never silently accepted."""


SCHEMA4_HISTORY_OPERATIONS = frozenset((
    'create_project', 'create_child_project', 'move_project_subtree',
    'create_task', 'rename_project', 'rename_task',
    'archive_project', 'unarchive_project', 'archive_task', 'unarchive_task',
))

SCHEMA4_LIFECYCLE_OPERATIONS = frozenset((
    'archive_project', 'unarchive_project', 'archive_task', 'unarchive_task',
))

SCHEMA4_MOVE_FIELDS = frozenset((
    'project_id', 'expected_version', 'source_parent_project_id',
    'destination_parent_project_id', 'expected_destination_parent_version',
    'reviewed_source_ancestry', 'reviewed_destination_ancestry',
    'reviewed_projects', 'reviewed_tasks',
))


def _candidate_ancestry(forest, projects, parent):
    return [dict(project_id=key, expected_version=projects[key]['version'],
                 parent_project_id=projects[key]['parent_project_id'])
            for key in (() if parent is None else forest.ancestry(parent))]


def _candidate_review(actual, expected, fields):
    if type(actual) is not list:
        raise ValueError('Complete ordered candidate review required')
    for row in actual:
        if type(row) is not dict or set(row) != set(fields):
            raise ValueError('Invalid candidate review fields')
        integer(row['expected_version'], 'Reviewed candidate version', 1, 2**63-1)
        for field in set(fields) - {'expected_version'}:
            if row[field] is not None:
                uuid_text(row[field])
    if canonical(actual) != canonical(expected):
        raise ValueError('Candidate review differs from chronological state')


def candidate_move_result(projects, tasks, arguments):
    """Validate a detached native-v4 contract; no service, write or retry path.

    None means a fully reviewed no-op, which must never have a committed receipt.
    Package B must implement its own authoritative transactional execution.
    """
    from .hierarchy import ProjectForest, candidate_task_observations
    if type(arguments) is not dict or set(arguments) != SCHEMA4_MOVE_FIELDS:
        raise ValueError('Incorrect candidate project movement fields')
    a = arguments
    for field in ('project_id', 'source_parent_project_id', 'destination_parent_project_id'):
        if a[field] is not None or field == 'project_id':
            uuid_text(a[field])
    integer(a['expected_version'], 'Reviewed source version', 1, 2**63-1)
    forest = ProjectForest(list(projects.values()))
    candidate_task_observations(list(tasks.values()), list(projects.values()))
    source = projects.get(a['project_id'])
    if source is None or (source['version'], source['parent_project_id']) != (
            a['expected_version'], a['source_parent_project_id']):
        raise ValueError('Candidate movement source changed')
    destination = a['destination_parent_project_id']
    if destination is None:
        if a['expected_destination_parent_version'] is not None:
            raise ValueError('Root destination has no version')
    else:
        integer(a['expected_destination_parent_version'], 'Destination version', 1, 2**63-1)
        if destination not in projects or projects[destination]['version'] != a['expected_destination_parent_version']:
            raise ValueError('Candidate movement destination changed')
    _candidate_review(a['reviewed_source_ancestry'],
                      _candidate_ancestry(forest, projects, source['parent_project_id']),
                      ('project_id', 'expected_version', 'parent_project_id'))
    _candidate_review(a['reviewed_destination_ancestry'],
                      _candidate_ancestry(forest, projects, destination),
                      ('project_id', 'expected_version', 'parent_project_id'))
    branch = set(forest.descendants(source['project_id']))
    expected_projects = [dict(project_id=key, expected_version=projects[key]['version'],
                              parent_project_id=projects[key]['parent_project_id']) for key in sorted(branch)]
    expected_tasks = [dict(task_id=key, expected_version=row['version'],
                           parent_task_id=row['parent_task_id'], project_id=row['project_id'])
                      for key, row in sorted(tasks.items()) if row['project_id'] in branch]
    _candidate_review(a['reviewed_projects'], expected_projects,
                      ('project_id', 'expected_version', 'parent_project_id'))
    _candidate_review(a['reviewed_tasks'], expected_tasks,
                      ('task_id', 'expected_version', 'parent_task_id', 'project_id'))
    if destination in branch:
        raise ValueError('Candidate project movement creates a cycle')
    if forest.effective_archived[source['project_id']] or destination is not None and forest.effective_archived[destination]:
        raise ValueError('Candidate movement context is effectively archived')
    if source['parent_project_id'] == destination:
        return None
    return dict(project_id=source['project_id'],
                version=integer(source['version']+1, 'Moved version', 1, 2**63-1),
                parent_project_id=destination)


def verify_schema4_history(actual_projects, actual_tasks, receipt_rows, dataset_id, *, facts=None):
    """Independent native candidate reconstruction; never a schema-3 adapter.

    Complete C2 replay requires protected facts; detached administrative use
    never fabricates missing protected evidence.
    The ordinary verify/verify_records functions and classification stay intact.
    """
    import json
    from .records import Request
    from .hierarchy import ProjectForest, candidate_task_observations
    uuid_text(dataset_id)
    from . import templates as template_model
    from .schema4_tasks import effective_projects
    from .schema_profiles import ADMINISTRATIVE_OPERATIONS as candidate_admin
    from .schema4_evidence import WorkChronology
    from .recording_services import FIELDS as protected_operations
    templates, used = {}, {}
    actual_templates = template_model.from_facts(facts) if facts is not None else []
    surviving_templates = {d['template_id'] for d in actual_templates}
    erased = {json.loads(r['request_bytes'])['arguments'].get('source_template_id',
              json.loads(r['request_bytes'])['arguments'].get('template_id'))
              for r in receipt_rows if r['operation'] in ('apply_template','duplicate_template')} - surviving_templates
    chronology = WorkChronology(facts) if facts is not None else None
    active = None
    projects, tasks, seen = {}, {}, set()
    sequences = [integer(r['commit_seq'], 'Commit sequence', 1, 2**63-1) for r in receipt_rows]
    if len(set(sequences)) != len(sequences):
        raise ValueError('Duplicate candidate commit sequence')
    for row in sorted(receipt_rows, key=lambda r: r['commit_seq']):
        content = json.loads(row['request_bytes'])
        if (type(content) is not dict or set(content) != {'format', 'dataset_id', 'operation', 'action_utc_us', 'arguments'}
                or type(content['format']) is not int or content['format'] != 1
                or content['dataset_id'] != dataset_id or content['operation'] != row['operation']
                or content['action_utc_us'] != row['action_utc_us'] or type(content['arguments']) is not dict):
            raise ValueError('Invalid candidate receipt envelope')
        request = Request.make(row['request_id'], dataset_id, row['operation'],
                               row['action_utc_us'], **content['arguments'])
        result = json.loads(row['result_bytes'])
        if (request.request_id in seen or request.content() != row['request_bytes']
                or type(result) is not dict or canonical(result) != row['result_bytes']):
            raise ValueError('Invalid canonical candidate receipt bytes/identity')
        seen.add(request.request_id)
        op, a, now = request.operation, request.args(), request.action_utc_us
        expected_class = 'administrative' if op in candidate_admin else 'protected'
        if row['receipt_class'] != expected_class:
            raise ValueError('Incorrect candidate receipt classification')
        if op in protected_operations:
            if chronology is None:
                raise UnsupportedCandidateOperation('Protected history requires complete evidence facts')
            chronology.step(request, result, tasks, projects)
            active = chronology.active
            continue
        if op in template_model.OPERATIONS:
            a = dict(a)
            if op == 'apply_template':
                if 'reviewed_destination_project_ancestry' not in a:raise ValueError('Missing Apply project ancestry')
                _candidate_review(a.pop('reviewed_destination_project_ancestry'),
                    _candidate_ancestry(ProjectForest(list(projects.values())),projects,a['destination_project_id']),
                    ('project_id','expected_version','parent_project_id'))
            expected = template_model.effect(op,a,templates,tasks,
                {p['project_id']:p for p in effective_projects(list(projects.values()))},active,used,request.request_id,now,erased)
            if expected is None or canonical(expected)!=canonical(result):raise ValueError('Template chronology/result differs')
            continue
        if op not in SCHEMA4_HISTORY_OPERATIONS | {'assign_task_to_project','move_task_branch'}:
            raise UnsupportedCandidateOperation('Candidate history operation not implemented: '+op)
        if op in SCHEMA4_LIFECYCLE_OPERATIONS:
            # Independent reconstruction: never call the service transition.
            # Active state comes from the independent protected chronology.
            ProjectForest(list(projects.values()))
            candidate_task_observations(list(tasks.values()), list(projects.values()))
            entity = 'project' if op.endswith('_project') else 'task'
            rows, field = (projects if entity == 'project' else tasks), entity+'_id'
            if set(a) != {field, 'expected_version'}:
                raise ValueError('Incorrect candidate lifecycle fields')
            key = uuid_text(a[field])
            integer(a['expected_version'], 'Reviewed lifecycle version', 1, 2**63-1)
            if key not in rows or rows[key]['version'] != a['expected_version']:
                raise ValueError('Candidate lifecycle prior identity/version differs')
            archived = int(op.startswith('archive_'))
            if rows[key]['is_archived'] == archived:
                raise ValueError('No-op lifecycle cannot have a committed receipt')
            if archived and active is not None:
                contains = (tasks[active['task_id']]['project_id'] in set(ProjectForest(list(projects.values())).descendants(key))
                            if entity == 'project' else key in task_paths(list(tasks.values()))[active['task_id']])
                if contains:raise ValueError('Historical Archive contains active work')
            rows[key] = dict(rows[key], is_archived=archived,
                             archived_at_utc_us=now if archived else None,
                             version=integer(rows[key]['version']+1, 'Lifecycle version', 1, 2**63-1),
                             updated_utc_us=now)
            expected = {field: key, 'version': rows[key]['version']}
        elif op == 'move_task_branch':
            from .movement import plan, FIELDS
            extensions = {'reviewed_source_project_ancestry','reviewed_destination_project_ancestry'}
            if set(a) != FIELDS | extensions:raise ValueError('Incorrect schema-4 task move fields')
            forest = ProjectForest(list(projects.values()))
            for field,group in (('reviewed_source_project_ancestry',a['source_project_id']),
                                ('reviewed_destination_project_ancestry',a['destination_project_id'])):
                _candidate_review(a[field],_candidate_ancestry(forest,projects,group),('project_id','expected_version','parent_project_id'))
            final,expected = plan(list(tasks.values()),effective_projects(list(projects.values())),active,
                                  {k:v for k,v in a.items() if k not in extensions})
            if not expected['changed_tasks']:raise ValueError('Retained no-op task movement')
            tasks = {t['task_id']:t for t in final}
            for changed in expected['changed_tasks']:tasks[changed['task_id']]['updated_utc_us'] = now
        elif op == 'assign_task_to_project':
            if set(a) != {'task_id','project_id','expected_version','reviewed_source_project_ancestry','reviewed_destination_project_ancestry'}:
                raise ValueError('Incorrect schema-4 assignment fields')
            key = uuid_text(a['task_id']);integer(a['expected_version'],'Assignment version',1,2**63-1)
            if key not in tasks or tasks[key]['version']!=a['expected_version']:raise ValueError('Assignment source changed')
            item=tasks[key];forest=ProjectForest(list(projects.values()));group=a['project_id']
            if group is not None:uuid_text(group)
            for field,parent in (('reviewed_source_project_ancestry',item['project_id']),('reviewed_destination_project_ancestry',group)):
                _candidate_review(a[field],_candidate_ancestry(forest,projects,parent),('project_id','expected_version','parent_project_id'))
            if item['parent_task_id'] is not None or any(t['parent_task_id']==key for t in tasks.values()):raise ValueError('Assignment requires standalone task')
            if candidate_task_observations(list(tasks.values()),list(projects.values()))[key]['effective_archived'] or group is not None and forest.effective_archived[group]:
                raise ValueError('Archived assignment context')
            if group==item['project_id']:raise ValueError('Retained no-op assignment')
            item.update(project_id=group,version=integer(item['version']+1,'Assignment version',1,2**63-1),updated_utc_us=now)
            expected=dict(task_id=key,version=item['version'])
        elif op == 'move_project_subtree':
            expected = candidate_move_result(projects, tasks, a)
            if expected is None:
                raise ValueError('No-op project movement cannot have a committed receipt')
            project = projects[expected['project_id']]
            project.update(parent_project_id=expected['parent_project_id'], version=expected['version'], updated_utc_us=now)
        else:
            entity = 'task' if op in ('create_task', 'rename_task') else 'project'
            rows, field = (tasks if entity == 'task' else projects), entity+'_id'
            required = {field, 'name'}
            if op == 'create_task':required.add('reviewed_destination_project_ancestry')
            if op == 'create_child_project':
                required |= {'parent_project_id', 'expected_parent_version', 'reviewed_parent_ancestry'}
            elif op.startswith('rename_'):
                required.add('expected_version')
            allowed = required | ({'project_id', 'parent_task_id', 'expected_project_version', 'expected_parent_version'} if op == 'create_task' else set())
            if not required <= set(a) or not set(a) <= allowed:
                raise ValueError('Incorrect candidate administrative fields')
            key = uuid_text(a[field])
            if type(a['name']) is not str or not a['name'].strip():
                raise ValueError('Invalid candidate name')
            if op.startswith('rename_'):
                integer(a['expected_version'], 'Reviewed version', 1, 2**63-1)
                if key not in rows or rows[key]['version'] != a['expected_version'] or rows[key]['name'] == a['name'].strip():
                    raise ValueError('Stale or no-op candidate rename')
                rows[key].update(name=a['name'].strip(), version=integer(rows[key]['version']+1, 'New version', 1, 2**63-1), updated_utc_us=now)
            else:
                if key in rows:
                    raise ValueError('Duplicate candidate creation identity')
                parent = None
                if op == 'create_child_project':
                    parent = uuid_text(a['parent_project_id'])
                    integer(a['expected_parent_version'], 'Parent version', 1, 2**63-1)
                    forest = ProjectForest(list(projects.values()))
                    if parent not in projects or projects[parent]['version'] != a['expected_parent_version'] or forest.effective_archived[parent]:
                        raise ValueError('Candidate child destination changed or archived')
                    _candidate_review(a['reviewed_parent_ancestry'], _candidate_ancestry(forest, projects, parent),
                                      ('project_id', 'expected_version', 'parent_project_id'))
                value = dict(name=a['name'].strip(), version=1, is_archived=0, archived_at_utc_us=None,
                             created_request_id=request.request_id, created_utc_us=now, updated_utc_us=now)
                value[field] = key
                if entity == 'project':
                    value['parent_project_id'] = parent
                else:
                    parent, group = a.get('parent_task_id'), a.get('project_id')
                    if parent is not None:
                        uuid_text(parent)
                        integer(a.get('expected_parent_version'), 'Task parent version', 1, 2**63-1)
                        if parent not in tasks or tasks[parent]['version'] != a['expected_parent_version']:
                            raise ValueError('Candidate task parent changed')
                        if 'project_id' in a and group != tasks[parent]['project_id']:
                            raise ValueError('Candidate task project differs')
                        group = tasks[parent]['project_id']
                    elif a.get('expected_parent_version') is not None:
                        raise ValueError('Root task has no parent version')
                    if group is not None:
                        uuid_text(group)
                        if group not in projects:
                            raise ValueError('Unknown candidate task project')
                        if parent is None or a.get('expected_project_version') is not None:
                            integer(a.get('expected_project_version'), 'Project version', 1, 2**63-1)
                            if projects[group]['version'] != a['expected_project_version']:
                                raise ValueError('Candidate task project changed')
                    elif a.get('expected_project_version') is not None:
                        raise ValueError('Unassigned has no version')
                    _candidate_review(a['reviewed_destination_project_ancestry'],
                        _candidate_ancestry(ProjectForest(list(projects.values())),projects,group),
                        ('project_id','expected_version','parent_project_id'))
                    if active and active['task_id']==parent:raise ValueError('Running task became a parent')
                    value.update(parent_task_id=parent, project_id=group)
                rows[key] = value
            expected = {field: key, 'version': rows[key]['version']}
        if canonical(result) != canonical(expected):
            raise ValueError('Candidate administrative result differs')
        ProjectForest(list(projects.values()))
        observations = candidate_task_observations(list(tasks.values()), list(projects.values()))
        if active and not observations[active['task_id']]['eligible_for_new_work']:raise ValueError('Administrative history invalidates active task')
        if op == 'create_task' and observations[a['task_id']]['effective_archived']:
            raise ValueError('Candidate task was created under archived ancestry')
    for actual, expected, field in ((actual_projects, projects, 'project_id'), (actual_tasks, tasks, 'task_id')):
        values = {r[field]: r for r in actual}
        if len(values) != len(actual) or canonical(sorted(values.values(), key=lambda r:r[field])) != canonical(sorted(expected.values(), key=lambda r:r[field])):
            raise ValueError('Candidate creation/history/current coverage differs')

    template_model.unique(templates)
    if canonical(sorted(templates.values(),key=lambda d:d['template_id'])) != canonical(sorted(actual_templates,key=lambda d:d['template_id'])):
        raise ValueError('Candidate template creation/history/current coverage differs')
    if chronology is not None:chronology.finish()
