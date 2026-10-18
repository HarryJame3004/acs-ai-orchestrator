# Upgrade configuration

The packaged acs_team/defaults.json mirrors config/defaults.json. Feature flags
are rollout declarations; the implemented runtime switches are environment
variables below, checked explicitly rather than auto-enabled from the JSON.
All new mutating runtime paths are off by default.

- ACS_ENABLE_RECOVERY=1 enables new recovery/migration/staging commands.
- ACS_ENABLE_SUPERVISION=1 selects supervised worker execution with mandatory
  bwrap. Authentication/toolchain mounting still needs local verification.
- ACS_ENABLE_RUNTIME_LIMITS=1 enables ACS_WORKER_MEMORY_MB and
  ACS_WORKER_CPU_SECONDS in that supervised path (zero means no optional cap).
- ACS_ENABLE_EMERGENCY_STOP=1 enables emergency-stop/resume CLI mutations.
  Existing stop state is honored by planner regardless of this CLI switch.
- ACS_ENABLE_MCP_SCOPES=1 requires explicit mission tool/permission allowlists.
- ACS_ENABLE_PERIODIC_BACKUPS=1 enables daemon snapshots; interval is
  ACS_BACKUP_INTERVAL_SECONDS (minimum 60, default 3600). Retention deletion is
  intentionally not automatic.
- ACS_PROTECTED_PATHS is a nonempty JSON list. ACS_CORE_PATH is always protected.
- ACS_WORKER_ENV_ALLOWLIST names explicit extra worker variables. Dangerous
  interpreter/loader controls are rejected. Never pass controller credentials.
- ACS_WORKER_NETWORK=1 explicitly grants supervised worker networking.

Flags for coordination/intelligence/review/notifications/multi-solution and
external MCP in defaults do not imply implementations are operational.
Do not enable an entire release based only on cloud test results.

ACS_ENABLE_COORDINATION=1 enables the host-configured TeamRunner API; it does not
automatically wire the legacy daemon. ACS_ENABLE_INTELLIGENCE=1 enables bounded
context/advisory lessons and measured selection in the existing planner.
ACS_ENABLE_MULTI_SOLUTION=1 additionally permits the explicitly configured
alternatives API; need/quota checks still apply. Real provider role adapters are
unverified. `bench --workers fake` explicitly selects simulation.

ACS_ENABLE_REVIEW_WORKFLOW=1 permits explicit local structured review import;
exports/dry-run are read-only with respect to target repositories.
ACS_ENABLE_DAEMON_EXECUTION=1 enables bounded queued mission dispatch and makes
CLI --bg enqueue only. Actual providers additionally require verified adapters
and ACS_ENABLE_SUPERVISION=1. An ACTIVE durable dispatch is not auto-stolen after
restart. ACS_ENABLE_NOTIFICATIONS=1 allows desktop event-only attempts; HTTPS
provider attempts also require ACS_NOTIFY_NETWORK=1 and an explicitly approved
credential-free ACS_NOTIFY_NTFY_URL. None are enabled automatically.

Security follow-up: worker dispatch has no unsupervised fallback. With supervision
off, real execution is denied. Production verification also always requires bwrap,
independent of rollout flags. The cloud/fake-reference harness injects a trusted
fixture executor explicitly; it is not a runtime configuration escape. All real
provider activation, profile/toolchain and role checks remain blocked.
