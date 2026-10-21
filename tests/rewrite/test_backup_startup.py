"""Cold recovery CLI followed by a separate ordinary source-launch session."""
import os
from pathlib import Path
import subprocess
import sys

from conftest import NOW,uid
from test_app import root
from test_backup_restore import cli,logical,rich


def test_real_tk_cold_restore_then_normal_source_launcher_new_owner_and_worker(store,service,task,rich,tmp_path,root):
    backup=tmp_path/'backup.sqlite3';assert store.backup(backup).verified
    source=logical(store.path);source_bytes=store.path.read_bytes();backup_bytes=backup.read_bytes()
    result=cli('--restore-from',backup,'--data-dir',tmp_path/'restored')
    assert result.returncode==0,result.stderr
    # The recovery invocation is finished. This is an independent process with
    # the real root launcher, App, worker and ready/read delivery, not a live swap.
    code=r'''
import importlib.abc,runpy,sys
from pathlib import Path
sys.path.insert(0,str(Path('src').resolve()))
class Forbidden(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,*a):
        if fullname.split('.')[0] in ('task_timer','apsw','pysqlite3','PyInstaller'):
            raise AssertionError('Forbidden runtime import: '+fullname)
sys.meta_path.insert(0,Forbidden())
from chronicle import bootstrap
from chronicle.app import ChronicleApp
from chronicle.timekeeping import from_us
expected_entry,task,entry,directory=sys.argv[1:]
class Driver(ChronicleApp):
    def __init__(self,root,worker):
        super().__init__(root,worker,now_utc=lambda:from_us(1792422000000000))
        assert self.pending is None and self.editor is self.history is self.timesheet is self.backup_dialog is None
        self.stage=0
        root.report_callback_exception=lambda *args:(_ for _ in ()).throw(args[1])
        root.after(0,self.drive)
        root.after(10000,lambda:(_ for _ in ()).throw(AssertionError('Source launch timed out')))
    def drive(self):
        if self.ready and self.state.get('report') is not None:
            assert self.state['active']['entry_id']==expected_entry
            if self.stage==0:
                assert self._submit('add_date_only_work',task_id=task,entry_id=entry,work_date='2026-10-19',duration_text='0:01',comment='new restored session')
                self.stage=1
            elif self.stage==1 and self.pending is None and not self.executing:
                self.stage=2
                self.request_close()
                return
        if self.alive:self.root.after(10,self.drive)
bootstrap.ChronicleApp=Driver
sys.argv=['run_chronicle.py','--data-dir',directory]
result=runpy.run_path('run_chronicle.py',run_name='__main__')
assert not bootstrap.tk._default_root
print('Fresh source session ready, mutation committed, active timer preserved, orderly shutdown.')
'''
    added=uid()
    result=subprocess.run([sys.executable,'-B','-c',code,rich['active'],task,added,str(tmp_path/'restored')],
                          env=os.environ.copy(),capture_output=True,text=True,timeout=18)
    assert result.returncode==0,result.stderr
    assert 'Fresh source session ready' in result.stdout
    recovered=logical(tmp_path/'restored'/'chronicle.sqlite3')
    assert any(r[0]==added for r in recovered['work_entries'])
    for name,rows in source.items():
        if name not in ('work_entries','work_revisions','committed_requests','sqlite_sequence'):
            assert recovered[name]==rows
        else:
            if name!='sqlite_sequence':assert all(r in recovered[name] for r in rows)
    assert store.path.read_bytes()==source_bytes and logical(store.path)==source and backup.read_bytes()==backup_bytes
