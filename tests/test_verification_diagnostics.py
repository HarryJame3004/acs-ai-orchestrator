"""Failed verifier evidence survives exception unwinding and SQLite reopening."""
import json
from pathlib import Path

import pytest

from acs_team.coordination import CoordinationStore
from acs_team.db import DatabaseManager
from acs_team.evidence import EvidenceEngine
from acs_team.team_runner import IndependentTester, TeamRunner
from acs_team.worktree_manager import WorktreeManager


@pytest.mark.simulated
@pytest.mark.parametrize('raises', [False, True])
def test_failed_verification_retains_private_signed_cause(tmp_path, raises):
    db = DatabaseManager(tmp_path / 'state.db')
    calls = []
    failure = {'executed': True, 'passed': False, 'exit_code': 125,
               'reason': 'completed', 'output': 'worker cleanup failed; token=fixture-sensitive',
               'counts': {'passed': 2, 'failed': 1}}

    def verify(*args):
        calls.append(args)
        if raises:
            raise RuntimeError('controlled verifier exception')
        return failure

    runner = TeamRunner(CoordinationStore(db), {}, IndependentTester('tester', lambda *_: {}),
                        {'reviewer': lambda *_: None}, WorktreeManager(tmp_path / 'worktrees'),
                        tmp_path / 'artifacts', 'fixture-diagnostic-signing', verification_runner=verify)
    runner._mission_id = 'diagnostic'
    if raises:
        with pytest.raises(RuntimeError, match='controlled verifier exception'):
            runner.verify(['pytest', '-q'], tmp_path)
    else:
        result = runner.verify(['pytest', '-q'], tmp_path)
        assert result == {**failure, 'label': 'CLOUD_SIMULATED'}
    assert len(calls) == 1  # A diagnostic must never silently retry execution.
    events = DatabaseManager(tmp_path / 'state.db').get_audit_trail('diagnostic')
    event = next(e for e in events if e['action'] == 'VERIFICATION_RESULT')['details']
    assert event['passed'] is False
    path = Path(event['evidence_ref'])
    assert path.stat().st_mode & 0o077 == 0
    evidence = json.loads(path.read_text())
    assert EvidenceEngine('fixture-diagnostic-signing').verify_evidence(evidence, '0' * 40)
    assert evidence['test_results']['executed'] == (not raises)
    if raises:
        assert evidence['test_results']['exception_type'] == 'RuntimeError'
    else:
        assert event['exit_code'] == 125 and event['counts']['failed'] == 1
        assert 'fixture-sensitive' not in path.read_text()
        assert '[REDACTED]' in evidence['test_results']['output']
