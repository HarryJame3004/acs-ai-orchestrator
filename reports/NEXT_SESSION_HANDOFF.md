# Exact next-session handoff

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
