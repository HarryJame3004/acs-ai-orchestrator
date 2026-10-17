import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from .config import MODEL_REVIEWER
from .llm_client import query_llm, extract_json_block

logger = logging.getLogger("acs_team.reviewer")

REVIEWER_SYSTEM_PROMPT = """You are an Independent Senior Code Reviewer and Quality Assurance Engineer for ACS.
Your job is to thoroughly inspect code changes, git diffs, and test outputs.
You are strict, objective, and constructive.

Evaluation criteria:
1. Correctness: Does the implementation fulfill the goal without bugs?
2. Test pass: Did the automated test suite pass completely?
3. Edge Cases & Regressions: Are there subtle edge cases, unhandled errors, or regressions?
4. Cleanliness: Minimal diffs, no unnecessary refactoring or debug garbage.

Output format must be clean JSON.
"""


class CodeReviewer:
    def __init__(self, model: str = MODEL_REVIEWER):
        self.model = model

    def run_tests(
        self, repo_path: Path, test_command: str = "pytest"
    ) -> Dict[str, Any]:
        """Execute automated tests in the repository and capture results."""
        from .security import run_verification
        try:
            result = run_verification(test_command, repo_path, 300)
            return {**result, "returncode": result["exit_code"]}
        except Exception as error:
            return {"passed": False, "returncode": -1, "output": str(error)}

    def get_git_diff(self, repo_path: Path) -> str:
        """Get unstaged or latest git diff."""
        try:
            diff = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            ).stdout.strip()
            if not diff:
                diff = subprocess.run(
                    ["git", "diff"],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            if not diff:
                diff = subprocess.run(
                    ["git", "status", "--short"],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            return diff[-4000:] if len(diff) > 4000 else diff
        except Exception as e:
            return f"Could not retrieve diff: {e}"

    def review(
        self,
        goal: str,
        repo_path: Path,
        changed_files: List[str],
        test_command: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform comprehensive independent review and test verification."""
        # 1. Run tests if test_command provided
        test_result: Dict[str, Any] = {"passed": False, "returncode": -1, "output": "No test command specified; verification is incomplete."}
        if test_command:
            test_result = self.run_tests(repo_path, test_command)

        # 2. Get diff
        diff_text = self.get_git_diff(repo_path)

        # 3. LLM Review via free-review model
        prompt = f"""GOAL:
{goal}

CHANGED FILES:
{changed_files}

GIT DIFF / STATUS:
{diff_text}

AUTOMATED TEST RESULT:
Passed: {test_result['passed']}
Output:
{test_result['output']}

Evaluate whether this implementation is ready to be approved.
If automated tests FAILED, you MUST mark approved=false and list the test failure in defects.
If automated tests PASSED and the code satisfies the goal without defects, mark approved=true.

Respond ONLY with a JSON object with this schema:
{{
  "approved": true/false,
  "summary": "Concise review verdict",
  "defects": ["issue 1", "issue 2"],
  "recommendations": "Specific fix recommendations if issues found"
}}
"""
        logger.info("Submitting diff and test results to Reviewer model...")
        resp = query_llm(
            prompt, system_prompt=REVIEWER_SYSTEM_PROMPT, model=self.model
        )

        try:
            if not isinstance(resp, str) or len(resp.encode()) > 32768:
                raise ValueError("Reviewer output exceeds the bounded text contract")
            review_data = extract_json_block(resp)
            if (
                not isinstance(review_data, dict)
                or type(review_data.get("approved")) is not bool
                or not isinstance(review_data.get("summary"), str)
                or not isinstance(review_data.get("recommendations"), str)
                or not isinstance(review_data.get("defects"), list)
                or len(review_data["defects"]) > 32
                or not all(isinstance(item, str) for item in review_data["defects"])
            ):
                raise ValueError("Invalid independent reviewer output")
            if review_data["defects"]:
                review_data["approved"] = False
        except Exception:
            # Passing tests cannot substitute for an independent review.
            review_data = {
                "approved": False,
                "summary": "Independent review is incomplete",
                "defects": ["Missing or invalid independent reviewer output"],
                "recommendations": "Obtain a valid review; preserve all security gates",
            }

        # Override approved flag if automated tests definitively failed
        if not test_result["passed"]:
            review_data["approved"] = False
            if not review_data.get("defects"):
                review_data["defects"] = [
                    f"Test command failed with code {test_result['returncode']}"
                ]

        review_data["test_passed"] = test_result["passed"]
        review_data["test_output"] = test_result["output"]
        return review_data
