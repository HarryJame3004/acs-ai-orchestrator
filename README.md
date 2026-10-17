# ACS AI upgrade candidate

[![Cloud regression](https://github.com/HarryJame3004/acs-ai-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/HarryJame3004/acs-ai-orchestrator/actions/workflows/ci.yml)

ACS AI is an experimental local-first coding orchestrator. This dependent upgrade
implements parts of V2.3–V2.6; the package version remains 2.2.0 until acceptance.
It is **PARTIAL, not a production release**. Real Codex/AGY authentication,
independent provider roles, sandbox operation and laptop deployment are unverified.
Real adapters fail closed instead of treating an installed binary as readiness.

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

The existing `acsai -m` path remains single-task. Coordinated `TeamRunner` is an
opt-in host API and is not yet connected to that path. Do not enable new runtime
flags merely because cloud tests pass.

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
