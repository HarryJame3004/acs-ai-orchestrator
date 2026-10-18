# Upgrade candidate release preparation

No release/tag/version bump or laptop deployment was performed. Package metadata
remains 2.2.0. The candidate contains partial V2.3–V2.6 implementation with explicit
rollout flags and cloud evidence; it is not an accepted production release.

A private committed-source ZIP can be built with:

```bash
python scripts/build_local_bundle.py --output /path/to/new/acs-source-candidate.zip
```

The builder reads committed Git blobs, excludes credential names and symlinks,
preserves executable bits, bounds size, emits a checksum manifest and refuses to
overwrite. It does not package operational state, auto-install or activate anything.
Checksums detect corruption; the unsigned ZIP is not an authenticity signature.
Use reports/FINAL_ACCEPTANCE_REPORT.md and the handoff before deciding what to merge.

The ZIP excludes Git metadata. Use a real checkout of the integration branch for
Git/history regression commands; checksum validation alone does not certify Git
history or activate any runtime component.
