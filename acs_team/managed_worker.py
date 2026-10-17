"""Opt-in supervised worker execution, with a mandatory sandbox and narrow env."""

import os
from pathlib import Path
import subprocess
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from .security import sandbox_argv
from .supervision import ProcessSupervisor

_SUPERVISOR = ProcessSupervisor()
_CONTEXT: ContextVar[tuple[Any, str] | None] = ContextVar("acs_worker_context", default=None)


@contextmanager
def worker_context(control, mission_id):
    token = _CONTEXT.set((control, mission_id))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def worker_run(command, *, task_id=None, **kwargs):
    if os.environ.get("ACS_ENABLE_SUPERVISION") != "1":
        raise PermissionError('Real worker execution requires ACS_ENABLE_SUPERVISION=1; no unsupervised fallback is permitted')
    from .db import DatabaseManager
    from .runtime_control import RuntimeControl
    from .config import STATE_DIR, AUTH_TOKEN_PATH
    context = _CONTEXT.get()
    control, mission_id = context if context else (RuntimeControl(DatabaseManager(), initialize=False), None)
    control.require_dispatch()
    def cancelled():
        mission = control.db.get_mission(mission_id) if mission_id else None
        return control.stopped() or bool(mission and mission["state"] == "CANCELLED")
    provided = kwargs.get("env") or os.environ
    names = {"PATH", "LANG", "LC_ALL", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "GIT_TERMINAL_PROMPT"}
    names.update(filter(None, os.environ.get("ACS_WORKER_ENV_ALLOWLIST", "").split(",")))
    if any(name.startswith(("LD_", "DYLD_", "PYTHON", "GIT_CONFIG", "ACS_")) or name in {"BASH_ENV", "ENV", "NODE_OPTIONS"} for name in names):
        raise PermissionError("Worker environment contains a reserved execution-control name")
    environment = {name: provided[name] for name in names if name in provided}
    workspace = Path(kwargs["cwd"])
    with tempfile.TemporaryDirectory(prefix="acs-worker-home-") as temporary:
        environment.update({'HOME': temporary, 'XDG_CONFIG_HOME': str(Path(temporary)/'.config'),
                            'XDG_DATA_HOME': str(Path(temporary)/'.local/share'),
                            'XDG_STATE_HOME': str(Path(temporary)/'.local/state')})
        argv = sandbox_argv(workspace, command, home=Path(temporary), network=os.environ.get("ACS_WORKER_NETWORK") == "1",
                            private_paths=(STATE_DIR, AUTH_TOKEN_PATH))
        limited = os.environ.get("ACS_ENABLE_RUNTIME_LIMITS") == "1"
        result = _SUPERVISOR.run(argv, workspace, timeout=kwargs.get("timeout", 300),
                                 cancelled=cancelled, env=environment,
                                 memory_mb=int(os.environ.get("ACS_WORKER_MEMORY_MB", "0")) if limited else 0,
                                 cpu_seconds=int(os.environ.get("ACS_WORKER_CPU_SECONDS", "0")) if limited else 0)
    return subprocess.CompletedProcess(command, result["exit_code"], result.get("stdout", ""), result.get("stderr", ""))
