# Arch Linux local acceptance — LOCAL_VERIFICATION_REQUIRED

This candidate is PARTIAL and is not approved for live deployment. Do not enable
new flags against an operational database until remaining source gaps are closed.
No command in this document has been executed on the user's laptop.

Use LOCAL_DEPLOYMENT_GUIDE.md and docs/upgrade/TEAM_RUNTIME.md for the existing
operator-reviewed procedures. Work in a new staging directory; verify the source
archive SHA256 and its ACS_BUNDLE_MANIFEST.json commit before installing. Preserve
existing services, credentials, dirty checkouts and mission history.

Required independent local evidence:

1. Read-only environment/preflight and real repository/MCP inventory, excluding
   ACS Core internals and operational secret contents.
2. Consistent WAL-aware backup, verified manifest and new-directory scratch
   restore. Dry-run copy migrations; never overwrite the only live database.
3. Real bwrap namespace write/escape denial and isolated auth/toolchain bindings
   for Codex, AGY A and AGY B. Three binaries/profile files alone are not readiness.
4. Explicit challenge activation with distinct accounts/profiles; real independent
   tester/reviewer sessions. Never share credentials or accept fake receipts.
5. Dedicated delegated cgroup and measured CPU/RAM/PID enforcement; separately
   configure whole-service overhead and a verified bounded block filesystem (or
   retain the explicit incomplete sampled-storage mode). Optional source contracts
   are ACS_REQUIRE_HARD_STORAGE and ACS_REQUIRE_SERVICE_LIMITS; consult TEAM_RUNTIME
   for all prerequisites and do not provision mounts/cgroups without approval. Set accounted
   roots for repository/shared Git, state/DB/logs/artifacts and an owned 0700
   ACS_AGGREGATE_SCRATCH_ROOT. Sampled storage is not a quota.
6. Explicit `acsai verify-team --execute-probe --output NEW_DIRECTORY --report
   NEW_FILE` only after operator approval for real provider calls/quota; retain
   failures as well as successes. Inspect `--help` and TEAM_RUNTIME.md first.
7. All local tests, MCP authenticated operations/approvals, service watchdog and
   restart recovery, terminal UI and notification delivery; evidence must identify
   exact checkout and platform. No cloud run establishes these laptop outcomes.
8. Review the original 20-step scenario against real providers, backup and
   rollback, then obtain explicit approval before any service promotion.

Any prerequisite failure stops the affected local operation; do not bypass a
Guardian/sandbox/auth check, rotate credentials or touch ACS Core to proceed.
