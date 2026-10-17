"""CLOUD_REAL: moving existing diagnostics must not hide new debt or secrets."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("cloud_static", Path(__file__).parents[2] / "scripts/cloud_static.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_line_movement_preserves_existing_debt():
    old = {"file": "code.py", "line": 1, "code": "F401", "message": "Unused import"}
    moved = dict(old, line=10)
    assert not module.new_findings({"ruff": [old]}, {"ruff": [moved]})["ruff"]


def test_duplicate_diagnostic_is_new_debt():
    row = {"file": "code.py", "line": 1, "code": "F401", "message": "Unused import"}
    assert len(module.new_findings({"ruff": [row]}, {"ruff": [row, dict(row, line=2)]})["ruff"]) == 1


def test_changed_fingerprint_is_not_a_baselined_candidate():
    row = {"file": "code.py", "line": 1, "type": "Candidate", "fingerprint": "old"}
    assert module.new_findings({"secrets": [row]}, {"secrets": [dict(row, fingerprint="changed")]})["secrets"]
