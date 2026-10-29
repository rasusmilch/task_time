"""Owned template management/drafts. No database access or alternate authority."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, simpledialog
from uuid import uuid4
from .templates import graph, definition, apply_effect
from .hierarchy import task_observations
from .history_window import widget_live
from .move_window import MoveWindow
from .mini_mode import configure_changed


def uid():return str(uuid4())


class TemplateDialog(MoveWindow):
    """Same accepted-request lifetime as Move, scoped to template ordinary operations."""
    def __init__(self,owner,title):
        self.owner=owner;self.phase='reviewing';self.presented=self.disposed=False
        self.request=self.token=self.outcome=None;self.return_focus=owner.root.focus_get()
        self.window=tk.Toplevel(owner.root);self.window.withdraw();self.window.title(title);self.window.transient(owner.root)
        self.window.geometry('940x620');self.window.columnconfigure(0,weight=1);self.window.rowconfigure(1,weight=1)
        self.status=ttk.Label(self.window,text='',wraplength=900);self.status.grid(row=5,column=0,padx=10,pady=6,sticky='w')
        bar=ttk.Frame(self.window);bar.grid(row=6,column=0,padx=10,pady=6,sticky='w')
        self.confirm_button=ttk.Button(bar,text='Save',command=self.submit)
        self.retry_button=ttk.Button(bar,text='Retry/Reconcile exact request',command=self.retry)
        self.exit_button=ttk.Button(bar,text='Exit despite unresolved save',command=owner.exit_template_uncertain)
        self.close_button=ttk.Button(bar,text='Cancel',command=self.close)
        for b in (self.confirm_button,self.retry_button,self.exit_button,self.close_button):b.pack(side='left',padx=5)
        self.window.protocol('WM_DELETE_WINDOW',self.close);self.window.bind('<Escape>',lambda e:self.close())
        self.window.bind('<Map>',self.mapped,add='+');self.window.bind('<Destroy>',self.destroyed,add='+')
        self.arguments=None

    def current(self):
        return not self.disposed and self.owner.alive and self.owner.template_dialog is self and self.owner.editor is self.window and widget_live(self.window)

    def destroyed(self,event):
        if event.widget is self.window:
            self.disposed=True
            if self.owner.template_dialog is self:self.owner.template_dialog=None
            if self.owner.editor is self.window:self.owner.editor=None
            if self.owner.alive:self.owner._controls()

    def close(self,*,force=False):
        if not self.current() or not force and self.phase in ('executing','unverified'):return False
        grab=self.window.grab_current()
        if grab is not None and grab is not self.window and not force:return False
        if grab is self.window:self.window.grab_release()
        self.window.destroy()
        if self.owner.alive and not self.owner.closing and self.owner.root.grab_current() is None:
            focus=self.return_focus;manager=self.owner.templates_window
            allowed=(self.owner.root,manager.window) if manager is not None and manager.current() else (self.owner.root,)
            (focus if widget_live(focus) and focus.winfo_toplevel() in allowed else self.owner.root).focus_set()
        return True

    def record_result(self,result):
        self.outcome=result;self.phase='unverified' if result.status=='unverified' else 'complete' if result.status in ('committed','unchanged') else 'failed'
        if self.current():
            self.status.configure(text='Not verified. Retry/Reconcile retains the original UUIDs and request; or explicitly exit.' if self.phase=='unverified' else
                                  'Saved. Applied task instances remain independent.' if result.status=='committed' else 'Unchanged; no receipt.' if result.status=='unchanged' else f'Refused: {result.error or result.status}. Close and obtain fresh review.')
            self.controls()

    def submit(self):
        if not self.mutation_allowed() or not self.owner.can_mutate(origin=self):return False
        try:op,args=self.build()
        except ValueError as exc:self.status.configure(text=str(exc));return False
        return self.owner._submit(op,_origin=self,**deepcopy(args))

    def controls(self):
        if not self.current():return
        if hasattr(self,'name_entry'):self.name_entry.configure(state='normal' if self.phase=='reviewing' else 'disabled')
        if hasattr(self,'parent_choice'):self.parent_choice.configure(state='readonly' if self.phase=='reviewing' else 'disabled')
        if hasattr(self,'draft_buttons'):
            for b in self.draft_buttons.values():b.configure(state='normal' if self.phase=='reviewing' and not self.duplicate else 'disabled')
        if hasattr(self,'choice'):self.choice.configure(state='readonly' if self.phase=='reviewing' else 'disabled')
        self.confirm_button.configure(state='normal' if self.phase=='reviewing' and not self.owner.closing else 'disabled')
        self.close_button.configure(text='Close' if self.phase in ('complete','failed') else 'Cancel',state='disabled' if self.phase in ('executing','unverified') else 'normal')
        self.retry_button.configure(state='normal' if self.phase=='unverified' and not self.owner._worker_stopped else 'disabled')
        self.exit_button.configure(state='normal' if self.phase=='unverified' and not self.owner.executing else 'disabled')


class TemplateEditor(TemplateDialog):
    def __init__(self,owner,source=None,duplicate=False):
        super().__init__(owner,'Duplicate template' if duplicate else 'Edit template' if source else 'Create template')
        self.source=deepcopy(source);self.duplicate=duplicate;self.key=uid() if source is None or duplicate else source['template_id']
        self.title=tk.StringVar(self.window,source['name'] if source else '')
        bar=ttk.Frame(self.window);bar.grid(row=0,column=0,sticky='ew',padx=10,pady=8)
        ttk.Label(bar,text='Template name (active names must be unique)').pack(side='left')
        self.name_entry=ttk.Entry(bar,textvariable=self.title,width=42);self.name_entry.pack(side='left',padx=8)
        self.nodes=deepcopy(source['nodes']) if source else []
        self.mapping=[]
        if duplicate:
            lookup={n['node_id']:uid() for n in self.nodes}
            self.mapping=sorted((dict(node_id=k,new_node_id=v) for k,v in lookup.items()),key=lambda p:p['node_id'])
            self.nodes=[dict(n,node_id=lookup[n['node_id']],parent_node_id=lookup[n['parent_node_id']] if n['parent_node_id'] else None) for n in self.nodes]
        self.tree=ttk.Treeview(self.window,columns=('uuid',),selectmode='browse');self.tree.heading('#0',text='Complete draft hierarchy');self.tree.heading('uuid',text='Node UUID')
        self.tree.grid(row=1,column=0,sticky='nsew',padx=10)
        actions=ttk.Frame(self.window);actions.grid(row=2,column=0,sticky='w',padx=10,pady=8)
        self.draft_buttons={}
        for label,fn in [('Add root',lambda:self.add(False)),('Add child',lambda:self.add(True)),('Rename node',self.rename),('Remove subtree',self.remove),('Reparent',self.reparent),('Up',lambda:self.reorder(-1)),('Down',lambda:self.reorder(1))]:
            b=ttk.Button(actions,text=label,command=fn);b.pack(side='left',padx=2);self.draft_buttons[label]=b
            if duplicate:b.configure(state='disabled')
        self.parent_choice=ttk.Combobox(self.window,state='readonly',width=100)
        self.parent_choice.grid(row=3,column=0,padx=10,sticky='ew')
        ttk.Label(self.window,text='Reparent destination: Root or reviewed node UUID. Preview above is the complete structure saved atomically.').grid(row=4,column=0,padx=10,sticky='w')
        self.render()
        self.status.configure(text=('Source: '+source['template_id']+' version '+str(source['version'])+'; duplicate uses fresh UUIDs.' if duplicate else 'Draft only. Save validates the complete graph; Cancel writes nothing.'))

    def selected_node(self):
        rows=self.tree.selection();return rows[0] if rows else None

    def editable(self):return self.current() and self.phase=='reviewing' and not self.duplicate and self.owner.pending is None

    def render(self,selected=None):
        self.tree.delete(*self.tree.get_children())
        for n in self.nodes:self.tree.insert(n['parent_node_id'] or '','end',iid=n['node_id'],text=n['name'],values=(n['node_id'],),open=True)
        self.parent_ids=[None]+[n['node_id'] for n in self.nodes]
        self.parent_choice.configure(values=['Root']+[n['name']+' ('+n['node_id']+')' for n in self.nodes]);self.parent_choice.current(0)
        if selected and self.tree.exists(selected):self.tree.selection_set(selected)

    def normalize(self,nodes):
        children={None:[]}
        for n in nodes:children.setdefault(n['parent_node_id'],[]).append(n);children.setdefault(n['node_id'],[])
        ordered=[]
        def walk(parent):
            for n in children[parent]:ordered.append(dict(n,position=len(ordered)));walk(n['node_id'])
        # Validate ancestry first without recursive traversal on cycles.
        known={n['node_id']:n for n in nodes}
        for key in known:
            path=[];cursor=key
            while cursor is not None:
                if cursor in path or cursor not in known or len(path)>=3:raise ValueError('Reparent would create cycle, missing parent or depth overflow')
                path.append(cursor);cursor=known[cursor]['parent_node_id']
        walk(None)
        if ordered:graph(ordered)
        return ordered

    def add(self,child):
        if not self.editable():return False
        parent=self.selected_node() if child else None
        if child and parent is None:return False
        try:title=simpledialog.askstring('Template node','Node name',parent=self.window)
        finally:self.restore_modal()
        if title is None:return False
        try:
            key=uid();nodes=self.normalize(self.nodes+[dict(node_id=key,parent_node_id=parent,name=title.strip(),position=0)])
        except ValueError as exc:self.status.configure(text=str(exc));return False
        self.nodes=nodes;self.render(key);return True

    def rename(self):
        if not self.editable() or not self.selected_node():return False
        key=self.selected_node();n=next(n for n in self.nodes if n['node_id']==key)
        try:title=simpledialog.askstring('Rename node','Node name',initialvalue=n['name'],parent=self.window)
        finally:self.restore_modal()
        if title is None:return False
        if not title.strip():self.status.configure(text='Nonempty node name required');return False
        n['name']=title.strip();self.render(key);return True

    def remove(self):
        if not self.editable() or not self.selected_node():return False
        key=self.selected_node();_,paths=graph(self.nodes);self.nodes=[n for n in self.nodes if key not in paths[n['node_id']]];self.render();return True

    def reparent(self):
        if not self.editable() or not self.selected_node():return False
        key=self.selected_node();index=self.parent_choice.current()
        if index<0:return False
        proposed=[dict(n,parent_node_id=self.parent_ids[index]) if n['node_id']==key else dict(n) for n in self.nodes]
        try:self.nodes=self.normalize(proposed)
        except ValueError as exc:self.status.configure(text=str(exc));return False
        self.render(key);return True

    def reorder(self,delta):
        if not self.editable() or not self.selected_node():return False
        key=self.selected_node();node=next(n for n in self.nodes if n['node_id']==key)
        siblings=[n for n in self.nodes if n['parent_node_id']==node['parent_node_id']];i=next(i for i,n in enumerate(siblings) if n['node_id']==key);j=i+delta
        if not 0<=j<len(siblings):return False
        siblings[i],siblings[j]=siblings[j],siblings[i];iterator=iter(siblings)
        self.nodes=self.normalize([next(iterator) if n['parent_node_id']==node['parent_node_id'] else n for n in self.nodes]);self.render(key);return True

    def build(self):
        title=self.title.get().strip()
        if not title:raise ValueError('Nonempty template name required')
        graph(self.nodes)
        if self.duplicate:
            return 'duplicate_template',dict(template_id=self.key,name=title,source_template_id=self.source['template_id'],expected_source_version=self.source['version'],reviewed_source=self.source,node_mapping=self.mapping)
        args=dict(template_id=self.key,name=title,nodes=self.nodes)
        if self.source:args['expected_version']=self.source['version']
        # Advisory uniqueness only; the service rechecks all current definitions.
        archived=self.source and self.source['is_archived']
        if not archived and any(d['template_id']!=self.key and not d['is_archived'] and d['name_key']==title.casefold() for d in self.owner.state.get('templates',[])):raise ValueError('Active template name collision')
        return ('edit_template' if self.source else 'create_template'),args


class TemplateApply(TemplateDialog):
    def __init__(self,owner,source):
        super().__init__(owner,'Apply template — review insertion');self.source=deepcopy(source);self.state=deepcopy(owner.state)
        self.mapping=[dict(node_id=n['node_id'],task_id=uid()) for n in source['nodes']]
        ttk.Label(self.window,text=f"Template: {source['name']} ({source['template_id']}) version {source['version']} — {len(source['nodes'])} nodes",wraplength=900).grid(row=0,column=0,padx=10,sticky='w')
        self.tree=ttk.Treeview(self.window);self.tree.heading('#0',text='Complete blueprint');self.tree.grid(row=1,column=0,sticky='nsew',padx=10)
        for n in source['nodes']:self.tree.insert(n['parent_node_id'] or '','end',iid=n['node_id'],text=n['name'],open=True)
        self.choice=ttk.Combobox(self.window,state='readonly',width=110);self.choice.grid(row=2,column=0,padx=10,sticky='ew')
        self.choice.bind('<<ComboboxSelected>>',self.selected);self.options=[]
        tasks={t['task_id']:t for t in self.state['tasks']};projects={p['project_id']:p for p in self.state['projects']}
        choices=[(None,None,'Unassigned')]+[(None,p['project_id'],p['name']+' ('+p['project_id']+')') for p in projects.values()]+[(t['task_id'],t['project_id'],owner._task_path_label(t['task_id'],self.state)) for t in tasks.values()]
        for parent,group,label in choices:
            args=dict(template_id=source['template_id'],expected_template_version=source['version'],reviewed_definition=deepcopy(source),destination_parent_task_id=parent,destination_project_id=group,expected_destination_parent_version=tasks[parent]['version'] if parent else None,expected_destination_project_version=projects[group]['version'] if group else None,node_mapping=deepcopy(self.mapping))
            reason=None;depth=0
            try:
                proposed=deepcopy(tasks);apply_effect(args,{source['template_id']:source},proposed,projects,self.state['active'],uid(),0)
                depth=max(task_observations(list(proposed.values()),list(projects.values()))[p['task_id']]['depth'] for p in self.mapping)
            except ValueError as exc:reason=str(exc)
            self.options.append(dict(args=args,label=label,reason=reason,depth=depth))
        self.choice.configure(values=[o['label'] for o in self.options]);selected=owner._selected();project=owner._selected_project()
        i=next((i for i,o in enumerate(self.options) if o['args']['destination_parent_task_id']==(selected['task_id'] if selected else None) and o['args']['destination_project_id']==(selected['project_id'] if selected else project['project_id'] if project else None)),0)
        self.choice.current(i);self.selected()
        self.confirm_button.configure(text='Confirm Apply')

    def selected(self,event=None):
        if self.phase!='reviewing':return
        i=self.choice.current();o=self.options[i] if i>=0 else None;self.arguments=None
        if o:
            if not o['reason']:self.arguments=deepcopy(o['args'])
            self.status.configure(text='Destination: '+o['label']+'\n'+('Unavailable: '+o['reason'] if o['reason'] else f"Resulting maximum depth: {o['depth']}. Insert exactly {len(self.mapping)} fresh tasks; no work/timer/evidence copied."))
        self.controls()

    def controls(self):
        super().controls()
        if self.current() and self.arguments is None:self.confirm_button.configure(state='disabled')

    def build(self):
        if self.arguments is None:raise ValueError('Review an eligible destination')
        return 'apply_template',self.arguments


class TemplatesWindow:
    def __init__(self,owner):
        self.owner=owner;self.disposed=False;self.rows={};self.window=tk.Toplevel(owner.root)
        try:
            self.window.withdraw();self.window.title('Templates');self.window.geometry('900x530');self.window.transient(owner.root)
            self.window.columnconfigure(0,weight=1);self.window.rowconfigure(0,weight=1)
            self.tree=ttk.Treeview(self.window,columns=('uuid','version','state','count'),selectmode='browse')
            self.tree.heading('#0',text='Template / complete structure')
            for key,label in [('uuid','UUID'),('version','Version'),('state','State'),('count','Nodes')]:self.tree.heading(key,text=label)
            self.tree.grid(row=0,column=0,sticky='nsew',padx=10,pady=10)
            self.tree.bind('<<TreeviewSelect>>',lambda e:self.controls())
            bar=ttk.Frame(self.window);bar.grid(row=1,column=0,sticky='w',padx=10)
            self.buttons={}
            for label,fn in [('Create',lambda:self.edit(False)),('Edit',lambda:self.edit(True)),('Duplicate',self.duplicate),('Archive',lambda:self.archive(True)),('Unarchive',lambda:self.archive(False)),('Delete',self.delete),('Apply',self.apply),('Close',self.close)]:
                b=ttk.Button(bar,text=label,command=fn);b.pack(side='left',padx=3);self.buttons[label]=b
            self.status=ttk.Label(self.window,text='',wraplength=850);self.status.grid(row=2,column=0,padx=10,pady=8,sticky='w')
            self.window.protocol('WM_DELETE_WINDOW',self.close);self.window.bind('<Escape>',lambda e:self.close());self.window.bind('<Destroy>',self.destroyed,add='+')
        except BaseException:
            self.window.destroy();raise

    def current(self):return not self.disposed and self.owner.alive and self.owner.templates_window is self and widget_live(self.window)
    def selected(self):
        selected=self.tree.selection();return self.rows.get(selected[0]) if selected else None
    def allowed(self):return self.current() and self.owner.can_mutate() and self.owner.root.grab_current() is None
    def controls(self):
        if not self.current():return
        d=self.selected();allowed=self.allowed()
        for label,b in self.buttons.items():
            enabled=allowed and (label in ('Create','Close') or d is not None)
            if label=='Apply':enabled=enabled and not d['is_archived']
            if label=='Archive':enabled=enabled and not d['is_archived']
            if label=='Unarchive':enabled=enabled and d['is_archived']
            configure_changed(b,state='normal' if enabled else 'disabled')
        configure_changed(self.status,text=self.owner.status.cget('text'))
    def render(self,state):
        if not self.current():return
        wanted={};rows={}
        for d in state.get('templates',[]):
            key='template:'+d['template_id'];rows[key]=deepcopy(d);wanted[key]=('',d['name'],(d['template_id'],d['version'],'Archived' if d['is_archived'] else 'Active',len(d['nodes'])))
            for n in d['nodes']:wanted['node:'+n['node_id']]=('node:'+n['parent_node_id'] if n['parent_node_id'] else key,n['name'],(n['node_id'],'','',''))
        selection=self.tree.selection();scroll=self.tree.yview()
        for key,(parent,title,values) in wanted.items():
            if not self.tree.exists(key):self.tree.insert(parent,'end',iid=key,text=title,values=values,open=False)
            else:
                if self.tree.parent(key)!=parent:self.tree.move(key,parent,'end')
                if self.tree.item(key,'text')!=title:self.tree.item(key,text=title)
                if self.tree.item(key,'values')!=tuple(map(str,values)):self.tree.item(key,values=values)
        def clean(parent):
            for key in self.tree.get_children(parent):
                if key not in wanted:self.tree.delete(key)
                else:clean(key)
        clean('')
        children={'':[]}
        for key,(parent,_,_) in wanted.items():children.setdefault(parent,[]).append(key);children.setdefault(key,[])
        for parent,ordered in children.items():
            if tuple(self.tree.get_children(parent))!=tuple(ordered):
                for index,key in enumerate(ordered):
                    if self.tree.index(key)!=index:self.tree.move(key,parent,index)
        self.rows=rows
        valid=tuple(k for k in selection if k in wanted)
        if self.tree.selection()!=valid:self.tree.selection_set(valid)
        if scroll and self.tree.yview()!=scroll:self.tree.yview_moveto(scroll[0])
        reveal=self.owner._template_reveal
        if reveal and 'template:'+reveal in wanted:
            self.owner._template_reveal=None;self.tree.selection_set('template:'+reveal);self.tree.see('template:'+reveal)
        self.controls()
    def edit(self,existing):
        if not self.allowed() or existing and not self.selected():return False
        return self.owner.open_template_dialog('edit',self.selected() if existing else None)
    def duplicate(self):
        if not self.allowed() or not self.selected():return False
        return self.owner.open_template_dialog('duplicate',self.selected())
    def apply(self):
        d=self.selected()
        if not self.allowed() or d is None or d['is_archived']:return False
        return self.owner.open_template_dialog('apply',d)
    def archive(self,archived):
        d=self.selected()
        if not self.allowed() or d is None:return False
        return self.owner._submit('archive_template' if archived else 'unarchive_template',template_id=d['template_id'],expected_version=d['version'])
    def delete(self):
        if not self.allowed() or not self.selected():return False
        return self.owner.open_template_delete(self.selected(),self)
    def close(self):
        if not self.current() or self.owner.root.grab_current() is not None:return False
        self.window.destroy();return True
    def destroyed(self,event):
        if event.widget is self.window:
            self.disposed=True
            if self.owner.templates_window is self:self.owner.templates_window=None
