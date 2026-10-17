"""Mission-scoped MCP catalogs, approval hashes and conservative supply-chain policy."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, field_validator

from .recovery import private_write
from .schemas import Data, Identifier, Text, parse_data
from .security import redact


class ServerPolicy(Data):
    name: Identifier
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[.+-][A-Za-z0-9.-]+)?$")
    source_url: Text
    command: list[str] = Field(min_length=1, max_length=32)
    tools: list[Identifier] = Field(min_length=1, max_length=64)
    harmless_tool: Identifier
    harmless_arguments: dict[str, Any] = Field(default_factory=dict, max_length=16)
    approved_tool_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    network: bool = False
    env_names: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("command")
    @classmethod
    def pinned_command(cls, argv):
        if any(
            len(a) > 512 or any(c in a for c in "\n\r\x00") or "latest" in a.casefold()
            for a in argv
        ):
            raise ValueError("Unbounded/unpinned MCP command")
        program = Path(argv[0]).name
        if program in {"sh", "bash", "zsh", "cmd", "powershell", "curl", "wget"}:
            raise ValueError("MCP command may not be a shell or installer script")
        if program in {"npx", "uvx"}:
            package = next((a for a in argv[1:] if not a.startswith("-")), "")
            if program == "npx" and not re.search(r"@\d+\.\d+\.\d+$", package):
                raise ValueError("npx MCP packages require exact versions")
            if program == "uvx" and not re.search(r"==\d+\.\d+\.\d+$", package):
                raise ValueError("uvx MCP packages require exact versions")
        return argv

    @field_validator("source_url")
    @classmethod
    def valid_source(cls, value):
        parsed = urlparse(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Supply-chain source must be credential-free HTTPS")
        return value

    @field_validator("env_names")
    @classmethod
    def narrow_environment(cls, names):
        if any(
            not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", name)
            or name.startswith(("LD_", "DYLD_", "PYTHON", "GIT_CONFIG"))
            or name in {"HOME", "ACS_HOME", "BASH_ENV", "ENV", "NODE_OPTIONS"}
            for name in names
        ):
            raise ValueError(
                "MCP cannot inherit execution/controller environment controls"
            )
        return names


class MissionMCPPolicy(Data):
    servers: list[ServerPolicy] = Field(default_factory=list, max_length=6)


def definition_hash(tools: list[dict]) -> str:
    if not isinstance(tools, list) or len(tools) > 128:
        raise ValueError("MCP tool catalog exceeds budget")
    names = []
    for tool in tools:
        if (
            not isinstance(tool, dict)
            or not isinstance(tool.get("name"), str)
            or not tool["name"]
            or len(tool["name"]) > 128
        ):
            raise ValueError("Malformed MCP tool definition")
        names.append(tool["name"])
    if len(set(names)) != len(names):
        raise ValueError("Duplicate MCP tools")
    raw = json.dumps(
        sorted(tools, key=lambda t: t["name"]),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    if len(raw.encode()) > 65536:
        raise ValueError("MCP definitions exceed 64 KiB")
    # Hash raw definitions, including untrusted descriptions, rather than a
    # redacted display. Updates to any description/schema require re-approval.
    return hashlib.sha256(raw.encode()).hexdigest()


def audit_catalog(name: str, tools: list[dict], approved: str | None = None) -> dict:
    digest = definition_hash(tools)
    return {
        "name": name,
        "tool_hash": digest,
        "status": "APPROVED" if approved == digest else "REAPPROVAL_REQUIRED",
        "tools": redact(tools),
        "tool_count": len(tools),
        "operational_status": "NOT_TESTED",
    }


def save_catalog(
    path: Path, name: str, tools: list[dict], *, operator_confirmed: bool = False
) -> dict:
    if not operator_confirmed:
        raise PermissionError(
            "Tool definition approval requires explicit operator confirmation"
        )
    result = audit_catalog(name, tools, definition_hash(tools))
    private_write(path, (json.dumps(result, indent=2) + "\n").encode())
    return result


def load_policy(path: Path) -> MissionMCPPolicy:
    with path.open("rb") as stream:
        raw = stream.read(65537)
    policy = parse_data(MissionMCPPolicy, raw)
    if len({s.name for s in policy.servers}) != len(policy.servers):
        raise ValueError("Duplicate MCP servers")
    return policy
