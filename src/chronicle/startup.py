"""First-run/remembered source launch, outside the authoritative application session."""
from queue import Empty
import stat
import sys
import traceback
from tkinter import StringVar, filedialog, ttk

from . import launcher_selection as selection
from .sqlite_store import DATABASE
from .timekeeping import load_zone
from .worker import Message

TIMEZONES = {
    'Eastern Time (US & Canada)': 'America/New_York',
    'Central Time (US & Canada)': 'America/Chicago',
    'Mountain Time (US & Canada)': 'America/Denver',
    'Pacific Time (US & Canada)': 'America/Los_Angeles',
    'Arizona': 'America/Phoenix',
    'Alaska': 'America/Anchorage',
    'Hawaii': 'Pacific/Honolulu',
    'UTC': 'Etc/UTC',
}
OTHER = 'Advanced / Other'
WINDOWS_ZONES = {
    'Eastern Standard Time': 'America/New_York',
    'Central Standard Time': 'America/Chicago',
    'Mountain Standard Time': 'America/Denver',
    'Pacific Standard Time': 'America/Los_Angeles',
    'US Mountain Standard Time': 'America/Phoenix',
    'Alaskan Standard Time': 'America/Anchorage',
    'Hawaiian Standard Time': 'Pacific/Honolulu',
    'UTC': 'Etc/UTC',
}


def windows_zone_id():
    """Read the authoritative Windows key name, never an abbreviation/offset."""
    if sys.platform != 'win32':
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SYSTEM\CurrentControlSet\Control\TimeZoneInformation') as key:
            value, kind = winreg.QueryValueEx(key, 'TimeZoneKeyName')
        return value.rstrip('\0') if kind == winreg.REG_SZ and type(value) is str else None
    except OSError:
        return None


def suggested_timezone(identifier):
    zone = WINDOWS_ZONES.get(identifier)
    return next((label for label, key in TIMEZONES.items() if key == zone), '')


def selected_timezone(label, other):
    key = other.strip() if label == OTHER else TIMEZONES.get(label)
    if not key:
        raise ValueError('Choose your timezone before creating a dataset')
    load_zone(key)
    return key


def admit_folder(value, *, create):
    path = selection.local_path(value)
    if create:
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise ValueError('Creation requires a new or genuinely empty folder. Choose another folder or Open Existing Dataset.')
    else:
        if not path.is_dir():
            raise ValueError('The selected dataset folder is missing or unavailable. Choose an existing dataset.')
        db = path / DATABASE
        selection.local_path(db)
        try:
            mode = db.lstat().st_mode
        except FileNotFoundError as exc:
            raise ValueError('This folder has no Chronicle database. Choose a dataset folder, not a backup file.') from exc
        if not stat.S_ISREG(mode):
            raise ValueError('A regular Chronicle database is required; existing objects are retained')
    return path  # Worker/store final validation, ownership, creation and races remain authoritative.


class StartupWindow:
    def __init__(self, root, *, app_factory, worker_factory, locations=None, timezone_id=None):
        self.root, self.app_factory, self.worker_factory = root, app_factory, worker_factory
        self.locations = selection.locations() if locations is None else locations
        self.expected = None
        self.remember_allowed = self.locations.record is not None
        self.worker = self.app = None
        self.choosing = False
        self.alive, self.stopped, self.cleanup_failed = True, False, False
        self.poll_id = self.discover_id = None
        self.failure = None
        self.directory = None
        self.root.title('Welcome to Chronicle')
        self.root.geometry('680x480')
        self.frame = ttk.Frame(root, padding=18)
        self.frame.pack(fill='both', expand=True)
        ttk.Label(self.frame, text='Welcome to Chronicle', font=('', 17)).pack(anchor='w')
        ttk.Label(self.frame, text='Your work is stored locally in a Chronicle dataset folder.\nChoose its location and timezone, or open an existing dataset.').pack(anchor='w', pady=10)
        ttk.Label(self.frame, text='Dataset folder').pack(anchor='w')
        self.folder = ttk.Entry(self.frame, width=75)
        self.folder.pack(fill='x')
        if self.locations.folder is not None:
            self.folder.insert(0, str(self.locations.folder))
        self.choose_button = ttk.Button(self.frame, text='Choose folder', command=self.choose_folder)
        self.choose_button.pack(anchor='w', pady=5)
        ttk.Label(self.frame, text='Timezone for a new dataset').pack(anchor='w')
        self.timezone = ttk.Combobox(self.frame, values=(*TIMEZONES, OTHER), state='readonly', width=45)
        self.timezone.set(suggested_timezone(windows_zone_id() if timezone_id is None else timezone_id))
        self.timezone.pack(anchor='w')
        self.other_text = StringVar(self.root, '')
        self.other = ttk.Entry(self.frame, width=45, textvariable=self.other_text)
        self.timezone.bind('<<ComboboxSelected>>', self.zone_changed)
        self.zone_label = ttk.Label(self.frame, text='')
        self.zone_label.pack(anchor='w', pady=5)
        self.other_text.trace_add('write', lambda *args: self.zone_changed())
        self.status = ttk.Label(self.frame, text='', wraplength=620)
        self.status.pack(fill='x', pady=8)
        actions = ttk.Frame(self.frame)
        actions.pack(fill='x')
        self.create_button = ttk.Button(actions, text='Create and Open', command=self.create)
        self.open_button = ttk.Button(actions, text='Open Existing Dataset', command=self.open_existing)
        self.cancel_button = ttk.Button(actions, text='Cancel', command=self.cancel)
        for button in (self.create_button, self.open_button, self.cancel_button):
            button.pack(side='left', padx=3)
        self.cleanup_button = ttk.Button(self.frame, text='Retry cleanup', command=self.retry_cleanup)
        self.root.protocol('WM_DELETE_WINDOW', self.cancel)
        self.escape_binding = self.root.bind('<Escape>', lambda event: self.cancel(), add='+')
        self.destroy_binding = self.root.bind('<Destroy>', self.destroyed, add='+')
        self.zone_changed()
        self.discover_id = self.root.after_idle(self.discover)

    def zone_changed(self, event=None):
        label = self.timezone.get()
        if label == OTHER:
            self.other.pack(before=self.zone_label, anchor='w')
            text = self.other.get().strip() or 'Enter an IANA timezone below Advanced / Other'
        else:
            self.other.pack_forget()
            text = label or 'Choose a timezone; no timezone has been assumed'
        self.zone_label.configure(text='Selected timezone: ' + text)

    def diagnostic(self, context, exc):
        self.status.configure(text=f'{context}\n{type(exc).__name__}: {exc}')
        traceback.print_exception(exc)

    def discover(self):
        self.discover_id = None
        if not self.alive:
            return
        try:
            if self.locations.record is not None:
                self.expected = selection.read_selection(self.locations.record)
            if self.expected is not None:
                self.folder.delete(0, 'end'); self.folder.insert(0, str(self.expected.directory))
                self.begin(self.expected.directory, create=False, timezone=None)
                return
        except Exception as exc:
            self.remember_allowed = False
            self.diagnostic('Launcher selection cannot be read safely. Choose a dataset explicitly; the original selection will be retained.', exc)
            return
        try:
            folder = self.locations.folder
            if folder is None:
                self.status.configure(text=self.locations.diagnostic + '\nChoose a local folder explicitly.')
            else:
                selection.local_path(folder)
                if folder.exists():
                    if (folder / DATABASE).exists():
                        self.begin(folder, create=False, timezone=None)
                    elif not folder.is_dir() or any(folder.iterdir()):
                        raise ValueError('Suggested folder contains unknown or incomplete data. Choose another folder or explicitly open an existing dataset; nothing will be recreated.')
        except Exception as exc:
            self.diagnostic('Automatic opening was refused. Choose a folder explicitly.', exc)

    def choose_directory(self, *, existing):
        self.choosing = True
        self.controls()
        try:
            return filedialog.askdirectory(parent=self.root,
                title='Open Existing Chronicle Dataset' if existing else 'Choose Chronicle dataset folder',
                mustexist=existing)
        finally:
            self.choosing = False
            self.controls()

    def choose_folder(self):
        if self.worker is not None or self.choosing:
            return
        try:
            chosen = self.choose_directory(existing=False)
            if chosen:
                self.folder.delete(0, 'end'); self.folder.insert(0, chosen)
        except Exception as exc:
            self.diagnostic('Folder selection failed; you can enter a folder or cancel.', exc)

    def open_existing(self):
        if self.worker is not None or self.choosing:
            return
        try:
            chosen = self.choose_directory(existing=True)
            if chosen:
                self.folder.delete(0, 'end'); self.folder.insert(0, chosen)
                self.begin(chosen, create=False, timezone=None)
        except Exception as exc:
            self.diagnostic('Unable to select an existing dataset.', exc)

    def create(self):
        if self.worker is not None or self.choosing:
            return
        try:
            zone = selected_timezone(self.timezone.get(), self.other.get())
            self.begin(self.folder.get(), create=True, timezone=zone)
        except Exception as exc:
            self.diagnostic('Dataset was not submitted for creation. Check the folder and timezone.', exc)

    def controls(self):
        idle = self.worker is None and not self.choosing
        for widget in (self.choose_button, self.create_button, self.open_button, self.cancel_button, self.folder, self.other):
            widget.configure(state='normal' if idle else 'disabled')
        self.timezone.configure(state='readonly' if idle else 'disabled')
        if self.cleanup_failed:
            self.cleanup_button.pack(anchor='w', pady=5)
        else:
            self.cleanup_button.pack_forget()

    def begin(self, directory, *, create, timezone):
        if self.worker is not None or not self.alive:
            return
        try:
            directory = admit_folder(directory, create=create)
            self.failure = None
            self.stopped = self.cleanup_failed = False
            self.directory = directory
            self.worker = self.worker_factory(directory, create=create, timezone=timezone)
            self.controls()
            self.status.configure(text='Opening your dataset; please wait for complete validation…')
            self.worker.start()
        except Exception as exc:
            if self.worker is not None and self.worker.is_alive():
                self.failure = exc
                self.worker.requests.put(Message('shutdown'))
                self.poll_id = self.root.after(20, self.poll)
            else:
                self.worker = None
            self.controls()
            self.diagnostic('Unable to open or create this dataset. Existing data has not been replaced.', exc)
            return
        self.poll_id = self.root.after(20, self.poll)

    def poll(self):
        self.poll_id = None
        if not self.alive:
            return
        for _ in range(16):
            try:
                message = self.worker.results.get_nowait()
            except Empty:
                break
            if message.kind == 'ready':
                self.handoff(message)
                return
            if message.kind == 'startup_failed':
                self.failure = message.value
                self.diagnostic('Chronicle could not open this dataset. Check permissions, another running instance, or choose another dataset. No replacement is created.', message.value)
            elif message.kind == 'shutdown_failed':
                self.cleanup_failed = True
                self.diagnostic(f'Dataset cleanup did not finish; ownership is retained. Startup error: {self.failure}. Retry cleanup before choosing another dataset or exiting.', message.value)
                self.controls()
            elif message.kind == 'stopped':
                self.stopped = True
        if self.stopped and not self.worker.is_alive():
            self.worker = None
            self.cleanup_failed = False
            self.controls()
            return
        self.poll_id = self.root.after(20, self.poll)

    def retry_cleanup(self):
        if self.worker is not None and self.cleanup_failed:
            self.cleanup_failed = False
            self.controls()
            self.worker.requests.put(Message('shutdown'))

    def handoff(self, ready):
        # No ChronicleApp, session, timer callback or modal grab exists before ready.
        self.frame.pack_forget()
        self.root.unbind('<Escape>', self.escape_binding)
        self.root.unbind('<Destroy>', self.destroy_binding)
        callbacks = set(self.root.tk.call('after', 'info'))
        destroy_script = self.root.bind('<Destroy>') or ''
        try:
            self.app = self.app_factory(self.root, self.worker)
            self.app._handle(ready)  # Deliver the actual worker result through the established owner path.
        except Exception as exc:
            # Construction/ready delivery has not yielded to operator input. Retire
            # only this partial application's callbacks/widgets, then drain the same
            # worker's cleanup before enabling another explicit choice.
            if self.app is not None:
                self.app.alive = False
                self.app._shutdown_sent = True
            for token in set(self.root.tk.call('after', 'info')) - callbacks:
                self.root.after_cancel(token)
            self.root.tk.call('bind', self.root._w, '<Destroy>', destroy_script)
            for widget in self.root.winfo_children():
                if widget is not self.frame:
                    widget.destroy()
            self.app = None
            self.frame.pack(fill='both', expand=True)
            self.root.title('Welcome to Chronicle')
            self.root.protocol('WM_DELETE_WINDOW', self.cancel)
            self.escape_binding = self.root.bind('<Escape>', lambda event: self.cancel(), add='+')
            self.destroy_binding = self.root.bind('<Destroy>', self.destroyed, add='+')
            self.failure = exc
            self.diagnostic('Unable to display Chronicle. The dataset is retained; wait for cleanup, then open it explicitly or cancel.', exc)
            self.worker.requests.put(Message('shutdown'))
            self.controls()
            self.poll_id = self.root.after(20, self.poll)
            return
        self.frame.destroy()
        self.alive = False
        try:
            if not self.remember_allowed:
                raise ValueError(self.locations.diagnostic or 'The unreadable/unsupported selection record was preserved')
            selection.remember(self.locations.record, self.directory, self.expected)
        except Exception as exc:
            traceback.print_exception(exc)
            self.app.launcher_notice = ttk.Label(self.root, wraplength=700,
                text=f'This dataset is open, but its location could not be remembered. Next launch may require choosing it again.\n{type(exc).__name__}: {exc}')
            self.app.launcher_notice.grid(row=9, column=0, sticky='w', padx=10, pady=5)

    def cancel(self):
        if not self.alive:
            return
        if self.worker is not None or self.choosing:
            self.status.configure(text='Please finish the folder choice or wait for startup/cleanup before closing. No accepted operation is interrupted.')
            return
        self.root.destroy()

    def destroyed(self, event):
        if event.widget is self.root and self.alive:
            self.alive = False
            for token in (self.poll_id, self.discover_id):
                if token is not None:
                    self.root.after_cancel(token)
            if self.worker is not None:
                self.worker.requests.put(Message('shutdown'))
