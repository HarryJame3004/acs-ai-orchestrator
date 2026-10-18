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
