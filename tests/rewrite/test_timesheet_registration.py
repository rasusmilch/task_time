"""Immutable SQLite exports, exact requests, faults and bounded process interruption."""
from dataclasses import replace
import hashlib
import sqlite3

import pytest

from chronicle.records import Request
from chronicle.sqlite_store import SQLiteStore,EXPORT_TABLES
from chronicle.services import TimerService
from conftest import NOW,uid
from test_timesheet_candidate import preview,case_c
from test_manual_work import dated,facts
from test_services import FaultConnection


def request(store,candidate):
    return Request.make(uid(),store.dataset_id,'register_timesheet_export',NOW,candidate=candidate.content())


def exports(store):
    store._recover_connection()
    return {t:[tuple(r) for r in store.connection.execute(f'SELECT * FROM {t} ORDER BY 1,2')] for t in EXPORT_TABLES}


def test_register_exact_atomic_frozen_recovery_and_later_changes(service,task,store,monkeypatch):
    case_c(service,task)
    c=preview(service,period='custom',start_date='2026-10-20',end_date='2026-10-20')
    r=request(store,c)
    service.rename_task(task,'New name',expected_version=1,request_id=uid(),action_utc_us=NOW)
    service.set_week_start(1,expected_week_start=6,request_id=uid(),action_utc_us=NOW)
    dated(service,task,duration='3:00')
    before_registration=facts(store)
    with monkeypatch.context() as m:
        m.setattr('chronicle.timesheet.calculate_daily',lambda *a,**k:(_ for _ in ()).throw(AssertionError('registration recalculated')))
        result=service.execute(r)
    assert result.status=='committed' and result.result=={'export_id':c.export_id,'report_sha256':c.report_sha256}
    after=facts(store)
    assert all(after[t]==before_registration[t] for t in before_registration if t!='committed_requests')
    assert len(after['committed_requests'])==len(before_registration['committed_requests'])+1
    assert [len(v) for v in exports(store).values()]==[1,1,7,1]
    assert service.read_registered_timesheet_export(c.export_id)==c
    listed=service.list_registered_timesheet_exports()
    assert listed[0]['export_id']==c.export_id and listed[0]['tasks']==c.tasks
    assert service.execute(r).result==result.result
    assert service.execute(replace(r,action_utc_us=NOW+1)).status=='rejected'
    assert len(service.list_registered_timesheet_exports())==1
    directory=store.directory;store.close()
    reopened=SQLiteStore(directory)
    try:
        s=TimerService(reopened)
        assert s.read_registered_timesheet_export(c.export_id)==c
        # Historical exact bytes are independent of a later renderer implementation.
        with monkeypatch.context() as m:
            m.setattr('chronicle.timesheet.render',lambda c:'changed renderer\n')
            assert s.read_registered_timesheet_export(c.export_id).report_utf8==c.report_utf8
            assert s.execute(r).status=='committed'
    finally:reopened.close()


@pytest.mark.parametrize('table',EXPORT_TABLES)
@pytest.mark.parametrize('verb',['UPDATE','DELETE'])
def test_direct_export_evidence_update_delete_reject(service,task,store,table,verb):
    c=preview(service);service.register_timesheet_export(c,request_id=uid(),action_utc_us=NOW)
    with pytest.raises(sqlite3.IntegrityError,match='immutable'):
        store.connection.execute(f'{verb} FROM {table}' if verb=='DELETE' else f'UPDATE {table} SET export_id=export_id')


@pytest.mark.parametrize('table',EXPORT_TABLES[1:])
def test_sealed_children_cannot_be_appended(service,task,store,table):
    c=preview(service);service.register_timesheet_export(c,request_id=uid(),action_utc_us=NOW)
    with pytest.raises(sqlite3.IntegrityError,match='sealed'):
        store.connection.execute(f'INSERT INTO {table} SELECT * FROM {table}')


@pytest.mark.parametrize('damage',['missing_basis','extra_basis','missing_cell','extra_cell','suggestion','actual_display',
    'text','digest','date','uuid','scope','dataset','destination','float','bool'])
def test_tampered_complete_candidate_cannot_commit_any_subset(service,task,store,damage):
    case_c(service,task);c=preview(service);data=c.content()
    if damage=='missing_basis':data['basis'].pop()
    elif damage=='extra_basis':data['basis'].append(data['basis'][0])
    elif damage=='missing_cell':data['cells'].pop()
    elif damage=='extra_cell':data['cells'].append(data['cells'][0])
    elif damage=='suggestion':data['basis'][1]['suggested_quarters']+=1
    elif damage=='actual_display':data['cells'][1]['actual_hundredths']+=1
    elif damage=='text':
        data['report_text']+='forged\n';data['report_sha256']=hashlib.sha256(data['report_text'].encode()).hexdigest()
    elif damage=='digest':data['report_sha256']='0'*64
    elif damage=='date':data['start_date']='2026-02-30'
    elif damage=='uuid':data['tasks'][0]['task_id']='bad'
    elif damage=='scope':data['scope_kind']='selected'
    elif damage=='dataset':data['dataset_id']=uid()
    elif damage=='destination':data['preferred_destination']='bad\x00path'
    elif damage=='float':data['cells'][0]['actual_us']=0.0
    elif damage=='bool':data['cells'][0]['actual_us']=False
    before=facts(store)
    if damage=='float':
        with pytest.raises(ValueError,match='no floats'):service.register_timesheet_export(data,request_id=uid(),action_utc_us=NOW)
    else: assert service.register_timesheet_export(data,request_id=uid(),action_utc_us=NOW).status=='rejected'
    assert facts(store)==before and all(not v for v in exports(store).values())


def test_preferred_path_is_frozen_and_registration_creates_no_file(service,task,store,tmp_path):
    path=tmp_path/'not-published.txt';c=replace(preview(service),preferred_destination=str(path))
    assert service.register_timesheet_export(c,request_id=uid(),action_utc_us=NOW).status=='committed'
    assert service.read_registered_timesheet_export(c.export_id).preferred_destination==str(path)
    assert not path.exists()


@pytest.mark.parametrize('after',[False,True])
def test_failed_commit_never_uses_uncommitted_receipt(service,task,store,after):
    c=preview(service);r=request(store,c);before=facts(store)
    fault=FaultConnection(store.connection,after=after);store.connection=fault
    out=service.execute(r)
    assert out.status==('committed' if after else 'rolled_back')
    assert fault.transaction_at_commit and out.error
    assert service.reconcile_request(r).status==('committed' if after else 'absent')
    if not after:
        assert all(not v for v in exports(store).values()) and facts(store)==before
    assert service.execute(r).status=='committed' and service.read_registered_timesheet_export(c.export_id)==c


def test_ambiguous_registration_reuses_same_request_after_new_work(service,task,store,monkeypatch):
    c=preview(service);r=request(store,c)
    store.connection=FaultConnection(store.connection,after=True)
    with monkeypatch.context() as m:
        m.setattr(store,'_probe',lambda:(_ for _ in ()).throw(OSError('probe unavailable')))
        result=service.execute(r)
        assert result.status=='unverified' and 'probe unavailable' in ' '.join(result.error.__notes__)
    newer=dated(service,task,duration='2:00');before=facts(store)
    assert service.reconcile_request(r).status=='committed'
    assert service.execute(r).status=='committed' and facts(store)==before
    assert service.read_registered_timesheet_export(c.export_id)==c
    assert service.read_work_entry_revisions(newer)['revisions'][0]['duration_us']>0


@pytest.mark.parametrize('phase',['tasks','basis','cells','master','receipt','commit_ready','committed'])
def test_process_death_export_transaction_is_atomic(tmp_path,phase):
    from test_interruptions import paused_child,TRANSACTION_CHILD,frozen_json
    directory=tmp_path/'interrupted-export';store=SQLiteStore(directory,create=True,timezone='America/Chicago')
    s=TimerService(store);task=uid();s.create_task(task,'A',request_id=uid(),action_utc_us=NOW);case_c(s,task)
    c=preview(s);r=request(store,c);before=facts(store);store.close()
    table={'tasks':'tasks','basis':'week_basis','cells':'cells','master':'exports'}.get(phase)
    code=TRANSACTION_CHILD
    if table:
        prefix='INSERT INTO timesheet_export_'+table if table!='exports' else 'INSERT INTO timesheet_exports'
        code=code.replace("phase == 'facts' and facts",f"phase == {phase!r} and sql.startswith({prefix!r})")
    with paused_child(code,directory,phase,frozen_json(r)): pass
    reopened=SQLiteStore(directory)
    try:
        s=TimerService(reopened)
        assert reopened.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert s.reconcile_request(r).status==('committed' if phase=='committed' else 'absent')
        if phase!='committed':assert facts(reopened)==before and all(not v for v in exports(reopened).values())
        assert s.execute(r).status=='committed'
        assert s.read_registered_timesheet_export(c.export_id)==c
        assert s.execute(r).status=='committed' and len(s.list_registered_timesheet_exports())==1
    finally:reopened.close()


@pytest.mark.parametrize('damage',['bytes','basis','cell','label','scope','orphan_basis'])
def test_corrupted_evidence_read_and_reopen_refuse_without_recalculation(service,task,store,damage):
    c=preview(service);r=request(store,c);assert service.execute(r).status=='committed'
    conn=store.connection
    if damage=='bytes':
        trigger='immutable_timesheet_exports_update';sql="UPDATE timesheet_exports SET report_utf8=x'ff'"
    elif damage=='basis':
        trigger='immutable_timesheet_export_week_basis_delete';sql='DELETE FROM timesheet_export_week_basis'
    elif damage=='cell':
        trigger='immutable_timesheet_export_cells_update';sql='UPDATE timesheet_export_cells SET suggested_quarters=1'
    elif damage=='label':
        trigger='immutable_timesheet_export_tasks_update';sql="UPDATE timesheet_export_tasks SET name='Forged'"
    elif damage=='orphan_basis':
        trigger='immutable_timesheet_export_week_basis_update';sql=f"UPDATE timesheet_export_week_basis SET task_id='{uid()}'"
    else:
        trigger='immutable_timesheet_exports_update';sql="UPDATE timesheet_exports SET selected_task_ids_json='[ ]'"
    conn.execute(f'DROP TRIGGER {trigger}');conn.execute('PRAGMA foreign_keys=OFF');conn.execute(sql)
    with pytest.raises((ValueError,UnicodeError)):
        service.read_registered_timesheet_export(c.export_id)
    directory=store.directory;store.close()
    with pytest.raises(ValueError):SQLiteStore(directory)
