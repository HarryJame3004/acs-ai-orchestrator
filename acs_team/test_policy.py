"""Conservative baseline-test inspection; findings always require explicit review."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess


def inspect_tests(source: str) -> dict:
    tree = ast.parse(source)
    tests = {}
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.name.startswith("test"):
            assertions = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            checks = [
                n
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
                and (
                    isinstance(n.func, ast.Attribute)
                    and (
                        n.func.attr.startswith("assert")
                        or n.func.attr in {"raises", "fail"}
                    )
                )
            ]
            trivial = (
                not assertions
                and not checks
                or any(
                    isinstance(n.test, ast.Constant) and n.test.value is True
                    for n in assertions
                )
            )
            skips = [
                ast.dump(n)
                for n in ast.walk(node)
                if isinstance(n, ast.Attribute)
                and n.attr in {"skip", "skipif", "xfail"}
            ]
            tests[f"{node.name}:{node.lineno}"] = {
                "name": node.name,
                "assertions": sorted(
                    ast.dump(n, include_attributes=False) for n in assertions
                ),
                "checks": sorted(ast.dump(n, include_attributes=False) for n in checks),
                "skips": skips,
                "trivial": trivial,
            }
    return tests


def baseline_findings(workspace: Path, base_sha: str) -> list[str]:
    names = (
        subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "-z", base_sha],
            cwd=workspace,
            check=True,
            capture_output=True,
        )
        .stdout.decode()
        .split("\0")
    )
    findings = []
    for name in names:
        path = Path(name)
        if not (path.name.startswith("test_") and path.suffix == ".py"):
            continue
        old = subprocess.run(
            ["git", "show", f"{base_sha}:{name}"],
            cwd=workspace,
            check=True,
            capture_output=True,
        ).stdout
        current = workspace / name
        if not current.is_file() or current.is_symlink():
            findings.append(f"{name}: baseline test file removed or replaced")
            continue
        if len(old) > 1024 * 1024 or current.stat().st_size > 1024 * 1024:
            findings.append(f"{name}: test inspection budget exceeded")
            continue
        try:
            before, after = (
                inspect_tests(old.decode()),
                inspect_tests(current.read_text()),
            )

            # Line movement is harmless; preserve each test's assertions and skip state.
            def canonical(tests):
                return sorted(
                    (v["name"], v["assertions"], v["checks"], v["skips"], v["trivial"])
                    for v in tests.values()
                )

            if canonical(before) != canonical(after):
                findings.append(
                    f"{name}: baseline assertions, count or skip state changed"
                )
            if any(v["trivial"] for v in after.values()):
                findings.append(f"{name}: trivially passing test requires review")
        except (SyntaxError, UnicodeError):
            findings.append(f"{name}: cannot inspect baseline tests")
    return findings
