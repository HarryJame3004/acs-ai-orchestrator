# ACS AI upgrade candidate

[![Cloud regression](https://github.com/HarryJame3004/acs-ai-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/HarryJame3004/acs-ai-orchestrator/actions/workflows/ci.yml)

ACS AI is an experimental local-first coding orchestrator. This dependent upgrade
implements parts of V2.3–V2.6; the package version remains 2.2.0 until acceptance.
It is **PARTIAL, not a production release**. Real Codex/AGY authentication,
independent provider roles, sandbox operation and laptop deployment are unverified.
Real adapters fail closed instead of treating an installed binary as readiness.

This is a personal, single-owner system. **ACS Core is the primary free-first
executor; ACS AI is optional paid intelligence support.** Use the
[Core-first handoff](docs/upgrade/CORE_FIRST_CONTRACT.md) for bounded escalation
and return to Core. Native paid escalation stays disabled until a real charge
ceiling is supported. Existing direct execution commands remain explicit
compatibility operations and can consume provider quota.

For a verified source bundle, use the [personal Arch installation guide](INSTALL.md):
checksum → inspect → `python scripts/personal_install.py --preflight` → install
into a new private prefix → configure/authenticate → explicit local acceptance.
Installation never starts providers or services.

Current evidence and exact gaps are in [progress](docs/progress/PROGRESS.md),
[requirements](reports/REQUIREMENTS.json) and [acceptance](reports/FINAL_ACCEPTANCE_REPORT.md).
Original baseline: 37 passed / 5 failed. Original baselines remain unchanged.

Implemented cloud-tested paths include consistent SQLite backups and staged
migrations, canonical protected paths, commit-bound approval/evidence, non-vacuous
verification, supervised process cleanup, emergency stop, fenced task claims,
independent fixture tests/review, sequential mission integration, advisory lessons,
bounded context, measured scheduling, a 12-case fake-worker benchmark harness,
no-write dry-run, review/escalation artifacts, strict review import, MCP definition
auditing and local verification tooling. See each stage report for limits.

The opt-in coordinated path connects natural-language CLI and daemon dispatch to
Planner, TeamRunner, independent verification/review, Guardian and integration.
Cloud end-to-end tests use explicitly fake provider responses; real account and
kernel acceptance remains pending. Do not enable new runtime flags merely
because cloud tests pass.

```bash
bash scripts/cloud_setup.sh
.venv/bin/python scripts/cloud_test.py --compare-baseline --report /tmp/acs-tests.json
.venv/bin/python scripts/cloud_static.py --report /tmp/acs-static.json
.venv/bin/acsai -m "Fix calculator" --repo /path/to/reviewed/repo --dry-run
.venv/bin/acsai bench run --suite smoke --workers fake --report /tmp/new-smoke.json
```

Dry-run performs no target writes/provider calls. Fake benchmarks validate the
harness; they do not score real providers. Existing `ui`, `status`, `daemon`,
`worker`, `memory`, `approval`, `plan`, `run`, `missions`, `mission`, `mcp`, `repo`
commands and flags remain. New commands are described by `acsai --help`.

Use [LOCAL_DEPLOYMENT_GUIDE.md](LOCAL_DEPLOYMENT_GUIDE.md) for isolated evaluation,
backup and rollout gates. Live activation remains blocked on documented source
and local verification gaps. No cloud task deploys, merges main or rotates credentials.
