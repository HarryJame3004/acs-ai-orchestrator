# ACS AI V2.2 — System Architecture & Design Specification

## 1. Architectural Philosophy

ACS AI V2.2 is designed according to five foundational engineering principles:
1. **Local-First Autonomy**: All coordination, orchestration, and evaluation occur locally on the host machine without external SaaS dependencies.
2. **Strict Worktree Isolation**: Workers never write directly to the primary working tree or main branch. Every task executes in an ephemeral git worktree.
3. **Evidence-Driven Verification**: Quality is verified through reproducible test runs, exit codes, and cryptographically signed evidence packages rather than model self-assessment.
4. **Fail-Closed Guardian Security**: The Guardian acts as an independent gatekeeper. Any ambiguity, missing test, out-of-scope diff, or signature mismatch results in immediate rejection.
5. **CoreLock Immutability**: Protected repository roots are strictly read-only. Attempts to write, delete, or merge to protected paths abort with immediate permission faults.

---

## 2. System Subsystems & Topology

```
+-----------------------------------------------------------------------------------------+
|                                    USER INTERFACES                                      |
|                                                                                         |
|       Natural Language CLI (acsai -m)            Textual TUI Dashboard (acsai ui)       |
|               (Typer / Rich)                            (Textual Framework)             |
+--------------------------------------------+--------------------------------------------+
                                             |
                                 UNIX Socket / HTTP REST API
                                     (127.0.0.1:20129)
                                             |
+--------------------------------------------v--------------------------------------------+
|                                  ACS AI DAEMON ENGINE                                   |
|                                                                                         |
|  +------------------------+  +------------------------+  +---------------------------+  |
|  |     State Machine      |  |   Autonomous Planner   |  |        Repo Manager       |  |
|  |   (13-State Flow)      |  | (Decomposition & Eval) |  |   (Git Telemetry & Lock)  |  |
|  +------------------------+  +------------------------+  +---------------------------+  |
|  |   Worker Registry      |  |      MCP Manager       |  |     Human Approval DB     |  |
|  | (Health & Allocation)  |  |  (51 Servers Audited)  |  |      (Pending Actions)    |  |
|  +------------------------+  +------------------------+  +---------------------------+  |
|                                                                                         |
|                      SQLite WAL Database (~/.local/share/acs-orchestrator/state/acs_ai.db) |
+--------------------------------------------+--------------------------------------------+
                                             |
                                    Subprocess Spawner
                                             |
+--------------------------------------------v--------------------------------------------+
|                                MULTI-AGENT WORKER POOL                                  |
|                                                                                         |
|   +-----------------------+     +-----------------------+     +-----------------------+ |
|   |     codex-primary     |     |     agy-google-a      |     |     agy-google-b      | |
|   |   (Codex CLI Bwrap)   |     |   (Google Account A)  |     | (Account B Isolated)  | |
|   +-----------+-----------+     +-----------+-----------+     +-----------+-----------+ |
+---------------|-----------------------------|-----------------------------|-------------+
                +-----------------------------+-----------------------------+
                                              |
                                              v
                              +-------------------------------+
                              |    Ephemeral Git Worktree     |
                              |  (~/.local/share/.../worktree)|
                              +---------------+---------------+
                                              |
                                              v
                              +-------------------------------+
                              |   Automated Pytest Runner     |
                              |   (Exit Code & Output Track)  |
                              +---------------+---------------+
                                              |
                                              v
                              +-------------------------------+
                              |    HMAC-SHA256 Evidence Bnd   |
                              +---------------+---------------+
                                              |
                                              v
                              +-------------------------------+
                              |   Guardian Security Review    |
                              +---------------+---------------+
                                              |
                             [APPROVED]       |       [REJECTED]
                                 +------------+------------+
                                 |                         |
                                 v                         v
                       +-------------------+     +-------------------+
                       | Merge Integration |     | Bounded Retry (3) |
                       |      Branch       |     |   or Failover     |
                       +-------------------+     +-------------------+
```

---

## 3. Component Details

### 3.1 Daemon Engine & HTTP API Server
- **Process Management**: Runs as a managed user systemd service (`acs-ai.service`) or standalone daemon (`acs_team/daemon.py`).
- **Endpoint**: Binds to `127.0.0.1:20129` with local token authentication (`auth.token`).
- **REST Endpoints**:
  - `GET /health`: Heartbeat, PID, and uptime verification.
  - `GET /status`: Consolidated system telemetry.
  - `GET /workers`: Worker pool health and capacity query.
  - `GET /mcp`: Audited MCP server list, connection statuses, and tool inventory.
  - `GET /repos`: Registered repository list with branch, clean/dirty state, and CoreLock flags.
  - `POST /missions`: Submits natural language or structured JSON missions.
  - `GET /missions/<id>/logs`: Real-time streaming log retrieval.
  - `POST /missions/<id>/cancel`: Graceful mission cancellation.
  - `POST /missions/<id>/resume`: Resumes interrupted execution from the last persisted checkpoint.

### 3.2 Multi-Agent Worker Pool
The platform supports three distinct autonomous coding workers:
1. **`codex-primary`** (`acs_team/worker_adapters.py`):
   - Invokes OpenAI Codex CLI wrapped through the `agpair` protocol.
   - Enforces non-interactive execution with workspace-only write permissions via Linux bubblewrap sandboxing.
2. **`agy-google-a`**:
   - Dispatches tasks to the Google Antigravity CLI authenticated with primary Google Account A.
   - Operates in headless non-interactive mode.
3. **`agy-google-b`**:
   - Dispatches tasks to the Google Antigravity CLI authenticated with secondary Google Account B.
   - Uses an isolated home environment (`~/.local/share/acs-orchestrator/agy_b_home/`) to prevent session and cookie collisions.

### 3.3 Autonomous Mission Planner
- **Prompt Decomposition**: Analyzes natural language instructions and repo structure using LLM Client (`acs_team/llm_client.py`) with 9Router free-tier models (`free-coding`, `free-review`).
- **Task Graph Generation**: Emits structured task definitions containing:
  - Task ID and title.
  - Target files to modify or create.
  - Detailed coding prompt for the assigned worker.
  - Explicit acceptance criteria.
  - Exact test command (e.g. `pytest test_calculator.py -v`).
- **Worktree Lifecycle**:
  - Creates an isolated branch `mission-<id>-task-<id>`.
  - Mounts a clean git worktree under `~/.local/share/acs-orchestrator/worktrees/`.
  - Dispatches the task to the selected or auto-routed worker.
  - Executes the verification test suite inside the worktree.
- **Self-Correction & Provider Failover**:
  - If tests fail, the test stdout/stderr and diff are analyzed by the planner.
  - Generates a surgical correction prompt and dispatches up to 3 retry attempts.
  - Automatically fails over to an alternate worker if provider timeouts occur.

### 3.4 Cryptographic Evidence & Guardian Review
- **HMAC-SHA256 Evidence Packaging** (`acs_team/evidence.py`):
  - Gathers: task plan, worker output, git diff, pytest exit code, test execution log, and commit SHA.
  - Signs the canonical JSON payload with HMAC-SHA256 using the local orchestrator secret.
- **Independent Guardian** (`acs_team/guardian.py`):
  - Verifies signature integrity.
  - Verifies test exit code == 0.
  - Inspects file modifications against allowed scope.
  - Evaluates quality metrics (Quality Score >= 0.85).
  - Approves or vetos the merge.

### 3.5 CoreLock Guard & Repository Management
- **CoreLock Protected Path**: `/home/khoi/autonomous-coding-system` is hardcoded as an immutable, read-only boundary.
- **Enforcement**: Any CLI or API call attempting to pass a protected path as a writable workspace raises `PermissionError` immediately.
- **Workspace Fallback**: If a mission prompt is run outside any Git repository, an isolated repository is automatically initialized under `~/.local/share/acs-orchestrator/workspaces/workspace_<mid>`.

### 3.6 MCP Inventory & Governance
- **Auditing** (`acs_team/mcp_manager.py`):
  - Scans native ACS tools, Antigravity configs, AGY B configs, and Codex plugins.
  - Reports: 51 Configured, 49 Connected, 19 Usable, 68 Discovered Tools.
- **Credential Masking**:
  - Automatically intercepts all GitHub PATs, OpenAI keys, Anthropic tokens, and Google API keys.
  - Replaces secrets with secure masked representations (`github_pat_***`) before logging or displaying in UI.

---

## 4. State Machine Progression

Missions progress through 13 well-defined lifecycle states:
```
[QUEUED] -> [PLANNING] -> [READY] -> [RUNNING] -> [TESTING] -> [REVIEWING] -> [COMPLETED]
                                         |            |              |
                                         | (failure)  v (fail)       v (veto)
                                         +-------> [CORRECTING] <----+
                                                      |
                                                      v (retries exhausted)
                                                   [FAILED]

[INTERRUPTED] -> [RECOVERING] -> [READY] -> (resumes from checkpoint)
[USER ACTION] -> [CANCELLED]
[UNAPPROVED MERGE] -> [WAITING_APPROVAL]
[SECURITY VIOLATION] -> [BLOCKED]
```
All transitions are recorded in the SQLite WAL database and checkpointed for crash recovery.
