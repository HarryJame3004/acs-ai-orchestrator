"""Exact reviewed non-secret evidence blobs; any byte change invalidates review.

The seed fixture contains public Git/artifact/error hashes and disposable worktree
paths, not credentials. This is a finite source-reviewed exception, never a report
folder exclusion. Real raw private evidence remains unchanged outside the checkout.
"""
from __future__ import annotations

import hashlib
import re

# Reviewed against the retained fixture: every flagged value is a disposable
# worktree name, fixture commit, error fingerprint or verifier artifact checksum.
REVIEWED_EVIDENCE_SHA256 = {
    "reports/reliability/seed_20261018_failure/audit.json": "6ace235b46efe05fb698d9895dcfefb4921b752226a3f869f76eda21da4461ae",  # pragma: allowlist secret (public evidence checksum)
    "reports/reliability/seed_20261018_failure/campaign_failure.txt": "45806b66a6978604d540cde75f0b15faffa33145f9f6329f1d9c31201bb10e9d",  # pragma: allowlist secret (public evidence checksum)
    "reports/reliability/seed_20261018_failure/failed_verifiers.json": "954c0e2f397399801d2f4c1a8123d2e0228703e51586c3330a67b6f10fbb375b",  # pragma: allowlist secret (public evidence checksum)
    "reports/reliability/seed_20261018_failure/result.json": "fa3fbcf4a25f4f4e6b020768d396688bea5cdd931d782ccfcea0a0fd54a4856b",  # pragma: allowlist secret (public evidence checksum)
    "reports/reliability/seed_20261018_failure/state.sql": "9e7513596072755b9c3e3f7bda340988dcc5dfaa17d6a2aa79609d871a5ca0a5",  # pragma: allowlist secret (public evidence checksum)
}


def reviewed_evidence(name: str, content: bytes) -> bool:
    expected = REVIEWED_EVIDENCE_SHA256.get(name)
    return expected is not None and hashlib.sha256(content).hexdigest() == expected


def public_checkpoint(name: str, line: str, detector_hash: str, commits: set[str]) -> bool:
    if name != 'reports/CLOUD_VERIFICATION_2026_10_18.json':
        return False
    match = re.fullmatch(r'\s*"tested_source_commit": "([a-f0-9]{40})",?\s*', line)
    return bool(match and match[1] in commits
                and hashlib.sha1(match[1].encode()).hexdigest() == detector_hash)
