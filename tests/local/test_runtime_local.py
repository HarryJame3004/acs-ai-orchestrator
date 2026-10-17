"""User-run namespace checks on disposable fixtures; never operational data."""

import pytest

from acs_team.local_verification import disposable_sandbox_probe


@pytest.mark.local_only(
    reason="Real bubblewrap user namespaces must be available on the local Linux host"
)
def test_real_namespace_write_and_escape_denial(tmp_path):
    status, evidence = disposable_sandbox_probe(tmp_path)
    assert status == "PASS", evidence
