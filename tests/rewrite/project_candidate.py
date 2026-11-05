"""Test-owned candidate transaction adapter. Not an application runtime.

Callers exclusively own disposable files and join interrupted children before
reopening. No concurrent application writer or general coordinator is supported.
Fault checkpoints make real transaction boundaries observable to killed children.
"""
import json
import sqlite3
from pathlib import Path

from chronicle import schema_profiles as schema
from chronicle.project_services import CandidateProjectContext, apply_project_operation
from chronicle.records import Outcome, canonical


def facts(c):
    return {name: sorted(schema._rows(c, name), key=repr) for name, in c.execute(
        "SELECT name FROM sqlite_schema WHERE type='table'")}


class RequestConflict(ValueError):
    pass


def receipt_extension(before, c, request, result):
    """Independent complete surviving facts, not the service's mutation plan."""
    after = facts(c)
    previous = next((r['seq'] for r in before['sqlite_sequence'] if r['name'] == 'committed_requests'), 0)
    row = dict(commit_seq=previous+1, request_id=request.request_id, operation=request.operation,
               receipt_class='administrative', request_bytes=request.content(),
               result_bytes=canonical(result), action_utc_us=request.action_utc_us)
    expected = dict(before, projects=after['projects'],
                    committed_requests=sorted(before['committed_requests']+[row], key=repr),
                    sqlite_sequence=[dict(name='committed_requests', seq=previous+1)])
    if after != expected:
        raise ValueError('Unexpected receipt extension or unrelated row change')


class CandidateAdapter:
    def __init__(self, path, dataset_id, checkpoint=lambda stage, c: None):
        self.path = Path(path).resolve()
        self.context = CandidateProjectContext(dataset_id)
        self.checkpoint = checkpoint
        self.retired = None

    def connect(self, readonly=False):
        c = sqlite3.connect(self.path.as_uri()+('?mode=ro' if readonly else '?mode=rw'),
                            uri=True, isolation_level=None, timeout=schema.BUSY_MS/1000)
        try:
            c.execute('PRAGMA synchronous=EXTRA')
            c.execute('PRAGMA foreign_keys=ON')
            return c
        except BaseException:
            c.close()
            raise

    def receipt(self, c, request):
        row = c.execute('SELECT operation,request_bytes,result_bytes FROM committed_requests WHERE request_id=?',
                        (request.request_id,)).fetchone()
        if row is None:
            return None
        if row[:2] != (request.operation, request.content()):
            raise RequestConflict('Request UUID reused with different content')
        result = json.loads(row[2])
        if type(result) is not dict or canonical(result) != row[2]:
            raise ValueError('Invalid committed result bytes')
        return result

    def envelope(self, request):
        request.content()
        if request.dataset_id != self.context.dataset_id:
            raise ValueError('Wrong candidate dataset')

    def inspect(self, request):
        """Independent exact evidence/absence under test-owned exclusive ownership."""
        c = None
        try:
            self.envelope(request)
            if self.retired is not None:
                raise RuntimeError('Unverified old connection cleanup')
            c = self.connect(readonly=True)
            c.execute('BEGIN')
            if c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0] != request.dataset_id:
                raise ValueError('Wrong installed dataset')
            conflict = None
            try:
                result = self.receipt(c, request)
            except RequestConflict as error:
                conflict, result = error, None
            schema.verify_candidate_transaction(c)
            c.execute('ROLLBACK')
            c.close()
            c = None
            if conflict is not None:
                return Outcome('conflict', error=conflict)
            return Outcome('committed', result) if result is not None else Outcome('absent')
        except Exception as error:
            if c is not None:
                try:
                    c.close()
                except Exception as secondary:
                    error.add_note(f'Independent close failed: {secondary!r}')
                    self.retired = c
            return Outcome('unverified', error=error)

    def execute(self, request):
        try:
            self.envelope(request)
        except ValueError as error:
            return Outcome('rejected', error=error)
        c = None
        try:
            self.envelope(request)
            if self.retired is not None:
                raise RuntimeError('Unverified old connection cleanup')
            c = self.connect()
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT dataset_id FROM dataset_meta').fetchone()[0] != request.dataset_id:
                raise ValueError('Wrong installed dataset')
            previous = self.receipt(c, request)  # Before new-state/stale evaluation.
            schema.verify_candidate_transaction(c)
            if previous is not None:
                result = Outcome('committed', previous)
                c.execute('ROLLBACK')
            else:
                before = facts(c)
                applied = apply_project_operation(c, request, self.context)
                self.checkpoint('after_apply', c)
                if applied is None:
                    c.execute('ROLLBACK')
                    result = Outcome('unchanged')
                else:
                    if request.operation not in schema.ADMINISTRATIVE_OPERATIONS:
                        raise ValueError('Not a candidate administrative operation')
                    c.execute('INSERT INTO committed_requests(request_id,operation,receipt_class,request_bytes,result_bytes,action_utc_us) VALUES(?,?,?,?,?,?)',
                              (request.request_id, request.operation, 'administrative', request.content(),
                               canonical(applied), request.action_utc_us))
                    self.checkpoint('after_receipt', c)
                    receipt_extension(before, c, request, applied)
                    schema.verify_candidate_transaction(c)
                    self.checkpoint('after_verify', c)
                    self.checkpoint('before_commit', c)
                    c.execute('COMMIT')
                    self.checkpoint('after_commit', c)
                    result = Outcome('committed', applied)
            self.checkpoint('close', c)
            c.close()
            return result
        except Exception as error:
            clean = True
            if c is not None:
                try:
                    if c.in_transaction:
                        self.checkpoint('rollback', c)
                        c.execute('ROLLBACK')
                except Exception as secondary:
                    error.add_note(f'Rollback failed: {secondary!r}')
                    clean = False
                try:
                    self.checkpoint('close', c)
                    c.close()
                except Exception as secondary:
                    error.add_note(f'Close failed: {secondary!r}')
                    self.retired = c
                    clean = False
            # Never treat COMMIT errors as absence. Retire first, independently
            # verify complete state, then reconcile the *same* original request.
            observed = self.inspect(request)
            if observed.status == 'committed':
                return observed
            if clean and observed.status == 'absent':
                return Outcome('rejected' if isinstance(error, ValueError) else 'rolled_back', error=error)
            if clean and observed.status == 'conflict':
                return Outcome('rejected', error=error)
            return Outcome('unverified', error=error)
