"""Read-only team plan validation and persisted coordination inspection."""

import json
from pathlib import Path
import sqlite3
from urllib.parse import quote

from .config import DB_PATH
from .schemas import Plan, parse_data, plan_lint
from .security import redact


def execute(args):
    if args.team_action == "validate":
        path = Path(args.plan)
        if path.stat().st_size > 65536:
            raise ValueError("Plan exceeds 64 KiB")
        plan = parse_data(Plan, path.read_bytes())
        print(
            json.dumps(
                {
                    "valid": True,
                    "plan": redact(plan.model_dump()),
                    "warnings": plan_lint(plan),
                }
            )
        )
        return
    if not DB_PATH.is_file():
        raise SystemExit("No coordination database exists")
    con = sqlite3.connect(
        f"file:{quote(str(DB_PATH.resolve()), safe='/')}?mode=ro", uri=True
    )
    try:
        con.row_factory = sqlite3.Row
        table = "coord_tasks" if args.team_action == "status" else "coord_messages"
        if not con.execute(
            "SELECT 1 FROM sqlite_master WHERE name=?", (table,)
        ).fetchone():
            print("[]")
            return
        rows = con.execute(
            f"SELECT * FROM {table} WHERE mission=? LIMIT 100", (args.mission_id,)
        ).fetchall()
        print(json.dumps(redact([dict(r) for r in rows])))
    finally:
        con.close()


def register(subparsers):
    parser = subparsers.add_parser(
        "team", help="Validate structured team plans and inspect coordination"
    )
    children = parser.add_subparsers(dest="team_action", required=True)
    validate = children.add_parser(
        "validate",
        help="Validate a bounded plan without executing or writing to a repository",
    )
    validate.add_argument("--plan", required=True)
    validate.set_defaults(func=execute)
    for name in ("status", "messages"):
        child = children.add_parser(name)
        child.add_argument("mission_id")
        child.set_defaults(func=execute)
