import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from .config import AGPAIR_BIN, CODEX_BIN

logger = logging.getLogger("acs_team.worker")


class CodexWorker:
    def __init__(self, agpair_bin: Path = AGPAIR_BIN):
        self.agpair_bin = agpair_bin

    def execute_task(
        self,
        task_name: str,
        instructions: str,
        repo_path: Path,
        files_to_modify: Optional[List[str]] = None,
        timeout_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        """Dispatch a coding task to Codex CLI via agpair lifecycle."""
        logger.info(
            f"Dispatching task '{task_name}' to Codex CLI worker in {repo_path}..."
        )

        body_prompt = f"""Task: {task_name}
Instructions:
{instructions}

Target files: {', '.join(files_to_modify) if files_to_modify else 'Appropriate repository files'}
Requirements:
1. Make surgical, minimal changes directly serving the instructions.
2. Ensure any new or modified functions are clean, syntax-error-free, and follow project patterns.
3. Verify files and syntax before concluding.
"""

        cmd = [
            str(self.agpair_bin),
            "task",
            "start",
            "--executor",
            "codex",
            "--task-kind",
            "implementation",
            "--repo-path",
            str(repo_path),
            "--body",
            body_prompt,
            "--timeout-seconds",
            str(timeout_seconds),
            "--json",
        ]

        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=timeout_seconds + 30,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # Parse agpair JSON output
        parsed_data = {}
        if stdout:
            try:
                parsed_data = json.loads(stdout)
            except json.JSONDecodeError:
                # If wrapped or multi-line, find JSON block
                for line in reversed(stdout.splitlines()):
                    line = line.strip()
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            parsed_data = json.loads(line)
                            break
                        except Exception:
                            pass

        task_state = parsed_data.get("task", {})
        receipt = task_state.get("terminal_receipt", {})
        payload = receipt.get("payload", {})

        changed_files = (
            payload.get("changed_files")
            or payload.get("scope_validation", {}).get("actual_changed_files")
            or []
        )
        # Filter out agpair receipt/log files from changed files list
        code_changed_files = [
            f
            for f in changed_files
            if not f.endswith(".receipt.json") and not f.endswith(".validation.log")
        ]

        success = (
            result.returncode == 0
            and task_state.get("phase") in ["ready_for_review", "completed"]
        )

        return {
            "success": success,
            "task_id": task_state.get("task_id", "UNKNOWN"),
            "phase": task_state.get("phase", "UNKNOWN"),
            "changed_files": code_changed_files,
            "summary": receipt.get("summary")
            or task_state.get("executor_output_excerpt", ""),
            "raw_stdout": stdout,
            "raw_stderr": stderr,
            "receipt_path": payload.get("receipt_path"),
            "evidence_path": task_state.get("evidence_path"),
        }
