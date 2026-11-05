"""Complete candidate semantic boundary. No ordinary startup or writer authority."""
import sqlite3
from . import schema_profiles as schema
from .records import integer,canonical,uuid_text
from .timekeeping import load_zone,local_date,resolve_start


class Rows:
    """One connection view: named rows without changing caller row_factory."""
    def __init__(self,c):self.inner=c.inner if isinstance(c,Rows) else c
    def __getattr__(self,name):return getattr(self.inner,name)
    def execute(self,*args):return Cursor(self.inner.execute(*args))


class Cursor:
    def __init__(self,c):self.inner=c
    def __getattr__(self,name):return getattr(self.inner,name)
    def row(self,row):return None if row is None else sqlite3.Row(self.inner,tuple(row))
    def __iter__(self):return (self.row(row) for row in self.inner)
    def fetchone(self):return self.row(self.inner.fetchone())
    def fetchall(self):return list(self)


class Context:
    administrative_operations=schema.ADMINISTRATIVE_OPERATIONS

    @staticmethod
    def verify_administration(c,receipts):
        from .administration import verify_schema4_history
        facts={name:schema._rows(c,name) for name, in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        verify_schema4_history(facts['projects'],facts['tasks'],facts['committed_requests'],
                              facts['dataset_meta'][0]['dataset_id'],facts=facts)


def verify_transaction(c):
    """Read-only full verification within an already owned SQLite transaction."""
    from .sqlite_store import SQLiteStore as S
    if not c.in_transaction:raise ValueError('Complete candidate verification requires an owned transaction')
    schema.verify_structure(c)
    # SQLite's one declared AUTOINCREMENT table is the only extra table. Exact
    # candidate admission does not silently ignore internal-looking facts.
    import re
    tables={re.match(r'CREATE TABLE (\w+)',s)[1] for s in schema.schema_statements() if s.startswith('CREATE TABLE ')}|{'sqlite_sequence'}
    if {name for name, in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")}!=tables:
        raise ValueError('Unexpected candidate table coverage')
    named=Rows(c)
    meta=named.execute('SELECT * FROM dataset_meta').fetchone()
    load_zone(meta['timezone']);integer(meta['week_start'],'Week start',0,6)
    S.dismissed_date(named)
    S.assert_lifecycle(named,structure=schema.verify_structure)
    for row in named.execute('SELECT export_id FROM timesheet_exports'):S.read_export(named,row[0])
    S.assert_confirmations(named)
    S.verify_receipts(named,context=Context)
    # AUTOINCREMENT high water survives legitimate retired sequence gaps.
    sequences=schema._rows(c,'sqlite_sequence')
    if len(sequences)>1 or sequences and sequences[0]['name']!='committed_requests':raise ValueError('Invalid receipt sequence coverage')
    maximum=named.execute('SELECT COALESCE(max(commit_seq),0) FROM committed_requests').fetchone()[0]
    if maximum and not sequences:raise ValueError('Missing receipt sequence high water')
    if sequences and integer(sequences[0]['seq'],'Receipt sequence',0,2**63-1)<maximum:raise ValueError('Receipt high water is below retained chronology')
    return schema.CandidateVerification()


class WorkChronology:
    """Independent historical eligibility and active state, not mutation replay.

    Shared evidence checks prove immutable row/request contents; this traversal
    proves those effects were possible in their retained chronological context.
    """
    def __init__(self,facts):
        self.facts=facts;self.zone=load_zone(facts['dataset_meta'][0]['timezone'])
        self.active=None;self.entries={};self.week_start=6;self.dismissed=None
        self.revisions={r['request_id']:r for r in facts['work_revisions']}
        self.corrections={r['request_id']:r for r in facts['active_start_corrections']}

    def step(self,request,result,tasks,projects):
        from .recording_services import FIELDS
        from .hierarchy import candidate_task_observations
        op,a,now=request.operation,request.args(),request.action_utc_us
        if op not in FIELDS or set(a)!=FIELDS[op]:raise ValueError('Unknown or malformed protected request')
        local_date(now,self.zone)
        def eligible(identity,version=None):
            uuid_text(identity)
            if identity not in tasks:raise ValueError('Historical recording task missing')
            if version is not None:
                integer(version,'Reviewed task version',1,2**63-1)
                if tasks[identity]['version']!=version:raise ValueError('Historical recording task version differs')
            if not candidate_task_observations(list(tasks.values()),list(projects.values()))[identity]['eligible_for_new_work']:
                raise ValueError('Historical new work requires an effectively active leaf')
        def active(identity,version):
            integer(version,'Reviewed active version',1,2**63-1)
            if self.active is None or self.active['entry_id']!=identity or self.active['version']!=version:
                raise ValueError('Historical active state differs')
            return self.active
        if op in ('start_timer','switch_timer','add_timed_work','add_date_only_work'):
            identity=a['next_entry_id'] if op=='switch_timer' else a['entry_id']
            task=a['next_task_id'] if op=='switch_timer' else a['task_id']
            uuid_text(identity)
            if identity in self.entries:raise ValueError('Duplicate work creation identity')
            eligible(task,a['expected_task_version'] if op in ('start_timer','switch_timer') else None)
            if op=='start_timer' and self.active is not None:raise ValueError('Historical simultaneous timers')
            if op=='switch_timer':
                old=active(a['expected_active_entry_id'],a['expected_active_version'])
                if task==old['task_id'] or now<=old['start_utc_us']:raise ValueError('Invalid historical Switch')
                self.entries[old['entry_id']]['revision']=1
                revision=self.revisions.get(request.request_id)
                if revision is None or revision['start_utc_us']!=old['start_utc_us']:raise ValueError('Switch start differs')
            self.entries[identity]=dict(task_id=task,revision=0 if op in ('start_timer','switch_timer') else 1,deleted=False)
            if op in ('start_timer','switch_timer'):
                self.active=dict(singleton=1,entry_id=identity,task_id=task,start_utc_us=now,version=1)
        elif op=='stop_timer':
            old=active(a['entry_id'],a['expected_version'])
            if now<=old['start_utc_us']:raise ValueError('Historical Stop does not advance')
            revision=self.revisions.get(request.request_id)
            if revision is None or revision['start_utc_us']!=old['start_utc_us']:raise ValueError('Stopped start differs')
            self.entries[old['entry_id']]['revision']=1;self.active=None
        elif op=='correct_active_start':
            old=active(a['entry_id'],a['expected_version'])
            corrected=resolve_start(old['start_utc_us'],a['date_text'],a['time_text'],a['occurrence'],self.zone)
            if corrected==old['start_utc_us'] or corrected>now:raise ValueError('No-op or future historical correction')
            if request.request_id not in self.corrections:raise ValueError('Missing chronological correction')
            old.update(start_utc_us=corrected,version=old['version']+1)
        elif op in ('edit_closed_timed_work','edit_date_only_work','delete_work_entry'):
            identity=a['entry_id'];entry=self.entries.get(identity)
            integer(a['expected_revision'],'Reviewed revision',1,2**63-1)
            if entry is None or entry['task_id']!=a['task_id'] or entry['revision']!=a['expected_revision'] or entry['deleted']:
                raise ValueError('Historical reviewed work state differs')
            if self.active is not None and self.active['entry_id']==identity:raise ValueError('Cannot edit active work as closed')
            row=self.revisions.get(request.request_id)
            if row is None:raise ValueError('Missing historical revision')
            if op!='delete_work_entry':
                prior=next((r for r in self.facts['work_revisions'] if r['entry_id']==identity and r['revision']==a['expected_revision']),None)
                if prior is None or all(row[k]==prior[k] for k in ('start_utc_us','stop_utc_us','work_date','duration_us')):
                    raise ValueError('Missing prior or no-op work revision')
            entry.update(revision=entry['revision']+1,deleted=op=='delete_work_entry')
        elif op=='set_week_start':
            integer(a['week_start'],'Week start',0,6);integer(a['expected_week_start'],'Prior week start',0,6)
            if a['expected_week_start']!=self.week_start or a['week_start']==self.week_start:raise ValueError('Stale or no-op week configuration')
            self.week_start=a['week_start']
        elif op=='dismiss_polr_reminder_today':
            day=local_date(now,self.zone).isoformat()
            if a!={'local_date':day} or self.dismissed==day:raise ValueError('Incorrect or no-op dismissal')
            self.dismissed=day
        elif op=='register_timesheet_export':
            from .timesheet import from_content
            value=from_content(a['candidate'],check_render=False)
            if any(t.task_id not in tasks or t.project_id is not None and t.project_id not in projects for t in value.tasks):
                raise ValueError('Frozen identities were not present at registration')
        elif op=='confirm_polr_absolute':
            for field in ('reviewed_rows','selected_keys','manual_cells','acknowledgements'):
                if any(r['task_id'] not in tasks for r in a[field]):raise ValueError('Confirmation task was not present')

    def finish(self):
        expected=[] if self.active is None else [self.active]
        if expected!=self.facts['active_timer']:raise ValueError('Final active timer differs from chronological recording')
        actual={r['entry_id']:r for r in self.facts['work_entries']}
        if set(actual)!=set(self.entries):raise ValueError('Work creation chronology coverage differs')
        for key,value in self.entries.items():
            if actual[key]['task_id']!=value['task_id'] or actual[key]['current_revision']!=(value['revision'] or None):raise ValueError('Final work revision/owner differs')
        meta=self.facts['dataset_meta'][0]
        if (meta['week_start'],meta['polr_reminder_dismissed_local_date'])!=(self.week_start,self.dismissed):raise ValueError('Configuration/reminder history differs')
