"""Pinned provider contracts, isolated sessions and host-signed activation.

Only local, explicitly requested probes can create production activation receipts.
No executable/profile-presence shortcut or simulation-to-production promotion.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
from typing import Callable, Literal

from pydantic import Field, model_validator

from .schemas import Data, parse_data
from .security import sandbox_argv
from .supervision import ProcessSupervisor


class ProviderContract(Data):
    worker_id: Literal['codex-primary', 'agy-google-a', 'agy-google-b']
    executable: str = Field(max_length=1024)
    executable_sha256: str = Field(pattern='^[a-f0-9]{64}$')
    auth_home: str = Field(max_length=1024)
    auth_paths: list[str] = Field(min_length=1, max_length=8)
    toolchain_roots: list[str] = Field(default_factory=list, max_length=8)
    network: bool = False
    timeout: int = Field(default=300, ge=1, le=900)
    memory_mb: int = Field(default=2048, ge=128, le=8192)
    cpu_seconds: int = Field(default=180, ge=1, le=900)

    @model_validator(mode='after')
    def bounded_paths(self):
        for text in [self.executable, self.auth_home, *self.toolchain_roots]:
            if not Path(text).is_absolute() or '..' in Path(text).parts:
                raise ValueError('Provider bindings require canonical absolute paths')
        for name in self.auth_paths:
            p = Path(name)
            if p.is_absolute() or '..' in p.parts or not p.parts or '\\' in name:
                raise ValueError('Auth bindings must be relative to the dedicated profile')
        return self

    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class ProviderCatalog(Data):
    providers: list[ProviderContract] = Field(min_length=1, max_length=3)

    @model_validator(mode='after')
    def separate_profiles(self):
        ids = [p.worker_id for p in self.providers]
        homes = [Path(p.auth_home).resolve() for p in self.providers]
        if len(set(ids)) != len(ids) or any(a == b or a in b.parents or b in a.parents
                                        for i, a in enumerate(homes) for b in homes[i+1:]):
            raise ValueError('Providers require distinct identities and disjoint auth homes')
        return self


def load_catalog(path: Path) -> ProviderCatalog:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise PermissionError('Provider catalog must be a bounded regular file')
    return parse_data(ProviderCatalog, path.read_bytes(), 32768)


def validate_bindings(contract: ProviderContract, private_paths: tuple[Path, ...]) -> None:
    executable = Path(contract.executable)
    if executable.is_symlink() or not executable.is_file() or executable.stat().st_size > 128*1024*1024:
        raise PermissionError('Provider executable must be a pinned regular file')
    if not os.access(executable, os.X_OK) or executable.stat().st_mode & 0o022:
        raise PermissionError('Provider executable has unsafe permissions')
    if hashlib.sha256(executable.read_bytes()).hexdigest() != contract.executable_sha256:
        raise PermissionError('Provider executable changed; activation revoked')
    auth = Path(contract.auth_home)
    if auth.resolve() in {Path('/'), Path.home(), Path('/tmp'), Path('/workspace')} or auth.resolve() in Path.home().parents:
        raise PermissionError('Authentication requires a dedicated profile, never the real HOME')
    if auth.is_symlink() or not auth.is_dir() or auth.stat().st_uid != os.getuid() or auth.stat().st_mode & 0o077:
        raise PermissionError('Dedicated auth home must be owned and private')
    roots = [Path(p).resolve() for p in contract.toolchain_roots]
    for root in roots:
        if root in {Path('/'), Path('/home'), Path('/tmp'), Path('/workspace'), Path.home()} or not root.is_dir():
            raise PermissionError('Broad or missing provider toolchain binding')
        if root == auth.resolve() or root in auth.resolve().parents or auth.resolve() in root.parents:
            raise PermissionError('Toolchain cannot expose auth profiles')
    if not any(executable.resolve() == root or root in executable.resolve().parents
               for root in [Path('/usr'), Path('/bin').resolve(), *roots]):
        raise PermissionError('Executable is outside the declared toolchain')
    for name in contract.auth_paths:
        source = auth / name
        if source.is_symlink() or not source.exists() or auth.resolve() not in source.resolve().parents:
            raise PermissionError('Missing or escaping auth binding')
        if source.is_dir():
            for index, entry in enumerate(source.rglob('*')):
                if index >= 4096 or entry.is_symlink():
                    raise PermissionError('Auth binding has symlinks or exceeds metadata budget')
        if any(p.is_symlink() for p in [source, *source.parents] if p != Path('/')):
            raise PermissionError('Symlinked authentication path is forbidden')
    for private in private_paths:
        private = private.resolve()
        for root in [auth.resolve(), *roots]:
            if private == root or root in private.parents or private in root.parents:
                raise PermissionError('Provider binding overlaps protected controller/profile state')


def response_text(worker: str, output: str) -> str:
    """Unwrap native CLI envelopes without executing or trusting their metadata."""
    if len(output.encode()) > 65536:
        raise ValueError('Provider response exceeds contract')
    if worker == 'codex-primary':
        texts = []
        for line in output.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            item = value.get('item', {}) if isinstance(value, dict) else {}
            if isinstance(value, dict) and isinstance(item, dict) and value.get('type') == 'item.completed' and item.get('type') == 'agent_message':
                texts.append(item.get('text', ''))
        if not texts or not isinstance(texts[-1], str):
            raise ValueError('Missing Codex agent-message result')
        return texts[-1]
    value = json.loads(output)
    if not isinstance(value, dict) or value.get('is_error') is True or not isinstance(value.get('result'), str):
        raise ValueError('Missing AGY structured result')
    return value['result']


class ProviderRuntime:
    """All production calls use the real mandatory sandbox; tests inject a host runner."""
    def __init__(self, private_paths: tuple[Path, ...], supervisor: ProcessSupervisor | None = None,
                 executor: Callable | None = None):
        self.private = private_paths
        self.supervisor = supervisor or ProcessSupervisor(output_limit=65536)
        self.executor = executor
        self.label = 'CLOUD_SIMULATED' if executor else 'LOCAL_VERIFICATION_REQUIRED'

    def run(self, contract: ProviderContract, workspace: Path, prompt: str, *, readonly: bool = False,
            cancelled: Callable[[], bool] | None = None) -> dict:
        validate_bindings(contract, self.private)
        profile = Path(contract.auth_home).resolve()
        workspace = workspace.resolve()
        if workspace == profile or workspace in profile.parents or profile in workspace.parents:
            raise PermissionError('Workspace and authentication profile must be disjoint')
        if len(prompt.encode()) > 32768:
            raise ValueError('Provider input exceeds 32 KiB')
        with tempfile.TemporaryDirectory(prefix='acs-provider-home-') as tmp:
            home = Path(tmp)
            for path in ['.config', '.local/share', '.local/state', '.cache', 'tmp']:
                (home/path).mkdir(parents=True, mode=0o700, exist_ok=True)
            if contract.worker_id == 'codex-primary':
                command = [contract.executable, 'exec', '--ephemeral', '--json', '--sandbox',
                           'workspace-write', '--skip-git-repo-check', '-C', str(workspace), prompt]
            else:
                command = [contract.executable, '-p', prompt, '--output-format', 'json',
                           '--print-timeout', f'{contract.timeout}s']
            argv = sandbox_argv(workspace, command, home=home, network=contract.network,
                                private_paths=self.private, read_only_workspace=readonly,
                                read_only_roots=tuple(Path(p) for p in contract.toolchain_roots))
            separator = argv.index('--')
            bindings = []
            if contract.network:
                for source_name in ['/etc/resolv.conf', '/etc/hosts', '/etc/ssl/certs']:
                    source = Path(source_name).resolve()
                    if not source.exists():
                        continue
                    if any(p.resolve() == source or source in p.resolve().parents for p in self.private):
                        raise PermissionError('Network trust binding overlaps controller state')
                    bindings += ['--ro-bind', str(source), source_name]
            for name in contract.auth_paths:
                target = home/name
                target.parent.mkdir(parents=True, exist_ok=True)
                source = Path(contract.auth_home)/name
                if source.is_dir():
                    target.mkdir(exist_ok=True)
                else:
                    target.touch(mode=0o600)
                bindings += ['--ro-bind', str(source), str(target)]
            argv[separator:separator] = bindings
            env = {'PATH': ':'.join([*(str(Path(p)/'bin') for p in contract.toolchain_roots), '/usr/bin', '/bin']),
                   'HOME': tmp, 'XDG_CONFIG_HOME': str(home/'.config'), 'XDG_DATA_HOME': str(home/'.local/share'),
                   'XDG_STATE_HOME': str(home/'.local/state'), 'XDG_CACHE_HOME': str(home/'.cache'),
                   'CODEX_HOME': str(home/'.codex'), 'TMPDIR': str(home/'tmp'), 'GIT_TERMINAL_PROMPT': '0'}
            from .managed_worker import _PROCESS_OBSERVER
            observer = _PROCESS_OBSERVER.get()
            session_id = secrets.token_hex(16)
            def started(owned):
                if observer:
                    observer({**owned.__dict__, 'provider_session':session_id,
                              'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
            execute = self.executor or self.supervisor.run
            result = execute(argv, workspace, env=env, timeout=contract.timeout,
                             memory_mb=contract.memory_mb, cpu_seconds=contract.cpu_seconds,
                             cancelled=cancelled, on_spawn=started)
            if result['exit_code'] != 0 or result['reason'] != 'completed' or result.get('truncated'):
                raise RuntimeError('Provider failed/expired/cancelled; no result accepted')
            return {'text': response_text(contract.worker_id, result['stdout']),
                    'session_id': session_id, 'worker_id': contract.worker_id, 'label': self.label}

    def boundary_probe(self, contract: ProviderContract) -> bool:
        if self.executor is not None:
            return False  # Simulated execution cannot attest actual namespace isolation.
        validate_bindings(contract, self.private)
        with tempfile.TemporaryDirectory(prefix='acs-provider-probe-') as temp:
            root = Path(temp)
            workspace, home = root/'workspace', root/'home'
            workspace.mkdir()
            home.mkdir()
            sentinel = root/'private-sentinel'
            sentinel.write_text(secrets.token_hex(16))
            code = ('import pathlib,sys; w=pathlib.Path(sys.argv[1]); '
                    'assert not pathlib.Path(sys.argv[2]).exists(); '
                    '(w/"allowed").write_text("ok"); '
                    'assert all(not pathlib.Path(p).exists() for p in sys.argv[3:]); print("BOUNDARY_OK")')
            roots = tuple(dict.fromkeys([Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()]))
            argv = sandbox_argv(workspace, [sys.executable, '-c', code, str(workspace), str(sentinel),
                                           *(str(p) for p in self.private)], home=home,
                                private_paths=self.private, read_only_roots=roots)
            result = self.supervisor.run(argv, workspace, env={'PATH':'/usr/bin:/bin','HOME':str(home)}, timeout=15)
            return result['exit_code'] == 0 and result['reason'] == 'completed' and 'BOUNDARY_OK' in result['stdout']


class Activations:
    def __init__(self, key: str, clock: Callable = time.time):
        self.key, self.clock = key.encode(), clock

    def _signature(self, receipt: dict) -> str:
        return hmac.new(self.key, json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()

    def verify(self, contract: ProviderContract, runtime: ProviderRuntime) -> dict:
        if not runtime.boundary_probe(contract):
            raise PermissionError('Real sandbox boundary probe is required for activation')
        nonce = secrets.token_hex(16)
        with tempfile.TemporaryDirectory(prefix='acs-provider-auth-probe-') as temp:
            result = runtime.run(contract, Path(temp), 'Harmless authentication verification. Do not use tools or modify files. '
                                 f'Return exactly ACS_PROVIDER_PROBE_{nonce}', readonly=True)
            if result['text'].strip() != f'ACS_PROVIDER_PROBE_{nonce}' or result['label'] != 'LOCAL_VERIFICATION_REQUIRED':
                raise PermissionError('Authenticated provider challenge failed')
        issued = self.clock()
        receipt = {'worker_id':contract.worker_id, 'contract_digest':contract.digest(), 'verified_at':issued,
                   'expires_at':issued+3600, 'session_id':result['session_id'], 'sandbox_verified':True,
                   'label':'LOCAL_VERIFICATION_REQUIRED'}
        return {**receipt, 'signature':self._signature(receipt)}

    def valid(self, contract: ProviderContract, receipt: dict) -> bool:
        unsigned = {k:v for k,v in receipt.items() if k != 'signature'}
        try:
            return (hmac.compare_digest(self._signature(unsigned), receipt['signature'])
                    and receipt['worker_id'] == contract.worker_id and receipt['contract_digest'] == contract.digest()
                    and receipt['verified_at'] <= self.clock() < receipt['expires_at'] <= receipt['verified_at']+3600
                    and receipt['sandbox_verified'] is True and receipt['label'] == 'LOCAL_VERIFICATION_REQUIRED')
        except (KeyError, TypeError, ValueError):
            return False
