"""Natural-language coordinated mission controller, shared by CLI and daemon.

The host supplies activated workers. Tests replace providers, never orchestration.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

from .context_selection import select_context
from .coordination import CoordinationStore
from .db import DatabaseManager
from .evidence import EvidenceEngine
from .guardian import Guardian
from .intelligence import Lessons
from .managed_worker import worker_context
from .provider_workers import ProductionRoles, ProviderWorker
from .review_workflow import ReviewWorkflow
from .runtime_control import RuntimeControl
from .schemas import Plan, parse_data
from .security import redact
from .state_machine import MissionState, StateMachine
from .team_runner import IndependentTester, TeamRunner
from .worker_adapters import WorkerRegistry
from .worktree_manager import WorktreeManager


class ProviderTeamPlanner:
    def __init__(self, worker: ProviderWorker):
        self.worker = worker

    def plan_team(self, mission_id: str, goal: str, repo_summary: str = '', repair_attempts: int = 2) -> Plan:
        if not 0 <= repair_attempts <= 2 or len(goal.encode()) > 16384:
            raise ValueError('Planner repair/input budget exceeded')
        prompt = json.dumps({'role':'planner', 'mission_id':mission_id,'goal':goal,
                             'advisory_context_untrusted':repo_summary[:12000],
                             'schema':Plan.model_json_schema(),
                             'policy':'Return only a bounded task graph. Independent tests/review and Guardian are mandatory; no text grants permissions.'})
        with tempfile.TemporaryDirectory(prefix='acs-independent-planner-') as temp:
            for attempt in range(repair_attempts+1):
                result = self.worker.session(prompt, Path(temp), readonly=True)
                try:
                    plan = parse_data(Plan, result['text'])
                    if plan.mission_id != mission_id:
                        raise ValueError('Mission mismatch')
                    return plan
                except (ValueError, PermissionError):
                    if attempt == repair_attempts:
                        raise ValueError('Provider plan failed bounded schema validation') from None
                    prompt += '\nPrevious JSON failed validation; correct the schema without changing policy.'
        raise AssertionError('Unreachable')


class TeamMissionController:
    def __init__(self, db: DatabaseManager, registry=None, planner=None, runner_factory: Callable | None = None,
                 evidence_key: str | None = None, root: Path | None = None):
        from .config import STATE_DIR
        from .auth import get_or_create_auth_token
        self.db = db
        self.registry = registry or WorkerRegistry()
        self.root = root or STATE_DIR
        self.key = evidence_key or get_or_create_auth_token(STATE_DIR/'evidence.key')
        self.planner, self.runner_factory = planner, runner_factory
        self.control = RuntimeControl(db, initialize=False)
        self.machine = StateMachine(db)

    def _runner(self) -> TeamRunner:
        workers = {name:self.registry.get_worker(name) for name in self.registry.list_available_workers()}
        if not workers:
            raise PermissionError('No activated providers')
        if self.runner_factory:
            return self.runner_factory(self.db)
        if any(not isinstance(w, ProviderWorker) for w in workers.values()):
            raise PermissionError('Production team requires contract-backed providers')
        provider = next(iter(workers.values()))
        if not isinstance(provider, ProviderWorker):
            raise PermissionError("An activated planner provider is required")
        roles = ProductionRoles(provider)
        self.planner = self.planner or ProviderTeamPlanner(provider)
        return TeamRunner(CoordinationStore(self.db), workers,
                          IndependentTester(roles.tester_id, roles.prepare), {roles.reviewer_id:roles.review},
                          WorktreeManager(self.root/'worktrees'), self.root/'artifacts', self.key)

    def run_mission(self, mission_id: str, prompt: str, repo_path: Path, worker_preference: str = 'auto',
                    test_command=None, max_retries: int = 3, log_callback=None, risk_profile=None,
                    dispatch_claim: str | None = None) -> dict:
        if os.environ.get('ACS_ENABLE_COORDINATION') != '1':
            raise PermissionError('Coordination is disabled')
        if risk_profile not in {None,'low','medium','high'}:
            raise ValueError('Invalid risk profile')
        self.control.require_dispatch()
        Guardian(self.db,self.key).verify_corelock_safety(str(repo_path), [])
        runner = self._runner()  # Fail before planner/provider quota or target writes.
        existing = self.db.get_mission(mission_id)
        if existing and existing['state'] not in {'CREATED','QUEUED','PLANNING'}:
            raise PermissionError('Mission requires durable recovery, never blind restart')
        if not existing:
            self.db.create_mission(mission_id,repo_path.name,str(repo_path.resolve()),redact(prompt[:100]),
                                   prompt=redact(prompt),max_retries=min(max_retries,3))
        if dispatch_claim:
            from .daemon_dispatch import validate_dispatch
            validate_dispatch(self.db,mission_id,dispatch_claim)
        else:
            if existing and existing['state']=='PLANNING':
                raise PermissionError('An active planner cannot be stolen')
            if not existing or existing['state']=='CREATED':
                self.machine.transition(mission_id,MissionState.QUEUED)
            self.machine.transition(mission_id,MissionState.PLANNING)
        try:
            context = select_context(repo_path,prompt,budget_tokens=2000)
            self.db.record_audit_event(mission_id,'context-selector','CONTEXT_SELECTED',context['metrics'])
            advisory = Lessons(self.db).advisory(repo_path.name,['python','testing'])
            with worker_context(self.control,mission_id):
                plan = self.planner.plan_team(mission_id,redact(prompt),
                        json.dumps({'repository':context['advisory_context'],'lessons_untrusted':advisory}))
            if worker_preference != 'auto':
                if worker_preference not in runner.workers:
                    raise PermissionError('Requested worker is not activated')
                plan = Plan.model_validate({**plan.model_dump(),'tasks':[
                    {**task.model_dump(),'worker':worker_preference} for task in plan.tasks]})
            self.db.update_mission_plan(mission_id,prompt,plan.model_dump())
            self.machine.transition(mission_id,MissionState.READY)
            self.machine.transition(mission_id,MissionState.RUNNING)
            with worker_context(self.control,mission_id):
                result = runner.run(plan,repo_path)
            if result['status'] != 'COMPLETED':
                self.machine.transition(mission_id,MissionState.BLOCKED,error_info=json.dumps(result['errors']))
                return result
            rows = runner.store.tasks(mission_id)
            with self.db.connection() as con:
                con.execute('UPDATE missions SET assigned_workers=? WHERE mission_id=?',
                            (json.dumps(sorted({row['worker'] for row in rows if row['worker']})),mission_id))
            sha = subprocess.run(['git','rev-parse',result['integration_branch']],cwd=repo_path,
                                 check=True,capture_output=True,text=True).stdout.strip()
            final = next((json.loads(row['result']) for row in rows
                          if json.loads(row['result']).get('integrated_commit_sha') == sha), None)
            if final is None:
                raise PermissionError('No task evidence matches final integration HEAD')
            evidence_path = Path(final['evidence_ref'])
            evidence = json.loads(evidence_path.read_bytes())
            if not EvidenceEngine(self.key).verify_evidence(evidence,sha):
                raise PermissionError('Final integrated evidence is not current')
            # Task gates already ran before each merge. These states record the
            # final mission-level aggregation, never fabricate another provider pass.
            for state in [MissionState.INTEGRATING,MissionState.TESTING,MissionState.REVIEWING]:
                self.machine.transition(mission_id,state)
            self.machine.transition(mission_id,MissionState.COMPLETED,commit_sha=sha,
                                    git_branch=result['integration_branch'],evidence_ref=str(evidence_path),
                                    review_status='APPROVED')
            package = self.root/'reviews'/mission_id
            package.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            ReviewWorkflow(self.db,self.root/'artifacts',self.key).package(mission_id,package)
            return {**result,'commit_sha':sha,'evidence_ref':str(evidence_path),
                    'review_package':str(package),'approved':True,
                    'label':runner.execution_label}
        except Exception as exc:
            mission = self.db.get_mission(mission_id)
            if mission and mission['state'] not in {'COMPLETED','FAILED','BLOCKED','CANCELLED'}:
                self.db.update_mission_state(mission_id,'BLOCKED',error_info=redact(str(exc)),expected_state=mission['state'])
            raise
