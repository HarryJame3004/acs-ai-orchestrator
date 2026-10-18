# Integrated team acceptance evidence

Overall candidate: PARTIAL. Every workflow row below is CLOUD_SIMULATED because
the native provider responses are fixtures. Git, SQLite, pytest, supervision,
Guardian and controller methods execute for real. No authenticated provider or
actual cloud namespace/cgroup success is inferred.

The executable scenario is
`tests/test_team_missions.py::test_native_protocol_natural_language_team_to_signed_integration_and_review`.
Its variants exercise direct service, natural-language CLI, real daemon queue,
dependency delivery, imported review, blocked-review escalation/replanning and
controller-crash recovery. This is the production TeamMissionController/TeamRunner
path; fixtures replace provider responses and the cloud-unavailable namespace
boundary only. The complete test accounting is in continuation_tests.json.

| Master §14 step | Observed source behavior and assertion |
|---|---|
| 1 Accept mission | CLI/daemon/service persist the goal and final mission state |
| 2 Validate tasks | Native planner JSON parses through strict Plan and task-graph validation |
| 3 Record criteria | Stored plan and final review contain actual task criteria |
| 4 Select context | Real selector runs; CONTEXT_SELECTED audit persists |
| 5 Coordinate assignments | Actual SQLite claims and two measured worker assignments |
| 6 Enforce ownership | Actual diff/scope guards execute; separate scope-attack regression denies excess writes |
| 7 Safe concurrency | A two-party implementer barrier requires overlapping executions |
| 8 Structured handoffs | Host-stamped messages persist; dependent third task receives both commit-bound handoffs |
| 9 Specification tests | Separate readonly tester sessions produce pytest artifacts before implementation |
| 10 Independent review | Fresh readonly sessions, host IDs, exact commit/diff and criteria coverage gates |
| 11 Sequential integration | Dedicated Git branch/worktree and serialized crash-released integrator lock |
| 12 Post-integration tests | Real pytest after merges and every declared command at final combined HEAD |
| 13 Guardian | Task and final mission decisions; dashboard records APPROVED only after passing gates |
| 14 Failure escalation | Rejected reviews produce bounded measured escalation; imported review causes validated correction mission and re-execution |
| 15 Evidence | Signed task packages plus whole-mission SHA-bound evidence; final package verifies signature |
| 16 Verified lessons retained | Explicitly human-reviewed fixture lesson is retrieved as advisory context and retained; fake results cannot verify new lessons |
| 17 Mission state | SQLite reaches COMPLETED only after verification and review export |
| 18 Dashboard | Actual runtime projection contains tasks, workers, Guardian, lessons and controller measurements |
| 19 Review package | Private bounded final_review JSON/Markdown and criterion/evidence matrix |
| 20 Completion artifact | completion.json records VERIFIED, exact SHA, evidence and CLOUD_SIMULATED label; local requirements remain explicit |

Crash variant terminates a separate controller after a real merge, before durable
integration completion. Daemon startup reconciles ownership and expired leases,
preserves the interrupted merge, reuses both completed workers and re-verifies.
The seven original provider sessions remain seven; recovery does not repeat them.
Main/HEAD and the original checkout remain unchanged in all completed variants.
Cleanup removes only accepted clean registered checkouts, retaining branches and
evidence; a dirty-worktree assertion demonstrates refusal to discard user data.

This mapping does not certify every Master requirement. The seeded lesson is a
simulated operator-reviewed fixture, not learning proof from authenticated work.
Three provider profiles are invoked across planner/test/review/implementation;
these fixtures do not prove three authenticated accounts. General MCP mission
tool routing/HTTP approvals, all language profiles, full schema migration,
quota/failover accounting and randomized campaigns remain incomplete. See the
final acceptance report and handoff rather than promoting the release to FULL PASS.
