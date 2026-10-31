"""Bounded observations; six Windows preconditions have a one-shot input driver."""
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
    result['observation_errors']=[]
    if sys.platform=='win32':
        # A destroyed interpreter cannot supply winfo_id(). Do not let final
        # diagnostics replace the assertion that caused its destruction.
        try:
            if not root.winfo_exists():raise tk.TclError('Tk root destroyed')
            result['foreground']=windows_foreground(root)
            if result['foreground'].get('observation_error'):
                result['observation_errors'].append(result['foreground']['observation_error'])
        except Exception as exc:
            result['foreground']=dict(observation_error=repr(exc))
            result['observation_errors'].append(repr(exc))
    return result


def wait_observed(root, predicate, *, phase, widgets=(), timeout=8000, foreground=False):
    from test_app import pump
    deadline=time.monotonic()+timeout/1000
    timeline=[]
    bindings=[]
    primary=None
    secondary=[]
    driver=getattr(root,'_f2_focus_driver',None)
    prepared=False
    try:
        initial=snapshot(root,widgets)
        timeline.append(dict(event='begin',state=initial))
        if initial.get('observation_errors'):
            raise RuntimeError('Initial Tk observation is uncertain: '+repr(initial['observation_errors']))
        if driver is not None and foreground:
            from win32_focus import NODES, FocusBlocked
            if phase!=NODES[driver.node][0] or len(widgets)!=1:
                driver.disarm()
                raise FocusBlocked('Unauthorized focus-precondition phase or target')
        for event in ('<FocusIn>','<FocusOut>','<Map>','<Unmap>'):
            def record(value, name=event):
                if len(timeline)<100:
                    timeline.append(dict(event=name,widget=str(value.widget),monotonic=time.monotonic()))
            bindings.append((event,root.bind(event,record,add='+')))
        def ready():
            nonlocal prepared
            if driver is not None:
                from win32_focus import NODES
                if foreground:
                    if not prepared:
                        if not driver.prepare(widgets[0],deadline):return False
                        prepared=True
                    if not driver.observe(widgets[0]):return False
                elif phase==NODES[driver.node][1]:
                    # Modal-return checking has no route to prepare(),
                    # SendInput or the driver's ordinary focus_set().
                    if not driver.observe(widgets[0]):return False
            if foreground and sys.platform=='win32':
                observed=windows_foreground(root)
                if not (observed['owned'] and observed['root_is_foreground']):return False
            return predicate()
        remaining=int((deadline-time.monotonic())*1000)
        if remaining<=0:raise AssertionError('Focus observation deadline exhausted')
        pump(root,ready,timeout=remaining)
    except BaseException as exc:
        primary=exc
        exc.add_note('Tk phase '+phase+'; observation failed during '+
                     ('PRECONDITION' if phase.startswith('PRECONDITION') else 'RESULT')+
                     '; initial foreground is a prerequisite, not a modal-return assertion')
        raise
    finally:
        if driver is not None and foreground:
            try:
                if not prepared:
                    driver.record('precondition_incomplete',status='FAIL' if driver.sent else 'BLOCKED',
                                  error=repr(primary))
                driver.disarm()
            except BaseException as exc:secondary.append(exc)
        try:
            final=snapshot(root,widgets)
            timeline.append(dict(event='end',state=final))
            if final.get('observation_errors'):
                secondary.append(RuntimeError('Final Tk observation is uncertain: '+repr(final['observation_errors'])))
        except BaseException as exc:
            secondary.append(exc)
            timeline.append(dict(event='end',observation_error=repr(exc)))
        try:
            print('CHRONICLE_TK_OBSERVATION '+json.dumps(dict(phase=phase,
                observation_kind='PRECONDITION' if phase.startswith('PRECONDITION') else 'RESULT',
                timeline=timeline,driver=driver.evidence() if driver is not None else None),default=str),flush=True)
        except BaseException as exc:secondary.append(exc)
        for event,token in bindings:
            try:root.unbind(event,token)
            except BaseException as exc:secondary.append(exc)
        if primary is not None:
            for exc in secondary:primary.add_note('Tk observation also failed: '+repr(exc))
        elif secondary:
            failure=RuntimeError('Tk observation diagnostics incomplete')
            for exc in secondary:failure.add_note(repr(exc))
            raise failure from secondary[0]
