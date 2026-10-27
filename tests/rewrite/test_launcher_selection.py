"""Isolated bounded launcher settings and explicit offline timezone choices."""
import json
import os
from pathlib import Path

import pytest

from chronicle import launcher_selection as ls
from chronicle.startup import (TIMEZONES, WINDOWS_ZONES, OTHER, admit_folder,
                               selected_timezone, suggested_timezone)
from test_backup_restore import symlink


def test_locations_are_per_user_and_display_creates_nothing(tmp_path):
    env = {'HOME': str(tmp_path), 'LOCALAPPDATA': str(tmp_path)}
    win = ls.locations(environ=env, platform='win32')
    assert win.folder == tmp_path/'Chronicle'/'Data'
    assert win.record == tmp_path/'Chronicle'/'launcher-selection.json'
    assert ls.locations(environ=env, platform='linux').folder == tmp_path/'.local'/'share'/'Chronicle'/'Data'
    assert ls.locations(environ=env, platform='darwin').folder == tmp_path/'Library'/'Application Support'/'Chronicle'/'Data'
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('env', [{}, {'LOCALAPPDATA': 'relative'}, {'LOCALAPPDATA': '//server/share'}])
def test_missing_unsuitable_windows_appdata_requires_choice(env):
    value = ls.locations(environ=env, platform='win32')
    assert value.folder is value.record is None and value.diagnostic


def test_record_round_trip_contains_only_version_and_absolute_path(tmp_path):
    path = tmp_path/'prefs'/'launcher-selection.json'
    data = tmp_path/'spaced Unicode Ω'
    assert ls.read_selection(path) is None
    ls.remember(path, data, None)
    first = ls.read_selection(path)
    assert first.directory == data
    assert json.loads(first.raw) == {'format_version': 1, 'dataset_directory': str(data)}
    other = tmp_path/'other'
    ls.remember(path, other, first)
    assert ls.read_selection(path).directory == other
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]


@pytest.mark.parametrize('raw', [b'', b'{', b'[]', b'null', b'\xff',
    b'{"format_version":2,"dataset_directory":"/tmp/x"}',
    b'{"format_version":true,"dataset_directory":"/tmp/x"}',
    b'{"format_version":1,"dataset_directory":"relative"}',
    b'{"format_version":1,"dataset_directory":4}',
    b'{"format_version":1,"format_version":1,"dataset_directory":"/tmp/x"}',
    b'{"format_version":1,"dataset_directory":"/tmp/x","timezone":"UTC"}', b'x'*8193])
def test_bad_records_are_retained_and_cannot_be_overwritten(tmp_path, raw):
    path = tmp_path/'selection'
    path.write_bytes(raw); before = path.stat()
    for action in (lambda: ls.read_selection(path), lambda: ls.remember(path, tmp_path/'new', None)):
        with pytest.raises((ValueError, OSError, UnicodeError)):
            action()
        assert path.read_bytes() == raw
        assert path.stat().st_ino == before.st_ino and path.stat().st_mtime_ns == before.st_mtime_ns
    assert sorted(p.name for p in tmp_path.iterdir()) == ['selection']


@pytest.mark.parametrize('kind', ['directory', 'symlink', 'dangling', 'hardlink'])
def test_unexpected_settings_objects_preserved(tmp_path, kind):
    path, sentinel = tmp_path/'selection', tmp_path/'sentinel'
    sentinel.write_bytes(b'outside record')
    if kind == 'directory': path.mkdir()
    elif kind == 'hardlink': os.link(sentinel, path)
    else: symlink(sentinel if kind == 'symlink' else tmp_path/'absent', path)
    before = sentinel.stat()
    with pytest.raises((ValueError, OSError)):
        ls.remember(path, tmp_path/'new', None)
    assert sentinel.read_bytes() == b'outside record'
    assert sentinel.stat().st_ino == before.st_ino and sentinel.stat().st_mtime_ns == before.st_mtime_ns
    assert path.exists() or path.is_symlink()


def test_changed_valid_record_cannot_consume_stale_selection(tmp_path):
    path = tmp_path/'record'
    ls.remember(path, tmp_path/'one', None)
    first = ls.read_selection(path)
    ls.remember(path, tmp_path/'two', first)
    raw = path.read_bytes()
    with pytest.raises(OSError, match='changed'):
        ls.remember(path, tmp_path/'three', first)
    assert path.read_bytes() == raw


@pytest.mark.parametrize('fault', ['fsync', 'link', 'replace', 'race'])
def test_publication_failure_preserves_previous_or_racing_file(tmp_path, monkeypatch, fault):
    path = tmp_path/'record'; expected = None
    if fault == 'replace':
        ls.remember(path, tmp_path/'one', None)
        expected = ls.read_selection(path)
    before = path.read_bytes() if path.exists() else None
    primary = OSError('publication failure')
    def fail(*a): raise primary
    if fault == 'race':
        original = ls.os.link
        def race(source, destination):
            path.write_bytes(b'unrelated racing file')
            return original(source, destination)
        monkeypatch.setattr(ls.os, 'link', race)
    else: monkeypatch.setattr(ls.os, fault, fail)
    with pytest.raises(OSError) as caught:
        ls.remember(path, tmp_path/'data', expected)
    if fault == 'race': assert path.read_bytes() == b'unrelated racing file'
    else:
        assert caught.value is primary
        assert (path.read_bytes() if path.exists() else None) == before
    assert not list(tmp_path.glob('.launcher-selection-*'))


def test_settings_cannot_be_written_inside_selected_dataset(tmp_path):
    with pytest.raises(ValueError, match='outside'):
        ls.remember(tmp_path/'selection', tmp_path, None)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('windows,iana', WINDOWS_ZONES.items())
def test_exact_offline_windows_mapping(windows, iana):
    label = suggested_timezone(windows)
    assert TIMEZONES[label] == iana
    assert selected_timezone(label, '') == iana


@pytest.mark.parametrize('unknown', [None, '', 'CST', 'UTC-06:00', 'Central Standard Time (Mexico)',
                                     'central standard time', 'Eastern Standard Time_dstoff'])
def test_unsupported_windows_id_never_guesses(unknown):
    assert suggested_timezone(unknown) == ''


def test_advanced_zone_uses_packaged_validation():
    assert selected_timezone(OTHER, ' Australia/Lord_Howe ') == 'Australia/Lord_Howe'
    for label, text in [('', ''), (OTHER, 'Not/AZone'), ('CST', ''), (OTHER, '../Chicago')]:
        with pytest.raises(ValueError): selected_timezone(label, text)


@pytest.mark.parametrize('bad', ['', 'relative', '//server/share', '\\\\server\\share', 'bad\0path'])
def test_bad_dataset_paths_do_not_create(bad, tmp_path):
    with pytest.raises(ValueError): admit_folder(bad, create=True)
    assert not list(tmp_path.iterdir())


def test_dataset_admission_is_noncreating_and_protects_unknown(tmp_path):
    missing = tmp_path/'new'
    assert admit_folder(missing, create=True) == missing and not missing.exists()
    with pytest.raises(ValueError, match='missing'): admit_folder(missing, create=False)
    missing.mkdir(); sentinel = missing/'unknown'; sentinel.write_bytes(b'keep')
    with pytest.raises(ValueError, match='empty'): admit_folder(missing, create=True)
    assert sentinel.read_bytes() == b'keep'


def test_redirected_destination_and_appdata_refuse(tmp_path):
    target = tmp_path/'target'; target.mkdir()
    link = tmp_path/'alias'; symlink(target, link, True)
    with pytest.raises(ValueError, match='redirection'): admit_folder(link/'new', create=True)
    value = ls.locations(environ={'LOCALAPPDATA': str(link)}, platform='win32')
    assert value.folder is value.record is None
    assert not list(target.iterdir())


@pytest.mark.parametrize('fault', ['read', 'close', 'growing', 'mutation'])
def test_record_read_faults_never_return_a_selection(tmp_path, monkeypatch, fault):
    path = tmp_path/'record'
    ls.remember(path, tmp_path/'data', None)
    read, close = ls.os.read, ls.os.close
    primary = OSError('selection read failure')
    calls = []
    def changed(fd, count):
        if fault == 'read': raise primary
        value = read(fd, count)
        if not calls:
            calls.append(True)
            if fault == 'growing':
                with path.open('ab') as f: f.write(b'x'*(ls.LIMIT+1))
            elif fault == 'mutation':
                raw = path.read_bytes(); path.write_bytes(raw.replace(b'data', b'DATA'))
        return value
    def failed_close(fd):
        close(fd)
        raise primary
    if fault == 'close': monkeypatch.setattr(ls.os, 'close', failed_close)
    else: monkeypatch.setattr(ls.os, 'read', changed)
    with pytest.raises(OSError) as caught: ls.read_selection(path)
    if fault in ('read', 'close'): assert caught.value is primary
    assert path.exists()


def test_secondary_cleanup_failure_retains_primary_and_stage(tmp_path, monkeypatch):
    primary = OSError('primary sync failure')
    def fail(*a): raise primary
    def cleanup(*a): raise OSError('secondary cleanup failure')
    monkeypatch.setattr(ls.os, 'fsync', fail)
    monkeypatch.setattr(ls, '_remove_owned', cleanup)
    with pytest.raises(OSError) as caught: ls.remember(tmp_path/'selection', tmp_path/'data', None)
    assert caught.value is primary
    assert any('secondary cleanup failure' in n for n in primary.__notes__)
    assert not (tmp_path/'selection').exists()
    assert len(list(tmp_path.glob('.launcher-selection-*'))) == 1
