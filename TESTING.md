# Latest verification — source 511ff9b, PARTIAL

Root stable-source regression: 220 passed / 7 explicit local skips. Exact scopes,
commands/labels and historical direct failures are in reports/FULL_TEST_EVIDENCE.json.
Latest seed 1337 had one postmerge failure; later passing runs do not close it.
Read reports/POSTMERGE_RANDOMIZED_FAILURE.txt before claiming reliability.

Effective pytest.ini registers markers. CPU tests retain CPU/signal assertions
and reject wall cancellation as CPU proof. New profiles cover bounded disk/service
contracts, write admission, baseline helper/config tampering and independent
Guardian invocation failures. Positive kernel-contract fixtures are simulated;
authenticated providers, host delegation and laptop behavior remain local gates.

# Current verification profiles

Use reports/stage_7_tests.json and reports/bridge_tests.json for the latest
measured outcomes. The original baseline below is historical and unchanged.

- CLOUD_REAL: actual Python, temp Git/SQLite/HTTP/process/filesystem checks.
- CLOUD_SIMULATED: fake providers, model/service/notifier transports and bridge
  scenarios, even when the controller uses real Git/SQLite/subprocesses.
- LOCAL_VERIFICATION_REQUIRED: real providers, bwrap on the laptop, systemd,
  actual MCP auth/worker visibility and live deployment. Skips are not passes.

```bash
.venv/bin/python scripts/cloud_test.py --compare-baseline --report /tmp/acs-final-tests.json
.venv/bin/python scripts/cloud_static.py --report /tmp/acs-final-static.json
.venv/bin/python scripts/security_scan.py --history --report /tmp/acs-history.json
# Bridge suite expects its own project directory:
(cd agpair && ../.venv/bin/python -m pytest tests -q -p no:cacheprovider)
```

Production verification always requests bwrap; missing namespaces fail closed.
The cloud harness injects a real pytest executor only for fixed trusted temp
fixtures, and fake benchmarks explicitly use the same fixture executor. This
checks orchestration/counting, never proves runtime isolation and has no runtime
environment switch. Real model/provider output uses the sandboxed default.

The cloud runner allows only loopback servers bound by the disposable test process
(and the historical 20135 fixture), plus disposable Unix sockets. Operational
services/gateway remain blocked. New local-only cases need explicit capability
reasons; the comparator never permits relabeling an original cloud test as local
to hide a skip. All legacy assertions remain; incorrect fixtures were corrected
in separate justified commits, never through baseline rewrites.

Local inspection: `acsai verify-local --report NEW_FILE` is read-only except the
requested report. `--execute-probes` runs scratch DB/control/HMAC/sandbox checks;
`--run-local-tests` explicitly executes the local-only profile in disposable ACS
state. The old availability assertions are not proof of authenticated provider
execution. Real provider task/role activation remains incomplete.

Golden harness: `acsai bench run --suite smoke|full --workers fake`. Full has 12
fixtures; real mode honestly returns BLOCKED pending provider role verification.
No uncontrolled provider calls are needed for cloud tests. CI uses pinned actions,
read-only permissions, no persisted checkout credentials and no supplied secrets.

Scoped static debt is now resolved: 0 Ruff findings and 0 mypy
errors at the Stage 7 checkpoint; no new finding is allowed. Thirty-four pinned
dependencies had no published advisory in PyPI version metadata; this is not a
complete vulnerability audit or a build-backend hash lock.

# Historical baseline (preserved context)

# Cloud baseline and verification

STAGE-0 records the existing implementation; it does not repair runtime features.
The historical 42/42 claim is not the measured baseline.

Use Python 3.12+ (the orchestrator declares 3.11+, but the required bridge
declares 3.12+), git and a writable checkout. No root privileges, authenticated
workers, gateway or systemd session are needed for this profile.

```bash
bash scripts/cloud_setup.sh
.venv/bin/python scripts/cloud_static.py --report /tmp/acs-static.json
.venv/bin/python scripts/cloud_test.py --report /tmp/acs-tests.json
```

The continuation repaired both the CLI console target and the original test's
workstation-specific interpreter in separate code and test commits. The command
now exits 0: 47 passed, 4 explicit local-only skips. All original CLI assertions
remain intact; subprocesses use temp runtime paths and the active interpreter.
Do not create a fake workstation or authenticated worker profile to make the
local-only tests pass. Historical baseline details below remain unchanged.

The initial unchanged 42-test suite produced 37 passed / 5 failed / 0 skipped
in 5.22 seconds of pytest execution (5.386 seconds including the wrapper), on
Python 3.12.14 and pytest 9.1.1, with no reported warnings. Full dependencies,
test identities and one label per test are in `reports/baseline_tests.json`.

| Label | Original baseline | Meaning |
|---|---|---|
| CLOUD_REAL | 33 passed, 1 failed | Temp SQLite/git, real Python logic and subprocess tests |
| CLOUD_SIMULATED | 4 passed | Manually authored worker changes, fake planner/worker/merge, or fake service response |
| LOCAL_VERIFICATION_REQUIRED | 4 cloud diagnostic failures | Three AGY B availability assumptions and one namespace-dependent REA check; local verification NOT_TESTED |

The cloud runner now explicitly skips those four local cases with reasons. It
does not modify assertions or mark failures xfail. Six added scaffold tests
exercise missing cases, zero tests, unexpected skips, changed exception types,
new failures and setup errors. The current result is in
`reports/stage_0_tests.json`; local skips are not successful local verification.

For an incremental CI regression check:

```bash
.venv/bin/python scripts/cloud_test.py --compare-baseline --report /tmp/acs-tests.json
```

The original Stage 0 comparator allowed a known failure. After repairing it,
the continuation tightened the gate: it now requires pytest exit 0 as well as
no regression. JSON always preserves
`pytest_exit_code`, each outcome, label and regressions. Missing baseline tests,
new failures, changed exception types, unexpected skips, collection failures and
empty runs fail the comparison. The original baseline remains immutable as
historical evidence, but its prior failures cannot excuse a current failing
pytest run. Local-only skips remain pending local verification, so cloud passing
results still do not establish full operational acceptance.

The runner redirects tilde expansion before application imports to a disposable
directory; it leaves HOME unchanged. It uses a disposable current directory,
tempfile root and pytest basetemp, disables the pytest cache, and disables user
and system Git configuration in the test process. Its socket patch permits
only the existing test API at loopback port 20135; it blocks the operational
daemon and gateway. It does not start real workers. This is scoped test
instrumentation, not a worker sandbox or an application configuration feature.
The existing API test still has a fixed port and a sleep: V2.3 must replace
those with a random port and readiness synchronization in a justified test fix.

Direct `pytest tests/` still has import-time home-directory writes in the
application and ambient service/config reads. Prefer the cloud runner until
portable `ACS_HOME` configuration and isolated fixtures are implemented.

The runner registers `unit`, `integration`, `security`, `failure_injection`,
`simulated`, `local_only`, `slow`. It applies `simulated` and `local_only` to
known cases using the baseline metadata. Comprehensive marker coverage and
dedicated runnable local sandbox/worker tests are later-stage work; the legacy
availability assertions are not a real worker verification harness.

## Static analysis and supply chain

`cloud_static.py` runs Ruff's explicit E4/E7/E9/F profile, mypy with
`config/mypy.ini`, and detect-secrets with live credential verification disabled.
The analysis profile covers `acs_team`, root tests and new cloud scripts;
secret candidate scanning covers tracked and nonignored files, including the
bridge and companion, excluding real `.env` files and the scanner's own JSON
baseline (which contains fingerprints). It never tests credentials. Only
candidate metadata and fingerprints are retained; candidate status is not a
claim that any credential is real or active.

The scoped original-code debt is 99 Ruff findings and 13 mypy errors in 7 files.
`reports/baseline_static.json` stores actionable file/line/code details. No new
scaffolding finding is allowed. Historical debt remains visible and is assigned
to V2.3; no `noqa` or type ignores were added to application code. Fingerprints
make a changed secret candidate fail even at an existing location. Candidate
line shifts require review, not automatic baseline refresh. The CI scan is a
skeleton for full V2.3 history scanning and pre-commit enforcement.

`requirements/cloud-dev.txt` pins all resolved runtime/test/tool distributions.
Editable projects still use their repository-declared build-backend ranges in
isolated builds; build-backend hash locking is not yet provided. No new runtime
dependency declarations or existing lockfiles changed.

| New direct dev tool | Pin | Purpose | Maintenance/license evidence |
|---|---|---|---|
| Ruff | 0.17.1 | Fast scoped lint regression | PyPI release 2026-10-15; Astral upstream; MIT |
| mypy | 2.4.0 | Existing annotations and new script checks | PyPI release 2026-10-01; Python/mypy upstream; MIT |
| detect-secrets | 1.5.0 | Offline candidate scan without printing values | Yelp upstream commit 5e141933, dated 2026-04-02; release 2024-05-06; Apache-2.0 |

Sources: https://pypi.org/pypi/ruff/json,
https://pypi.org/pypi/mypy/json,
https://pypi.org/pypi/detect-secrets/json and
https://github.com/Yelp/detect-secrets. Versions and metadata were read from the
package registry; detector upstream activity was checked through read-only Git.
These development-tool licenses are compatible with the repository's stated
Apache-2.0 intent; this is not a full license or vulnerability audit. Their
transitive dependencies are pinned in the development requirements file.
Bandit, Semgrep, pip-audit, Hypothesis, Coverage.py and other candidate tools
remain uninstalled and NOT_TESTED; choose them only when later work requires them.

CI uses read-only repository permissions, no secrets, immutable checkout and
Python setup action SHAs, and disables checkout credential persistence. It runs
installation, static comparison and test comparison. GitHub-hosted execution is
NOT_TESTED until the PR workflow actually runs; local execution is evidence for
the commands, not for GitHub Actions itself. No companion extension build or
real provider/MCP/worker test is part of this stage's profile.

For retained full-suite diagnostics, use a NEW private directory:

```bash
.venv/bin/python scripts/cloud_test.py --compare-baseline \
  --retain-dir /tmp/NEW-acs-fixtures --report /tmp/NEW-acs-tests.json
```

This keeps fixture SQLite databases, worktrees and artifacts instead of cleaning
them at exit. Existing/protected destinations are refused before pytest can clear
a basetemp. Keep this directory private; fixed-fixture evidence is not provider
activation. The seeded/scheduled diagnostic runner is
`scripts/reliability_campaign.py`; see `reports/POSTMERGE_ROOT_CAUSE.md` for the
retained failed campaign and deterministic process-guard before/after proof.
Language and explicit performance/resource profiles are described in
`docs/upgrade/VERIFICATION_PROFILES.md`.
