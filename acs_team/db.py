"""ACS AI V2 SQLite Database Engine with WAL, FTS5, and Single-Writer Safety.
Enforces:
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .config import ACS_CORE_DIR, DB_PATH, LOGS_DIR, PROTECTED_PATHS
from .security import redact

logger = logging.getLogger("acs_ai.db")

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    repository_path TEXT NOT NULL,
    goal TEXT NOT NULL,
    state TEXT NOT NULL,
    assigned_workers TEXT, -- JSON list of worker IDs
    current_checkpoint TEXT,
    git_branch TEXT,
    commit_sha TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    review_status TEXT,
    quality_score REAL DEFAULT 0.0,
    evidence_ref TEXT,
    error_info TEXT,
    prompt TEXT,
    plan_json TEXT,
    logs TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    assigned_worker TEXT,
    state TEXT NOT NULL,
    worktree_path TEXT,
    branch_name TEXT,
    attempt_no INTEGER DEFAULT 1,
    exit_code INTEGER,
    changed_files TEXT, -- JSON list
    diff_summary TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    state_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT,
    task_id TEXT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details_json TEXT,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    memory_type TEXT NOT NULL, -- project, task, decision, failure, knowledge
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_reference TEXT,
    source_commit TEXT,
    confidence REAL DEFAULT 1.0,
    stale INTEGER DEFAULT 0,
    sensitivity TEXT DEFAULT 'normal',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_verified TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    title,
    content,
    memory_id UNINDEXED,
    project_id UNINDEXED
);

CREATE TABLE IF NOT EXISTS human_approvals (
    approval_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    target_repo TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL, -- PENDING, APPROVED, REJECTED
    approved_by TEXT,
    reason TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS repositories (
    repo_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    is_protected INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class DatabaseManager:
    """Manages SQLite connection lifecycle, schema migrations, and transactions."""

    def __init__(self, db_path: Optional[Path] = None, read_only: bool = False):
        self.db_path = Path(db_path or DB_PATH)
        self.read_only = read_only
        canonical = self.db_path.resolve()
        if any(canonical == p or p in canonical.parents for p in PROTECTED_PATHS):
            raise PermissionError('Database path overlaps a protected project')
        if self.db_path.is_symlink() or (self.db_path.exists() and self.db_path.stat().st_nlink != 1):
            raise PermissionError('Database must not be a symlink or hard link')
        if read_only:
            if not self.db_path.is_file():
                raise FileNotFoundError('Read-only database must already exist')
        else:
            self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not self.db_path.exists():
                try:
                    descriptor = os.open(self.db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                except FileExistsError:
                    if self.db_path.is_symlink():
                        raise PermissionError('Concurrent database symlink replacement') from None
                else:
                    os.close(descriptor)
        self._ensure_initialized()

    def close(self) -> None:
        """Closes any underlying resources if applicable."""
        pass

    def get_connection(self) -> sqlite3.Connection:
        """Returns a configured SQLite connection with required PRAGMAs."""
        if self.read_only:
            uri = f"file:{self.db_path.resolve()}?mode=ro"
            con = sqlite3.connect(uri, uri=True, timeout=5.0)
        else:
            con = sqlite3.connect(str(self.db_path), timeout=5.0)

        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA busy_timeout=5000;")
        con.execute("PRAGMA foreign_keys=ON;")
        return con

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Internal short transaction scope; preserve get_connection compatibility."""
        con = self.get_connection()
        try:
            with con:
                yield con
        finally:
            con.close()

    def _ensure_initialized(self) -> None:
        """Applies schema if not present (only if writable)."""
        if self.read_only:
            return
        with self.connection() as con:
            con.executescript(SCHEMA_SQL)
            cur = con.execute("SELECT version FROM schema_version WHERE version = ?", (SCHEMA_VERSION,))
            if not cur.fetchone():
                con.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.datetime.now(datetime.timezone.utc).isoformat()),
                )

            # Non-destructive column migrations for existing missions table
            try:
                table_cols = {row["name"] for row in con.execute("PRAGMA table_info(missions);").fetchall()}
                for col, col_type in [("prompt", "TEXT"), ("plan_json", "TEXT"), ("logs", "TEXT")]:
                    if col not in table_cols:
                        con.execute(f"ALTER TABLE missions ADD COLUMN {col} {col_type};")
            except Exception as e:
                logger.debug(f"Column migration check: {e}")

            # Seed protected ACS Core repository if not present
            try:
                acs_core_str = str(ACS_CORE_DIR.resolve())
                cur = con.execute("SELECT repo_id FROM repositories WHERE path = ?", (acs_core_str,))
                if not cur.fetchone():
                    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    con.execute(
                        "INSERT INTO repositories (repo_id, name, path, is_protected, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        ("repo-acs-core", "ACS Core (Protected)", acs_core_str, 1, now_str, now_str),
                    )
            except Exception as e:
                logger.debug(f"Could not seed ACS Core repository: {e}")

    # ---------------------------------------------------------
    # Mission Operations
    # ---------------------------------------------------------
    def create_mission(
        self,
        mission_id: str,
        project_id: str,
        repository_path: str,
        goal: str,
        state: str = "CREATED",
        assigned_workers: Optional[List[str]] = None,
        max_retries: int = 3,
        prompt: Optional[str] = None,
        plan_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        goal, prompt = redact(goal), redact(prompt)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        workers_json = json.dumps(assigned_workers or [])
        with self.connection() as con:
            con.execute(
                """
                INSERT INTO missions (
                    mission_id, project_id, repository_path, goal, state,
                    assigned_workers, retry_count, max_retries, prompt, plan_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (mission_id, project_id, repository_path, goal, state, workers_json, max_retries, prompt or goal, plan_json, now, now),
            )
            self.record_event(
                con,
                mission_id=mission_id,
                actor="system",
                action="create_mission",
                details={"goal": redact(goal), "project_id": project_id, "state": state},
            )
        return self.get_mission(mission_id)  # type: ignore

    def get_mission(self, mission_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as con:
            cur = con.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,))
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row)
            data["assigned_workers"] = json.loads(data["assigned_workers"]) if data["assigned_workers"] else []
            return data

    def list_missions(self, limit: int = 50, state: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.connection() as con:
            if state:
                cur = con.execute(
                    "SELECT * FROM missions WHERE state = ? ORDER BY created_at DESC LIMIT ?",
                    (state, limit),
                )
            else:
                cur = con.execute("SELECT * FROM missions ORDER BY created_at DESC LIMIT ?", (limit,))
            results = []
            for row in cur.fetchall():
                d = dict(row)
                d["assigned_workers"] = json.loads(d["assigned_workers"]) if d["assigned_workers"] else []
                results.append(d)
            return results

    def update_mission_state(
        self,
        mission_id: str,
        new_state: str,
        error_info: Optional[str] = None,
        commit_sha: Optional[str] = None,
        git_branch: Optional[str] = None,
        review_status: Optional[str] = None,
        quality_score: Optional[float] = None,
        evidence_ref: Optional[str] = None,
        expected_state: Optional[str] = None,
    ) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.connection() as con:
            updates = ["state = ?", "updated_at = ?"]
            params: List[Any] = [new_state, now]

            if error_info is not None:
                updates.append("error_info = ?")
                params.append(redact(error_info))
            if commit_sha is not None:
                updates.append("commit_sha = ?")
                params.append(commit_sha)
            if git_branch is not None:
                updates.append("git_branch = ?")
                params.append(git_branch)
            if review_status is not None:
                updates.append("review_status = ?")
                params.append(review_status)
            if quality_score is not None:
                updates.append("quality_score = ?")
                params.append(quality_score)
            if evidence_ref is not None:
                updates.append("evidence_ref = ?")
                params.append(evidence_ref)

            params.append(mission_id)
            condition = ' AND state = ?' if expected_state is not None else ''
            if expected_state is not None:
                params.append(expected_state)
            changed = con.execute(f"UPDATE missions SET {', '.join(updates)} WHERE mission_id = ?" + condition, params)
            if expected_state is not None and changed.rowcount != 1:
                raise RuntimeError('Concurrent mission state transition rejected')
            self.record_event(
                con,
                mission_id=mission_id,
                actor="state_machine",
                action="transition_state",
                details={"new_state": new_state, "error_info": error_info},
            )

    def increment_mission_retry(self, mission_id: str) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.connection() as con:
            con.execute(
                "UPDATE missions SET retry_count = retry_count + 1, updated_at = ? WHERE mission_id = ?",
                (now, mission_id),
            )
            cur = con.execute("SELECT retry_count FROM missions WHERE mission_id = ?", (mission_id,))
            return cur.fetchone()[0]

    # ---------------------------------------------------------
    # Checkpoints
    # ---------------------------------------------------------
    def save_checkpoint(self, mission_id: str, state_name: str, payload: Dict[str, Any]) -> str:
        payload_str = json.dumps(payload, sort_keys=True)
        sha256_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        checkpoint_id = f"chk-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}-{sha256_hash[:8]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.connection() as con:
            con.execute(
                """
                INSERT INTO checkpoints (checkpoint_id, mission_id, state_name, payload_json, sha256_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (checkpoint_id, mission_id, state_name, payload_str, sha256_hash, now),
            )
            con.execute(
                "UPDATE missions SET current_checkpoint = ?, updated_at = ? WHERE mission_id = ?",
                (checkpoint_id, now, mission_id),
            )
            self.record_event(
                con,
                mission_id=mission_id,
                actor="checkpoint_manager",
                action="save_checkpoint",
                details={"checkpoint_id": checkpoint_id, "state_name": state_name, "sha256": sha256_hash},
            )
        return checkpoint_id

    def get_latest_checkpoint(self, mission_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as con:
            cur = con.execute(
                "SELECT * FROM checkpoints WHERE mission_id = ? ORDER BY created_at DESC LIMIT 1",
                (mission_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row)
            # Verify hash integrity
            calc_hash = hashlib.sha256(data["payload_json"].encode("utf-8")).hexdigest()
            data["valid"] = (calc_hash == data["sha256_hash"])
            data["payload"] = json.loads(data["payload_json"])
            return data

    # ---------------------------------------------------------
    # Audit Events
    # ---------------------------------------------------------
    def record_event(
        self,
        con: sqlite3.Connection,
        mission_id: Optional[str],
        actor: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        details_str = json.dumps(redact(details or {}))
        con.execute(
            """
            INSERT INTO audit_events (mission_id, task_id, actor, action, details_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (mission_id, task_id, actor, action, details_str, now),
        )

    def record_audit_event(
        self,
        mission_id: Optional[str],
        actor: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> None:
        with self.connection() as con:
            self.record_event(con, mission_id, actor, action, details, task_id)
            con.commit()

    def get_audit_trail(self, mission_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connection() as con:
            cur = con.execute(
                "SELECT * FROM audit_events WHERE mission_id = ? ORDER BY event_id ASC LIMIT ?",
                (mission_id, limit),
            )
            events = []
            for r in cur.fetchall():
                d = dict(r)
                d["details"] = json.loads(d["details_json"]) if d["details_json"] else {}
                events.append(d)
            return events

    # ---------------------------------------------------------
    # Memories (Gate 4 engine ready)
    # ---------------------------------------------------------
    def save_memory(
        self,
        memory_id: str,
        project_id: str,
        repository_id: str,
        memory_type: str,
        title: str,
        content: str,
        source_type: str,
        source_reference: Optional[str] = None,
        source_commit: Optional[str] = None,
        confidence: float = 1.0,
        sensitivity: str = "normal",
    ) -> str:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.connection() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO memories (
                    memory_id, project_id, repository_id, memory_type, title, content,
                    source_type, source_reference, source_commit, confidence, stale,
                    sensitivity, created_at, updated_at, last_verified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (
                    memory_id, project_id, repository_id, memory_type, title, content,
                    source_type, source_reference, source_commit, confidence,
                    sensitivity, now, now, now,
                ),
            )
            # Update FTS index
            con.execute("DELETE FROM memories_fts WHERE memory_id = ?", (memory_id,))
            con.execute(
                "INSERT INTO memories_fts (title, content, memory_id, project_id) VALUES (?, ?, ?, ?)",
                (title, content, memory_id, project_id),
            )
        return memory_id

    def search_memories(
        self,
        query: str,
        project_id: str,
        memory_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        with self.connection() as con:
            if query.strip():
                # Clean query for FTS5
                clean_query = "".join(c if c.isalnum() or c.isspace() else " " for c in query).strip()
                if not clean_query:
                    clean_query = query
                sql = """
                    SELECT m.*, rank
                    FROM memories_fts f
                    JOIN memories m ON f.memory_id = m.memory_id
                    WHERE memories_fts MATCH ? AND m.stale = 0
                """
                params: List[Any] = [clean_query]
                if project_id:
                    sql += " AND m.project_id = ?"
                    params.append(project_id)
                if memory_type:
                    sql += " AND m.memory_type = ?"
                    params.append(memory_type)
                sql += " ORDER BY rank LIMIT ?"
                params.append(limit)
                cur = con.execute(sql, params)
            else:
                sql = "SELECT * FROM memories WHERE stale = 0"
                params = []
                if project_id:
                    sql += " AND project_id = ?"
                    params.append(project_id)
                if memory_type:
                    sql += " AND memory_type = ?"
                    params.append(memory_type)
                sql += " ORDER BY updated_at DESC LIMIT ?"
                params.append(limit)
                cur = con.execute(sql, params)

            return [dict(r) for r in cur.fetchall()]

    def mark_memory_stale(self, project_id: str, repository_id: str, commit_sha: str) -> int:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.connection() as con:
            cur = con.execute(
                """
                UPDATE memories
                SET stale = 1, updated_at = ?
                WHERE project_id = ? AND repository_id = ? AND source_commit != ? AND source_commit IS NOT NULL
                """,
                (now, project_id, repository_id, commit_sha),
            )
            return cur.rowcount

    # ---------------------------------------------------------
    # Mission Plan & Log Operations
    # ---------------------------------------------------------
    def update_mission_plan(self, mission_id: str, prompt: str, plan_dict: Dict[str, Any]) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.connection() as con:
            con.execute(
                "UPDATE missions SET prompt = ?, plan_json = ?, updated_at = ? WHERE mission_id = ?",
                (prompt, json.dumps(plan_dict), now, mission_id),
            )

    def append_mission_log(self, mission_id: str, message: str) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{now}] {message.strip()}\n"
        with self.connection() as con:
            cur = con.execute("SELECT logs FROM missions WHERE mission_id = ?", (mission_id,))
            row = cur.fetchone()
            existing = row["logs"] if row and row["logs"] else ""
            updated = existing + formatted
            con.execute("UPDATE missions SET logs = ? WHERE mission_id = ?", (updated, mission_id))

        try:
            log_file = LOGS_DIR / f"mission_{mission_id}.log"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(formatted)
        except Exception:
            pass

    def get_mission_logs(self, mission_id: str) -> List[str]:
        with self.connection() as con:
            cur = con.execute("SELECT logs FROM missions WHERE mission_id = ?", (mission_id,))
            row = cur.fetchone()
            if row and row["logs"]:
                return [l for l in row["logs"].splitlines() if l.strip()]
        log_file = LOGS_DIR / f"mission_{mission_id}.log"
        if log_file.exists():
            try:
                return [l for l in log_file.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
            except Exception:
                pass
        return []


    # ---------------------------------------------------------
    # Repository Management Operations
    # ---------------------------------------------------------
    def register_repository(
        self,
        repo_id: str,
        name: str,
        path: str,
        is_protected: bool = False,
    ) -> Dict[str, Any]:
        canonical_path = str(Path(path).resolve())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.connection() as con:
            con.execute(
                """
                INSERT INTO repositories (repo_id, name, path, is_protected, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    name = excluded.name,
                    is_protected = excluded.is_protected,
                    updated_at = excluded.updated_at
                """,
                (repo_id, name, canonical_path, 1 if is_protected else 0, now, now),
            )
        repo = self.get_repository_by_path(canonical_path)
        return repo or {"repo_id": repo_id, "name": name, "path": canonical_path, "is_protected": is_protected}

    def list_repositories(self) -> List[Dict[str, Any]]:
        with self.connection() as con:
            cur = con.execute("SELECT * FROM repositories ORDER BY is_protected DESC, name ASC")
            return [dict(r) for r in cur.fetchall()]

    def get_repository(self, repo_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as con:
            cur = con.execute("SELECT * FROM repositories WHERE repo_id = ?", (repo_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_repository_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        canonical_path = str(Path(path).resolve())
        with self.connection() as con:
            cur = con.execute("SELECT * FROM repositories WHERE path = ?", (canonical_path,))
            row = cur.fetchone()
            return dict(row) if row else None

    def delete_repository(self, repo_id: str) -> bool:
        with self.connection() as con:
            cur = con.execute("DELETE FROM repositories WHERE repo_id = ? AND is_protected = 0", (repo_id,))
            return cur.rowcount > 0
