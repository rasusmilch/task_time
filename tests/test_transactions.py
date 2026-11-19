from dataclasses import replace
import pytest
from conftest import uid


def test_begin_immediate_receipt_exact_retry_noop_and_conflict(client):
    h=client;trace=[];h.store.connection.set_trace_callback(trace.append)
    r,result=h.send('create_project',project_id=uid(),name='One')
    assert 'BEGIN IMMEDIATE' in trace and 'COMMIT' in trace
    before=h.facts();assert h.service.execute(r).status=='committed' and h.facts()==before
    assert h.service.execute(replace(r,arguments=b'{}')).status=='rejected' and h.facts()==before
    h.send('rename_project',expect='unchanged',project_id=r.args()['project_id'],expected_version=1,name='One')
    assert h.facts()==before


def test_post_install_verification_failure_rolls_back_every_fact(client,monkeypatch):
    import chronicle.sqlite_store as module
    h=client;before=h.facts();original=module.verify_transaction
    def verify(c):
        if c.execute('SELECT count(*) FROM projects').fetchone()[0]:raise ValueError('Deliberate post-operation failure')
        return original(c)
    monkeypatch.setattr(module,'verify_transaction',verify)
    r=h.request('create_project',project_id=uid(),name='Not committed')
    result=h.service.execute(r);assert result.status=='rejected' and 'Deliberate' in str(result.error)
    monkeypatch.undo();assert h.facts()==before and not h.store.connection.in_transaction


def test_commit_before_acknowledgement_requires_exact_original_reconciliation(client,monkeypatch):
    h=client;original=h.store._commit
    def lost(c):original(c);raise OSError('Lost commit acknowledgement')
    monkeypatch.setattr(h.store,'_commit',lost)
    r=h.request('create_project',project_id=uid(),name='Durable unknown');result=h.service.execute(r)
    assert result.status=='unverified' and h.store._unresolved is r
    retained=h.facts();assert len(retained['projects'])==1
    assert h.service.execute(r).status=='unavailable'
    assert h.service.reconcile_request(replace(r)).status=='unavailable'
    assert h.service.reconcile_request(r).status=='committed' and h.facts()==retained
    monkeypatch.undo();assert h.service.execute(r).status=='committed' and h.facts()==retained


def test_unused_delete_proof_high_water_and_protected_refusal(client):
    h=client;p=h.project();t=h.task(p);before=h.facts()
    review=h.service.read_delete_preview('project',p);assert review['eligible']
    r=h.request('delete_project',project_id=p,expected_version=1,review=review,confirmed_text='DELETE')
    assert h.service.execute(r).status=='committed';after=h.facts()
    assert not after['projects'] and not after['tasks'] and not after['committed_requests']
    assert after['sqlite_sequence']==before['sqlite_sequence']
    p=h.project();t=h.task(p);h.dated(t)
    review=h.service.read_delete_preview('project',p);assert not review['eligible']
    h.send('delete_project',expect='rejected',project_id=p,expected_version=1,review=review,confirmed_text='DELETE')


def test_uncertain_delete_never_retries_or_uses_presence_as_proof(client,monkeypatch):
    h=client;p=h.project();h.task(p);review=h.service.read_delete_preview('project',p)
    original=h.store._commit
    def lost(c):original(c);raise OSError('Delete commit acknowledgement lost')
    monkeypatch.setattr(h.store,'_commit',lost)
    r=h.request('delete_project',project_id=p,expected_version=1,review=review,confirmed_text='DELETE')
    assert h.service.execute(r).status=='unverified'
    assert h.service.read_delete_presence('project',p)['present'] is False
    assert h.service.reconcile_request(r).status=='unverified'
    assert h.service.execute(r).status=='unavailable'
    assert h.service.execute(h.request('create_project',project_id=uid(),name='Blocked')).status=='unavailable'


@pytest.mark.parametrize('text',['delete',' DELETE','DELETE ',''])
def test_delete_requires_exact_confirmation(client,text):
    h=client;p=h.project();h.task(p);review=h.service.read_delete_preview('project',p)
    h.send('delete_project',expect='rejected',project_id=p,expected_version=1,review=review,confirmed_text=text)
