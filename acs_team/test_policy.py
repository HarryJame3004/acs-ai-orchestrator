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


TEST_CONTROL_FILES = frozenset({
    'pytest.ini', '.pytest.ini', 'pyproject.toml', 'tox.ini', 'setup.cfg',
    '.coveragerc', 'conftest.py',
    'CMakeLists.txt', 'CTestConfig.cmake', 'package.json',
})


def baseline_findings(workspace: Path, base_sha: str,
                      independent_files: tuple[str, ...] = ()) -> list[str]:
    """Default-deny changes to baseline tests, their helpers and configuration.

    Assertion AST equality cannot attest fixtures, constants, decorators, helper
    bodies or collection configuration. Reviewed exceptions need a separate
    trusted approval path; this function does not accept model-supplied waivers.
    """
    names = set(subprocess.run(
        ['git', 'ls-tree', '-r', '--name-only', '-z', base_sha],
        cwd=workspace, check=True, capture_output=True, timeout=10,
    ).stdout.decode().split('\0')) - {''}

    def test_related(path):
        return path.suffix in {'.py', '.c', '.cc', '.cpp', '.cxx', '.h', '.hpp',
                               '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx'} and (
            path.name.startswith('test') or path.name.endswith('_test.py')
            or path.stem.endswith(('_test', '.test', '.spec'))
            or any(part.casefold() in {'test', 'tests'} for part in path.parts[:-1]))

    protected = {name for name in names if test_related(Path(name))
                 or Path(name).name in TEST_CONTROL_FILES}
    controls = set(TEST_CONTROL_FILES)
    for name in protected | set(independent_files):
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise PermissionError('Invalid acceptance-test path')
        for parent in path.parents:
            controls.update(str(parent/control) for control in TEST_CONTROL_FILES)

    def current_path(name):
        current = workspace
        for part in Path(name).parts:
            current = current/part
            if current.is_symlink():
                raise PermissionError('Test/configuration path traverses a symlink')
        return current

    findings = []
    for name in sorted(controls-names):
        try:
            if current_path(name).exists():
                findings.append(f'{name}: new verification configuration requires explicit review')
        except PermissionError:
            findings.append(f'{name}: verification configuration path replaced')
    for name in sorted(protected):
        try:
            current = current_path(name)
            if not current.is_file():
                findings.append(f'{name}: baseline test/configuration removed or replaced')
                continue
            size = int(subprocess.run(
                ['git','cat-file','-s',f'{base_sha}:{name}'],cwd=workspace,
                check=True,capture_output=True,timeout=10).stdout)
            if size > 1024*1024 or current.stat().st_size > 1024*1024:
                findings.append(f'{name}: test inspection budget exceeded')
                continue
            old = subprocess.run(
                ['git','show',f'{base_sha}:{name}'],cwd=workspace,
                check=True,capture_output=True,timeout=10).stdout
            with current.open('rb') as stream:
                after = stream.read(1024*1024+1)
            if old != after:
                findings.append(f'{name}: baseline test/helper/configuration changed; explicit review required')
            if Path(name).suffix == '.py' and any(v['trivial'] for v in inspect_tests(after.decode()).values()):
                findings.append(f'{name}: trivially passing test requires review')
        except (PermissionError, SyntaxError, UnicodeError):
            findings.append(f'{name}: cannot safely inspect baseline test/configuration')
    return findings
