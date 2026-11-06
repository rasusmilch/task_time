"""Owned paired-copy recovery admission, never replacement or rollback parsing.

The caller retains DatasetLock. SQLite recovers only this private pair until the
complete version-specific semantic gate and source stability checks have passed.
Trusted local storage only; no hostile concurrent-filesystem guarantee.
"""
import hashlib
import errno
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

from .timesheet_files import metadata, same_domain_metadata, path_matches_handle, same_file_identity, _remove_owned
from .sqlite_store import BUSY_MS


def observation(path):
    value = path.lstat()
    if not stat.S_ISREG(value.st_mode):
        raise ValueError('Recovery requires regular database and rollback-journal files')
    return value


class PrivateRecovery:
    def __init__(self, original):
        self.original = original
        self.directory = None
        self.identity = None
        self.connection = None
        self.files = {}
        self.sources = {}
        self.digests = {}
        self.descriptors = {}

    def _close_descriptor(self, fd):
        try:
            current = os.fstat(fd)
        except OSError as exc:
            if exc.errno != errno.EBADF: raise
        else:
            if self.descriptors[fd] is not None and not same_file_identity(self.descriptors[fd], current):
                raise OSError('Private-copy descriptor identity changed; no guessed close')
            os.close(fd)
        del self.descriptors[fd]

    def _copy(self, source, target):
        observed = self.sources[source]
        read = write = None
        try:
            read = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                           | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0))
            self.descriptors[read] = None  # Retain ownership even if the first observation fails.
            before = os.fstat(read)
            self.descriptors[read] = before
            if not path_matches_handle(observed, before):
                raise OSError('Recovery source identity changed before copy')
            write = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                            | getattr(os, 'O_BINARY', 0), 0o600)
            self.descriptors[write] = None
            self.files[target] = os.fstat(write)
            self.descriptors[write] = self.files[target]
            remaining = observed.st_size
            digest = hashlib.sha256()
            while remaining:
                data = os.read(read, min(65536, remaining))
                if not data:
                    raise OSError('Recovery source was incompletely read')
                digest.update(data)
                remaining -= len(data)
                offset = 0
                while offset < len(data):
                    written = os.write(write, data[offset:])
                    if written <= 0:
                        raise OSError('Private recovery write did not advance')
                    offset += written
            if (os.read(read, 1) or not same_domain_metadata(before, os.fstat(read))
                    or not same_domain_metadata(observed, observation(source))):
                raise OSError('Recovery source changed during copy')
            self.digests[source.name] = digest.hexdigest()
        except BaseException as primary:
            for fd in (write, read):
                if fd is not None:
                    try: self._close_descriptor(fd)
                    except Exception as secondary: primary.add_note(f'Paired-copy descriptor close also failed: {secondary!r}')
            raise
        else:
            error = None
            for fd in (write, read):
                if fd is not None:
                    try: self._close_descriptor(fd)
                    except Exception as exc:
                        if error is None: error = exc
                        else: error.add_note(f'Additional paired-copy close failed: {exc!r}')
            if error is not None: raise error

    def unchanged(self):
        for path, before in self.sources.items():
            if metadata(observation(path)) != metadata(before):
                raise OSError('Original database/journal changed during private recovery preflight')
        for suffix in ('-wal', '-shm'):
            if os.path.lexists(str(self.original) + suffix):
                raise OSError('Unexpected SQLite sidecar during recovery preflight')

    def authorize(self, policy, *, timezone=None):
        journal = Path(str(self.original) + '-journal')
        self.sources = {p: observation(p) for p in (self.original, journal)}
        self.directory = Path(tempfile.mkdtemp(prefix='chronicle-recovery-'))
        self.identity = self.directory.lstat()
        if self.directory.is_relative_to(self.original.parent):
            raise ValueError('Private recovery directory must be outside the original dataset')
        for source in self.sources:
            self._copy(source, self.directory / source.name)
        self.unchanged()
        c = sqlite3.connect((self.directory / self.original.name).as_uri() + '?mode=rw',
                            uri=True, isolation_level=None, timeout=BUSY_MS/1000)
        self.connection = c
        c.row_factory = sqlite3.Row
        # These connection-local settings precede SQLite-native recovery of the
        # private copy. Nothing has opened the original database for writing.
        c.execute('PRAGMA synchronous=EXTRA')
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('BEGIN')
        policy.verify(c)
        if timezone is not None and c.execute('SELECT timezone FROM dataset_meta').fetchone()[0] != timezone:
            raise ValueError('Explicit timezone conflicts with recovered dataset')
        c.execute('ROLLBACK')
        c.close()
        self.connection = None
        self.unchanged()
        self.close()
        self.unchanged()  # Cleanup is part of admission, not deferred until ready.

    def close(self):
        for fd in tuple(self.descriptors): self._close_descriptor(fd)
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        for path, identity in tuple(self.files.items()):
            _remove_owned(path, identity)
            del self.files[path]
        if self.directory is not None:
            observed = self.directory.lstat()
            if (observed.st_dev, observed.st_ino) != (self.identity.st_dev, self.identity.st_ino) or not stat.S_ISDIR(observed.st_mode):
                raise OSError('Private recovery directory identity changed; no guessed cleanup')
            self.directory.rmdir()  # Unexpected objects are never removed recursively.
            self.directory = None
