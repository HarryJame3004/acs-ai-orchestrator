"""Offline, metadata-only scanning of every unique text blob in Git history."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def known_report_metadata(name: str, line: str, detector_hash: str,
                          known_fingerprints: set[str], commits: list[str]) -> bool:
    """Recognize only authentic scanner fingerprints/Git refs in our report.

    Never blanket-exclude reports: unknown values, other fields and source files
    still fail. Match the detector hash as well as the exact field/value identity.
    """
    if name != "reports/stage_7_history.json":
        return False
    match = re.fullmatch(r'\s*"(fingerprint|commit)"\s*:\s*"([a-f0-9]{7,40})"\s*,?\s*', line)
    if match is None:
        return False
    field, value = match.groups()
    if hashlib.sha1(value.encode()).hexdigest() != detector_hash:
        return False
    if field == "fingerprint":
        return value in known_fingerprints
    return any(commit.startswith(value) for commit in commits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    known = json.loads((ROOT / "reports/baseline_static.json").read_text())["secret_candidates"]
    permitted = {(row["file"], row["type"], row["fingerprint"]) for row in known}
    commits = git("rev-list", "--all").decode().splitlines()
    objects: dict[str, tuple[str, str]] = {}
    for commit in commits:
        for entry in git("ls-tree", "-r", "-z", commit).split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            _, kind, sha = metadata.decode().split()
            if kind == "blob":
                objects.setdefault(sha, (raw_name.decode(), commit))
    mapping = {}
    metadata_lines = {}
    skipped = []
    with tempfile.TemporaryDirectory(prefix="acs-history-scan-") as temporary:
        directory = Path(temporary)
        canary = directory / "canary.py"
        # Fixed dummy .invalid URL checks detector execution, never authentication.
        canary.write_text('address = "https://fixture:fixture@example.invalid/path"\n')  # pragma: allowlist secret
        canary.chmod(0o600)
        for index, (sha, (name, commit)) in enumerate(objects.items()):
            filename = Path(name).name
            if name == "reports/baseline_static.json":
                continue  # Scanner's own derived fingerprints, not source credentials.
            if filename == ".env" or (filename.startswith(".env.") and not filename.endswith(".example")):
                skipped.append({"file": name, "reason": "Private environment file requires operator review"})
                continue
            if int(git("cat-file", "-s", sha)) > 4 * 1024 * 1024:
                skipped.append({"file": name, "reason": "Blob exceeds scan budget"})
                continue
            content = git("cat-file", "blob", sha)
            if b"\0" in content:
                continue
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe Git object path")
            target = directory / f"blob-{index}" / relative
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o600)
            mapping[str(target)] = (name, commit)
            if name == "reports/stage_7_history.json":
                metadata_lines[str(target)] = content.decode("utf-8").splitlines()
        scan = subprocess.run([sys.executable, "-m", "detect_secrets", "scan", "--no-verify", "--all-files", str(canary), *mapping],
                              cwd=directory, capture_output=True, text=True, check=True)
        result = json.loads(scan.stdout)
        normalized = {str((directory / name).resolve()): rows for name, rows in result["results"].items()}
        if not any(row["type"] == "Basic Auth Credentials" for row in normalized.get(str(canary), [])):
            raise RuntimeError("Secret scanner self-test failed; refusing a zero-coverage scan")
        candidates = []
        for filename, rows in normalized.items():
            if filename == str(canary):
                continue
            name, commit = mapping[filename]
            lines = metadata_lines.get(filename, [])
            for row in rows:
                line_index = row["line_number"] - 1
                metadata_line = lines[line_index] if 0 <= line_index < len(lines) else ""
                candidates.append({"file": name, "commit": commit[:12], "line": row["line_number"],
                                   "type": row["type"], "fingerprint": row["hashed_secret"],
                                   "known_fixture_or_metadata": (
                                       (name, row["type"], row["hashed_secret"]) in permitted
                                       or known_report_metadata(
                                           name,
                                           metadata_line,
                                           row["hashed_secret"],
                                           {r["fingerprint"] for r in known}, commits,
                                       )
                                   )})
    report = {"label": "CLOUD_REAL", "commits": len(commits), "unique_blobs": len(objects),
              "candidates": candidates, "skipped": skipped,
              "limitations": ["Heuristic text scan; no credential validation", "Scanner fingerprint baseline excluded", "Binary blobs not analyzed"]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    unknown = sum(not row["known_fixture_or_metadata"] for row in candidates)
    print(json.dumps({"commits": len(commits), "candidates": len(candidates), "unknown": unknown, "skipped": len(skipped)}))
    return int(bool(unknown or skipped))


if __name__ == "__main__":
    raise SystemExit(main())
