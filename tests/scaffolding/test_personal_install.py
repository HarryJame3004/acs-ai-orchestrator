"""Installation must reject source tampering and protected/existing destinations."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts.personal_install import allowed_prefix, install, preflight, verify_source


def source_fixture(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    files = {'pyproject.toml': 'fixture', 'agpair/pyproject.toml': 'fixture',
             'requirements/cloud-dev.txt': 'fixture', 'requirements/local-build.txt': 'fixture',
             'scripts/personal_install.py': 'fixture',
             'acs_team/defaults.json': json.dumps({'protected_paths': [str(tmp_path / 'protected')]})}
    entries = []
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        entries.append({'path': name, 'bytes': len(content.encode()),
                        'sha256': hashlib.sha256(content.encode()).hexdigest()})
    (source / 'ACS_BUNDLE_MANIFEST.json').write_text(json.dumps({'commit': 'a' * 40, 'files': entries}))
    return source


@pytest.mark.parametrize('attack', ['tamper', 'unlisted', 'symlink', 'duplicate', 'traversal'])
def test_source_integrity_denials_leave_target_and_protected_fixture_untouched(tmp_path, attack):
    source = source_fixture(tmp_path)
    protected = tmp_path / 'protected'
    protected.mkdir()
    original = protected / 'untouched'
    original.write_text('original')
    manifest = source / 'ACS_BUNDLE_MANIFEST.json'
    if attack == 'tamper':
        (source / 'pyproject.toml').write_text('modified build backend')
    elif attack == 'unlisted':
        (source / 'unexpected.py').write_text('raise RuntimeError("unlisted")')
    elif attack == 'symlink':
        (source / 'pyproject.toml').unlink()
        (source / 'pyproject.toml').symlink_to(original)
    else:
        data = json.loads(manifest.read_text())
        data['files'].append(data['files'][0] if attack == 'duplicate' else {
            'path': '../protected/untouched', 'bytes': 8, 'sha256': hashlib.sha256(b'original').hexdigest()})
        manifest.write_text(json.dumps(data))
    destination = tmp_path / 'installation'
    with pytest.raises(PermissionError):
        install(source, destination, yes=True)
    assert not destination.exists() and original.read_text() == 'original'


def test_protected_custom_core_and_ancestor_prefixes_are_denied(tmp_path, monkeypatch):
    source = source_fixture(tmp_path)
    custom = tmp_path / 'separate-core-fixture'
    monkeypatch.setenv('ACS_CORE_PATH', str(custom))
    for target in (Path('/'), tmp_path, source / 'install', custom, custom / 'child', tmp_path / 'protected/child'):
        with pytest.raises(PermissionError):
            allowed_prefix(target, source)
    assert allowed_prefix(tmp_path / 'new-install', source) == tmp_path / 'new-install'
    assert not custom.exists()


def test_existing_incomplete_prefix_is_retained_without_overwrite(tmp_path):
    source = source_fixture(tmp_path)
    assert verify_source(source)['commit'] == 'a' * 40
    destination = tmp_path / 'existing'
    destination.mkdir()
    marker = destination / 'owner-file'
    marker.write_text('preserve')
    with pytest.raises(FileExistsError):
        install(source, destination, yes=True)
    assert marker.read_text() == 'preserve'


def test_preflight_never_claims_provider_or_kernel_acceptance():
    report = preflight()
    assert report['paid_provider_calls'] == 0
    assert report['providers'] == report['sandbox'] == 'LOCAL_VERIFICATION_REQUIRED'
    assert report['runtime_ready'] is False and report['sqlite_fts5']
