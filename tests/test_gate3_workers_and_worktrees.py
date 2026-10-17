"""Gate 3 Verification Suite: Workers, Worktree Isolation, Scope Reservation, and Integration."""

import os
import shutil
import subprocess
from pathlib import Path
import pytest

from acs_team.scope_and_integration import (
    IntegrationManager,
    MergeConflictError,
    ResourceManager,
    ScopeConflictError,
    ScopeManager,
)
from acs_team.worker_adapters import (
    AGYGoogleAWorker,
    AGYGoogleBWorker,
    CodexPrimaryWorker,
    WorkerRegistry,
    WorkerUnverifiedError,
)
from acs_team.worktree_manager import DiskSpaceCircuitBreakerError, WorktreeManager


@pytest.fixture
def test_git_repo(tmp_path):
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "audit@test.local"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Audit Test"], cwd=str(repo), check=True)
    (repo / "README.md").write_text("# Test Repo\nInitial commit\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo), check=True)
    return repo


def test_worker_registry_and_banned_flags(tmp_path):
    registry = WorkerRegistry()
    available = registry.list_available_workers()
    assert "codex-primary" in available
    assert "agy-google-a" in available
    assert "agy-google-b" in available  # Authenticated and verified

    # An unverified worker must fail-closed if invoked
    unverified_b = AGYGoogleBWorker(agy_b_home=Path("/tmp/nonexistent-home"))
    assert not unverified_b.is_available()
    with pytest.raises(WorkerUnverifiedError):
        unverified_b.execute_task("t1", "goal", "inst", tmp_path)

    # Codex worker must reject banned bypass flags
    codex = registry.get_worker("codex-primary")
    with pytest.raises(PermissionError) as exc_info:
        codex.execute_task(
            "t-danger",
            "Do dangerous stuff",
            "Run with --dangerously-bypass-approvals-and-sandbox",
            tmp_path,
        )
    assert "Prohibited flag" in str(exc_info.value)

    # AGY worker must reject banned bypass flags
    agy = registry.get_worker("agy-google-a")
    with pytest.raises(PermissionError) as exc_info2:
        agy.execute_task(
            "t-danger-agy",
            "Do dangerous stuff",
            "Run with --bypass-sandbox",
            tmp_path,
        )
    assert "Prohibited flag" in str(exc_info2.value)


def test_worktree_isolation_and_lifecycle(test_git_repo, tmp_path):
    wt_dir = tmp_path / "worktrees"
    wm = WorktreeManager(worktrees_dir=wt_dir, min_free_gb=1.0)

    # 1. Create worktree
    wt_path = wm.create_worktree(test_git_repo, "m-001", "task-1")
    assert wt_path.exists()
    assert (wt_path / "README.md").exists()

    # Verify branch was created
    branch_res = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=str(wt_path),
        capture_output=True,
        text=True,
        check=True,
    )
    assert branch_res.stdout.strip() == "acsai/worker/m-001/task-1"

    # 2. Garbage collection policy
    # Failed task retains worktree for inspection
    assert wm.garbage_collect_worktree(test_git_repo, wt_path, "FAILED") is False
    assert wt_path.exists()

    # Completed task removes worktree cleanly
    assert wm.garbage_collect_worktree(test_git_repo, wt_path, "COMPLETED") is True
    assert not wt_path.exists()


def test_disk_space_circuit_breaker(tmp_path):
    # Set threshold artificially high (1,000,000 GB) to trigger circuit breaker
    wm = WorktreeManager(worktrees_dir=tmp_path / "wt", min_free_gb=1000000.0)
    with pytest.raises(DiskSpaceCircuitBreakerError) as exc_info:
        wm.assert_disk_space_available()
    assert "Disk Space Circuit Breaker triggered" in str(exc_info.value)


def test_scope_reservation_and_diff_verification(test_git_repo, tmp_path):
    sm = ScopeManager()

    # 1. Reserve scope for task 1
    sm.reserve_scope("m-100", "t-1", ["src/core.py", "tests/test_core.py"])

    # 2. Overlapping reservation for task 2 in same mission must raise ScopeConflictError
    with pytest.raises(ScopeConflictError):
        sm.reserve_scope("m-100", "t-2", ["src/core.py", "docs/readme.md"])

    # 3. Non-overlapping reservation succeeds
    sm.reserve_scope("m-100", "t-3", ["src/auth.py"])

    # 4. Releasing scope frees the reservation
    sm.release_scope("m-100", "t-1")
    sm.reserve_scope("m-100", "t-2", ["src/core.py", "docs/readme.md"])

    # 5. Diff verification
    wt_dir = tmp_path / "wt"
    wm = WorktreeManager(worktrees_dir=wt_dir, min_free_gb=1.0)
    wt = wm.create_worktree(test_git_repo, "m-100", "t-2")

    # Modify an unexpected file
    (wt / "unexpected.py").write_text("print('rogue change')")
    is_valid, actual, unexpected = sm.verify_diff_against_scope(wt, ["docs/readme.md"])
    assert is_valid is False
    assert "unexpected.py" in unexpected


def test_integration_manager_merge_and_conflict_handling(test_git_repo, tmp_path):
    im = IntegrationManager(test_git_repo)
    wt_dir = tmp_path / "wt_integ"
    wm = WorktreeManager(worktrees_dir=wt_dir, min_free_gb=1.0)

    # Create integration branch
    integ_branch = im.ensure_integration_branch("m-200")
    assert integ_branch == "acsai/mission/m-200"

    # Create worker 1 change
    wt1 = wm.create_worktree(test_git_repo, "m-200", "task-a")
    (wt1 / "file_a.py").write_text("def a(): return 1\n")
    sha1 = im.commit_worktree_changes(wt1, "Implement file a")
    assert len(sha1) == 40

    # Merge worker 1 into integration branch
    res1 = im.merge_task_branch(integ_branch, "acsai/worker/m-200/task-a")
    assert res1["success"] is True
    assert len(res1["integrated_commit_sha"]) == 40

    # Create conflicting worker change on same line in same file
    wt2 = wm.create_worktree(test_git_repo, "m-200", "task-conflict", base_ref=res1["integrated_commit_sha"] + "~1")
    (wt2 / "file_a.py").write_text("def a(): return 999\n")
    im.commit_worktree_changes(wt2, "Conflicting commit")

    # Attempt merge: must raise MergeConflictError and abort cleanly
    with pytest.raises(MergeConflictError):
        im.merge_task_branch(integ_branch, "acsai/worker/m-200/task-conflict")

    # Verify repo is clean (merge was aborted)
    status_res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(test_git_repo),
        capture_output=True,
        text=True,
    )
    assert status_res.stdout.strip() == ""
