"""ACS AI V2 Scope Reservation, Diff Verification, Integration Manager, and Resource Semaphore.
Ensures:
1. Scope reservation prevents conflicting parallel dispatches.
2. Diff verification detects undeclared/unexpected file modifications.
3. Integration manager merges worker branches into mission integration branch.
4. Resource manager bounds concurrency on constrained hardware (16 GB RAM).
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import GIT_BIN, MAX_CONCURRENT_WORKERS, WORKTREES_DIR

logger = logging.getLogger("acs_ai.integration")


class ScopeConflictError(ValueError):
    """Raised when two concurrent tasks attempt to reserve overlapping files."""
    pass


class MergeConflictError(RuntimeError):
    """Raised when integration cannot be automatically merged due to git conflicts."""
    pass


class ScopeManager:
    """Manages file scope reservations and verifies actual git diffs against declared boundaries."""

    def __init__(self):
        self._lock = threading.Lock()
        # Maps mission_id -> {task_id: set(file_paths)}
        self._active_reservations: Dict[str, Dict[str, Set[str]]] = {}

    def reserve_scope(
        self,
        mission_id: str,
        task_id: str,
        declared_files: List[str],
    ) -> None:
        """Reserves a set of target files for a task. Raises ScopeConflictError if overlapping."""
        norm_files = {os.path.normpath(f) for f in declared_files if f}
        if not norm_files:
            return

        with self._lock:
            mission_res = self._active_reservations.setdefault(mission_id, {})
            for other_tid, other_files in mission_res.items():
                if other_tid == task_id:
                    continue
                intersection = norm_files.intersection(other_files)
                if intersection:
                    raise ScopeConflictError(
                        f"Scope conflict: Task '{task_id}' targets {intersection} which is already "
                        f"reserved by active task '{other_tid}' in mission '{mission_id}'."
                    )
            mission_res[task_id] = norm_files
            logger.info(f"Scope reserved for task '{task_id}': {norm_files}")

    def release_scope(self, mission_id: str, task_id: str) -> None:
        with self._lock:
            if mission_id in self._active_reservations:
                self._active_reservations[mission_id].pop(task_id, None)

    def verify_diff_against_scope(
        self,
        worktree_path: Path,
        declared_files: List[str],
        base_ref: str = "HEAD",
    ) -> Tuple[bool, List[str], List[str]]:
        """Verifies actual git diff against declared scope.
        Returns: (is_within_scope, actual_modified_files, unexpected_files)
        """
        try:
            # Check unstaged + staged + uncommitted
            cmd = [str(GIT_BIN), "diff", "--name-only", "--no-renames", "-z", base_ref, "--"]
            res = subprocess.run(
                cmd,
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            untracked = subprocess.run([str(GIT_BIN), "ls-files", "--others", "--exclude-standard", "-z"],
                                       cwd=worktree_path, check=True, capture_output=True, text=True)
            generated = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
            new_files = [name for name in untracked.stdout.split("\0") if name and not generated.intersection(Path(name).parts)]
            actual_files = sorted(set(filter(None, res.stdout.split("\0"))) | set(new_files))

            norm_declared = {os.path.normpath(f) for f in declared_files if f}
            unexpected = [f for f in actual_files if f not in norm_declared]

            is_valid = len(unexpected) == 0
            if not is_valid:
                logger.warning(
                    f"Scope violation in {worktree_path}: unexpected files modified: {unexpected}"
                )
            return is_valid, actual_files, unexpected
        except Exception as e:
            logger.error(f"Failed to verify git diff in {worktree_path}: {e}")
            return False, [], [f"Error: {e}"]


class IntegrationManager:
    """Manages integration branch creation, ancestry verification, and merge conflict detection."""

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path)
        self.integration_path: Optional[Path] = None

    def ensure_integration_branch(self, mission_id: str, base_ref: str = "master") -> str:
        """Creates or checks out the dedicated mission integration branch: acsai/mission/{mission_id}."""
        clean_mid = mission_id.replace("/", "_")
        branch_name = f"acsai/mission/{clean_mid}"

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        # Check if branch already exists
        check = subprocess.run(
            [str(GIT_BIN), "rev-parse", "--verify", branch_name],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            env=env,
        )
        if check.returncode != 0:
            # Create branch from base_ref
            res = subprocess.run(
                [str(GIT_BIN), "branch", branch_name, base_ref],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                env=env,
            )
            if res.returncode != 0:
                # If master doesn't exist, try HEAD
                subprocess.run(
                    [str(GIT_BIN), "branch", branch_name, "HEAD"],
                    cwd=str(self.repo_path),
                    capture_output=True,
                    text=True,
                    env=env,
                )
        return branch_name

    def commit_worktree_changes(
        self,
        worktree_path: Path,
        commit_message: str,
        author_name: str = "ACS AI Worker",
        author_email: str = "acsai@local.audit",
    ) -> str:
        """Stages all changes in worktree and commits them. Returns commit SHA."""
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_AUTHOR_NAME"] = author_name
        env["GIT_AUTHOR_EMAIL"] = author_email
        env["GIT_COMMITTER_NAME"] = author_name
        env["GIT_COMMITTER_EMAIL"] = author_email

        subprocess.run([str(GIT_BIN), "add", "."], cwd=str(worktree_path), check=True, env=env)
        res = subprocess.run(
            [str(GIT_BIN), "commit", "-m", commit_message],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            env=env,
        )
        # Get head sha
        sha_res = subprocess.run(
            [str(GIT_BIN), "rev-parse", "HEAD"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            check=True,
        )
        return sha_res.stdout.strip()

    def merge_task_branch(
        self,
        integration_branch: str,
        worker_branch: str,
    ) -> Dict[str, Any]:
        """Merges worker branch into mission integration branch. Detects conflicts cleanly."""
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        if not integration_branch.startswith("acsai/mission/"):
            raise PermissionError("Integration requires a dedicated mission branch")
        if self.integration_path is None:
            WORKTREES_DIR.mkdir(parents=True, exist_ok=True)
            path = Path(tempfile.mkdtemp(prefix="integration-", dir=WORKTREES_DIR))
            path.rmdir()  # Only our just-created empty directory.
            subprocess.run([str(GIT_BIN), "worktree", "add", str(path), integration_branch],
                           cwd=self.repo_path, check=True, capture_output=True)
            self.integration_path = path
        previous = subprocess.run([str(GIT_BIN), "rev-parse", "HEAD"], cwd=self.integration_path,
                                  check=True, capture_output=True, text=True).stdout.strip()

        # Attempt merge with --no-ff
        merge_res = subprocess.run(
            [str(GIT_BIN), "merge", "--no-ff", "-m", f"Merge task {worker_branch} into {integration_branch}", worker_branch],
            cwd=str(self.integration_path),
            capture_output=True,
            text=True,
            env=env,
        )

        if merge_res.returncode != 0:
            # Merge conflict detected! Abort merge to preserve clean state
            subprocess.run([str(GIT_BIN), "merge", "--abort"], cwd=str(self.integration_path), capture_output=True, env=env, check=True)
            conflict_msg = merge_res.stderr or merge_res.stdout
            raise MergeConflictError(f"Merge conflict merging {worker_branch} into {integration_branch}: {conflict_msg}")

        # Get frozen commit SHA
        sha = subprocess.run(
            [str(GIT_BIN), "rev-parse", "HEAD"],
            cwd=str(self.integration_path),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "success": True,
            "integration_branch": integration_branch,
            "merged_branch": worker_branch,
            "integrated_commit_sha": sha,
            "previous_commit_sha": previous,
            "integration_worktree": str(self.integration_path),
        }

    def rollback_integration(self, commit: str) -> None:
        if self.integration_path is None or WORKTREES_DIR.resolve() not in self.integration_path.resolve().parents:
            raise PermissionError("Only the manager's own integration worktree may be reset")
        subprocess.run([str(GIT_BIN), "reset", "--hard", commit], cwd=self.integration_path,
                       check=True, capture_output=True)


class ResourceManager:
    """Enforces hardware limits (RAM/CPU concurrency) using semaphores and test locks."""

    def __init__(self, max_concurrent_workers: int = MAX_CONCURRENT_WORKERS):
        self.worker_semaphore = threading.Semaphore(max_concurrent_workers)
        self.test_lock = threading.Lock()  # Serializes heavy test suites

    def acquire_worker_slot(self, timeout: float = 30.0) -> bool:
        return self.worker_semaphore.acquire(timeout=timeout)

    def release_worker_slot(self) -> None:
        self.worker_semaphore.release()
