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
