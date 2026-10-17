"""Durable emergency dispatch gate; no signalling of arbitrary external PIDs."""

from .db import DatabaseManager


class RuntimeControl:
    def __init__(self, db: DatabaseManager, initialize: bool = True):
        self.db = db
        if initialize:
            with db.connection() as con:
                con.execute("CREATE TABLE IF NOT EXISTS runtime_control (key TEXT PRIMARY KEY,value TEXT NOT NULL)")

    def stopped(self) -> bool:
        with self.db.connection() as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='runtime_control'").fetchone():
                return False
            row = con.execute("SELECT value FROM runtime_control WHERE key='emergency_stop'").fetchone()
            return row is not None and row[0] == "1"

    def stop(self) -> None:
        with self.db.connection() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("INSERT INTO runtime_control VALUES ('emergency_stop','1') ON CONFLICT(key) DO UPDATE SET value='1'")
            con.execute("UPDATE missions SET state='CANCELLED',error_info='Emergency stop' WHERE state NOT IN ('COMPLETED','FAILED','BLOCKED','CANCELLED')")

    def resume(self, *, operator_confirmed: bool = False) -> None:
        if not operator_confirmed:
            raise PermissionError("Resuming requires explicit operator confirmation")
        with self.db.connection() as con:
            con.execute("INSERT INTO runtime_control VALUES ('emergency_stop','0') ON CONFLICT(key) DO UPDATE SET value='0'")

    def require_dispatch(self) -> None:
        if self.stopped():
            raise PermissionError("Emergency stop is active; dispatch denied")
