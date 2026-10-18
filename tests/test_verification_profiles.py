"""Real compilers/test runners on trusted fixtures; fake boundary is explicit."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

from acs_team.security import verification_argv
from acs_team.supervision import ProcessSupervisor
from acs_team.verification_profiles import ToolBinding, ToolCatalog, UnsupportedProfile, run_profile


def configure(tmp_path, monkeypatch):
    entries = []
    for name in ('cmake', 'ctest', 'node'):
        path = Path(sys.prefix) / 'bin' / name
        if name in {'cmake', 'ctest'} and path.exists():
            import cmake
            path = Path(cmake.CMAKE_BIN_DIR) / name
        if not path.exists():
            discovered = shutil.which(name)
            assert discovered, f'Install the documented {name} verification toolchain'
            path = Path(discovered)
        path = path.resolve()
        root = Path('/usr') if Path('/usr') in path.parents else (
            Path(sys.prefix) if Path(sys.prefix) in path.parents else path.parent.parent)
        entries.append(ToolBinding(name=name, executable=str(path), root=str(root),
                                   sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    catalog = tmp_path / 'host-toolchains.json'
    catalog.write_text(ToolCatalog(bindings=entries).model_dump_json())
    catalog.chmod(0o600)
    monkeypatch.setenv('ACS_ENABLE_VERIFICATION_PROFILES', '1')
    monkeypatch.setenv('ACS_VERIFICATION_TOOLCHAIN_FILE', str(catalog))
    root = tmp_path / 'project'
    root.mkdir()
    return root, catalog


def trusted_fixture(argv, cwd, **kwargs):
    # Never wired into production. The profile still builds its mandatory
    # sandbox argv; these hardcoded fixtures test its real orchestration and
    # actual compilers/test counts on namespace-restricted CI machines.
    assert '--unshare-all' in argv and '--share-net' not in argv
    assert ['--ro-bind', str(cwd), str(cwd)] == argv[argv.index(str(cwd)) - 1:argv.index(str(cwd)) + 2]
    return ProcessSupervisor().run(argv[argv.index('--') + 1:], cwd, **kwargs)


@pytest.mark.simulated
@pytest.mark.parametrize('mode', ['pass', 'failure', 'skip', 'empty'])
def test_node_requires_actual_nonempty_unskipped_tests(tmp_path, monkeypatch, mode):
    root, _ = configure(tmp_path, monkeypatch)
    if mode != 'empty':
        (root / 'behavior.test.js').write_text(
            "const test=require('node:test'); const assert=require('node:assert/strict');\n"
            + ('test.skip' if mode == 'skip' else 'test')
            + "('value',()=>assert.equal(42," + ('41' if mode == 'failure' else '42') + "));\n")
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    result = run_profile('node', root, executor=trusted_fixture)
    assert result['passed'] == (mode == 'pass'), result
    assert result['provenance'] == 'TRUSTED_FIXTURE_SIMULATION'
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    if mode == 'pass':
        assert result['counts']['passed'] == 1
    if mode == 'skip':
        assert result['counts']['skipped'] == 1


@pytest.mark.simulated
@pytest.mark.parametrize('mode', ['pass', 'failure', 'skip', 'empty', 'build-failure'])
def test_cpp_build_success_is_not_test_success(tmp_path, monkeypatch, mode):
    root, _ = configure(tmp_path, monkeypatch)
    cmake = 'cmake_minimum_required(VERSION 3.20)\nproject(Fixture LANGUAGES CXX)\nenable_testing()\nadd_executable(contract main.cpp)\n'
    if mode != 'empty':
        cmake += 'add_test(NAME value-contract COMMAND contract)\n'
    if mode == 'skip':
        cmake += 'set_tests_properties(value-contract PROPERTIES DISABLED TRUE)\n'
    (root / 'CMakeLists.txt').write_text(cmake)
    (root / 'main.cpp').write_text('not valid C++' if mode == 'build-failure' else
                                  'int main(){return ' + ('1' if mode == 'failure' else '0') + ';}\n')
    result = run_profile('cpp', root, executor=trusted_fixture)
    assert result['passed'] == (mode == 'pass'), result
    assert len(result['stages']) == (2 if mode == 'build-failure' else 3)
    if mode == 'pass':
        assert result['counts']['passed'] == 1
    assert sorted(p.name for p in root.iterdir()) == ['CMakeLists.txt', 'main.cpp']


def test_disabled_unknown_and_absent_performance_profiles_do_not_silently_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv('ACS_ENABLE_VERIFICATION_PROFILES', raising=False)
    with pytest.raises(PermissionError):
        verification_argv(['acs-profile', 'node'])
    monkeypatch.setenv('ACS_ENABLE_VERIFICATION_PROFILES', '1')
    for command in (['acs-profile', 'rust'], ['acs-profile', 'node', '--anything']):
        with pytest.raises(PermissionError):
            verification_argv(command)
    for name in ('rust', 'performance', 'resources'):
        with pytest.raises(UnsupportedProfile):
            run_profile(name, tmp_path)


def test_changed_or_project_supplied_tool_catalog_is_rejected_before_execution(tmp_path, monkeypatch):
    root, catalog = configure(tmp_path, monkeypatch)
    data = json.loads(catalog.read_text())
    next(b for b in data['bindings'] if b['name'] == 'node')['sha256'] = '0' * 64
    catalog.write_text(json.dumps(data))
    with pytest.raises(PermissionError, match='hash changed'):
        run_profile('node', root)
    moved = root / catalog.name
    catalog.rename(moved)
    monkeypatch.setenv('ACS_VERIFICATION_TOOLCHAIN_FILE', str(moved))
    with pytest.raises(PermissionError, match='outside the project'):
        run_profile('node', root)


@pytest.mark.simulated
def test_cpp_profile_flows_through_team_runner_review_guardian_and_integration(tmp_path, monkeypatch):
    import subprocess
    from acs_team.benchmarks import fixture_verification
    from acs_team.coordination import CoordinationStore
    from acs_team.db import DatabaseManager
    from acs_team.schemas import Plan, Review
    from acs_team.team_runner import IndependentTester, TeamRunner
    from acs_team.worker_adapters import BaseWorker
    from acs_team.worktree_manager import WorktreeManager

    root, _ = configure(tmp_path, monkeypatch)
    monkeypatch.setenv('ACS_ENABLE_COORDINATION', '1')
    (root / 'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(Fixture LANGUAGES CXX)\nenable_testing()\nadd_executable(contract main.cpp)\nadd_test(NAME value-contract COMMAND contract)\nset_tests_properties(value-contract PROPERTIES PASS_REGULAR_EXPRESSION "42")\n')
    def implementation(value):
        return '#include <iostream>\nint main(){std::cout << ' + str(value) + ' << "\\n";}\n'
    (root / 'main.cpp').write_text(implementation(41))
    def git(*args):
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    git('init', '-b', 'main')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    git('add', '.')
    git('commit', '-m', 'failing baseline behavior')
    original = git('rev-parse', 'HEAD')
    plan = Plan.model_validate({'mission_id': 'cpp-team', 'requirements': ['Program prints 42'], 'tasks': [{
        'task_id': 'fix', 'title': 'Fix the number', 'description': 'Print 42', 'owns': ['main.cpp'],
        'acceptance_criteria': ['Program prints 42'], 'verification_commands': [['acs-profile', 'cpp']]}]})
    class Worker(BaseWorker):
        def execute_task(self, **kwargs):
            (kwargs['worktree_path'] / 'main.cpp').write_text(implementation(42))
            return {'success': True}
    def prepare(*_):
        return {'tests/test_contract.py': '''import subprocess, tempfile
from pathlib import Path
def test_specification():
    with tempfile.TemporaryDirectory() as home:
        binary = Path(home)/'contract'
        subprocess.run(['/usr/bin/g++','main.cpp','-o',str(binary)],check=True)
        result = subprocess.run([str(binary)],capture_output=True,text=True,check=True)
        assert result.stdout.strip() == '42'
'''}
    def verify(command, workspace, timeout=180):
        argv = verification_argv(command)
        return (run_profile(argv[1], workspace, timeout, executor=trusted_fixture) if argv[0] == 'acs-profile'
                else fixture_verification(command, workspace, timeout))
    def review(task, workspace, implementer, sha):
        return Review(task_id=task.task_id, implementer=implementer, reviewer='reviewer',
                      commit_sha=sha, verdict='PASS', requirement_coverage=task.acceptance_criteria)
    db = DatabaseManager(tmp_path / 'cpp-team.db')
    runner = TeamRunner(CoordinationStore(db), {'worker': Worker('worker')}, IndependentTester('tester', prepare),
                        {'reviewer': review}, WorktreeManager(tmp_path / 'worktrees', min_free_gb=0),
                        tmp_path / 'evidence', 'fixture-cpp-evidence', verification_runner=verify)
    result = runner.run(plan, root)
    assert result['status'] == 'COMPLETED', result['errors']
    assert result['tasks'][0]['state'] == 'INTEGRATED'
    assert git('rev-parse', 'HEAD') == original and git('status', '--porcelain') == ''
    assert any(e['action'] == 'GUARDIAN_APPROVED' for e in db.get_audit_trail('cpp-team'))


def test_verification_refuses_disposable_protected_core_boundary_before_spawn(tmp_path, monkeypatch):
    from acs_team import config, security
    protected = tmp_path / 'protected-core-fixture'
    protected.mkdir()
    marker = protected / 'owner-file'
    marker.write_text('must remain unchanged')
    monkeypatch.setattr(config, 'PROTECTED_PATHS', (protected,))
    monkeypatch.setenv('ACS_ENABLE_VERIFICATION_PROFILES', '1')
    def forbidden(*args, **kwargs):
        raise AssertionError('No subprocess may start for the protected fixture')
    monkeypatch.setattr(ProcessSupervisor, 'run', forbidden)
    # The cloud harness patches only trusted fixed-fixture verification. Exercise
    # the preserved real runtime boundary when running under that harness.
    runtime = getattr(security, '_runtime_verification_under_test', security.run_verification)
    with pytest.raises(PermissionError):
        runtime(['pytest', '-q'], protected)
    for name in ('python', 'cpp', 'node'):
        with pytest.raises(PermissionError, match='protected project'):
            run_profile(name, protected)
    assert marker.read_text() == 'must remain unchanged'


@pytest.mark.simulated
@pytest.mark.parametrize('profile', ['performance', 'resources'])
def test_specialized_python_profiles_execute_only_the_declared_acceptance_directory(tmp_path, monkeypatch, profile):
    from acs_team import security
    from acs_team.benchmarks import fixture_verification
    monkeypatch.setenv('ACS_ENABLE_VERIFICATION_PROFILES', '1')
    directory = tmp_path / 'tests' / profile
    directory.mkdir(parents=True)
    (directory / 'test_acceptance.py').write_text('def test_requirement():\n    assert sum(range(10)) == 45\n')
    # Another project's failing tests must not become a silent profile substitute.
    (tmp_path / 'tests/test_other.py').write_text('def test_other():\n    assert False\n')
    calls = []
    def verify(command, workspace, timeout):
        calls.append(command)
        return fixture_verification(command, workspace, timeout)
    monkeypatch.setattr(security, 'run_verification', verify)
    result = run_profile(profile, tmp_path, 30)
    assert result['passed'] and result['counts']['passed'] == 1
    assert calls == [['pytest', '-q', 'tests/' + profile]]
