from datetime import timezone
from types import SimpleNamespace

import pytest

from task_timer.dialogs import SelectedTaskExportDialog
from task_timer.time_utils import parse_utc_z


def _svc() -> object:
    return SimpleNamespace(local_tz=timezone.utc, find_active_export_checkpoint=lambda: None)


def test_dialog_validation_requires_task_selection() -> None:
    with pytest.raises(ValueError):
        SelectedTaskExportDialog.validate_inputs(selected_task_ids=[], window_mode="checkpoint", start_date_text="2026-01-01", end_date_text="2026-01-02", mark_submitted=False, reason="", service=_svc())


def test_dialog_validation_custom_range_end_after_start() -> None:
    with pytest.raises(ValueError):
        SelectedTaskExportDialog.validate_inputs(selected_task_ids=["t1"], window_mode="custom", start_date_text="2026-01-02", end_date_text="2026-01-01", mark_submitted=False, reason="", service=_svc())


def test_dialog_validation_reason_required_when_mark_submitted() -> None:
    with pytest.raises(ValueError):
        SelectedTaskExportDialog.validate_inputs(selected_task_ids=["t1"], window_mode="checkpoint", start_date_text="2026-01-01", end_date_text="2026-01-02", mark_submitted=True, reason=" ", service=_svc())


def test_dialog_select_all_and_clear_all() -> None:
    dlg = SelectedTaskExportDialog.__new__(SelectedTaskExportDialog)
    dlg._task_vars = {"a": SimpleNamespace(set=lambda v: setattr(dlg, "a", v)), "b": SimpleNamespace(set=lambda v: setattr(dlg, "b", v))}
    SelectedTaskExportDialog.select_all_tasks(dlg)
    assert dlg.a is True and dlg.b is True
    SelectedTaskExportDialog.clear_all_tasks(dlg)
    assert dlg.a is False and dlg.b is False


def test_dialog_explanatory_text_present() -> None:
    source = open("src/task_timer/dialogs.py", encoding="utf-8").read()
    assert "Selecting a parent task includes its subtasks. Selecting an individual subtask exports only that subtask." in source
