"""Local artifact export and bounded review import; no automatic remote sending."""

import json
import os
from pathlib import Path
import sys

from .config import STATE_DIR
from .db import DatabaseManager
from .mission_templates import TEMPLATES
from .review_workflow import ReviewWorkflow


def execute(args):
    if args.command == "templates":
        print(
            json.dumps(
                {
                    name: {
                        "risk": item[0],
                        "criteria": item[1],
                        "roles": item[2],
                        "review_required": item[3],
                        "verification_profile": "pytest",
                        "permissions": ["workspace_read"],
                    }
                    for name, item in TEMPLATES.items()
                }
            )
        )
        return
    from .auth import get_or_create_auth_token

    key_path = STATE_DIR / "evidence.key"
    key = get_or_create_auth_token(key_path) if key_path.exists() else None
    workflow = ReviewWorkflow(DatabaseManager(), STATE_DIR / "artifacts", key)
    if args.command == "apply":
        if os.environ.get("ACS_ENABLE_REVIEW_WORKFLOW") != "1":
            raise SystemExit("Review intake requires ACS_ENABLE_REVIEW_WORKFLOW=1")
        if args.file == "-":
            raw = sys.stdin.buffer.read(32769)
        else:
            with Path(args.file).open("rb") as stream:
                raw = stream.read(32769)
        print(json.dumps(workflow.apply(args.mission_id, raw)))
    else:
        print(
            json.dumps(
                workflow.package(
                    args.mission_id,
                    Path(args.output),
                    escalation=args.command == "escalate",
                )
            )
        )


def register(subparsers):
    templates = subparsers.add_parser(
        "templates", help="List conservative mission templates"
    )
    templates.set_defaults(func=execute)
    for name in ("review", "escalate", "apply"):
        child = subparsers.add_parser(name, help="Local bounded review workflow")
        child.add_argument("mission_id")
        if name == "apply":
            child.add_argument(
                "--file", default="-", help="Structured review file or stdin"
            )
        else:
            child.add_argument(
                "--output", required=True, help="New private artifact directory"
            )
        child.set_defaults(func=execute)
