"""ACS AI V2 Git Worktree & Disk Safeguards Manager.
Enforces:
1. Isolated worktrees per worker: acsai/worker/{mission_id}/{task_id}
2. Disk Space Circuit Breaker: blocks worktree creation if free SSD space < 10 GB
3. Worktree Garbage Collection: auto-cleans completed worktrees, retains failed/blocked for inspection.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Optional

from .config import GIT_BIN, MIN_DISK_FREE_GB, WORKTREES_DIR

logger = logging.getLogger("acs_ai.worktree")


class DiskSpaceCircuitBreakerError(RuntimeError):
    """Raised when available disk space is insufficient for safe worktree creation."""
    pass


class WorktreeManager:
    """Manages creation, lifecycle, and safe garbage collection of isolated Git worktrees."""

    def __init__(self, worktrees_dir: Optional[Path] = None, min_free_gb: float = MIN_DISK_FREE_GB):
        self.worktrees_dir = Path(worktrees_dir or WORKTREES_DIR)
        self.min_free_gb = min_free_gb
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    def check_disk_space(self) -> float:
        """Returns free disk space in GB for the worktrees filesystem."""
        usage = shutil.disk_usage(self.worktrees_dir)
        free_gb = usage.free / (1024 ** 3)
        return free_gb

    def assert_disk_space_available(self) -> None:
        """Enforces the Disk Space Circuit Breaker safeguard."""
        free_gb = self.check_disk_space()
        if free_gb < self.min_free_gb:
            raise DiskSpaceCircuitBreakerError(
                f"Disk Space Circuit Breaker triggered: only {free_gb:.2f} GB free, "
                f"minimum required is {self.min_free_gb:.1f} GB. Halting worktree allocation."
            )

    def create_worktree(
        self,
        repo_path: Path,
        mission_id: str,
        task_id: str,
        base_ref: str = "HEAD",
    ) -> Path:
        """Creates an isolated git worktree on a dedicated branch."""
        self.assert_disk_space_available()

        clean_mid = mission_id.replace("/", "_")
        clean_tid = task_id.replace("/", "_")
        if not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", item) for item in (clean_mid, clean_tid)):
            raise ValueError("Unsafe worktree identifier")
        branch_name = f"acsai/worker/{clean_mid}/{clean_tid}"
        worktree_path = self.worktrees_dir / f"{clean_mid}_{clean_tid}"

        if worktree_path.exists() or worktree_path.is_symlink():
            raise FileExistsError("Existing worktree retained for inspection")

        logger.info(f"Creating isolated worktree at {worktree_path} on branch {branch_name}...")
        cmd = [
            str(GIT_BIN),
            "worktree",
            "add",
            "-b",
            branch_name,
            str(worktree_path),
            base_ref,
        ]

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        res = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            env=env,
        )
        if res.returncode != 0:
            raise RuntimeError(
                f"Failed to create git worktree: {res.stderr or res.stdout}"
            )

        return worktree_path

    def remove_worktree(
        self,
        repo_path: Path,
        worktree_path: Path,
        force: bool = False,
    ) -> None:
        """Removes a worktree and prunes git metadata."""
        if not worktree_path.exists():
            return
        root, target = self.worktrees_dir.resolve(), worktree_path.resolve()
        if worktree_path.is_symlink() or root not in target.parents:
            raise PermissionError("Refusing removal outside the owned worktree root")
        listing = subprocess.run([str(GIT_BIN), "worktree", "list", "--porcelain"], cwd=repo_path,
                                 check=True, capture_output=True, text=True)
        registered = {Path(line[9:]).resolve() for line in listing.stdout.splitlines() if line.startswith("worktree ")}
        if target not in registered or not (target / ".git").is_file():
            raise PermissionError("Refusing removal of an unregistered linked worktree")

        cmd = [str(GIT_BIN), "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(worktree_path))

        subprocess.run(cmd, cwd=str(repo_path), capture_output=True, text=True, check=True)

        # Prune dead worktree metadata
        subprocess.run([str(GIT_BIN), "worktree", "prune"], cwd=str(repo_path), capture_output=True)

    def garbage_collect_worktree(
        self,
        repo_path: Path,
        worktree_path: Path,
        task_status: str,
    ) -> bool:
        """Garbage collection policy:
        - If task COMPLETED: auto-clean worktree to free disk space.
        - If task FAILED or BLOCKED: retain worktree for developer/QA inspection.
        """
        if task_status.upper() in ["COMPLETED", "SUCCESS", "READY_FOR_REVIEW"]:
            logger.info(f"Task status '{task_status}': auto-cleaning worktree {worktree_path}...")
            self.remove_worktree(repo_path, worktree_path, force=True)
            return True
        else:
            logger.info(
                f"Task status '{task_status}': retaining worktree {worktree_path} for inspection."
            )
            return False
