"""ACS AI V2.2 Autonomous Mission Planner & Multi-Agent Scheduler.
Orchestrates:
1. Natural language prompt analysis and repo inspection.
2. Structured task graph generation with acceptance criteria.
3. Intelligent multi-agent worker scheduling (auto, codex, agy-google-a, agy-google-b).
4. Worktree isolation, test execution, bounded correction retries.
5. Guardian gatekeeper evaluation, HMAC-SHA256 evidence generation.
6. Real-time logging and SQLite persistence.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .auth import get_or_create_auth_token
from .config import GIT_BIN, LOGS_DIR, STATE_DIR
from .db import DatabaseManager
from .evidence import EvidenceEngine, persist_evidence
from .guardian import Guardian, GuardianVerdict
from .planner import AIPlanner
from .scope_and_integration import IntegrationManager, ScopeManager
from .state_machine import MissionState, StateMachine
from .worker_adapters import BaseWorker, WorkerRegistry, WorkerUnverifiedError
from .worktree_manager import WorktreeManager
from .runtime_control import RuntimeControl
from .security import redact
from .managed_worker import worker_context

logger = logging.getLogger("acs_ai.autonomous_planner")


class AutonomousMissionPlanner:
    """End-to-end autonomous mission planning and multi-agent execution pipeline."""

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        registry: Optional[WorkerRegistry] = None,
    ):
        self.db = db or DatabaseManager()
        self.state_machine = StateMachine(self.db)
        self.registry = registry or WorkerRegistry()
        self.worktree_mgr = WorktreeManager()
        self.scope_mgr = ScopeManager()
        self.planner = AIPlanner()
        self.auth_token = get_or_create_auth_token(STATE_DIR / "evidence.key")
        self.control = RuntimeControl(self.db, initialize=False)

    def run_mission(
        self,
        mission_id: str,
        prompt: str,
        repo_path: Path,
        worker_preference: str = "auto",
        test_command: Optional[str] = None,
        max_retries: int = 3,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Executes a full natural-language mission from prompt to Guardian integration."""
        repo_path = repo_path.resolve()
        self.control.require_dispatch()
        Guardian(self.db, auth_token=self.auth_token).verify_corelock_safety(str(repo_path), [])
        start_time = time.time()

        def _log(msg: str) -> None:
            msg = redact(msg)
            formatted = f"[{mission_id}] {msg}"
            logger.info(formatted)
            self.db.append_mission_log(mission_id, msg)
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass

        _log(f"=== Starting Natural Language Mission {mission_id} ===")
        _log(f"Target Repository: {repo_path}")
        _log(f"Worker Preference: {worker_preference}")
        _log(f"Prompt:\n{prompt}")

        # Ensure mission exists in DB
        existing = self.db.get_mission(mission_id)
        if not existing:
            self.db.create_mission(
                mission_id=mission_id,
                project_id=repo_path.name,
                repository_path=str(repo_path),
                goal=prompt.splitlines()[0][:100] if prompt else "Natural language mission",
                state=MissionState.CREATED.value,
                assigned_workers=[],
                max_retries=max_retries,
                prompt=prompt,
            )

        # Transition CREATED -> QUEUED -> PLANNING
        try:
            self.state_machine.transition(mission_id, MissionState.QUEUED)
        except Exception:
            pass
        self.state_machine.transition(mission_id, MissionState.PLANNING)

        # Step 1: Inspect repository structure
        _log("Step 1: Inspecting repository structure...")
        repo_summary = self._inspect_repo(repo_path)
        _log(f"Repository inspected ({len(repo_summary.splitlines())} lines context).")

        # Step 2: Generate Actionable Task Graph via Planner
        _log("Step 2: AI Planner decomposing natural language prompt into task specification...")
        plan = self.planner.plan_task(prompt, repo_summary=repo_summary)
        if test_command:
            plan["test_command"] = test_command

        _log(f"Plan generated: Task '{plan.get('task_name')}' | Goal: {plan.get('goal_summary')}")
        _log(f"Files to modify: {plan.get('files_to_modify', [])}")
        _log(f"Test command: {plan.get('test_command', 'pytest')}")

        self.db.update_mission_plan(mission_id, prompt, plan)

        # Transition PLANNING -> READY -> RUNNING
        self.state_machine.transition(mission_id, MissionState.READY)
        self.state_machine.transition(mission_id, MissionState.RUNNING)

        # Step 3: Multi-Agent Worker Scheduling
        _log("Step 3: Scheduling worker...")
        worker_id, worker = self._schedule_worker(worker_preference, plan)
        _log(f"Assigned worker: {worker_id}")

        with self.db.connection() as con:
            con.execute(
                "UPDATE missions SET assigned_workers = ? WHERE mission_id = ?",
                (json.dumps([worker_id]), mission_id),
            )

        # Step 4: Allocate Isolated Worktree
        task_id = f"task-{uuid.uuid4().hex[:16]}"
        base_sha = EvidenceEngine.get_repo_head_commit(repo_path)
        _log(f"Step 4: Allocating isolated git worktree for task {task_id}...")
        worktree_path = self.worktree_mgr.create_worktree(
            repo_path=repo_path,
            mission_id=mission_id,
            task_id=task_id,
        )
        worker_branch = f"acsai/worker/{mission_id.replace('/', '_')}/{task_id}"
        _log(f"Worktree allocated at {worktree_path} on branch {worker_branch}")

        # Reserve scope
        target_files = plan.get("files_to_modify", [])
        if target_files:
            self.scope_mgr.reserve_scope(mission_id, task_id, target_files)

        # Step 5: Worker Execution & Correction Loop
        attempt = 0
        execution_success = False
        last_error = ""
        last_worker_result: Dict[str, Any] = {}

        current_instructions = plan.get("instructions", prompt)
        current_files = list(target_files)
        current_test_cmd = plan.get("test_command", test_command or "pytest")

        while attempt < max_retries and not execution_success:
            self.control.require_dispatch()
            attempt += 1
            _log(f"Step 5 (Attempt {attempt}/{max_retries}): Worker '{worker_id}' executing code changes...")

            with worker_context(self.control, mission_id):
                dispatch_res = worker.execute_task(
                    task_id=task_id,
                    goal=plan.get("goal_summary", prompt),
                    instructions=current_instructions,
                    worktree_path=worktree_path,
                    files_to_modify=current_files,
                    timeout_seconds=300.0,
                )
            current_mission = self.db.get_mission(mission_id)
            if current_mission is None:
                raise RuntimeError("Mission state disappeared during execution")
            if self.control.stopped() or current_mission["state"] == MissionState.CANCELLED.value:
                return {"mission_id": mission_id, "status": "CANCELLED", "worktree_path": str(worktree_path)}
            last_worker_result = dispatch_res

            if not dispatch_res.get("success", False):
                last_error = dispatch_res.get("error", "Worker execution failed")
                _log(f"Worker attempt {attempt} failed: {last_error}")

                # Fail-over to alternative worker if available
                if worker_preference == "auto" and attempt < max_retries:
                    alt_worker_id, alt_worker = self._schedule_failover(worker_id)
                    if alt_worker_id != worker_id:
                        _log(f"Failing over to alternative worker: {alt_worker_id}")
                        worker_id, worker = alt_worker_id, alt_worker

                continue

            changed = dispatch_res.get("changed_files", [])
            _log(f"Worker finished execution. Changed files detected: {changed}")

            # Step 6: Automated Test Verification
            _log(f"Step 6: Running automated tests in worktree ('{current_test_cmd}')...")
            test_run = self._run_test_command(worktree_path, current_test_cmd)
            _log(f"Test exit code: {test_run['exit_code']} (Passed: {test_run['passed']})")

            if test_run["passed"]:
                execution_success = True
                _log("Automated verification tests PASSED.")
                break
            else:
                last_error = f"Test failure: {test_run['output'][-500:]}"
                _log(f"Automated tests failed on attempt {attempt}: {last_error}")

                if attempt < max_retries:
                    _log("AI Planner generating surgical correction instructions...")
                    correction = self.planner.plan_correction(
                        original_plan=plan,
                        reviewer_report={"summary": "Test failure", "defects": [test_run["output"][:1000]]},
                    )
                    current_instructions = correction.get("instructions", current_instructions)
                    current_files = correction.get("files_to_modify", current_files)

        if not execution_success:
            _log(f"Mission {mission_id} failed after {max_retries} attempts: {last_error}")
            self.state_machine.transition(mission_id, MissionState.FAILED, error_info=last_error)
            # Retain failed worktrees/evidence for recovery and operator review.
            return {
                "mission_id": mission_id,
                "status": "FAILED",
                "error": last_error,
                "attempts": attempt,
            }

        # Step 7: Commit Worker Changes to Branch
        _log("Step 7: Committing verified worker modifications...")
        valid_scope, unstaged_files, unexpected = self.scope_mgr.verify_diff_against_scope(worktree_path, current_files, base_ref=base_sha)
        if not valid_scope:
            self.state_machine.transition(mission_id, MissionState.BLOCKED, error_info=f"Scope violation: {unexpected}")
            return {"mission_id": mission_id, "status": "BLOCKED", "unexpected_files": unexpected}
        if unstaged_files:
            subprocess.run([str(GIT_BIN), "add", "-A", "--", *unstaged_files], cwd=str(worktree_path), check=True)
        commit_msg = f"Implement: {plan.get('goal_summary', prompt)[:80]} (Worker: {worker_id})"
        status_res = subprocess.run([str(GIT_BIN), "diff", "--cached", "--quiet"], cwd=str(worktree_path))
        if status_res.returncode == 1:
            subprocess.run([str(GIT_BIN), "commit", "-m", commit_msg], cwd=str(worktree_path), check=True)
        elif status_res.returncode != 0:
            raise RuntimeError("Cannot inspect staged worker changes")

        worker_commit_sha = subprocess.run(
            [str(GIT_BIN), "rev-parse", "HEAD"], cwd=str(worktree_path), capture_output=True, text=True, check=True
        ).stdout.strip()
        _log(f"Worker commit SHA: {worker_commit_sha}")


        valid_scope, actual_files, unexpected = self.scope_mgr.verify_diff_against_scope(worktree_path, current_files, base_ref=base_sha)
        if not valid_scope:
            self.state_machine.transition(mission_id, MissionState.BLOCKED, error_info=f"Scope violation: {unexpected}")
            return {"mission_id": mission_id, "status": "BLOCKED", "unexpected_files": unexpected}
        # Prepare integration; Guardian must approve BEFORE the branch advances.
        _log("Step 8: Preparing independent pre-integration verification...")
        int_mgr = IntegrationManager(repo_path)
        integ_branch = int_mgr.ensure_integration_branch(mission_id)
        integrated_sha = worker_commit_sha


        self.state_machine.transition(mission_id, MissionState.INTEGRATING, commit_sha=integrated_sha)
        self.state_machine.transition(mission_id, MissionState.TESTING)

        # Step 9: Cryptographic Evidence Generation
        _log("Step 9: Generating HMAC-SHA256 commit-bound evidence package...")
        evidence_eng = EvidenceEngine(self.auth_token)
        diff_text = subprocess.run(
            ["git", "diff", f"{base_sha}..HEAD"], cwd=str(worktree_path), capture_output=True, text=True, check=True
        ).stdout or ""

        evidence = evidence_eng.create_evidence(
            mission_id=mission_id,
            task_id=task_id,
            commit_sha=integrated_sha,
            test_results={
                "executed": True,
                "passed": True,
                "exit_code": 0,
                "command": current_test_cmd,
            },
            diff_summary={"diff_text": diff_text},
        )
        ev_dict = evidence.to_dict()
        evidence_path = persist_evidence(ev_dict, STATE_DIR / "artifacts")
        _log(f"Evidence package signed: {ev_dict['signature'][:16]} (Payload SHA256: {ev_dict['payload_sha256'][:16]})")

        self.state_machine.transition(mission_id, MissionState.REVIEWING, evidence_ref=str(evidence_path))

        # Step 10: Guardian Independent Gatekeeper Evaluation
        _log("Step 10: Running Guardian security, branch, and quality evaluation...")
        guardian = Guardian(self.db, auth_token=self.auth_token, quality_threshold=0.85)
        target_mission_branch = f"acsai/mission/{mission_id.replace('/', '_')}"

        verdict: GuardianVerdict = guardian.evaluate(
            mission_id=mission_id,
            repository_path=repo_path,
            worktree_path=worktree_path,
            target_branch=target_mission_branch,
            commit_sha=integrated_sha,
            evidence_dict=ev_dict,
            changed_files=actual_files,
            test_command=current_test_cmd,
        )

        _log(f"Guardian Verdict: Approved={verdict.approved} | Quality Score={verdict.quality_score:.4f}")
        if verdict.veto_reasons:
            _log(f"Guardian Veto Reasons: {verdict.veto_reasons}")

        duration = time.time() - start_time

        if not verdict.approved:
            _log(f"Mission failed Guardian evaluation: {verdict.veto_reasons}")
            self.state_machine.transition(mission_id, MissionState.BLOCKED, error_info=str(verdict.veto_reasons))
            return {
                "mission_id": mission_id,
                "status": "BLOCKED",
                "approved": False,
                "quality_score": verdict.quality_score,
                "veto_reasons": verdict.veto_reasons,
                "duration_sec": round(duration, 2),
            }

        self.control.require_dispatch()
        merge_result = int_mgr.merge_task_branch(integration_branch=integ_branch, worker_branch=worker_branch)
        integrated_sha = merge_result["integrated_commit_sha"]
        integrated_tests = self._run_test_command(Path(merge_result.get("integration_worktree", repo_path)), current_test_cmd)
        if not integrated_tests["passed"]:
            int_mgr.rollback_integration(merge_result["previous_commit_sha"])
            self.state_machine.transition(mission_id, MissionState.BLOCKED, error_info="Post-integration tests failed; mission branch rolled back")
            return {"mission_id": mission_id, "status": "BLOCKED", "error": "Post-integration verification failed"}
        final_evidence = evidence_eng.create_evidence(mission_id, task_id, integrated_sha,
                                                     {"executed": True, **integrated_tests},
                                                     {"diff_text": diff_text}).to_dict()
        final_path = persist_evidence(final_evidence, STATE_DIR / "artifacts")
        self.worktree_mgr.remove_worktree(repo_path, worktree_path, force=True)
        # Step 11: Final Completion
        self.state_machine.transition(mission_id, MissionState.COMPLETED, commit_sha=integrated_sha, evidence_ref=str(final_path))
        _log(f"=== Mission {mission_id} COMPLETED SUCCESSFULLY in {duration:.1f}s ===")

        # Update quality score in DB
        with self.db.connection() as con:
            con.execute(
                "UPDATE missions SET quality_score = ?, commit_sha = ? WHERE mission_id = ?",
                (verdict.quality_score, integrated_sha, mission_id),
            )

        return {
            "mission_id": mission_id,
            "status": "COMPLETED",
            "approved": True,
            "worker_used": worker_id,
            "integrated_sha": integrated_sha,
            "quality_score": verdict.quality_score,
            "evidence_signature": ev_dict["signature"],
            "duration_sec": round(duration, 2),
            "files_modified": last_worker_result.get("changed_files", []),
        }

    def _inspect_repo(self, repo_path: Path) -> str:
        """Collects repository structure, files, and project context."""
        summary_lines = [f"Repository: {repo_path}"]
        try:
            # List files up to 2 levels
            files = []
            for root, dirs, filenames in os.walk(repo_path):
                # skip git and venvs
                dirs[:] = [d for d in dirs if d not in (".git", "venv", "__pycache__", ".pytest_cache", "node_modules")]
                rel_root = os.path.relpath(root, repo_path)
                for f in filenames:
                    p = f if rel_root == "." else os.path.join(rel_root, f)
                    files.append(p)
                    if len(files) >= 50:
                        break
                if len(files) >= 50:
                    break

            summary_lines.append(f"Discovered Files ({len(files)}):")
            for f in files[:30]:
                summary_lines.append(f"  - {f}")

            # Read README if present
            readme = repo_path / "README.md"
            if readme.exists() and not readme.is_symlink():
                summary_lines.append("\nREADME.md excerpt:")
                summary_lines.append(readme.read_text(encoding="utf-8", errors="replace")[:1000])

            # Detect test framework
            if (repo_path / "pytest.ini").exists() or (repo_path / "tests").is_dir():
                summary_lines.append("\nDetected Test Suite: pytest")
        except Exception as e:
            summary_lines.append(f"Error inspecting repository: {e}")

        return "\n".join(summary_lines)

    def _schedule_worker(self, worker_pref: str, plan: Dict[str, Any]) -> Tuple[str, BaseWorker]:
        """Schedules appropriate worker based on preference, availability, and task needs."""
        available = self.registry.list_available_workers()
        if not available:
            raise RuntimeError("No workers are currently verified and ready.")

        pref = worker_pref.lower().strip()
        worker_map = {
            "codex": "codex-primary",
            "codex-primary": "codex-primary",
            "agy-a": "agy-google-a",
            "agy-google-a": "agy-google-a",
            "agy-b": "agy-google-b",
            "agy-google-b": "agy-google-b",
        }

        # 1. Explicit Worker Requested
        if pref in worker_map:
            target_id = worker_map[pref]
            if target_id not in available:
                raise WorkerUnverifiedError(
                    f"Requested worker '{target_id}' is unavailable or unverified in WorkerRegistry."
                )
            return target_id, self.registry.get_worker(target_id)

        # 2. Auto Scheduling
        # Priority order: agy-google-b -> agy-google-a -> codex-primary
        # Balance work between available workers
        if "agy-google-b" in available:
            return "agy-google-b", self.registry.get_worker("agy-google-b")
        elif "agy-google-a" in available:
            return "agy-google-a", self.registry.get_worker("agy-google-a")
        else:
            return "codex-primary", self.registry.get_worker("codex-primary")

    def _schedule_failover(self, failing_worker_id: str) -> Tuple[str, BaseWorker]:
        """Selects a healthy alternative worker upon failure."""
        available = [w for w in self.registry.list_available_workers() if w != failing_worker_id]
        if not available:
            return failing_worker_id, self.registry.get_worker(failing_worker_id)
        next_worker = available[0]
        return next_worker, self.registry.get_worker(next_worker)

    def _run_test_command(self, worktree_path: Path, cmd: str) -> Dict[str, Any]:
        """Executes test command in worktree."""
        from .security import run_verification
        try:
            return run_verification(cmd, worktree_path, 120)
        except Exception as error:
            return {"passed": False, "exit_code": -1, "output": str(error)}
