"""Cold schema-4 compatibility, backup and restore through production policy."""
from pathlib import Path
import sqlite3
import pytest
from chronicle import backup_restore as br
from chronicle.sqlite_store import SQLiteStore
from runtime4_cases import runtime,Runtime,uid
from test_backup_restore import logical,cli
from chronicle.timesheet_files import metadata


@pytest.mark.parametrize('kind,classification',[
 ('valid','SUPPORTED_CURRENT'),('schema3','OLDER_UNSUPPORTED'),('future','NEWER_UNSUPPORTED'),
 ('foreign','FOREIGN_DATABASE'),('layout','UNSUPPORTED_LAYOUT'),('receipt','UNSAFE_OR_UNAVAILABLE'),
 ('metadata','UNSAFE_OR_UNAVAILABLE'),('wal','UNSUPPORTED_PROFILE'),('journal','UNSAFE_OR_UNAVAILABLE'),('corrupt','UNSAFE_OR_UNAVAILABLE')])
def test_actual_current_cold_matrix_and_headless_cli_preserve_originals(tmp_path,kind,classification):
    directory=tmp_path/'source';s=SQLiteStore(directory,create=True,timezone='America/Chicago',schema_version=3 if kind=='schema3' else 4)
    if kind!='schema3':Runtime(s).project()
    if kind=='future':s.connection.execute('PRAGMA user_version=5')
    if kind=='foreign':s.connection.execute('PRAGMA application_id=111')
    if kind=='layout':s.connection.execute('DROP TRIGGER active_only_open')
    if kind=='receipt':
        s.connection.execute('DROP TRIGGER immutable_committed_requests_update')
        s.connection.execute("UPDATE committed_requests SET result_bytes=?",(b'{}',))
        from chronicle.schema_profiles import schema_statements
        s.connection.execute(next(x for x in schema_statements() if x.startswith('CREATE TRIGGER immutable_committed_requests_update')))
    if kind=='metadata':s.connection.execute("UPDATE dataset_meta SET timezone='Unknown/Zone'")
    if kind=='wal':s.connection.execute('PRAGMA journal_mode=WAL')
    s.close();db=directory/'chronicle.sqlite3'
    if kind=='journal':Path(str(db)+'-journal').write_bytes(b'Unproven sidecar')
    if kind=='corrupt':db.write_bytes(b'Not a database')
    def observed():return {p.name:(p.read_bytes(),metadata(p.stat())) for p in directory.iterdir()}
    before=observed();result=br.inspect_dataset(directory)
    assert result.classification.value==classification and result.supported_schema_version==4
    assert result.ordinary_startup_permitted==(kind=='valid')
    assert result.full_validation_completed==(kind=='valid')
    command=cli('--inspect-dataset',directory)
    assert command.returncode==result.exit_status and classification in command.stdout
    assert observed()==before
    target=tmp_path/'restore'
    if kind=='valid':
        image=br.validate_image(db);restored=br.restore_image(db,target)
        assert restored.verified and logical(target/'chronicle.sqlite3')==logical(db)
        assert image.dataset_id==restored.image.dataset_id
    else:
        with pytest.raises((ValueError,OSError,sqlite3.DatabaseError)):br.validate_image(db)
        # Refusal must occur before reserving the restore directory.
        with pytest.raises((ValueError,OSError,sqlite3.DatabaseError)):br.restore_image(db,target)
        assert not target.exists()
    assert observed()==before


@pytest.mark.parametrize('phase',['copy','stage verify','link before','link after','final verify','cleanup'])
def test_current_backup_faults_never_acknowledge_or_remove_final(runtime,tmp_path,monkeypatch,phase):
    h=runtime;h.project();before=h.facts();target=tmp_path/'backup.sqlite3'
    failure=OSError('Original '+phase+' fault');validate=br.validate_image;link=br.os.link;remove=br._remove_owned
    def fail(*a,**k):raise failure
    if phase=='copy':monkeypatch.setattr(br,'_copy',fail)
    elif phase.endswith('verify'):
        def verify(path,**kw):
            if path.name.startswith('.chronicle-backup-')==(phase=='stage verify'):raise failure
            return validate(path,**kw)
        monkeypatch.setattr(br,'validate_image',verify)
    elif phase.startswith('link'):
        def publish(a,b):
            if phase=='link after':link(a,b)
            raise failure
        monkeypatch.setattr(br.os,'link',publish)
    else:monkeypatch.setattr(br,'_remove_owned',fail)
    result=h.store.backup(target)
    assert not result.verified and result.error is failure and h.facts()==before
    published=phase in ('link after','final verify','cleanup')
    assert target.exists()==published
    if published:
        assert logical(target)==before and validate(target).dataset_id==h.store.dataset_id
        assert result.phase==(br.BackupPhase.VERIFIED if phase=='cleanup' else br.BackupPhase.PUBLISHED_UNVERIFIED)
    if phase=='cleanup':
        # Restore cleanup ability, remove only this test's retained owned stage.
        monkeypatch.setattr(br,'_remove_owned',remove)
        stages=list(tmp_path.glob('.chronicle-backup-*'));assert len(stages)==1
        remove(stages[0],stages[0].stat())


def test_restore_existing_target_and_source_alias_refuse_without_overwrite(runtime,tmp_path):
    h=runtime;h.project();target=tmp_path/'backup';assert h.store.backup(target).verified
    raw=target.read_bytes();occupied=tmp_path/'occupied';occupied.mkdir();sentinel=occupied/'keep';sentinel.write_bytes(b'keep')
    with pytest.raises(FileExistsError):br.restore_image(target,occupied)
    assert sentinel.read_bytes()==b'keep'
    with pytest.raises(FileExistsError):br.restore_image(target,h.store.directory)
    alias=tmp_path/'alias'
    try:alias.symlink_to(target)
    except OSError as exc:pytest.skip(f'Native symlink unavailable: {exc}')
    with pytest.raises(ValueError):br.validate_image(alias)
    assert target.read_bytes()==raw
