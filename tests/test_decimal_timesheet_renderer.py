"""Pure replacement decimal cells; legacy/exact output remains protected."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, Inexact, localcontext
from hashlib import sha256

import pytest

from task_timer.exporter import (
    build_decimal_timesheet_text, build_timesheet_text, seconds_to_decimal_hundredths,
    _format_decimal_hundredths, _timesheet_escape, _render_table,
    build_export_text, build_selected_tasks_export_text,
)
from task_timer.time_utils import format_decimal_hours
from task_timer.app import TaskTimerService
from task_timer.storage import EventStorage
from test_timesheet_renderer import (
    setup, dated, calculate, example, logical_rows, table_rows, assert_table_geometry,
    SUN, MON, TUE, SAT, NEXT, CUTOFF,
)


@pytest.mark.parametrize('seconds,units,text', [
    (0, 0, '0.00'), (60, 2, '0.02'), (900, 25, '0.25'),
    (1800, 50, '0.50'), (2700, 75, '0.75'), (3600, 100, '1.00'),
    (5400, 150, '1.50'), (9000, 250, '2.50'), (11700, 325, '3.25'),
    (12000, 333, '3.33'), (10800, 300, '3.00'), (18000, 500, '5.00'),
    (50400, 1400, '14.00'), (17.999, 0, '0.00'), (18, 1, '0.01'),
    (53.999, 1, '0.01'), (54, 2, '0.02'), (0.000000001, 0, '0.00'),
    (36.125, 1, '0.01'),
])
def test_conversion_examples_and_half_up_boundaries(seconds, units, text):
    result = seconds_to_decimal_hundredths(seconds)
    assert type(result) is int and result == units
    assert _format_decimal_hundredths(result) == text


@pytest.mark.parametrize('invalid', [
    -1, -0.00001, float('nan'), float('inf'), -float('inf'), True, False,
    None, '60', b'60', [], {}, 1j, Decimal('60'),
])
def test_conversion_rejects_invalid_seconds(invalid):
    with pytest.raises(ValueError):
        seconds_to_decimal_hundredths(invalid)


@pytest.mark.parametrize('invalid', [-1, 1.0, True, None, '1'])
def test_formatter_requires_nonnegative_integer_hundredths(invalid):
    with pytest.raises(ValueError):
        _format_decimal_hundredths(invalid)


def test_decimal_context_and_large_integer_do_not_change_rounding():
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        assert seconds_to_decimal_hundredths(12000) == 333
        assert seconds_to_decimal_hundredths(36 * 10**80 + 18) == 10**80 + 1
        assert seconds_to_decimal_hundredths(5e-324) == 0
        assert seconds_to_decimal_hundredths(1e308) == (10**308 + 18) // 36
    assert _format_decimal_hundredths(10**80 + 1) == f'{10**78}.01'


def test_complete_weekly_report_has_independent_cells_and_metadata(setup):
    s, a, b, _, _ = setup
    example(s, a, b)
    report = calculate(s, all_tasks=True)
    text = build_decimal_timesheet_text(report)
    assert table_rows(text, 'Task A')[0][3:] == ['0.00', '1.00', '1.50'] + ['0.00'] * 4 + ['2.50']
    assert table_rows(text, 'Task B')[0][3:] == ['0.00', '2.00', '0.50'] + ['0.00'] * 4 + ['2.50']
    subtotal = table_rows(text, 'Project total — informational')[0]
    assert subtotal[4:6] == ['3.00', '2.00']
    assert subtotal[-1] == table_rows(text, 'Application total')[0][-1] == '5.00'
    assert report['application']['window_seconds'] == 18000
    assert 'Decimal hours, two places.' in text
    assert 'Week (Sunday start): 2026-10-11 to 2026-10-17' in text
    assert 'Local timezone: America/Chicago' in text
    assert '2026-10-25T12:00:00.123456Z' in text
    assert 'Scope: Complete eligible-task scope' in text
    assert 'Deleted historical tasks included: No' in text
    assert 'Project subtotals are informational' in text
    assert text.endswith('\n') and '\r' not in text
    text.encode('utf-8')
    for row, _ in logical_rows(text):
        if row[0] != 'Task':
            assert all(cell.replace('.', '').isdigit() and len(cell.split('.')[-1]) == 2
                       for cell in row[3:])
    assert_table_geometry(text)


@pytest.mark.parametrize('distributed', [False, True])
def test_three_minutes_round_per_cell_and_conserve_across_groups(setup, distributed):
    s, a, b, p, q = setup
    c = s.create_task('Task C', '', project_id=p)
    if distributed:
        s.assign_task_to_project(b, q)
        s.unassign_task_from_project(c)
    for task in (a, b, c):
        dated(s, task, MON, 60)
    report = calculate(s, all_tasks=True)
    text = build_decimal_timesheet_text(report)
    for name in ('Task A', 'Task B', 'Task C'):
        assert table_rows(text, name)[0][4] == table_rows(text, name)[0][-1] == '0.02'
    assert table_rows(text, 'Application total')[0][4] == '0.06'
    assert table_rows(text, 'Application total')[0][-1] == '0.06'
    subtotals = table_rows(text, 'Project total — informational')
    if distributed:
        assert [row[-1] for row in subtotals] == ['0.02', '0.02']
        assert table_rows(text, 'Unassigned subtotal — informational')[0][-1] == '0.02'
    else:
        assert [row[-1] for row in subtotals] == ['0.06', '0.00']
    assert report['application']['window_seconds'] == 180
    assert all(cell not in ('0.05', '0.12') for row, _ in logical_rows(text)
               if row[0] != 'Task' for cell in row[3:])


def test_combined_contributions_are_rounded_after_task_day_sum(setup):
    s, a, _, _, _ = setup
    start = datetime(2026, 10, 12, 9, tzinfo=s.local_tz)
    s.add_manual_interval(a, start, start + timedelta(seconds=18), 'Actual interval')
    dated(s, a, MON, 18)
    report = calculate(s, task_ids=(a,))
    assert report['tasks'][a]['daily_seconds'][MON] == 36
    text = build_decimal_timesheet_text(report)
    assert table_rows(text, 'Task A')[0][4] == '0.01'
    assert table_rows(text, 'Selected-scope total')[0][-1] == '0.01'


def test_task_weekly_total_sums_displayed_days_not_raw_week_seconds(setup):
    s, a, _, _, _ = setup
    dated(s, a, MON, 60)
    dated(s, a, TUE, 60)
    report = calculate(s, task_ids=(a,))
    assert report['tasks'][a]['weekly_seconds'][SUN] == 120
    text = build_decimal_timesheet_text(report)
    row = table_rows(text, 'Task A')[0]
    assert row[4:6] == ['0.02', '0.02'] and row[-1] == '0.04'
    assert table_rows(text, 'Selected tasks subtotal — informational')[0][-1] == '0.04'
    assert table_rows(text, 'Selected-scope total')[0][-1] == '0.04'


def test_raw_aggregate_fields_are_not_display_rounding_inputs(setup):
    s, a, b, _, _ = setup
    for task in (a, b):
        dated(s, task, MON, 60)
    report = calculate(s, all_tasks=True)
    for row in [*report['tasks'].values(), *report['projects'].values(), report['application'], report['unassigned']]:
        row['weekly_seconds'] = {SUN: 999999}
        row['window_seconds'] = 999999
        if 'task_id' not in row:
            row['daily_seconds'] = {MON: 999999}
    before = deepcopy(report)
    text = build_decimal_timesheet_text(report)
    assert table_rows(text, 'Task A')[0][-1] == '0.02'
    assert table_rows(text, 'Project total — informational')[0][-1] == '0.04'
    assert table_rows(text, 'Application total')[0][4] == '0.04'
    assert table_rows(text, 'Application total')[0][-1] == '0.04'
    assert report == before


@pytest.mark.parametrize('selection', ['task', 'project', 'combined', 'empty', 'empty-project', 'unassigned'])
def test_selection_scope_empty_projects_and_deduplication(setup, selection):
    s, a, b, p, q = setup
    example(s, a, b)
    u = s.create_task('Unassigned task', '')
    dated(s, u, MON, 900)
    options = {'task': {'task_ids': (a,)}, 'project': {'project_ids': (p,)},
               'combined': {'project_ids': (p,), 'task_ids': (a, a)}, 'empty': {},
               'empty-project': {'project_ids': (q,)}, 'unassigned': {'include_unassigned': True}}[selection]
    text = build_decimal_timesheet_text(calculate(s, **options))
    expected = {'task': '2.50', 'project': '5.00', 'combined': '5.00', 'unassigned': '0.25'}.get(selection, '0.00')
    assert table_rows(text, 'Selected-scope total')[0][-1] == expected
    assert 'Scope: Selected scope' in text
    assert len(table_rows(text, 'Task A')) == int(selection in ('task', 'project', 'combined'))
    assert len(table_rows(text, 'Task B')) == int(selection in ('project', 'combined'))
    if selection == 'task':
        assert table_rows(text, 'Selected tasks subtotal — informational')[0][-1] == '2.50'
    if selection in ('project', 'combined'):
        assert table_rows(text, 'Project total — informational')[0][-1] == '5.00'
    if selection == 'empty-project':
        assert 'Project: Project Q' in text
        assert 'No eligible tasks included in this project.' in text
    if selection == 'unassigned':
        assert table_rows(text, 'Unassigned subtotal — informational')[0][-1] == '0.25'


def test_duplicate_tasks_and_projects_keep_local_identities_and_deleted_status(setup):
    s, a, b, p, q = setup
    name = 'Same name ' + 'management assignment ' * 6 + 'end'
    s.update_task(a, name, '')
    s.update_task(b, name, '')
    s.rename_project(p, 'Project P\u202e')
    s.rename_project(q, 'Project P\u202e')
    s.assign_task_to_project(b, q)
    dated(s, a, MON, 3600)
    dated(s, b, MON, 5400)
    s.delete_task(b)
    text = build_decimal_timesheet_text(calculate(s, all_tasks=True, include_deleted=True))
    rows = table_rows(text, name)
    assert {row[2]: (row[1], row[-1]) for row in rows} == {
        a: ('Active', '1.00'), b: ('Inactive (deleted)', '1.50')}
    assert f'Chronicle local project reference: {p}' in text
    assert f'Chronicle local project reference: {q}' in text
    assert 'Deleted historical tasks included: Yes' in text
    assert table_rows(text, 'Application total')[0][-1] == '2.50'
    assert '\\u202e' in text and '\u202e' not in text
    assert_table_geometry(text)
    for row, physical in logical_rows(text):
        if row[0] == name:
            assert len(physical) > 1
            assert all(not cell.strip() for part in physical[1:] for cell in part[1:])


def test_empty_complete_scope_and_both_metadata_assertions(tmp_path, setup):
    empty = TaskTimerService(EventStorage(tmp_path / 'empty'))
    report = calculate(empty, all_tasks=True)
    text = build_decimal_timesheet_text(report, scope='complete', local_timezone=report['local_timezone'])
    assert 'Scope: Complete eligible-task scope' in text and 'No tasks included' in text
    assert table_rows(text, 'Application total')[0][3:] == ['0.00'] * 8
    s, a, _, _, _ = setup
    selected = calculate(s, task_ids=(a,))
    before = deepcopy(selected)
    with pytest.raises(ValueError, match='does not match'):
        build_decimal_timesheet_text(selected, scope='complete')
    assert selected == before


def test_partial_and_multiple_weeks_keep_dates_and_long_dated_work(setup):
    s, a, _, _, _ = setup
    start = datetime(2026, 10, 17, 23, 30, tzinfo=s.local_tz)
    s.add_manual_interval(a, start, start + timedelta(hours=2), 'Midnight crossing')
    dated(s, a, SAT, 50400)
    text = build_decimal_timesheet_text(calculate(s, SAT, NEXT, task_ids=(a,)))
    rows = table_rows(text, 'Task A')
    assert rows[0][3:] == ['out of scope'] * 6 + ['14.50', '14.50']
    assert rows[1][3:] == ['1.50'] + ['out of scope'] * 6 + ['1.50']
    assert [row[-1] for row in table_rows(text, 'Selected-scope total')] == ['14.50', '1.50']
    assert text.index('2026-10-11 to 2026-10-17') < text.index('2026-10-18 to 2026-10-24')
    assert_table_geometry(text)


@pytest.mark.parametrize('start,end,seconds', [
    (date(9999, 12, 30), date(9999, 12, 30), 12600),
    (date.min, date.min, 0),
])
def test_calendar_edge_slots_remain_safe(setup, start, end, seconds):
    s, a, _, _, _ = setup
    s.local_tz = timezone.utc
    if seconds:
        dated(s, a, start, seconds)
    text = build_decimal_timesheet_text(calculate(s, start, end, task_ids=(a,)))
    row = table_rows(text, 'Task A')[0]
    assert len(row) == 11
    assert row[-1] == ('3.50' if seconds else '0.00')
    assert 'unrepresentable' in row[3:10] and 'out of scope' in row[3:10]
    assert '10000-' not in text
    assert_table_geometry(text)


def test_long_unicode_escaped_label_geometry_and_nonduplicated_numbers(setup):
    s, a, _, _, _ = setup
    name = 'é e\u0301 漢字 👩\u200d💻\u200c | \\ \t \n \u202e ' + 'management assignment ' * 8 + 'Z' * 90
    report = calculate(s, task_ids=(a,))
    report['tasks'][a]['name'] = name  # isolated label fixture; original service unchanged
    report['tasks'][a]['daily_seconds'] = {MON: 60}
    text = build_decimal_timesheet_text(report)
    encoded = _timesheet_escape(name)
    matches = [(row, physical) for row, physical in logical_rows(text) if row[0] == encoded]
    assert len(matches) == 1
    row, physical = matches[0]
    assert len(physical) > 3 and row[4] == row[-1] == '0.02'
    assert all(not cell.strip() for part in physical[1:] for cell in part[1:])
    assert '\\u202e' in text and '\u202e' not in text
    assert_table_geometry(text)


def test_determinism_precision_and_read_only_running_service(setup):
    s, a, b, _, _ = setup
    example(s, a, b)
    dated(s, a, MON, 0.000000001)
    s.start_task(a)
    report = s.calculate_date_window(CUTOFF.date(), CUTOFF.date(),
                                     cutoff_utc=CUTOFF + timedelta(hours=1), all_tasks=True)
    before = deepcopy(report), deepcopy(s.state), deepcopy(s.events), _files(s)
    text = build_decimal_timesheet_text(report)
    assert table_rows(text, 'Task A')[0][-1] == '1.00'
    assert text == build_decimal_timesheet_text(report)
    reversed_report = deepcopy(report)
    for key in ('tasks', 'projects'):
        reversed_report[key] = dict(reversed(list(reversed_report[key].items())))
    for row in reversed_report['tasks'].values():
        row['daily_seconds'] = dict(reversed(list(row['daily_seconds'].items())))
    assert text == build_decimal_timesheet_text(reversed_report)
    for options in ({'scope': 'selected'}, {'local_timezone': 'UTC'}):
        with pytest.raises(ValueError, match='does not match'):
            build_decimal_timesheet_text(report, **options)
    assert (report, s.state, s.events, _files(s)) == before
    tiny = calculate(s, task_ids=(b,))
    tiny['tasks'][b]['daily_seconds'] = {MON: 0.000000001}
    before_tiny = deepcopy(tiny)
    assert table_rows(build_decimal_timesheet_text(tiny), 'Task B')[0][-1] == '0.00'
    assert tiny == before_tiny and tiny['tasks'][b]['daily_seconds'][MON] > 0


def _files(s):
    root = s.storage.data_dir
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*') if path.is_file()}


def test_positive_dated_record_displaying_zero_remains_positive_and_unchanged(setup):
    s, a, _, _, _ = setup
    dated(s, a, MON, 0.000000001)
    report = calculate(s, task_ids=(a,))
    before = deepcopy(report), deepcopy(s.state), deepcopy(s.events), _files(s)
    assert table_rows(build_decimal_timesheet_text(report), 'Task A')[0][4] == '0.00'
    assert report['tasks'][a]['daily_seconds'][MON] == 0.000000001
    record = next(iter(s.state.tasks[a].dated_durations.values()))
    assert record.duration_seconds == 0.000000001 and not record.deleted
    assert (report, s.state, s.events, _files(s)) == before


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), True, '60'])
def test_invalid_detached_task_day_amounts_fail_without_mutation(setup, value):
    s, a, _, _, _ = setup
    report = calculate(s, task_ids=(a,))
    report['tasks'][a]['daily_seconds'] = {MON: value}
    state, events, files = deepcopy(s.state), deepcopy(s.events), _files(s)
    with pytest.raises(ValueError):
        build_decimal_timesheet_text(report)
    assert (s.state, s.events, _files(s)) == (state, events, files)
    assert report['tasks'][a]['daily_seconds'][MON] is value


def test_exact_and_legacy_outputs_match_preimplementation_byte_baselines(setup):
    s, a, b, _, _ = setup
    example(s, a, b)
    report = calculate(s, all_tasks=True)
    assert sha256(build_timesheet_text(report).encode()).hexdigest() == '149f2a4de57b9f0a3ebb9097baea6226d3f399e49bb0783334f3b6633c10daf6'
    assert s.generate_date_range_timesheet(SUN, SAT, cutoff_utc=CUTOFF, all_tasks=True) == build_timesheet_text(report)
    common = dict(generated_at_utc=CUTOFF, local_timezone='America/Chicago', window_start_utc=None,
                  window_end_utc=CUTOFF, source_segments=['active_events.jsonl'], weekly_headers=['Week'],
                  weekly_summary_rows=[{'name': 'Task A', 'notes': 'n', 'weeks': [12000]}],
                  per_task_rows=[], history_lines=['Audit'])
    assert sha256(build_export_text(**common, reset_after=False, tag_daily={}, tag_weekly={}).encode()).hexdigest() == '0faf686c4497090e68914e93772b17fe2fa84d5867fee19d6aa78f5a8df66fea'
    assert sha256(build_selected_tasks_export_text(**common, mark_submitted=False, reason='').encode()).hexdigest() == '678b54573af74e7f76af3abaa62ddf401d86fac9f9f20601aaeb4ebb59130911'
    assert _render_table(['A', 'B'], [['long', 'x']]) == ['A    | B', '-----+--', 'long | x']
    assert format_decimal_hours(54) == '0.01'  # legacy differs from new HALF_UP 0.02
