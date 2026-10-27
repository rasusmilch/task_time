"""Bounded launcher preferences, never an authority for Chronicle facts."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import sys
from uuid import uuid4

from .timesheet_files import (path_matches_handle, same_domain_metadata,
                             same_file_identity, _remove_owned)

LIMIT = 8192


@dataclass(frozen=True)
class Locations:
    folder: Path | None
    record: Path | None
    diagnostic: str = ''


@dataclass(frozen=True)
class Selection:
    directory: Path
    raw: bytes
    observation: object


def local_path(value):
    """Reject known remote paths and existing redirects; never create anything."""
    if not isinstance(value, (str, Path)) or not str(value).strip() or '\0' in str(value):
        raise ValueError('Choose a nonempty absolute local folder')
    text = str(value)
    if text.startswith(('//', '\\\\')):
        raise ValueError('Choose local storage, not a network or device path')
    path = Path(text)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Choose an absolute local folder without parent traversal')
    for part in reversed((path, *path.parents)):
        try:
            observed = part.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(observed.st_mode)
                or getattr(observed, 'st_file_attributes', 0) & 0x400):
            raise ValueError(f'Symlink/reparse redirection is not supported: {part}')
        if part != path and not stat.S_ISDIR(observed.st_mode):
            raise ValueError(f'A folder parent is not a directory: {part}')
    if sys.platform == 'win32':
        import ctypes
        get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
        get_drive_type.argtypes = [ctypes.c_wchar_p]
        get_drive_type.restype = ctypes.c_uint
        if get_drive_type(path.anchor) not in (2, 3, 6):
            raise ValueError('Choose available local storage, not a network drive')
    return path


def locations(*, environ=None, platform=None):
    env = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    try:
        if platform == 'win32':
            base = local_path(env.get('LOCALAPPDATA', ''))
            if not base.is_dir():
                raise ValueError('LOCALAPPDATA is unavailable; choose a folder explicitly')
        elif platform == 'darwin':
            base = local_path(env.get('HOME', '')) / 'Library' / 'Application Support'
        else:
            base = (local_path(env['XDG_DATA_HOME']) if env.get('XDG_DATA_HOME')
                    else local_path(env.get('HOME', '')) / '.local' / 'share')
        base = local_path(base / 'Chronicle')
        return Locations(base / 'Data', base / 'launcher-selection.json')
    except (ValueError, OSError) as exc:
        return Locations(None, None, f'Local launcher storage unavailable: {exc}')


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError('Duplicate launcher selection field')
        value[key] = item
    return value


def read_selection(path):
    """Read at most LIMIT bytes, with independent path/handle stability checks."""
    path = local_path(path)
    try:
        observed = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1 or observed.st_size > LIMIT:
        raise ValueError('Launcher selection must be a bounded regular file with one link')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0)
                 | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        before = os.fstat(fd)
        if not path_matches_handle(observed, before) or before.st_nlink != 1:
            raise OSError('Launcher selection changed before reading')
        raw = b''
        while len(raw) <= LIMIT:
            chunk = os.read(fd, LIMIT + 1 - len(raw))
            if not chunk:
                break
            raw += chunk
        if (len(raw) != observed.st_size or len(raw) > LIMIT
                or not same_domain_metadata(before, os.fstat(fd))
                or not same_domain_metadata(observed, path.lstat())):
            raise OSError('Launcher selection changed during reading')
    except BaseException as primary:
        try:
            os.close(fd)
        except Exception as secondary:
            primary.add_note(f'Launcher read close also failed: {secondary!r}')
        raise
    else:
        os.close(fd)
    data = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs)
    if (type(data) is not dict or set(data) != {'format_version', 'dataset_directory'}
            or type(data['format_version']) is not int or data['format_version'] != 1
            or type(data['dataset_directory']) is not str):
        raise ValueError('Unsupported or malformed launcher selection; original retained')
    # A missing target is still a syntactically valid remembered path, never create consent.
    directory = local_path(data['dataset_directory'])
    return Selection(directory, raw, observed)


def _same_selection(expected, current):
    if expected is None or current is None:
        return expected is current
    return (expected.raw == current.raw
            and same_domain_metadata(expected.observation, current.observation))


def remember(path, directory, expected):
    """Publish only after readiness; replace only a valid, unchanged reviewed record.

    Trusted per-user storage. Reinspection is not hostile-filesystem atomic CAS.
    No final file is removed as rollback after publication uncertainty.
    """
    path, directory = local_path(path), local_path(directory)
    if path.is_relative_to(directory):
        raise ValueError('Launcher selection storage must be outside the dataset')
    if not _same_selection(expected, read_selection(path)):
        raise OSError('Launcher selection changed; existing object retained')
    raw = (json.dumps({'format_version': 1, 'dataset_directory': str(directory)},
                      ensure_ascii=False) + '\n').encode('utf-8')
    if len(raw) > LIMIT:
        raise ValueError('Selected folder exceeds launcher record size limit')
    path.parent.mkdir(parents=True, exist_ok=True)
    local_path(path)
    stage = path.with_name(f'.launcher-selection-{uuid4()}.tmp')
    created = None
    primary = None
    try:
        fd = os.open(stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0), 0o600)
        try:
            created = os.fstat(fd)
            remaining = raw
            while remaining:
                written = os.write(fd, remaining)
                if written <= 0:
                    raise OSError('Incomplete launcher selection write')
                remaining = remaining[written:]
            os.fsync(fd)
        except BaseException as exc:
            try:
                os.close(fd)
            except Exception as secondary:
                exc.add_note(f'Launcher write close also failed: {secondary!r}')
            raise
        else:
            os.close(fd)
        candidate = read_selection(stage)
        if candidate.raw != raw or not same_file_identity(candidate.observation, created):
            raise OSError('Launcher stage identity/content changed')
        if not _same_selection(expected, read_selection(path)):
            raise OSError('Launcher selection changed before publication; original retained')
        if expected is None:
            os.link(stage, path)  # Absent-target exclusive publication; no clobber fallback.
        else:
            os.replace(stage, path)  # Only the complete valid reviewed record may be replaced.
    except BaseException as exc:
        primary = exc
        raise
    finally:
        if created is not None:
            try:
                _remove_owned(stage, created)
            except Exception as secondary:
                if primary is not None:
                    primary.add_note(f'Launcher stage cleanup also failed: {secondary!r}')
                else:
                    raise
    installed = read_selection(path)
    if (installed is None or installed.raw != raw
            or not same_file_identity(installed.observation, created)):
        raise OSError('Launcher selection final verification failed; dataset remains open')
