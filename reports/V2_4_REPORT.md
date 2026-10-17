# V2.4 checkpoint

Status: PARTIAL. Implemented production API and CLI plan validation/state views;
not yet the default natural-language/daemon execution path. See
MULTI_AGENT_DESIGN.md for exact interfaces and acceptance gaps.

Cloud suite: 110 passed, 4 local skips, exit 0, no regressions. CLOUD_REAL 95;
CLOUD_SIMULATED 15. Real Git/SQLite under simulated provider scenarios; no actual
Codex/AGY/MCP invocation. Cases include 8-way claim race, WAL/reloaded store,
lease expiration/death/worktree/fencing checks, duplicate completions, contract
ack/dependency gating, append-only/redacted/rate-limited messages, malformed
plans, bounded model schema repair, no-write plan validation, concurrent workers
synchronized by barrier, independent tests/review, ownership veto, worker death,
review rejection and post-merge failure rollback to the prior owned commit.

Pinned new dependency: Pydantic 2.12.3, pydantic-core 2.41.4, annotated-types
0.8.0, typing-inspection 0.4.4; pip check passes. Structured schemas reject
unknown fields, unsupported versions, duplicate JSON keys and oversized payloads.
Static comparison has zero new findings (95/12 legacy Ruff/mypy, 15 candidates).

Outstanding: provider tester/reviewer adapters and dynamic role selection,
controller/daemon dispatch integration, automatic restart reconciliation of Git
and SQLite, versioned migration registration, baseline-test exception approvals
and coverage comparison, supervisor process-identity recovery wiring, real
three-provider E2E and local verification harness. These are not PASS.
