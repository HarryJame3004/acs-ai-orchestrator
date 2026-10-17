"""ACS AI Local API Server.
Provides authenticated REST / JSON endpoints for CLI, TUI, and external integrations.
Runs inside the daemon process to guarantee a single-writer SQLite architecture.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from .auth import get_or_create_auth_token, verify_token
from .config import API_HOST, API_PORT
from .db import DatabaseManager
from .state_machine import MissionState, StateMachine

logger = logging.getLogger("acs_ai.api")


class ACSRequestHandler(BaseHTTPRequestHandler):
    """Handles authenticated HTTP requests to the ACS AI Local API."""

    server: ACSServer  # type hint

    def _send_json(self, status_code: int, data: Any) -> None:
        from .security import redact
        payload = json.dumps(redact(data), indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_error(self, status_code: int, message: str) -> None:
        self._send_json(status_code, {"error": message, "status": "error"})

    def _check_auth(self) -> bool:
        auth_header = self.headers.get("Authorization")
        if not auth_header:
            self._send_error(401, "Missing Authorization header")
            return False
        if not verify_token(auth_header, self.server.auth_token):
            self._send_error(403, "Invalid Bearer authentication token")
            return False
        return True

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length < 0 or content_length > 65536:
                self._send_error(413, 'Request body exceeds 64 KiB')
                return None
            if content_length == 0:
                return {}
            self.connection.settimeout(5)
            raw_body = self.rfile.read(content_length).decode("utf-8")
            value = json.loads(raw_body)
            if not isinstance(value, dict):
                raise ValueError('Object required')
            return value
        except (ValueError, UnicodeError, OSError, RecursionError):
            self._send_error(400, "Malformed JSON request body")
            return None

    def log_message(self, format: str, *args: Any) -> None:
        # Route to standard python logger instead of stderr
        logger.debug(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)

        # Health endpoint requires no authentication
        if path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "daemon": "acs-ai-daemon",
                    "version": "2.1",
                    "db": "connected",
                },
            )
            return

        # Authenticate all other endpoints
        if not self._check_auth():
            return

        db: DatabaseManager = self.server.db

        if path == '/runtime':
            from .runtime_view import runtime_snapshot
            self._send_json(200, runtime_snapshot(db))
            return

        if path == "/status":
            missions = db.list_missions(limit=10)
            active_missions = [m for m in missions if m["state"] in ["RUNNING", "PLANNING", "INTEGRATING", "TESTING"]]
            self._send_json(
                200,
                {
                    "status": "online",
                    "active_missions_count": len(active_missions),
                    "total_missions_recorded": len(missions),
                    "recent_missions": missions[:5],
                    "workers": self.server.get_worker_statuses(),
                },
            )
            return

        elif path == "/missions":
            state = query.get("state", [None])[0]
            limit = int(query.get("limit", [50])[0])
            self._send_json(200, db.list_missions(limit=limit, state=state))
            return

        elif path.startswith("/missions/"):
            parts = path.split("/")
            if len(parts) == 3:
                mission_id = parts[2]
                m = db.get_mission(mission_id)
                if not m:
                    self._send_error(404, f"Mission '{mission_id}' not found")
                    return
                checkpoint = db.get_latest_checkpoint(mission_id)
                audit = db.get_audit_trail(mission_id, limit=50)
                m["checkpoint"] = checkpoint
                m["audit_trail"] = audit
                self._send_json(200, m)
                return
            elif len(parts) == 4 and parts[3] == "logs":
                mission_id = parts[2]
                logs = db.get_mission_logs(mission_id)
                self._send_json(200, {"mission_id": mission_id, "logs": logs})
                return

        elif path == "/workers":
            self._send_json(200, self.server.get_worker_statuses())
            return

        elif path == "/mcp":
            from .mcp_manager import MCPManager
            mgr = MCPManager()
            inv = [s.to_dict() for s in mgr.get_inventory()]
            self._send_json(200, inv)
            return

        elif path == "/mcp/status":
            from .mcp_manager import MCPManager
            mgr = MCPManager()
            self._send_json(200, mgr.get_summary_stats())
            return

        elif path == "/mcp/tools":
            from .mcp_manager import MCPManager
            mgr = MCPManager()
            self._send_json(200, mgr.list_all_tools())
            return

        elif path in ("/repos", "/repos/status"):
            from .repo_manager import RepoManager
            rm = RepoManager(db)
            self._send_json(200, rm.list_repositories())
            return

        elif path == "/memory":
            q = query.get("q", [""])[0]
            project_id = query.get("project_id", ["default"])[0]
            m_type = query.get("type", [None])[0]
            limit = int(query.get("limit", [10])[0])
            results = db.search_memories(query=q, project_id=project_id, memory_type=m_type, limit=limit)
            self._send_json(200, results)
            return

        self._send_error(404, f"Path '{path}' not found")

    def do_POST(self) -> None:
        if not self._check_auth():
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        db: DatabaseManager = self.server.db
        body = self._read_json_body()
        if body is None:
            return

        if path == "/missions":
            # Submit new mission (supports goal or prompt)
            goal = body.get("goal") or body.get("prompt")
            if not isinstance(goal, str) or not goal.strip() or len(goal.encode()) > 16384:
                self._send_error(400, "Goal must be a nonempty string within 16 KiB")
                return
            project_id = body.get("project_id", "default")
            repo_path = body.get("repository_path", "") or body.get("repo_path", "")
            workers = body.get("assigned_workers", ["auto"])
            if not isinstance(project_id, str) or len(project_id)>128 or not isinstance(repo_path, str) or len(repo_path)>4096 or not isinstance(workers, list) or len(workers)>3 or not all(isinstance(w, str) and len(w)<65 for w in workers):
                self._send_error(400, 'Invalid mission metadata')
                return

            # Generate mission ID
            import datetime, uuid
            mission_id = f"mission-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
            mission = db.create_mission(
                mission_id=mission_id,
                project_id=project_id,
                repository_path=repo_path,
                goal=goal,
                state=MissionState.QUEUED.value,
                assigned_workers=workers,
                prompt=body.get("prompt") or goal,
            )
            self._send_json(201, mission)
            return

        elif path.startswith("/missions/") and path.endswith("/cancel"):
            mission_id = path.split("/")[2]
            sm = StateMachine(db)
            try:
                updated = sm.transition(mission_id, MissionState.CANCELLED, error_info="User cancelled via API")
                self._send_json(200, updated)
            except Exception as e:
                self._send_error(400, str(e))
            return

        elif path.startswith("/missions/") and path.endswith("/resume"):
            mission_id = path.split("/")[2]
            sm = StateMachine(db)
            try:
                updated = sm.transition(mission_id, MissionState.RECOVERING, error_info="Resumed via API")
                self._send_json(200, updated)
            except Exception as e:
                self._send_error(400, str(e))
            return

        elif path == "/memory":
            import uuid
            mem_id = body.get("memory_id") or f"mem-{uuid.uuid4().hex[:8]}"
            required = ["project_id", "repository_id", "memory_type", "title", "content", "source_type"]
            for r in required:
                if not body.get(r):
                    self._send_error(400, f"Missing required memory field: '{r}'")
                    return
            saved_id = db.save_memory(
                memory_id=mem_id,
                project_id=body["project_id"],
                repository_id=body["repository_id"],
                memory_type=body["memory_type"],
                title=body["title"],
                content=body["content"],
                source_type=body["source_type"],
                source_reference=body.get("source_reference"),
                source_commit=body.get("source_commit"),
                confidence=float(body.get("confidence", 1.0)),
                sensitivity=body.get("sensitivity", "normal"),
            )
            self._send_json(201, {"memory_id": saved_id, "status": "saved"})
            return

        self._send_error(404, f"Path '{path}' not found")


class ACSServer(ThreadingHTTPServer):
    """Custom HTTP Server holding shared database connection and worker registry."""

    def __init__(self, host: str, port: int, db: DatabaseManager, auth_token: str):
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("API binding must be loopback")
        super().__init__((host, port), ACSRequestHandler)
        self.db = db
        self.auth_token = auth_token

    def get_worker_statuses(self) -> Any:
        """Returns verified real statuses of workers from WorkerRegistry."""
        try:
            from .worker_adapters import WorkerRegistry
            reg = WorkerRegistry()
            return reg.get_all_statuses()
        except Exception as e:
            return [{"name": "unknown", "status": "ERROR", "details": str(e)}]

