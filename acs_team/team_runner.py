"""Opt-in coordinated execution with real Git, SQLite, tests and Guardian gates.

Workers and independent tester/reviewer adapters are supplied by the host. No
worker-produced message can grant permissions or approve its own changes.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess
import threading
import uuid
from typing import Callable

from .coordination import ClaimDenied, CoordinationStore
from .evidence import EvidenceEngine, persist_evidence
from .guardian import Guardian
from .ownership import validate_changes
from .runtime_control import RuntimeControl
from .schemas import Message, Plan, Review, Task
from .scope_and_integration import IntegrationManager, ScopeManager
from .security import contained_path, redact, run_verification
from .test_policy import baseline_findings
from .worker_adapters import BaseWorker
from .worktree_manager import WorktreeManager
from .managed_worker import worker_context


@dataclass(frozen=True)
class IndependentTester:
    worker_id: str
    # Derive contract tests from requirements BEFORE implementation.
    prepare: Callable[[Task, list[str]], dict[str, str]]


class TeamRunner:
    def __init__(
        self,
        store: CoordinationStore,
        workers: dict[str, BaseWorker],
        tester: IndependentTester,
        reviewers: dict[str, Callable[[Task, Path, str, str], Review]],
        worktrees: WorktreeManager,
        artifacts: Path,
        evidence_key: str,
        concurrency: int = 2,
    ):
        if not 1 <= concurrency <= 3 or not reviewers:
            raise ValueError("Bounded concurrency and independent reviewers required")
        self.store, self.workers, self.tester, self.reviewers = (
            store,
            workers,
            tester,
            reviewers,
        )
        self.worktrees, self.artifacts, self.key, self.concurrency = (
            worktrees,
            artifacts,
            evidence_key,
            concurrency,
        )
        self.control = RuntimeControl(store.db, initialize=False)
        self._allocation = threading.Lock()

    def _worker(self, task: Task, busy: set[str]) -> tuple[str, BaseWorker]:
        available = [
            (name, worker)
            for name, worker in self.workers.items()
            if name not in busy
            and name != self.tester.worker_id
            and worker.is_verified
            and (task.worker == "auto" or task.worker == name)
        ]
        if not available:
            raise ClaimDenied("No verified available implementer")
        return sorted(available, key=lambda pair: pair[0])[0]

    def _execute(
        self,
        plan: Plan,
        task: Task,
        root: Path,
        worker_id: str,
        worker: BaseWorker,
        token: int,
        base: str,
    ) -> dict:
        worktree = None
        done = threading.Event()
        lost = threading.Event()

        def heartbeat():
            while not done.wait(10):
                try:
                    self.store.heartbeat(plan.mission_id, task.task_id, token)
                except Exception:
                    lost.set()
                    return

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            self.control.require_dispatch()
            with self._allocation:
                worktree = self.worktrees.create_worktree(
                    root,
                    plan.mission_id,
                    f"{task.task_id}-{uuid.uuid4().hex[:8]}",
                    base_ref=base,
                )
            self.store.heartbeat(
                plan.mission_id, task.task_id, token, worktree=str(worktree)
            )
            # Tester has no worker checkout or implementation at this point.
            supplied = self.tester.prepare(task, plan.requirements)
            if not supplied or len(supplied) > 16:
                raise ValueError("Independent bounded contract tests required")
            protected = {}
            for name, code in supplied.items():
                if (
                    not name.startswith("tests/")
                    or not Path(name).name.startswith("test_")
                    or not name.endswith(".py")
                    or len(code.encode()) > 65536
                ):
                    raise ValueError("Invalid tester artifact")
                from .test_policy import inspect_tests

                checks = inspect_tests(code)
                if not checks or any(v["trivial"] for v in checks.values()):
                    raise ValueError(
                        "Independent tests must contain substantive assertions"
                    )
                path = contained_path(worktree, name)
                if path.exists():
                    raise PermissionError("Tester may not replace baseline files")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(code)
                protected[name] = hashlib.sha256(code.encode()).hexdigest()
            with worker_context(self.control, plan.mission_id):
                result = worker.execute_task(
                    task_id=task.task_id,
                    goal=task.title,
                    instructions=task.description,
                    worktree_path=worktree,
                    files_to_modify=task.owns,
                )
            if lost.is_set():
                raise ClaimDenied("Lost task ownership while worker was running")
            self.control.require_dispatch()
            if not result.get("success"):
                raise RuntimeError("Worker reported failure")
            for name, digest in protected.items():
                path = contained_path(worktree, name)
                if (
                    not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != digest
                ):
                    raise PermissionError(
                        "Worker modified independent acceptance tests"
                    )
            if baseline_findings(worktree, base):
                raise PermissionError(
                    "Baseline test modification requires explicit review"
                )
            _, names, _ = ScopeManager().verify_diff_against_scope(
                worktree, [*task.owns, *protected], base_ref=base
            )
            validate_changes(
                worktree, [n for n in names if n not in protected], task.owns
            )
            if not names:
                raise ValueError("Task produced no changes")
            tests = [
                run_verification(command, worktree)
                for command in task.verification_commands
            ]
            independent = run_verification(["pytest", "-q", *protected], worktree)
            if not independent["passed"] or not all(t["passed"] for t in tests):
                raise ValueError(
                    "Task verification or independent contract tests failed"
                )
            subprocess.run(
                ["git", "add", "-A", "--", *names],
                cwd=worktree,
                check=True,
                capture_output=True,
            )
            environment = {
                **os.environ,
                "GIT_AUTHOR_NAME": "ACS AI",
                "GIT_AUTHOR_EMAIL": "acsai@local.audit",
                "GIT_COMMITTER_NAME": "ACS AI",
                "GIT_COMMITTER_EMAIL": "acsai@local.audit",
            }
            staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet"], cwd=worktree
            )
            if staged.returncode == 1:
                subprocess.run(
                    ["git", "commit", "-m", f"Implement task {task.task_id}"],
                    cwd=worktree,
                    env=environment,
                    check=True,
                    capture_output=True,
                )
            elif staged.returncode != 0:
                raise RuntimeError("Cannot inspect task staging")
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            reviewer_id = next(
                (r for r in sorted(self.reviewers) if r != worker_id), None
            )
            if reviewer_id is None:
                raise PermissionError("Independent review unavailable")
            review = Review.model_validate(
                self.reviewers[reviewer_id](task, worktree, worker_id, sha).model_dump()
            )
            if (
                review.reviewer != reviewer_id
                or review.implementer != worker_id
                or review.commit_sha != sha
                or review.task_id != task.task_id
                or review.verdict != "PASS"
                or not set(task.acceptance_criteria).issubset(
                    review.requirement_coverage
                )
            ):
                raise PermissionError(
                    "Independent review rejected or is not bound to task/commit/criteria"
                )
            diff = subprocess.run(
                ["git", "diff", f"{base}..{sha}"],
                cwd=worktree,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            if len(diff.encode()) > 1024 * 1024:
                raise ValueError("Diff exceeds evidence budget")
            evidence = (
                EvidenceEngine(self.key)
                .create_evidence(
                    plan.mission_id, task.task_id, sha, independent, {"diff_text": diff}
                )
                .to_dict()
            )
            persist_evidence(evidence, self.artifacts)
            verdict = Guardian(self.store.db, self.key).evaluate(
                plan.mission_id,
                root,
                worktree,
                f"acsai/mission/{plan.mission_id}",
                sha,
                evidence,
                names,
                test_command=" ".join(task.verification_commands[0]),
            )
            if not verdict.approved:
                raise PermissionError("Guardian vetoed task")
            # Re-check after reviewer and Guardian callbacks, which are also
            # untrusted producers. Signed evidence must describe a clean SHA.
            if (
                subprocess.run(
                    ["git", "diff", "HEAD", "--quiet"], cwd=worktree
                ).returncode
                != 0
            ):
                raise PermissionError("Worktree changed after commit-bound review")
            _, final_names, _ = ScopeManager().verify_diff_against_scope(
                worktree, [*task.owns, *protected], base_ref=base
            )
            if final_names != names:
                raise PermissionError("Task file set changed after review")
            self.store.publish(
                Message(
                    mission_id=plan.mission_id,
                    task_id=task.task_id,
                    sender=worker_id,
                    recipient="integrator",
                    kind="handoff",
                    payload={"commit": sha, "reviewer": reviewer_id},
                ),
                worker_id,
            )
            completion = {
                "commit": sha,
                "branch": branch,
                "worktree": str(worktree),
                "tests": tests,
                "independent_tests": independent,
                "review": review.model_dump(),
                "files": names,
                "test_files": list(protected),
            }
            self.store.complete(plan.mission_id, task.task_id, token, completion)
            return completion
        finally:
            done.set()
            thread.join(timeout=1)

    def run(self, plan: Plan, repository: Path) -> dict:
        if os.environ.get("ACS_ENABLE_COORDINATION") != "1":
            raise PermissionError("Coordination is disabled")
        # Revalidate even trusted callers; nested lists in frozen models can mutate.
        plan = Plan.model_validate(plan.model_dump())
        repository = repository.resolve()
        self.control.require_dispatch()
        Guardian(self.store.db, self.key).verify_corelock_safety(str(repository), [])
        self.store.register(plan, str(repository))
        integration = IntegrationManager(
            repository, worktrees_dir=self.worktrees.worktrees_dir
        )
        branch = integration.ensure_integration_branch(plan.mission_id, "HEAD")
        busy: set[str] = set()
        running: dict = {}
        failures: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            while True:
                self.control.require_dispatch()
                states = {
                    r["task"]: r["state"] for r in self.store.tasks(plan.mission_id)
                }
                for task in plan.tasks:
                    if (
                        len(running) >= self.concurrency
                        or states[task.task_id] != "PENDING"
                        or task.task_id in failures
                    ):
                        continue
                    try:
                        worker_id, worker = self._worker(task, busy)
                        token = self.store.claim(
                            plan.mission_id, task.task_id, worker_id
                        )
                    except ClaimDenied:
                        continue
                    base = subprocess.run(
                        ["git", "rev-parse", branch],
                        cwd=repository,
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    future = pool.submit(
                        self._execute,
                        plan,
                        task,
                        repository,
                        worker_id,
                        worker,
                        token,
                        base,
                    )
                    running[future] = (task, worker_id, token)
                    busy.add(worker_id)
                if not running:
                    break
                ready, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in ready:
                    task, worker_id, token = running.pop(future)
                    busy.remove(worker_id)
                    try:
                        completion = future.result()

                        def integrate():
                            self.control.require_dispatch()
                            merged = integration.merge_task_branch(
                                branch, completion["branch"]
                            )
                            try:
                                all_tests = [
                                    run_verification(
                                        cmd, Path(merged["integration_worktree"])
                                    )
                                    for completed in plan.tasks
                                    if completed.task_id == task.task_id
                                    or states[completed.task_id] == "INTEGRATED"
                                    for cmd in completed.verification_commands
                                ]
                                contract_tests = run_verification(
                                    ["pytest", "-q", "tests"],
                                    Path(merged["integration_worktree"]),
                                )
                                if not contract_tests["passed"] or not all(
                                    t["passed"] for t in all_tests
                                ):
                                    raise ValueError(
                                        "Post-integration verification failed"
                                    )
                                final_diff = subprocess.run(
                                    [
                                        "git",
                                        "diff",
                                        f"{merged['previous_commit_sha']}..{merged['integrated_commit_sha']}",
                                    ],
                                    cwd=merged["integration_worktree"],
                                    check=True,
                                    capture_output=True,
                                    text=True,
                                ).stdout
                                final_evidence = (
                                    EvidenceEngine(self.key)
                                    .create_evidence(
                                        plan.mission_id,
                                        task.task_id,
                                        merged["integrated_commit_sha"],
                                        contract_tests,
                                        {"diff_text": final_diff},
                                    )
                                    .to_dict()
                                )
                                evidence_path = persist_evidence(
                                    final_evidence, self.artifacts
                                )
                                return {
                                    "evidence_ref": str(evidence_path),
                                    **merged,
                                    "tests": all_tests,
                                    "contract_tests": contract_tests,
                                }
                            except Exception:
                                integration.rollback_integration(
                                    merged["previous_commit_sha"]
                                )
                                raise

                        self.store.integration(
                            plan.mission_id, task.task_id, token, integrate
                        )
                    except Exception as exc:
                        failures[task.task_id] = redact(str(exc))[:4096]
                        try:
                            self.store.fail(
                                plan.mission_id,
                                task.task_id,
                                token,
                                failures[task.task_id],
                            )
                        except ClaimDenied:
                            pass  # Expired ownership remains locked for explicit recovery.
        rows = self.store.tasks(plan.mission_id)
        return {
            "mission_id": plan.mission_id,
            "status": "COMPLETED"
            if all(r["state"] == "INTEGRATED" for r in rows)
            else "BLOCKED",
            "tasks": rows,
            "errors": failures,
            "integration_branch": branch,
        }
