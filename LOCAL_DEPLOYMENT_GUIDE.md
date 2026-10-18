# Current deployment gate — PARTIAL candidate

Latest application source 511ff9b has verified improvements but an unresolved
seeded postmerge failure and incomplete source acceptance. This guide remains an
operator-reviewed procedure, not permission or readiness to promote this candidate.
Read reports/ARCH_LINUX_LOCAL_ACCEPTANCE.md, reports/FINAL_CLOUD_HANDOFF.md and
docs/upgrade/TEAM_RUNTIME.md for new opt-in filesystem/service contracts before
any local staging/probes. No live deployment was performed from cloud.

# Local evaluation and rollout gates

**Candidate PARTIAL: live activation BLOCKED on the HIGH source/operational gaps
in reports/FINAL_ACCEPTANCE_REPORT.md.** The commands below prepare an isolated
candidate and evidence. They do not authorize activation. All laptop package,
service, credential binding and live migration actions are YELLOW/user-run under
Master Spec §1.1. No cloud task executed them.

## Review and isolate

Review PRs in dependency order; no PR has been merged by this task. Use a fresh
checkout of upgrade/overnight-integration outside the operational installation.
Keep the original application, database and credentials untouched. Do not point
ACS_HOME at ACS Core or the existing live state during initial tests.

Set these locally to explicit staging paths before running application commands:

```bash
export ACS_HOME=/absolute/new/staging/runtime
export ACS_BACKUPS_DIR=/absolute/new/staging/backups
export ACS_CREDENTIALS_FILE=/absolute/new/staging/absent-credentials.json
bash scripts/cloud_setup.sh
.venv/bin/acsai verify-local --report /absolute/new/inspection.json
.venv/bin/python scripts/cloud_test.py --compare-baseline --report /absolute/new/cloud-tests.json
```

Read-only inspection does not initialize runtime directories or consult router
credential files. The report itself is an explicit new private output artifact.
Missing/unsupported checks remain SKIPPED; no automatic feature activation follows.

## Backup, scratch restore and staging

After reviewing the actual live DB path locally, choose new backup/staging
locations. The read-only SQLite backup API reads the source; it never replaces it.

```bash
export ACS_ENABLE_RECOVERY=1
acsai upgrade-preflight --source /absolute/reviewed/source --database /absolute/live/state/acs_ai.db
acsai backup create --database /absolute/live/state/acs_ai.db --target /absolute/new/pre-upgrade.acs-backup
acsai backup verify /absolute/new/pre-upgrade.acs-backup
acsai backup restore /absolute/new/pre-upgrade.acs-backup --target /absolute/new/scratch-restore
acsai migrate --database /absolute/new/scratch-restore/database.sqlite3
acsai upgrade-stage --source /absolute/reviewed/source --database /absolute/live/state/acs_ai.db --target /absolute/new/candidate
```

Inspect omitted files, permissions and preserved mission history. Install the
candidate in its own venv. Keep its state bound to the candidate DB copy. Stage
health defaults NOT_TESTED. No source tree/DB/app pointer is activated by staging.

Explicit disposable checks, after reviewing the test source:

```bash
acsai verify-local --repository /absolute/reviewed/source --execute-probes --run-local-tests --report /absolute/new/local-verification.json
acsai import-local-report --file /absolute/new/local-verification.json --output /absolute/new/imported-local-evidence
```

The local suite includes legacy availability assertions; these do not prove real
authenticated tasks. Real provider tasks/roles, key visibility, systemd, full MCP
checks and real multi-agent E2E remain incomplete. Imported reports are untrusted
user evidence and never auto-enable flags or bypass policy.

## One flag at a time, only after acceptance

| Order | Capability | Verification / rollback |
|---|---|---|
| 1 | Offline scanning / optional hooks | Run static/history gates; hook enabling is an explicit local Git setting |
| 2 | Supervision/timeouts | Real bwrap, auth/toolchain mounts, timeout/cancel/reaping; disable flag if checks fail |
| 3 | Emergency stop | Test-instance durable stop/resume; explicit operator resume required |
| 4 | Recovery/backups | Verify and restore scratch history; preserve the prior app and backups |
| 5 | Strict outputs | Validate bounded plans/malformed input; do not use legacy fallback as team authorization |
| 6 | Claims single-worker | Confirm ownership/leases/token rejection; retain failed worktrees |
| 7 | Blackboard/integration | Verify handoffs and rollback on a disposable repo |
| 8 | Independent tester/reviewer | BLOCKED until real role adapters and natural-language integration are implemented |
| 9 | Lessons/scheduling/optional alternatives | Evidence-backed advice and neutral scheduling; alternatives last, off by default |
| 10 | UX/notifications/dashboard | Validate accurate reports; external notification delivery explicitly configured |

Use CONFIGURATION.md for the actual env switches. JSON rollout declarations alone
do not activate code. No flag overrides Guardian/Core/approval policy.

## Live changes and rollback — require separate operator approval

Do not run a live migration or change a service pointer yet. When all gates close,
stop writers explicitly, create/verify a fresh backup and review migration history.
`migrate --apply` additionally requires a new backup destination and exact resolved
--confirm-target. Never replace a live database with a raw copied .db file.

Managed application promotion is an API with explicit approval and reviewed
stop/start/health callbacks, not an automatic CLI deploy. Its rollback restores an
owned app pointer, not external side effects or the live DB. A rollback after new
missions/remote effects needs an operator recovery decision. Preserve versions,
evidence and backups. No deletion, chmod of existing live data, credential rotation,
service activation, tag, release publication or main merge is authorized here.
