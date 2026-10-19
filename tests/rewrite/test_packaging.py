import ast
from pathlib import Path
import runpy
import sys


def test_only_new_root_runtime_and_no_legacy_fallback():
    before = set(sys.modules)
    result = runpy.run_path("run_chronicle.py", run_name="inspect_launcher")
    assert result["main"].__module__ == "chronicle.bootstrap"
    assert not any(name == "task_timer" or name.startswith("task_timer.") for name in set(sys.modules) - before)
    assert not Path("run_task_timer.py").exists()


def test_spec_package_selection_and_offline_data():
    source = Path("chronicle.spec").read_text()
    ast.parse(source)
    assert 'collect_data_files("tzdata")' in source
    assert '"task_timer"' in source
    assert '"chronicle.bootstrap"' in source
    import tomllib
    project = tomllib.loads(Path("pyproject.toml").read_text())
    assert project["tool"]["setuptools"]["packages"]["find"]["include"] == ["chronicle*"]
