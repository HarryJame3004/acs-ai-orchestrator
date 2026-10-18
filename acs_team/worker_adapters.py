"""ACS AI V2 Worker Adapters.
Provides unified, isolated execution adapters for:
1. codex-primary (Codex CLI via workspace-write sandbox)
2. agy-google-a (AGY CLI via Google Account A)
3. agy-google-b (AGY CLI via Google Account B - Unverified fail-closed)
"""

from __future__ import annotations

import logging
import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import AGY_BIN, AGY_B_BIN, AGY_B_HOME, CODEX_BIN
from .managed_worker import worker_run
from .security import redact

logger = logging.getLogger("acs_ai.workers")

BANNED_FLAGS = [
    "--dangerously-bypass-approvals-and-sandbox",
    "--bypass-sandbox",
    "--no-sandbox",
]


class WorkerUnverifiedError(PermissionError):
    """Raised when an unverified worker is scheduled for execution."""
    pass


class BaseWorker(ABC):
    def __init__(self, worker_id: str, is_verified: bool = True):
        self.worker_id = worker_id
        self.is_verified = is_verified

    def is_available(self) -> bool:
        return self.is_verified

    @abstractmethod
    def execute_task(
        self,
        task_id: str,
        goal: str,
        instructions: str,
        worktree_path: Path,
        files_to_modify: Optional[List[str]] = None,
        timeout_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        """Execute a coding task within an isolated worktree."""
        pass


class CodexPrimaryWorker(BaseWorker):
    """Codex CLI Worker running in non-interactive workspace-write sandbox."""

    def __init__(self, codex_bin: Optional[Path] = None):
        super().__init__(worker_id="codex-primary", is_verified=False)
        self.codex_bin = Path(codex_bin or CODEX_BIN)

    def execute_task(
        self,
        task_id: str,
        goal: str,
        instructions: str,
        worktree_path: Path,
        files_to_modify: Optional[List[str]] = None,
        timeout_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        logger.info(f"[{self.worker_id}] Executing task '{task_id}' in {worktree_path}...")

        # Defensive check against banned sandbox bypass flags
        combined = f"{goal} {instructions}"
        for banned in BANNED_FLAGS:
            if banned in combined:
                raise PermissionError(f"Prohibited flag/instruction '{banned}' detected.")

        if not self.is_verified:
            raise WorkerUnverifiedError("Real worker requires explicit local verification")

        prompt = f"""Task ID: {task_id}
Goal: {goal}
Target files: {', '.join(files_to_modify) if files_to_modify else 'Repository files'}

Instructions:
{instructions}

Requirements:
1. Make surgical, minimal, working changes in the workspace.
2. Verify syntax and run tests before finishing.
"""

        # Command for Codex CLI 0.163.0:
        # --approve-for-me automatically routes approvals into workspace-write sandbox
        cmd = [
            str(self.codex_bin),
            "exec",
            "-C",
            str(worktree_path),
            "--approve-for-me",
            "--json",
            prompt,
        ]

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        try:
            proc = worker_run(
                cmd,
                task_id=task_id,
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                stdin=subprocess.DEVNULL,
                env=env,
            )
            stdout = redact(proc.stdout)
            stderr = redact(proc.stderr)
            returncode = proc.returncode

            # Extract changed files from git
            changed_files = self._get_changed_files(worktree_path)

            return {
                "success": returncode == 0,
                "worker_id": self.worker_id,
                "task_id": task_id,
                "exit_code": returncode,
                "changed_files": changed_files,
                "stdout_excerpt": stdout[-2000:] if len(stdout) > 2000 else stdout,
                "stderr_excerpt": stderr[-1000:] if len(stderr) > 1000 else stderr,
                "error": None if returncode == 0 else f"Codex CLI exited with code {returncode}",
            }
        except subprocess.TimeoutExpired as te:
            return {
                "success": False,
                "worker_id": self.worker_id,
                "task_id": task_id,
                "exit_code": -1,
                "changed_files": self._get_changed_files(worktree_path),
                "stdout_excerpt": (te.stdout or "")[-1000:],
                "stderr_excerpt": (te.stderr or "")[-1000:],
                "error": f"Codex worker timed out after {timeout_seconds}s",
            }
        except Exception as e:
            return {
                "success": False,
                "worker_id": self.worker_id,
                "task_id": task_id,
                "exit_code": -1,
                "changed_files": [],
                "stdout_excerpt": "",
                "stderr_excerpt": "",
                "error": f"Failed to invoke Codex CLI: {e}",
            }

    def _get_changed_files(self, repo_path: Path) -> List[str]:
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            files = []
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    files.append(parts[-1])
            return files
        except Exception:
            return []


class AGYGoogleAWorker(BaseWorker):
    """AGY CLI Worker using authenticated Google Account A."""

    def __init__(self, agy_bin: Optional[Path] = None):
        super().__init__(worker_id="agy-google-a", is_verified=False)
        self.agy_bin = Path(agy_bin or AGY_BIN)

    def execute_task(
        self,
        task_id: str,
        goal: str,
        instructions: str,
        worktree_path: Path,
        files_to_modify: Optional[List[str]] = None,
        timeout_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        logger.info(f"[{self.worker_id}] Executing task '{task_id}' in {worktree_path}...")

        combined = f"{goal} {instructions}"
        for banned in BANNED_FLAGS:
            if banned in combined:
                raise PermissionError(f"Prohibited flag/instruction '{banned}' detected.")

        if not self.is_verified:
            raise WorkerUnverifiedError("Real worker requires explicit local verification")

        prompt = f"""Task ID: {task_id}
Goal: {goal}
Target files: {', '.join(files_to_modify) if files_to_modify else 'Repository files'}

Instructions:
{instructions}

Requirements:
1. Make surgical, minimal, working changes in the workspace.
2. Verify files and syntax before concluding.
"""

        cmd = [
            str(self.agy_bin),
            "-p",
            prompt,
            "--output-format",
            "text",
            "--print-timeout",
            f"{int(timeout_seconds)}s",
        ]

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        try:
            proc = worker_run(
                cmd,
                task_id=task_id,
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=timeout_seconds + 10,
                stdin=subprocess.DEVNULL,
                env=env,
            )
            stdout = redact(proc.stdout)
            stderr = redact(proc.stderr)
            returncode = proc.returncode

            changed_files = self._get_changed_files(worktree_path)

            return {
                "success": returncode == 0,
                "worker_id": self.worker_id,
                "task_id": task_id,
                "exit_code": returncode,
                "changed_files": changed_files,
                "stdout_excerpt": stdout[-2000:] if len(stdout) > 2000 else stdout,
                "stderr_excerpt": stderr[-1000:] if len(stderr) > 1000 else stderr,
                "error": None if returncode == 0 else f"AGY CLI exited with code {returncode}",
            }
        except subprocess.TimeoutExpired as te:
            return {
                "success": False,
                "worker_id": self.worker_id,
                "task_id": task_id,
                "exit_code": -1,
                "changed_files": self._get_changed_files(worktree_path),
                "stdout_excerpt": (te.stdout or "")[-1000:],
                "stderr_excerpt": (te.stderr or "")[-1000:],
                "error": f"AGY worker timed out after {timeout_seconds}s",
            }
        except Exception as e:
            return {
                "success": False,
                "worker_id": self.worker_id,
                "task_id": task_id,
                "exit_code": -1,
                "changed_files": [],
                "stdout_excerpt": "",
                "stderr_excerpt": "",
                "error": f"Failed to invoke AGY CLI: {e}",
            }

    def _get_changed_files(self, repo_path: Path) -> List[str]:
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            files = []
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    files.append(parts[-1])
            return files
        except Exception:
            return []


class AGYGoogleBWorker(BaseWorker):
    """AGY CLI Worker for Google Account B.
    Runs isolated using dedicated HOME and XDG environment via ~/.local/bin/agy-b.
    """

    def __init__(self, agy_b_bin: Optional[Path] = None, agy_b_home: Optional[Path] = None):
        self.agy_b_bin = Path(agy_b_bin or AGY_B_BIN)
        self.agy_b_home = Path(agy_b_home or AGY_B_HOME)
        is_verified = False  # Executable/profile presence is not authentication evidence.
        super().__init__(worker_id="agy-google-b", is_verified=is_verified)

    def _build_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["HOME"] = str(self.agy_b_home)
        env["USER"] = os.environ.get("USER", "khoi")
        env["XDG_CONFIG_HOME"] = str(self.agy_b_home / ".config")
        env["XDG_DATA_HOME"] = str(self.agy_b_home / ".local" / "share")
        env["XDG_STATE_HOME"] = str(self.agy_b_home / ".local" / "state")
        return env

    def execute_task(
        self,
        task_id: str,
        goal: str,
        instructions: str,
        worktree_path: Path,
        files_to_modify: Optional[List[str]] = None,
        timeout_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        if not self.is_verified or not self.agy_b_bin.exists():
            raise WorkerUnverifiedError(
                "Worker 'agy-google-b' requires authenticated Google profile and is unavailable."
            )

        prompt = f"""Task: {goal}

Instructions:
{instructions}

Requirements:
1. Make surgical, minimal, working changes in the workspace.
2. Verify files and syntax before concluding.
"""

        cmd = [
            str(self.agy_b_bin),
            "--model",
            "gemini-3.8-flash-low",
            "--effort",
            "low",
            "-p",
            prompt,
            "--output-format",
            "text",
            "--print-timeout",
            f"{int(timeout_seconds)}s",
        ]

        env = self._build_env()

        try:
            proc = worker_run(
                cmd,
                task_id=task_id,
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=timeout_seconds + 10,
                stdin=subprocess.DEVNULL,
                env=env,
            )
            stdout = redact(proc.stdout)
            stderr = redact(proc.stderr)
            returncode = proc.returncode

            changed_files = self._get_changed_files(worktree_path)

            return {
                "success": returncode == 0,
                "worker_id": self.worker_id,
                "task_id": task_id,
                "exit_code": returncode,
                "changed_files": changed_files,
                "stdout_excerpt": stdout[-2000:] if len(stdout) > 2000 else stdout,
                "stderr_excerpt": stderr[-1000:] if len(stderr) > 1000 else stderr,
                "error": None if returncode == 0 else f"AGY B CLI exited with code {returncode}",
            }
        except subprocess.TimeoutExpired as te:
            return {
                "success": False,
                "worker_id": self.worker_id,
                "task_id": task_id,
                "exit_code": -1,
                "changed_files": self._get_changed_files(worktree_path),
                "stdout_excerpt": (te.stdout or "")[-1000:],
                "stderr_excerpt": (te.stderr or "")[-1000:],
                "error": f"AGY B worker timed out after {timeout_seconds}s",
            }
        except Exception as e:
            return {
                "success": False,
                "worker_id": self.worker_id,
                "task_id": task_id,
                "exit_code": -1,
                "changed_files": [],
                "stdout_excerpt": "",
                "stderr_excerpt": "",
                "error": f"Failed to invoke AGY B CLI: {e}",
            }

    def _get_changed_files(self, repo_path: Path) -> List[str]:
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=5,
            )
            files = []
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    files.append(parts[-1])
            return files
        except Exception:
            return []


class WorkerRegistry:
    """Manages worker pool registration, discovery, and dispatch."""

    def __init__(self):
        self._workers: Dict[str, BaseWorker] = {
            "codex-primary": CodexPrimaryWorker(),
            "agy-google-a": AGYGoogleAWorker(),
            "agy-google-b": AGYGoogleBWorker(),
        }
        if os.environ.get("ACS_ENABLE_PROVIDER_CONTRACTS") == "1":
            from .provider_workers import configured_workers
            self._workers.update(configured_workers())

    def get_worker(self, worker_id: str) -> BaseWorker:
        if worker_id not in self._workers:
            raise KeyError(f"Unknown worker: '{worker_id}'")
        return self._workers[worker_id]

    def list_available_workers(self) -> List[str]:
        """Returns list of verified, operational workers eligible for scheduling."""
        return [wid for wid, w in self._workers.items() if w.is_verified]

    def get_all_worker_metadata(self) -> Dict[str, Dict[str, Any]]:
        wb = self._workers.get("agy-google-b")
        b_ready = wb.is_verified if wb else False
        return {
            "codex-primary": {
                "backend": "codex-cli",
                "status": "READY" if self._workers["codex-primary"].is_verified else "UNAVAILABLE",
                "verified": self._workers["codex-primary"].is_verified,
                "notes": "Requires explicit local authentication and harmless task verification",
            },
            "agy-google-a": {
                "backend": "agy-cli",
                "status": "READY" if self._workers["agy-google-a"].is_verified else "UNAVAILABLE",
                "verified": self._workers["agy-google-a"].is_verified,
                "notes": "Requires explicit local authentication and harmless task verification",
            },
            "agy-google-b": {
                "backend": "agy-cli (Account B)",
                "status": "READY" if b_ready else "UNVERIFIED",
                "verified": b_ready,
                "notes": "Verified with Google Account B via dedicated isolated home" if b_ready else "Requires interactive Google Account B login",
            },
        }

    def get_all_statuses(self) -> List[Dict[str, Any]]:
        meta = self.get_all_worker_metadata()
        statuses = []
        for wid, data in meta.items():
            statuses.append({
                "name": wid,
                "role": "worker",
                "ready": data["verified"],
                "status": data["status"],
                "details": f"{data['backend']} - {data['notes']}",
            })
        return statuses
