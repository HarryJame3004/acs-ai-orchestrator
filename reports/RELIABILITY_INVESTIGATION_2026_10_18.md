# Current acceptance checkpoint — PARTIAL (2026-10-18)

Latest application source: 0e6b35c; fetch actual remote/PR HEAD before resuming.
Current evidence: [CLOUD_VERIFICATION_2026_10_18.json](CLOUD_VERIFICATION_2026_10_18.json).
Detailed continuation: [NEXT_SESSION_HANDOFF.md](NEXT_SESSION_HANDOFF.md).
Precise open source backlog: [CLOUD_SOURCE_GAPS.json](CLOUD_SOURCE_GAPS.json).
The matrix now indexes all 64 explicit Master acceptance bullets; unreviewed
source bullets remain FAIL. No cloud-complete or authenticated/local pass is claimed.

The false guard-125 defect is root-caused/fixed, with retained failure evidence and
controlled regressions. Later supervisor/discovery and fixture-publication failures
were separately investigated and corrected; see POSTMERGE_ROOT_CAUSE.md,
SUPERVISOR_COMPLETION_RACE.md, RECOVERY_FIXTURE_PUBLICATION.md and CUSTOM_DATABASE_BINDING.md.
Latest 0e6b35c root: 286 passed / 7 local skips (197 real, 89 simulated); bridge 847;
companion 138 / 25 suites plus build; six hosted checks passed at that source.
Latest-source seeds 1337 and 7331 each passed 143 tests / 1 local skip.
Latest-source campaign/CI outcomes are in the current evidence, not inferred here.
Native provider calls now require durable mission admission; uncertain calls block
re-dispatch. No real Core API or native enforceable currency ceiling is confirmed.

Historical report below is preserved as evidence and is superseded by this notice.

# Post-merge investigation — OPEN, release blocked

Remote resume baseline: 12057b30258404bbe333f1a7cd79922bbb50ef6e on both approved
upgrade refs. PR #7 was OPEN, draft, unmerged. The original failure remains
`POSTMERGE_RANDOMIZED_FAILURE.txt`; its database was lost in the earlier session.
No root cause or deterministic reproduction of that failure has been established.

## Evidence retained this session

- Original eight-module command `.venv/bin/python /tmp/acs-randomized-profile.py 1337`
  with observation-only `retain_plugin`, explicit basetemp, showlocals and log file:
  **138 passed, 1 skipped**, exit 0, 44.79 seconds. Application source unchanged
  from resume baseline. Result/error maps plus SQLite backups were captured before
  fixture teardown. `/workspace/acs-evidence/directive-repro/` retains basetemp,
  worktrees, artifacts, audit database copies, pytest log, result maps and JUnit.
- Same eight-module order profile, seed 7331, with production diagnostic changes:
  **138 passed, 1 skipped**, 36.05 seconds. Retained basetemp:
  `/workspace/acs-evidence/directive-repro/instrumented-7331`.
- Focused diagnostics/Guardian/coordination: **31 passed**, 15.01 seconds.
  Command: `.venv/bin/python -m pytest tests/test_verification_diagnostics.py
  tests/test_guardian_verification_failure.py tests/test_coordination.py -q
  --basetemp=/workspace/acs-evidence/diagnostics-focused`.
- Controlled schedules `both-ready`, `t0-first`, `t1-first`: **1 passed each**,
  respectively 5.04, 8.12, 8.35 seconds. All use real production coordination,
  Git, SQLite and sandboxed verification with explicitly fake implementers.
  The original assertions still require one INTEGRATED task, one FAILED task,
  rollback of the failing merge and unchanged user checkout/main.

All campaign results are **CLOUD_SIMULATED** because providers are fixtures.
They do not establish authenticated readiness, and passing repetitions do not
close the original 137/1/1 campaign. One capability-dependent skip remains visible.

## Changes and next experiments

`TeamRunner` now records verification transition metadata (command, workspace,
duration, reason, exit code, counts and label). Failed results/exceptions retain
bounded, redacted, private, signed evidence before integration rollback. Worker
failure audit retains exception class and sanitized reason, and Guardian vetoes
include the actual veto reasons. Tests verify private mode, signature validity,
redaction, persistence after database reopen and exactly one verifier call.
No result is changed, no retry added, no Guardian/security assertion weakened.

`scripts/reliability_campaign.py` makes the eight-module seeded profile reusable.
It refuses existing output directories, uses an isolated credential-free HOME,
retains SQLite snapshots and the full pytest basetemp, and offers event/barrier
controlled postmerge schedules. Example next command, with a NEW destination:

```bash
.venv/bin/python scripts/reliability_campaign.py --seed 1337 \
  --output /workspace/acs-evidence/next-seed-1337
```

Use `--postmerge-only --schedule t0-first|t1-first|both-ready` for controlled
interleavings. These are diagnostic schedules, not a regression proving an old
production defect fixed. Investigate any next failure from the retained error
map, signed verifier output, audit ordering, lease tokens and Git state. Do not
invent a concurrency, subprocess, lease, Guardian or transaction cause in advance.
Release remains blocked until convincing root-cause evidence and a deterministic
regression are available.
