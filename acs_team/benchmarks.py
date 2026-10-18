"""Reproducible disposable golden harness; fake scoring proves only this harness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import resource
import subprocess
from .aggregate_limits import managed_temporary_directory
import time

from .coordination import CoordinationStore
from .db import DatabaseManager
from .schemas import Plan, Review
from .security import redact
from .team_runner import IndependentTester, TeamRunner
from .worker_adapters import BaseWorker, WorkerRegistry
from .worktree_manager import WorktreeManager


def compare_benchmark(baseline: dict, current: dict) -> list[str]:
    if (
        baseline["workers"] != current["workers"]
        or baseline["suite"] != current["suite"]
    ):
        raise ValueError(
            "Benchmark comparisons require identical worker mode and suite"
        )
    before = {r["name"]: r for r in baseline["results"]}
    after = {r["name"]: r for r in current["results"]}
    issues = [
        f"{name}: missing benchmark" for name in sorted(before.keys() - after.keys())
    ]
    issues += [
        f"{name}: pass-rate regression"
        for name in before.keys() & after.keys()
        if before[name]["passed"] and not after[name]["passed"]
    ]
    return issues


class FixtureWorker(BaseWorker):
    def __init__(self, name: str, solution: dict[str, str]):
        super().__init__(name)
        self.solution = solution

    def execute_task(
        self,
        task_id,
        goal,
        instructions,
        worktree_path,
        files_to_modify=None,
        timeout_seconds=300,
    ):
        for name in files_to_modify or []:
            destination = worktree_path / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(self.solution[name])
        return {
            "success": True,
            "summary": "Deterministic fixture implementation (simulation)",
        }


def fixture_verification(command, workspace, timeout=180):
    """ONLY fixed trusted golden/test fixtures; never used for real provider output.

    Cloud fixtures prove orchestration/test counting without claiming OS isolation.
    Production run_verification always requests bwrap and fails closed if unavailable.
    """
    from .security import verification_argv, verification_summary
    from .supervision import ProcessSupervisor

    result = ProcessSupervisor().run(
        verification_argv(command), workspace, timeout=timeout,
        env={'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONNOUSERSITE':'1'},
    )
    return verification_summary({**result, "isolation": "TRUSTED_FIXTURE_SIMULATION"})


def run_benchmarks(
    suite: str = "smoke", workers: str = "fake", cases_path: Path | None = None
) -> dict:
    if suite not in {"smoke", "full"} or workers not in {"fake", "real"}:
        raise ValueError("Invalid benchmark mode")
    path = cases_path or Path(__file__).with_name("golden_cases.json")
    data = json.loads(path.read_text())
    cases = data["cases"][:2] if suite == "smoke" else data["cases"]
    if len(cases) > 20:
        raise ValueError("Benchmark corpus exceeds budget")
    if workers == "real":
        # Real authenticated adapters and independent tester/reviewer roles must
        # be verified locally before costly provider executions can be offered.
        available = WorkerRegistry().list_available_workers()
        return {
            "schema_version": 1,
            "suite": suite,
            "workers": workers,
            "label": "LOCAL_VERIFICATION_REQUIRED",
            "status": "BLOCKED",
            "reason": "Real benchmark role adapters/local verification are incomplete",
            "verified_workers": available,
            "results": [],
            "pass_rate": None,
        }
    results = []
    start = time.monotonic()
    for case in cases:
        case_start = time.monotonic()
        with managed_temporary_directory(prefix="acs-golden-") as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()

            def git(*args):
                return subprocess.run(
                    ["git", *args], cwd=repo, check=True, capture_output=True, text=True
                ).stdout.strip()

            git("init", "-b", "main")
            git("config", "user.name", "ACS Fixture")
            git("config", "user.email", "fixture@example.invalid")
            (repo / "README.md").write_text("Disposable golden fixture.\n")
            for name, content in case["initial"].items():
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            git("add", ".")
            git("commit", "-m", "fixture baseline")
            before = git("rev-parse", "HEAD")
            status = git("status", "--porcelain")
            tasks = []
            scopes = (
                [[name] for name in case["solution"]]
                if case["category"] == "collaboration"
                else [list(case["solution"])]
            )
            for index, owns in enumerate(scopes):
                tasks.append(
                    {
                        "task_id": f"t{index}",
                        "title": case["goal"],
                        "description": case["goal"],
                        "owns": owns,
                        "acceptance_criteria": [case["goal"]],
                        "verification_commands": [["pytest", "-q"]],
                        "risk_level": "low",
                    }
                )
            plan = Plan.model_validate(
                {
                    "mission_id": case["name"],
                    "requirements": [case["goal"]],
                    "tasks": tasks,
                }
            )
            db = DatabaseManager(root / "state.db")
            clock = [100.0]
            store = CoordinationStore(db, clock=lambda: clock[0])
            if case["category"] == "failure-recovery":
                store.register(plan, str(repo))
                store.claim(plan.mission_id, "t0", "dead-fixture", 1)
                clock[0] = 102.0
                store.recover(
                    plan.mission_id,
                    "t0",
                    lambda row: (
                        row["worker"] == "dead-fixture" and row["process"] is None
                    ),
                    lambda row: row["worktree"] is None,
                )
            registry: dict[str, BaseWorker] = {
                name: FixtureWorker(name, case["solution"])
                for name in ("fixture-a", "fixture-b", "fixture-c")
            }

            def prepare(task, requirements):
                text = case["test"]
                if case["category"] == "collaboration":
                    text = text.replace("{module}", Path(task.owns[0]).stem)
                return {f"tests/test_acceptance_{task.task_id}.py": text}

            def review(task, worktree, implementer, sha):
                return Review(
                    task_id=task.task_id,
                    implementer=implementer,
                    reviewer="fixture-reviewer",
                    commit_sha=sha,
                    verdict="PASS",
                    requirement_coverage=task.acceptance_criteria,
                )

            runner = TeamRunner(
                store,
                registry,
                IndependentTester("fixture-tester", prepare),
                {"fixture-reviewer": review},
                WorktreeManager(root / "worktrees", min_free_gb=0),
                root / "artifacts",
                "disposable-benchmark-signing-key",
                verification_runner=fixture_verification,
            )
            previous = os.environ.get("ACS_ENABLE_COORDINATION")
            os.environ["ACS_ENABLE_COORDINATION"] = "1"
            try:
                outcome = runner.run(plan, repo)
                passed = (
                    outcome["status"] == "COMPLETED"
                    and git("rev-parse", "HEAD") == before
                    and git("status", "--porcelain") == status
                )
                errors = outcome["errors"]
            except Exception as exc:
                passed = False
                errors = {"harness": redact(str(exc))[:2048]}
            finally:
                if previous is None:
                    os.environ.pop("ACS_ENABLE_COORDINATION", None)
                else:
                    os.environ["ACS_ENABLE_COORDINATION"] = previous
            results.append(
                {
                    "name": case["name"],
                    "category": case["category"],
                    "passed": passed,
                    "runtime_seconds": round(time.monotonic() - case_start, 3),
                    "errors": errors,
                }
            )
    return {
        "schema_version": 1,
        "suite": suite,
        "workers": workers,
        "label": "CLOUD_SIMULATED",
        "status": "PASS" if all(r["passed"] for r in results) else "FAIL",
        "results": results,
        "pass_rate": sum(r["passed"] for r in results) / len(results),
        "runtime_seconds": round(time.monotonic() - start, 3),
        "max_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "measurement_note": "Harness child high-water RSS on this machine; not a laptop/provider measurement",
    }
