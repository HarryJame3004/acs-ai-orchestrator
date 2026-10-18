BEGIN TRANSACTION;
CREATE TABLE audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id TEXT,
    task_id TEXT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details_json TEXT,
    timestamp TEXT NOT NULL
);
INSERT INTO "audit_events" VALUES(1,'mission',NULL,'verifier','VERIFICATION_RESULT','{"command": ["pytest", "-q"], "workspace": "/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/worktrees/mission_t0-e2e6930a", "runtime_seconds": 1.2274237849997007, "executed": true, "passed": true, "exit_code": 0, "reason": "completed", "counts": {"passed": 2, "failed": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "errors": 0}, "label": "CLOUD_SIMULATED"}','2026-10-18T06:52:01.589505+00:00');
INSERT INTO "audit_events" VALUES(2,'mission',NULL,'verifier','VERIFICATION_RESULT','{"command": ["pytest", "-q"], "workspace": "/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/worktrees/mission_t1-9f8963ca", "runtime_seconds": 2.73043605699786, "executed": true, "passed": true, "exit_code": 0, "reason": "completed", "counts": {"passed": 2, "failed": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "errors": 0}, "label": "CLOUD_SIMULATED"}','2026-10-18T06:52:03.125125+00:00');
INSERT INTO "audit_events" VALUES(3,'mission',NULL,'verifier','VERIFICATION_RESULT','{"command": ["pytest", "-q", "tests/test_contract_t0.py"], "workspace": "/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/worktrees/mission_t0-e2e6930a", "runtime_seconds": 2.30268726900249, "executed": true, "passed": true, "exit_code": 0, "reason": "completed", "counts": {"passed": 2, "failed": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "errors": 0}, "label": "CLOUD_SIMULATED"}','2026-10-18T06:52:03.913144+00:00');
INSERT INTO "audit_events" VALUES(4,'mission',NULL,'verifier','VERIFICATION_RESULT','{"command": ["pytest", "-q", "tests/test_contract_t1.py"], "workspace": "/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/worktrees/mission_t1-9f8963ca", "runtime_seconds": 3.6990351709973766, "executed": true, "passed": false, "exit_code": 125, "reason": "completed", "counts": {"passed": 2, "failed": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "errors": 0}, "label": "CLOUD_SIMULATED", "evidence_ref": "/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/artifacts/79baf65cb5654bf298c0007a17e7439b.evidence.json"}','2026-10-18T06:52:07.009177+00:00');
INSERT INTO "audit_events" VALUES(5,'mission',NULL,'b','TASK_EXECUTION','{"task_id": "t1", "runtime_seconds": 6.850039500997809, "completed": false, "label": "CLOUD_SIMULATED"}','2026-10-18T06:52:07.053619+00:00');
INSERT INTO "audit_events" VALUES(6,'mission',NULL,'b','WORKER_FAILURE','{"task_id": "t1", "fingerprint": "166aa2a456552b78c062cf2287cd6387c9cf3548b7265b97e9d052511c96f76c", "exception_type": "ValueError", "reason": "Task verification or independent contract tests failed", "stage": "task-verification-or-integration", "label": "CLOUD_SIMULATED"}','2026-10-18T06:52:07.096524+00:00');
INSERT INTO "audit_events" VALUES(7,'mission',NULL,'verifier','VERIFICATION_RESULT','{"command": "pytest -q", "workspace": "/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/worktrees/mission_t0-e2e6930a", "runtime_seconds": 6.331484128000739, "executed": true, "passed": false, "exit_code": 125, "reason": "completed", "counts": {"passed": 2, "failed": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "errors": 0}, "label": "CLOUD_SIMULATED", "evidence_ref": "/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/artifacts/d2a6d5236a1c42f688dc019ba6ed6010.evidence.json"}','2026-10-18T06:52:10.567104+00:00');
INSERT INTO "audit_events" VALUES(8,'mission','t0','guardian','GUARDIAN_VETOED','{"target_branch": "acsai/mission/mission", "commit_sha": "ddd347b8d7a42e40a470a1b5e6a6e9deae895df6", "quality_score": 0.6, "veto_reasons": ["Quality Score 0.6 fell below required threshold 0.85", "Automated test suite failed."], "approved": false}','2026-10-18T06:52:10.671940+00:00');
INSERT INTO "audit_events" VALUES(9,'mission',NULL,'a','TASK_EXECUTION','{"task_id": "t0", "runtime_seconds": 10.58390751400293, "completed": false, "label": "CLOUD_SIMULATED"}','2026-10-18T06:52:10.756836+00:00');
INSERT INTO "audit_events" VALUES(10,'mission',NULL,'a','WORKER_FAILURE','{"task_id": "t0", "fingerprint": "de8b89c154d8ff6218a7f13afb42298b684efe08378647e6c120c688b3ea187c", "exception_type": "PermissionError", "reason": "Guardian vetoed task: Quality Score 0.6 fell below required threshold 0.85; Automated test suite failed.", "stage": "task-verification-or-integration", "label": "CLOUD_SIMULATED"}','2026-10-18T06:52:10.788513+00:00');
CREATE TABLE checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    state_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE coord_acks (mission TEXT NOT NULL, task TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(mission,task,digest));
CREATE TABLE coord_contracts (mission TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(mission, digest));
CREATE TABLE coord_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, mission TEXT NOT NULL, task TEXT NOT NULL, sender TEXT NOT NULL, created REAL NOT NULL, message TEXT NOT NULL);
CREATE TABLE coord_plans (mission TEXT PRIMARY KEY, repository TEXT NOT NULL, plan TEXT NOT NULL);
INSERT INTO "coord_plans" VALUES('mission','/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/repo','{"schema_version":1,"mission_id":"mission","requirements":["Functions return 42"],"tasks":[{"schema_version":1,"task_id":"t0","title":"Implement alpha.py","description":"Implement alpha.py with value() returning 42","worker":"auto","role":"implementer","owns":["alpha.py"],"reads":[],"depends_on":[],"acceptance_criteria":["value() returns 42"],"verification_commands":[["pytest","-q"]],"risk_level":"low","contract_hashes":[]},{"schema_version":1,"task_id":"t1","title":"Implement beta.py","description":"Implement beta.py with value() returning 42","worker":"auto","role":"implementer","owns":["beta.py"],"reads":[],"depends_on":[],"acceptance_criteria":["value() returns 42"],"verification_commands":[["pytest","-q"]],"risk_level":"low","contract_hashes":[]}]}');
CREATE TABLE coord_recoveries (id INTEGER PRIMARY KEY AUTOINCREMENT, mission TEXT NOT NULL, task TEXT NOT NULL, snapshot TEXT NOT NULL);
CREATE TABLE coord_tasks (mission TEXT NOT NULL REFERENCES coord_plans(mission), task TEXT NOT NULL, state TEXT NOT NULL, worker TEXT, token INTEGER, expires REAL, heartbeat REAL, process TEXT, worktree TEXT, result TEXT, PRIMARY KEY(mission, task));
INSERT INTO "coord_tasks" VALUES('mission','t0','FAILED','a',1,1792306630.193234,1792306330.1932347,NULL,'/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/worktrees/mission_t0-e2e6930a','{"error": "Guardian vetoed task: Quality Score 0.6 fell below required threshold 0.85; Automated test suite failed."}');
INSERT INTO "coord_tasks" VALUES('mission','t1','FAILED','b',2,1792306625.1485624,1792306325.1485632,NULL,'/workspace/acs-evidence/new-runner-20261018/basetemp/test_coordinated_real_git_sqli3/worktrees/mission_t1-9f8963ca','{"error": "Task verification or independent contract tests failed"}');
CREATE TABLE coord_tokens (token INTEGER PRIMARY KEY AUTOINCREMENT);
INSERT INTO "coord_tokens" VALUES(1);
INSERT INTO "coord_tokens" VALUES(2);
CREATE TABLE human_approvals (
    approval_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    target_repo TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL, -- PENDING, APPROVED, REJECTED
    approved_by TEXT,
    reason TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE TABLE integration_intents (mission TEXT NOT NULL, task TEXT NOT NULL, token INTEGER NOT NULL, intent TEXT NOT NULL, phase TEXT NOT NULL, PRIMARY KEY(mission,task));
CREATE TABLE memories (
    memory_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    memory_type TEXT NOT NULL, -- project, task, decision, failure, knowledge
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_reference TEXT,
    source_commit TEXT,
    confidence REAL DEFAULT 1.0,
    stale INTEGER DEFAULT 0,
    sensitivity TEXT DEFAULT 'normal',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_verified TEXT
);
PRAGMA writable_schema=ON;
INSERT INTO sqlite_master(type,name,tbl_name,rootpage,sql)VALUES('table','memories_fts','memories_fts',0,'CREATE VIRTUAL TABLE memories_fts USING fts5(
    title,
    content,
    memory_id UNINDEXED,
    project_id UNINDEXED
)');
CREATE TABLE 'memories_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;
INSERT INTO "memories_fts_config" VALUES('version',4);
CREATE TABLE 'memories_fts_content'(id INTEGER PRIMARY KEY, c0, c1, c2, c3);
CREATE TABLE 'memories_fts_data'(id INTEGER PRIMARY KEY, block BLOB);
INSERT INTO "memories_fts_data" VALUES(1,X'');
INSERT INTO "memories_fts_data" VALUES(10,X'00000000000000');
CREATE TABLE 'memories_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE 'memories_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE missions (
    mission_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    repository_path TEXT NOT NULL,
    goal TEXT NOT NULL,
    state TEXT NOT NULL,
    assigned_workers TEXT, -- JSON list of worker IDs
    current_checkpoint TEXT,
    git_branch TEXT,
    commit_sha TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    review_status TEXT,
    quality_score REAL DEFAULT 0.0,
    evidence_ref TEXT,
    error_info TEXT,
    prompt TEXT,
    plan_json TEXT,
    logs TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE repositories (
    repo_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    is_protected INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
INSERT INTO "repositories" VALUES('repo-acs-core','ACS Core (Protected)','/workspace/acs-evidence/new-runner-20261018/home/autonomous-coding-system',1,'2026-10-18T06:51:59.922866+00:00','2026-10-18T06:51:59.922866+00:00');
CREATE TABLE review_runs (parent TEXT NOT NULL, round INTEGER NOT NULL, root TEXT NOT NULL, child TEXT NOT NULL UNIQUE, base_commit TEXT NOT NULL, PRIMARY KEY(parent,round));
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
INSERT INTO "schema_version" VALUES(1,'2026-10-18T06:51:59.922244+00:00');
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    assigned_worker TEXT,
    state TEXT NOT NULL,
    worktree_path TEXT,
    branch_name TEXT,
    attempt_no INTEGER DEFAULT 1,
    exit_code INTEGER,
    changed_files TEXT, -- JSON list
    diff_summary TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE team_runs (mission TEXT PRIMARY KEY, repository TEXT NOT NULL, owner TEXT NOT NULL, phase TEXT NOT NULL, baseline TEXT, plan TEXT);
CREATE TRIGGER coord_messages_no_update BEFORE UPDATE ON coord_messages BEGIN SELECT RAISE(ABORT, "append-only blackboard"); END;
CREATE TRIGGER coord_messages_no_delete BEFORE DELETE ON coord_messages BEGIN SELECT RAISE(ABORT, "append-only blackboard"); END;
CREATE INDEX coord_message_rate ON coord_messages(sender, created);
PRAGMA writable_schema=OFF;
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('coord_tokens',2);
INSERT INTO "sqlite_sequence" VALUES('audit_events',10);
COMMIT;
