# Backup and recovery

Recovery tooling is opt-in: `ACS_ENABLE_RECOVERY=1`. Paths are explicit, and
backup/restore/staging destinations must be new. Source databases are opened
read-only for SQLite's backup API; copying only a live `.db` file is unsafe.
Checksums and integrity checks detect corruption, not malicious manifest forgery.

These commands are for the local operator after reviewing paths. No operational
database was inspected by cloud tests. Substitute actual paths locally; do not
paste credentials into a command, report or chat.

```bash
export ACS_ENABLE_RECOVERY=1
acsai backup create --database "$ACS_HOME/state/acs_ai.db" --target /path/to/new.acs-backup
acsai backup verify /path/to/new.acs-backup
acsai backup restore /path/to/new.acs-backup --target /path/to/new-scratch
acsai migrate --database /path/to/new-scratch/database.sqlite3
```

Backup directories are 0700, files 0600. Source/config references can be added
with repeated `--reference FILE`. Environment/credential files and likely
credential assignments are excluded by default. `--include-credentials` is an
explicit local opt-in; backup media must then receive the same protection as
credentials. The DB may itself contain private mission data: protect every
backup, even when credential files are excluded. No backup artifacts belong in Git.

`migrate` defaults to dry-run: it snapshots the source and migrates only a temp
copy. Applying a migration requires BOTH `--apply --confirm-target RESOLVED_PATH`
and `--backup-target NEW_DIRECTORY`. Quiesce local writers and authorize the
operation yourself. The runner checks ordered migration history, runs SQLite
DDL in a transaction, rolls back failure and preserves existing mission tables.
It never resets a schema or deletes mission history. The registry now contains
five additive versions: upgrade metadata, emergency controls, fenced team tables,
worker metrics, and review/daemon dispatch. Constructors share these definitions;
perform the staged migration/backup procedure before enabling the associated flags.

Restore never overwrites a live install or existing directory. Verify first,
restore to scratch, inspect history and run the candidate's tests. Switch the
application only after successful local checks. Do not roll back a database
blindly after other systems have observed effects; app-pointer rollback cannot
undo external actions or incompatible schema changes.

CLOUD_REAL tests cover WAL concurrent writes, history preservation, tampered
checksums, traversal, symlinks, extra members, idempotence and transactional DDL
rollback. Application service-control rollback is CLOUD_SIMULATED. Live backup,
scratch restore and service behavior remain LOCAL_VERIFICATION_REQUIRED.
