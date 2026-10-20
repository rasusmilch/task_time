"""Real one-transaction History context and pure precise presentation."""

from copy import deepcopy
import pytest

from chronicle.history_display import clock_text, details_text, duration_text, prepare_rows
from chronicle.sqlite_store import SQLiteStore
from chronicle.timekeeping import load_zone
from conftest import NOW, uid
from test_manual_work import H, M, dated, timed, facts, stamp


@pytest.mark.parametrize("weekday", range(7))
def test_snapshot_context_records_and_deleted_index_are_one_read(service, task, store, weekday, monkeypatch):
    timed(service, task, '2026-10-17', '23:00', '2026-10-19', '01:00')
    removed = dated(service, task, '2026-10-19', '14:00')
    service.delete_work_entry(task, removed, expected_revision=1, request_id=uid(), action_utc_us=NOW)
    service.set_week_start(weekday, expected_week_start=6, request_id=uid(), action_utc_us=NOW)
    before = facts(store)
    observed = []
    original = SQLiteStore.week_start.fget
    def read(s):
        observed.append(s.connection.in_transaction)
        return original(s)
    monkeypatch.setattr(SQLiteStore, 'week_start', property(read))
    snap = service.read_history_snapshot(task, cutoff_utc_us=NOW)
    assert observed == [True]
    assert snap['dataset_id'] == store.dataset_id and snap['task_id'] == task
    assert snap['cutoff_utc_us'] == NOW and snap['week_start'] == weekday
    assert snap['period'] == 'current_week'
    assert snap['rows'] == service.read_task_work_history(task, cutoff_utc_us=NOW)
    assert [r['entry_id'] for r in snap['deleted_entries']] == [removed]
    assert snap['deleted_entries'][0]['revision'] == 2 and snap['deleted_entries'][0]['is_deleted'] == 1
    assert removed not in [r['entry_id'] for r in snap['rows']]
    snap['rows'].clear(); snap['deleted_entries'][0]['revision'] = 99
    assert service.read_history_snapshot(task, cutoff_utc_us=NOW)['deleted_entries'][0]['revision'] == 2
    assert facts(store) == before


def test_snapshot_all_custom_empty_deleted_task_and_audit_order(service, task, store):
    empty = service.read_history_snapshot(task, cutoff_utc_us=NOW, period='all')
    assert empty['rows'] == [] and empty['start_date'] is empty['end_date'] is None
    e = dated(service, task)
    service.edit_date_only_work(task, e, '2026-10-20', '2:00', expected_revision=1,
                               request_id=uid(), action_utc_us=NOW-1)
    service.delete_work_entry(task, e, expected_revision=2, request_id=uid(), action_utc_us=NOW-2)
    store.connection.execute('UPDATE tasks SET is_deleted=1 WHERE task_id=?', (task,))
    snap = service.read_history_snapshot(task, cutoff_utc_us=NOW, period='custom', start_date='2026-10-19', end_date='2026-10-19')
    assert snap['rows'] == [] and len(snap['deleted_entries']) == 1
    text = details_text(service.read_work_entry_revisions(e))
    assert text.index('Creation — revision 1') < text.index('Correction — revision 2') < text.index('Deletion — revision 3')
    assert e in text and 'audit_utc_us' in text and 'request_id' in text


@pytest.mark.parametrize('value,text', [(0,'0:00'), (1,'<1 min'),(59_999_999,'<1 min'),(M,'0:01'),(125*H+45*M,'125:45')])
def test_precise_history_duration(value,text):
    assert duration_text(value) == text


def test_formatter_full_metadata_midnight_link_and_stable_date_groups(service, task, store):
    e = timed(service, task, '2026-10-17', '23:00', '2026-10-19', '01:00')
    d = dated(service, task, '2026-10-18', '14:00')
    active = uid()
    service.start_timer(task, active, expected_task_version=1, request_id=uid(), action_utc_us=NOW)
    rows = service.read_task_work_history(task, cutoff_utc_us=NOW, period='all')
    original = deepcopy(rows)
    newest = prepare_rows(rows, task, store.zone, True)
    oldest = prepare_rows(rows, task, store.zone, False)
    assert [r[0]['work_date'] for r in newest] == sorted([r['work_date'] for r in rows], reverse=True)
    for day in {r['work_date'] for r in rows}:
        assert [r for r in newest if r[0]['work_date']==day] == [r for r in oldest if r[0]['work_date']==day]
    parts = [values for row,values in newest if row['entry_id']==e]
    assert all(values[0]=='↔' for values in parts)
    assert parts[1][4]=='2026-10-19 00:00'
    assert next(values for row,values in newest if row['entry_id']==d)[2:]==('Date only','','','14:00')
    running = next(values for row,values in newest if row['entry_id']==active)
    assert running[2]=='Running' and running[4].startswith('as of ') and running[5]=='0:00'
    newest[0][0]['comment']='detached'
    assert rows==original


@pytest.mark.parametrize('zone,utc,day,text', [
    ('America/Chicago','2026-11-01T06:30:00+00:00','2026-11-01','01:30 (UTC-05:00)'),
    ('America/Chicago','2026-11-01T07:30:00+00:00','2026-11-01','01:30 (UTC-06:00)'),
    ('Australia/Lord_Howe','2026-04-04T14:45:00+00:00','2026-04-05','01:45 (UTC+11:00)'),
    ('Australia/Lord_Howe','2026-04-04T15:15:00+00:00','2026-04-05','01:45 (UTC+10:30)'),
    ('America/Chicago','2026-10-19T14:00:00+00:00','2026-10-19','09:00'),
    ('America/Chicago','2026-10-19T05:00:00+00:00','2026-10-18','2026-10-19 00:00')])
def test_actual_repeated_offsets_only_and_real_endpoint_dates(zone,utc,day,text):
    assert clock_text(stamp(utc), day, load_zone(zone))==text


def test_bad_display_row_preparation_never_changes_input(service, task, store):
    dated(service, task)
    rows = service.read_task_work_history(task, cutoff_utc_us=NOW)
    rows.append(dict(rows[0], task_id=uid()))
    before = deepcopy(rows)
    with pytest.raises(ValueError, match='another task'):
        prepare_rows(rows, task, store.zone, True)
    assert rows == before


def test_empty_snapshot_still_requires_representable_utc_calendar_boundaries(tmp_path):
    from chronicle.services import TimerService
    store=SQLiteStore(tmp_path/'positive-offset-boundary',create=True,timezone='Asia/Tokyo')
    try:
        service=TimerService(store); task=uid()
        service.create_task(task,'Empty',request_id=uid(),action_utc_us=NOW)
        before=facts(store)
        with pytest.raises(ValueError,match='unrepresentable'):
            service.read_history_snapshot(task,cutoff_utc_us=NOW,period='custom',start_date='0001-01-01',end_date='0001-01-01')
        assert facts(store)==before
    finally:store.close()
