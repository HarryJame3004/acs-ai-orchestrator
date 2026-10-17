"""ACS AI V2.2 Repository Inventory & Target Resolver.
Manages explicitly registered repositories, verifies Git states,
and ensures ACS Core is NEVER automatically selected as a writable workspace.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import ACS_CORE_DIR, GIT_BIN, WORKSPACES_DIR
from .db import DatabaseManager

logger = logging.getLogger("acs_ai.repo_manager")


class RepoManager:
    """Manages explicitly registered development repositories for ACS AI."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def list_managed_repositories(self) -> List[Dict[str, Any]]:
        """Returns all explicitly registered repositories with live Git telemetry."""
        raw_repos = self.db.list_repositories()
        enriched = []

        for r in raw_repos:
            path = Path(r["path"])
            exists = path.is_dir()
            is_git = (path / ".git").exists() if exists else False
            is_corelock = self.is_corelock_protected(path)

            branch = "N/A"
            tree_state = "MISSING" if not exists else ("NOT_A_GIT_REPO" if not is_git else "UNKNOWN")

            if exists and is_git:
                try:
                    # Get current branch
                    res_b = subprocess.run(
                        [str(GIT_BIN), "branch", "--show-current"],
                        cwd=str(path),
                        capture_output=True,
                        text=True,
                        timeout=3.0,
                    )
                    branch = res_b.stdout.strip() or "detached"

                    # Get working tree status
                    res_s = subprocess.run(
                        [str(GIT_BIN), "status", "--porcelain"],
                        cwd=str(path),
                        capture_output=True,
                        text=True,
                        timeout=3.0,
                    )
                    uncommitted = [l for l in res_s.stdout.splitlines() if l.strip()]
                    tree_state = "clean" if not uncommitted else f"dirty ({len(uncommitted)} uncommitted files)"
                except Exception as e:
                    tree_state = f"error: {e}"

            # Query last mission on this repo
            last_mission = "None"
            try:
                with self.db.connection() as con:
                    cur = con.execute(
                        "SELECT mission_id, state, updated_at FROM missions WHERE repository_path = ? ORDER BY created_at DESC LIMIT 1",
                        (str(path.resolve()),),
                    )
                    row = cur.fetchone()
                    if row:
                        last_mission = f"{row['mission_id']} [{row['state']}]"
            except Exception:
                pass

            can_safely_operate = exists and is_git and not is_corelock

            enriched.append({
                "repo_id": r["repo_id"],
                "name": r["name"],
                "path": str(path.resolve()),
                "exists": exists,
                "is_git": is_git,
                "git_branch": branch,
                "working_tree_state": tree_state,
                "last_mission": last_mission,
                "is_protected": bool(r["is_protected"] or is_corelock),
                "safe_to_operate": can_safely_operate,
                "status_badge": "READ_ONLY" if is_corelock else ("READY" if can_safely_operate else "BLOCKED"),
            })

        return enriched

    def list_repositories(self) -> List[Dict[str, Any]]:
        """Alias for list_managed_repositories."""
        return self.list_managed_repositories()

    def register_repo(self, path_str: str, name: Optional[str] = None) -> Dict[str, Any]:
        """Explicitly registers a repository path with ACS AI."""
        path = Path(path_str).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"Target path does not exist or is not a directory: {path}")

        repo_name = name or path.name
        is_protected = self.is_corelock_protected(path)
        repo_id = f"repo-{path.name.lower().replace(' ', '-')[:20]}"

        return self.db.register_repository(
            repo_id=repo_id,
            name=repo_name,
            path=str(path),
            is_protected=is_protected,
        )

    def register_repository(self, path: Path | str, name: Optional[str] = None) -> Dict[str, Any]:
        """Alias for register_repo accepting Path or str."""
        return self.register_repo(str(path), name=name)


    def is_corelock_protected(self, path: Path | str) -> bool:
        """Determines if a path is strictly protected under CoreLock rules."""
        try:
            canon = Path(path).expanduser().resolve()
            from .config import PROTECTED_PATHS
            protected = (*PROTECTED_PATHS, ACS_CORE_DIR)
            return any(canon == p.expanduser().resolve() or p.expanduser().resolve() in canon.parents for p in protected)
        except Exception:
            return True

    def resolve_target_workspace(
        self,
        requested_repo: Optional[str] = None,
        mission_id: Optional[str] = None,
    ) -> Tuple[Path, bool]:
        """Resolves target workspace for a mission.
        
        Returns:
            Tuple[Path, bool]: (resolved_path, is_ephemeral_workspace)
        
        Guarantees:
        - NEVER selects ACS Core as a writable target.
        - If requested_repo is provided and is ACS Core -> raises PermissionError.
        - If no repo provided -> checks CWD. If CWD is a Git repo and not ACS Core -> uses CWD.
        - If CWD is not a Git repo or is ACS Core -> creates dedicated isolated workspace.
        """
        # 1. Explicit repository requested
        if requested_repo:
            target = Path(requested_repo).expanduser().resolve()
            if self.is_corelock_protected(target):
                raise PermissionError(
                    f"CoreLock Violation: '{target}' is strictly protected and read-only. "
                    "Cannot be targeted for automated mission mutations."
                )
            if not target.is_dir():
                raise FileNotFoundError(f"Target repository does not exist: {target}")

            # Register it if not already registered
            self.register_repo(str(target))
            return target, False

        # 2. Check current working directory
        cwd = Path.cwd().resolve()
        if not self.is_corelock_protected(cwd) and (cwd / ".git").exists():
            logger.info(f"Detected Git repository in CWD: {cwd}")
            self.register_repo(str(cwd))
            return cwd, False

        # 3. Create isolated mission workspace under WORKSPACES_DIR
        clean_mid = (mission_id or "default").replace("/", "_").replace(":", "_")
        workspace_dir = WORKSPACES_DIR / f"workspace_{clean_mid}"
        if workspace_dir.is_symlink() or WORKSPACES_DIR.resolve() not in workspace_dir.resolve().parents:
            raise PermissionError('Isolated workspace escapes the managed root')
        if self.is_corelock_protected(workspace_dir):
            raise PermissionError('Isolated workspace overlaps protected paths')
        if workspace_dir.exists() and not (workspace_dir / '.git').exists():
            raise FileExistsError('Existing non-Git workspace is retained; refusing to initialize over user files')
        workspace_dir.mkdir(parents=True, exist_ok=True)

        if not (workspace_dir / ".git").exists():
            logger.info(f"Initializing isolated Git repository at {workspace_dir}")
            subprocess.run([str(GIT_BIN), "init", "-b", "main"], cwd=str(workspace_dir), check=True, capture_output=True)
            subprocess.run([str(GIT_BIN), "config", "user.name", "ACS AI Worker"], cwd=str(workspace_dir), check=True)
            subprocess.run([str(GIT_BIN), "config", "user.email", "worker@acsai.local"], cwd=str(workspace_dir), check=True)

            readme = workspace_dir / "README.md"
            readme.write_text(f"# Workspace for Mission {mission_id}\n\nCreated automatically by ACS AI V2.2.\n")
            subprocess.run([str(GIT_BIN), "add", "README.md"], cwd=str(workspace_dir), check=True)
            subprocess.run([str(GIT_BIN), "commit", "-m", "Initial commit"], cwd=str(workspace_dir), check=True)

        # Register workspace
        self.register_repo(str(workspace_dir), name=f"Workspace: {clean_mid}")
        return workspace_dir, True
