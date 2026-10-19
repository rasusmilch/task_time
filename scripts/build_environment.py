"""Build preflight/provenance only; never opens a Chronicle dataset."""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import platform
import sqlite3
import struct
import sys
import tkinter

# Script execution from an unrelated working directory still inspects this source.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from chronicle.sqlite_store import runtime_info


def inspect_environment(venv: Path, *, windows: bool = True) -> dict:
    if sys.version_info < (3, 11) or sys.version_info >= (3, 16):
        raise RuntimeError('Build inputs require CPython 3.11–3.15; source floor remains 3.11')
    if sys.prefix == sys.base_prefix or Path(sys.prefix).resolve() != venv.resolve():
        raise RuntimeError('Refusing installation/build outside the selected virtual environment')
    if windows and (sys.platform != 'win32' or platform.python_implementation() != 'CPython'
                    or struct.calcsize('P') != 8 or platform.machine().lower() not in ('amd64', 'x86_64')):
        raise RuntimeError('This build input set targets native Windows x64 CPython')
    info = runtime_info()  # STRICT floor alone does not qualify the linked SQLite build.
    with sqlite3.connect(':memory:') as connection:
        info['source_id'] = connection.execute('SELECT sqlite_source_id()').fetchone()[0]
        info['compile_options'] = [r[0] for r in connection.execute('PRAGMA compile_options')]
    info.update(python=sys.version, executable=sys.executable, architecture=platform.machine(),
                platform=platform.platform(), tcl=tkinter.Tcl().eval('info patchlevel'),
                tk_linked=tkinter.TkVersion)
    return info


def verified_inputs(lock_path: Path, *, exact: bool = True) -> dict:
    required = {}
    for line in lock_path.read_text().splitlines():
        if line and not line.startswith('#'):
            name, rest = line.split('==', 1)
            version, artifact = rest.split(' --hash=sha256:', 1)
            if len(artifact) != 64 or any(c not in '0123456789abcdef' for c in artifact):
                raise RuntimeError('Invalid artifact hash in build lock')
            required[name.lower().replace('_', '-')] = version
    installed = {d.metadata['Name'].lower().replace('_', '-'): d.version for d in distributions()}
    if exact and any(installed.get(k) != v for k, v in required.items()):
        raise RuntimeError(f'Installed dependencies do not match the build lock: {required}')
    extras = installed.keys() - required.keys() - {'chronicle'}
    if extras:
        raise RuntimeError(f'Uncontrolled build dependencies present; use a fresh venv: {sorted(extras)}')
    return {k: installed[k] for k in sorted(required) if k in installed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--venv', type=Path, required=True)
    parser.add_argument('--record', type=Path)
    args = parser.parse_args(argv)
    info = inspect_environment(args.venv)
    lock = ROOT / 'requirements/windows-build.lock'
    verified_inputs(lock, exact=False)  # Refuse unrelated environments before any install.
    if args.record:
        info['dependencies'] = verified_inputs(lock)
        info['lock_sha256'] = hashlib.sha256(lock.read_bytes()).hexdigest()
        inputs = [ROOT / 'chronicle.spec', ROOT / 'run_chronicle.py', ROOT / 'pyproject.toml',
                  *sorted((ROOT / 'src/chronicle').glob('*.py')),
                  *sorted((ROOT / 'scripts').glob('build*'))]
        info['source_sha256'] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs if p.is_file()}
        import _sqlite3
        info['sqlite_module'] = getattr(_sqlite3, '__file__', 'built-in')
        native = [Path(getattr(_sqlite3, '__file__', sys.executable)), *Path(sys.base_prefix).glob('DLLs/sqlite3.dll')]
        info['sqlite_binary_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in native}
        with args.record.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(info, indent=2) + '\n')
    print(json.dumps(info, indent=2))


if __name__ == '__main__':
    main()
