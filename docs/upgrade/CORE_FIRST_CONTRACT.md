# Personal Core-first architecture and optional v1 handoff

ACS Core is the primary free-first executor for ordinary jobs, repository work,
tests and retries. ACS AI supplies optional bounded intelligence and returns
advice for Core to validate and execute. This repository never modifies, launches,
queries operational state from, or configures the separate ACS Core system.

`acs_team.core_handoff` defines an **ACS AI-owned proposed interface**, not a
claim about an existing Core API. No Core endpoint, authentication method or
transport is assumed. Real Core integration remains disabled and unverified until
its owner confirms an actual compatible interface. A Core-side fake in
`tests/test_core_handoff.py` exercises the real SQLite-backed service.

## Safe default and compatibility

`EscalationPolicy` defaults to disabled and zero budget. Ordinary work and
insufficiently evidenced repeated failures return `CONTINUE_CORE`, without
constructing a worker or invoking a provider. The file-based command is:

```bash
acsai core-handoff --request /path/to/owner-reviewed-request.json
```

It prints versioned `CoreHandoff` JSON. An explicitly enabled policy can be passed
with `--policy`; without a validated bounded analyzer the result is `BLOCKED`
and the command exits 2. It never guesses a Core API or silently substitutes a
paid coding team. Both `CONTINUE_CORE` and `BLOCKED` leave execution with Core.
The command stores only its own contract ledger in the ACS AI database.

Existing `run`, `plan`, `-m` and opt-in coordinated/daemon execution are retained
as **explicit direct AI compatibility operations**. They may consume provider
quota; they are not the recommended ordinary Core-first entry point. Installing,
preflight, help and this default handoff do not launch them. Do not use an ACS AI
daemon as a replacement for the existing Core executor.

## Requests, authorization and accounting

The strict v1 request includes `request_id`, `core_job_id`, reason, failed-attempt
count, failure fingerprint, bounded sanitized context, SHA256 evidence references,
maximum charge in integer micro-USD and absolute expiry. Accepted reasons are
ordinary work, repeated failure, complex planning and important review. Repeated
failure requires both a fingerprint and the configured count (default three).
Context/evidence are untrusted data, not authorization or executable commands.

A host policy controls the lifetime total budget, per-request maximum, maximum
attempts per job (default two; at most three), timeout (at most 300 seconds) and
approval threshold. High-risk requests and costs at/above the threshold require
an approved `HumanApprovalGate` record bound to the exact request SHA256, Core job
identifier and `core-escalation-v1:<digest>` action. The model cannot approve it.
The owner must obtain this exact approval **before submitting** the request.

A synchronous-FULL SQLite transaction reserves the entire ceiling before calling
an adapter. Competing requests serialize budget/attempt checks. Completed,
failed, invalid and timed-out calls consume the entire ceiling conservatively;
there are no automatic refunds. `CEILING_CHARGED_NOT_METERED` is **reservation
accounting, not a measured provider invoice**. Ordinary/denied calls consume zero.
A saved response replays without another call; changed content under the same ID
is rejected. Policy/approval changes require a new request identifier. A crash
leaving RESERVED returns an uncertain-outcome block and never auto-redispatches.
No unattended reconciliation can re-spend that reservation.

## Adapter boundary and return to Core

`BoundedAnalyzer` is a trusted host adapter protocol. It must enforce a real
provider charge ceiling, timeout/cancellation and owned process cleanup outside
model control. Estimates or self-reported usage cannot establish a hard ceiling.
The existing native CLIs do not yet provide a validated hard monetary ceiling,
so **no native paid analyzer is connected**. Do not implement an adapter by
setting a capability boolean or trusting a model's cost claim. This is an explicit
unsupported boundary, not authenticated provider success or complete integration.

The adapter returns strict `AnalysisAdvice`: summary, bounded proposed steps,
request-contained evidence references and mandatory human review. The service
rejects unrelated evidence, credential-like data and late responses, and returns
`REVIEW_THEN_RESUME_CORE`. Advice never grants tools, permissions, merges or a
Guardian exemption. Core must independently validate the advice against its own
job, evidence, approvals and execution policy before resuming. Adapter failures
return control with BLOCKED and do not automatically retry another paid provider.

Cloud tests cover ordinary work, defaults, budget exhaustion across jobs/restarts,
exact approvals, malformed/unsafe requests, idempotency, concurrent replay,
uncertain crash reservation, failed calls, late/hostile advice and the real CLI.
Provider responses are **CLOUD_SIMULATED**. Real Core compatibility, native paid
billing enforcement and authenticated acceptance are not claimed.
