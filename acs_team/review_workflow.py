"""Bounded review/escalation artifacts and untrusted review intake; no execution."""

from __future__ import annotations

from .upgrade_schema import REVIEW_SQL

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import Field, model_validator

from .db import DatabaseManager
from .evidence import EvidenceEngine
from .recovery import new_directory, private_write
from .schemas import Data, Text, parse_data
from .security import redact


class Finding(Data):
    severity: Literal["BLOCKER", "HIGH", "MEDIUM", "LOW", "INFO"]
    requirement_id: Text
    description: Text
    suggested_action: Text
    evidence: list[Text] = Field(default_factory=list, max_length=16)


class ImportedReview(Data):
    verdict: Literal["PASS", "FIX_REQUIRED", "REPLAN"]
    findings: list[Finding] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def valid_verdict(self):
        if self.verdict == "PASS" and self.findings:
            raise ValueError("PASS cannot contain unresolved findings")
        data = json.dumps(self.model_dump()).casefold()
        if re.search(
            r"(ignore|bypass|disable|override).{0,40}(guardian|sandbox|approval|security policy|ownership)",
            data,
        ):
            raise ValueError("Imported review attempts to override protected policy")
        return self




def bounded(value, budget: int = 24576):
    """Always return valid JSON-compatible data and expose any truncation."""
    clean = redact(value)
    encoded = json.dumps(clean, ensure_ascii=True, sort_keys=True)
    if len(encoded) + 40 <= budget:
        return {"truncated": False, "data": clean}
    preview = encoded[: max(0, budget - 128)]
    while (
        len(
            json.dumps(
                {"truncated": True, "preview": preview + " [truncated]"},
                ensure_ascii=True,
            ).encode()
        )
        > budget
    ):
        preview = preview[: len(preview) // 2]
    return {"truncated": True, "preview": preview + " [truncated]"}


def escalation_reasons(
    mission: dict, events: list[dict], no_progress_rounds: int = 3
) -> list[str]:
    reasons = []
    if mission.get("retry_count", 0) >= mission.get("max_retries", 3):
        reasons.append("retries exhausted")
    failures = [e for e in events if e.get("action") == "WORKER_FAILURE"]
    fingerprints = [e.get("details", {}).get("fingerprint") for e in failures]
    if any(f and fingerprints.count(f) >= 2 for f in fingerprints):
        reasons.append("same failure fingerprint repeated")
    stages: dict[str, set[str]] = {}
    for event in failures:
        details = event.get("details", {})
        if details.get("stage"):
            stages.setdefault(details["stage"], set()).add(
                str(event.get("actor") or "unknown")
            )
    if any(len(workers) >= 2 for workers in stages.values()):
        reasons.append("different workers failed at the same stage")
    progress = [
        e.get("details", {}).get("passed_count")
        for e in events
        if e.get("action") == "TEST_PROGRESS"
    ]
    if (
        len(progress) >= no_progress_rounds
        and len(set(progress[-no_progress_rounds:])) == 1
    ):
        reasons.append("no measured test progress")
    if any(
        e.get("action")
        in {"SENSITIVE_SCOPE", "CONFLICTING_REVIEW", "REVIEW_LOOP_BLOCKED"}
        for e in events
    ):
        reasons.append("sensitive scope or conflicting/repeated reviews")
    return reasons


class ReviewWorkflow:
    def __init__(
        self, db: DatabaseManager, artifacts_root: Path, key: str | None = None
    ):
        self.db, self.artifacts_root, self.key = db, artifacts_root.resolve(), key

    def package(
        self, mission_id: str, destination: Path, escalation: bool = False
    ) -> dict:
        mission = self.db.get_mission(mission_id)
        if mission is None:
            raise KeyError("Unknown mission")
        events = self.db.get_audit_trail(mission_id, limit=100)
        evidence = {}
        verified = False
        reference = mission.get("evidence_ref")
        if reference:
            path = Path(reference)
            if (
                not path.is_symlink()
                and self.artifacts_root in path.resolve().parents
                and path.is_file()
                and path.stat().st_size <= 1024 * 1024
            ):
                evidence = json.loads(path.read_text())
                verified = bool(
                    self.key
                    and evidence.get("mission_id") == mission_id
                    and EvidenceEngine(self.key).verify_evidence(
                        evidence, mission.get("commit_sha") or ""
                    )
                )
        try:
            plan = json.loads(mission.get("plan_json") or "{}")
        except (ValueError, TypeError):
            plan = {}
        criteria = plan.get("acceptance_criteria", []) if isinstance(plan, dict) else []
        if isinstance(plan, dict) and isinstance(plan.get('tasks'), list):
            criteria = list(dict.fromkeys(c for task in plan['tasks'] if isinstance(task, dict)
                                          for c in task.get('acceptance_criteria', []) if isinstance(c, str)))
        guardian = [
            e["details"]
            for e in events
            if e["action"] in {"GUARDIAN_APPROVED", "GUARDIAN_VETOED"}
        ]
        tests = (
            evidence.get("test_results", {})
            if verified
            else {
                "status": "NOT_TESTED",
                "reason": "No verified commit-bound evidence available",
            }
        )
        payload = {
            "schema_version": 1,
            "mission_id": mission_id,
            "state": mission["state"],
            "requirements": mission.get("prompt") or mission["goal"],
            "acceptance_criteria": criteria,
            "requirement_evidence_matrix": [
                {"criterion": c, "status": "NOT_TESTED", "evidence_ref": reference}
                for c in criteria[:64]
            ],
            "commit_sha": mission.get("commit_sha"),
            "evidence_verified": verified,
            "tests_by_label": {tests.get("label", "UNLABELED"): tests},
            "modified_files": plan.get("files_to_modify", [])
            if isinstance(plan, dict)
            else [],
            "diff_summary": evidence.get("diff_summary", {}) if verified else {},
            "guardian_decisions": guardian[-3:],
            "security_and_reviewer_findings": [
                e["details"]
                for e in events
                if e["action"] in {"SECURITY_FINDING", "REVIEW_FINDING"}
            ][-16:],
            "outstanding_issues": [mission.get("error_info")]
            if mission.get("error_info")
            else [],
            "suggested_actions": [
                "Resolve unverified requirements; inspect Guardian findings before any activation"
            ],
            "escalation_triggers": escalation_reasons(mission, events),
        }
        if escalation:
            payload = {
                "schema_version": 1,
                "mission_id": mission_id,
                "problem_statement": mission.get("error_info") or mission["goal"],
                "relevant_context": (mission.get("prompt") or mission["goal"])[:3000],
                "failed_attempts": [
                    {"actor": e["actor"], "result": e.get("details", {})}
                    for e in events
                    if e["action"] == "WORKER_FAILURE"
                ][-3:],
                "exact_sanitized_errors": (mission.get("error_info") or "")[-2048:],
                "constraints": [
                    "Guardian, sandbox, ownership and approvals remain mandatory"
                ],
                "question": "Which bounded correction should be attempted for the documented failure?",
                "proposed_solutions": [
                    "Review failure evidence and replan the smallest safe change"
                ],
                "evidence_references": [reference] if reference else [],
                "triggers": escalation_reasons(mission, events),
            }
        envelope = bounded(payload)
        root = new_directory(destination)
        name = "escalation" if escalation else "final_review"
        encoded = json.dumps(envelope, indent=2, ensure_ascii=True)
        private_write(root / f"{name}.json", (encoded + "\n").encode())
        private_write(
            root / f"{name}.md",
            (
                f"# {name.replace('_', ' ').title()}\n\n```json\n" + encoded + "\n```\n"
            ).encode(),
        )
        return envelope

    def apply(self, mission_id: str, raw: bytes | str, max_rounds: int = 2) -> dict:
        if not 1 <= max_rounds <= 4:
            raise ValueError("Invalid review round budget")
        review = parse_data(ImportedReview, raw, 32768)
        if self.db.get_mission(mission_id) is None:
            raise KeyError("Unknown mission")
        normalized = sorted(
            (
                f.requirement_id.casefold(),
                re.sub(r"\s+", " ", f.description.casefold()).strip(),
            )
            for f in review.findings
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                normalized if normalized else review.model_dump(), sort_keys=True
            ).encode()
        ).hexdigest()
        tasks = [
            {
                "requirement_id": f.requirement_id,
                "description": redact(f.description),
                "suggested_action": redact(f.suggested_action),
                "state": "NEEDS_PLANNING",
                "mandatory": f.severity in {"BLOCKER", "HIGH"},
            }
            for f in review.findings
        ]
        with self.db.connection() as con:
            for sql in REVIEW_SQL:
                con.execute(sql)
            con.execute("BEGIN IMMEDIATE")
            count = con.execute(
                "SELECT count(*) FROM imported_reviews WHERE mission=?", (mission_id,)
            ).fetchone()[0]
            repeated = con.execute(
                "SELECT 1 FROM imported_reviews WHERE mission=? AND fingerprint=?",
                (mission_id, fingerprint),
            ).fetchone()
            result: dict[str, Any]
            if count >= max_rounds or repeated:
                self.db.record_event(
                    con,
                    mission_id,
                    "review-import",
                    "REVIEW_LOOP_BLOCKED",
                    {"reason": "round limit or repeated findings"},
                )
                result = {
                    "status": "BLOCKED",
                    "reason": "Review rounds exhausted or identical findings repeated; escalate to operator",
                }
            else:
                con.execute(
                    "INSERT INTO imported_reviews VALUES (?,?,?,?,?)",
                    (
                        mission_id,
                        count + 1,
                        fingerprint,
                        json.dumps(redact(review.model_dump())),
                        json.dumps(tasks),
                    ),
                )
                self.db.record_event(
                    con,
                    mission_id,
                    "review-import",
                    "REVIEW_IMPORTED",
                    {"round": count + 1, "verdict": review.verdict},
                )
                result = {
                    "status": "ACCEPTED",
                    "round": count + 1,
                    "mandatory_tasks": [t for t in tasks if t["mandatory"]],
                    "backlog": [t for t in tasks if not t["mandatory"]],
                    "permissions_changed": False,
                }
        return result
