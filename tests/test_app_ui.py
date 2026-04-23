from datetime import timezone
from types import SimpleNamespace

from task_timer.app import STOPPED_COLOR, TaskTimerApp, TaskTimerService
from task_timer.models import TaskState
from task_timer.mini_mode import MiniModeWindow
from task_timer.storage import EventStorage
from task_timer.time_utils import format_duration_hm


class _FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[int] = []
        self.iconified = False

    def after(self, delay_ms: int, callback: object) -> str:
        self.after_calls.append(delay_ms)
        return "after-id"

    def iconify(self) -> None:
        self.iconified = True


def test_tick_refreshes_live_values_only() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = _FakeRoot()
    app.service = SimpleNamespace(local_tz=timezone.utc)
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


def test_starting_one_task_stops_prior_running_task(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_1 = service.create_task("Task 1", "")
    task_2 = service.create_task("Task 2", "")

    service.start_task(task_1)
    service.start_task(task_2)

    assert not service.state.tasks[task_1].is_running
    assert service.state.tasks[task_2].is_running
    assert service.state.running_task_id == task_2


def test_row_refresh_sets_toggle_text_and_color() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    task_id = "task-1"
    task = SimpleNamespace(is_running=False, name="Name", notes="Notes")
    app.service = SimpleNamespace(state=SimpleNamespace(tasks={task_id: task}))

    class _Widget:
        def __init__(self) -> None:
            self.config: dict[str, object] = {}

        def configure(self, **kwargs: object) -> None:
            self.config.update(kwargs)

    app.rows = {
        task_id: {
            "state_label": _Widget(),
            "elapsed_label": _Widget(),
            "toggle_btn": _Widget(),
            "container": _Widget(),
            "name_var": SimpleNamespace(get=lambda: "Name", set=lambda x: None),
            "notes_var": SimpleNamespace(get=lambda: "Notes", set=lambda x: None),
            "name_dirty": False,
            "notes_dirty": False,
            "name_entry": object(),
            "notes_entry": object(),
        }
    }
    app.root = SimpleNamespace(focus_get=lambda: None)

    TaskTimerApp.refresh_row(app, task_id)
    assert app.rows[task_id]["toggle_btn"].config["text"] == "Start"
    assert app.rows[task_id]["state_label"].config["bg"] == STOPPED_COLOR

    task.is_running = True
    TaskTimerApp.refresh_row(app, task_id)
    assert app.rows[task_id]["toggle_btn"].config["text"] == "Stop"


def test_open_mini_mode_minimizes_main_window() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    root = _FakeRoot()
    app.root = root
    app.service = object()
    app.mini_mode_window = None
    app._after_state_change = lambda: None

    class _Mini:
        def __init__(self) -> None:
            self.window = SimpleNamespace(winfo_exists=lambda: True, lift=lambda: None)

    import task_timer.app as app_module

    original = app_module.MiniModeWindow
    app_module.MiniModeWindow = lambda *args, **kwargs: _Mini()
    try:
        TaskTimerApp.open_mini_mode(app)
        assert root.iconified is True
    finally:
        app_module.MiniModeWindow = original


def test_mini_mode_resolves_running_then_recent_task(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    first = service.create_task("First", "")
    second = service.create_task("Second", "")
    service.update_task(second, "Second Updated", "")

    mini = MiniModeWindow.__new__(MiniModeWindow)
    mini.service = service
    assert mini._resolve_display_task_id() in {first, second}

    service.start_task(first)
    assert mini._resolve_display_task_id() == first


def test_display_order_uses_casefold_sort_with_stable_task_id_tiebreak(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_b = service.create_task("beta", "")
    task_a = service.create_task(" Alpha ", "")
    task_a2 = service.create_task("alpha", "")

    app = TaskTimerApp.__new__(TaskTimerApp)
    app.service = service
    app.sort_alpha_var = SimpleNamespace(get=lambda: True)

    ordered = TaskTimerApp._get_active_tasks_in_display_order(app)
    expected = sorted(
        [service.state.tasks[task_b], service.state.tasks[task_a], service.state.tasks[task_a2]],
        key=lambda task: (task.name.strip().casefold(), task.task_id),
    )
    assert [task.task_id for task in ordered] == [task.task_id for task in expected]


def test_commit_row_refreshes_structure_for_rename_sorting(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Beta", "")
    task: TaskState = service.state.tasks[task_id]
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.service = service
    app.mini_mode_window = None
    calls: list[str] = []
    app.refresh_structure = lambda: calls.append("structure")
    app.refresh_live_values = lambda: calls.append("live")
    app.rows = {
        task_id: {
            "name_var": SimpleNamespace(get=lambda: "Alpha", set=lambda _v: None),
            "notes_var": SimpleNamespace(get=lambda: task.notes),
            "name_dirty": True,
            "notes_dirty": False,
        }
    }

    TaskTimerApp._commit_row(app, task_id)

    assert calls == ["structure", "live"]
    assert service.state.tasks[task_id].name == "Alpha"


def test_mini_mode_close_routes_to_restore_main() -> None:
    calls: list[str] = []

    class _Window:
        def attributes(self, *_args) -> None:
            return None

        def protocol(self, _name: str, callback) -> None:
            self.callback = callback

    mini = MiniModeWindow.__new__(MiniModeWindow)
    mini.window = _Window()
    mini.restore_main = lambda: calls.append("restore")

    MiniModeWindow._configure_window_chrome(mini)
    mini.window.callback()

    assert calls == ["restore"]


def _local_dt(value: str):
    from datetime import datetime

    return datetime.strptime(value, "%Y-%m-%d %H:%M").astimezone()
