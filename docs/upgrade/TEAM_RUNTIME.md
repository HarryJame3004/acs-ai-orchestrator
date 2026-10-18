# Provider-backed team runtime

This candidate remains PARTIAL. These are source interfaces for isolated local
evaluation; no local installation, credential operation or delegation has been
performed by the cloud task. Real provider, sandbox and kernel quota checks are
LOCAL_VERIFICATION_REQUIRED. Cloud protocol fixtures cannot activate providers.

## Activation and execution

An operator-provided catalog (`ACS_PROVIDER_CONTRACT_FILE`) contains a bounded
`providers` list. Each entry declares `worker_id` (`codex-primary`, `agy-google-a`
or `agy-google-b`), absolute `executable`, its `executable_sha256`, a dedicated
0700 `auth_home`, relative readonly `auth_paths`, and narrow readonly
`toolchain_roots`. Existing authenticated profiles are prerequisites. Do not put
credentials in the catalog or share auth roots. Auth source trees cannot contain
symlinks. Network defaults off; enable `network` explicitly for provider access.
Timeout, per-process address-space and CPU-time budgets are bounded by schema.

`acsai provider-activate WORKER --contracts CATALOG --execute-probe` requests a
real bubblewrap boundary test and a fresh provider challenge. It saves a private,
signed receipt bound to the exact contract. The default lifetime is one hour;
`--valid-for-seconds` explicitly permits 900–86400 seconds for an overnight run.
The lifetime is signed and every invocation still rechecks executable/auth binds.
Existing receipts are never
silently overwritten. Renewal currently requires explicit operator review of the
old receipt; automatic credential rotation is unsupported. Binary presence and
simulated executors never establish activation. Authenticated identity, installed
CLI syntax/version and network availability still need local verification.

Opt-ins: `ACS_ENABLE_PROVIDER_CONTRACTS=1`, `ACS_ENABLE_COORDINATION=1`, and
`ACS_ENABLE_SUPERVISION=1`. Natural-language foreground missions and the daemon
queue use the same TeamMissionController. Tester sessions see specifications
before implementation. Reviewer sessions get a host-bound commit/diff and a
readonly tree. Host session IDs are distinct from implementer IDs. Every task
and the final combined tree pass independent tests, scope checks and Guardian.
Final evidence covers all declared commands and acceptance tests. Export occurs
before the mission becomes COMPLETED, so failed review export is recoverable.

## Recovery

`acsai mission resume MISSION` uses the durable validated plan when coordination
is enabled. A kernel mission lock, controller boot/PID/birth identity and fenced
claims prevent stealing active work. Wait for old leases to expire. Running
claims retain their old snapshot/worktrees before reassignment; verified completed
worker output is reused under a fresh token. Integration intents are committed
before Git changes. Unexpected or dirty Git history fails closed. An exact
interrupted merge is preserved under an `acsai/recovery/` branch before rollback
of only the owned integration checkout. Main and the user's checkout stay intact.
SQLite is writable for heartbeats while integration tests run. Owned launchers
receive a parent-death signal and reap descendant processes after a controller
crash. Never kill an arbitrary PID or delete retained worktrees to bypass recovery.

With `ACS_ENABLE_TEAM_RECOVERY=1`, daemon startup recognizes dead controller
owners with durable validated plans, waits for expired leases and resumes through
the same reconciler. It never steals live controller ownership. The native
protocol crash fixture verifies that completed provider calls are not repeated.

## Shared limits

`ACS_ENABLE_AGGREGATE_LIMITS=1` requires an operator-delegated cgroup v2 path in
`ACS_AGGREGATE_CGROUP` and a JSON list of narrow owned storage paths in
`ACS_AGGREGATE_STORAGE_ROOTS`, plus an existing owned mode-0700 scratch directory
in `ACS_AGGREGATE_SCRATCH_ROOT` beneath one of those roots. Provider sessions,
activation probes, independent planner/tester workspaces, legacy supervised worker
homes, migration/benchmark/local-verification fixtures, verification homes and MCP
homes use that scratch directory. Execution refuses a workspace outside the
accounted roots, including the shared Git metadata/object directory of a linked
worktree (also when executing from a checkout subdirectory). Symlinked Git
directories are refused. This task does not create or apply systemd/cgroup
configuration. The cgroup must be exclusively owned, writable for worker
attachment, and configured with exact values:

| Environment setting | Default | Required kernel value |
|---|---|---|
| ACS_AGGREGATE_MEMORY_MB | 8192 | memory.max = MB × 1048576 |
| ACS_AGGREGATE_CPU_PERCENT | 200 | cpu.max = percent × 1000, period 100000 |
| ACS_AGGREGATE_PIDS | 256 | pids.max = setting |
| (fixed) | 0 | memory.swap.max = 0 |
| (fixed) | 1 | memory.oom.group = 1 |

Every supervised worker, verification and MCP launcher joins the same cgroup
before forking untrusted code. Missing delegation/mismatched limits deny startup;
there is no unsupervised fallback. The controller itself remains outside this
worker cgroup so it can record failures and clean up after OOM. A whole-service
systemd cap for controller overhead remains a separate local requirement.

`ACS_AGGREGATE_STORAGE_MB` defaults to 8192. Metadata accounting does not follow
symlinks, counts hardlinks once and bounds traversal. Running supervisors monitor
storage and stop their owned process tree on excess. This is sampled enforcement,
with possible overshoot between scans. Include worktrees, artifacts/logs and Git
object storage in the configured roots. It is **not a hard filesystem quota**;
project/filesystem quotas and scratch tmpfs accounting still need local setup.
`ACS_ENABLE_ACCEPTED_WORKTREE_CLEANUP=1` enables cleanup after verified completion:
clean registered worker and integration checkouts are removed only after branch,
HEAD, ancestry, owned-process and signed-evidence checks. Branches and evidence
remain; dirty and failed work is retained. No force removal or unrelated metadata
pruning occurs. Reserve disk space before starting missions.

## Imported-review corrections

`acsai apply MISSION --file REVIEW --execute` additionally requires
`ACS_ENABLE_REVIEW_WORKFLOW=1` and `ACS_ENABLE_REVIEW_EXECUTION=1`.
Only accepted HIGH/BLOCKER findings referencing a known original requirement,
task or acceptance criterion become mandatory correction work. The parent must
be COMPLETED with valid evidence or BLOCKED with reconciled ownership and an
exact original baseline/accepted integration head. Active interrupted claims must
be recovered first. A fresh strict plan must retain original requirements and
all original acceptance criteria, and include every mandatory finding as an
acceptance criterion. Corrections run from the parent's exact commit on a new
mission branch through the same tests/review/Guardian gates. Duplicate execution
reuses the saved child; two correction runs per lineage are allowed, then escalation
is required. Suggested actions are untrusted text and cannot grant permissions.
Baseline test edits still require separate reviewed exceptions and are denied.

Natural-language/queued execution now propagates the chosen template and risk
profile, records its criteria/roles, keeps a risk floor and runs an explicit
allowlisted `--test-cmd` in addition to plan tests. Templates remain conservative
pytest profiles; specialized C/C++/web/performance profiles are incomplete.
The completion artifact records VERIFIED, its exact SHA/evidence and verification
label; durable mission state determines whether finalization reached COMPLETED.
Verified lesson context is advisory. Fake outcomes never promote candidate lessons.

## Explicit authenticated fixture evaluation

After the operator completes real activation for all three profiles,
`acsai verify-team --output NEW_PRIVATE_DIRECTORY --report NEW_REPORT.json --execute-probe`
creates a new retained fixture repository/database, never targets the user's
checkout, and consumes provider quota. Codex plans and supplies independent
tester/reviewer sessions; AGY A and B implement separate modules. A fixed
baseline behavior test is committed before execution. Plans must contain exactly
two independent module scopes with the expected isolated implementers. Actual
tests, Guardian, signed evidence, all three observed identities and unchanged
fixture main are required. The output is a LocalReport with
LOCAL_VERIFICATION_REQUIRED labels; failures produce a nonzero exit and private
failure report. Artifacts remain for inspection. No automatic activation,
credential prompt, live DB operation or deployment is performed.

This command is delivered but was not executed with real providers in the cloud.
The cloud tests verify refusal before provider activation and an honest failure
report. The separate local-only test additionally requires
ACS_RUN_LOCAL_TEAM_PROBE=1. The kernel attachment test requires a dedicated empty
delegated cgroup and ACS_RUN_LOCAL_AGGREGATE_PROBE=1. Neither is silently enabled
by verify-local. The older read-only verifier continues to list pending checks.
