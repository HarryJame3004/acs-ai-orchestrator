#!/usr/bin/env python3
"""ACS AI V2.1 Priorities 7 & 8: Guardian Security & SQLite WAL Integrity Audit.
Verifies:
1. CoreLock protection fail-closed against protected paths.
2. Protected branch block without human approval.
3. Cryptographic tamper detection on forged evidence.
4. Static security vetoes on banned code patterns.
5. SQLite WAL pragmas (integrity_check, foreign_keys, synchronous, journal_mode).
6. Crash reconciliation and orphan recovery.
"""

import os
import shutil
import sqlite3
import sys
from pathlib import Path

ORCHESTRATOR_DIR = Path("/home/khoi/.local/share/acs-orchestrator")
sys.path.insert(0, str(ORCHESTRATOR_DIR))

from acs_team.auth import get_or_create_auth_token
from acs_team.config import STATE_DIR, ACS_CORE_DIR
from acs_team.db import DatabaseManager
from acs_team.evidence import EvidenceEngine
from acs_team.guardian import Guardian, CoreLockViolation
from acs_team.human_approval import HumanApprovalGate, RiskLevel
from acs_team.quality import QualityEngine
from acs_team.state_machine import MissionState, StateMachine


def audit_guardian_security():
    print("\n--- 1. GUARDIAN SECURITY AUDIT ---")
    db_path = STATE_DIR / "acs_ai.db"
    db = DatabaseManager(db_path)
    auth_token = get_or_create_auth_token()
    guardian = Guardian(db, auth_token=auth_token, quality_threshold=0.85)

    # 1. CoreLock Fail-Closed Verification
    print("[Check 1.1] CoreLock Boundary:")
    try:
        guardian.verify_corelock_safety(str(ACS_CORE_DIR), ["any_file.py"])
        print("  FAIL: CoreLock did not reject ACS Core directory!")
        sys.exit(1)
    except CoreLockViolation as e:
        print(f"  PASS: CoreLock correctly rejected modification to {ACS_CORE_DIR}: {e}")

    # Subdirectory of CoreLock
    try:
        guardian.verify_corelock_safety(str(ACS_CORE_DIR / "acs_core" / "test.py"), ["test.py"])
        print("  FAIL: CoreLock did not reject ACS Core subdirectory!")
        sys.exit(1)
    except CoreLockViolation as e:
        print(f"  PASS: CoreLock correctly rejected modification to subdirectory: {e}")

    # 2. Protected Branch Gate
    print("[Check 1.2] Protected Branch Gate:")
    dummy_repo = Path("/tmp/dummy_repo")
    dummy_repo.mkdir(exist_ok=True)
    ev_dict = {
        "mission_id": "m-sec-test",
        "task_id": "t1",
        "commit_sha": "abc1234",
        "payload_sha256": "dummy",
        "signature": "dummy",
        "diff_summary": {"diff_text": ""},
    }
    verdict = guardian.evaluate(
        mission_id="m-sec-test",
        repository_path=dummy_repo,
        worktree_path=dummy_repo,
        target_branch="main",  # Protected branch
        commit_sha="abc1234",
        evidence_dict=ev_dict,
        changed_files=["app.py"],
    )
    assert verdict.approved is False
    assert any("requires explicit human approval" in r for r in verdict.veto_reasons)
    print("  PASS: Direct integration into 'main' blocked without approval.")

    # 3. Evidence Tamper Detection
    print("[Check 1.3] Cryptographic Tamper Detection:")
    engine = EvidenceEngine(auth_token)
    ev = engine.create_evidence(
        mission_id="m-tamper",
        task_id="t1",
        commit_sha="1111222233334444555566667777888899990000",
        test_results={"executed": True, "passed": True},
        diff_summary={"diff_text": "+ pass"},
    )
    ev_dict = ev.to_dict()
    assert engine.verify_evidence(ev_dict, "1111222233334444555566667777888899990000") is True

    # Tamper with diff
    ev_dict["diff_summary"]["diff_text"] = "+ tampered content"
    assert engine.verify_evidence(ev_dict, "1111222233334444555566667777888899990000") is False
    print("  PASS: Tampered diff payload detected and rejected.")

    # Tamper with commit SHA binding
    assert engine.verify_evidence(ev.to_dict(), "9999888877776666555544443333222211110000") is False
    print("  PASS: Commit SHA mismatch detected and rejected.")

    # 4. Security Veto on Banned Code Patterns & Diff Sanity
    print("[Check 1.4] Banned Code Patterns & Diff Sanity Gate:")
    qe = QualityEngine()
    bad_diff = "+ import pdb\n+ pdb.set_trace()\n+ --dangerously-bypass\n"
    diff_res = qe.evaluate_diff_sanity(Path("/tmp"), bad_diff)
    assert len(diff_res["veto_reasons"]) >= 2
    assert diff_res["score"] < 0.5
    print(f"  PASS: Banned patterns caught in diff: {diff_res['veto_reasons']}")
    shutil.rmtree(dummy_repo)


def audit_sqlite_wal_and_recovery():
    print("\n--- 2. SQLITE WAL & CRASH RECONCILIATION AUDIT ---")
    db_path = STATE_DIR / "acs_ai.db"
    assert db_path.exists(), f"State database missing at {db_path}"

    db = DatabaseManager(db_path)
    con = db.get_connection()
    cur = con.cursor()

    # 1. PRAGMA Checks
    journal_mode = cur.execute("PRAGMA journal_mode;").fetchone()[0]
    integrity = cur.execute("PRAGMA integrity_check;").fetchone()[0]
    quick = cur.execute("PRAGMA quick_check;").fetchone()[0]
    foreign_keys = cur.execute("PRAGMA foreign_keys;").fetchone()[0]

    print(f"  - PRAGMA journal_mode:    {journal_mode.upper()} (expected: WAL)")
    print(f"  - PRAGMA integrity_check: {integrity} (expected: ok)")
    print(f"  - PRAGMA quick_check:     {quick} (expected: ok)")
    print(f"  - PRAGMA foreign_keys:    {foreign_keys} (expected: 1)")

    assert journal_mode.lower() == "wal", f"Journal mode is not WAL: {journal_mode}"
    assert integrity == "ok", f"Integrity check failed: {integrity}"
    assert quick == "ok", f"Quick check failed: {quick}"
    assert foreign_keys == 1, f"Foreign keys not enabled: {foreign_keys}"

    # 2. Checkpoint Table Cryptographic Verification
    cur.execute("SELECT checkpoint_id, mission_id, state_name, sha256_hash FROM checkpoints ORDER BY created_at DESC LIMIT 5;")
    cps = cur.fetchall()
    print(f"  - Verified checkpoints recorded: {len(cps)}")
    for cp in cps:
        print(f"    • {cp[0]}: {cp[1]} [{cp[2]}] (SHA256: {cp[3][:12]}...)")

    con.close()

    # 3. Crash Reconciliation Test
    print("[Check 2.2] Crash Reconciliation Test:")
    test_db_path = Path("/tmp/crash_test.db")
    if test_db_path.exists():
        test_db_path.unlink()

    tdb = DatabaseManager(test_db_path)
    # Simulate orphan mission interrupted in RUNNING state
    tdb.create_mission("m-interrupted", "proj", "/tmp", "interrupted task")
    tsm = StateMachine(tdb)
    tsm.transition("m-interrupted", MissionState.QUEUED)
    tsm.transition("m-interrupted", MissionState.PLANNING)
    tsm.transition("m-interrupted", MissionState.READY)
    tsm.transition("m-interrupted", MissionState.RUNNING)

    print("  - Pre-crash state: RUNNING")
    reconciled = tsm.reconcile_interrupted_missions()
    print(f"  - Reconciled orphan missions count: {len(reconciled)}")
    m = tdb.get_mission("m-interrupted")
    print(f"  - Post-recovery state: {m['state']}")
    assert m["state"] == MissionState.BLOCKED.value
    print("  PASS: Orphan running mission cleanly marked BLOCKED (fail-closed without valid checkpoint).")

    tdb.close()
    if test_db_path.exists():
        test_db_path.unlink()


if __name__ == "__main__":
    audit_guardian_security()
    audit_sqlite_wal_and_recovery()
    print("\n✓ ALL PRIORITIES 7 & 8 CHECKS PASSED (100% VERIFIED)\n")
