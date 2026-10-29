"""Typed template graphs and transient historical effects; SQLite remains authority."""
from copy import deepcopy
import json
from .records import canonical, uuid_text, integer, StaleState
from .timekeeping import instant
from .hierarchy import task_paths, task_observations

MANAGEMENT=frozenset(('create_template','edit_template','duplicate_template','archive_template','unarchive_template'))
OPERATIONS=MANAGEMENT|{'apply_template'}
NODE_FIELDS={'node_id','parent_node_id','name','position'}
DEFINITION_FIELDS={'template_id','name','name_key','version','is_archived','archived_at_utc_us','created_request_id','created_utc_us','updated_utc_us','nodes'}


def fields(value, expected):
    if type(value) is not dict or set(value)!=set(expected):raise ValueError('Exact template fields required')


def name(value):
    if type(value) is not str or not value.strip():raise ValueError('Nonempty template/node name required')
    return value.strip()


def graph(nodes):
    if type(nodes) is not list or not nodes:raise ValueError('Template needs at least one node')
    known={};paths={};ordered=[]
    for position,node in enumerate(nodes):
        fields(node,NODE_FIELDS);key=uuid_text(node['node_id']);parent=node['parent_node_id']
        integer(node['position'],'Node position',0,2**63-1)
        if node['position']!=position or key in known:raise ValueError('Canonical contiguous positions and distinct UUIDs required')
        if node['name']!=name(node['name']):raise ValueError('Node names must be trimmed')
        if parent is not None:
            uuid_text(parent)
            if parent not in known:raise ValueError('Parent must precede child in same graph')
        path=(() if parent is None else paths[parent])+(key,)
        if len(path)>3:raise ValueError('Template exceeds three levels')
        # Canonical preorder must not revisit a branch after leaving it.
        if parent is not None and ordered and parent not in paths[ordered[-1]]:raise ValueError('Nodes must follow preorder')
        known[key]=dict(node);paths[key]=path;ordered.append(key)
    return deepcopy(nodes),paths


def definition(value):
    fields(value,DEFINITION_FIELDS);uuid_text(value['template_id']);uuid_text(value['created_request_id'])
    if value['name']!=name(value['name']) or value['name_key']!=value['name'].casefold():raise ValueError('Invalid canonical template name/key')
    integer(value['version'],'Template version',1,2**63-1);integer(value['is_archived'],'Template archive',0,1)
    instant(value['created_utc_us']);instant(value['updated_utc_us'])
    if bool(value['is_archived'])!=(value['archived_at_utc_us'] is not None):raise ValueError('Invalid template archive timestamp')
    if value['archived_at_utc_us'] is not None:instant(value['archived_at_utc_us'])
    graph(value['nodes']);return deepcopy(value)


def read(c):
    values = {r['template_id']:dict(r,nodes=[{k:n[k] for k in NODE_FIELDS} for n in c.execute('SELECT * FROM template_nodes WHERE template_id=? ORDER BY position',(r['template_id'],))]) for r in c.execute('SELECT * FROM template_definitions ORDER BY name_key,template_id')}

    unique(values)
    return values

def unique(definitions):
    keys=[];nodes=[]
    for d in definitions.values():
        definition(d)
        if not d['is_archived']:keys.append(d['name_key'])
        nodes.extend(n['node_id'] for n in d['nodes'])
    if len(keys)!=len(set(keys)):raise ValueError('Active template name collision; choose a distinct name')
    if len(nodes)!=len(set(nodes)):raise ValueError('Template node UUID collision')


def reviewed_source(a,defs,field,version_field,review_field,erased):
    key=uuid_text(a[field]);wanted=integer(a[version_field],'Reviewed template version',1,2**63-1)
    frozen=definition(a[review_field])
    if frozen['template_id']!=key or frozen['version']!=wanted:raise ValueError('Frozen template identity/version differs')
    if key in defs:
        if canonical(frozen)!=canonical(defs[key]):raise StaleState('Reviewed template changed')
    elif key not in erased:raise StaleState('Template source missing')
    return frozen


def apply_effect(a,defs,tasks,projects,active,request_id,now,erased=frozenset()):
    fields(a,{'template_id','expected_template_version','reviewed_definition','destination_parent_task_id','destination_project_id','expected_destination_parent_version','expected_destination_project_version','node_mapping'})
    d=reviewed_source(a,defs,'template_id','expected_template_version','reviewed_definition',erased)
    if d['is_archived']:raise ValueError('Archived template cannot be applied')
    parent=a['destination_parent_task_id'];group=a['destination_project_id']
    for key,v,rows in ((parent,a['expected_destination_parent_version'],tasks),(group,a['expected_destination_project_version'],projects)):
        if key is None:
            if v is not None:raise ValueError('Absent destination has no version')
        else:
            uuid_text(key);integer(v,'Destination version',1,2**63-1)
            if key not in rows or rows[key]['version']!=v:raise StaleState('Reviewed destination changed')
    if parent is not None:
        context=task_observations(list(tasks.values()),list(projects.values()))[parent]
        if tasks[parent]['project_id']!=group or context['effective_archived'] or active and active['task_id']==parent:raise ValueError('Apply destination ineligible or running')
    if group is not None and projects[group]['is_archived']:raise ValueError('Apply project archived')
    mapping=a['node_mapping']
    if type(mapping) is not list or len(mapping)!=len(d['nodes']):raise ValueError('Complete ordered Apply mapping required')
    mapped={};created=[]
    for node,pair in zip(d['nodes'],mapping):
        fields(pair,{'node_id','task_id'});uuid_text(pair['task_id'])
        if pair['node_id']!=node['node_id'] or pair['task_id'] in tasks or pair['task_id'] in mapped.values():raise ValueError('Invalid/fresh Apply mapping')
        mapped[pair['node_id']]=pair['task_id']
    proposed=deepcopy(tasks)
    for node in d['nodes']:
        key=mapped[node['node_id']]
        proposed[key]=dict(task_id=key,project_id=group,parent_task_id=mapped[node['parent_node_id']] if node['parent_node_id'] else parent,name=node['name'],version=1,is_archived=0,archived_at_utc_us=None,created_request_id=request_id,created_utc_us=now,updated_utc_us=now)
        created.append(dict(node_id=node['node_id'],task_id=key,version=1))
    observations=task_observations(list(proposed.values()),list(projects.values()))
    if active and (not observations[active['task_id']]['is_leaf'] or observations[active['task_id']]['effective_archived']):raise ValueError('Apply invalidates active leaf')
    tasks.clear();tasks.update(proposed)
    return dict(template_id=d['template_id'],created_tasks=created)


def effect(op,a,defs,tasks,projects,active,used,request_id,now,erased=frozenset()):
    if op=='apply_template':return apply_effect(a,defs,tasks,projects,active,request_id,now,erased)
    key=uuid_text(a.get('template_id'))
    expected={'template_id','name','nodes'} if op=='create_template' else {'template_id','expected_version','name','nodes'} if op=='edit_template' else {'template_id','name','source_template_id','expected_source_version','reviewed_source','node_mapping'} if op=='duplicate_template' else {'template_id','expected_version'}
    fields(a,expected)
    if op in ('create_template','duplicate_template'):
        if key in defs:raise ValueError('Template identity already exists')
        if op=='duplicate_template':
            source=reviewed_source(a,defs,'source_template_id','expected_source_version','reviewed_source',erased)
            mapping=a['node_mapping']
            if type(mapping) is not list or len(mapping)!=len(source['nodes']):raise ValueError('Complete Duplicate mapping required')
            for pair in mapping:fields(pair,{'node_id','new_node_id'});uuid_text(pair['node_id']);uuid_text(pair['new_node_id'])
            if [p['node_id'] for p in mapping]!=sorted(n['node_id'] for n in source['nodes']):raise ValueError('Duplicate mapping must be UUID-sorted')
            lookup={p['node_id']:p['new_node_id'] for p in mapping}
            if len(set(lookup.values()))!=len(mapping) or set(lookup.values()) & {n['node_id'] for n in source['nodes']}:raise ValueError('Duplicate nodes must be fresh')
            nodes=[dict(n,node_id=lookup[n['node_id']],parent_node_id=lookup[n['parent_node_id']] if n['parent_node_id'] else None) for n in source['nodes']]
        else:nodes=a['nodes']
        nodes,_=graph(nodes);title=name(a['name'])
        d=dict(template_id=key,name=title,name_key=title.casefold(),nodes=nodes,version=1,is_archived=0,archived_at_utc_us=None,created_request_id=request_id,created_utc_us=now,updated_utc_us=now)
    else:
        integer(a['expected_version'],'Template version',1,2**63-1)
        if key not in defs or defs[key]['version']!=a['expected_version']:raise StaleState('Reviewed template version changed')
        d=deepcopy(defs[key])
        if op=='edit_template':
            nodes,_=graph(a['nodes']);title=name(a['name'])
            if (d['name'],d['nodes'])==(title,nodes):return None
            prior={n['node_id'] for n in d['nodes']};new={n['node_id'] for n in nodes}
            if (new-prior)&used.get(key,set()):raise ValueError('Removed template node UUID cannot be reused')
            d.update(name=title,name_key=title.casefold(),nodes=nodes)
        else:
            archived=int(op=='archive_template')
            if d['is_archived']==archived:return None
            d.update(is_archived=archived,archived_at_utc_us=now if archived else None)
        d.update(version=integer(d['version']+1,'Next template version',1,2**63-1),updated_utc_us=now)
    defs[key]=d;unique(defs);used.setdefault(key,set()).update(n['node_id'] for n in d['nodes'])
    return dict(template_id=key,version=d['version'])


def execute(c,request):
    from .sqlite_store import SQLiteStore
    SQLiteStore._verify_complete(c)
    defs=read(c);tasks={r['task_id']:dict(r) for r in c.execute('SELECT * FROM tasks')};projects={r['project_id']:dict(r) for r in c.execute('SELECT * FROM projects')}
    active=c.execute('SELECT * FROM active_timer').fetchone();used={}
    for row in c.execute('SELECT operation,request_bytes FROM committed_requests'):
        op=row['operation'];a=json.loads(row['request_bytes'])['arguments']
        if op in ('create_template','edit_template'):used.setdefault(a['template_id'],set()).update(n['node_id'] for n in a['nodes'])
        if op=='duplicate_template':used.setdefault(a['template_id'],set()).update(n['new_node_id'] for n in a['node_mapping'])
    before=deepcopy(defs)
    result=effect(request.operation,request.args(),defs,tasks,projects,active,used,request.request_id,request.action_utc_us)
    if result is None:return None
    if request.operation=='apply_template':
        for pair in result['created_tasks']:
            row=tasks[pair['task_id']];columns=tuple(row)
            c.execute('INSERT INTO tasks('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(row.values()))
    else:
        key=result['template_id'];d=defs[key];values={k:v for k,v in d.items() if k!='nodes'}
        graph_changed=key not in before or before[key]['nodes']!=d['nodes']
        if key in before:
            if graph_changed:c.execute('DELETE FROM template_nodes WHERE template_id=?',(key,))
            c.execute('UPDATE template_definitions SET name=?,name_key=?,version=?,is_archived=?,archived_at_utc_us=?,updated_utc_us=? WHERE template_id=?',
                      (d['name'],d['name_key'],d['version'],d['is_archived'],d['archived_at_utc_us'],d['updated_utc_us'],key))
        else:c.execute('INSERT INTO template_definitions('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))
        if graph_changed:
            for n in d['nodes']:c.execute('INSERT INTO template_nodes(template_id,node_id,parent_node_id,name,position) VALUES(?,?,?,?,?)',(key,n['node_id'],n['parent_node_id'],n['name'],n['position']))
    return result


def from_facts(facts):
    return [dict(r,nodes=[{k:n[k] for k in NODE_FIELDS} for n in sorted(facts['template_nodes'],key=lambda n:n['position']) if n['template_id']==r['template_id']]) for r in facts['template_definitions']]
