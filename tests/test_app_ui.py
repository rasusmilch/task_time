from types import SimpleNamespace

from task_timer.app import TaskTimerApp, TaskTimerService
from task_timer.mini_mode import build_task_choices
from task_timer.storage import EventStorage
from task_timer.time_utils import format_duration_hm


class _FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[int] = []

    def after(self, delay_ms: int, callback: object) -> str:
        self.after_calls.append(delay_ms)
        return "after-id"


def test_tick_refreshes_live_values_only() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = _FakeRoot()
    app.service = SimpleNamespace(local_tz=None)
    called: list[str] = []
    app.refresh_live_values = lambda: called.append("live")
    app.refresh_structure = lambda: called.append("structure")

    TaskTimerApp._tick(app)

    assert called == ["live"]
    assert app.root.after_calls


def test_ui_duration_formatter_is_hours_minutes_only() -> None:
    assert format_duration_hm(59) == "00:00"
    assert format_duration_hm(61) == "00:01"
    assert format_duration_hm(3661) == "01:01"


def test_task_id_stable_after_rename_and_history_retained(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Original", "n1")
    service.add_manual_interval(task_id, start_local=_local_dt("2026-01-01 10:00"), stop_local=_local_dt("2026-01-01 11:00"), reason="seed")
    before = service.task_elapsed(service.state.tasks[task_id])
    service.update_task(task_id, "Renamed", "n2")
    service.start_task(task_id)
    service.stop_task(task_id)
    assert task_id in service.state.tasks
    assert service.state.tasks[task_id].name == "Renamed"
    assert service.task_elapsed(service.state.tasks[task_id]) >= before


def test_build_task_choices_uses_friendly_labels_and_uuid_mapping() -> None:
    tasks = [
        SimpleNamespace(task_id="11111111-1111-1111-1111-111111111111", name="Build", is_deleted=False),
        SimpleNamespace(task_id="22222222-2222-2222-2222-222222222222", name="Build", is_deleted=False),
    ]
    labels, label_to_id, id_to_label = build_task_choices(tasks)
    assert labels[0].startswith("Build (")
    assert label_to_id[labels[0]] == tasks[0].task_id
    assert id_to_label[tasks[1].task_id] == labels[1]


def test_add_task_uses_dialog_name_and_note(monkeypatch) -> None:
    created: list[tuple[str, str]] = []
    service = SimpleNamespace(create_task=lambda name, notes: created.append((name, notes)) or "task-1")
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    app.service = service
    app.rows = {}
    app.refresh_structure = lambda: None
    app.refresh_live_values = lambda: None

    class _Dialog:
        confirmed = True
        name = "  New Name  "
        notes = "hello"

        def __init__(self, parent: object) -> None:
            pass

    monkeypatch.setattr("task_timer.app.AddTaskDialog", _Dialog)
    TaskTimerApp.add_task(app)
    assert created == [("  New Name  ", "hello")]


def _local_dt(value: str):
    from datetime import datetime

    return datetime.strptime(value, "%Y-%m-%d %H:%M").astimezone()
