"""Owned modal shell for the staged, fixed-task history browser."""

from tkinter import Toplevel, ttk


class HistoryWindow:
    """Construct withdrawn; the application publishes ownership before presentation."""

    def __init__(self, parent, *, make_browser, on_closed):
        self._parent = parent
        self._on_closed = on_closed
        self._constructed = False
        self._destroyed = False
        self._notified = False
        self.window = None
        try:
            self.window = Toplevel(parent)
            self.window.withdraw()
            self.window.title("Work history")
            self.window.bind("<Destroy>", self._on_destroy, add="+")
            self.window.protocol("WM_DELETE_WINDOW", self.close)
            self.window.grid_columnconfigure(0, weight=1)
            self.window.grid_rowconfigure(0, weight=1)
            self.browser = make_browser(self.window)
            self.browser.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
            self.close_button = ttk.Button(self.window, text="Close", command=self.close)
            self.close_button.grid(row=1, column=0, sticky="e", padx=8, pady=8)
            self._constructed = True
        except BaseException as exc:
            self._dispose_after_failure(exc)
            raise

    def show_modal(self):
        """Use a local grab and normal Tk event processing, without another load."""
        try:
            self.window.transient(self._parent.winfo_toplevel())
            self.window.deiconify()
            self.window.wait_visibility()
            self.window.grab_set()
            self.window.focus_force()
            self.window.wait_window()
        except BaseException as exc:
            self._dispose_after_failure(exc)
            raise

    def close(self):
        """Idempotently destroy only this window and release only its own grab."""
        if self.window is None or self._destroyed:
            return
        try:
            if self.window.grab_current() is self.window:
                self.window.grab_release()
        finally:
            self.window.destroy()

    def _dispose_after_failure(self, original):
        try:
            self.close()
        except BaseException as cleanup:
            original.add_note(f"History window cleanup also failed: {cleanup}")

    def _on_destroy(self, event):
        if event.widget is self.window:
            self._destroyed = True
            if self._constructed and not self._notified:
                self._notified = True
                self._on_closed(self)
