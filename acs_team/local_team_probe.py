"""Explicit user-run authenticated team evaluation on a new disposable repository.

Never used by cloud tests to claim real provider readiness. Retains all probe
artifacts for inspection; never targets a user repository or live database.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import time

from .db import DatabaseManager
from .evidence import EvidenceEngine
from .local_verification import LocalCheck, LocalReport
from .provider_workers import ProviderWorker
from .recovery import new_directory
from .schemas import Plan
from .team_missions import TeamMissionController
from .worker_adapters import WorkerRegistry


def run_local_team_probe(destination: Path) -> dict:
    for flag in ['ACS_ENABLE_PROVIDER_CONTRACTS','ACS_ENABLE_COORDINATION','ACS_ENABLE_SUPERVISION']:
        if os.environ.get(flag) != '1':
            raise PermissionError(f'Authenticated team probe requires {flag}=1')
    from .config import PROTECTED_PATHS, STATE_DIR
    if destination.is_symlink():
        raise PermissionError('Probe output may not be a symlink')
    destination = destination.resolve()
    if any(destination == path or path in destination.parents for path in PROTECTED_PATHS):
        raise PermissionError('Protected output location')
    registry = WorkerRegistry()
    expected = {'codex-primary','agy-google-a','agy-google-b'}
    if set(registry.list_available_workers()) != expected:
        raise PermissionError('All three providers require prior real activation; discovery is insufficient')
    for name in expected:
        worker = registry.get_worker(name)
        if not isinstance(worker,ProviderWorker) or worker.runtime.executor is not None:
            raise PermissionError('Simulated providers cannot run authenticated acceptance')
    started = time.monotonic()
    root = new_directory(destination)
    repo = root/'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.run(['git',*args],cwd=repo,check=True,capture_output=True,text=True,timeout=15).stdout.strip()
    git('init','-b','main')
    git('config','user.name','ACS local probe')
    git('config','user.email','acs-probe@example.invalid')
    (repo/'.gitignore').write_text('__pycache__/\n.pytest_cache/\n')
    (repo/'tests').mkdir()
    (repo/'tests/test_acs_local_probe_expected_behavior.py').write_text(
        'def test_required_behavior():\n    import alpha, beta\n    assert alpha.value() == 42\n    assert beta.value() == 42\n')
    git('add','.')
    git('commit','-m','Harmless team probe specification')
    baseline = git('rev-parse','HEAD')
    db = DatabaseManager(root/'state.db')
    key = (STATE_DIR/'evidence.key').read_text().strip()  # Existing activation authority only.
    controller = TeamMissionController(db,registry,evidence_key=key,root=root)
    def validate(plan: Plan):
        if len(plan.tasks) != 2 or {tuple(t.owns) for t in plan.tasks} != {('alpha.py',),('beta.py',)} or any(t.depends_on for t in plan.tasks):
            raise PermissionError('Probe requires exactly two independent narrowly owned module tasks')
        for task in plan.tasks:
            expected_worker = 'agy-google-a' if task.owns==['alpha.py'] else 'agy-google-b'
            if task.worker != expected_worker:
                raise PermissionError('Probe implementation assignments must exercise both isolated AGY profiles')
    result = controller.run_mission('local-team-probe',
        'Create exactly two independent Python implementation tasks: alpha.py with agy-google-a and beta.py with agy-google-b. '
        'Each module exports value() returning integer 42. Own only the respective module. '
        'Preserve baseline tests. Add independent tests under fresh filenames. Run pytest -q. '
        'Return a validated task graph; no deployment, network tools or user repository changes.',repo,plan_validator=validate)
    if result['status'] != 'COMPLETED' or result['label'] != 'LOCAL_VERIFICATION_REQUIRED':
        raise PermissionError('Real coordinated probe did not complete; retained artifacts require review')
    if git('rev-parse','HEAD') != baseline or git('status','--porcelain'):
        raise PermissionError('Probe changed its original checkout')
    evidence = json.loads(Path(result['evidence_ref']).read_bytes())
    if not EvidenceEngine(key).verify_evidence(evidence,result['commit_sha']):
        raise PermissionError('Probe final evidence invalid')
    observed = {e['actor'] for e in db.get_audit_trail('local-team-probe',limit=1000) if e['action']=='PROVIDER_SESSION'}
    if observed != expected:
        raise PermissionError('Probe did not exercise all activated provider identities')
    checks = [LocalCheck(id='multiagent.real_e2e',status='PASS',
        evidence=f"Actual provider-backed controller completed; SHA={result['commit_sha']}; retained evidence={result['evidence_ref']}",
        duration_s=time.monotonic()-started)]
    try:
        source_commit = subprocess.run(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[1],
                                       check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    except (OSError,subprocess.SubprocessError):
        source_commit = 'UNKNOWN'
    return LocalReport(generated_at=datetime.now(timezone.utc).isoformat(),repo_commit=source_commit,
        environment={'os':platform.platform(),'python':platform.python_version(),'probe_root':str(root),
                     'probe_baseline':baseline},
        checks=checks,summary={'pass':1,'fail':0,'skipped':0,'error':0}).model_dump()
