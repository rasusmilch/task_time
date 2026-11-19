import hashlib
import inspect
import sqlite3
import pytest
from chronicle import schema
from chronicle.sqlite_store import SQLiteStore
from chronicle.evidence import verify_transaction
from chronicle.worker import DatabaseWorker
from chronicle.startup import StartupWindow
from conftest import uid, NOW


def test_single_schema_fresh_profile_and_complete_semantics(client):
    s=client.store;c=s.connection
    assert c.execute('PRAGMA user_version').fetchone()[0]==5
    assert c.execute('PRAGMA application_id').fetchone()[0]==0x4348524E
    assert [c.execute('PRAGMA '+n).fetchone()[0] for n in ('journal_mode','synchronous','foreign_keys')]==['delete',3,1]
    assert client.state()['schema_version']==5 and not client.state()['tasks'] and not client.state()['projects']
    assert len(list(schema.schema_statements()))==65
    assert hashlib.sha256(schema.SCHEMA.encode()).hexdigest()=='196625dc8571b0d5c8c50fd30b6594949d7e807aa490bb814e315f4be3229855'
    for factory in (SQLiteStore,DatabaseWorker,StartupWindow):assert 'schema_version' not in inspect.signature(factory).parameters
    with s.read_transaction() as c:assert verify_transaction(c)==dict(schema_version=5,semantic_verified=True)


def test_owner_exclusion_reopen_and_no_overwrite(client):
    s=client.store;p=client.project();t=client.task(p);client.dated(t)
    before=client.facts()
    with pytest.raises(OSError):SQLiteStore(s.directory)
    with pytest.raises(ValueError):SQLiteStore(s.directory,create=True,timezone='UTC')
    path=s.directory;identity=s.dataset_id;s.close()
    fresh=SQLiteStore(path)
    try:
        from conftest import Client
        assert fresh.dataset_id==identity and Client(fresh).facts()==before
    finally:fresh.close()


@pytest.mark.parametrize('damage',['marker','foreign','ddl','receipt','metadata'])
def test_invalid_current_database_refuses(client,damage):
    p=client.project();client.task(p);s=client.store;path=s.path;directory=s.directory;s.close()
    c=sqlite3.connect(path,isolation_level=None)
    try:
        if damage=='marker':c.execute('PRAGMA user_version=42')
        elif damage=='foreign':c.execute('PRAGMA application_id=123')
        elif damage=='ddl':c.execute('DROP TRIGGER active_only_open')
        elif damage=='metadata':c.execute("UPDATE dataset_meta SET timezone='Invalid/Zone'")
        else:
            c.execute('DROP TRIGGER immutable_committed_requests_update')
            c.execute("UPDATE committed_requests SET result_bytes=x'7b7d'")
            c.execute(next(x for x in schema.schema_statements() if x.startswith('CREATE TRIGGER immutable_committed_requests_update')))
    finally:c.close()
    before=path.read_bytes()
    with pytest.raises((ValueError,sqlite3.Error,KeyError)):SQLiteStore(directory)
    assert path.read_bytes()==before


def test_service_requires_active_transaction_and_real_dataset(client):
    from chronicle.operations import apply_operation
    r=client.request('create_project',project_id=uid(),name='Review')
    with pytest.raises(ValueError,match='transaction'):apply_operation(client.store.connection,r,client.store.dataset_id)
    with client.store.read_transaction() as c:
        with pytest.raises(ValueError,match='dataset'):apply_operation(c,r,uid())
    assert not client.state()['projects']
