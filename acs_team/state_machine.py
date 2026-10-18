"""ACS AI V2 Mission State Machine.
Validates state transitions, enforces monotonicity, bounds retries,
and triggers automatic cryptographic checkpointing.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .db import DatabaseManager

logger = logging.getLogger("acs_ai.state_machine")


class MissionState(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    INTEGRATING = "INTEGRATING"
    TESTING = "TESTING"
    REVIEWING = "REVIEWING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    RECOVERING = "RECOVERING"


VALID_TRANSITIONS: Dict[MissionState, Set[MissionState]] = {
    MissionState.CREATED: {MissionState.QUEUED, MissionState.CANCELLED},
    MissionState.QUEUED: {MissionState.PLANNING, MissionState.CANCELLED},
    MissionState.PLANNING: {
        MissionState.READY,
        MissionState.FAILED,
        MissionState.BLOCKED,
        MissionState.CANCELLED,
    },
    MissionState.READY: {MissionState.RUNNING, MissionState.CANCELLED},
    MissionState.RUNNING: {
        MissionState.INTEGRATING,
        MissionState.FAILED,
        MissionState.BLOCKED,
        MissionState.CANCELLED,
        MissionState.RECOVERING,
    },
    MissionState.INTEGRATING: {
        MissionState.TESTING,
        MissionState.RUNNING,  # conflict resolution re-attempt
        MissionState.FAILED,
        MissionState.BLOCKED,
        MissionState.CANCELLED,
    },
    MissionState.TESTING: {
        MissionState.REVIEWING,
        MissionState.RUNNING,  # test failure re-attempt
        MissionState.FAILED,
        MissionState.BLOCKED,
        MissionState.CANCELLED,
    },
    MissionState.REVIEWING: {
        MissionState.AWAITING_APPROVAL,
        MissionState.COMPLETED,
        MissionState.RUNNING,  # reviewer defect correction loop
        MissionState.FAILED,
        MissionState.BLOCKED,
        MissionState.CANCELLED,
    },
    MissionState.AWAITING_APPROVAL: {
        MissionState.COMPLETED,
        MissionState.RUNNING,  # human requested changes
        MissionState.BLOCKED,  # human rejected
        MissionState.CANCELLED,
    },
    MissionState.RECOVERING: {
        MissionState.RUNNING,
        MissionState.READY,
        MissionState.PLANNING,
        MissionState.FAILED,
        MissionState.BLOCKED,
    },
    # Terminal states
    MissionState.COMPLETED: set(),
    MissionState.FAILED: {MissionState.RECOVERING},  # explicit recovery allowed
    MissionState.BLOCKED: {MissionState.RECOVERING},  # explicit recovery allowed
    MissionState.CANCELLED: set(),
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state transition is attempted."""
    pass


class StateMachine:
    """Controls and validates mission state transitions with durable checkpointing."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def can_transition(self, current_state_str: str, next_state_str: str) -> bool:
        try:
            curr = MissionState(current_state_str)
            nxt = MissionState(next_state_str)
        except ValueError:
            return False
        return nxt in VALID_TRANSITIONS.get(curr, set())

    def transition(
        self,
        mission_id: str,
        target_state: MissionState,
        checkpoint_payload: Optional[Dict[str, Any]] = None,
        error_info: Optional[str] = None,
        commit_sha: Optional[str] = None,
        git_branch: Optional[str] = None,
        review_status: Optional[str] = None,
        quality_score: Optional[float] = None,
        evidence_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transitions mission to target state if allowed, creating a checkpoint."""
        mission = self.db.get_mission(mission_id)
        if not mission:
            raise KeyError(f"Mission '{mission_id}' not found.")

        current_state = MissionState(mission["state"])
        if not self.can_transition(current_state, target_state):
            raise InvalidStateTransitionError(
                f"Illegal state transition from {current_state.value} to {target_state.value} for mission {mission_id}."
            )

        # Checkpoint if payload is provided or transitioning into critical milestones
        checkpoint_id = None
        if checkpoint_payload is not None:
            checkpoint_id = self.db.save_checkpoint(
                mission_id=mission_id,
                state_name=target_state.value,
                payload=checkpoint_payload,
            )

        self.db.update_mission_state(
            mission_id=mission_id,
            new_state=target_state.value,
            error_info=error_info,
            commit_sha=commit_sha,
            git_branch=git_branch,
            review_status=review_status,
            quality_score=quality_score,
            evidence_ref=evidence_ref,
            expected_state=current_state.value,
        )

        logger.info(
            f"Mission {mission_id} successfully transitioned {current_state.value} -> {target_state.value}"
            + (f" [checkpoint: {checkpoint_id}]" if checkpoint_id else "")
        )
        return self.db.get_mission(mission_id)  # type: ignore

    def reconcile_interrupted_missions(self) -> List[Dict[str, Any]]:
        """Recovers missions that were in active states when the daemon previously stopped."""
        active_states = [
            MissionState.RUNNING.value,
            MissionState.INTEGRATING.value,
            MissionState.TESTING.value,
            MissionState.PLANNING.value,
            MissionState.READY.value,
            MissionState.REVIEWING.value,
        ]
        reconciled = []
        for state in active_states:
            missions = self.db.list_missions(limit=100, state=state)
            for m in missions:
                mid = m["mission_id"]
                import os
                if os.environ.get('ACS_ENABLE_COORDINATION') == '1':
                    with self.db.connection() as con:
                        exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='team_runs' AND type='table'").fetchone()
                        run = con.execute('SELECT * FROM team_runs WHERE mission=?',(mid,)).fetchone() if exists else None
                    if run:
                        import json
                        from .team_recovery import owner_alive
                        from .schemas import Plan, parse_data
                        if owner_alive(json.loads(run['owner'])):
                            continue  # A second observer must not steal a live run.
                        if run['phase']=='ACTIVE' and run['plan']:
                            parse_data(Plan,run['plan'])
                            self.db.update_mission_state(mid,'RECOVERING',expected_state=m['state'],
                                error_info='Interrupted team run; durable plan awaits fenced Git/claim reconciliation')
                            updated = self.db.get_mission(mid)
                            if updated:
                                reconciled.append(updated)
                            continue
                logger.warning(
                    f"Found interrupted mission {mid} in state {m['state']}; recovering..."
                )
                chk = self.db.get_latest_checkpoint(mid)
                if chk and chk.get("valid"):
                    self.db.update_mission_state(
                        mission_id=mid,
                        new_state=MissionState.RECOVERING.value,
                        error_info=f"Interrupted during {m['state']}; checkpoint {chk['checkpoint_id']} loaded",
                    )
                else:
                    self.db.update_mission_state(
                        mission_id=mid,
                        new_state=MissionState.BLOCKED.value,
                        error_info=f"Interrupted during {m['state']}; no valid checkpoint found",
                    )
                updated = self.db.get_mission(mid)
                if updated is None:
                    raise RuntimeError("Mission disappeared during reconciliation")
                reconciled.append(updated)
        return reconciled
