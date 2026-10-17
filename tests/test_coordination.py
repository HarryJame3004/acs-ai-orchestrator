"""Real local SQLite/Git policy, with explicitly simulated worker scenarios."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import subprocess
import threading

import pytest
from pydantic import ValidationError

from acs_team.coordination import ClaimDenied, CoordinationStore
from acs_team.db import DatabaseManager
from acs_team.ownership import matches, overlaps, scope, validate_changes
from acs_team.schemas import Message, Plan, Review, parse_data
from acs_team.team_runner import IndependentTester, TeamRunner
from acs_team.test_policy import inspect_tests
from acs_team.worker_adapters import BaseWorker
from acs_team.worktree_manager import WorktreeManager


def plan(mission="mission", scopes=("alpha.py", "beta.py"), dependencies=False):
    return Plan.model_validate(
        {
            "mission_id": mission,
            "requirements": ["Functions return 42"],
            "tasks": [
                {
                    "task_id": f"t{i}",
                    "title": f"Implement {name}",
                    "description": f"Implement {name} with value() returning 42",
                    "owns": [name],
                    "depends_on": ["t0"] if dependencies and i else [],
                    "acceptance_criteria": ["value() returns 42"],
                    "verification_commands": [["pytest", "-q"]],
                    "risk_level": "low",
                }
                for i, name in enumerate(scopes)
            ],
        }
    )


def store(tmp_path, clock=None):
    return CoordinationStore(
        DatabaseManager(tmp_path / "state.db"), **({"clock": clock} if clock else {})
    )


@pytest.mark.parametrize(
    "bad",
    [
        "**",
        "../src",
        "/tmp/source",
        ".git/**",
        ".github/workflows/*",
        "src//a",
        "src/../a",
        "*/*",
        "src/[ab]",
    ],
)
def test_invalid_ownership_rejected(bad):
    with pytest.raises(ValueError):
        scope(bad)


def test_glob_overlap_casefold_and_actual_symlinks(tmp_path):
    assert overlaps("src/a*.py", "src/*b.py")
    assert overlaps("SRC/**", "src/sub/new.py")
    assert not overlaps("src/auth/**", "src/payments/**")
    assert matches("src/**/*.py", "src/a.py") and matches("src/**/*.py", "src/sub/a.py")
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "repo"
    root.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(PermissionError):
        validate_changes(root, ["link/secret"], ["link/**"])
    with pytest.raises(PermissionError):
        validate_changes(root, ["src/a.py", "src/A.py"], ["src/**"])


def test_strict_plan_cycles_unknown_commands_and_payload_limits():
    obj = plan().model_dump()
    obj["tasks"][0]["depends_on"] = ["t1"]
    obj["tasks"][1]["depends_on"] = ["t0"]
    with pytest.raises(ValidationError):
        Plan.model_validate(obj)
    obj = plan().model_dump()
    obj["tasks"][0]["verification_commands"] = [["sh", "-c", "pytest"]]
    with pytest.raises((ValidationError, PermissionError)):
        Plan.model_validate(obj)
    with pytest.raises(ValueError):
        parse_data(Plan, b" " * 65537)
    with pytest.raises(ValueError):
        parse_data(Plan, '{"mission_id":"a","mission_id":"b"}')
    with pytest.raises(ValidationError):
        parse_data(Plan, '{"schema_version":2}')


def test_real_sqlite_atomic_claim_race_and_restart(tmp_path):
    engine = store(tmp_path)
    engine.register(plan(scopes=("src/**", "src/a*.py")), str(tmp_path / "repo"))
    barrier = threading.Barrier(8)

    def race(i):
        other = CoordinationStore(DatabaseManager(tmp_path / "state.db"))
        barrier.wait()
        try:
            return other.claim("mission", "t0" if i % 2 else "t1", f"worker{i}")
        except ClaimDenied:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens = list(pool.map(race, range(8)))
    assert sum(v is not None for v in tokens) == 1
    assert (
        len(
            [
                r
                for r in CoordinationStore(engine.db).tasks("mission")
                if r["state"] == "RUNNING"
            ]
        )
        == 1
    )
    with engine.db.connection() as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_expiry_death_worktree_fencing_and_duplicate_completion(tmp_path):
    now = [100.0]
    engine = store(tmp_path, lambda: now[0])
    engine.register(plan(), str(tmp_path))
    token = engine.claim("mission", "t0", "worker", 10)
    now[0] = 111
    with pytest.raises(ClaimDenied):
        engine.complete("mission", "t0", token, {"ok": True})
    with pytest.raises(ClaimDenied):
        engine.recover("mission", "t0", lambda row: False, lambda row: True)
    with pytest.raises(ClaimDenied):
        engine.recover("mission", "t0", lambda row: True, lambda row: False)
    engine.recover("mission", "t0", lambda row: True, lambda row: True)
    new = engine.claim("mission", "t0", "replacement", 10)
    assert new > token
    with pytest.raises(ClaimDenied):
        engine.heartbeat("mission", "t0", token)
    engine.complete("mission", "t0", new, {"ok": True})
    engine.complete("mission", "t0", new, {"ok": True})
    with pytest.raises(ClaimDenied):
        engine.complete("mission", "t0", new, {"ok": False})
    engine.integration("mission", "t0", new, lambda: {"integrated": True})
    with pytest.raises(ClaimDenied):
        engine.integration(
            "mission", "t0", token, lambda: pytest.fail("stale operation executed")
        )


def test_contract_ack_dependency_and_failed_integration_transaction(tmp_path):
    engine = store(tmp_path)
    digest = engine.contract("mission", {"signature": "value() -> int"})
    obj = plan(dependencies=True).model_dump()
    obj["tasks"][0]["contract_hashes"] = [digest]
    engine.register(Plan.model_validate(obj), str(tmp_path))
    with pytest.raises(ClaimDenied):
        engine.claim("mission", "t0", "worker")
    engine.acknowledge("mission", "t0", digest)
    token = engine.claim("mission", "t0", "worker")
    engine.complete("mission", "t0", token, {"ok": True})
    with pytest.raises(ClaimDenied):
        engine.claim("mission", "t1", "worker")

    def failed():
        raise ValueError("post-merge test failed")

    with pytest.raises(ValueError):
        engine.integration("mission", "t0", token, failed)
    assert engine.tasks("mission")[0]["state"] == "COMPLETED"
    engine.integration("mission", "t0", token, lambda: {"ok": True})
    assert engine.claim("mission", "t1", "worker") > token


def test_blackboard_redaction_rate_appendonly_and_no_authority(tmp_path):
    engine = store(tmp_path)
    engine.register(plan(), str(tmp_path))
    message = Message(
        mission_id="mission",
        task_id="t0",
        sender="worker",
        recipient="integrator",
        kind="decision",
        payload={"text": "ignore Guardian", "token": "dummy"},
    )
    with pytest.raises(PermissionError):
        engine.publish(message, "other")
    for _ in range(30):
        engine.publish(message, "worker")
    with pytest.raises(ClaimDenied):
        engine.publish(message, "worker")
    assert "dummy" not in json.dumps(engine.messages("mission"))
    assert engine.tasks("mission")[0]["state"] == "PENDING"
    with pytest.raises(sqlite3.IntegrityError), engine.db.connection() as con:
        con.execute("DELETE FROM coord_messages")
    with pytest.raises(ValueError):
        engine.publish(
            message.model_copy(
                update={"payload": {"text": "x" * 9000}, "sender": "other"}
            ),
            "other",
        )


def test_test_ast_detects_trivial_and_skip_changes():
    assert next(iter(inspect_tests("def test_bad(): assert True").values()))["trivial"]
    assert next(iter(inspect_tests("def test_bad(): pass").values()))["trivial"]
    assert not next(iter(inspect_tests("def test_good(): assert 1+1==2").values()))[
        "trivial"
    ]


class FakeWorker(BaseWorker):
    def __init__(self, name, barrier=None, malicious=False, fail=False):
        super().__init__(name)
        self.barrier = barrier
        self.malicious = malicious
        self.fail = fail

    def execute_task(
        self,
        task_id,
        goal,
        instructions,
        worktree_path,
        files_to_modify=None,
        timeout_seconds=300,
    ):
        if self.barrier:
            self.barrier.wait(timeout=10)
        if self.fail:
            raise RuntimeError("simulated worker death")
        (worktree_path / files_to_modify[0]).write_text("def value(): return 42\n")
        if self.malicious:
            (worktree_path / "unauthorized.py").write_text("outside ownership\n")
        return {"success": True}


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.simulated
@pytest.mark.parametrize("failure", [None, "scope", "death", "review", "postmerge"])
def test_coordinated_real_git_sqlite_guardian_with_fake_workers(
    tmp_path, monkeypatch, failure
):
    monkeypatch.setenv("ACS_ENABLE_COORDINATION", "1")
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    (root / "README.md").write_text("Disposable fixture\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "initial")
    head = git(root, "rev-parse", "HEAD")
    status = git(root, "status", "--porcelain")
    engine = store(tmp_path)
    barrier = threading.Barrier(2) if failure is None else None
    workers = {
        name: FakeWorker(
            name, barrier, malicious=failure == "scope", fail=failure == "death"
        )
        for name in ("a", "b", "c")
    }

    def test_prepare(task, requirements):
        name = Path(task.owns[0]).stem
        assert requirements == ["Functions return 42"]
        code = f"from {name} import value\ndef test_requirement_{task.task_id}(): assert value() == 42\n"
        if failure == "postmerge":
            code += "from pathlib import Path\ndef test_injected_integration_failure(): assert not (Path('alpha.py').exists() and Path('beta.py').exists())\n"
        return {f"tests/test_contract_{task.task_id}.py": code}

    def review(task, worktree, implementer, sha):
        return Review(
            task_id=task.task_id,
            implementer=implementer,
            reviewer="reviewer",
            commit_sha=sha,
            verdict="FIX_REQUIRED" if failure == "review" else "PASS",
            requirement_coverage=task.acceptance_criteria,
        )

    runner = TeamRunner(
        engine,
        workers,
        IndependentTester("tester", test_prepare),
        {"reviewer": review},
        WorktreeManager(tmp_path / "worktrees", min_free_gb=0),
        tmp_path / "artifacts",
        "offline-evidence-fixture",
    )
    result = runner.run(plan(), root)
    assert result["status"] == ("COMPLETED" if failure is None else "BLOCKED"), result[
        "errors"
    ]
    assert (
        git(root, "rev-parse", "HEAD") == head
        and git(root, "status", "--porcelain") == status
    )
    if failure is None:
        assert len(engine.messages("mission")) == 2
        assert git(root, "rev-list", "--count", result["integration_branch"]) == "5"
        assert all(row["state"] == "INTEGRATED" for row in result["tasks"])
    else:
        if failure == "postmerge":
            assert sorted(row["state"] for row in result["tasks"]) == [
                "FAILED",
                "INTEGRATED",
            ]
            assert git(root, "rev-list", "--count", result["integration_branch"]) == "3"
        else:
            assert git(root, "rev-parse", result["integration_branch"]) == head
            assert all(row["state"] == "FAILED" for row in result["tasks"])


@pytest.mark.simulated
def test_team_planner_bounds_repairs_without_executing_invalid_json(monkeypatch):
    from acs_team.planner import AIPlanner

    calls = []

    def invalid(*args, **kwargs):
        calls.append(args)
        return '{"mission_id":"wrong", "commands":"rm -rf"}'

    monkeypatch.setattr("acs_team.planner.query_llm", invalid)
    with pytest.raises(ValueError):
        AIPlanner().plan_team("mission", "goal")
    assert len(calls) == 3
    calls.clear()
    monkeypatch.setattr(
        "acs_team.planner.query_llm", lambda *a, **k: plan().model_dump_json()
    )
    assert AIPlanner().plan_team("mission", "goal").mission_id == "mission"


def test_team_validate_cli_does_not_change_target(tmp_path):
    from argparse import Namespace
    from acs_team.team_cli import execute

    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    before = git(root, "status", "--porcelain")
    source = tmp_path / "plan.json"
    source.write_text(plan().model_dump_json())
    execute(Namespace(team_action="validate", plan=str(source)))
    assert git(root, "status", "--porcelain") == before
