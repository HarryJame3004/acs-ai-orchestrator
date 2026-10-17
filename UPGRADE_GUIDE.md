# Safe staged upgrade

Candidate PARTIAL; live activation is BLOCKED on the HIGH source gaps in
reports/FINAL_ACCEPTANCE_REPORT.md. Use LOCAL_DEPLOYMENT_GUIDE.md for isolated
evaluation first. No cloud command deploys to a laptop. Keep the operational install, state and
credentials intact. PRs are dependent while PR #1 is open; review stage commits
in order. `upgrade/overnight-integration` contains the tested cumulative work.

1. Locally review the branch/diff, then enable `ACS_ENABLE_RECOVERY=1` explicitly.
2. Run `acsai upgrade-preflight --source SOURCE --database DATABASE`. This checks
   Python/git/disk and integrity/migrations on a copy. Inspect your systemd user
   service state separately; cloud cannot do that for your laptop.
3. Create and verify a consistent backup; restore it into scratch and verify
   mission history before making any live change (BACKUP_AND_RECOVERY.md).
4. `acsai upgrade-stage --source SOURCE --database DATABASE --target NEW_CANDIDATE`
   copies a credential-filtered application tree, pre-migration backup and
   candidate DB. No active pointer or original DB is replaced. Inspect omitted
   credential/config files and supply local runtime bindings securely. A staged
   candidate without an executed health callback is NOT_TESTED, not healthy.
5. Install candidate dependencies in its own venv using the repository's pinned
   cloud setup script where appropriate. Check CLI, tests and isolated daemon
   health with candidate state before enabling flags on the real service.
6. Any live migration requires stopped writers, the exact target confirmation,
   and a new backup. Obtain local operator approval; do not automate this step
   from cloud. Existing migrations are additive; check backward compatibility.
7. Optional managed application deployment uses `recovery.promote_application`:
   a candidate below a dedicated deployment root, a `current` symlink inside
   that root, explicit approval and dedicated stop/start/health callbacks.
   Candidate health failure restores the previous app pointer and restarts the
   prior service. It NEVER replaces or rolls back the live database. Callback
   failures require operator recovery; inspect service health after any error.

The promotion API is tested with fake service control on temp paths; actual
systemd callbacks, staged installation and all live actions are
LOCAL_VERIFICATION_REQUIRED. No automatic default activation command is exposed
to workers. Preserve old candidate versions and backups until local acceptance.
