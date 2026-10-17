"""ACS AI V2 Guardian & Security Gatekeeper Engine.
Acts as the independent, un-bypassable boundary between worker pull requests/worktrees
and the integrated repository.

Enforces:
1. CoreLock Protection (strict read-only isolation for /home/khoi/autonomous-coding-system).
2. Protected branch protection (no direct pushes/merges to main, master, release, production).
3. Cryptographic evidence verification (HMAC-SHA256, commit SHA integrity).
4. Strict Quality Score verification (Q >= 0.85, 0 test failures, 0 banned patterns).
5. Mandatory Human Approval for high-risk / release operations.
6. Tamper-proof audit logging into SQLite WAL.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .db import DatabaseManager
from .evidence import EvidenceEngine
from .human_approval import HumanApprovalGate, RiskLevel
from .quality import QualityEngine, QualityReport

logger = logging.getLogger("acs_ai.guardian")

PROTECTED_BRANCHES = {"main", "master", "release", "production", "stable"}
CORELOCK_PROTECTED_PATHS = ["/home/khoi/autonomous-coding-system"]


class CoreLockViolation(Exception):
    """Raised when an operation attempts to mutate CoreLock-protected repositories."""
    pass


@dataclass
class GuardianVerdict:
    approved: bool
    mission_id: str
    target_branch: str
    commit_sha: str
    quality_score: float
    evidence_verified: bool
    human_approval_required: bool
    human_approved: bool
    veto_reasons: List[str] = field(default_factory=list)
    quality_report: Optional[QualityReport] = None


class Guardian:
    """The master gatekeeper enforcing fail-closed security and quality standards."""

    def __init__(
        self,
        db: DatabaseManager,
        auth_token: str,
        quality_threshold: float = 0.85,
    ):
        self.db = db
        self.auth_token = auth_token
        self.evidence_engine = EvidenceEngine(auth_token)
        self.quality_engine = QualityEngine(threshold=quality_threshold)
        self.approval_gate = HumanApprovalGate(db)

    def verify_corelock_safety(self, repository_path: str, changed_files: List[str]) -> None:
        """Verifies that the target path does not violate CoreLock boundaries."""
        canonical_repo = os.path.realpath(repository_path)
        for protected in CORELOCK_PROTECTED_PATHS:
            canonical_protected = os.path.realpath(protected)
            if canonical_repo == canonical_protected or canonical_repo.startswith(canonical_protected + "/"):
                raise CoreLockViolation(
                    f"CoreLock Violation: Attempted modification to protected core repository '{canonical_repo}'."
                )

    def evaluate(
        self,
        mission_id: str,
        repository_path: Path,
        worktree_path: Path,
        target_branch: str,
        commit_sha: str,
        evidence_dict: Dict[str, Any],
        changed_files: List[str],
        test_command: Optional[str] = None,
        approval_id: Optional[str] = None,
        is_release_attempt: bool = False,
    ) -> GuardianVerdict:
        """Runs the complete verification matrix. Fails closed on any defect."""
        veto_reasons: List[str] = []
        human_approval_required = False
        human_approved = False

        # 1. CoreLock Protection
        try:
            self.verify_corelock_safety(str(repository_path), changed_files)
        except CoreLockViolation as e:
            veto_reasons.append(str(e))

        # 2. Protected Branch Gate
        if target_branch in PROTECTED_BRANCHES or is_release_attempt:
            human_approval_required = True
            if not approval_id or not self.approval_gate.is_operation_approved(approval_id):
                veto_reasons.append(
                    f"Direct integration into protected branch '{target_branch}' requires explicit human approval."
                )
            else:
                human_approved = True

        # 3. Cryptographic Evidence Verification
        evidence_valid = self.evidence_engine.verify_evidence(
            evidence_dict=evidence_dict,
            expected_commit_sha=commit_sha,
        )
        if not evidence_valid:
            veto_reasons.append("Cryptographic evidence verification failed: signature or commit SHA mismatch.")

        # 4. Independent Test Execution & Quality Evaluation
        test_res = self.quality_engine.run_tests(worktree_path, test_command=test_command)
        static_res = self.quality_engine.evaluate_static_analysis(worktree_path, changed_files)

        diff_text = evidence_dict.get("diff_summary", {}).get("diff_text", "")
        diff_res = self.quality_engine.evaluate_diff_sanity(worktree_path, diff_text)

        quality_report = self.quality_engine.compute_quality_score(
            test_result=test_res,
            static_result=static_res,
            diff_result=diff_res,
            is_evidence_valid=evidence_valid,
        )

        if not quality_report.passed_threshold:
            veto_reasons.append(
                f"Quality Score {quality_report.overall_score} fell below required threshold {self.quality_engine.threshold}"
            )
            veto_reasons.extend(quality_report.veto_reasons)

        approved = len(veto_reasons) == 0

        # 5. Tamper-Proof Audit Event Logging
        self.db.record_audit_event(
            mission_id=mission_id,
            task_id=evidence_dict.get("task_id"),
            actor="guardian",
            action="GUARDIAN_APPROVED" if approved else "GUARDIAN_VETOED",
            details={
                "target_branch": target_branch,
                "commit_sha": commit_sha,
                "quality_score": quality_report.overall_score,
                "veto_reasons": veto_reasons,
                "approved": approved,
            },
        )

        logger.info(
            f"Guardian Verdict for mission '{mission_id}' on '{target_branch}': {'APPROVED' if approved else 'VETOED'} (Score: {quality_report.overall_score})"
        )

        return GuardianVerdict(
            approved=approved,
            mission_id=mission_id,
            target_branch=target_branch,
            commit_sha=commit_sha,
            quality_score=quality_report.overall_score,
            evidence_verified=evidence_valid,
            human_approval_required=human_approval_required,
            human_approved=human_approved,
            veto_reasons=veto_reasons,
            quality_report=quality_report,
        )
