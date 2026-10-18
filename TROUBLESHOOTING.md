# Troubleshooting the candidate

- Worker UNAVAILABLE means authentication/usability is unverified. Installed binary,
  successful --help or a configured profile is insufficient. Real activation and
  independent provider role adapters remain source blockers; do not set internal
  is_verified fields or add bypass flags to work around them.
- `setting up uid map: Read-only file system` or namespace denial means the host
  cannot run the required bwrap boundary. Cloud probes report SKIPPED/local pending;
  verify namespaces on the laptop. Do not disable sandboxing.
- Expired task claims remain locked until trusted death and worktree checks pass.
  Never delete the DB/worktree or manually zero a token to force progress. Restarted
  COMPLETED/Git integration reconciliation is not fully automated.
- Daemon execution is off by default. With ACS_ENABLE_DAEMON_EXECUTION=1 it needs
  verified supervised workers. An ACTIVE durable dispatch is not stolen after a
  restart. Inspect retained state and prepare a recovery plan.
- Terminal/active `mission resume` is refused to avoid duplicate execution. Retained
  worktrees/checkpoints need review; blindly rerunning the same mission is unsafe.
- Database restore/staging/report destinations must be new. Apply migrations only
  after stopped writers, backup and exact resolved target confirmation.
- Changed MCP definitions require operator re-approval. HTTP transport, arbitrary
  external mission actions and remote-write approvals are not implemented by the
  stdio verification broker.
- GitHub API access succeeded with existing authentication in this session. Actions
  log-download hosts separately returned proxy 403; safe check annotations identify
  failures without log downloads. Do not rotate/request a token for that tunnel
  problem. See reports/GITHUB_API_DIAGNOSTIC.md.

An older gh build may fail `gh pr edit` with a deprecated `projectCards` GraphQL
query. That is a client/query compatibility error, not failed authentication.
Updating PR title/body through the existing authenticated REST pulls endpoint
with a structured JSON input file works; no token replacement is needed.
