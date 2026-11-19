"""Current frozen reports and absolute confirmation persistence; no connection owner."""
import json
from .records import Request, canonical, uuid_text

def dismissed_date(c):
    from .polr_allocation import civil
    value = c.execute('SELECT polr_reminder_dismissed_local_date FROM dataset_meta').fetchone()[0]
    if value is not None:
        civil(value)
    return value

def insert_export(c, candidate, request):
    """Validated children first, immutable master last, receipt owned by transact."""
    from .timesheet import validate
    value = validate(candidate)
    if any((t.is_deleted for t in value.tasks)):
        raise ValueError('Current schema has no live deleted-task state to freeze')
    for task in value.tasks:
        c.execute('INSERT INTO timesheet_export_tasks\n          (export_id,task_id,name,project_id,project_name,is_deleted,ordinal) VALUES(?,?,?,?,?,?,?)', (value.export_id, task.task_id, task.name, task.project_id, task.project_name, int(task.is_deleted), task.ordinal))
    for row in value.basis:
        c.execute('INSERT INTO timesheet_export_week_basis\n          (export_id,task_id,week_start_date,work_date,actual_us,suggested_quarters) VALUES(?,?,?,?,?,?)', (value.export_id, row.task_id, row.week_start_date, row.work_date, row.actual_us, row.suggested_quarters))
    for row in value.cells:
        c.execute('INSERT INTO timesheet_export_cells\n          (export_id,task_id,work_date,week_start_date,actual_us,actual_hundredths,suggested_quarters) VALUES(?,?,?,?,?,?,?)', (value.export_id, row.task_id, row.work_date, row.week_start_date, row.actual_us, row.actual_hundredths, row.suggested_quarters))
    c.execute('INSERT INTO timesheet_exports\n      (export_id,created_request_id,registered_utc_us,cutoff_utc_us,start_date,end_date,timezone,week_start,\n       scope_kind,selected_task_ids_json,preferred_destination,report_utf8,report_sha256)\n      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (value.export_id, request.request_id, request.action_utc_us, value.cutoff_utc_us, value.start_date, value.end_date, value.timezone, value.week_start, value.scope_kind, canonical(list(value.selected_task_ids)).decode(), value.preferred_destination, value.report_utf8, value.report_sha256))
    if read_export(c, value.export_id, check_request=False) != value:
        raise ValueError('Installed frozen export differs from reviewed candidate')
    return {'export_id': value.export_id, 'report_sha256': value.report_sha256}

def read_export(c, export_id, *, check_request=True):
    from .timesheet import from_content
    uuid_text(export_id)
    row = c.execute('SELECT * FROM timesheet_exports WHERE export_id=?', (export_id,)).fetchone()
    if row is None:
        raise ValueError('Registered export is unknown')
    meta = c.execute('SELECT dataset_id,timezone FROM dataset_meta').fetchone()
    data = {key: row[key] for key in ('export_id', 'start_date', 'end_date', 'cutoff_utc_us', 'timezone', 'week_start', 'scope_kind', 'preferred_destination', 'report_sha256')}
    data.update(dataset_id=meta['dataset_id'], selected_task_ids=json.loads(row['selected_task_ids_json']), report_text=row['report_utf8'].decode('utf-8'))
    if canonical(data['selected_task_ids']).decode() != row['selected_task_ids_json']:
        raise ValueError('Noncanonical registered scope')
    data['tasks'] = [dict(r) for r in c.execute('SELECT task_id,name,project_id,project_name,is_deleted,ordinal\n      FROM timesheet_export_tasks WHERE export_id=? ORDER BY ordinal', (export_id,))]
    for task in data['tasks']:
        if type(task['is_deleted']) is not int or task['is_deleted'] != 0:
            raise ValueError('Invalid frozen deleted flag')
        task['is_deleted'] = bool(task['is_deleted'])
    for table, fields, key in (('week_basis', 'b.task_id,b.week_start_date,b.work_date,b.actual_us,b.suggested_quarters', 'b.week_start_date,b.work_date'), ('cells', 'b.task_id,b.work_date,b.week_start_date,b.actual_us,b.actual_hundredths,b.suggested_quarters', 'b.work_date')):
        data['basis' if table == 'week_basis' else 'cells'] = [dict(r) for r in c.execute(f'SELECT {fields} FROM timesheet_export_{table} b LEFT JOIN timesheet_export_tasks t USING(export_id,task_id) WHERE b.export_id=? ORDER BY t.ordinal,{key}', (export_id,))]
    value = from_content(data, check_render=False)
    if row['timezone'] != meta['timezone']:
        raise ValueError('Registered export timezone/dataset association disagrees')
    if check_request:
        if list(c.execute('PRAGMA foreign_key_check')):
            raise ValueError('Frozen export relational integrity failed')
        receipt = c.execute('SELECT * FROM committed_requests WHERE request_id=?', (row['created_request_id'],)).fetchone()
        if receipt is None:
            raise ValueError('Export has no committed receipt')
        expected = Request.make(row['created_request_id'], meta['dataset_id'], 'register_timesheet_export', row['registered_utc_us'], candidate=data)
        if receipt['operation'] != expected.operation or receipt['request_bytes'] != expected.content() or receipt['action_utc_us'] != row['registered_utc_us'] or (json.loads(receipt['result_bytes']) != {'export_id': export_id, 'report_sha256': value.report_sha256}):
            raise ValueError('Frozen export and committed request disagree')
    return value

def confirmation_state(c):
    current, history = ({}, {})
    for row in c.execute('SELECT b.batch_id,v.task_id,v.work_date,v.confirmed_quarters,r.commit_seq\n      FROM polr_confirmation_batches b JOIN committed_requests r ON r.request_id=b.created_request_id\n      JOIN polr_confirmation_cells v USING(batch_id) ORDER BY r.commit_seq,v.task_id,v.work_date'):
        k = (row['task_id'], row['work_date'])
        history[row['batch_id'], *k] = (row['confirmed_quarters'], row['commit_seq'])
    for row in c.execute('SELECT p.task_id,p.work_date,p.batch_id,v.confirmed_quarters,r.commit_seq\n      FROM polr_confirmed_current p JOIN polr_confirmation_cells v USING(batch_id,task_id,work_date)\n      JOIN polr_confirmation_batches b USING(batch_id) JOIN committed_requests r ON r.request_id=b.created_request_id'):
        current[row['task_id'], row['work_date']] = (row['batch_id'], row['confirmed_quarters'], row['commit_seq'])
    return (current, history)

def assert_confirmations(c):
    """Prove receipts, complete batches, prior chains and latest pointers in commit order."""
    from .polr_confirmation import validate_batch
    meta = c.execute('SELECT dataset_id FROM dataset_meta').fetchone()
    tasks = {r[0] for r in c.execute('SELECT task_id FROM tasks')}
    current, history = ({}, {})
    batches = list(c.execute('SELECT b.*,r.commit_seq,r.operation,r.request_bytes,r.result_bytes,r.action_utc_us\n      FROM polr_confirmation_batches b LEFT JOIN committed_requests r ON r.request_id=b.created_request_id\n      ORDER BY r.commit_seq'))
    if len(batches) != c.execute("SELECT count(*) FROM committed_requests WHERE operation='confirm_polr_absolute'").fetchone()[0]:
        raise ValueError('Confirmation batch/receipt coverage differs')
    for b in batches:
        if b['operation'] != 'confirm_polr_absolute' or b['commit_seq'] is None:
            raise ValueError('Confirmation has no committed receipt')
        content = json.loads(b['request_bytes'])
        if type(content) is not dict or set(content) != {'format', 'dataset_id', 'operation', 'action_utc_us', 'arguments'} or type(content['format']) is not int or (content['format'] != 1):
            raise ValueError('Invalid confirmation receipt format')
        a = content['arguments']
        expected = Request.make(b['created_request_id'], meta['dataset_id'], 'confirm_polr_absolute', b['audit_utc_us'], **a)
        if expected.content() != b['request_bytes'] or b['action_utc_us'] != b['audit_utc_us']:
            raise ValueError('Confirmation receipt identity/content differs')
        if a['batch_id'] != b['batch_id'] or a['mode'] != b['mode'] or a['source_export_id'] != b['source_export_id']:
            raise ValueError('Confirmation master differs from its request')
        source = None
        source_seq = None
        if b['source_export_id'] is not None:
            source = read_export(c, b['source_export_id'])
            source_seq = c.execute('SELECT r.commit_seq FROM timesheet_exports e JOIN committed_requests r\n             ON r.request_id=e.created_request_id WHERE e.export_id=?', (source.export_id,)).fetchone()[0]
            if source_seq >= b['commit_seq']:
                raise ValueError('Confirmation source was not yet committed')
        cells = validate_batch(a, source=source, source_seq=source_seq, current=current, history=history, tasks=tasks)
        actual = [tuple(r) for r in c.execute('SELECT task_id,work_date,confirmed_quarters,expected_prior_batch_id,\n          expected_prior_quarters,stale_export_acknowledged FROM polr_confirmation_cells WHERE batch_id=? ORDER BY task_id,work_date', (b['batch_id'],))]
        expected_cells = [(r.task_id, r.work_date, r.confirmed_quarters, r.expected_prior_batch_id, r.expected_prior_quarters, int(r.stale_export_acknowledged)) for r in cells]
        result = {'batch_id': b['batch_id'], 'cell_count': len(cells)}
        if actual != expected_cells or b['result_bytes'] != canonical(result):
            raise ValueError('Confirmation cells/result differ from the whole committed request')
        for cell in cells:
            k = (cell.task_id, cell.work_date)
            current[k] = (b['batch_id'], cell.confirmed_quarters, b['commit_seq'])
            history[b['batch_id'], *k] = (cell.confirmed_quarters, b['commit_seq'])
    pointers = {(r['task_id'], r['work_date']): r['batch_id'] for r in c.execute('SELECT * FROM polr_confirmed_current')}
    if pointers != {k: v[0] for k, v in current.items()}:
        raise ValueError('Current confirmation does not identify the latest committed cell')
    if list(c.execute('PRAGMA foreign_key_check')):
        raise ValueError('Confirmation relational integrity failed')

def insert_confirmation(c, request, source, source_seq):
    from .polr_confirmation import validate_batch
    assert_confirmations(c)
    current, history = confirmation_state(c)
    a = request.args()
    cells = validate_batch(a, source=source, source_seq=source_seq, current=current, history=history, tasks={r[0] for r in c.execute('SELECT task_id FROM tasks')})
    c.execute('INSERT INTO polr_confirmation_batches(batch_id,created_request_id,audit_utc_us,source_export_id,mode)\n      VALUES(?,?,?,?,?)', (a['batch_id'], request.request_id, request.action_utc_us, a['source_export_id'], a['mode']))
    for cell in cells:
        c.execute('INSERT INTO polr_confirmation_cells(batch_id,task_id,work_date,confirmed_quarters,\n         expected_prior_batch_id,expected_prior_quarters,stale_export_acknowledged) VALUES(?,?,?,?,?,?,?)', (a['batch_id'], cell.task_id, cell.work_date, cell.confirmed_quarters, cell.expected_prior_batch_id, cell.expected_prior_quarters, int(cell.stale_export_acknowledged)))
        c.execute('INSERT INTO polr_confirmed_current(task_id,work_date,batch_id) VALUES(?,?,?)\n          ON CONFLICT(task_id,work_date) DO UPDATE SET batch_id=excluded.batch_id', (cell.task_id, cell.work_date, a['batch_id']))
    return {'batch_id': a['batch_id'], 'cell_count': len(cells)}
