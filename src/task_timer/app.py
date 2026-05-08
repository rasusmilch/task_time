"""Business logic and tkinter UI for Chronicle."""

from __future__ import annotations

import os
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import StringVar, Tk, filedialog, messagebox, simpledialog, ttk

from loguru import logger

from .dialogs import (
    AddTaskDialog,
    EditTaskDialog,
    ManageSubtaskTemplatesDialog,
    ManageTagsDialog,
    BackupSettingsDialog,
    EditTimelineDialog,
    MonthEndCloseReminderDialog,
    MonthEndReminderSettingsDialog,
    MoveTaskDialog,
    PostSelectedExportActionDialog,
    SelectedTaskExportDialog,
)
from .mini_mode import MiniModeWindow
from .reminders import should_show_month_end_banner
from .service import TaskTimerService
from .models import TaskState
from .settings import UISettingsStore
from .time_utils import format_duration_hm, is_last_business_day, utc_now
from .window_chrome import install_zoom_guard

RUNNING_COLOR = "#1f9d55"
STOPPED_COLOR = "#c62828"
DEFAULT_LONG_RUNNING_TASK_WARNING_HOURS = 12
# Legacy constants kept for compatibility with tests; row-grid UI was removed.
ROW_PARENT_STOPPED_COLOR = STOPPED_COLOR
ROW_SUBTASK_STOPPED_COLOR = STOPPED_COLOR


class TaskTimerApp:
    """tkinter user interface wrapper."""

    def __init__(self, root: Tk, service: TaskTimerService) -> None:
        self.root = root
        self.service = service
        self.log_path = getattr(
            service, "log_path", service.storage.data_dir / "logs" / "chronicle.log"
        )
        self._showing_error_dialog = False
        self.root.title("Chronicle")
        self.root.report_callback_exception = self._handle_tk_exception
        logger.info("UI startup")
        self.root.resizable(True, True)
        self.root.minsize(800, 500)
        install_zoom_guard(self.root)
        self.expanded_parents: set[str] = set()
        self.selected_task_id: str | None = None
        self.daily_var = StringVar()
        self.weekly_var = StringVar()
        self.ui_settings_store = UISettingsStore(self.service.storage.data_dir)
        self.ui_settings = self.ui_settings_store.load()
        self.sort_alpha_var = tk.BooleanVar(value=self.ui_settings.sort_alphabetically)
        self.keep_mini_open_var = tk.BooleanVar(value=self.ui_settings.keep_mini_open)
        self.mini_mode_window: MiniModeWindow | None = None
        self._tick_job: str | None = None
        self._startup_reminder_prompted_date: str | None = None
        self.default_name_font: tkfont.Font | None = None
        self.parent_name_font: tkfont.Font | None = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self.refresh_structure()
        self._refresh_month_end_reminder_ui()
        self._maybe_show_startup_reminder_popup()
        self.refresh_live_values()
        self.root.after_idle(self._open_mini_mode_if_persistent_enabled)
        self._tick()

    def _handle_tk_exception(self, exc_type, exc_value, exc_traceback) -> None:
        logger.opt(exception=(exc_type, exc_value, exc_traceback)).error(
            "Unhandled Tkinter callback exception"
        )
        if self._showing_error_dialog:
            return
        self._showing_error_dialog = True
        try:
            messagebox.showerror(
                "Chronicle Error",
                "Chronicle encountered an unexpected error.\nDetails were written to the log file.\n\nLog file:\n"
                + str(self.log_path),
            )
        except Exception:
            logger.exception("Failed to show Tkinter error dialog")
        finally:
            self._showing_error_dialog = False

    def _build_ui(self) -> None:
        self._init_row_fonts()
        self._build_menus()
        self.reminder_banner = tk.Frame(self.root, bg="#fff4e5", bd=1, relief="solid")
        reminder_label = tk.Label(
            self.reminder_banner,
            text="Month-end reminder: enter/export your time today.",
            bg="#fff4e5",
            anchor="w",
        )
        reminder_label.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=4)
        ttk.Button(
            self.reminder_banner, text="Export", command=self._on_reminder_export
        ).pack(side="left", padx=4, pady=4)
        ttk.Button(
            self.reminder_banner,
            text="Dismiss",
            command=self._dismiss_month_end_reminder_today,
        ).pack(side="left", padx=(0, 8), pady=4)

        self.toolbar_frame = ttk.Frame(self.root)
        self.toolbar_frame.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Button(self.toolbar_frame, text="Add Task", command=self.add_task).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(self.toolbar_frame, text="Export", command=self.export).pack(
            side="left", padx=4
        )
        ttk.Button(
            self.toolbar_frame, text="Mini Mode", command=self.open_mini_mode
        ).pack(side="left", padx=4)
        self.keep_mini_open_checkbox = ttk.Checkbutton(
            self.toolbar_frame,
            text="Keep Mini Open",
            variable=self.keep_mini_open_var,
            command=self._on_keep_mini_open_toggle,
        )
        self.keep_mini_open_checkbox.pack(side="left", padx=(0, 6))
        self.sort_alpha_checkbox = ttk.Checkbutton(
            self.toolbar_frame,
            text="Sort A-Z",
            variable=self.sort_alpha_var,
            command=self._on_sort_toggle,
        )
        self.sort_alpha_checkbox.pack(side="left", padx=(10, 4))
        self.daily_total_label = ttk.Label(
            self.toolbar_frame, textvariable=self.daily_var
        )
        self.daily_total_label.pack(side="left", padx=(12, 4))
        self.weekly_total_label = ttk.Label(
            self.toolbar_frame, textvariable=self.weekly_var
        )
        self.weekly_total_label.pack(side="left", padx=4)

        self.table_frame = ttk.Frame(self.root)
        self.table_frame.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_task_tree()
        self._build_selected_task_panel()

    def _init_row_fonts(self) -> None:
        try:
            self.default_name_font = tkfont.nametofont("TkDefaultFont")
            self.parent_name_font = self.default_name_font.copy()
            self.parent_name_font.configure(weight="bold")
        except (tk.TclError, RuntimeError):
            self.default_name_font = None
            self.parent_name_font = None

    def _build_menus(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(
            label="Create Backup Now", command=self._create_backup_now
        )
        file_menu.add_command(
            label="Backup Settings", command=self._open_backup_settings
        )
        file_menu.add_command(label="Open Data Folder", command=self._open_data_folder)
        file_menu.add_command(
            label="Open Backup Folder", command=self._open_backup_folder
        )
        file_menu.add_command(
            label="Export Selected Tasks...", command=self.export_selected_tasks
        )
        file_menu.add_command(
            label="Restore From Backup", command=self._restore_from_backup
        )
        file_menu.add_command(
            label="Rebuild Snapshot From Journal",
            command=self._rebuild_snapshot_from_journal,
        )
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(
            label="Reopen Last Export Checkpoint",
            command=self._reopen_last_export_checkpoint,
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Reset All Task Timers...", command=self._reset_all_task_timers
        )
        tools_menu.add_separator()
        tools_menu.add_command(label="Manage Tags", command=self._manage_tags)
        tools_menu.add_command(
            label="Manage Subtask Templates", command=self._manage_subtask_templates
        )
        tools_menu.add_command(
            label="Month-End Reminder Settings",
            command=self._open_month_end_reminder_settings,
        )
        menubar.add_cascade(label="Tools", menu=tools_menu)
        self.root.configure(menu=menubar)

    def add_task(self) -> None:
        dialog = AddTaskDialog(self.root, self.service)
        if not dialog.confirmed:
            return
        try:
            task_id = self.service.create_task(dialog.name, dialog.notes, dialog.tags)
        except ValueError as exc:
            logger.warning("User-facing validation error: {}", exc)
            messagebox.showerror("Create Task", str(exc))
            return
        selected_template_ids = getattr(dialog, "selected_template_ids", [])
        if selected_template_ids:
            try:
                result = self.service.apply_subtask_templates(
                    task_id, selected_template_ids
                )
            except ValueError as exc:
                logger.warning("User-facing validation error: {}", exc)
                messagebox.showerror("Create Task", str(exc))
                return
            logger.info(
                "Subtask template apply: created_count={} skipped_count={}",
                result.created_count,
                result.skipped_count,
            )
            if result.created_subtask_ids:
                self.expanded_parents.add(task_id)
                summary = f"Created {len(result.created_subtask_ids)} subtasks."
                if result.skipped_duplicates:
                    summary += f" Skipped {len(result.skipped_duplicates)} duplicates."
                messagebox.showinfo("Create Task", summary)
        self.refresh_structure()
        self.refresh_live_values()

    def export(self) -> bool:
        target = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text", "*.txt")]
        )
        if not target:
            return False
        self.service.export_report(Path(target), reset_after=False)
        logger.info("Normal export created at {}", target)
        self.mark_month_end_reminder_handled_today()
        should_reset = messagebox.askyesno(
            "Reset after export", "Export done. Reset all non-deleted task timers?"
        )
        if should_reset:
            self.service.reset_all_non_deleted_tasks()
        logger.info("Reset all timers")
        self.refresh_structure()
        self.refresh_live_values()
        self._refresh_month_end_reminder_ui()
        return True

    def export_selected_tasks(self) -> bool:
        dialog = SelectedTaskExportDialog(self.root, self.service)
        if not dialog.result:
            return False
        if dialog.result.mark_submitted:
            overlaps = self.service.find_submission_overlaps(
                dialog.result.task_ids,
                dialog.result.window_start_utc,
                dialog.result.window_end_utc,
            )
            if overlaps:
                lines = [
                    "Some selected time may already have been entered in Epicor.",
                    "",
                    "Overlaps:",
                ]
                for item in overlaps:
                    start = (
                        item["overlap_start_utc"]
                        .astimezone(self.service.local_tz)
                        .strftime("%Y-%m-%d %I:%M %p")
                    )
                    end = (
                        item["overlap_end_utc"]
                        .astimezone(self.service.local_tz)
                        .strftime("%Y-%m-%d %I:%M %p")
                    )
                    reason = item["existing_reason"] or "n/a"
                    lines.append(
                        f"- {item['task_name']}: {start} to {end} (submission {item['existing_submission_id']}, reason: {reason})"
                    )
                proceed = messagebox.askyesno(
                    "Possible duplicate Epicor entry",
                    "\n".join(lines) + "\n\nContinue and Mark Anyway?",
                )
                if not proceed:
                    return False
        target = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text", "*.txt")]
        )
        if not target:
            return False
        logger.info("Selected export started")
        self.service.export_selected_tasks_report(
            Path(target),
            dialog.result.task_ids,
            dialog.result.window_start_utc,
            dialog.result.window_end_utc,
            mark_submitted=dialog.result.mark_submitted,
            reason=dialog.result.reason,
        )

        logger.info("Selected export created at {}", target)
        if dialog.result.mark_submitted:
            logger.info("Selected export marked as submitted")
        post_action = PostSelectedExportActionDialog(self.root).choice
        self._handle_selected_export_post_action(post_action, dialog.result.task_ids)

        messagebox.showinfo("Export Selected Tasks", "Selected-task export complete.")
        return True

    def _clear_selection_if_deleted(self, affected_task_ids: set[str]) -> None:
        current_selected = getattr(self, "selected_task_id", None)
        if current_selected in affected_task_ids:
            self.selected_task_id = None
            if hasattr(self, "task_tree"):
                self.task_tree.selection_remove(*self.task_tree.selection())

    def _handle_selected_export_post_action(
        self, action: str, selected_task_ids: list[str]
    ) -> None:
        if action == "leave":
            return
        if action == "reset":
            logger.info("Post selected export action: reset")
            self._create_risky_operation_backup(
                "before resetting selected exported tasks"
            )
            self.service.reset_selected_tasks(selected_task_ids)
            self.refresh_structure()
            self.refresh_live_values()
            return
        if action == "delete":
            logger.info("Post selected export action: delete")
            self._create_risky_operation_backup(
                "before deleting selected exported tasks"
            )
            affected_ids = set(
                self.service.delete_selected_tasks(selected_task_ids) or []
            )
            self._clear_selection_if_deleted(affected_ids)
            self.refresh_structure()
            self.refresh_live_values()

    def _on_keep_mini_open_toggle(self) -> None:
        self.ui_settings.keep_mini_open = self.keep_mini_open_var.get()
        self.ui_settings_store.save(self.ui_settings)
        if self.ui_settings.keep_mini_open:
            self.open_mini_mode()

    def _on_mini_mode_closed(self) -> None:
        self.mini_mode_window = None

    def _open_mini_mode_if_persistent_enabled(self) -> None:
        if self.ui_settings.keep_mini_open:
            self.open_mini_mode()

    def open_mini_mode(self) -> None:
        should_keep_open = self.ui_settings.keep_mini_open
        if self.mini_mode_window and self.mini_mode_window.window.winfo_exists():
            self.mini_mode_window.window.lift()
            if not should_keep_open:
                self.root.iconify()
            return
        self.mini_mode_window = MiniModeWindow(
            self.root,
            self.service,
            self._after_state_change,
            self._is_month_end_reminder_due_today,
            keep_open_provider=lambda: self.ui_settings.keep_mini_open,
            on_destroy=self._on_mini_mode_closed,
        )
        if not should_keep_open:
            self.root.iconify()

    def _build_task_tree(self) -> None:
        # Keep the task tree column first because ttk.Treeview uses #0 for hierarchy.
        self.task_tree = ttk.Treeview(
            self.table_frame,
            columns=("notes", "state", "elapsed"),
            show="tree headings",
            selectmode="browse",
        )
        self.task_tree.heading("#0", text="Task")
        self.task_tree.heading("notes", text="Notes")
        self.task_tree.heading("state", text="State")
        self.task_tree.heading("elapsed", text="Elapsed")
        self.task_tree.column("#0", width=240, minwidth=170, stretch=False, anchor="w")
        self.task_tree.column(
            "notes", width=280, minwidth=200, stretch=True, anchor="w"
        )
        self.task_tree.column(
            "state", width=130, minwidth=120, stretch=False, anchor="center"
        )
        self.task_tree.column(
            "elapsed", width=80, minwidth=75, stretch=False, anchor="e"
        )
        y_scroll = ttk.Scrollbar(
            self.table_frame, orient="vertical", command=self.task_tree.yview
        )
        self.task_tree.configure(yscrollcommand=y_scroll.set)
        self.task_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.table_frame.grid_rowconfigure(0, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)
        if self.parent_name_font is not None:
            self.task_tree.tag_configure("parent", font=self.parent_name_font)
        self.task_tree.tag_configure(
            "running", foreground=RUNNING_COLOR, background="#eef8f1"
        )
        self.task_tree.tag_configure("stopped", foreground=STOPPED_COLOR)
        self.task_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.task_tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.task_tree.bind("<<TreeviewClose>>", self._on_tree_close)
        self.task_tree.bind("<Double-1>", self._on_tree_double_click)
        self.task_tree.bind("<Return>", self._on_tree_toggle_shortcut)
        self.task_tree.bind("<space>", self._on_tree_toggle_shortcut)
        self.task_tree.bind("<Delete>", self._on_tree_delete_shortcut)
        self.task_tree.bind("<Control-e>", self._on_tree_edit_shortcut)

    def _build_selected_task_panel(self) -> None:
        self.selected_task_panel = ttk.Frame(self.table_frame)
        self.selected_task_panel.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        self.selected_task_panel.grid_columnconfigure(0, weight=1)
        self.selected_task_label_var = StringVar(value="Selected: None")
        ttk.Label(
            self.selected_task_panel, textvariable=self.selected_task_label_var
        ).grid(row=0, column=0, sticky="w")
        self.selected_state_label = tk.Label(
            self.selected_task_panel,
            text="",
            bg=self.root.cget("bg"),
            fg="black",
            padx=8,
            pady=1,
        )
        self.selected_state_label.grid(
            row=0, column=1, sticky="e", padx=(8, 0), pady=(0, 6)
        )
        button_bar = ttk.Frame(self.selected_task_panel)
        button_bar.grid(row=1, column=0, sticky="w")
        self.selected_toggle_btn = ttk.Button(
            button_bar, text="Start", command=self._toggle_selected_task
        )
        self.selected_toggle_btn.pack(side="left", padx=(0, 4))
        self.selected_reset_btn = ttk.Button(
            button_bar, text="Reset", command=self._reset_selected_task
        )
        self.selected_reset_btn.pack(side="left", padx=4)
        self.selected_delete_btn = ttk.Button(
            button_bar, text="Delete", command=self._delete_selected_task
        )
        self.selected_delete_btn.pack(side="left", padx=4)
        self.selected_move_btn = ttk.Button(
            button_bar, text="Move Task", command=self._move_selected_task
        )
        self.selected_move_btn.pack(side="left", padx=4)
        self.selected_edit_btn = ttk.Button(
            button_bar, text="Edit Task", command=self._edit_selected_task
        )
        self.selected_edit_btn.pack(side="left", padx=4)
        self.selected_timeline_btn = ttk.Button(
            button_bar, text="Edit Timeline", command=self._edit_selected_timeline
        )
        self.selected_timeline_btn.pack(side="left", padx=4)
        self._refresh_selected_task_panel()

    def refresh_structure(self) -> None:
        selected = self._selected_task_id()
        for item in self.task_tree.get_children(""):
            self.task_tree.delete(item)
        roots = self._sorted_tasks(self.service.root_tasks(include_deleted=False))
        children_map = self.service.task_tree_children_map(include_deleted=False)
        for root in roots:
            children = self._sorted_tasks(children_map.get(root.task_id, []))
            if self._has_running_descendant(root.task_id, children_map):
                self.expanded_parents.add(root.task_id)
            self.task_tree.insert(
                "",
                "end",
                iid=root.task_id,
                text=root.name,
                values=(root.notes, "■ Stopped", "00:00"),
                open=root.task_id in self.expanded_parents,
                tags=self._tree_tags(
                    root, is_subtask=False, has_children=bool(children)
                ),
            )
            for child in children:
                grandkids = self._sorted_tasks(children_map.get(child.task_id, []))
                if self._has_running_descendant(child.task_id, children_map):
                    self.expanded_parents.add(child.task_id)
                self.task_tree.insert(
                    root.task_id,
                    "end",
                    iid=child.task_id,
                    text=child.name,
                    values=(child.notes, "■ Stopped", "00:00"),
                    open=child.task_id in self.expanded_parents,
                    tags=self._tree_tags(
                        child, is_subtask=True, has_children=bool(grandkids)
                    ),
                )
                for nested in grandkids:
                    self.task_tree.insert(
                        child.task_id,
                        "end",
                        iid=nested.task_id,
                        text=nested.name,
                        values=(nested.notes, "■ Stopped", "00:00"),
                        tags=self._tree_tags(
                            nested, is_subtask=True, has_children=False
                        ),
                    )
            if self._has_running_descendant(root.task_id, children_map):
                self.task_tree.item(root.task_id, open=True)
        if selected and self.task_tree.exists(selected):
            self.task_tree.selection_set(selected)
            self.selected_task_id = selected
        elif self.selected_task_id and not self.task_tree.exists(self.selected_task_id):
            self.selected_task_id = None
        self._refresh_selected_task_panel()
        if self.mini_mode_window and self.mini_mode_window.window.winfo_exists():
            self.mini_mode_window.refresh_structure()

    def _sorted_tasks(self, tasks: list[TaskState]) -> list[TaskState]:
        if not self.sort_alpha_var.get():
            return tasks
        return sorted(
            tasks, key=lambda task: (task.name.strip().casefold(), task.task_id)
        )

    def _has_running_descendant(
        self, task_id: str, children_map: dict[str, list[TaskState]]
    ) -> bool:
        stack = list(children_map.get(task_id, []))
        while stack:
            child = stack.pop()
            if child.is_running:
                return True
            stack.extend(children_map.get(child.task_id, []))
        return False

    def _tree_tags(
        self, task: TaskState, *, is_subtask: bool, has_children: bool
    ) -> tuple[str, ...]:
        tags = ["subtask" if is_subtask else "parent" if has_children else "task"]
        tags.append("running" if task.is_running else "stopped")
        return tuple(tags)

    def _selected_task_id(self) -> str | None:
        sel = self.task_tree.selection()
        return sel[0] if sel else self.selected_task_id

    def _on_sort_toggle(self) -> None:
        self.ui_settings.sort_alphabetically = self.sort_alpha_var.get()
        self.ui_settings_store.save(self.ui_settings)
        self.refresh_structure()
        self.refresh_live_values()

    def refresh_live_values(self) -> None:
        now_utc = utc_now()
        for task_id, task in self.service.state.tasks.items():
            if task.is_deleted or not self.task_tree.exists(task_id):
                continue
            elapsed = (
                self.service.task_own_elapsed(task_id, now_utc)
                if not self.service.child_tasks(task_id, include_deleted=False)
                else self.service.task_tree_elapsed(task_id, now_utc)
            )
            state_text = self._task_state_display(task, now_utc)
            self.task_tree.set(task_id, "elapsed", format_duration_hm(elapsed))
            if self.task_tree.set(task_id, "state") != state_text:
                self.task_tree.set(task_id, "state", state_text)
            parent = self.task_tree.parent(task_id)
            has_children = bool(
                self.service.child_tasks(task_id, include_deleted=False)
            )
            self.task_tree.item(
                task_id,
                tags=self._tree_tags(
                    task, is_subtask=bool(parent), has_children=has_children
                ),
            )
        children_map = self.service.task_tree_children_map(include_deleted=False)
        for task_id in list(self.service.state.tasks):
            if not self.task_tree.exists(task_id):
                continue
            if self._has_running_descendant(task_id, children_map):
                self.expanded_parents.add(task_id)
                self.task_tree.item(task_id, open=True)
        daily, weekly, _ = self.service.compute_totals(now_utc)
        self.daily_var.set(f"Daily Total: {format_duration_hm(daily)}")
        self.weekly_var.set(f"Weekly Total: {format_duration_hm(weekly)}")
        if self.mini_mode_window and self.mini_mode_window.window.winfo_exists():
            self.mini_mode_window.refresh_live_values()

    def _task_state_display(self, task: TaskState, now_utc: datetime) -> str:
        if not task.is_running:
            return "■ Stopped"
        threshold = timedelta(
            hours=getattr(
                self.ui_settings,
                "long_running_task_warning_hours",
                DEFAULT_LONG_RUNNING_TASK_WARNING_HOURS,
            )
        )
        start_utc = getattr(task, "currently_open_interval_start_utc", None)
        if start_utc is not None and (now_utc - start_utc) >= threshold:
            return "⚠ Long-running"
        return "▶ Running"

    def _on_tree_select(self, _event: object | None = None) -> None:
        self.selected_task_id = self._selected_task_id()
        self._refresh_selected_task_panel()

    def _tree_event_item_id(self) -> str | None:
        focused = self.task_tree.focus()
        if focused:
            return str(focused)
        return self._selected_task_id()

    def _on_tree_open(self, _event: object | None = None) -> None:
        task_id = self._tree_event_item_id()
        if task_id:
            self.expanded_parents.add(task_id)

    def _on_tree_close(self, _event: object | None = None) -> None:
        task_id = self._tree_event_item_id()
        if not task_id:
            return
        if any(
            child.is_running
            for child in self.service.descendant_tasks(task_id, include_deleted=False)
        ):
            self.expanded_parents.add(task_id)
            self.task_tree.item(task_id, open=True)
        else:
            self.expanded_parents.discard(task_id)

    def _after_state_change(self) -> None:
        self.refresh_structure()
        self.refresh_live_values()
        self._refresh_month_end_reminder_ui()

    def _selected_state_colors(self, state_text: str) -> tuple[str, str]:
        if state_text == "▶ Running":
            return ("#2e7d32", "#ffffff")
        if state_text == "⚠ Long-running":
            return ("#f9a825", "#111111")
        if state_text == "■ Stopped":
            return ("#c62828", "#ffffff")
        return (self.root.cget("bg"), "black")

    def _refresh_selected_task_panel(self) -> None:
        if not hasattr(self, "selected_task_label_var"):
            return
        task_id = self._selected_task_id()
        task = self.service.state.tasks.get(task_id) if task_id else None
        if task is None or task.is_deleted:
            self.selected_task_label_var.set("Selected: None")
            if hasattr(self, "selected_state_label"):
                bg, fg = self._selected_state_colors("")
                self.selected_state_label.configure(text="", bg=bg, fg=fg)
            self.selected_toggle_btn.configure(text="Start", state="disabled")
            for btn in (
                self.selected_reset_btn,
                self.selected_delete_btn,
                self.selected_move_btn,
                self.selected_edit_btn,
                self.selected_timeline_btn,
            ):
                btn.configure(state="disabled")
            return
        path_names: list[str] = [task.name]
        parent_id = task.parent_task_id
        while parent_id:
            parent = self.service.state.tasks.get(parent_id)
            if parent is None:
                break
            path_names.append(parent.name)
            parent_id = parent.parent_task_id
        self.selected_task_label_var.set(
            f"Selected: {' / '.join(reversed(path_names))}"
        )
        state_text = self._task_state_display(task, utc_now())
        if hasattr(self, "selected_state_label"):
            bg, fg = self._selected_state_colors(state_text)
            self.selected_state_label.configure(
                text=f"State: {state_text}", bg=bg, fg=fg
            )
        self.selected_toggle_btn.configure(
            text="Stop" if task.is_running else "Start", state="normal"
        )
        for btn in (
            self.selected_reset_btn,
            self.selected_delete_btn,
            self.selected_move_btn,
            self.selected_edit_btn,
            self.selected_timeline_btn,
        ):
            btn.configure(state="normal")

    def _toggle_selected_task(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self._toggle_task(task_id)

    def _reset_selected_task(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self._reset_task(task_id)

    def _delete_selected_task(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self._delete_task(task_id)

    def _move_selected_task(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self._move_task(task_id)

    def _edit_selected_task(self) -> None:
        task_id = self._selected_task_id()
        if task_id:
            self._edit_task(task_id)

    def _edit_selected_timeline(self) -> None:
        task_id = self._selected_task_id()
        if not task_id:
            return
        dialog = EditTimelineDialog(self.root, self.service, task_id)
        if dialog.changed:
            self._after_state_change()

    def _on_tree_double_click(self, _event: object | None = None) -> str | None:
        self._toggle_selected_task()
        return "break"

    def _on_tree_toggle_shortcut(self, _event: object | None = None) -> str | None:
        self._toggle_selected_task()
        return "break"

    def _on_tree_delete_shortcut(self, _event: object | None = None) -> str | None:
        self._delete_selected_task()
        return "break"

    def _on_tree_edit_shortcut(self, _event: object | None = None) -> str | None:
        self._edit_selected_task()
        return "break"

    def _toggle_task(self, task_id: str) -> None:
        task = self.service.state.tasks.get(task_id)
        if task is None:
            return
        try:
            if task.is_running:
                self.service.stop_task(task_id)
            else:
                self.service.start_task(task_id)
        except ValueError as exc:
            logger.warning("User-facing validation error: {}", exc)
            messagebox.showerror("Task", str(exc))
            return
        except Exception:
            logger.exception("Unexpected failure while toggling task state")
            messagebox.showerror(
                "Task", "Unexpected failure while toggling task state."
            )
            return
        self._after_state_change()

    def _reset_task(self, task_id: str) -> None:
        task = self.service.state.tasks.get(task_id)
        if not task:
            return
        children = self.service.child_tasks(task_id, include_deleted=False)

        if children:
            choice = messagebox.askyesnocancel(
                "Confirm reset",
                "This task has subtasks. Choose reset scope:\n\n"
                "• Yes = Reset selected task and all subtasks (default)\n"
                "• No = Reset selected task only\n"
                "• Cancel = Do nothing",
                default=messagebox.YES,
            )
            if choice is None:
                return
            if choice:
                self._create_risky_operation_backup(
                    "before resetting selected task and descendants"
                )
                try:
                    self.service.reset_task_tree(task_id)
                except ValueError as exc:
                    logger.warning("User-facing validation error: {}", exc)
                    messagebox.showerror("Reset Task", str(exc))
                    return
            else:
                self._create_risky_operation_backup("before resetting selected task")
                try:
                    self.service.reset_task_only(task_id)
                except ValueError as exc:
                    logger.warning("User-facing validation error: {}", exc)
                    messagebox.showerror("Reset Task", str(exc))
                    return
            self._after_state_change()
            return

        if messagebox.askyesno("Confirm reset", "Reset this task timer to zero?"):
            self._create_risky_operation_backup("before resetting selected task")
            try:
                self.service.reset_task_only(task_id)
            except ValueError as exc:
                logger.warning("User-facing validation error: {}", exc)
                messagebox.showerror("Reset Task", str(exc))
                return
            self._after_state_change()

    def _reset_all_task_timers(self) -> None:
        should_reset = messagebox.askyesno(
            "Confirm Reset All Timers",
            "Reset elapsed time for all active tasks to zero?\n\n"
            "This will record reset events for every non-deleted task.\n\n"
            "Task history will remain in the journal, but current elapsed totals will restart from this point.",
        )
        if not should_reset:
            return
        has_active = any(
            not task.is_deleted for task in self.service.state.tasks.values()
        )
        if not has_active:
            messagebox.showinfo(
                "Reset All Task Timers", "There are no active tasks to reset."
            )
            return
        self._create_risky_operation_backup("before reset all task timers")
        self.service.reset_all_non_deleted_tasks()
        logger.info("Reset all timers")
        self._after_state_change()
        messagebox.showinfo(
            "Reset All Task Timers", "All active task timers were reset."
        )

    def _delete_task(self, task_id: str) -> None:
        task = self.service.state.tasks.get(task_id)
        if not task:
            return
        children = self.service.child_tasks(task_id, include_deleted=False)

        if children:
            should_delete_tree = messagebox.askokcancel(
                "Confirm delete",
                "Deleting this task will also delete all descendant subtasks.\n\n"
                "Continue?",
                default=messagebox.OK,
            )
            if not should_delete_tree:
                return
            self._create_risky_operation_backup(
                "before deleting selected task and descendants"
            )
            try:
                self.service.delete_task_tree(task_id)
            except ValueError as exc:
                logger.warning("User-facing validation error: {}", exc)
                messagebox.showerror("Delete Task", str(exc))
                return
            self.expanded_parents.discard(task_id)
            self._after_state_change()
            return

        if messagebox.askyesno("Confirm delete", "Delete this task from active view?"):
            self._create_risky_operation_backup("before deleting selected task")
            try:
                self.service.delete_task_only(task_id)
            except ValueError as exc:
                logger.warning("User-facing validation error: {}", exc)
                messagebox.showerror("Delete Task", str(exc))
                return
            self._after_state_change()

    def _edit_task(self, task_id: str) -> None:
        dialog = EditTaskDialog(self.root, self.service, task_id)
        if getattr(dialog, "added_subtask", False):
            self.expanded_parents.add(task_id)
        if dialog.changed:
            self._after_state_change()

    def _move_task(self, task_id: str) -> None:
        task = self.service.state.tasks.get(task_id)
        if not task or task.is_deleted:
            messagebox.showerror("Move Task", "Selected task no longer exists.")
            self._after_state_change()
            return

        old_parent_task_id = task.parent_task_id
        dialog = MoveTaskDialog(self.root, self.service, task_id)
        if not getattr(dialog, "confirmed", False):
            return

        if dialog.new_parent_task_id is not None and not self.service.state.tasks.get(
            dialog.new_parent_task_id
        ):
            messagebox.showerror("Move Task", "Selected parent task no longer exists.")
            self._after_state_change()
            return

        if old_parent_task_id == dialog.new_parent_task_id:
            return

        try:
            self.service.move_task(
                task_id,
                dialog.new_parent_task_id,
                getattr(dialog, "reason", "") or None,
            )
            logger.info("Task move/re-parent completed for task_id={}", task_id)
        except ValueError as exc:
            logger.warning("User-facing validation error: {}", exc)
            messagebox.showerror("Move Task", str(exc))
            return

        if dialog.new_parent_task_id:
            self.expanded_parents.add(dialog.new_parent_task_id)

        self.refresh_structure()
        if self.task_tree.exists(task_id):
            self.task_tree.selection_set(task_id)
            self.selected_task_id = task_id
        self._refresh_selected_task_panel()
        self.refresh_live_values()

    def _manage_tags(self) -> None:
        dialog = ManageTagsDialog(self.root, self.service)
        if dialog.changed:
            self._after_state_change()

    def _manage_subtask_templates(self) -> None:
        dialog = ManageSubtaskTemplatesDialog(self.root, self.service)
        if dialog.changed:
            self._after_state_change()

    def _create_risky_operation_backup(self, reason: str) -> None:
        self.service._create_risky_operation_backup(reason)

    def _create_backup_now(self) -> None:
        backup_path = self.service.create_backup_now("manual backup from UI")
        logger.info("Backup created at {}", backup_path)
        messagebox.showinfo("Backup Created", f"Backup created:\n{backup_path}")

    def _open_backup_settings(self) -> None:
        dialog = BackupSettingsDialog(
            self.root, self.service, self.service.load_backup_settings()
        )
        if not dialog.confirmed or dialog.settings is None:
            return
        self.service.save_backup_settings(dialog.settings)
        self.service.apply_backup_retention()
        messagebox.showinfo("Backup Settings", "Backup settings saved.")

    def _open_data_folder(self) -> None:
        self._open_folder(self.service.storage.data_dir)

    def _open_backup_folder(self) -> None:
        self._open_folder(self.service.backups.open_backup_folder())

    def _restore_from_backup(self) -> None:
        backups = self.service.list_managed_backups()
        if not backups:
            messagebox.showinfo("Restore", "No managed backups are available.")
            return
        options = [
            f"{idx + 1}. {item.created_utc} [{item.backup_type}] {item.reason} :: {item.path.name}"
            for idx, item in enumerate(backups[:25])
        ]
        choice = simpledialog.askinteger(
            "Restore From Backup",
            "Select backup number to restore:\n\n" + "\n".join(options),
            minvalue=1,
            maxvalue=len(options),
        )
        if not choice:
            return
        selected = backups[choice - 1]
        if not messagebox.askyesno(
            "Confirm restore",
            "A safety backup of current data will be created first.\nContinue restore?",
        ):
            return
        logger.info("Restore started from {}", selected.path)
        self.service.restore_from_backup(selected.path)
        logger.info("Restore completed from {}", selected.path)
        self._after_state_change()
        messagebox.showinfo("Restore", f"Restore complete from:\n{selected.path.name}")

    def _rebuild_snapshot_from_journal(self) -> None:
        if not messagebox.askyesno(
            "Rebuild Snapshot",
            "This will create a safety backup and rebuild state_snapshot.json from journal events. Continue?",
        ):
            return
        self.service.rebuild_snapshot_from_journal()
        self._after_state_change()
        messagebox.showinfo("Rebuild complete", "Snapshot rebuilt from journal.")

    def _reopen_last_export_checkpoint(self) -> None:
        reason = simpledialog.askstring(
            "Reopen Export Checkpoint",
            "Reason/comment for reopening the last export checkpoint:",
        )
        if reason is None:
            return
        if not messagebox.askyesno(
            "Confirm Reopen",
            "This will void/reopen the active export checkpoint.\n"
            "It will not delete old export files and the action is journaled.\nContinue?",
        ):
            return
        try:
            self.service.void_last_export_checkpoint(reason)
            messagebox.showinfo(
                "Checkpoint reopened", "The active export checkpoint was reopened."
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected failure reopening export checkpoint")
            messagebox.showerror("Reopen failed", str(exc))

    @staticmethod
    def _open_folder(path: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif os.name == "posix":
                subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
        except Exception:  # noqa: BLE001
            messagebox.showinfo("Folder", f"Folder path:\n{path}")

    def _local_today(self) -> date:
        return datetime.now().astimezone(self.service.local_tz).date()

    def _is_month_end_reminder_due_today(self) -> bool:
        return should_show_month_end_banner(self.ui_settings, self._local_today())

    def mark_month_end_reminder_handled_today(self) -> None:
        today_iso = self._local_today().isoformat()
        self.ui_settings.month_end_reminder_last_dismissed_local_date = today_iso
        self.ui_settings.month_end_reminder_last_export_prompted_local_date = today_iso
        self.ui_settings_store.save(self.ui_settings)

    def _dismiss_month_end_reminder_today(self) -> None:
        self.mark_month_end_reminder_handled_today()
        self._refresh_month_end_reminder_ui()

    def _on_reminder_export(self) -> None:
        self.export()
        self._refresh_month_end_reminder_ui()

    def _refresh_month_end_reminder_ui(self) -> None:
        if not hasattr(self, "reminder_banner"):
            return
        should_show = self._is_month_end_reminder_due_today()
        if should_show:
            if not self.reminder_banner.winfo_ismapped():
                if hasattr(self, "toolbar_frame"):
                    self.reminder_banner.pack(
                        fill="x", padx=8, pady=(8, 4), before=self.toolbar_frame
                    )
                else:
                    self.reminder_banner.pack(fill="x", padx=8, pady=(8, 4))
        elif self.reminder_banner.winfo_ismapped():
            self.reminder_banner.pack_forget()
        if self.mini_mode_window and self.mini_mode_window.window.winfo_exists():
            self.mini_mode_window.refresh_live_values()

    def _maybe_show_startup_reminder_popup(self) -> None:
        if not self.ui_settings.month_end_reminder_enabled:
            return
        if not self.ui_settings.month_end_reminder_show_startup_notice:
            return
        today = self._local_today()
        today_iso = today.isoformat()
        if not is_last_business_day(today):
            return
        if self.ui_settings.month_end_reminder_last_dismissed_local_date == today_iso:
            return
        if (
            self.ui_settings.month_end_reminder_last_export_prompted_local_date
            == today_iso
        ):
            return
        if self._startup_reminder_prompted_date == today_iso:
            return
        self._startup_reminder_prompted_date = today_iso
        messagebox.showinfo(
            "Month-End Reminder", "Month-end reminder: enter/export your time today."
        )
        self.ui_settings.month_end_reminder_last_export_prompted_local_date = today_iso
        self.ui_settings_store.save(self.ui_settings)
        self.root.lift()

    def _open_month_end_reminder_settings(self) -> None:
        dialog = MonthEndReminderSettingsDialog(self.root, self.ui_settings)
        if not dialog.confirmed:
            return
        self.ui_settings.month_end_reminder_enabled = dialog.enabled_var.get()
        self.ui_settings.month_end_reminder_show_startup_notice = (
            dialog.startup_var.get()
        )
        self.ui_settings.month_end_reminder_show_close_notice = dialog.close_var.get()
        self.ui_settings_store.save(self.ui_settings)
        self._refresh_month_end_reminder_ui()

    def _on_close_request(self) -> None:
        if (
            not self.ui_settings.month_end_reminder_enabled
            or not self.ui_settings.month_end_reminder_show_close_notice
            or not is_last_business_day(self._local_today())
        ):
            self.root.destroy()
            return
        dialog = MonthEndCloseReminderDialog(self.root)
        if dialog.choice == "return":
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            return
        if dialog.choice == "export":
            self.export()
            self.root.deiconify()
            self.root.lift()
            return
        self.root.destroy()

    def _tick(self) -> None:
        self.refresh_live_values()
        now_local = datetime.now().astimezone(self.service.local_tz)
        next_delay_ms = max(
            (60 - now_local.second) * 1000 - (now_local.microsecond // 1000), 1000
        )
        self._tick_job = self.root.after(next_delay_ms, self._tick)
