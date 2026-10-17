# STAGE-0 forensic baseline audit

Stage status: PARTIAL. Audit and cloud scaffolding are implemented. The baseline
has known failures; later runtime stages and local acceptance are not complete.
Audit target: initial commit `eecbce4a8a834d3cd6ac835f587f02bafa88bb08`, verified
against local HEAD and origin/main. The initial branch was `work`; no progress
file or AGENTS.md existed. The feature branch is `upgrade/stage-0-audit`.

No live user system was inspected or modified. Earlier onboarding started a
daemon in this cloud container only; that is not evidence about the user's
service. The current cloud profile uses disposable runtime paths and blocks
that cloud daemon too. The original legacy baseline retained its existing
loopback health probe, which could observe a cloud-only instance; no user
service was reachable or verified. ACS Core remains untouched and unavailable.

## Implementation matrix

Each row carries one verification label. CLOUD_REAL in a static row means the
code was inspected, not that the claimed operational behavior was exercised.

| Capability | Existing | Missing or uncertain | Evidence (file:line) | Label | Planned action |
|---|---|---|---|---|---|
| Packaging and CLI | argparse main and module execution; editable install | Console entry point references missing `app` | pyproject.toml:39; acs_team/cli.py:718; acs_team/cli.py:841 | CLOUD_REAL | V2.3 portable entry point and compatibility test |
| Python versions | Main declares >=3.11 | Bridge requires >=3.12; advertised shared 3.11 install fails | pyproject.toml:10; agpair/pyproject.toml:12 | CLOUD_REAL | Document 3.12+ shared setup now; reconcile declarations later |
| Configuration | Environment gateway/model/API settings, user-path defaults | Import creates directories; no ACS_HOME/XDG default; worker overrides in template not read | acs_team/config.py:6; acs_team/config.py:16; acs_team/config.py:28; .env.example:21 | CLOUD_REAL | V2.3 portable configuration and isolated fixtures |
| Daemon lifecycle | HTTP thread, signals, heartbeat and reconciliation | No worker dispatch after queued→PLANNING; no reliable singleton ownership or watchdog | acs_team/daemon.py:53; acs_team/daemon.py:84; acs_team/daemon.py:125 | CLOUD_REAL | V2.3 actual supervision and restart semantics |
| Local API | Health/status, missions, workers, MCP, repos, memory, cancellation/resume | Binding configurable beyond loopback; cancel updates state without process cancellation | acs_team/api_server.py:69; acs_team/api_server.py:179; acs_team/api_server.py:204; acs_team/config.py:41 | CLOUD_REAL | V2.3 policy, cancellation and API integration |
| API authentication | Random token, 0600 on creation, constant-time verify | Existing weak/malformed token is overwritten; existing permissions not revalidated | acs_team/auth.py:16; acs_team/auth.py:30 | CLOUD_REAL | V2.3 key lifecycle and separate worker-invisible evidence key |
| SQLite | WAL, foreign keys, busy timeout, mission/task/checkpoint/memory/approval/repo schema | Version 1 marker plus ad hoc ALTERs; migration errors only debug logged | acs_team/db.py:23; acs_team/db.py:161; acs_team/db.py:184 | CLOUD_REAL | STAGE-1 transactional migration tooling, data-preservation fixtures |
| State machine | Allowed transitions and checkpoint hash verification | Reconciliation reads at most 100 per active state; recovery not wired to actual worker resumption | acs_team/state_machine.py:32; acs_team/state_machine.py:162 | CLOUD_REAL | V2.3 bounded reliable restart/cancel and regression tests |
| Natural-language planner | LLM JSON parsing, single task, retry loop and failover | No validated task DAG/structured contracts; no true coordinated three-worker pool | acs_team/planner.py:36; acs_team/autonomous_planner.py:110; acs_team/autonomous_planner.py:161 | CLOUD_REAL | V2.4 planner schemas, fake-worker contracts and coordination |
| Background missions | CLI launches a detached module subprocess | Daemon does not supervise spawned mission process; full environment inherited | acs_team/cli.py:357; acs_team/cli.py:380 | CLOUD_REAL | V2.3 ownership/cancellation; preserve CLI flags |
| Worker interface | BaseWorker.execute_task and result dictionaries; separate legacy CodexWorker | No structured result validation, shared cancellation API or scenario fake adapters | acs_team/worker_adapters.py:35; acs_team/worker.py:11 | CLOUD_REAL | V2.3 supervision; V2.4 deterministic fake scenarios |
| Real workers | Static invocation/config analysis only | Authentication, execution, quota, timeout trees, permissions and MCP visibility unverified | acs_team/worker_adapters.py:60; acs_team/worker_adapters.py:177; acs_team/worker_adapters.py:293 | LOCAL_VERIFICATION_REQUIRED | Per-worker local checklist below |
| Worktree management | Git add/remove, disk threshold, sanitized slash in identifiers | `..`/symlinks/root ownership not fully guarded; removal falls back to rmtree after failed git removal | acs_team/worktree_manager.py:57; acs_team/worktree_manager.py:106 | CLOUD_REAL | V2.3 registered-root containment before deletion |
| Scope and integration | In-memory exact-path reservations; status-based scope check; sequential git merge | No glob overlap, claims/leases or cross-process durability; git status parse fragile; some exit codes ignored | acs_team/scope_and_integration.py:38; acs_team/scope_and_integration.py:65; acs_team/scope_and_integration.py:115 | CLOUD_REAL | V2.4 claims, ownership and serialized verified integration |
| Guardian/CoreLock | Canonical repository-path veto, branch approval gate, quality/evidence check | Hardcoded path differs from config-derived Core path; `changed_files` unused by CoreLock; no complete changed-path/symlink/mode policy | acs_team/guardian.py:33; acs_team/guardian.py:73; acs_team/repo_manager.py:123 | CLOUD_REAL | V2.3 fail-closed configurable protected list and escape tests |
| Guardian ordering | Evidence generated and Guardian evaluated | Planner merges first; worker tree tested rather than a verified integrated tree | acs_team/autonomous_planner.py:240; acs_team/autonomous_planner.py:279 | CLOUD_REAL | HIGH: enforce pre-integration approval and post-integration testing in V2.3/V2.4 |
| Evidence | Canonical JSON, SHA256, HMAC-SHA256, constant-time comparison and commit check | Shared API auth token used as HMAC key; worker invisibility/replay scope not established | acs_team/evidence.py:42; acs_team/evidence.py:104; acs_team/guardian.py:68 | CLOUD_REAL | V2.3 tamper/replay/key isolation; local mount inspection |
| Quality/testing | Real subprocess test execution; Python syntax and diff regex checks | shell=True accepts model-generated command; syntax compilation is not full lint; no hard ban on skipped/zero-test evidence | acs_team/quality.py:55; acs_team/quality.py:110; acs_team/autonomous_planner.py:419 | CLOUD_REAL | V2.3 controlled commands and trustworthy test accounting |
| Approval | Persisted approval gate and worker-identity rejection | Guardian checks approval status without visibly binding it to the requested repo/action/commit at this call site | acs_team/human_approval.py:86; acs_team/human_approval.py:133; acs_team/guardian.py:111 | CLOUD_REAL | HIGH: verify full approval binding in V2.3 |
| Memory/context | SQLite FTS5, decisions/failures/knowledge, stale marking | Planner mostly loads one context file; verified lesson retrieval/security separation absent | acs_team/memory.py:24; acs_team/planner.py:29 | CLOUD_REAL | V2.5 reuse existing storage rather than duplicate memory |
| MCP inventory | Gemini A/B/plugin and Codex plugin config parsers; five internal definitions | Executable or URL existence counted as usable/connected; no protocol probe | acs_team/mcp_manager.py:48; acs_team/mcp_manager.py:130; acs_team/mcp_manager.py:200 | CLOUD_REAL | STAGE-7 verify/audit harness; never claim reported 51/49/68 |
| MCP permissions | Role categories, canonical path boundaries for common argument names | Unknown roles are not default-denied; required_permissions metadata not enforced; handlers may be absent | acs_team/mcp_registry.py:75; acs_team/mcp_registry.py:105; acs_team/mcp_registry.py:158 | CLOUD_REAL | V2.3 mission/worker allowlist; fake-server tests |
| MCP redaction | Auth display masks suffix | Can expose first 10 characters and command args/URL; not comprehensive redaction | acs_team/mcp_manager.py:119; acs_team/mcp_manager.py:128 | CLOUD_REAL | HIGH: redact names/status only, credential tests in V2.3 |
| TUI | Textual views, composer, log modal, mission thread | Instantiation test does not establish real interactive functionality | acs_team/tui.py:342; acs_team/tui.py:693; tests/test_gate6_e2e_and_cli.py:206 | CLOUD_REAL | V2.6 headless UI behavior plus local interaction check |
| Backup/recovery | Backup directory constant; checkpoints and reconciliation | No consistent SQLite backup/restore/verify command or upgrade dry-run | acs_team/config.py:13; acs_team/state_machine.py:162; scripts/run_security_and_wal_audit.py:113 | CLOUD_REAL | STAGE-1 copy-based backup/restore and staged upgrade tooling |
| Resource limits | 10 GB disk guard, max workers=3, in-memory semaphore helper | No full application-enforced memory/CPU/log/worktree/mission limits | acs_team/config.py:44; acs_team/scope_and_integration.py:229 | CLOUD_REAL | V2.3 opt-in limits with compatibility defaults |
| Logging and errors | Standard logging, persisted mission logs, audit events | Logs unbounded; broad exception catches; mutable DB audit is not a tamper-proof log | acs_team/daemon.py:29; acs_team/db.py:390; acs_team/llm_client.py:78 | CLOUD_REAL | V2.3 redaction/rotation/error classification |
| Test evidence | Temp SQLite/git and manual/fake-worker lifecycle | README's real-worker E2E interpretation unsupported | tests/test_gate6_e2e_and_cli.py:86; tests/test_gate8_natural_language_and_v2_2.py:136; tests/test_gate8_natural_language_and_v2_2.py:310 | CLOUD_SIMULATED | Keep honest labels; later real local missions |
| CI and cloud tooling | None at initial revision | Added pinned setup, lint/type/candidate and test regression profiles | .github/workflows/ci.yml:1; scripts/cloud_setup.sh:1; scripts/cloud_test.py:1 | CLOUD_REAL | Validate commands now; hosted workflow remains NOT_TESTED |

## Worker analysis (static, CLOUD_REAL)

| Adapter | Invocation and output | Isolation/environment | Timeout/cancel/log gap |
|---|---|---|---|
| CodexPrimaryWorker | `exec -C ... --approve-for-me --json`; trusts exit code; stdout/stderr excerpts; git status for files | Hardcoded per-user binary; inherits complete environment; no explicit bubblewrap wrapper here | subprocess.run timeout; no tracked process group/cancellation; JSON stream not parsed into a validated receipt |
| AGY A | `-p` and JSON output flags; exit status and excerpts | Separate default binary; inherits normal environment and home | Timeout with extra 10 seconds; no group ownership/descendant cleanup or cancellation |
| AGY B | model/effort/print-timeout flags and text output | Dedicated configured home and HOME/XDG variables, but copies all ambient variables | Executable plus .gemini directory treated as verification; no authentication probe; no group cleanup |
| Legacy CodexWorker | Dispatches through agpair rather than the newer registry | Hardcoded bridge path under orchestrator runtime | Separate execution path must stay compatible and be reconciled before rewriting |

AGY A and B default directories differ statically, but there is no validator
rejecting aliased/symlink-equivalent homes or shared caches, nor an environment
allowlist. Real separation is not established. Do not create placeholder .gemini
directories or change worker bypass flags to make availability assertions pass.
The bridge is a substantial separate package; reuse its process-lifecycle ideas
only after checking their actual behavior. Its optional extension scripts include
deployment side effects and unpinned `npx` packaging; none were executed.

## MCP inventory (static, CLOUD_REAL)

Config sources: Gemini primary `config/mcp_config.json`, the dedicated B home's
equivalent, Gemini plugins and cached tool schemas, and Codex plugin `.mcp.json`.
Transport labels are stdio/http/internal; neither a URL nor an installed command
proves startup, discovery or a harmless tool call. Native tools are read_file,
write_file, list_directory, inspect_binary and force_reset_state; only the first
three have default handlers. Per-worker visibility is descriptive metadata rather
than demonstrated worker connectivity. Full verifier/audit commands are future
STAGE-7 features, not implemented during this audit-only stage.

## Measured baseline and security findings

`reports/baseline_tests.json` contains 42 unchanged tests: 37 passed, 5 failed,
0 skipped, no warnings. CLOUD_REAL: 33 pass / 1 fail; CLOUD_SIMULATED: 4 pass;
four LOCAL_VERIFICATION_REQUIRED cases failed their cloud diagnostic attempt
and remain NOT_TESTED locally. Root scope only; bridge and companion suites
are separate workflows and not acceptance gates for STAGE-0. `TESTING.md`
explains the temporary-path instrumentation and exact commands.

The scoped Ruff profile found 99 existing diagnostics; mypy found 13 errors in
7 files. Undefined `Any` in the daemon signature is one concrete existing
typing issue. Findings are recorded individually in `baseline_static.json`,
not suppressed with source ignores. V2.3 must triage them by impact and fix
runtime defects before cosmetic lint debt. New scaffolding must remain clean.

Offline detect-secrets found 13 candidates in the original tracked tree and
the sole historical commit. Sanitized metadata is in `secret_scan.json`. They
are test literals/hash fixtures and keyword/default declarations; no detector
candidate was found in `acs_team/config.py`, whose key loader uses environment
or a settings file. This does not prove absence of all secrets or validity of
any reported historical key. No credential was tested, copied, rotated or
revoked. Generated audit commit identifiers can add entropy candidates in the
current-tree scan; those are disclosed in the static baseline.

If the user confirms a previously real exposed key: replace it through the
provider's local secure settings, stop relying on the old key, revoke it in
the provider console, inspect provider audit activity and recheck local config
without logging values. Backup handling and any history rewrite require user
review; history rewriting is not performed by this task.

Priority findings: HIGH—Guardian after merge, unbound approval call site,
overbroad inherited environment, inaccurate worker/MCP readiness, partial
redaction, insufficient deletion containment. MEDIUM—nonportable config/CLI/test
paths, cancellation and queue gaps, unbounded logs and unclassified retries,
missing backup runner and import side effects. LOW—existing unused-import/style
debt. These are static findings needing focused regression tests, not claims of
an exploited vulnerability. Security and coordinated-runtime implementation is
explicitly deferred to its stage rather than silently omitted.

## Local verification checklist

Every item below is LOCAL_VERIFICATION_REQUIRED, status NOT_TESTED. Procedures
must run on disposable fixtures or copies, with the user's local authorization.
No cloud result closes these checks.

- Compare hashes of the operational install with repository HEAD, excluding
  secrets, state, caches and build artifacts. A read-only drift tool is STAGE-7 work.
- Codex, AGY A and AGY B independently: discover actual executable/version,
  auth boolean, harmless temp-repo task, timeout, cancellation/descendant cleanup,
  MCP visibility, tool permissions, sanitized logs and exit code.
- Confirm distinct canonical A/B HOME/XDG/cache paths without exposing credentials.
- Exercise actual bubblewrap allowed write/denied write, traversal/symlink denial,
  and a simulated protected path; confirm the evidence key is not mounted.
- Inspect real systemd user service/watchdog/restart behavior; no cloud PID is proof.
- Verify actual MCP startup/discovery/harmless call, least privilege, timeout and
  recovery; reported server/tool counts remain unverified.
- Run consistent backup, verify and scratch restore before any live upgrade; no
  operational DB is opened or migrated by STAGE-0.
- Run the interactive TUI and later real multi-agent E2E on a disposable repo.

`scripts/local_verify.sh`, `acsai verify-local`, backup/migration tooling, fake
worker scenario adapters and `acsai mcp verify` are not falsely supplied as
finished features here: the stage plan assigns them to STAGE-1/V2.3/V2.4/STAGE-7.
Continue one stage per task after the user merges this stage's PR.
