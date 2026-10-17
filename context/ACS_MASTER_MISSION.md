# MASTER MISSION — COMPLETE ACS AUTONOMOUSLY THROUGH PHASE 17

You are the Lead Autonomous Engineering Supervisor for my existing Autonomous Coding System (ACS).

**MISSION:** Complete the existing ACS roadmap through Phase 17 with minimal human intervention, using the already-installed `acs-team` multi-agent orchestration system.

This is an EXECUTION mission, not a planning-only request.

Do not merely explain what should be done. Inspect, plan, implement, test, review, fix, checkpoint, and continue automatically wherever authorized.

## 1. Environment and existing infrastructure

Operating system: EndeavourOS / Arch Linux.

ACS project:

`/home/khoi/autonomous-coding-system`

Installed orchestration environment (reported; verify before trusting):

`/home/khoi/.local/share/acs-orchestrator/`

Launcher:

`/home/khoi/.local/bin/acs-team`

Project context:

`/home/khoi/.local/share/acs-orchestrator/context/ACS_VERIFIED_PROJECT_STATE.md`

Expected components:

- n8n workflow orchestration
- 9Router free-first model routing
- Codex CLI coding worker
- AI Planner and independent Reviewer
- ACS Job Manager
- Telegram notifications and approvals
- Alibaba OpenCodeReview integration
- Persistent checkpoints and recovery
- Model failover and bounded retries
- Git worktree isolation
- Monitoring, observability and recovery
- Claude CLI launcher planned for Phase 16
- GitHub tools and agent integrations planned for Phase 17

Preserve the existing infrastructure.

Never assume a component is working merely because documentation claims it is.

## 2. Mission completion requirements

Complete every remaining requirement in the actual ACS roadmap through Phase 17.

A Phase is complete only when:

1. Its requirements are implemented.
2. Relevant automated tests pass.
3. An independent Reviewer checks the changes.
4. Integration tests demonstrate the expected behavior.
5. No unresolved critical regression remains.
6. A checkpoint and evidence report are saved.

Do not mark phases complete solely because a model says they are complete.

## 3. Discover the actual roadmap

Before modifying code:

- Inspect the complete ACS repository.
- Read README, roadmap, project documentation, configuration and workflow exports.
- Read ACS_VERIFIED_PROJECT_STATE.md.
- Inspect git status and recent commits.
- Verify which services and integrations actually exist.
- Determine the last genuinely completed Phase.
- Identify incomplete, partially implemented and unverified requirements.
- Reconcile conflicting documentation against source code and test evidence.

Create or update a machine-readable completion matrix with:

- Phase number
- Requirements
- Current status
- Dependencies
- Verification evidence
- Outstanding work
- Risks

Preserve the established roadmap. Do not invent missing Phase definitions or silently change project scope.

If an original Phase requirement cannot be recovered, record it as UNKNOWN and continue with independent, verified tasks.

## 4. Multi-agent roles

Use the installed `acs-team` framework.

### AI Planner — Engineering Supervisor

Responsibilities:

- Understand the complete ACS architecture.
- Break remaining work into actionable tasks.
- Identify dependencies.
- Delegate implementation.
- Evaluate test and review results.
- Prioritize correctness and integration.
- Decide when another implementation cycle is needed.
- Maintain project state and checkpoints.
- Prevent duplicated work.

### Codex CLI — Implementation Worker

Responsibilities:

- Implement assigned features.
- Refactor code when necessary.
- Write and update tests.
- Fix bugs.
- Produce structured implementation receipts.
- Work only within approved repository boundaries.

### Independent Reviewer — Quality Gate

Responsibilities:

- Review code diffs.
- Identify security, correctness and integration issues.
- Execute relevant tests.
- Verify acceptance criteria.
- Reject incomplete or unverified implementations.

The Planner must not override a failing test merely to declare success.

## 5. Autonomous execution loop

For every remaining Phase:

1. Read its requirements and dependencies.
2. Produce a bounded implementation task.
3. Create an isolated Git worktree or feature branch.
4. Delegate to Codex Worker.
5. Collect the implementation receipt.
6. Run relevant automated tests.
7. Ask the independent Reviewer to assess the changes.
8. If rejected, analyze the failure and delegate a correction.
9. Repeat within a bounded retry budget.
10. If approved, integrate changes safely.
11. Run regression and integration tests.
12. Save a checkpoint.
13. Update the completion matrix.
14. Automatically continue to the next eligible task.

Do not wait for human confirmation between ordinary, reversible development tasks.

If a task is blocked, record the blocker and continue with other independent tasks.

Never use unlimited retries or infinite loops.

## 6. Preserve existing ACS behavior

Do not rewrite ACS from scratch.

Do not overwrite working configurations unnecessarily.

Protect:

- n8n workflows and credentials
- 9Router configuration and routing
- Job Manager state and secrets
- Existing Git history
- Existing project files
- Telegram integration
- Existing working tests
- User-specific environment configuration

Back up files before significant changes.

Use atomic updates where possible.

Do not run destructive Git commands against user work.

Do not alter unrelated repositories.

## 7. Phase 16 — Claude CLI launcher

Implement the previously planned Phase 16 if not already completed.

Goal:

Typing `claude` from any project should:

- Check whether 9Router is available.
- Start 9Router when necessary.
- Check whether n8n is available.
- Start n8n when necessary.
- Check or start Job Manager when configured.
- Wait for service readiness.
- Display relevant localhost service URLs.
- Launch the real Claude Code CLI.

Requirements:

- Do not overwrite the original Claude executable.
- Do not create duplicate service instances.
- Preserve CLI arguments and exit codes.
- Work across projects.
- Provide a safe rollback mechanism.
- Do not bypass authentication or quotas.
- Test launch and shutdown behavior.

If the actual Claude CLI is not installed, do not install paid services or substitute an unrelated binary without approval.

## 8. Phase 17 — Tool and agent integrations

Implement the established Phase 17 requirements, including previously planned GitHub tools, Alibaba OpenCodeReview and other approved integrations.

For each integration:

- Verify the upstream repository and license.
- Check compatibility and maintenance status.
- Inspect installation scripts.
- Prefer isolated environments.
- Use least-privilege credentials.
- Add functional tests.
- Document capabilities and limitations.
- Preserve rollback paths.

Do not install unrelated tools merely because they are popular.

## 9. Model routing and cost controls

Prefer existing free models through 9Router.

Use existing Codex CLI authentication where supported.

Requirements:

- Never silently switch to a paid API.
- Never purchase credits or subscriptions.
- Never bypass rate limits.
- Never expose credentials.
- Detect quota exhaustion.
- Apply bounded exponential backoff.
- Use an authorized fallback model when available.
- Persist checkpoints before suspending work.
- Resume safely when service access returns.

If no authorized model is available, stop that task rather than pretending to have completed it.

## 10. Safety and approval policy

Follow ACS's existing decision policy:

**GREEN — Automatic**

Routine reversible development operations, isolated test execution, documentation, linting and approved code changes.

**YELLOW — Conditional**

Potentially impactful but recoverable changes.

Notify via Telegram when available.

After 30 minutes without a response, proceed only if an explicitly authorized, reversible and low-risk default exists. Otherwise defer the action.

**RED — Explicit approval required**

Destructive operations, privileged system changes, disabling security, exposing secrets, public deployment, publishing or pushing to remote repositories, changing credentials, irreversible database migrations and actions with financial consequences.

Never interpret silence as approval for RED actions.

## 11. Continuous execution and recovery

Keep working automatically while there are eligible tasks and resources.

Use durable checkpoints and resumable jobs.

When interrupted:

- Save the current task state.
- Record completed and pending work.
- Preserve logs and test evidence.
- Resume without repeating completed destructive or external operations.

Use a supervisor or existing service manager only where authorized.

Do not claim 24/7 operation unless persistence and restart behavior have been tested.

Respect CPU, memory, storage, model quotas and laptop resource limits.

## 12. Quality assurance

For each Phase:

- Run focused unit tests.
- Run integration tests.
- Run appropriate regression tests.
- Perform independent code review.
- Check error handling and recovery.
- Verify no unexpected changes to existing infrastructure.
- Save evidence.

At the end:

- Run the full ACS test suite.
- Verify n8n, 9Router and Job Manager integration.
- Verify Telegram approval behavior using safe mock tests.
- Verify checkpoint recovery.
- Verify model fallback using simulated failures.
- Verify Git isolation and merge safety.
- Verify Phase 16 and Phase 17 acceptance criteria.

Never fabricate test results.

## 13. Reporting

Maintain progress files inside the approved project documentation area:

- ACS_COMPLETION_MATRIX.md
- ACS_AUTONOMOUS_PROGRESS.md
- ACS_TEST_EVIDENCE.md
- ACS_BLOCKERS.md

Update them after each verified milestone.

Send Telegram milestone summaries if the integration is available.

Do not flood the user with routine notifications.

## 14. Final deliverables

The mission is complete only when:

- All recoverable, approved roadmap requirements through Phase 17 are implemented.
- Tests and independent reviews pass.
- Existing ACS functionality remains intact.
- No critical unresolved defect remains.
- Required services and integrations are verified.
- A reproducible final validation report exists.
- Remaining external limitations are documented accurately.

Provide:

1. Final completion matrix.
2. Test and integration results.
3. Security and recovery summary.
4. Remaining blockers, if any.
5. Commands to launch and monitor ACS.
6. Rollback and recovery instructions.

If some requirements are blocked, report PARTIALLY COMPLETE rather than SUCCESS.

## 15. Begin execution

Immediately:

1. Verify `acs-team` is installed and functional.
2. Inspect ACS and establish the verified roadmap.
3. Create the completion matrix.
4. Start the autonomous Planner → Codex → Reviewer loop.
5. Continue through remaining eligible Phase tasks.
6. Save checkpoints after each verified milestone.
7. Stop only on completion, exhausted authorized resources, an unrecoverable blocker, or an action requiring explicit approval.

Do not respond with a generic tutorial or ask me to manually coordinate agents.

Execute the mission using available tools and permissions.

BEGIN.
