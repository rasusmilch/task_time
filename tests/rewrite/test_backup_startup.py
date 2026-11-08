"""Current source recovery/launch and separate historical-schema refusal."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from conftest import uid
from test_app import root
from test_backup_restore import logical
from runtime4_cases import Runtime
from chronicle.sqlite_store import SQLiteStore
from chronicle.schema4_runtime_service import Schema4RuntimeService


def command_record(path, result):
    path.write_text(json.dumps(dict(command=result.args, exit_code=result.returncode,
        stdout=result.stdout, stderr=result.stderr), indent=2)+'\n', encoding='utf-8')


def cli(*args):
    return subprocess.run([sys.executable,'-B','run_chronicle.py',*map(str,args)],
        capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=15,
        env=dict(os.environ,DISPLAY='',PYTHONIOENCODING='utf-8'))


def test_real_tk_cold_restore_then_normal_source_launcher_new_owner_and_worker(tmp_path, root):
    directory=tmp_path/'source';backup=tmp_path/'backup.sqlite3'
    store=SQLiteStore(directory,create=True,timezone='America/Chicago',schema_version=4)
    try:
        runtime=Runtime(store);assert type(runtime.service) is Schema4RuntimeService
        task=runtime.task();retained=uid()
        runtime.send('add_date_only_work',task_id=task,entry_id=retained,work_date='2026-10-19',
                     duration_text='0:15',comment='Retained schema4 source work')
        active=uid();started,_=runtime.send('start_timer',task_id=task,entry_id=active,expected_task_version=1)
        start=started.action_utc_us;action=start+60_000_000
        before=runtime.facts();identity=store.dataset_id;timezone=store.timezone
        source_bytes=store.path.read_bytes()
        result=store.backup(backup);assert result.verified,result
        backup_bytes=backup.read_bytes();assert logical(backup)==before
        requests=[dict(request_id=r.request_id,content_hex=r.content().hex()) for r in runtime.requests]
    finally:
        store.close()
    assert store.connection is None and store.lock.file is None
    assert store.path.read_bytes()==source_bytes and logical(store.path)==before
    verified=cli('--verify-backup',backup);command_record(tmp_path/'verify-command.json',verified)
    assert verified.returncode==0,verified.stderr
    assert 'Backup verified' in verified.stdout and identity in verified.stdout
    restored=tmp_path/'restored';assert not restored.exists()
    result=cli('--restore-from',backup,'--data-dir',restored);command_record(tmp_path/'restore-command.json',result)
    assert result.returncode==0,result.stderr
    assert 'Restore verified' in result.stdout
    assert logical(restored/'chronicle.sqlite3')==before
    assert store.path.read_bytes()==source_bytes and backup.read_bytes()==backup_bytes
    # A fresh process drives the real root launcher, StartupWindow handoff and
    # actual app/worker. Instrumentation observes the canonical execution only.
    code=r'''
import importlib.abc,json,os,runpy,sys,threading,traceback
from pathlib import Path
sys.path[:0]=[str(Path('src').resolve()),str(Path('tests/rewrite').resolve())]
class Forbidden(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,*a):
        if fullname.split('.')[0] in ('task_timer','apsw','pysqlite3','PyInstaller'):
            raise AssertionError('Forbidden runtime import: '+fullname)
sys.meta_path.insert(0,Forbidden())
from chronicle import bootstrap,startup
from chronicle.app import ChronicleApp
from chronicle.worker import DatabaseWorker
from chronicle.sqlite_store import SQLiteStore
from chronicle.schema4_runtime_service import Schema4RuntimeService
from chronicle.timekeeping import from_us
from test_backup_restore import logical
expected_entry,expected_start,task,entry,directory,identity,zone,instant,backup,proof=sys.argv[1:]
expected_start=int(expected_start);instant=int(instant)
assert bootstrap.tk._default_root is None
apps=[];starts=[];executions=[];errors=[];stage=[0];accepted=[];stores=[]
handoff=startup.StartupWindow.handoff
execute=Schema4RuntimeService.execute

def observed_handoff(self,ready):
    assert type(self) is startup.StartupWindow
    starts.append(self)
    return handoff(self,ready)
startup.StartupWindow.handoff=observed_handoff

def observed_execute(self,request):
    assert type(self) is Schema4RuntimeService and type(self.store) is SQLiteStore
    assert self.store.schema_version==4
    stores.append(self.store);executions.append((request,threading.get_ident()))
    return execute(self,request)
Schema4RuntimeService.execute=observed_execute

def application(root,worker,**kwargs):
    assert type(worker) is DatabaseWorker and worker.is_alive()
    app=ChronicleApp(root,worker,now_utc=lambda:from_us(instant),**kwargs)
    assert type(app) is ChronicleApp and starts[-1].root is root and starts[-1].worker is worker
    assert app.pending is None and app.editor is app.history is app.timesheet is app.backup_dialog is None
    apps.append(app)
    def failed(*args):
        errors.append(repr(args[1]));traceback.print_exception(*args);root.destroy()
    root.report_callback_exception=failed
    def drive():
        if app.ready and app.state.get('report') is not None:
            assert app.presentation_profile=='schema4' and not app.candidate_presentation and app.schema4_presentation
            assert app.state['schema_version']==4 and app.state['semantic_verified'] is True
            assert app.state['ordinary_startup_permitted'] is True
            assert app.dataset_id==app.state['dataset_id']==identity and app.state['timezone']==zone
            assert app.state['active']['entry_id']==expected_entry and app.state['active']['start_utc_us']==expected_start
            assert [w for w in threading.enumerate() if type(w) is DatabaseWorker]==[worker]
            if stage[0]==0:
                assert logical(Path(directory)/'chronicle.sqlite3')==logical(Path(backup))
                assert not errors and root.grab_current() is None
                assert app._submit('add_date_only_work',task_id=task,entry_id=entry,work_date='2026-10-19',duration_text='0:01',comment='new restored session')
                accepted.append(app.pending);assert app.pending.action_utc_us==instant
                stage[0]=1
            elif stage[0]==1 and app.pending is None and not app.executing:
                assert app._mutation_outcome.status=='committed'
                stage[0]=2;app.request_close();return
        if app.alive:root.after(10,drive)
    root.after(0,drive)
    def timeout():raise AssertionError('Source launch timed out')
    root.after(10000,timeout)
    return app
bootstrap.ChronicleApp=application
sys.argv=['run_chronicle.py','--data-dir',directory]
runpy.run_path('run_chronicle.py',run_name='__main__')
assert len(starts)==len(apps)==len(accepted)==len(executions)==1
app=apps[0];worker=app.worker;worker.join(5)
assert not worker.is_alive() and app._worker_stopped and not errors and stage[0]==2
assert executions[0][0] is accepted[0] and executions[0][1]==worker.ident!=threading.get_ident()
assert stores[0].connection is None and stores[0].lock.file is None
assert not bootstrap.tk._default_root
try:app.root.winfo_exists()
except bootstrap.tk.TclError:pass
else:raise AssertionError('Source root survived shutdown')
Path(proof).write_text(json.dumps(dict(pid=os.getpid(),parent_pid=os.getppid(),dataset_id=app.dataset_id,
    active_entry_id=app.state['active']['entry_id'],active_start=app.state['active']['start_utc_us'],request_id=accepted[0].request_id,
    request_content_hex=accepted[0].content().hex(),action_utc_us=accepted[0].action_utc_us,schema_version=app.state['schema_version'],
    semantic_verified=app.state['semantic_verified'],ordinary_startup_permitted=app.state['ordinary_startup_permitted'],
    presentation_profile=app.presentation_profile,candidate_presentation=app.candidate_presentation,
    worker_type=type(worker).__name__,worker_stopped=not worker.is_alive(),store_closed=stores[0].connection is None,
    startup_count=len(starts),root_disposed=True,callback_errors=errors),indent=2)+'\n',encoding='utf-8')
print('Fresh source session ready, mutation committed, active timer preserved, orderly shutdown.')
'''
    added=uid();proof=tmp_path/'source-process.json';profile=tmp_path/'profile';profile.mkdir()
    command=[sys.executable,'-B','-c',code,active,str(start),task,added,str(restored),identity,timezone,str(action),str(backup),str(proof)]
    result=subprocess.run(command,env=dict(os.environ,HOME=str(profile),USERPROFILE=str(profile),LOCALAPPDATA=str(profile)),
                          capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=18)
    command_record(tmp_path/'source-command.json',result)
    assert result.returncode==0,result.stderr
    assert 'Fresh source session ready' in result.stdout
    observed=json.loads(proof.read_text(encoding='utf-8'))
    assert observed['pid']!=os.getpid()  # A Windows venv redirector may be the immediate parent.
    after=logical(restored/'chronicle.sqlite3')
    assert len([r for r in after['work_entries'] if r[0]==added])==1
    revisions=[r for r in after['work_revisions'] if r[0]==added]
    assert len(revisions)==1 and revisions[0][2]=='date_only'
    assert revisions[0][5]=='2026-10-19' and revisions[0][6]==60_000_000
    receipts=[r for r in after['committed_requests'] if r not in before['committed_requests']]
    assert len(receipts)==1 and receipts[0][1]==observed['request_id']
    assert receipts[0][4]==bytes.fromhex(observed['request_content_hex']) and receipts[0][6]==action
    assert len([r for r in after['work_entries'] if r[0]==active])==1
    for name,rows in before.items():
        if name not in ('work_entries','work_revisions','committed_requests','sqlite_sequence'):assert after[name]==rows
        elif name!='sqlite_sequence':assert all(r in after[name] for r in rows)
    assert len(after['work_entries'])==len(before['work_entries'])+1
    assert len(after['work_revisions'])==len(before['work_revisions'])+1
    final=SQLiteStore(restored,schema_version=4)
    try:
        assert final.dataset_id==identity and final.timezone==timezone
        assert Schema4RuntimeService(final).read_current_state(cutoff_utc_us=action)['active']['entry_id']==active
    finally:final.close()
    assert store.path.read_bytes()==source_bytes and logical(store.path)==before and backup.read_bytes()==backup_bytes
    (tmp_path/'source-facts.json').write_text(json.dumps(dict(dataset_id=identity,timezone=timezone,task_id=task,
        retained_entry_id=retained,active_entry_id=active,active_start=start,setup_requests=requests,
        before=before,after=after,new_entry_id=added,process=observed,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),backup_sha256=hashlib.sha256(backup_bytes).hexdigest()),indent=2,
        default=lambda b:dict(bytes_hex=b.hex()))+'\n',encoding='utf-8')


def test_historical_schema3_backup_restore_refuses_current_cli_without_mutating_source(store,task,tmp_path):
    backup=tmp_path/'historical.sqlite3';assert store.schema_version==3 and store.backup(backup).verified
    source_bytes=store.path.read_bytes();backup_bytes=backup.read_bytes();before=logical(store.path);identity=store.dataset_id
    target=tmp_path/'must-not-exist';assert not target.exists()
    result=cli('--restore-from',backup,'--data-dir',target);command_record(tmp_path/'historical-refusal-command.json',result)
    assert result.returncode!=0 and 'require schema 4' in result.stderr
    assert not target.exists() and store.dataset_id==identity and logical(store.path)==before
    assert logical(backup)==before and store.path.read_bytes()==source_bytes and backup.read_bytes()==backup_bytes
