"""CLOUD_REAL: ensure the CI regression gate cannot hide missing/broken tests."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("cloud_test", Path(__file__).parents[2] / "scripts/cloud_test.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(outcome="passed", label="CLOUD_REAL", nodeid="example"):
    return {"nodeid": nodeid, "outcome": outcome, "label": label}


def test_missing_and_zero_tests_are_regressions():
    assert module.compare_results([row()], [])


def test_new_failure_is_a_regression():
    assert module.compare_results([row()], [row("failed")])


def test_known_failure_stays_visible_and_improvement_is_allowed():
    assert not module.compare_results([row("failed")], [row("failed")])
    assert not module.compare_results([row("failed")], [row()])


def test_only_explicit_local_checks_may_be_skipped():
    assert module.compare_results([row()], [row("skipped")])
    assert not module.compare_results(
        [row("failed", "LOCAL_VERIFICATION_REQUIRED")],
        [row("skipped", "LOCAL_VERIFICATION_REQUIRED")],
    )


def test_setup_error_does_not_equal_a_known_assertion_failure():
    assert module.compare_results([row("failed")], [row("error")])


def test_changed_exception_cannot_hide_behind_a_known_failure():
    old, new = row("failed"), row("failed")
    old["failure_type"], new["failure_type"] = "FileNotFoundError", "PermissionError"
    assert module.compare_results([old], [new])
