"""Tests for Gate 5: QualityEngine, EvidenceEngine, HumanApprovalGate, and Guardian.
Covers both positive validation and negative security attack vectors.
"""

import os
import shutil
import tempfile
import subprocess
from pathlib import Path
import pytest

from acs_team.db import DatabaseManager
from acs_team.evidence import EvidenceEngine
from acs_team.guardian import Guardian
from acs_team.human_approval import HumanApprovalGate, HumanApprovalError, RiskLevel, ApprovalStatus
from acs_team.quality import QualityEngine


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    db.close()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def temp_worktree():
    dir_path = tempfile.mkdtemp(prefix="acs_test_wt_g5_")
    folder = Path(dir_path)
    (folder / "module.py").write_text("def answer(): return 42\n")
    (folder / "test_module.py").write_text("from module import answer\ndef test_contract(): assert answer() == 42\n")
    subprocess.run(["git", "init", "-b", "main"], cwd=folder, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=folder, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=folder, check=True)
    subprocess.run(["git", "add", "."], cwd=folder, check=True)
    subprocess.run(["git", "commit", "-m", "Fixture contract"], cwd=folder, check=True, capture_output=True)
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)


def test_quality_engine_scoring_and_vetoes(temp_worktree):
    engine = QualityEngine(threshold=0.85)

    # 1. Perfect pass
    test_res = {"executed": True, "passed": True, "exit_code": 0}
    static_res = {"score": 1.0, "issues": []}
    diff_res = {"score": 1.0, "veto_reasons": []}
    report = engine.compute_quality_score(test_res, static_res, diff_res, is_evidence_valid=True)
    assert report.overall_score == 1.0
    assert report.passed_threshold is True
    assert len(report.veto_reasons) == 0

    # 2. Failing tests: T=0, score drops to 0.60, vetoed
    fail_test_res = {"executed": True, "passed": False, "exit_code": 1}
    fail_report = engine.compute_quality_score(fail_test_res, static_res, diff_res, is_evidence_valid=True)
    assert fail_report.overall_score == 0.60
    assert fail_report.passed_threshold is False
    assert any("test suite failed" in v for v in fail_report.veto_reasons)

    # 3. Diff sanity detects banned patterns
    banned_diff = "+ import pdb\n+ breakpoint()\n+ os.system('chmod 777 /tmp')"
    diff_eval = engine.evaluate_diff_sanity(temp_worktree, banned_diff)
    assert diff_eval["score"] < 1.0
    assert len(diff_eval["veto_reasons"]) >= 3


def test_evidence_engine_integrity():
    auth_token = "secret-orchestrator-token-12345"
    engine = EvidenceEngine(auth_token)
    commit_sha = "abcdef1234567890abcdef1234567890abcdef12"

    evidence = engine.create_evidence(
        mission_id="m-100",
        task_id="t-1",
        commit_sha=commit_sha,
        test_results={"passed": True, "exit_code": 0},
        diff_summary={"changed_files": ["app.py"]},
    )
    ev_dict = evidence.to_dict()

    # 1. Valid verification
    assert engine.verify_evidence(ev_dict, expected_commit_sha=commit_sha) is True

    # 2. Tampered commit SHA
    assert engine.verify_evidence(ev_dict, expected_commit_sha="9999999999999999999999999999999999999999") is False

    # 3. Tampered payload content
    tampered_dict = dict(ev_dict)
    tampered_dict["test_results"] = {"passed": False, "exit_code": 1}
    assert engine.verify_evidence(tampered_dict, expected_commit_sha=commit_sha) is False

    # 4. Tampered signature
    forged_dict = dict(ev_dict)
    forged_dict["signature"] = "deadbeef" * 8
    assert engine.verify_evidence(forged_dict, expected_commit_sha=commit_sha) is False


def test_human_approval_gate(temp_db, tmp_path):
    gate = HumanApprovalGate(temp_db)
    temp_db.create_mission(
        mission_id="m-200",
        project_id="test-proj",
        repository_path=str(tmp_path / "repo"),
        goal="Test approval gate",
    )
    
    # 1. Request approval
    appr_id = gate.request_approval(
        mission_id="m-200",
        action="merge_to_main",
        target_repo=str(tmp_path / "repo"),
        commit_sha="1111222233334444555566667777888899990000",
        risk_level=RiskLevel.HIGH,
    )
    assert appr_id.startswith("appr-")
    assert gate.is_operation_approved(appr_id) is False

    # 2. Worker attempting to approve MUST fail
    with pytest.raises(HumanApprovalError, match="forbidden from resolving"):
        gate.resolve_approval(appr_id, ApprovalStatus.APPROVED, resolved_by="codex-primary")

    # 3. Legitimate human approval
    success = gate.resolve_approval(appr_id, ApprovalStatus.APPROVED, resolved_by="user_khoi", reason="Code verified")
    assert success is True
    assert gate.is_operation_approved(appr_id) is True


def test_guardian_security_boundaries(temp_db, temp_worktree, tmp_path, monkeypatch):
    protected = tmp_path / "protected-core"
    monkeypatch.setattr("acs_team.guardian.CORELOCK_PROTECTED_PATHS", [str(protected)])
    auth_token = "guardian-secret-token-abcdef"
    guardian = Guardian(temp_db, auth_token=auth_token, quality_threshold=0.85)
    commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=temp_worktree, text=True).strip()

    temp_db.create_mission(
        mission_id="m-core-check",
        project_id="core-proj",
        repository_path=str(protected),
        goal="Check corelock",
    )
    temp_db.create_mission(
        mission_id="m-branch-check",
        project_id="branch-proj",
        repository_path=temp_worktree,
        goal="Check branch gate",
    )

    # Setup valid evidence
    ev = guardian.evidence_engine.create_evidence(
        mission_id="m-core-check",
        task_id="t-1",
        commit_sha=commit_sha,
        test_results={"executed": True, "passed": True},
        diff_summary={"diff_text": ""},
    )
    ev_dict = ev.to_dict()

    # 1. The disposable protected fixture must be vetoed
    verdict_core = guardian.evaluate(
        mission_id="m-core-check",
        repository_path=str(protected),
        worktree_path=temp_worktree,
        target_branch="acsai/mission/m-core-check",
        commit_sha=commit_sha,
        evidence_dict=ev_dict,
        changed_files=["core.py"],
    )
    assert verdict_core.approved is False
    assert any("CoreLock Violation" in v for v in verdict_core.veto_reasons)

    # 2. Protected Branch Gate: Merging directly to 'main' without approval MUST be vetoed
    safe_repo = temp_worktree
    ev_branch = guardian.evidence_engine.create_evidence(
        mission_id="m-branch-check",
        task_id="t-1",
        commit_sha=commit_sha,
        test_results={"executed": True, "passed": True},
        diff_summary={"diff_text": ""},
    )
    verdict_main = guardian.evaluate(
        mission_id="m-branch-check",
        repository_path=safe_repo,
        worktree_path=temp_worktree,
        target_branch="main",
        commit_sha=commit_sha,
        evidence_dict=ev_branch.to_dict(),
        changed_files=["module.py"],
    )
    assert verdict_main.approved is False
    assert any("requires explicit human approval" in v for v in verdict_main.veto_reasons)

    # 3. Permitted with human approval
    appr_id = guardian.approval_gate.request_approval(
        mission_id="m-branch-check",
        action="merge_to_main",
        target_repo=str(safe_repo),
        commit_sha=commit_sha,
        risk_level=RiskLevel.HIGH,
    )
    guardian.approval_gate.resolve_approval(appr_id, ApprovalStatus.APPROVED, resolved_by="user_khoi")

    verdict_approved = guardian.evaluate(
        mission_id="m-branch-check",
        repository_path=safe_repo,
        worktree_path=temp_worktree,
        target_branch="main",
        commit_sha=commit_sha,
        evidence_dict=ev_branch.to_dict(),
        changed_files=["module.py"],
        approval_id=appr_id,
    )
    assert verdict_approved.approved is True
    assert verdict_approved.human_approved is True
