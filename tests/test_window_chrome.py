from __future__ import annotations

from types import SimpleNamespace

from loguru import logger

from task_timer.window_chrome import disable_snap_maximize, install_zoom_guard


class _FakeWindow:
    def __init__(self) -> None:
        self.resizable_calls: list[tuple[bool, bool]] = []
        self.update_calls = 0
        self.bindings: dict[str, object] = {}
        self._state = "normal"
        self._geometry = "300x120+10+10"
        self.state_calls: list[str] = []
        self.geometry_calls: list[str] = []

    def resizable(self, x: bool, y: bool) -> None:
        self.resizable_calls.append((x, y))

    def update_idletasks(self) -> None:
        self.update_calls += 1

    def winfo_id(self) -> int:
        return 101

    def bind(self, event: str, callback, add: str | None = None) -> None:
        self.bindings[event] = callback

    def state(self, value: str | None = None) -> str:
        if value is None:
            return self._state
        self._state = value
        self.state_calls.append(value)
        return self._state

    def geometry(self, value: str | None = None) -> str:
        if value is None:
            return self._geometry
        self._geometry = value
        self.geometry_calls.append(value)
        return self._geometry


class _FakeUser32:
    def __init__(self) -> None:
        self.style = 0x00010000 | 0x00040000

    def GetWindowLongW(self, _hwnd: int, _index: int) -> int:
        return self.style

    def SetWindowLongW(self, _hwnd: int, _index: int, value: int) -> int:
        self.style = value
        return value

    def SetWindowPos(self, *_args: object) -> int:
        return 1


def test_disable_snap_maximize_non_windows_still_sets_resizable(monkeypatch) -> None:
    win = _FakeWindow()
    monkeypatch.setattr("task_timer.window_chrome.sys.platform", "linux")

    disable_snap_maximize(win)

    assert win.resizable_calls == [(False, False)]
    assert win.update_calls == 0


def test_disable_snap_maximize_windows_graceful_when_win32_missing(monkeypatch) -> None:
    win = _FakeWindow()
    monkeypatch.setattr("task_timer.window_chrome.sys.platform", "win32")
    monkeypatch.setattr("task_timer.window_chrome.ctypes.windll", SimpleNamespace(), raising=False)

    disable_snap_maximize(win)

    assert win.resizable_calls == [(False, False)]


def test_disable_snap_maximize_logs_debug_on_windows_style_failures(monkeypatch) -> None:
    win = _FakeWindow()
    monkeypatch.setattr("task_timer.window_chrome.sys.platform", "win32")
    monkeypatch.setattr("task_timer.window_chrome.ctypes.windll", object(), raising=False)
    messages: list[str] = []
    sink = logger.add(lambda m: messages.append(str(m)), level="DEBUG")
    try:
        disable_snap_maximize(win)
    finally:
        logger.remove(sink)
    assert any("Unable to apply Windows chrome style updates" in msg for msg in messages)


def test_install_zoom_guard_restores_from_zoomed(monkeypatch) -> None:
    win = _FakeWindow()
    monkeypatch.setattr("task_timer.window_chrome.sys.platform", "win32")
    monkeypatch.setattr(
        "task_timer.window_chrome.ctypes.windll",
        SimpleNamespace(user32=_FakeUser32()),
        raising=False,
    )

    install_zoom_guard(win)
    callback = win.bindings["<Configure>"]

    callback(None)
    assert win.geometry_calls == []

    win._geometry = "1200x900+0+0"
    win._state = "zoomed"
    callback(None)

    assert "normal" in win.state_calls
    assert win.geometry_calls[-1] == "300x120+10+10"
