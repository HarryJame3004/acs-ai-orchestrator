import datetime
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import STATE_DIR
from .planner import AIPlanner
from .reviewer import CodeReviewer
from .worker import CodexWorker

logger = logging.getLogger("acs_team.coordinator")


class TeamCoordinator:
    def __init__(
        self,
        planner: Optional[AIPlanner] = None,
        worker: Optional[CodexWorker] = None,
        reviewer: Optional[CodeReviewer] = None,
        max_retries: int = 3,
    ):
        self.planner = planner or AIPlanner()
        self.worker = worker or CodexWorker()
        self.reviewer = reviewer or CodeReviewer()
        self.max_retries = max_retries

    def run_development_cycle(
        self,
        goal: str,
        repo_path: Path,
        repo_summary: str = "",
        test_command: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a complete, autonomous development cycle:
        Planner -> Codex Worker -> Reviewer -> (Correction Loop) -> Planner Verification
        """
        session_id = f"session-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        logger.info(f"=== Starting Autonomous AI Team Cycle [{session_id}] ===")
        logger.info(f"Goal: {goal}")
        logger.info(f"Repository: {repo_path}")

        session_log: List[Dict[str, Any]] = []

        # Step 1: Planner analyzes request & decomposes task
        logger.info("[Step 1] AI Planner analyzing goal and creating plan...")
        plan = self.planner.plan_task(goal, repo_summary=repo_summary)
        if test_command:
            plan["test_command"] = test_command

        session_log.append(
            {
                "step": 1,
                "role": "Planner",
                "action": "plan_task",
                "output": plan,
                "timestamp": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
            }
        )

        current_instructions = plan.get("instructions", goal)
        current_files = plan.get("files_to_modify", [])
        current_test_cmd = plan.get("test_command", test_command)

        attempt = 0
        is_approved = False
        final_worker_result = {}
        final_review_result = {}

        # Step 2-5: Implementation and Review / Correction Loop
        while attempt < self.max_retries and not is_approved:
            attempt += 1
            logger.info(
                f"[Step 2] Codex Worker executing task (Attempt {attempt}/{self.max_retries})..."
            )

            # Delegate to Codex
            worker_result = self.worker.execute_task(
                task_name=f"{plan.get('task_name', 'task')}_attempt_{attempt}",
                instructions=current_instructions,
                repo_path=repo_path,
                files_to_modify=current_files,
            )
            final_worker_result = worker_result

            session_log.append(
                {
                    "step": 2,
                    "attempt": attempt,
                    "role": "CodexWorker",
                    "action": "execute_task",
                    "output": {
                        "success": worker_result.get("success"),
                        "task_id": worker_result.get("task_id"),
                        "changed_files": worker_result.get("changed_files"),
                        "summary": worker_result.get("summary"),
                    },
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                }
            )

            # Step 3: Reviewer evaluates changes and executes automated tests
            logger.info(
                f"[Step 3] Independent Reviewer evaluating changes and running tests..."
            )
            review_result = self.reviewer.review(
                goal=goal,
                repo_path=repo_path,
                changed_files=worker_result.get("changed_files", []),
                test_command=current_test_cmd,
            )
            final_review_result = review_result

            session_log.append(
                {
                    "step": 3,
                    "attempt": attempt,
                    "role": "Reviewer",
                    "action": "review",
                    "output": review_result,
                    "timestamp": datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat(),
                }
            )

            is_approved = review_result.get("approved", False)
            if is_approved:
                logger.info(
                    f"✓ Reviewer APPROVED implementation on attempt {attempt}!"
                )
                break

            logger.warning(
                f"✗ Reviewer REJECTED implementation on attempt {attempt}: {review_result.get('defects')}"
            )

            # Step 4: If not approved and retries remain, Planner plans surgical correction
            if attempt < self.max_retries:
                logger.info(
                    f"[Step 4] AI Planner formulating surgical correction task..."
                )
                correction_plan = self.planner.plan_correction(
                    original_plan=plan, reviewer_report=review_result
                )
                current_instructions = correction_plan.get(
                    "instructions", current_instructions
                )
                current_files = correction_plan.get(
                    "files_to_modify", current_files
                )

                session_log.append(
                    {
                        "step": 4,
                        "attempt": attempt,
                        "role": "Planner",
                        "action": "plan_correction",
                        "output": correction_plan,
                        "timestamp": datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                    }
                )

        # Step 6: Final Verification by Planner
        logger.info("[Step 6] AI Planner conducting final verification...")
        verification = self.planner.verify_completion(
            goal=goal,
            plan=plan,
            worker_result=final_worker_result,
            review_result=final_review_result,
        )

        session_log.append(
            {
                "step": 6,
                "role": "Planner",
                "action": "verify_completion",
                "output": verification,
                "timestamp": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
            }
        )

        final_summary = {
            "session_id": session_id,
            "goal": goal,
            "repo_path": str(repo_path),
            "status": verification.get("status", "FAILED"),
            "attempts": attempt,
            "approved": is_approved,
            "changed_files": final_worker_result.get("changed_files", []),
            "tests_passed": final_review_result.get("test_passed", False),
            "verification": verification,
            "history": session_log,
        }

        # Save session file
        state_file = STATE_DIR / f"{session_id}.json"
        state_file.write_text(json.dumps(final_summary, indent=2))
        logger.info(
            f"=== Cycle finished with status: {final_summary['status']} (saved to {state_file}) ==="
        )

        return final_summary
