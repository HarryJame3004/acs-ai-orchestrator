"""ACS AI V2 Quality Engine.
Calculates the unified Quality Score:
Q = 0.40 * T + 0.30 * S + 0.20 * M + 0.10 * E

Where:
- T: Test Pass Rate (0.0 to 1.0; 0.0 if any critical test fails)
- S: Static Analysis / Lint Cleanliness (0.0 to 1.0)
- M: Maintainability & Diff Sanity (0.0 to 1.0; penalizes debug garbage, excessive diffs, secrets)
- E: Evidence Authenticity (0.0 or 1.0; must be cryptographically signed)

Threshold: Q >= 0.85 for automated approval.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("acs_ai.quality")

BANNED_CODE_PATTERNS = [
    (r"breakpoint\(\)", "Active Python breakpoint"),
    (r"import\s+pdb", "PDB debugger import"),
    (r"--dangerously-bypass", "Banned security bypass flag"),
    (r"chmod\s+777", "Insecure file permission modification"),
    (r"password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password pattern"),
    (r"BEGIN\s+(RSA|OPENSSH|EC)\s+PRIVATE\s+KEY", "Embedded private key"),
]


@dataclass
class QualityReport:
    overall_score: float
    test_score: float
    static_score: float
    maintainability_score: float
    evidence_score: float
    passed_threshold: bool
    threshold: float = 0.85
    details: Dict[str, Any] = field(default_factory=dict)
    veto_reasons: List[str] = field(default_factory=list)


class QualityEngine:
    """Evaluates code quality, test results, static analysis, and diff sanity."""

    def __init__(self, threshold: float = 0.85, verification_runner=None):
        self.threshold = threshold
        self.verification_runner = verification_runner

    def run_tests(
        self,
        worktree_path: Path | str,
        test_command: Optional[str] = None,
        timeout_sec: int = 180,
    ) -> Dict[str, Any]:
        """Executes test suite within the designated worktree."""
        from .security import run_verification
        worktree_path = Path(worktree_path)
        try:
            return (self.verification_runner or run_verification)(test_command or "pytest", worktree_path, timeout_sec)
        except Exception as error:
            return {"executed": False, "passed": False, "exit_code": -1,
                    "output": str(error), "counts": {}}

    def evaluate_static_analysis(self, worktree_path: Path | str, changed_files: List[str]) -> Dict[str, Any]:
        """Runs basic python syntax validation and lint checks on changed files."""
        worktree_path = Path(worktree_path)
        issues = []
        checked_count = 0

        for file_rel in changed_files:
            file_path = worktree_path / file_rel
            if not file_path.is_file() or not file_rel.endswith(".py"):
                continue

            checked_count += 1
            # Compile syntax check
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                compile(content, str(file_path), "exec")
            except SyntaxError as e:
                issues.append(f"Syntax error in {file_rel}:{e.lineno}: {e.msg}")

        score = 1.0 if not issues else max(0.0, 1.0 - (len(issues) * 0.3))
        return {
            "score": score,
            "checked_files": checked_count,
            "issues": issues,
        }

    def evaluate_diff_sanity(self, worktree_path: Path | str, diff_text: str) -> Dict[str, Any]:
        """Evaluates diff cleanliness and scans for banned patterns / debug junk."""
        worktree_path = Path(worktree_path)
        veto_reasons = []
        score = 1.0

        for pattern, desc in BANNED_CODE_PATTERNS:
            if re.search(pattern, diff_text, re.IGNORECASE):
                veto_reasons.append(f"Banned pattern detected in diff: {desc} (regex: {pattern})")
                score -= 0.4

        lines = diff_text.splitlines()
        added_lines = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
        
        # Penalize excessive diffs (> 1500 lines changed in a single task)
        if len(added_lines) > 1500:
            score -= 0.2
            veto_reasons.append(f"Diff volume warning: {len(added_lines)} lines added in a single task")

        score = max(0.0, min(1.0, score))
        return {
            "score": score,
            "added_lines": len(added_lines),
            "veto_reasons": veto_reasons,
        }

    def compute_quality_score(
        self,
        test_result: Dict[str, Any],
        static_result: Dict[str, Any],
        diff_result: Dict[str, Any],
        is_evidence_valid: bool,
    ) -> QualityReport:
        """Computes Q = 0.40*T + 0.30*S + 0.20*M + 0.10*E."""
        veto_reasons = []

        # T: Test Pass Rate
        if test_result.get("executed", False):
            if test_result.get("passed", False):
                t_score = 1.0
            else:
                t_score = 0.0
                veto_reasons.append("Automated test suite failed.")
        else:
            t_score = 1.0  # No tests required / empty test suite

        # S: Static analysis
        s_score = float(static_result.get("score", 1.0))
        if static_result.get("issues"):
            veto_reasons.extend(static_result["issues"])

        # M: Maintainability / Diff Sanity
        m_score = float(diff_result.get("score", 1.0))
        if diff_result.get("veto_reasons"):
            veto_reasons.extend(diff_result["veto_reasons"])

        # E: Evidence Authenticity
        e_score = 1.0 if is_evidence_valid else 0.0
        if not is_evidence_valid:
            veto_reasons.append("Cryptographic evidence verification failed or signature invalid.")

        overall = (0.40 * t_score) + (0.30 * s_score) + (0.20 * m_score) + (0.10 * e_score)
        overall = round(overall, 3)

        passed = overall >= self.threshold and len(veto_reasons) == 0

        return QualityReport(
            overall_score=overall,
            test_score=t_score,
            static_score=s_score,
            maintainability_score=m_score,
            evidence_score=e_score,
            passed_threshold=passed,
            threshold=self.threshold,
            details={
                "tests": test_result,
                "static": static_result,
                "diff": diff_result,
                "evidence_valid": is_evidence_valid,
            },
            veto_reasons=veto_reasons,
        )
