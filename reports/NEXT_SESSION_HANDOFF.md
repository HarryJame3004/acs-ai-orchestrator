# Exact next-session handoff

## Current handoff — supersedes the historical instructions below

Continue PR #7 on upgrade/stage-7-verification-release and fast-forward only
upgrade/overnight-integration. Do not restart completed stages. Tested source
milestones: 35372c1 (provider contracts/real team route), bf9e542 (durable recovery,
shared limits and correction runs), 2c42da3 (daemon recovery/dependencies/retention).
Use git log/status for the subsequent explicit local-team probe and final evidence
commits. Main must not be pushed/merged. Never modify ACS Core, request credentials
or deploy. The original MASTER_SPEC.md and baselines remain unchanged.

Implemented production path: activated ProviderWorker → ProviderTeamPlanner →
TeamMissionController → concurrent TeamRunner → independent tester/reviewer sessions
→ signed task evidence/Guardian → sequential integration → final combined tests/
Guardian → review/completion exports → durable COMPLETED state. CLI and daemon
use it behind coordination flags. Imported reviews can create at most two
dependent correction missions per lineage; original requirements AND criteria
must survive. BLOCKED parents require reconciled claims and exact baseline or
accepted integration evidence. Duplicate corrections do not execute twice.

Crash tests terminate a controller between Git merge and durable integration
completion. They verify preservation, rollback of only the owned checkout,
fresh fencing and completed-output reuse; seven provider calls stay seven.
Daemon resumption requires ACS_ENABLE_TEAM_RECOVERY=1 and expired leases/dead
owner proof. Integration uses a crash-released lock without holding SQLite's
writer during tests; a keeper renews completed/integrating leases. Parent-death
guards reap provider descendants, including escaped sessions.

Shared CPU/RAM/PID cgroup contracts fail closed when enabled without exact
delegation. Storage is sampled, not a hard quota. Accepted-checkout cleanup is
opt-in, requires signed completed evidence/ancestry/clean registered worktrees,
retains branches/artifacts and refuses dirty data. Failed work remains retained.
Source flags/defaults and exact local procedures: docs/upgrade/TEAM_RUNTIME.md.
Activation lifetime defaults to one hour; explicit signed lifetime may reach
24 hours. Existing receipts are never silently replaced or renewed.

New local `acsai verify-team` requires explicit --execute-probe, three activated
real providers and a new output repository/database. It delivers a fixed baseline
behavior test and narrow two-task plan validation, runs the production controller,
requires all three actual provider identities and retains evidence. It is not run
with authenticated providers in cloud. Missing activation produces a private
failure report and nonzero exit; no new token is requested. Separate real-provider
and delegated-cgroup tests remain explicit local-only checks.

Evidence: continuation_tests.json and continuation_static.json hold latest root
counts/labels; continuation_history.json holds the latest committed-history scan.
INTEGRATED_TEAM_ACCEPTANCE.md maps the 20-step flow to actual scenario assertions,
including CLI/daemon, barrier-proven concurrency, consumed dependency handoffs,
escalation/replanning, crash recovery and a retained advisory lesson. Lessons are
explicitly human-reviewed fixtures; simulated outcomes cannot verify real lessons.
Full bridge/companion snapshots remain in their existing reports. Targeted bridge
guard-related profile: 56 passed. Hosted checks all passed at 2c42da3; refresh newer
heads. Do not mistake a prior source ZIP for the latest candidate.

Next work, without repeating the implemented source:

1. Inspect newest PR #7 checks/annotations and git status before edits. Keep exact
   counts in machine reports. Actions log host may still proxy-403; API works.
2. Finish resource coverage: hard disk quotas, bounded private scratch placement/
   accounting (provider homes and verification/MCP scratch currently need complete
   coverage), Git object/log/artifact storage, whole-service controller caps and
   measured kernel enforcement. Never label sampled storage a hard ceiling.
3. Implement reviewed baseline-test exceptions plus meaningful coverage comparison;
   current default denies baseline edits. Preserve that denial until a complete
   trusted approval path exists. Expand sensitive-area classification/escalation.
4. Implement MCP HTTP/general mission operations, per-operation remote-write
   approvals and actual provider-visible least-privilege bindings together. Current
   external broker permits only exact approved harmless probes; do not add isolated
   transport scaffolding or treat inventory as connectivity.
5. Complete remaining legacy producer schemas, measured provider quota/failover,
   optional alternative-run accounting and language/performance verification
   profiles. Template/risk/test-command propagation now exists; do not redo it.
6. Connect evidence-backed lesson production to real outcomes/imported local proof;
   retain advisory-only semantics and never promote fake mission outcomes.
7. Extend randomized/flaky campaigns and full dependency/license audit. Review
   crash boundaries beyond controller termination, e.g. host power loss and artifact
   fsync. Current evidence does not establish those guarantees.
8. Rerun affected tests/static/history, commit focused increments, update all
   requirement coverage and regenerate a source bundle only after the candidate
   is stable. Keep overall PARTIAL until every cloud-verifiable requirement passes.

Local-only blockers: actual Codex/AGY identity/auth/CLI compatibility, real sandbox
and delegated cgroup behavior, MCP authentication/tools, services/watchdog, live
backup/rollback, terminal UI and deployment. Do not ask for credentials or execute
these on the user's laptop. Provide procedures; keep local checks explicitly
LOCAL_VERIFICATION_REQUIRED. Ordinary safe development needs no stage approval.
No cloud background continuation is promised after this turn.

## Historical handoff (absent-source claims below are superseded)

## Resume state

Read AGENTS.md, docs/progress/PROGRESS.md, this file and the unchanged original
specification docs/upgrade/MASTER_SPEC.md. The user's overnight override permits
safe development across dependent stages without waiting for intermediate merges;
it does not authorize main pushes/merges, credential operations, local deployment
or bypassing approval gates. Do not restart or repeat completed stage scaffolding.

Repository: HarryJame3004/acs-ai-orchestrator. Continue
upgrade/stage-7-verification-release (PR #7, draft) and keep the fast-forward
upgrade/overnight-integration branch current. Stage PRs #1–#6 remain open and
unmerged. Main must remain eecbce4 unless the user independently changes it.
Inspect git log/status/remote heads before editing; final documentation commits
follow source checkpoints 490fbb0, e69f67e, 54e598e, 8595f48, 2892d6c, 46ff7ad and 329e402. Use git log for
exact latest evidence commit rather than treating this document's own hash as fixed.

## Saved evidence

- reports/stage_7_tests.json: 151 pass / 5 explicit local skips; CLOUD_REAL 126,
  CLOUD_SIMULATED 25. No baseline regressions.
- reports/bridge_tests.json: latest full measured bridge result; fake providers.
  Earlier 846-pass run did not reveal a fast-terminal timing race; the expanded
  suite adds a deterministic controller-policy regression. Final CI_STATUS.json
  records hosted outcomes, including any unresolved follow-up.
- reports/companion_tests.json: 138 pass, compilation/build pass. Companion CI
  passed. reports/COMPANION_DEPENDENCY_AUDIT.json: zero npm advisories at audit.
- reports/golden_fake_final.json: full 12/12 fake-worker harness, actual Git,
  SQLite, pytest and Guardian; runtime is not a provider/laptop performance score.
- reports/stage_7_static.json: zero scoped Ruff/mypy findings, 15 existing known
  candidate fingerprints, zero new. Original baselines unchanged.
- reports/stage_7_history.json: final offline history scan, canary required.
- reports/local_bundle.json: exact committed source ZIP and integrity metadata.
- reports/REQUIREMENTS.json: section coverage; reports/FINAL_ACCEPTANCE_REPORT.md:
  full stage status, security/operational gaps and approval boundaries.

Reproduce root checks with bash scripts/cloud_setup.sh then the commands in
TESTING.md. Bridge pytest must run with working directory agpair. CI uses fake
providers, NO_COLOR=1 and COLUMNS=1000 for stable error text. Individual Codex
fixtures configure their own harmless executables; no authenticated CLI is needed.
Do not set a real provider availability flag just to make tests pass.

## First unresolved work, in dependency order

1. Inspect latest PR #7 checks and CI_STATUS.json. Fix any actual hosted regression
   before expanding features; annotations are available even when log downloads
   are proxy-blocked. Preserve failure evidence and never weaken assertions.
2. Define a legitimate, explicit local provider verification/activation contract
   with independent Codex/AGY A/AGY B profiles, exact toolchain/auth bindings and
   fail-closed supervisor/bwrap behavior. Merely finding a binary/auth filename
   is insufficient. Never ask for or import real tokens into cloud.
3. Implement production tester/reviewer adapters with independent session identity,
   bounded strict outputs and scopes. Keep the functioning host callback API and
   all cloud fake-worker tests. Simulations cannot activate real providers.
4. Connect a validated team plan to natural-language/queued mission dispatch behind
   explicit opt-in. Persist mission/task/evidence/dashboard/review state coherently;
   preserve legacy dry-run/CLI compatibility. Existing -m path is single-task.
5. Implement complete interrupted integration recovery: reconcile actual owned Git
   worktree/HEAD, fenced SQLite claims and evidence after every crash boundary;
   wire owned process identity into recovery. Do not steal ACTIVE jobs or delete
   retained failed worktrees as a shortcut.
6. Finish aggregate controller/MCP/worker RAM/CPU/disk controls and retention with
   owned processes and fail-closed cleanup. Real cgroup/sandbox proof stays local.
7. Complete review-driven validated replan/execution, reviewed baseline-test
   exceptions/coverage comparison, sensitive-risk classification and accurate
   template/profile/escalation/metrics telemetry. No imported text grants approval.
8. Finish remaining producer schemas/failover scheduling and real optional
   multi-solution quota accounting. MCP HTTP/general mission operations and
   per-operation remote-write approval remain separate bounded work.
9. Demonstrate all Master §14 steps in one actual controller flow using fake workers
   on a temp repo, including context, handoff, verified learning policy, persisted
   mission/dashboard and review. Current component/12-case tests are partial.
10. Rerun appropriate tests/static/history, update per-section evidence and publish
    focused fast-forward commits to stage/integration branches. Keep PARTIAL until
    every cloud-feasible acceptance item is implemented and measured.

Local deployment, authenticated provider missions, actual MCP/service/watchdog/
sandbox/key-visibility/live backup tests and activation remain
LOCAL_VERIFICATION_REQUIRED. LOCAL_DEPLOYMENT_GUIDE.md supplies isolated preflight,
backup/scratch restore/migration/staging/import/rollback instructions. HIGH source
gaps block activation before these local checks can close acceptance. A local
report never automatically enables flags.

## Exact resume instruction

> Continue the existing ACS AI upgrade on upgrade/stage-7-verification-release.
> Read AGENTS.md, docs/progress/PROGRESS.md, reports/NEXT_SESSION_HANDOFF.md,
> reports/FINAL_ACCEPTANCE_REPORT.md and the original docs/upgrade/MASTER_SPEC.md.
> Check all PR statuses and the latest CI evidence first. Preserve all completed
> stages and baselines; do not restart, merge, push main, access ACS Core, request
> credentials or deploy. Implement the numbered source backlog in dependency
> order, beginning with unresolved CI and verified provider/independent role
> contracts, then actual natural-language TeamRunner dispatch and crash recovery.
> Test real controller logic with fake workers, clearly label local-only checks,
> commit/push focused increments to the stage and cumulative integration branch,
> and update requirement coverage and this handoff. Never claim PARTIAL work ready
> for deployment. Continue safe development without ordinary stage confirmations.

This is a saved continuation checkpoint. A finished chat turn does not leave an
agent running in the background; the next task must explicitly resume the work.
