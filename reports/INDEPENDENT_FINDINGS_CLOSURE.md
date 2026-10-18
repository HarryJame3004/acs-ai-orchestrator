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

# Independent findings closure — partial, original case list missing

Source baseline was verified remotely as d3f87a6b887885dfb026af590b92a7da8d82d3b6.
PR #7 was open, draft, unmerged, targeting main. All six check-run instances at
that baseline succeeded. Those results were not treated as independent closure.

The supplied directive reports 148 passed / 24 failed at bf9e542, but supplies
neither the 24 node IDs nor the original command, traces or environment details.
The repository/attachments search did not recover that list. Exact one-to-one
closure of those 24 failures is **BLOCKED** pending that evidence; no missing
failure IDs or classifications have been invented. The following are current
family-level reproductions, not a claim that all original failures are closed.

| Named concern | Current classification | Reproduction/evidence |
|---|---|---|
| Reaper exit 125 | FIXED_AND_RETESTED for current regression cases | `.venv/bin/python -m pytest tests/test_runtime_security.py -q -k 'guard or supervisor'`: final 7 passed. Existing subreaper handles escaped children and kernels without children files. No 125 observed in these cases. |
| Descendants after controller death | FIXED_AND_RETESTED for current cases | Runtime security and native team `recover` scenario exercise owned cleanup/controller termination. Identity checks remain mandatory; unrelated processes are not killed. |
| Fake coordination unexpectedly BLOCKED | STILL_BROKEN for current randomized reliability finding | Normal root cases pass, but latest seed 1337 postmerge left both tasks FAILED. Passing diagnostics/stress do not close it; see POSTMERGE_RANDOMIZED_FAILURE.txt. Original 24-case mapping remains unavailable. |
| Team E2E | FIXED_AND_RETESTED for current scenarios | `tests/test_team_missions.py`: direct, CLI, daemon, review, recover, escalate, dependent. Exact latest counts are in FULL_TEST_EVIDENCE.json. Providers remain CLOUD_SIMULATED. |
| Worktree imports/install | FIXED_AND_RETESTED for current checkout | `pip check`: no broken requirements. From `/tmp`, absolute `.venv/bin/python -I -c 'import acs_team'` imports installed checkout; `-I -m acs_team._exec_limits 65536 0 0 /usr/bin/true` exits 0. Native team scenarios run child helpers from real linked worktrees. |
| Guardian | FIXED_AND_RETESTED for current cases | Security/coordinated/native team tests preserve negative assertions and exact SHA/HMAC gates. No policy bypass or lowered quality threshold. |
| Worker registry | LOCAL_VERIFICATION_REQUIRED | Direct pytest exposes three unchanged legacy availability failures: registry, all-three registry, explicit worker selection. Empty/unverified provider registry fails closed. Fake readiness must not satisfy these assertions. |
| Model gateway doubles | FIXED_AND_RETESTED for current checkout | Direct pytest gateway case passed. No real endpoint/authentication acceptance is inferred. |
| Namespace portability | ENVIRONMENT_DEPENDENT | Direct pytest production verification and real namespace escape-denial fixture passed in this container. This differs from earlier namespace-limited observations; Arch Linux remains separately LOCAL_VERIFICATION_REQUIRED. |
| CPU-limit timing | FIXED_AND_RETESTED | Concurrent focused run originally returned -15 at its five-second wall deadline. Sequential unchanged run passed. d641fea retains the one-second CPU limit and original signal assertions, allows 30 wall seconds, and additionally requires `reason == completed`; final focused profile 7 passed. |
| CLI/daemon/recovery consistency | FIXED_AND_RETESTED for current scenarios | Seven native protocol routes use the real controller; review/dependency/crash scenarios retain explicit simulated provider classification. Broader crash-boundary/power-loss coverage remains open. |

## Direct test evidence

The isolated direct run used fresh HOME, ACS_HOME, backup directory and absent
credentials, removed inherited ACS_/AGPAIR_ variables, disabled system/global Git
configuration, and ran `.venv/bin/python -m pytest tests -q
--junitxml=/tmp/acs-directive-direct.xml` without cloud harness injection/skips.
Result: **173 passed, 3 failed, 2 skipped**, exit 1. Exact outcomes and failure
messages are retained in `directive_direct_pytest.json`. Source started at d3f87a6;
aggregate-related edits occurred while it ran, so this is diagnostic evidence,
not a clean committed-source acceptance run. Latest stable-source regression is
recorded separately in FULL_TEST_EVIDENCE.json.

The three failures were:

- tests/test_gate3_workers_and_worktrees.py::test_worker_registry_and_banned_flags
- tests/test_gate7_audit_and_reliability.py::test_all_three_workers_in_registry
- tests/test_gate8_natural_language_and_v2_2.py::test_6_explicit_worker_selection

They retain their assertions and original local-verification classification.
The two explicit skips require delegated cgroup execution and authorized real
provider quota. No token, account configuration or local deployment was requested.

## Source corrections in this continuation

- f8faffe: aggregate-enabled dispatch checks repository/state/database and shared
  Git storage; private provider/planner/tester/verification/MCP/legacy/fixture
  scratch is placed inside declared accounting roots. Missing coverage denies
  dispatch. Sampled monitoring is still not a hard filesystem quota.
- d641fea: CPU/wall-time distinction above; effective pytest.ini registers the
  already declared markers, avoiding shadowed pyproject marker configuration.
- a5ec808: evidence file sync, atomic no-overwrite publication, directory sync,
  private artifacts, failure injection and no partial evidence references.
- ecbdbb7: coordinated SQLite connections require synchronous FULL WAL commits;
  legacy NORMAL default retained. Host power-loss recovery is not certified.

Unresolved production requirements remain in the acceptance report/handoff.
Passing these current families does not close missing original case mappings or
all requirements of the Master Prompt.

Additional substantive source findings: c7a86af adds a verified bounded block
filesystem contract and accounted sandbox /tmp; dd07ec7 verifies a bounded
controller/worker parent cgroup. These kernel contracts are simulated in positive
cloud fixtures and deny missing delegation/mounts; actual enforcement is local.
f888349 rejects changes to baseline helpers/constants/configuration and new
collection controls, including ignored conftest files, at worker/integration/final
gates. f461c9d fixes verifier timeout arity and vetoes unexecuted independent
Guardian tests. These are new discovered regressions/requirements, not invented
mappings to the unavailable original 24 failures.

Latest stable source 511ff9b: root 220 passed / 7 explicit local skips. The
seeded-order failure remains open despite two passing diagnostic seed profiles
and 16 passing isolated stress cases. Original failed fixture DB was not retained
after pytest rotation; preserve --basetemp and audit/error maps on next run.
