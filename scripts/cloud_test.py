"""Run the legacy suite with disposable runtime paths; retain its exit status."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
from typing import Any
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "reports/baseline_tests.json"
LABELS = {"CLOUD_REAL", "CLOUD_SIMULATED", "LOCAL_VERIFICATION_REQUIRED"}


@contextmanager
def fixture_directory(retain: Path | None):
    if retain is None:
        with tempfile.TemporaryDirectory(prefix="acs-cloud-tests-") as temporary:
            yield temporary
        return
    target = retain.expanduser().absolute()
    policy = json.loads((ROOT / 'acs_team/defaults.json').read_text())['protected_paths']
    policy += json.loads(os.environ.get('ACS_PROTECTED_PATHS', '[]'))
    policy += [os.environ.get('ACS_CORE_PATH', '~/autonomous-coding-system')]
    for name in policy:
        protected = Path(name).expanduser().resolve()
        if target.resolve() == protected or protected in target.resolve().parents or target.resolve() in protected.parents:
            raise PermissionError('Retained fixture path overlaps a protected project')
    # Never let pytest recursively clear an existing directory via --basetemp.
    target.mkdir(mode=0o700, exist_ok=False)
    yield str(target)


def compare_results(baseline: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[str]:
    """Reject missing tests, new failures/errors and unexpected skips."""
    old = {row["nodeid"]: row for row in baseline}
    new = {row["nodeid"]: row for row in current}
    issues = [f"Missing test: {nodeid}" for nodeid in sorted(old.keys() - new.keys())]
    if not current:
        issues.append("No tests executed")
    for nodeid, row in new.items():
        previous = old.get(nodeid)
        if row["outcome"] in {"failed", "error"}:
            if previous is None or previous["outcome"] != row["outcome"]:
                issues.append(f"New failure: {nodeid}")
            elif previous.get("failure_type") != row.get("failure_type"):
                issues.append(f"Changed failure type: {nodeid}")
        if row["outcome"] == "skipped":
            new_local = previous is None and row.get('label') == 'LOCAL_VERIFICATION_REQUIRED' and len(row.get('local_reason', '')) >= 10
            if not new_local and (not previous or previous["label"] != "LOCAL_VERIFICATION_REQUIRED"):
                issues.append(f"Unexpected skip: {nodeid}")
    return issues


class Capture:
    def __init__(self, policy: dict[str, dict[str, Any]]) -> None:
        self.policy = policy
        self.results: dict[str, dict[str, Any]] = {}

    def pytest_configure(self, config: Any) -> None:
        for marker in ("unit", "integration", "security", "failure_injection", "simulated", "local_only", "slow"):
            config.addinivalue_line("markers", f"{marker}: see TESTING.md")

    def pytest_collection_modifyitems(self, items: list[Any]) -> None:
        for item in items:
            label = "CLOUD_SIMULATED" if item.get_closest_marker("simulated") else "CLOUD_REAL"
            local = item.get_closest_marker('local_only')
            if local and item.nodeid not in self.policy:
                reason = local.kwargs.get('reason', '')
                if not isinstance(reason, str) or len(reason) < 10:
                    raise ValueError('New local-only tests require an explicit local capability reason')
                self.policy[item.nodeid] = {'label':'LOCAL_VERIFICATION_REQUIRED', 'local_reason':reason}
            policy = self.policy.setdefault(item.nodeid, {"label": label})
            if label == "CLOUD_SIMULATED" and policy["label"] != "LOCAL_VERIFICATION_REQUIRED":
                self.policy[item.nodeid] = policy = {"label": label}
            if policy["label"] == "LOCAL_VERIFICATION_REQUIRED":
                item.add_marker(pytest.mark.local_only)
                item.add_marker(pytest.mark.skip(reason=policy["local_reason"]))
            elif policy["label"] == "CLOUD_SIMULATED":
                item.add_marker(pytest.mark.simulated)

    def pytest_runtest_logreport(self, report: Any) -> None:
        if report.when == "call" or (report.when != "call" and report.outcome != "passed"):
            outcome = "error" if report.failed and report.when != "call" else report.outcome
            self.results[report.nodeid] = {
                "nodeid": report.nodeid,
                "label": self.policy.get(report.nodeid, {}).get("label", "CLOUD_REAL"),
                "outcome": outcome,
            }
            if self.policy.get(report.nodeid, {}).get('local_reason'):
                self.results[report.nodeid]['local_reason'] = self.policy[report.nodeid]['local_reason']
            if report.failed:
                message = report.longrepr.reprcrash.message
                self.results[report.nodeid]["failure_type"] = message.split(":", 1)[0].split()[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--compare-baseline", action="store_true")
    parser.add_argument("--retain-dir", type=Path, help="NEW private directory retaining DB/worktrees/fixture logs")
    args = parser.parse_args()
    baseline = json.loads(BASELINE.read_text())
    capture = Capture({row["nodeid"]: row for row in baseline["tests"]})
    start = time.monotonic()
    real_expanduser = os.path.expanduser
    real_connect = socket.socket.connect
    real_bind = socket.socket.bind

    with fixture_directory(args.retain_dir) as temporary:
        scratch = Path(temporary)

        def expanduser(path: Any) -> Any:
            if isinstance(path, str) and (path == "~" or path.startswith("~/")):
                return str(scratch / "user") + path[1:]
            return real_expanduser(path)

        allowed_endpoints = {("127.0.0.1", 20135)}

        def bind(sock: socket.socket, address: Any) -> Any:
            if isinstance(address, tuple):
                if address[0] not in {"127.0.0.1", "::1"}:
                    raise PermissionError("Cloud test servers must bind loopback")
                result = real_bind(sock, address)
                endpoint = sock.getsockname()
                allowed_endpoints.add((endpoint[0], endpoint[1]))
                return result
            if not isinstance(address, str) or scratch not in Path(address).resolve().parents:
                raise PermissionError("Cloud test Unix sockets must be disposable")
            return real_bind(sock, address)

        def connect(sock: socket.socket, address: Any) -> Any:
            # Only the suite's disposable local HTTP server may be contacted.
            if not isinstance(address, tuple) or address[:2] not in allowed_endpoints:
                raise PermissionError("Cloud tests cannot contact operational services")
            return real_connect(sock, address)

        previous_cwd = Path.cwd()
        sys.path.insert(0, str(ROOT))
        try:
            os.chdir(scratch)
            with patch("os.path.expanduser", expanduser), patch("tempfile.tempdir", temporary), \
                 patch("socket.socket.connect", connect), patch("socket.socket.bind", bind), patch.dict(os.environ, {
                     "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                 }):
                # All project-executed tests in this harness are fixed temp
                # fixtures, not authenticated/model worker output. Keep this
                # dependency injection in the harness; no runtime escape flag.
                from acs_team.benchmarks import fixture_verification
                from acs_team import security
                runtime_verification = security.run_verification
                with patch('acs_team.security.run_verification', fixture_verification), \
                     patch('acs_team.team_runner.run_verification', fixture_verification), \
                     patch.object(security, '_runtime_verification_under_test', runtime_verification, create=True):
                    exit_code = int(pytest.main([
                        str(ROOT / "tests"), "-q", "-p", "no:cacheprovider",
                        "--rootdir", str(ROOT), "--basetemp", str(scratch / "pytest"),
                    ], plugins=[capture]))
        finally:
            os.chdir(previous_cwd)
            sys.path.remove(str(ROOT))

    results = list(capture.results.values())
    issues = compare_results(baseline["tests"], results)
    report = {
        "schema_version": 1,
        "pytest_exit_code": exit_code,
        "duration_s": round(time.monotonic() - start, 3),
        "counts": dict(Counter(row["outcome"] for row in results)),
        "by_label": {
            label: dict(Counter(row["outcome"] for row in results if row["label"] == label))
            for label in sorted(LABELS)
        },
        "tests": results,
        "regressions": issues,
        "retained_fixture_directory": str(args.retain_dir.absolute()) if args.retain_dir else None,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("counts", "by_label", "pytest_exit_code", "regressions")}))
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # Expose metadata through check annotations when log-download hosts are
        # unreachable. Never publish raw exceptions, source, or captured output.
        for row in results:
            if row["outcome"] in {"failed", "error"}:
                node = row["nodeid"].replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")
                print(f"::error title=Cloud test failed::{node} ({row.get('failure_type', 'error')})")
    if args.compare_baseline:
        # The original CLI failure is repaired: current acceptance requires a
        # clean pytest result, even if a historical failure later reappears.
        return 1 if issues or exit_code != 0 else 0
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
