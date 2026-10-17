import logging
from typing import Any, Dict, Optional
from .config import MODEL_PLANNER, CONTEXT_FILE
from .llm_client import query_llm, extract_json_block

logger = logging.getLogger("acs_team.planner")

PLANNER_SYSTEM_PROMPT = """You are the Lead AI Planner for the Autonomous Coding System (ACS).
Your job is to analyze user requests, understand the project roadmap and constraints, decompose tasks, delegate to workers, evaluate feedback from code reviewers and automated tests, and verify final completion.

You strictly follow these engineering principles:
1. Simplicity First: Write minimal, clear, and complete specifications.
2. Surgical Changes: Target only the relevant files and functions.
3. Test-Driven: Every task must specify clear test/verification criteria.
4. Output must be clean, structured JSON where requested.
"""


class AIPlanner:
    def __init__(self, model: str = MODEL_PLANNER):
        self.model = model
        self.project_context = self._load_project_context()

    def _load_project_context(self) -> str:
        if CONTEXT_FILE.exists():
            try:
                return CONTEXT_FILE.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not read context file: {e}")
        return "Autonomous Coding System (ACS) Project"

    def plan_task(self, goal: str, repo_summary: str = "") -> Dict[str, Any]:
        """Decompose a high-level goal into an actionable worker specification."""
        prompt = f"""PROJECT CONTEXT:
{self.project_context[:1500]}

REPOSITORY CONTEXT:
{repo_summary}

USER GOAL:
{goal}

Generate a structured execution plan for the Codex CLI worker.
Respond ONLY with a JSON object with this schema:
{{
  "task_name": "short identifier",
  "goal_summary": "one sentence goal",
  "files_to_modify": ["path1", "path2"],
  "instructions": "clear step-by-step instructions for Codex CLI",
  "test_command": "shell command to run tests (e.g. pytest or python test.py)",
  "acceptance_criteria": ["criterion 1", "criterion 2"]
}}
"""
        logger.info(f"AI Planner decomposing goal with model {self.model}...")
        resp = query_llm(
            prompt, system_prompt=PLANNER_SYSTEM_PROMPT, model=self.model
        )
        try:
            return extract_json_block(resp)
        except Exception as e:
            logger.warning(f"JSON extraction failed, using fallback plan: {e}")
            return {
                "task_name": "implementation_task",
                "goal_summary": goal,
                "files_to_modify": [],
                "instructions": goal,
                "test_command": "pytest",
                "acceptance_criteria": [
                    "Code implemented correctly",
                    "Automated tests pass",
                ],
            }

    def plan_correction(
        self, original_plan: Dict[str, Any], reviewer_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Formulate a targeted correction task when Reviewer or tests identify defects."""
        prompt = f"""The Codex implementation had issues identified during review and testing.

ORIGINAL PLAN:
{original_plan}

REVIEWER & TEST FEEDBACK:
{reviewer_report}

Formulate surgical correction instructions for the Codex CLI worker to fix the exact defect.
Respond ONLY with a JSON object with this schema:
{{
  "task_name": "correction_task",
  "goal_summary": "summary of the fix needed",
  "files_to_modify": ["path1"],
  "instructions": "exact instructions on how to resolve the defect",
  "test_command": "{original_plan.get('test_command', 'pytest')}",
  "acceptance_criteria": ["All automated tests pass", "Defect resolved"]
}}
"""
        logger.info(f"AI Planner formulating correction task...")
        resp = query_llm(
            prompt, system_prompt=PLANNER_SYSTEM_PROMPT, model=self.model
        )
        try:
            return extract_json_block(resp)
        except Exception:
            return {
                "task_name": "correction_task",
                "goal_summary": "Fix defects identified in review",
                "files_to_modify": original_plan.get("files_to_modify", []),
                "instructions": f"Fix issues reported by reviewer: {reviewer_report.get('summary', '')}. Reviewer details: {reviewer_report.get('defects', [])}",
                "test_command": original_plan.get("test_command", "pytest"),
                "acceptance_criteria": ["All tests pass"],
            }

    def verify_completion(
        self,
        goal: str,
        plan: Dict[str, Any],
        worker_result: Dict[str, Any],
        review_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Final verification that the work meets all acceptance criteria."""
        tests_passed = review_result.get("test_passed", False)
        approved = review_result.get("approved", False)

        is_complete = tests_passed and approved

        return {
            "verified": is_complete,
            "status": "COMPLETED" if is_complete else "FAILED",
            "summary": (
                "All acceptance criteria met and verified by Reviewer"
                if is_complete
                else f"Verification failed: Review approved={approved}, Tests passed={tests_passed}"
            ),
            "evidence": {
                "changed_files": worker_result.get("changed_files", []),
                "test_passed": tests_passed,
                "review_summary": review_result.get("summary", ""),
            },
        }
