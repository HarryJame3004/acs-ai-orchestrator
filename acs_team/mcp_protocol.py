"""Bounded MCP JSON-RPC stdio transport and sandboxed mission-scoped broker."""

from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
from queue import Empty, Queue, Full
import selectors
import tempfile
import threading
import time

from .mcp_audit import ServerPolicy, definition_hash
from .security import sandbox_argv, redact
from .supervision import ProcessSupervisor


class ProtocolError(RuntimeError):
    pass


class StdioClient:
    """Host-supplied process argv only. Use MCPBroker for untrusted real servers."""

    def __init__(
        self,
        argv: list[str],
        workspace: Path,
        env: dict[str, str] | None = None,
        timeout: float = 3,
    ):
        if not 0 < timeout <= 30:
            raise ValueError("Invalid MCP timeout")
        self.argv, self.workspace, self.env, self.timeout = (
            argv,
            workspace,
            env,
            timeout,
        )
        self.stack = ExitStack()
        self.messages: Queue = Queue(maxsize=32)
        self.failed = threading.Event()
        self.error = ""
        self.next_id = 0
        self.threads: list[threading.Thread] = []

    def __enter__(self):
        self.process = self.stack.enter_context(
            ProcessSupervisor(maximum_workers=1).start_owned(
                self.argv, self.workspace, env=self.env
            )
        )

        def stdout():
            try:
                while line := self.process.stdout.readline(65537):
                    if len(line) > 65536:
                        raise ProtocolError("oversized protocol message")
                    message = json.loads(line)
                    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                        raise ProtocolError("invalid protocol message")
                    self.messages.put_nowait(message)
            except (ValueError, Full, ProtocolError):
                self.error = "Malformed/oversized/flooded MCP response"
                self.failed.set()
            finally:
                self.failed.set()

        def stderr():
            # Drain to avoid a deadlock; retain no raw server output or secrets.
            try:
                while self.process.stderr.read(4096):
                    pass
            except (OSError, ValueError):
                pass

        for target in (stdout, stderr):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self.threads.append(thread)
        os.set_blocking(self.process.stdin.fileno(), False)
        return self

    def _write(self, message):
        data = json.dumps(message, separators=(",", ":")).encode() + b"\n"
        if len(data) > 65536:
            raise ValueError("MCP request exceeds 64 KiB")
        deadline = time.monotonic() + self.timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE)
            while data:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("MCP input timeout")
                try:
                    written = os.write(self.process.stdin.fileno(), data)
                    data = data[written:]
                except BlockingIOError:
                    continue
                except BrokenPipeError:
                    raise ProtocolError("MCP process closed input") from None

    def notification(self, method: str, params: dict):
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def call(self, method: str, params: dict) -> dict:
        self.next_id += 1
        identifier = self.next_id
        self._write(
            {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}
        )
        deadline = time.monotonic() + self.timeout
        notifications = 0
        while time.monotonic() < deadline:
            try:
                message = self.messages.get(
                    timeout=min(0.05, max(0.001, deadline - time.monotonic()))
                )
            except Empty:
                if self.failed.is_set():
                    raise ProtocolError(self.error or "MCP process closed output")
                continue
            if "id" not in message:
                notifications += 1
                if notifications > 16:
                    raise ProtocolError("MCP notification flood")
                continue  # Notifications are untrusted data, never host commands.
            if (
                message["id"] != identifier
                or "error" in message
                or not isinstance(message.get("result"), dict)
            ):
                raise ProtocolError("MCP error or unexpected response identity/schema")
            return message["result"]
        raise TimeoutError("MCP response timeout")

    def initialize(self) -> dict:
        result = self.call(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "acs-ai", "version": "2.2.0"},
            },
        )
        if result.get("protocolVersion") != "2025-03-26":
            raise ProtocolError("Unsupported MCP protocol version")
        self.notification("notifications/initialized", {})
        return result

    def __exit__(self, *args):
        self.stack.close()
        for thread in self.threads:
            thread.join(timeout=1)


class MCPBroker:
    def __init__(
        self,
        policy: ServerPolicy,
        workspace: Path,
        private_paths: tuple[Path, ...] = (),
    ):
        self.policy = ServerPolicy.model_validate(policy.model_dump())
        self.workspace, self.private_paths = workspace.resolve(), private_paths
        self.stack = ExitStack()
        self.client = None

    def __enter__(self):
        if os.environ.get("ACS_ENABLE_MCP_EXTERNAL") != "1":
            raise PermissionError("External MCP execution is disabled")
        examined = 0
        for directory, children, files in os.walk(self.workspace, followlinks=False):
            examined += len(children) + len(files)
            if examined > 5000:
                raise PermissionError(
                    "MCP workspace inventory exceeds the sanitized fixture budget"
                )
            for name in [*children, *files]:
                if name.casefold().startswith(".env") or name.casefold() in {
                    ".aws",
                    ".codex",
                    "auth.token",
                    "credentials.json",
                    "auth.json",
                    "id_rsa",
                    "id_ed25519",
                }:
                    raise PermissionError(
                        "Prepare a sanitized disposable MCP workspace without credential files"
                    )
            children[:] = [name for name in children if name != ".git"]
        home = Path(
            self.stack.enter_context(
                tempfile.TemporaryDirectory(prefix="acs-mcp-home-")
            )
        )
        argv = sandbox_argv(
            self.workspace,
            self.policy.command,
            home=home,
            network=self.policy.network,
            private_paths=self.private_paths,
            read_only_workspace=True,
        )
        environment = {
            name: os.environ[name]
            for name in self.policy.env_names
            if name in os.environ
        }
        environment.update(
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local/share"),
            }
        )
        try:
            self.client = self.stack.enter_context(
                StdioClient(argv, self.workspace, environment)
            )
            self.client.initialize()
            result = self.client.call("tools/list", {})
            if result.get("nextCursor"):
                raise ProtocolError(
                    "Paginated catalogs require explicit bounded approval"
                )
            self.tools = result.get("tools")
            if definition_hash(self.tools) != self.policy.approved_tool_hash:
                raise PermissionError(
                    "MCP tool definitions changed; operator re-approval required"
                )
            known = {tool["name"] for tool in self.tools}
            if (
                not set(self.policy.tools).issubset(known)
                or self.policy.harmless_tool not in self.policy.tools
            ):
                raise PermissionError("MCP declared tool allowlist is unavailable")
            return self
        except BaseException:
            self.stack.close()
            raise

    def call(self, tool: str, arguments: dict) -> dict:
        if tool not in self.policy.tools:
            raise PermissionError("Tool is outside the mission allowlist")
        if (
            tool != self.policy.harmless_tool
            or arguments != self.policy.harmless_arguments
        ):
            raise PermissionError(
                "This verification broker permits only the exact pre-approved harmless operation; additional actions need a separate operation approval policy"
            )
        if self.client is None:
            raise RuntimeError("MCP server has not initialized")
        # Guard common path parameters before a server sees them; sandbox is the
        # boundary for servers with different schemas or hostile descriptions.
        from .security import contained_path

        for key, value in arguments.items():
            if key in {"path", "file_path", "directory"}:
                if not isinstance(value, str):
                    raise ValueError("MCP path must be a string")
                contained_path(self.workspace, value)
        result = self.client.call("tools/call", {"name": tool, "arguments": arguments})
        if result.get("isError"):
            raise ProtocolError("MCP tool returned an error")
        return redact(result)

    def __exit__(self, *args):
        self.stack.close()
