"""Application-owned read-only Timesheet preview; all I/O belongs to its worker."""
import calendar
from datetime import date
import tkinter as tk
from tkinter import ttk

from .history_window import widget_live
from .records import Outcome
from .timekeeping import from_us, parse_date, to_us
from .timesheet import validate


class TimesheetWindow:
    def __init__(self, owner):
        self.owner = owner
        self.window = None
        self.disposed = self.presented = self._constructed = False
        self._disposal_primary = None
        self.candidate = None
        self.current = False
        self.preview_token = self.choices_token = None
        self.attempt = None
        self._selected_ids = ()
        self.picker = None
        self.observation = None
        self.load_state = 'Not previewed'
        try:
            self.window = tk.Toplevel(owner.root)
            self.window.withdraw()
            self.window.transient(owner.root)
            self.window.title('Timesheet / POL-R — Preview')
            self.window.geometry('980x740')
            self.window.minsize(800,620)
            self.window.columnconfigure(0,weight=1)
            self.window.rowconfigure(3,weight=1)
            self._build()
            self.window.protocol('WM_DELETE_WINDOW',self.close)
            self.window.bind('<Escape>',self._escape)
            self.window.bind('<Map>',self._mapped,add='+')
            self.window.bind('<Destroy>',self._destroyed,add='+')
            self._constructed = True
        except BaseException as primary:
            try: self.close(primary=primary)
            except Exception as secondary: primary.add_note(f'Timesheet construction cleanup failed: {secondary!r}')
            raise

    def _build(self):
        bar = ttk.Frame(self.window)
        bar.grid(row=0,column=0,sticky='ew',padx=8,pady=6)
        self.period = tk.StringVar(bar,'This week')
        self.period_control = ttk.Combobox(bar,textvariable=self.period,values=('This week','Last week','Custom'),state='readonly',width=13)
        self.period_control.grid(row=0,column=0)
        self.start,self.end = tk.StringVar(bar,''),tk.StringVar(bar,'')
        self.date_controls = []
        for i,(name,var) in enumerate((('Start',self.start),('End',self.end))):
            ttk.Label(bar,text=name).grid(row=0,column=1+i*3)
            field = ttk.Entry(bar,textvariable=var,width=12)
            field.grid(row=0,column=2+i*3,padx=3)
            button = ttk.Button(bar,text='Calendar',command=lambda v=var:self.open_picker(v))
            button.grid(row=0,column=3+i*3,padx=3)
            self.date_controls.extend((field,button))
        self.scope = tk.StringVar(bar,'All tasks')
        self.scope_control = ttk.Combobox(bar,textvariable=self.scope,values=('All tasks','Selected tasks'),state='readonly',width=15)
        self.scope_control.grid(row=1,column=0,pady=5)
        self.preview_button = ttk.Button(bar,text='Preview',command=self.refresh_preview)
        self.preview_button.grid(row=1,column=1,columnspan=2)
        self.calendar_area = ttk.Frame(bar)
        self.calendar_area.grid(row=2,column=0,columnspan=7,sticky='w')
        holder = ttk.LabelFrame(self.window,text='Independent task UUIDs (Ctrl/Shift selection; no descendant expansion)')
        holder.grid(row=1,column=0,sticky='ew',padx=8)
        holder.columnconfigure(0,weight=1)
        self.tasks = ttk.Treeview(holder,columns=('task','project','status'),show='headings',height=4,selectmode='extended')
        for key,label,width in (('task','Task name / UUID',500),('project','Project',210),('status','Status',80)):
            self.tasks.heading(key,text=label); self.tasks.column(key,width=width,minwidth=60)
        self.tasks.grid(row=0,column=0,sticky='ew')
        scroll = ttk.Scrollbar(holder,orient='vertical',command=self.tasks.yview)
        scroll.grid(row=0,column=1,sticky='ns'); self.tasks.configure(yscrollcommand=scroll.set)
        horizontal = ttk.Scrollbar(holder,orient='horizontal',command=self.tasks.xview)
        horizontal.grid(row=1,column=0,sticky='ew'); self.tasks.configure(xscrollcommand=horizontal.set)
        self.tasks.bind('<<TreeviewSelect>>',lambda event:self.selection_changed())
        self.context = ttk.Label(self.window,text='Not previewed. Preview only; no file is saved and no POL-R value is confirmed.',wraplength=940)
        self.context.grid(row=2,column=0,sticky='ew',padx=8,pady=4)
        report = ttk.Frame(self.window)
        report.grid(row=3,column=0,sticky='nsew',padx=8)
        report.columnconfigure(0,weight=1); report.rowconfigure(0,weight=1)
        self.report = tk.Text(report,wrap='none',state='disabled',height=12)
        self.report.grid(row=0,column=0,sticky='nsew')
        for orient,row,column,command in (('vertical',0,1,self.report.yview),('horizontal',1,0,self.report.xview)):
            scroll = ttk.Scrollbar(report,orient=orient,command=command)
            scroll.grid(row=row,column=column,sticky='ns' if orient=='vertical' else 'ew')
            self.report.configure(**{('yscrollcommand' if orient=='vertical' else 'xscrollcommand'):scroll.set})
        self.status = ttk.Label(self.window,text='',wraplength=940)
        self.status.grid(row=4,column=0,sticky='ew',padx=8,pady=4)
        self.close_button = ttk.Button(self.window,text='Close',command=self.close)
        self.close_button.grid(row=5,column=0,sticky='e',padx=8,pady=6)
        for var in (self.period,self.start,self.end,self.scope):
            var.trace_add('write',lambda *args:self.draft_changed())
        self.controls()

    def controls(self):
        custom = self.period.get()=='Custom'
        for control in self.date_controls: control.configure(state='normal' if custom else 'disabled')
        if not custom: self.close_picker()

    def selection_changed(self):
        selected = tuple(sorted(self.tasks.selection()))
        if selected != self._selected_ids:
            self._selected_ids = selected
            self.draft_changed()

    def draft_changed(self):
        self.current = False
        self.preview_token = None  # Logically abandon the old read; worker continues.
        self.load_state = 'Previous preview — inputs changed; refresh required.' if self.candidate else 'Not previewed — inputs changed.'
        self.context.configure(text=self.load_state)
        self.controls()

    def get_prepared_export(self):
        # Candidate and all its children are strict frozen values, not live references.
        return self.candidate if self.current else None

    def refresh_preview(self):
        if self.disposed or not self.presented or self.owner.timesheet is not self:
            return False
        self.selection_changed()
        self.current = False
        self.preview_token = None
        try:
            period = {'This week':'this_week','Last week':'last_week','Custom':'custom'}[self.period.get()]
            scope = {'All tasks':'all','Selected tasks':'selected'}[self.scope.get()]
            selected = tuple(sorted(self.tasks.selection())) if scope=='selected' else ()
            if scope=='selected' and not selected:
                raise ValueError('Select at least one task UUID')
            args = dict(period=period,scope_kind=scope,task_ids=selected)
            if period=='custom': args.update(start_date=self.start.get(),end_date=self.end.get())
            self.preview_token,self.attempt = self.owner._timesheet_read(self,'timesheet_preview',args)
            self.observation = self.attempt['cutoff_utc_us']
            self.load_state = 'Loading'
            self.context.configure(text='Loading; previous preview is not current.' if self.candidate else 'Loading')
            self.status.configure(text='')
            return True
        except Exception as exc:
            return self.failure(exc)

    def receive_preview(self,token,value):
        if self.disposed or token != self.preview_token:
            return
        self.preview_token = None
        if isinstance(value,Outcome):
            return self.failure(value.error or ValueError('Preview unavailable'))
        try:
            candidate = validate(value)
            if (candidate.dataset_id != self.owner.dataset_id or self.attempt is None
                    or candidate.export_id != self.attempt['export_id']
                    or candidate.cutoff_utc_us != self.attempt['cutoff_utc_us']):
                raise ValueError('Preview identity/observation does not match this request')
            text = candidate.report_text
            context = (f'Applied: {candidate.start_date} to {candidate.end_date}; '
                       f'as of UTC {from_us(candidate.cutoff_utc_us).isoformat()}; {candidate.timezone}; '
                       f'week starts {calendar.day_name[candidate.week_start]}. Suggested only; not confirmed.')
        except Exception as exc:
            return self.failure(exc)
        try:
            self.report.configure(state='normal')
            self.report.delete('1.0','end')
            self.report.insert('1.0',text)
            self.report.configure(state='disabled')
            self.context.configure(text=context)
            self.preview_button.configure(text='Refresh Preview')
            self.report.grid()
            self.status.configure(text='Preview ready (empty All).' if not candidate.tasks else 'Preview ready. No file saved; no POL-R confirmation.')
        except Exception as primary:
            # Partial output has no trusted identity. Hide it, without claiming rollback.
            try:
                self.report.grid_remove()
                self.report.configure(state='disabled')
            except Exception as secondary:
                primary.add_note(f'Unable to hide untrusted Timesheet output: {secondary!r}')
            return self.failure(primary)
        self.candidate,self.current = candidate,True
        self.load_state = 'Previewed with rows' if candidate.tasks else 'Previewed empty All'

    def receive_choices(self,token,value):
        if self.disposed or token != self.choices_token: return
        self.choices_token = None
        if isinstance(value,Outcome): return self.failure(value.error or ValueError('Task choices unavailable'))
        try:
            if value['dataset_id'] != self.owner.dataset_id: raise ValueError('Task choices belong to another dataset')
            rows = [(t['task_id'],(f"{t['name']} / {t['task_id']}",t['project_name'],'Deleted' if t['is_deleted'] else 'Active')) for t in value['tasks']]
            for key,values in rows: self.tasks.insert('', 'end',iid=key,values=values)
        except Exception as exc: self.failure(exc)

    def failure(self,exc):
        self.current = False
        self.load_state = 'Preview failed'
        try:
            self.context.configure(text='Previous preview — unavailable as current.' if self.candidate else 'Preview failed; no current candidate.')
            self.status.configure(text=f'Unable to prepare Timesheet preview: {exc}')
        except Exception as secondary:
            exc.add_note(f'Timesheet error presentation failed: {secondary!r}')
        self.owner._diagnose(exc)
        return False

    def present(self): self.window.deiconify()

    def _mapped(self,event):
        if event.widget is not self.window or self.presented or self.disposed: return
        try:
            current = self.window.grab_current()
            parent = self.owner.root
            if current is not None and (current not in (self.window,parent) or current.grab_status()!='local'):
                raise ValueError('Timesheet cannot replace an unrelated or global grab')
            if current is not self.window:
                self.window.grab_set()
            self.presented = True
            self.close_button.focus_set()
            self.owner._timesheet_presented(self)
            self.choices_token,_ = self.owner._timesheet_read(self,'timesheet_tasks',None)
        except Exception as primary:
            self.owner._timesheet_launch_failed(self,primary)

    def open_picker(self,variable):
        if self.disposed or self.period.get()!='Custom': return False
        try: seed = parse_date(variable.get())
        except ValueError:
            if self.observation is None:
                self.observation = to_us(self.owner.now_utc())  # Explicit picker seed only, never a report cutoff.
            seed = from_us(self.observation).astimezone(self.owner.zone).date()
        self.close_picker()
        self.picker = ttk.LabelFrame(self.calendar_area,text='Choose a draft date')
        self.picker.grid()
        self._picker_variable,self._picker_month = variable,seed.replace(day=1)
        self._draw_calendar()
        return True

    def _draw_calendar(self):
        for child in self.picker.winfo_children(): child.destroy()
        month = self._picker_month
        self.previous_month = ttk.Button(self.picker,text='Previous month',command=lambda:self._move_month(-1))
        self.previous_month.grid(row=0,column=0,columnspan=2)
        ttk.Label(self.picker,text=f'{calendar.month_name[month.month]} {month.year:04d}').grid(row=0,column=2,columnspan=3)
        self.next_month = ttk.Button(self.picker,text='Next month',command=lambda:self._move_month(1))
        self.next_month.grid(row=0,column=5,columnspan=2)
        self.previous_month.configure(state='disabled' if month==date.min else 'normal')
        self.next_month.configure(state='disabled' if (month.year,month.month)==(9999,12) else 'normal')
        for col,label in enumerate(calendar.day_abbr): ttk.Label(self.picker,text=label).grid(row=1,column=col)
        self.day_buttons = {}
        for row,week in enumerate(calendar.Calendar().monthdayscalendar(month.year,month.month),2):
            for col,day in enumerate(week):
                if day:
                    button = ttk.Button(self.picker,text=str(day),width=4,command=lambda d=day:self._choose_day(d))
                    button.grid(row=row,column=col); self.day_buttons[day] = button
        self.picker_cancel = ttk.Button(self.picker,text='Cancel',command=self.close_picker)
        self.picker_cancel.grid(row=8,column=0,columnspan=7)

    def _move_month(self,amount):
        if self.picker is None: return
        index = (self._picker_month.year-1)*12+self._picker_month.month-1+amount
        if 0<=index<9999*12:
            self._picker_month = date(index//12+1,index%12+1,1); self._draw_calendar()

    def _choose_day(self,day):
        if self.picker is not None:
            self._picker_variable.set(self._picker_month.replace(day=day).isoformat()); self.close_picker()

    def close_picker(self):
        if self.picker is not None:
            self.picker.destroy(); self.picker = None

    def _escape(self,event=None):
        if self.picker is not None: self.close_picker()
        else: self.close()
        return 'break'

    def close(self,*,primary=None):
        if self.disposed or self.window is None: return True
        self._disposal_primary = primary
        error = None
        try:
            if self.window.grab_current() is self.window: self.window.grab_release()
        except Exception as exc: error = exc
        try: self.window.destroy()
        except Exception as exc:
            if error is None: raise
            error.add_note(f'Timesheet destruction also failed: {exc!r}')
        if error is not None: raise error
        return True

    def _destroyed(self,event):
        if event.widget is self.window and not self.disposed:
            self.disposed,self.presented,self.current = True,False,False
            self.picker = None
            self.preview_token = self.choices_token = None
            if self._constructed: self.owner._timesheet_disposed(self,self._disposal_primary)
