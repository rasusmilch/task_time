"""Bounded test diagnostics. Never activate another window or force focus."""
import json
import os
import sys
import time
import tkinter as tk


def windows_foreground(root, user=None):
    """Read-only HWND observation; Tk's client is not its native top-level."""
    import ctypes as c
    from ctypes import wintypes as w
    if user is None:user=c.WinDLL('user32',use_last_error=True)
    user.GetForegroundWindow.argtypes=[];user.GetForegroundWindow.restype=w.HWND
    user.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
    user.GetWindowThreadProcessId.restype=w.DWORD
    user.GetAncestor.argtypes=[w.HWND,w.UINT];user.GetAncestor.restype=w.HWND
    client=int(root.winfo_id())
    top=user.GetAncestor(client,2)  # GA_ROOT: the containing Windows top-level.
    foreground=user.GetForegroundWindow();pid=w.DWORD()
    user.GetWindowThreadProcessId(foreground,c.byref(pid))
    return dict(client_hwnd=client,root_hwnd=top,hwnd=foreground,pid=pid.value,
        owned=pid.value==os.getpid(),root_is_foreground=bool(top and foreground and top==foreground),
        observation_error=None if top else 'Native root HWND unavailable')


def snapshot(root, widgets=()):
    def safe(call):
        try: return call()
        except (tk.TclError, KeyError, AttributeError) as exc: return repr(exc)
    def identity(widget):
        return None if widget is None else dict(path=str(widget),python_id=id(widget),
            path_exists=safe(widget.winfo_exists),
            live=safe(lambda:bool(widget.winfo_exists()) and root.nametowidget(str(widget)) is widget),mapped=safe(widget.winfo_ismapped),
            viewable=safe(widget.winfo_viewable),manager=safe(widget.winfo_manager),
            top=safe(lambda:str(widget.winfo_toplevel())),
            grid=safe(lambda:widget.grid_info()),geometry=safe(widget.winfo_geometry))
    grab=safe(root.grab_current)
    result=dict(monotonic=time.monotonic(),root=identity(root),
        state=safe(root.state),focus=identity(safe(root.focus_get)) if not isinstance(safe(root.focus_get),str) else safe(root.focus_get),
        grab=identity(grab) if not isinstance(grab,str) else grab,
        grab_status=safe(grab.grab_status) if grab is not None and not isinstance(grab,str) else None,
        widgets=[identity(w) for w in widgets])
    if sys.platform=='win32':result['foreground']=windows_foreground(root)
    return result


def wait_observed(root, predicate, *, phase, widgets=(), timeout=8000, foreground=False):
    from test_app import pump
    timeline=[dict(event='begin',state=snapshot(root,widgets))]
    bindings=[]
    try:
        for event in ('<FocusIn>','<FocusOut>','<Map>','<Unmap>'):
            def record(value, name=event):
                if len(timeline)<100:
                    timeline.append(dict(event=name,widget=str(value.widget),monotonic=time.monotonic()))
            bindings.append((event,root.bind(event,record,add='+')))
        def ready():
            if foreground and sys.platform=='win32':
                observed=windows_foreground(root)
                if not (observed['owned'] and observed['root_is_foreground']):return False
            return predicate()
        pump(root,ready,timeout=timeout)
    except BaseException as exc:
        exc.add_note('Tk phase '+phase+'; observation failed during '+
                     ('PRECONDITION' if phase.startswith('PRECONDITION') else 'RESULT')+
                     '; initial foreground is a prerequisite, not a modal-return assertion')
        raise
    finally:
        timeline.append(dict(event='end',state=snapshot(root,widgets)))
        print('CHRONICLE_TK_OBSERVATION '+json.dumps(dict(phase=phase,observation_kind='PRECONDITION' if phase.startswith('PRECONDITION') else 'RESULT',timeline=timeline),default=str),flush=True)
        for event,token in bindings:
            try: root.unbind(event,token)
            except tk.TclError: pass
