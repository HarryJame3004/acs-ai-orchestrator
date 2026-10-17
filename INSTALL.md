# Isolated candidate installation

Use Linux and Python 3.12+ for the combined orchestrator/bridge. Git is required;
real supervised execution additionally requires working bubblewrap namespaces.
Package/service installation on the laptop is a user-run YELLOW action. This
candidate is PARTIAL; live activation is not currently recommended.

Review the dependent integration branch in a fresh staging checkout. Before
importing/running the application, point ACS_HOME and ACS_BACKUPS_DIR at new staging
paths and ACS_CREDENTIALS_FILE at a nonexistent fixture path. Then run:

```bash
bash scripts/cloud_setup.sh
.venv/bin/acsai --help
.venv/bin/acsai verify-local --report /path/to/new-inspection.json
```

The setup script installs pinned development/runtime dependencies into the local
checkout's .venv and the two editable packages. It does not start a daemon/worker,
install system packages, enable hooks or modify a user service. Review
requirements/cloud-dev.txt; build-backend hashes are not locked.

Read LOCAL_DEPLOYMENT_GUIDE.md for backup, migration copy checks, explicit probe
execution and rollback. Do not replace a working environment or reuse its state
for initial evaluation. No new provider token is required for cloud tests.
