# STAGE-0 completion report

Status: PARTIAL. Repository audit, original baseline, AGENTS.md, pinned cloud
setup, CI skeleton and regression checks are implemented. Runtime features
remain at the original version; later stages have not started. No live user
system was inspected or modified. ACS Core remains unchanged.

| Check | Label | Outcome |
|---|---|---|
| Original unchanged root tests | CLOUD_REAL | 33 passed, 1 failed |
| Original manual/fake-worker/service tests | CLOUD_SIMULATED | 4 passed |
| Original environment-dependent tests | LOCAL_VERIFICATION_REQUIRED | 4 cloud diagnostic failures; local NOT_TESTED |
| Current root plus six scaffold tests | CLOUD_REAL | 39 passed, 1 failed |
| Current manual/fake-worker/service tests | CLOUD_SIMULATED | 4 passed |
| Current environment-dependent cases | LOCAL_VERIFICATION_REQUIRED | 4 explicitly skipped with reasons; local NOT_TESTED |
| Baseline identity/outcome comparison | CLOUD_REAL | PASS: no missing tests or new failures; underlying pytest exit remains 1 |
| New cloud scripts: Ruff and mypy | CLOUD_REAL | PASS: no diagnostics |
| Scoped original lint/type baseline | CLOUD_REAL | 99 Ruff findings; 13 mypy errors in 7 files; not clean |
| Offline original-tree/history secret candidate scan | CLOUD_REAL | 13 candidates; no detector finding in config.py; heuristic only |
| Pinned setup script, rerun with installed state | CLOUD_REAL | PASS; editable builds/install and pip check succeeded |
| Shell syntax and workflow YAML/read-only permissions | CLOUD_REAL | PASS; hosted Actions execution remains NOT_TESTED |
| User workers, services, MCP and Arch sandbox | LOCAL_VERIFICATION_REQUIRED | NOT_TESTED |

Exact current test outcomes are in `stage_0_tests.json`; the original baseline
and dependency versions are in `baseline_tests.json`. CLOUD_REAL confirms the
actual check ran here, not the user's deployment. Test fixtures that manually
write worker changes or fake providers retain CLOUD_SIMULATED labels.

The remaining CLOUD_REAL failure is the unmodified CLI subprocess test's
workstation-specific interpreter. Separately, the console-script target is
incorrect. Three local skips require authenticated AGY B assumptions; the
fourth requires supported bubblewrap namespaces. No fake credentials, assertion
weakening, xfails or source fixes were introduced. The cloud runner's isolated
paths protect ambient user state while preserving the original assertions.

Security findings and requirement-to-implementation mapping are in
`PHASE_0_BASELINE_AUDIT.md`. No key was validated, rotated or revoked; existing
candidate metadata is fingerprinted without values. The CI secret scanner is
an offline baseline gate, not proof of zero secrets or completed V2.3 security.

New dependencies are development-only: Ruff, mypy and detect-secrets with exact
pins and pinned transitive dependencies; rationale, upstream activity and
license evidence are in TESTING.md. No production dependency declaration,
existing lockfile, CLI flag, API route, schema, feature flag or runtime module
changed. There is no migration or live deployment to apply or roll back.

Cloud checks completed locally. GitHub-hosted CI and PR publication require
working repository/API access; the final branch/PR outcome is recorded in
`docs/progress/PROGRESS.md`. Do not start STAGE-1 before the user merges STAGE-0.
