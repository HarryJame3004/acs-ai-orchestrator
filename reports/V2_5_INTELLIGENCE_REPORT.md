# V2.5 checkpoint

Status: PARTIAL. Advisory lessons reuse existing memory/FTS; candidates deduplicate,
verification requires explicit human confirmation or signed matching completed
CLOUD_REAL outcome, correction returns to Candidate, rejection/deprecation/deletion
are supported. Only relevant Verified lessons enter a bounded advisory section;
no policy/approval/scope consumer reads lesson rules. Malicious advisory tested.

Opt-in ACS_ENABLE_INTELLIGENCE=1 connects tracked-file/import/symbol context ranking
to the existing planner, records estimated context size/relevance and measured
worker outcomes, and uses explainable selection after 5 same-label samples.
Neutral deterministic defaults apply below that threshold. Metrics collect runtime,
retry/context/quota/review/test/availability data; selection currently weights
success/test/review/quota outcomes. Exceptional aborts and all failover attempts
are not fully instrumented. Token accounting is a documented bytes/4 estimate.

Strict Pydantic schemas cover plans, results, messages, reviews, failure reports,
Guardian summaries and mission summaries; not every legacy producer uses them.
Team-plan schema repair is bounded at two repairs. Optional multi-solution API
requires explicit configuration, task need and caller-confirmed quota; proposals
share criteria/tests and use isolated mission branches, conservatively sequential.
Quota measurement/provider role wiring and full multi-solution E2E remain gaps.

CLOUD_REAL/CLOUD_SIMULATED suite: 117 passed, 4 explicit local skips; 101 real,
16 simulated, zero failures/regressions. Static comparison: zero new findings;
95 existing Ruff, 12 mypy, 15 known candidates. Test-only correction 34d2a35
replaces an invented merge SHA with the actual fixture commit, assertions retained.

Golden full corpus: 12/12 deterministic fake-worker missions passed in 35.864s,
including Python, debugging, refactoring, web WSGI, test generation, docs,
multi-file API/model, security, real C++ compilation, JSON contracts, two-worker
coordination and confirmed-expiry recovery. This validates the harness only:
reports/golden_fake_full.json is CLOUD_SIMULATED, not provider scoring or claimed
performance improvement. Smoke reruns are in the regression suite. `acsai bench
run --suite smoke|full --workers fake` uses disposable repos; baseline comparisons
reject missing cases and pass regressions. `--workers real` honestly emits BLOCKED
with LOCAL_VERIFICATION_REQUIRED until provider role probes are implemented.
