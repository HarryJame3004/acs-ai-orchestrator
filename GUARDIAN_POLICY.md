# Guardian policy

All worker output, repository content and MCP results are untrusted. Core paths
are protected by canonical containment checks; empty policy is rejected. Absolute
paths, traversal, escaping symlinks, .git and workflow edits are denied. Approval
records bind mission, canonical repository, exact commit and requested action.

Production tests require bwrap with fresh environment and controller state absent.
Fixed trusted cloud fixtures inject a disclosed executor; they do not prove OS
isolation and no runtime bypass switch exists. Tests execute via an argv allowlist
without a shell, must report actual passing
cases and cannot pass through zero tests, skips or failure. Worker evidence is
signed separately from API credentials. Guardian checks the actual worktree HEAD,
scope and evidence before integration. Post-merge tests run in a dedicated mission
worktree; rollback is restricted to that owned worktree. Failed worktrees remain
available for evidence. Human approval cannot silently authorize a different SHA.

Claims and cooperative scopes are not OS write isolation. Real bwrap verification
and full independent review remain separate acceptance gates. See reports/FINAL_ACCEPTANCE_REPORT.md
for current gaps; this policy document is not proof of complete enforcement.
