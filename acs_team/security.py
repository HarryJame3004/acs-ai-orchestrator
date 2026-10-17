"""Deterministic path/command policy and value-free credential redaction."""

from __future__ import annotations

import json
import logging
from pathlib import Path, PurePosixPath
import re
import shlex
import sys
from typing import Any


_SENSITIVE = re.compile(r"(?i)(token|secret|password|api[_-]?key|authorization|cookie)")
_VALUES = re.compile(r"(?i)(bearer\s+)[^\s\"']+|((?:password|token|secret|api[_-]?key)\s*[=:]\s*)[^\s,;]+|(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SENSITIVE.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
        return _VALUES.sub(lambda m: (m.group(1) or m.group(2) or "") + "[REDACTED]", value)
    return value


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def contained_path(root: Path, relative: str, protected: tuple[Path, ...] = ()) -> Path:
    path = PurePosixPath(relative)
    if not relative or "\\" in relative or "\x00" in relative or path.is_absolute() or ".." in path.parts:
        raise PermissionError("Invalid relative path")
    if (path.parts and path.parts[0].casefold() == ".git") or tuple(part.casefold() for part in path.parts[:2]) == (".github", "workflows"):
        raise PermissionError("Repository control files require explicit operator review")
    target, workspace = (root / relative).resolve(), root.resolve()
    if target != workspace and workspace not in target.parents:
        raise PermissionError("Path escapes workspace")
    for entry in protected:
        canon = entry.resolve()
        if target == canon or canon in target.parents:
            raise PermissionError("Protected path")
    return target


def verification_argv(command: str | list[str]) -> list[str]:
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv or any(any(char in arg for char in ";&|><\n\r\x00") for arg in argv):
        raise PermissionError("Shell syntax is forbidden in verification commands")
    executable = Path(argv[0]).name
    if executable in {"pytest", "pytest.exe"}:
        argv[0:1] = [sys.executable, "-m", "pytest"]
    elif executable in {"python", "python3", Path(sys.executable).name} and argv[1:3] in (["-m", "pytest"], ["-m", "unittest"]):
        argv[0] = sys.executable
    else:
        raise PermissionError("Command is outside the verification allowlist")
    if any(arg.startswith(("--override-ini", "--confcutdir")) or arg in {"--collect-only", "--co", "--noconftest"} for arg in argv):
        raise PermissionError("Verification may not disable or replace test configuration")
    return argv


def run_verification(command: str | list[str], workspace: Path, timeout: float = 180) -> dict:
    from .supervision import ProcessSupervisor
    result = ProcessSupervisor().run(verification_argv(command), workspace, timeout=timeout)
    output = result["output"]
    counts = {"passed": 0, "failed": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "errors": 0}
    for number, state in re.findall(r"(\d+) (passed|failed|skipped|xfailed|xpassed|errors?)\b", output):
        counts["errors" if state in {"error", "errors"} else state] = int(number)
    unittest_count = re.search(r"Ran (\d+) tests?", output)
    if unittest_count and result["exit_code"] == 0 and re.search(r"\bOK\b", output):
        counts["passed"] = int(unittest_count[1])
    return {**result, "executed": True, "counts": counts,
            "passed": result["exit_code"] == 0 and result["reason"] == "completed" and counts["passed"] > 0
            and not any(counts[key] for key in ("failed", "skipped", "xfailed", "xpassed", "errors"))}


def sandbox_argv(workspace: Path, command: list[str], *, home: Path, network: bool = False,
                 private_paths: tuple[Path, ...] = (), read_only_workspace: bool = False) -> list[str]:
    workspace, home = workspace.resolve(), home.resolve()
    if workspace == Path("/") or workspace == home or home in workspace.parents:
        raise ValueError("Sandbox requires separate bounded workspace and home")
    bound = (workspace, home, *(Path(p).resolve() for p in ("/usr", "/bin", "/lib", "/lib64")))
    for private in private_paths:
        if any(private.resolve() == root or root in private.resolve().parents for root in bound):
            raise PermissionError("Sandbox bind would expose private controller state")
    # Never bind / or the operational home. The evidence key/state is absent.
    argv = ["bwrap", "--die-with-parent", "--new-session", "--unshare-all"]
    if network:
        argv.append("--share-net")
    for path in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(path).exists():
            argv += ["--ro-bind", path, path]
    argv += ["--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
             "--ro-bind" if read_only_workspace else "--bind", str(workspace), str(workspace), "--bind", str(home), str(home),
             "--chdir", str(workspace), "--", *command]
    return argv


def load_protected_paths(template: Path, override: str | None = None) -> tuple[Path, ...]:
    data = json.loads(override) if override is not None else json.loads(template.read_text())["protected_paths"]
    if not isinstance(data, list) or not data or not all(isinstance(p, str) and p.strip() for p in data):
        raise ValueError("Protected paths must be a nonempty list")
    return tuple(Path(p).expanduser().resolve() for p in data)
