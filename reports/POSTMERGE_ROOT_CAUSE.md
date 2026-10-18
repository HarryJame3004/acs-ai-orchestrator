# Reproduced post-merge failure: premature process-guard cleanup exit

This fixes a demonstrated production defect, not a retry-based disposition.
Candidate readiness remains PARTIAL because other cloud source requirements remain.

## Retained reproduction

At a27de72, the eight-module randomized campaign with seed **20261018** failed:
**142 passed, 1 failed, 1 skipped**, 76.00 seconds. The failing node is the same
postmerge coordination scenario as the historical seed-1337 failure. Both tasks
were FAILED. Unlike the earlier session, basetemp, SQLite, audit, result/error
maps, signed failed verifier artifacts and Git worktrees were retained at:
`/workspace/acs-evidence/new-runner-20261018/`.

Portable evidence is committed under `reports/reliability/seed_20261018_failure/`:
exact failure output, result map, SQLite SQL snapshot, ordered audit, Git graph/
worktree/status records, failed-verifier outcomes and original artifact hashes.
Original signed files/database/worktrees remain unchanged in the retained directory.
All workers in this reproduction are fixtures: CLOUD_SIMULATED, no authentication.

Audit event 4: independent t1 pytest printed **2 passed**, but returned exit **125**,
reason `completed`. Audit event 7: Guardian's independent t0 pytest also printed
**2 passed** and returned **125**. Neither timeout nor a failing assertion caused
these two results. Guardian correctly vetoed unaccepted verification. No task
reached integration; this was not a merge conflict, a lease/fencing rejection or
an SQLite transaction failure. The fixture main/checkout remained unchanged.

## Root cause and deterministic old-code failure

Both copies of `process_guard.py` had a two-second wall-clock cleanup cutoff.
The loop checks waitpid, then signals owned descendants, then checks that cutoff.
A scheduling delay in this interval can cross two seconds after a descendant has
already exited but before the next waitpid. The helper returns 125 without reaping
that ready child or propagating its already-successful primary worker result.
This is a false execution failure and can also relinquish subreaper ownership early.

`tests/test_guard_cleanup_race.py` uses real forks, adoption, SIGTERM/SIGKILL and
waitid(WNOWAIT), with a controlled clock advance after a descendant becomes
waitable. The exact original guard copies both fail with **125 instead of 0**:
`deterministic_before.txt` preserves **2 failed**, 2.61 seconds. This is direct
old-code evidence of the erroneous transition, not an assertion weakened to green.
An earlier draft diagnostic used an incorrect bridge path; that harness typo was
corrected before this two-copy demonstration. Its log remains outside the repo.

The earlier seed-1337 database was lost, so its precise historical scheduling
interval cannot be established. The retained later failure has the same symptom,
proves false 125 verification outcomes, and the controlled regression establishes
a production path producing those outcomes. Do not claim forensic access to the
missing original database or that every possible exit 125 has the same cause.

## Fix and security/resource invariants

Normal helper exit now requires waitpid to establish ECHILD, preserving ownership
until descendants are reaped. It still signals only its own birth-validated tree,
sends TERM then KILL, and propagates genuine worker failures/signals. The outer
supervisor's invocation deadline, cancellation and owned-tree termination policy
are unchanged. The bridge caller likewise retains its existing communicate timeout
and escalation. No worker is rerun and no test result is converted to success.
A kernel-uninterruptible child may require the outer timeout/kernel recovery;
there is no invented guarantee of instantaneous kernel process termination.

Both stdlib helper copies remain byte-identical. The regression was extended to
actual primary-worker statuses **0, 7 and 125**, across both copies: **6 passed**,
11.66 seconds. A genuine exit 125 remains a failure. Runtime security/recovery plus
the initial two regression cases: **49 passed**, 18.25 seconds. No guard, quality
threshold, HMAC check or postmerge state assertion was disabled or reduced.

Post-fix randomized, stress, full-suite and CI evidence is recorded in the current
session verification report. Passing campaigns alone are not the justification;
the retained failing outcomes, demonstrated stale cleanup check and deterministic
before/after regression are the justification. Remaining reliability boundaries,
including every provider-call crash window and host power loss, are not all closed.
