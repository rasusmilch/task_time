"""Application-owned modal Timesheet shell with session-only unfinished retention."""

from tkinter import BooleanVar, TclError, Toplevel, messagebox, ttk

from .timesheet_save import TimesheetSaveFrame


class TimesheetWindow:
    def __init__(self, parent, service, *, now_utc, on_disposed):
        self._parent, self._on_disposed = parent, on_disposed
        self._constructed = self._destroyed = self._notified = False
        self._presented = self._closing = False
        self.window = None
        self._wait_done = BooleanVar(parent, value=False)
        try:
            self.window = Toplevel(parent)
            self.window.withdraw()
            self.window.title("Timesheet")
            self.window.bind('<Destroy>', self._on_destroy, add='+')
            self.window.bind('<Unmap>', self._on_unmap, add='+')
            self.window.bind('<Escape>', self._escape)
            self.window.protocol('WM_DELETE_WINDOW', self.close)
            self.window.grid_columnconfigure(0, weight=1)
            self.window.grid_rowconfigure(0, weight=1)
            self.save_frame = TimesheetSaveFrame(self.window, service, now_utc=now_utc)
            self.save_frame.grid(row=0, column=0, sticky='nsew', padx=8, pady=8)
            self.close_button = ttk.Button(self.window, text='Close', command=self.close)
            self.close_button.grid(row=1, column=0, sticky='e', padx=8, pady=8)
            self._constructed = True
        except BaseException as exc:
            self._cleanup_failure(exc)
            raise

    def is_busy(self):
        return self._closing or (self._constructed and self.save_frame.is_busy())

    def is_presented(self):
        return self._presented and not self._destroyed

    def has_unfinished_attempt(self):
        return self._constructed and self.save_frame.has_unfinished_attempt()

    def show_modal(self):
        if self._destroyed or self._presented or self.is_busy():
            return
        self._wait_done.set(False)
        self._presented = True
        try:
            self.window.transient(self._parent)
            self.window.deiconify()
            if not self.window.winfo_viewable():
                try:
                    self.window.wait_visibility()
                except TclError:
                    if self._destroyed:
                        return
                    raise
            if self._destroyed:
                return
            grab = self.window.grab_current()
            if grab is not None and (grab is not self._parent or grab.grab_status() != 'local'):
                raise ValueError('Timesheet cannot replace an unrelated or global grab')
            self.window.grab_set()
            self.window.focus_set()
            self.window.wait_variable(self._wait_done)
        except BaseException as exc:
            self._cleanup_failure(exc)
            raise

    @staticmethod
    def _widget_exists(widget):
        # A reused Tcl path must not revive a saved Python widget reference.
        if widget.master is not None and widget.master.children.get(widget._name) is not widget:
            return False
        return bool(widget.tk.call("namespace", "which", "-command", widget._w))

    def restore_modal(self, focus_widget=None):
        """Return ownership after an owned dialog, without presenting or loading."""
        if (not self.is_presented() or self.is_busy()
                or not self._widget_exists(self._parent) or not self._widget_exists(self.window)
                or not self.window.winfo_viewable()):
            return False
        current = self.window.grab_current()
        if current is not None:
            if current is not self.window or current.grab_status() != 'local':
                return False  # Leave competing local/global ownership and focus alone.
        else:
            self.window.grab_set()
        target = self.window
        if (focus_widget is not None and self._widget_exists(focus_widget)
                and focus_widget.winfo_toplevel() is self.window):
            target = focus_widget
        target.focus_set()
        return True

    def _release_grab(self):
        if self.window.grab_current() is self.window:
            self.window.grab_release()

    def _withdraw(self):
        self._release_grab()
        self.window.withdraw()
        self._presented = False
        self._wait_done.set(True)

    def close(self):
        if self._destroyed or self.is_busy():
            return False
        self._closing = True
        try:
            if self.has_unfinished_attempt():
                if not messagebox.askyesno(
                    parent=self.window, title='Keep unfinished Timesheet in this session?', default='no',
                    message='Save is unverified. Close and retain this attempt? Reopening Timesheet '
                            'during this application session resumes it. Registered evidence and '
                            'external files are not undone.',
                ):
                    return False
                self._withdraw()
            else:
                self._dispose()
            return True
        finally:
            self._closing = False

    def _escape(self, _event):
        self.close()
        return 'break'

    def _dispose(self):
        if self.window is None or self._destroyed:
            return
        primary = None
        try:
            self._release_grab()
        except BaseException as exc:
            primary = exc
        try:
            self.window.destroy()
        except BaseException as exc:
            if primary is None:
                raise
            primary.add_note(f'Timesheet destruction also failed: {exc}')
        finally:
            if self._destroyed:
                self._wait_done.set(True)
        if primary is not None:
            raise primary

    def _cleanup_failure(self, original):
        try:
            if self.has_unfinished_attempt() and not self._destroyed:
                self._withdraw()
            else:
                self._dispose()
        except BaseException as cleanup:
            original.add_note(f'Timesheet cleanup also failed: {cleanup}')

    def _on_unmap(self, event):
        if event.widget is self.window and self.window.state() == 'withdrawn':
            self._release_grab()
            self._presented = False
            self._wait_done.set(True)

    def _on_destroy(self, event):
        if event.widget is self.window:
            self._destroyed, self._presented = True, False
            try:
                if self._constructed and not self._notified:
                    self._notified = True
                    self._on_disposed(self)
            finally:
                self._wait_done.set(True)
