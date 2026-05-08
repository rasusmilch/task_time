"""Reusable tag-selection widgets and helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol
from tkinter import Listbox, StringVar, messagebox, simpledialog, ttk
import tkinter as tk

from .tags import normalize_tag_list


class _TagMeta(Protocol):
    key: str
    archived: bool


class TagService(Protocol):
    def list_global_tags(self, include_archived: bool = ...) -> Sequence[_TagMeta]: ...

    def create_tag(self, key: str) -> None: ...


class TagSelectionFrame(ttk.Frame):
    """Two-list selector for assigning tags to a task."""

    def __init__(
        self,
        parent: tk.Misc,
        service: TagService,
        initial_tags: Iterable[str],
        allow_new_tags: bool = True,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.allow_new_tags = allow_new_tags
        self._selected_tags = set(normalize_tag_list(list(initial_tags)))
        self.error_var = StringVar(value="")

        lists = ttk.Frame(self)
        lists.grid(row=0, column=0, sticky="n")
        lists.grid_columnconfigure(0, weight=0)
        lists.grid_columnconfigure(1, weight=0)
        lists.grid_columnconfigure(2, weight=0)
        lists.grid_columnconfigure(3, weight=0)
        lists.grid_columnconfigure(4, weight=0)
        lists.grid_rowconfigure(1, weight=1)

        ttk.Label(lists, text="Available tags").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(lists, text="Task tags").grid(
            row=0, column=3, columnspan=2, sticky="w"
        )

        self.available_list = Listbox(lists, width=28, height=8, exportselection=False)
        self.available_list.grid(row=1, column=0, sticky="nsew")
        avail_scroll = ttk.Scrollbar(
            lists, orient="vertical", command=self.available_list.yview
        )
        avail_scroll.grid(row=1, column=1, sticky="ns")
        self.available_list.configure(yscrollcommand=avail_scroll.set)

        center = ttk.Frame(lists)
        center.grid(row=1, column=2, padx=8, sticky="n")
        ttk.Button(center, text="Add >", command=self._add_selected_available).pack(
            fill="x", pady=(4, 4)
        )
        ttk.Button(
            center, text="< Remove", command=self._remove_selected_assigned
        ).pack(fill="x")

        self.selected_list = Listbox(lists, width=28, height=8, exportselection=False)
        self.selected_list.grid(row=1, column=3, sticky="nsew")
        sel_scroll = ttk.Scrollbar(
            lists, orient="vertical", command=self.selected_list.yview
        )
        sel_scroll.grid(row=1, column=4, sticky="ns")
        self.selected_list.configure(yscrollcommand=sel_scroll.set)

        self.available_list.bind(
            "<Double-Button-1>", lambda _e: self._add_selected_available()
        )
        self.selected_list.bind(
            "<Double-Button-1>", lambda _e: self._remove_selected_assigned()
        )

        actions = ttk.Frame(self)
        actions.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        if allow_new_tags:
            ttk.Button(
                actions, text="Add New Tag", command=self._prompt_add_new_tag
            ).pack(side="left")
        ttk.Label(actions, textvariable=self.error_var, foreground="#b00020").pack(
            side="left", padx=8
        )

        self.grid_columnconfigure(0, weight=1)
        self.refresh_lists()

    @staticmethod
    def _sorted_visible_tags(
        global_tags: Iterable[_TagMeta], selected_tags: Iterable[str]
    ) -> list[str]:
        selected = set(selected_tags)
        keys = [
            meta.key
            for meta in global_tags
            if not meta.archived and meta.key not in selected
        ]
        return sorted(keys)

    def get_selected_tags(self) -> list[str]:
        return sorted(self._selected_tags)

    def set_selected_tags(self, tags: Iterable[str]) -> None:
        self._selected_tags = set(normalize_tag_list(list(tags)))
        self.refresh_lists()

    def refresh_lists(self) -> None:
        self.available_list.delete(0, "end")
        global_tags = self.service.list_global_tags(include_archived=True)
        for key in self._sorted_visible_tags(global_tags, self._selected_tags):
            self.available_list.insert("end", key)

        self.selected_list.delete(0, "end")
        for key in sorted(self._selected_tags):
            self.selected_list.insert("end", key)

    def _selected_value(self, listbox: Listbox) -> str | None:
        sel = listbox.curselection()
        if not sel:
            return None
        return str(listbox.get(sel[0]))

    def add_selected_tag(self, key: str) -> None:
        self._selected_tags.add(key)

    def remove_selected_tag(self, key: str) -> None:
        self._selected_tags.discard(key)

    def _add_selected_available(self) -> None:
        key = self._selected_value(self.available_list)
        if not key:
            return
        self.add_selected_tag(key)
        self.error_var.set("")
        self.refresh_lists()

    def _remove_selected_assigned(self) -> None:
        key = self._selected_value(self.selected_list)
        if not key:
            return
        self.remove_selected_tag(key)
        self.error_var.set("")
        self.refresh_lists()

    def _prompt_add_new_tag(self) -> None:
        raw = simpledialog.askstring("Add New Tag", "Tag key:", parent=self)
        if raw is None:
            return
        try:
            selected = self.add_or_select_tag(raw)
        except ValueError as exc:
            self.error_var.set(str(exc))
            messagebox.showerror("Tag not added", str(exc), parent=self)
            return
        self.error_var.set("")
        self._selected_tags = set(selected)
        self.refresh_lists()

    def add_or_select_tag(self, raw_tag: str) -> list[str]:
        normalized = normalize_tag_list([raw_tag])[0]
        for meta in self.service.list_global_tags(include_archived=True):
            if meta.key != normalized:
                continue
            if meta.archived:
                raise ValueError(
                    f"Tag '{normalized}' is archived. Unarchive it from Manage Tags."
                )
            self._selected_tags.add(normalized)
            return self.get_selected_tags()
        self.service.create_tag(normalized)
        self._selected_tags.add(normalized)
        return self.get_selected_tags()
