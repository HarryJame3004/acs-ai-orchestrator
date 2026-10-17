# Stage 1 checkpoint

Status: CLOUD_PASS_LOCAL_PENDING. New recovery commands are opt-in via
ACS_ENABLE_RECOVERY=1. Production code provides read-only SQLite backup API
snapshots, checksum/integrity verification, private file permissions, explicit
new-directory restore, reference credential exclusion, versioned transactional
migrations, copy-first dry-run and mandatory pre-apply backups. Staging never
activates an app or replaces a DB. Approved managed app-pointer promotion has
health-based rollback with injected service control; live service actions were
not run. See BACKUP_AND_RECOVERY.md and UPGRADE_GUIDE.md.

CLOUD_REAL: 54 passed. CLOUD_SIMULATED: 5 passed (including application service
rollback with fake callbacks). LOCAL_VERIFICATION_REQUIRED: 4 explicit skips;
live backup/service behavior remains NOT_TESTED. Total 59 passed, 4 skipped,
pytest exit 0. Existing baseline cases and assertions preserved. Static gate:
99 existing Ruff findings, 13 existing mypy errors, no new diagnostics/candidates.
No new dependencies. No operational data, local service or ACS Core touched.

Dependent on open PR #1; stage branch upgrade/stage-1-backup-upgrade. The
integration branch is advanced by fast-forward pushes only. Next: V2.3 security
and runtime. Requirement tracking is in reports/REQUIREMENTS.json; NOT_TESTED
items are not implied complete by this checkpoint.
