# V2.3 checkpoint

Status: PARTIAL. Cloud security/runtime increments are implemented; this is not
V2.3 acceptance. Evidence: v2_3_tests.json (87 passed, 4 skipped; CLOUD_REAL 78,
CLOUD_SIMULATED 9, LOCAL_VERIFICATION_REQUIRED 4), v2_3_static.json (95 existing
Ruff, 12 existing mypy, 15 known secret candidates; zero new findings).
Original tests corrected separately in 53514c0 with rationale; no baseline reset.

Implemented: nonempty portable Core policy; canonical path/control-file denial;
commit-bound approvals; real non-vacuous allowlisted test execution; Guardian
before merge; dedicated integration worktree and restricted rollback; redaction
on persistence/output/rotating logs; invalid auth fails without replacement;
MCP roles/scopes/no fabricated handlers/readiness; atomic worktree cleanup;
process identity checks, bounded pipes/concurrency, cancellation/timeout and
optional CPU/address-space caps; persistent emergency stop; optional watchdog
and periodic consistent backups; transactional DB scopes; offline history scanner
with coverage canary; CI and opt-in pre-commit hook. No new dependencies.

Defaults remain conservative. Real worker adapters are unverified until a local
probe can prove authentication/usability. The opt-in supervised path requires
bwrap and a fresh home; provider toolchain mounts/auth provisioning are not yet
verified. No live credential files were read. Process tests cover owned groups,
escaped descendants and unrelated-process protection; fast-parent exit races and
orphan zombie reaping are outstanding. Resource controls do not yet cover all
controller/MCP processes or disk limits. The retry/circuit-breaker primitives are
not a complete persistent scheduler. Emergency state is additive but not yet in
the versioned migration registry. Daemon queue integration is still incomplete.

LOCAL_VERIFICATION_REQUIRED: real worker authentication and harmless missions,
bwrap UID/mount/network/auth boundary, systemd watchdog/restart/cgroups, laptop
backup/deployment/restore, real MCP server behavior. No local deployment, ACS Core
access, main push or merge performed. Continue V2.4 using a dependent branch.
