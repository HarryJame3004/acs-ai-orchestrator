# ACS AI V2.2 — NATURAL LANGUAGE AUTONOMOUS MISSION CONTROL REPORT
**System:** ACS AI Autonomous Coding & Guardian Platform  
**Version:** V2.2 (Release Candidate)  
**Date:** 2026-10-18  
**Environment:** Arch Linux / EndeavourOS, HP EliteBook 840 G6, Python 3.14.8  
**Author:** Principal Autonomous Systems Engineer & Security Auditor  

---

## 1. Executive Summary

ACS AI V2.2 transforms the Autonomous Coding System from a JSON-only multi-phase runner into a **production-ready, natural-language mission control platform**. Developers can now prompt the platform directly via CLI (`acsai -m "..."`) or via the upgraded Textual Dashboard Mission Composer (`acsai ui`), completely removing the requirement to manually author JSON task graphs.

The system autonomously inspects target Git repositories, generates structured task specifications with acceptance criteria, isolates work in git worktrees, schedules workers (`codex-primary`, `agy-google-a`, `agy-google-b`), executes automated pytest verification with bounded correction retries, generates cryptographic HMAC-SHA256 evidence packages, and enforces independent fail-closed Guardian review before merging.

All 16 acceptance test criteria and all 42 platform unit/integration tests passed with **100% success rate (42 passed, 0 failed)**. A real end-to-end coding mission was executed live on a temporary repository, successfully generating a Python calculator module with pytest test suite in 74.0 seconds with a Quality Score of 1.00.

---

## 2. Features Implemented

### Feature 1 — Direct Natural-Language Missions
- **CLI Flag:** Top-level `-m / --mission` accepting natural-language prompts.
- **Multiline Support:** Supports multiline strings and stdin pipes (`-m -`).
- **No JSON Required:** Decomposes user goals directly into actionable tasks.
- **Repository Detection:** Detects Git repo from CWD; falls back to an isolated workspace under `~/.local/share/acs-orchestrator/workspaces/` if outside a Git repo.
- **CoreLock Guard:** Strictly forbids selecting `/home/khoi/autonomous-coding-system` as a writable workspace, failing closed with a `PermissionError`.
- **Execution Modes:** Foreground progress streaming with stage logs or background detached execution via `--bg`.

### Feature 2 — Autonomous Mission Planner
- **Inspection:** Automatically inspects repository file tree, project instructions, and branch status.
- **Task Graph Generation:** AI Planner decomposes natural-language prompts into task specifications with target files, acceptance criteria, and test commands.
- **Worktree Isolation:** Creates clean git worktrees under `~/.local/share/acs-orchestrator/worktrees/` for every task.
- **Automated Verification:** Runs pytests inside worktrees to verify implementation correctness.
- **Correction Loop:** Automatically analyzes test failures and triggers AI Planner to generate surgical fix instructions (up to 3 retries).
- **HMAC Evidence:** Binds test execution outputs and git diffs to commit SHAs using HMAC-SHA256 signatures.
- **Guardian Gatekeeper:** Independent fail-closed evaluation before integration.

### Feature 3 — Multi-Agent Worker Scheduling
- **Intelligent Allocation:** Supports `--worker auto`, `--worker codex`, `--worker agy-google-a`, `--worker agy-google-b`.
- **Worker Verification:** Dynamic health and capability verification from `WorkerRegistry`.
- **Failover:** Automatic failover between verified workers if provider errors occur during correction retries.
- **Isolation:** AGY Google B runs in dedicated isolated home environment (`~/.local/share/acs-orchestrator/agy_b_home/`).

### Feature 4 — Dashboard Mission Composer (TUI)
- **Main Dashboard Composer:** Built directly into the Textual TUI (`acsai ui`), featuring:
  - Prompt `TextArea` for natural language inputs.
  - Repository `Select` dropdown populated from registered repositories + Isolated Workspace option.
  - Worker `Select` dropdown (`auto`, `codex`, `agy-google-a`, `agy-google-b`).
  - "Start Mission" action button.
  - Active Mission Progress & Live Logs box updating in real-time via thread-safe background workers (`app.run_worker`).
- **Expanded Mission Modal:** Pressing `Ctrl+N` opens a dedicated fullscreen composer for complex multiline prompts.
- **Live Logs Modal:** Pressing `Ctrl+L` displays full scrollable logs for active or historical missions.
- **Keyboard Shortcuts:** `Ctrl+N` (New Mission), `Ctrl+L` (View Logs), `Ctrl+Enter` (Submit), `Esc` (Close Modal).
- **Responsive Layout:** Fluid layout without fixed pixel overflows, rendering cleanly on compact terminal windows (80x24).

### Feature 5 — Mission Lifecycle & Management
- **Lifecycle States:** QUEUED, PLANNING, READY, RUNNING, INTEGRATING, TESTING, REVIEWING, WAITING_APPROVAL, COMPLETED, FAILED, BLOCKED, CANCELLED, RECOVERING.
- **CLI Commands:**
  - `acsai missions` (list all missions with state and score)
  - `acsai mission status <id>` (detailed mission breakdown, prompt, plan, checkpoints)
  - `acsai mission logs <id>` (real-time persisted logs)
  - `acsai mission cancel <id>` (graceful cancellation)
  - `acsai mission resume <id>` (resume interrupted missions)
  - `acsai mission <file.json>` (retains backward compatibility for JSON missions)
- **Persistence:** Mission state, prompt, plan, and logs persist in SQLite WAL across daemon restarts.

### Feature 6 — MCP Inventory & Tool Verification
- **Registry Inspection:** Audits native ACS tools, Antigravity configs (`~/.gemini/config/mcp_config.json`), AGY Google B configs, and Codex plugins.
- **Classification:** Distinguishes CONFIGURED (defined in JSON), CONNECTED (runnable/testable), USABLE (tools exposed and invokable), and INSTALLED.
- **Zero Credential Leaking:** All tokens, API keys, and sensitive URLs are strictly masked (`github_pat_***`).
- **CLI Commands:**
  - `acsai mcp list`
  - `acsai mcp status`
  - `acsai mcp tools`
- **Dashboard Cards:** Real-time MCP server and tool counts displayed on TUI dashboard.

### Feature 7 — Repository Inventory & Management
- **Managed Repositories:** Tracks explicitly registered repositories in SQLite (`repositories` table).
- **Live Git Telemetry:** Tracks branch, clean/dirty working tree state, last mission, and read-only protection.
- **CLI Commands:**
  - `acsai repo list`
  - `acsai repo status`
  - `acsai repo add <path> [--name <name>]` (rejects ACS Core)

### Feature 8 — Security & Permissions
- **CoreLock Immutability:** `/home/khoi/autonomous-coding-system` is 100% read-only.
- **Path Traversal Guards:** Resolves canonical paths to prevent symlink traversal outside designated workspaces.
- **Fail-Closed Guardian:** Rejects unverified commits, missing tests, or unapproved merges to protected branches.

---

## 3. Files Modified and Created

| File | Change Type | Description |
|------|-------------|-------------|
| `acs_team/config.py` | Modified | Added `WORKSPACES_DIR = ORCHESTRATOR_HOME / "workspaces"`. |
| `acs_team/db.py` | Modified | Added `repositories` table, migrated `missions` schema (`prompt`, `plan_json`, `logs`), added repository CRUD and mission log methods. |
| `acs_team/repo_manager.py` | Created | Implemented `RepoManager` with live Git telemetry, CoreLock guard, and `resolve_target_workspace()`. |
| `acs_team/mcp_manager.py` | Created | Implemented `MCPManager` auditing 51 MCP servers with secret masking. |
| `acs_team/autonomous_planner.py` | Created | Implemented end-to-end `AutonomousMissionPlanner` with worker scheduling, worktrees, pytests, retries, and Guardian integration. |
| `acs_team/api_server.py` | Modified | Added `/mcp`, `/repos`, `/missions/<id>/logs`, `/workers` dynamic dispatch, and natural language POST endpoints. |
| `acs_team/cli.py` | Modified | Added `-m / --mission`, `--repo`, `--worker`, `--bg`, `missions`, `mission status/logs/cancel/resume`, `mcp list/status/tools`, `repo list/status/add`. |
| `acs_team/tui.py` | Modified | Upgraded Textual TUI with Dashboard Mission Composer, `NewMissionModal` (Ctrl+N), `LogsModal` (Ctrl+L), and live background updates. |
| `tests/test_gate8_natural_language_and_v2_2.py` | Created | Comprehensive 16-test acceptance suite covering all Feature 9 scenarios. |
| `tests/test_gate6_e2e_and_cli.py` | Modified | Updated TUI title assertion for V2.2. |
| `reports/ACS_AI_V2_2_NATURAL_LANGUAGE_MISSION_REPORT.md` | Created | Official delivery report. |

---

## 4. Exact CLI Usage Examples

### 1. Direct Natural Language Mission (Foreground)
```bash
acsai -m "Create a Python calculator and test it"
```

### 2. Targeted Repository Mission
```bash
acsai -m "Fix all failing tests" --repo ~/Projects/example
```

### 3. Worker Preference Selection
```bash
acsai -m "Review this project" --worker auto
acsai -m "Implement authentication" --worker codex
acsai -m "Refactor parser" --worker agy-google-b
```

### 4. Background Execution
```bash
acsai -m "Build REST API endpoint" --bg
# Returns mission ID: mission-20261017-175203-edd440
```

### 5. Multiline Mission Prompt
```bash
acsai -m "Create calculator module
- Implement add, subtract, multiply, divide
- Raise ValueError on divide by zero
- Add full pytest suite"
```
Or via standard input:
```bash
cat task.txt | acsai -m -
```

### 6. Inspecting and Managing Missions
```bash
# List all missions
acsai missions

# Inspect mission details and plan
acsai mission status mission-20261017-175203-edd440

# Inspect live mission logs
acsai mission logs mission-20261017-175203-edd440

# Cancel a running mission
acsai mission cancel mission-20261017-175203-edd440

# Resume an interrupted mission
acsai mission resume mission-20261017-175203-edd440
```

### 7. MCP Inventory & Verification
```bash
acsai mcp list
acsai mcp status
acsai mcp tools
```

### 8. Repository Inventory
```bash
acsai repo list
acsai repo status
acsai repo add ~/Projects/my-app --name "My Application"
```

### 9. Interactive Dashboard TUI
```bash
acsai ui
```

---

## 5. Verified Dashboard UI Description

The Textual Dashboard (`acsai ui`) is organized into an accessible, non-overlapping responsive layout:

1. **Header:** Displays live clock and title `ACS AI V2.2 Control Center`.
2. **Top Telemetry Row (6 Stat Cards):**
   - **DAEMON:** Endpoint `127.0.0.1:20129` | Status: `RUNNING` | DB: `CONNECTED`
   - **DUNG LƯỢNG SSD:** Free: `117.1 GB` | Threshold: `10.0 GB` | Status: `AN TOÀN`
   - **NHIỆM VỤ:** Total count | Running count | Completed count
   - **CORELOCK GUARD:** ACS Core (RO) | Status: `KHÓA CHẶT CHẼ` | Tests: `PASS`
   - **HỆ THỐNG MCP:** Configured: `51` | Usable: `19` | Discovered Tools: `68`
   - **KHO MÃ NGUỒN:** Total: `2` | Protected RO: `1` | Writable: `1`
3. **Mission Composer Card:**
   - Header with `BẢNG SOẠN THẢO NHIỆM VỤ (NATURAL LANGUAGE COMPOSER)` and `📜 Mở rộng (Ctrl+N)`.
   - Multiline `TextArea` prompt box with line numbers and syntax styling.
   - Controls row: Repository dropdown (`Select`), Worker dropdown (`Select`), and `🚀 Bắt đầu (Submit)` button.
4. **Active Mission Progress & Live Logs Box:**
   - Displays real-time updates as stages advance (`PLANNING -> RUNNING -> TESTING -> REVIEWING -> COMPLETED`).
   - Streams worker output and pytest results directly without freezing UI.
5. **Recent Missions Table:** Displays latest missions with ID, State, Quality Score, and prompt snippet.
6. **Active Worker Pool Table:** Displays live status of `codex-primary`, `agy-google-a`, and `agy-google-b`.
7. **Modals:**
   - `Ctrl+N` opens `NewMissionModal` (fullscreen prompt editor).
   - `Ctrl+L` opens `LogsModal` (full scrollable transcript).

---

## 6. Real Test Results

### Suite Execution
Command: `./venv/bin/pytest tests/`  
Result: **42 passed in 4.60s (100% pass rate)**

```
tests/test_gate2_daemon_and_db.py ......                                 [ 14%]
tests/test_gate3_workers_and_worktrees.py .....                          [ 26%]
tests/test_gate4_memory_mcp_rea.py ...                                   [ 33%]
tests/test_gate5_guardian_and_security.py ....                           [ 42%]
tests/test_gate6_e2e_and_cli.py ...                                      [ 50%]
tests/test_gate7_audit_and_reliability.py .....                          [ 61%]
tests/test_gate8_natural_language_and_v2_2.py ................           [100%]
============================== 42 passed in 4.60s ==============================
```

### Breakdown of Acceptance Test Scenarios (Feature 9)
| # | Test Scenario | Verified Result |
|---|---------------|-----------------|
| 1 | `acsai -m` without `--repo` | PASSED (Allocated isolated git workspace with README and commit) |
| 2 | `acsai -m` with existing repository | PASSED (Resolved target repo correctly) |
| 3 | Multiline prompts | PASSED (Preserved newlines in SQLite and plan) |
| 4 | Dashboard mission submission | PASSED (Invoked planner pipeline and emitted live logs) |
| 5 | Automatic worker selection | PASSED (Selected verified available worker) |
| 6 | Explicit worker selection | PASSED (Mapped codex, agy-a, agy-b properly) |
| 7 | SQLite mission persistence | PASSED (Verified prompt, plan_json, logs, score roundtrip) |
| 8 | Mission logs and progress | PASSED (Logged progress checkpoints in order) |
| 9 | Mission cancellation | PASSED (Transitioned to CANCELLED cleanly) |
| 10 | Resume after restart | PASSED (Crash reconciliation recovered from checkpoint) |
| 11 | Real coding task | PASSED (Created math functions and ran pytest 2 passed) |
| 12 | Pytest execution in worktree | PASSED (Captured exit codes 0 and non-zero) |
| 13 | Guardian evaluation & HMAC | PASSED (Verified HMAC-SHA256 signature and approval) |
| 14 | MCP inventory & secret masking | PASSED (51 servers audited, zero credentials leaked) |
| 15 | Repository inventory & status | PASSED (Listed registered repos with branch & clean status) |
| 16 | Protected ACS Core rejection | PASSED (PermissionError raised on CoreLock violation) |

---

## 7. Real End-to-End Mission Verification

A live natural-language mission was submitted to the orchestrator:
```bash
acsai -m "Create calculator.py and test_calculator.py and test it" --repo /tmp/acs_calc_test_repo --worker auto
```

### Execution Telemetry
- **Mission ID:** `mission-20261017-175203-edd440`
- **Target Repository:** `/tmp/acs_calc_test_repo`
- **Decomposed Plan:** Task `create_calculator_and_tests` with files `['calculator.py', 'test_calculator.py']`
- **Assigned Worker:** `agy-google-b` (Antigravity CLI isolated session)
- **Worktree:** `~/.local/share/acs-orchestrator/worktrees/mission-20261017-175203-edd440_task-1792259537`
- **Execution Time:** 74.0 seconds
- **Verification Tests:** `pytest test_calculator.py -v` (Exit code: 0, 5 unit tests passed)
- **Files Created:**
  - `calculator.py` (Functions: `add`, `subtract`, `multiply`, `divide` with `ValueError` on 0)
  - `test_calculator.py` (5 tests verifying positive, negative, float, and zero division)
- **HMAC Evidence Signature:** `d45908671f7a8285...`
- **Guardian Verdict:** `APPROVED (Score: 1.0000)`
- **Integrated Commit SHA:** `81cc9d7e9e845ac577c56910c5d53435bfaf4835`
- **Final Mission Status:** `COMPLETED`

---

## 8. Platform Inventory Telemetry

- **MCP Servers Configured:** 51
- **MCP Servers Connected:** 49
- **MCP Servers Usable:** 19
- **MCP Tools Usable:** 68
- **Managed Repositories:** 2
  - `ACS Core (Protected)`: `/home/khoi/autonomous-coding-system` [READ-ONLY]
  - `acs_calc_test_repo`: `/tmp/acs_calc_test_repo` [WRITABLE]
- **Worker Status:**
  - `codex-primary`: `[READY]` (Codex CLI sandbox)
  - `agy-google-a`: `[READY]` (Antigravity CLI Google Account A)
  - `agy-google-b`: `[READY]` (Antigravity CLI Google Account B, isolated home)

---

## 9. Backup & Rollback Instructions

### Safety Backup Created Prior to V2.2:
- **Archive Path:** `/home/khoi/.local/share/acs-orchestrator-backups/acs_orchestrator_backup_v2_2_pre_20261018_002829.tar.gz`
- **Size:** 2.75 MB
- **SHA-256:** `1de645c2aa3bd1b2d9271ac2ed1e443e68081a8f75d4a4868d00ec3f8006f36b`

### Rollback Procedure:
If a rollback is ever needed:
```bash
# 1. Stop daemon service
systemctl --user stop acs-ai.service

# 2. Restore orchestrator directory from backup archive
tar -xzf /home/khoi/.local/share/acs-orchestrator-backups/acs_orchestrator_backup_v2_2_pre_20261018_002829.tar.gz -C /home/khoi/.local/share/

# 3. Restart daemon service
systemctl --user start acs-ai.service
```

---

## 10. Known Limitations
1. **Interactive Prompts in Workers:** Non-interactive execution is enforced; workers attempting to open interactive terminal dialogues will encounter timeouts.
2. **External Push Permissions:** Pushing integrated branches to remote GitHub repositories requires explicit human approval via `acsai approval approve <id>` to guarantee fail-closed security.
