import sqlite3
import pytest
from chronicle import schema
from chronicle.evidence import verify_transaction
from chronicle.records import canonical
from conftest import uid


@pytest.mark.parametrize('damage',['receipt class','receipt bytes','result','timestamp','owner','sequence','work','frozen','confirmed'])
def test_complete_current_semantics_reject_tampered_evidence(client,damage):
    h=client;p=h.project();task=h.task(p);h.dated(task);h.export(task);h.manual(task,1)
    c=h.store.connection
    tables={'receipt class':'committed_requests','receipt bytes':'committed_requests','result':'committed_requests','timestamp':'tasks','owner':'tasks','sequence':'sqlite_sequence','work':'work_revisions','frozen':'timesheet_exports','confirmed':'polr_confirmed_current'}
    table=tables[damage];triggers=list(c.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",(table,)))
    for name,sql in triggers:c.execute('DROP TRIGGER '+name)
    if damage=='receipt class':
        with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE committed_requests SET receipt_class='protected' WHERE operation='create_task'")
        c.execute('PRAGMA ignore_check_constraints=ON')
        c.execute("UPDATE committed_requests SET receipt_class='protected' WHERE operation='create_task'")
        c.execute('PRAGMA ignore_check_constraints=OFF')
    elif damage=='receipt bytes':c.execute("UPDATE committed_requests SET request_bytes=x'7b7d' WHERE operation='create_task'")
    elif damage=='result':c.execute("UPDATE committed_requests SET result_bytes=x'7b7d' WHERE operation='create_task'")
    elif damage=='timestamp':c.execute('UPDATE tasks SET updated_utc_us=updated_utc_us+1')
    elif damage=='owner':
        c.execute('PRAGMA foreign_keys=OFF');c.execute('UPDATE tasks SET created_request_id=?',(uid(),));c.execute('PRAGMA foreign_keys=ON')
    elif damage=='sequence':c.execute('UPDATE sqlite_sequence SET seq=0')
    elif damage=='work':c.execute("UPDATE work_revisions SET comment='Forged'")
    elif damage=='frozen':c.execute("UPDATE timesheet_exports SET report_sha256=?",('0'*64,))
    else:c.execute('DELETE FROM polr_confirmed_current')
    for name,sql in triggers:c.execute(sql)
    raw=h.store.path.read_bytes()
    with pytest.raises((ValueError,KeyError,sqlite3.Error)):
        with h.store.read_transaction():pass
    assert h.store.path.read_bytes()==raw


def test_reconstruction_never_calls_mutation_services(client,monkeypatch):
    h=client;p=h.project();t=h.task(p);h.dated(t);h.export(t);h.manual(t,1)
    def forbidden(*args,**kw):raise AssertionError('Verifier invoked a mutation implementation')
    for path in ('chronicle.operations.apply_operation','chronicle.project_services.apply_project_operation','chronicle.task_services.apply_task_operation','chronicle.template_services.apply_template_operation'):
        monkeypatch.setattr(path,forbidden)
    with h.store.read_transaction() as c:assert verify_transaction(c)['semantic_verified']


def test_projectless_request_cannot_hide_behind_valid_current_rows(client):
    import json
    h=client;p=h.project();task=h.task(p);c=h.store.connection
    c.execute('DROP TRIGGER immutable_committed_requests_update')
    row=c.execute("SELECT * FROM committed_requests WHERE operation='create_task'").fetchone();content=json.loads(row['request_bytes'])
    content['arguments']['project_id']=None
    c.execute('UPDATE committed_requests SET request_bytes=? WHERE request_id=?',(canonical(content),row['request_id']))
    c.execute(next(x for x in schema.schema_statements() if x.startswith('CREATE TRIGGER immutable_committed_requests_update')))
    assert c.execute('SELECT project_id FROM tasks').fetchone()[0]==p
    with pytest.raises(ValueError):
        with h.store.read_transaction():pass
