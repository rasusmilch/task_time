"""Ordinary worker/store rich workflow, immutable evidence, backup and restore."""
from contextlib import contextmanager
from pathlib import Path
import threading
import pytest
from chronicle.worker import DatabaseWorker,Message
from chronicle.sqlite_store import SQLiteStore
from chronicle.records import Request
from chronicle import project_ui as ui,backup_restore as br
from runtime4_cases import Runtime,uid,NOW,M
from test_backup_restore import logical,cli
from test_templates import nodes,apply_args


class Client:
    project=Runtime.project
    task=Runtime.task
    lifecycle=Runtime.lifecycle
    def __init__(self,worker,ready):
        self.worker=worker;self.ready=ready;self.now=NOW;self.requests=[];self.token=0
    def exchange(self,kind,value=None):
        self.token+=1;self.worker.requests.put(Message(kind,self.token,value))
        result=self.worker.results.get(timeout=15)
        assert result.kind==kind and result.token==self.token,result
        if kind in ('mutate','reconcile'):assert result.request is value
        return result.value
    def send(self,op,expect='committed',**args):
        self.now+=1000000
        r=Request.make(uid(),self.ready['dataset_id'],op,self.now,**args);self.requests.append(r)
        outcome=self.exchange('mutate',r);assert outcome.status==expect,outcome
        return r,outcome
    def state(self):return self.exchange('read',self.now)
    def facts(self):return logical(Path(self.worker.directory)/'chronicle.sqlite3')


@contextmanager
def session(directory,create=False):
    worker=DatabaseWorker(directory,create=create,timezone='America/Chicago' if create else None)
    worker.start()
    try:
        ready=worker.results.get(timeout=15);assert ready.kind=='ready',ready.value
        assert ready.value['schema_version']==4 and ready.value['semantic_verified'] is True
        assert ready.value['ordinary_startup_permitted'] is True and not ready.value.get('candidate_verified')
        yield Client(worker,ready.value)
    finally:
        if worker.is_alive():worker.requests.put(Message('shutdown'))
        worker.join(15);assert not worker.is_alive()


def test_production_worker_owns_the_only_store_connection_and_reports_actual_profile(tmp_path,monkeypatch):
    opened=[];original=SQLiteStore.__init__
    def observed(self,*args,**kw):
        original(self,*args,**kw);opened.append((self,threading.get_ident()))
    monkeypatch.setattr(SQLiteStore,'__init__',observed)
    with session(tmp_path/'ordinary',True) as h:
        assert len(opened)==1 and opened[0][1]==h.worker.ident!=threading.get_ident()
        assert opened[0][0].schema_version==4
        assert {k:h.ready['runtime'][k] for k in ('journal_mode','synchronous','foreign_keys')}==dict(journal_mode='delete',synchronous=3,foreign_keys=1)
        p=h.project();key=h.task(p)
        state=h.state();assert state['schema_version']==4 and state['tasks'][0]['task_id']==key
        assert h.exchange('reconcile',h.requests[-1]).status=='committed'
        assert h.exchange('unknown_read').status=='unavailable'
    assert opened[0][0].connection is None and opened[0][0].lock.file is None


def test_complete_ordinary_workflow_frozen_evidence_and_restored_future_work(tmp_path):
    directory=tmp_path/'production';backup=tmp_path/'backup.sqlite3';saved=tmp_path/'report.csv'
    with session(directory,True) as h:
        root=h.project(name='Root');child=h.project(root,'Child');deep=h.project(child,'Deep');other=h.project(name='Other')
        branch=h.task(deep,name='Former leaf')
        h.send('add_date_only_work',task_id=branch,entry_id=uid(),work_date='2026-10-19',duration_text='0:10',comment='Retained direct work')
        leaf=h.task(deep,branch,name='Leaf');second=h.task(deep,name='Second');zero=h.task(other,name='Zero')
        active=uid();start,_=h.send('start_timer',task_id=leaf,entry_id=active,expected_task_version=1)
        h.send('correct_active_start',entry_id=active,expected_version=1,date_text='2026-10-19',time_text='09:59',occurrence=None,comment='Accepted correction')
        h.now+=M;next_entry=uid()
        switch,_=h.send('switch_timer',expected_active_entry_id=active,expected_active_version=2,next_task_id=second,next_entry_id=next_entry,expected_task_version=1)
        h.now+=M;stop,_=h.send('stop_timer',entry_id=next_entry,expected_version=1)
        manual=uid();h.send('add_timed_work',task_id=second,entry_id=manual,start_date='2026-10-19',start_time='08:00',end_date='2026-10-19',end_time='08:20',start_occurrence=None,end_occurrence=None,comment='Manual')
        h.send('edit_closed_timed_work',task_id=second,entry_id=manual,expected_revision=1,start_date='2026-10-19',start_time='08:00',end_date='2026-10-19',end_time='08:25',start_occurrence=None,end_occurrence=None,comment='Corrected')
        dated=uid();h.send('add_date_only_work',task_id=second,entry_id=dated,work_date='2026-10-19',duration_text='0:15',comment='Dated')
        h.send('edit_date_only_work',task_id=second,entry_id=dated,expected_revision=1,work_date='2026-10-19',duration_text='0:20',comment='Corrected')
        deleted=uid();h.send('add_date_only_work',task_id=second,entry_id=deleted,work_date='2026-10-19',duration_text='0:03',comment='Retained deletion')
        h.send('delete_work_entry',task_id=second,entry_id=deleted,expected_revision=1,comment='Deleted revision retained')
        state=h.state();report=state['report']
        expected=55*M+stop.action_utc_us-(NOW-M)
        assert report['application']['today_us']==expected
        assert report['individual'][branch]['today_us']==10*M
        assert report['individual'][leaf]['today_us']==switch.action_utc_us-(NOW-M)
        assert report['project_direct'][root]['today_us']==0 and report['projects'][root]['today_us']==expected
        # Exercise every production read category using real retained records.
        hist=dict(task_id=second,cutoff_utc_us=h.now,period='all')
        assert h.exchange('history',hist)==h.exchange('history_snapshot',hist)['rows']
        assert len(h.exchange('revisions',dated)['revisions'])==2
        assert h.exchange('timesheet_tasks')['dataset_id']==h.ready['dataset_id']
        export_id=uid();candidate=h.exchange('timesheet_preview',dict(export_id=export_id,cutoff_utc_us=h.now,period='this_week',scope_kind='all'))
        h.send('register_timesheet_export',candidate=candidate.content())
        frozen_before=h.facts()['timesheet_exports']
        assert h.exchange('timesheet_export',export_id).report_utf8==candidate.report_utf8
        assert h.exchange('timesheet_exports')[0]['export_id']==export_id
        proposal=h.exchange('polr_proposal',export_id)
        h.send('confirm_polr_absolute',batch_id=uid(),mode='source',source_export_id=export_id,**proposal,manual_cells=[],acknowledgements=[])
        current=h.exchange('polr_manual',dict(task_id=zero,work_date='2026-10-19',cutoff_utc_us=h.now))
        batch=uid();h.send('confirm_polr_absolute',batch_id=batch,mode='manual',source_export_id=None,source_metadata=None,reviewed_rows=[],selected_keys=[],acknowledgements=[],manual_cells=[dict(task_id=zero,work_date='2026-10-19',confirmed_quarters=0,prior_batch_id=current['current_batch_id'],prior_quarters=current['confirmed_quarters'])])
        assert h.exchange('polr_day',dict(task_id=zero,work_date='2026-10-19',cutoff_utc_us=h.now))['confirmed_quarters']==0
        assert h.exchange('polr_batch',batch)['cells'][0]['confirmed_quarters']==0
        assert len(h.exchange('polr_history'))==2
        confirmed=h.facts()['polr_confirmation_cells']
        h.send('move_project_subtree',**ui.ProjectMoveReview(h.state(),child).arguments(other))
        from chronicle.movement import snapshot
        state=h.state();args,_=ui.task_move_arguments(state,branch,None,other,snapshot(state['tasks'],branch))
        h.send('move_task_branch',**args)
        moved=h.state()['report']
        assert moved['application']==report['application'] and moved['individual']==report['individual'] and moved['cumulative']==report['cumulative']
        assert moved['projects'][root]['today_us']==0 and moved['projects'][other]['today_us']==expected
        assert moved['project_direct'][other]['today_us']==10*M+report['individual'][leaf]['today_us']
        assert h.facts()['timesheet_exports']==frozen_before and h.facts()['polr_confirmation_cells']==confirmed
        h.lifecycle('project',deep);h.lifecycle('project',deep,'unarchive')
        template=uid();h.send('create_template',template_id=template,name='Blueprint',nodes=nodes(2))
        definition=next(t for t in h.state()['templates'] if t['template_id']==template)
        args=apply_args(definition,project=deep,project_version=next(p for p in h.state()['projects'] if p['project_id']==deep)['version'])
        args['reviewed_destination_project_ancestry']=ui.ancestry(h.state(),deep)
        h.send('apply_template',**args)
        assert h.state()['report']['application']==report['application']
        # Create unused structure after freezing all-scope reporting evidence.
        unused=h.project();nested=h.project(unused);unused_task=h.task(nested)
        preview=h.exchange('delete_preview',dict(entity_type='project',entity_id=unused))
        assert preview['project_count']==2 and preview['task_count']==1 and preview['eligible']
        sequence=h.facts()['sqlite_sequence'];h.send('delete_project',project_id=unused,expected_version=1,review=preview,confirmed_text='DELETE')
        assert h.facts()['sqlite_sequence']==sequence
        assert h.exchange('delete_presence',dict(entity_type='task',entity_id=unused_task))['historical_outcome_verified'] is False
        h.send('set_week_start',week_start=0,expected_week_start=6)
        reconciliation=h.exchange('polr_reconciliation',dict(cutoff_utc_us=h.now,period='this_week'))
        assert reconciliation['dataset_id']==h.ready['dataset_id']
        assert h.exchange('polr_reminder',h.now)['dataset_id']==h.ready['dataset_id']
        h.send('dismiss_polr_reminder_today',local_date='2026-10-19')
        assert h.exchange('timesheet_status',dict(export_id=export_id,destination=str(saved)))['result'].state.value
        published=h.exchange('timesheet_publish',dict(export_id=export_id,destination=str(saved)))['result']
        assert published.verified and saved.read_bytes()==candidate.report_utf8
        # Include a live timer in backup, without implicit Stop or Switch.
        h.send('start_timer',task_id=second,entry_id=uid(),expected_task_version=1)
        before=h.facts();identity=h.ready['dataset_id']
        result=h.exchange('backup',dict(request_id=uid(),destination=str(backup)))['result']
        assert result.verified and h.facts()==before
    raw=backup.read_bytes();image=br.validate_image(backup)
    assert image.dataset_id==identity and backup.read_bytes()==raw
    assert br.inspect_dataset(directory).classification==br.Compatibility.SUPPORTED_CURRENT
    verification=cli('--verify-backup',backup);assert verification.returncode==0,verification.stderr
    restored=tmp_path/'restored';restoration=cli('--restore-from',backup,'--data-dir',restored)
    assert restoration.returncode==0,restoration.stderr
    assert logical(restored/'chronicle.sqlite3')==before and backup.read_bytes()==raw
    with session(restored) as fresh:
        fresh.now=h.now
        assert fresh.ready['dataset_id']==identity and fresh.state()['active'] is not None
        assert fresh.exchange('timesheet_export',export_id).report_utf8==saved.read_bytes()
        assert fresh.facts()['polr_confirmation_cells']==confirmed
        active=fresh.state()['active'];fresh.now=h.now+M
        fresh.send('stop_timer',entry_id=active['entry_id'],expected_version=active['version'])
        assert fresh.state()['active'] is None


def test_worker_ready_waits_for_complete_schema4_validation(tmp_path,monkeypatch):
    from threading import Event
    from queue import Empty
    import chronicle.schema4_evidence as evidence
    verify=evidence.verify_transaction;entered=Event();release=Event();calls=[]
    def observed(c):
        if not calls:
            calls.append(True);entered.set();assert release.wait(8)
        return verify(c)
    monkeypatch.setattr(evidence,'verify_transaction',observed)
    worker=DatabaseWorker(tmp_path/'guarded',create=True,timezone='Etc/UTC');worker.start()
    try:
        assert entered.wait(8)
        with pytest.raises(Empty):worker.results.get(timeout=.1)
        release.set();ready=worker.results.get(timeout=10)
        assert ready.kind=='ready' and ready.value['semantic_verified']
    finally:
        release.set();worker.requests.put(Message('shutdown'));worker.join(15);assert not worker.is_alive()


def test_worker_legacy_refusal_never_publishes_ready_or_changes_source(tmp_path):
    from chronicle.timesheet_files import metadata
    s=SQLiteStore(tmp_path/'legacy',create=True,timezone='Etc/UTC',schema_version=3);path=s.path;s.close()
    raw=path.read_bytes();before=metadata(path.stat());worker=DatabaseWorker(path.parent);worker.start()
    try:
        failure=worker.results.get(timeout=10);stopped=worker.results.get(timeout=10)
        assert failure.kind=='startup_failed' and 'require schema 4' in str(failure.value)
        assert stopped.kind=='stopped'
    finally:worker.join(15);assert not worker.is_alive()
    assert path.read_bytes()==raw and metadata(path.stat())==before


def test_worker_failed_close_retains_lock_and_waits_for_explicit_retry(tmp_path,monkeypatch):
    release=[];owned=[];close=SQLiteStore.close;failure=OSError('Original production close fault')
    def refused(self):
        if not release:
            owned.append(self);raise failure
        return close(self)
    worker=DatabaseWorker(tmp_path/'closing',create=True,timezone='Etc/UTC');worker.start()
    try:
        assert worker.results.get(timeout=10).kind=='ready'
        monkeypatch.setattr(SQLiteStore,'close',refused)
        worker.requests.put(Message('shutdown'));result=worker.results.get(timeout=10)
        assert result.kind=='shutdown_failed' and result.value is failure
        assert worker.is_alive() and owned[0].lock.file is not None
        from test_bootstrap import child
        contender=child('from chronicle.sqlite_store import SQLiteStore;import sys;SQLiteStore(sys.argv[1])',worker.directory)
        assert contender.returncode!=0
    finally:
        release.append(True);worker.requests.put(Message('shutdown'));worker.join(15);assert not worker.is_alive()
    assert owned[0].connection is None and owned[0].lock.file is None


def test_unverified_ordinary_request_blocks_other_mutation_and_backup_until_exact_reconciliation(tmp_path,monkeypatch):
    from chronicle.records import Outcome
    verify=SQLiteStore.reconcile;probes=[]
    def unavailable(self,r):
        if not probes:return Outcome('unverified',error=OSError('Independent evidence temporarily unreadable'))
        return verify(self,r)
    # The actual SQL commit succeeds, its acknowledgement fails, and independent
    # evidence is temporarily unavailable. No success response is fabricated.
    from test_runtime4_store import Fault
    transact=SQLiteStore.transact;fired=[]
    def commit_fault(self,r,operation):
        if not fired:self.connection=Fault(self.connection,'after');fired.append(True)
        return transact(self,r,operation)
    monkeypatch.setattr(SQLiteStore,'transact',commit_fault);monkeypatch.setattr(SQLiteStore,'reconcile',unavailable)
    with session(tmp_path/'unverified',True) as h:
        original,_=h.send('create_project',expect='unverified',project_id=uid(),name='Original')
        before=h.facts()
        h.send('create_project',expect='unavailable',project_id=uid(),name='Must block')
        assert h.facts()==before
        result=h.exchange('backup',dict(request_id=uid(),destination=str(tmp_path/'blocked')))
        assert result['result'].status=='unavailable' and not (tmp_path/'blocked').exists()
        probes.append(True)
        result=h.exchange('reconcile',original);assert result.status=='committed'
        assert h.facts()==before
        h.project(name='After exact resolution')
