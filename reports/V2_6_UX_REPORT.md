# V2.6 checkpoint

Status: PARTIAL. CLI preserves existing commands/flags and adds deterministic
no-write/no-provider dry-run, eight templates, review/escalation export and
bounded structured review intake. Read-only preview shows scopes, dependencies,
criteria, roles, risk, permissions, approvals and explicitly UNKNOWN cost/runtime.
It never grants execution permission. High risk propagates to a human approval
hold at Guardian; terminal/active missions cannot blindly restart via resume.

Review packages validate available commit-bound evidence, redact content, expose
missing coverage as NOT_TESTED, and bound/truncate explicitly. Imported verdicts
are strict versioned data with no commands/permissions, 32 findings/32 KiB limits,
repeated-finding detection and two-round default. Only HIGH/BLOCKER create
mandatory NEEDS_PLANNING items; low findings go to backlog. Nothing auto-executes
or approves based on imported text. Policy override attempts are rejected.

Event-only desktop/explicit opt-in HTTPS notifications are best-effort; real
transport delivery remains LOCAL_VERIFICATION_REQUIRED. Existing Textual layout
now projects persisted mission/task/approval/review/lesson/MCP/failure/DB storage
state, tested headlessly. CPU/memory display explicitly says NOT_MEASURED.

Runtime integration increment: optional bounded daemon dispatcher atomically
claims queued missions, requires verified supervised workers, persists ownership
and retains ACTIVE claims over restarts rather than stealing work. Background CLI
uses the queue without an extra child when this flag is enabled. Default daemon
leaves queued missions queued instead of falsely advancing them to PLANNING.
A flock with PID birth identity prevents duplicate daemons; existing live PID is
not signaled. State transitions use compare-and-set to preserve cancellation.
Authenticated /runtime API has real random-loopback-port tests; request bodies
are bounded and malformed metadata rejected. All configured Core paths and managed
workspace symlinks are checked before repository resolution writes.

Cloud evidence: 133 passed, 4 local-only skips, 0 regressions; CLOUD_REAL 114,
CLOUD_SIMULATED 19 (including headless Textual/notifier/fake daemon planner).
Original parser surface reconstructed from immutable eecbce4 plus actual current
command --help checks; historical full help text was not captured pre-upgrade.

Remaining: natural-language path still uses single-task legacy orchestration;
provider-independent tester/reviewer wiring, complete baseline test update review,
clipboard support, imported task execution/replan workflow, comprehensive
escalation telemetry and every dashboard metric are not complete. Templates are
complete dry-run profiles; execution-side template criteria/roles are not fully
wired. Daemon provider operation/systemd/notification/terminal appearance require
local verification. No deploy, local service operation or main merge performed.
