"""ACS AI V2 Human Approval Gate.
Enforces human-in-the-loop governance for high-risk operations:
- Release branch merges
- Modifying security or CoreLock boundaries
- Running ADMIN category tools
Workers are forbidden from self-approving or bypassing this gate.
"""

from __future__ import annotations

import datetime
import enum
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .db import DatabaseManager

logger = logging.getLogger("acs_ai.human_approval")


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class HumanApprovalError(Exception):
    pass


class HumanApprovalGate:
    """Manages creation, verification, and resolution of human approval gates."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def request_approval(
        self,
        mission_id: str,
        action: str,
        target_repo: str,
        commit_sha: str,
        risk_level: RiskLevel = RiskLevel.HIGH,
        reason: Optional[str] = None,
    ) -> str:
        """Creates a pending human approval request in the database."""
        approval_id = f"appr-{uuid.uuid4().hex[:8]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.db.get_connection() as con:
            con.execute(
                """
                INSERT INTO human_approvals (
                    approval_id, mission_id, action, target_repo, commit_sha,
                    risk_level, status, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    mission_id,
                    action,
                    target_repo,
                    commit_sha,
                    risk_level.value,
                    ApprovalStatus.PENDING.value,
                    reason,
                    now,
                ),
            )
            con.commit()

        logger.info(
            f"Created Human Approval Request '{approval_id}' for mission '{mission_id}' [{risk_level.value}]: {action}"
        )
        return approval_id

    def resolve_approval(
        self,
        approval_id: str,
        status: ApprovalStatus,
        resolved_by: str,
        reason: Optional[str] = None,
    ) -> bool:
        """Approves or rejects a pending request. Workers cannot resolve."""
        if resolved_by.startswith("worker-") or resolved_by in ("codex-primary", "agy-google-a", "agy-google-b"):
            raise HumanApprovalError(f"Autonomous worker '{resolved_by}' is forbidden from resolving approval gates.")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.get_connection() as con:
            cur = con.execute(
                """
                UPDATE human_approvals
                SET status = ?, approved_by = ?, reason = COALESCE(?, reason), resolved_at = ?
                WHERE approval_id = ? AND status = 'PENDING'
                """,
                (status.value, resolved_by, reason, now, approval_id),
            )
            con.commit()
            updated = cur.rowcount > 0

        if updated:
            logger.info(f"Resolved Approval Request '{approval_id}' as {status.value} by '{resolved_by}'")
        return updated

    def get_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as con:
            cur = con.execute("SELECT * FROM human_approvals WHERE approval_id = ?", (approval_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_pending_approvals(self, mission_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.db.get_connection() as con:
            if mission_id:
                cur = con.execute(
                    "SELECT * FROM human_approvals WHERE mission_id = ? AND status = 'PENDING' ORDER BY created_at DESC",
                    (mission_id,),
                )
            else:
                cur = con.execute(
                    "SELECT * FROM human_approvals WHERE status = 'PENDING' ORDER BY created_at DESC"
                )
            return [dict(r) for r in cur.fetchall()]

    def is_operation_approved(self, approval_id: str) -> bool:
        """Returns True only if the specified approval has status APPROVED."""
        rec = self.get_approval(approval_id)
        return rec is not None and rec.get("status") == ApprovalStatus.APPROVED.value
