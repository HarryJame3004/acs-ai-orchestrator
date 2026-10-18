# Supervisor completion observation race

A retained full root campaign reported 279 passed, 1 failed and 7 local skips.
`test_guard_reaps_escaped_orphan_even_when_worker_parent_exits` observed exit 0
with reason `timeout`. Evidence and the complete fixture remain at
`/workspace/acs-evidence/ledger-final-root` and its adjacent JSON/text reports.
This failed campaign is preserved, not replaced by a later green summary.

The supervisor polled the child at loop entry, ran monitor/cancellation work,
then could decide timeout using that old observation. A monitor or scheduling
pause may span child completion. A deterministic real-process regression uses
waitid(WNOWAIT) to observe completion without stealing the exit status and a
controlled monotonic clock to resume beyond the deadline. The old implementation
fails all three cases (actual exit 0, 7 and 125); the correction re-polls before
deciding to terminate and preserves the actual status. It does not rewrite any
nonzero exit or retry execution. A still-running expired child is terminated as
before. Cancellation and output-limit vetoes retain precedence.

The failed historical run did not record the child's precise completion time,
so it cannot prove whether completion preceded that run's deadline. The new
controlled regression establishes the stale-observation production path. This
is a polling supervisor, not a hard real-time kernel deadline guarantee. Existing
outer limits, owned-process identity checks and descendant cleanup remain in place.

See `tests/test_supervisor_completion_race.py`; the before-fix regression output
is retained at `/workspace/acs-evidence/supervisor-race-before.txt`. This issue is
separate from the earlier process-guard false exit 125 documented in
POSTMERGE_ROOT_CAUSE.md. Final verification must cover both corrections together.


## Second production path: slow fallback discovery before reaping

The kernel in this container has no `/proc/self/task/TID/children` files. A
measured fallback process-table scan took 0.58 seconds; another observed scan
under concurrent load took over two seconds. Guard instrumentation reproduced
exit 0/timeout in one of twelve paired calls. It adds an extra discovery for
observation, so its elapsed times are diagnostic, not an uninstrumented benchmark.
The trace recorded TERM, another expensive KILL-discovery pass, and only then
reaping a child whose actual termination status was SIGTERM.

The guard started its 100ms grace before discovery/delivery. A slow TERM scan
could therefore immediately trigger a second scan before waitpid reaped the
already-exited child. The correction starts grace after TERM delivery and checks
waitpid in the next loop before another discovery. It retains KILL escalation
for children which actually ignore TERM; both helper copies remain identical.

The existing six real-process scheduling cases were strengthened to reject that
redundant discovery: all six fail before this correction. After correction,
16 focused cases passed, including real timeout/cancellation/output enforcement,
all three genuine worker statuses across both helpers, and two new TERM-ignoring
adopted-child cases proving KILL and complete reaping. The old five-second orphan
cleanup assertion is unchanged. No failing test was removed or skipped.

A root run after the supervisor poll correction but before this second guard
correction passed 283 tests with seven local skips. It is retained separately at
`/workspace/acs-evidence/guard-ledger-final`; it does not replace the earlier
failed run. Re-run both full root/bridge suites for the final combined source.
