"""CLOUD_REAL policy/process/SQLite checks; no real worker or laptop services."""

import json
from pathlib import Path
import subprocess
import sys
import socket
import signal

import pytest

from acs_team.auth import get_or_create_auth_token
from acs_team.db import DatabaseManager
from acs_team.human_approval import ApprovalStatus, HumanApprovalGate
from acs_team.mcp_registry import MCPPermissionError, MCPRegistry, PathEscapeError
from acs_team.runtime_control import RuntimeControl
from acs_team.security import contained_path, load_protected_paths, redact, run_verification, sandbox_argv, verification_argv
from acs_team.supervision import ProcessSupervisor
from acs_team.resilience import CircuitBreaker, FailureKind, RetryPolicy, classify
from acs_team.watchdog import notify


def test_shipped_protected_policy_and_empty_policy_rejection():
    root = Path(__file__).parents[1]
    shipped = root / "acs_team/defaults.json"
    assert json.loads(shipped.read_text()) == json.loads((root / "config/defaults.json").read_text())
    assert any("autonomous-coding-system" in p for p in json.loads(shipped.read_text())["protected_paths"])
    with pytest.raises(ValueError):
        load_protected_paths(shipped, "[]")


@pytest.mark.parametrize("name", ["../outside", "/outside", ".git/hooks/pre-commit", ".github/workflows/inject.yml", "a/../../outside"])
def test_path_policy_rejects_escapes_and_controls(tmp_path, name):
    with pytest.raises(PermissionError):
        contained_path(tmp_path, name)


def test_symlink_escape_and_configured_protected_path(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError):
        contained_path(workspace, "link/value")
    with pytest.raises(PermissionError):
        contained_path(workspace, "protected/file", (workspace / "protected",))


def test_redaction_covers_nested_values_headers_and_url_userinfo():
    # Reserved .invalid host and fixed dummy values; offline redaction fixture.
    sample = {"token": "synthetic-fixture", "items": ["Bearer synthetic-fixture", "https://fixture:fixture@example.invalid/path"]}  # pragma: allowlist secret
    result = redact(sample)
    assert "synthetic-fixture" not in json.dumps(result)
    assert "fixture:fixture" not in json.dumps(result)
    assert result["token"] == "[REDACTED]"


@pytest.mark.parametrize("command", ["pytest; echo injected", "sh -c pytest", "python -c print(1)", "pytest --collect-only", "pytest | cat"])
def test_shell_and_nonverification_commands_denied(command):
    with pytest.raises(PermissionError):
        verification_argv(command)


def test_real_verification_counts_tests_and_rejects_empty_suite(tmp_path):
    assert not run_verification("pytest", tmp_path)["passed"]
    (tmp_path / "calculator.py").write_text("def add(a,b): return a+b\n")
    (tmp_path / "test_calculator.py").write_text("from calculator import add\ndef test_add(): assert add(2,3)==5\n")
    result = run_verification("pytest", tmp_path)
    assert result["passed"] and result["counts"]["passed"] == 1


def test_sandbox_policy_does_not_bind_root_or_state(tmp_path):
    command = sandbox_argv(tmp_path / "work", ["python", "-V"], home=tmp_path / "home")
    assert "--unshare-all" in command and "--share-net" not in command
    assert ["--ro-bind", "/", "/"] != command[:3]
    assert all(command[i+1] != "/" for i, value in enumerate(command) if value in {"--bind", "--ro-bind"})
    with pytest.raises(PermissionError):
        sandbox_argv(tmp_path / "work", ["python"], home=tmp_path / "home",
                     private_paths=(tmp_path / "work/evidence.key",))


def test_supervisor_cancels_group_and_escaped_child_without_signalling_sibling(tmp_path):
    marker = tmp_path / "child.pid"
    source = tmp_path / "parent.py"
    source.write_text("import subprocess,os,pathlib,threading\n"
                      "child=subprocess.Popen(['sleep','30'],start_new_session=True)\n"
                      f"pathlib.Path({str(marker)!r}).write_text(str(child.pid))\n"
                      "threading.Event().wait(30)\n")
    unrelated = subprocess.Popen(["sleep", "30"])
    try:
        result = ProcessSupervisor().run([sys.executable, str(source)], tmp_path, timeout=5,
                                         cancelled=marker.exists)
        assert result["reason"] == "cancelled"
        child_pid = int(marker.read_text())
        stat = Path(f"/proc/{child_pid}/stat")
        # PID 1 may retain dead grandchildren as zombies in this cloud runtime.
        assert not stat.exists() or stat.read_text().rsplit(")",1)[1].split()[0] == "Z"
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)


def test_supervisor_bounds_output_and_excludes_ambient_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_CREDENTIAL_BINDING", "synthetic-fixture")
    supervisor = ProcessSupervisor(output_limit=4096)
    result = supervisor.run([sys.executable, "-c", "print('x'*1000000)"], tmp_path)
    assert result["reason"] == "output_limit" and len(result["stdout"]) <= 4096
    result = supervisor.run([sys.executable, "-c", "import os;print('TEST_CREDENTIAL_BINDING' in os.environ)"], tmp_path)
    assert result["stdout"].strip() == "False"


def test_supervisor_timeout_and_memory_limit(tmp_path):
    result = ProcessSupervisor().run([sys.executable, "-c", "import threading;threading.Event().wait(30)"], tmp_path, timeout=0.3)
    assert result["reason"] == "timeout" and result["exit_code"] != 0
    limited = ProcessSupervisor().run([sys.executable, "-c", "data=bytearray(300*1024*1024)"], tmp_path, memory_mb=96)
    assert limited["exit_code"] != 0 and "MemoryError" in limited["output"]
    cpu = ProcessSupervisor().run([sys.executable, "-c", "while True: pass"], tmp_path, cpu_seconds=1, timeout=5)
    assert cpu["exit_code"] in {-signal.SIGXCPU, -signal.SIGKILL}


def test_emergency_stop_is_persistent_and_preserves_history(tmp_path):
    db = DatabaseManager(tmp_path / "state.db")
    db.create_mission("mission", "project", str(tmp_path), "preserve", state="RUNNING")
    RuntimeControl(db).stop()
    reloaded = RuntimeControl(DatabaseManager(tmp_path / "state.db"))
    assert reloaded.stopped() and db.get_mission("mission")["state"] == "CANCELLED"
    assert db.get_mission("mission")["goal"] == "preserve"
    with pytest.raises(PermissionError):
        reloaded.require_dispatch()
    with pytest.raises(PermissionError):
        reloaded.resume()
    reloaded.resume(operator_confirmed=True)
    reloaded.require_dispatch()


def test_existing_invalid_auth_is_never_silently_replaced(tmp_path):
    path = tmp_path / "auth.token"
    path.write_text("invalid-fixture")
    path.chmod(0o600)
    with pytest.raises(ValueError):
        get_or_create_auth_token(path)
    assert path.read_text() == "invalid-fixture"


def test_approval_is_bound_to_entire_operation(tmp_path):
    db = DatabaseManager(tmp_path / "state.db")
    db.create_mission("mission", "project", str(tmp_path), "approval")
    gate = HumanApprovalGate(db)
    approval = gate.request_approval("mission", "merge_to_main", str(tmp_path), "commit")
    gate.resolve_approval(approval, ApprovalStatus.APPROVED, "operator")
    assert gate.is_operation_approved(approval, mission_id="mission", action="merge_to_main", commit_sha="commit", target_repo=str(tmp_path))
    assert not gate.is_operation_approved(approval, commit_sha="other")
    assert not gate.is_operation_approved(approval, action="publish")


def test_mcp_unknown_role_allowlist_and_control_path_denial(tmp_path):
    registry = MCPRegistry()
    with pytest.raises(MCPPermissionError):
        registry.authorize("write_file", "untrusted")
    with pytest.raises(MCPPermissionError):
        registry.execute_tool("read_file", {"file_path":"safe"}, "worker", str(tmp_path), allowed_tools=set())
    with pytest.raises(PathEscapeError):
        registry.execute_tool("write_file", {"file_path":".git/hooks/run", "content":"ignored"}, "worker", str(tmp_path))
    assert not registry.execute_tool("inspect_binary", {}, "worker", str(tmp_path))["success"]


def test_real_workers_are_not_verified_by_executable_or_profile_presence(tmp_path):
    from acs_team.worker_adapters import WorkerRegistry, WorkerUnverifiedError
    registry = WorkerRegistry()
    assert registry.list_available_workers() == []
    for name in ("codex-primary", "agy-google-a", "agy-google-b"):
        with pytest.raises(WorkerUnverifiedError):
            registry.get_worker(name).execute_task("fixture", "harmless", "harmless", tmp_path)


def test_periodic_backup_is_opt_in_and_interval_bounded(tmp_path, monkeypatch):
    from acs_team.daemon import ACSDaemon
    from acs_team.recovery import verify_backup
    database = tmp_path / "state.db"
    DatabaseManager(database).create_mission("fixture", "fixture", str(tmp_path), "preserve")
    monkeypatch.setattr("acs_team.daemon.DB_PATH", database)
    monkeypatch.setattr("acs_team.config.BACKUPS_DIR", tmp_path / "backups")
    daemon = object.__new__(ACSDaemon)
    daemon.last_backup = 0
    monkeypatch.delenv("ACS_ENABLE_PERIODIC_BACKUPS", raising=False)
    daemon._periodic_backup()
    assert not (tmp_path / "backups").exists()
    monkeypatch.setenv("ACS_ENABLE_PERIODIC_BACKUPS", "1")
    # Fresh CI VMs may have uptime below the backup interval. First backup is
    # due immediately; subsequent calls are interval bounded.
    monkeypatch.setattr("acs_team.daemon.time.monotonic", lambda: 10.0)
    daemon._periodic_backup()
    daemon._periodic_backup()
    backups = list((tmp_path / "backups").iterdir())
    assert len(backups) == 1 and verify_backup(backups[0])["integrity"] == "ok"


def test_circuit_and_retry_classification_with_injected_clock():
    now = [10.0]
    circuit = CircuitBreaker(threshold=2, cooldown=5, clock=lambda: now[0])
    assert classify(401) == FailureKind.AUTH and classify(429) == FailureKind.QUOTA
    circuit.failure(FailureKind.AUTH)
    assert not circuit.allow()
    now[0] = 15.0
    assert circuit.allow()
    circuit.success()
    assert circuit.failures == 0
    assert RetryPolicy().delay(0, lambda: 1.0) == 0.25
    assert RetryPolicy().delay(100, lambda: 1.0) == 5


@pytest.mark.simulated
def test_watchdog_message_with_fake_local_notify_socket(tmp_path, monkeypatch):
    target = str(tmp_path / "notify.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
        server.bind(target)
        server.settimeout(2)
        monkeypatch.setenv("NOTIFY_SOCKET", target)
        assert notify("WATCHDOG=1")
        assert server.recv(1024) == b"WATCHDOG=1"


@pytest.mark.simulated
@pytest.mark.parametrize("tampered", [False, True])
def test_actual_pipeline_integrates_only_after_guardian_and_keeps_source_branch(tmp_path, monkeypatch, tampered):
    from acs_team.autonomous_planner import AutonomousMissionPlanner
    from acs_team.evidence import EvidenceEngine
    from acs_team.worker_adapters import BaseWorker
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a,b): return 0\n")
    (repo / "test_calc.py").write_text("from calc import add\ndef test_add(): assert add(2,3)==5\n")
    for command in (["git","init","-b","main"], ["git","config","user.name","Fixture"],
                    ["git","config","user.email","fixture@example.invalid"], ["git","add","."],
                    ["git","commit","-m","Initial failing contract"]):
        subprocess.run(command, cwd=repo, check=True, capture_output=True)
    before = subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    class FakeWorker(BaseWorker):
        def execute_task(self, task_id, goal, instructions, worktree_path, **kwargs):
            (worktree_path / "calc.py").write_text("def add(a,b): return a+b\n")
            return {"success": True, "changed_files": ["calc.py"]}
    class Registry:
        def list_available_workers(self):
            return ["codex-primary"]
        def get_worker(self, name):
            return FakeWorker(name)
    db = DatabaseManager(tmp_path / "state.db")
    planner = AutonomousMissionPlanner(db, Registry())
    monkeypatch.setattr(planner.planner, "plan_task", lambda *a, **k: {
        "task_name":"fix", "goal_summary":"Correct addition", "files_to_modify":["calc.py"],
        "instructions":"Fix addition", "test_command":f"{sys.executable} -m pytest",
    })
    if tampered:
        monkeypatch.setattr(EvidenceEngine, "verify_evidence", lambda *a, **k: False)
    result = planner.run_mission("fixture-mission", "Fix addition", repo)
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip() == before
    integrated = subprocess.check_output(["git","rev-parse","acsai/mission/fixture-mission"],cwd=repo,text=True).strip()
    if tampered:
        assert result["status"] == "BLOCKED" and integrated == before
    else:
        assert result["status"] == "COMPLETED" and integrated != before
        assert db.get_mission("fixture-mission")["commit_sha"] == integrated


def test_guard_reaps_escaped_orphan_even_when_worker_parent_exits(tmp_path):
    import os
    marker=tmp_path/'orphan.pid'
    source=tmp_path/'worker.py'
    source.write_text('import subprocess,sys,pathlib\n'
                      'child=subprocess.Popen([sys.executable,"-c","import threading; threading.Event().wait(30)"],start_new_session=True)\n'
                      f'pathlib.Path({str(marker)!r}).write_text(str(child.pid))\n')
    result=ProcessSupervisor().run([sys.executable,str(source)],tmp_path,timeout=5)
    assert result['exit_code']==0 and result['reason']=='completed'
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()),0)
    root=Path(__file__).parents[1]
    assert (root/'acs_team/process_guard.py').read_bytes()==(root/'agpair/agpair/executors/process_guard.py').read_bytes()


def test_database_new_files_private_and_readonly_missing_is_nonmutating(tmp_path):
    database=tmp_path/'private'/'state.db'
    DatabaseManager(database)
    assert database.stat().st_mode & 0o777 == 0o600
    absent=tmp_path/'absent'/'state.db'
    with pytest.raises(FileNotFoundError):
        DatabaseManager(absent,read_only=True)
    assert not absent.parent.exists()
    linked=tmp_path/'alias.db';linked.symlink_to(database)
    with pytest.raises(PermissionError):
        DatabaseManager(linked)
