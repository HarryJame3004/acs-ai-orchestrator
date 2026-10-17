# ACS AI upgrade acceptance checkpoint

Overall **PARTIAL**. Live activation/release **BLOCKED** on the HIGH source gaps
below. This report records implemented, verified increments; it does not certify
the complete V2.3–V2.6 system. Package version stays 2.2.0. No live system was
inspected or modified; ACS Core was not accessed. No merge, main push, tag,
credential rotation, local service operation or laptop deployment occurred.

## A. Executive summary

Production changes span backup/recovery, Guardian, process ownership, isolated
verification, SQLite coordination, independent-role host APIs, advisory learning,
context/metrics, review workflow, MCP auditing/stdio probes and local inspection.
They extend the existing Python application and agpair bridge. Root CLI flags
and historical baseline evidence are retained. Actual provider activation and the
natural-language-to-TeamRunner path are incomplete: do not deploy this candidate
as a working autonomous three-provider system.

The original Stage 0 failure was a CLI test using a workstation-specific Python
path, alongside the broken console entry point. Source repair is 1cb2ad7; the
separately justified test portability correction is fd23285. Original assertions
and baseline remain. PR #1 hosted CI subsequently passed. A later V2.3 hosted
failure came from assuming machine uptime exceeded one hour: cebfd08 makes a
first periodic backup immediately due and tests a fresh VM uptime of 10 seconds.
Neither fix changes assertions merely to accept broken behavior.

## B. Stage and version status

| Stage | Status | Implemented cloud evidence | Outstanding acceptance |
|---|---|---|---|
| Stage 0 | CLOUD_PASS_LOCAL_PENDING | Audit, reproducible baseline, CLI repair, PR #1 CI | Actual installation/worker/MCP inventory |
| Stage 1 | CLOUD_PASS_LOCAL_PENDING | Consistent backup/verify, new-only scratch restore, transactional copy migration, staged candidate and rollback fixtures | Live snapshot/history, service health and local promotion |
| V2.3 | PARTIAL | Guardian before merge, bound approvals/evidence, protected paths, private files, redaction, bounded process supervision, stop/watchdog/backup primitives | Provider activation, real sandbox/auth binding, aggregate limits and laptop service checks |
| V2.4 | PARTIAL | Strict plans, atomic fenced claims, ownership, contracts/blackboard, concurrent host workers, independent test/review gates, sequential integration | Actual independent provider roles, legacy CLI wiring, complete crash/resume reconciliation |
| V2.5 | PARTIAL | Candidate/verified advisory lessons, bounded context, measured selection, optional comparison API, 12-case golden harness | All producer schemas/metrics, complete real scheduling/alternative runs and verified outcomes |
| V2.6 | PARTIAL | No-write dry-run, eight templates, bounded review/escalation/import, safe queue/daemon ownership, notifications and persisted dashboard projection | Team mission integration, review-driven execution, full profile/telemetry behavior |
| Stage 7 | PARTIAL | MCP policy/protocol/native file guards, local report/import tooling, migrations, regression and source bundle preparation | Complete integrated demonstration, real local probes, deployment and release acceptance |

Section coverage, implementation paths and explicit remaining work are indexed in
REQUIREMENTS.json. Section status never implies all its individual bullets passed.

## C. Test results

Final machine-readable results are authoritative; check the final committed
reports if a subsequent verification changes these checkpoint numbers.

| Profile | Label | Actual result |
|---|---|---|
| Root policy, SQLite, Git, filesystem and process tests | CLOUD_REAL | 124 passed |
| Root fake providers/model/transports, fixture pipeline and review | CLOUD_SIMULATED | 25 passed |
| Root laptop-only assertions | LOCAL_VERIFICATION_REQUIRED | 5 explicit cloud skips; no local pass |
| Full agpair bridge | CLOUD_SIMULATED | 846 passed, 0 failures in recorded full container run; hosted profile follow-up recorded in CI_STATUS.json |
| Companion TypeScript/fake SDK/transports | CLOUD_SIMULATED | 138 passed, 25 suites, 0 failures/skips; compilation and production build passed |
| Full golden harness | CLOUD_SIMULATED | 12/12 passed, no missing/pass-rate regressions versus stored fake baseline |
| Scoped Ruff / mypy | CLOUD_REAL | 0 diagnostics / 0 errors, without changing the original debt baseline |
| Offline working-tree candidate gate | CLOUD_REAL | 15 known fixture/metadata candidates; zero new findings |
| npm dependency advisories | CLOUD_REAL | 0 advisories at audit time after exact esbuild 0.28.2 update |

Mypy uses the existing scoped configuration; untyped function bodies and missing
external stubs are not exhaustively checked. Zero diagnostics is not a proof of
complete typing or full-repository security.

The original raw root baseline was 37 passed / 5 failed; four failures needed
local capabilities, one was the portable CLI issue described above. No baseline
was refreshed to hide failures. Separate justified fixture commits removed
fabricated worker readiness, vacuous tests and unsafe approval defaults. Safe
Ruff corrections remove unused imports and rename locals; all test assertions
remain. Reviewer regression additionally rejects absent tests, malformed output,
non-boolean approval and unresolved defects.

Root runner reports per-case labels in stage_7_tests.json. Bridge and companion
are conservatively labeled simulated as entire mixed profiles. Production
verification always requests bwrap. Only fixed trusted fixtures in the cloud
harness inject a real-pytest executor; this is not namespace proof and is not a
runtime escape switch. The cloud host cannot create the required UID mapping.

Golden runtime was 57.245s with 33720 KiB child high-water RSS. The older fake
baseline was measured under different load: no performance improvement is
claimed. No authenticated worker, real MCP, laptop systemd or live DB was tested.

## D. Security status

Guardian checks occur before integration, approvals bind mission/repository/HEAD/
action, and evidence must match the actual tested commit. Verification rejects
vacuous/skip-only outcomes. Independent acceptance files are hashed before worker
execution, baseline test modification is denied pending reviewed exceptions, and
failed worktrees are retained. Runtime workers cannot claim verification merely
because their executable exists. Unsupervised legacy execution fails closed.

Fresh worker environments and mandatory bwrap verification exclude controller
keys/state. Native MCP file operations use Linux dirfd/O_NOFOLLOW anchoring,
regular-file/link/size checks, bounded arguments and secret-path denial. Owned
process helpers use birth identity/pidfd where available, act as child subreapers,
and reap escaped orphans without killing unrelated processes. Core file limits
are disabled for these helpers. Auth/DB creation is private; malformed existing
auth is never silently regenerated. Redaction covers Basic/Bearer, common key
assignments, credential URLs and CLI token arguments.

These tests do not establish a complete threat-model proof. Aggregate controller/
MCP/worker limits, storage quotas and provider auth/toolchain binds remain HIGH.
The heuristic scanner is offline and does not validate/revoke credentials; known
candidate metadata contains no copied values. History scan has a detector canary;
see stage_7_history.json for the final committed-history result. PyPI's version
metadata reported no published advisories for 34 pins; it is not a complete
vulnerability or license audit. npm's zero-advisory result is time-dependent.

## E. MCP inventory

Existing configured entries remain inventory, never counted as connected servers.
Native bounded read/write/list operations, strict role/scope denial and external
stdio initialize/discover/one exact harmless call are implemented. A bounded
catalog is hashed including raw definitions to detect poisoning; source URL,
exact version/argv, allowed environment/tools and explicit approval are required.
No server was installed or declared authenticated. HTTP transport, general
mission operations, per-operation remote-write approval and actual worker-visible
permissions remain incomplete. See MCP_INTEGRATION.md and MCP_VERIFICATION_REPORT.md.

## F. Operational status

No live system was inspected or modified. Laptop checks remain
LOCAL_VERIFICATION_REQUIRED, including real Codex, AGY A and AGY B authenticated
missions, independent profiles, real sandbox escape/credential denial, actual MCP
catalog/auth, systemd/watchdog/cgroups, live DB snapshot/restore/history, terminal
appearance and notifications. Local inspection may report skipped/blocked checks;
it cannot promote source gaps into operational readiness.

GitHub API transport and existing authentication work. A CONNECT 403 occurs at
the proxy before GitHub authentication and does not imply token failure. Actions
log downloads use a separate host that still returns 403; metadata/annotations
remain available. No new token or environment restart is needed for the working
GitHub API. Full diagnosis is GITHUB_API_DIAGNOSTIC.md.

## G. Changes and publication

All seven PRs target main and are unmerged. Branches are dependent snapshots;
later PR diffs therefore include earlier work. The integration branch contains
the cumulative candidate. Refresh PR/check metadata before reviewing or merging.

| PR | Branch | Saved checkpoint |
|---|---|---|
| [#1](https://github.com/HarryJame3004/acs-ai-orchestrator/pull/1) | upgrade/stage-0-audit | 8906cd1 |
| [#2](https://github.com/HarryJame3004/acs-ai-orchestrator/pull/2) | upgrade/stage-1-backup-upgrade | 071cc2a |
| [#3](https://github.com/HarryJame3004/acs-ai-orchestrator/pull/3) | upgrade/v2.3-security-runtime | cebfd08 |
| [#4](https://github.com/HarryJame3004/acs-ai-orchestrator/pull/4) | upgrade/v2.4-coordination | e960726 |
| [#5](https://github.com/HarryJame3004/acs-ai-orchestrator/pull/5) | upgrade/v2.5-intelligence | e933d72 |
| [#6](https://github.com/HarryJame3004/acs-ai-orchestrator/pull/6) | upgrade/v2.6-review-workflow | 21831cd |
| [#7](https://github.com/HarryJame3004/acs-ai-orchestrator/pull/7) | upgrade/stage-7-verification-release | 490fbb0, e69f67e, 54e598e plus final evidence commits |

Cumulative branch: upgrade/overnight-integration. Main was eecbce4 at task start;
final remote comparison is recorded with the CI checkpoint. No push to main.

Additive migration registry: upgrade metadata, runtime control, coordination,
metrics, review/dispatch tables. Migration dry-run copies first; apply takes a
pre-apply backup and uses a transaction. Store constructors share definitions;
they still permit additive initialization outside the migration ledger, a
compatibility limitation. No live schema changed.

Development dependencies are exactly pinned in requirements/cloud-dev.txt;
Pydantic 2.12.3 supports strict schemas and Click 8.3.0 supports bridge tests.
Companion package-lock supplies transitive integrity pins; esbuild is exactly
0.28.2. Three omitted companion state modules were restored from a pinned public
upstream commit, reviewed and documented in docs/upgrade/COMPANION_STATE_RESTORATION.md;
no wholesale vendor replacement. Snapshot writes now use private exclusive
random temporary files. The original build's hidden IDE deployment was removed;
build:prod only builds. Explicit deploy/dev:install scripts remain user-run only.

CONFIGURATION.md documents runtime opt-ins and conservative defaults. Ordinary
feature JSON declarations are metadata; actual implemented environment flags
are documented individually. No production version or release tag was fabricated.

## H. Recovery and local evaluation

The source ZIP uses committed Git blobs only, rejects overwrites, excludes
credential names/symlinks, includes file SHA256 manifest and performs no activation.
See local_bundle.json for the exact source commit and archive verification. It is
an evaluation package, not a deployable accepted release. Do not send secrets.

LOCAL_DEPLOYMENT_GUIDE.md gives isolated checkout/venv/state setup, preflight,
API snapshot/verify, restore to a new scratch location, migration dry-run, staged
candidate, explicit local probes/import, one-flag rollout gates and rollback.
Read-only inspection is safe; live packages/service/auth/migration/promotion are
YELLOW/user-run. The backup reference default excludes credentials before reading
known sensitive names. Keep old app/DB/backup and use a reviewed managed pointer;
never downgrade a live upgraded DB in place or overwrite original backups.

## I. Remaining issues

- **HIGH / source:** real provider activation and verified auth/toolchain mounts.
  Native and legacy adapters deliberately remain unverified; simply installing a
  CLI or copying credentials will not make this candidate operational.
- **HIGH / source:** independent real tester/reviewer adapters with trustworthy
  session identities; currently these are host callbacks and fake fixtures.
- **HIGH / source:** natural-language and daemon dispatch into TeamRunner; the
  existing mission path remains single-task, with early unverified preflight.
- **HIGH / source:** complete interrupted Git/SQLite reconciliation, resumable
  coordinated missions and process-identity wiring for claim recovery. Current
  active/terminal runs conservatively block rather than blindly rerun.
- **HIGH / source:** aggregate controller/MCP/worker RAM/CPU/storage ceilings,
  retention and full sandbox resource proof. Per-process bounds alone are partial.
- **HIGH / source:** validated review-driven replan/task execution; baseline-test
  exception review and coverage comparison. Import currently records bounded work
  requiring planning, never silently executes it.
- **MEDIUM / source:** complete sensitive-scope classification, template profile
  execution, escalation telemetry and dashboard CPU/RAM; all legacy producer
  schemas, metric/failover instrumentation and alternative-run quota accounting.
- **MEDIUM / source:** MCP HTTP/general mission operations, remote-write approvals
  and real worker visibility. Companion persistence failures remain best-effort.
- **MEDIUM / acceptance:** full single integrated 20-step cloud demonstration,
  randomized/flaky campaign and complete dependency/license audit; existing
  component/golden tests do not substitute for these.
- **BLOCKED / local approval:** deployment, live services/DB, actual credentials,
  local packages/profiles and release activation. Scripts/procedures supplied;
  no approval bypass or token request was made.

This task stops at a saved, testable PARTIAL checkpoint. No background continuation
is implied. NEXT_SESSION_HANDOFF.md gives exact continuation priorities and gates.
