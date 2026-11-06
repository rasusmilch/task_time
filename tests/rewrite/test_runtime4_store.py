"""Production schema policy, exact transactions and protected runtime admission."""
from dataclasses import replace
import hashlib,json,sqlite3
import pytest
from chronicle.sqlite_store import SQLiteStore
from chronicle import schema_profiles,backup_restore as br
from chronicle.schema4_runtime_service import Schema4RuntimeService
from chronicle.records import Request,canonical
from chronicle.services import TimerService
from chronicle.timesheet_files import metadata
from runtime4_cases import runtime,Runtime,uid,NOW,M


def test_fresh_production_creation_exact_schema_profile_and_empty_readiness(runtime):
    s=runtime.store;c=s.connection
    assert s.schema_version==4 and c.execute('PRAGMA user_version').fetchone()[0]==4
    assert c.execute('PRAGMA application_id').fetchone()[0]==0x4348524E
    assert s._profile_values()==dict(journal_mode='delete',synchronous=3,foreign_keys=1)
    schema_profiles.verify_candidate(c)
    state=runtime.state()
    assert state['schema_version']==4 and state['semantic_verified'] and state['ordinary_startup_permitted']
    assert not state.get('candidate_verified') and not state['projects'] and not state['tasks'] and not state['templates']
    identity=s.dataset_id;s.close();reopened=SQLiteStore(s.directory)
    try:
        assert reopened.dataset_id==identity
        assert Schema4RuntimeService(reopened).read_current_state(cutoff_utc_us=NOW)['report']['application']['today_us']==0
    finally:reopened.close()


@pytest.mark.parametrize('damage',['schema3','foreign','future','missing trigger','bad metadata','bad receipt','wal'])
def test_clean_refusal_never_opens_original_for_writing(tmp_path,monkeypatch,damage):
    path=tmp_path/'source';s=SQLiteStore(path,create=True,timezone='America/Chicago',schema_version=3 if damage=='schema3' else 4)
    if damage=='schema3':
        assert TimerService(s).create_task(uid(),'Legacy',request_id=uid(),action_utc_us=NOW).status=='committed'
    elif damage=='bad receipt':
        Runtime(s).project()
        s.connection.execute('DROP TRIGGER immutable_committed_requests_update')
        s.connection.execute("UPDATE committed_requests SET result_bytes=?",(b'{}',))
        trigger=next(sql for sql in schema_profiles.schema_statements() if sql.startswith('CREATE TRIGGER immutable_committed_requests_update'))
        s.connection.execute(trigger)
    elif damage=='foreign':s.connection.execute('PRAGMA application_id=123')
    elif damage=='future':s.connection.execute('PRAGMA user_version=5')
    elif damage=='missing trigger':s.connection.execute('DROP TRIGGER active_only_open')
    elif damage=='bad metadata':s.connection.execute('UPDATE dataset_meta SET timezone=?',('Unknown/Nowhere',))
    elif damage=='wal':s.connection.execute('PRAGMA journal_mode=WAL')
    s.close();db=path/'chronicle.sqlite3';before=db.read_bytes();observed=metadata(db.stat())
    monkeypatch.setattr(SQLiteStore,'_connect',lambda self:pytest.fail('Refused source opened for writing'))
    with pytest.raises((ValueError,sqlite3.DatabaseError)):SQLiteStore(path)
    assert db.read_bytes()==before and metadata(db.stat())==observed


def test_ordinary_clean_admission_uses_bounded_checks_not_cold_fingerprint(runtime,monkeypatch):
    path=runtime.store.directory;runtime.store.close()
    monkeypatch.setattr(br,'_fingerprint',lambda *a:pytest.fail('Ordinary admission fingerprinted full image'))
    reopened=SQLiteStore(path)
    try:assert reopened.schema_version==4
    finally:reopened.close()


def test_exact_retry_conflict_stale_noop_and_receipt_bytes(runtime):
    h=runtime;p=h.project();key=h.task(p);old=h.requests[-1];before=h.facts()
    outcome=h.service.execute(old);assert outcome.status=='committed' and h.facts()==before
    assert h.service.execute(replace(old,action_utc_us=old.action_utc_us+1)).status=='rejected'
    assert h.facts()==before
    h.send('rename_task',task_id=key,name='Task',expected_version=1,expect='unchanged');assert h.facts()==before
    h.send('rename_task',task_id=key,name='Changed',expected_version=99,expect='rejected');assert h.facts()==before
    h.send('unrecognized_operation',expect='rejected');assert h.facts()==before
    with h.store.read_transaction() as c:
        for request in h.requests[:2]:
            row=c.execute('SELECT request_bytes,result_bytes,receipt_class FROM committed_requests WHERE request_id=?',(request.request_id,)).fetchone()
            assert row[0]==request.content() and canonical(json.loads(row[1]))==row[1] and row[2]=='administrative'
    assert h.service.execute(replace(old,dataset_id=uid(),request_id=uid())).status=='rejected'


class Fault:
    def __init__(self,c,mode):self.c=c;self.mode=mode;self.once=False;self.release=False
    def __getattr__(self,name):return getattr(self.c,name)
    def execute(self,sql,*args):
        if sql=='COMMIT' and not self.once:
            self.once=True
            if self.mode!='before':self.c.execute(sql,*args)
            raise OSError('Original COMMIT acknowledgement fault')
        return self.c.execute(sql,*args)


@pytest.mark.parametrize('mode,expected',[('before','rolled_back'),('after','committed')])
def test_real_transaction_commit_uncertainty_reconciles_exact_evidence(runtime,mode,expected):
    h=runtime;before=h.facts();original=h.store.connection
    h.store.connection=Fault(original,mode)
    request,result=h.send('create_project',expect=expected,project_id=uid(),name='Boundary')
    assert result.error and 'Original COMMIT' in str(result.error)
    if mode=='before':assert h.facts()==before
    else:
        retained=h.facts();assert h.service.reconcile_request(request).status=='committed'
        assert h.service.execute(request).result==result.result and h.facts()==retained


def test_delete_has_no_receipt_and_uncertainty_never_enters_retry(runtime):
    h=runtime;p=h.project();review=h.service.read_delete_preview('project',p)
    request=Request.make(uid(),h.store.dataset_id,'delete_project',h.now+1,
        project_id=p,expected_version=1,review=review,confirmed_text='DELETE')
    h.store.connection=Fault(h.store.connection,'after')
    result=h.service.execute(request)
    assert result.status=='unverified' and h.store._unresolved_delete is request
    assert h.service.reconcile_request(request).status=='unverified'
    assert h.service.execute(request).status=='unverified'
    assert h.service.read_delete_presence('project',p)['historical_outcome_verified'] is False
    assert h.service.read_delete_presence('project',p)['present'] is False
    blocked=Request.make(uid(),h.store.dataset_id,'create_project',h.now+2,project_id=uid(),name='Blocked')
    assert h.service.execute(blocked).status=='unverified'
    assert not h.facts()['committed_requests'] and not h.facts()['projects']
    with pytest.raises(RuntimeError):h.store.backup(h.store.directory.parent/'blocked.sqlite3')


def test_ddl_sources_unchanged_and_explicit_legacy_policy_remains_separate(tmp_path):
    from chronicle.sqlite_store import SCHEMA
    assert hashlib.sha256(SCHEMA.encode()).hexdigest()=='9557130e5bfdc2d5ff8ffbe1b8a26f19d74546e65b59eb3c02217295e4f42f49'
    assert hashlib.sha256(schema_profiles.SCHEMA.encode()).hexdigest()=='ec4c8687cd13d5db79ad5031a7a3155bab7670ae1388f8b47bd468b7b4f1c467'
    legacy=SQLiteStore(tmp_path/'legacy',create=True,timezone='Etc/UTC',schema_version=3)
    try:
        assert legacy.connection.execute('PRAGMA user_version').fetchone()[0]==3
        with pytest.raises(ValueError):Schema4RuntimeService(legacy)
    finally:legacy.close()


def test_ordinary_store_refuses_directory_alias_without_creating_or_following_it(runtime,tmp_path):
    alias=tmp_path/'alias'
    try:alias.symlink_to(runtime.store.directory,target_is_directory=True)
    except OSError as exc:pytest.skip(f'Native directory symlink unavailable: {exc}')
    before=runtime.facts()
    with pytest.raises(ValueError,match='Symlink/reparse'):SQLiteStore(alias)
    assert runtime.facts()==before
