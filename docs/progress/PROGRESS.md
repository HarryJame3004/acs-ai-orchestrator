# Upgrade progress

Current stage: **STAGE-0 — PARTIAL**. STAGE-1 and V2.3–V2.6/STAGE-7 are NOT_TESTED
and have not started. Work is limited to audit, baseline, agent guidance and
cloud/CI scaffolding. No runtime feature, schema or existing test was changed.

Branch: `upgrade/stage-0-audit`, targeting `main`.
Implementation commit: `78bc57e6b05c93d750145decd9943255bfe42744`.
This handoff is committed separately; use `git log` for its containing commit.
Initial baseline/origin main: `eecbce4a8a834d3cd6ac835f587f02bafa88bb08`.

## Completed work

- Inspected CLI/daemon/API/schema/state machine/planning/worker adapters,
  worktrees/scope/integration, Guardian/HMAC/approvals, memory, MCP, TUI,
  deployment scripts and existing reports. Recorded discrepancies with file:line
  evidence in `reports/PHASE_0_BASELINE_AUDIT.md`.
- Captured all 42 original assertions unchanged in `reports/baseline_tests.json`,
  with dependencies, Python/pytest versions, duration, warnings and labels.
- Added AGENTS.md, pinned cloud setup, read-only SHA-pinned CI skeleton,
  isolated test runner and six regression-comparison checks. The comparison
  retains the actual failing pytest status rather than claiming all tests pass.
- Added scoped lint/type and offline secret-candidate checks with disclosed
  legacy debt; scanned the initial source and sole original history commit.
  No real credentials were inspected, validated, rotated or revoked.
- Corrected README maturity/readiness/test claims. Setup rerun and pip check
  succeeded. No production dependency declaration or existing lockfile changed.

## Exact verification outcomes

| Scope | Label | Passed | Failed | Skipped | Local status |
|---|---|---:|---:|---:|---|
| Original 42 tests | CLOUD_REAL | 33 | 1 | 0 | Not applicable |
| Original 42 tests | CLOUD_SIMULATED | 4 | 0 | 0 | Not applicable |
| Original 42 tests | LOCAL_VERIFICATION_REQUIRED | 0 | 4 cloud diagnostic attempts | 0 | NOT_TESTED |
| Current 48 tests | CLOUD_REAL | 39 | 1 | 0 | Not applicable |
| Current 48 tests | CLOUD_SIMULATED | 4 | 0 | 0 | Not applicable |
| Current 48 tests | LOCAL_VERIFICATION_REQUIRED | 0 | 0 | 4 explicit reasons | NOT_TESTED |

The current underlying pytest exit is **1**; regression comparison has no new
failures and exits **0**. The original suite took 5.22s pytest time / 5.386s
wrapper time; the recorded current suite took 5.28s pytest time. Machine-readable
current results: `reports/stage_0_tests.json`.
The same profile was repeated after implementation: 43 passed / 1 failed /
4 skipped in 4.52s, with the same labels and zero regressions. No retry was used
to turn a failure into a pass.

Other CLOUD_REAL checks: new scripts clean under Ruff and mypy; setup rerun,
dependency consistency, shell syntax and workflow YAML/permissions passed.
Legacy analysis remains 99 Ruff findings and 13 mypy errors in 7 files.
The initial offline source/history scan found 13 candidates and none in
config.py; current source plus audit metadata has 15 candidates (two added
audit commit identifiers). Locations/fingerprints are recorded without values.
Full history/pre-commit/vulnerability enforcement is V2.3 work. Hosted CI is
NOT_TESTED until a real Actions run occurs. Random-order testing was not run
because no random-order plugin is installed.

## Remaining issues and external blockers

- **HIGH (V2.3/V2.4):** Guardian is evaluated after merge; approval status is not
  bound at the Guardian call site to the entire requested operation; inherited
  worker environments, partial redaction, deletion containment and reported
  readiness need hardening. See the audit for evidence, not operational claims.
- **MEDIUM (V2.3):** broken installed CLI entry point, workstation-specific CLI
  test interpreter, import-time runtime writes, no ACS_HOME/XDG support,
  cancellation/queue/supervision gaps. Existing tests remain unchanged;
  incorrect tests must be fixed in a separate justified commit.
- **LOCAL_VERIFICATION_REQUIRED / NOT_TESTED:** real workers/auth/HOME separation,
  MCP probes/counts, sandbox/namespace boundaries, evidence-key invisibility,
  systemd/watchdog, operational install drift, real backups and interactive UI.
  No live user system or ACS Core was inspected or modified.
- **Stage scope:** scenario FakeWorkers and validated worker contracts belong
  to V2.4; backup/migration/upgrade tooling to STAGE-1; portable config and
  controlled local tests to V2.3; full MCP/local verification CLI to STAGE-7.
  They are deferred explicitly, not delivered as audit-stage features.
- Native Git read/push works. Implementation commit was published only to the
  stage branch. GitHub REST metadata access returned `Forbidden`; the separate
  `gh pr create` outcome is recorded below. Never request real credentials here.

## Publication

Stage branch push succeeded; no push to main, merge, tag or deployment occurred.
PR creation is **BLOCKED**: `gh pr create` returned
`Post https://api.github.com/graphql: Forbidden`. The read-only REST check was
also forbidden. No callable GitHub PR connector is available. This is an API
access blocker; working native Git authentication does not establish API access.
No token was requested or extracted.

Git returned this URL for the user to create the stage PR:
https://github.com/HarryJame3004/acs-ai-orchestrator/pull/new/upgrade/stage-0-audit

Target main; title: `STAGE-0: audit ACS AI and establish cloud regression baseline`.
The complete reviewable PR body is `reports/PR_STAGE_0.md`. The user can open
the PR using that body; hosted CI remains unrun until PR creation. This task
does not claim a PR exists.

## Next task

First have the user review and merge the STAGE-0 PR. Do not merge it yourself
or start a dependent stage before that merge.

After merge, start a new task with this exact instruction:

> Read AGENTS.md and docs/progress/PROGRESS.md, inspect current git history and
> rerun the stored baseline comparison. Execute STAGE-1: sections 3, 3.1 and
> the migration-runner parts of 4.9 from the master prompt. Implement consistent
> SQLite backup/verify/restore into an explicit scratch target, transactional
> versioned migration and staged upgrade/dry-run tooling. Use disposable temp
> databases/repositories and simulated service control; preserve mission history
> and exclude credentials by default. Do not deploy, access live state, modify
> ACS Core or fix unrelated runtime features. Work on upgrade/stage-1-backup-upgrade,
> update this file with labeled results and commit hashes, and open one PR to
> main. Real backup/deployment verification remains LOCAL_VERIFICATION_REQUIRED.
