# ACS AI V2.2 — Autonomous Multi-Agent Coding & Guardian Platform

[![Platform](https://img.shields.io/badge/Platform-Arch%20Linux%20%7C%20Linux-blue)](https://archlinux.org/)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://python.org/)
[![Cloud baseline regression](https://github.com/HarryJame3004/acs-ai-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/HarryJame3004/acs-ai-orchestrator/actions/workflows/ci.yml)

**ACS AI** is an experimental, local-first Python coding orchestrator with planner, worker adapters, git worktrees, SQLite persistence and a **Guardian** evidence gate. Coordinated multi-agent execution and security guarantees remain under audit.

The unchanged orchestrator baseline is **37 passed / 5 failed**, with cloud and simulated results distinguished in [the audit](reports/PHASE_0_BASELINE_AUDIT.md). CI compares against disclosed existing failures; a green regression check does not mean all tests pass. Real worker authentication, MCP connectivity and the user's local deployment remain unverified. See [TESTING.md](TESTING.md) and [stage progress](docs/progress/PROGRESS.md) before development.

---

## 🌟 Key Capabilities

1. **Natural-Language Mission Control (`acsai -m`)**
   - Direct command-line missions without authoring JSON files:
     ```bash
     acsai -m "Create a Python calculator and test it"
     ```
   - Targeted workspace execution:
     ```bash
     acsai -m "Fix all failing tests" --repo ~/Projects/my-app
     ```
   - Dynamic worker routing:
     ```bash
     acsai -m "Refactor parser" --worker agy-google-b
     ```
   - Detached background execution:
     ```bash
     acsai -m "Build REST API" --bg
     ```
   - Multiline prompt and standard input piping:
     ```bash
     cat prompt.txt | acsai -m -
     ```

2. **Interactive Textual Dashboard (`acsai ui`)**
   - Live telemetry status cards (Daemon, SSD circuit breaker, CoreLock status, MCP count, Repositories).
   - In-terminal Mission Composer with multiline prompt editor, repository dropdown, and worker selector.
   - Real-time progress tracker and streaming live log modal (`Ctrl+L`).
   - Fullscreen mission modal (`Ctrl+N`).

3. **Multi-Agent Worker Pool**
   - **`codex-primary`**: OpenAI Codex CLI executed inside non-interactive bubblewrap sandboxes.
   - **`agy-google-a`**: Google Antigravity CLI authenticated with Google Account A.
   - **`agy-google-b`**: Google Antigravity CLI authenticated with Google Account B running in a dedicated isolated home directory.

4. **Autonomous Mission Planner & Verification Engine**
   - Automated git worktree isolation under `~/.local/share/acs-orchestrator/worktrees/`.
   - In-worktree automated pytest verification.
   - Bounded self-correction loop (up to 3 retries) with provider failover.
   - Cryptographic HMAC-SHA256 evidence package generation binding test results to commit SHAs.

5. **Fail-Closed Guardian & CoreLock Security**
   - Protected path immutability: Rejects any attempt to write or merge to protected core repositories (CoreLock).
   - Strict gatekeeper evaluation: Code is rejected if tests fail, diffs violate scope, or HMAC signatures do not verify.
   - Human approval requirement for remote branch publishing.

6. **MCP Inventory & Governance**
   - Inventories native tool definitions, Antigravity configs and Codex plugins; configured entries are not proof of connectivity.
   - Auth display masking exists, but comprehensive credential redaction is pending security hardening.

7. **SQLite WAL Persistence & Crash Recovery**
   - Full state persistence across systemd daemon restarts.
   - Automatic reconciliation of interrupted missions with safe checkpoint resumption.

---

## 📋 System Architecture Overview

```
                                  +-----------------------------+
                                  |   User Prompt / CLI / TUI   |
                                  |   (acsai -m / acsai ui)     |
                                  +--------------+--------------+
                                                 |
                                                 v
                                  +-----------------------------+
                                  |    ACS AI Daemon Server     |
                                  |     (127.0.0.1:20129)       |
                                  +--------------+--------------+
                                                 |
                     +---------------------------+---------------------------+
                     |                           |                           |
                     v                           v                           v
        +-------------------------+ +-------------------------+ +-------------------------+
        |   Autonomous Planner    | |     Repo Manager        | |       MCP Manager       |
        | (Decompose, Worktrees)  | | (Telemetry, CoreLock)   | | (51 Servers, Masking)   |
        +------------+------------+ +-------------------------+ +-------------------------+
                     |
                     v
+-----------------------------------------------------------------------------------------+
|                                Multi-Agent Worker Pool                                  |
|                                                                                         |
|   +-----------------------+     +-----------------------+     +-----------------------+ |
|   |     codex-primary     |     |     agy-google-a      |     |     agy-google-b      | |
|   |  (Bubblewrap Sandbox) |     |   (Google Account A)  |     |   (Google Account B)  | |
|   +-----------------------+     +-----------------------+     +-----------------------+ |
+--------------------------------------------+--------------------------------------------+
                                             |
                                             v
                              +-----------------------------+
                              |   Pytest Verification       |
                              |   (In-Worktree Sandbox)     |
                              +--------------+--------------+
                                             |
                                             v
                              +-----------------------------+
                              |    Cryptographic Evidence   |
                              |      (HMAC-SHA256)          |
                              +--------------+--------------+
                                             |
                                             v
                              +-----------------------------+
                              |    Guardian Gatekeeper      |
                              |  (Fail-Closed Verification) |
                              +--------------+--------------+
                                             |
                                             v
                              +-----------------------------+
                              | Clean Integration & Commit  |
                              +-----------------------------+
```

For comprehensive architectural specifications, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🚀 Quick Start

### Prerequisites
- Linux OS (Arch Linux, EndeavourOS, Debian/Ubuntu, Fedora)
- Python 3.12+ for the shared orchestrator and agpair installation
- Git 2.30+

### Installation
```bash
git clone https://github.com/HarryJame3004/acs-ai-orchestrator.git
cd acs-ai-orchestrator
python3 -m venv venv
source venv/bin/activate
pip install -e .
pip install -e ./agpair
```

For complete systemd daemon service installation, see [INSTALL.md](INSTALL.md).

### Cloud Development and Tests
```bash
bash scripts/cloud_setup.sh
.venv/bin/python scripts/cloud_test.py --report /tmp/acs-tests.json
```
The runner isolates runtime paths and explicitly lists local-only checks. One existing CLI test still fails because it hardcodes the original workstation's interpreter path. Use `python -m acs_team.cli` for the CLI: the installed `acsai` entry point also needs a separate packaging fix. See [TESTING.md](TESTING.md) for exact counts, labels and the incremental CI comparison command.

---

## 💻 CLI Command Reference

| Command | Description |
|---------|-------------|
| `acsai status` | Displays live multi-agent daemon, worker, and MCP status |
| `acsai -m "<prompt>"` | Executes natural-language coding mission |
| `acsai -m "<prompt>" --repo <path>` | Targets mission to specific Git repository |
| `acsai -m "<prompt>" --worker <w>` | Explicitly assigns worker (`auto`, `codex`, `agy-google-a`, `agy-google-b`) |
| `acsai -m "<prompt>" --bg` | Detaches mission to run in background |
| `acsai ui` | Launches interactive Textual Dashboard |
| `acsai missions` | Lists all historical and active missions |
| `acsai mission status <id>` | Shows detailed breakdown, plan, and checkpoints of a mission |
| `acsai mission logs <id>` | Views real-time persisted stage logs |
| `acsai mission cancel <id>` | Gracefully cancels an active mission |
| `acsai mission resume <id>` | Resumes an interrupted mission from its last checkpoint |
| `acsai mcp list` | Audits configured and usable MCP servers |
| `acsai mcp status` | Shows connected count and security masking state |
| `acsai mcp tools` | Discovers and enumerates all available MCP tools |
| `acsai repo list` | Lists registered repositories and branches |
| `acsai repo add <path>` | Registers a repository for orchestration |

---

## 🔒 Security & Verification

ACS AI enforces **strict fail-closed security**:
- **CoreLock Protected Paths**: Read-only protection prevents accidental modification of critical repositories.
- **HMAC Evidence Verification**: Diffs and test runs are bound to commit SHAs using HMAC signatures.
- **Credential Masking**: Sensitive tokens are never printed in logs or UI.

For details on security design and threat models, see [SECURITY.md](SECURITY.md).

---

## ⚠️ Current Limitations

1. **Non-Interactive Execution**: Workers execute in non-interactive batch modes. Interactive prompts (e.g. `read -p`) will timeout.
2. **Remote Push Isolation**: Remote pushing to GitHub branches requires explicit human confirmation via `acsai approval approve <id>`.

---

## 📄 License & Contributing

Contributions are welcome! Please review [CONTRIBUTING.md](CONTRIBUTING.md) before opening pull requests.
Licensed under the Apache License 2.0.
