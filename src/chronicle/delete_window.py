"""Owned Delete preview/typed confirmation; accepted requests belong to ChronicleApp."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk

from .history_window import widget_live
from .records import Outcome, canonical


UNCERTAIN = ('Delete outcome is uncertain. Do not retry. Inspect current presence, then exit and reopen. '
             'Current absence is not historical proof of which request removed the item.')


class DeleteWindow:
    def __init__(self, owner, entity, key, origin):
        self.owner, self.entity, self.key, self.origin = owner, entity, key, origin
        self.disposed = self.presented = False
        self.phase = 'loading'
        self.review = self.preview_token = self.request = self.token = self.outcome = None
        self.return_grab, self.return_focus = owner.root.grab_current(), owner.root.focus_get()
        self.window = tk.Toplevel(owner.root)
        try:
            self.window.withdraw()
            self.window.title('Delete unused ' + entity)
            self.window.transient(owner.root)
            self.window.geometry('850x540')
            self.window.columnconfigure(0, weight=1)
            self.window.rowconfigure(1, weight=1)
            self.context = ttk.Label(self.window, text='Loading complete authoritative deletion review…', wraplength=810)
            self.context.grid(row=0, column=0, padx=12, pady=8, sticky='w')
            holder = ttk.Frame(self.window)
            holder.grid(row=1, column=0, sticky='nsew', padx=12)
            holder.columnconfigure(0, weight=1); holder.rowconfigure(0, weight=1)
            self.tree = ttk.Treeview(holder, columns=('uuid', 'version', 'archive'), selectmode='browse')
            self.tree.heading('#0', text='Complete selected hierarchy')
            for key, label in (('uuid','UUID'),('version','Version'),('archive','Explicit archive')):
                self.tree.heading(key,text=label)
            self.tree.column('uuid',width=285); self.tree.column('version',width=60); self.tree.column('archive',width=110)
            self.tree.grid(row=0,column=0,sticky='nsew')
            scroll=ttk.Scrollbar(holder,orient='vertical',command=self.tree.yview)
            scroll.grid(row=0,column=1,sticky='ns');self.tree.configure(yscrollcommand=scroll.set)
            self.status=ttk.Label(self.window,text='',wraplength=810)
            self.status.grid(row=2,column=0,padx=12,pady=8,sticky='w')
            ttk.Label(self.window,text='Delete permanently removes this unused structure. It cannot be undone.').grid(row=3,column=0,padx=12,sticky='w')
            ttk.Label(self.window,text='Type exactly DELETE to confirm the frozen scope:').grid(row=4,column=0,padx=12,sticky='w')
            self.confirmed=tk.StringVar(self.window,'')
            self.entry=ttk.Entry(self.window,textvariable=self.confirmed,width=30)
            self.entry.grid(row=5,column=0,padx=12,pady=6,sticky='w')
            self.entry.bind('<KeyRelease>',lambda event:self.controls())
            bar=ttk.Frame(self.window);bar.grid(row=6,column=0,padx=12,pady=8,sticky='w')
            self.delete_button=ttk.Button(bar,text='Delete',command=self.submit)
            self.refresh_button=ttk.Button(bar,text='New preview',command=self.refresh)
            self.inspect_button=ttk.Button(bar,text='Inspect current state',command=owner.inspect_delete_state)
            self.exit_button=ttk.Button(bar,text='Exit and reopen',command=owner.exit_delete_uncertain)
            self.close_button=ttk.Button(bar,text='Cancel',command=self.close)
            for button in (self.delete_button,self.refresh_button,self.inspect_button,self.exit_button,self.close_button):button.pack(side='left',padx=4)
            self.window.protocol('WM_DELETE_WINDOW',self.close)
            self.window.bind('<Escape>',lambda event:self.close())
            self.window.bind('<Map>',self.mapped,add='+')
            self.window.bind('<Destroy>',self.destroyed,add='+')
        except BaseException as primary:
            try:self.window.destroy()
            except BaseException as secondary:primary.add_note(f'Delete construction cleanup failed: {secondary!r}')
            raise

    def current(self):
        return (not self.disposed and self.owner.alive and self.owner.deletion is self
                and self.owner.editor is self.window and widget_live(self.window))

    def mutation_allowed(self):
        return (self.current() and self.presented and self.window.grab_current() is self.window
                and self.window.grab_status()=='local' and self.phase=='ready' and self.review is not None and self.review['eligible'])

    def restore_modal(self):
        if not self.current() or not self.presented:return False
        grab=self.window.grab_current()
        if grab is not None and (grab is not self.window or grab.grab_status()!='local'):return False
        if grab is None:
            self.window.grab_set();self.close_button.focus_set()
        return True

    def mapped(self,event):
        if event.widget is not self.window or self.presented or not self.current():return
        try:
            grab=self.window.grab_current()
            if grab is not None and (grab is not self.owner.root or grab.grab_status()!='local'):
                raise ValueError('Delete cannot replace an unrelated or global grab')
            self.window.grab_set();self.close_button.focus_set();self.presented=True
            self.owner._controls();self.refresh()
        except Exception as primary:
            try:self.close(force=True)
            except Exception as secondary:primary.add_note(f'Delete launch cleanup failed: {secondary!r}')
            self.owner.status.configure(text=f'Unable to open Delete: {primary}');self.owner._diagnose(primary)

    def refresh(self):
        if not self.current() or not self.presented or self.phase in ('executing','unverified') or self.owner.pending is not None:return False
        self.phase='loading';self.review=None;self.confirmed.set('');self.controls()
        try:
            self.preview_token=self.owner._delete_read(self,'delete_preview')
            self.status.configure(text='Reading complete scope and administrative closure…')
            return True
        except Exception as exc:
            self.phase='failed';self.status.configure(text=f'Unable to read Delete preview: {exc}');self.controls();return False

    def receive(self,token,value):
        if not self.current() or token!=self.preview_token or self.phase!='loading':return
        self.preview_token=None
        if isinstance(value,Outcome):
            self.phase='failed';self.status.configure(text=f'Preview unavailable: {value.error}');self.controls();return
        if (value.get('dataset_id')!=self.owner.dataset_id or value.get('entity_type')!=self.entity or value.get('entity_id')!=self.key):
            self.phase='failed';self.status.configure(text='Rejected preview from another dataset or selection.');self.controls();return
        canonical(value);self.review=deepcopy(value);self.phase='ready' if value['eligible'] else 'blocked'
        selected=value['selected']
        self.context.configure(text=f"{self.entity}: {selected['name']}\nUUID: {self.key}\nProjects: {value['project_count']}    Tasks: {value['task_count']}    Administrative requests: {len(value['retire_receipts'])}\nExplicit archive: {bool(selected['is_archived'])}; effective archive: {value['effective_archived']}")
        self.tree.delete(*self.tree.get_children())
        if self.entity=='project':self.tree.insert('','end',iid='project:'+self.key,text=selected['name'],values=(self.key,selected['version'],bool(selected['is_archived'])),open=True)
        tasks={t['task_id']:t for t in value['tasks']}
        def install(key):
            task=tasks[key];parent=task['parent_task_id']
            row='task:'+key
            if self.tree.exists(row):return
            if parent in tasks:install(parent);parent_row='task:'+parent
            else:parent_row='project:'+self.key if self.entity=='project' else ''
            self.tree.insert(parent_row,'end',iid=row,text=task['name'],values=(key,task['version'],bool(task['is_archived'])),open=True)
        for key in sorted(tasks):install(key)
        self.status.configure(text=('Eligible unused scope. Review every row and type DELETE.' if value['eligible'] else
                                   'Delete refused. Use Archive for history-bearing items.\n'+'\n'.join(value['reasons'])))
        self.controls()

    def submit(self):
        if not self.mutation_allowed() or self.confirmed.get()!='DELETE' or not self.owner.can_mutate(origin=self):return False
        return self.owner._submit('delete_'+self.entity,_origin=self,
            **{self.entity+'_id':self.key,'expected_version':self.review['selected']['version'],
               'review':deepcopy(self.review),'confirmed_text':self.confirmed.get()})

    def record_result(self,result):
        # Record model state before fallible widget presentation.
        self.outcome=result;self.phase='complete' if result.status=='committed' else 'unverified' if result.status=='unverified' else 'failed'
        if not self.current():return
        self.status.configure(text=UNCERTAIN if result.status=='unverified' else
            'Deleted the reviewed unused structure. No work or protected evidence was removed.' if result.status=='committed' else
            f'Delete did not commit. Obtain a new preview before another confirmation. {result.error or result.status}')
        self.confirmed.set('');self.controls()

    def controls(self):
        if not self.current():return
        enabled=self.phase=='ready' and self.review is not None and self.review['eligible'] and not self.owner.closing
        self.entry.configure(state='normal' if enabled else 'disabled')
        self.delete_button.configure(state='normal' if enabled and self.confirmed.get()=='DELETE' else 'disabled')
        self.refresh_button.configure(state='normal' if self.phase in ('failed','blocked','ready') and not self.owner.closing else 'disabled')
        self.close_button.configure(text='Close' if self.phase=='complete' else 'Cancel',state='disabled' if self.phase in ('executing','unverified') else 'normal')
        self.inspect_button.configure(state='normal' if self.phase=='unverified' and not self.owner._worker_stopped and self.owner._delete_inspection_token is None else 'disabled')
        self.exit_button.configure(state='normal' if self.phase=='unverified' and not self.owner.executing else 'disabled')

    def close(self,*,force=False):
        if not self.current():return False
        if not force and self.phase in ('executing','unverified'):return False
        grab=self.window.grab_current()
        if grab is not None and grab is not self.window and not force:return False
        if grab is self.window:self.window.grab_release()
        self.window.destroy()
        if self.owner.alive and not self.owner.closing and widget_live(self.origin):
            current=self.owner.root.grab_current()
            if current is None:
                if self.return_grab is self.origin and self.return_grab.grab_status()!='global':self.origin.grab_set()
                focus=self.return_focus
                if widget_live(focus) and focus.winfo_toplevel() is self.origin:focus.focus_set()
                else:self.origin.focus_set()
        return True

    def destroyed(self,event):
        if event.widget is self.window:
            self.disposed=True
            if self.owner.deletion is self:self.owner.deletion=None
            if self.owner.editor is self.window:self.owner.editor=None
            if self.owner.alive:self.owner._controls()
