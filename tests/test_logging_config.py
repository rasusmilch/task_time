from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from loguru import logger

from task_timer.app import TaskTimerApp
from task_timer.logging_config import configure_logging


def test_configure_logging_creates_log_dir_and_file_path(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path)
    logger.info("hello")
    logger.remove()
    assert log_path.name == "chronicle.log"
    assert (tmp_path / "logs").exists()
    assert "hello" in log_path.read_text(encoding="utf-8")


def test_configure_logging_rotation_config_does_not_error(tmp_path: Path) -> None:
    log_path = configure_logging(tmp_path)
    logger.info("rotation-check")
    logger.remove()
    assert log_path.exists()


def test_tk_exception_handler_logs_and_shows_message(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = configure_logging(tmp_path)
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.log_path = log_path
    app._showing_error_dialog = False

    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "task_timer.app.messagebox.showerror", lambda t, m: shown.append((t, m))
    )

    try:
        raise ValueError("boom")
    except ValueError as exc:
        TaskTimerApp._handle_tk_exception(app, ValueError, exc, exc.__traceback__)

    logger.remove()
    assert shown
    assert shown[0][0] == "Chronicle Error"
    assert "Details were written to the log file" in shown[0][1]
    assert "Unhandled Tkinter callback exception" in log_path.read_text(
        encoding="utf-8"
    )


def test_move_task_value_error_logs_warning(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    app.service = SimpleNamespace(
        state=SimpleNamespace(
            tasks={"t1": SimpleNamespace(is_deleted=False, parent_task_id="old")}
        ),
        move_task=lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad move")),
    )
    app._selected_task_id = lambda: "t1"
    app._after_state_change = lambda: None
    app.refresh_structure = lambda: None
    app.refresh_live_values = lambda: None
    app._refresh_selected_task_panel = lambda: None
    app.task_tree = SimpleNamespace(
        exists=lambda _x: False, selection_set=lambda _x: None
    )
    app.expanded_parents = set()

    class _Dialog:
        confirmed = True
        new_parent_task_id = None
        reason = ""

    monkeypatch.setattr("task_timer.app.MoveTaskDialog", lambda *_a, **_k: _Dialog())
    errors: list[str] = []
    monkeypatch.setattr(
        "task_timer.app.messagebox.showerror", lambda _t, m: errors.append(m)
    )
    warnings: list[str] = []
    sink = logger.add(lambda m: warnings.append(str(m)), level="WARNING")

    TaskTimerApp._move_task(app, "t1")

    logger.remove(sink)
    assert errors == ["bad move"]
    assert any("User-facing validation error" in item for item in warnings)
