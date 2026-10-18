# MCP verification acceptance

Status PARTIAL. CLOUD_SIMULATED tests start real subprocess fake stdio servers,
initialize/discover/call, detect changed catalog descriptions, enforce explicit
allowlists, reject malformed/oversized messages, time out and clean owned processes.
CLOUD_REAL native file tests cover permissions, traversal, symlinks, hard links,
reserved arguments and data bounds. Configured inventory entries are not operational.

External verification is opt-in, source/version/hash gated, exact harmless-operation
only, sanitized read-only workspace and bounded fresh-home stdio. No server was
installed, updated, deleted or declared authenticated. HTTP transport, arbitrary
mission operations, remote-write approval policy and real worker visibility remain
incomplete. Real servers require local checks; see MCP_INTEGRATION.md.
