"""Optional systemd notify protocol using the standard library only."""

import os
import socket


def notify(message: str) -> bool:
    target = os.environ.get("NOTIFY_SOCKET")
    if not target:
        return False
    if target.startswith("@"):
        target = "\0" + target[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
            client.sendto(message.encode(), target)
        return True
    except OSError:
        return False
