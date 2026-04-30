from datetime import timedelta, timezone
from types import SimpleNamespace

from task_timer.app import STOPPED_COLOR, TaskTimerApp, TaskTimerService
from task_timer.dialogs import AddTaskDialog, BackupSettingsDialog, EditTaskDialog
from task_timer.mini_mode import MiniModeWindow, RUNNING_COLOR, STOPPED_COLOR as MINI_STOPPED_COLOR
from task_timer.settings import BackupSettings, UISettings
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
            "name_label": _Widget(),
            "notes_label": _Widget(),
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
    app.daily_var = object()
    app.weekly_var = object()
    app.add_task = lambda: None
    app.export = lambda: True
    app.open_mini_mode = lambda: None
    app._on_sort_toggle = lambda: None
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
    assert "Sort A-Z" in toolbar_texts


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
