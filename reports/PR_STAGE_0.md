Establishes an auditable cloud baseline before runtime changes. The original
root suite has 37 passes and 5 failures, despite the README's 42/42 claim.
The cloud profile isolates runtime paths, explicitly skips four local-only
checks and retains the existing CLI failure. Its regression gate preserves
pytest's exit status and rejects new failures, missing tests and unexpected skips.

## Requirement mapping

| STAGE-0 requirement | Implementation/evidence |
|---|---|
| Repository and worker/MCP audit | reports/PHASE_0_BASELINE_AUDIT.md, static file:line matrix |
| Original tests, versions and labels | reports/baseline_tests.json, reports/secret_scan.json |
| Agent instructions and continuity | AGENTS.md, docs/progress/PROGRESS.md |
| Reusable pinned cloud setup | scripts/cloud_setup.sh, requirements/cloud-dev.txt |
| CI skeleton: lint, typing, tests, secrets | .github/workflows/ci.yml, scripts/cloud_static.py, scripts/cloud_test.py |
| Honest maturity and test claims | README.md, TESTING.md, reports/STAGE_0_REPORT.md |

## Validation

- CLOUD_REAL: original 33 passed / 1 failed; current 39 passed / 1 failed
  (six added regression-gate tests).
- CLOUD_SIMULATED: 4 passed in both original and current profiles.
- LOCAL_VERIFICATION_REQUIRED: four cloud diagnostic failures in the original
  suite; four explicit skips in the cloud profile; local status NOT_TESTED.
- Underlying pytest exit 1 retained; no missing baseline tests or new failures.
- CLOUD_REAL: new scripts pass Ruff/mypy; scoped legacy debt remains 99 Ruff
  findings and 13 mypy errors, recorded individually rather than suppressed.
- CLOUD_REAL: setup rerun succeeds, pip check passes, shell/YAML checks pass.
- CLOUD_REAL: offline original source/history scan has 13 candidate locations;
  no candidate in config.py. Candidates are not validated credentials.
- Hosted GitHub Actions is NOT_TESTED until the workflow actually runs.

## Security and known limitations

The audit identifies merge-before-Guardian ordering, incomplete approval
binding, inherited worker environments, misleading readiness, partial redaction
and unsafe removal fallback as later hardening priorities. No runtime feature
or security mechanism is changed by this audit stage. Cloud test path/socket
instrumentation is not a worker sandbox. Existing failures remain visible;
baseline comparison is not full acceptance. Secret values and credential
validation are absent; full history scanning/pre-commit enforcement is V2.3 work.

Development-only additions are pinned Ruff 0.17.1, mypy 2.4.0 and detect-secrets
1.5.0 plus pinned transitive dependencies. TESTING.md documents purpose,
maintenance/license evidence, analysis scope and build-backend pinning limits.
CI action SHAs are immutable; permissions are contents:read; no secrets are used.

## Migration and local verification

No schema migration, user data change, runtime feature flag or live deployment.
No live system was inspected or modified. ACS Core was not touched. Ordinary
revert of this stage's commits removes only scaffolding/documentation.

All items below are LOCAL_VERIFICATION_REQUIRED, NOT_TESTED:

- [ ] Operational install drift versus repository HEAD, excluding secrets/state.
- [ ] Each real worker: auth boolean, harmless temp task, timeout/cancellation,
  descendant cleanup, log/exit behavior, tool permissions and MCP visibility.
- [ ] Canonical AGY A/B HOME/XDG separation and credential isolation.
- [ ] Real sandbox denial/escape cases on disposable fixtures; HMAC key invisible.
- [ ] Actual MCP startup/discovery/harmless calls and least privilege.
- [ ] Consistent live backup and scratch restore before any later upgrade.
- [ ] Systemd/watchdog and interactive TUI checks; later real E2E missions.

Backup/local verification tooling is delivered in its assigned later stages.
Merge is the user's action; proceed to STAGE-1 in a new task only after merging.
