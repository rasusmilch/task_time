"""Window chrome helpers for disabling maximize/snap behavior."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk

from loguru import logger

GWL_STYLE = -16
WS_MAXIMIZEBOX = 0x00010000
WS_THICKFRAME = 0x00040000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020


def disable_snap_maximize(window: tk.Tk | tk.Toplevel) -> None:
    """Make a window non-resizable/non-maximizable to discourage Windows snap maximize."""
    window.resizable(False, False)
    if not sys.platform.startswith("win"):
        return

    try:
        window.update_idletasks()
        hwnd = int(window.winfo_id())
    except Exception as exc:
        logger.debug("Unable to access native window handle for chrome update: {}", exc)
        return

    try:
        user32 = ctypes.windll.user32
        get_window_long = user32.GetWindowLongW
        set_window_long = user32.SetWindowLongW
        set_window_pos = user32.SetWindowPos

        style = get_window_long(hwnd, GWL_STYLE)
        updated_style = style & ~WS_MAXIMIZEBOX & ~WS_THICKFRAME
        if updated_style == style:
            return

        set_window_long(hwnd, GWL_STYLE, updated_style)
        set_window_pos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
    except Exception as exc:
        logger.debug("Unable to apply Windows chrome style updates: {}", exc)
        return


def install_zoom_guard(window: tk.Tk | tk.Toplevel) -> None:
    """Restore a window if Windows reports a zoomed/maximized state."""
    if not sys.platform.startswith("win"):
        return

    state = {"last_normal_geometry": None, "restoring": False}

    def _on_configure(_event: object | None = None) -> None:
        if state["restoring"]:
            return

        state["restoring"] = True
        try:
            current_state = window.state()
            if current_state == "zoomed":
                window.state("normal")
                if state["last_normal_geometry"]:
                    window.geometry(state["last_normal_geometry"])
                disable_snap_maximize(window)
            elif current_state == "normal":
                state["last_normal_geometry"] = window.geometry()
        except tk.TclError:
            return
        finally:
            state["restoring"] = False

    window.bind("<Configure>", _on_configure, add="+")
