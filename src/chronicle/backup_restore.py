"""Consistent SQLite images and cold, new-directory recovery.

Trusted local directories and serialized ownership only. Identity/stability
checks are bounded observations, not hostile-directory or power-loss guarantees.
No final pathname is ever removed as rollback.
"""

from dataclasses import dataclass
from enum import Enum
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from uuid import uuid4

from .dataset_lock import DatasetLock
from .sqlite_store import BUSY_MS, DATABASE, SQLiteStore, runtime_info
from .timesheet_files import destination_path, metadata, protect, _owned, _remove_owned


class BackupPhase(str, Enum):
    NOT_STARTED = 'NOT_STARTED'
    STAGING = 'STAGING'
    VALIDATING = 'VALIDATING'
    PUBLICATION_ATTEMPTED = 'PUBLICATION_ATTEMPTED'
    PUBLISHED_UNVERIFIED = 'PUBLISHED_UNVERIFIED'
    VERIFIED = 'VERIFIED'


@dataclass(frozen=True)
class Image:
    path: Path
    dataset_id: str
    timezone: str
    week_start: int
    metadata: tuple
    digest: str


@dataclass(frozen=True)
class BackupResult:
    destination: str
    phase: BackupPhase = BackupPhase.NOT_STARTED
    image: Image | None = None
    error: Exception | None = None

    @property
    def verified(self):
        return self.phase == BackupPhase.VERIFIED and self.error is None


def _regular(path):
    observed = path.lstat()
    if not stat.S_ISREG(observed.st_mode):
        raise ValueError('A suitable regular SQLite file is required; symlinks are not accepted')
    return observed


def _fingerprint(path):
    """Complete, bounded regular-file read; no FIFO or symlink is opened."""
    observed = _regular(path)
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    try:
        if metadata(os.fstat(fd)) != metadata(observed):
            raise OSError('SQLite image changed before inspection')
        count, digest, header = 0, hashlib.sha256(), b''
        while True:
            block = os.read(fd, min(65536, max(1, observed.st_size-count+1)))
            if not block:
                break
            if count == 0:
                header = block[:20]
            count += len(block)
            digest.update(block)
            if count > observed.st_size:
                raise OSError('SQLite image grew during inspection')
        if (count != observed.st_size or metadata(os.fstat(fd)) != metadata(observed)
                or metadata(path.lstat()) != metadata(observed)):
            raise OSError('SQLite image changed or was incompletely read')
        # Reject WAL images before SQLite can create/read WAL shared-memory
        # sidecars, even through a read-only connection. Schema validation still
        # belongs exclusively to SQLiteStore; this is format/profile selection.
        if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
            raise ValueError('A supported SQLite image with DELETE journal profile is required')
        result = metadata(observed), digest.hexdigest()
    except BaseException as primary:
        try:
            os.close(fd)
        except Exception as secondary:
            primary.add_note(f'Image descriptor cleanup also failed: {secondary!r}')
        raise
    else:
        os.close(fd)
        return result


def _readonly(path):
    c = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=BUSY_MS/1000)
    try:
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA query_only=ON')
        c.execute('PRAGMA foreign_keys=ON')
    except BaseException as primary:
        _close(c, primary)
        raise
    return c


def _close(connection, primary=None):
    try:
        connection.close()
    except Exception as secondary:
        if primary is None:
            raise
        primary.add_note(f'SQLite connection close also failed: {secondary!r}')


def validate_image(value) -> Image:
    """Independent read-only full integrity plus the production semantic validator."""
    runtime_info()
    path = destination_path(value)
    before, digest = _fingerprint(path)
    c = _readonly(path)
    try:
        c.execute('BEGIN')
        if c.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            raise ValueError('Backup requires the supported DELETE journal profile')
        if [r[0] for r in c.execute('PRAGMA integrity_check')] != ['ok']:
            raise ValueError('Full SQLite integrity check failed')
        SQLiteStore._verify(c)
        # Receipt shape and relationships are owned by SQLiteStore as well.
        SQLiteStore.verify_receipts(c)
        meta = c.execute('SELECT * FROM dataset_meta').fetchone()
        result = Image(path, meta['dataset_id'], meta['timezone'], meta['week_start'], before, digest)
        c.execute('COMMIT')
    except BaseException as primary:
        _close(c, primary)
        raise
    else:
        _close(c)
    if _fingerprint(path) != (before, digest):
        raise OSError('SQLite image changed during independent validation')
    return result


def _absent(path):
    if not path.parent.is_dir():
        raise ValueError('Destination parent must be an existing suitable directory')
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise FileExistsError(f'Destination already exists; choose another path: {path}')


def _stage(target):
    stage = target.parent / f'.chronicle-backup-{uuid4()}.tmp'
    if stage == target:
        raise ValueError('Private staging must differ from the requested final destination')
    fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
    try:
        created = os.fstat(fd)
    except BaseException as primary:
        try:
            os.close(fd)
        except Exception as secondary:
            primary.add_note(f'Stage reservation close also failed: {secondary!r}')
        primary.add_note(f'Stage identity could not be established; no guessed cleanup: {stage}')
        raise
    else:
        try:
            os.close(fd)
        except BaseException as primary:
            try:
                _remove_owned(stage, created)
            except Exception as secondary:
                primary.add_note(f'Stage reservation cleanup also failed: {secondary!r}')
            raise
    return stage, created


def _copy(source, stage):
    destination = sqlite3.connect(stage, isolation_level=None, timeout=BUSY_MS/1000)
    try:
        destination.execute('PRAGMA journal_mode=DELETE')
        destination.execute('PRAGMA synchronous=EXTRA')
        destination.execute('PRAGMA foreign_keys=ON')
        actual = tuple(destination.execute(f'PRAGMA {name}').fetchone()[0]
                       for name in ('journal_mode', 'synchronous', 'foreign_keys'))
        if actual != ('delete', 3, 1):
            raise ValueError('Unsupported backup staging profile')
        def progress(status, remaining, total):
            if status in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise TimeoutError('Backup could not acquire bounded SQLite access')
        source.backup(destination, pages=256, progress=progress, sleep=0.05)
    except BaseException as primary:
        _close(destination, primary)
        raise
    else:
        _close(destination)  # Successful close is part of preparation, not cleanup.


def _sync(stage, created):
    observed = _owned(stage, created)
    # Our owned stage is writable; a write-capable descriptor also supports
    # Windows FlushFileBuffers/_commit. No contents are written or truncated.
    fd = os.open(stage, os.O_RDWR | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try:
        if metadata(os.fstat(fd)) != metadata(observed):
            raise OSError('Stage changed before sync')
        os.fsync(fd)
    except BaseException as primary:
        try:
            os.close(fd)
        except Exception as secondary:
            primary.add_note(f'Sync descriptor close also failed: {secondary!r}')
        raise
    else:
        os.close(fd)


def _same_content(stage, target):
    # Digest checks accompany this complete byte comparison; page layout need
    # only agree between this completed stage and its publication, not the source.
    descriptors, observed = [], []
    primary = cleanup_error = None
    try:
        for path in (stage, target):
            value = _regular(path)
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0)
                         | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
            descriptors.append(fd)
            observed.append(metadata(value))
            if metadata(os.fstat(fd)) != metadata(value):
                raise OSError('Final comparison object changed before opening')
        if observed[0][3] != observed[1][3]:
            raise OSError('Final backup size differs from the validated stage')
        remaining = observed[0][3]
        while remaining:
            a = os.read(descriptors[0], min(65536, remaining))
            b = os.read(descriptors[1], len(a))
            if not a or a != b:
                raise OSError('Final backup bytes differ from the validated stage')
            remaining -= len(a)
        for path, fd, value in zip((stage, target), descriptors, observed):
            if os.read(fd, 1) or metadata(os.fstat(fd)) != value or metadata(path.lstat()) != value:
                raise OSError('Final comparison object changed during reading')
    except BaseException as exc:
        primary = exc
        raise
    finally:
        for fd in descriptors:
            try:
                os.close(fd)
            except Exception as secondary:
                if primary is not None:
                    primary.add_note(f'Final comparison cleanup failed: {secondary!r}')
                else:
                    if cleanup_error is None:
                        cleanup_error = secondary
                    else:
                        cleanup_error.add_note(f'Additional descriptor cleanup failed: {secondary!r}')
        if primary is None and cleanup_error is not None:
            raise cleanup_error


def _publish(source, target, *, dataset=None, source_image=None, reserved=None):
    stage = created = image = None
    phase, error = BackupPhase.NOT_STARTED, None
    try:
        if dataset is not None:
            protect(target, dataset)
        _absent(target)
        phase = BackupPhase.STAGING
        stage, created = _stage(target)
        _owned(stage, created)
        _copy(source, stage)
        _sync(stage, created)
        phase = BackupPhase.VALIDATING
        image = validate_image(stage)
        _owned(stage, created)
        if source_image is not None and _fingerprint(source_image.path) != (source_image.metadata, source_image.digest):
            raise OSError('Restore source changed during staging')
        if dataset is not None:
            protect(target, dataset)
        if reserved is not None:
            directory, identity = reserved
            observed = directory.lstat()
            if (observed.st_dev, observed.st_ino) != identity or not stat.S_ISDIR(observed.st_mode):
                raise OSError('Restore directory ownership changed')
            if {p.name for p in directory.iterdir()} != {stage.name, '.chronicle.lock'}:
                raise OSError('Unexpected objects in reserved restore directory')
        _absent(target)
        if _fingerprint(stage) != (image.metadata, image.digest):
            raise OSError('Validated stage changed before publication')
        phase = BackupPhase.PUBLICATION_ATTEMPTED
        os.link(stage, target)  # Exclusive absent-name publication; no fallback.
        phase = BackupPhase.PUBLISHED_UNVERIFIED
        published = _regular(target)
        if (published.st_dev, published.st_ino) != (created.st_dev, created.st_ino):
            raise OSError('Published backup identity differs from owned staging')
        final = validate_image(target)
        _same_content(stage, target)
        if final.digest != image.digest or final.dataset_id != image.dataset_id:
            raise OSError('Final backup does not match validated staging')
        if _fingerprint(target) != (final.metadata, final.digest):
            raise OSError('Final backup changed before acknowledgement')
        image, phase = final, BackupPhase.VERIFIED
    except Exception as primary:
        error = primary
        if phase == BackupPhase.PUBLICATION_ATTEMPTED:
            # A link may have succeeded before its acknowledgement failed.
            # Inspection is diagnostic only; it cannot erase the primary failure.
            try:
                observed = target.lstat()
                if (stat.S_ISREG(observed.st_mode) and created is not None
                        and (observed.st_dev, observed.st_ino) == (created.st_dev, created.st_ino)):
                    phase = BackupPhase.PUBLISHED_UNVERIFIED
                    validate_image(target)
                else:
                    primary.add_note('Final object exists but is not proven to be our publication; retained untouched.')
            except Exception as secondary:
                primary.add_note(f'Publication reinspection: {secondary!r}')
        primary.add_note(f'Backup phase: {phase.value}. Final output is never removed as rollback.')
    finally:
        if created is not None:
            try:
                _remove_owned(stage, created)
            except Exception as secondary:
                if error is not None:
                    error.add_note(f'Owned stage cleanup also failed: {secondary!r}')
                else:
                    error = secondary
                    error.add_note('Final image was verified; temporary-file cleanup failed.')
    return BackupResult(str(target), phase, image, error)


def backup_connection(source, destination, dataset) -> BackupResult:
    target = destination_path(destination)
    if source.in_transaction:
        raise RuntimeError('Backup refuses an executing or unresolved transaction')
    SQLiteStore._verify(source)
    return _publish(source, target, dataset=dataset)


def restore_image(source_path, directory) -> BackupResult:
    """Cold install only. Source validation precedes any target reservation."""
    image = validate_image(source_path)
    if isinstance(directory, (str, Path)) and str(directory).startswith(('\\\\', '//')):
        raise ValueError('Restore requires a supported local dataset directory, not a network path')
    target_dir = destination_path(directory)
    _absent(target_dir)  # Includes existing empty directories and dangling links.
    # mkdir is exclusive, with an existing local parent; no recursive creation.
    target_dir.mkdir(mode=0o700)
    observed = target_dir.lstat()
    lock, source = DatasetLock(target_dir), None
    result = None
    try:
        if any(target_dir.iterdir()):
            raise OSError('Unexpected objects after restore directory reservation')
        lock.acquire()
        if _fingerprint(image.path) != (image.metadata, image.digest):
            raise OSError('Restore source changed after preliminary validation')
        source = _readonly(image.path)
        result = _publish(source, target_dir / DATABASE, source_image=image,
                          reserved=(target_dir, (observed.st_dev, observed.st_ino)))
    except BaseException as primary:
        if source is not None:
            _close(source, primary)
            source = None
        try:
            lock.close()
        except Exception as secondary:
            primary.add_note(f'Restore ownership release also failed: {secondary!r}')
        raise
    else:
        primary = result.error
        try:
            _close(source, primary)
        except Exception as exc:
            exc.add_note('Restore installation outcome is retained; source connection cleanup did not complete.')
            primary = exc
        try:
            lock.close()
        except Exception as exc:
            if primary:
                primary.add_note(f'Restore ownership release also failed: {exc!r}')
            else:
                primary = exc
        if primary is not result.error:
            result = BackupResult(result.destination, result.phase, result.image, primary)
        return result
