"""Signed fixture evidence must never excuse failed independent re-execution."""
import subprocess

import pytest

from acs_team.benchmarks import fixture_verification
from acs_team.coordination import CoordinationStore
from acs_team.db import DatabaseManager
from acs_team.evidence import EvidenceEngine
from acs_team.guardian import Guardian
from acs_team.quality import QualityEngine
from acs_team.team_runner import IndependentTester, TeamRunner
from acs_team.worktree_manager import WorktreeManager


@pytest.mark.parametrize('result',[{}, {'executed':False,'passed':True},
                                   {'executed':False,'passed':False}])
def test_missing_execution_is_a_veto_even_at_a_low_score_threshold(result):
    report = QualityEngine(threshold=0.1).compute_quality_score(
        result,{'score':1.,'issues':[]},{'score':1.,'veto_reasons':[]},True)
    assert not report.passed_threshold
    assert report.test_score == 0
    assert any('not executed' in reason for reason in report.veto_reasons)


@pytest.mark.simulated
@pytest.mark.parametrize('mode',['exception','not_executed','actual_pytest'])
def test_guardian_reexecutes_with_timeout_and_never_accepts_runner_failure(tmp_path,mode):
    root = tmp_path/'repository'
    root.mkdir()
    def git(*args):
        return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True,text=True).stdout.strip()
    git('init','-b','fixture')
    git('config','user.name','Fixture')
    git('config','user.email','fixture@example.invalid')
    (root/'test_behavior.py').write_text('def test_behavior():\n    assert 6*7 == 42\n')
    git('add','.')
    git('commit','-m','behavior contract')
    sha = git('rev-parse','HEAD')
    db = DatabaseManager(tmp_path/'fixture.db')
    db.create_mission('guardian-regression','fixture',str(root),'Verify behavior')
    calls = []
    def verify(command,workspace,timeout):
        calls.append((command,workspace,timeout))
        if mode=='exception':
            raise TypeError('injected verifier invocation failure')
        if mode=='not_executed':
            return {'executed':False,'passed':False,'exit_code':-1}
        return fixture_verification(command,workspace,timeout)
    runner = TeamRunner(CoordinationStore(db),{},IndependentTester('fixture-tester',lambda *_:{}),
                        {'fixture-reviewer':lambda *_:None},WorktreeManager(tmp_path/'worktrees'),
                        tmp_path/'artifacts','fixture-guardian-regression',verification_runner=verify)
    evidence = EvidenceEngine('fixture-guardian-regression').create_evidence(
        'guardian-regression',None,sha,{'executed':True,'passed':True}, {'diff_text':''}).to_dict()
    verdict = Guardian(db,'fixture-guardian-regression',verification_runner=runner.verify).evaluate(
        'guardian-regression',root,root,'acsai/mission/guardian-regression',sha,evidence,
        ['test_behavior.py'],test_command='pytest -q')
    assert len(calls) == 1 and calls[0][2] == 180
    assert verdict.approved == (mode=='actual_pytest')
    if mode!='actual_pytest':
        assert any('not executed' in reason for reason in verdict.veto_reasons)
    else:
        assert verdict.quality_report.test_score == 1
