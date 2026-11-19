"""Fresh source-launch processes use the actual current startup and worker."""
import json,os,subprocess,sys
from pathlib import Path
import pytest
from chronicle.sqlite_store import SQLiteStore
from chronicle import launcher_selection as ls
from test_ui import root,pump
from chronicle.startup import StartupWindow
from chronicle.app import ChronicleApp
from chronicle.worker import DatabaseWorker


def test_cancel_is_pure_and_failed_startup_cleans_same_root(root,tmp_path):
    places=ls.Locations(tmp_path/'never-created',tmp_path/'selection.json')
    flow=StartupWindow(root,app_factory=ChronicleApp,worker_factory=DatabaseWorker,locations=places)
    pump(root,lambda:flow.discover_id is None)
    assert flow.app is None and flow.worker is None and not list(tmp_path.iterdir())
    flow.cancel();assert not list(tmp_path.iterdir())


def test_damaged_current_data_refuses_before_application_construction(root,tmp_path):
    directory=tmp_path/'bad';s=SQLiteStore(directory,create=True,timezone='UTC');s.connection.execute('DROP TRIGGER active_only_open');s.close()
    calls=[]
    def forbidden(*a,**k):calls.append(True);raise AssertionError('App must not be constructed')
    flow=StartupWindow(root,app_factory=forbidden,worker_factory=DatabaseWorker,locations=ls.Locations(tmp_path/'unused',None))
    pump(root,lambda:flow.discover_id is None);flow.begin(directory,create=False,timezone=None)
    pump(root,lambda:flow.failure is not None and flow.worker is None)
    assert flow.app is None and not calls and root.winfo_exists() and not root.errors


@pytest.mark.parametrize('mode',['explicit','remembered','create'])
def test_actual_source_launcher_process_ready_and_orderly_shutdown(tmp_path,mode):
    if not os.environ.get('DISPLAY'):pytest.skip('Real Tk display required for source launch')
    repo=Path(__file__).resolve().parents[1];directory=tmp_path/'xdg'/'Chronicle'/'Data'
    if mode!='create':
        owner=SQLiteStore(directory,create=True,timezone='America/Chicago');identity=owner.dataset_id;owner.close()
    else:identity=None
    if mode=='remembered':ls.remember(directory.parent/'launcher-selection.json',directory,None)
    args=['--data-dir',str(directory)] if mode!='remembered' else []
    if mode=='create':args+=['--create','--timezone','America/Chicago']
    code='''import json,runpy,sys
from chronicle.app import ChronicleApp
original=ChronicleApp.__init__
def construct(self,*args,**kwargs):
    original(self,*args,**kwargs)
    errors=[];self.root.report_callback_exception=lambda t,e,b:errors.append(repr(e))
    def observe():
        if not self.ready or self.state.get('report') is None:
            self.root.after(20,observe);return
        print(json.dumps(dict(dataset_id=self.dataset_id,schema_version=self.state['schema_version'],semantic_verified=self.state['semantic_verified'],ordinary_startup_permitted=self.state['ordinary_startup_permitted'],worker_alive=self.worker.is_alive(),worker_type=type(self.worker).__name__,errors=errors)),flush=True)
        self.request_close()
    self.root.after(20,observe)
ChronicleApp.__init__=construct
sys.argv=['run_chronicle.py']+sys.argv[1:]
runpy.run_path('run_chronicle.py',run_name='__main__')
'''
    env=dict(os.environ,XDG_DATA_HOME=str(tmp_path/'xdg'),PYTHONPATH=str(repo/'src'),PYTHONDONTWRITEBYTECODE='1')
    command=[sys.executable,'-B','-c',code,*args];result=subprocess.run(command,cwd=repo,env=env,capture_output=True,text=True,timeout=20)
    (tmp_path/'launcher-observation.json').write_text(json.dumps(dict(command=command,exit=result.returncode,stdout=result.stdout,stderr=result.stderr),indent=2)+'\n')
    assert result.returncode==0,(result.stdout,result.stderr)
    observed=json.loads(result.stdout.strip());assert observed['schema_version']==5 and observed['semantic_verified'] and observed['ordinary_startup_permitted']
    assert observed['worker_type']=='DatabaseWorker' and observed['worker_alive'] and not observed['errors']
    if identity:assert observed['dataset_id']==identity
    fresh=SQLiteStore(directory)
    try:assert fresh.dataset_id==observed['dataset_id']
    finally:fresh.close()
