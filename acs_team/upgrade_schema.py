"""Additive upgrade table definitions shared by opt-in stores and migrations."""

RUNTIME_SQL = (
    "CREATE TABLE IF NOT EXISTS runtime_control (key TEXT PRIMARY KEY,value TEXT NOT NULL)",
)

COORD_SQL = (
    "CREATE TABLE IF NOT EXISTS coord_plans (mission TEXT PRIMARY KEY, repository TEXT NOT NULL, plan TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS coord_tasks (mission TEXT NOT NULL REFERENCES coord_plans(mission), task TEXT NOT NULL, state TEXT NOT NULL, worker TEXT, token INTEGER, expires REAL, heartbeat REAL, process TEXT, worktree TEXT, result TEXT, PRIMARY KEY(mission, task))",
    "CREATE TABLE IF NOT EXISTS coord_tokens (token INTEGER PRIMARY KEY AUTOINCREMENT)",
    "CREATE TABLE IF NOT EXISTS coord_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, mission TEXT NOT NULL, task TEXT NOT NULL, sender TEXT NOT NULL, created REAL NOT NULL, message TEXT NOT NULL)",
    'CREATE TRIGGER IF NOT EXISTS coord_messages_no_update BEFORE UPDATE ON coord_messages BEGIN SELECT RAISE(ABORT, "append-only blackboard"); END',
    'CREATE TRIGGER IF NOT EXISTS coord_messages_no_delete BEFORE DELETE ON coord_messages BEGIN SELECT RAISE(ABORT, "append-only blackboard"); END',
    "CREATE INDEX IF NOT EXISTS coord_message_rate ON coord_messages(sender, created)",
    "CREATE TABLE IF NOT EXISTS coord_contracts (mission TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(mission, digest))",
    "CREATE TABLE IF NOT EXISTS coord_acks (mission TEXT NOT NULL, task TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(mission,task,digest))",
)

METRICS_SQL = (
    "CREATE TABLE IF NOT EXISTS worker_samples (id INTEGER PRIMARY KEY AUTOINCREMENT, worker TEXT NOT NULL, mission TEXT NOT NULL, sample TEXT NOT NULL, UNIQUE(worker,mission))",
    "CREATE TABLE IF NOT EXISTS worker_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, mission TEXT NOT NULL, worker TEXT NOT NULL, reason TEXT NOT NULL)",
)

REVIEW_SQL = (
    "CREATE TABLE IF NOT EXISTS imported_reviews (mission TEXT NOT NULL REFERENCES missions(mission_id), round INTEGER NOT NULL, fingerprint TEXT NOT NULL, review TEXT NOT NULL, tasks TEXT NOT NULL, PRIMARY KEY(mission,round), UNIQUE(mission,fingerprint))",
)

DISPATCH_SQL = (
    "CREATE TABLE IF NOT EXISTS daemon_dispatch (mission TEXT PRIMARY KEY REFERENCES missions(mission_id), owner TEXT NOT NULL, state TEXT NOT NULL)",
)
