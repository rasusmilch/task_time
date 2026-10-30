"""Bounded test diagnostics. Never activate another window or force focus."""
import json
import os
import sys
import time
import tkinter as tk


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
    if sys.platform=='win32':
        import ctypes as c
        from ctypes import wintypes as w
        user=c.WinDLL('user32',use_last_error=True)
        user.GetForegroundWindow.argtypes=[];user.GetForegroundWindow.restype=w.HWND
        user.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
        user.GetWindowThreadProcessId.restype=w.DWORD
        hwnd=user.GetForegroundWindow();pid=w.DWORD()
        user.GetWindowThreadProcessId(hwnd,c.byref(pid))
        result['foreground']=dict(hwnd=hwnd,pid=pid.value,owned=pid.value==os.getpid())
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
            if foreground and sys.platform=='win32' and not snapshot(root)['foreground']['owned']:
                return False
            return predicate()
        pump(root,ready,timeout=timeout)
    except BaseException as exc:
        exc.add_note('Tk phase '+phase+'; initial foreground is a prerequisite, not a modal-return assertion')
        raise
    finally:
        timeline.append(dict(event='end',state=snapshot(root,widgets)))
        print('CHRONICLE_TK_OBSERVATION '+json.dumps(dict(phase=phase,timeline=timeline),default=str),flush=True)
        for event,token in bindings:
            try: root.unbind(event,token)
            except tk.TclError: pass
