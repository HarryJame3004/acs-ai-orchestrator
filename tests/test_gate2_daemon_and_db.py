"""Gate 2 Verification Suite: SQLite Engine, State Machine, Checkpointing, and Local API."""

import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
import pytest

from acs_team.api_server import ACSServer
from acs_team.auth import get_or_create_auth_token, verify_token
from acs_team.db import DatabaseManager
from acs_team.state_machine import InvalidStateTransitionError, MissionState, StateMachine


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_acs.db"
    return DatabaseManager(db_file, read_only=False)


def test_db_pragmas_and_schema(temp_db):
    con = temp_db.get_connection()
    journal_mode = con.execute("PRAGMA journal_mode;").fetchone()[0]
    foreign_keys = con.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert journal_mode.upper() == "WAL"
    assert foreign_keys == 1

    # Verify tables exist
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    assert "missions" in tables
    assert "tasks" in tables
    assert "checkpoints" in tables
    assert "audit_events" in tables
    assert "memories" in tables
    assert "memories_fts" in tables


def test_state_machine_valid_transitions(temp_db):
    sm = StateMachine(temp_db)
    m = temp_db.create_mission(
        mission_id="m-test-1",
        project_id="proj-1",
        repository_path="/tmp/repo",
        goal="Test goal",
    )
    assert m["state"] == MissionState.CREATED.value

    # Valid transition to QUEUED
    m2 = sm.transition("m-test-1", MissionState.QUEUED)
    assert m2["state"] == MissionState.QUEUED.value

    # Valid transition to PLANNING
    m3 = sm.transition("m-test-1", MissionState.PLANNING)
    assert m3["state"] == MissionState.PLANNING.value

    # Valid transition to READY
    m4 = sm.transition("m-test-1", MissionState.READY)
    assert m4["state"] == MissionState.READY.value

    # Valid transition to RUNNING
    m5 = sm.transition("m-test-1", MissionState.RUNNING)
    assert m5["state"] == MissionState.RUNNING.value


def test_state_machine_invalid_transition_fails_closed(temp_db):
    sm = StateMachine(temp_db)
    temp_db.create_mission(
        mission_id="m-invalid",
        project_id="proj-1",
        repository_path="/tmp/repo",
        goal="Test invalid transition",
    )

    # CREATED -> COMPLETED is illegal and must raise error
    with pytest.raises(InvalidStateTransitionError):
        sm.transition("m-invalid", MissionState.COMPLETED)


def test_cryptographic_checkpoint_integrity(temp_db):
    sm = StateMachine(temp_db)
    temp_db.create_mission(
        mission_id="m-chk",
        project_id="proj-1",
        repository_path="/tmp/repo",
        goal="Test checkpointing",
    )
    sm.transition("m-chk", MissionState.QUEUED)

    # Transition with payload
    payload = {"step": 1, "worker": "codex-primary", "diff": "+print('hello')"}
    sm.transition("m-chk", MissionState.PLANNING, checkpoint_payload=payload)

    chk = temp_db.get_latest_checkpoint("m-chk")
    assert chk is not None
    assert chk["valid"] is True
    assert chk["payload"] == payload

    # Tamper with payload in DB directly and assert valid becomes False
    with temp_db.get_connection() as con:
        con.execute("UPDATE checkpoints SET payload_json = '{\"tampered\": true}' WHERE mission_id = 'm-chk'")
    tampered_chk = temp_db.get_latest_checkpoint("m-chk")
    assert tampered_chk["valid"] is False


def test_crash_reconciliation(temp_db):
    sm = StateMachine(temp_db)
    # Create mission that was left in RUNNING with a checkpoint
    temp_db.create_mission("m-crash-1", "p1", "/tmp", "Interrupted job 1")
    sm.transition("m-crash-1", MissionState.QUEUED)
    sm.transition("m-crash-1", MissionState.PLANNING)
    sm.transition("m-crash-1", MissionState.READY)
    sm.transition("m-crash-1", MissionState.RUNNING, checkpoint_payload={"safe": True})

    # Create mission left in RUNNING without a checkpoint
    temp_db.create_mission("m-crash-2", "p1", "/tmp", "Interrupted job 2")
    sm.transition("m-crash-2", MissionState.QUEUED)
    sm.transition("m-crash-2", MissionState.PLANNING)
    sm.transition("m-crash-2", MissionState.READY)
    sm.transition("m-crash-2", MissionState.RUNNING)

    reconciled = sm.reconcile_interrupted_missions()
    assert len(reconciled) == 2

    m1 = temp_db.get_mission("m-crash-1")
    m2 = temp_db.get_mission("m-crash-2")
    assert m1["state"] == MissionState.RECOVERING.value
    assert m2["state"] == MissionState.BLOCKED.value


def test_local_api_server(tmp_path):
    db_file = tmp_path / "api_test.db"
    db = DatabaseManager(db_file, read_only=False)
    token = get_or_create_auth_token(tmp_path / "auth.token")

    # Pick an ephemeral test port
    test_port = 20135
    server = ACSServer("127.0.0.1", test_port, db, token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)

    base_url = f"http://127.0.0.1:{test_port}"

    try:
        # 1. GET /health (unauthenticated)
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            assert data["status"] == "ok"
            assert data["daemon"] == "acs-ai-daemon"

        # 2. GET /status without auth -> 401
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base_url}/status")
        assert exc_info.value.code == 401

        # 3. GET /status with wrong token -> 403
        req_bad = urllib.request.Request(
            f"{base_url}/status", headers={"Authorization": "Bearer wrong_token"}
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req_bad)
        assert exc_info.value.code == 403

        # 4. GET /status with valid token -> 200
        req_good = urllib.request.Request(
            f"{base_url}/status", headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req_good) as resp:
            data = json.loads(resp.read().decode())
            assert data["status"] == "online"
            assert "workers" in data

        # 5. POST /missions -> 201
        payload = json.dumps({"goal": "Build persistent test mission"}).encode("utf-8")
        req_post = urllib.request.Request(
            f"{base_url}/missions",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req_post) as resp:
            assert resp.status == 201
            m = json.loads(resp.read().decode())
            assert m["state"] == "QUEUED"
            mid = m["mission_id"]

        # 6. GET /missions/{id} -> 200
        req_get_m = urllib.request.Request(
            f"{base_url}/missions/{mid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req_get_m) as resp:
            m_detail = json.loads(resp.read().decode())
            assert m_detail["mission_id"] == mid
            assert m_detail["state"] == "QUEUED"

    finally:
        server.shutdown()
        server.server_close()
