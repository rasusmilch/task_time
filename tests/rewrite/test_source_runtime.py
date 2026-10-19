from pathlib import Path
import runpy
import sys


def test_only_new_root_runtime_and_no_legacy_fallback():
    before = set(sys.modules)
    result = runpy.run_path("run_chronicle.py", run_name="inspect_launcher")
    assert result["main"].__module__ == "chronicle.bootstrap"
    assert not any(name == "task_timer" or name.startswith("task_timer.") for name in set(sys.modules) - before)
    assert not Path("run_task_timer.py").exists()


def test_source_dependencies_and_offline_rules():
    import sqlite3
    import tomllib
    from chronicle import sqlite_store
    from chronicle.timekeeping import load_zone
    project = tomllib.loads(Path("pyproject.toml").read_text())
    assert project["project"]["dependencies"] == ["tzdata==2026.5"]
    runtime_requirements = [line for line in Path("requirements.txt").read_text().splitlines()
                            if line and not line.startswith("#")]
    assert runtime_requirements == project["project"]["dependencies"]
    assert project["tool"]["setuptools"]["packages"]["find"]["include"] == ["chronicle*"]
    assert sqlite_store.sqlite3 is sqlite3
    assert load_zone("America/Chicago").key == "America/Chicago"


def test_source_launcher_needs_no_project_install_or_executable_builder(tmp_path):
    import os
    import subprocess
    # Fresh isolated import state; reject legacy and optional executable-builder imports.
    code = r"""
import importlib.abc, runpy, sys
class Forbidden(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in ('task_timer', 'PyInstaller', 'apsw', 'pysqlite3'):
            raise AssertionError('Forbidden runtime import: ' + fullname)
sys.meta_path.insert(0, Forbidden())
sys.argv = ['run_chronicle.py', '--help']
runpy.run_path('run_chronicle.py', run_name='__main__')
"""
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code],
                            env={**os.environ, 'HOME': str(tmp_path)}, capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert '--data-dir' in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_missing_tk_has_actionable_error(tmp_path):
    from test_bootstrap import child
    result = child("""
import importlib.abc, runpy, sys
class MissingTk(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname == 'tkinter':
            raise ModuleNotFoundError('No tkinter', name='tkinter')
sys.meta_path.insert(0, MissingTk())
runpy.run_path('run_chronicle.py', run_name='inspect_launcher')
""")
    assert result.returncode != 0
    assert 'requires Python with Tcl/Tk' in result.stderr


def test_missing_tzdata_has_actionable_error(monkeypatch):
    import pytest
    from chronicle import timekeeping
    def missing(*args):
        raise ModuleNotFoundError('No tzdata', name='tzdata')
    monkeypatch.setattr(timekeeping, 'files', missing)
    with pytest.raises(ValueError, match=r'pip install.*tzdata==2026\.5'):
        timekeeping.load_zone('America/Chicago')
