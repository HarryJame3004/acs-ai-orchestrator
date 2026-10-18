# Resume ACS AI — PARTIAL (2026-10-18)

Fetch and inspect actual approved remote refs and PR #7 first. Latest application
source checkpoint in this handoff is 0e6b35c (custom database binding protection);
later commits may contain evidence only. Never merge/push main, touch ACS Core,
deploy, request credentials, weaken assertions or retry uncertain paid calls.
Work continues only in this active session; no persistent automation is scheduled.

## Do not repeat completed work

Read AGENTS.md, docs/upgrade/MASTER_SPEC.md, TEAM_RUNTIME.md, FINAL_ACCEPTANCE_REPORT.md,
CLOUD_VERIFICATION_2026_10_18.json, CLOUD_SOURCE_GAPS.json and the strict acceptance
matrix. Historical snapshots below old report notices do not override this one.

Completed this continuation:

- Root-caused retained postmerge seed-20261018 failure: false guard exit 125 after
  a scheduling delay before reaping. Both helper copies fixed at 84d302f. Original
  seed-1337 DB was lost previously; its precise timing is not retrospectively known.
- Added signed bounded failed-verifier evidence and retained seeded/full campaigns.
- Optional Core-first bounded escalation/handoff, default disabled/zero budget;
  real Core API remains unconfirmed and no native paid analyzer is connected.
- Manifest-verified personal installer and patched pip/build bootstrap; cloud
  setup exercised; actual fresh isolated installs and repeat receipts verified.
- Integrated C++/Node/performance/resource verification profiles with pinned ELF
  toolchains and whole-pipeline supervision. Unsupported profiles fail closed.
- ccad4fd: refresh supervisor completion before timeout, start TERM grace after
  delivery, reap before another expensive fallback discovery. Kernel lacks proc
  children files here. Actual nonzero exits and TERM→KILL escalation stay enforced.
- dbdb0b9: FULL-WAL provider reservations before dispatch, shared call ceilings,
  cross-worker uncertain implementation denial, HMAC-bound readonly result reuse,
  no mutating replay to fresh worktrees, readonly provider-usage CLI.
- 1bb7b7f: finite exact-byte diagnostic metadata review, not blanket secret/report
  exclusions. This is not project test-baseline update authorization.
- c743f45: atomic PID readiness publication in recovery fixture only. Every original
  timeout/kill/cleanup/unrelated-sibling assertion remains. Separate justified commit.
- 0e6b35c: custom controller DB/WAL/SHM cannot enter provider workspace/toolchain
  binds or activation probes. Runtime policy derives per-context, not shared mutation.

## Evidence and failures (preserve all)

Latest 0e6b35c root: 286 passed / 7 local skips, split 197 CLOUD_REAL and
89 CLOUD_SIMULATED. Full bridge after both helper fixes: 847 passed. Companion:
138 passed / 25 suites; production build passed; npm audit zero vulnerabilities.
All six hosted checks passed at 0e6b35c. Latest-source seeds 1337 and 7331
each passed 143 tests / 1 explicit local skip. Exact results/CI are in
CLOUD_VERIFICATION_2026_10_18.json; final documentation HEAD checks are separate. Latest focused provider/ledger binding suite: 16 passed.
Static: Ruff/mypy 0/0, 15 known source candidates, zero new, 16 separately reviewed
metadata findings. Source history through 0e6b35c: 69 commits, 86 candidates,
zero unknown and zero skipped. Rescan the final report-only commit before release.

The earlier failed campaigns remain at:

- /workspace/acs-evidence/new-runner-20261018 (retained DB/audit/worktrees/errors);
  portable proof in reports/reliability/seed_20261018_failure and POSTMERGE_ROOT_CAUSE.md.
- /workspace/acs-evidence/ledger-final-root (279 passed / 1 failed / 7 skips;
  exit 0/timeout investigation), plus supervisor-race-before.txt (3 deterministic
  failures), guard-redundant-discovery-before.txt (6 failures), and guard-observation.
- /workspace/acs-evidence/combined-final-root (284 passed / 1 failed / 7 skips;
  empty JSON marker race), documented in RECOVERY_FIXTURE_PUBLICATION.md.

After guard discovery fix: 16 focused cleanup/security cases passed; instrumented
paired calls improved from 11/12 to 12/12. Instrumentation adds a discovery scan;
those durations are not an uninstrumented performance benchmark. Earlier three
fixed seeded campaigns each passed 143 / 1 local skip; 16 scheduled stress runs
passed. Later campaigns do not erase earlier failures or their specific causes.

The c743f45 internal source archive was built twice identically, manifest-verified,
installed in a new cloud prefix, re-run as ALREADY_INSTALLED, and audited with zero
known vulnerabilities (two local distributions not on PyPI skipped). It predates
0e6b35c and is INTERNAL PARTIAL, not a final release candidate. See SOURCE_ARCHIVE.md.

## Next source work, dependency order

1. Trusted baseline update authorization and accurate baseline/current coverage.
   Exact first inspection command:
   `sed -n '1,220p' acs_team/test_policy.py`
   Then inspect TeamRunner precommit/postintegration baseline checks and the existing
   HumanApprovalGate. Implement owner-reviewed, exact-content/mission/repo/base-bound
   signed decisions in the host control plane, never model-supplied waivers. Preserve
   independent acceptance test immutability and Guardian. Test approved/denied,
   tampered, wrong-repo, changed-content and replay cases. Do not mistake the finite
   scanner-evidence metadata policy for this missing source feature.
2. General bounded MCP HTTP/stdio mission/provider routing with least privilege,
   exact per-operation remote write approval, cancellation/timeouts/untrusted-result
   handling. Existing broker supports only exact preapproved harmless stdio probes.
3. Provider capability/quota/free-first selection and controlled failover with
   accounting across all paths. Session ceilings are not token/currency metering.
   Do not fail over uncertain invocations or wire native CLIs to a monetary-cap
   contract they cannot independently enforce. Native costly analysis stays disabled.
4. Remaining crash-boundary/resource exhaustion, telemetry/outcome lessons,
   specialized/golden profile cases and full original per-bullet acceptance review.
5. Full artifact hash locks/license review, then final clean reproducible archive
   and clean-room verification only after all cloud source requirements pass.

The matrix now indexes all 64 explicit acceptance bullets verbatim. Unreviewed
source criteria stay FAIL; normative paragraph source gaps are listed separately.
Section-level historical status is not acceptance. Missing original independent
24-case IDs must stay BLOCKED rather than be invented. Root owner licensing decision
is unresolved; do not invent a license or change repository visibility.

## Commands and local gates

Setup: `bash scripts/cloud_setup.sh`.
Full cloud: `.venv/bin/python scripts/cloud_test.py --compare-baseline --retain-dir /tmp/acs-resume-NEW --report /tmp/acs-resume-tests.json`
(the retain directory must not already exist).
Seeded: `.venv/bin/python scripts/reliability_campaign.py --seed 1337 --output /tmp/acs-seed-NEW`.
Static: `.venv/bin/python scripts/cloud_static.py --report /tmp/acs-static.json`.
History: `.venv/bin/python scripts/security_scan.py --history --report /tmp/acs-history.json`.
Run focused tests with disposable ACS_HOME, ACS_BACKUPS_DIR and absent ACS_CREDENTIALS_FILE,
or use the full isolated cloud harness; never initialize/read operational state.

Read INSTALL.md and ARCH_LINUX_LOCAL_ACCEPTANCE.md for the actual owner-run sequence:
checksum → inspect → install in NEW prefix → configure/authenticate isolated profiles
→ preflight → explicit activation/verify-team. Enable ACS_ENABLE_PROVIDER_LEDGER=1
alongside the documented native flags. Never launch paid missions during install.
Real Codex/AGY authentication, actual Core API, remote MCP accounts, Arch kernel
cgroup/storage/sandbox and systemd/session appearance remain LOCAL_VERIFICATION_REQUIRED.
These do not excuse the cloud-feasible source gaps above. Overall readiness: PARTIAL.
