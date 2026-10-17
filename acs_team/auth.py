"""Authentication and token management for ACS AI Local API and IPC.
Enforces secure token generation, constant-time validation, and file permission 0600.
"""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path
from typing import Optional

from .config import AUTH_TOKEN_PATH


def get_or_create_auth_token(token_path: Optional[Path] = None) -> str:
    """Retrieves existing auth token or generates a 32-byte hex token with 0600 permissions."""
    path = Path(token_path or AUTH_TOKEN_PATH)
    if path.exists():
        try:
            token = path.read_text(encoding="utf-8").strip()
            if len(token) >= 32:
                return token
        except Exception:
            pass

    # Generate fresh secure token
    token = secrets.token_hex(32)
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write with strict 0600 permissions
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = 0o600
    fd = os.open(str(path), flags, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    return token


def verify_token(provided_token: Optional[str], expected_token: str) -> bool:
    """Constant-time verification of bearer token to prevent timing attacks."""
    if not provided_token or not expected_token:
        return False
    # Strip optional 'Bearer ' prefix
    cleaned = provided_token.strip()
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
    return hmac.compare_digest(cleaned.encode("utf-8"), expected_token.encode("utf-8"))
