"""Single local daemon lock; never signals a PID read from an untrusted file."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from .supervision import identity


class ServiceLock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None

    def acquire(self):
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            own = identity(os.getpid())
            if own is None:
                raise RuntimeError("Cannot verify daemon birth identity")
            os.ftruncate(descriptor, 0)
            os.write(
                descriptor,
                json.dumps({"pid": own.pid, "start_ticks": own.start}).encode(),
            )
            self.fd = descriptor
        except BaseException:
            os.close(descriptor)
            raise
        return self

    def release(self):
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None
