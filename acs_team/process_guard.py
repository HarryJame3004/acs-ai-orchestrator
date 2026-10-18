"""Linux child subreaper in its own helper process; never alters the controller.

The separately packaged bridge ships the same stdlib-only helper. Keep copies
identical. A group signal requests cleanup; the helper reaps adopted descendants
before exiting so container PID 1 is not responsible for their zombies.
"""

from __future__ import annotations

import ctypes
import os
import resource
from pathlib import Path
import signal
import sys
import time


def _scan_descendants(root: int) -> dict[int, str]:
    # Some kernels omit /proc/.../children (CONFIG_CHECKPOINT_RESTORE).
    records = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / "stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            records[int(path.name)] = (int(fields[1]), fields[19])
        except (OSError, ValueError, IndexError):
            continue
    found = {root}
    while True:
        additions = {pid for pid, (parent, _) in records.items() if parent in found} - found
        if not additions:
            break
        found.update(additions)
    return {pid: records[pid][1] for pid in found - {root}}


def _descendants(root: int) -> dict[int, str]:
    # Traverse only this owned tree. A full /proc scan can miss a cleanup deadline
    # on busy hosts and is unnecessary; children may belong to any worker thread.
    found: dict[int, str] = {}
    children_available = False
    pending = [root]
    visited = {root}
    while pending:
        parent = pending.pop()
        try:
            threads = list(Path(f"/proc/{parent}/task").iterdir())
        except OSError:
            continue
        for thread in threads:
            try:
                children = (thread / "children").read_text().split()
                children_available = True
            except OSError:
                continue
            for text in children:
                try:
                    pid = int(text)
                    if pid in visited:
                        continue
                    raw = Path(f"/proc/{pid}/stat").read_text()
                    fields = raw[raw.rfind(")") + 2:].split()
                    # Ignore a PID already reparented outside this owned tree.
                    if int(fields[1]) != parent:
                        continue
                    found[pid] = fields[19]
                    visited.add(pid)
                    pending.append(pid)
                except (OSError, ValueError, IndexError):
                    continue
    return found if children_available else _scan_descendants(root)


def _signal_owned(root: int, sig: signal.Signals) -> None:
    for pid, start in _descendants(root).items():
        descriptor = None
        try:
            descriptor = os.pidfd_open(pid, 0)
            raw = Path(f"/proc/{pid}/stat").read_text()
            fields = raw[raw.rfind(")") + 2 :].split()
            if fields[19] == start:
                signal.pidfd_send_signal(descriptor, sig)
        except (OSError, ValueError, IndexError):
            pass
        finally:
            if descriptor is not None:
                os.close(descriptor)


def run(argv: list[str], expected_parent: int | None = None) -> int:
    if not argv:
        raise ValueError("Guard requires a child argv")
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Process guard requires Linux")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Cannot enable child subreaper")
    stopping = [False]

    def stop(signum, frame):
        stopping[0] = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    if expected_parent is not None:
        if library.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'Cannot enforce supervisor parent lifetime')
        if os.getppid() != expected_parent:
            return 143
    worker = os.fork()
    if worker == 0:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        try:
            os.execvpe(argv[0], argv, os.environ)
        except OSError:
            os._exit(127)
    worker_result = None
    cleanup_started = None
    sent_term = False
    while True:
        no_children = False
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                no_children = True
                break
            except InterruptedError:
                continue
            if pid == 0:
                break
            if pid == worker:
                worker_result = os.waitstatus_to_exitcode(status)
                stopping[0] = True
        if no_children:
            result = worker_result if worker_result is not None else 143
            if result < 0:
                child_signal = -result
                if child_signal not in {signal.SIGKILL, signal.SIGSTOP}:
                    signal.signal(child_signal, signal.SIG_DFL)
                os.kill(os.getpid(), child_signal)
                return 128 + child_signal
            return result
        if stopping[0]:
            if not sent_term:
                _signal_owned(os.getpid(), signal.SIGTERM)
                sent_term = True
                # Discovery can be slow on kernels without /proc children.
                # Start grace after TERM delivery and reap before scanning again.
                cleanup_started = time.monotonic()
            elif cleanup_started is not None and time.monotonic() - cleanup_started >= 0.1:
                _signal_owned(os.getpid(), signal.SIGKILL)
            # Only ECHILD above establishes completed cleanup. A wall-clock
            # deadline here can expire while this helper is descheduled, after
            # a descendant has already exited but before the next waitpid. It
            # falsely returned 125 and could orphan an unreaped descendant.
            # Keep ownership and reap; the outer supervisor still enforces the
            # unchanged invocation deadline and owned-tree termination policy.
        time.sleep(0.005)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
