# Latest internal installation test archive — PARTIAL

Archive source: c743f45, before the later custom database binding correction.
This is an INTERNAL PARTIAL test snapshot, not the final release candidate.
No final RC is issued while cloud-feasible source requirements remain open.

Archive: /workspace/acs-evidence/ACS-AI-c743f45-INTERNAL-PARTIAL-a.zip
Independent second build: /workspace/acs-evidence/ACS-AI-c743f45-INTERNAL-PARTIAL-b.zip
The two ZIPs are byte-identical; 517 files, 5,494,344 source bytes, 1,462,284 ZIP bytes.

SHA256:

e526f6314c7c8a4b82734b938b081af4c280f5512ffa5748bb4e9de18816a350

All archive paths/types were checked before extraction; every manifest hash was
verified. Actual cloud install in a new prefix succeeded, repeat returned
ALREADY_INSTALLED, installed CLI help passed, and dependency audit found zero known
vulnerabilities with two source distributions explicitly skipped (not on PyPI).
No provider mission, authentication, service, deployment or laptop action occurred.
The extraction remains pristine; build products are inside the new prefix only.

Evidence: c743-bundle-a/b.json, c743-cleanroom-install.txt,
c743-cleanroom-repeat.txt and c743-cleanroom-audit.json under /workspace/acs-evidence.
The archive predates the latest source/report commits; rebuild from the finished
source after all source acceptance gates close, not by renaming this snapshot.

Historical archive record follows; it is not the current release.

# Reproducible source archive — PARTIAL candidate

Archive commit: e0c0a6114f8e5c7663f7406d85a6b9c5a89aa725
Application source remains 511ff9b; this archive additionally includes evidence
and the deterministic manifest packaging fix. No automatic activation/deployment.
The unresolved postmerge failure and source acceptance gaps remain open.

Archive: /workspace/acs-ai-artifacts/acs-ai-e0c0a61-partial.zip
Checksum file: /workspace/acs-ai-artifacts/acs-ai-e0c0a61-partial.zip.sha256

SHA256:

2ecc1f5f17f87eb35ba2ed498f4c959da92e3bd878ec7d2f4128fda453c3ebca

Two independent builds of this committed snapshot produced byte-identical ZIPs.
The archive has 485 committed files, 5,317,865 source bytes and 1,393,673 ZIP bytes.
It includes ACS_BUNDLE_MANIFEST.json with per-file digests and the exact commit.
The archive snapshot necessarily predates this external checksum record; later
record-only commits do not alter the packaged application/helper source.

Rebuild with the committed scripts/build_local_bundle.py at the archive commit,
using a new output filename. The regression sets the clock to 2031 and checks
byte equality as well as fixed timestamps, secret/symlink exclusions and refusal
to overwrite existing destinations. Earlier 9676296 ZIPs failed reproducibility
and are superseded; do not use their hashes as this archive's verification.
