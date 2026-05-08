"""Business logic and tkinter UI for Chronicle."""

from __future__ import annotations

import json
import os
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from tkinter import StringVar, Tk, Toplevel, filedialog, messagebox, simpledialog, ttk
from typing import Any
from uuid import uuid4

from loguru import logger

from .backups import BackupManager
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
    format_timeline_row,
)
from .exporter import build_export_text, build_selected_tasks_export_text, write_export_file
from .mini_mode import MiniModeWindow
from .models import AppState, IntervalRecord, NOTES_MAX_LENGTH, TagMeta, TaskState, TimeSubmission, event_dict
from .reminders import should_show_month_end_banner
from .settings import BackupSettings, UISettings, UISettingsStore
from .storage import EventStorage
from .subtask_templates import SubtaskTemplate, SubtaskTemplateItem, SubtaskTemplateStore
from .window_chrome import install_zoom_guard
from .tags import normalize_tag, normalize_tag_list
from .time_utils import (
    detect_local_timezone,
    format_duration_hm,
    is_last_business_day,
    combine_local_date_time,
    interval_seconds_in_local_day,
    interval_seconds_in_local_week,
    parse_duration_seconds,
    parse_flexible_time,
    parse_utc_z,
    sunday_week_start,
    to_utc_z,
    utc_now,
)

RUNNING_COLOR = "#1f9d55"
STOPPED_COLOR = "#c62828"
DEFAULT_LONG_RUNNING_TASK_WARNING_HOURS = 12
MAX_TASK_TREE_DEPTH = 2
# Legacy constants kept for compatibility with tests; row-grid UI was removed.
ROW_PARENT_STOPPED_COLOR = STOPPED_COLOR
ROW_SUBTASK_STOPPED_COLOR = STOPPED_COLOR

@dataclass(slots=True)
class ApplySubtaskTemplatesResult:
    created_subtask_ids: list[str]
    created_names: list[str]
    skipped_duplicates: list[str]
    template_names: list[str]
    created_count: int = 0
    skipped_count: int = 0


class TaskTimerService:
    """Business logic layer that emits events and derives state."""

    def __init__(self, storage: EventStorage) -> None:
        self.storage = storage
        self.backups = BackupManager(storage.data_dir)
        self.subtask_template_store = SubtaskTemplateStore(storage.data_dir)
        self.subtask_templates = self.subtask_template_store.load()
        self.local_tz = detect_local_timezone()
        self.local_tz_name = getattr(self.local_tz, "key", None) or getattr(self.local_tz, "zone", None) or str(self.local_tz)
        self.state = AppState()
        self.events = self.storage.iter_all_events()
        self._rebuild_state(self.events)
        self._save_snapshot()
        self._maybe_create_app_start_backup()

    def list_subtask_templates(self) -> list[SubtaskTemplate]:
        return list(self.subtask_templates)

    def get_subtask_template(self, template_id: str) -> SubtaskTemplate:
        for template in self.subtask_templates:
            if template.template_id == template_id:
                return template
        raise ValueError("Subtask template not found")

    def create_subtask_template(self, name: str, notes: str = "") -> str:
        now = to_utc_z(utc_now())
        template = SubtaskTemplate(
            template_id=str(uuid4()),
            name=name,
            notes=notes,
            items=[],
            created_at_utc=now,
            updated_at_utc=now,
        )
        self.subtask_templates.append(template)
        self.subtask_template_store.save(self.subtask_templates)
        return template.template_id

    def update_subtask_template(self, template_id: str, name: str, notes: str, items: list[SubtaskTemplateItem]) -> None:
        for idx, template in enumerate(self.subtask_templates):
            if template.template_id != template_id:
                continue
            normalized_items: list[SubtaskTemplateItem] = []
            for sort_order, item in enumerate(items):
                normalized_items.append(
                    SubtaskTemplateItem(
                        item_id=item.item_id or str(uuid4()),
                        name=item.name,
                        parent_item_id=item.parent_item_id,
                        notes=item.notes,
                        tags=item.tags,
                        sort_order=sort_order,
                    )
                )
            by_id = {item.item_id: item for item in normalized_items}
            for item in normalized_items:
                if item.parent_item_id is None:
                    continue
                parent_item = by_id.get(item.parent_item_id)
                if not parent_item:
                    raise ValueError("Template item parent not found")
                if parent_item.parent_item_id is not None:
                    raise ValueError("Template depth cannot exceed 2")
            self.subtask_templates[idx] = SubtaskTemplate(
                template_id=template.template_id,
                name=name,
                notes=notes,
                items=normalized_items,
                created_at_utc=template.created_at_utc,
                updated_at_utc=to_utc_z(utc_now()),
            )
            self.subtask_template_store.save(self.subtask_templates)
            return
        raise ValueError("Subtask template not found")

    def delete_subtask_template(self, template_id: str) -> None:
        kept = [template for template in self.subtask_templates if template.template_id != template_id]
        if len(kept) == len(self.subtask_templates):
            return
        self.subtask_templates = kept
        self.subtask_template_store.save(self.subtask_templates)

    def apply_subtask_templates(self, parent_task_id: str, template_ids: list[str]) -> ApplySubtaskTemplatesResult:
        parent = self.state.tasks.get(parent_task_id)
        if not parent:
            raise ValueError("Parent task not found")
        if parent.is_deleted:
            raise ValueError("Parent task is deleted")
        depth = self.task_depth(parent_task_id)
        if depth >= MAX_TASK_TREE_DEPTH:
            raise ValueError("Cannot apply templates to depth-2 subtasks.")
        if not template_ids:
            raise ValueError("At least one template must be selected")

        template_map = {template.template_id: template for template in self.subtask_templates}
        selected_templates: list[SubtaskTemplate] = []
        for template_id in template_ids:
            template = template_map.get(template_id)
            if not template:
                raise ValueError("Subtask template not found")
            selected_templates.append(template)

        existing_children = {child.name.strip().casefold(): child for child in self.child_tasks(parent_task_id, include_deleted=False)}
        created_subtask_ids: list[str] = []
        created_names: list[str] = []
        skipped_duplicates: list[str] = []

        for template in selected_templates:
            roots = sorted([i for i in template.items if i.parent_item_id is None], key=lambda i: i.sort_order)
            nested = sorted([i for i in template.items if i.parent_item_id is not None], key=lambda i: i.sort_order)
            item_to_task: dict[str, str] = {}

            for item in roots:
                normalized_name = item.name.strip().casefold()
                existing = existing_children.get(normalized_name)
                if existing:
                    skipped_duplicates.append(item.name)
                    item_to_task[item.item_id] = existing.task_id
                    continue
                subtask_id = self.create_subtask(parent_task_id, item.name, item.notes, item.tags)
                created = self.state.tasks[subtask_id]
                existing_children[normalized_name] = created
                created_subtask_ids.append(subtask_id)
                created_names.append(item.name)
                item_to_task[item.item_id] = subtask_id

            for item in nested:
                parent_subtask_id = item_to_task.get(item.parent_item_id or "")
                if not parent_subtask_id:
                    continue
                existing_nested = {c.name.strip().casefold() for c in self.child_tasks(parent_subtask_id, include_deleted=False)}
                normalized_name = item.name.strip().casefold()
                if normalized_name in existing_nested:
                    skipped_duplicates.append(item.name)
                    continue
                nested_id = self.create_subtask(parent_subtask_id, item.name, item.notes, item.tags)
                created_subtask_ids.append(nested_id)
                created_names.append(item.name)

        return ApplySubtaskTemplatesResult(
            created_subtask_ids=created_subtask_ids,
            created_names=created_names,
            skipped_duplicates=skipped_duplicates,
            template_names=[template.name for template in selected_templates],
            created_count=len(created_subtask_ids),
            skipped_count=len(skipped_duplicates),
        )


    def create_task(self, name: str, notes: str, tags: list[str] | None = None) -> str:
        task_id = str(uuid4())
        tag_list = normalize_tag_list(tags or [])
        self._append(task_id, "task_created", {"name": name.strip(), "notes": self._clean_notes(notes), "tags": tag_list, "parent_task_id": None})
        for key in tag_list:
            self.ensure_tag_exists(key)
        return task_id


    def create_subtask(self, parent_task_id: str, name: str, notes: str, tags: list[str] | None = None) -> str:
        can_accept, message = self.can_accept_child(parent_task_id)
        if not can_accept:
            raise ValueError(message)
        if not name.strip():
            raise ValueError("Task name is required")
        task_id = str(uuid4())
        tag_list = normalize_tag_list(tags or [])
        self._append(task_id, "task_created", {"name": name.strip(), "notes": self._clean_notes(notes), "tags": tag_list, "parent_task_id": parent_task_id})
        for key in tag_list:
            self.ensure_tag_exists(key)
        return task_id

    def task_depth(self, task_id: str) -> int:
        task = self.state.tasks.get(task_id)
        if not task:
            raise ValueError("Task not found")
        depth = 0
        seen: set[str] = {task_id}
        cursor = task
        while cursor.parent_task_id is not None:
            parent_id = cursor.parent_task_id
            if parent_id in seen:
                return depth
            parent = self.state.tasks.get(parent_id)
            if not parent:
                return depth
            seen.add(parent_id)
            depth += 1
            cursor = parent
        return depth

    def ancestor_tasks(self, task_id: str) -> list[TaskState]:
        task = self.state.tasks.get(task_id)
        if not task:
            raise ValueError("Task not found")
        out: list[TaskState] = []
        seen: set[str] = {task_id}
        cursor = task
        while cursor.parent_task_id is not None:
            parent_id = cursor.parent_task_id
            if parent_id in seen:
                raise ValueError("Task hierarchy is corrupted")
            parent = self.state.tasks.get(parent_id)
            if not parent:
                raise ValueError("Task hierarchy is corrupted")
            out.append(parent)
            seen.add(parent_id)
            cursor = parent
        return out

    def descendant_tasks(self, task_id: str, include_deleted: bool = False) -> list[TaskState]:
        if task_id not in self.state.tasks:
            raise ValueError("Task not found")
        out: list[TaskState] = []
        stack = list(reversed(self.child_tasks(task_id, include_deleted=True)))
        seen: set[str] = set()
        while stack:
            task = stack.pop()
            if task.task_id in seen:
                continue
            seen.add(task.task_id)
            if include_deleted or not task.is_deleted:
                out.append(task)
            stack.extend(reversed(self.child_tasks(task.task_id, include_deleted=True)))
        return out

    def direct_child_tasks(self, task_id: str, include_deleted: bool = False) -> list[TaskState]:
        return self.child_tasks(task_id, include_deleted=include_deleted)

    def subtree_height(self, task_id: str, include_deleted: bool = False) -> int:
        if task_id not in self.state.tasks:
            raise ValueError("Task not found")
        children = self.child_tasks(task_id, include_deleted=include_deleted)
        if not children:
            return 0
        return 1 + max(self.subtree_height(child.task_id, include_deleted=include_deleted) for child in children)

    def max_depth_after_move(self, task_id: str, new_parent_task_id: str | None) -> int:
        base_depth = 0 if new_parent_task_id is None else self.task_depth(new_parent_task_id) + 1
        return base_depth + self.subtree_height(task_id, include_deleted=False)

    def can_accept_child(self, parent_task_id: str) -> tuple[bool, str]:
        parent = self.state.tasks.get(parent_task_id)
        if not parent:
            return False, "Parent task not found"
        if parent.is_deleted:
            return False, "Cannot move a task under a deleted task."
        try:
            depth = self.task_depth(parent_task_id)
        except ValueError:
            return False, "Task hierarchy is corrupted"
        if depth >= MAX_TASK_TREE_DEPTH:
            return False, "Cannot create another subtask level here. Chronicle currently supports two nested subtask levels."
        return True, ""

    def child_tasks(self, parent_task_id: str, include_deleted: bool = False) -> list[TaskState]:
        children = [t for t in self.state.tasks.values() if t.parent_task_id == parent_task_id]
        if not include_deleted:
            children = [t for t in children if not t.is_deleted]
        return sorted(children, key=lambda t: (t.created_at_utc, t.task_id))

    def parent_task(self, task_id: str) -> TaskState | None:
        task = self.state.tasks.get(task_id)
        if not task or task.parent_task_id is None:
            return None
        return self.state.tasks.get(task.parent_task_id)

    def is_subtask(self, task_id: str) -> bool:
        task = self.state.tasks.get(task_id)
        return bool(task and task.parent_task_id is not None)

    def root_tasks(self, include_deleted: bool = False) -> list[TaskState]:
        roots = [t for t in self.state.tasks.values() if t.parent_task_id is None]
        if not include_deleted:
            roots = [t for t in roots if not t.is_deleted]
        return sorted(roots, key=lambda t: (t.created_at_utc, t.task_id))

    def task_tree_children_map(self, include_deleted: bool = False) -> dict[str, list[TaskState]]:
        output: dict[str, list[TaskState]] = {}
        for task in self.state.tasks.values():
            if task.parent_task_id is None:
                continue
            if not include_deleted and task.is_deleted:
                continue
            output.setdefault(task.parent_task_id, []).append(task)
        for children in output.values():
            children.sort(key=lambda t: (t.created_at_utc, t.task_id))
        return output


    def movable_parent_targets(self, task_id: str) -> list[TaskState]:
        task = self.state.tasks.get(task_id)
        if not task or task.is_deleted:
            return []
        descendants = {t.task_id for t in self.descendant_tasks(task_id, include_deleted=True)}
        out: list[TaskState] = []
        for candidate in sorted(self.state.tasks.values(), key=lambda t: (t.created_at_utc, t.task_id)):
            if candidate.is_deleted or candidate.task_id == task_id or candidate.task_id in descendants:
                continue
            try:
                depth = self.task_depth(candidate.task_id)
            except ValueError:
                continue
            if depth >= MAX_TASK_TREE_DEPTH:
                continue
            if self.max_depth_after_move(task_id, candidate.task_id) > MAX_TASK_TREE_DEPTH:
                continue
            out.append(candidate)
        return out

    def can_move_task(self, task_id: str, new_parent_task_id: str | None) -> tuple[bool, str]:
        task = self.state.tasks.get(task_id)
        if not task:
            return False, "Task not found"
        if task.is_deleted:
            return False, "Task is deleted"
        if new_parent_task_id == task_id:
            return False, "Cannot move a task under itself or one of its descendants."

        if new_parent_task_id is None:
            return True, ""

        new_parent = self.state.tasks.get(new_parent_task_id)
        if not new_parent:
            return False, "Parent task not found"
        if new_parent.is_deleted:
            return False, "Cannot move a task under a deleted task."
        can_accept, message = self.can_accept_child(new_parent_task_id)
        if not can_accept:
            if "two subtask levels" in message:
                return False, "Cannot move a task under a nested subtask."
            return False, message

        seen: set[str] = set()
        cursor = new_parent
        while cursor.parent_task_id is not None and cursor.parent_task_id not in seen:
            if cursor.parent_task_id == task_id:
                return False, "Cannot move a task under itself or one of its descendants."
            seen.add(cursor.parent_task_id)
            parent = self.state.tasks.get(cursor.parent_task_id)
            if not parent:
                break
            cursor = parent

        try:
            if self.max_depth_after_move(task_id, new_parent_task_id) > MAX_TASK_TREE_DEPTH:
                return False, "Cannot move this task there because it would exceed Chronicle's two-level subtask limit."
        except ValueError:
            return False, "Task hierarchy is corrupted"

        return True, ""

    def move_task(self, task_id: str, new_parent_task_id: str | None, reason: str | None = None) -> None:
        can_move, message = self.can_move_task(task_id, new_parent_task_id)
        if not can_move:
            raise ValueError(message)
        task = self.state.tasks.get(task_id)
        if not task:
            raise ValueError("Task not found")
        old_parent_task_id = task.parent_task_id
        if old_parent_task_id == new_parent_task_id:
            return
        payload: dict[str, Any] = {
            "old_parent_task_id": old_parent_task_id,
            "new_parent_task_id": new_parent_task_id,
        }
        if reason is not None and reason.strip():
            payload["reason"] = reason.strip()
        self._append(task_id, "task_moved", payload)

    def update_task(self, task_id: str, name: str, notes: str) -> None:
        self._append(task_id, "task_updated", {"name": name.strip(), "notes": self._clean_notes(notes)})

    def update_task_tags(self, task_id: str, tags: list[str]) -> None:
        norm = normalize_tag_list(tags)
        for key in norm:
            self.ensure_tag_exists(key)
        self._append(task_id, "task_tags_updated", {"tags": norm})

    def ensure_tag_exists(self, key: str) -> None:
        k = normalize_tag(key)
        meta = self.state.global_tags.get(k)
        if meta and not meta.archived:
            return
        if meta and meta.archived:
            raise ValueError(f"Tag '{k}' is archived. Unarchive it from Manage Tags.")
        self._append("__app__", "tag_created", {"key": k})

    def list_global_tags(self, include_archived: bool = True) -> list[TagMeta]:
        tags = sorted(self.state.global_tags.values(), key=lambda meta: meta.key)
        if include_archived:
            return tags
        return [meta for meta in tags if not meta.archived]

    def tag_usage_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in self.state.tasks.values():
            if task.is_deleted:
                continue
            for key in task.tags:
                counts[key] = counts.get(key, 0) + 1
        return counts

    def create_tag(self, key: str) -> None:
        norm = normalize_tag(key)
        meta = self.state.global_tags.get(norm)
        if meta and not meta.archived:
            raise ValueError(f"Tag '{norm}' already exists")
        if meta and meta.archived:
            raise ValueError(f"Tag '{norm}' is archived. Unarchive it instead.")
        self._append("__app__", "tag_created", {"key": norm})

    def rename_tag(self, old_key: str, new_key: str) -> None:
        old_norm = normalize_tag(old_key)
        new_norm = normalize_tag(new_key)
        if old_norm == new_norm:
            return
        if old_norm not in self.state.global_tags:
            raise ValueError(f"Tag '{old_norm}' does not exist")
        if new_norm in self.state.global_tags:
            raise ValueError(f"Tag '{new_norm}' already exists")
        self._append("__app__", "tag_renamed", {"old_key": old_norm, "new_key": new_norm})

    def archive_tag(self, key: str) -> None:
        norm = normalize_tag(key)
        meta = self.state.global_tags.get(norm)
        if not meta:
            raise ValueError(f"Tag '{norm}' does not exist")
        if meta.archived:
            return
        if self.tag_usage_counts().get(norm, 0) > 0:
            raise ValueError(f"Tag '{norm}' is in use and cannot be archived")
        self._append("__app__", "tag_archived", {"key": norm})

    def unarchive_tag(self, key: str) -> None:
        norm = normalize_tag(key)
        meta = self.state.global_tags.get(norm)
        if not meta:
            raise ValueError(f"Tag '{norm}' does not exist")
        if not meta.archived:
            return
        self._append("__app__", "tag_unarchived", {"key": norm})

    def delete_tag(self, key: str) -> None:
        norm = normalize_tag(key)
        meta = self.state.global_tags.get(norm)
        if not meta:
            raise ValueError(f"Tag '{norm}' does not exist")
        if self.tag_usage_counts().get(norm, 0) > 0:
            raise ValueError(f"Tag '{norm}' is in use and cannot be deleted")
        if not meta.archived:
            raise ValueError(f"Tag '{norm}' must be archived before deleting")
        self._append("__app__", "tag_deleted", {"key": norm})

    def available_tags_for_task(self, task_id: str) -> list[str]:
        if task_id not in self.state.tasks:
            raise ValueError("Task not found")
        return [meta.key for meta in self.list_global_tags(include_archived=False)]

    def assigned_tags_for_task(self, task_id: str) -> list[str]:
        task = self.state.tasks.get(task_id)
        if not task:
            raise ValueError("Task not found")
        return sorted(task.tags)

    def delete_task(self, task_id: str) -> None:
        self.delete_task_tree(task_id)

    def delete_task_only(self, task_id: str) -> None:
        task = self.state.tasks.get(task_id)
        if not task or task.is_deleted:
            return
        self.stop_task(task_id)
        self._append(task_id, "task_deleted", {})

    def delete_task_tree(self, task_id: str) -> None:
        task = self.state.tasks.get(task_id)
        if not task or task.is_deleted:
            return
        for child in self.child_tasks(task_id):
            self.delete_task_tree(child.task_id)
        self.delete_task_only(task_id)

    def start_task(self, task_id: str) -> None:
        if self.state.running_task_id == task_id:
            return
        if self.state.running_task_id:
            self.stop_task(self.state.running_task_id)
        self._append(task_id, "started", {})

    def stop_task(self, task_id: str) -> None:
        task = self.state.tasks.get(task_id)
        if not task or not task.is_running:
            return
        self._append(task_id, "stopped", {"interval_id": str(uuid4())})

    def reset_task(self, task_id: str) -> None:
        self.reset_task_only(task_id)

    def reset_task_only(self, task_id: str) -> None:
        self.stop_task(task_id)
        self._append(task_id, "reset", {})

    def reset_task_tree(self, task_id: str) -> None:
        task = self.state.tasks.get(task_id)
        if not task:
            return
        for child in self.child_tasks(task_id):
            self.reset_task_tree(child.task_id)
        self.reset_task_only(task_id)

    def parse_local_datetime_inputs(self, work_date: date, time_text: str) -> datetime:
        parsed_time = parse_flexible_time(time_text)
        return combine_local_date_time(work_date, parsed_time, self.local_tz)

    def parse_duration_input_seconds(self, duration_text: str) -> float:
        return parse_duration_seconds(duration_text)

    def add_manual_interval(self, task_id: str, start_local: datetime, stop_local: datetime, reason: str) -> None:
        if stop_local <= start_local:
            raise ValueError("Stop must be after start")
        if not reason.strip():
            raise ValueError("Reason is required")
        self._validate_interval_against_checkpoint(start_local, stop_local)
        self._append(
            task_id,
            "manual_interval_added",
            {
                "interval_id": str(uuid4()),
                "start_utc": to_utc_z(start_local.astimezone(timezone.utc)),
                "stop_utc": to_utc_z(stop_local.astimezone(timezone.utc)),
                "reason": reason.strip(),
            },
        )

    def edit_interval(self, task_id: str, interval_id: str, start_local: datetime, stop_local: datetime, reason: str) -> None:
        if stop_local <= start_local:
            raise ValueError("Stop must be after start")
        if not reason.strip():
            raise ValueError("Reason is required")
        task = self.state.tasks.get(task_id)
        if not task or interval_id not in task.intervals:
            raise ValueError("Interval not found")
        self._create_risky_operation_backup("before manual interval edit")
        self._validate_interval_against_checkpoint(start_local, stop_local)
        prior = task.intervals[interval_id]
        prior_start = prior.start_utc.astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
        prior_stop = prior.stop_utc.astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
        self._append(
            task_id,
            "interval_edited",
            {
                "interval_id": interval_id,
                "new_interval_id": str(uuid4()),
                "start_utc": to_utc_z(start_local.astimezone(timezone.utc)),
                "stop_utc": to_utc_z(stop_local.astimezone(timezone.utc)),
                "prior_interval_label": f"{prior_start} to {prior_stop}",
                "entry_mode": "interval",
                "reason": reason.strip(),
            },
        )

    def edit_duration_interval(
        self, task_id: str, interval_id: str, work_date_local: date, duration_seconds: float, reason: str
    ) -> None:
        if duration_seconds <= 0:
            raise ValueError("Duration must be greater than zero")
        if not reason.strip():
            raise ValueError("Reason is required")
        task = self.state.tasks.get(task_id)
        if not task or interval_id not in task.intervals:
            raise ValueError("Interval not found")
        self._create_risky_operation_backup("before manual duration edit")
        self._validate_duration_against_checkpoint(work_date_local)
        synthetic_start = combine_local_date_time(work_date_local, time(hour=12), self.local_tz).astimezone(timezone.utc)
        synthetic_stop = synthetic_start + timedelta(seconds=duration_seconds)
        prior = task.intervals[interval_id]
        prior_label = f"{prior.work_date_local or prior.start_utc.astimezone(self.local_tz).date().isoformat()} ({format_duration_hm(prior.duration_seconds or 0.0)})"
        self._append(
            task_id,
            "interval_edited",
            {
                "interval_id": interval_id,
                "new_interval_id": str(uuid4()),
                "start_utc": to_utc_z(synthetic_start),
                "stop_utc": to_utc_z(synthetic_stop),
                "entry_mode": "duration",
                "work_date_local": work_date_local.isoformat(),
                "duration_seconds": duration_seconds,
                "prior_interval_label": prior_label,
                "reason": reason.strip(),
            },
        )

    def delete_interval(self, task_id: str, interval_id: str, reason: str) -> None:
        if not reason.strip():
            raise ValueError("Reason is required")
        task = self.state.tasks.get(task_id)
        if not task or interval_id not in task.intervals:
            raise ValueError("Interval not found")
        interval = task.intervals[interval_id]
        checkpoint_utc = self.find_last_export_checkpoint_utc()
        if checkpoint_utc and interval.start_utc <= checkpoint_utc:
            raise ValueError(self._checkpoint_reject_message())
        interval_label = (
            f"{interval.start_utc.astimezone(self.local_tz).strftime('%Y-%m-%d %I:%M %p')} "
            f"to {interval.stop_utc.astimezone(self.local_tz).strftime('%Y-%m-%d %I:%M %p')}"
        )
        self._create_risky_operation_backup("before manual interval delete")
        self._append(
            task_id,
            "interval_deleted",
            {"interval_id": interval_id, "interval_label": interval_label, "reason": reason.strip()},
        )

    def add_manual_duration(self, task_id: str, work_date_local: date, duration_seconds: float, reason: str) -> None:
        if not reason.strip():
            raise ValueError("Reason is required")
        self._validate_duration_against_checkpoint(work_date_local)
        synthetic_start = combine_local_date_time(work_date_local, time(hour=12), self.local_tz).astimezone(timezone.utc)
        synthetic_stop = synthetic_start + timedelta(seconds=duration_seconds)
        self._append(
            task_id,
            "manual_duration_added",
            {
                "interval_id": str(uuid4()),
                "work_date_local": work_date_local.isoformat(),
                "duration_seconds": duration_seconds,
                "entry_mode": "duration",
                "start_utc": to_utc_z(synthetic_start),
                "stop_utc": to_utc_z(synthetic_stop),
                "reason": reason.strip(),
            },
        )

    def correct_running_interval_stop(self, task_id: str, corrected_stop_local: datetime, reason: str) -> None:
        if not reason.strip():
            raise ValueError("Reason is required")
        task = self.state.tasks.get(task_id)
        if not task or not task.is_running or not task.currently_open_interval_start_utc:
            raise ValueError("Task is not currently running")
        corrected_stop_utc = corrected_stop_local.astimezone(timezone.utc)
        if corrected_stop_utc <= task.currently_open_interval_start_utc:
            raise ValueError("Corrected stop must be after the running start")
        checkpoint_utc = self.find_last_export_checkpoint_utc()
        if checkpoint_utc and task.currently_open_interval_start_utc <= checkpoint_utc:
            raise ValueError(self._checkpoint_reject_message())
        if checkpoint_utc and corrected_stop_utc <= checkpoint_utc:
            raise ValueError(self._checkpoint_reject_message())
        self._create_risky_operation_backup("before missed stop correction")
        self._append(
            task_id,
            "missed_stop_corrected",
            {
                "interval_id": str(uuid4()),
                "original_open_start_utc": to_utc_z(task.currently_open_interval_start_utc),
                "corrected_stop_utc": to_utc_z(corrected_stop_utc),
                "reason": reason.strip(),
            },
        )

    def get_task_timeline(self, task_id: str, include_before_reset: bool = False, now_utc: datetime | None = None) -> list[dict[str, str]]:
        task = self.state.tasks[task_id]
        check_now = now_utc or utc_now()
        intervals = self._all_intervals(task, check_now) if include_before_reset else self._effective_intervals(task, check_now)
        intervals = sorted(intervals, key=lambda i: (i.start_utc, i.stop_utc, i.interval_id))
        return [format_timeline_row(interval, self.local_tz) for interval in intervals]

    def export_report(self, target: Path, reset_after: bool) -> None:
        self._create_risky_operation_backup("before export")
        now_utc = utc_now()
        active_checkpoint = self.find_active_export_checkpoint()
        window_start_utc = parse_utc_z(active_checkpoint["timestamp_utc"]) if active_checkpoint else None
        window_events = self.events_in_window(window_start_utc, now_utc)
        per_task = self.compute_global_export_task_totals(window_start_utc, now_utc)
        self._apply_submission_flags(per_task, window_start_utc, now_utc)
        weekly_ranges = self.collect_week_ranges(per_task)
        history_lines = self.build_human_audit_lines(window_events, window_end_utc=now_utc)
        tag_daily, tag_weekly = self.compute_tag_totals(window_start_utc, now_utc)
        content = build_export_text(
            generated_at_utc=now_utc,
            local_timezone=self.local_tz_name,
            window_start_utc=window_start_utc,
            window_end_utc=now_utc,
            reset_after=reset_after,
            weekly_headers=weekly_ranges,
            weekly_summary_rows=self.build_epicor_weekly_summary_rows(per_task, weekly_ranges),
            per_task_rows=per_task,
            history_lines=history_lines,
            source_segments=self.storage.source_segments(),
            tag_daily=tag_daily,
            tag_weekly=tag_weekly,
        )
        write_export_file(target, content)
        self._append(
            "__app__",
            "export_checkpoint",
            {
                "path": str(target),
                "generated_at_utc": to_utc_z(now_utc),
                "window_start_utc": to_utc_z(window_start_utc) if window_start_utc else None,
                "window_end_utc": to_utc_z(now_utc),
                "reset_after": reset_after,
            },
        )
        if reset_after:
            self.reset_all_non_deleted_tasks()

    def reset_all_non_deleted_tasks(self) -> None:
        """Reset all non-deleted tasks by emitting reset events."""
        for task in list(self.state.tasks.values()):
            if not task.is_deleted:
                self.reset_task(task.task_id)

    def reset_selected_tasks(self, task_ids: list[str]) -> list[str]:
        normalized = self._normalize_selected_task_ids(task_ids)
        expanded = self._expand_selected_task_ids(normalized)
        affected: list[str] = []
        for task_id in sorted(expanded):
            task = self.state.tasks.get(task_id)
            if task and not task.is_deleted:
                self.reset_task(task_id)
                affected.append(task_id)
        return affected

    def delete_selected_tasks(self, task_ids: list[str]) -> list[str]:
        normalized = self._normalize_selected_task_ids(task_ids)
        expanded = self._expand_selected_task_ids(normalized)
        affected = [task_id for task_id in sorted(expanded) if (self.state.tasks.get(task_id) and not self.state.tasks[task_id].is_deleted)]
        for task_id in affected:
            self.delete_task(task_id)
        return affected

    def compute_totals(self, now_utc: datetime | None = None) -> tuple[float, float, list[dict[str, Any]]]:
        check_now = now_utc or utc_now()
        local_now = check_now.astimezone(self.local_tz)
        day_ref = local_now
        overall_today = 0.0
        overall_week = 0.0
        rows: list[dict[str, Any]] = []
        for task in self.state.tasks.values():
            if task.is_deleted:
                continue
            intervals = self._effective_intervals(task, check_now)
            today_seconds = sum(interval_seconds_in_local_day(i.start_utc, i.stop_utc, self.local_tz, day_ref) for i in intervals)
            week_seconds = sum(interval_seconds_in_local_week(i.start_utc, i.stop_utc, self.local_tz, local_now) for i in intervals)
            overall_today += today_seconds
            overall_week += week_seconds
            rows.append(
                {
                    "task_id": task.task_id,
                    "name": task.name,
                    "notes": task.notes,
                    "state": "running" if task.is_running else "stopped",
                    "today_seconds": today_seconds,
                    "week_seconds": week_seconds,
                }
            )
        return overall_today, overall_week, rows

    def task_elapsed(self, task: TaskState, now_utc: datetime | None = None) -> float:
        check_now = now_utc or utc_now()
        return sum((i.stop_utc - i.start_utc).total_seconds() for i in self._effective_intervals(task, check_now))

    def task_own_elapsed(self, task_id: str, now_utc: datetime | None = None) -> float:
        task = self.state.tasks.get(task_id)
        if not task or task.is_deleted:
            return 0.0
        return self.task_elapsed(task, now_utc)

    def task_tree_elapsed(self, parent_task_id: str, now_utc: datetime | None = None) -> float:
        total = self.task_own_elapsed(parent_task_id, now_utc)
        for child in self.child_tasks(parent_task_id, include_deleted=False):
            total += self.task_tree_elapsed(child.task_id, now_utc)
        return total

    def build_history_lines(self) -> list[str]:
        output: list[str] = []
        for item in sorted(self.events, key=lambda ev: ev["timestamp_utc"]):
            output.append(
                f"- {item['timestamp_utc']} [{item['event_type']}] task={item['task_id']} payload={json.dumps(item['payload'], ensure_ascii=False)}"
            )
        return output

    def find_last_export_checkpoint_utc(self) -> datetime | None:
        active = self.find_active_export_checkpoint()
        if active:
            return parse_utc_z(active["timestamp_utc"])
        return None

    def find_active_export_checkpoint(self) -> dict[str, Any] | None:
        checkpoints: list[dict[str, Any]] = []
        voided_event_ids: set[str] = set()
        for event in sorted(self.events, key=lambda ev: ev["timestamp_utc"]):
            if event["task_id"] != "__app__":
                continue
            if event["event_type"] == "export_checkpoint":
                checkpoints.append(event)
            elif event["event_type"] == "export_checkpoint_voided":
                payload = event.get("payload", {})
                if payload.get("voided_checkpoint_event_id"):
                    voided_event_ids.add(payload["voided_checkpoint_event_id"])
        for checkpoint in reversed(checkpoints):
            if checkpoint["event_id"] in voided_event_ids:
                continue
            return checkpoint
        return None

    def void_last_export_checkpoint(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("Reason is required")
        active = self.find_active_export_checkpoint()
        if not active:
            raise ValueError("No active export checkpoint to reopen")
        self._create_risky_operation_backup("before checkpoint reopen")
        self._append(
            "__app__",
            "export_checkpoint_voided",
            {
                "voided_checkpoint_event_id": active["event_id"],
                "voided_checkpoint_timestamp_utc": active["timestamp_utc"],
                "reason": reason.strip(),
                "previous_checkpoint_timestamp_utc": active.get("payload", {}).get("window_start_utc"),
            },
        )

    def events_in_window(self, window_start_utc: datetime | None, window_end_utc: datetime) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for event in sorted(self.events, key=lambda ev: ev["timestamp_utc"]):
            event_ts = parse_utc_z(event["timestamp_utc"])
            if event_ts > window_end_utc:
                continue
            if window_start_utc and event_ts <= window_start_utc:
                continue
            output.append(event)
        return output

    def events_in_window_for_tasks(
        self,
        task_ids: set[str],
        window_start_utc: datetime | None,
        window_end_utc: datetime,
        include_related_app_events: bool = True,
        related_submission_id: str | None = None,
    ) -> list[dict[str, Any]]:
        selected_events: list[dict[str, Any]] = []
        for event in self.events_in_window(window_start_utc, window_end_utc):
            task_id = event["task_id"]
            if task_id in task_ids:
                selected_events.append(event)
                continue
            if not include_related_app_events or task_id != "__app__":
                continue
            if event["event_type"] != "time_submission_created":
                continue
            payload = event.get("payload", {})
            payload_task_ids = set(payload.get("task_ids", []))
            if payload_task_ids & task_ids:
                selected_events.append(event)
                continue
            if related_submission_id and payload.get("submission_id") == related_submission_id:
                selected_events.append(event)
        return selected_events

    def compute_windowed_task_totals(self, window_start_utc: datetime | None, window_end_utc: datetime) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for task in self.state.tasks.values():
            if task.is_deleted:
                continue
            clipped_intervals = self._windowed_intervals(task, window_start_utc, window_end_utc)
            day_totals = self._compute_daily_totals(clipped_intervals)
            week_totals = self._compute_weekly_totals(clipped_intervals)
            overall_seconds = sum((stop - start).total_seconds() for start, stop in clipped_intervals)
            rows.append(
                {
                    "task_id": task.task_id,
                    "name": task.name,
                    "notes": task.notes,
                    "daily_totals": sorted(day_totals.items()),
                    "weekly_totals": sorted(week_totals.items()),
                    "overall_seconds": overall_seconds,
                }
            )
        rows.sort(key=lambda row: (row["name"].strip().casefold(), row["task_id"]))
        return rows

    def compute_global_export_task_totals(self, window_start_utc: datetime | None, window_end_utc: datetime) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for task in self.state.tasks.values():
            clipped_intervals = self._windowed_intervals(task, window_start_utc, window_end_utc)
            day_totals = self._compute_daily_totals(clipped_intervals)
            week_totals = self._compute_weekly_totals(clipped_intervals)
            overall_seconds = sum((stop - start).total_seconds() for start, stop in clipped_intervals)
            if overall_seconds <= 0:
                continue
            by_id[task.task_id] = {
                "task_id": task.task_id,
                "name": task.name,
                "notes": task.notes,
                "daily_totals": sorted(day_totals.items()),
                "weekly_totals": sorted(week_totals.items()),
                "overall_seconds": overall_seconds,
                "status_notes": ["task later deleted"] if task.is_deleted else [],
            }

        for event in self.events:
            if event["task_id"] != "__app__" or event["event_type"] != "time_submission_created":
                continue
            payload = event.get("payload", {})
            marker_end = parse_utc_z(payload.get("window_end_utc", event["timestamp_utc"]))
            for snapshot in payload.get("task_snapshots", []):
                task_id = snapshot.get("task_id")
                if not task_id:
                    continue
                task = self.state.tasks.get(task_id)
                row = by_id.get(task_id)
                if row is None:
                    row = {
                        "task_id": task_id,
                        "name": snapshot.get("task_name", task.name if task else task_id),
                        "notes": snapshot.get("notes", task.notes if task else ""),
                        "daily_totals": [],
                        "weekly_totals": [],
                        "overall_seconds": 0.0,
                        "status_notes": [],
                    }
                    by_id[task_id] = row
                row["status_notes"].append("already entered through selected export")
                if task and task.is_deleted:
                    row["status_notes"].append("task later deleted")
                if task and task.last_reset_utc and task.last_reset_utc >= marker_end:
                    row["status_notes"].append("task later reset")
                daily = payload.get("submitted_daily_totals_by_task", {}).get(task_id, {})
                weekly = payload.get("submitted_weekly_totals_by_task", {}).get(task_id, {})
                overall = float(payload.get("submitted_overall_totals_by_task", {}).get(task_id, 0.0))
                if daily:
                    merged = dict(row["daily_totals"])
                    for day, seconds in daily.items():
                        merged[day] = merged.get(day, 0.0) + float(seconds)
                    row["daily_totals"] = sorted(merged.items())
                if weekly:
                    merged_w = dict(row["weekly_totals"])
                    for week, seconds in weekly.items():
                        merged_w[week] = merged_w.get(week, 0.0) + float(seconds)
                    row["weekly_totals"] = sorted(merged_w.items())
                row["overall_seconds"] += overall
        output = [row for row in by_id.values() if row["overall_seconds"] > 0]
        output = self._aggregate_parent_rows(output)
        for row in output:
            row["status_notes"] = sorted(set(row.get("status_notes", [])))
        output.sort(key=lambda row: (row["name"].strip().casefold(), row["task_id"]))
        return output

    def _expand_selected_task_ids(self, task_ids: list[str]) -> set[str]:
        selected = set(task_ids)
        expanded = set(selected)
        for task_id in list(selected):
            task = self.state.tasks.get(task_id)
            if task:
                expanded.update(child.task_id for child in self.descendant_tasks(task_id, include_deleted=True))
        return expanded

    def _normalize_selected_task_ids(self, task_ids: list[str]) -> list[str]:
        selected = list(dict.fromkeys(task_ids))
        selected_set = set(selected)
        normalized: list[str] = []
        for task_id in selected:
            task = self.state.tasks.get(task_id)
            if task and task.parent_task_id and task.parent_task_id in selected_set:
                continue
            normalized.append(task_id)
        return normalized

    def _aggregate_parent_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        row_by_id = {r["task_id"]: r for r in rows}
        out = []
        for row in rows:
            task = self.state.tasks.get(row["task_id"])
            if task and task.parent_task_id is not None and task.parent_task_id in row_by_id:
                continue
            direct_children = [
                r
                for r in rows
                if (self.state.tasks.get(r["task_id"]) and self.state.tasks[r["task_id"]].parent_task_id == row["task_id"])
            ]
            daily = dict(row["daily_totals"])
            weekly = dict(row["weekly_totals"])
            total = row["overall_seconds"]
            breakdown = [("Parent/general", row["overall_seconds"])]
            for child_row in direct_children:
                child_breakdown = child_row.get("breakdown") or [("Parent/general", child_row["overall_seconds"])]
                for label, seconds in child_breakdown:
                    if label == "Parent/general":
                        break
                total += child_row["overall_seconds"]
                breakdown.append((f"{child_row['name']} total", child_row["overall_seconds"]))
                for label, seconds in child_breakdown:
                    if label == "Parent/general":
                        breakdown.append((f"  {child_row['name']}/general", seconds))
                    else:
                        breakdown.append((f"  {label}", seconds))
                for k, v in child_row["daily_totals"]:
                    daily[k] = daily.get(k, 0) + v
                for k, v in child_row["weekly_totals"]:
                    weekly[k] = weekly.get(k, 0) + v
            merged = dict(row)
            merged["daily_totals"] = sorted(daily.items())
            merged["weekly_totals"] = sorted(weekly.items())
            merged["overall_seconds"] = total
            merged["breakdown"] = breakdown
            out.append(merged)
        return out

    def compute_selected_task_totals(
        self, task_ids: list[str], window_start_utc: datetime | None, window_end_utc: datetime
    ) -> list[dict[str, Any]]:
        wanted = self._expand_selected_task_ids(task_ids)
        rows = self.compute_windowed_task_totals(window_start_utc, window_end_utc)
        filtered = [row for row in rows if row["task_id"] in wanted]
        return self._aggregate_parent_rows(filtered)

    def collect_week_ranges(self, per_task_rows: list[dict[str, Any]]) -> list[str]:
        week_ranges: set[str] = set()
        for row in per_task_rows:
            week_ranges.update(week_range for week_range, _ in row["weekly_totals"])
        return sorted(week_ranges)

    def build_epicor_weekly_summary_rows(
        self, per_task_rows: list[dict[str, Any]], weekly_ranges: list[str]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in per_task_rows:
            week_map = dict(row["weekly_totals"])
            week_flags = row.get("weekly_submission_flags", {})
            week_values: list[str] = []
            for week_range in weekly_ranges:
                marker = week_flags.get(week_range, {}).get("marker", "")
                week_values.append(marker)
            rows.append(
                {
                    "task_id": row["task_id"],
                    "name": row["name"],
                    "notes": row["notes"],
                    "weeks": [week_map.get(week_range, 0.0) for week_range in weekly_ranges],
                    "week_markers": week_values,
                }
            )
        return rows

    def list_time_submissions(self) -> list[TimeSubmission]:
        output: list[TimeSubmission] = []
        for event in sorted(self.events, key=lambda ev: ev["timestamp_utc"]):
            if event["task_id"] != "__app__" or event["event_type"] != "time_submission_created":
                continue
            payload = event.get("payload", {})
            output.append(
                TimeSubmission(
                    submission_id=payload.get("submission_id", event["event_id"]),
                    submitted_at_utc=parse_utc_z(payload.get("submitted_at_utc", event["timestamp_utc"])),
                    window_start_utc=parse_utc_z(payload["window_start_utc"]) if payload.get("window_start_utc") else None,
                    window_end_utc=parse_utc_z(payload.get("window_end_utc", event["timestamp_utc"])),
                    task_ids=set(payload.get("task_ids", [])),
                    reason=payload.get("reason", ""),
                    export_path=payload.get("export_path"),
                )
            )
        return output

    def create_time_submission_marker(
        self, task_ids: list[str], window_start_utc: datetime | None, window_end_utc: datetime, reason: str, export_path: Path | None
    ) -> str:
        if window_start_utc and window_end_utc <= window_start_utc:
            raise ValueError("Window end must be after window start")
        selected = self._normalize_selected_task_ids(task_ids)
        expanded = list(dict.fromkeys(self._expand_selected_task_ids(selected)))
        if not selected:
            raise ValueError("At least one task must be selected")
        valid = [tid for tid in expanded if tid in self.state.tasks]
        if len(valid) != len(expanded):
            raise ValueError("One or more selected task IDs do not exist")
        if not any(not self.state.tasks[tid].is_deleted for tid in valid):
            raise ValueError("At least one selected task must be non-deleted")
        submission_id = str(uuid4())
        snapshots = [{"task_id": tid, "task_name": self.state.tasks[tid].name, "notes": self.state.tasks[tid].notes, "tags": sorted(self.state.tasks[tid].tags)} for tid in valid]
        per_task = self.compute_selected_task_totals(valid, window_start_utc, window_end_utc)
        included_by_parent = {
            parent_id: sorted(child.task_id for child in self.child_tasks(parent_id, include_deleted=True) if child.task_id in valid)
            for parent_id in selected
            if self.state.tasks.get(parent_id) and self.state.tasks[parent_id].parent_task_id is None
        }
        self._append("__app__", "time_submission_created", {"submission_id": submission_id, "submitted_at_utc": to_utc_z(utc_now()), "window_start_utc": to_utc_z(window_start_utc) if window_start_utc else None, "window_end_utc": to_utc_z(window_end_utc), "selected_task_ids": selected, "task_ids": valid, "included_subtask_ids_by_parent": included_by_parent, "reason": reason.strip(), "export_path": str(export_path) if export_path else None, "task_snapshots": snapshots, "submitted_daily_totals_by_task": {row["task_id"]: {day: seconds for day, seconds in row["daily_totals"]} for row in per_task}, "submitted_weekly_totals_by_task": {row["task_id"]: {week: seconds for week, seconds in row["weekly_totals"]} for row in per_task}, "submitted_overall_totals_by_task": {row["task_id"]: row["overall_seconds"] for row in per_task}})
        return submission_id

    def export_selected_tasks_report(
        self, target: Path, task_ids: list[str], window_start_utc: datetime | None, window_end_utc: datetime, mark_submitted: bool, reason: str
    ) -> None:
        self._create_risky_operation_backup("before selected export")
        normalized_task_ids = self._normalize_selected_task_ids(task_ids)
        per_task = self.compute_selected_task_totals(normalized_task_ids, window_start_utc, window_end_utc)
        self._apply_submission_flags(per_task, window_start_utc, window_end_utc)
        weekly_ranges = self.collect_week_ranges(per_task)
        selected_ids = self._expand_selected_task_ids(normalized_task_ids)
        selected_window_events = self.events_in_window_for_tasks(
            selected_ids,
            window_start_utc,
            window_end_utc,
            include_related_app_events=True,
        )
        content = build_selected_tasks_export_text(
            generated_at_utc=utc_now(),
            local_timezone=self.local_tz_name,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            weekly_headers=weekly_ranges,
            weekly_summary_rows=self.build_epicor_weekly_summary_rows(per_task, weekly_ranges),
            per_task_rows=per_task,
            history_lines=self.build_human_audit_lines(selected_window_events, window_end_utc=window_end_utc),
            source_segments=self.storage.source_segments(),
            mark_submitted=mark_submitted,
            reason=reason,
        )
        write_export_file(target, content)
        if mark_submitted:
            self.create_time_submission_marker(normalized_task_ids, window_start_utc, window_end_utc, reason, target)

    def find_submitted_seconds_for_task_window(
        self, task_id: str, bucket_start_utc: datetime, bucket_end_utc: datetime
    ) -> dict[str, Any]:
        total = max(0.0, (bucket_end_utc - bucket_start_utc).total_seconds())
        submitted = 0.0
        for marker in self.list_time_submissions():
            if task_id not in marker.task_ids:
                continue
            marker_start = marker.window_start_utc or datetime.min.replace(tzinfo=timezone.utc)
            overlap_start = max(bucket_start_utc, marker_start)
            overlap_end = min(bucket_end_utc, marker.window_end_utc)
            if overlap_end > overlap_start:
                submitted = max(submitted, (overlap_end - overlap_start).total_seconds())
        return {"already_submitted_seconds": submitted, "total_seconds": total, "is_fully_submitted": submitted >= total and total > 0, "is_partially_submitted": 0 < submitted < total}

    def find_submission_overlaps(
        self, task_ids: list[str], window_start_utc: datetime | None, window_end_utc: datetime
    ) -> list[dict[str, Any]]:
        selected = set(task_ids)
        overlaps: list[dict[str, Any]] = []
        for marker in self.list_time_submissions():
            shared = marker.task_ids & selected
            if not shared:
                continue
            marker_start = marker.window_start_utc or datetime.min.replace(tzinfo=timezone.utc)
            overlap_start = max(marker_start, window_start_utc) if window_start_utc else marker_start
            overlap_end = min(marker.window_end_utc, window_end_utc)
            if overlap_end <= overlap_start:
                continue
            for task_id in sorted(shared):
                task = self.state.tasks.get(task_id)
                overlaps.append(
                    {
                        "task_id": task_id,
                        "task_name": task.name if task else task_id,
                        "existing_submission_id": marker.submission_id,
                        "overlap_start_utc": overlap_start,
                        "overlap_end_utc": overlap_end,
                        "existing_reason": marker.reason,
                    }
                )
        return overlaps

    def _apply_submission_flags(self, per_task_rows: list[dict[str, Any]], window_start_utc: datetime | None, window_end_utc: datetime) -> None:
        for row in per_task_rows:
            week_flags: dict[str, dict[str, Any]] = {}
            for week_range, seconds in row["weekly_totals"]:
                start_s, end_s = week_range.split(" to ")
                week_start_local = datetime.combine(date.fromisoformat(start_s), time.min, self.local_tz)
                week_end_local = datetime.combine(date.fromisoformat(end_s), time.max, self.local_tz)
                info = self.find_submitted_seconds_for_task_window(row["task_id"], week_start_local.astimezone(timezone.utc), week_end_local.astimezone(timezone.utc))
                marker = "*" if info["already_submitted_seconds"] > 0 else ""
                if info["is_partially_submitted"]:
                    marker = "~"
                week_flags[week_range] = {**info, "marker": marker, "week_seconds": seconds}
            row["weekly_submission_flags"] = week_flags

    def build_human_audit_lines(self, window_events: list[dict[str, Any]], window_end_utc: datetime) -> list[str]:
        events_until_end = self.events_in_window(window_start_utc=None, window_end_utc=window_end_utc)
        name_by_task_id: dict[str, str] = {}
        notes_by_task_id: dict[str, str] = {}
        running_starts: dict[str, datetime] = {}
        formatted_by_event_id: dict[str, str] = {}
        for event in events_until_end:
            task_id = event["task_id"]
            event_type = event["event_type"]
            payload = event["payload"]
            event_ts = parse_utc_z(event["timestamp_utc"])
            local_stamp = event_ts.astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
            task_name = name_by_task_id.get(task_id, task_id)

            if event_type == "task_created":
                task_name = payload.get("name", task_name)
                name_by_task_id[task_id] = task_name
                notes_by_task_id[task_id] = payload.get("notes", "")
                line = f'{local_stamp}  Created task "{task_name}"'
                if notes_by_task_id[task_id]:
                    line += f" (Notes: {notes_by_task_id[task_id]})"
            elif event_type == "task_updated":
                old_name = task_name
                new_name = payload.get("name", old_name)
                new_notes = payload.get("notes", notes_by_task_id.get(task_id, ""))
                name_by_task_id[task_id] = new_name
                notes_by_task_id[task_id] = new_notes
                line = f'{local_stamp}  Updated task "{old_name}"'
                if old_name != new_name:
                    line += f' to "{new_name}"'
                if new_notes:
                    line += f" (Notes: {new_notes})"
            elif event_type == "started":
                running_starts[task_id] = event_ts
                line = f'{local_stamp}  Started "{task_name}"'
            elif event_type == "stopped":
                line = f'{local_stamp}  Stopped "{task_name}"'
                start_ts = running_starts.pop(task_id, None)
                if start_ts and event_ts > start_ts:
                    duration = format_duration_hm((event_ts - start_ts).total_seconds())
                    line += f" (interval {duration})"
            elif event_type == "reset":
                line = f'{local_stamp}  Reset task "{task_name}"'
            elif event_type == "manual_interval_added":
                start_local = parse_utc_z(payload["start_utc"]).astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
                stop_local = parse_utc_z(payload["stop_utc"]).astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
                line = f'{local_stamp}  Added manual interval to "{task_name}": {start_local} to {stop_local}'
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            elif event_type == "interval_edited":
                start_local = parse_utc_z(payload["start_utc"]).astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
                stop_local = parse_utc_z(payload["stop_utc"]).astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
                prior_label = payload.get("prior_interval_label") or payload.get("interval_id", "unknown")
                line = (
                    f'{local_stamp}  Edited interval for "{task_name}": {start_local} to {stop_local} '
                    f"replaced prior interval {prior_label}"
                )
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            elif event_type == "interval_deleted":
                line = (
                    f'{local_stamp}  Deleted interval from "{task_name}": '
                    f'{payload.get("interval_label", payload.get("interval_id", "unknown"))}'
                )
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            elif event_type == "manual_duration_added":
                duration_label = format_duration_hm(payload.get("duration_seconds", 0.0))
                line = (
                    f'{local_stamp}  Added manual duration to "{task_name}": {duration_label} '
                    f'on {payload.get("work_date_local", "unknown date")}'
                )
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            elif event_type == "task_deleted":
                line = f'{local_stamp}  Deleted task "{task_name}"'
            elif event_type == "export_checkpoint":
                line = f"{local_stamp}  Export checkpoint created"
            elif event_type == "export_checkpoint_voided":
                checkpoint_local = parse_utc_z(payload["voided_checkpoint_timestamp_utc"]).astimezone(self.local_tz).strftime(
                    "%Y-%m-%d %I:%M %p"
                )
                line = f"{local_stamp}  Reopened export checkpoint from {checkpoint_local}"
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            elif event_type == "missed_stop_corrected":
                started_local = parse_utc_z(payload["original_open_start_utc"]).astimezone(self.local_tz).strftime(
                    "%Y-%m-%d %I:%M %p"
                )
                stop_local = parse_utc_z(payload["corrected_stop_utc"]).astimezone(self.local_tz).strftime("%Y-%m-%d %I:%M %p")
                line = f'{local_stamp}  Corrected missed stop for "{task_name}": started {started_local}, corrected stop {stop_local}'
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            elif event_type == "time_submission_created":
                task_names = []
                for submitted_task_id in payload.get("task_ids", []):
                    task_names.append(name_by_task_id.get(submitted_task_id, submitted_task_id))
                task_list = ", ".join(task_names)
                start_label = payload.get("window_start_utc", "beginning")
                end_label = payload.get("window_end_utc", "unknown")
                line = (
                    f"{local_stamp}  Marked selected task time as entered: {task_list}; "
                    f"window {start_label} to {end_label}"
                )
                if payload.get("reason"):
                    line += f" (Reason: {payload['reason']})"
            else:
                line = f'{local_stamp}  {event_type} for "{task_name}"'
            formatted_by_event_id[event["event_id"]] = line
        return [formatted_by_event_id[event["event_id"]] for event in window_events if event["event_id"] in formatted_by_event_id]

    def create_backup_now(self, reason: str = "manual backup") -> Path:
        return self.backups.create_backup("son", reason)

    def list_managed_backups(self) -> list[Any]:
        return self.backups.list_backups()

    def restore_from_backup(self, backup_path: Path) -> None:
        # Restore always forces a safety backup regardless of user setting.
        self.backups.restore_backup(backup_path)
        self.events = self.storage.iter_all_events()
        self._rebuild_state(self.events)
        self._save_snapshot()

    def rebuild_snapshot_from_journal(self) -> None:
        self._create_risky_operation_backup("before rebuild snapshot from journal")
        self.events = self.storage.iter_all_events()
        self._rebuild_state(self.events)
        self._save_snapshot()

    def load_backup_settings(self) -> BackupSettings:
        return self.backups.load_settings()

    def save_backup_settings(self, settings: BackupSettings) -> None:
        self.backups.save_settings(settings)

    def apply_backup_retention(self) -> None:
        self.backups.apply_retention()

    def _create_risky_operation_backup(self, reason: str) -> None:
        if self.load_backup_settings().auto_backup_before_risky_operations:
            self.backups.create_safety_backup(reason)

    def _maybe_create_app_start_backup(self) -> None:
        settings = self.load_backup_settings()
        if not settings.auto_backup_on_app_start:
            return
        if not self.backups.should_create_automatic_backup("automatic backup on app start"):
            return
        self.backups.create_backup("son", "automatic backup on app start")

    def _checkpoint_reject_message(self) -> str:
        return (
            "This manual time is before the active export checkpoint and will not be included in the next export. "
            "Reopen or void the last checkpoint before adding this correction."
        )

    def _validate_interval_against_checkpoint(self, start_local: datetime, stop_local: datetime) -> None:
        checkpoint_utc = self.find_last_export_checkpoint_utc()
        if not checkpoint_utc:
            return
        start_utc = start_local.astimezone(timezone.utc)
        stop_utc = stop_local.astimezone(timezone.utc)
        if stop_utc <= checkpoint_utc or start_utc <= checkpoint_utc:
            raise ValueError(self._checkpoint_reject_message())

    def _validate_duration_against_checkpoint(self, work_date_local: date) -> None:
        checkpoint_utc = self.find_last_export_checkpoint_utc()
        if not checkpoint_utc:
            return
        checkpoint_local_date = checkpoint_utc.astimezone(self.local_tz).date()
        if work_date_local <= checkpoint_local_date:
            raise ValueError(self._checkpoint_reject_message())

    def _windowed_intervals(
        self, task: TaskState, window_start_utc: datetime | None, window_end_utc: datetime
    ) -> list[tuple[datetime, datetime]]:
        output: list[tuple[datetime, datetime]] = []
        for interval in self._effective_intervals(task, window_end_utc):
            start = interval.start_utc
            stop = interval.stop_utc
            if window_start_utc and stop <= window_start_utc:
                continue
            if start > window_end_utc:
                continue
            clipped_start = max(start, window_start_utc) if window_start_utc else start
            clipped_stop = min(stop, window_end_utc)
            if clipped_stop > clipped_start:
                output.append((clipped_start, clipped_stop))
        return output

    def _compute_daily_totals(self, intervals: list[tuple[datetime, datetime]]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for start_utc, stop_utc in intervals:
            start_local = start_utc.astimezone(self.local_tz)
            stop_local = stop_utc.astimezone(self.local_tz)
            day_cursor = start_local.date()
            last_day = stop_local.date()
            while day_cursor <= last_day:
                day_ref = datetime.combine(day_cursor, time(hour=12), self.local_tz)
                seconds = interval_seconds_in_local_day(start_utc, stop_utc, self.local_tz, day_ref)
                if seconds > 0:
                    key = day_cursor.isoformat()
                    totals[key] = totals.get(key, 0.0) + seconds
                day_cursor += timedelta(days=1)
        return totals

    def _compute_weekly_totals(self, intervals: list[tuple[datetime, datetime]]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for start_utc, stop_utc in intervals:
            start_local = start_utc.astimezone(self.local_tz)
            stop_local = stop_utc.astimezone(self.local_tz)
            week_cursor = sunday_week_start(start_local)
            while week_cursor <= stop_local:
                week_range = self._week_range_label(week_cursor.date())
                seconds = interval_seconds_in_local_week(start_utc, stop_utc, self.local_tz, week_cursor)
                if seconds > 0:
                    totals[week_range] = totals.get(week_range, 0.0) + seconds
                week_cursor += timedelta(days=7)
        return totals

    @staticmethod
    def _week_range_label(week_start: date) -> str:
        week_end = week_start + timedelta(days=6)
        return f"{week_start.isoformat()} to {week_end.isoformat()}"


    def compute_tag_totals(
        self, window_start_utc: datetime | None, window_end_utc: datetime
    ) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, dict[str, dict[str, Any]]]]:
        daily: dict[str, dict[str, dict[str, Any]]] = {}
        weekly: dict[str, dict[str, dict[str, Any]]] = {}
        for task in self.state.tasks.values():
            intervals = self._windowed_intervals(task, window_start_utc, window_end_utc)
            if not intervals:
                continue
            effective_tags = set(task.tags)
            for ancestor in self.ancestor_tasks(task.task_id):
                effective_tags |= ancestor.tags
            tags = tuple(sorted(effective_tags)) or ("untagged",)
            task_name = task.name.strip() or task.task_id
            for start_utc, stop_utc in intervals:
                start_local = start_utc.astimezone(self.local_tz)
                stop_local = stop_utc.astimezone(self.local_tz)
                day_cursor = start_local.date()
                last_day = stop_local.date()
                while day_cursor <= last_day:
                    day_ref = datetime.combine(day_cursor, time(hour=12), self.local_tz)
                    seconds = interval_seconds_in_local_day(start_utc, stop_utc, self.local_tz, day_ref)
                    if seconds > 0:
                        day_key = day_cursor.isoformat()
                        day_bucket = daily.setdefault(day_key, {})
                        for tag in tags:
                            entry = day_bucket.setdefault(tag, {"seconds": 0.0, "tasks": set()})
                            entry["seconds"] += seconds
                            entry["tasks"].add(task_name)
                    day_cursor += timedelta(days=1)

                week_cursor = sunday_week_start(start_local)
                while week_cursor <= stop_local:
                    week_label = self._week_range_label(week_cursor.date())
                    seconds = interval_seconds_in_local_week(start_utc, stop_utc, self.local_tz, week_cursor)
                    if seconds > 0:
                        week_bucket = weekly.setdefault(week_label, {})
                        for tag in tags:
                            entry = week_bucket.setdefault(tag, {"seconds": 0.0, "tasks": set()})
                            entry["seconds"] += seconds
                            entry["tasks"].add(task_name)
                    week_cursor += timedelta(days=7)
        return daily, weekly

    def snapshot_dict(self) -> dict[str, Any]:
        tasks_payload: dict[str, Any] = {}
        for task_id, task in self.state.tasks.items():
            tasks_payload[task_id] = {
                "task_id": task.task_id,
                "name": task.name,
                "notes": task.notes,
                "is_deleted": task.is_deleted,
                "is_running": task.is_running,
                "created_at_utc": to_utc_z(task.created_at_utc),
                "updated_at_utc": to_utc_z(task.updated_at_utc),
                "display_color": task.display_color,
                "currently_open_interval_start_utc": to_utc_z(task.currently_open_interval_start_utc)
                if task.currently_open_interval_start_utc
                else None,
                "last_reset_utc": to_utc_z(task.last_reset_utc) if task.last_reset_utc else None,
                "tags": sorted(task.tags),
                "parent_task_id": task.parent_task_id,
                "intervals": [
                    {
                        "interval_id": interval.interval_id,
                        "task_id": interval.task_id,
                        "start_utc": to_utc_z(interval.start_utc),
                        "stop_utc": to_utc_z(interval.stop_utc),
                        "source": interval.source,
                        "entry_mode": interval.entry_mode,
                        "work_date_local": interval.work_date_local,
                        "duration_seconds": interval.duration_seconds,
                        "replaced_interval_id": interval.replaced_interval_id,
                        "edit_reason": interval.edit_reason,
                        "deleted": interval.deleted,
                    }
                    for interval in task.intervals.values()
                ],
            }
        return {"tasks": tasks_payload, "running_task_id": self.state.running_task_id, "global_tags": {k:{"key":v.key,"archived":v.archived,"created_at_utc":to_utc_z(v.created_at_utc),"updated_at_utc":to_utc_z(v.updated_at_utc)} for k,v in self.state.global_tags.items()}}

    def _append(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        event = event_dict(
            timestamp_utc=to_utc_z(utc_now()),
            local_timezone=self.local_tz_name,
            task_id=task_id,
            event_type=event_type,
            payload=payload,
            event_id=str(uuid4()),
        )
        self.storage.append_event(event)
        self.events.append(event)
        self._apply_event(event)
        self._save_snapshot()

    def _save_snapshot(self) -> None:
        self.storage.save_snapshot(self.snapshot_dict())

    def _all_intervals(self, task: TaskState, now_utc: datetime) -> list[IntervalRecord]:
        intervals = [interval for interval in task.intervals.values() if not interval.deleted]
        if task.is_running and task.currently_open_interval_start_utc:
            intervals.append(
                IntervalRecord(
                    interval_id="__open__",
                    task_id=task.task_id,
                    start_utc=task.currently_open_interval_start_utc,
                    stop_utc=now_utc,
                    source="open",
                )
            )
        return intervals

    def _effective_intervals(self, task: TaskState, now_utc: datetime) -> list[IntervalRecord]:
        effective = self._all_intervals(task, now_utc)
        if task.last_reset_utc:
            effective = [interval for interval in effective if interval.stop_utc > task.last_reset_utc]
            clipped: list[IntervalRecord] = []
            for interval in effective:
                if interval.start_utc < task.last_reset_utc:
                    clipped.append(
                        IntervalRecord(
                            interval_id=interval.interval_id,
                            task_id=interval.task_id,
                            start_utc=task.last_reset_utc,
                            stop_utc=interval.stop_utc,
                            source=interval.source,
                            entry_mode=interval.entry_mode,
                            work_date_local=interval.work_date_local,
                            duration_seconds=interval.duration_seconds,
                            replaced_interval_id=interval.replaced_interval_id,
                            edit_reason=interval.edit_reason,
                            deleted=interval.deleted,
                        )
                    )
                else:
                    clipped.append(interval)
            effective = clipped
        return effective

    def _rebuild_state(self, events: list[dict[str, Any]]) -> None:
        self.state = AppState()
        for event in sorted(events, key=lambda ev: (ev["timestamp_utc"], ev.get("_read_sequence", 0))):
            self._apply_event(event)

    @staticmethod
    def _normalize_tags_for_replay(raw_tags: Any) -> set[str]:
        """Best-effort tag normalization for historical event replay."""
        if not isinstance(raw_tags, list):
            return set()
        normalized: set[str] = set()
        for raw_tag in raw_tags:
            if not isinstance(raw_tag, str):
                continue
            try:
                normalized.add(normalize_tag(raw_tag))
            except ValueError:
                continue
        return normalized

    def _apply_event(self, event: dict[str, Any]) -> None:
        try:
            task_id = event["task_id"]
            event_type = event["event_type"]
            payload = event["payload"]
            timestamp = parse_utc_z(event["timestamp_utc"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipped malformed replay event {}: {}", event.get("event_id", "<unknown>"), exc)
            return
        if task_id == "__app__":
            if event_type == "tag_created":
                try:
                    key = normalize_tag(payload["key"])
                except (KeyError, TypeError, ValueError):
                    return
                existing = self.state.global_tags.get(key)
                if not existing:
                    self.state.global_tags[key] = TagMeta(key=key, archived=False, created_at_utc=timestamp, updated_at_utc=timestamp)
            elif event_type == "tag_archived":
                try:
                    key = normalize_tag(payload["key"])
                except (KeyError, TypeError, ValueError):
                    return
                if key in self.state.global_tags: self.state.global_tags[key].archived=True; self.state.global_tags[key].updated_at_utc=timestamp
            elif event_type == "tag_unarchived":
                try:
                    key = normalize_tag(payload["key"])
                except (KeyError, TypeError, ValueError):
                    return
                if key in self.state.global_tags: self.state.global_tags[key].archived=False; self.state.global_tags[key].updated_at_utc=timestamp
            elif event_type == "tag_deleted":
                try:
                    key = normalize_tag(payload["key"])
                except (KeyError, TypeError, ValueError):
                    return
                self.state.global_tags.pop(key, None)
            elif event_type == "tag_renamed":
                try:
                    old = normalize_tag(payload["old_key"])
                    new = normalize_tag(payload["new_key"])
                except (KeyError, TypeError, ValueError):
                    return
                if old in self.state.global_tags and new not in self.state.global_tags:
                    meta=self.state.global_tags.pop(old); meta.key=new; meta.updated_at_utc=timestamp; self.state.global_tags[new]=meta
                for t in self.state.tasks.values():
                    if old in t.tags:
                        t.tags.discard(old); t.tags.add(new)
            return
        if event_type == "task_created":
            tags = self._normalize_tags_for_replay(payload.get("tags", []))
            self.state.tasks[task_id] = TaskState(
                task_id=task_id,
                name=payload.get("name", "Task"),
                notes=payload.get("notes", ""),
                is_deleted=False,
                is_running=False,
                created_at_utc=timestamp,
                updated_at_utc=timestamp,
                tags=tags,
                parent_task_id=payload.get("parent_task_id"),
            )
            for key in tags:
                if key not in self.state.global_tags:
                    self.state.global_tags[key] = TagMeta(key=key, archived=False, created_at_utc=timestamp, updated_at_utc=timestamp)
            return
        task = self.state.tasks.get(task_id)
        if not task:
            return
        task.updated_at_utc = timestamp
        if event_type == "task_updated":
            task.name = payload.get("name", task.name)
            task.notes = self._clean_notes(payload.get("notes", task.notes))
        elif event_type == "task_deleted":
            task.is_deleted = True
            task.is_running = False
            task.currently_open_interval_start_utc = None
            if self.state.running_task_id == task_id:
                self.state.running_task_id = None
        elif event_type == "started":
            task.is_running = True
            task.currently_open_interval_start_utc = timestamp
            task.display_color = "running"
            self.state.running_task_id = task_id
        elif event_type == "stopped":
            if task.is_running and task.currently_open_interval_start_utc:
                interval = IntervalRecord(
                    interval_id=payload.get("interval_id", str(uuid4())),
                    task_id=task_id,
                    start_utc=task.currently_open_interval_start_utc,
                    stop_utc=timestamp,
                    source="normal",
                )
                task.intervals[interval.interval_id] = interval
            task.is_running = False
            task.currently_open_interval_start_utc = None
            task.display_color = "neutral"
            if self.state.running_task_id == task_id:
                self.state.running_task_id = None
        elif event_type == "reset":
            task.last_reset_utc = timestamp
        elif event_type == "task_tags_updated":
            tags = self._normalize_tags_for_replay(payload.get("tags", []))
            task.tags = tags
            for key in tags:
                if key not in self.state.global_tags:
                    self.state.global_tags[key] = TagMeta(key=key, archived=False, created_at_utc=timestamp, updated_at_utc=timestamp)
        elif event_type == "task_moved":
            new_parent_task_id = payload.get("new_parent_task_id")
            if new_parent_task_id == task_id:
                return
            if new_parent_task_id is None:
                task.parent_task_id = None
                return
            new_parent = self.state.tasks.get(new_parent_task_id)
            if not new_parent or new_parent.is_deleted:
                return
            seen: set[str] = {task_id}
            cursor = new_parent
            while cursor.parent_task_id is not None:
                parent_id = cursor.parent_task_id
                if parent_id in seen:
                    return
                parent = self.state.tasks.get(parent_id)
                if not parent:
                    return
                seen.add(parent_id)
                cursor = parent
            try:
                if self.max_depth_after_move(task_id, new_parent_task_id) > 2:
                    return
            except ValueError:
                return
            task.parent_task_id = new_parent_task_id
        elif event_type == "manual_interval_added":
            try:
                interval = IntervalRecord(
                    interval_id=payload["interval_id"],
                    task_id=task_id,
                    start_utc=parse_utc_z(payload["start_utc"]),
                    stop_utc=parse_utc_z(payload["stop_utc"]),
                    source="manual",
                    entry_mode=payload.get("entry_mode", "interval"),
                    work_date_local=payload.get("work_date_local"),
                    duration_seconds=payload.get("duration_seconds"),
                    edit_reason=payload.get("reason"),
                )
                task.intervals[interval.interval_id] = interval
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipped malformed replay event {}: {}", event.get("event_id", "<unknown>"), exc)
        elif event_type == "manual_duration_added":
            try:
                interval = IntervalRecord(
                    interval_id=payload["interval_id"],
                    task_id=task_id,
                    start_utc=parse_utc_z(payload["start_utc"]),
                    stop_utc=parse_utc_z(payload["stop_utc"]),
                    source="manual_duration",
                    entry_mode="duration",
                    work_date_local=payload.get("work_date_local"),
                    duration_seconds=payload.get("duration_seconds"),
                    edit_reason=payload.get("reason"),
                )
                task.intervals[interval.interval_id] = interval
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipped malformed replay event {}: {}", event.get("event_id", "<unknown>"), exc)
        elif event_type == "interval_edited":
            try:
                prior = task.intervals.get(payload["interval_id"])
                if prior:
                    prior.deleted = True
                interval = IntervalRecord(
                    interval_id=payload["new_interval_id"],
                    task_id=task_id,
                    start_utc=parse_utc_z(payload["start_utc"]),
                    stop_utc=parse_utc_z(payload["stop_utc"]),
                    source="edit",
                    entry_mode=payload.get("entry_mode", "interval"),
                    work_date_local=payload.get("work_date_local"),
                    duration_seconds=payload.get("duration_seconds"),
                    replaced_interval_id=payload["interval_id"],
                    edit_reason=payload.get("reason"),
                )
                task.intervals[interval.interval_id] = interval
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipped malformed replay event {}: {}", event.get("event_id", "<unknown>"), exc)
        elif event_type == "interval_deleted":
            try:
                interval = task.intervals.get(payload["interval_id"])
                if interval:
                    interval.deleted = True
                    interval.edit_reason = payload.get("reason")
            except (KeyError, TypeError) as exc:
                logger.warning("Skipped malformed replay event {}: {}", event.get("event_id", "<unknown>"), exc)
        elif event_type == "missed_stop_corrected":
            try:
                original_open_start = parse_utc_z(payload["original_open_start_utc"])
                corrected_stop = parse_utc_z(payload["corrected_stop_utc"])
                if task.is_running and task.currently_open_interval_start_utc == original_open_start and corrected_stop > original_open_start:
                    interval = IntervalRecord(
                        interval_id=payload.get("interval_id", str(uuid4())),
                        task_id=task_id,
                        start_utc=original_open_start,
                        stop_utc=corrected_stop,
                        source="edit",
                        entry_mode="interval",
                        edit_reason=payload.get("reason"),
                    )
                    task.intervals[interval.interval_id] = interval
                    task.is_running = False
                    task.currently_open_interval_start_utc = None
                    task.display_color = "neutral"
                    if self.state.running_task_id == task_id:
                        self.state.running_task_id = None
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipped malformed replay event {}: {}", event.get("event_id", "<unknown>"), exc)

    @staticmethod
    def _clean_notes(notes: str) -> str:
        return notes.replace("\n", " ").strip()[:NOTES_MAX_LENGTH]


class TaskTimerApp:
    """tkinter user interface wrapper."""

    def __init__(self, root: Tk, service: TaskTimerService) -> None:
        self.root = root
        self.service = service
        self.log_path = getattr(service, "log_path", service.storage.data_dir / "logs" / "chronicle.log")
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
        logger.opt(exception=(exc_type, exc_value, exc_traceback)).error("Unhandled Tkinter callback exception")
        if self._showing_error_dialog:
            return
        self._showing_error_dialog = True
        try:
            messagebox.showerror("Chronicle Error", "Chronicle encountered an unexpected error.\nDetails were written to the log file.\n\nLog file:\n" + str(self.log_path))
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
        ttk.Button(self.reminder_banner, text="Export", command=self._on_reminder_export).pack(side="left", padx=4, pady=4)
        ttk.Button(self.reminder_banner, text="Dismiss", command=self._dismiss_month_end_reminder_today).pack(
            side="left", padx=(0, 8), pady=4
        )

        self.toolbar_frame = ttk.Frame(self.root)
        self.toolbar_frame.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Button(self.toolbar_frame, text="Add Task", command=self.add_task).pack(side="left", padx=(0, 4))
        ttk.Button(self.toolbar_frame, text="Export", command=self.export).pack(side="left", padx=4)
        ttk.Button(self.toolbar_frame, text="Mini Mode", command=self.open_mini_mode).pack(side="left", padx=4)
        self.keep_mini_open_checkbox = ttk.Checkbutton(
            self.toolbar_frame, text="Keep Mini Open", variable=self.keep_mini_open_var, command=self._on_keep_mini_open_toggle
        )
        self.keep_mini_open_checkbox.pack(side="left", padx=(0, 6))
        self.sort_alpha_checkbox = ttk.Checkbutton(
            self.toolbar_frame, text="Sort A-Z", variable=self.sort_alpha_var, command=self._on_sort_toggle
        )
        self.sort_alpha_checkbox.pack(side="left", padx=(10, 4))
        self.daily_total_label = ttk.Label(self.toolbar_frame, textvariable=self.daily_var)
        self.daily_total_label.pack(side="left", padx=(12, 4))
        self.weekly_total_label = ttk.Label(self.toolbar_frame, textvariable=self.weekly_var)
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
        file_menu.add_command(label="Create Backup Now", command=self._create_backup_now)
        file_menu.add_command(label="Backup Settings", command=self._open_backup_settings)
        file_menu.add_command(label="Open Data Folder", command=self._open_data_folder)
        file_menu.add_command(label="Open Backup Folder", command=self._open_backup_folder)
        file_menu.add_command(label="Export Selected Tasks...", command=self.export_selected_tasks)
        file_menu.add_command(label="Restore From Backup", command=self._restore_from_backup)
        file_menu.add_command(label="Rebuild Snapshot From Journal", command=self._rebuild_snapshot_from_journal)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Reopen Last Export Checkpoint", command=self._reopen_last_export_checkpoint)
        tools_menu.add_separator()
        tools_menu.add_command(label="Reset All Task Timers...", command=self._reset_all_task_timers)
        tools_menu.add_separator()
        tools_menu.add_command(label="Manage Tags", command=self._manage_tags)
        tools_menu.add_command(label="Manage Subtask Templates", command=self._manage_subtask_templates)
        tools_menu.add_command(label="Month-End Reminder Settings", command=self._open_month_end_reminder_settings)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        self.root.configure(menu=menubar)

    def add_task(self) -> None:
        dialog = AddTaskDialog(self.root, self.service)
        if not dialog.confirmed:
            return
        task_id = self.service.create_task(dialog.name, dialog.notes, dialog.tags)
        selected_template_ids = getattr(dialog, "selected_template_ids", [])
        if selected_template_ids:
            result = self.service.apply_subtask_templates(task_id, selected_template_ids)
            logger.info("Subtask template apply: created_count={} skipped_count={}", result.created_count, result.skipped_count)
            if result.created_subtask_ids:
                self.expanded_parents.add(task_id)
                summary = f"Created {len(result.created_subtask_ids)} subtasks."
                if result.skipped_duplicates:
                    summary += f" Skipped {len(result.skipped_duplicates)} duplicates."
                messagebox.showinfo("Create Task", summary)
        self.refresh_structure()
        self.refresh_live_values()
        

    def export(self) -> bool:
        target = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not target:
            return False
        self.service.export_report(Path(target), reset_after=False)
        logger.info("Normal export created at {}", target)
        self.mark_month_end_reminder_handled_today()
        should_reset = messagebox.askyesno("Reset after export", "Export done. Reset all non-deleted task timers?")
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
                dialog.result.task_ids, dialog.result.window_start_utc, dialog.result.window_end_utc
            )
            if overlaps:
                lines = [
                    "Some selected time may already have been entered in Epicor.",
                    "",
                    "Overlaps:",
                ]
                for item in overlaps:
                    start = item["overlap_start_utc"].astimezone(self.service.local_tz).strftime("%Y-%m-%d %I:%M %p")
                    end = item["overlap_end_utc"].astimezone(self.service.local_tz).strftime("%Y-%m-%d %I:%M %p")
                    reason = item["existing_reason"] or "n/a"
                    lines.append(
                        f'- {item["task_name"]}: {start} to {end} (submission {item["existing_submission_id"]}, reason: {reason})'
                    )
                proceed = messagebox.askyesno(
                    "Possible duplicate Epicor entry",
                    "\n".join(lines) + "\n\nContinue and Mark Anyway?",
                )
                if not proceed:
                    return False
        target = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
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

    def _handle_selected_export_post_action(self, action: str, selected_task_ids: list[str]) -> None:
        if action == "leave":
            return
        if action == "reset":
            logger.info("Post selected export action: reset")
            self._create_risky_operation_backup("before resetting selected exported tasks")
            self.service.reset_selected_tasks(selected_task_ids)
            self.refresh_structure()
            self.refresh_live_values()
            return
        if action == "delete":
            logger.info("Post selected export action: delete")
            self._create_risky_operation_backup("before deleting selected exported tasks")
            affected_ids = set(self.service.delete_selected_tasks(selected_task_ids) or [])
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
        self.task_tree = ttk.Treeview(self.table_frame, columns=("notes", "state", "elapsed"), show="tree headings", selectmode="browse")
        self.task_tree.heading("#0", text="Task")
        self.task_tree.heading("notes", text="Notes")
        self.task_tree.heading("state", text="State")
        self.task_tree.heading("elapsed", text="Elapsed")
        self.task_tree.column("#0", width=240, minwidth=170, stretch=False, anchor="w")
        self.task_tree.column("notes", width=280, minwidth=200, stretch=True, anchor="w")
        self.task_tree.column("state", width=130, minwidth=120, stretch=False, anchor="center")
        self.task_tree.column("elapsed", width=80, minwidth=75, stretch=False, anchor="e")
        y_scroll = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=y_scroll.set)
        self.task_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.table_frame.grid_rowconfigure(0, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)
        if self.parent_name_font is not None:
            self.task_tree.tag_configure("parent", font=self.parent_name_font)
        self.task_tree.tag_configure("running", foreground=RUNNING_COLOR, background="#eef8f1")
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
        self.selected_task_panel.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.selected_task_panel.grid_columnconfigure(0, weight=1)
        self.selected_task_label_var = StringVar(value="Selected: None")
        ttk.Label(self.selected_task_panel, textvariable=self.selected_task_label_var).grid(row=0, column=0, sticky="w")
        self.selected_state_label = tk.Label(
            self.selected_task_panel,
            text="",
            bg=self.root.cget("bg"),
            fg="black",
            padx=8,
            pady=1,
        )
        self.selected_state_label.grid(row=0, column=1, sticky="e", padx=(8, 0), pady=(0, 6))
        button_bar = ttk.Frame(self.selected_task_panel)
        button_bar.grid(row=1, column=0, sticky="w")
        self.selected_toggle_btn = ttk.Button(button_bar, text="Start", command=self._toggle_selected_task)
        self.selected_toggle_btn.pack(side="left", padx=(0, 4))
        self.selected_reset_btn = ttk.Button(button_bar, text="Reset", command=self._reset_selected_task)
        self.selected_reset_btn.pack(side="left", padx=4)
        self.selected_delete_btn = ttk.Button(button_bar, text="Delete", command=self._delete_selected_task)
        self.selected_delete_btn.pack(side="left", padx=4)
        self.selected_move_btn = ttk.Button(button_bar, text="Move Task", command=self._move_selected_task)
        self.selected_move_btn.pack(side="left", padx=4)
        self.selected_edit_btn = ttk.Button(button_bar, text="Edit Task", command=self._edit_selected_task)
        self.selected_edit_btn.pack(side="left", padx=4)
        self.selected_timeline_btn = ttk.Button(button_bar, text="Edit Timeline", command=self._edit_selected_timeline)
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
            self.task_tree.insert("", "end", iid=root.task_id, text=root.name, values=(root.notes, "■ Stopped", "00:00"), open=root.task_id in self.expanded_parents, tags=self._tree_tags(root, is_subtask=False, has_children=bool(children)))
            for child in children:
                grandkids = self._sorted_tasks(children_map.get(child.task_id, []))
                if self._has_running_descendant(child.task_id, children_map):
                    self.expanded_parents.add(child.task_id)
                self.task_tree.insert(root.task_id, "end", iid=child.task_id, text=child.name, values=(child.notes, "■ Stopped", "00:00"), open=child.task_id in self.expanded_parents, tags=self._tree_tags(child, is_subtask=True, has_children=bool(grandkids)))
                for nested in grandkids:
                    self.task_tree.insert(child.task_id, "end", iid=nested.task_id, text=nested.name, values=(nested.notes, "■ Stopped", "00:00"), tags=self._tree_tags(nested, is_subtask=True, has_children=False))
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
        return sorted(tasks, key=lambda task: (task.name.strip().casefold(), task.task_id))

    def _has_running_descendant(self, task_id: str, children_map: dict[str, list[TaskState]]) -> bool:
        stack = list(children_map.get(task_id, []))
        while stack:
            child = stack.pop()
            if child.is_running:
                return True
            stack.extend(children_map.get(child.task_id, []))
        return False

    def _tree_tags(self, task: TaskState, *, is_subtask: bool, has_children: bool) -> tuple[str, ...]:
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
            elapsed = self.service.task_own_elapsed(task_id, now_utc) if not self.service.child_tasks(task_id, include_deleted=False) else self.service.task_tree_elapsed(task_id, now_utc)
            state_text = self._task_state_display(task, now_utc)
            self.task_tree.set(task_id, "elapsed", format_duration_hm(elapsed))
            if self.task_tree.set(task_id, "state") != state_text:
                self.task_tree.set(task_id, "state", state_text)
            parent = self.task_tree.parent(task_id)
            has_children = bool(self.service.child_tasks(task_id, include_deleted=False))
            self.task_tree.item(task_id, tags=self._tree_tags(task, is_subtask=bool(parent), has_children=has_children))
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
        threshold = timedelta(hours=getattr(self.ui_settings, "long_running_task_warning_hours", DEFAULT_LONG_RUNNING_TASK_WARNING_HOURS))
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
        if any(child.is_running for child in self.service.descendant_tasks(task_id, include_deleted=False)):
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
        has_selected_task = bool(task and not task.is_deleted)
        if not has_selected_task:
            self.selected_task_label_var.set("Selected: None")
            if hasattr(self, "selected_state_label"):
                bg, fg = self._selected_state_colors("")
                self.selected_state_label.configure(text="", bg=bg, fg=fg)
            self.selected_toggle_btn.configure(text="Start", state="disabled")
            for btn in (self.selected_reset_btn, self.selected_delete_btn, self.selected_move_btn, self.selected_edit_btn, self.selected_timeline_btn):
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
        self.selected_task_label_var.set(f"Selected: {' / '.join(reversed(path_names))}")
        state_text = self._task_state_display(task, utc_now())
        if hasattr(self, "selected_state_label"):
            bg, fg = self._selected_state_colors(state_text)
            self.selected_state_label.configure(text=f"State: {state_text}", bg=bg, fg=fg)
        self.selected_toggle_btn.configure(text="Stop" if task.is_running else "Start", state="normal")
        for btn in (self.selected_reset_btn, self.selected_delete_btn, self.selected_move_btn, self.selected_edit_btn, self.selected_timeline_btn):
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
        if not task:
            return
        if task.is_running:
            self.service.stop_task(task_id)
        else:
            self.service.start_task(task_id)
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
                self._create_risky_operation_backup("before resetting selected task and descendants")
                self.service.reset_task_tree(task_id)
            else:
                self._create_risky_operation_backup("before resetting selected task")
                self.service.reset_task_only(task_id)
            self._after_state_change()
            return

        if messagebox.askyesno("Confirm reset", "Reset this task timer to zero?"):
            self._create_risky_operation_backup("before resetting selected task")
            self.service.reset_task_only(task_id)
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
        has_active = any(not task.is_deleted for task in self.service.state.tasks.values())
        if not has_active:
            messagebox.showinfo("Reset All Task Timers", "There are no active tasks to reset.")
            return
        self._create_risky_operation_backup("before reset all task timers")
        self.service.reset_all_non_deleted_tasks()
        logger.info("Reset all timers")
        self._after_state_change()
        messagebox.showinfo("Reset All Task Timers", "All active task timers were reset.")

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
            self._create_risky_operation_backup("before deleting selected task and descendants")
            self.service.delete_task_tree(task_id)
            self.expanded_parents.discard(task_id)
            self._after_state_change()
            return

        if messagebox.askyesno("Confirm delete", "Delete this task from active view?"):
            self._create_risky_operation_backup("before deleting selected task")
            self.service.delete_task_only(task_id)
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

        if dialog.new_parent_task_id is not None and not self.service.state.tasks.get(dialog.new_parent_task_id):
            messagebox.showerror("Move Task", "Selected parent task no longer exists.")
            self._after_state_change()
            return

        if old_parent_task_id == dialog.new_parent_task_id:
            return

        try:
            self.service.move_task(task_id, dialog.new_parent_task_id, getattr(dialog, "reason", "") or None)
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
        dialog = BackupSettingsDialog(self.root, self.service, self.service.load_backup_settings())
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
            messagebox.showinfo("Checkpoint reopened", "The active export checkpoint was reopened.")
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
                    self.reminder_banner.pack(fill="x", padx=8, pady=(8, 4), before=self.toolbar_frame)
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
        if self.ui_settings.month_end_reminder_last_export_prompted_local_date == today_iso:
            return
        if self._startup_reminder_prompted_date == today_iso:
            return
        self._startup_reminder_prompted_date = today_iso
        messagebox.showinfo("Month-End Reminder", "Month-end reminder: enter/export your time today.")
        self.ui_settings.month_end_reminder_last_export_prompted_local_date = today_iso
        self.ui_settings_store.save(self.ui_settings)
        self.root.lift()

    def _open_month_end_reminder_settings(self) -> None:
        dialog = MonthEndReminderSettingsDialog(self.root, self.ui_settings)
        if not dialog.confirmed:
            return
        self.ui_settings.month_end_reminder_enabled = dialog.enabled_var.get()
        self.ui_settings.month_end_reminder_show_startup_notice = dialog.startup_var.get()
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
        next_delay_ms = max((60 - now_local.second) * 1000 - (now_local.microsecond // 1000), 1000)
        self._tick_job = self.root.after(next_delay_ms, self._tick)
