"""ACS AI V2.2 MCP Inventory, Discovery & Verification Engine.
Inspects native ACS AI tools, Antigravity configs, AGY Google B configs, and Codex plugins.
Categorizes servers as INSTALLED, CONFIGURED, CONNECTED, or USABLE without exposing secrets.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from .config import AGY_B_HOME
from .mcp_registry import MCPRegistry
from .security import redact

logger = logging.getLogger("acs_ai.mcp_manager")


@dataclass
class MCPServerInfo:
    name: str
    source_config: str
    command_or_url: str
    server_type: str  # stdio, http, internal
    enabled: bool
    status: str       # USABLE, CONNECTED, CONFIGURED, INSTALLED, UNAVAILABLE
    tools_count: int
    capabilities: List[str]
    accessible_workers: List[str]
    auth_status: str  # NONE, CONFIGURED (MASKED), MISSING
    can_invoke: bool
    tools: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return redact(asdict(self))


class MCPManager:
    """Discovers, verifies, and audits MCP servers across the entire ACS platform."""

    def __init__(self):
        self.internal_registry = MCPRegistry()

    def get_inventory(self) -> List[MCPServerInfo]:
        """Discovers and inspects all MCP servers from all subsystem sources."""
        servers: List[MCPServerInfo] = []

        # 1. Native Internal ACS AI MCP Tools
        native_tools = self.internal_registry.list_tools()
        servers.append(MCPServerInfo(
            name="acs-native-core",
            source_config="internal:acs_team.mcp_registry",
            command_or_url="in-process (Python)",
            server_type="internal",
            enabled=True,
            status="USABLE",
            tools_count=len(native_tools),
            capabilities=["file_system", "binary_analysis", "state_control"],
            accessible_workers=["codex-primary", "agy-google-a", "agy-google-b", "orchestrator"],
            auth_status="INTERNAL (No auth required)",
            can_invoke=True,
            tools=native_tools,
        ))

        # 2. Antigravity Desktop / CLI (AGY A) Config
        agy_a_cfg = Path(os.path.expanduser("~/.gemini/config/mcp_config.json"))
        servers.extend(self._parse_gemini_mcp_config(agy_a_cfg, source_label="agy-google-a", workers=["agy-google-a", "orchestrator"]))

        # 3. AGY Google B Config
        agy_b_cfg = AGY_B_HOME / ".gemini" / "config" / "mcp_config.json"
        if agy_b_cfg.exists():
            servers.extend(self._parse_gemini_mcp_config(agy_b_cfg, source_label="agy-google-b", workers=["agy-google-b"]))

        # 4. Antigravity Plugins (gemini-api, science, flutter, data-agent-kit)
        plugin_root = Path(os.path.expanduser("~/.gemini/config/plugins"))
        if plugin_root.is_dir():
            for p_dir in plugin_root.iterdir():
                if p_dir.is_dir():
                    p_cfg = p_dir / "mcp_config.json"
                    if p_cfg.exists():
                        servers.extend(self._parse_gemini_mcp_config(p_cfg, source_label=f"plugin:{p_dir.name}", workers=["agy-google-a"]))

        # 5. Codex Plugin Cache
        codex_tmp = Path(os.path.expanduser("~/.codex/.tmp/plugins/plugins"))
        if codex_tmp.is_dir():
            for plug_dir in codex_tmp.iterdir():
                if plug_dir.is_dir():
                    mcp_json = plug_dir / ".mcp.json"
                    if mcp_json.exists():
                        servers.extend(self._parse_codex_mcp_config(mcp_json, plugin_name=plug_dir.name))

        return servers

    def _parse_gemini_mcp_config(
        self,
        config_path: Path,
        source_label: str,
        workers: List[str],
    ) -> List[MCPServerInfo]:
        """Parses a gemini standard mcp_config.json file."""
        if not config_path.exists() or config_path.stat().st_size == 0:
            return []

        results: List[MCPServerInfo] = []
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            mcp_servers = data.get("mcpServers", {})

            for name, s_cfg in mcp_servers.items():
                cmd = s_cfg.get("command", "")
                url = s_cfg.get("serverUrl") or s_cfg.get("url", "")
                env = s_cfg.get("env", {})

                # Check auth status without leaking tokens
                auth_status = "NONE"
                for k, v in env.items():
                    if any(s in k.lower() for s in ["token", "key", "secret", "auth"]):
                        auth_status = f"CONFIGURED ({k}=***)"
                        break

                server_type = "http" if url else "stdio"
                from urllib.parse import urlparse
                parsed_url = urlparse(url) if url else None
                command_summary = (f"{parsed_url.scheme}://{parsed_url.hostname} [endpoint details redacted]"
                                   if parsed_url else f"{cmd} [arguments redacted]")

                # Test if command binary is installed
                is_installed = bool(cmd and shutil.which(cmd)) or bool(url)
                can_invoke = is_installed
                status = "INSTALLED" if is_installed else "CONFIGURED"
                can_invoke = False  # A config or executable is not a protocol probe.

                # Check for cached tool schemas under ~/.gemini/antigravity/mcp/<name>/
                schema_dir = Path(os.path.expanduser(f"~/.gemini/antigravity/mcp/{name}"))
                tools_list = []
                if schema_dir.is_dir():
                    for f in schema_dir.glob("*.json"):
                        try:
                            s_data = json.loads(f.read_text(encoding="utf-8"))
                            tools_list.append({
                                "name": f.stem,
                                "description": s_data.get("description", "No description provided"),
                                "category": "tool",
                                "source": name,
                            })
                        except Exception:
                            tools_list.append({"name": f.stem, "description": "JSON schema tool", "source": name})

                tools_count = len(tools_list)

                results.append(MCPServerInfo(
                    name=name,
                    source_config=f"{source_label} ({config_path.name})",
                    command_or_url=command_summary,
                    server_type=server_type,
                    enabled=True,
                    status=status,
                    tools_count=tools_count,
                    capabilities=["tool_execution", "context_provider"],
                    accessible_workers=workers,
                    auth_status=auth_status,
                    can_invoke=can_invoke,
                    tools=tools_list,
                ))
        except Exception as e:
            logger.warning(f"Failed to parse MCP config at {config_path}: {e}")

        return results

    def _parse_codex_mcp_config(self, mcp_json: Path, plugin_name: str) -> List[MCPServerInfo]:
        """Parses a Codex plugin .mcp.json file."""
        results = []
        try:
            data = json.loads(mcp_json.read_text(encoding="utf-8"))
            mcp_servers = data.get("mcpServers", {})
            for name, s_cfg in mcp_servers.items():
                cmd = s_cfg.get("command", "")
                url = s_cfg.get("url", "")
                is_installed = bool(cmd and shutil.which(cmd)) or bool(url)
                results.append(MCPServerInfo(
                    name=f"codex-{plugin_name}-{name}",
                    source_config=f"codex:plugin/{plugin_name}",
                    command_or_url="[configured endpoint redacted]" if url else cmd,
                    server_type="http" if url else "stdio",
                    enabled=True,
                    status="INSTALLED" if is_installed else "CONFIGURED",
                    tools_count=0,
                    capabilities=["codex_plugin"],
                    accessible_workers=["codex-primary"],
                    auth_status="NONE",
                    can_invoke=False,
                    tools=[],
                ))
        except Exception:
            pass
        return results

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculates platform-wide MCP telemetry metrics."""
        inv = self.get_inventory()
        total_servers = len(inv)
        usable_servers = sum(1 for s in inv if s.status == "USABLE")
        connected_servers = sum(1 for s in inv if s.can_invoke)
        total_tools = sum(s.tools_count for s in inv)

        return {
            "total_servers": total_servers,
            "usable_servers": usable_servers,
            "connected_servers": connected_servers,
            "configured_servers": total_servers,
            "total_tools": total_tools,
        }

    def list_all_tools(self) -> List[Dict[str, Any]]:
        """Aggregates all discovered tools across all servers."""
        inv = self.get_inventory()
        all_tools = []
        for s in inv:
            for t in s.tools:
                all_tools.append({
                    "tool_name": t.get("name"),
                    "server_name": s.name,
                    "description": t.get("description", ""),
                    "category": t.get("category", "general"),
                    "server_status": s.status,
                    "workers": s.accessible_workers,
                })
        return all_tools
