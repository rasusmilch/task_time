from dataclasses import replace
import pytest
from conftest import uid,M
from chronicle import project_ui as ui


@pytest.mark.parametrize('mon,tue,quarters,adjustment',[('1:08','1:07',(5,4),0),('1:08','1:08',(5,5),14),('1:10','0:20',(5,1),0),('0:03','0:03',(1,0),9),('0:15','0:30',(1,2),0)],ids=['C','D','E','F','G'])
def test_frozen_real_project_allocation_and_reopen(client,mon,tue,quarters,adjustment):
    h=client;p=h.project();task=h.task(p);h.dated(task,mon);h.dated(task,tue,'2026-10-20');value=h.export(task)
    assert tuple(c.suggested_quarters for c in value.cells)==quarters
    assert len(value.basis)==7 and value.tasks[0].project_id==p
    assert sum(r.suggested_quarters*15*M-r.actual_us for r in value.basis)==adjustment*M
    s=h.store;directory=s.directory;before=h.facts();raw=s.path.read_bytes();s.close()
    from chronicle.sqlite_store import SQLiteStore
    from conftest import Client
    reopened=SQLiteStore(directory)
    try:
        assert Client(reopened).facts()==before and reopened.path.read_bytes()==raw
        assert Client(reopened).service.read_registered_timesheet_export(value.export_id)==value
    finally:reopened.close()


def test_frozen_bytes_publication_saved_inventory_and_movement(client,tmp_path):
    h=client;p=h.project();q=h.project();task=h.task(p);h.dated(task);value=h.export(task)
    target=tmp_path/'report.txt';published=h.service.materialize_registered_timesheet_export(value.export_id,target)
    assert published.verified and target.read_bytes()==value.report_utf8
    before=h.facts();h.send('rename_project',project_id=p,expected_version=1,name='Renamed')
    h.send('move_task_branch',**h.move_args(task,q))
    assert h.service.read_registered_timesheet_export(value.export_id)==value
    assert h.service.list_registered_timesheet_exports()[0]['export_id']==value.export_id
    for table in ('timesheet_exports','timesheet_export_tasks','timesheet_export_cells','timesheet_export_week_basis'):
        assert h.facts()[table]==before[table]
    target.unlink();assert h.service.read_registered_timesheet_export(value.export_id).report_utf8==value.report_utf8


def reconcile(h,task):
    return h.service.read_polr_reconciliation(cutoff_utc_us=h.now,period='custom',start_date='2026-10-19',end_date='2026-10-20',scope_kind='selected',task_ids=[task])


def test_unknown_zero_absolute_confirmation_and_opposing_mismatches(client):
    h=client;p=h.project();task=h.task(p);h.dated(task,'1:15');h.dated(task,'0:45','2026-10-20')
    assert [c['classification'] for c in reconcile(h,task)['daily_cells']]==['UNKNOWN','UNKNOWN']
    h.manual(task,0);day=h.service.read_polr_day_status(task,'2026-10-19',cutoff_utc_us=h.now)
    assert day['confirmed_quarters']==0 and day['current_batch_id']
    h.manual(task,4);h.manual(task,4,'2026-10-20');report=reconcile(h,task)
    assert [c['suggested_gap_quarters'] for c in report['daily_cells']]==[1,-1]
    assert [c['classification'] for c in report['daily_cells']]==['MISMATCH','MISMATCH'] and not report['coverage']['complete']


def test_source_confirmation_stale_prior_and_signed_delta(client):
    h=client;p=h.project();task=h.task(p);h.dated(task,'3:00');frozen=h.export(task)
    h.manual(task,0)
    proposal=h.service.read_polr_confirmation_proposal(frozen.export_id)
    args=dict(batch_id=uid(),mode='source',source_export_id=frozen.export_id,manual_cells=[],acknowledgements=[],**proposal)
    h.send('confirm_polr_absolute',expect='rejected',**args)
    args['acknowledgements']=[dict(task_id=r['task_id'],work_date=r['work_date'],suggested_quarters=r['suggested_quarters'],reviewed_prior_batch_id=r['prior_batch_id'],reviewed_prior_quarters=r['prior_quarters']) for r in args['reviewed_rows'] if r['requires_stale_acknowledgement'] and dict(task_id=r['task_id'],work_date=r['work_date']) in args['selected_keys']]
    _,out=h.send('confirm_polr_absolute',**args);h.dated(task,'2:00')
    day=h.service.read_polr_day_status(task,'2026-10-19',cutoff_utc_us=h.now)
    assert (day['actual_hundredths'],day['suggested_quarters'],day['confirmed_quarters'],day['daily_delta_hundredths'],day['suggested_entry_gap_quarters'])==(500,20,12,200,8)
    assert h.service.read_registered_timesheet_export(frozen.export_id)==frozen
    batch=h.service.read_polr_confirmation_batch(out.result['batch_id']);assert batch['cells'][0]['confirmed_quarters']==12
    h.send('dismiss_polr_reminder_today',local_date='2026-10-19');before=h.facts();h.service.read_polr_reminder_status(cutoff_utc_us=h.now);assert h.facts()==before


@pytest.mark.parametrize('damage',['null project','wrong project','omitted task'])
def test_registration_refuses_crafted_ownership_without_partial_facts(client,damage):
    h=client;p=h.project();q=h.project();task=h.task(p);h.dated(task);value=h.preview()
    content=value.content()
    if damage=='null project':content['tasks'][0]['project_id']=None
    elif damage=='wrong project':content['tasks'][0]['project_id']=q
    else:content['tasks']=[]
    h.send('register_timesheet_export',expect='rejected',candidate=content)


def test_report_conflict_requires_exact_review_and_never_changes_registered_evidence(client,tmp_path):
    from chronicle.timesheet_files import FileState
    h=client;p=h.project();task=h.task(p);h.dated(task);value=h.export(task);before=h.facts()
    target=tmp_path/'report.txt';target.write_bytes('Unrelated Ω report'.encode('utf-8'));old=target.read_bytes()
    observed=h.service.inspect_registered_export_destination(value.export_id,target)
    assert observed.state is FileState.CONFLICT
    refused=h.service.materialize_registered_timesheet_export(value.export_id,target)
    assert not refused.verified and refused.inspection.state is FileState.CONFLICT
    assert target.read_bytes()==old and h.facts()==before
    target.write_bytes(b'Changed after review')
    refused=h.service.materialize_registered_timesheet_export(value.export_id,target,confirmed_overwrite=True,expected_conflict=observed.conflict)
    assert not refused.verified and refused.error is not None
    assert target.read_bytes()==b'Changed after review' and h.facts()==before
    fresh=h.service.inspect_registered_export_destination(value.export_id,target)
    result=h.service.materialize_registered_timesheet_export(value.export_id,target,confirmed_overwrite=True,expected_conflict=fresh.conflict)
    assert result.verified and target.read_bytes()==value.report_utf8 and h.facts()==before
    assert h.service.materialize_registered_timesheet_export(value.export_id,target).verified
    assert h.facts()==before
