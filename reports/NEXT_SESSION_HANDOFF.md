# Resume ACS AI — PARTIAL

Read FINAL_CLOUD_HANDOFF.md, FULL_TEST_EVIDENCE.json,
POSTMERGE_RANDOMIZED_FAILURE.txt, INDEPENDENT_FINDINGS_CLOSURE.md,
REQUIREMENTS.json and docs/upgrade/MASTER_SPEC.md before edits.

Latest tested application source: 511ff9b. Resolve the actual remote/PR #7 HEAD;
later commits may contain documentation/evidence. Keep both approved upgrade refs
fast-forward only; do not merge/push main, touch ACS Core, request credentials,
deploy or weaken security. No background continuation is promised after this turn.

First priority is the unresolved latest seed-1337 postmerge failure. A green root
suite (220 passed / 7 explicit local skips), CI, diagnostic reruns and 16 passing
stress cases do not close it. Retain --basetemp/DB/audit/error maps on reproduction.
Then finish reviewed baseline exceptions/coverage diff, integrated MCP routing/
approvals, provider quota/failover, specialized profiles/learning and per-bullet
original acceptance. Do not redo the nine implemented increments summarized in
the full handoff. All real account/laptop/kernel/deployment gates remain explicit.
