"""ACS AI V2 MCP Tool Registry & Permission-Gated Execution Engine.
Enforces:
1. Strict separation between READ_ONLY, MUTATING, and ADMIN tools.
2. Worktree path boundary enforcement (blocking traversal outside worktree).
3. Role-based execution policies (Planner/Reviewer read-only, Worker mutating strictly within worktree).
4. Fail-closed on unknown tools or unauthorized operations.
"""

from __future__ import annotations

import enum
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("acs_ai.mcp_registry")


class ToolCategory(str, enum.Enum):
    READ_ONLY = "read_only"
    MUTATING = "mutating"
    ANALYSIS = "analysis"
    ADMIN = "admin"


class MCPPermissionError(Exception):
    """Raised when an MCP tool invocation violates security or permission policies."""
    pass


class PathEscapeError(MCPPermissionError):
    """Raised when an MCP tool attempts to access a path outside the designated worktree."""
    pass


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: ToolCategory
    required_permissions: Set[str] = field(default_factory=set)
    parameters_schema: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable[..., Any]] = None


class MCPRegistry:
    """Central registry and permission gatekeeper for MCP tools."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register_tool(self, tool: ToolDefinition) -> None:
        """Registers a new tool in the registry."""
        self._tools[tool.name] = tool
        logger.debug(f"Registered MCP tool: {tool.name} [{tool.category.value}]")

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self, category: Optional[ToolCategory] = None) -> List[Dict[str, Any]]:
        results = []
        for tool in self._tools.values():
            if category is None or tool.category == category:
                results.append({
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category.value,
                    "required_permissions": list(tool.required_permissions),
                    "available": tool.handler is not None,
                })
        return results

    @staticmethod
    def validate_path_boundary(target_path: str, worktree_dir: str) -> str:
        """Validates that target_path is strictly contained within worktree_dir.
        
        Prevents directory traversal, symlink escapes, and absolute path escaping.
        Returns the resolved canonical path.
        """
        canonical_worktree = os.path.realpath(worktree_dir)
        
        # If relative path, join with worktree_dir
        if not os.path.isabs(target_path):
            full_path = os.path.join(canonical_worktree, target_path)
        else:
            full_path = target_path

        canonical_target = os.path.realpath(full_path)
        from .security import contained_path
        try:
            relative = str(Path(canonical_target).relative_to(canonical_worktree))
            contained_path(Path(canonical_worktree), relative)
        except (ValueError, PermissionError) as error:
            raise PathEscapeError("MCP path violates workspace policy") from error
        
        # Verify commonpath
        try:
            common = os.path.commonpath([canonical_worktree, canonical_target])
            if common != canonical_worktree:
                raise PathEscapeError(
                    f"Path escape detected: '{target_path}' resolves outside worktree '{canonical_worktree}'"
                )
        except ValueError as e:
            # Different drive letters or invalid paths
            raise PathEscapeError(f"Invalid path comparison: {e}")

        return canonical_target

    def authorize(
        self,
        tool_name: str,
        caller_role: str,
        is_human_approved: bool = False,
    ) -> ToolDefinition:
        """Enforces role-based authorization for tool access.
        
        Roles:
        - 'planner': READ_ONLY and ANALYSIS only.
        - 'reviewer': READ_ONLY and ANALYSIS only.
        - 'worker': READ_ONLY, ANALYSIS, and MUTATING (subject to path boundaries).
        - 'admin': ALL categories if human approved.
        """
        tool = self.get_tool(tool_name)
        if caller_role not in {"planner", "reviewer", "worker", "admin"}:
            raise MCPPermissionError("Unknown role is denied")
        if not tool:
            raise MCPPermissionError(f"Unknown MCP tool: '{tool_name}'")

        if tool.category == ToolCategory.ADMIN and not is_human_approved:
            raise MCPPermissionError(f"Admin tool '{tool_name}' requires explicit human approval.")

        if caller_role in ("planner", "reviewer"):
            if tool.category not in (ToolCategory.READ_ONLY, ToolCategory.ANALYSIS):
                raise MCPPermissionError(
                    f"Role '{caller_role}' is restricted to READ_ONLY or ANALYSIS tools. Attempted: '{tool_name}' ({tool.category.value})"
                )

        if caller_role == "worker":
            if tool.category == ToolCategory.ADMIN and not is_human_approved:
                raise MCPPermissionError(f"Workers cannot execute ADMIN tools without human approval.")

        return tool

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        caller_role: str,
        worktree_dir: str,
        is_human_approved: bool = False,
        allowed_tools: Optional[Set[str]] = None,
        permissions: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Validates permissions, sanitizes path arguments, and executes the requested tool."""
        tool = self.authorize(tool_name, caller_role, is_human_approved=is_human_approved)
        if allowed_tools is not None and tool_name not in allowed_tools:
            raise MCPPermissionError("Tool is not in the mission allowlist")
        import os
        strict = os.environ.get("ACS_ENABLE_MCP_SCOPES") == "1"
        if strict and allowed_tools is None:
            raise MCPPermissionError("An explicit mission tool allowlist is required")
        granted = permissions if permissions is not None else (set() if strict else {"filesystem:read", "filesystem:write"} if caller_role == "worker" else {"filesystem:read"})
        if not tool.required_permissions.issubset(granted):
            raise MCPPermissionError("Required tool permissions are missing")

        # Check all common path argument names to enforce worktree boundaries
        sanitized_args = dict(arguments)
        path_keys = ["path", "file_path", "target_path", "directory", "dest"]
        for key in path_keys:
            if key in sanitized_args and isinstance(sanitized_args[key], str):
                sanitized_args[key] = self.validate_path_boundary(sanitized_args[key], worktree_dir)

        if not tool.handler:
            return {
                "success": False,
                "tool": tool_name,
                "unavailable": True,
                "message": f"Tool '{tool_name}' has no installed handler.",
                "sanitized_arguments": sanitized_args,
            }

        try:
            result = tool.handler(**sanitized_args)
            return {"success": True, "tool": tool_name, "result": result}
        except Exception as e:
            logger.error(f"Error executing MCP tool '{tool_name}': {e}", exc_info=True)
            return {"success": False, "tool": tool_name, "error": str(e)}

    def _register_default_tools(self) -> None:
        """Registers standard MCP tools with safe boundary-enforced defaults."""
        def _read_file_handler(file_path: str, **kwargs):
            p = Path(file_path)
            if not p.is_file():
                raise FileNotFoundError(f"File not found: {file_path}")
            return p.read_text(errors="replace")[:100000]

        def _write_file_handler(file_path: str, content: str, **kwargs):
            p = Path(file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return {"bytes_written": len(content), "path": file_path}

        def _list_dir_handler(directory: str = ".", **kwargs):
            p = Path(directory)
            if not p.is_dir():
                raise NotADirectoryError(f"Directory not found: {directory}")
            return [f.name for f in p.iterdir()][:200]

        self.register_tool(ToolDefinition(
            name="read_file",
            description="Reads file contents from within the worktree.",
            category=ToolCategory.READ_ONLY,
            required_permissions={"filesystem:read"},
            parameters_schema={"file_path": "string"},
            handler=_read_file_handler,
        ))

        self.register_tool(ToolDefinition(
            name="write_file",
            description="Writes file contents strictly within the worktree.",
            category=ToolCategory.MUTATING,
            required_permissions={"filesystem:write"},
            parameters_schema={"file_path": "string", "content": "string"},
            handler=_write_file_handler,
        ))

        self.register_tool(ToolDefinition(
            name="list_directory",
            description="Lists entries inside a worktree directory.",
            category=ToolCategory.READ_ONLY,
            required_permissions={"filesystem:read"},
            parameters_schema={"directory": "string"},
            handler=_list_dir_handler,
        ))

        self.register_tool(ToolDefinition(
            name="inspect_binary",
            description="Performs static inspection on a binary file using REA or fallback tools.",
            category=ToolCategory.ANALYSIS,
            parameters_schema={"file_path": "string"},
        ))

        self.register_tool(ToolDefinition(
            name="force_reset_state",
            description="Forces database state reset (Admin only).",
            category=ToolCategory.ADMIN,
            parameters_schema={"confirm": "boolean"},
        ))
