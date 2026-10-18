"""ACS AI V2 Daemon Client & Health Checker.
Dynamically inspects daemon health via HTTP /health and process state.
Handles RUNNING, UNHEALTHY, and STOPPED states separately.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .config import API_HOST, API_PORT, PID_FILE

logger = logging.getLogger("acs_ai.daemon_client")


def check_daemon_health(
    host: str = API_HOST,
    port: int = API_PORT,
    timeout_sec: float = 1.5,
) -> Dict[str, Any]:
    """Dynamically checks daemon health via HTTP /health and process state."""
    url = f"http://{host}:{port}/health"
    http_data: dict[str, Any] = {}
    is_http_ok = False
    error_msg = None

    # 1. Probe HTTP /health endpoint
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "acsai-client/2.1"})
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status == 200:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError("Invalid health response")
                http_data = parsed
                if http_data.get("status") == "ok":
                    is_http_ok = True
    except urllib.error.URLError as e:
        error_msg = str(e.reason)
    except Exception as e:
        error_msg = str(e)

    # 2. Check PID file and process existence
    pid: Optional[int] = None
    process_alive = False
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            process_alive = True
        except (ValueError, ProcessLookupError, PermissionError):
            process_alive = False

    # 3. Check systemd user service state
    systemd_active = False
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-active", "acs-ai.service"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        systemd_active = res.stdout.strip() == "active"
        if systemd_active and pid is None:
            try:
                res_pid = subprocess.run(
                    ["systemctl", "--user", "show", "acs-ai.service", "--property", "MainPID"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                )
                for line in res_pid.stdout.splitlines():
                    if line.startswith("MainPID="):
                        val = int(line.split("=", 1)[1].strip())
                        if val > 0:
                            pid = val
            except Exception:
                pass
    except Exception:
        pass

    # 4. Synthesize verified state
    if is_http_ok:
        return {
            "status": "RUNNING",
            "running": True,
            "healthy": True,
            "endpoint": f"{host}:{port}",
            "pid": pid,
            "version": http_data.get("version", "2.1") if http_data else "2.1",
            "db": http_data.get("db", "connected") if http_data else "connected",
            "systemd_active": systemd_active,
            "details": f"Health: OK | Database: {str(http_data.get('db') or 'connected').upper()}",
        }
    elif process_alive or systemd_active:
        return {
            "status": "UNHEALTHY",
            "running": True,
            "healthy": False,
            "endpoint": f"{host}:{port}",
            "pid": pid,
            "systemd_active": systemd_active,
            "details": f"Process running but API unresponsive: {error_msg}",
        }
    else:
        return {
            "status": "STOPPED",
            "running": False,
            "healthy": False,
            "endpoint": f"{host}:{port}",
            "pid": None,
            "systemd_active": False,
            "details": f"Socket/Port {port} idle",
        }
