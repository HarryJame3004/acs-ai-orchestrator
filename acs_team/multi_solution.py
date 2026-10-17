"""Explicit opt-in isolated proposal comparison; policy remains in TeamRunner."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .schemas import Plan
from .team_runner import TeamRunner


def compare_solutions(outcomes: list[dict]) -> dict:
    if len(outcomes) != 2:
        raise ValueError("Exactly two isolated proposals required")
    eligible = []
    for index, outcome in enumerate(outcomes):
        if outcome.get("status") != "COMPLETED" or not outcome.get("tasks"):
            continue
        if not all(row.get("state") == "INTEGRATED" for row in outcome["tasks"]):
            continue
        eligible.append(index)
    if not eligible:
        return {
            "status": "BLOCKED",
            "selected": None,
            "reason": "No proposal passed required tests, review, scope and Guardian integration",
        }
    # Both passed the same explicit acceptance profile. A deterministic tie does
    # not pretend that model preference proves higher quality.
    return {
        "status": "PASS",
        "selected": eligible[0],
        "reason": "Passed objective acceptance, independent review, scope and Guardian; deterministic tie-break if both pass",
    }


def run_alternatives(
    runner: TeamRunner,
    plans: list[Plan],
    repository: Path,
    *,
    difficult: bool = False,
    quota_available: bool = False,
    compare: Callable[[list[dict]], dict] = compare_solutions,
) -> dict:
    if (
        os.environ.get("ACS_ENABLE_MULTI_SOLUTION") != "1"
        or not difficult
        or not quota_available
    ):
        raise PermissionError(
            "Multi-solution requires explicit configuration, task need and measured available quota"
        )
    if len(plans) != 2 or plans[0].mission_id == plans[1].mission_id:
        raise ValueError("Two separately identified mission branches required")
    left, right = plans
    if (
        left.requirements != right.requirements
        or [t.acceptance_criteria for t in left.tasks]
        != [t.acceptance_criteria for t in right.tasks]
        or [t.verification_commands for t in left.tasks]
        != [t.verification_commands for t in right.tasks]
    ):
        raise ValueError("Proposals must share objective acceptance criteria and tests")
    # Execute sequentially to preserve the conservative shared-repository claim
    # policy. Each result stays on its own dedicated mission branch.
    outcomes = [runner.run(plan, repository) for plan in plans]
    objective = compare_solutions(outcomes)
    recommendation = compare(outcomes)
    selected = recommendation.get("selected")
    if selected not in {0, 1} or outcomes[selected].get("status") != "COMPLETED":
        return {"status": "BLOCKED", "outcomes": outcomes, "comparison": objective}
    return {
        "status": "PASS",
        "outcomes": outcomes,
        "comparison": {**objective, "selected": selected},
    }
