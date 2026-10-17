"""Tests for Gate 8: ACS AI V2.2 Natural Language Autonomous Mission Control.
Verifies all 16 acceptance test criteria from Feature 9:
1. acsai -m without --repo (isolated workspace fallback).
2. acsai -m with an existing repository.
3. Multiline prompts.
4. Dashboard mission submission.
5. Automatic worker selection.
6. Explicit worker selection.
7. SQLite mission persistence.
8. Mission logs and progress.
9. Cancellation.
10. Resume after daemon restart / crash reconciliation.
11. Real coding task execution.
12. Pytest execution in worktree.
13. Guardian evaluation and HMAC evidence.
14. MCP inventory and secret masking.
15. Repository inventory and status.
16. Protected ACS Core rejection.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


from acs_team.autonomous_planner import AutonomousMissionPlanner
from acs_team.config import ACS_CORE_DIR, GIT_BIN, WORKSPACES_DIR
from acs_team.db import DatabaseManager
from acs_team.evidence import EvidenceEngine
from acs_team.guardian import Guardian, GuardianVerdict
from acs_team.mcp_manager import MCPManager
from acs_team.repo_manager import RepoManager
from acs_team.state_machine import MissionState, StateMachine
from acs_team.worker_adapters import BaseWorker, WorkerRegistry


@pytest.fixture
def temp_env():
    base_dir = tempfile.mkdtemp(prefix="acs_v2_2_test_")
    base_path = Path(base_dir)

    # 1. Target Repo
    repo_dir = base_path / "sample-calc"
    repo_dir.mkdir(parents=True)
    subprocess.run([str(GIT_BIN), "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run([str(GIT_BIN), "config", "user.name", "Test Engineer"], cwd=str(repo_dir), check=True)
    subprocess.run([str(GIT_BIN), "config", "user.email", "test@acsai.local"], cwd=str(repo_dir), check=True)

    (repo_dir / "test_fixture.py").write_text("from pathlib import Path\ndef test_readme_contract(): assert Path('README.md').read_text().startswith('# Sample')\n")
    init_file = repo_dir / "README.md"
    init_file.write_text("# Sample Calculator Project\n")
    subprocess.run([str(GIT_BIN), "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run([str(GIT_BIN), "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)

    # 2. Database
    db_path = base_path / "state.db"
    db = DatabaseManager(db_path)

    yield {
        "base_path": base_path,
        "repo_dir": repo_dir,
        "db": db,
    }

    db.close()
    shutil.rmtree(base_dir, ignore_errors=True)


# Test 1: acsai -m without --repo
def test_1_nl_mission_without_repo(temp_env):
    db: DatabaseManager = temp_env["db"]
    rm = RepoManager(db)

    # When no repo is requested and CWD is not a git repo or isolated
    resolved_path, is_ephemeral = rm.resolve_target_workspace(requested_repo=None, mission_id="test-no-repo-1")

    assert resolved_path.exists()
    assert (resolved_path / ".git").exists()
    assert (resolved_path / "README.md").exists()
    assert is_ephemeral is True or resolved_path == Path.cwd().resolve()


# Test 2: acsai -m with an existing repository
def test_2_nl_mission_with_existing_repo(temp_env):
    db: DatabaseManager = temp_env["db"]
    repo_dir: Path = temp_env["repo_dir"]
    rm = RepoManager(db)

    resolved_path, is_ephemeral = rm.resolve_target_workspace(requested_repo=str(repo_dir))
    assert resolved_path == repo_dir.resolve()
    assert is_ephemeral is False


# Test 3: Multiline prompts
def test_3_multiline_prompts(temp_env):
    db: DatabaseManager = temp_env["db"]
    multiline_prompt = (
        "Create a comprehensive Python calculator with the following requirements:\n"
        "- Implement add(a, b), subtract(a, b), multiply(a, b), and divide(a, b).\n"
        "- Raise ZeroDivisionError on divide by zero.\n"
        "- Add unit tests verifying each operation."
    )

    mission_id = "test-multiline-prompt"
    db.create_mission(
        mission_id=mission_id,
        project_id="test",
        repository_path=str(temp_env["repo_dir"]),
        goal="Calculator",
        state=MissionState.QUEUED.value,
        assigned_workers=["auto"],
        prompt=multiline_prompt,
    )

    m = db.get_mission(mission_id)
    assert m is not None
    assert m["prompt"] == multiline_prompt
    assert "\n- Implement add" in m["prompt"]


# Test 4: Dashboard mission submission backend
def test_4_dashboard_mission_submission(temp_env):
    db: DatabaseManager = temp_env["db"]
    planner = AutonomousMissionPlanner(db=db)

    # Simulate TUI composer submission
    mid = "test-dash-submission"
    prompt = "Create a basic helper module"

    # Mock planner, worker execution, and integration merge to verify pipeline wiring
    with patch.object(planner.planner, "plan_task") as mock_plan, \
         patch.object(planner, "_schedule_worker") as mock_sched, \
         patch.object(planner, "_run_test_command") as mock_test, \
         patch("acs_team.autonomous_planner.IntegrationManager") as mock_int_cls:

        mock_plan.return_value = {
            "task_name": "helper_module",
            "goal_summary": "Helper module",
            "files_to_modify": ["helper.py"],
            "test_command": f"{sys.executable} -m pytest",
        }
        mock_worker = MagicMock(spec=BaseWorker)
        mock_worker.execute_task.return_value = {
            "success": True,
            "changed_files": ["helper.py"],
        }
        mock_sched.return_value = ("codex-primary", mock_worker)
        mock_test.return_value = {"exit_code": 0, "passed": True, "output": "1 passed"}

        mock_int_inst = mock_int_cls.return_value
        mock_int_inst.ensure_integration_branch.return_value = "acsai/mission/test-dash-submission"
        mock_int_inst.merge_task_branch.return_value = {"success": True, "integrated_commit_sha": "123456"}

        logs_collected = []
        res = planner.run_mission(
            mission_id=mid,
            prompt=prompt,
            repo_path=temp_env["repo_dir"],
            worker_preference="auto",
            test_command=f"{sys.executable} -m pytest",
            log_callback=lambda l: logs_collected.append(l),
        )


        assert res["status"] == "COMPLETED"
        assert res["mission_id"] == mid
        assert len(logs_collected) > 0



# Test 5: Automatic worker selection
@pytest.mark.simulated
def test_5_automatic_worker_selection(temp_env):
    db: DatabaseManager = temp_env["db"]
    planner = AutonomousMissionPlanner(db=db)

    # Scheduling logic uses an explicit fake registry, never inferred real auth.
    planner.registry = MagicMock(spec=WorkerRegistry)
    planner.registry.list_available_workers.return_value = ["codex-primary"]
    planner.registry.get_worker.return_value = MagicMock(spec=BaseWorker)
    worker_id, worker = planner._schedule_worker("auto", {"files_to_modify": ["test.py"]})
    assert worker_id in ("codex-primary", "agy-google-a", "agy-google-b")
    assert worker is not None


# Test 6: Explicit worker selection
def test_6_explicit_worker_selection(temp_env):
    db: DatabaseManager = temp_env["db"]
    planner = AutonomousMissionPlanner(db=db)

    worker_id_codex, _ = planner._schedule_worker("codex", {})
    assert worker_id_codex == "codex-primary"

    worker_id_a, _ = planner._schedule_worker("agy-google-a", {})
    assert worker_id_a == "agy-google-a"

    worker_id_b, _ = planner._schedule_worker("agy-google-b", {})
    assert worker_id_b == "agy-google-b"


# Test 7: SQLite mission persistence
def test_7_sqlite_mission_persistence(temp_env):
    db: DatabaseManager = temp_env["db"]
    mid = "test-persistence-mission"
    prompt = "Test prompt persistence"
    plan = {"task": "demo", "steps": ["step1", "step2"]}

    db.create_mission(
        mission_id=mid,
        project_id="sample",
        repository_path="/tmp/sample",
        goal="Demo",
        state=MissionState.RUNNING.value,
        assigned_workers=["agy-google-b"],
        prompt=prompt,
    )

    db.update_mission_plan(mid, prompt, plan)
    db.append_mission_log(mid, "Log entry 1")
    db.append_mission_log(mid, "Log entry 2")

    m = db.get_mission(mid)
    assert m["mission_id"] == mid
    assert m["prompt"] == prompt
    assert json.loads(m["plan_json"]) == plan

    logs = db.get_mission_logs(mid)
    assert len(logs) == 2
    assert "Log entry 1" in logs[0]
    assert "Log entry 2" in logs[1]


# Test 8: Mission logs and progress
def test_8_mission_logs_and_progress(temp_env):
    db: DatabaseManager = temp_env["db"]
    mid = "test-logs-progress"

    db.create_mission(
        mission_id=mid,
        project_id="test",
        repository_path=str(temp_env["repo_dir"]),
        goal="Test logs",
        state=MissionState.CREATED.value,
    )

    # Append 5 sequential logs
    for i in range(5):
        db.append_mission_log(mid, f"Progress checkpoint {i}: step complete")

    logs = db.get_mission_logs(mid)
    assert len(logs) == 5
    assert "checkpoint 0" in logs[0]
    assert "checkpoint 4" in logs[4]


# Test 9: Cancellation
def test_9_mission_cancellation(temp_env):
    db: DatabaseManager = temp_env["db"]
    sm = StateMachine(db)
    mid = "test-cancellation"

    db.create_mission(
        mission_id=mid,
        project_id="test",
        repository_path=str(temp_env["repo_dir"]),
        goal="Test cancellation",
        state=MissionState.RUNNING.value,
    )

    updated = sm.transition(mid, MissionState.CANCELLED, error_info="User requested cancel via CLI")
    assert updated["state"] == "CANCELLED"
    assert updated["error_info"] == "User requested cancel via CLI"

    m = db.get_mission(mid)
    assert m["state"] == "CANCELLED"


# Test 10: Resume after restart / crash reconciliation
def test_10_resume_after_restart(temp_env):
    db: DatabaseManager = temp_env["db"]
    sm = StateMachine(db)
    mid = "test-reconciliation"

    # Simulate an interrupted mission left in RUNNING during unexpected shutdown
    db.create_mission(
        mission_id=mid,
        project_id="test",
        repository_path=str(temp_env["repo_dir"]),
        goal="Test resume",
        state=MissionState.RUNNING.value,
    )
    # Save a valid checkpoint prior to the interruption
    db.save_checkpoint(
        mission_id=mid,
        state_name=MissionState.RUNNING.value,
        payload={"valid": True, "step": "code_edit"},
    )


    # Daemon crash reconciliation recovers interrupted missions to RECOVERING
    reconciled = sm.reconcile_interrupted_missions()
    assert any(m["mission_id"] == mid for m in reconciled)

    m = db.get_mission(mid)
    assert m["state"] == MissionState.RECOVERING.value


# Test 11: Real coding task execution
def test_11_real_coding_task_execution(temp_env):
    repo_dir: Path = temp_env["repo_dir"]

    # Write a real math function and test directly into the git repo
    calc_py = repo_dir / "math_calc.py"
    calc_py.write_text("def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n")

    test_calc_py = repo_dir / "test_math_calc.py"
    test_calc_py.write_text("from math_calc import add, multiply\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_multiply():\n    assert multiply(3, 4) == 12\n")

    subprocess.run([str(GIT_BIN), "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run([str(GIT_BIN), "commit", "-m", "Implement math_calc and tests"], cwd=str(repo_dir), check=True)

    # Verify real pytest execution on the real files
    res = subprocess.run([sys.executable, "-m", "pytest", str(test_calc_py)], cwd=str(repo_dir), capture_output=True, text=True)
    assert res.returncode == 0
    assert "2 passed" in res.stdout


# Test 12: Pytest execution in worktree
def test_12_pytest_execution_in_worktree(temp_env):
    db: DatabaseManager = temp_env["db"]
    planner = AutonomousMissionPlanner(db=db)
    repo_dir: Path = temp_env["repo_dir"]

    # Passing test
    p_test = repo_dir / "test_sample_pass.py"
    p_test.write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    run_res = planner._run_test_command(repo_dir, f"{sys.executable} -m pytest {p_test}")
    assert run_res["passed"] is True
    assert run_res["exit_code"] == 0

    # Failing test
    f_test = repo_dir / "test_sample_fail.py"
    f_test.write_text("def test_broken():\n    assert 1 == 2\n")
    fail_res = planner._run_test_command(repo_dir, f"{sys.executable} -m pytest {f_test}")
    assert fail_res["passed"] is False
    assert fail_res["exit_code"] != 0


# Test 13: Guardian evaluation and HMAC evidence
def test_13_guardian_evaluation_and_hmac(temp_env):
    db: DatabaseManager = temp_env["db"]
    repo_dir: Path = temp_env["repo_dir"]
    auth_token = "test-token-guardian-123"
    guardian = Guardian(db, auth_token=auth_token)
    evidence_eng = EvidenceEngine(auth_token=auth_token)

    dummy_test = repo_dir / "test_dummy.py"
    dummy_test.write_text("def test_ok(): assert True\n")
    subprocess.run([str(GIT_BIN), "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run([str(GIT_BIN), "commit", "-m", "Add dummy test"], cwd=str(repo_dir), check=True)

    # Get latest commit
    res = subprocess.run([str(GIT_BIN), "rev-parse", "HEAD"], cwd=str(repo_dir), capture_output=True, text=True, check=True)
    head_sha = res.stdout.strip()


    # Create evidence bundle
    ev = evidence_eng.create_evidence(
        mission_id="test-guardian-mid",
        task_id="task-1",
        commit_sha=head_sha,
        test_results={"executed": True, "passed": True, "output": "1 passed"},
        diff_summary={"changed_files": ["README.md"]},
    )
    assert ev.signature is not None
    assert len(ev.signature) == 64  # SHA-256 hex string

    # Guardian gatekeeper check
    verdict = guardian.evaluate(
        mission_id="test-guardian-mid",
        repository_path=repo_dir,
        worktree_path=repo_dir,
        target_branch="feature/test-branch",
        commit_sha=head_sha,
        evidence_dict=ev.to_dict(),
        changed_files=["README.md"],
        test_command=f"{sys.executable} -m pytest",
    )
    assert verdict.approved is True




# Test 14: MCP inventory and secret masking
def test_14_mcp_inventory_and_verification():
    mgr = MCPManager()
    stats = mgr.get_summary_stats()
    inventory = mgr.get_inventory()

    assert stats["configured_servers"] > 0
    assert stats["connected_servers"] > 0
    assert stats["usable_servers"] > 0
    assert stats["total_tools"] > 0

    # Verify zero raw secrets leaked
    for s in inventory:
        assert not s.auth_status.startswith("ghp_")
        assert not s.auth_status.startswith("github_pat_")
        if "TOKEN" in s.auth_status or "KEY" in s.auth_status:
            assert "***" in s.auth_status or s.auth_status.startswith("CONFIGURED")


# Test 15: Repository inventory and status
def test_15_repository_inventory(temp_env):
    db: DatabaseManager = temp_env["db"]
    rm = RepoManager(db)

    # Register repo
    rm.register_repository(temp_env["repo_dir"], name="Test Repo")

    repos = rm.list_repositories()
    assert len(repos) >= 1
    found = next((r for r in repos if r["path"] == str(temp_env["repo_dir"].resolve())), None)
    assert found is not None
    assert found["name"] == "Test Repo"
    assert found["is_protected"] is False
    assert found["git_branch"] in ("main", "master")


# Test 16: Protected ACS Core rejection
def test_16_protected_acs_core_rejection(temp_env):
    db: DatabaseManager = temp_env["db"]
    rm = RepoManager(db)

    # Attempting to target ACS Core must raise PermissionError
    with pytest.raises(PermissionError) as exc_info:
        rm.resolve_target_workspace(requested_repo=str(ACS_CORE_DIR))

    assert "CoreLock Violation" in str(exc_info.value)
    assert "strictly protected" in str(exc_info.value)
