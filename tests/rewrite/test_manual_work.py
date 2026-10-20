"""Real Stage 2A creation, typed shape and transaction evidence."""
from dataclasses import replace
from datetime import datetime
import sqlite3

import pytest

from chronicle.records import Request
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import parse_duration, to_us
from conftest import NOW, uid

M = 60_000_000
H = 60 * M


def stamp(text):
    return to_us(datetime.fromisoformat(text))


def facts(store):
    c = store._probe()
    try:
        return {table: [tuple(r) for r in c.execute(f'SELECT * FROM {table} ORDER BY 1,2')]
                for table in ('dataset_meta','tasks','projects','work_entries','work_revisions',
                              'active_timer','active_start_corrections','committed_requests')}
    finally:
        c.close()


def dated(service, task, day='2026-10-19', duration='1:30', **kwargs):
    entry = uid()
    outcome = service.add_date_only_work(task, entry, day, duration,
                                        request_id=uid(), action_utc_us=NOW, **kwargs)
    assert outcome.status == 'committed', outcome
    return entry


def timed(service, task, start_day='2026-10-19', start='08:00', end_day='2026-10-19', end='09:00',
          now=NOW, **kwargs):
    entry = uid()
    outcome = service.add_timed_work(task, entry, start_day, start, end_day, end,
                                    request_id=uid(), action_utc_us=now, **kwargs)
    assert outcome.status == 'committed', outcome
    return entry


def test_initial_mixed_records_are_typed_atomic_and_detached(service, task, store):
    a, b = timed(service, task, comment='timed'), dated(service, task, duration='125:45', comment='dated')
    records = {r['entry_id']: dict(r) for r in store.connection.execute('SELECT * FROM work_entries')}
    assert records[a]['kind'] == 'timed' and records[a]['original_start_utc_us'] is not None
    assert records[b]['kind'] == 'date_only' and records[b]['original_start_utc_us'] is None
    for entry in (a,b):
        detail = service.read_work_entry_revisions(entry)
        assert detail['entry']['task_id'] == task and detail['entry']['current_revision'] == 1
        row = detail['revisions'][0]
        assert row['request_id'] == records[entry]['created_request_id']
        assert row['audit_utc_us'] == NOW and row['revision'] == 1
        assert store.connection.execute('SELECT 1 FROM committed_requests WHERE request_id=?',(row['request_id'],)).fetchone()
    row = service.read_work_entry_revisions(b)['revisions'][0]
    assert row['duration_us'] == (125*60+45)*M
    assert row['work_date'] == '2026-10-19' and row['start_utc_us'] is row['stop_utc_us'] is None


@pytest.mark.parametrize('text', ['', '0:00','-1:30','1.5','1:2','1:60','1:30:00','1:30.5','a:30',None,True,'9'*100+':00'])
def test_bad_duration_rejects_without_any_facts(service, task, store, text):
    before = facts(store)
    out = service.add_date_only_work(task,uid(),'2026-10-19',text,request_id=uid(),action_utc_us=NOW)
    assert out.status == 'rejected'
    assert facts(store) == before


@pytest.mark.parametrize('text,expected', [(' 0:15 ',15*M),('14:00',14*H),('125:45',125*H+45*M),('0001:00',H)])
def test_exact_duration_inputs(text,expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize('day', ['2026-02-30','2026-1-01','20260101','0000-01-01',None,True])
def test_invalid_civil_dates_are_not_sql_string_validation(service,task,store,day):
    before = facts(store)
    assert service.add_date_only_work(task,uid(),day,'1:00',request_id=uid(),action_utc_us=NOW).status == 'rejected'
    assert facts(store) == before


@pytest.mark.parametrize('changes', [dict(start_time='08:00:01'),dict(start_time='08:00.1'),
    dict(end_time='08:00'),dict(end_time='07:00'),dict(end_time='11:00'),
    dict(start_date='2026-03-08',start_time='02:30'),
    dict(start_date='2026-11-01',start_time='01:30',end_date='2026-11-01',end_time='02:00')])
def test_new_timed_validation_is_pure(service,task,store,changes):
    a=dict(task_id=task,entry_id=uid(),start_date='2026-10-19',start_time='08:00',
           end_date='2026-10-19',end_time='09:00',start_occurrence=None,end_occurrence=None,comment='')
    a.update(changes)
    before=facts(store)
    assert service.execute(Request.make(uid(),store.dataset_id,'add_timed_work',NOW,**a)).status == 'rejected'
    assert facts(store)==before


def test_explicit_repeat_and_non_hour_transition(service,task,store,tmp_path):
    cutoff=stamp('2026-11-01T10:00:00+00:00')
    entry=timed(service,task,'2026-11-01','01:30','2026-11-01','01:30',now=cutoff,
                start_occurrence='first',end_occurrence='second')
    r=service.read_work_entry_revisions(entry)['revisions'][0]
    assert r['stop_utc_us']-r['start_utc_us']==H
    from chronicle.services import TimerService
    with_store=SQLiteStore(tmp_path/'lord-howe',create=True,timezone='Australia/Lord_Howe')
    try:
        s=TimerService(with_store); t=uid()
        s.create_task(t,'Half hour',request_id=uid(),action_utc_us=NOW)
        e=timed(s,t,'2026-04-05','01:45','2026-04-05','01:45',start_occurrence='first',end_occurrence='second')
        r=s.read_work_entry_revisions(e)['revisions'][0]
        assert r['stop_utc_us']-r['start_utc_us']==30*M
    finally: with_store.close()


@pytest.mark.parametrize('boundary', ['identity','revision','reference','receipt'])
def test_initial_partial_writes_roll_back_and_retry_exactly(service,task,store,make_request,boundary):
    request=make_request('add_date_only_work',task_id=task,entry_id=uid(),work_date='2026-10-19',duration_text='1:00',comment='')
    original=store.connection; before=facts(store)
    prefixes={'identity':'INSERT INTO work_entries','revision':'INSERT INTO work_revisions',
              'reference':'UPDATE work_entries','receipt':'INSERT INTO committed_requests'}
    class Fault:
        def __getattr__(self,name): return getattr(original,name)
        def execute(self,sql,*args):
            result=original.execute(sql,*args)
            if sql.startswith(prefixes[boundary]): raise sqlite3.OperationalError('injected partial write')
            return result
    store.connection=Fault()
    assert service.execute(request).status=='rolled_back'
    assert facts(store)==before
    result=service.execute(request)
    assert result.status=='committed'
    assert service.execute(request).result==result.result
    assert service.execute(replace(request,action_utc_us=NOW+1)).status=='rejected'
    assert len(facts(store)['work_revisions'])==1


def test_unknown_deleted_task_and_duplicate_uuid_do_not_create_orphans(service,task,store):
    e=dated(service,task)
    for target,entry in ((uid(),uid()),(task,e)):
        before=facts(store)
        result=service.add_date_only_work(target,entry,'2026-10-19','1:00',request_id=uid(),action_utc_us=NOW)
        assert result.status in ('rejected','rolled_back') and facts(store)==before
    service.read_current_state(cutoff_utc_us=NOW)  # Reconnect after the rejected identity collision.
    store.connection.execute('UPDATE tasks SET is_deleted=1 WHERE task_id=?',(task,))
    before=facts(store)
    assert service.add_date_only_work(task,uid(),'2026-10-19','1:00',request_id=uid(),action_utc_us=NOW).status=='rejected'
    assert facts(store)==before


@pytest.mark.parametrize('change',[
    {'kind':'unsupported'}, {'original_start_utc_us':NOW}, {'current_revision':None}])
def test_date_only_identity_shape_constraints(service,task,store,change):
    e=dated(service,task)
    # Identity is immutable, including attempted cross-kind conversion.
    before=facts(store)
    column,value=next(iter(change.items()))
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(f'UPDATE work_entries SET {column}=? WHERE entry_id=?',(value,e))
    assert facts(store)==before


@pytest.mark.parametrize('change',[
    dict(kind='timed'), dict(start_utc_us=NOW-H), dict(stop_utc_us=NOW),
    dict(duration_us=0), dict(duration_us=-1), dict(duration_us=None), dict(work_date=None),
    dict(work_date='2026-1-01'), dict(is_deleted=1,duration_us=2*H),dict(revision=3)])
def test_bad_revision_shapes_and_successors_reject_direct_sql(service,task,store,change):
    e=dated(service,task)
    row=service.read_work_entry_revisions(e)['revisions'][0]
    row.update(revision=2,request_id=row['request_id']);row.update(change)
    columns=','.join(row); placeholders=','.join('?' for _ in row)
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(f'INSERT INTO work_revisions({columns}) VALUES({placeholders})',tuple(row.values()))


def test_active_date_only_wrong_owner_and_revision_kind_foreign_keys(service,task,store):
    e=dated(service,task)
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute('INSERT INTO active_timer(singleton,entry_id,task_id,start_utc_us,version) VALUES(1,?,?,?,1)',(e,task,NOW))
    row=service.read_work_entry_revisions(e)['revisions'][0]
    row.update(kind='timed',revision=2,start_utc_us=NOW-H,stop_utc_us=NOW,work_date=None,duration_us=None)
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(f"INSERT INTO work_revisions({','.join(row)}) VALUES({','.join('?' for _ in row)})",tuple(row.values()))
    with pytest.raises(sqlite3.IntegrityError,match='immutable'):
        store.connection.execute('UPDATE work_entries SET task_id=? WHERE entry_id=?',(uid(),e))


def test_unknown_schema_objects_refuse_without_recreation(store):
    store.connection.execute('CREATE TABLE unexpected(value TEXT) STRICT')
    directory=store.directory;store.close()
    before={p.name:p.read_bytes() for p in directory.iterdir()}
    with pytest.raises(ValueError,match='Unexpected schema'):
        SQLiteStore(directory)
    assert {p.name:p.read_bytes() for p in directory.iterdir()}==before


def test_duration_limit_has_no_arbitrary_hour_cap():
    maximum=(2**63-1)//M
    assert parse_duration(f'{maximum//60}:{maximum%60:02d}')==maximum*M
    with pytest.raises(ValueError):parse_duration(f'{maximum//60}:{maximum%60+1:02d}')


def test_backward_looking_repeated_wall_time_is_ordered_in_utc(service,task):
    e=timed(service,task,'2026-11-01','01:45','2026-11-01','01:15',
            now=stamp('2026-11-01T10:00:00+00:00'),start_occurrence='first',end_occurrence='second')
    r=service.read_work_entry_revisions(e)['revisions'][0]
    assert r['stop_utc_us']-r['start_utc_us']==30*M
