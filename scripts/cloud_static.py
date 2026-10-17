"""CLOUD_REAL: compare lint/type/secret candidate metadata with the audit baseline."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "reports/baseline_static.json"


def run(arguments: list[str], allowed: set[int]) -> str:
    result = subprocess.run(arguments, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode not in allowed:
        # Tool stderr may contain source or credentials; retain neither in reports.
        raise RuntimeError(f"{arguments[0]} failed with exit status {result.returncode}")
    return result.stdout


def collect() -> dict[str, Any]:
    lint = json.loads(run([
        sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache",
        "--select", "E4,E7,E9,F", "--output-format", "json",
        "acs_team", "tests", "scripts/cloud_test.py", "scripts/cloud_static.py", "scripts/security_scan.py",
    ], {0, 1}))
    lint_rows = [
        {"file": str(Path(row["filename"]).relative_to(ROOT)), "line": row["location"]["row"],
         "code": row["code"], "message": row["message"]}
        for row in lint
    ]
    typed = run([
        sys.executable, "-m", "mypy", "--config-file", "config/mypy.ini",
        "acs_team", "scripts/cloud_test.py", "scripts/cloud_static.py", "scripts/security_scan.py",
    ], {0, 1})
    type_rows = []
    for line in typed.splitlines():
        match = re.fullmatch(r"(.+):(\d+): error: (.+)  \[([\w-]+)\]", line)
        if match:
            type_rows.append({"file": match[1], "line": int(match[2]), "message": match[3], "code": match[4]})
        elif ": error:" in line:
            raise RuntimeError("Unparsed mypy diagnostic")
    # Scan tracked and nonignored files, including newly created source. Never open real .env files.
    files = run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], {0}).split("\0")
    files = sorted({name for name in files if name and not (
        Path(name).name == ".env" or
        (Path(name).name.startswith(".env.") and not name.endswith(".example")) or
        name == "reports/baseline_static.json"
    )})
    secrets = json.loads(run([
        sys.executable, "-m", "detect_secrets", "scan", "--no-verify", *files,
    ], {0}))
    secret_rows = [
        {"file": name, "line": row["line_number"], "type": row["type"], "fingerprint": row["hashed_secret"]}
        for name, rows in secrets["results"].items() for row in rows
    ]
    return {"ruff": lint_rows, "mypy": type_rows, "secret_candidates": secret_rows}


def new_findings(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, list[Any]]:
    # Line movement is not new debt. Keep multiplicity and secret fingerprints
    # so duplicate errors or a changed secret at the same location still fail.
    def identity(row: dict[str, Any]) -> str:
        return json.dumps({k: v for k, v in row.items() if k != "line"}, sort_keys=True)

    findings: dict[str, list[Any]] = {}
    for tool, rows in current.items():
        remaining = Counter(identity(row) for row in previous.get(tool, []))
        findings[tool] = []
        for row in rows:
            key = identity(row)
            if remaining[key]:
                remaining[key] -= 1
            else:
                findings[tool].append(row)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-baseline", action="store_true", help="Explicit audit-only baseline creation")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    current = collect()
    if args.record_baseline:
        BASELINE.write_text(json.dumps(current, indent=2) + "\n")
    previous = json.loads(BASELINE.read_text())
    regressions = new_findings(previous, current)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({
        "label": "CLOUD_REAL", "counts": {k: len(v) for k, v in current.items()},
        "new_findings": regressions,
    }, indent=2) + "\n")
    print(json.dumps({"counts": {k: len(v) for k, v in current.items()},
                      "new_counts": {k: len(v) for k, v in regressions.items()}}))
    return int(any(regressions.values()))


if __name__ == "__main__":
    raise SystemExit(main())
