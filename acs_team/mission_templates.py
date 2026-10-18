"""Local conservative templates; dry-run is deterministic and read-only."""

from __future__ import annotations

from pathlib import Path
import subprocess

from .security import contained_path, redact

TEMPLATES = {
    "fix-tests": (
        "medium",
        ["Existing failures fixed without weakening assertions"],
        ["implementer", "tester", "reviewer"],
        True,
    ),
    "add-feature": (
        "medium",
        ["New behavior meets explicit acceptance tests"],
        ["planner", "implementer", "tester", "reviewer"],
        True,
    ),
    "refactor": (
        "medium",
        ["Public behavior preserved by baseline tests"],
        ["implementer", "tester", "reviewer"],
        True,
    ),
    "write-docs": (
        "low",
        ["Documentation matches verified behavior"],
        ["implementer", "reviewer"],
        True,
    ),
    "security-audit": (
        "high",
        ["Findings include reproducible evidence and severity"],
        ["tester", "reviewer"],
        True,
    ),
    "review-pr": (
        "high",
        ["Review covers requirements, security and test quality"],
        ["reviewer"],
        True,
    ),
    "debug": (
        "medium",
        ["Root cause reproduced and regression verified"],
        ["implementer", "tester", "reviewer"],
        True,
    ),
    "performance-check": (
        "medium",
        ["Before/after measurements use the same workload"],
        ["tester", "reviewer"],
        True,
    ),
}


def dry_run(
    goal: str,
    repository: Path,
    template: str = "add-feature",
    worker: str = "auto",
    risk: str | None = None,
) -> dict:
    if template not in TEMPLATES or not goal.strip() or len(goal.encode()) > 16384:
        raise ValueError("Invalid dry-run request")
    repository = repository.resolve()
    contained_path(repository, ".")
    from .config import PROTECTED_PATHS

    if any(repository == p or p in repository.parents for p in PROTECTED_PATHS):
        raise PermissionError("Protected repository")
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=repository, check=True, capture_output=True
    )
    names = [
        n for n in result.stdout.decode().split("\0") if n and not n.startswith(".")
    ]
    words = set(goal.casefold().split())
    ranked = sorted(names, key=lambda n: (-sum(w in n.casefold() for w in words), n))
    chosen = [n for n in ranked if any(w in n.casefold() for w in words)][:16]
    default_risk, criteria, roles, review = TEMPLATES[template]
    selected_risk = risk or default_risk
    if selected_risk not in {"low", "medium", "high"}:
        raise ValueError("Invalid risk profile")
    # No scope is invented when relevance is unclear; execution must use a
    # separately validated plan. This view grants no permissions or approvals.
    return {
        "schema_version": 1,
        "mode": "DRY_RUN",
        "requirements": redact(goal),
        "repository": str(repository),
        "template": template,
        "proposed_task_graph": [
            {
                "task_id": "proposal",
                "depends_on": [],
                "acceptance_criteria": criteria,
                "expected_scopes": chosen,
                "worker": worker,
                "roles": roles,
            }
        ],
        "risk": selected_risk,
        "mcp_requirements": [],
        "required_permissions": ["workspace_read"],
        "required_approvals": [
            "Independent review",
            "Explicit execution plan with bounded scopes",
        ]
        + (["Human review for high risk"] if selected_risk == "high" else []),
        "resource_estimate": {
            "max_workers": 1,
            "model_cost": "UNKNOWN",
            "runtime": "UNKNOWN",
        },
        "review_required": review,
        "execution_ready": False,
    }
