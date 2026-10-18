"""Real Git/SQLite crash cutpoints; disposable repositories and signed evidence."""
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from acs_team.coordination import ClaimDenied, CoordinationStore
from acs_team.db import DatabaseManager
from acs_team.evidence import EvidenceEngine, persist_evidence
from acs_team.schemas import Plan
from acs_team.scope_and_integration import IntegrationManager
from acs_team.team_recovery import TeamRecovery, process_owner


def fixture(tmp_path):
    repo = tmp_path/'repo'
    repo.mkdir()
    def git(*args, cwd=repo):
        return subprocess.run(['git',*args],cwd=cwd,check=True,capture_output=True,text=True).stdout.strip()
    git('init','-b','main')
    git('config','user.name','Fixture')
    git('config','user.email','fixture@example.invalid')
    (repo/'baseline').write_text('Keep unchanged')
    git('add','.')
    git('commit','-m','baseline')
    original = git('rev-parse','HEAD')
    db = DatabaseManager(tmp_path/'state.db')
    store = CoordinationStore(db)
    plan = Plan(mission_id='crash',requirements=['Add value'],tasks=[{
        'task_id':'add','title':'Add value','description':'Return 42','owns':['value.py'],
        'acceptance_criteria':['Returns 42'],'verification_commands':[['pytest','-q']], 'risk_level':'low'}])
    store.register(plan,str(repo))
    token = store.claim('crash','add','codex-primary')
    trees = tmp_path/'worktrees'
    trees.mkdir()
    worker = trees/'worker'
    branch = 'acsai/worker/crash/add'
    git('worktree','add','-b',branch,str(worker))
    (worker/'value.py').write_text('def value(): return 42\n')
    git('add','.',cwd=worker)
    git('commit','-m','implementation',cwd=worker)
    commit = git('rev-parse','HEAD',cwd=worker)
    key = 'disposable-recovery-test-key'
    evidence = EvidenceEngine(key).create_evidence('crash','add',commit,{'passed':True},{}).to_dict()
    ref = persist_evidence(evidence,tmp_path/'artifacts')
    completion = {'commit':commit,'branch':branch,'worktree':str(worker),'worker_evidence_ref':str(ref)}
    store.complete('crash','add',token,completion)
    recovery = TeamRecovery(db,trees,key)
    manager = IntegrationManager(repo,trees)
    integration_branch = manager.ensure_integration_branch('crash','HEAD')
    integration_path = manager.ensure_worktree(integration_branch)
    return locals()


@pytest.mark.failure_injection
def test_crash_after_git_merge_before_sqlite_commit_preserves_and_recovers(tmp_path):
    f = fixture(tmp_path)
    # A separate controller is killed by os._exit at the exact consistency gap.
    source = '''
import os, sys
from pathlib import Path
from acs_team.db import DatabaseManager
from acs_team.coordination import CoordinationStore
from acs_team.team_recovery import TeamRecovery
from acs_team.scope_and_integration import IntegrationManager
root=Path(sys.argv[1]); db=DatabaseManager(root/'state.db')
store=CoordinationStore(db); recovery=TeamRecovery(db,root/'worktrees','disposable-recovery-test-key')
row=store.tasks('crash')[0]; import json
completion=json.loads(row['result']); manager=IntegrationManager(root/'repo',root/'worktrees')
branch=manager.ensure_integration_branch('crash','HEAD')
recovery.prepare('crash','add',row['token'],root/'repo',branch,manager.ensure_worktree(branch),completion)
def cutpoint():
    manager.merge_task_branch(branch,completion['branch'])
    os._exit(77)
store.integration('crash','add',row['token'],cutpoint)
'''
    result = subprocess.run([sys.executable,'-c',source,str(tmp_path)],cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 77
    store, recovery, git = f['store'], f['recovery'], f['git']
    row = store.tasks('crash')[0]
    assert row['state'] == 'INTEGRATING'  # Durable intent survives the dead controller.
    interrupted = git('rev-parse',f['integration_branch'])
    assert interrupted != f['original']
    with pytest.raises(ClaimDenied):
        recovery.reconcile('crash',f['repo'])
    with f['db'].connection() as con:
        con.execute('UPDATE coord_tasks SET expires=0 WHERE mission="crash"')
    assert recovery.reconcile('crash',f['repo']) == ['add']
    assert git('rev-parse',f['integration_branch']) == f['original']
    assert git('rev-parse',f"acsai/recovery/crash/add-{f['token']}") == interrupted
    row = store.tasks('crash')[0]
    assert row['state'] == 'COMPLETED' and row['token'] > f['token']
    assert json.loads(row['result']) == f['completion']
    with pytest.raises(ClaimDenied):
        store.complete('crash','add',f['token'],f['completion'])
    # Same immutable worker output can now be integrated under the fresh token.
    recovery.prepare('crash','add',row['token'],f['repo'],f['integration_branch'],f['integration_path'],f['completion'])
    store.integration('crash','add',row['token'],lambda:f['manager'].merge_task_branch(f['integration_branch'],f['branch']))
    recovery.resolved('crash','add','VERIFIED')
    assert store.tasks('crash')[0]['state'] == 'INTEGRATED'
    assert git('rev-parse','HEAD') == f['original']
    assert git('status','--porcelain') == ''
    with f['db'].connection() as con:
        assert con.execute('SELECT count(*) FROM coord_recoveries').fetchone()[0] == 1


@pytest.mark.security
def test_recovery_refuses_live_owner_dirty_tree_and_tampered_evidence(tmp_path):
    f = fixture(tmp_path)
    recovery, db = f['recovery'], f['db']
    recovery.begin('crash',f['repo'])
    with pytest.raises(PermissionError,match='stolen'):
        recovery.begin('crash',f['repo'],resume=True)
    recovery.prepare('crash','add',f['token'],f['repo'],f['integration_branch'],f['integration_path'],f['completion'])
    with db.connection() as con:
        con.execute('UPDATE coord_tasks SET expires=0')
    with pytest.raises(PermissionError,match='still alive'):
        recovery.reconcile('crash',f['repo'])
    with db.connection() as con:
        row = con.execute('SELECT intent FROM integration_intents').fetchone()
        intent = json.loads(row[0])
        intent['owner']={**process_owner(),'start':'wrong-start'}
        con.execute('UPDATE integration_intents SET intent=?',(json.dumps(intent),))
    (f['integration_path']/'uncommitted').write_text('Preserve me')
    with pytest.raises(PermissionError,match='dirty'):
        recovery.reconcile('crash',f['repo'])
    assert (f['integration_path']/'uncommitted').read_text() == 'Preserve me'
    (f['integration_path']/'uncommitted').unlink()
    f['ref'].write_text('{}')
    with pytest.raises(PermissionError,match='evidence invalid'):
        recovery.reconcile('crash',f['repo'])
    assert f['store'].tasks('crash')[0]['token'] == f['token']


def test_integration_keeps_heartbeats_writable_and_serializes_other_integrators(tmp_path):
    f = fixture(tmp_path)
    store = f['store']
    def verify_without_database_writer_lock():
        assert store.tasks('crash')[0]['state'] == 'INTEGRATING'
        store.heartbeat('crash','add',f['token'])
        with pytest.raises(BlockingIOError):
            CoordinationStore(f['db']).integration('crash','add',f['token'],lambda:{})
        return {'verified':True}
    assert store.integration('crash','add',f['token'],verify_without_database_writer_lock)=={'verified':True}
    assert store.tasks('crash')[0]['state']=='INTEGRATED'


@pytest.mark.failure_injection
def test_supervised_tree_dies_when_controller_is_killed(tmp_path):
    marker = tmp_path/'worker-pids.json'
    code = '''import os,json,subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
Path(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid]))
time.sleep(60)
'''
    launcher = '''import sys
from pathlib import Path
from acs_team.supervision import ProcessSupervisor
ProcessSupervisor().run([sys.executable,'-c',sys.argv[2],sys.argv[1]],Path(sys.argv[1]).parent,timeout=90)
'''
    unrelated = subprocess.Popen(['sleep','30'])
    controller = subprocess.Popen([sys.executable,'-c',launcher,str(marker),code])
    try:
        deadline = time.monotonic()+10
        while not marker.exists() and time.monotonic()<deadline:
            time.sleep(.02)
        assert marker.exists()
        pids = json.loads(marker.read_text())
        controller.kill()
        controller.wait(timeout=5)
        deadline = time.monotonic()+5
        while any(Path(f'/proc/{pid}').exists() for pid in pids) and time.monotonic()<deadline:
            time.sleep(.02)
        assert all(not Path(f'/proc/{pid}').exists() for pid in pids)
        assert unrelated.poll() is None
    finally:
        if controller.poll() is None:
            controller.kill()
            controller.wait(timeout=5)
        unrelated.terminate()
        unrelated.wait(timeout=5)
