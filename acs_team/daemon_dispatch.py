"""Bounded opt-in daemon queue dispatch with durable exclusive mission claims."""

from __future__ import annotations

from .upgrade_schema import DISPATCH_SQL

from concurrent.futures import Future, ThreadPoolExecutor
import os
import json
import uuid
from typing import Callable

from .db import DatabaseManager
from .runtime_control import RuntimeControl
from .security import redact



def validate_dispatch(db: DatabaseManager, mission: str, owner: str) -> None:
    with db.connection() as con:
        row = con.execute(
            "SELECT owner,state FROM daemon_dispatch WHERE mission=?", (mission,)
        ).fetchone()
        state = con.execute(
            "SELECT state FROM missions WHERE mission_id=?", (mission,)
        ).fetchone()
    if (
        not row
        or row["owner"] != owner
        or row["state"] != "ACTIVE"
        or not state
        or state[0] != "PLANNING"
    ):
        raise PermissionError("Mission dispatch ownership is invalid")


class DaemonDispatcher:
    def __init__(self, db: DatabaseManager, factory: Callable | None = None):
        self.db, self.factory = db, factory
        self.control = RuntimeControl(db, initialize=False)
        self.pool: ThreadPoolExecutor | None = None
        self.active: dict[Future, tuple[str, str]] = {}
        self.closed = False

    def _run(self, mission: dict, owner: str) -> dict:
        try:
            validate_dispatch(self.db, mission["mission_id"], owner)
            self.control.require_dispatch()
            if self.factory is None:
                from .autonomous_planner import AutonomousMissionPlanner

                planner = AutonomousMissionPlanner(self.db)
                # Provider dispatch is impossible without local verification and
                # the supervisor. Do not call a model gateway just to learn this.
                if (
                    os.environ.get("ACS_ENABLE_SUPERVISION") != "1"
                    or not planner.registry.list_available_workers()
                ):
                    raise PermissionError(
                        "Verified workers and supervised execution are required"
                    )
            else:
                planner = self.factory(self.db)
            preference = (
                mission["assigned_workers"][0]
                if mission["assigned_workers"]
                else "auto"
            )
            from .repo_manager import RepoManager

            repository, _ = RepoManager(self.db).resolve_target_workspace(
                mission["repository_path"] or None, mission_id=mission["mission_id"]
            )
            options = json.loads(mission.get("plan_json") or "{}").get(
                "dispatch_options", {}
            )
            result = planner.run_mission(
                mission["mission_id"],
                mission.get("prompt") or mission["goal"],
                repository,
                worker_preference=preference,
                dispatch_claim=owner,
                test_command=options.get("test_command"),
                risk_profile=options.get("risk"),
                template=options.get('template','add-feature'),
            )
            return result
        except Exception as exc:
            with self.db.connection() as con:
                con.execute(
                    'UPDATE missions SET state="BLOCKED",error_info=? WHERE mission_id=? AND state NOT IN ("COMPLETED","CANCELLED","FAILED")',
                    (redact(str(exc))[:4096], mission["mission_id"]),
                )
            return {"status": "BLOCKED"}
        finally:
            with self.db.connection() as con:
                con.execute(
                    'UPDATE daemon_dispatch SET state="FINISHED" WHERE mission=? AND owner=?',
                    (mission["mission_id"], owner),
                )

    def tick(self) -> int:
        if self.closed or os.environ.get("ACS_ENABLE_DAEMON_EXECUTION") != "1":
            return 0
        self.control.require_dispatch()
        for future in list(self.active):
            if future.done():
                future.result()
                self.active.pop(future)
        if self.active:
            return 0
        if self._recover_one():
            return 1
        with self.db.connection() as con:
            for sql in DISPATCH_SQL:
                con.execute(sql)
            con.execute("BEGIN IMMEDIATE")
            # ACTIVE claims survive restarts and require operator reconciliation;
            # never steal a potentially running worker based on missing memory.
            row = con.execute(
                'SELECT m.mission_id FROM missions m LEFT JOIN daemon_dispatch d ON d.mission=m.mission_id WHERE m.state="QUEUED" AND (d.mission IS NULL OR d.state="FINISHED") ORDER BY m.created_at LIMIT 1'
            ).fetchone()
            if not row:
                return 0
            mission_id = row[0]
            owner = uuid.uuid4().hex
            con.execute(
                'INSERT INTO daemon_dispatch VALUES (?, ?, "ACTIVE") ON CONFLICT(mission) DO UPDATE SET owner=excluded.owner,state="ACTIVE"',
                (mission_id, owner),
            )
            con.execute(
                'UPDATE missions SET state="PLANNING" WHERE mission_id=? AND state="QUEUED"',
                (mission_id,),
            )
        mission = self.db.get_mission(mission_id)
        assert mission is not None
        if self.pool is None:
            self.pool = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="acs-daemon-mission"
            )
        future = self.pool.submit(self._run, mission, owner)
        self.active[future] = (mission_id, owner)
        return 1

    def _recover_one(self) -> bool:
        """Resume only a dead controller's previously authorized validated run."""
        if os.environ.get('ACS_ENABLE_TEAM_RECOVERY') != '1' or os.environ.get('ACS_ENABLE_COORDINATION') != '1':
            return False
        from .team_recovery import owner_alive
        import time
        with self.db.connection() as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='team_runs' AND type='table'").fetchone():
                return False
            rows = con.execute('SELECT r.mission,r.owner FROM team_runs r JOIN missions m ON m.mission_id=r.mission WHERE r.phase="ACTIVE" AND r.plan IS NOT NULL AND m.state="RECOVERING" ORDER BY m.created_at LIMIT 100').fetchall()
            eligible = [r for r in rows if not owner_alive(json.loads(r['owner'])) and not con.execute(
                'SELECT 1 FROM coord_tasks WHERE mission=? AND state IN ("RUNNING","COMPLETED","INTEGRATING") AND expires>?',
                (r['mission'],time.time())).fetchone()]
        if not eligible:
            return False
        mission = eligible[0]['mission']
        def resume():
            try:
                if self.factory:
                    controller = self.factory(self.db)
                else:
                    from .team_missions import TeamMissionController
                    controller = TeamMissionController(self.db)
                self.control.require_dispatch()
                result = controller.resume_mission(mission)
                with self.db.connection() as con:
                    if con.execute("SELECT 1 FROM sqlite_master WHERE name='daemon_dispatch' AND type='table'").fetchone():
                        con.execute('UPDATE daemon_dispatch SET state="FINISHED" WHERE mission=?',(mission,))
                return result
            except Exception as exc:
                # The mission lock/reconciler owns state changes. Do not turn a
                # concurrent lock refusal into cancellation of another owner.
                self.db.record_audit_event(mission,'daemon-recovery','RECOVERY_BLOCKED',
                                           {'reason':redact(str(exc))[:1024]})
                return {'status':'BLOCKED'}
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='acs-daemon-mission')
        future = self.pool.submit(resume)
        self.active[future] = (mission,'recovery')
        return True

    def close(self) -> None:
        self.closed = True
        with self.db.connection() as con:
            for mission, _ in self.active.values():
                con.execute(
                    'UPDATE missions SET state="CANCELLED",error_info="Daemon shutdown" WHERE mission_id=? AND state NOT IN ("COMPLETED","FAILED","BLOCKED","CANCELLED")',
                    (mission,),
                )
        if self.pool:
            self.pool.shutdown(wait=True, cancel_futures=True)
