"""CLOUD_SIMULATED native protocol, real controller/Git/SQLite/pytest/Guardian."""
import hashlib
import json
from pathlib import Path
import subprocess
import threading

import pytest

from acs_team.benchmarks import fixture_verification
from acs_team.coordination import CoordinationStore
from acs_team.db import DatabaseManager
from acs_team.provider_workers import ProductionRoles, ProviderWorker
from acs_team.providers import Activations, ProviderContract, ProviderRuntime
from acs_team.runtime_view import runtime_snapshot
from acs_team.team_missions import ProviderTeamPlanner, TeamMissionController
from acs_team.team_runner import IndependentTester, TeamRunner
from acs_team.worktree_manager import WorktreeManager


@pytest.mark.simulated
@pytest.mark.parametrize('route',['direct','cli','daemon','review','recover','escalate','dependent'])
def test_native_protocol_natural_language_team_to_signed_integration_and_review(tmp_path, monkeypatch,route):
    monkeypatch.setenv('ACS_ENABLE_COORDINATION','1')
    monkeypatch.setenv('ACS_ENABLE_INTELLIGENCE','1')
    if route=='direct':
        monkeypatch.setenv('ACS_ENABLE_ACCEPTED_WORKTREE_CLEANUP','1')
    repo=tmp_path/'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git',*args],cwd=repo,check=True,capture_output=True,text=True).stdout.strip()
    git('init','-b','main')
    git('config','user.name','Fixture')
    git('config','user.email','fixture@example.invalid')
    (repo/'README.md').write_text('Disposable fixture')
    git('add','.')
    git('commit','-m','baseline')
    before=git('rev-parse','HEAD')
    db=DatabaseManager(tmp_path/'state.db')
    from acs_team.intelligence import Lessons
    lessons=Lessons(db)
    lesson=lessons.candidate(repo.name,'Testing','Missing assertions','Missing contract',
        'Check behavior through independent contracts',['python','testing'])
    # Explicit fixture human review; a fake provider outcome must never promote
    # a candidate lesson into a verified production lesson.
    lessons.human_confirm(repo.name,lesson,operator_confirmed=True,reference='fixture-human-review')
    calls=[]
    simultaneous = threading.Barrier(2)
    def provider(argv, workspace, **kwargs):
        cmd=argv[argv.index('--')+1:]
        prompt=cmd[-1] if 'exec' in cmd else cmd[cmd.index('-p')+1]
        request=json.loads(prompt)
        role=request['role']
        calls.append((role, str(workspace), kwargs['env']['HOME']))
        if role=='planner':
            assert 'Check behavior through independent contracts' in request['advisory_context_untrusted']
            correction = 'mandatory_acceptance_criteria' in request['goal']
            value={'mission_id':request['mission_id'],'requirements':['Both modules return 42'],
                   'tasks':[{'task_id':f't{i}','title':f'Implement {name}',
                             'description':f'Implement {name} with value() returning 42','owns':[name],
                             'acceptance_criteria':[f'{name} value returns 42'],
                             'verification_commands':[['pytest','-q']],'risk_level':'low'}
                            for i,name in enumerate(['alpha.py','beta.py'])]}
            if correction:
                required=json.loads(request['goal'])
                if route=='escalate':
                    value['tasks'][0]['acceptance_criteria'] += required['mandatory_acceptance_criteria']
                else:
                    value['tasks']=[{**value['tasks'][0],'task_id':'correction','owns':['gamma.py'],
                                     'acceptance_criteria':required['mandatory_acceptance_criteria']+required['required_original_acceptance_criteria']}]
            if route=='dependent':
                value['tasks'].append({**value['tasks'][0],'task_id':'t2','owns':['gamma.py'],
                    'reads':['alpha.py','beta.py'],'depends_on':['t0','t1'],
                    'acceptance_criteria':['Gamma combines both dependency values and returns 42']})
        elif role=='tester':
            module=Path(request['owns'][0]).stem
            value={'files':{f'tests/test_{module}.py':f'from {module} import value\ndef test_value(): assert value() == 42\n'}}
        elif role=='implementer':
            if request['owns'][0] in {'alpha.py','beta.py'}:
                simultaneous.wait(timeout=10)
            for name in request['owns']:
                if route=='dependent' and name=='gamma.py':
                    instruction=json.loads(request['instructions_untrusted'])
                    assert {m['task_id'] for m in instruction['dependency_handoffs_untrusted']}=={'t0','t1'}
                    assert all(m['payload']['commit'] for m in instruction['dependency_handoffs_untrusted'])
                    (workspace/name).write_text('from alpha import value as a\nfrom beta import value as b\ndef value(): return (a()+b())//2\n')
                else:
                    (workspace/name).write_text('def value(): return 42\n')
            value={'task_id':request['task_id'],'worker':request['worker_id'],'success':True,'summary':'Fixture implementation'}
        else:
            assert role=='reviewer'
            value={'verdict':'PASS','requirement_coverage':request['requirements'],'findings':[]}
            if route=='escalate' and sum(c[0]=='reviewer' for c in calls)<=2:
                value={'verdict':'FIX_REQUIRED','requirement_coverage':request['requirements'],
                       'findings':['Independent fixture review rejects the implementation']}
        text=json.dumps(value)
        output=json.dumps({'type':'item.completed','item':{'type':'agent_message','text':text}}) if 'exec' in cmd else json.dumps({'result':text})
        return {'exit_code':0,'reason':'completed','stdout':output}
    workers={}
    key='disposable-team-evidence-fixture-key'
    for name in ['codex-primary','agy-google-a','agy-google-b']:
        tools=tmp_path/f'{name}-tools'
        tools.mkdir()
        binary=tools/'provider'
        binary.write_text('#!/bin/sh\nexit 0\n')
        binary.chmod(0o700)
        home=tmp_path/f'{name}-auth'
        home.mkdir(mode=0o700)
        (home/'fixture').write_text('not credentials')
        contract=ProviderContract(worker_id=name,executable=str(binary),
            executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),auth_home=str(home),
            auth_paths=['fixture'],toolchain_roots=[str(tools)])
        authority=Activations(key,clock=lambda:150.)
        data={'worker_id':name,'contract_digest':contract.digest(),'verified_at':100.,'expires_at':200.,
              'session_id':'fixture','sandbox_verified':True,'label':'LOCAL_VERIFICATION_REQUIRED'}
        workers[name]=ProviderWorker(contract,ProviderRuntime((),executor=provider),authority,
                                     {**data,'signature':authority._signature(data)})
    class Registry:
        def list_available_workers(self):return list(workers)
        def get_worker(self,name):return workers[name]
    roles=ProductionRoles(workers['codex-primary'])
    def factory(database):
        return TeamRunner(CoordinationStore(database),workers,IndependentTester(roles.tester_id,roles.prepare),
                          {roles.reviewer_id:roles.review},WorktreeManager(tmp_path/'worktrees',min_free_gb=0),
                          tmp_path/'artifacts',key,verification_runner=fixture_verification)
    controller=TeamMissionController(db,Registry(),ProviderTeamPlanner(workers['codex-primary']),factory,
                                     evidence_key=key,root=tmp_path)
    goal='Implement alpha and beta value functions returning 42'
    if route=='recover':
        import multiprocessing
        import os
        import time
        from concurrent.futures import wait
        from acs_team.daemon_dispatch import DaemonDispatcher
        from acs_team.state_machine import StateMachine
        def interrupted_controller():
            original=CoordinationStore.integration
            def cutpoint(store,mission,task,token,operation):
                def merge_then_crash():
                    deadline=time.monotonic()+15
                    while any(row['state']=='RUNNING' for row in store.tasks(mission)) and time.monotonic()<deadline:
                        time.sleep(.02)
                    operation()
                    os._exit(77)
                return original(store,mission,task,token,merge_then_crash)
            CoordinationStore.integration=cutpoint
            controller.run_mission('team-e2e',goal,repo)
        child=multiprocessing.get_context('fork').Process(target=interrupted_controller)
        child.start()
        child.join(45)
        try:
            assert child.exitcode==77
        finally:
            if child.is_alive():
                child.kill()
                child.join(5)
        store=CoordinationStore(db)
        assert sorted(row['state'] for row in store.tasks('team-e2e'))==['COMPLETED','INTEGRATING']
        with db.connection() as con:
            con.execute('UPDATE coord_tasks SET expires=0')  # Fixture clock cutpoint.
        assert StateMachine(db).reconcile_interrupted_missions()[0]['state']=='RECOVERING'
        monkeypatch.setenv('ACS_ENABLE_TEAM_RECOVERY','1')
        monkeypatch.setenv('ACS_ENABLE_DAEMON_EXECUTION','1')
        dispatcher=DaemonDispatcher(db,lambda database:controller)
        try:
            assert dispatcher.tick()==1
            done,_=wait(list(dispatcher.active),timeout=45)
            assert len(done)==1
            result=next(iter(done)).result()
            assert result['status']=='COMPLETED',result
        finally:
            dispatcher.close()
        sessions=[e['details']['session_id'] for e in db.get_audit_trail('team-e2e') if e['action']=='PROVIDER_SESSION']
        assert len(sessions)==len(set(sessions))==7  # No provider calls repeated on recovery.
    elif route in {'direct','review','escalate','dependent'}:
        result=controller.run_mission('team-e2e',goal,repo)
    else:
        from argparse import Namespace
        from concurrent.futures import wait
        from acs_team import autonomous_planner, cli, config, worktree_manager
        from acs_team.daemon_dispatch import DaemonDispatcher
        monkeypatch.setattr(autonomous_planner,'STATE_DIR',tmp_path)
        monkeypatch.setattr(config,'STATE_DIR',tmp_path)
        monkeypatch.setattr(worktree_manager,'WORKTREES_DIR',tmp_path/'legacy-unused-worktrees')
        # Substitute only provider/role binding and disposable host state; actual
        # CLI, autonomous planner route, daemon and controller methods execute.
        monkeypatch.setattr(autonomous_planner,'WorkerRegistry',Registry)
        monkeypatch.setattr(cli,'WorkerRegistry',Registry)
        monkeypatch.setattr(cli,'DatabaseManager',lambda:db)
        monkeypatch.setattr(autonomous_planner,'AIPlanner',lambda:object())
        (tmp_path/'evidence.key').write_text(key)
        (tmp_path/'evidence.key').chmod(0o600)
        def bound_runner(self):
            self.planner=ProviderTeamPlanner(workers['codex-primary'])
            return factory(self.db)
        monkeypatch.setattr(TeamMissionController,'_runner',bound_runner)
        if route=='cli':
            cli.cmd_natural_language_mission(Namespace(mission=goal,repo=str(repo),worker='auto',
                bg=False,fg_internal='team-e2e',test_cmd=None,risk='low',dry_run=False))
        else:
            monkeypatch.setenv('ACS_ENABLE_DAEMON_EXECUTION','1')
            monkeypatch.setenv('ACS_ENABLE_SUPERVISION','1')
            db.create_mission('team-e2e',repo.name,str(repo),goal,state='QUEUED',prompt=goal)
            dispatcher=DaemonDispatcher(db)
            try:
                assert dispatcher.tick()==1
                done,_=wait(list(dispatcher.active),timeout=30)
                assert len(done)==1
                assert next(iter(done)).result()['status']=='COMPLETED'
            finally:
                dispatcher.close()
        mission=db.get_mission('team-e2e')
        result={'status':mission['state'],'label':'CLOUD_SIMULATED',
                'review_package':str(next((tmp_path/'reviews').iterdir()))}
    if route=='escalate':
        assert result['status']=='BLOCKED' and result['label']=='CLOUD_SIMULATED'
        assert db.get_mission('team-e2e')['state']=='BLOCKED'
        assert git('rev-parse','HEAD')==before and git('status','--porcelain')==''
        escalation=json.loads((Path(result['escalation_package'])/'escalation.json').read_bytes())['data']
        assert len(escalation['failed_attempts'])==2
        assert 'different workers failed at the same stage' in escalation['triggers']
        assert any(e['action']=='REVIEW_FINDING' for e in db.get_audit_trail('team-e2e'))
        assert all(row['state']=='FAILED' for row in CoordinationStore(db).tasks('team-e2e'))
        from acs_team.review_workflow import ReviewWorkflow
        monkeypatch.setenv('ACS_ENABLE_REVIEW_EXECUTION','1')
        accepted=ReviewWorkflow(db,tmp_path/'artifacts',key).apply('team-e2e',json.dumps({
            'verdict':'REPLAN','findings':[{'severity':'HIGH','requirement_id':'t0',
              'description':'Repeat original implementations with independent review','suggested_action':'Replan both tasks and verify original criteria'}]}))
        corrected=controller.replan_from_review('team-e2e',accepted['round'])
        assert corrected['status']=='COMPLETED',corrected
        assert db.get_mission('team-e2e')['state']=='BLOCKED'
        assert git('rev-parse','HEAD')==before and git('status','--porcelain')==''
        assert json.loads(Path(corrected['evidence_ref']).read_bytes())['test_results']['independent_contracts']['counts']['passed']==2
        return
    assert result['status']=='COMPLETED', result
    if route=='direct':
        assert len(result['worktree_cleanup'])==3
        for row in CoordinationStore(db).tasks('team-e2e'):
            accepted=json.loads(row['result'])['worker_completion']
            assert not Path(accepted['worktree']).exists()
            assert git('rev-parse',accepted['branch'])==accepted['commit']
            assert Path(accepted['worker_evidence_ref']).is_file()
    assert result['label']=='CLOUD_SIMULATED'
    assert git('rev-parse','HEAD')==before
    assert git('status','--porcelain')==''
    assert db.get_mission('team-e2e')['state']=='COMPLETED'
    expected_tasks=3 if route=='dependent' else 2
    assert len(runtime_snapshot(db)['tasks'])==expected_tasks
    assert runtime_snapshot(db)['missions'][0]['guardian']=='APPROVED'
    assert runtime_snapshot(db)['resources']['controller_peak_rss_bytes']>0
    package=json.loads((Path(result['review_package'])/'final_review.json').read_text())['data']
    assert package['evidence_verified'] is True
    assert len(package['acceptance_criteria'])==expected_tasks
    if route!='recover':
        assert {c[0] for c in calls}=={'planner','tester','implementer','reviewer'}
        assert len({c[2] for c in calls})==len(calls)
        assert len({session['session_id'] for session in roles.sessions})==expected_tasks*2
    with db.connection() as con:
        samples=[json.loads(r[0]) for r in con.execute('SELECT sample FROM worker_samples WHERE mission="team-e2e"')]
        assert len(samples)==2 and all(sample['label']=='CLOUD_SIMULATED' and sample['runtime']>0 for sample in samples)
    assert all(item['status']=='PASS' and item['label']=='CLOUD_SIMULATED' for item in package['requirement_evidence_matrix'])
    assert lessons.get(repo.name,lesson).status=='Verified'
    assert len(CoordinationStore(db).messages('team-e2e'))==expected_tasks
    mission=db.get_mission('team-e2e')
    evidence=json.loads(Path(mission['evidence_ref']).read_bytes())
    assert evidence['task_id'] is None and evidence['commit_sha']==mission['commit_sha']
    assert len(evidence['test_results']['declared_commands'])==expected_tasks
    assert evidence['test_results']['independent_contracts']['counts']['passed']==expected_tasks
    completion=json.loads((Path(result['review_package'])/'completion.json').read_bytes())
    assert completion['label']=='CLOUD_SIMULATED' and completion['guardian']=='APPROVED'
    assert len(completion['local_verification_required'])==3
    audits=db.get_audit_trail('team-e2e')
    assert any(e['action']=='CONTEXT_SELECTED' for e in audits)
    assert any(e['action']=='EXECUTION_PROFILE' for e in audits)
    if route=='review':
        from acs_team.review_workflow import ReviewWorkflow
        monkeypatch.setenv('ACS_ENABLE_REVIEW_EXECUTION','1')
        workflow=ReviewWorkflow(db,tmp_path/'artifacts',key)
        raw=json.dumps({'verdict':'FIX_REQUIRED','findings':[{'severity':'HIGH','requirement_id':'t0',
            'description':'Gamma returns 42','suggested_action':'Add gamma without breaking alpha and beta'}]})
        accepted=workflow.apply('team-e2e',raw)
        correction=controller.replan_from_review('team-e2e',accepted['round'])
        assert correction['status']=='COMPLETED',correction
        assert correction['mission_id']!='team-e2e'
        assert git('rev-parse','HEAD')==before
        child=db.get_mission(correction['mission_id'])
        assert git('merge-base','--is-ancestor',db.get_mission('team-e2e')['commit_sha'],child['commit_sha'])==''
        assert git('show',child['commit_sha']+':gamma.py')=='def value(): return 42'
        assert controller.replan_from_review('team-e2e',accepted['round'])['already_executed'] is True
        assert workflow.apply('team-e2e',raw)['status']=='BLOCKED'
        from acs_team.team_recovery import TeamRecovery
        first=json.loads(CoordinationStore(db).tasks('team-e2e')[0]['result'])['worker_completion']
        retained=Path(first['worktree'])/'retain-user-data.txt'
        retained.write_text('Uncommitted work must remain')
        with pytest.raises(PermissionError,match='dirty'):
            TeamRecovery(db,tmp_path/'worktrees',key).cleanup_accepted_workers('team-e2e',repo)
        assert retained.read_text()=='Uncommitted work must remain'
