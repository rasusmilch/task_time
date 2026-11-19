"""Complete schema-5 receipt, work and evidence integrity on the caller's snapshot."""
import json
import re
from . import schema, reporting
from .records import Request, canonical, uuid_text, integer
from .timekeeping import load_zone, parse_date, local_date, resolve_start

def verify_receipts(c):
    """Validate detached receipt content and persisted work associations.

    Export and confirmation whole-content validation remains in _verify;
    this adds no second renderer, replay authority or mutation path.
    """
    from .timekeeping import local_date, parse_duration, resolve_minute, resolve_start
    meta = c.execute('SELECT dataset_id,timezone FROM dataset_meta').fetchone()
    dataset, zone = (meta[0], load_zone(meta[1]))
    receipts = {}
    for row in c.execute('SELECT * FROM committed_requests ORDER BY commit_seq'):
        content = json.loads(row['request_bytes'])
        if type(content) is not dict or set(content) != {'format', 'dataset_id', 'operation', 'action_utc_us', 'arguments'} or type(content['format']) is not int or (content['format'] != 1) or (content['dataset_id'] != dataset) or (content['operation'] != row['operation']) or (content['action_utc_us'] != row['action_utc_us']) or (type(content['arguments']) is not dict):
            raise ValueError('Invalid committed request receipt content')
        request = Request.make(row['request_id'], dataset, row['operation'], row['action_utc_us'], **content['arguments'])
        result = json.loads(row['result_bytes'])
        if request.content() != row['request_bytes'] or type(result) is not dict or canonical(result) != row['result_bytes']:
            raise ValueError('Noncanonical committed request receipt')
        receipts[request.request_id] = (request, result)
        a, op = (request.args(), request.operation)
        expected_class = 'administrative' if op in schema.ADMINISTRATIVE_OPERATIONS else 'protected'
        if row['receipt_class'] != expected_class:
            raise ValueError('Incorrect committed receipt classification')
        for key in ('expected_version', 'expected_task_version', 'expected_active_version', 'expected_revision'):
            if key in a and (type(a[key]) is not int or not 1 <= a[key] <= 2 ** 63 - 1):
                raise ValueError('Invalid reviewed version in receipt')
        if op in schema.ADMINISTRATIVE_OPERATIONS:
            pass
        elif op == 'set_week_start':
            if type(a.get('week_start')) is not int or not 0 <= a['week_start'] <= 6 or type(a.get('expected_week_start')) is not int or (not 0 <= a['expected_week_start'] <= 6) or (canonical(result) != canonical({'week_start': a['week_start']})):
                raise ValueError('Week setting receipt differs')
        elif op == 'dismiss_polr_reminder_today':
            if a != {'local_date': local_date(request.action_utc_us, zone).isoformat()} or result != a:
                raise ValueError('Reminder receipt differs')
        elif op in ('register_timesheet_export', 'confirm_polr_absolute'):
            pass
        elif op in ('start_timer', 'switch_timer', 'add_timed_work', 'add_date_only_work'):
            key = a.get('next_entry_id' if op == 'switch_timer' else 'entry_id')
            if c.execute('SELECT 1 FROM work_entries WHERE entry_id=? AND created_request_id=?', (key, request.request_id)).fetchone() is None:
                raise ValueError('Creation receipt has no owning work identity')
        elif op in ('stop_timer', 'edit_closed_timed_work', 'edit_date_only_work', 'delete_work_entry'):
            if c.execute('SELECT 1 FROM work_revisions WHERE request_id=?', (request.request_id,)).fetchone() is None:
                raise ValueError('Work receipt has no immutable revision')
        elif op == 'correct_active_start':
            if c.execute('SELECT 1 FROM active_start_corrections WHERE request_id=?', (request.request_id,)).fetchone() is None:
                raise ValueError('Correction receipt has no audit evidence')
        else:
            raise ValueError('Unsupported committed receipt operation')
    verify_administration(c)
    for entry in c.execute('SELECT * FROM work_entries'):
        request, result = receipts[entry['created_request_id']]
        a = request.args()
        switched = request.operation == 'switch_timer'
        if request.operation not in ('start_timer', 'switch_timer', 'add_timed_work', 'add_date_only_work') or a.get('next_entry_id' if switched else 'entry_id') != entry['entry_id'] or a.get('next_task_id' if switched else 'task_id') != entry['task_id'] or (result.get('entry_id') != entry['entry_id']):
            raise ValueError('Work identity/creation receipt relationship differs')
        if request.operation in ('start_timer', 'switch_timer'):
            if entry['kind'] != 'timed' or entry['original_start_utc_us'] != request.action_utc_us or canonical(result) != canonical({'entry_id': entry['entry_id'], 'version': 1, **({'closed_entry_id': a['expected_active_entry_id']} if switched else {})}):
                raise ValueError('Timer creation differs from accepted action')
    for row in c.execute('SELECT * FROM work_revisions'):
        request, result = receipts[row['request_id']]
        op, a = (request.operation, request.args())
        expected_entry = a.get('expected_active_entry_id' if op == 'switch_timer' else 'entry_id')
        if op not in ('stop_timer', 'switch_timer', 'add_timed_work', 'add_date_only_work', 'edit_closed_timed_work', 'edit_date_only_work', 'delete_work_entry') or expected_entry != row['entry_id'] or request.action_utc_us != row['audit_utc_us']:
            raise ValueError('Work revision/receipt relationship differs')
        if op == 'switch_timer':
            if result.get('closed_entry_id') != row['entry_id'] or row['revision'] != 1:
                raise ValueError('Switch revision receipt differs')
        elif canonical(result) != canonical({'entry_id': row['entry_id'], 'revision': row['revision']}):
            raise ValueError('Work revision result differs')
        if op.startswith('edit_') or op == 'delete_work_entry':
            if a.get('expected_revision') != row['revision'] - 1:
                raise ValueError('Revision receipt prior differs')
        elif row['revision'] != 1:
            raise ValueError('Initial revision receipt differs')
        if bool(row['is_deleted']) != (op == 'delete_work_entry'):
            raise ValueError('Deleted revision receipt kind differs')
        if op not in ('stop_timer', 'switch_timer'):
            owner = c.execute('SELECT task_id FROM work_entries WHERE entry_id=?', (row['entry_id'],)).fetchone()[0]
            if a['task_id'] != owner or a.get('comment', '').strip() != row['comment']:
                raise ValueError('Revision request ownership/comment differs')
        if op in ('stop_timer', 'switch_timer'):
            if row['stop_utc_us'] != request.action_utc_us or row['kind'] != 'timed':
                raise ValueError('Stopped revision differs from accepted action')
        elif op != 'delete_work_entry':
            if row['kind'] == 'date_only':
                if (row['work_date'], row['duration_us']) != (parse_date(a['work_date']).isoformat(), parse_duration(a['duration_text'])):
                    raise ValueError('Dated revision differs from frozen input')
            else:
                prior = c.execute('SELECT * FROM work_revisions WHERE entry_id=? AND revision=?', (row['entry_id'], row['revision'] - 1)).fetchone()
                start = resolve_minute(a['start_date'], a['start_time'], a['start_occurrence'], zone, original=prior['start_utc_us'] if prior else None)
                stop = resolve_minute(a['end_date'], a['end_time'], a['end_occurrence'], zone, original=prior['stop_utc_us'] if prior else None)
                if (start, stop) != (row['start_utc_us'], row['stop_utc_us']) or stop > request.action_utc_us:
                    raise ValueError('Timed revision differs from frozen input')
    for row in c.execute('SELECT * FROM active_start_corrections'):
        request, result = receipts[row['request_id']]
        a = request.args()
        if request.operation != 'correct_active_start' or a.get('entry_id') != row['entry_id'] or a.get('expected_version') != row['version'] - 1 or (request.action_utc_us != row['audit_utc_us']) or (result != {'entry_id': row['entry_id'], 'version': row['version']}):
            raise ValueError('Active-start correction receipt differs')
        if resolve_start(row['prior_start_utc_us'], a['date_text'], a['time_text'], a['occurrence'], zone) != row['corrected_start_utc_us'] or row['comment'] != a['comment'].strip():
            raise ValueError('Active-start evidence differs from frozen input')

def assert_lifecycle(c):
    schema.verify_structure(c)
    bad = c.execute("SELECT e.entry_id FROM work_entries e LEFT JOIN active_timer a USING(entry_id)\n      WHERE (a.entry_id IS NOT NULL AND e.kind!='timed')\n         OR (e.current_revision IS NULL AND a.entry_id IS NULL)\n         OR (e.current_revision IS NOT NULL AND a.entry_id IS NOT NULL) LIMIT 1").fetchone()
    if bad:
        raise ValueError(f'Invalid active/closed lifecycle: {bad[0]}')
    for table, key in (('tasks', 'task_id'), ('projects', 'project_id'), ('work_entries', 'entry_id')):
        for row in c.execute(f'SELECT {key} FROM {table}'):
            uuid_text(row[0])
    for entry in c.execute('SELECT * FROM work_entries'):
        revisions = list(c.execute('SELECT * FROM work_revisions WHERE entry_id=? ORDER BY revision', (entry['entry_id'],)))
        expected = entry['current_revision'] or 0
        if len(revisions) != expected or any((r['revision'] != i for i, r in enumerate(revisions, 1))):
            raise ValueError('Invalid current revision chain')
        previous = None
        for revision in revisions:
            if revision['kind'] != entry['kind'] or (previous is not None and previous['is_deleted']):
                raise ValueError('Invalid revision kind/deleted successor')
            if revision['kind'] == 'date_only':
                if parse_date(revision['work_date']).isoformat() != revision['work_date']:
                    raise ValueError('Invalid revision civil date')
            if revision['is_deleted']:
                if previous is None or any((revision[key] != previous[key] for key in ('start_utc_us', 'stop_utc_us', 'work_date', 'duration_us'))):
                    raise ValueError('Deletion must retain prior work values')
            previous = revision
        corrections = list(c.execute('SELECT * FROM active_start_corrections WHERE entry_id=? ORDER BY version', (entry['entry_id'],)))
        prior, version = (entry['original_start_utc_us'], 1)
        for correction in corrections:
            version += 1
            if entry['kind'] != 'timed' or correction['version'] != version or correction['prior_start_utc_us'] != prior:
                raise ValueError('Invalid active-start audit chain')
            prior = correction['corrected_start_utc_us']
        active = c.execute('SELECT * FROM active_timer WHERE entry_id=?', (entry['entry_id'],)).fetchone()
        if active and (active['version'] != version or active['start_utc_us'] != prior):
            raise ValueError('Active start does not match immutable evidence')
        if revisions and entry['kind'] == 'timed' and (revisions[0]['start_utc_us'] != prior):
            raise ValueError('Initial closed revision does not match original/active-start evidence')
from .hierarchy import task_observations

class WorkChronology:
    """Independent historical eligibility and active state, not mutation replay.

    Shared evidence checks prove immutable row/request contents; this traversal
    proves those effects were possible in their retained chronological context.
    """

    def __init__(self, facts):
        self.facts = facts
        self.zone = load_zone(facts['dataset_meta'][0]['timezone'])
        self.active = None
        self.entries = {}
        self.week_start = 6
        self.dismissed = None
        self.revisions = {r['request_id']: r for r in facts['work_revisions']}
        self.corrections = {r['request_id']: r for r in facts['active_start_corrections']}

    def step(self, request, result, tasks, projects):
        from .recording_services import FIELDS
        from .hierarchy import task_observations
        op, a, now = (request.operation, request.args(), request.action_utc_us)
        if op not in FIELDS or set(a) != FIELDS[op]:
            raise ValueError('Unknown or malformed protected request')
        local_date(now, self.zone)

        def eligible(identity, version=None):
            uuid_text(identity)
            if identity not in tasks:
                raise ValueError('Historical recording task missing')
            if version is not None:
                integer(version, 'Reviewed task version', 1, 2 ** 63 - 1)
                if tasks[identity]['version'] != version:
                    raise ValueError('Historical recording task version differs')
            if not task_observations(list(tasks.values()), list(projects.values()))[identity]['eligible_for_new_work']:
                raise ValueError('Historical new work requires an effectively active leaf')

        def active(identity, version):
            integer(version, 'Reviewed active version', 1, 2 ** 63 - 1)
            if self.active is None or self.active['entry_id'] != identity or self.active['version'] != version:
                raise ValueError('Historical active state differs')
            return self.active
        if op in ('start_timer', 'switch_timer', 'add_timed_work', 'add_date_only_work'):
            identity = a['next_entry_id'] if op == 'switch_timer' else a['entry_id']
            task = a['next_task_id'] if op == 'switch_timer' else a['task_id']
            uuid_text(identity)
            if identity in self.entries:
                raise ValueError('Duplicate work creation identity')
            eligible(task, a['expected_task_version'] if op in ('start_timer', 'switch_timer') else None)
            if op == 'start_timer' and self.active is not None:
                raise ValueError('Historical simultaneous timers')
            if op == 'switch_timer':
                old = active(a['expected_active_entry_id'], a['expected_active_version'])
                if task == old['task_id'] or now <= old['start_utc_us']:
                    raise ValueError('Invalid historical Switch')
                self.entries[old['entry_id']]['revision'] = 1
                revision = self.revisions.get(request.request_id)
                if revision is None or revision['start_utc_us'] != old['start_utc_us']:
                    raise ValueError('Switch start differs')
            self.entries[identity] = dict(task_id=task, revision=0 if op in ('start_timer', 'switch_timer') else 1, deleted=False)
            if op in ('start_timer', 'switch_timer'):
                self.active = dict(singleton=1, entry_id=identity, task_id=task, start_utc_us=now, version=1)
        elif op == 'stop_timer':
            old = active(a['entry_id'], a['expected_version'])
            if now <= old['start_utc_us']:
                raise ValueError('Historical Stop does not advance')
            revision = self.revisions.get(request.request_id)
            if revision is None or revision['start_utc_us'] != old['start_utc_us']:
                raise ValueError('Stopped start differs')
            self.entries[old['entry_id']]['revision'] = 1
            self.active = None
        elif op == 'correct_active_start':
            old = active(a['entry_id'], a['expected_version'])
            corrected = resolve_start(old['start_utc_us'], a['date_text'], a['time_text'], a['occurrence'], self.zone)
            if corrected == old['start_utc_us'] or corrected > now:
                raise ValueError('No-op or future historical correction')
            if request.request_id not in self.corrections:
                raise ValueError('Missing chronological correction')
            old.update(start_utc_us=corrected, version=old['version'] + 1)
        elif op in ('edit_closed_timed_work', 'edit_date_only_work', 'delete_work_entry'):
            identity = a['entry_id']
            entry = self.entries.get(identity)
            integer(a['expected_revision'], 'Reviewed revision', 1, 2 ** 63 - 1)
            if entry is None or entry['task_id'] != a['task_id'] or entry['revision'] != a['expected_revision'] or entry['deleted']:
                raise ValueError('Historical reviewed work state differs')
            if self.active is not None and self.active['entry_id'] == identity:
                raise ValueError('Cannot edit active work as closed')
            row = self.revisions.get(request.request_id)
            if row is None:
                raise ValueError('Missing historical revision')
            if op != 'delete_work_entry':
                prior = next((r for r in self.facts['work_revisions'] if r['entry_id'] == identity and r['revision'] == a['expected_revision']), None)
                if prior is None or all((row[k] == prior[k] for k in ('start_utc_us', 'stop_utc_us', 'work_date', 'duration_us'))):
                    raise ValueError('Missing prior or no-op work revision')
            entry.update(revision=entry['revision'] + 1, deleted=op == 'delete_work_entry')
        elif op == 'set_week_start':
            integer(a['week_start'], 'Week start', 0, 6)
            integer(a['expected_week_start'], 'Prior week start', 0, 6)
            if a['expected_week_start'] != self.week_start or a['week_start'] == self.week_start:
                raise ValueError('Stale or no-op week configuration')
            self.week_start = a['week_start']
        elif op == 'dismiss_polr_reminder_today':
            day = local_date(now, self.zone).isoformat()
            if a != {'local_date': day} or self.dismissed == day:
                raise ValueError('Incorrect or no-op dismissal')
            self.dismissed = day
        elif op == 'register_timesheet_export':
            from .timesheet import from_content
            value = from_content(a['candidate'], check_render=False)
            ids = {t.task_id for t in value.tasks}
            if value.scope_kind == 'all' and ids != set(tasks):
                raise ValueError('Frozen All scope omits historical task identities')
            for task in value.tasks:
                uuid_text(task.project_id)
                if task.task_id not in tasks or task.project_id != tasks[task.task_id]['project_id']:
                    raise ValueError('Frozen task/project differs at registration')
            if any((t.task_id not in tasks or t.project_id not in projects for t in value.tasks)):
                raise ValueError('Frozen identities were not present at registration')
        elif op == 'confirm_polr_absolute':
            for field in ('reviewed_rows', 'selected_keys', 'manual_cells', 'acknowledgements'):
                if any((r['task_id'] not in tasks for r in a[field])):
                    raise ValueError('Confirmation task was not present')

    def finish(self):
        expected = [] if self.active is None else [self.active]
        if expected != self.facts['active_timer']:
            raise ValueError('Final active timer differs from chronological recording')
        actual = {r['entry_id']: r for r in self.facts['work_entries']}
        if set(actual) != set(self.entries):
            raise ValueError('Work creation chronology coverage differs')
        for key, value in self.entries.items():
            if actual[key]['task_id'] != value['task_id'] or actual[key]['current_revision'] != (value['revision'] or None):
                raise ValueError('Final work revision/owner differs')
        meta = self.facts['dataset_meta'][0]
        if (meta['week_start'], meta['polr_reminder_dismissed_local_date']) != (self.week_start, self.dismissed):
            raise ValueError('Configuration/reminder history differs')

def verify_administration(c):
    from .administration import verify_administration as replay
    facts = {name: schema._rows(c, name) for name, in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    replay(facts['projects'], facts['tasks'], facts['committed_requests'], facts['dataset_meta'][0]['dataset_id'], facts=facts)

def verify_transaction(c):
    if not c.in_transaction:
        raise ValueError('Semantic verification requires an active transaction')
    schema.verify_structure(c)
    expected = {re.match('CREATE TABLE (\\w+)', statement)[1] for statement in schema.schema_statements() if statement.startswith('CREATE TABLE ')} | {'sqlite_sequence'}
    if {name for name, in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")} != expected:
        raise ValueError('Unexpected table coverage')
    reporting.dismissed_date(c)
    assert_lifecycle(c)
    for row in c.execute('SELECT export_id FROM timesheet_exports'):
        reporting.read_export(c, row[0])
    reporting.assert_confirmations(c)
    verify_receipts(c)
    sequences = schema._rows(c, 'sqlite_sequence')
    if len(sequences) > 1 or (sequences and sequences[0]['name'] != 'committed_requests'):
        raise ValueError('Invalid receipt sequence coverage')
    maximum = c.execute('SELECT COALESCE(max(commit_seq),0) FROM committed_requests').fetchone()[0]
    if maximum and (not sequences) or (sequences and integer(sequences[0]['seq'], 'Receipt sequence', 0, 2 ** 63 - 1) < maximum):
        raise ValueError('Receipt sequence high water differs')
    return dict(schema_version=5, semantic_verified=True)
