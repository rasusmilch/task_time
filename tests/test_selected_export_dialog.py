from datetime import timezone
from types import SimpleNamespace

import pytest

from task_timer.dialogs import SelectedTaskExportDialog


def _svc() -> object:
    return SimpleNamespace(local_tz=timezone.utc, find_active_export_checkpoint=lambda: None)


def test_dialog_validation_requires_task_selection() -> None:
    with pytest.raises(ValueError):
        SelectedTaskExportDialog.validate_inputs(
            selected_task_ids=[],
            window_mode="checkpoint",
            start_date_text="2026-01-01",
            end_date_text="2026-01-02",
            mark_submitted=False,
            reason="",
            service=_svc(),
        )


def test_dialog_validation_custom_range_end_after_start() -> None:
    with pytest.raises(ValueError):
        SelectedTaskExportDialog.validate_inputs(
            selected_task_ids=["t1"],
            window_mode="custom",
            start_date_text="2026-01-02",
            end_date_text="2026-01-01",
            mark_submitted=False,
            reason="",
            service=_svc(),
        )


def test_dialog_validation_reason_required_when_mark_submitted() -> None:
    with pytest.raises(ValueError):
        SelectedTaskExportDialog.validate_inputs(
            selected_task_ids=["t1"],
            window_mode="checkpoint",
            start_date_text="2026-01-01",
            end_date_text="2026-01-02",
            mark_submitted=True,
            reason=" ",
            service=_svc(),
        )


def test_dialog_validation_reason_optional_when_not_marking_submitted() -> None:
    result = SelectedTaskExportDialog.validate_inputs(
        selected_task_ids=["t1"],
        window_mode="checkpoint",
        start_date_text="2026-01-01",
        end_date_text="2026-01-02",
        mark_submitted=False,
        reason=" ",
        service=_svc(),
    )
    assert result.reason == ""
    assert result.mark_submitted is False


def test_dialog_select_all_and_clear_all() -> None:
    dlg = SelectedTaskExportDialog.__new__(SelectedTaskExportDialog)
    dlg._task_vars = {
        "a": SimpleNamespace(set=lambda v: setattr(dlg, "a", v)),
        "b": SimpleNamespace(set=lambda v: setattr(dlg, "b", v)),
    }
    SelectedTaskExportDialog.select_all_tasks(dlg)
    assert dlg.a is True and dlg.b is True
    SelectedTaskExportDialog.clear_all_tasks(dlg)
    assert dlg.a is False and dlg.b is False


def test_dialog_explanatory_text_present() -> None:
    source = open("src/task_timer/dialogs.py", encoding="utf-8").read()
    assert (
        "Selecting a parent task includes its subtasks. Selecting an individual subtask exports only that subtask."
        in source
    )


def test_dialog_layout_uses_dedicated_task_list_frame_with_adjacent_scrollbar() -> None:
    source = open("src/task_timer/dialogs.py", encoding="utf-8").read()
    assert "task_list_frame = ttk.Frame(task_area)" in source
    assert "canvas = tk.Canvas(" in source
    assert "height=220" in source
    assert "width=500" in source
    assert "bd=0" in source
    assert "borderwidth=0" in source
    assert "highlightthickness=0" in source
    assert (
        'scroll = ttk.Scrollbar(task_list_frame, orient="vertical", command=canvas.yview)' in source
    )
    assert 'canvas.grid(row=0, column=0, sticky="nsew")' in source
    assert 'scroll.grid(row=0, column=1, sticky="ns")' in source


def test_dialog_layout_has_controls_and_actions_outside_scrollable_task_list() -> None:
    source = open("src/task_timer/dialogs.py", encoding="utf-8").read()
    assert "control_buttons = ttk.Frame(task_area)" in source
    assert "options_frame = ttk.Frame(frame)" in source
    assert "reason_row = ttk.Frame(options_frame)" in source
    assert 'ttk.Button(actions, text="Export Selected", command=self._confirm).pack(' in source
    assert 'side="right"' in source
    assert 'ttk.Button(actions, text="Cancel", command=self.window.destroy).pack(' in source
    assert "padx=4" in source


def test_dialog_contains_mark_submitted_and_reason_controls() -> None:
    source = open("src/task_timer/dialogs.py", encoding="utf-8").read()
    assert "Mark exported time as already entered into Epicor" in source
    assert 'ttk.Label(reason_row, text="Reason")' in source
    assert 'self.reason_var = StringVar(value="Job closing / entered into Epicor")' in source


def test_dialog_task_canvas_border_and_highlight_are_disabled() -> None:
    source = open("src/task_timer/dialogs.py", encoding="utf-8").read()
    assert "bd=0" in source
    assert "borderwidth=0" in source
    assert "highlightthickness=0" in source


def test_dialog_mark_submitted_checkbutton_uses_supported_options_only() -> None:
    source = open("src/task_timer/dialogs.py", encoding="utf-8").read()
    block = source.split("ttk.Checkbutton(\n            options_frame,", 1)[1].split(
        ').pack(anchor="w", fill="x")', 1
    )[0]
    assert "wraplength=" not in block
    assert "justify=" not in block
