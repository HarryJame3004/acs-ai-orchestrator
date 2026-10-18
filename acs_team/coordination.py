"""Persistent, fenced, local SQLite coordination and append-only communication."""

from __future__ import annotations

from .upgrade_schema import COORD_SQL as SCHEMA

import hashlib
import json
import time
from typing import Callable

from .db import DatabaseManager
from .ownership import overlaps
from .schemas import Message, Plan
from .security import redact



class ClaimDenied(RuntimeError):
    pass


class CoordinationStore:
    def __init__(self, db: DatabaseManager, clock: Callable[[], float] = time.time):
        self.db, self.clock = db, clock
        with db.connection() as con:
            for statement in SCHEMA:
                con.execute(statement)

    def register(self, plan: Plan, repository: str) -> None:
        from pathlib import Path

        repository = str(Path(repository).resolve())
        with self.db.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            previous = con.execute(
                "SELECT repository,plan FROM coord_plans WHERE mission=?",
                (plan.mission_id,),
            ).fetchone()
            encoded = Plan.model_validate(redact(plan.model_dump())).model_dump_json()
            if previous:
                if previous["repository"] != repository or previous["plan"] != encoded:
                    raise ValueError(
                        "Existing mission plan is immutable; replan under a new mission"
                    )
                return
            con.execute(
                "INSERT INTO coord_plans VALUES (?,?,?)",
                (plan.mission_id, repository, encoded),
            )
            con.executemany(
                'INSERT INTO coord_tasks(mission,task,state) VALUES (?, ?, "PENDING")',
                [(plan.mission_id, t.task_id) for t in plan.tasks],
            )

    def plan(self, mission: str) -> Plan:
        with self.db.connection() as con:
            row = con.execute(
                "SELECT plan FROM coord_plans WHERE mission=?", (mission,)
            ).fetchone()
        if row is None:
            raise KeyError("Unknown mission")
        return Plan.model_validate_json(row["plan"])

    def tasks(self, mission: str) -> list[dict]:
        with self.db.connection() as con:
            return [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM coord_tasks WHERE mission=? ORDER BY task",
                    (mission,),
                )
            ]

    def claim(
        self, mission: str, task_id: str, worker: str, lease_seconds: float = 300
    ) -> int:
        if not worker or not 1 <= lease_seconds <= 3600:
            raise ValueError("Worker and bounded lease required")
        plan = self.plan(mission)
        task = next(t for t in plan.tasks if t.task_id == task_id)
        now = self.clock()
        with self.db.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT * FROM coord_tasks WHERE mission=? AND task=?",
                (mission, task_id),
            ).fetchone()
            if row["state"] != "PENDING":
                raise ClaimDenied("Task is already claimed or terminal")
            for dependency in task.depends_on:
                dep = con.execute(
                    "SELECT state FROM coord_tasks WHERE mission=? AND task=?",
                    (mission, dependency),
                ).fetchone()
                if dep["state"] != "INTEGRATED":
                    raise ClaimDenied("Dependency has not integrated successfully")
            for digest in task.contract_hashes:
                if not con.execute(
                    "SELECT 1 FROM coord_acks WHERE mission=? AND task=? AND digest=?",
                    (mission, task_id, digest),
                ).fetchone():
                    raise ClaimDenied("Contract must be acknowledged before dispatch")
            repository = con.execute(
                "SELECT repository FROM coord_plans WHERE mission=?", (mission,)
            ).fetchone()[0]
            active = con.execute(
                'SELECT t.mission,t.task,p.plan FROM coord_tasks t JOIN coord_plans p ON p.mission=t.mission WHERE p.repository=? AND t.state IN ("RUNNING","COMPLETED","INTEGRATING")',
                (repository,),
            ).fetchall()
            for other in active:
                other_task = next(
                    t
                    for t in Plan.model_validate_json(other["plan"]).tasks
                    if t.task_id == other["task"]
                )
                if any(overlaps(a, b) for a in task.owns for b in other_task.owns):
                    raise ClaimDenied(
                        "Overlapping ownership, including expired but unrecovered workers"
                    )
            token = con.execute("INSERT INTO coord_tokens DEFAULT VALUES").lastrowid
            con.execute(
                'UPDATE coord_tasks SET state="RUNNING",worker=?,token=?,expires=?,heartbeat=? WHERE mission=? AND task=?',
                (worker, token, now + lease_seconds, now, mission, task_id),
            )
        assert token is not None
        return token

    def _fenced(
        self, con, mission: str, task: str, token: int, states: tuple[str, ...]
    ):
        row = con.execute(
            "SELECT * FROM coord_tasks WHERE mission=? AND task=?", (mission, task)
        ).fetchone()
        if (
            row is None
            or row["token"] != token
            or row["state"] not in states
            or row["expires"] <= self.clock()
        ):
            raise ClaimDenied("Stale, expired or invalid ownership token")
        return row

    def heartbeat(
        self,
        mission: str,
        task: str,
        token: int,
        lease_seconds: float = 300,
        process: dict | None = None,
        worktree: str | None = None,
    ) -> None:
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease")
        with self.db.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            self._fenced(
                con, mission, task, token, ("RUNNING", "COMPLETED", "INTEGRATING")
            )
            con.execute(
                "UPDATE coord_tasks SET expires=?,heartbeat=?,process=COALESCE(?,process),worktree=COALESCE(?,worktree) WHERE mission=? AND task=?",
                (
                    self.clock() + lease_seconds,
                    self.clock(),
                    json.dumps(process) if process else None,
                    worktree,
                    mission,
                    task,
                ),
            )

    def complete(self, mission: str, task: str, token: int, result: dict) -> None:
        encoded = json.dumps(redact(result), sort_keys=True)
        if len(encoded.encode()) > 65536:
            raise ValueError("Completion evidence too large")
        with self.db.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            row = self._fenced(con, mission, task, token, ("RUNNING", "COMPLETED"))
            if row["state"] == "COMPLETED" and row["result"] != encoded:
                raise ClaimDenied("Conflicting duplicate completion")
            con.execute(
                'UPDATE coord_tasks SET state="COMPLETED",result=? WHERE mission=? AND task=?',
                (encoded, mission, task),
            )

    def integration(
        self, mission: str, task: str, token: int, operation: Callable[[], dict]
    ) -> dict:
        # Serialize integrators with a crash-released kernel lock, while leaving
        # SQLite available for other workers' heartbeats during long test runs.
        from .service_lock import ServiceLock
        path = self.db.db_path.parent/'coord-integration.lock'
        lock = ServiceLock(path).acquire()
        try:
            return self._integrate(mission,task,token,operation)
        finally:
            lock.release()

    def _integrate(self, mission: str, task: str, token: int, operation: Callable[[],dict]) -> dict:
        with self.db.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            completion = self._fenced(con, mission, task, token, ("COMPLETED",))
            worker_result = json.loads(completion['result'])
            con.execute(
                'UPDATE coord_tasks SET state="INTEGRATING" WHERE mission=? AND task=?',
                (mission, task),
            )
        try:
            result = operation()
        except BaseException:
            with self.db.connection() as con:
                con.execute('UPDATE coord_tasks SET state="COMPLETED" WHERE mission=? AND task=? AND token=? AND state="INTEGRATING"',
                            (mission,task,token))
            raise
        with self.db.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            self._fenced(con,mission,task,token,('INTEGRATING',))
            con.execute(
                'UPDATE coord_tasks SET state="INTEGRATED",result=? WHERE mission=? AND task=?',
                (json.dumps(redact({**result, 'worker_completion': worker_result})), mission, task),
            )
        return result

    def fail(self, mission: str, task: str, token: int, reason: str) -> None:
        with self.db.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            self._fenced(con, mission, task, token, ("RUNNING", "COMPLETED"))
            con.execute(
                'UPDATE coord_tasks SET state="FAILED",result=? WHERE mission=? AND task=?',
                (json.dumps({"error": redact(reason)[:4096]}), mission, task),
            )

    def recover(
        self,
        mission: str,
        task: str,
        confirmed_dead: Callable[[dict], bool],
        worktree_safe: Callable[[dict], bool],
    ) -> None:
        with self.db.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT * FROM coord_tasks WHERE mission=? AND task=?", (mission, task)
            ).fetchone()
            if (
                not row
                or row["state"] not in {"RUNNING", "COMPLETED"}
                or row["expires"] > self.clock()
            ):
                raise ClaimDenied("Only expired claims may be recovered")
            if not confirmed_dead(dict(row)) or not worktree_safe(dict(row)):
                raise ClaimDenied(
                    "Old worker death and worktree safety must be confirmed"
                )
            con.execute(
                'UPDATE coord_tasks SET state="PENDING",token=NULL,worker=NULL,expires=NULL,process=NULL,worktree=NULL,result=NULL WHERE mission=? AND task=?',
                (mission, task),
            )

    def contract(self, mission: str, payload: dict) -> str:
        encoded = json.dumps(redact(payload), sort_keys=True, separators=(",", ":"))
        if len(encoded.encode()) > 32768:
            raise ValueError("Contract too large")
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.db.connection() as con:
            con.execute(
                "INSERT OR IGNORE INTO coord_contracts VALUES (?,?,?)",
                (mission, digest, encoded),
            )
        return digest

    def acknowledge(self, mission: str, task: str, digest: str) -> None:
        plan = self.plan(mission)
        if not any(
            t.task_id == task and digest in t.contract_hashes for t in plan.tasks
        ):
            raise ValueError("Contract not declared in task")
        with self.db.connection() as con:
            if not con.execute(
                "SELECT 1 FROM coord_contracts WHERE mission=? AND digest=?",
                (mission, digest),
            ).fetchone():
                raise ValueError("Unknown contract")
            con.execute(
                "INSERT OR IGNORE INTO coord_acks VALUES (?,?,?)",
                (mission, task, digest),
            )

    def publish(self, message: Message, authenticated_sender: str) -> int:
        if message.sender != authenticated_sender:
            raise PermissionError("Cannot impersonate another sender")
        # Re-validate models constructed through unsafe model_construct callers.
        message = Message.model_validate(message.model_dump())
        encoded = json.dumps(redact(message.model_dump()), sort_keys=True)
        if len(encoded.encode()) > 8192:
            raise ValueError("Blackboard message exceeds 8 KiB")
        now = self.clock()
        with self.db.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            if not con.execute(
                "SELECT 1 FROM coord_tasks WHERE mission=? AND task=?",
                (message.mission_id, message.task_id),
            ).fetchone():
                raise ValueError("Unknown message task")
            count = con.execute(
                "SELECT count(*) FROM coord_messages WHERE sender=? AND created>?",
                (message.sender, now - 60),
            ).fetchone()[0]
            if count >= 30:
                raise ClaimDenied("Blackboard rate limit exceeded")
            cursor = con.execute(
                "INSERT INTO coord_messages(mission,task,sender,created,message) VALUES (?,?,?,?,?)",
                (message.mission_id, message.task_id, message.sender, now, encoded),
            )
            assert cursor.lastrowid is not None
            return cursor.lastrowid

    def messages(self, mission: str, after: int = 0, limit: int = 100) -> list[dict]:
        with self.db.connection() as con:
            return [
                dict(r)
                for r in con.execute(
                    "SELECT id,message FROM coord_messages WHERE mission=? AND id>? ORDER BY id LIMIT ?",
                    (mission, after, min(max(limit, 1), 100)),
                )
            ]
