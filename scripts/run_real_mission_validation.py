#!/usr/bin/env python3
"""ACS AI V2.1 Priority 6 Real Mission Validation.
Dispatches a real engineering task to the newly integrated AGY Google B worker,
collects changes in an isolated git worktree, executes tests, generates cryptographically
signed commit-bound evidence, and runs Guardian security verification.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Set up orchestrator import path
ORCHESTRATOR_DIR = Path("/home/khoi/.local/share/acs-orchestrator")
sys.path.insert(0, str(ORCHESTRATOR_DIR))

from acs_team.auth import get_or_create_auth_token
from acs_team.config import STATE_DIR
from acs_team.db import DatabaseManager
from acs_team.evidence import EvidenceEngine
from acs_team.guardian import Guardian
from acs_team.scope_and_integration import IntegrationManager, ScopeManager
from acs_team.state_machine import MissionState, StateMachine
from acs_team.worker_adapters import WorkerRegistry
from acs_team.worktree_manager import WorktreeManager

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("real_mission_validator")


def run_mission():
    repo_dir = Path("/tmp/acs_real_mission_lab")
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    repo_dir.mkdir(parents=True)

    import time
    ts = int(time.time())
    mission_id = f"m-real-audit-p6-{ts}"
    task_id = f"t-math-utils-{ts}"
    project_id = "real-mission-verification"

    logger.info("Step 1: Initializing disposable repository at %s", repo_dir)
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "ACS Orchestrator"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "acs-orchestrator@local"], cwd=str(repo_dir), check=True)

    (repo_dir / "README.md").write_text("# Real Mission Lab\nTest repository for ACS AI V2.1 live verification.\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)

    db_path = STATE_DIR / "acs_ai.db"
    db = DatabaseManager(db_path)
    sm = StateMachine(db)

    logger.info("Step 2: Creating mission %s in state database", mission_id)
    db.create_mission(
        mission_id=mission_id,
        project_id=project_id,
        repository_path=str(repo_dir),
        goal="Generate Python math_lib.py and test_math_lib.py using real AGY Google B worker",
    )
    sm.transition(mission_id, MissionState.QUEUED)
    sm.transition(mission_id, MissionState.PLANNING)
    sm.transition(mission_id, MissionState.READY)
    sm.transition(mission_id, MissionState.RUNNING)

    logger.info("Step 3: Allocating isolated git worktree for worker")
    wt_mgr = WorktreeManager()
    worktree_path = wt_mgr.create_worktree(repo_path=repo_dir, mission_id=mission_id, task_id=task_id)
    worker_branch = f"acsai/worker/{mission_id}/{task_id}"
    logger.info("Worktree active at %s on branch %s", worktree_path, worker_branch)

    logger.info("Step 4: Dispatching real engineering task to 'agy-google-b'")
    registry = WorkerRegistry()
    worker = registry.get_worker("agy-google-b")

    goal = "Create math_lib.py and test_math_lib.py in the repository"
    instructions = (
        "1. Create math_lib.py with two functions:\n"
        "   - factorial(n: int) -> int (returns n! for n >= 0, raises ValueError for n < 0)\n"
        "   - is_prime(n: int) -> bool (returns True if n is prime, False otherwise)\n"
        "2. Create test_math_lib.py with pytest tests verifying factorial(0)=1, factorial(5)=120, "
        "factorial(-1) raises ValueError, is_prime(2)=True, is_prime(4)=False, is_prime(17)=True.\n"
        "3. Only create these two files, no markdown or explanation outside the files."
    )

    dispatch_res = worker.execute_task(
        task_id=task_id,
        goal=goal,
        instructions=instructions,
        worktree_path=worktree_path,
        files_to_modify=["math_lib.py", "test_math_lib.py"],
        timeout_seconds=120.0,
    )

    logger.info("Worker dispatch result: success=%s, changed_files=%s", dispatch_res["success"], dispatch_res["changed_files"])
    if not (worktree_path / "math_lib.py").exists() or not (worktree_path / "test_math_lib.py").exists():
        logger.error("Files not created as expected! Excerpt: %s", dispatch_res.get("stdout_excerpt"))
        raise RuntimeError("Worker failed to create required files")

    logger.info("Step 5: Executing test suite inside worker worktree")
    pytest_bin = str(ORCHESTRATOR_DIR / "venv" / "bin" / "pytest")
    test_run = subprocess.run(
        [pytest_bin, "-v", "test_math_lib.py"],
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
    )
    logger.info("Pytest exit code: %d", test_run.returncode)
    logger.info("Pytest output:\n%s", test_run.stdout)
    assert test_run.returncode == 0, f"Tests failed: {test_run.stdout}\n{test_run.stderr}"

    logger.info("Step 6: Committing verified worker changes")
    subprocess.run(["git", "add", "."], cwd=str(worktree_path), check=True)
    subprocess.run(["git", "commit", "-m", "Implement math_lib and unit tests via AGY Google B"], cwd=str(worktree_path), check=True)

    worker_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(worktree_path), capture_output=True, text=True, check=True
    ).stdout.strip()
    logger.info("Worker commit SHA: %s", worker_commit)

    logger.info("Step 7: Merging worker branch into mission integration branch")
    scope_mgr = ScopeManager()
    scope_mgr.reserve_scope(mission_id, task_id, ["math_lib.py", "test_math_lib.py"])

    int_mgr = IntegrationManager(repo_dir)
    integ_branch = int_mgr.ensure_integration_branch(mission_id)
    merge_result = int_mgr.merge_task_branch(
        integration_branch=integ_branch,
        worker_branch=worker_branch,
    )
    merge_sha = merge_result["integrated_commit_sha"]
    logger.info("Integrated merge commit SHA: %s", merge_sha)

    sm.transition(mission_id, MissionState.INTEGRATING, commit_sha=merge_sha)
    sm.transition(mission_id, MissionState.TESTING)

    logger.info("Step 8: Generating cryptographically signed commit-bound evidence")
    auth_token = get_or_create_auth_token()
    evidence_eng = EvidenceEngine(auth_token)

    diff_output = subprocess.run(
        ["git", "diff", "main..HEAD"], cwd=str(worktree_path), capture_output=True, text=True, check=True
    ).stdout

    evidence = evidence_eng.create_evidence(
        mission_id=mission_id,
        task_id=task_id,
        commit_sha=merge_sha,
        test_results={
            "executed": True,
            "passed": True,
            "exit_code": 0,
            "output": test_run.stdout,
        },
        diff_summary={"diff_text": diff_output},
    )
    ev_dict = evidence.to_dict()
    logger.info("Evidence signature generated: %s (SHA256: %s)", ev_dict["signature"][:16], ev_dict["payload_sha256"][:16])

    sm.transition(mission_id, MissionState.REVIEWING)

    logger.info("Step 9: Running Guardian independent gatekeeper evaluation")
    guardian = Guardian(db, auth_token=auth_token, quality_threshold=0.85)
    target_mission_branch = f"acsai/mission/{mission_id}"

    verdict = guardian.evaluate(
        mission_id=mission_id,
        repository_path=repo_dir,
        worktree_path=worktree_path,
        target_branch=target_mission_branch,
        commit_sha=merge_sha,
        evidence_dict=ev_dict,
        changed_files=["math_lib.py", "test_math_lib.py"],
        test_command=f"{pytest_bin} -v test_math_lib.py",
    )

    logger.info("Guardian Verdict:")
    logger.info("  Approved: %s", verdict.approved)
    logger.info("  Quality Score: %.4f (Threshold: 0.85)", verdict.quality_score)
    logger.info("  Evidence Verified: %s", verdict.evidence_verified)
    logger.info("  Veto Reasons: %s", verdict.veto_reasons)

    assert verdict.approved is True, f"Guardian rejected mission: {verdict.veto_reasons}"
    assert verdict.quality_score >= 0.85, f"Quality score too low: {verdict.quality_score}"

    logger.info("Step 10: Finalizing mission in state machine")
    sm.transition(mission_id, MissionState.COMPLETED)

    # Clean up worktree safely
    wt_mgr.remove_worktree(repo_path=repo_dir, worktree_path=worktree_path, force=True)

    print("\n" + "=" * 60)
    print("✓ REAL MISSION E2E VALIDATION: 100% SUCCESS")
    print(f"- Mission ID:        {mission_id}")
    print(f"- Worker:            agy-google-b (Real Google Account B via agy-b)")
    print(f"- Repository:        {repo_dir}")
    print(f"- Integrated SHA:    {merge_sha}")
    print(f"- Quality Score:     {verdict.quality_score:.4f} / 1.0000")
    print(f"- Evidence Signed:   HMAC-SHA256 bound to commit")
    print(f"- Guardian Verdict:  APPROVED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_mission()
