# Local verification requirements

No actual laptop report has been imported. Every item below is
LOCAL_VERIFICATION_REQUIRED / NOT_TESTED unless the user supplies real evidence.

| Check | Status / blocker |
|---|---|
| Linux/Python/git/disk/systemd user environment | NOT_TESTED on laptop |
| Installation drift and existing directory/DB permissions | NOT_TESTED; never auto-chmod live state |
| Codex authenticated task / timeout / cancel / cleanup | BLOCKED: activation/probe and toolchain/auth binding incomplete |
| AGY A authenticated task and profile isolation | BLOCKED: provider role/auth verification incomplete |
| AGY B authenticated task and separate HOME/XDG | BLOCKED: provider role/auth verification incomplete |
| Real bwrap allowed/denied writes, traversal, symlink, network | NOT_TESTED; cloud UID map is read-only/unsupported |
| Real controller key not visible in worker sandbox | NOT_TESTED; cloud HMAC uses fixtures |
| Live DB API snapshot / scratch restore / migration history | NOT_TESTED; cloud fixtures pass |
| User service watchdog / restart / cgroups | NOT_TESTED; no service operation executed |
| Test-instance emergency stop through real supervised workers | NOT_TESTED; fixture persistence/cancellation checks pass |
| Every configured MCP startup/tools/harmless call/permissions/timeout/recovery/visibility | NOT_TESTED; fake protocol harness passes |
| Real multi-agent mission with independent roles and sequential acceptance | BLOCKED on source role/dispatch integration |
| Notification delivery / real terminal dashboard appearance | NOT_TESTED; fake transport/headless rendering pass |

`acsai verify-local --report NEW_FILE` inspects read-only. Review the source before
explicit scratch probes/local-only tests. Legacy availability assertions can fail
until source activation is implemented and never establish authentication by
mere binary presence. `acsai import-local-report --file FILE --output NEW_DIR`
validates untrusted evidence into a private checklist; it does not activate flags
or mark this repository's checklist PASS automatically. Follow LOCAL_DEPLOYMENT_GUIDE.md.
