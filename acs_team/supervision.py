"""Owned process-group supervision with bounded disk output and cancellation."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Callable
from .security import redact


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start: str
    group: int
    session: int


def identity(pid: int) -> ProcessIdentity | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        fields = raw[raw.rfind(")") + 2:].split()
        return ProcessIdentity(pid, fields[19], int(fields[2]), int(fields[3]))
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None


def descendants(root: int) -> list[ProcessIdentity]:
    found = {root}
    result = []
    entries = []
    for path in Path("/proc").iterdir():
        if path.name.isdigit():
            try:
                fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
                entries.append((int(path.name), int(fields[1])))
            except (OSError, ValueError):
                continue
    for _ in range(len(entries) + 1):
        additions = {pid for pid, parent in entries if parent in found} - found
        if not additions:
            break
        found.update(additions)
    for pid in found - {root}:
        child = identity(pid)
        if child:
            result.append(child)
    return result


class ProcessSupervisor:
    def __init__(self, maximum_workers: int = 3, output_limit: int = 1024 * 1024):
        if maximum_workers < 1 or output_limit < 1024:
            raise ValueError("Invalid supervisor resource limits")
        self.slots = threading.BoundedSemaphore(maximum_workers)
        self.output_limit = output_limit
        self._lock = threading.Lock()
        self._owned: dict[int, tuple[subprocess.Popen, ProcessIdentity]] = {}

    @contextmanager
    def start_owned(self, argv: list[str], cwd: Path, *, env: dict[str, str] | None = None):
        """Streaming protocol lifecycle; caller must bound its pipe messages."""
        if not self.slots.acquire(timeout=5):
            raise TimeoutError("Protocol process slot unavailable")
        process = None
        expected = None
        try:
            environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
            environment.update(env or {})
            command = [sys.executable, '-m', 'acs_team._exec_limits', str(self.output_limit), '0', '0', *argv]
            process = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            expected = identity(process.pid)
            if expected is None:
                process.wait(timeout=5)
                raise RuntimeError("Protocol process exited before ownership registration")
            with self._lock:
                self._owned[process.pid] = (process, expected)
            yield process
        finally:
            if process is not None:
                if expected is not None and process.poll() is None:
                    self.terminate(process, expected)
                process.wait(timeout=5)
                with self._lock:
                    self._owned.pop(process.pid, None)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream:
                        stream.close()
            self.slots.release()

    def terminate(self, process: subprocess.Popen, expected: ProcessIdentity, grace: float = 0.3) -> None:
        with self._lock:
            if self._owned.get(process.pid) != (process, expected):
                raise PermissionError("Refusing to terminate an unowned process")
        children = descendants(process.pid)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if identity(process.pid) == expected:
                try:
                    os.killpg(expected.group, sig)
                except ProcessLookupError:
                    pass
            # A descendant may create a new session; validate its birth identity.
            for child in children:
                if identity(child.pid) == child:
                    try:
                        os.kill(child.pid, sig)
                    except ProcessLookupError:
                        pass
            if sig == signal.SIGTERM:
                try:
                    process.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    pass
        process.wait(timeout=5)

    def run(self, argv: list[str], cwd: Path, *, timeout: float = 300,
            cancelled: Callable[[], bool] | None = None, env: dict[str, str] | None = None,
            memory_mb: int = 0, cpu_seconds: int = 0) -> dict:
        if timeout <= 0:
            raise ValueError("A positive execution timeout is required")
        names: tuple[str, ...] = ("PATH", "LANG", "LC_ALL", "TERM", "TMPDIR")
        if env is None:
            names += ("ACS_HOME", "ACS_BACKUPS_DIR", "ACS_CREDENTIALS_FILE")
        safe_env = {key: os.environ[key] for key in names if key in os.environ}
        if env:
            safe_env.update(env)
        if not self.slots.acquire(timeout=timeout):
            raise TimeoutError("Worker slot unavailable within the execution budget")
        try:
            buffers = [bytearray(), bytearray()]
            exceeded = threading.Event()
            def collect(stream, target):
                try:
                    while chunk := stream.read(4096):
                        remaining = self.output_limit - len(target)
                        target.extend(chunk[:max(0, remaining)])
                        if len(chunk) > remaining:
                            exceeded.set()
                finally:
                    stream.close()
            command = [sys.executable, "-m", "acs_team._exec_limits", str(self.output_limit), str(memory_mb), str(cpu_seconds), *argv]
            process = subprocess.Popen(command, cwd=cwd, env=safe_env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            readers = [threading.Thread(target=collect, args=(stream, target), daemon=True)
                       for stream, target in zip((process.stdout, process.stderr), buffers)]
            for reader in readers:
                reader.start()
            owned = identity(process.pid)
            if owned is None:
                process.wait(timeout=5)
                return {"exit_code": process.returncode, "output": "", "reason": "exited_before_registration"}
            with self._lock:
                self._owned[process.pid] = (process, owned)
            deadline = time.monotonic() + timeout
            reason = "completed"
            try:
                while process.poll() is None:
                    if cancelled and cancelled():
                        reason = "cancelled"
                    elif time.monotonic() >= deadline:
                        reason = "timeout"
                    elif exceeded.is_set():
                        reason = "output_limit"
                    else:
                        try:
                            process.wait(timeout=0.02)
                        except subprocess.TimeoutExpired:
                            pass
                        continue
                    self.terminate(process, owned)
                    break
            except BaseException:
                self.terminate(process, owned)
                raise
            finally:
                with self._lock:
                    self._owned.pop(process.pid, None)
            for reader in readers:
                reader.join(timeout=1)
            stdout, stderr = (redact(bytes(data).decode(errors="replace")) for data in buffers)
            if exceeded.is_set():
                reason = "output_limit"
            return {"exit_code": process.returncode, "output": stdout + "\n" + stderr,
                    "stdout": stdout, "stderr": stderr,
                    "reason": reason, "truncated": exceeded.is_set()}
        finally:
            self.slots.release()
