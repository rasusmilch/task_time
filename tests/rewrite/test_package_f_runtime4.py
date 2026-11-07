"""F1 production worker/SQLite integration; no candidate authority or native claim."""
from datetime import datetime
from pathlib import Path
import hashlib
import json

import pytest

from chronicle import backup_restore as br, project_ui as ui
from chronicle.records import Request, canonical
from chronicle.timekeeping import to_us
from test_runtime4_worker import session
from test_backup_restore import logical
from runtime4_cases import uid, M

H = 60 * M
MONDAY = '2026-10-19'
TUESDAY = '2026-10-20'
OBS = to_us(datetime.fromisoformat('2026-10-25T18:00:00+00:00'))


def record(path, **values):
    path.write_text(json.dumps(values, indent=2, default=lambda v: dict(bytes_hex=v.hex())) + '\n')


def request(h, operation, **args):
    return Request.make(uid(), h.ready['dataset_id'], operation, h.now + 1_000_000, **args)


def dated(h, task, amount, day=MONDAY):
    key = uid()
    h.send('add_date_only_work', task_id=task, entry_id=key, work_date=day,
           duration_text=amount, comment='F1 disposable date-only work')
    return key


def manual(h, task, quarters, day=MONDAY):
    prior = h.exchange('polr_manual', dict(task_id=task, work_date=day, cutoff_utc_us=OBS))
    batch = uid()
    req, result = h.send('confirm_polr_absolute', batch_id=batch, mode='manual', source_export_id=None,
        source_metadata=None, reviewed_rows=[], selected_keys=[], acknowledgements=[],
        manual_cells=[dict(task_id=task, work_date=day, confirmed_quarters=quarters,
            prior_batch_id=prior['current_batch_id'], prior_quarters=prior['confirmed_quarters'])])
    receipt(h.facts(), req, result.result)
    return batch


def receipt(facts, req, result):
    rows = [r for r in facts['committed_requests'] if r[1] == req.request_id]
    assert len(rows) == 1
    assert rows[0][2] == req.operation and rows[0][4] == req.content()
    assert rows[0][5] == canonical(result) and rows[0][6] == req.action_utc_us


def preview(h, task, end=TUESDAY):
    return h.exchange('timesheet_preview', dict(export_id=uid(), cutoff_utc_us=OBS, period='custom',
        start_date=MONDAY, end_date=end, scope_kind='selected', task_ids=(task,)))


def registered(h, task):
    before = h.facts()
    value = preview(h, task)
    assert h.facts() == before
    req, result = h.send('register_timesheet_export', candidate=value.content())
    receipt(h.facts(), req, result.result)
    assert h.facts()['dataset_meta'] == before['dataset_meta']
    assert hashlib.sha256(value.report_utf8).hexdigest() == value.report_sha256
    assert h.exchange('timesheet_export', value.export_id) == value
    return value


def week(h):
    return h.exchange('polr_reconciliation', dict(cutoff_utc_us=OBS, period='custom',
        start_date=MONDAY, end_date='2026-10-25'))


def test_deep_projects_grouping_stale_review_and_active_archive(tmp_path):
    with session(tmp_path/'deep', True) as h:
        root = h.project(name='Root'); child = h.project(root, 'Child')
        grand = h.project(child, 'Grandchild'); fourth = h.project(grand, 'Fourth')
        fifth = h.project(fourth, 'Fifth'); destination = h.project(name='Destination')
        direct = h.task(grand); leaf = h.task(fifth)
        dated(h, direct, '0:10'); dated(h, leaf, '0:20')
        before = h.facts(); report = h.state()['report']
        assert report['application']['today_us'] == 30*M
        assert sum(v['today_us'] for v in report['individual'].values()) == 30*M
        assert report['project_direct'][grand]['today_us'] == 10*M
        assert report['project_direct'][fifth]['today_us'] == 20*M
        assert report['projects'][root]['today_us'] == 30*M
        assert report['projects'][destination]['today_us'] == 0
        move, outcome = h.send('move_project_subtree', **ui.ProjectMoveReview(h.state(), grand).arguments(destination))
        receipt(h.facts(), move, outcome.result)
        moved = h.state(); after = h.facts()
        assert {p['project_id']: p['parent_project_id'] for p in moved['projects']} == {
            root: None, child: root, grand: destination, fourth: grand, fifth: fourth, destination: None}
        for table in before.keys()-{'projects', 'committed_requests', 'sqlite_sequence'}:
            assert after[table] == before[table], table
        old_projects = {r[0]: r for r in before['projects']}
        assert all(r == old_projects[r[0]] for r in after['projects'] if r[0] != grand)
        for name in ('application', 'individual', 'cumulative', 'project_direct'):
            assert moved['report'][name] == report[name]
        assert moved['report']['projects'][root]['today_us'] == 0
        assert moved['report']['projects'][destination]['today_us'] == 30*M
        stale = request(h, 'move_project_subtree', **ui.ProjectMoveReview(moved, grand).arguments(child))
        h.send('rename_project', project_id=root, expected_version=1, name='Changed reviewed ancestor')
        stable = h.facts()
        assert h.exchange('mutate', stale).status == 'rejected'
        assert h.facts() == stable
        noop = request(h, 'move_project_subtree', **ui.ProjectMoveReview(h.state(), grand).arguments(destination))
        assert h.exchange('mutate', noop).status == 'unchanged' and h.facts() == stable
        active = uid(); start, _ = h.send('start_timer', task_id=leaf, entry_id=active, expected_task_version=1)
        live = h.state()['active']; stable = h.facts()
        h.lifecycle('project', destination, expect='rejected')
        assert h.state()['active'] == live and h.facts() == stable
        assert live['entry_id'] == active and live['start_utc_us'] == start.action_utc_us
        h.send('stop_timer', entry_id=active, expected_version=1)
        chain = [h.task(fifth)]
        chain.append(h.task(fifth, chain[-1])); chain.append(h.task(fifth, chain[-1]))
        stable = h.facts(); overflow = request(h, 'create_task', task_id=uid(), name='Fourth task level',
            parent_task_id=chain[-1], expected_parent_version=1, project_id=fifth,
            expected_project_version=1, reviewed_destination_project_ancestry=ui.ancestry(h.state(), fifth))
        assert h.exchange('mutate', overflow).status == 'rejected' and h.facts() == stable
        # Independent child flags survive ancestor Archive/Unarchive.
        h.lifecycle('task', chain[-1]); independent = next(t for t in h.state()['tasks'] if t['task_id'] == chain[-1])
        h.lifecycle('project', destination)
        assert all(t['effective_archived'] for t in h.state()['tasks'] if t['project_id'] in (grand, fourth, fifth))
        h.lifecycle('project', destination, 'unarchive')
        assert next(t for t in h.state()['tasks'] if t['task_id'] == chain[-1]) == independent
        record(tmp_path/'deep-evidence.json', move=move.content().decode(), before=before, moved=after,
               final=h.facts(), task_chain=chain, active=live)


def definition(h, key):
    return next(t for t in h.state()['templates'] if t['template_id'] == key)


def apply(h, source, destination):
    mapping = [dict(node_id=n['node_id'], task_id=uid()) for n in source['nodes']]
    state = h.state(); p = next(p for p in state['projects'] if p['project_id'] == destination)
    before = h.facts()
    req, result = h.send('apply_template', template_id=source['template_id'], expected_template_version=source['version'],
        reviewed_definition=source, destination_parent_task_id=None, destination_project_id=destination,
        expected_destination_parent_version=None, expected_destination_project_version=p['version'],
        reviewed_destination_project_ancestry=ui.ancestry(state, destination), node_mapping=mapping)
    keys = [r['task_id'] for r in mapping]; actual = {t['task_id']: t for t in h.state()['tasks']}
    by_node = {r['node_id']: r['task_id'] for r in mapping}
    assert [r['task_id'] for r in result.result['created_tasks']] == keys and len(set(keys)) == 3
    assert not set(keys) & {r[0] for r in before['tasks']}
    for n in source['nodes']:
        row = actual[by_node[n['node_id']]]
        assert row['parent_task_id'] == by_node.get(n['parent_node_id']) and row['project_id'] == destination
    after = h.facts()
    assert len(after['committed_requests']) == len(before['committed_requests']) + 1
    assert after['work_entries'] == before['work_entries'] and after['work_revisions'] == before['work_revisions']
    receipt(after, req, result.result)
    return keys, req


def delete_request(h, entity, key, review, text='DELETE'):
    return request(h, 'delete_'+entity, **{entity+'_id': key,
        'expected_version': review['selected']['version'], 'review': review, 'confirmed_text': text})


def review(h, entity, key):
    return h.exchange('delete_preview', dict(entity_type=entity, entity_id=key))


def test_template_apply_retirement_and_definition_delete_restore(tmp_path):
    directory = tmp_path/'templates'; image = tmp_path/'templates.sqlite3'; restored = tmp_path/'restored'
    with session(directory, True) as h:
        root_node, child_node, second_node = uid(), uid(), uid()
        graph = [dict(node_id=root_node, parent_node_id=None, name='Root one', position=0),
                 dict(node_id=child_node, parent_node_id=root_node, name='Child', position=1),
                 dict(node_id=second_node, parent_node_id=None, name='Root two', position=2)]
        template = uid(); h.send('create_template', template_id=template, name='Blueprint', nodes=graph)
        first_project = h.project(h.project()); second_project = h.project(h.project())
        first, first_apply = apply(h, definition(h, template), first_project)
        second, second_apply = apply(h, definition(h, template), second_project)
        dated(h, first[1], '0:15')
        for entity, key in (('project', first_project), ('task', first[0]), ('task', second[0])):
            frozen = review(h, entity, key); before = h.facts(); assert not frozen['eligible']
            assert h.exchange('mutate', delete_request(h, entity, key, frozen)).status == 'rejected'
            assert h.facts() == before
        stale = review(h, 'project', second_project)
        h.send('rename_project', project_id=second_project, expected_version=1, name='Renamed after review')
        before = h.facts()
        assert h.exchange('mutate', delete_request(h, 'project', second_project, stale)).status == 'rejected'
        assert h.facts() == before
        current = review(h, 'project', second_project); assert current['eligible']
        second_review = current
        for text in ('delete', ' DELETE', 'DELETE ', ''):
            assert h.exchange('mutate', delete_request(h, 'project', second_project, current, text)).status == 'rejected'
            assert h.facts() == before
        removed = delete_request(h, 'project', second_project, current)
        assert h.exchange('mutate', removed).status == 'committed'
        after = h.facts(); retired = {r['request_id'] for r in current['retire_receipts']}
        assert before['sqlite_sequence'] == after['sqlite_sequence']
        assert after['committed_requests'] == [r for r in before['committed_requests'] if r[1] not in retired]
        assert second_apply.request_id in retired and first_apply.request_id not in retired
        assert not any(r[1] == removed.request_id for r in after['committed_requests'])
        for table in before.keys()-{'projects', 'tasks', 'committed_requests'}:
            assert after[table] == before[table], table
        assert {r[0] for r in after['tasks']} == set(first)
        d = definition(h, template)
        h.send('edit_template', template_id=template, expected_version=d['version'], name='Edited blueprint', nodes=d['nodes'])
        d = definition(h, template); duplicate = uid()
        duplicate_request, _ = h.send('duplicate_template', template_id=duplicate, name='Independent copy',
            source_template_id=template, expected_source_version=d['version'], reviewed_source=d,
            node_mapping=sorted([dict(node_id=n['node_id'], new_node_id=uid()) for n in d['nodes']], key=lambda n:n['node_id']))
        h.send('archive_template', template_id=duplicate, expected_version=1)
        h.send('unarchive_template', template_id=duplicate, expected_version=2)
        before_definition_delete = h.facts(); current = review(h, 'template', template); assert current['eligible']
        removed_definition = delete_request(h, 'template', template, current)
        assert h.exchange('mutate', removed_definition).status == 'committed'
        final = h.facts()
        definition_retired = {r['request_id'] for r in current['retire_receipts']}
        assert final['committed_requests'] == [r for r in before_definition_delete['committed_requests'] if r[1] not in definition_retired]
        assert final['sqlite_sequence'] == before_definition_delete['sqlite_sequence']
        for table in before_definition_delete.keys()-{'template_definitions','template_nodes','committed_requests'}:
            assert final[table] == before_definition_delete[table]
        for kept in (first_apply, duplicate_request):
            assert next(r for r in final['committed_requests'] if r[1] == kept.request_id) == next(r for r in before_definition_delete['committed_requests'] if r[1] == kept.request_id)
        assert {t['template_id'] for t in h.state()['templates']} == {duplicate}
        assert not any(r[2].startswith('delete_') for r in final['committed_requests'])
        assert h.exchange('backup', dict(request_id=uid(), destination=str(image)))['result'].verified
        assert logical(image) == final and h.facts() == final
        identity = h.ready['dataset_id']
    raw = image.read_bytes(); source = (directory/'chronicle.sqlite3').read_bytes()
    assert br.validate_image(image).dataset_id == identity
    assert br.restore_image(image, restored).verified and logical(restored/'chronicle.sqlite3') == final
    with session(restored) as fresh:
        assert fresh.ready['dataset_id'] == identity and fresh.facts() == final
        assert fresh.exchange('reconcile', first_apply).status == 'committed' and fresh.facts() == final
        assert {t['template_id'] for t in fresh.state()['templates']} == {duplicate}
    assert image.read_bytes() == raw and (directory/'chronicle.sqlite3').read_bytes() == source
    record(tmp_path/'template-evidence.json', retired=sorted(retired), project_review=second_review, definition_retired=sorted(definition_retired), definition_review=current,
           before=before, after=after, restored=final, backup_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('start,stop,days', [
    ('2026-10-25T23:30:00-05:00', '2026-10-26T00:30:00-05:00', {'2026-10-25':30*M, '2026-10-26':30*M}),
    ('2026-03-08T01:30:00-06:00', '2026-03-08T03:30:00-05:00', {'2026-03-08':H}),
    ('2026-11-01T01:30:00-05:00', '2026-11-01T01:30:00-06:00', {'2026-11-01':H}),
    ('2026-10-19T09:00:00-05:00', '2026-10-19T22:00:00-05:00', {'2026-10-19':13*H}),
])
def test_temporal_restart_without_tick_writes_schema4(tmp_path, start, stop, days):
    begin, end = [to_us(datetime.fromisoformat(v)) for v in (start, stop)]
    directory = tmp_path/'temporal'
    with session(directory, True) as h:
        h.now = begin-10_000_000; key = h.task(); entry = uid(); h.now = begin-1_000_000
        accepted, _ = h.send('start_timer', task_id=key, entry_id=entry, expected_task_version=1)
        assert accepted.action_utc_us == begin
        baseline = h.facts()
    with session(directory) as h:
        impossible = h.exchange('read', begin-1)
        assert impossible['report'] is None and impossible['calculation_error']
        for observation in (begin, end, begin, end):
            state = h.exchange('read', observation)
            assert state['active']['entry_id'] == entry and state['active']['start_utc_us'] == begin
            assert h.facts() == baseline
        h.now = end-1_000_000; accepted, _ = h.send('stop_timer', entry_id=entry, expected_version=1)
        assert accepted.action_utc_us == end
        history = h.exchange('history', dict(task_id=key, cutoff_utc_us=end, period='all'))
        assert {r['work_date']:r['duration_us'] for r in history} == days
        assert all(r['entry_id'] == entry and r['original_start_utc_us'] == begin for r in history)
        assert sum(r['duration_us'] for r in history) == end-begin
        final = h.facts(); assert len(final['work_entries']) == len(final['work_revisions']) == 1
    with session(directory) as fresh:
        assert fresh.exchange('read', end)['active'] is None and fresh.facts() == final
    record(tmp_path/'temporal-evidence.json', start_utc_us=begin, stop_utc_us=end, expected=days,
           history=history, baseline=baseline, final=final)


@pytest.mark.parametrize('monday,tuesday,quarters,adjustment', [
    ('1:08','1:07',(5,4),0), ('1:08','1:08',(5,5),14*M),
    ('1:10','0:20',(5,1),0), ('0:03','0:03',(1,0),9*M), ('0:15','0:30',(1,2),0),
], ids=['C','D','E','F','G'])
def test_independent_C_to_G_allocation_frozen_restore_schema4(tmp_path, monday, tuesday, quarters, adjustment):
    directory = tmp_path/'source'; image = tmp_path/'snapshot'; restored = tmp_path/'restored'
    with session(directory, True) as h:
        key = h.task(h.project(h.project())); dated(h, key, monday); dated(h, key, tuesday, TUESDAY)
        value = preview(h, key)
        assert tuple(v.suggested_quarters for v in value.cells) == quarters and len(value.basis) == 7
        assert sum(quarters)*15*M-sum(v.actual_us for v in value.basis) == adjustment
        assert {v.task_id for v in value.cells} == {key}
        accepted, outcome = h.send('register_timesheet_export', candidate=value.content())
        receipt(h.facts(), accepted, outcome.result)
        assert h.exchange('timesheet_export', value.export_id) == value
        facts = h.facts(); assert h.exchange('backup', dict(request_id=uid(), destination=str(image)))['result'].verified
    raw = image.read_bytes(); assert br.validate_image(image).dataset_id == value.dataset_id
    assert br.restore_image(image, restored).verified
    with session(restored) as h:
        assert h.facts() == facts
        retained = h.exchange('timesheet_export', value.export_id)
        assert retained == value and retained.report_utf8 == value.report_utf8
        assert retained.content() == value.content() and retained.basis == value.basis
        assert tuple(v.suggested_quarters for v in retained.cells) == quarters
    assert image.read_bytes() == raw
    record(tmp_path/'allocation-evidence.json', expected_quarters=quarters, adjustment_us=adjustment,
           candidate=value.content(), request=accepted.content().decode(), facts=facts)


def test_unknown_zero_and_opposing_daily_mismatch_schema4(tmp_path):
    with session(tmp_path/'confirmation', True) as h:
        h.send('set_week_start', week_start=0, expected_week_start=6)
        key = h.task(h.project(h.project())); dated(h, key, '0:03'); dated(h, key, '0:03', TUESDAY)
        report = week(h); cells = {r['work_date']:r for r in report['daily_cells'] if r['task_id'] == key}
        assert [cells[d]['suggested_quarters'] for d in (MONDAY,TUESDAY)] == [1,0]
        assert [cells[d]['classification'] for d in (MONDAY,TUESDAY)] == ['UNKNOWN','UNKNOWN']
        manual(h, key, 1); report = week(h)
        cells = {r['work_date']:r for r in report['daily_cells'] if r['task_id'] == key}
        assert [cells[d]['classification'] for d in (MONDAY,TUESDAY)] == ['MATCH','UNKNOWN']
        assert not report['coverage']['complete']
        zero = manual(h, key, 0, TUESDAY); report = week(h)
        cells = {r['work_date']:r for r in report['daily_cells'] if r['task_id'] == key}
        assert [cells[d]['classification'] for d in (MONDAY,TUESDAY)] == ['MATCH','MATCH']
        assert all(cells[d]['classification'] == 'NOT_APPLICABLE' for d in ('2026-10-21','2026-10-22','2026-10-23','2026-10-24','2026-10-25'))
        assert report['coverage']['complete'] and report['task_weeks'][0]['review_complete']
        assert h.exchange('polr_day', dict(task_id=key,work_date=TUESDAY,cutoff_utc_us=OBS))['current_batch_id'] == zero
        assert h.exchange('polr_batch', zero)['cells'][0]['confirmed_quarters'] == 0
        other = h.task(); dated(h, other, '1:15'); dated(h, other, '0:45', TUESDAY)
        manual(h, other, 4); manual(h, other, 4, TUESDAY); opposing = week(h)
        daily = {r['work_date']:r for r in opposing['daily_cells'] if r['task_id'] == other}
        assert [daily[d]['suggested_gap_quarters'] for d in (MONDAY,TUESDAY)] == [1,-1]
        assert [daily[d]['classification'] for d in (MONDAY,TUESDAY)] == ['MISMATCH','MISMATCH']
        task_week = next(r for r in opposing['task_weeks'] if r['task_id'] == other)
        assert task_week['weekly_target_quarters'] == task_week['known_confirmed_quarters'] == 8
        assert not task_week['review_complete'] and not opposing['coverage']['complete']
        record(tmp_path/'confirmation-evidence.json', complete_zero=report, opposing=opposing, facts=h.facts())


def test_frozen_report_corrections_and_reminder_schema4(tmp_path):
    directory = tmp_path/'corrections'
    with session(directory, True) as h:
        h.send('set_week_start', week_start=0, expected_week_start=6)
        group = h.project(h.project()); a = h.task(group); dated(h, a, '3:00')
        a_report = registered(h, a); manual(h, a, 12)
        b = h.task(group); b_entry = dated(h, b, '3:00'); b_report = registered(h, b); manual(h, b, 12)
        frozen = h.facts(); assert h.exchange('polr_reminder', h.now)['dismissed_local_date'] is None
        dated(h, a, '2:00')
        h.send('edit_date_only_work', task_id=b, entry_id=b_entry, expected_revision=1,
               work_date=MONDAY, duration_text='2:30', comment='F1 independent case B')
        report = week(h); cells = {(r['task_id'],r['work_date']):r for r in report['daily_cells']}
        for key, expected in ((a,(500,20,12,200,8)), (b,(250,10,12,-50,-2))):
            cell = cells[key,MONDAY]
            assert tuple(cell[f] for f in ('actual_hundredths','suggested_quarters','confirmed_quarters','daily_delta_hundredths','suggested_gap_quarters')) == expected
            assert cell['classification'] == 'MISMATCH'
        after = h.facts()
        for table in ('timesheet_exports','timesheet_export_tasks','timesheet_export_week_basis','timesheet_export_cells',
                      'polr_confirmation_batches','polr_confirmation_cells','polr_confirmed_current'):
            assert after[table] == frozen[table], table
        for value in (a_report,b_report):assert h.exchange('timesheet_export',value.export_id) == value
        assert h.state()['report']['application']['today_us'] == 450*M
        assert sum(v['today_us'] for v in h.state()['report']['individual'].values()) == 450*M
        # Monday's approved current-week reminder evaluation includes both mismatches.
        due = h.exchange('polr_reminder',h.now); assert due['reminder_due']
        before_dismiss = h.facts()
        dismissal, _ = h.send('dismiss_polr_reminder_today', local_date=MONDAY)
        dismissed = h.facts()
        for table in before_dismiss.keys()-{'dataset_meta','committed_requests','sqlite_sequence'}:
            assert dismissed[table] == before_dismiss[table], table
        assert dismissed['dataset_meta'][0][:-1] == before_dismiss['dataset_meta'][0][:-1]
        assert dismissed['dataset_meta'][0][-1] == MONDAY
        assert len(dismissed['committed_requests']) == len(before_dismiss['committed_requests']) + 1
        assert not h.exchange('polr_reminder',h.now)['reminder_due']
        restart_cutoff = h.now
    with session(directory) as h:
        assert h.facts() == dismissed
        same = h.exchange('polr_reminder',restart_cutoff)
        assert same['local_today'] == same['dismissed_local_date'] == MONDAY and not same['reminder_due']
        # Friday is the next selected current-week reminder day, not a system-clock change.
        friday = to_us(datetime.fromisoformat('2026-10-23T15:00:00+00:00'))
        later = h.exchange('polr_reminder',friday)
        assert later['local_today'] == '2026-10-23' and later['dismissed_local_date'] == MONDAY
        assert later['reminder_due'] and h.facts() == dismissed
        record(tmp_path/'correction-evidence.json', reconciliation=report, before=frozen, after=after,
               dismissal=dismissal.content().decode(), same_day=same, later_day=later, facts=dismissed)
