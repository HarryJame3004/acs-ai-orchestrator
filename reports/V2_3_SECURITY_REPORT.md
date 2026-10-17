# V2.3 security acceptance

Status PARTIAL. See V2_3_REPORT.md for the original checkpoint and STAGE_7_CHECKPOINT.md
for later hardening. Guardian/path/approval/test/integration checks have cloud
coverage. New process guard now reaps escaped descendants and fast-parent orphans;
bridge lifecycle tests no longer rely on container PID 1. Native MCP file tools
resist symlink/hardlink replacement and bound data. New DBs are private.

Not accepted: real sandbox/network/auth boundaries and worker activation, complete
aggregate CPU/RAM/disk/controller/MCP limits, all recovery races, full static debt
removal and real systemd behavior. Never infer a laptop PASS from fake transports.
