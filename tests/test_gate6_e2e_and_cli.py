"""Tests for Gate 6: End-to-End (E2E) Multi-Agent Workflow, CLI subcommands, and TUI instantiation.
"""

import os
import shutil
import subprocess
import tempfile
import pytest
from pathlib import Path

from acs_team.config import AUTH_TOKEN_PATH
from acs_team.db import DatabaseManager
from acs_team.evidence import EvidenceEngine
from acs_team.guardian import Guardian
from acs_team.human_approval import HumanApprovalGate, RiskLevel
from acs_team.quality import QualityEngine
from acs_team.scope_and_integration import IntegrationManager, ScopeManager
from acs_team.state_machine import MissionState, StateMachine
from acs_team.tui import ACSControlCenterApp
from acs_team.worktree_manager import WorktreeManager


@pytest.fixture
def temp_workspace():
    base_dir = tempfile.mkdtemp(prefix="acs_e2e_test_")
    repo_dir = Path(base_dir) / "test-repo"
    repo_dir.mkdir(parents=True)

    # Initialize a git repo with an initial commit
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)

    test_file = repo_dir / "app.py"
    test_file.write_text("def hello():\n    return 'initial'\n")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)

    db_path = Path(base_dir) / "state.db"
    db = DatabaseManager(db_path)

    wt_dir = Path(base_dir) / "worktrees"
    wt_dir.mkdir()

    yield {
        "base_dir": base_dir,
        "repo_dir": repo_dir,
        "db": db,
        "wt_dir": wt_dir,
    }

    db.close()
    shutil.rmtree(base_dir, ignore_errors=True)


def test_e2e_autonomous_lifecycle(temp_workspace):
    db: DatabaseManager = temp_workspace["db"]
    repo_dir: Path = temp_workspace["repo_dir"]
    wt_dir: Path = temp_workspace["wt_dir"]

    auth_token = "e2e-secret-token-xyz"
    mission_id = "m-e2e-001"
    task_id = "t-001"
    project_id = "e2e-project"

    # 1. Create Mission in DB & State Machine
    db.create_mission(
        mission_id=mission_id,
        project_id=project_id,
        repository_path=str(repo_dir),
        goal="Implement feature foo",
    )
    sm = StateMachine(db)

    # Advance state: CREATED -> QUEUED -> PLANNING -> READY -> RUNNING
    sm.transition(mission_id, MissionState.QUEUED)
    sm.transition(mission_id, MissionState.PLANNING)
    sm.transition(mission_id, MissionState.READY)
    sm.transition(mission_id, MissionState.RUNNING)

    # 2. Worktree Allocation & Isolation
    wt_mgr = WorktreeManager(worktrees_dir=wt_dir, min_free_gb=1.0)
    branch_name = f"acsai/worker/{mission_id}/{task_id}"
    worktree_path = wt_mgr.create_worktree(repo_path=repo_dir, mission_id=mission_id, task_id=task_id)
    assert worktree_path.is_dir()

    # 3. Worker Action (Simulated safe code change)
    file_to_change = worktree_path / "app.py"
    file_to_change.write_text("def hello():\n    return 'updated'\n\ndef add(a, b):\n    return a + b\n")

    subprocess.run(["git", "add", "app.py"], cwd=str(worktree_path), check=True)
    subprocess.run(["git", "commit", "-m", "Implement add function"], cwd=str(worktree_path), check=True)

    worker_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(worktree_path), capture_output=True, text=True, check=True
    ).stdout.strip()

    # 4. Scope & Integration Manager Merge to Mission Branch
    scope_mgr = ScopeManager()
    scope_mgr.reserve_scope(mission_id, task_id, ["app.py"])

    int_mgr = IntegrationManager(repo_dir)
    integ_branch = int_mgr.ensure_integration_branch(mission_id)
    merge_result = int_mgr.merge_task_branch(
        integration_branch=integ_branch,
        worker_branch=branch_name,
    )
    merge_sha = merge_result["integrated_commit_sha"]
    assert len(merge_sha) == 40

    # Advance state: RUNNING -> INTEGRATING -> TESTING
    sm.transition(mission_id, MissionState.INTEGRATING, commit_sha=merge_sha)
    sm.transition(mission_id, MissionState.TESTING)

    # 5. Evidence Generation
    evidence_eng = EvidenceEngine(auth_token)
    evidence = evidence_eng.create_evidence(
        mission_id=mission_id,
        task_id=task_id,
        commit_sha=merge_sha,
        test_results={"executed": False, "passed": True},
        diff_summary={"diff_text": "+ def add(a, b):\n+     return a + b\n"},
    )
    ev_dict = evidence.to_dict()

    # Advance state: TESTING -> REVIEWING
    sm.transition(mission_id, MissionState.REVIEWING)

    # 6. Guardian Gatekeeper Evaluation
    guardian = Guardian(db, auth_token=auth_token, quality_threshold=0.85)
    target_mission_branch = f"acsai/mission/{mission_id}"
    verdict = guardian.evaluate(
        mission_id=mission_id,
        repository_path=repo_dir,
        worktree_path=worktree_path,
        target_branch=target_mission_branch,
        commit_sha=merge_sha,
        evidence_dict=ev_dict,
        changed_files=["app.py"],
    )

    assert verdict.approved is True
    assert verdict.quality_score >= 0.85
    assert len(verdict.veto_reasons) == 0

    # Advance state: REVIEWING -> COMPLETED
    final_mission = sm.transition(
        mission_id,
        MissionState.COMPLETED,
        quality_score=verdict.quality_score,
        review_status="APPROVED",
    )
    assert final_mission["state"] == MissionState.COMPLETED.value

    # 7. Cleanup worktree
    wt_mgr.remove_worktree(repo_path=repo_dir, worktree_path=worktree_path)
    assert not worktree_path.exists()


def test_cli_subcommands():
    venv_py = "/home/khoi/.local/share/acs-orchestrator/venv/bin/python3"
    
    # 1. Test acsai status
    res_status = subprocess.run(
        [venv_py, "-m", "acs_team.cli", "status"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ACS AI V2 — PLATFORM & MULTI-AGENT TEAM STATUS" in res_status.stdout
    assert "codex-primary" in res_status.stdout
    assert "agy-google-a" in res_status.stdout
    assert "agy-google-b" in res_status.stdout

    # 2. Test acsai worker
    res_worker = subprocess.run(
        [venv_py, "-m", "acs_team.cli", "worker"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "codex-primary" in res_worker.stdout
    assert "agy-google-a" in res_worker.stdout
    assert "agy-google-b" in res_worker.stdout
    assert "READY" in res_worker.stdout

    # 3. Test acsai memory search
    res_mem = subprocess.run(
        [venv_py, "-m", "acs_team.cli", "memory", "WAL"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Found" in res_mem.stdout

    # 4. Test acsai approval list
    res_appr = subprocess.run(
        [venv_py, "-m", "acs_team.cli", "approval", "list"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Pending Human Approvals" in res_appr.stdout


def test_tui_app_instantiation(temp_workspace):
    db = temp_workspace["db"]
    app = ACSControlCenterApp(db)
    assert "Control Center" in app.title and "ACS AI V2" in app.title
    assert app.memory_engine is not None

    assert app.approval_gate is not None
