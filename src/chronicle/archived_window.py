"""Modeless archived-tree consumer of the application's coordinated snapshots."""

from copy import deepcopy
import tkinter as tk
from tkinter import ttk

from .hierarchy import task_paths
from .history_window import widget_live
from .mini_mode import configure_changed
from .timekeeping import format_duration, from_us


SORTS = ('Name — A to Z', 'Name — Z to A',
         'Date Archived — Newest first', 'Date Archived — Oldest first')


def projection(state, order, period, zone):
    """Derived visibility/provenance only; no independent work calculation."""
    tasks = {t['task_id']: t for t in state['tasks']}
    projects = {p['project_id']: p for p in state['projects']}
    paths = task_paths(list(tasks.values()))
    rows = {}
    report = state['report']
    field = 'today_us' if period == 'Today' else 'week_us'

    def row(entity, item, parent, name, source):
        key = entity + ':' + item[entity + '_id']
        if entity == 'project':
            individual = '—'
            cumulative = format_duration(report['projects'][item['project_id']][field]) if report else '—'
        else:
            individual = format_duration(report['individual'][item['task_id']][field]) if report else '—'
            cumulative = format_duration(report['cumulative'][item['task_id']][field]) if report else '—'
        stamp = source['archived_at_utc_us']
        # Numeric UTC offset disambiguates repeated local clock hours.
        date = from_us(stamp).astimezone(zone).strftime('%Y-%m-%d %H:%M:%S.%f UTC%z')
        rows[key] = dict(parent=parent, text=name, values=(date, individual, cumulative),
                         item=item, entity=entity, stamp=stamp, source=source)
        return key

    for p in projects.values():
        if p['is_archived']:
            row('project', p, '', p['name'], p)
    for key, task in tasks.items():
        ancestors = paths[key]
        source = next((tasks[a] for a in ancestors if tasks[a]['is_archived']), None)
        project = projects.get(task['project_id'])
        if source is None and project and project['is_archived']:
            source = project
        if source is None:
            continue
        parent = task['parent_task_id']
        # Include the complete original branch if an ancestor is archived.
        ancestor_hidden = any(tasks[a]['is_archived'] for a in ancestors[1:]) or bool(project and project['is_archived'])
        if ancestor_hidden:
            parent_row = 'task:' + parent if parent else 'project:' + task['project_id']
            name = task['name']
        else:
            parent_row = ''
            context = [project['name'] if project else 'Unassigned'] + [tasks[a]['name'] for a in reversed(ancestors[1:])]
            name = task['name'] + '  [' + ' → '.join(context) + ']'
        row('task', task, parent_row, name, source)
    children = {'': []}
    for key, value in rows.items():
        children.setdefault(value['parent'], []).append(key)
        children.setdefault(key, [])
    for siblings in children.values():
        # UUID precedes the type discriminator even among mixed top-level rows.
        siblings.sort(key=lambda key: (key.split(':', 1)[1], key))
        siblings.sort(key=lambda key: rows[key]['item']['name'].casefold() if order in SORTS[:2] else rows[key]['stamp'],
                      reverse=order in (SORTS[1], SORTS[2]))
    return rows, children


class ArchivedItemsWindow:
    def __init__(self, owner):
        self.owner = owner
        self.disposed = False
        self.rows = {}
        self.snapshot = None
        self.window = tk.Toplevel(owner.root)
        try:
            self.window.withdraw()
            self.window.title('Archived Items')
            self.window.transient(owner.root)
            self.window.geometry('1050x530')
            self.window.columnconfigure(0, weight=1)
            self.window.rowconfigure(1, weight=1)
            bar = ttk.Frame(self.window)
            bar.grid(row=0, column=0, sticky='ew', padx=8, pady=8)
            self.sort = tk.StringVar(self.window, SORTS[2])
            self.sort_control = ttk.Combobox(bar, textvariable=self.sort, values=SORTS, state='readonly', width=30)
            self.sort_control.pack(side='left', padx=4)
            self.period = tk.StringVar(self.window, 'Today')
            self.period_control = ttk.Combobox(bar, textvariable=self.period, values=('Today', 'This Week'), state='readonly', width=12)
            self.period_control.pack(side='left', padx=4)
            for control in (self.sort_control, self.period_control):
                control.bind('<<ComboboxSelected>>', self.changed)
            holder = ttk.Frame(self.window)
            holder.grid(row=1, column=0, sticky='nsew', padx=8)
            holder.columnconfigure(0, weight=1)
            holder.rowconfigure(0, weight=1)
            self.tree = ttk.Treeview(holder, columns=('archived', 'individual', 'cumulative'), selectmode='browse')
            self.tree.heading('#0', text='Archived project / task (original context)')
            self.tree.column('#0', width=350)
            for key, label, width in (('archived', 'Date Archived', 320), ('individual', 'Individual', 110), ('cumulative', 'Cumulative', 110)):
                self.tree.heading(key, text=label)
                self.tree.column(key, width=width)
            self.tree.grid(row=0, column=0, sticky='nsew')
            scroll = ttk.Scrollbar(holder, orient='vertical', command=self.tree.yview)
            scroll.grid(row=0, column=1, sticky='ns')
            self.tree.configure(yscrollcommand=scroll.set)
            self.tree.bind('<<TreeviewSelect>>', lambda event: self.controls())
            actions = ttk.Frame(self.window)
            actions.grid(row=2, column=0, sticky='ew', padx=8, pady=8)
            self.unarchive_button = ttk.Button(actions, text='Unarchive selected', command=self.unarchive)
            self.history_button = ttk.Button(actions, text='Work History', command=self.history)
            self.close_button = ttk.Button(actions, text='Close', command=self.close)
            self.delete_button = ttk.Button(actions, text='Delete', command=self.delete)
            for button in (self.unarchive_button, self.history_button, self.delete_button, self.close_button):
                button.pack(side='left', padx=4)
            self.status = ttk.Label(self.window, text='', wraplength=1000)
            self.status.grid(row=3, column=0, sticky='w', padx=8, pady=8)
            self.window.protocol('WM_DELETE_WINDOW', self.close)
            self.window.bind('<Escape>', lambda event: self.close())
            self.window.bind('<Destroy>', self.destroyed, add='+')
        except BaseException as primary:
            try:
                self.window.destroy()
            except BaseException as secondary:
                primary.add_note(f'Archived Items construction cleanup failed: {secondary!r}')
            raise

    def current(self):
        return (not self.disposed and self.owner.alive and self.owner.archived is self and widget_live(self.window))

    def selected(self):
        selected = self.tree.selection()
        return self.rows.get(selected[0]) if selected else None

    def controls(self):
        if not self.current():
            return
        allowed = self.owner.can_mutate() and self.owner.root.grab_current() is None
        selected = self.selected()
        explicit = selected and selected['item']['is_archived']
        configure_changed(self.unarchive_button, state='normal' if allowed and explicit else 'disabled')
        configure_changed(self.history_button, state='normal' if allowed and selected and selected['entity'] == 'task' else 'disabled')
        configure_changed(self.delete_button, state='normal' if allowed and selected else 'disabled')
        for control in (self.sort_control, self.period_control):
            configure_changed(control, state='readonly' if allowed else 'disabled')
        text = self.owner.status.cget('text')
        if selected and not explicit:
            source = selected['source']
            entity = 'task' if 'task_id' in source else 'project'
            text += (f" Hidden by archived ancestor {entity}: {source['name']} ({source[entity + '_id']}). "
                     'Unarchive that explicit node to expose this branch.')
        if self.snapshot and self.snapshot['report'] is None:
            text += ' Time totals unavailable. ' + (self.snapshot.get('calculation_error') or '')
        configure_changed(self.status, text=text)

    def changed(self, event=None):
        if self.current() and self.owner.can_mutate() and self.owner.root.grab_current() is None:
            self.render(self.owner.state)

    def render(self, state):
        if not self.current():
            return
        rows, children = projection(state, self.sort.get(), self.period.get(), self.owner.zone)
        selected, scroll = self.tree.selection(), self.tree.yview()
        self.snapshot = deepcopy(state)
        def install(parent):
            for key in children[parent]:
                value = rows[key]
                if not self.tree.exists(key):
                    self.tree.insert(parent, 'end', iid=key, text=value['text'], values=value['values'], open=False)
                else:
                    if self.tree.parent(key) != parent:
                        self.tree.move(key, parent, 'end')
                    old = self.tree.item(key)
                    updates = {k: v for k, v in (('text', value['text']), ('values', value['values']))
                               if (tuple(old[k]) if k == 'values' else old[k]) != v}
                    if updates:
                        self.tree.item(key, **updates)
                install(key)
        install('')  # Reparent survivors before deleting obsolete ancestor rows.
        def remove(parent):
            for key in self.tree.get_children(parent):
                if key not in rows:
                    self.tree.delete(key)
                else:
                    remove(key)
        remove('')
        for parent, ordered in children.items():
            if tuple(self.tree.get_children(parent)) != tuple(ordered):
                for index, key in enumerate(ordered):
                    self.tree.move(key, parent, index)
        remaining = tuple(key for key in selected if key in rows)
        if self.tree.selection() != remaining:
            self.tree.selection_set(remaining)
        if scroll and self.tree.yview() != scroll:
            self.tree.yview_moveto(scroll[0])
        self.rows = rows
        self.controls()

    def unarchive(self):
        if not self.current() or not self.owner.can_mutate() or self.owner.root.grab_current() is not None:
            return False
        selected = self.selected()
        if not selected or not selected['item']['is_archived']:
            return False
        entity, item = selected['entity'], selected['item']
        return self.owner._submit('unarchive_' + entity, **{entity + '_id': item[entity + '_id'], 'expected_version': item['version']})

    def delete(self):
        if not self.current() or self.selected() is None:return False
        return self.owner.open_delete(_archived_origin=self)

    def history(self):
        if not self.current():
            return False
        selected = self.selected()
        if not selected or selected['entity'] != 'task':
            return False
        return self.owner.open_history(_archived_origin=self, _task_id=selected['item']['task_id'])

    def close(self):
        if not self.current() or self.owner.root.grab_current() is not None:
            return False
        self.window.destroy()  # Accepted Requests remain exclusively owned by the app.
        return True

    def destroyed(self, event):
        if event.widget is self.window:
            self.disposed = True
            if self.owner.archived is self:
                self.owner.archived = None
