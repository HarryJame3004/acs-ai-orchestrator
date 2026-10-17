# Upgrade progress

## Current checkpoint — V2.3 PARTIAL

Stage 1 PR #2 is open. V2.3 production hardening passes 87 tests, with 4 explicit
local-only skips; no baseline regressions or new static findings. See
reports/V2_3_REPORT.md for implemented controls and unresolved acceptance gaps.
Continue V2.4 on a dependent branch. Earlier entries below are historical.

## Overnight execution — Stage 1 checkpoint

The final user directive authorizes all safe stages without merge waits.
Stage 0 PR #1 is OPEN and its latest hosted CI passed. Stage 1 recovery tooling
is implemented and validated: 59 passed / 4 local-only skips, no failures;
CLOUD_REAL 54 passed, CLOUD_SIMULATED 5 passed. See STAGE_1_REPORT.md and
reports/REQUIREMENTS.json. No local deployment occurred. Continue to V2.3 on a
dependent branch; maintain upgrade/overnight-integration by fast-forward only.
Original historical checkpoints follow.

## Latest continuation checkpoint

Latest network diagnosis: **CLOUD_REAL PASS**. Unauthenticated api.github.com
returns 200; curl CONNECT=200, API=200, TLS verification=0. Existing-auth REST
repository and GraphQL PR queries both succeed. PR #1 is OPEN, not merged.
The former tunnel 403 is resolved in this active task; no new token, restart or
republication is needed for current GitHub API access. The editable draft still
reports restricted + api.github.com whereas the user reports All; draft metadata
is not live policy evidence. No policy was overwritten. See
`reports/GITHUB_API_DIAGNOSTIC.md`. Older network-blocker entries below are
historical. Stage 1 can use a dependent branch under existing authorization.

The user requested cross-stage autonomous continuation on dependent branches,
then asked for a full prerequisite review before starting the unattended run.
That authorization supersedes the older merge-wait instructions below. No
Stage 0 work was repeated. The original master specification is now preserved
verbatim at `docs/upgrade/MASTER_SPEC.md`.

- Git ref discovery confirms PR #1 points to the previously published Stage 0
  head, while main remains the initial release. API review/CI/merge metadata
  remains unavailable because the HTTPS proxy tunnel to api.github.com is
  blocked (403); Git read and stage-branch push work.
- `1cb2ad7`: added ACS_HOME/XDG runtime selection, an explicit credentials-file
  override for isolated operation, and repaired the console-script main target.
- `fd23285`: fixed the original CLI test in a separate test-only commit. All
  assertions remain intact; it now uses sys.executable, temp state/backup paths,
  a nonexistent fixture credentials file and port 0 instead of a workstation.
- The static regression comparator now ignores line movement while preserving
  diagnostic multiplicity and secret fingerprints; three new tests cover it.
  This does not suppress new diagnostics or rewrite the original baselines.
  The CI comparison now also requires pytest exit 0; historical failure
  allowances cannot mask a recurrence of the repaired CLI failure.
  Commits: `c11d1d3` (static comparison), `c0395d1` (zero-failure gate).
- Latest suite: CLOUD_REAL **43 passed**, CLOUD_SIMULATED **4 passed**,
  LOCAL_VERIFICATION_REQUIRED **4 skipped with explicit reasons**. Total
  **47 passed, 4 skipped, 0 failed**, pytest exit 0. Isolated installed acsai
  --help also passes. Static gate has zero new findings; legacy debt remains
  99 Ruff, 13 mypy errors and 15 disclosed metadata/test candidates.
  Machine-readable results: `reports/continuation_tests.json` and
  `reports/continuation_static.json`. The 47/4 result repeated successfully;
  the final run took 7.01 seconds and the strict comparison exited 0.
- Saved a cloud environment draft adding only api.github.com, refreshed setup
  and startup instructions, and three nonsecret runtime path variables. This is
  a saved draft only, not an applied runtime policy or published snapshot. The
  user must review/save settings and publish before API access can be retested.
  No credentials were requested or printed.

Read `OVERNIGHT_PREFLIGHT.md` for the exact user actions and stage-by-stage
cloud/local dependency matrix. The latest user message requests that preparation
assessment before they signal readiness; preserve this checkpoint and resume
STAGE-1 after that signal without waiting for a Stage 0 merge. Stage 1 and
V2.3–V2.6/STAGE-7 remain **NOT_TESTED / not implemented**, apart from the small
portable config/entry-point prerequisite above. Do not label them complete.

The earlier Stage 0 report below is historical and its counts remain unchanged.

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
