"""Real Git regression fixtures for non-assertion baseline weakening attempts."""
import subprocess

import pytest

from acs_team.test_policy import baseline_findings


@pytest.fixture
def repository(tmp_path):
    root = tmp_path/'repository'
    root.mkdir()
    def git(*args):
        return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True,text=True).stdout.strip()
    git('init','-b','fixture')
    git('config','user.name','Fixture')
    git('config','user.email','fixture@example.invalid')
    files = {'tests/test_contract.py':'EXPECTED = 42\ndef test_value():\n    assert 42 == EXPECTED\n',
             'tests/helpers.py':'def expected():\n    return 42\n',
             'tests/conftest.py':'import pytest\n@pytest.fixture\ndef value():\n    return 42\n',
             'pytest.ini':'[pytest]\ntestpaths = tests\n',
             'calc.py':'def value():\n    return 42\n',
             'tests/value_contract.cpp':'int expected() { return 42; }\n',
             'value.test.js':'test("value", () => assert.equal(value(), 42));\n',
             'tests/helpers.ts':'export const expected = 42;\n',
             'CMakeLists.txt':'enable_testing()\nadd_test(NAME contract COMMAND contract)\n',
             'package.json':'{"type":"commonjs"}\n'}
    for name,content in files.items():
        path = root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content)
    git('add','.')
    git('commit','-m','baseline')
    return root,git('rev-parse','HEAD')


@pytest.mark.parametrize('name,content',[
    ('tests/test_contract.py','EXPECTED = 0\ndef test_value():\n    assert 42 == EXPECTED\n'),
    ('tests/helpers.py','def expected():\n    return 0\n'),
    ('tests/conftest.py','import pytest\n@pytest.fixture\ndef value():\n    return 0\n'),
    ('pytest.ini','[pytest]\ntestpaths = nonexistent\n'),
    ('tests/pytest.ini','[pytest]\npython_files = nothing.py\n'),
    ('pyproject.toml','[tool.pytest.ini_options]\npython_files = ["nothing.py"]\n'),
    ('tests/accept/conftest.py','def pytest_collection_modifyitems(items):\n    items.clear()\n'),
    ('tests/value_contract.cpp','int expected() { return 0; }\n'),
    ('value.test.js','test.skip("value", () => assert.equal(value(), 42));\n'),
    ('tests/helpers.ts','export const expected = 0;\n'),
    ('CMakeLists.txt','enable_testing()\n'),
    ('package.json','{"type":"module"}\n'),
])
def test_baseline_helpers_constants_and_collection_controls_cannot_change_unreviewed(repository,name,content):
    root,base = repository
    path = root/name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content)
    # A worker can hide new controls from git status; policy still inspects them.
    (root/'.gitignore').write_text(name+'\n')
    findings = baseline_findings(root,base,('tests/accept/test_independent.py',))
    assert any(name in finding for finding in findings)


def test_unrelated_implementation_and_new_independent_tests_are_allowed(repository):
    root,base = repository
    (root/'calc.py').write_text('def value():\n    return 43\n')
    independent = root/'tests/accept/test_independent.py'
    independent.parent.mkdir()
    independent.write_text('def test_independent():\n    assert 43 != 42\n')
    assert baseline_findings(root,base,('tests/accept/test_independent.py',)) == []


def test_baseline_symlinked_parent_is_refused_without_accepting_identical_contents(repository,tmp_path):
    root,base = repository
    outside = tmp_path/'outside-fixture'
    (root/'tests').rename(outside)
    (root/'tests').symlink_to(outside,target_is_directory=True)
    findings = baseline_findings(root,base)
    assert any('cannot safely inspect' in finding for finding in findings)
