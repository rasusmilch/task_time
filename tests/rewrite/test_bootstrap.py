from pathlib import Path
import os
import subprocess
import sys

import pytest

from chronicle.sqlite_store import SQLiteStore
from chronicle.services import TimerService
from conftest import NOW, uid


def child(code, *arguments):
    env = {**os.environ, "PYTHONPATH": str(Path("src").resolve())}
    return subprocess.run([sys.executable, "-B", "-c", code, *map(str, arguments)], env=env,
                          text=True, capture_output=True, timeout=10)


def test_separate_process_second_owner_refused(store):
    code = "from chronicle.sqlite_store import SQLiteStore; import sys; s=SQLiteStore(sys.argv[1])"
    result = child(code, store.directory)
    assert result.returncode != 0
    assert "BlockingIOError" in result.stderr or "PermissionError" in result.stderr or "OSError" in result.stderr


def test_directory_alias_second_owner_refused(store, tmp_path):
    code = "from chronicle.sqlite_store import SQLiteStore; import sys; s=SQLiteStore(sys.argv[1])"
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(store.directory, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        if isinstance(exc, OSError) and exc.errno not in (1, 13, 38, 95):
            raise
        pytest.skip(f"Native directory symlink unavailable: {exc}")
    assert child(code, alias).returncode != 0


def test_normal_restart_and_crash_keep_same_active_identity(tmp_path):
    path = tmp_path / "fresh"
    store = SQLiteStore(path, create=True, timezone="America/Chicago")
    service = TimerService(store)
    task, entry = uid(), uid()
    service.create_task(task, "Timer", request_id=uid(), action_utc_us=NOW)
    service.start_timer(task, entry, expected_task_version=1, request_id=uid(), action_utc_us=NOW)
    store.close()
    code = """from chronicle.sqlite_store import SQLiteStore
import sys,os
s=SQLiteStore(sys.argv[1]); assert s.connection.execute('SELECT entry_id FROM active_timer').fetchone()[0] == sys.argv[2]
os._exit(0)
"""
    assert child(code, path, entry).returncode == 0
    reopened = SQLiteStore(path)
    try:
        active = TimerService(reopened).read_current_state(cutoff_utc_us=NOW + 1)["active"]
        assert active["entry_id"] == entry and active["start_utc_us"] == NOW
        assert reopened.connection.execute("SELECT count(*) FROM committed_requests").fetchone()[0] == 2
        assert list(reopened.connection.execute("SELECT * FROM work_revisions")) == []
    finally:
        reopened.close()


def test_launcher_requires_explicit_path_without_touching_home(tmp_path):
    result = subprocess.run([sys.executable, "-B", "run_chronicle.py"], env={**os.environ, "HOME": str(tmp_path)},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "--data-dir" in result.stderr
    assert list(tmp_path.iterdir()) == []
