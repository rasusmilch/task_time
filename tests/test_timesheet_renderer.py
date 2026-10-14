"""The staged timesheet renders the authoritative detached mixed report."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from task_timer.app import TaskTimerService
from task_timer.exporter import build_timesheet_text
from task_timer.storage import EventStorage

SUN = date(2026, 10, 11)
MON = date(2026, 10, 12)
TUE = date(2026, 10, 13)
SAT = date(2026, 10, 17)
NEXT = date(2026, 10, 18)
CUTOFF = datetime(2026, 10, 25, 12, 0, 0, 123456, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr('task_timer.app.utc_now', lambda: CUTOFF)
    monkeypatch.setattr('task_timer.app.detect_local_timezone', lambda: ZoneInfo('America/Chicago'))
    s = TaskTimerService(EventStorage(tmp_path / 'fresh'))
    p = s.create_project('Project P')
    q = s.create_project('Project Q')
    a = s.create_task('Task A', '', project_id=p)
    b = s.create_task('Task B', '', project_id=p)
    return s, a, b, p, q


def dated(s, owner, day, seconds):
    s._append(owner, 'dated_duration_added', {'entry_id': str(uuid4()), 'work_date_local': day.isoformat(),
              'duration_seconds': seconds, 'reason': 'Work'})


def calculate(s, start=SUN, end=SAT, **selection):
    return s.calculate_date_window(start, end, cutoff_utc=CUTOFF, **selection)


def render(s, report, scope='selected'):
    return build_timesheet_text(report, local_timezone=s.local_tz_name, scope=scope)


def table_rows(text, name):
    return [[cell.strip() for cell in line.split(' | ')] for line in text.splitlines()
            if ' | ' in line and line.split(' | ')[0].strip() == name]


def example(s, a, b):
    dated(s, a, MON, 3600)
    dated(s, b, MON, 7200)
    dated(s, a, TUE, 5400)
    dated(s, b, TUE, 1800)


def test_two_independent_tasks_and_nonadditive_project_subtotal(setup):
    s, a, b, p, _ = setup
    example(s, a, b)
    report = calculate(s, all_tasks=True)
    text = render(s, report, 'complete')
    assert table_rows(text, 'Task A')[0][3:] == ['00:00:00', '01:00:00', '01:30:00', '00:00:00', '00:00:00', '00:00:00', '00:00:00', '02:30:00']
    assert table_rows(text, 'Task B')[0][3:] == ['00:00:00', '02:00:00', '00:30:00', '00:00:00', '00:00:00', '00:00:00', '00:00:00', '02:30:00']
    subtotal = table_rows(text, 'Project total — informational')[0]
    assert subtotal[4:6] == ['03:00:00', '02:00:00']
    assert subtotal[-1] == table_rows(text, 'Application total')[0][-1] == '05:00:00'
    assert text.count('Task A ') == text.count('Task B ') == 1
    assert 'Project subtotals are informational; they are not additional task entries.' in text
    assert report['projects'][p]['window_seconds'] == 18000
    assert '2026-10-25T12:00:00.123456Z' in text
    assert 'Local timezone: America/Chicago' in text
    assert 'Scope: Complete eligible-task scope' in text
    assert 'Deleted historical tasks included: No' in text
    assert 'Epicor' not in text and 'submitted' not in text.lower()


def test_multiple_projects_and_unassigned_group(setup):
    s, a, b, p, q = setup
    s.assign_task_to_project(b, q)
    u = s.create_task('Unassigned task', '')
    for task, seconds in [(a, 3600), (b, 7200), (u, 1800)]:
        dated(s, task, MON, seconds)
    text = render(s, calculate(s, all_tasks=True), 'complete')
    assert text.index('Project: Project P') < text.index('Task A ') < text.index('Project: Project Q') < text.index('Task B ') < text.index('\nUnassigned\n') < text.index('Unassigned task ')
    assert table_rows(text, 'Unassigned subtotal — informational')[0][-1] == '00:30:00'
    assert table_rows(text, 'Application total')[0][-1] == '03:30:00'
    assert len(table_rows(text, 'Task A')) == len(table_rows(text, 'Task B')) == len(table_rows(text, 'Unassigned task')) == 1


@pytest.mark.parametrize('selection', ['task', 'project', 'combined', 'projects', 'tasks', 'unassigned'])
def test_selected_scopes_match_accounting_and_project_completeness(setup, selection):
    s, a, b, p, q = setup
    example(s, a, b)
    u = s.create_task('Unassigned task', '')
    dated(s, u, MON, 1800)
    options = {'task': {'task_ids': (a,)}, 'project': {'project_ids': (p,)},
               'combined': {'project_ids': (p,), 'task_ids': (a,)},
               'projects': {'project_ids': (p, q)}, 'tasks': {'task_ids': (a, b)},
               'unassigned': {'include_unassigned': True}}[selection]
    report = calculate(s, **options)
    text = render(s, report)
    expected = {'task': '02:30:00', 'unassigned': '00:30:00'}.get(selection, '05:00:00')
    assert table_rows(text, 'Selected-scope total')[0][-1] == expected
    assert 'Scope: Selected scope' in text and not table_rows(text, 'Application total')
    if selection == 'task':
        assert 'Task B' not in text
        assert table_rows(text, 'Selected tasks subtotal — informational')[0][-1] == expected
        assert not table_rows(text, 'Project total — informational')
    elif selection != 'unassigned':
        assert table_rows(text, 'Project total — informational')[0][-1] == expected
    assert len(table_rows(text, 'Task A')) == int(a in report['tasks'])


def test_duplicate_names_retain_local_identity_and_exact_unicode_names(setup):
    s, a, b, p, q = setup
    name = 'Management task Ω — a very long descriptive name with  double spaces and no truncation'
    s.update_task(a, name, '')
    s.update_task(b, name, '')
    c = s.create_task(name, '', project_id=q)
    for task, amount in [(a, 3600), (b, 7200), (c, 1800)]:
        dated(s, task, MON, amount)
    text = render(s, calculate(s, all_tasks=True), 'complete')
    rows = table_rows(text, name)
    assert len(rows) == 3
    assert {row[2] for row in rows} == {a, b, c}
    assert {row[-1] for row in rows} == {'01:00:00', '02:00:00', '00:30:00'}
    assert text.count(name) == 3
    assert 'they are not external task numbers' in text
    assert render(s, calculate(s, all_tasks=True), 'complete') == text


def test_duplicate_project_names_are_locally_disambiguated(setup):
    s, a, b, p, q = setup
    s.rename_project(q, 'Project P')
    s.assign_task_to_project(b, q)
    text = render(s, calculate(s, all_tasks=True), 'complete')
    assert f'Project: Project P [Chronicle local project reference: {p}]' in text
    assert f'Project: Project P [Chronicle local project reference: {q}]' in text


def test_empty_selected_scope_does_not_expand_to_all_tasks(setup):
    s, a, b, _, _ = setup
    example(s, a, b)
    text = render(s, calculate(s))
    assert 'No tasks included in this scope.' in text
    assert 'Task A' not in text and 'Task B' not in text and 'Project:' not in text
    assert table_rows(text, 'Selected-scope total')[0][3:] == ['00:00:00'] * 8


def test_empty_explicit_project_is_truthfully_rendered(setup):
    s, _, _, _, q = setup
    text = render(s, calculate(s, project_ids=(q,)))
    assert 'Project: Project Q' in text
    assert 'No eligible tasks included in this project.' in text
    assert table_rows(text, 'Project total — informational')[0][-1] == '00:00:00'
    assert 'Task A' not in text and 'Task B' not in text


def test_partial_week_distinguishes_out_of_scope_and_in_scope_zero(setup):
    s, a, _, p, _ = setup
    dated(s, a, MON, 3600)
    dated(s, a, SAT, 50400)
    text = render(s, calculate(s, MON, TUE, project_ids=(p,)))
    assert 'Requested local dates (inclusive): 2026-10-12 to 2026-10-13' in text
    assert 'Week (Sunday start): 2026-10-11 to 2026-10-17' in text
    for day in [SUN + timedelta(days=n) for n in range(7)]:
        assert day.isoformat() in text
    assert table_rows(text, 'Task A')[0][3:] == ['out of scope', '01:00:00', '00:00:00', 'out of scope', 'out of scope', 'out of scope', 'out of scope', '01:00:00']
    assert table_rows(text, 'Selected-scope total')[0][-1] == '01:00:00'
    assert '14:00:00' not in text


def test_multiweek_real_interval_and_long_dated_amount_use_correct_weeks(setup):
    s, a, b, p, _ = setup
    start = datetime(2026, 10, 17, 23, 30, tzinfo=s.local_tz)
    stop = datetime(2026, 10, 18, 1, 30, tzinfo=s.local_tz)
    s.add_manual_interval(a, start, stop, 'Cross week')
    dated(s, b, SAT, 50400)
    report = calculate(s, SAT, NEXT, project_ids=(p,))
    text = render(s, report)
    assert text.index('Week (Sunday start): 2026-10-11') < text.index('Week (Sunday start): 2026-10-18')
    rows = table_rows(text, 'Task A')
    assert rows[0][3:] == ['out of scope'] * 6 + ['00:30:00', '00:30:00']
    assert rows[1][3:] == ['01:30:00'] + ['out of scope'] * 6 + ['01:30:00']
    assert [row[-1] for row in table_rows(text, 'Task B')] == ['14:00:00', '00:00:00']
    assert [row[-1] for row in table_rows(text, 'Selected-scope total')] == ['14:30:00', '01:30:00']
    assert '02:00:00' not in text  # no repeated multiweek task charge


def test_deleted_historical_task_is_marked_inactive(setup):
    s, a, _, _, _ = setup
    dated(s, a, MON, 3600)
    s.delete_task_only(a)
    assert 'Task A' not in render(s, calculate(s, all_tasks=True), 'complete')
    text = render(s, calculate(s, all_tasks=True, include_deleted=True), 'complete')
    assert table_rows(text, 'Task A')[0][1] == 'Inactive (deleted)'
    assert table_rows(text, 'Task A')[0][-1] == '01:00:00'
    assert 'Deleted historical tasks included: Yes' in text


@pytest.mark.parametrize('seconds,expected', [(90061.125, '25:01:01.125'),
    (0.000000001, '00:00:00.000000001'), (0.1 + 0.2, '00:00:00.30000000000000004'),
    (59.999, '00:00:59.999'), (3600.5, '01:00:00.5')])
def test_duration_precision_preserves_seconds_in_all_rows(setup, seconds, expected):
    s, a, _, p, _ = setup
    dated(s, a, MON, seconds)
    text = render(s, calculate(s, task_ids=(a,)))
    for label in ['Task A', 'Selected tasks subtotal — informational', 'Selected-scope total']:
        row = table_rows(text, label)[0]
        assert row[4] == row[-1] == expected
    assert 'without rounding' in text


def test_rendering_is_pure_and_deterministic_despite_dictionary_order(setup):
    s, a, b, _, _ = setup
    example(s, a, b)
    running = s.create_task('Running', '')
    s.start_task(running)
    report = calculate(s, all_tasks=True)
    root = s.storage.data_dir
    before = deepcopy(report), deepcopy(s.state), deepcopy(s.events), {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    text = render(s, report, 'complete')
    assert (report, s.state, s.events, {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}) == before
    shuffled = deepcopy(report)
    shuffled['tasks'] = dict(reversed(list(shuffled['tasks'].items())))
    shuffled['projects'] = dict(reversed(list(shuffled['projects'].items())))
    for row in shuffled['projects'].values():
        row['task_ids'].reverse()
    assert render(s, shuffled, 'complete') == text
    assert s.state.running_task_id == running


def test_no_submission_status_inference(setup):
    s, a, _, _, _ = setup
    dated(s, a, MON, 12600)
    report = calculate(s, task_ids=(a,))
    before = render(s, report)
    s.create_time_submission_marker([a], None, CUTOFF, 'Submitted', None)
    assert render(s, calculate(s, task_ids=(a,))) == before
    assert 'submitted' not in before.lower() and 'Epicor' not in before


def test_authoritative_supplied_totals_are_not_recomputed(setup):
    s, a, _, p, _ = setup
    dated(s, a, MON, 3600)
    report = calculate(s, task_ids=(a,))
    # Sentinel totals deliberately inconsistent with day buckets prove that
    # presentation does not introduce a second summation engine.
    report['tasks'][a]['weekly_seconds'][SUN] = 7200
    report['projects'][p]['weekly_seconds'][SUN] = 10800
    report['application']['weekly_seconds'][SUN] = 14400
    text = render(s, report)
    assert table_rows(text, 'Task A')[0][-1] == '02:00:00'
    assert table_rows(text, 'Selected tasks subtotal — informational')[0][-1] == '03:00:00'
    assert table_rows(text, 'Selected-scope total')[0][-1] == '04:00:00'


@pytest.mark.parametrize('options', [{'scope': 'unknown', 'local_timezone': 'UTC'}, {'scope': 'selected', 'local_timezone': ''}])
def test_missing_or_invalid_caller_metadata_rejected(setup, options):
    with pytest.raises(ValueError):
        build_timesheet_text(calculate(setup[0]), **options)
