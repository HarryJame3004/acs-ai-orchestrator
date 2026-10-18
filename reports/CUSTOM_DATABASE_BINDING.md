# Explicit controller database binding protection

Provider runtimes already deny exposing default STATE_DIR and authentication
profiles. Inspection found that an explicitly selected controller database outside
STATE_DIR was not added to that runtime's private-path policy. A caller choosing
an overlapping workspace/toolchain could therefore expose the custom database,
including approvals, leases and the new invocation ledger.

The runtime now derives database, WAL and SHM protection from the host mission
context on every call and activation boundary probe. Worker binding validation
uses the same effective policy. This does not mutate a runtime shared across
threads or assume the database uses the default path. Existing sandbox checks
refuse an overlapping bind before an executor is called; they do not mask a
sensitive file with a writable replacement or downgrade isolation.

The regression uses a real disposable SQLite database inside an attempted
workspace and then a toolchain. Both attempts fail before any executor call;
leaving the context restores the original policy. No authenticated provider,
real credential or external service is involved. Focused provider/ledger tests:
16 passed before the final probe-policy consistency update; rerun the same suite
and full campaign at the final commit. The preceding c743f45 full root run passed
285 tests with seven local skips and all six hosted checks passed.
