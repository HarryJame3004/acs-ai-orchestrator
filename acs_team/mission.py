import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import STATE_DIR
from .coordinator import TeamCoordinator

logger = logging.getLogger("acs_team.mission")


class MissionManager:
    def __init__(
        self,
        mission_id: str,
        repo_path: Path,
        phases: List[Dict[str, Any]],
        coordinator: Optional[TeamCoordinator] = None,
        state_dir: Path = STATE_DIR,
    ):
        self.mission_id = mission_id
        self.repo_path = repo_path.resolve()
        self.phases = phases
        self.coordinator = coordinator or TeamCoordinator()
        self.state_dir = state_dir
        self.state_file = self.state_dir / f"mission_{self.mission_id}.json"
        self.state = self._load_or_init_state()

    def _load_or_init_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                logger.info(
                    f"Loaded existing mission state from {self.state_file}"
                )
                return data
            except Exception as e:
                logger.warning(f"Could not read state file, initializing: {e}")

        initial_state = {
            "mission_id": self.mission_id,
            "repo_path": str(self.repo_path),
            "status": "INITIALIZED",
            "created_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "updated_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "phases_state": {
                p["phase_id"]: {
                    "name": p["name"],
                    "status": "PENDING",
                    "completed_at": None,
                    "attempts": 0,
                    "evidence": {},
                }
                for p in self.phases
            },
            "history": [],
        }
        self._save_state(initial_state)
        return initial_state

    def _save_state(self, state: Optional[Dict[str, Any]] = None):
        if state:
            self.state = state
        self.state["updated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        self.state_file.write_text(json.dumps(self.state, indent=2))

    def update_documentation_files(self):
        """Generate and update ACS progress documentation in repo and context."""
        docs_dir = self.repo_path / "reports"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # 1. Completion Matrix
        matrix_file = docs_dir / "ACS_COMPLETION_MATRIX.md"
        matrix_lines = [
            f"# ACS Autonomous Completion Matrix — Mission {self.mission_id}",
            f"**Last Updated:** {self.state['updated_at']}",
            f"**Mission Status:** {self.state['status']}\n",
            "| Phase ID | Phase Name | Status | Attempts | Completed At | Tests Passed |",
            "|---|---|---|---|---|---|",
        ]
        for p in self.phases:
            pid = p["phase_id"]
            pstate = self.state["phases_state"].get(pid, {})
            status = pstate.get("status", "PENDING")
            badge = (
                "✅ PASS"
                if status == "COMPLETED"
                else ("🔄 RUNNING" if status == "IN_PROGRESS" else "⏳ PENDING")
            )
            attempts = pstate.get("attempts", 0)
            completed_at = pstate.get("completed_at", "—")
            tests_passed = (
                "YES" if pstate.get("evidence", {}).get("tests_passed") else "—"
            )
            matrix_lines.append(
                f"| `{pid}` | {p['name']} | {badge} | {attempts} | {completed_at} | {tests_passed} |"
            )
        matrix_file.write_text("\n".join(matrix_lines) + "\n")

        # 2. Progress log
        progress_file = docs_dir / "ACS_AUTONOMOUS_PROGRESS.md"
        prog_lines = [
            f"# ACS Autonomous Progress Log — Mission {self.mission_id}",
            f"**Mission:** {self.mission_id}",
            f"**Target Repository:** `{self.repo_path}`\n",
            "## Execution History\n",
        ]
        for h in self.state.get("history", []):
            prog_lines.append(
                f"### Phase: {h.get('phase_id')} — {h.get('status')}"
            )
            prog_lines.append(f"- **Timestamp:** {h.get('timestamp')}")
            prog_lines.append(f"- **Session ID:** `{h.get('session_id')}`")
            prog_lines.append(f"- **Attempts:** {h.get('attempts')}")
            prog_lines.append(
                f"- **Changed Files:** {', '.join(h.get('changed_files', [])) or 'None'}"
            )
            prog_lines.append(f"- **Summary:** {h.get('summary')}\n")
        progress_file.write_text("\n".join(prog_lines) + "\n")

        # 3. Test Evidence
        evidence_file = docs_dir / "ACS_TEST_EVIDENCE.md"
        ev_lines = [
            f"# ACS Test Evidence Log — Mission {self.mission_id}",
            "**Verified Evidence Ledger**\n",
        ]
        for pid, pstate in self.state["phases_state"].items():
            ev_lines.append(f"## {pstate.get('name', pid)} (`{pid}`)")
            ev = pstate.get("evidence", {})
            ev_lines.append(f"- **Status:** {pstate.get('status')}")
            ev_lines.append(f"- **Tests Passed:** {ev.get('tests_passed')}")
            ev_lines.append(
                f"- **Verified by Reviewer:** {ev.get('approved')}"
            )
            ev_lines.append(
                f"- **Files Modified:** {', '.join(ev.get('changed_files', [])) or 'None'}"
            )
            ev_lines.append(f"- **Verification Note:** {ev.get('summary')}\n")
        evidence_file.write_text("\n".join(ev_lines) + "\n")

        # 4. Blockers
        blockers_file = docs_dir / "ACS_BLOCKERS.md"
        failed_phases = [
            (pid, pstate)
            for pid, pstate in self.state["phases_state"].items()
            if pstate.get("status") == "FAILED"
        ]
        blocker_lines = [
            f"# ACS Blockers Report — Mission {self.mission_id}",
            f"**Active Blockers:** {len(failed_phases)}\n",
        ]
        if not failed_phases:
            blocker_lines.append(
                "✅ **Zero active blockers.** All attempted phases completed cleanly.\n"
            )
        else:
            for pid, pstate in failed_phases:
                blocker_lines.append(f"### ❌ Blocked on `{pid}`")
                blocker_lines.append(
                    f"- **Details:** {pstate.get('evidence', {}).get('summary', 'Unknown error')}\n"
                )
        blockers_file.write_text("\n".join(blocker_lines) + "\n")

    def execute_mission(self, resume: bool = True) -> Dict[str, Any]:
        """Run all phases sequentially with checkpointing and resume support."""
        logger.info(f"=== Starting Mission Execution: {self.mission_id} ===")
        logger.info(f"Repository: {self.repo_path}")
        logger.info(f"Total phases defined: {len(self.phases)}")

        self.state["status"] = "IN_PROGRESS"
        self._save_state()
        self.update_documentation_files()

        for idx, phase in enumerate(self.phases, start=1):
            pid = phase["phase_id"]
            pstate = self.state["phases_state"].get(pid, {})

            if resume and pstate.get("status") == "COMPLETED":
                logger.info(
                    f"[Phase {idx}/{len(self.phases)}] Skipping already COMPLETED phase: {pid} ({phase['name']})"
                )
                continue

            logger.info(
                f"\n>>> [Phase {idx}/{len(self.phases)}] BEGINNING PHASE: {pid} ({phase['name']}) <<<"
            )
            pstate["status"] = "IN_PROGRESS"
            self._save_state()
            self.update_documentation_files()

            goal = phase["goal"]
            test_cmd = phase.get("test_cmd")

            # Execute via Team Coordinator
            result = self.coordinator.run_development_cycle(
                goal=goal,
                repo_path=self.repo_path,
                test_command=test_cmd,
            )

            status = result.get("status")
            pstate["status"] = status
            pstate["attempts"] = result.get("attempts", 1)
            pstate["evidence"] = {
                "session_id": result.get("session_id"),
                "approved": result.get("approved", False),
                "tests_passed": result.get("tests_passed", False),
                "changed_files": result.get("changed_files", []),
                "summary": result.get("verification", {}).get(
                    "summary", "No summary"
                ),
            }

            if status == "COMPLETED":
                pstate["completed_at"] = datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
                logger.info(f"✓ Phase {pid} successfully COMPLETED.")
            else:
                logger.error(
                    f"✗ Phase {pid} ended with status {status}. Halting mission for safety."
                )
                self.state["status"] = "FAILED"
                self.state["history"].append(
                    {
                        "phase_id": pid,
                        "status": status,
                        "session_id": result.get("session_id"),
                        "attempts": result.get("attempts"),
                        "changed_files": result.get("changed_files", []),
                        "summary": result.get("verification", {}).get(
                            "summary"
                        ),
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                    }
                )
                self._save_state()
                self.update_documentation_files()
                return self.state

            self.state["history"].append(
                {
                    "phase_id": pid,
                    "status": status,
                    "session_id": result.get("session_id"),
                    "attempts": result.get("attempts"),
                    "changed_files": result.get("changed_files", []),
                    "summary": result.get("verification", {}).get("summary"),
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                }
            )
            self._save_state()
            self.update_documentation_files()

        self.state["status"] = "COMPLETED"
        self._save_state()
        self.update_documentation_files()
        logger.info(f"=== Mission {self.mission_id} COMPLETED SUCCESSFULLY ===")
        return self.state
