# MCP inventory, supply chain and verification

Existing formats are preserved: native registry; AGY A/B mcp_config.json; plugin
mcp_config.json; Codex plugin .mcp.json and cached tool definitions. Configured,
installed and cached definitions are metadata, not successful protocol/auth probes.
The native registry has real file read/write/list handlers and unavailable binary/
admin placeholders; unavailable handlers never return fabricated success.

`acsai mcp audit` displays hashes of declared catalogs; `--catalog FILE` accepts an
explicit bounded tools object. `--approve --output NEW_FILE` is an explicit local
operator catalog approval. Any raw description/schema change changes the hash and
requires re-approval; descriptions are not privileged instructions. Cache-only
audits remain NOT_TESTED operationally.

config/mcp-policy.example.json starts empty (maximum six servers). Every proposed
server needs an exact version, credential-free HTTPS source, explicit argv/env/tool
allowlists and an approved catalog hash. No latest, shell installer or unpinned
npx/uvx command is accepted. No external server was installed; there is no invented
server version. Protocol implementation reference: MCP stdio JSON-RPC, protocol
2025-03-26, https://modelcontextprotocol.io/specification/2025-03-26.

```bash
acsai mcp audit --catalog /path/to/declared-tools.json
# User-run only after local source/catalog review:
ACS_ENABLE_MCP_EXTERNAL=1 acsai mcp verify --policy /path/to/approved-policy.json \
  --workspace /path/to/sanitized-disposable-fixture --report /path/to/new-mcp-report.json
```

The verification broker uses a read-only bwrap workspace, fresh home, private-path
checks, no network unless explicitly configured, bounded stdio/timeout/cleanup, and
only the exact pre-approved harmless operation. Other calls need a separate
operation approval policy and are refused. This is deliberately incomplete for
arbitrary mission tools/remote writes. Permission/timeout/failure/catalog changes
are tested against fake servers. Real worker visibility, auth, full recovery and
credential boundaries remain LOCAL_VERIFICATION_REQUIRED; one successful call
never upgrades an entire server to operational PASS.

| Candidate | Current decision | Source |
|---|---|---|
| Git / filesystem | Reuse Git CLI and native scoped handlers; no duplicate server | https://git-scm.com/ |
| Memory | Reuse SQLite/FTS memory | Existing acs_team/memory.py |
| SQLite MCP | Not installed; arbitrary live-DB write access prohibited | https://sqlite.org/ |
| Serena / ast-grep / Repomix | Pure Python context selection currently sufficient | https://github.com/oraios/serena / https://ast-grep.github.io/ |
| Semgrep | Not installed; independent security inspection remains useful later | https://semgrep.dev/ |
| Playwright MCP | Not installed; only justified for a real browser project | https://github.com/microsoft/playwright-mcp |
| Context7 | Preserve existing configs; local verification pending | https://github.com/upstash/context7 |
| GitHub MCP | No remote-write integration enabled; operation approvals needed | https://github.com/github/github-mcp-server |

9Router is retained. No LiteLLM/framework replacement was introduced. Adopted
patterns are local SQLite fencing, bounded structured state and isolated worktrees;
no external broker, consensus protocol or ML scheduler was added. Pydantic 2.12.3
and pinned transitives support strict outputs; Click 8.3.0 is needed by bridge tests.
PyPI version metadata for all 34 pinned dependencies had no published advisories
at audit time; this is not a full vulnerability/license audit. See
reports/DEPENDENCY_METADATA_AUDIT.json.

Companion compilation initially failed because three source modules were omitted
by the root state/ ignore rule. They were restored from a pinned, reviewed upstream
snapshot (docs/upgrade/COMPANION_STATE_RESTORATION.md), and 138 tests plus production
bundling pass. esbuild is pinned to 0.28.2 after fixing a LOW Windows development-
server advisory; the final npm lockfile audit reports zero known vulnerabilities.
No IDE installation or deploy script ran.
