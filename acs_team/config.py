import json
import os
import shutil
import sys
from pathlib import Path
from .security import load_protected_paths

# Base Paths
ORCHESTRATOR_HOME = Path(os.environ.get("ACS_HOME", str(Path(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))) / "acs-orchestrator"))).expanduser().resolve()
STATE_DIR = ORCHESTRATOR_HOME / "state"
CONTEXT_DIR = ORCHESTRATOR_HOME / "context"
CONTEXT_FILE = CONTEXT_DIR / "ACS_VERIFIED_PROJECT_STATE.md"
WORKTREES_DIR = ORCHESTRATOR_HOME / "worktrees"
WORKSPACES_DIR = ORCHESTRATOR_HOME / "workspaces"
LOGS_DIR = ORCHESTRATOR_HOME / "logs"
BACKUPS_DIR = Path(os.environ.get("ACS_BACKUPS_DIR", str(ORCHESTRATOR_HOME.parent / "acs-orchestrator-backups"))).expanduser()

# Executables
VENV_BIN = ORCHESTRATOR_HOME / "venv" / "bin"
VENV_PYTHON = VENV_BIN / "python3"
AGPAIR_BIN = VENV_BIN / "agpair"
CODEX_BIN = Path(os.environ.get("CODEX_BIN", shutil.which("codex") or os.path.expanduser("~/.npm-global/bin/codex")))
AGY_BIN = Path(os.environ.get("AGY_A_BIN", shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")))
AGY_B_BIN = Path(os.environ.get("AGY_B_BIN", shutil.which("agy-b") or os.path.expanduser("~/.local/bin/agy-b")))
AGY_B_HOME = Path(os.path.expanduser("~/.local/share/agy-google-b/home"))
GIT_BIN = Path("/usr/bin/git")
BWRAP_BIN = Path("/usr/bin/bwrap")
ACS_CORE_DIR = Path(os.path.expanduser("~/autonomous-coding-system"))
PROTECTED_PATHS = load_protected_paths(Path(__file__).with_name("defaults.json"), os.environ.get("ACS_PROTECTED_PATHS"))
ACS_CORE_DIR = Path(os.environ.get("ACS_CORE_PATH", str(ACS_CORE_DIR))).expanduser().resolve()
PROTECTED_PATHS = tuple(dict.fromkeys((*PROTECTED_PATHS, ACS_CORE_DIR)))

for runtime_path in (ORCHESTRATOR_HOME, BACKUPS_DIR):
    if any(runtime_path.resolve() == protected or protected in runtime_path.resolve().parents for protected in PROTECTED_PATHS):
        raise ValueError('Runtime state/backups may not be located inside a protected project')

# Read-only discovery/preview must not initialize an operational installation.
READ_ONLY_INVOCATION = any(arg in {'verify-local', 'provider-usage', '--dry-run', '--help', '-h', 'mcp'} for arg in sys.argv)
if not READ_ONLY_INVOCATION:
    if any(os.environ.get(name) == '1' for name in ('ACS_REQUIRE_HARD_STORAGE','ACS_REQUIRE_SERVICE_LIMITS')):
        from .aggregate_limits import configured_limits, require_managed_write
        configured_limits()  # Verify requested kernel contracts before state/log creation.
        require_managed_write(ORCHESTRATOR_HOME)
        require_managed_write(BACKUPS_DIR)
    for directory in (ORCHESTRATOR_HOME, STATE_DIR, CONTEXT_DIR, WORKTREES_DIR, WORKSPACES_DIR, LOGS_DIR, BACKUPS_DIR):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)

# Database & IPC
DB_PATH = STATE_DIR / "acs_ai.db"
SOCKET_PATH = ORCHESTRATOR_HOME / "acs_ai.sock"
AUTH_TOKEN_PATH = ORCHESTRATOR_HOME / "auth.token"
PID_FILE = ORCHESTRATOR_HOME / "daemon.pid"
API_PORT = int(os.environ.get("ACS_API_PORT", "20129"))
API_HOST = os.environ.get("ACS_API_HOST", "127.0.0.1")
if API_HOST not in {"127.0.0.1", "localhost", "::1"}:
    raise ValueError("ACS API is restricted to loopback")

# Resource Safeguards
MIN_DISK_FREE_GB = 10.0  # Circuit breaker threshold for 256GB SSD
DISK_MIN_FREE_BYTES = int(MIN_DISK_FREE_GB * (1024**3))
MAX_CONCURRENT_WORKERS = 3

# 9Router configuration
ROUTER_BASE_URL = os.environ.get("ROUTER_BASE_URL", "http://127.0.0.1:20128/v1")


def get_router_api_key() -> str:
    """Retrieve 9router API key from environment or ~/.claude/settings.json."""
    if os.environ.get("NINE_ROUTER_API_KEY"):
        return os.environ["NINE_ROUTER_API_KEY"]
    claude_settings = Path(os.environ.get("ACS_CREDENTIALS_FILE", os.path.expanduser("~/.claude/settings.json")))
    if claude_settings.exists():
        try:
            data = json.loads(claude_settings.read_text(encoding="utf-8"))
            token = data.get("env", {}).get("ANTHROPIC_AUTH_TOKEN")
            if token:
                return token
        except Exception:
            pass
    return os.environ.get("ROUTER_API_KEY", "")


ROUTER_API_KEY = "" if READ_ONLY_INVOCATION else get_router_api_key()

# Model assignments (all verified free tier on 9Router)
MODEL_PLANNER = os.environ.get("ACS_MODEL_PLANNER", "free-coding")
MODEL_REVIEWER = os.environ.get("ACS_MODEL_REVIEWER", "free-review")
MODEL_TESTER = os.environ.get("ACS_MODEL_TESTER", "free-testing")
MODEL_FALLBACK = "free-light"
