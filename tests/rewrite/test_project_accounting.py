"""Authoritative engine attribution plus independent schema-4 project totals."""
from copy import deepcopy
import sys

import pytest

from chronicle.accounting import calculate
from chronicle.project_accounting import project_report
from chronicle.timekeeping import load_zone
from conftest import NOW, uid
from test_accounting import stamp
from test_project_forest import project
from test_project_movement import adapter, populated, moved, snapshot
from test_schema4_history import key

M=60_000_000


def task(identity,group=None,parent=None,archived=0):
    return dict(task_id=identity,project_id=group,parent_task_id=parent,is_archived=archived,name='Duplicate')


def dated(identity,amount,day='2026-10-19'):
    return dict(task_id=identity,kind='date_only',work_date=day,duration_us=amount)


def amounts(today,week=None):
    return dict(today_us=today,week_us=today if week is None else week)


def projected(tasks,projects,work=(),active=None,cutoff=NOW,zone='America/Chicago'):
    report=calculate(tasks,list(work),active,cutoff,load_zone(zone))
    before=deepcopy((report,tasks,projects,work,active))
    result=project_report(report,tasks,projects)
    assert (report,tasks,projects,work,active)==before
    assert result['cutoff_utc_us']==cutoff
    for field in ('tasks','individual','cumulative','application','today','week_start','week_end'):
        assert result[field]==report[field]
    return report,result


def test_mixed_task_individuals_archived_history_and_project_subtotals_count_once():
    projects=[project(key(1)),project(key(2),key(1),1),project(key(3),key(2)),project(key(4)),project(key(5))]
    tasks=[task(key(101),key(1)),task(key(102),key(1),key(101)),task(key(103),key(1),key(102)),
           task(key(104),key(3),archived=1),task(key(105),key(2)),task(key(106))]
    work=[dated(key(k),n*M) for k,n in ((101,5),(102,7),(103,11),(104,13),(105,17),(106,19))]
    work.append(dated(key(104),23*M,'2026-10-24'))
    report,result=projected(tasks,projects,work)
    assert result['project_direct']=={key(1):amounts(23*M),key(2):amounts(17*M),key(3):amounts(13*M,36*M),
                                     key(4):amounts(0),key(5):amounts(0),None:amounts(19*M)}
    assert result['projects']=={key(1):amounts(53*M,76*M),key(2):amounts(30*M,53*M),key(3):amounts(13*M,36*M),
                                key(4):amounts(0),key(5):amounts(0),None:amounts(19*M)}
    assert result['application']==amounts(72*M,95*M)
    assert result['individual'][key(101)]==amounts(5*M)
    assert result['cumulative'][key(101)]==amounts(23*M)
    assert result['cumulative'][key(102)]==amounts(18*M)
    assert result['tasks'][key(104)]['daily_us']=={'2026-10-19':13*M,'2026-10-24':23*M}
    # Result is detached, including original fields, without touching input.
    result['tasks'][key(101)]['daily_us'].clear()
    assert report['tasks'][key(101)]['daily_us']=={'2026-10-19':5*M}


@pytest.mark.parametrize('where',['root direct','child only','both','neither','unassigned'])
def test_empty_and_direct_child_only_groups(where):
    projects=[project(key(1)),project(key(2),key(1))]
    tasks=[task(key(101),key(1)),task(key(102),key(2)),task(key(103))]
    work=[]
    if where in ('root direct','both'):work.append(dated(key(101),2*M))
    if where in ('child only','both'):work.append(dated(key(102),3*M))
    if where=='unassigned':work.append(dated(key(103),5*M))
    _,result=projected(tasks,projects,work)
    expected={'root direct':(2,2,0,0),'child only':(0,3,3,0),'both':(2,5,3,0),
              'neither':(0,0,0,0),'unassigned':(0,0,0,5)}[where]
    direct,root,child,unassigned=expected
    assert result['project_direct'][key(1)]==amounts(direct*M)
    assert result['projects'][key(1)]==amounts(root*M)
    assert result['projects'][key(2)]==amounts(child*M)
    assert result['projects'][None]==amounts(unassigned*M)
    assert result['application']==amounts((root+unassigned)*M)


@pytest.mark.parametrize('depth',[5,sys.getrecursionlimit()+100])
def test_project_depth_exceeds_three_and_python_recursion_limit(depth):
    ids=[uid() for _ in range(depth)]
    projects=[project(k,ids[i-1] if i else None) for i,k in enumerate(ids)]
    tasks=[task(key(101),ids[-1])]
    before=deepcopy(projects)
    _,result=projected(tasks,projects,[dated(key(101),1)])
    assert all(result['projects'][k]==amounts(1) for k in ids)
    assert result['project_direct'][ids[0]]==amounts(0)
    assert result['project_direct'][ids[-1]]==amounts(1)
    assert result['application']==amounts(1) and projects==before


@pytest.mark.parametrize('start,stop,zone,today,days,expected',[
    ('2026-10-19T23:59:59.999999-05:00','2026-10-20T00:00:00.000001-05:00','America/Chicago',1,{'2026-10-19':1,'2026-10-20':1},2),
    ('2026-03-08T01:30:00-06:00','2026-03-08T03:30:00-05:00','America/Chicago',60*M,{'2026-03-08':60*M},60*M),
    ('2026-11-01T01:30:00-05:00','2026-11-01T01:30:00-06:00','America/Chicago',60*M,{'2026-11-01':60*M},60*M),
    ('2026-10-04T01:45:00+10:30','2026-10-04T03:00:00+11:00','Australia/Lord_Howe',45*M,{'2026-10-04':45*M},45*M),
])
def test_projection_reuses_real_midnight_dst_and_nonhour_attribution(start,stop,zone,today,days,expected):
    tasks=[task(key(101),key(2))];projects=[project(key(1)),project(key(2),key(1))]
    work=[dict(task_id=key(101),kind='timed',start_utc_us=stamp(start),stop_utc_us=stamp(stop))]
    _,result=projected(tasks,projects,work,cutoff=stamp(stop),zone=zone)
    assert result['tasks'][key(101)]['daily_us']==days
    assert result['project_direct'][key(2)]==amounts(today,expected)
    assert result['projects'][key(1)]==amounts(today,expected)


def test_date_only_local_date_and_coordinated_active_cutoff():
    cutoff=stamp('2026-10-20T00:30:00+00:00')  # Still October 19 in Chicago.
    tasks=[task(key(101),key(2)),task(key(102))];projects=[project(key(1)),project(key(2),key(1))]
    work=[dated(key(101),17),dated(key(102),23,'2026-10-20')]
    active=dict(task_id=key(101),start_utc_us=cutoff-31)
    _,result=projected(tasks,projects,work,active,cutoff)
    assert result['today']=='2026-10-19'
    assert result['projects'][key(1)]==amounts(48)
    assert result['projects'][None]==amounts(0,23)
    assert result['application']==amounts(48,71)


def test_real_project_reparent_changes_only_live_project_rollups(populated):
    a=populated;before=snapshot(a)
    work=[dated(key(101),10*M),dated(key(102),20*M)]
    report,first=projected(before['tasks'],before['projects'],work)
    frozen,_=moved(a)
    after=snapshot(a)
    second=project_report(report,after['tasks'],after['projects'])
    assert after['tasks']==before['tasks']
    assert first['projects'][key(1)]==amounts(30*M) and first['projects'][key(2)]==amounts(0)
    assert second['projects'][key(1)]==amounts(0) and second['projects'][key(2)]==amounts(30*M)
    assert first['project_direct']==second['project_direct']
    for field in ('tasks','individual','cumulative','application','cutoff_utc_us'):
        assert second[field]==first[field]
    assert report['cutoff_utc_us']==NOW and frozen.action_utc_us==NOW+100
    for table in before.keys()-{'projects','committed_requests','sqlite_sequence'}:assert before[table]==after[table]


@pytest.mark.parametrize('bad',['missing project','malformed project','cycle','duplicate project','missing task parent','task cycle','task depth','cross project','duplicate task','archive flag'])
def test_invalid_current_complete_forest_refuses(bad):
    projects=[project(key(1)),project(key(2),key(1))]
    tasks=[task(key(101),key(2)),task(key(102),key(2),key(101))]
    report=calculate(tasks,[],None,NOW,load_zone('UTC'))
    if bad=='missing project':tasks[0]['project_id']=uid()
    if bad=='malformed project':projects[0]['project_id']='BAD'
    if bad=='cycle':projects[0]['parent_project_id']=key(2)
    if bad=='duplicate project':projects.append(dict(projects[0]))
    if bad=='missing task parent':tasks[0]['parent_task_id']=uid()
    if bad=='task cycle':tasks[0]['parent_task_id']=key(102)
    if bad=='task depth':tasks.extend([task(key(103),key(2),key(102)),task(key(104),key(2),key(103))])
    if bad=='cross project':tasks[1]['project_id']=key(1)
    if bad=='duplicate task':tasks.append(dict(tasks[0]))
    if bad=='archive flag':tasks[0]['is_archived']=True
    with pytest.raises(ValueError):project_report(report,tasks,projects)


@pytest.mark.parametrize('bad',['none','missing field','cutoff','coverage','individual coverage','task amount','cumulative unavailable','application','float','bool','negative','overflow','unavailable amount'])
def test_invalid_or_unavailable_report_never_becomes_zero(bad):
    projects=[project(key(1))];tasks=[task(key(101),key(1))]
    report=calculate(tasks,[dated(key(101),1)],None,NOW,load_zone('UTC'))
    if bad=='none':report=None
    if bad=='missing field':del report['individual']
    if bad=='cutoff':report['cutoff_utc_us']=True
    if bad=='coverage':report['tasks'].clear()
    if bad=='individual coverage':report['individual'][uid()]=amounts(0)
    if bad=='task amount':report['tasks'][key(101)]['today_us']=0
    if bad=='cumulative unavailable':report['cumulative'][key(101)]=None
    if bad=='application':report['application']['today_us']=0
    if bad=='float':report['individual'][key(101)]['today_us']=1.0
    if bad=='bool':report['individual'][key(101)]['today_us']=True
    if bad=='negative':report['individual'][key(101)]['today_us']=-1
    if bad=='overflow':report['individual'][key(101)]['today_us']=2**63
    if bad=='unavailable amount':report['individual'][key(101)]['today_us']=None
    before=deepcopy((report,tasks,projects))
    with pytest.raises(ValueError):project_report(report,tasks,projects)
    assert (report,tasks,projects)==before


def test_checked_aggregation_rejects_sum_overflow():
    projects=[project(key(1)),project(key(2),key(1))];tasks=[task(key(101),key(1)),task(key(102),key(2))]
    report=calculate(tasks,[],None,NOW,load_zone('UTC'))
    for name in ('tasks','individual','cumulative'):
        report[name][key(101)].update(amounts(2**63-1))
        report[name][key(102)].update(amounts(1))
    report['application']=amounts(2**63-1)
    with pytest.raises(ValueError,match='Application sum'):project_report(report,tasks,projects)


def test_empty_forest_and_unassigned_are_virtual_and_source_engine_remains_flat():
    tasks=[task(key(101))]
    report,result=projected(tasks,[],[dated(key(101),123)])
    assert result['project_direct']==result['projects']=={None:amounts(123)}
    assert report['projects']=={None:amounts(123)} and 'project_direct' not in report
    report,result=projected([], [project(key(1))])
    assert report['projects']=={None:amounts(0)}
    assert result['projects']=={None:amounts(0),key(1):amounts(0)}
