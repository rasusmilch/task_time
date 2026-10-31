"""One-shot, test-only Windows focus preparation on the current input desktop.

No desktop lifecycle or foreground-forcing API. Native inspection (including
WM_NCHITTEST) runs on a GUI-free thread, never Tk's input queue. Only the Tk
thread can send input, and only before terminal disarming.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import queue
import sys
import threading
import time
from uuid import uuid4


HISTORY = 'tests/rewrite/test_chronicle_history_modal.py'
TIMESHEET = 'tests/rewrite/test_chronicle_timesheet_ui.py'
NODES = {
    **{HISTORY + '::test_real_tk_history_parent_grab_focus_return_identity_and_guard[' + mode + ']':
       ('PRECONDITION History origin focus', 'History actual return focus')
       for mode in ('local', 'none', 'missing', 'reused')},
    TIMESHEET + '::test_real_tk_timesheet_origin_return_competing_grab_destroy_and_reentry':
        ('PRECONDITION Timesheet origin focus', 'Timesheet actual return focus'),
    TIMESHEET + '::test_real_tk_global_grab_and_deleted_focus_origin_are_not_replaced':
        ('PRECONDITION Timesheet destroyed origin', 'Timesheet root fallback focus'),
}
REPO = Path(__file__).resolve().parents[2]


class FocusBlocked(RuntimeError):
    status = 'BLOCKED'
    unsafe_input = False


class FocusFailed(RuntimeError):
    status = 'FAIL'
    def __init__(self, message, *, unsafe_input=False):
        super().__init__(message)
        self.unsafe_input = unsafe_input


def require(condition, message):
    if not condition:
        raise FocusBlocked(message)


class FocusPreconditionDriver:
    """Cooperative preparation: prepare() is polled by the existing Tk pump."""
    @classmethod
    def for_node(cls, item, *, platform=None, api=None, clock=time.monotonic):
        if (sys.platform if platform is None else platform) != 'win32':
            return None
        node = item.nodeid
        if node not in NODES:
            return None
        expected = (REPO / node.split('::', 1)[0]).resolve()
        require(Path(item.path).resolve() == expected,
                f'Authorized node {node} has a different source path: {item.path}; expected {expected}')
        return cls(node, expected, api or Win32API(), clock=clock, session=item.session)

    def __init__(self, node, source, api, *, clock=time.monotonic, session=None):
        require(node in NODES and Path(source).resolve() == (REPO/node.split('::', 1)[0]).resolve(),
                'Unapproved focus node/source')
        self.node, self.source, self.api = node, str(source), api
        self.clock, self.session = clock, session
        self.state = 'AUTHORIZED'
        self.root = self.target = self.widget = None
        self.result = None
        self.worker = None
        self.reply = queue.Queue(maxsize=1)
        self.focus_called = False
        self.sent = False
        self.verified = False
        self.observations = []
        self.events = []
        self.record('authorized')

    def record(self, event, **fields):
        if len(self.events) < 40:
            self.events.append(dict(event=event, monotonic=self.clock(), **fields))

    def attach(self, root):
        require(self.root is None, 'Driver already has a root')
        self.root = root

    def live(self, widget, *, viewable=True):
        require(self.root.winfo_exists() and self.root.nametowidget(str(self.root)) is self.root,
                'Destroyed or reused Tk root')
        require(widget.winfo_exists() and self.root.nametowidget(str(widget)) is widget,
                'Destroyed or reused intended Tk widget')
        require(widget.winfo_toplevel() is self.root, 'Intended widget belongs to another top-level')
        if viewable:
            require(self.root.winfo_viewable() and widget.winfo_viewable(), 'Tk input target is not viewable')

    def prepare(self, widget, deadline):
        try:
            require(self.state != 'DISARMED', 'Driver is terminally disarmed')
            if self.clock() >= deadline:
                if self.sent:raise FocusFailed('Focus activation deadline exhausted')
                raise FocusBlocked('Focus precondition deadline exhausted')
            self.live(widget, viewable=False)
            if self.state == 'AUTHORIZED':
                self.state = 'PREPARING'
                self.widget = widget
                self.record('preparing', widget=str(widget), python_id=id(widget))
            require(widget is self.widget, 'Intended widget changed during preparation')
            # grid()/Map work may still be queued at entry to the original
            # precondition. Let the existing pump map it without any input.
            if not (self.root.winfo_viewable() and widget.winfo_viewable()):return False
            if self.target is None:
                self.target = self.api.bind_target(int(self.root.winfo_id()))
                grab = self.root.grab_current()
                self.target['local_grab'] = grab is self.root and grab.grab_status() == 'local'
                # No Tk object is passed to the observation thread. It cannot
                # activate, call focus_set, or schedule a callback on Tk.
                def inspect():
                    try:
                        value = self.api.inspect(self.target, deadline)
                    except BaseException as exc:
                        value = exc
                    self.reply.put(value)
                self.worker = threading.Thread(target=inspect, name='F2-native-observation', daemon=True)
                self.worker.start()
                return False
            if self.result is None:
                try:
                    value = self.reply.get_nowait()
                except queue.Empty:
                    return False
                if isinstance(value, BaseException):
                    raise value
                self.result = value
                self.observations.append(value)
                require(self.clock() < deadline, 'Native verification exceeded the deadline')
                require(self.clock() - value['monotonic'] <= .100, 'Stale native target verification')
                self.live(widget)
                self.api.confirm(self.target, value)
                require(self.clock() < deadline and self.clock()-value['monotonic'] <= .100,
                        'Immediate target confirmation exceeded its freshness/deadline budget')
                if value['foreground'] != self.target['top']:
                    self.sent = True
                    try:
                        count, error = self.api.click(value['point'], deadline)
                    except BaseException as exc:
                        raise FocusFailed('SendInput outcome unavailable: '+repr(exc), unsafe_input=True) from exc
                    self.record('SendInput', expected=3, inserted=count, last_error=error)
                    if count != 3:
                        raise FocusFailed('SendInput did not insert the complete mouse sequence',
                                          unsafe_input=count > 1)
            if self.clock() >= deadline:raise FocusFailed('Focus activation deadline exhausted')
            native = self.api.focus_state(self.target)
            if native['foreground'] != self.target['top'] or not native['focus_inside']:
                return False
            self.live(widget)
            if self.clock() >= deadline:raise FocusFailed('Focus verification deadline exhausted')
            if not self.focus_called and (self.sent or self.root.focus_get() is not widget):
                self.focus_called = True
                self.record('ordinary_Tk_focus_set', widget=str(widget))
                widget.focus_set()
            if self.root.focus_get() is not widget:
                return False
            if self.clock() >= deadline:raise FocusFailed('Focus verification deadline exhausted')
            self.verified = True
            self.record('precondition_verified', **native)
            self.disarm()
            return True
        except BaseException as exc:
            if isinstance(exc, FocusFailed) and exc.unsafe_input and self.session is not None:
                self.session.shouldstop = 'Uncertain synthetic mouse-button state; qualification stopped'
            self.record('refused', status=getattr(exc, 'status', 'FAIL'), error=repr(exc),
                        notes=getattr(exc, '__notes__', []))
            self.disarm()
            raise

    def observe(self, widget):
        """No input/focus setter is reachable through this result path."""
        require(self.state == 'DISARMED' and self.verified, 'No verified focus precondition')
        self.live(widget)
        native = self.api.focus_state(self.target)
        return (native['foreground'] == self.target['top'] and native['focus_inside']
                and self.root.focus_get() is widget)

    def disarm(self):
        if self.state != 'DISARMED':
            self.state = 'DISARMED'
            self.record('disarmed')

    def evidence(self):
        return dict(node=self.node, source=self.source, state=self.state,
                    precondition_verified=self.verified, target=self.target,
                    last_native_input=getattr(self.api, 'last_input', None),
                    observations=self.observations, events=self.events,
                    observation_thread_alive=bool(self.worker and self.worker.is_alive()))

    def close(self):
        self.disarm()
        if self.target is not None:
            self.api.unbind_target(self.target)
        if self.worker is not None and self.worker.is_alive():
            if self.session is not None:
                self.session.shouldstop = 'Native observation did not finish; qualification stopped'
            raise FocusBlocked('Native observation thread still active; cleanup unverified')


class Win32API:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        require(sys.platform == 'win32', 'Native Windows input unavailable')
        self.c, self.w = c, w
        self.user = c.WinDLL('user32', use_last_error=True)
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.wts = c.WinDLL('wtsapi32', use_last_error=True)
        self.dwm = c.WinDLL('dwmapi', use_last_error=True)
        class GUI(c.Structure):
            _fields_ = [('cbSize', w.DWORD), ('flags', w.DWORD)] + [
                (n, w.HWND) for n in ('active', 'focus', 'capture', 'menu', 'move', 'caret')
            ] + [('rect', w.RECT)]
        class MOUSE(c.Structure):
            _fields_ = [('dx', w.LONG), ('dy', w.LONG), ('data', w.DWORD),
                        ('flags', w.DWORD), ('time', w.DWORD), ('extra', c.c_size_t)]
        class KEY(c.Structure):
            _fields_ = [('vk', w.WORD), ('scan', w.WORD), ('flags', w.DWORD),
                        ('time', w.DWORD), ('extra', c.c_size_t)]
        class HARD(c.Structure):
            _fields_ = [('message', w.DWORD), ('low', w.WORD), ('high', w.WORD)]
        class PAYLOAD(c.Union):
            _fields_ = [('mouse', MOUSE), ('key', KEY), ('hard', HARD)]
        class INPUT(c.Structure):
            _anonymous_ = ('payload',)
            _fields_ = [('kind', w.DWORD), ('payload', PAYLOAD)]
        self.GUI, self.MOUSE, self.INPUT = GUI, MOUSE, INPUT
        require(c.sizeof(INPUT) == (40 if c.sizeof(c.c_void_p) == 8 else 28), 'Unexpected native INPUT layout')
        self.ENUM = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        signatures = {
            'GetAncestor': ([w.HWND, w.UINT], w.HWND),
            'GetWindowThreadProcessId': ([w.HWND, c.POINTER(w.DWORD)], w.DWORD),
            'GetForegroundWindow': ([], w.HWND),
            'IsWindow': ([w.HWND], w.BOOL), 'IsWindowVisible': ([w.HWND], w.BOOL),
            'IsWindowEnabled': ([w.HWND], w.BOOL), 'IsIconic': ([w.HWND], w.BOOL),
            'GetWindowRect': ([w.HWND, c.POINTER(w.RECT)], w.BOOL),
            'GetClientRect': ([w.HWND, c.POINTER(w.RECT)], w.BOOL),
            'ClientToScreen': ([w.HWND, c.POINTER(w.POINT)], w.BOOL),
            'WindowFromPoint': ([w.POINT], w.HWND),
            'GetGUIThreadInfo': ([w.DWORD, c.POINTER(GUI)], w.BOOL),
            'IsChild': ([w.HWND, w.HWND], w.BOOL),
            'GetAsyncKeyState': ([c.c_int], c.c_short),
            'GetThreadDesktop': ([w.DWORD], w.HANDLE),
            'GetProcessWindowStation': ([], w.HANDLE),
            'OpenInputDesktop': ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            'CloseDesktop': ([w.HANDLE], w.BOOL),
            'GetUserObjectInformationW': ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
            'SetThreadDpiAwarenessContext': ([w.HANDLE], w.HANDLE),
            'GetSystemMetrics': ([c.c_int], c.c_int),
            'SendMessageTimeoutW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT,
                                     w.UINT, c.POINTER(c.c_size_t)], w.LPARAM),
            'SendInput': ([w.UINT, c.POINTER(INPUT), c.c_int], w.UINT),
            'SetPropW': ([w.HWND, w.LPCWSTR, w.HANDLE], w.BOOL),
            'GetPropW': ([w.HWND, w.LPCWSTR], w.HANDLE),
            'RemovePropW': ([w.HWND, w.LPCWSTR], w.HANDLE),
            'GetClassNameW': ([w.HWND, w.LPWSTR, c.c_int], c.c_int),
            'EnumWindows': ([self.ENUM, w.LPARAM], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            f = getattr(self.user, name); f.argtypes, f.restype = args, result
        self.kernel.GetCurrentThreadId.argtypes = []; self.kernel.GetCurrentThreadId.restype = w.DWORD
        self.kernel.ProcessIdToSessionId.argtypes = [w.DWORD, c.POINTER(w.DWORD)]
        self.kernel.ProcessIdToSessionId.restype = w.BOOL
        self.wts.WTSQuerySessionInformationW.argtypes = [w.HANDLE, w.DWORD, c.c_int,
                                                        c.POINTER(c.c_void_p), c.POINTER(w.DWORD)]
        self.wts.WTSQuerySessionInformationW.restype = w.BOOL
        self.wts.WTSFreeMemory.argtypes = [c.c_void_p]; self.wts.WTSFreeMemory.restype = None
        self.dwm.DwmGetWindowAttribute.argtypes = [w.HWND, w.DWORD, c.c_void_p, w.DWORD]
        self.dwm.DwmGetWindowAttribute.restype = w.LONG

    def checked(self, value):
        if not value:
            raise FocusBlocked('Win32 observation denied: ' + str(self.c.WinError(self.c.get_last_error())))
        return value

    @contextmanager
    def dpi(self):
        previous = self.checked(self.user.SetThreadDpiAwarenessContext(self.w.HANDLE(-4)))
        primary = None
        try:
            yield
        except BaseException as exc:
            primary = exc
            raise
        finally:
            try:self.checked(self.user.SetThreadDpiAwarenessContext(previous))
            except BaseException as exc:
                if primary is None:raise
                primary.add_note('Native DPI observation cleanup also failed: '+repr(exc))

    def owner(self, hwnd):
        pid = self.w.DWORD()
        tid = self.checked(self.user.GetWindowThreadProcessId(hwnd, self.c.byref(pid)))
        return pid.value, tid

    def marker(self, target):
        for hwnd in {target['client'], target['top']}:
            require(self.user.IsWindow(hwnd) and self.user.GetPropW(hwnd, target['property']) == target['token'],
                    'Destroyed or reused native window identity')
            require(self.owner(hwnd) == (target['pid'], target['thread']), 'Native window owner changed')
        require(self.user.GetAncestor(target['client'], 2) == target['top'], 'Native root/client mismatch')

    def bind_target(self, client):
        top = self.checked(self.user.GetAncestor(client, 2))
        pid, tid = self.owner(top)
        require(pid == os.getpid() and tid == self.kernel.GetCurrentThreadId(), 'Wrong root process/GUI thread')
        require(self.owner(client) == (pid, tid), 'Wrong Tk client owner')
        target = dict(client=client, top=top, pid=pid, thread=tid,
                      property='ChronicleF2-' + uuid4().hex, token=id(self))
        try:
            for hwnd in {client, top}:
                self.checked(self.user.SetPropW(hwnd, target['property'], target['token']))
        except BaseException as primary:
            try:self.unbind_target(target)
            except BaseException as secondary:primary.add_note('Native identity cleanup also failed: '+repr(secondary))
            raise
        return target

    def unbind_target(self, target):
        for hwnd in {target['client'], target['top']}:
            if self.user.GetPropW(hwnd, target['property']) == target['token']:
                self.checked(self.user.RemovePropW(hwnd, target['property']))

    def object_name(self, handle):
        data = self.c.create_unicode_buffer(256); needed = self.w.DWORD()
        self.checked(self.user.GetUserObjectInformationW(handle, 2, data, self.c.sizeof(data), self.c.byref(needed)))
        return data.value

    def desktop(self, tid):
        station = self.checked(self.user.GetProcessWindowStation())
        require(self.object_name(station) == 'WinSta0', 'Noninteractive window station')
        # USEROBJECTFLAGS: BOOL inherit, BOOL reserved, DWORD flags (WSF_VISIBLE).
        flags = (self.w.DWORD * 3)(); needed = self.w.DWORD()
        self.checked(self.user.GetUserObjectInformationW(station, 1, flags, self.c.sizeof(flags), self.c.byref(needed)))
        require(flags[2] & 1, 'Window station is not visible')
        name = self.object_name(self.checked(self.user.GetThreadDesktop(tid)))
        handle = self.checked(self.user.OpenInputDesktop(0, False, 1))  # DESKTOP_READOBJECTS only
        try:
            input_name = self.object_name(handle)
        finally:
            self.checked(self.user.CloseDesktop(handle))
        require(name == input_name == 'Default', 'Input desktop is locked, changed or not the normal desktop')
        return dict(station='WinSta0', thread_desktop=name, input_desktop=input_name)

    def session(self):
        c, w = self.c, self.w
        require(sys.getwindowsversion().build >= 22000, 'Windows 11 is required')
        sid = w.DWORD()
        self.checked(self.kernel.ProcessIdToSessionId(os.getpid(), c.byref(sid)))
        require(sid.value != 0, 'Session 0 is not interactive')
        pointer, size = c.c_void_p(), w.DWORD()
        class LEVEL1(c.Structure):
            _fields_ = [('session', w.DWORD), ('state', c.c_int), ('flags', w.LONG),
                        ('station', w.WCHAR*33), ('user', w.WCHAR*21), ('domain', w.WCHAR*18)] + [
                            (name, c.c_longlong) for name in ('logon', 'connect', 'disconnect', 'last_input', 'current')
                        ] + [(name, w.DWORD) for name in ('in_bytes', 'out_bytes', 'in_frames', 'out_frames', 'in_compressed', 'out_compressed')]
        class EX(c.Structure):
            _fields_ = [('level', w.DWORD), ('data', LEVEL1)]
        self.checked(self.wts.WTSQuerySessionInformationW(None, sid, 25, c.byref(pointer), c.byref(size)))
        try:
            require(size.value >= c.sizeof(EX), 'Incomplete session-lock observation')
            value = c.cast(pointer, c.POINTER(EX)).contents
            require(value.level == 1 and value.data.session == sid.value, 'Unexpected session observation identity')
            require(value.data.state == 0 and value.data.flags == 1,
                    'Session is locked or disconnected: '+repr(dict(session_id=sid.value,
                        connection_state=value.data.state, session_flags=value.data.flags)))
            return dict(session_id=sid.value, connection_state=value.data.state, session_flags=value.data.flags)
        finally:
            self.wts.WTSFreeMemory(pointer)

    def keys(self):
        held = [key for key in (1, 2, 4, 5, 6, 0x10, 0x11, 0x12, 0x5b, 0x5c)
                if self.user.GetAsyncKeyState(key) & 0x8000]
        require(not held, 'Mouse buttons or keyboard modifiers are already held: ' + repr(held))

    def gui(self, tid, target=None):
        info = self.GUI(); info.cbSize = self.c.sizeof(info)
        self.checked(self.user.GetGUIThreadInfo(tid, self.c.byref(info)))
        capture_ok = not info.capture or bool(target and target.get('local_grab') and
            (info.capture in (target['top'], target['client']) or self.user.IsChild(target['client'], info.capture)))
        require(capture_ok and not info.menu and not info.move and not (info.flags & 0x1e),
                'Unexpected mouse capture or menu/move operation')
        return info

    def rect(self, top):
        value = self.w.RECT()
        self.checked(self.user.GetWindowRect(top, self.c.byref(value)))
        return (value.left, value.top, value.right, value.bottom)

    def geometry(self, target):
        top = target['top']
        require(self.user.IsWindowVisible(top) and self.user.IsWindowEnabled(top)
                and self.user.IsWindowVisible(target['client']) and self.user.IsWindowEnabled(target['client'])
                and not self.user.IsIconic(top), 'Root/client is hidden, disabled or minimized')
        return self.rect(top)

    def competing(self, target, point):
        """Conservative z-order occlusion, including disabled/transparent covers."""
        rows, errors = [], []
        visited = 0
        @self.ENUM
        def visit(hwnd, unused):
            nonlocal visited
            try:
                visited += 1
                require(visited <= 256, 'Window enumeration exceeds its safety bound')
                if self.user.IsWindowVisible(hwnd):
                    rectangle = self.rect(hwnd)
                    pid, tid = self.owner(hwnd)
                    rows.append(dict(hwnd=hwnd, pid=pid, thread=tid, rectangle=rectangle))
                    if hwnd == target['top']:return False
                    if point is not None:
                        x, y = point
                        l, t, r, b = rectangle
                        require(not (l <= x < r and t <= y < b), 'Visible competing window obstructs the caption')
                return True
            except BaseException as exc:
                errors.append(exc)
                return False
        self.user.EnumWindows(visit, 0)
        if errors:raise errors[0]
        require(rows and rows[-1]['hwnd'] == target['top'], 'Root absent from native z-order observation')
        return rows

    def inspect(self, target, deadline):
        require(self.kernel.GetCurrentThreadId() != target['thread'], 'Hit testing must not use the Tk input queue')
        with self.dpi():
            self.marker(target)
            environment = {**self.session(), **self.desktop(target['thread'])}
            self.keys(); own_gui = self.gui(target['thread'], target)
            rectangle = self.geometry(target)
            cloaked = self.w.DWORD()
            require(self.dwm.DwmGetWindowAttribute(target['top'], 14, self.c.byref(cloaked), self.c.sizeof(cloaked)) == 0
                    and not cloaked.value, 'Root cloaking state is unavailable or cloaked')
            foreground = self.user.GetForegroundWindow()
            foreground_owner = self.owner(foreground) if foreground else None
            if foreground:
                self.gui(foreground_owner[1], target if foreground == target['top'] else None)
                name = self.c.create_unicode_buffer(256)
                self.checked(self.user.GetClassNameW(foreground, name, len(name)))
                require(name.value not in ('#32770', '#32768'), 'Unexpected foreground dialog/menu')
                require(foreground == target['top'] or foreground_owner[0] != target['pid'],
                        'Different top-level in the same process is foreground')
            point = None
            if foreground != target['top']:
                require(not own_gui.capture, 'Mouse capture makes ordinary caption activation unsafe')
                origin = self.w.POINT(0, 0)
                self.checked(self.user.ClientToScreen(target['client'], self.c.byref(origin)))
                left, upper, right, lower = rectangle
                require(right - left > 100 and upper < origin.y < lower, 'No safe native caption geometry')
                point = (left + (right-left)//2, (upper + origin.y)//2)
                require(all(-32768 <= v <= 32767 for v in point), 'Caption outside bounded hit-test coordinates')
                require(self.user.WindowFromPoint(self.w.POINT(*point)) == target['top'], 'Caption is obstructed')
                remaining = min(50, int((deadline-time.monotonic())*1000))
                require(remaining > 0, 'No remaining native hit-test budget')
                answer = self.c.c_size_t()
                packed = (point[0] & 0xffff) | ((point[1] & 0xffff) << 16)
                # This GUI-free observation thread never creates windows or
                # attaches input queues. Tk continues pumping while it waits.
                self.checked(self.user.SendMessageTimeoutW(target['top'], 0x84, 0, packed,
                                                           0x2 | 0x20, remaining, self.c.byref(answer)))
                require(answer.value == 2, 'Input target is not HTCAPTION')
            competitors = self.competing(target, point)
            return dict(monotonic=time.monotonic(), environment=environment, rectangle=rectangle,
                        competing_windows=competitors,
                        foreground=foreground, foreground_owner=foreground_owner, point=point,
                        client=target['client'], top=target['top'], pid=target['pid'], thread=target['thread'])

    def confirm(self, target, value):
        """Immediate message-free revalidation; no SendMessage on the Tk thread."""
        with self.dpi():
            self.marker(target); self.desktop(target['thread']); self.keys()
            own_gui = self.gui(target['thread'], target)
            require(self.geometry(target) == value['rectangle'], 'Target geometry changed after hit testing')
            require(self.user.GetForegroundWindow() == value['foreground'], 'Foreground changed after verification')
            if value['foreground']:
                self.gui(self.owner(value['foreground'])[1], target if value['foreground'] == target['top'] else None)
            if value['point'] is not None:
                require(not own_gui.capture, 'Mouse capture changed before input')
                require(self.user.WindowFromPoint(self.w.POINT(*value['point'])) == target['top'], 'Input target changed')
                self.competing(target, value['point'])

    def focus_state(self, target):
        self.marker(target); self.desktop(target['thread'])
        info = self.gui(target['thread'], target)
        return dict(foreground=self.user.GetForegroundWindow(),
                    focus_hwnd=info.focus, active_hwnd=info.active,
                    focus_inside=bool(info.active == target['top'] and info.focus and
                                      (info.focus == target['client'] or self.user.IsChild(target['client'], info.focus))))

    def click(self, point, deadline):
        with self.dpi():
            x, y = point
            left, upper, width, height = [self.user.GetSystemMetrics(i) for i in (76, 77, 78, 79)]
            require(width > 1 and height > 1 and left <= x < left+width and upper <= y < upper+height,
                    'Unsafe virtual-screen input coordinates')
            sequence = (self.INPUT * 3)()
            sequence[0].mouse = self.MOUSE(round((x-left)*65535/(width-1)), round((y-upper)*65535/(height-1)),
                                            0, 0x8000 | 0x4000 | 1, 0, 0)
            sequence[1].mouse.flags = 2
            sequence[2].mouse.flags = 4
            require(time.monotonic() < deadline, 'Input deadline exhausted before SendInput')
            self.c.set_last_error(0)
            count = self.user.SendInput(3, sequence, self.c.sizeof(self.INPUT))
            error = self.c.get_last_error()
            # Record the actual observation even if restoring the native DPI
            # context subsequently fails; the driver then stops qualification.
            self.last_input = dict(inserted=count, last_error=error)
            return count, error
