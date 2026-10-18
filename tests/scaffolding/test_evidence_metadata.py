"""Finite checksummed evidence review cannot authorize changed data or paths."""
import hashlib
from pathlib import Path

from acs_team.evidence_metadata import REVIEWED_EVIDENCE_SHA256, public_checkpoint, reviewed_evidence


def test_exact_reviewed_fixture_bytes_only():
    root = Path(__file__).resolve().parents[2]
    assert len(REVIEWED_EVIDENCE_SHA256) == 5
    for name in REVIEWED_EVIDENCE_SHA256:
        data = (root/name).read_bytes()
        assert reviewed_evidence(name, data)
        assert not reviewed_evidence(name, data+b'\ncredential=unreviewed-value')
        assert not reviewed_evidence('reports/unreviewed.json', data)


def test_public_commit_exception_requires_exact_field_file_and_known_git_commit():
    commit = 'a'*40
    fingerprint = hashlib.sha1(commit.encode()).hexdigest()
    name = 'reports/CLOUD_VERIFICATION_2026_10_18.json'
    line = f'  "tested_source_commit": "{commit}",'
    assert public_checkpoint(name, line, fingerprint, {commit})
    assert not public_checkpoint(name, line, fingerprint, set())
    assert not public_checkpoint(name, line.replace('tested_source_commit','token'), fingerprint, {commit})
    assert not public_checkpoint(name, line, 'wrong-fingerprint', {commit})
    assert not public_checkpoint('reports/other.json', line, fingerprint, {commit})
