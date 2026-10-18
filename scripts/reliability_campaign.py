"""Retained, credential-free seeded reliability profile (CLOUD_SIMULATED).

No green repetition closes a previous unexplained failure. Output must be new;
pytest never receives a pre-existing basetemp which it could silently remove.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import sqlite3
import sys
import threading
import uuid

MODULES = ['test_runtime_security.py', 'test_coordination.py', 'test_review_workflow.py',
           'test_recovery.py', 'test_aggregate_limits.py', 'test_evidence_durability.py',
           'test_baseline_integrity.py', 'test_guardian_verification_failure.py']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--postmerge-only', action='store_true')
    parser.add_argument('--schedule', choices=['natural', 't0-first', 't1-first', 'both-ready'], default='natural')
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    home = output / 'home'
    home.mkdir(mode=0o700)
    for name in list(os.environ):
        if name.startswith(('ACS_', 'AGPAIR_', 'PYTEST_')):
            del os.environ[name]
    os.environ.update(HOME=str(home), ACS_HOME=str(home / 'state'), ACS_BACKUPS_DIR=str(home / 'backups'),
                      ACS_CREDENTIALS_FILE=str(home / 'absent.json'), GIT_CONFIG_NOSYSTEM='1',
                      GIT_CONFIG_GLOBAL='/dev/null', PYTHONNOUSERSITE='1')
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    import pytest
    from acs_team.team_runner import TeamRunner
    from acs_team.coordination import CoordinationStore
    from acs_team.security import redact
    original_run, original_execute = TeamRunner.run, TeamRunner._execute
    original_integrate = CoordinationStore.integration
    first_integrated = threading.Event()
    both_ready = threading.Barrier(2, timeout=30)
    lock = threading.Lock()

    def selected():
        return '[postmerge]' in os.environ.get('PYTEST_CURRENT_TEST', '')

    def execute(self, plan, task, *values):
        result = original_execute(self, plan, task, *values)
        if selected():
            if args.schedule == 'both-ready':
                both_ready.wait()
            elif args.schedule in {'t0-first', 't1-first'} and task.task_id != args.schedule[:2]:
                if not first_integrated.wait(30):
                    raise TimeoutError('Controlled schedule did not observe first integration')
        return result

    def integrate(self, *values, **kwargs):
        try:
            return original_integrate(self, *values, **kwargs)
        finally:
            if selected():
                first_integrated.set()

    def observe(self, *values, **kwargs):
        result = None
        try:
            result = original_run(self, *values, **kwargs)
            return result
        finally:
            with lock:
                destination = output / ('team-' + uuid.uuid4().hex)
                destination.mkdir(mode=0o700)
                (destination / 'result.json').write_text(json.dumps(redact(result), default=str, indent=2))
                with self.store.db.connection() as source, sqlite3.connect(destination / 'state.sqlite') as target:
                    source.backup(target)
                # The new parent is private; the retained tree and artifacts stay
                # in basetemp, including audit/evidence files and Git metadata.

    class Order:
        def pytest_collection_modifyitems(self, items):
            random.Random(args.seed).shuffle(items)

    TeamRunner.run, TeamRunner._execute = observe, execute
    CoordinationStore.integration = integrate
    selection = [str(root / 'tests' / name) for name in MODULES]
    if args.postmerge_only:
        selection = [str(root / 'tests/test_coordination.py') + '::test_coordinated_real_git_sqlite_guardian_with_fake_workers[postmerge]']
    try:
        code = int(pytest.main(selection + ['-q', '--showlocals', '-p', 'no:cacheprovider',
            '--basetemp=' + str(output / 'basetemp'), '--junitxml=' + str(output / 'junit.xml'),
            '--log-file=' + str(output / 'pytest.log')], plugins=[Order()]))
    finally:
        TeamRunner.run, TeamRunner._execute = original_run, original_execute
        CoordinationStore.integration = original_integrate
    (output / 'campaign.json').write_text(json.dumps({
        'seed': args.seed, 'schedule': args.schedule, 'selection': selection,
        'exit_code': code, 'classification': 'CLOUD_SIMULATED',
        'historical_defect_closed': False,
        'retained': ['home', 'basetemp', 'team-*/result.json', 'team-*/state.sqlite', 'junit.xml', 'pytest.log'],
    }, indent=2) + '\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
