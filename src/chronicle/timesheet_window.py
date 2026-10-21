"""Owned frozen Timesheet Preview, Save and recovery; all I/O belongs to the worker."""
import calendar
from datetime import date
from dataclasses import replace
from copy import deepcopy
from uuid import uuid4
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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
        self.mode = 'preview'
        self.polr_tokens = {}
        self.polr_ready = False
        self.polr_proposal = self.polr_context = None
        self.polr_selected = set()
        self.polr_acks = {}
        self.polr_stale = False
        self.polr_return_mode = 'preview'
        self._dialog_busy = False
        self.saved_token = None
        self.saved_kind = None
        self.saved_identity = None
        self.load_state = 'Not previewed'
        try:
            self.window = tk.Toplevel(owner.root)
            self.window.withdraw()
            self.window.transient(owner.root)
            self.window.title('Timesheet / POL-R')
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
        self.save_bar = ttk.Frame(self.window)
        self.save_bar.grid(row=5,column=0,sticky='w',padx=8,pady=5)
        self.save_button = ttk.Button(self.save_bar,text='Save Timesheet',command=self.save)
        self.retry_save_button = ttk.Button(self.save_bar,text='Retry Save',command=self.retry_save)
        self.copy_button = ttk.Button(self.save_bar,text='Save Copy As',command=self.save_copy_as)
        self.check_button = ttk.Button(self.save_bar,text='Check File Status',command=self.check_file_status)
        self.overwrite_button = ttk.Button(self.save_bar,text='Overwrite',command=self.overwrite)
        self.saved_button = ttk.Button(self.save_bar,text='Saved Reports',command=self.saved_reports)
        self.new_button = ttk.Button(self.save_bar,text='New Preview',command=self.new_preview)
        for col,button in enumerate((self.save_button,self.retry_save_button,self.copy_button,self.check_button,
                                     self.overwrite_button,self.saved_button,self.new_button)):
            button.grid(row=col//4,column=col%4,padx=2,pady=2)
        self.saved_panel = ttk.Frame(self.window)
        self.saved_panel.grid(row=1,column=0,sticky='nsew',padx=8)
        self.saved_panel.columnconfigure(0,weight=1)
        self.saved_list = ttk.Treeview(self.saved_panel,columns=('report',),show='headings',height=4,selectmode='browse')
        self.saved_list.heading('report',text='Registered report UUID / dates / cutoff / scope / historical labels')
        self.saved_list.column('report',width=850,minwidth=200)
        self.saved_list.grid(row=0,column=0,sticky='ew')
        scroll = ttk.Scrollbar(self.saved_panel,orient='horizontal',command=self.saved_list.xview)
        scroll.grid(row=1,column=0,sticky='ew'); self.saved_list.configure(xscrollcommand=scroll.set)
        scroll_y = ttk.Scrollbar(self.saved_panel,orient='vertical',command=self.saved_list.yview)
        scroll_y.grid(row=0,column=1,sticky='ns'); self.saved_list.configure(yscrollcommand=scroll_y.set)
        self.load_saved_button = ttk.Button(self.saved_panel,text='Load registered report',command=self.load_saved)
        self.load_saved_button.grid(row=2,column=0,sticky='w')
        self.saved_panel.grid_remove()
        self._build_polr()
        self.close_button = ttk.Button(self.window,text='Close',command=self.close)
        self.close_button.grid(row=7,column=0,sticky='e',padx=8,pady=6)
        for var in (self.period,self.start,self.end,self.scope):
            var.trace_add('write',lambda *args:self.draft_changed())
        self.controls()

    def controls(self):
        if self.disposed: return
        locked = self.is_locked()
        custom = self.period.get()=='Custom'
        self.period_control.configure(state='disabled' if locked else 'readonly')
        self.scope_control.configure(state='disabled' if locked else 'readonly')
        self.preview_button.configure(state='disabled' if locked else 'normal')
        self.tasks.state(['disabled'] if locked else ['!disabled'])
        for control in self.date_controls: control.configure(state='normal' if custom and not locked else 'disabled')
        if locked: self.close_picker()
        attempt = self.owner._timesheet_attempt
        busy = self.is_busy()
        from .timesheet_files import FileState
        registered = attempt is not None and attempt.registration=='committed'
        active = not busy and self.saved_token is None and not self.mode.startswith('confirmation_')
        for button,allowed in ((self.save_button,active and not locked and self.current),
                               (self.retry_save_button,active and attempt is not None and (attempt.saved_path is None or (attempt.inspection is not None and attempt.inspection.state!=FileState.READY))),
                               (self.copy_button,active and registered), (self.check_button,active and registered),
                               (self.saved_button,active and self.can_leave_attempt()),
                               (self.new_button,active and self.can_leave_attempt())):
            button.configure(state='normal' if allowed else 'disabled')
        eligible = registered and attempt.inspection is not None and attempt.inspection.state==FileState.CONFLICT and attempt.inspection.conflict is not None
        self.overwrite_button.configure(state='normal' if active and eligible else 'disabled')
        if eligible: self.overwrite_button.grid()
        else: self.overwrite_button.grid_remove()
        self.load_saved_button.configure(state='normal' if active and self.mode=='saved' else 'disabled')
        if not custom: self.close_picker()
        self.polr_controls()

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
        if self.disposed or not self.presented or self.owner.timesheet is not self or self.is_locked():
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
        self.controls()

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

    def mutation_allowed(self):
        attempt = self.owner._timesheet_attempt
        if self.mode in ('confirmation_source','confirmation_manual'):
            return self.polr_ready and not self.polr_stale and not self._dialog_busy
        return (not self.disposed and not self._dialog_busy and self.mode=='preview' and self.current
                and (attempt is None or attempt.registration=='not attempted'))

    def is_busy(self):
        return self._dialog_busy or self.owner.executing or self.owner._timesheet_dialog_busy

    def is_locked(self):
        return self._dialog_busy or self.mode!='preview' or self.owner._timesheet_attempt is not None

    def can_leave_attempt(self):
        submission=getattr(self.owner,'_polr_submission',None)
        if submission is not None and submission.request is self.owner.pending:return False
        a = self.owner._timesheet_attempt
        return a is None or a.registration not in ('unverified','registering')

    def restore_modal(self,focus=None):
        if self.disposed or not self.presented or not widget_live(self.window) or not self.window.winfo_viewable(): return False
        current = self.window.grab_current()
        if current is not None and (current is not self.window or current.grab_status()!='local'): return False
        if current is not self.window: self.window.grab_set()
        target = focus if widget_live(focus) and focus.winfo_toplevel() is self.window else self.close_button
        target.focus_set()
        return True

    def dialog(self,callback):
        if self.is_busy(): return None
        focus = self.window.focus_get()
        self._dialog_busy,self.owner.executing = True,True
        primary_error = None
        try:
            self.controls()
            try: result = callback()
            except BaseException as primary:
                try: self.restore_modal(focus)
                except Exception as secondary: primary.add_note(f'Timesheet dialog return failed: {secondary!r}')
                primary_error = primary
                raise
            else:
                self.restore_modal(focus)
                return result
        except BaseException as primary:
            primary_error = primary
            raise
        finally:
            self._dialog_busy,self.owner.executing = False,False
            try: self.controls()
            except Exception as secondary:
                if primary_error is not None: primary_error.add_note(f'Timesheet dialog controls also failed: {secondary!r}')
                else: raise

    @staticmethod
    def path_text(value):
        from pathlib import Path
        if not isinstance(value,(str,Path)) or not str(value).strip() or '\x00' in str(value):
            raise ValueError('Choose a nonempty file path without NUL characters')
        return str(value)

    def choose_destination(self):
        selected = self.dialog(lambda:filedialog.asksaveasfilename(parent=self.window,title='Save frozen timesheet',
                        defaultextension='.txt',filetypes=(('Text files','*.txt'),),confirmoverwrite=False))
        return None if selected in ('',None) else self.path_text(selected)

    def save(self):
        if self.is_busy() or self.is_locked() or not self.current: return False
        reviewed = self.get_prepared_export()
        try:
            destination = self.choose_destination()
            if destination is None: return False
            if self.get_prepared_export()!=reviewed:
                raise ValueError('Preview changed; review a fresh Preview before Save')
            frozen = validate(replace(reviewed,preferred_destination=destination) if reviewed.preferred_destination is None else reviewed)
            return self.owner._timesheet_begin_save(self,frozen,destination)
        except Exception as exc: return self.save_failure(exc)
        finally: self.controls()

    def retry_save(self):
        a = self.owner._timesheet_attempt
        if self.is_busy() or a is None: return False
        if a.registration!='committed': return self.owner._timesheet_retry_registration()
        if a.saved_path is not None:
            from .timesheet_files import FileState
            if a.inspection is None or a.inspection.state==FileState.READY: return False
            a.saved_path = None
        if a.destination is None: return self.save_copy_as()
        return self.owner._timesheet_file('timesheet_publish')

    def save_copy_as(self):
        a = self.owner._timesheet_attempt
        if self.is_busy() or a is None or a.registration!='committed': return False
        try:
            destination = self.choose_destination()
            if destination is None: return False
            # New copy is a new file call, not a new report or registration.
            a.saved_path = None
            return self.owner._timesheet_file('timesheet_publish',destination=destination)
        except Exception as exc: return self.save_failure(exc)

    def check_file_status(self):
        a = self.owner._timesheet_attempt
        if self.is_busy() or a is None or a.registration!='committed': return False
        return self.owner._timesheet_file('timesheet_status')

    def overwrite(self):
        from .timesheet_files import FileState
        a = self.owner._timesheet_attempt
        if (self.is_busy() or a is None or a.inspection is None or a.inspection.state!=FileState.CONFLICT
                or a.inspection.conflict is None): return False
        reviewed = a.inspection.conflict
        try:
            yes = self.dialog(lambda:messagebox.askyesno('Overwrite existing timesheet?',
                f'The selected file contains different content:\n{a.destination}\nReplace it with the frozen registered report? '
                "Chronicle's immutable evidence will not change. This cannot be undone through Chronicle.",parent=self.window,default=messagebox.NO))
            if not yes: return False
            a.saved_path = None
            return self.owner._timesheet_file('timesheet_publish',confirmed_overwrite=True,expected_conflict=reviewed)
        except Exception as exc: return self.save_failure(exc)

    def save_failure(self,exc):
        try: self.status.configure(text=f'Timesheet operation did not complete: {exc}')
        except Exception as secondary: exc.add_note(f'Timesheet diagnostic failed: {secondary!r}')
        self.owner._diagnose(exc)
        return False

    def save_changed(self):
        a = self.owner._timesheet_attempt
        if self.disposed or a is None: return
        if a.saved_path is not None:
            text = f'File verified — Save complete: {a.saved_path}\nReport UUID: {a.candidate.export_id}. Not confirmed with POL-R.'
        elif a.file_token is not None:
            text = ('Publishing frozen registered report' if a.file_kind=='timesheet_publish' else 'Checking current file status')+'…'
        elif a.registration=='committed':
            state = a.inspection.state.value if a.inspection else 'publication pending'
            text = f'Registered export: {a.candidate.export_id} — {state}. Recoverable in Saved Reports.'
        elif a.registration=='unverified':
            text = 'Registration unverified; it may have committed. Retry/Reconcile retains the identical request.'
        else: text = f'Registration: {a.registration}.'
        if a.inspection is not None:
            if a.saved_path is not None and a.inspection.state.value!='READY':
                text = f'Earlier Save completed: {a.saved_path}. Report UUID: {a.candidate.export_id}.'
            text += f'\nCurrent destination observation: {a.inspection.state.value} — {a.inspection.destination or "no destination"}.'
        if a.error: text += f'\n{a.error}'
        self.status.configure(text=text)
        self.controls()

    def confirm_leave(self):
        a = self.owner._timesheet_attempt
        if not self.can_leave_attempt(): return False
        if a is None or a.registration!='committed' or not a.started or a.saved_path is not None: return True
        return bool(self.dialog(lambda:messagebox.askyesno('Unfinished Timesheet file save',
            f'File Save is unfinished for registered report {a.candidate.export_id}. Close this attempt? '
            'The frozen report remains recoverable in Saved Reports. No evidence or external file is undone.',
            parent=self.window,default=messagebox.NO)))

    def saved_reports(self):
        if self.is_busy() or not self.can_leave_attempt(): return False
        try:
            if not self.confirm_leave(): return False
            self.owner._timesheet_detach()
            self.preview_token = None
            self.current = False
            self._hide_polr()
            self.mode = 'saved'
            self.close_picker()
            self.saved_panel.grid()
            self.saved_token,_ = self.owner._timesheet_read(self,'timesheet_exports',None)
            self.saved_kind = 'timesheet_exports'
            self.context.configure(text='Loading registered reports; no file is assumed verified.')
            self.controls()
            return True
        except Exception as exc: return self.save_failure(exc)

    def load_saved(self):
        if self.is_busy() or self.saved_token is not None or self.mode!='saved': return False
        selected = self.saved_list.selection()
        if not selected: return False
        try:
            if not self.confirm_leave(): return False
            self.owner._timesheet_detach()
            self.saved_identity = selected[0]
            self.saved_token,_ = self.owner._timesheet_read(self,'timesheet_export',self.saved_identity)
            self.saved_kind = 'timesheet_export'
            self.controls()
            return True
        except Exception as exc: return self.save_failure(exc)

    def receive_saved(self,kind,token,value):
        if self.disposed or self.saved_token!=token or self.saved_kind!=kind or self.mode!='saved': return
        self.saved_token = None
        try:
            if isinstance(value,Outcome): raise value.error or ValueError('Registered reports unavailable')
            if kind=='timesheet_exports':
                rows = [(r['export_id'], f"{r['export_id']} | {r['start_date']} to {r['end_date']} | "
                         f"{from_us(r['cutoff_utc_us']).isoformat()} | {r['timezone']} | week starts {r['week_start']} | "
                         f"{r['scope_kind']} | "+'; '.join(t.name for t in r['tasks'])) for r in value]
                self.saved_list.delete(*self.saved_list.get_children())
                for key,text in rows: self.saved_list.insert('','end',iid=key,values=(text,))
                self.context.configure(text='Registered exports (SQLite evidence). Select and load one; file status requires explicit inspection.')
            else:
                candidate = validate(value,check_render=False)
                if candidate.export_id != self.saved_identity: raise ValueError('Recovered export identity changed')
                self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',candidate.report_text)
                self.report.configure(state='disabled');self.report.grid()
                self.context.configure(text=f'Registered export: {candidate.export_id}; {candidate.start_date} to {candidate.end_date}; '
                    f'as of UTC {from_us(candidate.cutoff_utc_us).isoformat()}. Original destination: '
                    +(candidate.preferred_destination if candidate.preferred_destination else 'No original destination recorded.'))
                if not self.owner._timesheet_recover(candidate):
                    raise RuntimeError('Registered report could not be installed for this view')
                self.candidate,self.current = candidate,False
                self.save_changed()
            self.controls()
        except Exception as exc:
            if kind=='timesheet_export': self.owner._timesheet_detach()
            try: self.report.grid_remove();self.report.configure(state='disabled')
            except Exception as secondary: exc.add_note(f'Recovery display invalidation failed: {secondary!r}')
            self.current = False
            self.save_failure(exc)

    def new_preview(self):
        if self.is_busy() or not self.can_leave_attempt(): return False
        try:
            if not self.confirm_leave(): return False
            self.owner._timesheet_detach()
            self.saved_token = self.preview_token = None
            self._hide_polr()
            self.mode = 'preview'
            self.candidate,self.current = None,False
            self.period.set('This week');self.scope.set('All tasks');self.start.set('');self.end.set('')
            self.tasks.selection_remove(*self.tasks.selection())
            self.saved_panel.grid_remove()
            self.report.configure(state='normal');self.report.delete('1.0','end');self.report.configure(state='disabled');self.report.grid()
            self.context.configure(text='Not previewed. New Preview will create a separate report identity.')
            self.status.configure(text='');self.controls()
            return True
        except Exception as exc: return self.save_failure(exc)

    def _build_polr(self):
        bar=ttk.Frame(self.window);bar.grid(row=6,column=0,sticky='w',padx=8)
        self.review_polr_button=ttk.Button(bar,text='Review POL-R Confirmation',command=self.review_polr)
        self.manual_polr_button=ttk.Button(bar,text='Manual POL-R Confirmation',command=self.manual_polr)
        self.polr_history_button=ttk.Button(bar,text='Confirmation History',command=self.confirmation_history)
        for i,b in enumerate((self.review_polr_button,self.manual_polr_button,self.polr_history_button)):b.grid(row=0,column=i,padx=2)
        self.polr_panel=ttk.Frame(self.window);self.polr_panel.grid(row=3,column=0,sticky='nsew',padx=8)
        self.polr_panel.columnconfigure(0,weight=1);self.polr_panel.rowconfigure(2,weight=1)
        ttk.Label(self.polr_panel,text='Confirmation records your entered POL-R values; it does not query or verify POL-R.',wraplength=750).grid(row=0,column=0,sticky='w')
        self.polr_manual=ttk.Frame(self.polr_panel);self.polr_manual.grid(row=1,column=0,sticky='ew')
        self.polr_task=tk.StringVar(self.window,'');self.polr_date=tk.StringVar(self.window,'');self.polr_hours=tk.StringVar(self.window,'')
        self.polr_task_choices=[]
        for row,text in enumerate(('Task UUID','Work date YYYY-MM-DD','Absolute POL-R hours')):ttk.Label(self.polr_manual,text=text).grid(row=row,column=0,sticky='w')
        self.polr_task_control=ttk.Combobox(self.polr_manual,textvariable=self.polr_task,state='readonly',width=48)
        self.polr_date_control=ttk.Entry(self.polr_manual,textvariable=self.polr_date,width=14)
        self.polr_hours_control=ttk.Entry(self.polr_manual,textvariable=self.polr_hours,width=12)
        for i,w in enumerate((self.polr_task_control,self.polr_date_control,self.polr_hours_control)):w.grid(row=i,column=1,padx=2,sticky='w')
        self.polr_context_button=ttk.Button(self.polr_manual,text='Review current',command=self.refresh_polr)
        self.polr_context_button.grid(row=3,column=0,sticky='w')
        self.polr_task.trace_add('write',lambda *a:self._manual_polr_dirty())
        self.polr_date.trace_add('write',lambda *a:self._manual_polr_dirty())
        holder=ttk.Frame(self.polr_panel);holder.grid(row=2,column=0,sticky='nsew');holder.columnconfigure(0,weight=1);holder.rowconfigure(0,weight=1)
        self.polr_tree=ttk.Treeview(holder,show='headings',height=5,selectmode='browse')
        self.polr_tree.grid(row=0,column=0,sticky='nsew')
        for orient,row,col,command in (('vertical',0,1,self.polr_tree.yview),('horizontal',1,0,self.polr_tree.xview)):
            b=ttk.Scrollbar(holder,orient=orient,command=command);b.grid(row=row,column=col,sticky='ns' if orient=='vertical' else 'ew')
            self.polr_tree.configure(**{('yscrollcommand' if orient=='vertical' else 'xscrollcommand'):b.set})
        self.polr_tree.bind('<Button-1>',self._polr_click,add='+')
        ack_holder=ttk.Frame(self.polr_panel);ack_holder.grid(row=3,column=0,sticky='ew');ack_holder.columnconfigure(0,weight=1)
        ack_canvas=tk.Canvas(ack_holder,height=85,highlightthickness=0);ack_canvas.grid(row=0,column=0,sticky='ew')
        self.polr_ack_frame=ttk.Frame(ack_canvas);ack_canvas.create_window(0,0,window=self.polr_ack_frame,anchor='nw')
        self.polr_ack_frame.bind('<Configure>',lambda event:ack_canvas.configure(scrollregion=ack_canvas.bbox('all')))
        for orient,row,col,command in (('vertical',0,1,ack_canvas.yview),('horizontal',1,0,ack_canvas.xview)):
            scroll=ttk.Scrollbar(ack_holder,orient=orient,command=command);scroll.grid(row=row,column=col,sticky='ns' if orient=='vertical' else 'ew')
            ack_canvas.configure(**{('yscrollcommand' if orient=='vertical' else 'xscrollcommand'):scroll.set})
        detail=ttk.Frame(self.polr_panel);detail.grid(row=4,column=0,sticky='ew');detail.columnconfigure(0,weight=1)
        self.polr_detail=tk.Text(detail,wrap='word',height=4,state='disabled');self.polr_detail.grid(row=0,column=0,sticky='ew')
        detail_scroll=ttk.Scrollbar(detail,orient='vertical',command=self.polr_detail.yview);detail_scroll.grid(row=0,column=1,sticky='ns')
        self.polr_detail.configure(yscrollcommand=detail_scroll.set)
        self.polr_status=ttk.Label(self.polr_panel,text='',wraplength=750);self.polr_status.grid(row=5,column=0,sticky='ew')
        self.polr_actions=ttk.Frame(self.polr_panel);self.polr_actions.grid(row=6,column=0,sticky='w')
        self.polr_positive_button=ttk.Button(self.polr_actions,text='Select all positive suggestions',command=self.polr_positive)
        self.polr_confirm_button=ttk.Button(self.polr_actions,text='Confirm checked',command=self.confirm_polr)
        self.polr_refresh_button=ttk.Button(self.polr_actions,text='Refresh review',command=self.refresh_polr)
        self.polr_defer_button=ttk.Button(self.polr_actions,text='Defer / Review later',command=self.defer_polr)
        self.polr_retry_button=ttk.Button(self.polr_actions,text='Retry/Reconcile',command=self.retry_polr)
        self.polr_load_button=ttk.Button(self.polr_actions,text='Read batch',command=self.load_polr_batch)
        for i,b in enumerate((self.polr_positive_button,self.polr_confirm_button,self.polr_refresh_button,self.polr_defer_button,self.polr_retry_button,self.polr_load_button)):
            b.grid(row=i//3,column=i%3,padx=2,pady=2)
        self.polr_panel.grid_remove()

    def _polr_pending(self):
        s=getattr(self.owner,'_polr_submission',None)
        return s is not None and s.request is self.owner.pending

    def polr_controls(self):
        if self.disposed:return
        pending=self._polr_pending();active=not self.is_busy() and self.can_leave_attempt()
        a=self.owner._timesheet_attempt
        for b,allowed in ((self.review_polr_button,active and a is not None and a.registration=='committed'),
                          (self.manual_polr_button,active),(self.polr_history_button,active)):
            b.configure(state='normal' if allowed else 'disabled')
        source=self.mode=='confirmation_source';manual=self.mode=='confirmation_manual';history=self.mode=='confirmation_history'
        for b,allowed in ((self.polr_positive_button,active and source and self.polr_ready),
                          (self.polr_confirm_button,active and (source or manual) and self.polr_ready and not self.polr_stale),
                          (self.polr_refresh_button,active and (source or manual)),(self.polr_defer_button,active),
                          (self.polr_retry_button,not self.is_busy() and pending),(self.polr_load_button,active and history)):
            b.configure(state='normal' if allowed else 'disabled')
        self.polr_task_control.configure(state='readonly' if active else 'disabled')
        for field in (self.polr_date_control,self.polr_hours_control):field.configure(state='normal' if active else 'disabled')
        self.polr_context_button.configure(state='normal' if active else 'disabled')
        for var,button in self.polr_acks.values():button.configure(state='normal' if active else 'disabled')

    def _show_polr(self,mode):
        if self.is_busy() or not self.can_leave_attempt():return False
        if not self.mode.startswith('confirmation_'):self.polr_return_mode=self.mode
        self.polr_tokens.clear();self.polr_ready=False;self.polr_stale=False
        self.saved_token=self.preview_token=None  # Abandon earlier view reads, never their worker operations.
        self.polr_proposal=self.polr_context=None
        self.mode=mode;self.close_picker();self.report.master.grid_remove();self.polr_panel.grid()
        self.polr_confirm_button.configure(text='Confirm absolute amount' if mode=='confirmation_manual' else 'Confirm checked')
        self.polr_defer_button.configure(text='Cancel' if mode=='confirmation_manual' else 'Defer / Review later')
        self.polr_manual.grid() if mode=='confirmation_manual' else self.polr_manual.grid_remove()
        self.polr_detail.configure(state='normal');self.polr_detail.delete('1.0','end');self.polr_detail.configure(state='disabled')
        self.polr_status.configure(text='Read-only review; nothing confirmed.')
        self.polr_tree.delete(*self.polr_tree.get_children());self.polr_mapping={};self._draw_polr_acks()
        self.controls();return True

    def _hide_polr(self):
        self.polr_tokens.clear();self.polr_ready=False
        self.polr_panel.grid_remove();self.report.master.grid()

    def review_polr(self):
        a=self.owner._timesheet_attempt
        if a is None or a.registration!='committed' or not self._show_polr('confirmation_source'):return False
        self.polr_source_id=a.candidate.export_id
        return self.refresh_polr()

    def manual_polr(self):
        if not self._show_polr('confirmation_manual'):return False
        self.polr_task_choices=list(self.tasks.get_children())
        labels=[str(self.tasks.item(k,'values')[0])+(' [Deleted]' if self.tasks.item(k,'values')[2]=='Deleted' else '') for k in self.polr_task_choices]
        self.polr_task_control.configure(values=labels)
        if labels:self.polr_task_control.current(0)
        self.polr_date.set(from_us(to_us(self.owner.now_utc())).astimezone(self.owner.zone).date().isoformat())
        self.polr_hours.set('');self.controls();return True

    def confirmation_history(self):
        if not self._show_polr('confirmation_history'):return False
        self._polr_columns(('batch','audit','source'),('Batch UUID','Audit UTC','Source / Manual'))
        return self._read_polr('polr_history',None)

    def _polr_columns(self,columns,labels):
        self.polr_tree.configure(columns=columns)
        for column,label in zip(columns,labels):
            self.polr_tree.heading(column,text=label);self.polr_tree.column(column,width=180 if column!='task' else 320,minwidth=60,stretch=False)

    def _read_polr(self,kind,value):
        try:
            token,_=self.owner._timesheet_read(self,kind,value);self.polr_tokens[kind]=token
            if kind=='polr_day':self.polr_day_key=(value['task_id'],value['work_date'])
            return True
        except Exception as exc:return self.polr_failure(exc)

    def _manual_polr_dirty(self):
        if self.mode=='confirmation_manual':
            self.polr_context=None;self.polr_ready=False;self.polr_tokens.pop('polr_manual',None);self.polr_tokens.pop('polr_day',None)
            self.polr_status.configure(text='Task/date changed; Review current before confirming.')
            self.polr_controls()

    def refresh_polr(self):
        if self.is_busy() or not self.can_leave_attempt():return False
        self.polr_ready=False;self.polr_stale=False
        self.polr_selected.clear();self._draw_polr_acks()
        if self.mode=='confirmation_manual':self.polr_confirm_button.configure(text='Confirm absolute amount')
        else:self.polr_confirm_button.configure(text='Confirm checked')
        if self.mode=='confirmation_source':return self._read_polr('polr_proposal',self.polr_source_id)
        if self.mode=='confirmation_manual':
            try:
                index=self.polr_task_control.current()
                if index<0:raise ValueError('Choose a retained task UUID')
                task=self.polr_task_choices[index];day=parse_date(self.polr_date.get()).isoformat()
                self.polr_date.set(day)
                self.polr_manual_key=(task,day)
                return self._read_polr('polr_manual',dict(task_id=task,work_date=day,cutoff_utc_us=to_us(self.owner.now_utc())))
            except Exception as exc:return self.polr_failure(exc)
        return False

    def receive_polr(self,kind,token,value):
        if self.disposed or self.polr_tokens.get(kind)!=token:return
        self.polr_tokens.pop(kind)
        try:
            if isinstance(value,Outcome):raise value.error or ValueError('Confirmation read unavailable')
            if kind=='polr_proposal':
                if self.mode!='confirmation_source' or value['source_metadata']['export_id']!=self.polr_source_id:raise ValueError('Confirmation review source changed')
                self.polr_proposal=deepcopy(value)
                self.polr_mapping={f'p{i}':r for i,r in enumerate(value['reviewed_rows'])}
                self.polr_selected={(r['task_id'],r['work_date']) for r in value['selected_keys']}
                self.polr_ready=True;self.polr_stale=False
                self._render_polr_rows();self._draw_polr_acks()
            elif kind=='polr_manual':
                if self.mode!='confirmation_manual' or (value['task_id'],value['work_date'])!=self.polr_manual_key:raise ValueError('Manual review task/date changed')
                self.polr_context=deepcopy(value);self.polr_ready=True;self.polr_stale=False
                self._show_day_status(value)
            elif kind=='polr_day':
                if (value['task_id'],value['work_date'])!=self.polr_day_key:raise ValueError('Confirmation day status identity changed')
                self._show_day_status(value)
            elif kind=='polr_history':
                if self.mode!='confirmation_history':return
                self.polr_tree.delete(*self.polr_tree.get_children())
                for row in value:self.polr_tree.insert('','end',iid=row['batch_id'],values=(row['batch_id'],from_us(row['audit_utc_us']).isoformat(),row['source_export_id'] or 'Manual'))
            elif kind=='polr_batch':
                if self.mode!='confirmation_history' or value['batch_id']!=self.polr_batch_id:return
                from .polr_allocation import quarter_text
                lines=[f"Batch {value['batch_id']} | request {value['created_request_id']} | committed sequence {value['commit_seq']}"]
                for r in value['cells']:lines.append(f"{r['task_id']} / {r['work_date']}: {quarter_text(r['confirmed_quarters'])}; prior {r['expected_prior_batch_id']} / {r['expected_prior_quarters']}; stale acknowledgement {bool(r['stale_export_acknowledged'])}")
                self.polr_detail.configure(state='normal');self.polr_detail.delete('1.0','end');self.polr_detail.insert('1.0','\n'.join(lines));self.polr_detail.configure(state='disabled')
            self.controls()
        except Exception as exc:self.polr_failure(exc)

    def _render_polr_rows(self):
        from .polr_allocation import quarter_text
        self._polr_columns(('select','task','date','suggested','confirmed','prior','stale'),('Select','Task / UUID','Date','Frozen Suggested POL-R','Current Confirmed POL-R','Current Prior Identity','Stale Source Conflict'))
        self.polr_tree.column('select',width=65)
        self.polr_tree.delete(*self.polr_tree.get_children())
        for handle,r in self.polr_mapping.items():
            self.polr_tree.insert('','end',iid=handle,values=('☑' if (r['task_id'],r['work_date']) in self.polr_selected else '☐',
                f"{r['task_name']} / {r['task_id']}",r['work_date'],quarter_text(r['suggested_quarters']),
                'Unknown' if r['prior_quarters'] is None else quarter_text(r['prior_quarters'])+' (confirmed)',r['prior_batch_id'] or 'Unknown',
                'Yes' if r['requires_stale_acknowledgement'] else 'No'))

    def _polr_click(self,event):
        if self.mode!='confirmation_source' or self.is_busy() or not self.polr_ready or not self.can_leave_attempt():return
        if self.polr_tree.identify_column(event.x)!='#1':return
        row=self.polr_mapping.get(self.polr_tree.identify_row(event.y))
        if row:self.toggle_polr_cell((row['task_id'],row['work_date']));return 'break'

    def toggle_polr_cell(self,key):
        if self.is_busy() or not self.can_leave_attempt() or not self.polr_ready:return False
        if not any((r['task_id'],r['work_date'])==key for r in self.polr_mapping.values()):return False
        if key in self.polr_selected:self.polr_selected.remove(key)
        else:self.polr_selected.add(key)
        self._render_polr_rows();self._draw_polr_acks();return True

    def polr_positive(self):
        if self.mode!='confirmation_source' or not self.polr_ready or self.is_busy() or not self.can_leave_attempt():return False
        self.polr_selected={(r['task_id'],r['work_date']) for r in self.polr_mapping.values() if r['suggested_quarters']>0}
        self._render_polr_rows();self._draw_polr_acks();return True

    def _draw_polr_acks(self):
        if not hasattr(self,'polr_ack_frame'):return
        previous={k:var.get() for k,(var,b) in self.polr_acks.items() if k in self.polr_selected}
        for child in self.polr_ack_frame.winfo_children():child.destroy()
        self.polr_acks={}
        from .polr_allocation import quarter_text
        for row in getattr(self,'polr_mapping',{}).values():
            k=(row['task_id'],row['work_date'])
            if k not in self.polr_selected or not row['requires_stale_acknowledgement']:continue
            var=tk.BooleanVar(self.window,previous.get(k,False))
            b=ttk.Checkbutton(self.polr_ack_frame,variable=var,text=f"Acknowledge replacing this newer confirmed value: {row['task_name']} / {k[0]} / {k[1]}; frozen {quarter_text(row['suggested_quarters'])}, prior {quarter_text(row['prior_quarters'])} / {row['prior_batch_id']}")
            b.grid(sticky='w');self.polr_acks[k]=(var,b)

    def confirm_polr(self):
        if self.is_busy() or not self.can_leave_attempt() or not self.polr_ready or self.polr_stale:return False
        from .polr_confirmation import parse_hours
        try:
            args=dict(batch_id=str(uuid4()),mode='source',source_export_id=None,source_metadata=None,reviewed_rows=[],selected_keys=[],manual_cells=[],acknowledgements=[])
            if self.mode=='confirmation_source':
                if not self.polr_selected:raise ValueError('Check at least one genuine source cell; empty does not mean All')
                if any(not var.get() for var,b in self.polr_acks.values()):raise ValueError('Explicitly acknowledge each selected stale conflict')
                args.update(source_export_id=self.polr_source_id,source_metadata=deepcopy(self.polr_proposal['source_metadata']),
                            reviewed_rows=deepcopy(self.polr_proposal['reviewed_rows']),selected_keys=[dict(task_id=t,work_date=d) for t,d in sorted(self.polr_selected)])
                for row in self.polr_proposal['reviewed_rows']:
                    k=(row['task_id'],row['work_date'])
                    if k in self.polr_acks:args['acknowledgements'].append(dict(task_id=k[0],work_date=k[1],suggested_quarters=row['suggested_quarters'],reviewed_prior_batch_id=row['prior_batch_id'],reviewed_prior_quarters=row['prior_quarters']))
            elif self.mode=='confirmation_manual':
                c=self.polr_context
                args.update(mode='manual',manual_cells=[dict(task_id=c['task_id'],work_date=c['work_date'],confirmed_quarters=parse_hours(self.polr_hours.get()),prior_batch_id=c['current_batch_id'],prior_quarters=c['confirmed_quarters'])])
            else:return False
            return self.owner._polr_submit(self,args)
        except Exception as exc:return self.polr_failure(exc,retain_review=True)

    def polr_result(self,result):
        from .records import StaleState
        if result.status=='committed':
            self.polr_status.configure(text=f"Committed confirmation {result.result['batch_id']}. This records your statement, not independent POL-R verification.")
            if self.mode in ('confirmation_source','confirmation_manual'):
                submitted=self.owner._polr_submission.request.args()
                keys=[(r['task_id'],r['work_date']) for r in (submitted['selected_keys'] if submitted['mode']=='source' else submitted['manual_cells'])]
                self.refresh_polr()
                if keys:
                    t,d=keys[0];self._read_polr('polr_day',dict(task_id=t,work_date=d,cutoff_utc_us=to_us(self.owner.now_utc())))
        else:
            self.polr_stale=isinstance(result.error,StaleState)
            self.polr_status.configure(text=f"Confirmation {result.status}: {result.error or ''}. "+('Explicit Refresh review is required.' if self.polr_stale else 'Reviewed inputs retained; no success is claimed.'))
        self.controls()

    def retry_polr(self):
        submission=getattr(self.owner,'_polr_submission',None)
        if self.is_busy() or submission is None or submission.request is not self.owner.pending:return False
        return self.owner.retry()

    def _show_day_status(self,c):
        from .polr_allocation import quarter_text,decimal_text
        confirmed='Unknown' if c['confirmed_quarters'] is None else quarter_text(c['confirmed_quarters'])+' (confirmed)'
        def signed(v):return ('+' if v>0 else '-' if v<0 else '')+f'{abs(v)//100}.{abs(v)%100:02d}'
        delta=('Unverified' if c['confirmed_quarters'] is None else 'Unavailable') if c['daily_delta_hundredths'] is None else signed(c['daily_delta_hundredths'])
        gap='unresolved' if c['suggested_entry_gap_quarters'] is None else signed(c['suggested_entry_gap_quarters']*25)
        self.polr_detail.configure(state='normal');self.polr_detail.delete('1.0','end')
        adjustment='Unavailable' if c['full_week_adjustment_us'] is None else str(c['full_week_adjustment_us'])+' µs'
        actual='Unavailable' if c['actual_us'] is None else str(c['actual_us'])+' µs / '+decimal_text(c['actual_hundredths'])
        suggested='Unavailable' if c['suggested_quarters'] is None else quarter_text(c['suggested_quarters'])
        self.polr_detail.insert('1.0',f"{c['task_name']} / {c['task_id']} / {c['work_date']} as of UTC {from_us(c['cutoff_utc_us']).isoformat()}\nActual: {actual}; Suggested: {suggested}; Confirmed: {confirmed}\nCurrent batch: {c['current_batch_id'] or 'Unknown'}; Daily Delta: {delta}; Suggested-entry gap: {gap}; full-week exact upward adjustment: {adjustment}. Differences may reflect weekly allocation.")
        self.polr_detail.configure(state='disabled')
        if c.get('calculation_error') is not None:
            self.polr_status.configure(text='Current Actual/suggestion context unavailable; reviewed confirmation prior remains available.')
            self.owner._diagnose(c['calculation_error'])

    def load_polr_batch(self):
        if self.mode!='confirmation_history' or self.is_busy() or not self.can_leave_attempt():return False
        selected=self.polr_tree.selection()
        if not selected:return False
        self.polr_batch_id=selected[0];return self._read_polr('polr_batch',self.polr_batch_id)

    def defer_polr(self):
        if self.is_busy() or not self.can_leave_attempt():return False
        self._hide_polr();self.mode=self.polr_return_mode;self.controls();return True

    def polr_failure(self,exc,*,retain_review=False):
        if not retain_review:self.polr_ready=False
        submission=getattr(self.owner,'_polr_submission',None)
        completed=(f"Committed confirmation {submission.outcome.result['batch_id']}. " if submission is not None and submission.outcome is not None and submission.outcome.status=='committed' else '')
        try:self.polr_status.configure(text=completed+f'Confirmation review/status unavailable: {exc}. Original evidence and any committed result are retained.')
        except Exception as secondary:exc.add_note(f'Confirmation diagnostic also failed: {secondary!r}')
        self.owner._diagnose(exc);self.polr_controls();return False

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
        if self.disposed or self.period.get()!='Custom' or self.is_locked(): return False
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

    def close(self,*,primary=None,force=False):
        if self.disposed or self.window is None: return True
        if not force:
            if self.is_busy(): return False
            attempt = self.owner._timesheet_attempt
            if attempt is not None and attempt.registration=='unverified':
                self.status.configure(text='Registration unverified; Retry/Reconcile or explicitly exit the application.')
                return False
            if not self.confirm_leave(): return False
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
            self.polr_tokens.clear()
            if self._constructed: self.owner._timesheet_disposed(self,self._disposal_primary)
