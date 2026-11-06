"""Complete date/time History direction; detached values, no I/O or clock."""
from copy import deepcopy
from datetime import datetime
from uuid import UUID
import pytest

from chronicle.history_display import prepare_rows
from chronicle.work_history import build_history
from chronicle.timekeeping import load_zone,to_us,MIN_US,MAX_US

TASK=str(UUID(int=1))
M=60_000_000


def identity(n):return str(UUID(int=n))
def stamp(text):return to_us(datetime.fromisoformat(text))
CUTOFF=stamp('2027-01-01T00:00:00+00:00')


def work(n,start=None,stop=None,day=None):
    begin=stamp(start) if start is not None else None
    return dict(task_id=TASK,entry_id=identity(n),kind='date_only' if day else 'timed',revision=1,
        original_start_utc_us=begin,created_request_id=identity(100+n),request_id=identity(200+n),
        audit_utc_us=CUTOFF,comment='retained metadata',start_utc_us=begin,
        stop_utc_us=stamp(stop) if stop is not None else None,work_date=day,duration_us=15*M if day else None)


def rows(entries,zone='UTC',active=None,cutoff=CUTOFF):
    return build_history(entries,active,cutoff,load_zone(zone))


def prepared(observed,newest=True,zone='UTC'):
    before=deepcopy(observed)
    result=prepare_rows(observed,TASK,load_zone(zone),newest)
    assert observed==before
    for row,_ in result:
        assert row==next(r for r in before if (r['entry_id'],r['work_date'])==(row['entry_id'],row['work_date']))
    return result


@pytest.mark.parametrize('newest,expected',[(True,[30,20,10]),(False,[10,20,30])])
def test_same_day_segments_follow_selected_direction(newest,expected):
    observed=rows([work(n,f'2026-10-19T{hour}:00:00+00:00',f'2026-10-19T{hour}:15:00+00:00')
                   for n,hour in ((20,'10'),(30,'11'),(10,'09'))])
    assert [r['entry_id'] for r,_ in prepared(observed,newest)]==list(map(identity,expected))


@pytest.mark.parametrize('newest,expected',[(True,[40,30,20,10]),(False,[10,20,30,40])])
def test_dates_and_times_reverse_together(newest,expected):
    observed=rows([work(n,f'2026-10-{day}T{hour}:00:00+00:00',f'2026-10-{day}T{hour}:15:00+00:00')
                   for n,day,hour in ((20,'18','10'),(40,'19','10'),(10,'18','09'),(30,'19','09'))])
    assert [r['entry_id'] for r,_ in prepared(observed,newest)]==list(map(identity,expected))


@pytest.mark.parametrize('newest,expected',[
    (True,[(30,'2026-10-19'),(10,'2026-10-19'),(20,'2026-10-18'),(10,'2026-10-18'),(10,'2026-10-17')]),
    (False,[(10,'2026-10-17'),(10,'2026-10-18'),(20,'2026-10-18'),(10,'2026-10-19'),(30,'2026-10-19')])])
def test_linked_multiday_portions_keep_identity_endpoints_duration_and_flags(newest,expected):
    observed=rows([work(10,'2026-10-17T23:00:00+00:00','2026-10-19T01:00:00+00:00'),
        work(20,'2026-10-18T12:00:00+00:00','2026-10-18T13:00:00+00:00'),
        work(30,'2026-10-19T00:30:00+00:00','2026-10-19T00:40:00+00:00')])
    result=prepared(observed,newest)
    assert [(r['entry_id'],r['work_date']) for r,_ in result]==[(identity(n),day) for n,day in expected]
    linked=[r for r,_ in result if r['entry_id']==identity(10)]
    assert len(linked)==3 and sum(r['duration_us'] for r in linked)==26*60*M
    assert {r['link_identity'] for r in linked}=={(TASK,'timed',identity(10))}
    assert all(values[0]=='↔' for r,values in result if r['entry_id']==identity(10))


@pytest.mark.parametrize('newest,expected',[(True,[30,10,20]),(False,[10,20,30])])
def test_stop_timestamp_secondary_key_and_uuid_ties(newest,expected):
    observed=rows([work(n,'2026-10-19T10:00:00+00:00',f'2026-10-19T10:{end}:00+00:00')
                   for n,end in ((20,'15'),(30,'30'),(10,'15'))])
    assert [r['entry_id'] for r,_ in prepared(observed,newest)]==list(map(identity,expected))


@pytest.mark.parametrize('newest,expected',[(True,[30,10,20,40]),(False,[10,30,20,40])])
def test_date_only_always_follows_timed_with_uuid_order_and_no_clock(newest,expected):
    observed=rows([work(40,day='2026-10-19'),work(30,'2026-10-19T10:00:00+00:00','2026-10-19T10:15:00+00:00'),
        work(20,day='2026-10-19'),work(10,'2026-10-19T09:00:00+00:00','2026-10-19T09:15:00+00:00')])
    result=prepared(observed,newest)
    assert [r['entry_id'] for r,_ in result]==list(map(identity,expected))
    for row,values in result:
        if row['kind']=='date_only':
            assert row['start_utc_us'] is row['stop_utc_us'] is row['segment_start_utc_us'] is row['segment_stop_utc_us'] is None
            assert values[2:5]==('Date only','','')


@pytest.mark.parametrize('elapsed,newest,expected',[(0,True,[20,10]),(0,False,[10,20]),
    (5*M,True,[30,20,10]),(5*M,False,[10,20,30])])
def test_running_zero_and_nonzero_segments_keep_observed_start_position(elapsed,newest,expected):
    start=stamp('2026-10-19T10:00:00+00:00')
    active=dict(work(20,'2026-10-19T10:00:00+00:00'),version=1,start_utc_us=start)
    observed=rows([work(10,'2026-10-19T09:00:00+00:00','2026-10-19T09:15:00+00:00'),
        work(30,'2026-10-19T10:01:00+00:00','2026-10-19T10:02:00+00:00')],active=active,cutoff=start+elapsed if elapsed else start)
    result=prepared(observed,newest)
    assert [r['entry_id'] for r,_ in result]==list(map(identity,expected))
    running=next((r,v) for r,v in result if r['entry_id']==identity(20))
    assert running[0]['is_running'] and running[0]['duration_us']==elapsed and running[1][4].startswith('as of ')


@pytest.mark.parametrize('zone,first,second,offsets',[
    ('America/Chicago','2026-11-01T06:30:00+00:00','2026-11-01T07:30:00+00:00',('UTC-05:00','UTC-06:00')),
    ('Australia/Lord_Howe','2026-04-04T14:45:00+00:00','2026-04-04T15:15:00+00:00',('UTC+11:00','UTC+10:30')),
    ('America/Chicago','2026-03-08T07:55:00+00:00','2026-03-08T08:05:00+00:00',None),
    ('Asia/Kathmandu','2026-10-19T03:15:00+00:00','2026-10-19T03:45:00+00:00',None)])
@pytest.mark.parametrize('newest',[True,False])
def test_dst_and_non_hour_zone_order_uses_actual_utc(zone,first,second,offsets,newest):
    a=work(10,first);b=work(20,second)
    a['stop_utc_us']=a['start_utc_us']+5*M;b['stop_utc_us']=b['start_utc_us']+5*M
    result=prepared(rows([b,a],zone),newest,zone)
    assert [r['entry_id'] for r,_ in result]==list(map(identity,[20,10] if newest else [10,20]))
    if offsets:
        displays={r['entry_id']:v[3] for r,v in result}
        assert offsets[0] in displays[identity(10)] and offsets[1] in displays[identity(20)]


def test_epoch_zero_is_a_real_timestamp_not_missing():
    observed=rows([work(10,'1970-01-01T00:00:00+00:00','1970-01-01T00:01:00+00:00'),
                   work(20,'1970-01-01T00:01:00+00:00','1970-01-01T00:02:00+00:00')])
    assert [r['segment_start_utc_us'] for r,_ in prepared(observed)]==[M,0]


@pytest.mark.parametrize('field',['segment_start_utc_us','segment_stop_utc_us'])
@pytest.mark.parametrize('invalid',[None,True,'0',1.5,MIN_US-1,MAX_US+1,'missing'])
def test_missing_or_invalid_segment_timestamp_refuses_without_input_mutation(field,invalid):
    observed=rows([work(10,'2026-10-19T10:00:00+00:00','2026-10-19T10:15:00+00:00')])
    if invalid=='missing':del observed[0][field]
    else:observed[0][field]=invalid
    before=deepcopy(observed)
    with pytest.raises((ValueError,KeyError)):prepare_rows(observed,TASK,load_zone('UTC'),True)
    assert observed==before
