# Installation & Setup Guide — ACS AI Orchestrator

This guide walks you through installing, configuring, and verifying ACS AI V2.2 on Linux.

---

## 1. Prerequisites

- **Operating System**: Linux (Arch Linux, EndeavourOS, Debian/Ubuntu 22.04+, Fedora 38+)
- **Python**: Version 3.11, 3.12, 3.13, or 3.14
- **Git**: Version 2.30 or newer
- **Sandboxing (Optional but recommended)**: `bubblewrap` (`bwrap`)
- **Worker Tools (Optional based on desired workers)**:
  - OpenAI Codex CLI
  - Google Antigravity CLI (`agy`)

On Arch Linux:
```bash
sudo pacman -S python git bubblewrap
```

On Ubuntu / Debian:
```bash
sudo apt update && sudo apt install -y python3 python3-venv git bubblewrap
```

---

## 2. Source Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/HarryJame3004/acs-ai-orchestrator.git
cd acs-ai-orchestrator
```

### Step 2: Set Up Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### Step 3: Install Package & Dependencies
```bash
# Install core ACS AI orchestrator in editable mode
pip install -e .

# Install agpair worker bridge in editable mode
pip install -e ./agpair
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env` and supply your API gateway credentials if using 9Router / Claude settings:
```bash
cp .env.example .env
# Edit .env with your favorite editor
```

---

## 3. Persistent Systemd User Daemon Setup

ACS AI runs as a persistent background daemon that coordinates tasks, manages the SQLite WAL database, and exposes the local REST API at `127.0.0.1:20129`.

### Step 1: Create Systemd User Unit
Create `~/.config/systemd/user/acs-ai.service`:
```ini
[Unit]
Description=ACS AI Persistent Daemon
After=network.target

[Service]
Type=simple
ExecStart=/path/to/acs-ai-orchestrator/venv/bin/python3 -m acs_team.daemon
WorkingDirectory=/path/to/acs-ai-orchestrator
Restart=on-failure
RestartSec=5s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
```

### Step 2: Enable & Start Daemon
```bash
systemctl --user daemon-reload
systemctl --user enable acs-ai.service
systemctl --user start acs-ai.service
```

### Step 3: Verify Daemon Status
```bash
systemctl --user status acs-ai.service --no-pager
```

---

## 4. Setting Up the `acsai` CLI Command

Link the CLI entrypoint into your `~/.local/bin` directory so you can invoke `acsai` globally:

```bash
mkdir -p ~/.local/bin
ln -sf $(pwd)/venv/bin/acsai ~/.local/bin/acsai
```
Ensure `~/.local/bin` is in your `$PATH`.

---

## 5. Verification & Testing

Verify that the installation is fully functional by running:

### Check Platform Status
```bash
acsai status
```
Expected output:
```text
✓ Background Daemon: RUNNING
✓ SQLite WAL Database: READY
✓ Multi-Agent Worker Pool: READY
✓ CoreLock Security Boundary: ACTIVE
```

### Run the Full Regression Test Suite
```bash
pytest tests/ -v
```
All 42 tests should pass with exit code `0`.

### Run a Test Mission
```bash
acsai -m "Create a simple hello.py module with test"
```

---

## 6. Troubleshooting

- **Daemon endpoint connection refused (`127.0.0.1:20129`)**:
  Verify the systemd service logs via `journalctl --user -u acs-ai.service -n 50 --no-pager`.
- **Worker timeouts**:
  Check worker executables via `which codex` or `which agy`. If workers are not installed, the platform falls back to simulated/mock execution in test environments.
- **Permission errors on protected directories**:
  CoreLock will prevent modifications to protected paths such as `/home/khoi/autonomous-coding-system`. This is normal fail-closed behavior. Target your missions to a writable workspace with `--repo <path>`.
