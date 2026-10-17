"""Best-effort event-only delivery, disabled by default; no private source payloads."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

EVENTS = {
    "completed",
    "failed",
    "approval_required",
    "worker_blocked",
    "security_finding",
    "recovery",
}


def notify_event(
    event: str,
    *,
    desktop: Callable[[list[str]], None] | None = None,
    network: Callable[[str, bytes], None] | None = None,
) -> dict:
    if event not in EVENTS:
        raise ValueError("Unsupported notification event")
    if os.environ.get("ACS_ENABLE_NOTIFICATIONS") != "1":
        return {"status": "DISABLED"}
    # No prompt, file path, error body, credential, code or model text enters
    # notification content. Event names are controller-owned enum values.
    message = "ACS AI: " + event.replace("_", " ")
    attempts = []
    try:
        executable = shutil.which("notify-send")
        if desktop or executable:
            argv = [executable or "notify-send", "ACS AI", message]
            if desktop:
                desktop(argv)
            else:
                subprocess.run(argv, check=True, timeout=3, capture_output=True)
            attempts.append("desktop accepted")
    except (OSError, subprocess.SubprocessError):
        attempts.append("desktop unavailable")
    endpoint = os.environ.get("ACS_NOTIFY_NTFY_URL")
    if endpoint and os.environ.get("ACS_NOTIFY_NETWORK") == "1":
        parsed = urlparse(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Notification provider must be an explicit credential-free HTTPS endpoint"
            )
        try:
            if network:
                network(endpoint, message.encode())
            else:
                with urlopen(
                    Request(endpoint, data=message.encode(), method="POST"), timeout=3
                ) as response:
                    response.read(4096)
            attempts.append("provider accepted")
        except OSError:
            attempts.append("provider unavailable")
    return {
        "status": "ATTEMPTED" if attempts else "UNAVAILABLE",
        "attempts": attempts,
        "label": "LOCAL_VERIFICATION_REQUIRED",
        "delivery_confirmed": False,
    }
