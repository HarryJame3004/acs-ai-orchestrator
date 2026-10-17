# Overnight continuation preflight

The user asked for prerequisite analysis before starting a long unattended task.
The original full specification is retained verbatim in
`docs/upgrade/MASTER_SPEC.md`; read it with AGENTS.md and PROGRESS.md. The latest
user instruction explicitly permits safe continuation across stages and separate
dependent branches even before earlier PRs merge. It overrides the original
one-stage-per-task/merge-wait convention. Never merge, push to main, force push,
deploy, touch ACS Core, request real credentials or bypass approval requirements.

## Verified current cloud capabilities (CLOUD_REAL)

- 5 CPUs, 32 GiB cgroup memory limit, approximately 29.7 GiB free workspace.
- Python 3.12.14, pytest 9.1.1, Ruff 0.17.1, mypy 2.4.0,
  detect-secrets 1.5.0, Textual 8.2.8, Typer 0.27.3 already installed.
- Git read and stage-branch push work. `refs/pull/1/head` matches Stage 0's
  previous published head; main remains the initial release. PR review/CI state
  cannot be read through the currently blocked API.
- PyPI and npm registries return HTTP 200; gcc/g++, make, Node/npm are present.
  The Python SQLite module needs no database server. CMake and the sqlite3 shell
  are absent but do not block core work; install pinned tools only when needed.
- The original failing CLI test now uses the active interpreter and disposable
  state while preserving all assertions. The installed console entry point is
  repaired. Isolated `acsai --help` succeeds.
- Current suite: CLOUD_REAL 43 passed; CLOUD_SIMULATED 4 passed;
  LOCAL_VERIFICATION_REQUIRED 4 explicitly skipped. Total 47 passed, 4 skipped,
  zero failures, pytest exit 0. The original baseline is preserved.

## One confirmed infrastructure blocker

`api.github.com` is missing from the current restricted network allowlist.
Even an unauthenticated request fails while establishing the HTTPS tunnel:
`Tunnel connection failed: 403 Forbidden`. GitHub REST/GraphQL CLI operations
also fail. Existing GitHub authentication is present; its value was not read or
printed. This is currently a network-policy failure, not evidence of a missing
credential. No new token or laptop secret should be requested.

The cloud configuration draft now adds only `api.github.com` to custom allowed
domains and preserves the package-manager preset. It also saves refreshed
install/start instructions and nonsecret suggested variables:

- ACS_HOME=/workspace/.acs-cloud-runtime
- ACS_BACKUPS_DIR=/workspace/.acs-cloud-backups
- ACS_CREDENTIALS_FILE=/workspace/.acs-cloud-runtime/no-credentials.json

The user must review and save these changes in environment settings and publish
the prepared environment. Saving the draft alone has not applied the policy or
published a snapshot. Keep package registry access enabled in the agent phase.
Do not broaden network access to every host merely for convenience.

After the user applies the settings, retry using existing authentication:

```bash
gh pr view 1 --repo HarryJame3004/acs-ai-orchestrator \
  --json number,state,mergedAt,url,statusCheckRollup
```

An API response then establishes transport access. A subsequent GitHub-specific
permission error must be diagnosed separately; if necessary the user updates
the existing GitHub connection for this repository (PR read/write, contents
write, Actions results read). Do not request a secret in chat. Hosted CI also
requires GitHub Actions to be enabled for PRs; no setting change is needed if
the existing workflow already runs. API failure must not stop independent code
and tests: save a PR body and mark PR automation BLOCKED.

## Stage requirements and who handles them

| Stage | Cloud prerequisites / work | User laptop requirements |
|---|---|---|
| STAGE-1 | Python SQLite backup API, temp WAL databases/git, fake service control; already available | Live backup/staging/deployment only after explicit local approval |
| V2.3 | Temp process trees, pure sandbox policies, redaction, static tools, fixtures | Real Arch namespaces, systemd/watchdog, evidence-key mount exclusion |
| V2.4 | Fake worker scenarios, SQLite claim races, temp git integration; no paid provider needed | Authenticated Codex/AGY A/B and actual isolation checks |
| V2.5 | Validated schemas, local context selection, simulated benchmark harness; add justified pinned deps when required | Real worker scoring, quotas, capabilities and performance measurements |
| V2.6 | CLI/API tests, fixture dry-runs, review import, headless Textual/fake notifications | Actual terminal appearance and desktop delivery |
| STAGE-7 / MCP | Protocol/permission harness against fake servers, bounded integrations, reports/release docs | Real server connectivity/permissions and real multi-agent E2E |

All laptop-column results are LOCAL_VERIFICATION_REQUIRED and NOT_TESTED.
Their absence does not prevent implementing and testing the cloud portions.
Cloud statuses remain PARTIAL or CLOUD_PASS_LOCAL_PENDING as appropriate.

Do not ask the user to install all suggested MCP servers or frameworks. Serena,
Semgrep, Playwright, Context7, GitHub/Filesystem/SQLite MCP and other candidates
must be evaluated for actual gaps, pinned and least-privileged; they are not a
mandatory install-all list. The cloud can add justified development tools using
existing package access. Do not install Docker/systemd or configure a VPN merely
to imitate the laptop. Do not add router keys, real worker logins, a live DB or
ACS Core to cloud. Model gateway/worker credentials are not prerequisites for
the required simulated cloud workflow.

## Starting the unattended task

Once configuration is applied, the user can say:

> Setup is complete. Recheck GitHub API access and continue from PROGRESS.md
> using the original master spec. Use dependent stage branches; do not wait for
> merges or routine confirmation. Record approval-dependent actions as BLOCKED
> and continue safe independent work. Commit and push tested increments, update
> exact labeled results and handoff regularly, and never claim unfinished work
> is complete.

There is no installation that removes execution-time, context or account usage
limits, repository defects, or the need for real laptop verification. Work runs
only while the task is active; do not promise background work after it ends.
Checkpoint tested increments before limits and leave the precise remaining work.
