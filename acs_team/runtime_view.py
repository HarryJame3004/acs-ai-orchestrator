"""Read-only dashboard projection of persisted runtime state, with bounded rows."""

from __future__ import annotations

import resource

from .db import DatabaseManager
from .security import redact


def runtime_snapshot(db: DatabaseManager) -> dict:
    measured = resource.getrusage(resource.RUSAGE_SELF)
    missions = db.list_missions(limit=20)
    with db.connection() as con:
        tables = {
            row[0]
            for row in con.execute('SELECT name FROM sqlite_master WHERE type="table"')
        }
        tasks = (
            [
                dict(row)
                for row in con.execute(
                    "SELECT mission,task,state,worker,expires FROM coord_tasks ORDER BY mission,task LIMIT 100"
                )
            ]
            if "coord_tasks" in tables
            else []
        )
        pending = con.execute(
            'SELECT count(*) FROM human_approvals WHERE status="PENDING"'
        ).fetchone()[0]
        lessons = con.execute(
            'SELECT source_type,count(*) AS count FROM memories WHERE memory_type="lesson" GROUP BY source_type'
        ).fetchall()
        reviews = (
            con.execute("SELECT count(*) FROM imported_reviews").fetchone()[0]
            if "imported_reviews" in tables
            else 0
        )
        usage = [
            dict(row)
            for row in con.execute(
                'SELECT actor,action,timestamp FROM audit_events WHERE action LIKE "MCP%" ORDER BY event_id DESC LIMIT 10'
            )
        ]
        failures = [
            dict(row)
            for row in con.execute(
                'SELECT mission_id,actor,action,timestamp FROM audit_events WHERE action IN ("WORKER_FAILURE","GUARDIAN_VETOED") ORDER BY event_id DESC LIMIT 10'
            )
        ]
        stopped = False
        if "runtime_control" in tables:
            row = con.execute(
                'SELECT value FROM runtime_control WHERE key="emergency_stop"'
            ).fetchone()
            stopped = bool(row and row[0] == "1")
    return redact(
        {
            "missions": [
                {
                    "id": m["mission_id"],
                    "stage": m["state"],
                    "workers": m["assigned_workers"],
                    "retry_count": m["retry_count"],
                    "guardian": m.get("review_status"),
                    "error": m.get("error_info"),
                }
                for m in missions
            ],
            "tasks": tasks,
            "pending_approvals": pending,
            "imported_review_rounds": reviews,
            "mcp_usage": usage,
            "recent_failures": failures,
            "lessons": {r[0]: r[1] for r in lessons},
            "emergency_stop": stopped,
            "resources": {
                "database_bytes": db.db_path.stat().st_size,
                "cpu_memory": "CONTROLLER_ONLY",
                "controller_cpu_seconds":measured.ru_utime+measured.ru_stime,
                "controller_peak_rss_bytes":measured.ru_maxrss*1024,
                "worker_aggregate": "LOCAL_VERIFICATION_REQUIRED",
            },
        }
    )
