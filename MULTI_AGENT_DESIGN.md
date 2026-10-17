# Coordinated missions

Status: PARTIAL. `TeamRunner` is an opt-in production API, enabled by
ACS_ENABLE_COORDINATION=1; the existing natural-language/daemon path is not yet
wired to it. It accepts strict versioned Pydantic plans, verified worker adapters,
a host-supplied independent tester and independent reviewers. Provider adapters
for those additional roles still need implementation/local verification. Use
`acsai team validate --plan FILE` to validate without execution; `team status`
and `team messages` inspect persisted state read-only.

Plans have bounded tasks/scopes, argv-only verification, acceptance criteria and
a cycle-free dependency graph. Ownership matching is case-insensitive and
conservative for glob intersections; ambiguous patterns serialize. Renames are
checked as removal plus addition. Canonical actual paths reject symlink escapes
and repository controls. Claims coordinate cooperating workers; they do not stop
an OS process from writing outside its scope. Sandbox verification is separate.

SQLite WAL transactions serialize claims across processes and missions sharing a
canonical repository. Tokens increase monotonically. Expired leases cannot
complete, heartbeat or integrate. Recovery requires explicit trusted confirmation
of both worker death and worktree safety; expiration alone never permits takeover.
Heartbeat, process/worktree slots, task states and completion data persist.
Process identity wiring to provider supervision remains incomplete. Duplicate
completion is idempotent only for identical data/current token.

Contracts are canonical-hashed and acknowledged before dispatch. Blackboard is
schema/size/rate-limited, redacted, append-only (SQL triggers), and never supplies
permissions or policy. Independent tests are derived before implementation,
hashed against later alteration, and executed independently. Baseline assertions,
skips/count changes and trivial tests are conservatively rejected; an explicit
review/decision-based exception workflow and coverage tracking remain outstanding.

Review is bound to another worker identity, task, SHA and acceptance criteria.
Guardian runs before merge. Dedicated mission worktrees integrate sequentially,
run all current tests, retain signed merged-commit evidence and roll back only the
owned mission worktree on failure. SQLite's write lock is held through each
integration: safe conservative throughput, not optimized. Crash reconciliation
between Git and SQLite and automatic resumed COMPLETED tasks remain gaps; a
restart conservatively reports BLOCKED rather than blindly re-integrating.

Cloud evidence covers real claim contention/restart/stale tokens, malformed
plans/messages, fake-worker parallelism (barrier), independent tester/reviewer,
Guardian ownership rejection, worker failure, and real Git sequential integration.
Real provider runs are LOCAL_VERIFICATION_REQUIRED. No actual provider was run.
