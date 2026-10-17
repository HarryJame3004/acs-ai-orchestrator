# ACS Verified Project State & Roadmap Specification

**Generated Date:** 2026-10-17  
**Verification Method:** Direct filesystem inspection, runtime probe, live 9Router/Codex testing, full pytest execution (240/240 passed).

---

## 1. Executive Status Overview

- **Core Project Path:** `/home/khoi/autonomous-coding-system`
- **Lab Project Path:** `/home/khoi/Projects/acs-telegram-control-lab`
- **Approved Workspace Roots:** `/home/khoi/Projects`, `/home/khoi/autonomous-coding-system`
- **Core Architecture:** Standalone Python 3.14 + SQLite WAL Persistent Job Manager on `127.0.0.1:5050`
- **Automated Test Health:** 362/362 tests passing (100% pass rate, 69.64s execution time)
- **Model Infrastructure:** Local 9Router (`http://127.0.0.1:20128/v1`) + OpenAI Codex CLI (`codex exec` via ChatGPT authentication)

---

## 2. Phase-by-Phase Verification Matrix

| Phase | Description | Observed Artifacts | Verified Status |
|---|---|---|---|
| **Phase 1-3** | Persistent Job Manager & SQLite WAL Schema | `src/models.py`, `src/manager.py`, `src/database.py`, `migrations/`, `data/job_manager.sqlite3` | **VERIFIED & WORKING** (240/240 unit/integration tests pass) |
| **Phase 4-8** | Model Registry, Failover, Decision Engine, Auto-fix | `src/decision_engine.py`, `src/autofix.py`, `data/model_registry.json` | **VERIFIED & WORKING** (Regression suite passes 100%) |
| **Phase 9-13** | n8n Orchestrator & Multi-Agent Controller | `n8n_workflows/phase12_recovery_monitor.json`, `phase13_multi_agent_controller.json` | **VERIFIED & WORKING** (Deployed & verified in Phase 13/14) |
| **Phase 14** | Durability & Stability Validation | `reports/ACS_PHASE14_STABILITY_AND_VALIDATION_REPORT.md` | **VERIFIED** (6-turn swarm verified, +2.64 MB leak-free) |
| **Phase 15** | Claude Code CLI Automatic Bridge | `staging/claude_bridge/`, `tests/test_claude_bridge.py` | **VERIFIED & STAGED** (Non-invasive pilot verified) |
| **Phase 16** | Claude Code CLI Autonomous Launcher | `scripts/claude_launcher.sh`, `scripts/manage_claude_launcher.py`, `tests/test_phase16_launcher.py` | **VERIFIED & WORKING** (22/22 launcher tests pass) |
| **Phase 17** | Tool & Agent Integrations (DAG Scheduler, Semantic Classifier, Adapters) | `src/phase17/`, `tests/test_phase17/` | **VERIFIED & WORKING** (100/100 Phase 17 tests pass; 362/362 total ACS tests pass) |

---

## 3. Verified Multi-Agent Runtime Assets

1. **AI Planner / Supervisor:**
   - **Endpoint:** `http://127.0.0.1:20128/v1/chat/completions` (9Router)
   - **Model:** `free-reasoning` (Free reasoning model with `<think>` capability)
   - **Cost:** $0.00 (verified via AtlasCloud free tier)
   - **Role:** High-level project analysis, roadmap decomposition, task delegation, reviewer arbitration.

2. **Codex CLI Coding Worker:**
   - **Binary:** `/home/khoi/.npm-global/bin/codex` (v0.163.0)
   - **Model:** `gpt-6.1-sol` via ChatGPT authentication tokens
   - **Mode:** Headless `codex exec --dangerously-bypass-approvals-and-sandbox --ephemeral --json`
   - **Role:** Concrete code implementation, refactoring, test-driven bug fixes in isolated Git worktrees.

3. **Independent Reviewer & Tester:**
   - **Endpoints:** `http://127.0.0.1:20128/v1` (`free-review` and `free-testing`)
   - **Local Tools:** `pytest`, `python3 -m unittest`, `git diff`
   - **Role:** Independent critique of implementation diffs, edge case checking, automated verification execution.

4. **Task Lifecycle & Evidence Engine:**
   - **Framework:** `logicrw/agpair` (installed at `~/.local/share/acs-orchestrator/venv`)
   - **Persistence:** SQLite task database at `~/.agpair/tasks/`
   - **Isolation:** Dedicated Git worktrees per task; zero cross-contamination.

---

## 4. Operational Boundaries & Rules

1. **Zero Silent Paid Fallbacks:** If free models or authorized quotas are unavailable, fail closed with explicit reason rather than hitting paid endpoints.
2. **Worktree Isolation:** All code worker operations must run in separate Git worktrees or temporary staging branches.
3. **Evidence-Driven Completion:** No task is accepted by the Planner until the Reviewer confirms tests pass and structured diffs match acceptance criteria.
