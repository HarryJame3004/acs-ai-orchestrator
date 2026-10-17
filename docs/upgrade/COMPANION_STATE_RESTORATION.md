# Companion state source restoration

The original checkout omitted three required TypeScript modules because root
.gitignore's state/ rule also matched companion-extension/src/state/. `npm test`
failed compilation before this correction. Runtime state remains ignored; precise
exceptions now include only these TypeScript source files.

Restored from upstream logicrw/agpair commit 755d4b2 (exact API object verified):
https://github.com/logicrw/agpair/commit/755d4b2e4d9a14871dc66d59ba6fd4bc4a3afa98

- delegationTaskTracker.ts, Git blob prefix 4d11637 (21,057 bytes).
- pendingEventStore.ts, Git blob prefix cfe5fb5 (1,784 bytes).
- taskSessionStore.ts, Git blob prefix 615d4cb (1,450 bytes).

Full blob identities were verified against pinned API metadata before copying.
Existing taskExecutionService.ts and delegationHeartbeat.test.ts blobs exactly
match this upstream snapshot, supporting compatibility. Reviewed source contains
map/state transitions, optional JSON persistence and random delivery IDs, with
no network or command execution. No wholesale vendor replacement occurred.
The tracker retains upstream best-effort persistence; disk-failure/live IDE
semantics need further acceptance. No real IDE/provider operation is implied.

The ordinary npm build script now builds only; its previous hidden rsync into
~/.antigravity/extensions was removed. Packaging no longer auto-installs an
unpinned vsce via npx. Explicit deploy/install commands are local operator actions
and were not run. Stage copying preserves nested source state/ while excluding
root runtime data and generated node_modules/dist/build directories.

After restoration, the tracker snapshot writer was hardened to a random exclusive
0600 temporary file and private new directory before atomic rename. All existing
state/heartbeat/delivery tests remain unchanged. The upstream digest identifies
the reviewed preimage, not this small local hardening change.
