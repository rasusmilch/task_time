from types import SimpleNamespace

import pytest
import task_timer.dialogs as dialogs_module

from task_timer.dialogs import ManageTagsDialog
from task_timer.tag_dialogs import TagSelectionFrame


class DummyService:
    def __init__(self) -> None:
        self.tags = {
            "alpha": SimpleNamespace(key="alpha", archived=False),
            "beta": SimpleNamespace(key="beta", archived=False),
            "archived": SimpleNamespace(key="archived", archived=True),
        }

    def list_global_tags(self, include_archived: bool = True):
        values = list(self.tags.values())
        if include_archived:
            return values
        return [meta for meta in values if not meta.archived]

    def create_tag(self, key: str) -> None:
        if key in self.tags and not self.tags[key].archived:
            raise ValueError("exists")
        if key in self.tags and self.tags[key].archived:
            raise ValueError("archived")
        self.tags[key] = SimpleNamespace(key=key, archived=False)


class DummyManageService(DummyService):
    def tag_usage_counts(self):
        return {"alpha": 1, "beta": 0, "archived": 0}

    def rename_tag(self, old_key: str, new_key: str) -> None:
        if old_key not in self.tags:
            raise ValueError("missing")
        if new_key.strip().casefold() in self.tags:
            raise ValueError("exists")
        key = new_key.strip().casefold()
        meta = self.tags.pop(old_key)
        meta.key = key
        self.tags[key] = meta

    def archive_tag(self, key: str) -> None:
        if self.tag_usage_counts().get(key, 0) > 0:
            raise ValueError("in use")
        self.tags[key].archived = True

    def unarchive_tag(self, key: str) -> None:
        self.tags[key].archived = False

    def delete_tag(self, key: str) -> None:
        if self.tag_usage_counts().get(key, 0) > 0:
            raise ValueError("in use")
        if not self.tags[key].archived:
            raise ValueError("archive first")
        self.tags.pop(key)


def _frame(service: DummyService, selected: list[str]) -> TagSelectionFrame:
    frame = TagSelectionFrame.__new__(TagSelectionFrame)
    frame.service = service
    frame._selected_tags = set(selected)
    return frame


class FakeTree:
    def __init__(self) -> None:
        self.items: dict[str, tuple[str, str, str]] = {}
        self._sel: tuple[str, ...] = ()

    def selection(self):
        return self._sel

    def selection_set(self, iid: str) -> None:
        self._sel = (iid,)

    def focus(self, _iid: str) -> None:
        return

    def get_children(self):
        return list(self.items)

    def delete(self, iid: str) -> None:
        self.items.pop(iid, None)

    def insert(self, _parent: str, _idx: str, iid: str, values: tuple[str, str, str]) -> None:
        self.items[iid] = values

    def exists(self, iid: str) -> bool:
        return iid in self.items


def test_sorted_visible_tags_excludes_selected_and_archived() -> None:
    service = DummyService()
    out = TagSelectionFrame._sorted_visible_tags(service.list_global_tags(include_archived=True), {"alpha"})
    assert out == ["beta"]


def test_get_selected_tags_sorted() -> None:
    f = _frame(DummyService(), ["beta", "alpha"])
    assert f.get_selected_tags() == ["alpha", "beta"]


def test_add_or_select_tag_creates_and_selects_normalized() -> None:
    service = DummyService()
    f = _frame(service, [])
    selected = f.add_or_select_tag("  New  TAG ")
    assert selected == ["new tag"]
    assert "new tag" in service.tags


def test_add_or_select_existing_active_tag_uses_existing() -> None:
    f = _frame(DummyService(), [])
    selected = f.add_or_select_tag(" Alpha ")
    assert selected == ["alpha"]


def test_add_or_select_archived_tag_blocked() -> None:
    f = _frame(DummyService(), [])
    with pytest.raises(ValueError, match="archived"):
        f.add_or_select_tag("archived")


def test_add_or_select_invalid_empty_tag_blocked() -> None:
    f = _frame(DummyService(), [])
    with pytest.raises(ValueError, match="Tag is required"):
        f.add_or_select_tag("   ")


def test_add_and_remove_selected_tag_moves_between_lists_logic() -> None:
    service = DummyService()
    f = _frame(service, [])
    available_before = TagSelectionFrame._sorted_visible_tags(service.list_global_tags(include_archived=True), f.get_selected_tags())
    assert available_before == ["alpha", "beta"]

    f.add_selected_tag("alpha")
    assert f.get_selected_tags() == ["alpha"]
    available_after_add = TagSelectionFrame._sorted_visible_tags(service.list_global_tags(include_archived=True), f.get_selected_tags())
    assert available_after_add == ["beta"]

    f.remove_selected_tag("alpha")
    assert f.get_selected_tags() == []
    available_after_remove = TagSelectionFrame._sorted_visible_tags(service.list_global_tags(include_archived=True), f.get_selected_tags())
    assert available_after_remove == ["alpha", "beta"]




def test_dialog_sources_do_not_use_comma_separated_tag_entry() -> None:
    import inspect

    from task_timer import dialogs as dialogs_src

    combined = "\n".join(
        [
            inspect.getsource(dialogs_src.AddTaskDialog),
            inspect.getsource(dialogs_src.EditTaskDialog),
        ]
    )
    assert "Tags (comma-separated)" not in combined
    assert '.split(",")' not in combined
def test_manage_tags_dialog_not_placeholder() -> None:
    import inspect

    source = inspect.getsource(ManageTagsDialog.__init__)
    assert "global actions not fully implemented" not in source


def test_manage_tags_dialog_add_rename_archive_unarchive_delete(monkeypatch) -> None:
    dlg = ManageTagsDialog.__new__(ManageTagsDialog)
    dlg.changed = False
    dlg.service = DummyManageService()
    dlg.tree = FakeTree()
    dlg.window = object()
    dlg.refresh_table()
    dlg.tree.selection_set("beta")

    monkeypatch.setattr(dialogs_module.simpledialog, "askstring", lambda *a, **k: "gamma")
    monkeypatch.setattr(dialogs_module.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(dialogs_module.messagebox, "askyesno", lambda *a, **k: True)
    dlg._add_tag()
    assert "gamma" in dlg.tree.items

    dlg.tree.selection_set("gamma")
    monkeypatch.setattr(dialogs_module.simpledialog, "askstring", lambda *a, **k: "delta")
    dlg._rename_tag()
    assert "delta" in dlg.tree.items

    dlg.tree.selection_set("delta")
    dlg._archive_tag()
    assert dlg.tree.items["delta"][1] == "archived"

    dlg._unarchive_tag()
    assert dlg.tree.items["delta"][1] == "active"

    dlg._archive_tag()
    dlg._delete_tag()
    assert "delta" not in dlg.tree.items
    assert dlg.changed is True


def test_manage_tags_dialog_blocks_archive_delete_when_in_use(monkeypatch) -> None:
    dlg = ManageTagsDialog.__new__(ManageTagsDialog)
    dlg.changed = False
    dlg.service = DummyManageService()
    dlg.tree = FakeTree()
    dlg.window = object()
    dlg.refresh_table()
    dlg.tree.selection_set("alpha")
    errors: list[str] = []
    monkeypatch.setattr(dialogs_module.messagebox, "showerror", lambda _t, msg, **k: errors.append(msg))
    monkeypatch.setattr(dialogs_module.messagebox, "askyesno", lambda *a, **k: True)
    dlg._archive_tag()
    dlg._delete_tag()
    assert any("in use" in e for e in errors)


def test_tag_selection_frame_grid_columns_are_distinct() -> None:
    import inspect
    import task_timer.tag_dialogs as tag_dialogs_module

    source = inspect.getsource(tag_dialogs_module.TagSelectionFrame.__init__)
    assert 'avail_scroll.grid(row=1, column=1' in source
    assert 'center.grid(row=1, column=2' in source
    assert 'self.selected_list.grid(row=1, column=3' in source
    assert 'sel_scroll.grid(row=1, column=4' in source
