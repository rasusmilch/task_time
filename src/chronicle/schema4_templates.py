"""Candidate template context adapter around the existing pure template model."""
import json
from copy import deepcopy
from . import templates
from .schema4_tasks import ancestry_review,effective_projects,check
from .project_services import _facts


def apply_effect(op,args,defs,tasks,projects,active,used,request_id,now,erased=frozenset()):
    a=deepcopy(args)
    if op=='apply_template':
        if 'reviewed_destination_project_ancestry' not in a:raise ValueError('Complete project ancestry review required')
        ancestry_review(projects,a['destination_project_id'],a.pop('reviewed_destination_project_ancestry'))
    return templates.effect(op,a,defs,tasks,{p['project_id']:p for p in effective_projects(list(projects.values()))},
                            active,used,request_id,now,erased)


def apply_template_operation(c,request,context):
    check(c,request,context)
    defs=templates.read(c);before=deepcopy(defs)
    facts=_facts(c);tasks={r['task_id']:r for r in facts['tasks']};projects={r['project_id']:r for r in facts['projects']}
    used={}
    for row in facts['committed_requests']:
        op=row['operation'];a=json.loads(row['request_bytes'])['arguments']
        if op in ('create_template','edit_template'):used.setdefault(a['template_id'],set()).update(n['node_id'] for n in a['nodes'])
        if op=='duplicate_template':used.setdefault(a['template_id'],set()).update(n['new_node_id'] for n in a['node_mapping'])
    result=apply_effect(request.operation,request.args(),defs,tasks,projects,facts['active_timer'][0] if facts['active_timer'] else None,
                        used,request.request_id,request.action_utc_us)
    if result is None:return None
    result=templates.install(c,request,defs,tasks,before,result)
    after=_facts(c)
    allowed={'tasks'} if request.operation=='apply_template' else {'template_definitions','template_nodes'}
    if any(after[t]!=facts[t] for t in facts.keys()-allowed):raise ValueError('Template operation changed unrelated facts')
    return result
