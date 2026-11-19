"""One owned, explicit real-project task creation review. No storage access."""
from copy import deepcopy
from uuid import uuid4
import tkinter as tk
from tkinter import ttk

from .history_window import widget_live
from .project_ui import context, new_task_review, path_label, project_row
from .records import name_text


class TaskCreationWindow:
    def __init__(self, owner):
        self.owner = owner
        self.state = deepcopy(owner.state)
        self.origin = owner.root.focus_get()
        selected = owner._selected()
        project = owner._selected_project()
        self.parent_id = selected['task_id'] if selected else None
        self.project_id = selected['project_id'] if selected else project['project_id'] if project else None
        self.closed = False
        self.projects, _, self.forest, _ = context(self.state)
        self.window = tk.Toplevel(owner.root)
        try:
            self.window.withdraw()
            self.window.title('New child task' if selected else 'New task')
            self.window.transient(owner.root)
            self.window.geometry('720x540')
            self.window.minsize(600, 440)
            self.window.columnconfigure(0, weight=1)
            self.window.rowconfigure(3, weight=1)
            title = 'Immediate child of: '+path_label(self.state, 'task', self.parent_id) if selected else 'Root task — choose its real project explicitly'
            ttk.Label(self.window, text=title, wraplength=660).grid(row=0, column=0, sticky='ew', padx=12, pady=8)
            self.name = ttk.Entry(self.window)
            self.name.grid(row=1, column=0, sticky='ew', padx=12)
            ttk.Label(self.window, text='Inherited project (read-only)' if selected else 'Destination project — full path and UUID shown below').grid(row=2, column=0, sticky='w', padx=12, pady=6)
            host = ttk.Frame(self.window)
            host.grid(row=3, column=0, sticky='nsew', padx=12)
            host.rowconfigure(0, weight=1)
            host.columnconfigure(0, weight=1)
            self.tree = ttk.Treeview(host, columns=('uuid','eligibility'), selectmode='browse')
            self.tree.heading('#0', text='Project')
            self.tree.heading('uuid', text='Project UUID')
            self.tree.heading('eligibility', text='Destination')
            self.tree.column('#0', width=260)
            self.tree.column('uuid', width=300, stretch=False)
            self.tree.column('eligibility', width=140, stretch=False)
            self.vertical = ttk.Scrollbar(host, orient='vertical', command=self.tree.yview)
            self.horizontal = ttk.Scrollbar(host, orient='horizontal', command=self.tree.xview)
            self.tree.configure(yscrollcommand=self.vertical.set, xscrollcommand=self.horizontal.set)
            self.tree.grid(row=0, column=0, sticky='nsew')
            self.vertical.grid(row=0, column=1, sticky='ns')
            self.horizontal.grid(row=1, column=0, sticky='ew')
            for key in self.forest.order:
                p = self.projects[key]
                self.tree.insert(project_row(p['parent_project_id']) if p['parent_project_id'] else '', 'end',
                    iid=project_row(key), text=p['name'], values=(key, 'Archived' if self.forest.effective_archived[key] else 'Eligible'), open=True)
            self.path = tk.StringVar(self.window, '')
            self.path_entry = ttk.Entry(self.window, textvariable=self.path, state='readonly')
            self.path_entry.grid(row=4, column=0, sticky='ew', padx=12, pady=5)
            self.status = ttk.Label(self.window, wraplength=660)
            self.status.grid(row=5, column=0, sticky='ew', padx=12)
            actions = ttk.Frame(self.window)
            actions.grid(row=6, column=0, sticky='ew', padx=12, pady=10)
            self.create_button = ttk.Button(actions, text='Create', command=self.submit)
            self.create_button.pack(side='left')
            self.cancel_button = ttk.Button(actions, text='Cancel', command=self.close)
            self.cancel_button.pack(side='left', padx=8)
            self.project_button = ttk.Button(actions, text='Create Project', command=self.create_project)
            if not any(not self.forest.effective_archived[k] for k in self.projects):
                self.project_button.pack(side='left')
            self.tree.bind('<<TreeviewSelect>>', self.selected)
            if self.parent_id:
                self.tree.bind('<Button-1>', lambda event:'break')
                self.tree.bind('<Key>', lambda event:'break')
            if self.project_id:
                self.tree.selection_set(project_row(self.project_id))
                self.tree.see(project_row(self.project_id))
            self.window.protocol('WM_DELETE_WINDOW', self.close)
            self.window.bind('<Escape>', lambda event:self.close())
            self.window.bind('<Destroy>', self.destroyed, add='+')
            self.window.bind('<Map>', self.mapped, add='+')
            self.controls()
            self.window.deiconify()
        except BaseException as primary:
            self.closed = True
            try:
                self.window.destroy()
            except BaseException as cleanup:
                primary.add_note('New Task construction cleanup failed: '+repr(cleanup))
            raise

    def mapped(self, event):
        if event.widget is not self.window or self.closed:
            return
        grab = self.owner.root.grab_current()
        if grab is not None and grab is not self.window:
            self.close()
            return
        self.window.grab_set()
        self.name.focus_set()

    def selected(self, event=None):
        if self.closed:
            return
        rows = self.tree.selection()
        if self.parent_id:
            expected = project_row(self.project_id)
            if rows != (expected,):
                self.tree.selection_set(expected)
        else:
            self.project_id = rows[0].split(':',1)[1] if rows else None
        self.controls()

    def controls(self):
        if self.closed:
            return
        error = None
        if self.project_id is None:
            error = 'A real project is required. Select one, or choose Create Project when none is available.'
        else:
            try:
                new_task_review(self.state, self.parent_id, self.project_id)
            except (ValueError, KeyError) as exc:
                error = str(exc)
        self.path.set(path_label(self.state,'project',self.project_id) if self.project_id else '')
        self.status.configure(text=error or 'Review the destination, enter a name, then Create. No work or timer is created.')
        self.create_button.configure(state='disabled' if error else 'normal')

    def submit(self):
        if self.closed or self.owner.editor is not self.window or self.owner.pending is not None or self.owner.executing or self.owner.closing:
            return False
        try:
            name = name_text(self.name.get())
            review = new_task_review(self.state, self.parent_id, self.project_id)
        except (ValueError, KeyError) as exc:
            self.status.configure(text=str(exc))
            return False
        self.close()
        return self.owner._submit('create_task', task_id=str(uuid4()), name=name, **review)

    def create_project(self):
        if self.closed or self.owner.pending is not None or self.owner.executing:
            return False
        self.close()
        return self.owner.create_project()

    def close(self):
        if self.closed:
            return True
        self.closed = True
        try:
            if widget_live(self.window):
                if self.owner.root.grab_current() is self.window:
                    self.window.grab_release()
                self.window.destroy()
            if self.owner.editor is self.window:
                self.owner.editor = None
            if widget_live(self.owner.root):
                (self.origin if widget_live(self.origin) else self.owner.root).focus_set()
        finally:
            if self.owner.task_creation is self:
                self.owner.task_creation = None
            if self.owner.alive:
                self.owner._controls()
        return True

    def destroyed(self, event):
        if event.widget is self.window:
            self.close()
