# Security posture

Status PARTIAL. See GUARDIAN_POLICY.md, reports/V2_3_SECURITY_REPORT.md and the
final acceptance report. No claim of complete containment or production readiness.

Protected project roots are nonempty and canonical. Runtime/backup/DB paths cannot
be inside them. Paths reject traversal, escaping symlinks, Git controls and CI
workflow edits. New DBs/files are private; existing installation permissions need
local review. API listeners are loopback-only, authenticated except health, with
bounded JSON bodies. State compare-and-set preserves cancellation.

Production verification code/conftest runs under a mandatory fresh-home bwrap
boundary with no controller key/DB, credential environment or network binds.
Unavailable namespaces fail closed. Explicit fixed-reference benchmark/cloud
fixture executors are test harness dependencies, not runtime escape flags. Legacy
worker dispatch also fails closed until verified.

Evidence is HMAC-bound to commits using a separate private controller key.
Approvals bind mission/repository/commit/action. Guardian runs before integration;
post-merge tests and rollback use an owned mission worktree. Backups use unsigned
checksum manifests: integrity detection, not provenance authentication.

Secret scanning is offline, metadata-only and includes reachable Git history with
a scanner coverage canary. Redaction is applied to logs, common credential formats,
messages, reports and persisted prompts. No regex can guarantee removal of every
unknown secret format; do not supply real credentials or private source to external
notifications/reviews. Notifications send fixed event names only, and never auto-send
source to an AI provider.

MCP defaults deny unknown roles/tools and require explicit permissions/scopes in
strict mode. Native file tools use dirfds/no-follow/type/link/size checks. External
verification is off by default, read-only, exact-operation and catalog-hash gated.
Use minimal server credentials locally; no server was installed by this upgrade.

Remaining HIGH issues include verified provider activation/auth provisioning,
provider role adapters and natural-language coordination integration, full Git/DB
crash reconciliation and aggregate resource limits. Static legacy debt remains.
Real namespace/network/auth isolation, systemd and MCP behavior require laptop
verification. Do not weaken tests, bypass permissions or enable unverified workers
as a workaround. Report security issues privately to the repository maintainer;
this task did not send external messages or change visibility.
