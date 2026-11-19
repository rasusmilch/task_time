"""One current SQLite connection and authoritative transaction boundary."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
from uuid import uuid4
from . import schema
from .dataset_lock import DatasetLock
from .evidence import verify_transaction
from .records import Outcome, Request, canonical, uuid_text, receipt_class
from .timekeeping import load_zone
DATABASE = 'chronicle.sqlite3'

def runtime_info():
    if sqlite3.sqlite_version_info < (3, 37):
        raise RuntimeError('Chronicle requires SQLite 3.37 or later')
    return dict(sqlite=sqlite3.sqlite_version, sqlite_version=sqlite3.sqlite_version)

class RequestConflict(ValueError):
    """An existing Request UUID has different canonical content."""

class SQLiteStore:
    schema_version = schema.SCHEMA_VERSION

    def __init__(self, directory, *, create=False, timezone=None):
        runtime_info()
        if type(create) is not bool:
            raise ValueError('Create must be boolean')
        self.directory = Path(directory).expanduser().absolute()
        self.path = self.directory / DATABASE
        self.connection = None
        self._unresolved = self._unresolved_delete = None
        self.lock = DatasetLock(self.directory)
        if create:
            load_zone(timezone)
            if self.directory.exists() and (not self.directory.is_dir() or any(self.directory.iterdir())):
                raise ValueError('Create requires a new or empty folder')
            self.directory.mkdir(parents=True, exist_ok=True)
        elif not self.path.is_file() or self.path.is_symlink():
            raise ValueError('Choose an existing Chronicle database folder')
        try:
            self.lock.acquire()
            if create:
                if any((p != self.lock.path for p in self.directory.iterdir())):
                    raise ValueError('Folder is no longer empty')
                with self.path.open('xb'):
                    pass
            self.connection = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, isolation_level=None, timeout=schema.BUSY_MS / 1000)
            c = self.connection
            c.row_factory = sqlite3.Row
            if not create and (c.execute('PRAGMA application_id').fetchone()[0] != schema.APPLICATION_ID or c.execute('PRAGMA user_version').fetchone()[0] != 5):
                raise ValueError('Chronicle requires schema 5. Create a fresh database; no migration or import is available.')
            c.execute('PRAGMA journal_mode=DELETE')
            c.execute('PRAGMA synchronous=EXTRA')
            c.execute('PRAGMA foreign_keys=ON')
            if create:
                c.execute('BEGIN IMMEDIATE')
                for statement in schema.schema_statements():
                    c.execute(statement)
                c.execute('INSERT INTO dataset_meta(singleton,dataset_id,timezone,week_start) VALUES(1,?,?,6)', (str(uuid4()), timezone))
                c.execute(f'PRAGMA application_id={schema.APPLICATION_ID}')
                c.execute('PRAGMA user_version=5')
                self.verification = verify_transaction(c)
                c.execute('COMMIT')
            else:
                with self.read_transaction() as snapshot:
                    self.verification = verify_transaction(snapshot)
            meta = c.execute('SELECT * FROM dataset_meta').fetchone()
            self.dataset_id = uuid_text(meta['dataset_id'])
            self.timezone = meta['timezone']
            self.zone = load_zone(self.timezone)
            if timezone is not None and timezone != self.timezone:
                raise ValueError('Timezone differs from the selected dataset')
            self.info = dict(runtime_info(), source_id=c.execute('SELECT sqlite_source_id()').fetchone()[0], journal_mode=c.execute('PRAGMA journal_mode').fetchone()[0], synchronous=c.execute('PRAGMA synchronous').fetchone()[0], foreign_keys=c.execute('PRAGMA foreign_keys').fetchone()[0])
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note('Initialization cleanup failed: ' + repr(cleanup))
                primary._chronicle_cleanup_store = self
            raise

    @property
    def week_start(self):
        return self.connection.execute('SELECT week_start FROM dataset_meta').fetchone()[0]

    @contextmanager
    def read_transaction(self):
        c = self.connection
        if c is None:
            raise RuntimeError('Database is closed')
        c.execute('BEGIN')
        try:
            verify_transaction(c)
            yield c
            c.execute('COMMIT')
        except BaseException:
            if c.in_transaction:
                c.execute('ROLLBACK')
            raise

    def _request(self, request):
        if not isinstance(request, Request):
            raise ValueError('A canonical Request is required')
        content = request.content()
        if request.dataset_id != self.dataset_id:
            raise ValueError('Request belongs to another dataset')
        return content

    @staticmethod
    def _receipt(c, request, content):
        row = c.execute('SELECT * FROM committed_requests WHERE request_id=?', (request.request_id,)).fetchone()
        if row is None:
            return None
        if row['request_bytes'] != content or row['operation'] != request.operation:
            raise RequestConflict('Request identity already has different content')
        return json.loads(row['result_bytes'])

    def _commit(self, c):
        c.execute('COMMIT')

    def transact(self, request, apply):
        return self._mutate(request, apply, deleting=False)

    def delete_unused(self, request):
        from .deletion import apply_delete
        return self._mutate(request, lambda c: apply_delete(c, request, self.dataset_id), deleting=True)

    def _mutate(self, request, apply, *, deleting):
        if self._unresolved_delete is not None or self._unresolved is not None:
            return Outcome('unavailable', error=RuntimeError('An accepted operation is unresolved; reconcile its original Request or exit'))
        c = self.connection
        attempted = False
        try:
            content = self._request(request)
            c.execute('BEGIN IMMEDIATE')
            verify_transaction(c)
            previous = self._receipt(c, request, content)
            if previous is not None:
                if deleting:
                    raise RequestConflict('Delete identity belongs to a retained receipt')
                c.execute('ROLLBACK')
                return Outcome('committed', previous)
            result = apply(c)
            if result is None:
                c.execute('ROLLBACK')
                return Outcome('unchanged')
            if not deleting:
                c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)', (request.request_id, request.operation, receipt_class(request.operation), content, canonical(result), request.action_utc_us))
            verify_transaction(c)
            attempted = True
            self._commit(c)
            return Outcome('committed', result)
        except Exception as primary:
            try:
                active = c is not None and c.in_transaction
                if active:
                    c.execute('ROLLBACK')
            except Exception as cleanup:
                primary.add_note('Rollback failed: ' + repr(cleanup))
                active = False
                attempted = True
            if attempted and (not active):
                if deleting:
                    self._unresolved_delete = request
                else:
                    self._unresolved = request
                return Outcome('unverified', error=primary)
            return Outcome('rejected' if isinstance(primary, ValueError) else 'rolled_back', error=primary)

    def reconcile(self, request):
        if self._unresolved_delete is not None or request.operation in ('delete_task', 'delete_project', 'delete_template'):
            return Outcome('unverified', error=RuntimeError('Delete has no receipt and cannot be retried or reconciled from presence'))
        if self._unresolved is not None and request is not self._unresolved:
            return Outcome('unavailable', error=ValueError('Only the exact original Request may reconcile'))
        try:
            content = self._request(request)
            with self.read_transaction() as c:
                result = self._receipt(c, request, content)
            if self._unresolved is request:
                self._unresolved = None
            return Outcome('committed', result) if result is not None else Outcome('absent')
        except RequestConflict as exc:
            return Outcome('conflict', error=exc)
        except Exception as exc:
            return Outcome('unverified', error=exc)

    def close(self):
        if self.connection is not None:
            if self.connection.in_transaction:
                self.connection.execute('ROLLBACK')
            self.connection.close()
            self.connection = None
        self.lock.close()
