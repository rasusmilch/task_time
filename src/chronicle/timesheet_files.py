"""Bounded protected publication of already validated frozen bytes.

Trusted local directories/serialized ownership; metadata rechecks are not atomic
compare-and-replace, hostile-directory protection or hardware power-loss proof.
"""
from dataclasses import dataclass
from enum import Enum
import hashlib
import os
from pathlib import Path
import stat
from uuid import uuid4


class FileState(str, Enum):
    PENDING = 'PENDING'
    READY = 'READY'
    MISSING = 'MISSING'
    CONFLICT = 'CONFLICT'
    UNVERIFIABLE = 'UNVERIFIABLE'


@dataclass(frozen=True)
class ContentConflict:
    destination: str
    metadata: tuple
    sha256: str


@dataclass(frozen=True)
class Inspection:
    state: FileState
    destination: str | None
    conflict: ContentConflict | None = None
    error: Exception | None = None


class PublicationPhase(str, Enum):
    NOT_ATTEMPTED = 'not attempted'
    PREPUBLICATION = 'prepublication failure'
    ATTEMPTED = 'publication attempted; outcome uncertain'
    PUBLISHED = 'publication returned; verification incomplete'
    VERIFIED = 'final content verified'
    REUSED = 'matching copy reused'


@dataclass(frozen=True)
class Publication:
    export_id: str
    destination: str
    phase: PublicationPhase
    inspection: Inspection
    error: Exception | None = None

    @property
    def verified(self):
        return self.phase in (PublicationPhase.VERIFIED, PublicationPhase.REUSED)


def destination_path(value):
    if not isinstance(value, (str, Path)) or not str(value).strip() or '\x00' in str(value):
        raise ValueError('Choose a nonempty file path without NUL characters')
    return Path(value).absolute()


def protect(target, dataset):
    root = Path(os.path.abspath(dataset))
    if Path(os.path.abspath(target)).is_relative_to(root) or target.resolve().is_relative_to(root.resolve()):
        raise ValueError('The active Chronicle dataset directory is protected')


def metadata(value):
    # ns fields are available on supported Python platforms, but do not imply
    # identical OS semantics (notably Windows creation/change time).
    return tuple(getattr(value, key, None) for key in
                 ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns'))


def same_file_identity(left, right):
    """Bind observations by usable device/file IDs and suitable file type only.

    Size/timestamps may legitimately change while our stage is written. Unknown
    or zero IDs cannot authorize ownership, cleanup or cross-domain binding.
    """
    a, b = metadata(left), metadata(right)
    return (all(type(v) is int and v > 0 for v in (*a[:3], *b[:3]))
            and stat.S_IFMT(a[2]) in (stat.S_IFREG, stat.S_IFDIR)
            and a[:2] == b[:2] and stat.S_IFMT(a[2]) == stat.S_IFMT(b[2]))


def same_domain_metadata(before, after):
    """All six raw fields must remain stable within path or descriptor reads."""
    return (same_file_identity(before, after)
            and all(type(v) is int for v in (*metadata(before), *metadata(after)))
            and metadata(before) == metadata(after))


def path_matches_handle(path_observation, handle_observation, *, windows=None):
    """Bind an lstat observation to fstat without conflating Windows clocks.

    Provisional Windows contract, pending native field observations: CPython
    pathname ctime may expose creation time while fstat exposes change time.
    Keep both clocks in their own complete before/after stability checks. Only
    pathname synthesis of all executable bits is allowed as a mode difference.
    Content equality never substitutes for usable, equal device/file identity.
    The explicit switch permits isolated synthetic tests, not global OS patches.
    """
    if windows is None:
        windows = os.name == 'nt'
    if not windows:
        return same_domain_metadata(path_observation, handle_observation)
    if not same_file_identity(path_observation, handle_observation):
        return False
    p, h = metadata(path_observation), metadata(handle_observation)
    if not all(type(v) is int for v in (*p, *h)) or p[3:5] != h[3:5]:
        return False
    if p[2] != h[2] and not (stat.S_ISREG(p[2]) and p[2] == (h[2] | 0o111)):
        return False
    birth_path = getattr(path_observation, 'st_birthtime_ns', None)
    birth_handle = getattr(handle_observation, 'st_birthtime_ns', None)
    if birth_path is not None and birth_handle is not None:
        if (type(birth_path) is not int or type(birth_handle) is not int
                or birth_path < 0 or birth_path != birth_handle):
            return False
    return True


def _read_regular(target, observed, expected, digest):
    flags = os.O_RDONLY | getattr(os,'O_BINARY',0) | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_NONBLOCK',0)
    fd = os.open(target, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not path_matches_handle(observed, before):
            raise OSError('Destination changed before complete inspection')
        total, matches, hasher = 0, True, hashlib.sha256()
        while True:
            # One byte beyond observed size detects growth without an unbounded
            # read of a concurrently growing stream or retaining arbitrary files.
            chunk = os.read(fd, min(65536, max(1, observed.st_size-total+1)))
            if not chunk: break
            if chunk != expected[total:total+len(chunk)]: matches = False
            total += len(chunk); hasher.update(chunk)
            if total > observed.st_size: raise OSError('Destination grew during inspection')
        if total != observed.st_size: raise OSError('Incomplete destination read')
        if (not same_domain_metadata(before, os.fstat(fd))
                or not same_domain_metadata(observed, target.lstat())):
            raise OSError('Destination changed during complete inspection')
        actual_digest = hasher.hexdigest()
        result = (matches and total==len(expected) and actual_digest==digest), actual_digest
    except BaseException as primary:
        try: os.close(fd)
        except Exception as secondary: primary.add_note(f'Inspection descriptor close also failed: {secondary!r}')
        raise
    else:
        os.close(fd)
        return result


def inspect(target, expected, digest):
    if target is None: return Inspection(FileState.PENDING,None)
    name = str(target)
    try: observed = target.lstat()
    except FileNotFoundError: return Inspection(FileState.MISSING,name)
    except OSError as exc: return Inspection(FileState.UNVERIFIABLE,name,error=exc)
    if not stat.S_ISREG(observed.st_mode):
        return Inspection(FileState.CONFLICT,name)  # No open of FIFO, directory or final symlink.
    try:
        matching, actual_digest = _read_regular(target,observed,expected,digest)
        if matching: return Inspection(FileState.READY,name)
        return Inspection(FileState.CONFLICT,name,ContentConflict(name,metadata(observed),actual_digest))
    except OSError as exc:
        return Inspection(FileState.UNVERIFIABLE,name,error=exc)


def _owned(stage, created):
    observed = stage.lstat()
    if (created is None or not stat.S_ISREG(observed.st_mode)
            or not same_file_identity(observed, created)):
        raise OSError(f'Staging ownership is uncertain; retained {stage}')
    return observed


def _remove_owned(stage, created):
    try: _owned(stage,created)
    except FileNotFoundError: return
    stage.unlink()  # Bounded check; never the requested final pathname.


def materialize(export_id, target, expected, digest, dataset, *, confirmed_overwrite=False, expected_conflict=None):
    if type(confirmed_overwrite) is not bool:
        raise ValueError('confirmed_overwrite must be boolean')
    if expected_conflict is not None:
        if (type(expected_conflict) is not ContentConflict or type(expected_conflict.destination) is not str
                or type(expected_conflict.metadata) is not tuple or len(expected_conflict.metadata)!=6
                or any(type(v) is not int for v in expected_conflict.metadata[:4])
                or any(type(v) not in (int,type(None)) for v in expected_conflict.metadata[4:])
                or type(expected_conflict.sha256) is not str or len(expected_conflict.sha256)!=64
                or any(c not in '0123456789abcdef' for c in expected_conflict.sha256)):
            raise ValueError('Expected conflict must be a complete typed observation')
    if confirmed_overwrite and expected_conflict is None:
        raise ValueError('Confirmed overwrite requires its reviewed conflict observation')
    if not confirmed_overwrite and expected_conflict is not None:
        raise ValueError('Conflict observation without one-call consent')
    protect(target,dataset)
    initial = inspect(target,expected,digest)
    if initial.state==FileState.READY:
        return Publication(export_id,str(target),PublicationPhase.REUSED,initial)
    replacing = initial.state==FileState.CONFLICT and initial.conflict is not None
    if initial.state!=FileState.MISSING:
        if not (replacing and confirmed_overwrite):
            return Publication(export_id,str(target),PublicationPhase.NOT_ATTEMPTED,initial,initial.error)
        if initial.conflict != expected_conflict:
            return Publication(export_id,str(target),PublicationPhase.NOT_ATTEMPTED,
                               Inspection(FileState.UNVERIFIABLE,str(target)),OSError('Reviewed conflict target changed; inspect and consent again'))
    else:
        replacing = False  # Absence never grants replacement, even after earlier consent.
    stage = target.parent / f'.chronicle-timesheet-{uuid4()}.tmp'
    created = fd = handle = None
    phase, error = PublicationPhase.PREPUBLICATION, None
    try:
        if not target.parent.is_dir(): raise ValueError('Destination parent must be an existing directory')
        if stage==target: raise ValueError('Staging name must differ from destination')
        fd = os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600)
        created = os.fstat(fd)
        handle = os.fdopen(fd,'wb'); fd = None
        try:
            if handle.write(expected)!=len(expected): raise OSError('Incomplete staging write')
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException as primary:
            try: handle.close()
            except Exception as secondary: primary.add_note(f'Stage close also failed: {secondary!r}')
            raise
        else:
            handle.close()  # Successful close is required before publication.
        observed = _owned(stage,created)
        matching,_ = _read_regular(stage,observed,expected,digest)
        if not matching: raise OSError('Completed staging bytes do not match the frozen report')
        protect(target,dataset)
        if replacing:
            # Re-read the entire target after staging. Path ctime alone cannot
            # detect same-size/restored-mtime writes on every supported runtime.
            reviewed = inspect(target,expected,digest)
            if reviewed.state != FileState.CONFLICT or reviewed.conflict != expected_conflict:
                if reviewed.error is not None:
                    raise reviewed.error
                raise OSError('Destination changed during final complete reinspection')
            now = target.lstat()
            if not stat.S_ISREG(now.st_mode) or metadata(now)!=expected_conflict.metadata:
                raise OSError('Destination changed immediately before replacement')
        phase = PublicationPhase.ATTEMPTED
        if replacing: os.replace(stage,target)
        else: os.link(stage,target)  # Exclusive creation, no unsafe fallback.
        phase = PublicationPhase.PUBLISHED
        final = inspect(target,expected,digest)
        if final.state!=FileState.READY: raise final.error or OSError('Complete final destination verification did not succeed')
        phase = PublicationPhase.VERIFIED
    except Exception as exc:
        error = exc
        exc.add_note(f'{phase.value}: {target}. Registered evidence is unchanged; final output is never rolled back.')
    finally:
        if fd is not None:
            try: os.close(fd)
            except OSError as exc:
                if error: error.add_note(f'Stage descriptor close failed: {exc!r}')
                else: error = exc
        # A faulty stream close can leave our descriptor open. Close only if its
        # identity still agrees, never an arbitrarily reused descriptor number.
        if handle is not None and not handle.closed:
            try:
                descriptor = handle.fileno()
                current = os.fstat(descriptor)
                if created and same_file_identity(current,created): os.close(descriptor)
            except OSError as exc:
                if error: error.add_note(f'Stage stream cleanup failed: {exc!r}')
                else: error = exc
        if created is not None:
            try: _remove_owned(stage,created)
            except OSError as exc:
                if error: error.add_note(f'Owned staging cleanup failed: {exc!r}')
                else: error = exc
    if phase==PublicationPhase.VERIFIED:
        return Publication(export_id,str(target),phase,final,error)
    # Fresh inspection communicates current truth even after an ambiguous link/
    # replace exception; a failed call is not promoted to successful Save here.
    latest = inspect(target,expected,digest)
    if phase in (PublicationPhase.ATTEMPTED,PublicationPhase.PUBLISHED):
        latest = Inspection(latest.state,latest.destination,error=latest.error)  # No postpublication overwrite grant.
    return Publication(export_id,str(target),phase,latest,error)
