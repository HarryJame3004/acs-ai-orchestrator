"""Real durable admission; no authenticated providers or operational state."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

import pytest

from acs_team.db import DatabaseManager
from acs_team.provider_ledger import ProviderInvocationBlocked, ProviderLedger


def ledger(tmp_path):
    return ProviderLedger(DatabaseManager(tmp_path/'state.db'), b'disposable-ledger-fixture')


def result():
    return dict(text='specification-derived output', worker_id='codex-primary',
                session_id='fixture-session', label='CLOUD_SIMULATED')


def reserve(store, prompt='one', readonly=True, mission='mission'):
    return store.reserve(mission, 'codex-primary', 'contract-digest', prompt, readonly)


def test_completed_readonly_replay_is_signed_and_mutating_replay_is_blocked(tmp_path):
    store = ledger(tmp_path)
    key, owner, cached = reserve(store)
    assert cached is None
    store.complete(key, owner, result())
    assert reserve(ledger(tmp_path))[2] == result()
    mutating, owner, _ = reserve(store, readonly=False)
    store.complete(mutating, owner, result())
    with pytest.raises(ProviderInvocationBlocked, match='reconciliation'):
        reserve(store, readonly=False)
    with store.transaction() as con:
        con.execute('UPDATE provider_invocations SET result_json=? WHERE invocation_id=?',
                    (json.dumps({**result(), 'text':'forged'}), key))
    with pytest.raises(ProviderInvocationBlocked, match='reconciliation'):
        reserve(store)


def test_concurrent_controllers_reserve_once_and_never_steal_uncertain_call(tmp_path):
    store = ledger(tmp_path)
    def attempt(_):
        try:
            return reserve(ledger(tmp_path))
        except ProviderInvocationBlocked:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, range(8)))
    assert sum(value is not None for value in outcomes) == 1
    with store.transaction() as con:
        assert con.execute('SELECT COUNT(*) FROM provider_invocations').fetchone()[0] == 1
    with pytest.raises(ProviderInvocationBlocked, match='reconciliation'):
        reserve(ledger(tmp_path))


def test_process_death_after_external_effect_preserves_uncertainty(tmp_path):
    db = tmp_path/'state.db'
    effect = tmp_path/'external-effect'
    program = '''
import os, sys
from pathlib import Path
from acs_team.db import DatabaseManager
from acs_team.provider_ledger import ProviderLedger
store=ProviderLedger(DatabaseManager(Path(sys.argv[1])), b'disposable-ledger-fixture')
store.reserve('mission','codex-primary','contract-digest','one',True)
with open(sys.argv[2], 'x') as output:
    output.write('external execution happened once')
    output.flush()
    os.fsync(output.fileno())
os._exit(73)
'''
    child = subprocess.run([sys.executable, '-c', program, str(db), str(effect)],
                           cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=20)
    assert child.returncode == 73, child.stderr.decode()
    assert effect.read_text() == 'external execution happened once'
    with pytest.raises(ProviderInvocationBlocked, match='reconciliation'):
        reserve(ledger(tmp_path))


def test_budget_counts_reserved_failures_across_workers_and_missions(tmp_path, monkeypatch):
    monkeypatch.setenv('ACS_PROVIDER_MAX_MISSION_CALLS', '1')
    monkeypatch.setenv('ACS_PROVIDER_MAX_TOTAL_CALLS', '2')
    store = ledger(tmp_path)
    reserve(store)
    with pytest.raises(ProviderInvocationBlocked, match='budget'):
        store.reserve('mission', 'agy-google-a', 'other-contract', 'other-prompt', False)
    reserve(store, mission='mission2')
    with pytest.raises(ProviderInvocationBlocked, match='budget'):
        reserve(store, mission='mission3')
    monkeypatch.setenv('ACS_PROVIDER_MAX_TOTAL_CALLS', '0')
    with pytest.raises(ProviderInvocationBlocked, match='safe range'):
        reserve(store, mission='mission4')


def test_completion_requires_owner_and_rejects_false_provenance_and_secrets(tmp_path):
    store = ledger(tmp_path)
    key, owner, _ = reserve(store)
    with pytest.raises(ProviderInvocationBlocked, match='ownership'):
        store.complete(key, 'wrong-owner', result())
    with pytest.raises(ProviderInvocationBlocked, match='provenance'):
        store.complete(key, owner, {**result(), 'label':'CLOUD_REAL'})
    with pytest.raises(ProviderInvocationBlocked, match='sensitive'):
        store.complete(key, owner, {**result(), 'text':'Authorization: Bearer fixture-sensitive-material'})
    store.complete(key, owner, result())
    with pytest.raises(ProviderInvocationBlocked, match='ownership'):
        store.complete(key, owner, result())


@pytest.mark.simulated
def test_worker_reserves_before_dispatch_and_reopened_readonly_reuses_once(tmp_path, monkeypatch):
    from acs_team.managed_worker import worker_context
    from acs_team.provider_workers import ProviderWorker
    from acs_team.providers import ProviderRuntime, Activations
    from acs_team.runtime_control import RuntimeControl
    from test_provider_contracts import contract, receipt
    monkeypatch.setenv('ACS_ENABLE_PROVIDER_LEDGER', '1')
    c = contract(tmp_path)
    authority = Activations('disposable-ledger-fixture', clock=lambda:150.)
    control = RuntimeControl(DatabaseManager(tmp_path/'state.db'))
    control.db.create_mission('mission','fixture',str(tmp_path/'repo'),'Fixture request')
    calls = []
    def provider(*args, **kwargs):
        with control.db.connection() as con:
            assert con.execute("SELECT COUNT(*) FROM provider_invocations WHERE state='RESERVED'").fetchone()[0] == 1
        calls.append('executed')
        return dict(exit_code=0, reason='completed', stdout=json.dumps(
            dict(type='item.completed', item=dict(type='agent_message', text='fixture-result'))))
    worker = ProviderWorker(c, ProviderRuntime((), executor=provider), authority, receipt(authority,c))
    with worker_context(control, 'mission'):
        first = worker.session('same prompt', tmp_path/'repo', readonly=True)
        again = worker.session('same prompt', tmp_path/'repo', readonly=True)
    assert first == again and calls == ['executed']
    assert control.db.get_audit_trail('mission')[-1]['action'] == 'PROVIDER_RESULT_REUSED'
    native = ProviderWorker(c, ProviderRuntime(()), authority, receipt(authority,c))
    with pytest.raises(ProviderInvocationBlocked, match='mission context'):
        native.session('must not launch', tmp_path/'repo')
    with control.db.connection() as con:
        con.execute("UPDATE missions SET state='FAILED' WHERE mission_id='mission'")
    with worker_context(control, 'mission'):
        with pytest.raises(ProviderInvocationBlocked, match='active mission'):
            worker.session('same prompt', tmp_path/'repo', readonly=True)
    with control.db.connection() as con:
        con.execute("UPDATE missions SET state='CREATED' WHERE mission_id='mission'")
    Path(c.executable).write_text('changed executable')
    with worker_context(control, 'mission'):
        with pytest.raises(PermissionError, match='changed'):
            worker.session('same prompt', tmp_path/'repo', readonly=True)
    assert calls == ['executed']


@pytest.mark.simulated
def test_worker_death_window_never_reexecutes_mutating_provider(tmp_path, monkeypatch):
    from acs_team.managed_worker import worker_context
    from acs_team.provider_workers import ProviderWorker
    from acs_team.providers import ProviderRuntime, Activations
    from acs_team.runtime_control import RuntimeControl
    from test_provider_contracts import contract, receipt
    monkeypatch.setenv('ACS_ENABLE_PROVIDER_LEDGER', '1')
    c = contract(tmp_path)
    authority = Activations('disposable-ledger-fixture', clock=lambda:150.)
    control = RuntimeControl(DatabaseManager(tmp_path/'state.db'))
    control.db.create_mission('mission','fixture',str(tmp_path/'repo'),'Fixture request')
    calls = []
    def provider(*args, **kwargs):
        calls.append('external effect')
        raise RuntimeError('controller lost result after external effect')
    worker = ProviderWorker(c, ProviderRuntime((), executor=provider), authority, receipt(authority,c))
    with worker_context(control, 'mission'):
        with pytest.raises(RuntimeError, match='external effect'):
            worker.session('implement task', tmp_path/'repo')
        with pytest.raises(ProviderInvocationBlocked, match='reconciliation'):
            worker.session('implement task', tmp_path/'fresh-worktree')
    assert calls == ['external effect']


def test_usage_counts_reserved_and_completed_without_exposing_outputs(tmp_path):
    from acs_team.provider_ledger import provider_usage
    store = ledger(tmp_path)
    key, owner, _ = reserve(store)
    store.complete(key, owner, result())
    reserve(store, prompt='uncertain')
    usage = provider_usage(DatabaseManager(tmp_path/'state.db', read_only=True))
    assert usage['total_reserved_calls'] == 2 and usage['uncertain_calls'] == 1
    assert sum(row['calls'] for row in usage['groups']) == 2
    assert result()['text'] not in json.dumps(usage)


def test_usage_cli_does_not_initialize_installation_or_missing_database(tmp_path):
    import os
    home = tmp_path/'uninitialized-install'
    environment = {key:value for key,value in os.environ.items() if not key.startswith(('ACS_', 'AGPAIR_'))}
    environment.update(ACS_HOME=str(home), ACS_BACKUPS_DIR=str(tmp_path/'backups'),
                       ACS_CREDENTIALS_FILE=str(tmp_path/'absent-credentials'))
    db = tmp_path/'readonly-fixture.db'
    DatabaseManager(db)
    root = Path(__file__).resolve().parents[1]
    child = subprocess.run([sys.executable, '-m', 'acs_team.cli', 'provider-usage', '--database', str(db)],
                           env=environment, cwd=root, capture_output=True, text=True, timeout=20)
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout)['total_reserved_calls'] == 0
    assert not home.exists() and not (tmp_path/'backups').exists()
    absent = tmp_path/'absent.db'
    child = subprocess.run([sys.executable, '-m', 'acs_team.cli', 'provider-usage', '--database', str(absent)],
                           env=environment, cwd=root, capture_output=True, text=True, timeout=20)
    assert child.returncode != 0 and not absent.exists() and not home.exists()


def test_uncertain_implementation_cannot_fail_over_or_change_instructions(tmp_path):
    store = ledger(tmp_path)
    prompt = json.dumps({'role':'implementer','task_id':'task1','worker_id':'codex-primary',
                         'instructions_untrusted':'implement required behavior'})
    store.reserve('mission','codex-primary','first-contract',prompt,False)
    changed = json.dumps({'role':'implementer','task_id':'task1','worker_id':'agy-google-a',
                          'instructions_untrusted':'new recovery instructions'})
    with pytest.raises(ProviderInvocationBlocked, match='reconciliation'):
        store.reserve('mission','agy-google-a','changed-contract',changed,False)
    with store.transaction() as con:
        assert con.execute('SELECT COUNT(*) FROM provider_invocations').fetchone()[0] == 1
