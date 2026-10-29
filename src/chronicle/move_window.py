"""One owned, frozen subtree/destination review; B2 remains the movement authority."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk

from .history_window import widget_live
from .movement import snapshot, plan


class MoveWindow:
    def __init__(self, owner, task_id, state):
        self.owner, self.task_id, self.state = owner, task_id, deepcopy(state)
        self.disposed = self.presented = False
        self.phase = 'reviewing'
        self.request = self.token = self.outcome = None
        self.arguments = None
        self.return_focus = owner.root.focus_get()
        tasks = {t['task_id']:t for t in self.state['tasks']}
        source = tasks[task_id]
        members = snapshot(self.state['tasks'],task_id)
        self.source_path = owner._task_path_label(task_id,self.state)
        self.destinations = {}
        self.window = tk.Toplevel(owner.root)
        try:
            self.window.withdraw()
            self.window.title('Move / Reparent')
            self.window.transient(owner.root)
            self.window.geometry('940x540')
            self.window.columnconfigure(0,weight=1)
            self.window.rowconfigure(1,weight=1)
            ttk.Label(self.window,text=f"Source: {self.source_path}\nTask UUID: {task_id}\nDescendant tasks: {len(members)-1}",wraplength=900).grid(row=0,column=0,padx=12,pady=10,sticky='w')
            holder=ttk.Frame(self.window);holder.grid(row=1,column=0,padx=12,sticky='nsew')
            holder.columnconfigure(0,weight=1);holder.rowconfigure(0,weight=1)
            self.tree=ttk.Treeview(holder,columns=('uuid','eligibility'),selectmode='browse')
            self.tree.heading('#0',text='Reviewed destination — full path')
            self.tree.heading('uuid',text='Destination UUID')
            self.tree.heading('eligibility',text='Advisory eligibility')
            self.tree.column('#0',width=420);self.tree.column('uuid',width=280);self.tree.column('eligibility',width=190)
            self.tree.grid(row=0,column=0,sticky='nsew')
            scroll=ttk.Scrollbar(holder,orient='vertical',command=self.tree.yview)
            scroll.grid(row=0,column=1,sticky='ns');self.tree.configure(yscrollcommand=scroll.set)
            projects={p['project_id']:p for p in self.state['projects']}
            destinations=[(owner.project_row(None),None,None,'Unassigned')]
            destinations += [(owner.project_row(p['project_id']),None,p['project_id'],f"{p['name']} ({p['project_id']})") for p in projects.values()]
            destinations += [(owner.task_row(t['task_id']),t['task_id'],t['project_id'],owner._task_path_label(t['task_id'],self.state)) for t in self.state['tasks']]
            for row,parent,group,label in destinations:
                args=dict(task_id=task_id,expected_version=source['version'],
                          source_parent_task_id=source['parent_task_id'],source_project_id=source['project_id'],
                          destination_parent_task_id=parent,destination_project_id=group,
                          expected_destination_parent_version=tasks[parent]['version'] if parent else None,
                          expected_destination_project_version=projects[group]['version'] if group else None,
                          reviewed_subtree=deepcopy(members))
                reason=None;unchanged=False
                try:
                    _,result=plan(self.state['tasks'],self.state['projects'],self.state['active'],args)
                    unchanged=not result['changed_tasks']
                except ValueError as exc:reason=str(exc)
                self.destinations[row]=dict(arguments=args,label=label,reason=reason,unchanged=unchanged)
                self.tree.insert('','end',iid=row,text=label,values=(parent or group or 'Virtual Unassigned',reason or ('Unchanged — same destination' if unchanged else 'Eligible')))
            self.tree.bind('<<TreeviewSelect>>',self.selected)
            self.status=ttk.Label(self.window,text='Select a destination to review source → destination. No rows move before commitment.',wraplength=900)
            self.status.grid(row=2,column=0,padx=12,pady=10,sticky='w')
            bar=ttk.Frame(self.window);bar.grid(row=3,column=0,padx=12,pady=10,sticky='w')
            self.confirm_button=ttk.Button(bar,text='Confirm Move',command=self.submit)
            self.retry_button=ttk.Button(bar,text='Retry/Reconcile exact Move',command=self.retry)
            self.exit_button=ttk.Button(bar,text='Exit despite unresolved Move',command=owner.exit_move_uncertain)
            self.close_button=ttk.Button(bar,text='Cancel',command=self.close)
            for button in (self.confirm_button,self.retry_button,self.exit_button,self.close_button):button.pack(side='left',padx=4)
            self.window.protocol('WM_DELETE_WINDOW',self.close)
            self.window.bind('<Escape>',lambda event:self.close())
            self.window.bind('<Map>',self.mapped,add='+')
            self.window.bind('<Destroy>',self.destroyed,add='+')
        except BaseException as primary:
            try:self.window.destroy()
            except BaseException as secondary:primary.add_note(f'Move construction cleanup failed: {secondary!r}')
            raise

    def current(self):
        return (not self.disposed and self.owner.alive and self.owner.movement is self
                and self.owner.editor is self.window and widget_live(self.window))

    def mutation_allowed(self):
        return (self.current() and self.presented and self.phase=='reviewing'
                and self.window.grab_current() is self.window and self.window.grab_status()=='local')

    def restore_modal(self):
        if not self.current() or not self.presented:return False
        grab=self.window.grab_current()
        if grab is not None and (grab is not self.window or grab.grab_status()!='local'):return False
        if grab is None:self.window.grab_set();self.close_button.focus_set()
        return True

    def mapped(self,event):
        if event.widget is not self.window or self.presented or not self.current():return
        try:
            if self.window.grab_current() is not None:raise ValueError('Move cannot replace another grab')
            self.window.grab_set();self.close_button.focus_set();self.presented=True
            self.owner._controls()
        except Exception as exc:
            self.close(force=True);self.owner.status.configure(text=f'Unable to present Move: {exc}');self.owner._diagnose(exc)

    def selected(self,event=None):
        if not self.current() or self.phase!='reviewing':return
        rows=self.tree.selection();destination=self.destinations.get(rows[0]) if rows else None
        self.arguments=None
        if destination:
            text=f"Source: {self.source_path}\nDestination: {destination['label']}\n"
            if destination['reason']:text+='Move unavailable: '+destination['reason']
            else:
                self.arguments=deepcopy(destination['arguments'])
                text+=('Same destination: unchanged; no receipt or structural write.' if destination['unchanged'] else 'Move this complete reviewed subtree. Existing work and timer identities stay unchanged.')
            self.status.configure(text=text)
        self.controls()

    def submit(self):
        if not self.mutation_allowed() or self.arguments is None or not self.owner.can_mutate(origin=self):return False
        return self.owner._submit('move_task_branch',_origin=self,**deepcopy(self.arguments))

    def retry(self):
        if not self.current() or self.phase!='unverified' or self.owner.pending is not self.request:return False
        return self.owner.retry()

    def record_result(self,result):
        self.outcome=result
        self.phase='unverified' if result.status=='unverified' else 'complete' if result.status in ('committed','unchanged') else 'failed'
        if not self.current():return
        text=('Move not verified; retain this exact request and Retry/Reconcile, or explicitly exit.' if self.phase=='unverified' else
              'Move committed. Updated hierarchy is read from the worker.' if result.status=='committed' else
              'Unchanged: same destination. No structural change or receipt.' if result.status=='unchanged' else
              f'Move did not commit: {result.error or result.status}. Close and obtain a fresh review.')
        self.status.configure(text=text);self.controls()

    def controls(self):
        if not self.current():return
        self.confirm_button.configure(state='normal' if self.phase=='reviewing' and self.arguments is not None and not self.owner.closing else 'disabled')
        self.close_button.configure(text='Close' if self.phase in ('complete','failed') else 'Cancel',state='disabled' if self.phase in ('executing','unverified') else 'normal')
        self.retry_button.configure(state='normal' if self.phase=='unverified' and not self.owner._worker_stopped else 'disabled')
        self.exit_button.configure(state='normal' if self.phase=='unverified' and not self.owner.executing else 'disabled')

    def close(self,*,force=False):
        if not self.current() or not force and self.phase in ('executing','unverified'):return False
        grab=self.window.grab_current()
        if grab is not None and grab is not self.window and not force:return False
        if grab is self.window:self.window.grab_release()
        self.window.destroy()
        if self.owner.alive and not self.owner.closing and self.owner.root.grab_current() is None:
            focus=self.return_focus
            (focus if widget_live(focus) and focus.winfo_toplevel() is self.owner.root else self.owner.root).focus_set()
        return True

    def destroyed(self,event):
        if event.widget is self.window:
            self.disposed=True
            if self.owner.movement is self:self.owner.movement=None
            if self.owner.editor is self.window:self.owner.editor=None
            if self.owner.alive:self.owner._controls()
