"""Shared real candidate cases; no application worker or placeholder evidence."""
from copy import deepcopy
from chronicle import schema_profiles as schema
from chronicle.schema4_evidence import Rows
from chronicle.schema4_services import read_state
from chronicle.records import Request
from chronicle.timesheet import prepare
from chronicle.templates import read
from conftest import uid,NOW
from test_project_movement import adapter,snapshot,create,ancestry
from chronicle.movement import snapshot as task_snapshot

M=60_000_000


def send(a,operation,*,now=NOW,**args):
    request=Request.make(uid(),a.context.dataset_id,operation,now,**args)
    result=a.execute(request)
    assert result.status=='committed',result
    return request,result


def project(a,parent=None):return create(a,parent=parent).args()['project_id']


def task(a,group=None,parent=None,name='Duplicate'):
    state=snapshot(a);groups={p['project_id']:p for p in state['projects']};tasks={t['task_id']:t for t in state['tasks']}
    if parent is not None:group=tasks[parent]['project_id']
    identity=uid()
    send(a,'create_task',task_id=identity,name=name,project_id=group,parent_task_id=parent,
         expected_parent_version=tasks[parent]['version'] if parent else None,
         expected_project_version=groups[group]['version'] if group else None,
         reviewed_destination_project_ancestry=ancestry(groups,group))
    return identity


def lifecycle(a,entity,identity,operation='archive'):
    row=next(r for r in snapshot(a)[entity+'s'] if r[entity+'_id']==identity)
    return send(a,operation+'_'+entity,**{entity+'_id':identity,'expected_version':row['version']})


def dated(a,identity,duration='0:15',day='2026-10-19'):
    entry=uid();send(a,'add_date_only_work',task_id=identity,entry_id=entry,work_date=day,duration_text=duration,comment='Accepted')
    return entry


def move_args(a,identity,parent=None,group=None):
    state=snapshot(a);tasks={t['task_id']:t for t in state['tasks']};projects={p['project_id']:p for p in state['projects']};row=tasks[identity]
    if parent is not None:group=tasks[parent]['project_id']
    return dict(task_id=identity,expected_version=row['version'],source_parent_task_id=row['parent_task_id'],source_project_id=row['project_id'],
                destination_parent_task_id=parent,destination_project_id=group,expected_destination_parent_version=tasks[parent]['version'] if parent else None,
                expected_destination_project_version=projects[group]['version'] if group else None,reviewed_subtree=task_snapshot(state['tasks'],identity),
                reviewed_source_project_ancestry=ancestry(projects,row['project_id']),reviewed_destination_project_ancestry=ancestry(projects,group))


def template(a,depth=2,name='Blueprint'):
    from test_templates import nodes
    identity=uid();send(a,'create_template',template_id=identity,name=name,nodes=nodes(depth))
    return definitions(a)[identity]


def definitions(a):
    c=a.connect(readonly=True)
    try:return read(Rows(c))
    finally:c.close()


def apply_args(a,definition,group=None,parent=None):
    from test_templates import apply_args as args
    state=snapshot(a);projects={p['project_id']:p for p in state['projects']};tasks={t['task_id']:t for t in state['tasks']}
    if parent is not None:group=tasks[parent]['project_id']
    result=args(definition,parent,group,tasks[parent]['version'] if parent else None,projects[group]['version'] if group else None)
    result['reviewed_destination_project_ancestry']=ancestry(projects,group)
    return result


def preview_export(a,cutoff=NOW,**options):
    c=a.connect(readonly=True)
    try:
        c.execute('BEGIN');state=read_state(c,a.context,cutoff_utc_us=cutoff)
        work=[dict(r) for r in Rows(c).execute('SELECT e.task_id,r.* FROM work_entries e JOIN work_revisions r ON r.entry_id=e.entry_id AND r.revision=e.current_revision WHERE r.is_deleted=0')]
        value=prepare(export_id=uid(),dataset_id=a.context.dataset_id,cutoff_utc_us=cutoff,timezone=state['timezone'],week_start=state['week_start'],
            tasks=state['tasks'],projects=state['projects'],work=work,active=state['active'],**options)
        c.execute('ROLLBACK');return value
    finally:c.close()


def export(a,**options):
    value=preview_export(a,**options);send(a,'register_timesheet_export',candidate=value.content());return value


def manual(a,identity,quarters=0,prior=None):
    return send(a,'confirm_polr_absolute',batch_id=uid(),mode='manual',source_export_id=None,source_metadata=None,reviewed_rows=[],selected_keys=[],acknowledgements=[],
        manual_cells=[dict(task_id=identity,work_date='2026-10-19',confirmed_quarters=quarters,prior_batch_id=prior[0] if prior else None,prior_quarters=prior[1] if prior else None)])


def delete_request(a,entity,identity,confirmation='DELETE'):
    review=a.preview(entity,identity)
    return Request.make(uid(),a.context.dataset_id,'delete_'+entity,NOW,**{entity+'_id':identity,'expected_version':review['selected']['version'],'review':review,'confirmed_text':confirmation})


def verified(a):
    c=a.connect(readonly=True)
    try:return schema.verify_candidate(c)
    finally:c.close()


def corrupt(a,table,sql,args=()):
    c=a.connect()
    try:
        c.execute('PRAGMA foreign_keys=OFF')
        triggers=list(c.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",(table,)))
        for name,_ in triggers:c.execute('DROP TRIGGER '+name)
        c.execute(sql,args)
        for _,definition in triggers:c.execute(definition)
    finally:c.close()
