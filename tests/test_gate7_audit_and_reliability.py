"""Gate 7 Verification Suite: Daemon Health Probing, Dynamic Test Tracking, and AGY Google B Isolation."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from acs_team.daemon_client import check_daemon_health
from acs_team.test_tracker import record_test_run, get_test_health
from acs_team.worker_adapters import AGYGoogleBWorker, WorkerRegistry
from acs_team.config import AGY_B_BIN, AGY_B_HOME


def test_test_tracker_roundtrip(tmp_path):
    tracker_file = tmp_path / "test_health.json"
    
    with patch("acs_team.test_tracker.TEST_HEALTH_FILE", tracker_file):
        # 1. Initially no record
        health = get_test_health("acs_core")
        assert health["verified"] is False
        assert health["status"] == "UNKNOWN"
        assert "NOT RECHECKED" in health["display"]
        
        # 2. Record passing test run
        rec = record_test_run(
            component="acs_core",
            total=362,
            passed=362,
            failed=0,
            duration_sec=14.2,
            notes="Full regression verification",
        )
        assert rec["passed"] == 362
        assert rec["status"] == "PASS"
        
        # 3. Read back
        health2 = get_test_health("acs_core")
        assert health2["verified"] is True
        assert health2["status"] == "PASS"
        assert health2["total"] == 362
        assert health2["passed"] == 362
        assert health2["failed"] == 0
        assert "362/362 PASS" in health2["display"]


def test_check_daemon_health_online():
    # When daemon is running on port 20129
    health = check_daemon_health(port=20129)
    assert health["status"] in ("RUNNING", "UNHEALTHY", "STOPPED")
    assert "running" in health
    assert "endpoint" in health
    assert "healthy" in health
    assert "details" in health


def test_check_daemon_health_offline():
    # Mock systemctl and PID file to simulate completely stopped state
    with patch("acs_team.daemon_client.PID_FILE", Path("/tmp/nonexistent_pid_file_test")), \
         patch("subprocess.run") as mock_sub:
        mock_sub.return_value = MagicMock(stdout="inactive\n")
        health = check_daemon_health(host="127.0.0.1", port=49999, timeout_sec=0.1)
        assert health["running"] is False
        assert health["healthy"] is False
        assert health["status"] == "STOPPED"
        assert "idle" in health["details"]


def test_agy_b_worker_isolation():
    worker = AGYGoogleBWorker()
    assert worker.worker_id == "agy-google-b"
    assert worker.agy_b_bin == Path(AGY_B_BIN)
    assert worker.agy_b_home == Path(AGY_B_HOME)
    
    # Verify environment isolation
    env = worker._build_env()
    assert env["HOME"] == str(AGY_B_HOME)
    assert "XDG_CONFIG_HOME" in env
    assert str(AGY_B_HOME) in env["XDG_CONFIG_HOME"]
    assert "XDG_DATA_HOME" in env
    assert str(AGY_B_HOME) in env["XDG_DATA_HOME"]


@pytest.mark.local_only(reason='Requires authenticated AGY B; no worker credentials are provisioned in cloud. Legacy assertion preserved; portable fake-worker coverage belongs to V2.3/V2.4.')
def test_all_three_workers_in_registry():
    registry = WorkerRegistry()
    available = registry.list_available_workers()
    assert "codex-primary" in available
    assert "agy-google-a" in available
    assert "agy-google-b" in available
    
    statuses = registry.get_all_statuses()
    worker_names = [s["name"] for s in statuses]
    assert "codex-primary" in worker_names
    assert "agy-google-a" in worker_names
    assert "agy-google-b" in worker_names
    
    for s in statuses:
        assert s["status"] == "READY"
        assert s["ready"] is True
