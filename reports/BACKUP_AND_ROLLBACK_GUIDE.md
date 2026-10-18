# Backup and rollback checkpoint

Live execution is LOCAL_VERIFICATION_REQUIRED and operator-controlled. This
continuation did not back up, migrate, restore or restart the user's live system.
The existing source procedures are in ../BACKUP_AND_RECOVERY.md,
../LOCAL_DEPLOYMENT_GUIDE.md and docs/upgrade/TEAM_RUNTIME.md (paths relative to
repository root for the latter). Candidate remains PARTIAL.

Before considering promotion, create a consistent SQLite backup with the existing
backup API/CLI and verify its manifest/integrity. Store configuration references
without copying secrets by default. Preserve current application ref, service
configuration and dirty work. Restore only into a new scratch destination and
check populated history plus migrations there before approval to change live state.

Rollback must stop only the service/processes owned by ACS, preserve failed and
dirty worktrees/evidence, restore only the operator-approved backup into the
intended new destination, verify integrity and then restore the previous known
application/service configuration. Never reset a user's branch, delete unrelated
paths, use a force worktree removal, merge main or rotate credentials as cleanup.

Coordinated commits now use FULL WAL synchronization and evidence publication
syncs files/directories. These primitives do not replace backups or prove crash
recovery at every boundary. An interrupted Git integration must use the existing
journal/owned-worktree reconciler; unknown/dirty/live-owned state stays blocked.
