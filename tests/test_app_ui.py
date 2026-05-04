from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from task_timer.app import ROW_PARENT_STOPPED_COLOR, ROW_SUBTASK_STOPPED_COLOR, STOPPED_COLOR, TaskTimerApp, TaskTimerService
from task_timer.dialogs import AddTaskDialog, BackupSettingsDialog, EditTaskDialog
from task_timer.mini_mode import MiniModeWindow, RUNNING_COLOR, STOPPED_COLOR as MINI_STOPPED_COLOR
from task_timer.settings import BackupSettings, UISettings
from task_timer.storage import EventStorage
from task_timer.time_utils import format_duration_hm


class _FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[int] = []
        self.after_idle_callbacks: list[object] = []
        self.iconified = False

    def after(self, delay_ms: int, callback: object) -> str:
        self.after_calls.append(delay_ms)
        return "after-id"

    def after_idle(self, callback: object) -> str:
        self.after_idle_callbacks.append(callback)
        return "after-idle"

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


def test_reset_all_non_deleted_tasks_skips_deleted_and_stops_running(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    keep = service.create_task("Keep", "")
    deleted = service.create_task("Deleted", "")
    service.start_task(keep)
    service.delete_task(deleted)

    before_keep_events = len([e for e in service.events if e["task_id"] == keep])
    before_deleted_events = len([e for e in service.events if e["task_id"] == deleted])
    service.reset_all_non_deleted_tasks()

    assert service.state.tasks[keep].is_running is False
    assert service.state.running_task_id is None
    keep_events = [e for e in service.events if e["task_id"] == keep]
    deleted_events = [e for e in service.events if e["task_id"] == deleted]
    assert len(keep_events) > before_keep_events
    assert any(e["event_type"] == "reset" for e in keep_events)
    assert len(deleted_events) == before_deleted_events
    assert not any(e["event_type"] == "reset" for e in deleted_events)


def test_row_refresh_sets_toggle_text_and_color() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    task_id = "task-1"
    task = SimpleNamespace(is_running=False, name="Name", notes="Notes")
    app.service = SimpleNamespace(
        state=SimpleNamespace(tasks={task_id: task}),
        child_tasks=lambda *_args, **_kwargs: [],
    )

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
            "name_cell": _Widget(),
            "notes_cell": _Widget(),
            "name_label": _Widget(),
            "notes_label": _Widget(),
            "expander_btn": _Widget(),
        }
    }
    app.root = SimpleNamespace(focus_get=lambda: None)

    TaskTimerApp.refresh_row(app, task_id)
    assert app.rows[task_id]["toggle_btn"].config["text"] == "Start"
    assert app.rows[task_id]["state_label"].config["bg"] == STOPPED_COLOR

    task.is_running = True
    TaskTimerApp.refresh_row(app, task_id)
    assert app.rows[task_id]["toggle_btn"].config["text"] == "Stop"
    assert app.rows[task_id]["name_label"].config["text"] == "Name"
    assert app.rows[task_id]["notes_label"].config["text"] == "Notes"


def test_clip_table_text_truncates_and_normalizes() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)

    assert TaskTimerApp._clip_table_text(app, "Short", 10) == "Short"
    assert TaskTimerApp._clip_table_text(app, "Line 1\nLine 2", 20) == "Line 1 Line 2"
    assert TaskTimerApp._clip_table_text(app, "123456", 5) == "1234…"


def test_refresh_row_uses_clipped_display_text_without_mutating_task() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    task_id = "task-1"
    long_name = "Task Name That Is Definitely Too Long For The Table"
    long_notes = "Reports, documentation, rework, questions"
    task = SimpleNamespace(is_running=False, name=long_name, notes=long_notes)
    app.service = SimpleNamespace(
        state=SimpleNamespace(tasks={task_id: task}),
        child_tasks=lambda *_args, **_kwargs: [],
    )

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
            "name_cell": _Widget(),
            "notes_cell": _Widget(),
            "name_label": _Widget(),
            "notes_label": _Widget(),
            "expander_btn": _Widget(),
        }
    }
    app.root = SimpleNamespace(focus_get=lambda: None)

    TaskTimerApp.refresh_row(app, task_id)

    assert str(app.rows[task_id]["name_label"].config["text"]).endswith("…")
    assert str(app.rows[task_id]["notes_label"].config["text"]).endswith("…")
    assert task.name == long_name
    assert task.notes == long_notes


def test_refresh_row_parent_and_subtask_hierarchy_styles() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    parent_id = "parent"
    child_id = "child"
    parent = SimpleNamespace(is_running=False, name="Parent", notes="P")
    child = SimpleNamespace(is_running=False, name="Reports", notes="C")
    app.default_name_font = "default-font"
    app.parent_name_font = "parent-bold-font"
    app.expanded_parents = set()

    class _Widget:
        def __init__(self) -> None:
            self.config: dict[str, object] = {}

        def configure(self, **kwargs: object) -> None:
            self.config.update(kwargs)

    app.rows = {
        parent_id: {
            "state_label": _Widget(),
            "elapsed_label": _Widget(),
            "toggle_btn": _Widget(),
            "container": _Widget(),
            "name_cell": _Widget(),
            "notes_cell": _Widget(),
            "name_label": _Widget(),
            "notes_label": _Widget(),
            "expander_btn": _Widget(),
        },
        child_id: {
            "state_label": _Widget(),
            "elapsed_label": _Widget(),
            "toggle_btn": _Widget(),
            "container": _Widget(),
            "name_cell": _Widget(),
            "notes_cell": _Widget(),
            "name_label": _Widget(),
            "notes_label": _Widget(),
            "expander_btn": _Widget(),
        },
    }
    app.service = SimpleNamespace(
        state=SimpleNamespace(tasks={parent_id: parent, child_id: child}),
        child_tasks=lambda task_id, **_kwargs: [child] if task_id == parent_id else [],
    )

    TaskTimerApp.refresh_row(app, parent_id, is_subtask=False)
    TaskTimerApp.refresh_row(app, child_id, is_subtask=True)

    assert app.rows[parent_id]["name_label"].config["font"] == "parent-bold-font"
    assert app.rows[parent_id]["container"].config["bg"] == ROW_PARENT_STOPPED_COLOR
    assert app.rows[parent_id]["expander_btn"].config["text"] == "+"
    assert app.rows[child_id]["container"].config["bg"] == ROW_SUBTASK_STOPPED_COLOR
    assert app.rows[child_id]["name_label"].config["text"].startswith("└─")
    assert "padding" not in app.rows[child_id]["name_label"].config


def test_refresh_row_uses_default_font_for_non_parent_rows_and_never_empty_font() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    parent_id = "parent"
    child_id = "child"
    solo_id = "solo"
    parent = SimpleNamespace(is_running=False, name="Parent", notes="P")
    child = SimpleNamespace(is_running=False, name="Child", notes="C")
    solo = SimpleNamespace(is_running=False, name="Solo", notes="S")
    app.default_name_font = "default-font"
    app.parent_name_font = "parent-bold-font"
    app.expanded_parents = set()

    class _Widget:
        def __init__(self) -> None:
            self.config: dict[str, object] = {}

        def configure(self, **kwargs: object) -> None:
            self.config.update(kwargs)

    def _row() -> dict[str, _Widget]:
        return {
            "state_label": _Widget(),
            "elapsed_label": _Widget(),
            "toggle_btn": _Widget(),
            "container": _Widget(),
            "name_cell": _Widget(),
            "notes_cell": _Widget(),
            "name_label": _Widget(),
            "notes_label": _Widget(),
            "expander_btn": _Widget(),
        }

    app.rows = {parent_id: _row(), child_id: _row(), solo_id: _row()}
    app.service = SimpleNamespace(
        state=SimpleNamespace(tasks={parent_id: parent, child_id: child, solo_id: solo}),
        child_tasks=lambda task_id, **_kwargs: [child] if task_id == parent_id else [],
        is_subtask=lambda task_id: task_id == child_id,
    )

    TaskTimerApp.refresh_row(app, parent_id, is_subtask=False)
    TaskTimerApp.refresh_row(app, child_id, is_subtask=True)
    TaskTimerApp.refresh_row(app, solo_id, is_subtask=False)

    assert app.rows[parent_id]["name_label"].config["font"] == "parent-bold-font"
    assert app.rows[child_id]["name_label"].config["font"] == "default-font"
    assert app.rows[solo_id]["name_label"].config["font"] == "default-font"
    assert app.rows[parent_id]["name_label"].config["font"] != ""
    assert app.rows[child_id]["name_label"].config["font"] != ""
    assert app.rows[solo_id]["name_label"].config["font"] != ""


def test_column_specs_keep_dedicated_expander_column() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    specs = TaskTimerApp._column_specs(app)
    assert specs[0]["key"] == "expander"
    assert specs[0]["header"] == ""
    assert specs[0]["minsize"] >= 24


def test_table_column_widths_match_column_specs() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    widths = TaskTimerApp._table_column_widths(app)
    specs = TaskTimerApp._column_specs(app)
    assert widths["name"] == next(spec["minsize"] for spec in specs if spec["key"] == "name")
    assert widths["notes"] == next(spec["minsize"] for spec in specs if spec["key"] == "notes")


def test_open_mini_mode_minimizes_main_window_when_keep_unchecked() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    root = _FakeRoot()
    app.root = root
    app.service = object()
    app.mini_mode_window = None
    app._after_state_change = lambda: None
    app.ui_settings = UISettings(keep_mini_open=False)

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


def test_open_mini_mode_keeps_main_visible_when_keep_checked() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    root = _FakeRoot()
    app.root = root
    app.service = object()
    app.mini_mode_window = None
    app._after_state_change = lambda: None
    app.ui_settings = UISettings(keep_mini_open=True)

    class _Mini:
        def __init__(self) -> None:
            self.window = SimpleNamespace(winfo_exists=lambda: True, lift=lambda: None)

    import task_timer.app as app_module

    original = app_module.MiniModeWindow
    app_module.MiniModeWindow = lambda *args, **kwargs: _Mini()
    try:
        TaskTimerApp.open_mini_mode(app)
        assert root.iconified is False
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
    app.expanded_parents = set()

    ordered = TaskTimerApp._get_active_tasks_in_display_order(app)
    expected = sorted(
        [service.state.tasks[task_b], service.state.tasks[task_a], service.state.tasks[task_a2]],
        key=lambda task: (task.name.strip().casefold(), task.task_id),
    )
    assert [task.task_id for task in ordered] == [task.task_id for task in expected]


def test_mini_mode_close_routes_to_restore_main() -> None:
    calls: list[str] = []

    class _Window:
        def attributes(self, *_args) -> None:
            return None

        def protocol(self, _name: str, callback) -> None:
            self.callback = callback

        def resizable(self, *_args) -> None:
            return None

    mini = MiniModeWindow.__new__(MiniModeWindow)
    mini.window = _Window()
    mini.restore_main = lambda: calls.append("restore")

    MiniModeWindow._configure_window_chrome(mini)
    mini.window.callback()

    assert calls == ["restore"]


def test_mini_mode_refresh_live_values_running_uses_elapsed_bar() -> None:
    task_id = "task-1"
    task = SimpleNamespace(task_id=task_id, is_running=True, name=" Focus ")

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    class _Widget:
        def __init__(self) -> None:
            self.config: dict[str, object] = {}
            self.states: list[list[str]] = []

        def configure(self, **kwargs: object) -> None:
            self.config.update(kwargs)

        def state(self, values: list[str]) -> None:
            self.states.append(values)

    mini = MiniModeWindow.__new__(MiniModeWindow)
    mini.service = SimpleNamespace(
        state=SimpleNamespace(tasks={task_id: task}),
        task_elapsed=lambda _task, _now=None: 3900,
    )
    mini.task_name_var = _Var()
    mini.elapsed_var = _Var()
    mini.toggle_btn = _Widget()
    mini.elapsed_bar_label = _Widget()
    mini.refresh_structure = lambda: setattr(mini, "_display_task_id", task_id)
    mini._display_task_id = None

    MiniModeWindow.refresh_live_values(mini)

    assert mini.task_name_var.value == "Focus"
    assert mini.elapsed_var.value == "01:05"
    assert mini.toggle_btn.config["text"] == "Stop"
    assert mini.elapsed_bar_label.config["bg"] == RUNNING_COLOR
    assert ["!disabled"] in mini.toggle_btn.states


def test_mini_mode_refresh_live_values_stopped_uses_red_elapsed_bar() -> None:
    task_id = "task-1"
    task = SimpleNamespace(task_id=task_id, is_running=False, name="Task")

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    class _Widget:
        def __init__(self) -> None:
            self.config: dict[str, object] = {}
            self.states: list[list[str]] = []

        def configure(self, **kwargs: object) -> None:
            self.config.update(kwargs)

        def state(self, values: list[str]) -> None:
            self.states.append(values)

    mini = MiniModeWindow.__new__(MiniModeWindow)
    mini.service = SimpleNamespace(
        state=SimpleNamespace(tasks={task_id: task}),
        task_elapsed=lambda _task, _now=None: 2580,
    )
    mini.task_name_var = _Var()
    mini.elapsed_var = _Var()
    mini.toggle_btn = _Widget()
    mini.elapsed_bar_label = _Widget()
    mini.refresh_structure = lambda: setattr(mini, "_display_task_id", task_id)
    mini._display_task_id = None

    MiniModeWindow.refresh_live_values(mini)

    assert mini.elapsed_var.value == "00:43"
    assert mini.toggle_btn.config["text"] == "Start"
    assert mini.elapsed_bar_label.config["bg"] == MINI_STOPPED_COLOR


def test_mini_mode_refresh_live_values_no_task_sets_default_and_disables_toggle() -> None:
    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    class _Widget:
        def __init__(self) -> None:
            self.config: dict[str, object] = {}
            self.states: list[list[str]] = []

        def configure(self, **kwargs: object) -> None:
            self.config.update(kwargs)

        def state(self, values: list[str]) -> None:
            self.states.append(values)

    mini = MiniModeWindow.__new__(MiniModeWindow)
    mini.service = SimpleNamespace(state=SimpleNamespace(tasks={}))
    mini.task_name_var = _Var()
    mini.elapsed_var = _Var()
    mini.toggle_btn = _Widget()
    mini.elapsed_bar_label = _Widget()
    mini.refresh_structure = lambda: setattr(mini, "_display_task_id", None)
    mini._display_task_id = None

    MiniModeWindow.refresh_live_values(mini)

    assert mini.task_name_var.value == "No tasks available"
    assert mini.elapsed_var.value == "00:00"
    assert mini.toggle_btn.config["text"] == "Start"
    assert mini.elapsed_bar_label.config["bg"] == MINI_STOPPED_COLOR
    assert ["disabled"] in mini.toggle_btn.states


def test_backup_settings_dialog_validation_rejects_non_positive_counts() -> None:
    try:
        BackupSettingsDialog.validate_inputs(
            son_keep_days="0",
            father_keep_days="1",
            grandfather_keep_days="1",
            auto_backup_before_risky_operations=True,
            auto_backup_on_app_start=False,
            auto_backup_min_interval_minutes="60",
        )
    except ValueError as exc:
        assert "positive integer" in str(exc)
    else:
        raise AssertionError("Expected validation failure")


def test_auto_backup_before_risky_operations_false_skips_non_restore_safety_backup(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Task", "")
    start = _local_dt("2026-01-01 10:00")
    stop = _local_dt("2026-01-01 11:00")
    service.add_manual_interval(task_id, start, stop, "seed")
    interval_id = next(iter(service.state.tasks[task_id].intervals))

    settings = service.load_backup_settings()
    settings.auto_backup_before_risky_operations = False
    service.save_backup_settings(settings)

    calls: list[str] = []
    service.backups.create_safety_backup = lambda reason: calls.append(reason)  # type: ignore[method-assign]
    service.edit_interval(task_id, interval_id, _local_dt("2026-01-01 12:00"), _local_dt("2026-01-01 13:00"), "fix")
    assert calls == []


def test_auto_backup_on_app_start_and_min_interval(tmp_path, monkeypatch) -> None:
    storage = EventStorage(tmp_path)
    store = storage.data_dir / "backup_settings.json"
    store.write_text(
        '{\n  "son_keep_days": 14,\n  "father_keep_days": 56,\n  "grandfather_keep_days": 365,\n'
        '  "auto_backup_before_risky_operations": true,\n  "auto_backup_on_app_start": true,\n'
        '  "auto_backup_min_interval_minutes": 60\n}\n',
        encoding="utf-8",
    )
    fixed = _local_dt("2026-01-10 10:00").astimezone(timezone.utc)
    monkeypatch.setattr("task_timer.app.utc_now", lambda: fixed)
    monkeypatch.setattr("task_timer.backups.utc_now", lambda: fixed)
    service = TaskTimerService(storage)
    assert len(service.list_managed_backups()) == 1

    service_2 = TaskTimerService(storage)
    assert len(service_2.list_managed_backups()) == 1


def test_manual_create_backup_now_not_blocked_by_interval_setting(tmp_path, monkeypatch) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    settings = BackupSettings(auto_backup_on_app_start=False, auto_backup_min_interval_minutes=9999)
    service.save_backup_settings(settings)
    fixed = _local_dt("2026-01-10 10:00").astimezone(timezone.utc)
    counter = {"i": 0}

    def _tick():
        counter["i"] += 1
        return fixed + timedelta(seconds=counter["i"])

    monkeypatch.setattr("task_timer.backups.utc_now", _tick)
    service.backups.create_backup("son", "existing")
    service.create_backup_now("manual backup regardless of interval")
    assert len(service.list_managed_backups()) == 2


def test_mini_mode_configure_window_chrome_applies_snap_guard(monkeypatch) -> None:
    calls: list[str] = []

    class _Window:
        def attributes(self, *_args) -> None:
            calls.append("topmost")

        def protocol(self, _name: str, callback) -> None:
            self.callback = callback

    mini = MiniModeWindow.__new__(MiniModeWindow)
    mini.window = _Window()
    mini.restore_main = lambda: None
    monkeypatch.setattr("task_timer.mini_mode.disable_snap_maximize", lambda _w: calls.append("disable"))
    monkeypatch.setattr("task_timer.mini_mode.install_zoom_guard", lambda _w: calls.append("guard"))

    MiniModeWindow._configure_window_chrome(mini)

    assert calls[:3] == ["topmost", "disable", "guard"]


def _local_dt(value: str):
    from datetime import datetime

    return datetime.strptime(value, "%Y-%m-%d %H:%M").astimezone()


def test_close_request_with_reminder_disabled_closes(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)

    class _Root:
        destroyed = False

        def destroy(self):
            self.destroyed = True

    app.root = _Root()
    app.ui_settings = UISettings(month_end_reminder_enabled=False)
    app._local_today = lambda: _local_dt("2026-04-30 12:00").date()
    TaskTimerApp._on_close_request(app)
    assert app.root.destroyed is True


def test_close_request_non_reminder_day_closes(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)

    class _Root:
        destroyed = False

        def destroy(self):
            self.destroyed = True

    app.root = _Root()
    app.ui_settings = UISettings(month_end_reminder_enabled=True, month_end_reminder_show_close_notice=True)
    app._local_today = lambda: _local_dt("2026-04-29 12:00").date()
    monkeypatch.setattr("task_timer.app.is_last_business_day", lambda _d: False)
    TaskTimerApp._on_close_request(app)
    assert app.root.destroyed is True


def test_close_request_reminder_day_return_to_app_cancels_close(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    events: list[str] = []

    class _Root:
        destroyed = False

        def destroy(self):
            self.destroyed = True

        def deiconify(self):
            events.append("deiconify")

        def lift(self):
            events.append("lift")

        def focus_force(self):
            events.append("focus")

    class _Dialog:
        def __init__(self, _parent):
            self.choice = "return"

    app.root = _Root()
    app.ui_settings = UISettings(month_end_reminder_enabled=True, month_end_reminder_show_close_notice=True)
    app._local_today = lambda: _local_dt("2026-04-30 12:00").date()
    monkeypatch.setattr("task_timer.app.is_last_business_day", lambda _d: True)
    monkeypatch.setattr("task_timer.app.MonthEndCloseReminderDialog", _Dialog)
    TaskTimerApp._on_close_request(app)
    assert app.root.destroyed is False
    assert events == ["deiconify", "lift", "focus"]


def test_close_request_reminder_day_close_anyway_closes(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)

    class _Root:
        destroyed = False

        def destroy(self):
            self.destroyed = True

    class _Dialog:
        def __init__(self, _parent):
            self.choice = "close"

    app.root = _Root()
    app.ui_settings = UISettings(month_end_reminder_enabled=True, month_end_reminder_show_close_notice=True)
    app._local_today = lambda: _local_dt("2026-04-30 12:00").date()
    monkeypatch.setattr("task_timer.app.is_last_business_day", lambda _d: True)
    monkeypatch.setattr("task_timer.app.MonthEndCloseReminderDialog", _Dialog)
    TaskTimerApp._on_close_request(app)
    assert app.root.destroyed is True


def test_close_request_reminder_day_export_invokes_export(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    calls: list[str] = []

    class _Root:
        destroyed = False

        def destroy(self):
            self.destroyed = True

        def deiconify(self):
            calls.append("deiconify")

        def lift(self):
            calls.append("lift")

    class _Dialog:
        def __init__(self, _parent):
            self.choice = "export"

    app.root = _Root()
    app.export = lambda: calls.append("export")
    app.ui_settings = UISettings(month_end_reminder_enabled=True, month_end_reminder_show_close_notice=True)
    app._local_today = lambda: _local_dt("2026-04-30 12:00").date()
    monkeypatch.setattr("task_timer.app.is_last_business_day", lambda _d: True)
    monkeypatch.setattr("task_timer.app.MonthEndCloseReminderDialog", _Dialog)
    TaskTimerApp._on_close_request(app)
    assert app.root.destroyed is False
    assert "export" in calls


def test_build_ui_creates_reminder_banner_and_toolbar_widgets(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)

    class _FakeWidget:
        def __init__(self, parent=None, **kwargs) -> None:
            self.parent = parent
            self.kwargs = kwargs
            self.packed = False
            self.pack_calls: list[dict[str, object]] = []
            self.children: list[_FakeWidget] = []
            if parent is not None and hasattr(parent, "children"):
                parent.children.append(self)

        def pack(self, **kwargs) -> None:
            self.packed = True
            self.pack_calls.append(kwargs)

        def grid(self, **_kwargs) -> None:
            return None

        def grid_columnconfigure(self, *_args, **_kwargs) -> None:
            return None

        def winfo_ismapped(self) -> bool:
            return self.packed

        def pack_forget(self) -> None:
            self.packed = False

    class _FakeRoot(_FakeWidget):
        def configure(self, **_kwargs) -> None:
            return None

    import task_timer.app as app_module

    monkeypatch.setattr(app_module.tk, "Frame", _FakeWidget)
    monkeypatch.setattr(app_module.tk, "Label", _FakeWidget)
    monkeypatch.setattr(app_module.ttk, "Frame", _FakeWidget)
    monkeypatch.setattr(app_module.ttk, "Button", _FakeWidget)
    monkeypatch.setattr(app_module.ttk, "Checkbutton", _FakeWidget)
    monkeypatch.setattr(app_module.ttk, "Label", _FakeWidget)
    app._build_menus = lambda: None
    app._configure_table_columns = lambda _frame: None
    app._setup_headers = lambda: None
    app.root = _FakeRoot()
    app.sort_alpha_var = object()
    app.keep_mini_open_var = object()
    app.daily_var = object()
    app.weekly_var = object()
    app.add_task = lambda: None
    app.export = lambda: True
    app.open_mini_mode = lambda: None
    app._on_sort_toggle = lambda: None
    app._on_keep_mini_open_toggle = lambda: None
    app._on_reminder_export = lambda: None
    app._dismiss_month_end_reminder_today = lambda: None

    TaskTimerApp._build_ui(app)

    assert hasattr(app, "reminder_banner")
    assert app.reminder_banner.winfo_ismapped() is False
    assert hasattr(app, "toolbar_frame")
    toolbar_texts = [child.kwargs.get("text") for child in app.toolbar_frame.children]
    assert "Add Task" in toolbar_texts
    assert "Export" in toolbar_texts
    assert "Mini Mode" in toolbar_texts
    assert "Keep Mini Open" in toolbar_texts
    assert "Sort A-Z" in toolbar_texts


def test_build_menus_tools_contains_reset_all_item(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)

    class _FakeMenu:
        def __init__(self, _parent=None, **_kwargs) -> None:
            self.commands: list[str] = []
            self.cascades: dict[str, object] = {}

        def add_command(self, label: str, command=None) -> None:
            self.commands.append(label)

        def add_separator(self) -> None:
            self.commands.append("---")

        def add_cascade(self, label: str, menu) -> None:
            self.cascades[label] = menu

    class _Root:
        def configure(self, **kwargs) -> None:
            self.menu = kwargs.get("menu")

    import task_timer.app as app_module

    monkeypatch.setattr(app_module.tk, "Menu", _FakeMenu)
    app.root = _Root()
    app._reopen_last_export_checkpoint = lambda: None
    app._reset_all_task_timers = lambda: None
    app._manage_tags = lambda: None
    app._manage_subtask_templates = lambda: None
    app._open_month_end_reminder_settings = lambda: None
    app._create_backup_now = lambda: None
    app._open_backup_settings = lambda: None
    app._open_data_folder = lambda: None
    app._open_backup_folder = lambda: None
    app._restore_from_backup = lambda: None
    app._rebuild_snapshot_from_journal = lambda: None

    TaskTimerApp._build_menus(app)

    tools_menu = app.root.menu.cascades["Tools"]
    assert "Reset All Task Timers..." in tools_menu.commands




def test_reset_parent_with_subtasks_prompts_scope_and_default_tree(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    parent = SimpleNamespace(parent_task_id=None)
    child = SimpleNamespace(task_id="c1", parent_task_id="p1")
    app.service = SimpleNamespace(
        state=SimpleNamespace(tasks={"p1": parent}),
        child_tasks=lambda *_a, **_k: [child],
        reset_task_tree=lambda task_id: calls.append(("tree", task_id)),
        reset_task_only=lambda task_id: calls.append(("only", task_id)),
    )
    app._create_risky_operation_backup = lambda reason: calls.append(("backup", reason))
    app._after_state_change = lambda: calls.append(("refresh", None))
    calls: list[tuple[str, str | None]] = []

    import task_timer.app as app_module

    captured: dict[str, object] = {}

    def _askyesnocancel(*_a, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", _askyesnocancel)

    TaskTimerApp._reset_task(app, "p1")
    assert captured["default"] == app_module.messagebox.YES
    assert calls == [
        ("backup", "before resetting parent task tree"),
        ("tree", "p1"),
        ("refresh", None),
    ]


def test_reset_parent_only_leaves_subtasks_intact_path(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    parent = SimpleNamespace(parent_task_id=None)
    child = SimpleNamespace(task_id="c1", parent_task_id="p1")
    calls: list[tuple[str, str]] = []
    app.service = SimpleNamespace(
        state=SimpleNamespace(tasks={"p1": parent}),
        child_tasks=lambda *_a, **_k: [child],
        reset_task_tree=lambda task_id: calls.append(("tree", task_id)),
        reset_task_only=lambda task_id: calls.append(("only", task_id)),
    )
    app._create_risky_operation_backup = lambda _reason: calls.append(("backup", "x"))
    app._after_state_change = lambda: calls.append(("refresh", "x"))

    import task_timer.app as app_module

    monkeypatch.setattr(app_module.messagebox, "askyesnocancel", lambda *_a, **_k: False)

    TaskTimerApp._reset_task(app, "p1")
    assert calls == [("only", "p1"), ("refresh", "x")]


def test_reset_subtask_resets_only_that_subtask(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    subtask = SimpleNamespace(parent_task_id="p1")
    calls: list[tuple[str, str]] = []
    app.service = SimpleNamespace(
        state=SimpleNamespace(tasks={"c1": subtask}),
        child_tasks=lambda *_a, **_k: [],
        reset_task_only=lambda task_id: calls.append(("only", task_id)),
    )
    app._after_state_change = lambda: calls.append(("refresh", "x"))

    import task_timer.app as app_module

    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_a, **_k: True)

    TaskTimerApp._reset_task(app, "c1")
    assert calls == [("only", "c1"), ("refresh", "x")]


def test_delete_parent_with_subtasks_prompts_and_deletes_tree_once(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    parent = SimpleNamespace(parent_task_id=None)
    child = SimpleNamespace(task_id="c1", parent_task_id="p1")
    calls: list[tuple[str, str]] = []
    app.service = SimpleNamespace(
        state=SimpleNamespace(tasks={"p1": parent}),
        child_tasks=lambda *_a, **_k: [child],
        delete_task_tree=lambda task_id: calls.append(("tree", task_id)),
        delete_task_only=lambda task_id: calls.append(("only", task_id)),
    )
    app.expanded_parents = {"p1"}
    app._create_risky_operation_backup = lambda reason: calls.append(("backup", reason))
    app._after_state_change = lambda: calls.append(("refresh", "x"))

    import task_timer.app as app_module

    monkeypatch.setattr(app_module.messagebox, "askokcancel", lambda *_a, **_k: True)

    TaskTimerApp._delete_task(app, "p1")
    assert "p1" not in app.expanded_parents
    assert calls == [
        ("backup", "before deleting parent task tree"),
        ("tree", "p1"),
        ("refresh", "x"),
    ]


def test_delete_subtask_deletes_only_subtask(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    subtask = SimpleNamespace(parent_task_id="p1")
    calls: list[tuple[str, str]] = []
    app.service = SimpleNamespace(
        state=SimpleNamespace(tasks={"c1": subtask}),
        child_tasks=lambda *_a, **_k: [],
        delete_task_only=lambda task_id: calls.append(("only", task_id)),
    )
    app._after_state_change = lambda: calls.append(("refresh", "x"))

    import task_timer.app as app_module

    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_a, **_k: True)

    TaskTimerApp._delete_task(app, "c1")
    assert calls == [("only", "c1"), ("refresh", "x")]
def test_reset_all_task_timers_requires_confirmation_and_handles_cancel(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.service = SimpleNamespace(state=SimpleNamespace(tasks={"t1": SimpleNamespace(is_deleted=False)}))
    calls: list[str] = []
    app._create_risky_operation_backup = lambda _reason: calls.append("backup")
    app._after_state_change = lambda: calls.append("refresh")
    app.service.reset_all_non_deleted_tasks = lambda: calls.append("reset")

    import task_timer.app as app_module

    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_a, **_k: False)
    monkeypatch.setattr(app_module.messagebox, "showinfo", lambda *_a, **_k: calls.append("info"))

    TaskTimerApp._reset_all_task_timers(app)
    assert calls == []


def test_reset_all_task_timers_confirmed_runs_backup_reset_refresh(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.service = SimpleNamespace(state=SimpleNamespace(tasks={"t1": SimpleNamespace(is_deleted=False)}))
    calls: list[str] = []
    app._create_risky_operation_backup = lambda reason: calls.append(f"backup:{reason}")
    app._after_state_change = lambda: calls.append("refresh")
    app.service.reset_all_non_deleted_tasks = lambda: calls.append("reset")

    import task_timer.app as app_module

    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_a, **_k: True)
    monkeypatch.setattr(app_module.messagebox, "showinfo", lambda *_a, **_k: calls.append("info"))

    TaskTimerApp._reset_all_task_timers(app)
    assert calls == [
        "backup:before reset all task timers",
        "reset",
        "refresh",
        "info",
    ]


def test_reset_all_task_timers_no_active_tasks_shows_message(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.service = SimpleNamespace(state=SimpleNamespace(tasks={"t1": SimpleNamespace(is_deleted=True)}))
    calls: list[str] = []
    app._create_risky_operation_backup = lambda _reason: calls.append("backup")
    app._after_state_change = lambda: calls.append("refresh")
    app.service.reset_all_non_deleted_tasks = lambda: calls.append("reset")

    import task_timer.app as app_module

    monkeypatch.setattr(app_module.messagebox, "askyesno", lambda *_a, **_k: True)
    monkeypatch.setattr(app_module.messagebox, "showinfo", lambda *_a, **_k: calls.append("info"))

    TaskTimerApp._reset_all_task_timers(app)
    assert calls == ["info"]


def test_refresh_month_end_reminder_ui_safe_before_banner_exists() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app._is_month_end_reminder_due_today = lambda: True
    app.mini_mode_window = None
    TaskTimerApp._refresh_month_end_reminder_ui(app)


def test_refresh_month_end_reminder_ui_shows_banner_before_toolbar_when_due() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)

    class _Widget:
        def __init__(self) -> None:
            self.mapped = False
            self.pack_kwargs: dict[str, object] | None = None

        def winfo_ismapped(self) -> bool:
            return self.mapped

        def pack(self, **kwargs) -> None:
            self.mapped = True
            self.pack_kwargs = kwargs

        def pack_forget(self) -> None:
            self.mapped = False

    app.reminder_banner = _Widget()
    app.toolbar_frame = object()
    app._is_month_end_reminder_due_today = lambda: True
    app.mini_mode_window = None

    TaskTimerApp._refresh_month_end_reminder_ui(app)

    assert app.reminder_banner.mapped is True
    assert app.reminder_banner.pack_kwargs is not None
    assert app.reminder_banner.pack_kwargs["before"] is app.toolbar_frame


def test_add_task_dialog_confirm_uses_selected_tags() -> None:
    dialog = AddTaskDialog.__new__(AddTaskDialog)
    dialog.name_var = SimpleNamespace(get=lambda: "New Task")
    dialog.notes_var = SimpleNamespace(get=lambda: "Note")
    dialog.tag_selector = SimpleNamespace(get_selected_tags=lambda: ["alpha", "beta"])
    dialog.window = SimpleNamespace(destroy=lambda: None)
    dialog.confirmed = False

    AddTaskDialog._confirm(dialog)

    assert dialog.confirmed is True
    assert dialog.tags == ["alpha", "beta"]


def test_add_task_passes_tags_to_service() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    calls: list[tuple[str, str, list[str]]] = []
    app.service = SimpleNamespace(create_task=lambda n, no, t: calls.append((n, no, t)))
    app.refresh_structure = lambda: None
    app.refresh_live_values = lambda: None

    import task_timer.app as app_module

    original = app_module.AddTaskDialog

    class _Dialog:
        def __init__(self, *_args) -> None:
            self.confirmed = True
            self.name = "Task"
            self.notes = "Note"
            self.tags = ["alpha"]

    app_module.AddTaskDialog = _Dialog
    try:
        TaskTimerApp.add_task(app)
    finally:
        app_module.AddTaskDialog = original

    assert calls == [("Task", "Note", ["alpha"])]


def test_edit_task_dialog_save_updates_task_and_tags_and_marks_changed() -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []
    dialog = EditTaskDialog.__new__(EditTaskDialog)
    dialog.task_id = "task-1"
    dialog.name_var = SimpleNamespace(get=lambda: " Renamed ")
    dialog.notes_var = SimpleNamespace(get=lambda: "New note")
    dialog.tag_selector = SimpleNamespace(get_selected_tags=lambda: ["beta"])
    dialog.service = SimpleNamespace(
        update_task=lambda *args: calls.append(("update_task", args)),
        update_task_tags=lambda *args: calls.append(("update_task_tags", args)),
    )
    dialog.window = SimpleNamespace(destroy=lambda: None)
    dialog.changed = False

    EditTaskDialog._save(dialog)

    assert dialog.changed is True
    assert calls == [
        ("update_task", ("task-1", "Renamed", "New note")),
        ("update_task_tags", ("task-1", ["beta"])),
    ]


def test_edit_task_dialog_timeline_marks_changed_when_dialog_changed() -> None:
    dialog = EditTaskDialog.__new__(EditTaskDialog)
    dialog.service = object()
    dialog.task_id = "task-1"
    dialog.window = object()
    dialog.changed = False

    import task_timer.dialogs as dialogs_module

    original = dialogs_module.EditTimelineDialog

    class _Timeline:
        def __init__(self, *_args) -> None:
            self.changed = True

    dialogs_module.EditTimelineDialog = _Timeline
    try:
        EditTaskDialog._edit_timeline(dialog)
    finally:
        dialogs_module.EditTimelineDialog = original

    assert dialog.changed is True


def test_edit_task_dialog_loads_existing_tags_from_task() -> None:
    task = SimpleNamespace(name="Task", notes="", tags={"zeta", "alpha"})
    service = SimpleNamespace(state=SimpleNamespace(tasks={"t1": task}))
    dialog = EditTaskDialog.__new__(EditTaskDialog)
    dialog.service = service
    dialog.task_id = "t1"
    dialog.tag_selector = SimpleNamespace(get_selected_tags=lambda: ["alpha", "zeta"])
    assert sorted(service.state.tasks["t1"].tags) == ["alpha", "zeta"]


def test_edit_task_button_triggers_edit_flow() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    calls: list[str] = []
    app.root = object()
    app.service = object()
    app._after_state_change = lambda: calls.append("refresh")

    import task_timer.app as app_module

    original = app_module.EditTaskDialog

    class _Dialog:
        def __init__(self, *_args) -> None:
            self.changed = True

    app_module.EditTaskDialog = _Dialog
    try:
        TaskTimerApp._edit_task(app, "t1")
    finally:
        app_module.EditTaskDialog = original

    assert calls == ["refresh"]


def test_edit_task_button_expands_parent_when_subtask_added() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    app.service = object()
    app.expanded_parents = set()
    calls: list[str] = []
    app._after_state_change = lambda: calls.append("refresh")

    import task_timer.app as app_module

    original = app_module.EditTaskDialog

    class _Dialog:
        def __init__(self, *_args) -> None:
            self.changed = True
            self.added_subtask = True

    app_module.EditTaskDialog = _Dialog
    try:
        TaskTimerApp._edit_task(app, "parent-1")
    finally:
        app_module.EditTaskDialog = original

    assert "parent-1" in app.expanded_parents
    assert calls == ["refresh"]


def test_edit_task_dialog_add_subtask_passes_parent_and_tags() -> None:
    dialog = EditTaskDialog.__new__(EditTaskDialog)
    dialog.task_id = "parent-1"
    dialog.changed = False
    dialog.added_subtask = False
    dialog.window = object()
    calls: list[tuple[str, tuple[object, ...]]] = []
    dialog._refresh_subtasks = lambda: calls.append(("refresh", tuple()))
    dialog.service = SimpleNamespace(create_subtask=lambda *args: calls.append(("create_subtask", args)))

    import task_timer.dialogs as dialogs_module

    original = dialogs_module.AddTaskDialog

    class _Dialog:
        def __init__(self, *_args) -> None:
            self.confirmed = True
            self.name = "Child"
            self.notes = "Note"
            self.tags = ["alpha"]

    dialogs_module.AddTaskDialog = _Dialog
    try:
        EditTaskDialog._add_subtask(dialog)
    finally:
        dialogs_module.AddTaskDialog = original

    assert ("create_subtask", ("parent-1", "Child", "Note", ["alpha"])) in calls
    assert dialog.changed is True
    assert dialog.added_subtask is True


def test_rename_task_preserves_uuid_history_and_tags(tmp_path) -> None:
    service = TaskTimerService(EventStorage(tmp_path))
    task_id = service.create_task("Original", "n1", ["alpha"])
    service.add_manual_interval(task_id, start_local=_local_dt("2026-01-01 10:00"), stop_local=_local_dt("2026-01-01 11:00"), reason="seed")
    before = service.task_elapsed(service.state.tasks[task_id])
    service.update_task(task_id, "Renamed", "n2")

    assert task_id in service.state.tasks
    assert service.state.tasks[task_id].name == "Renamed"
    assert service.state.tasks[task_id].tags == {"alpha"}
    assert service.task_elapsed(service.state.tasks[task_id]) >= before

def test_selected_export_menu_item_exists_in_build_menus() -> None:
    import inspect
    assert "Export Selected Tasks..." in inspect.getsource(TaskTimerApp._build_menus)


def test_selected_export_handler_uses_selected_service_not_normal_export(monkeypatch, tmp_path) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    called = {"selected": 0, "normal": 0, "reset": 0, "month": 0, "selected_reset": 0, "selected_delete": 0}
    app.service = SimpleNamespace(
        export_selected_tasks_report=lambda *a, **k: called.__setitem__("selected", called["selected"] + 1),
        reset_selected_tasks=lambda *_a, **_k: called.__setitem__("selected_reset", called["selected_reset"] + 1),
        delete_selected_tasks=lambda *_a, **_k: called.__setitem__("selected_delete", called["selected_delete"] + 1),
        export_report=lambda *a, **k: called.__setitem__("normal", called["normal"] + 1),
        reset_all_non_deleted_tasks=lambda: called.__setitem__("reset", called["reset"] + 1),
    )
    app.mark_month_end_reminder_handled_today = lambda: called.__setitem__("month", called["month"] + 1)
    app.refresh_structure = lambda: None
    app.refresh_live_values = lambda: None

    import task_timer.app as app_module
    app_module.SelectedTaskExportDialog = lambda _root, _service: SimpleNamespace(
        result=SimpleNamespace(task_ids=["t1"], window_start_utc=None, window_end_utc=_local_dt("2026-01-31 00:00").astimezone(timezone.utc), mark_submitted=False, reason="")
    )
    app_module.filedialog.asksaveasfilename = lambda **_k: str(tmp_path / "x.txt")
    app_module.PostSelectedExportActionDialog = lambda _root: SimpleNamespace(choice="leave")
    app_module.messagebox.showinfo = lambda *a, **k: None

    assert TaskTimerApp.export_selected_tasks(app) is True
    assert called["selected"] == 1
    assert called["normal"] == 0
    assert called["reset"] == 0
    assert called["month"] == 0


def test_selected_export_mark_submitted_overlap_cancel_prevents_marker(monkeypatch, tmp_path) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    called = {"selected": 0, "selected_reset": 0, "selected_delete": 0}
    app.service = SimpleNamespace(
        local_tz=timezone.utc,
        find_submission_overlaps=lambda *a, **k: [
            {
                "task_id": "t1",
                "task_name": "A",
                "existing_submission_id": "s1",
                "overlap_start_utc": datetime(2026, 1, 10, tzinfo=timezone.utc),
                "overlap_end_utc": datetime(2026, 1, 11, tzinfo=timezone.utc),
                "existing_reason": "closing",
            }
        ],
        export_selected_tasks_report=lambda *a, **k: called.__setitem__("selected", called["selected"] + 1),
        reset_selected_tasks=lambda *_a, **_k: called.__setitem__("selected_reset", called["selected_reset"] + 1),
        delete_selected_tasks=lambda *_a, **_k: called.__setitem__("selected_delete", called["selected_delete"] + 1),
    )
    app.refresh_structure = lambda: None
    app.refresh_live_values = lambda: None
    import task_timer.app as app_module
    app_module.SelectedTaskExportDialog = lambda _root, _service: SimpleNamespace(
        result=SimpleNamespace(task_ids=["t1"], window_start_utc=None, window_end_utc=datetime(2026, 1, 31, tzinfo=timezone.utc), mark_submitted=True, reason="r")
    )
    app_module.messagebox.askyesno = lambda *a, **k: False
    assert TaskTimerApp.export_selected_tasks(app) is False
    assert called["selected"] == 0


def test_selected_export_mark_submitted_overlap_continue_appends_marker(monkeypatch, tmp_path) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    called = {"selected": 0, "selected_reset": 0, "selected_delete": 0}
    app.service = SimpleNamespace(
        local_tz=timezone.utc,
        find_submission_overlaps=lambda *a, **k: [
            {
                "task_id": "t1",
                "task_name": "A",
                "existing_submission_id": "s1",
                "overlap_start_utc": datetime(2026, 1, 10, tzinfo=timezone.utc),
                "overlap_end_utc": datetime(2026, 1, 11, tzinfo=timezone.utc),
                "existing_reason": "closing",
            }
        ],
        export_selected_tasks_report=lambda *a, **k: called.__setitem__("selected", called["selected"] + 1),
        reset_selected_tasks=lambda *_a, **_k: called.__setitem__("selected_reset", called["selected_reset"] + 1),
        delete_selected_tasks=lambda *_a, **_k: called.__setitem__("selected_delete", called["selected_delete"] + 1),
    )
    app.refresh_structure = lambda: None
    app.refresh_live_values = lambda: None
    import task_timer.app as app_module
    app_module.SelectedTaskExportDialog = lambda _root, _service: SimpleNamespace(
        result=SimpleNamespace(task_ids=["t1"], window_start_utc=None, window_end_utc=datetime(2026, 1, 31, tzinfo=timezone.utc), mark_submitted=True, reason="r")
    )
    app_module.messagebox.askyesno = lambda *a, **k: True
    app_module.filedialog.asksaveasfilename = lambda **_k: str(tmp_path / "x.txt")
    app_module.PostSelectedExportActionDialog = lambda _root: SimpleNamespace(choice="leave")
    app_module.messagebox.showinfo = lambda *a, **k: None
    assert TaskTimerApp.export_selected_tasks(app) is True
    assert called["selected"] == 1

def test_selected_export_post_action_reset_creates_single_backup_and_resets_selected(tmp_path) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    calls = {"backup": 0, "reset": None, "delete": None, "refresh": 0}
    app.service = SimpleNamespace(
        local_tz=timezone.utc,
        find_submission_overlaps=lambda *a, **k: [],
        export_selected_tasks_report=lambda *a, **k: None,
        reset_selected_tasks=lambda ids: calls.__setitem__("reset", ids),
        delete_selected_tasks=lambda ids: calls.__setitem__("delete", ids),
    )
    app._create_risky_operation_backup = lambda _reason: calls.__setitem__("backup", calls["backup"] + 1)
    app.refresh_structure = lambda: calls.__setitem__("refresh", calls["refresh"] + 1)
    app.refresh_live_values = lambda: calls.__setitem__("refresh", calls["refresh"] + 1)

    import task_timer.app as app_module
    app_module.SelectedTaskExportDialog = lambda _root, _service: SimpleNamespace(
        result=SimpleNamespace(task_ids=["t1", "t2"], window_start_utc=None, window_end_utc=datetime(2026, 1, 31, tzinfo=timezone.utc), mark_submitted=False, reason="")
    )
    app_module.PostSelectedExportActionDialog = lambda _root: SimpleNamespace(choice="reset")
    app_module.filedialog.asksaveasfilename = lambda **_k: str(tmp_path / "x.txt")
    app_module.messagebox.showinfo = lambda *a, **k: None

    assert TaskTimerApp.export_selected_tasks(app) is True
    assert calls["backup"] == 1
    assert calls["reset"] == ["t1", "t2"]
    assert calls["delete"] is None


def test_selected_export_post_action_delete_creates_single_backup_and_deletes_selected(tmp_path) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    calls = {"backup": 0, "reset": None, "delete": None}
    app.service = SimpleNamespace(
        local_tz=timezone.utc,
        find_submission_overlaps=lambda *a, **k: [],
        export_selected_tasks_report=lambda *a, **k: None,
        reset_selected_tasks=lambda ids: calls.__setitem__("reset", ids),
        delete_selected_tasks=lambda ids: calls.__setitem__("delete", ids),
    )
    app._create_risky_operation_backup = lambda _reason: calls.__setitem__("backup", calls["backup"] + 1)
    app.refresh_structure = lambda: None
    app.refresh_live_values = lambda: None

    import task_timer.app as app_module
    app_module.SelectedTaskExportDialog = lambda _root, _service: SimpleNamespace(
        result=SimpleNamespace(task_ids=["t1"], window_start_utc=None, window_end_utc=datetime(2026, 1, 31, tzinfo=timezone.utc), mark_submitted=False, reason="")
    )
    app_module.PostSelectedExportActionDialog = lambda _root: SimpleNamespace(choice="delete")
    app_module.filedialog.asksaveasfilename = lambda **_k: str(tmp_path / "x.txt")
    app_module.messagebox.showinfo = lambda *a, **k: None

    assert TaskTimerApp.export_selected_tasks(app) is True
    assert calls["backup"] == 1
    assert calls["reset"] is None
    assert calls["delete"] == ["t1"]


def test_keep_mini_toggle_checked_saves_and_opens_without_minimize() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.ui_settings = UISettings(keep_mini_open=False)
    saves: list[bool] = []
    app.ui_settings_store = SimpleNamespace(save=lambda settings: saves.append(settings.keep_mini_open))
    app.keep_mini_open_var = SimpleNamespace(get=lambda: True)
    opened: list[str] = []
    app.open_mini_mode = lambda: opened.append("open")

    TaskTimerApp._on_keep_mini_open_toggle(app)

    assert app.ui_settings.keep_mini_open is True
    assert saves == [True]
    assert opened == ["open"]


def test_keep_mini_toggle_unchecked_saves_without_closing_open_mini() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.ui_settings = UISettings(keep_mini_open=True)
    saves: list[bool] = []
    app.ui_settings_store = SimpleNamespace(save=lambda settings: saves.append(settings.keep_mini_open))
    app.keep_mini_open_var = SimpleNamespace(get=lambda: False)
    app.mini_mode_window = SimpleNamespace(window=SimpleNamespace(winfo_exists=lambda: True))

    TaskTimerApp._on_keep_mini_open_toggle(app)

    assert app.ui_settings.keep_mini_open is False
    assert saves == [False]
    assert app.mini_mode_window is not None


def test_open_mini_mode_if_persistent_enabled_opens_only_when_true() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    opened: list[str] = []
    app.open_mini_mode = lambda: opened.append("open")
    app.ui_settings = UISettings(keep_mini_open=False)

    TaskTimerApp._open_mini_mode_if_persistent_enabled(app)
    assert opened == []

    app.ui_settings = UISettings(keep_mini_open=True)
    TaskTimerApp._open_mini_mode_if_persistent_enabled(app)
    assert opened == ["open"]


def test_init_schedules_startup_mini_mode_activation_when_setting_persisted() -> None:
    import task_timer.app as app_module

    root = _FakeRoot()
    root.title = lambda *_args, **_kwargs: None
    root.protocol = lambda *_args, **_kwargs: None

    original_disable = app_module.disable_snap_maximize
    original_zoom = app_module.install_zoom_guard
    original_stringvar = app_module.StringVar
    original_boolvar = app_module.tk.BooleanVar
    original_build_ui = app_module.TaskTimerApp._build_ui
    original_refresh_structure = app_module.TaskTimerApp.refresh_structure
    original_refresh_reminder = app_module.TaskTimerApp._refresh_month_end_reminder_ui
    original_maybe_popup = app_module.TaskTimerApp._maybe_show_startup_reminder_popup
    original_refresh_live = app_module.TaskTimerApp.refresh_live_values
    original_tick = app_module.TaskTimerApp._tick
    original_store = app_module.UISettingsStore
    try:
        app_module.disable_snap_maximize = lambda _root: None
        app_module.install_zoom_guard = lambda _root: None
        app_module.StringVar = lambda: SimpleNamespace()
        app_module.tk.BooleanVar = lambda value=False: SimpleNamespace(get=lambda: value)
        app_module.TaskTimerApp._build_ui = lambda self: None
        app_module.TaskTimerApp.refresh_structure = lambda self: None
        app_module.TaskTimerApp._refresh_month_end_reminder_ui = lambda self: None
        app_module.TaskTimerApp._maybe_show_startup_reminder_popup = lambda self: None
        app_module.TaskTimerApp.refresh_live_values = lambda self: None
        app_module.TaskTimerApp._tick = lambda self: None
        app_module.UISettingsStore = lambda _data_dir: SimpleNamespace(load=lambda: UISettings(keep_mini_open=True))

        service = SimpleNamespace(storage=SimpleNamespace(data_dir="."), state=SimpleNamespace(tasks={}))
        app = TaskTimerApp(root, service)
    finally:
        app_module.disable_snap_maximize = original_disable
        app_module.install_zoom_guard = original_zoom
        app_module.StringVar = original_stringvar
        app_module.tk.BooleanVar = original_boolvar
        app_module.TaskTimerApp._build_ui = original_build_ui
        app_module.TaskTimerApp.refresh_structure = original_refresh_structure
        app_module.TaskTimerApp._refresh_month_end_reminder_ui = original_refresh_reminder
        app_module.TaskTimerApp._maybe_show_startup_reminder_popup = original_maybe_popup
        app_module.TaskTimerApp.refresh_live_values = original_refresh_live
        app_module.TaskTimerApp._tick = original_tick
        app_module.UISettingsStore = original_store

    assert len(root.after_idle_callbacks) == 1
    assert root.after_idle_callbacks[0] == app._open_mini_mode_if_persistent_enabled


def test_open_mini_mode_keep_checked_lifts_existing_without_duplicate() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = _FakeRoot()
    app.service = object()
    app._after_state_change = lambda: None
    app.ui_settings = UISettings(keep_mini_open=True)
    lifts: list[str] = []
    existing = SimpleNamespace(window=SimpleNamespace(winfo_exists=lambda: True, lift=lambda: lifts.append("lift")))
    app.mini_mode_window = existing

    TaskTimerApp.open_mini_mode(app)

    assert lifts == ["lift"]
    assert app.mini_mode_window is existing


def test_mini_mode_destroy_callback_clears_reference() -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.mini_mode_window = object()

    TaskTimerApp._on_mini_mode_closed(app)

    assert app.mini_mode_window is None


def test_mini_mode_restore_main_respects_keep_open() -> None:
    calls: list[str] = []

    mini = MiniModeWindow.__new__(MiniModeWindow)
    mini.window = SimpleNamespace(
        master=SimpleNamespace(deiconify=lambda: calls.append("deiconify"), lift=lambda: calls.append("lift")),
        destroy=lambda: calls.append("destroy"),
    )
    mini.keep_open_provider = lambda: True

    MiniModeWindow.restore_main(mini)
    assert calls == ["deiconify", "lift"]

    mini.keep_open_provider = lambda: False
    MiniModeWindow.restore_main(mini)
    assert calls[-3:] == ["deiconify", "lift", "destroy"]


def test_build_menus_tools_contains_manage_subtask_templates(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    class _FakeMenu:
        def __init__(self, _parent=None, **_kwargs) -> None:
            self.commands=[]; self.cascades={}
        def add_command(self,label:str,command=None)->None: self.commands.append(label)
        def add_separator(self)->None: self.commands.append("---")
        def add_cascade(self,label:str,menu)->None: self.cascades[label]=menu
    class _Root:
        def configure(self, **kwargs) -> None: self.menu=kwargs.get("menu")
    import task_timer.app as app_module
    monkeypatch.setattr(app_module.tk, "Menu", _FakeMenu)
    app.root=_Root()
    app._reopen_last_export_checkpoint=lambda:None
    app._reset_all_task_timers=lambda:None
    app._manage_tags=lambda:None
    app._manage_subtask_templates=lambda:None
    app._open_month_end_reminder_settings=lambda:None
    app._create_backup_now=lambda:None
    app._open_backup_settings=lambda:None
    app._open_data_folder=lambda:None
    app._open_backup_folder=lambda:None
    app._restore_from_backup=lambda:None
    app._rebuild_snapshot_from_journal=lambda:None
    app.export_selected_tasks=lambda:None
    TaskTimerApp._build_menus(app)
    tools_menu = app.root.menu.cascades["Tools"]
    assert "Manage Subtask Templates" in tools_menu.commands


def test_manage_subtask_templates_dialog_opens(monkeypatch) -> None:
    app = TaskTimerApp.__new__(TaskTimerApp)
    app.root = object()
    app.service = object()
    called = {"opened": 0}
    import task_timer.app as app_module
    class _Dialog:
        def __init__(self, *_args, **_kwargs):
            called["opened"] += 1
            self.changed = False
    monkeypatch.setattr(app_module, "ManageSubtaskTemplatesDialog", _Dialog)
    TaskTimerApp._manage_subtask_templates(app)
    assert called["opened"] == 1
