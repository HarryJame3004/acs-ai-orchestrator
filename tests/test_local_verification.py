"""Cloud tests of local tooling do not prove local provider/service operation."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from acs_team.local_verification import import_local_report, verify_local


def test_readonly_local_cli_does_not_initialize_runtime_or_read_credentials(tmp_path):
    root = Path(__file__).parents[1]
    runtime = tmp_path / "runtime"
    credentials = tmp_path / "credentials.json"
    credentials.write_text("not valid JSON and must not be consulted")
    output = tmp_path / "report.json"
    env = {
        **os.environ,
        "ACS_HOME": str(runtime),
        "ACS_BACKUPS_DIR": str(tmp_path / "backups"),
        "ACS_CREDENTIALS_FILE": str(credentials),
    }
    subprocess.run(
        [
            sys.executable,
            "-m",
            "acs_team.cli",
            "verify-local",
            "--repository",
            str(root),
            "--report",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    result = json.loads(output.read_text())
    assert result["schema_version"] == 1 and result["summary"]["error"] == 0
    assert not runtime.exists() and not (tmp_path / "backups").exists()
    assert all(
        c["status"] == "SKIPPED"
        for c in result["checks"]
        if c["id"].endswith("auth_task_cleanup")
    )
    assert credentials.read_text() == "not valid JSON and must not be consulted"


def test_disposable_local_probes_report_unavailable_namespaces_honestly(tmp_path):
    root = Path(__file__).parents[1]
    result = verify_local(root, execute_probes=True)
    checks = {c["id"]: c for c in result["checks"]}
    assert checks["database.snapshot_restore_migration"]["status"] == "PASS", result
    assert checks["emergency_stop.test_state"]["status"] == "PASS"
    assert checks["guardian.fixture_hmac"]["status"] == "PASS"
    assert checks["sandbox.fixture_boundaries"]["status"] in {"PASS", "SKIPPED"}
    assert checks["multiagent.real_e2e"]["status"] == "SKIPPED"
    imported = import_local_report(json.dumps(result).encode(), tmp_path / "imported")
    assert imported["automatic_feature_activation"] is False
    assert (tmp_path / "imported/LOCAL_VERIFICATION_CHECKLIST.md").exists()
    result["summary"]["pass"] += 1
    with pytest.raises(ValueError):
        import_local_report(json.dumps(result).encode(), tmp_path / "bad")
