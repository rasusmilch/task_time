from types import SimpleNamespace

import pytest

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


def _frame(service: DummyService, selected: list[str]) -> TagSelectionFrame:
    frame = TagSelectionFrame.__new__(TagSelectionFrame)
    frame.service = service
    frame._selected_tags = set(selected)
    return frame


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
