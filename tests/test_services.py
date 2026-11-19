from dataclasses import replace
import pytest
from chronicle import project_ui as ui
from chronicle.records import canonical
from conftest import uid, M


@pytest.mark.parametrize('bad',['missing','null','unknown','invalid','version','ancestry','archived','parent mismatch','running','depth'])
def test_task_ownership_refusals_are_atomic(client,bad):
    h=client;p=h.project();q=h.project();parent=h.task(p)
    args=dict(task_id=uid(),name='Reviewed task',**ui.new_task_review(h.state(),parent if bad in ('parent mismatch','running') else None,p))
    if bad=='missing':args.pop('project_id')
    elif bad=='null':args['project_id']=None
    elif bad=='unknown':args['project_id']=uid()
    elif bad=='invalid':args['project_id']='invalid'
    elif bad=='version':args['expected_project_version']=999
    elif bad=='ancestry':args['reviewed_destination_project_ancestry']=[]
    elif bad=='archived':h.lifecycle('project',p)
    elif bad=='parent mismatch':args['project_id']=q
    elif bad=='running':h.send('start_timer',task_id=parent,entry_id=uid(),expected_task_version=1)
    else:
        leaf=h.task(p,h.task(p,parent));args.update(parent_task_id=leaf,expected_parent_version=1)
    h.send('create_task',expect='rejected',**args)


def test_nested_projects_task_depth_and_accounting(client):
    h=client;root=h.project(name='Alpha');deep=root
    for i in range(12):deep=h.project(deep,name='組立 Ω '+str(i))
    parent=h.task(root,name='Design');h.dated(parent,'0:10');child=h.task(root,parent);leaf=h.task(root,child);h.dated(leaf,'0:20')
    deep_task=h.task(deep,name='Validation');h.dated(deep_task,'0:30')
    state=h.state();report=state['report']
    assert len(state['projects'])==13 and [t['depth'] for t in state['tasks'] if t['task_id'] in (parent,child,leaf)]==[1,2,3]
    assert report['individual'][parent]['today_us']==10*M and report['cumulative'][parent]['today_us']==30*M
    assert report['project_direct'][root]['today_us']==30*M
    assert report['projects'][root]['today_us']==report['application']['today_us']==60*M
    rows,_,_=ui.main_projection(state)
    assert len([k for k in rows if k.startswith('project:')])==13
    assert all('Unassigned' not in r['text'] for r in rows.values())


def test_whole_branch_and_project_root_movement_preserve_work(client):
    h=client;p=h.project();deep=h.project(p);q=h.project();root=h.task(deep);h.dated(root,'0:10');leaf=h.task(deep,root);h.dated(leaf,'0:20')
    before=h.facts();h.send('move_task_branch',**h.move_args(root,q));after=h.facts()
    assert after['work_entries']==before['work_entries'] and after['work_revisions']==before['work_revisions']
    assert {t['project_id'] for t in after['tasks']}=={q}
    h.send('move_project_subtree',**ui.ProjectMoveReview(h.state(),deep).arguments(None))
    assert next(p for p in h.state()['projects'] if p['project_id']==deep)['parent_project_id'] is None
    h.send('move_task_branch',expect='unchanged',**h.move_args(root,q))
    h.send('rename_task',task_id=root,expected_version=2,name='Renamed')
    assert h.state()['report']['application']['today_us']==30*M


@pytest.mark.parametrize('bad',['null','omitted','duplicate','stale','archive','ancestry'])
def test_move_refusals_preserve_complete_facts(client,bad):
    h=client;p=h.project();q=h.project();root=h.task(p);h.task(p,root);args=h.move_args(root,q)
    if bad=='null':args.update(destination_project_id=None,expected_destination_project_version=None,reviewed_destination_project_ancestry=[])
    elif bad=='omitted':args['reviewed_subtree'].pop()
    elif bad=='duplicate':args['reviewed_subtree'].append(dict(args['reviewed_subtree'][0]))
    elif bad=='stale':args['reviewed_subtree'][0]['expected_version']=999
    elif bad=='archive':h.lifecycle('project',q)
    else:args['reviewed_source_project_ancestry']=[]
    h.send('move_task_branch',expect='rejected',**args)


def test_archive_inheritance_and_active_descendant_protection(client):
    h=client;p=h.project();deep=h.project(p);root=h.task(deep);leaf=h.task(deep,root)
    h.lifecycle('task',leaf);h.lifecycle('project',p);h.lifecycle('project',p,False)
    rows={t['task_id']:t for t in h.state()['tasks']}
    assert rows[leaf]['explicit_archived'] and rows[leaf]['effective_archived'] and not rows[root]['effective_archived']
    h.lifecycle('task',leaf,False);h.send('start_timer',task_id=leaf,entry_id=uid(),expected_task_version=3)
    h.lifecycle('project',p,expect='rejected')
    h.lifecycle('task',root,expect='rejected')


def test_template_management_apply_and_real_project_parent(client):
    h=client;p=h.project(h.project());parent=h.task(p);d=h.template()
    r,out=h.send('apply_template',**h.apply_args(d,p,parent))
    tasks=h.state()['tasks'];created={t['task_id'] for t in out.result['created_tasks']}
    assert len(created)==2 and len(tasks)==3 and {t['project_id'] for t in tasks}=={p}
    assert max(t['depth'] for t in tasks)==3
    h.send('edit_template',template_id=d['template_id'],expected_version=1,name='Edited',nodes=d['nodes'])
    assert next(x for x in h.facts()['committed_requests'] if x['request_id']==r.request_id)['result_bytes']==canonical(out.result)
    current=h.state()['templates'][0]
    h.send('duplicate_template',template_id=uid(),name='Copy',source_template_id=current['template_id'],expected_source_version=current['version'],reviewed_source=current,
        node_mapping=sorted([dict(node_id=n['node_id'],new_node_id=uid()) for n in current['nodes']],key=lambda r:r['node_id']))
    h.lifecycle('template',current['template_id']);h.lifecycle('template',current['template_id'],False)


@pytest.mark.parametrize('bad',['null','unknown','stale','mapping','depth','running','ancestry'])
def test_template_apply_refusals_are_atomic(client,bad):
    h=client;p=h.project();parent=h.task(p);d=h.template();args=h.apply_args(d,p)
    if bad=='null':args.update(destination_project_id=None,expected_destination_project_version=None,reviewed_destination_project_ancestry=[])
    elif bad=='unknown':args['destination_project_id']=uid()
    elif bad=='stale':args['expected_template_version']=99
    elif bad=='mapping':args['node_mapping'].append(dict(args['node_mapping'][0]))
    elif bad=='depth':args=h.apply_args(d,p,h.task(p,parent))
    elif bad=='running':
        args=h.apply_args(d,p,parent);h.send('start_timer',task_id=parent,entry_id=uid(),expected_task_version=1)
    else:args['reviewed_destination_project_ancestry']=[]
    h.send('apply_template',expect='rejected',**args)


def test_timer_switch_stop_correction_and_manual_revisions(client):
    h=client;p=h.project();first=h.task(p);second=h.task(p);entry=uid()
    start,_=h.send('start_timer',task_id=first,entry_id=entry,expected_task_version=1)
    h.send('correct_active_start',entry_id=entry,expected_version=1,date_text='2026-10-19',time_text='09:59',occurrence=None,comment='Earlier start')
    active=h.state()['active'];next_entry=uid()
    switch,_=h.send('switch_timer',expected_active_entry_id=entry,expected_active_version=2,next_task_id=second,next_entry_id=next_entry,expected_task_version=1)
    stop,_=h.send('stop_timer',entry_id=next_entry,expected_version=1)
    facts=h.facts();revisions={r['entry_id']:r for r in facts['work_revisions']}
    assert revisions[entry]['start_utc_us']==active['start_utc_us'] and revisions[entry]['stop_utc_us']==switch.action_utc_us
    assert revisions[next_entry]['start_utc_us']==switch.action_utc_us and revisions[next_entry]['stop_utc_us']==stop.action_utc_us
    key=h.dated(first);h.send('edit_date_only_work',task_id=first,entry_id=key,expected_revision=1,work_date='2026-10-19',duration_text='0:20',comment='Correction')
    h.send('delete_work_entry',task_id=first,entry_id=key,expected_revision=2,comment='Remove current contribution')
    timed=uid();args=dict(task_id=first,entry_id=timed,start_date='2026-10-19',start_time='09:00',end_date='2026-10-19',end_time='09:15',start_occurrence=None,end_occurrence=None,comment='Manual')
    h.send('add_timed_work',**args);h.send('edit_closed_timed_work',**dict(args,expected_revision=1,end_time='09:30'))
    assert h.state()['active'] is None
    assert [r['revision'] for r in h.facts()['work_revisions'] if r['entry_id']==key]==[1,2,3]


def test_standalone_assignment_real_destinations_and_exact_noop(client):
    h=client;p=h.project();q=h.project();key=h.task(p);h.dated(key);state=h.state()
    def args(destination,version):
        return dict(task_id=key,project_id=destination,expected_version=version,
                    reviewed_source_project_ancestry=ui.ancestry(h.state(),next(t for t in h.state()['tasks'] if t['task_id']==key)['project_id']),
                    reviewed_destination_project_ancestry=ui.ancestry(h.state(),destination))
    h.send('assign_task_to_project',expect='unchanged',**args(p,1))
    h.send('assign_task_to_project',expect='rejected',**args(None,1))
    reviewed=args(q,1);before=h.facts();h.send('assign_task_to_project',**reviewed)
    assert h.facts()['work_entries']==before['work_entries'] and h.facts()['work_revisions']==before['work_revisions']
    assert next(t for t in h.state()['tasks'] if t['task_id']==key)['project_id']==q
    h.send('assign_task_to_project',expect='rejected',**reviewed)
    h.send('assign_task_to_project',expect='unchanged',**args(q,2))
