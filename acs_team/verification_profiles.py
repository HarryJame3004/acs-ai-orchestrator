"""Opt-in language profiles with mandatory sandboxing and real test counts.

Build success alone never establishes tested success. Custom toolchains require
host-owned, hash-bound catalog entries; project/model text cannot select a binary.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import sys
import time
from typing import Literal

from pydantic import Field

from .schemas import Data, parse_data

PROFILES = frozenset({'python', 'cpp', 'node', 'performance', 'resources'})


class UnsupportedProfile(ValueError):
    pass


class ToolBinding(Data):
    name: Literal['cmake', 'ctest', 'cxx', 'node']
    executable: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    root: str = Field(min_length=1, max_length=1024)


class ToolCatalog(Data):
    bindings: list[ToolBinding] = Field(min_length=1, max_length=4)


def verified_tools(workspace: Path, required: tuple[str, ...]) -> dict[str, ToolBinding]:
    if os.environ.get('ACS_ENABLE_VERIFICATION_PROFILES') != '1':
        raise PermissionError('Verification profiles are disabled')
    entries: dict[str, ToolBinding] = {}
    filename = os.environ.get('ACS_VERIFICATION_TOOLCHAIN_FILE')
    if filename:
        path = Path(filename)
        canonical = path.resolve()
        if (path.is_symlink() or not path.is_file() or path.stat().st_size > 8192
                or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077
                or canonical == workspace or workspace in canonical.parents):
            raise PermissionError('Toolchain catalog must be private, bounded and outside the project')
        catalog = parse_data(ToolCatalog, path.read_bytes(), 8192)
        entries = {binding.name: binding for binding in catalog.bindings}
        if len(entries) != len(catalog.bindings):
            raise ValueError('Duplicate tool binding')
    for name in required:
        if name not in entries:
            path = Path('/usr/bin') / ('c++' if name == 'cxx' else name)
            if not path.is_file():
                raise UnsupportedProfile('Required verified tool is unavailable: ' + name)
            executable = path.resolve()
            if Path('/usr') not in executable.parents:
                raise UnsupportedProfile('System tool resolves outside the supported root')
            entries[name] = ToolBinding.model_validate({'name':name, 'executable':str(executable), 'root':'/usr',
                                        'sha256':hashlib.sha256(executable.read_bytes()).hexdigest()})
    verified = {}
    for name in required:
        binding = entries[name]
        path, root = Path(binding.executable), Path(binding.root)
        if (not path.is_absolute() or not root.is_absolute() or path.is_symlink()
                or not path.is_file() or not os.access(path, os.X_OK) or not root.is_dir() or path.stat().st_size > 128 * 1024 * 1024
                or root.resolve() != root or root in {Path('/'), Path('/home'), Path('/root'), Path('/tmp'), Path('/workspace')}
                or root not in path.parents or root == workspace or workspace in root.parents or root in workspace.parents
                or '..' in path.parts or '..' in root.parts):
            raise PermissionError('Unsafe verification toolchain binding')
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != binding.sha256:
            raise PermissionError('Verification toolchain hash changed')
        if not payload.startswith(b'\x7fELF'):
            raise PermissionError('Bind the actual native tool binary, not an unpinned launcher/import wrapper')
        verified[name] = binding
    return verified


def run_profile(name: str, workspace: Path, timeout: float = 180, *, executor=None) -> dict:
    from .aggregate_limits import managed_temporary_directory
    from .config import STATE_DIR, AUTH_TOKEN_PATH, PROTECTED_PATHS
    from .security import run_verification, sandbox_argv
    from .supervision import ProcessSupervisor

    if name not in PROFILES:
        raise UnsupportedProfile('Unsupported verification language/profile')
    if os.environ.get('ACS_ENABLE_VERIFICATION_PROFILES') != '1':
        raise PermissionError('Verification profiles are disabled')
    if not 0 < timeout <= 900:
        raise ValueError('Profile requires a bounded positive timeout')
    workspace = workspace.resolve()
    if any(workspace == path or path in workspace.parents or workspace in path.parents
           for path in PROTECTED_PATHS):
        raise PermissionError('Verification may not bind a protected project or its ancestor')
    if name in {'python', 'performance', 'resources'}:
        selected = ['pytest', '-q']
        if name != 'python':
            directory = workspace / 'tests' / name
            if directory.is_symlink() or not directory.is_dir():
                raise UnsupportedProfile('Explicit tests/' + name + ' acceptance tests required')
            selected.append('tests/' + name)
        return {**run_verification(selected, workspace, timeout), 'profile': name,
                'provenance': 'ACTUAL_PYTEST_PROFILE_NOT_PROVIDER_OUTPUT'}
    required = ('cmake', 'ctest', 'cxx') if name == 'cpp' else ('node',)
    tools = verified_tools(workspace, required)
    if name == 'cpp' and not (workspace / 'CMakeLists.txt').is_file():
        raise UnsupportedProfile('C++ profile requires reviewed CMake/CTest acceptance tests')
    roots = tuple(dict.fromkeys([Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(),
                               *(Path(binding.root) for binding in tools.values())]))
    private_paths = (STATE_DIR, AUTH_TOKEN_PATH, *PROTECTED_PATHS)
    if os.environ.get('ACS_PROVIDER_CONTRACT_FILE'):
        from .providers import load_catalog
        providers = load_catalog(Path(os.environ['ACS_PROVIDER_CONTRACT_FILE']))
        private_paths += tuple(Path(provider.auth_home) for provider in providers.providers)
    started = time.monotonic()
    stages: list[dict] = []
    with managed_temporary_directory(prefix='acs-profile-') as tmp:
        home = Path(tmp)
        (home / 'tmp').mkdir(mode=0o700)
        build = home / 'build'
        if name == 'cpp':
            commands = [[tools['cmake'].executable, '-S', str(workspace), '-B', str(build), '-DBUILD_TESTING=ON',
                         '-DCMAKE_CXX_COMPILER=' + tools['cxx'].executable],
                        [tools['cmake'].executable, '--build', str(build), '--parallel', '2'],
                        [tools['ctest'].executable, '--test-dir', str(build), '--output-on-failure', '--no-tests=error']]
        else:
            commands = [[tools['node'].executable, '--test', '--test-reporter=tap']]
        for command in commands:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                stages.append({'exit_code': -1, 'reason': 'timeout', 'output': '', 'executed': False})
                break
            argv = sandbox_argv(workspace, command, home=home,
                                private_paths=private_paths,
                                read_only_workspace=True, read_only_roots=roots)
            execute = executor or ProcessSupervisor(output_limit=65536).run
            result = execute(argv, workspace, timeout=remaining,
                env={'HOME': str(home), 'TMPDIR': str(home / 'tmp'), 'PATH': '/usr/bin:/bin',
                     'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
            stages.append({**result, 'executed': True, 'command': command})
            if result['exit_code'] or result['reason'] != 'completed' or result.get('truncated'):
                break
    final = stages[-1]
    output = final['output']
    counts = {'passed': 0, 'failed': 0, 'skipped': 0, 'errors': 0}
    if name == 'cpp':
        match = re.search(r'(\d+) tests failed out of (\d+)', output)
        if match:
            counts['failed'], total = map(int, match.groups())
            counts['passed'] = total - counts['failed']
        else:
            # CTest 4.4 omits the redundant zero-failure phrase on success.
            success = re.search(r'^100% tests passed out of (\d+)\s*$', output, re.MULTILINE)
            if success:
                counts['passed'] = int(success.group(1))
        if re.search(r'Not Run|Disabled|Skipped|tests? did not run', output, re.IGNORECASE):
            counts['skipped'] = 1
    else:
        values = {key: int(value) for key, value in re.findall(
            r'^# (tests|pass|fail|cancelled|skipped|todo) (\d+)\s*$', output, re.MULTILINE)}
        counts.update(passed=values.get('pass', 0), failed=values.get('fail', 0),
                      skipped=values.get('skipped', 0) + values.get('todo', 0), errors=values.get('cancelled', 0))
        if values.get('tests', 0) != sum(counts.values()):
            counts['errors'] += 1
    passed = (len(stages) == len(commands) and all(s.get('executed') and s['exit_code'] == 0
               and s['reason'] == 'completed' and not s.get('truncated') for s in stages)
              and counts['passed'] > 0 and not any(counts[k] for k in ('failed', 'skipped', 'errors')))
    return {'executed': True, 'passed': passed, 'counts': counts, 'profile': name,
            'exit_code': final['exit_code'], 'reason': final['reason'], 'output': output,
            'stages': stages, 'tool_bindings': {n: b.model_dump() for n, b in tools.items()},
            'runtime_seconds': time.monotonic() - started,
            'provenance': 'TRUSTED_FIXTURE_SIMULATION' if executor else 'ACTUAL_SANDBOXED_TESTS_NOT_PROVIDER_OUTPUT',
            'memory_enforcement': 'CONFIGURED_AGGREGATE_OR_HOST_DEFAULT'}


def execute(args):
    import json
    result = run_profile(args.profile, Path(args.workspace), args.timeout)
    print(json.dumps(result))
    if not result['passed']:
        raise SystemExit(1)


def register(subparsers):
    parser = subparsers.add_parser('verify-profile', help='Explicit sandboxed language/performance verification')
    parser.add_argument('profile', choices=sorted(PROFILES))
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--timeout', type=float, default=180)
    parser.set_defaults(func=execute)
