"""Non-destructive personal Linux preflight and explicit isolated installation.

Never installs system packages, starts services/providers, reads authentication,
modifies ACS Core, or overwrites an existing installation. No sudo is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sqlite3
import subprocess
import sys


def preflight():
    with sqlite3.connect(':memory:') as con:
        con.execute('CREATE VIRTUAL TABLE fixture USING fts5(content)')
        con.execute('PRAGMA integrity_check').fetchone()
    tools = {name: shutil.which(name) for name in ('git', 'bwrap', 'systemctl', 'codex', 'agy')}
    supported = (sys.platform == 'linux' and sys.version_info >= (3, 12)
                 and platform.machine() in {'x86_64', 'aarch64'} and bool(tools['git']))
    return {'schema_version': 1, 'classification': 'CLOUD_REAL',
            'python': platform.python_version(), 'architecture': platform.machine(),
            'installation_prerequisites': 'PASS' if supported else 'BLOCKED',
            'tools': tools, 'sqlite': sqlite3.sqlite_version, 'sqlite_fts5': True,
            'cgroup_v2_present': Path('/sys/fs/cgroup/cgroup.controllers').is_file(),
            'sandbox': 'LOCAL_VERIFICATION_REQUIRED', 'providers': 'LOCAL_VERIFICATION_REQUIRED',
            'runtime_ready': False, 'paid_provider_calls': 0}


def verify_source(source: Path):
    manifest_path = source / 'ACS_BUNDLE_MANIFEST.json'
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise PermissionError('A verified source bundle manifest is required')
    manifest = json.loads(manifest_path.read_text())
    commit = manifest.get('commit', '')
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('Manifest must identify an exact Git commit')
    rows = manifest.get('files', [])
    if not rows or len(rows) > 5000:
        raise ValueError('Invalid source manifest file budget')
    seen = set()
    total = 0
    for row in rows:
        name = row['path']
        relative = PurePosixPath(name)
        if not name or relative.is_absolute() or '..' in relative.parts or '\\' in name or name in seen:
            raise PermissionError('Unsafe or duplicate source path')
        seen.add(name)
        current = source
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise PermissionError('Source bundle contains a symlink')
        size = current.stat().st_size
        total += size
        if not current.is_file() or size > 4 * 1024 * 1024 or total > 32 * 1024 * 1024:
            raise PermissionError('Source file type or budget invalid')
        if size != row['bytes'] or hashlib.sha256(current.read_bytes()).hexdigest() != row['sha256']:
            raise PermissionError('Source manifest hash mismatch: ' + name)
    required = {'pyproject.toml', 'agpair/pyproject.toml', 'requirements/cloud-dev.txt',
                'requirements/local-build.txt', 'acs_team/defaults.json', 'scripts/personal_install.py'}
    if not required.issubset(seen):
        raise PermissionError('Required installation inputs absent from manifest')
    # Unlisted executable Python/config could otherwise enter a built wheel.
    actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() or p.is_symlink()}
    if actual - seen - {'ACS_BUNDLE_MANIFEST.json'}:
        raise PermissionError('Unlisted files in source bundle; use a fresh extraction')
    return {'commit': commit, 'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest()}


def allowed_prefix(prefix: Path, source: Path):
    # Default protected boundary always applies, even if an override omits it.
    defaults = json.loads((source / 'acs_team/defaults.json').read_text())['protected_paths']
    protected = [Path(p).expanduser().resolve() for p in defaults]
    protected.append(Path.home() / 'autonomous-coding-system')
    if os.environ.get('ACS_CORE_PATH'):
        protected.append(Path(os.environ['ACS_CORE_PATH']).expanduser().resolve())
    override = json.loads(os.environ.get('ACS_PROTECTED_PATHS', '[]'))
    if not isinstance(override, list) or not all(isinstance(p, str) and p for p in override):
        raise ValueError('Protected-path override must be a list of paths')
    protected.extend(Path(p).expanduser().resolve() for p in override)
    if prefix.is_symlink():
        raise PermissionError('Installation prefix may not be a symlink')
    target = prefix.resolve()
    boundaries = [*protected, source.resolve(), Path.home().resolve()]
    if target == Path('/') or any(target == p or target in p.parents for p in boundaries):
        raise PermissionError('Installation prefix is too broad or overlaps protected/source paths')
    if any(p == target or p in target.parents for p in [*protected, source.resolve()]):
        raise PermissionError('Installation prefix overlaps protected/source paths')
    return target


def install(source: Path, prefix: Path, *, yes=False, wheelhouse: Path | None = None):
    identity = verify_source(source)
    target = allowed_prefix(prefix, source)
    if preflight()['installation_prerequisites'] != 'PASS':
        raise RuntimeError('Linux x86_64/aarch64, Python 3.12+, Git and SQLite FTS5 required')
    receipt = target / 'INSTALL_RECEIPT.json'
    if target.exists():
        if receipt.is_file() and not receipt.is_symlink() and json.loads(receipt.read_text()) == identity:
            subprocess.run([str(target / 'venv/bin/python'), '-m', 'pip', 'check'], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {'status': 'ALREADY_INSTALLED', **identity, 'prefix': str(target)}
        raise FileExistsError('Existing or incomplete prefix retained; choose a NEW prefix')
    if not yes:
        answer = input(f'Install verified commit {identity["commit"]} into NEW {target}? [y/N] ')
        if answer.strip().lower() != 'y':
            raise PermissionError('Installation not confirmed')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=0o700)
    # Build backends may write egg-info/build trees. Build from a second verified
    # private copy so the original extraction remains immutable and reusable.
    staged_source = target / 'source'
    shutil.copytree(source, staged_source, symlinks=True)
    if verify_source(staged_source) != identity:
        raise PermissionError('Staged source identity changed')
    home = target / 'installer-home'
    home.mkdir(mode=0o700)
    environment = {k: v for k, v in os.environ.items() if not k.startswith(('ACS_', 'AGPAIR_'))}
    environment.update(HOME=str(home), ACS_HOME=str(target),
                       ACS_BACKUPS_DIR=str(target / 'backups'),
                       ACS_CREDENTIALS_FILE=str(target / 'unconfigured-credentials.json'))
    log = target / 'install.log'
    descriptor = os.open(log, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        def run(command):
            subprocess.run(command, cwd=staged_source, env=environment,
                           stdout=output, stderr=subprocess.STDOUT, check=True)
        run([sys.executable, '-m', 'venv', '--copies', str(target / 'venv')])
        python = str(target / 'venv/bin/python')
        offline = ['--no-index', '--find-links', str(wheelhouse.resolve())] if wheelhouse else []
        run([python, '-m', 'pip', 'install', '--no-cache-dir', *offline,
             '--constraint', str(staged_source / 'requirements/cloud-dev.txt'),
             '--requirement', str(staged_source / 'requirements/local-build.txt')])
        # No editable imports into the downloaded source, no provider lifecycle,
        # no shell, no global package installation. Runtime versions constrained.
        run([python, '-m', 'pip', 'install', '--no-cache-dir', '--no-build-isolation', *offline,
             '--constraint', str(staged_source / 'requirements/cloud-dev.txt'), str(staged_source) + '[test]', str(staged_source / 'agpair')])
        run([python, '-m', 'pip', 'check'])
        run([python, '-I', '-c', 'import acs_team, agpair, sqlite3; assert sqlite3.connect(":memory:").execute("PRAGMA integrity_check").fetchone()[0] == "ok"'])
        run([python, '-m', 'acs_team.cli', '--help'])
    # Legacy bridge discovery intentionally uses ACS_HOME/venv/bin/agpair.
    # Keep that contract while config.py places the database under ACS_HOME/state.
    configuration = {'ACS_HOME': str(target), 'ACS_BACKUPS_DIR': str(target / 'backups'),
                     'ACS_CREDENTIALS_FILE': str(target / 'unconfigured-credentials.json')}
    configuration_path = target / 'config.json'
    fd = os.open(configuration_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(configuration, stream, indent=2)
    bin_dir = target / 'bin'
    bin_dir.mkdir(mode=0o700)
    launcher = bin_dir / 'acsai'
    launcher.write_text('#!/usr/bin/env python3\nimport json, os, sys\n'
        + 'config = json.load(open(' + repr(str(configuration_path)) + '))\n'
        + 'assert isinstance(config, dict) and all(isinstance(k,str) and k.startswith("ACS_") and isinstance(v,str) for k,v in config.items())\n'
        + 'environment = {**os.environ, **config}\n'
        + 'os.execve(' + repr(python) + ', [' + repr(python) + ', "-m", "acs_team.cli", *sys.argv[1:]], environment)\n')
    launcher.chmod(0o700)
    receipt.write_text(json.dumps(identity, indent=2) + '\n')
    receipt.chmod(0o600)
    return {'status': 'INSTALLED', **identity, 'prefix': str(target), 'paid_provider_calls': 0,
            'local_acceptance': 'LOCAL_VERIFICATION_REQUIRED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true', help='Read-only dependency inspection; no auth/provider calls')
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--prefix', type=Path, help='NEW private installation directory')
    parser.add_argument('--yes', action='store_true', help='Confirm only this new isolated package installation')
    parser.add_argument('--wheelhouse', type=Path, help='Optional offline wheel directory including build backends')
    args = parser.parse_args()
    if args.preflight:
        report = preflight()
        print(json.dumps(report, indent=2))
        return 0 if report['installation_prerequisites'] == 'PASS' else 2
    if args.prefix is None:
        parser.error('--prefix is required for installation')
    print(json.dumps(install(args.source.resolve(), args.prefix.expanduser(), yes=args.yes,
                             wheelhouse=args.wheelhouse), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
