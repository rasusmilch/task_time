from __future__ import annotations

import runpy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_root_launcher_imports_package_from_src_layout(monkeypatch) -> None:
    launcher = REPO_ROOT / "run_task_timer.py"

    src_paths = {str(REPO_ROOT / "src"), str((REPO_ROOT / "src").resolve())}
    cleaned_path = [entry for entry in sys.path if entry not in src_paths]
    monkeypatch.setattr(sys, "path", cleaned_path)

    monkeypatch.delitem(sys.modules, "task_timer", raising=False)
    monkeypatch.delitem(sys.modules, "task_timer.main", raising=False)

    result_globals = runpy.run_path(str(launcher), run_name="task_timer_launcher_test")

    imported_main = result_globals["main"]
    assert imported_main.__module__ == "task_timer.main"
