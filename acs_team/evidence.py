"""ACS AI V2 Commit-Bound Evidence Engine.
Generates and cryptographically verifies immutable evidence packages bound to exact git commit SHAs.
Prevents worker tampering, post-hoc modification, and evidence forgery.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger("acs_ai.evidence")


def persist_evidence(evidence: Dict[str, Any], directory: Path) -> Path:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink():
        raise PermissionError("Evidence directory may not be a symlink")
    path = directory / f"{uuid.uuid4().hex}.evidence.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(evidence, stream, sort_keys=True)
    return path


@dataclass
class EvidencePackage:
    mission_id: str
    task_id: Optional[str]
    commit_sha: str
    test_results: Dict[str, Any]
    diff_summary: Dict[str, Any]
    timestamp: str
    payload_sha256: str
    signature: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceEngine:
    """Creates and verifies tamper-proof evidence packages bound to git commits."""

    def __init__(self, auth_token: str):
        self.auth_token = auth_token

    def _canonical_payload(
        self,
        mission_id: str,
        task_id: Optional[str],
        commit_sha: str,
        test_results: Dict[str, Any],
        diff_summary: Dict[str, Any],
        timestamp: str,
    ) -> str:
        """Produces canonical sorted JSON string of evidence data."""
        payload_dict = {
            "mission_id": mission_id,
            "task_id": task_id,
            "commit_sha": commit_sha,
            "test_results": test_results,
            "diff_summary": diff_summary,
            "timestamp": timestamp,
        }
        return json.dumps(payload_dict, sort_keys=True)

    def create_evidence(
        self,
        mission_id: str,
        task_id: Optional[str],
        commit_sha: str,
        test_results: Dict[str, Any],
        diff_summary: Dict[str, Any],
    ) -> EvidencePackage:
        """Constructs and signs a new EvidencePackage."""
        timestamp = datetime.now(timezone.utc).isoformat()
        canonical_str = self._canonical_payload(
            mission_id=mission_id,
            task_id=task_id,
            commit_sha=commit_sha,
            test_results=test_results,
            diff_summary=diff_summary,
            timestamp=timestamp,
        )

        payload_sha = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
        
        # Sign payload SHA with auth_token
        signature = hmac.new(
            self.auth_token.encode("utf-8"),
            payload_sha.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return EvidencePackage(
            mission_id=mission_id,
            task_id=task_id,
            commit_sha=commit_sha,
            test_results=test_results,
            diff_summary=diff_summary,
            timestamp=timestamp,
            payload_sha256=payload_sha,
            signature=signature,
        )

    def verify_evidence(
        self,
        evidence_dict: Dict[str, Any],
        expected_commit_sha: str,
    ) -> bool:
        """Verifies evidence authenticity, commit SHA match, and HMAC signature."""
        try:
            mission_id = evidence_dict.get("mission_id")
            task_id = evidence_dict.get("task_id")
            commit_sha = evidence_dict.get("commit_sha")
            test_results = evidence_dict.get("test_results") or {}
            diff_summary = evidence_dict.get("diff_summary") or {}
            timestamp = evidence_dict.get("timestamp")
            payload_sha256 = evidence_dict.get("payload_sha256")
            signature = evidence_dict.get("signature")

            if (
                not isinstance(mission_id, str) or not mission_id
                or not isinstance(commit_sha, str) or not commit_sha
                or not isinstance(timestamp, str) or not timestamp
                or not isinstance(payload_sha256, str) or not payload_sha256
                or not isinstance(signature, str) or not signature
                or (task_id is not None and not isinstance(task_id, str))
                or not isinstance(test_results, dict)
                or not isinstance(diff_summary, dict)
            ):
                logger.warning("Evidence package missing mandatory fields.")
                return False

            # 1. Commit SHA must match target branch/worktree HEAD exactly
            if commit_sha.lower() != expected_commit_sha.lower():
                logger.warning(
                    f"Evidence commit mismatch: evidence has '{commit_sha}', expected '{expected_commit_sha}'"
                )
                return False

            # 2. Recalculate canonical payload hash
            canonical_str = self._canonical_payload(
                mission_id=mission_id,
                task_id=task_id,
                commit_sha=commit_sha,
                test_results=test_results,
                diff_summary=diff_summary,
                timestamp=timestamp,
            )
            recalculated_sha = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(recalculated_sha, payload_sha256):
                logger.warning("Evidence payload SHA256 integrity check failed.")
                return False

            # 3. Verify HMAC signature using auth_token
            expected_sig = hmac.new(
                self.auth_token.encode("utf-8"),
                payload_sha256.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(expected_sig, signature):
                logger.warning("Evidence HMAC signature verification failed.")
                return False

            return True
        except Exception as e:
            logger.error(f"Unexpected error verifying evidence: {e}", exc_info=True)
            return False

    @staticmethod
    def get_repo_head_commit(repo_path: Path) -> str:
        """Extracts HEAD commit SHA from repository."""
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
