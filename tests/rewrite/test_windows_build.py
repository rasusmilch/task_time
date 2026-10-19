"""Executed build-tool guards plus static Windows wiring, not native qualification."""
from importlib import util
from importlib.metadata import version
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest


SPEC = util.spec_from_file_location('chronicle_build_environment', 'scripts/build_environment.py')
module = util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
LOCK = Path('requirements/windows-build.lock')


def locked():
    return {line.split('==')[0].lower().replace('_', '-'): line.split('==')[1].split()[0]
            for line in LOCK.read_text().splitlines() if line and not line.startswith('#')}


def test_windows_build_inputs_have_exact_versions_and_artifact_hashes():
    values = locked()
    assert set(values) == {'altgraph', 'packaging', 'pefile', 'pip', 'pyinstaller',
                           'pyinstaller-hooks-contrib', 'pywin32-ctypes', 'setuptools', 'tzdata', 'wheel'}
    assert values['tzdata'] == version('tzdata') and values['pyinstaller'] == '6.22.3'
    for line in LOCK.read_text().splitlines():
        if line and not line.startswith('#'):
            assert re.fullmatch(r'[A-Za-z0-9_-]+==[0-9.]+ --hash=sha256:[0-9a-f]{64}', line)


def test_actual_environment_preflight_and_system_python_refusal():
    details = module.inspect_environment(Path(sys.prefix), windows=False)
    assert details['source_id'] and details['sqlite'] and details['tcl']
    with pytest.raises(RuntimeError, match='selected virtual environment'):
        module.inspect_environment(Path(sys.prefix) / 'wrong', windows=False)
    if sys.platform != 'win32':
        with pytest.raises(RuntimeError, match='native Windows'):
            module.inspect_environment(Path(sys.prefix))


@pytest.mark.parametrize('change', ['missing', 'wrong', 'extra', 'none'])
def test_build_provenance_rejects_uncontrolled_dependencies(monkeypatch, change):
    values = locked()
    if change == 'missing': values.pop('tzdata')
    if change == 'wrong': values['packaging'] = '0'
    if change == 'extra': values['uncontrolled'] = '1'
    monkeypatch.setattr(module, 'distributions', lambda: [SimpleNamespace(metadata={'Name': k}, version=v) for k, v in values.items()])
    if change == 'none':
        assert module.verified_inputs(LOCK) == locked()
    else:
        with pytest.raises(RuntimeError): module.verified_inputs(LOCK)


def test_build_provenance_records_exclusively_without_dataset(tmp_path, monkeypatch):
    inspect = module.inspect_environment
    monkeypatch.setattr(module, 'inspect_environment', lambda venv: inspect(venv, windows=False))
    monkeypatch.setattr(module, 'verified_inputs', lambda path, **kwargs: locked())
    record = tmp_path / 'environment.json'
    module.main(['--venv', sys.prefix, '--record', str(record)])
    result = json.loads(record.read_text())
    assert result['source_sha256']['src/chronicle/sqlite_store.py']
    assert result['sqlite_binary_sha256'] and result['lock_sha256']
    before = record.read_bytes()
    with pytest.raises(FileExistsError): module.main(['--venv', sys.prefix, '--record', str(record)])
    assert record.read_bytes() == before and list(tmp_path.iterdir()) == [record]


def test_powershell_steps_are_guarded_and_no_destructive_reuse():
    # Wiring assertions only: real PS parsing/invocation remains a native gate.
    source = Path('scripts/build.ps1').read_text()
    assert '--require-hashes --only-binary=:all:' in source
    assert 'pip --isolated install --no-user --require-hashes' in source
    assert 'install --no-user $RepoRoot' not in source
    assert '-I -B $Preflight --venv $VenvPath' in source
    assert source.index('Existing build/ or dist/') < source.index('-m pip --isolated install')
    assert 'Remove-Item' not in source and 'Write-Warning' not in source
    commands = [line for line in source.splitlines() if line.strip().startswith('& ')]
    assert len(commands) == source.count('if ($LASTEXITCODE -ne 0)')
    assert '--noconfirm' not in next(line for line in commands if 'PyInstaller' in line)
    assert 'upx=True' not in Path('chronicle.spec').read_text()
