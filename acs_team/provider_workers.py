"""Production workers/independent roles backed by activated provider sessions."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Literal
import uuid

from pydantic import Field

from .providers import Activations, ProviderContract, ProviderRuntime
from .schemas import Data, Review, Task, parse_data
from .worker_adapters import BaseWorker, WorkerUnverifiedError


class TestArtifacts(Data):
    files: dict[str, str] = Field(min_length=1, max_length=16)


class ReviewContent(Data):
    verdict: Literal['PASS', 'FIX_REQUIRED', 'REPLAN']
    requirement_coverage: list[str] = Field(min_length=1, max_length=64)
    findings: list[str] = Field(default_factory=list, max_length=32)


class ProviderWorker(BaseWorker):
    def __init__(self, contract: ProviderContract, runtime: ProviderRuntime, activations: Activations, receipt: dict):
        self.contract, self.runtime, self.activations, self.receipt = contract, runtime, activations, receipt
        super().__init__(contract.worker_id, activations.valid(contract, receipt))

    def session(self, prompt: str, workspace: Path, readonly: bool = False) -> dict:
        from .managed_worker import _CONTEXT
        if not self.activations.valid(self.contract, self.receipt):
            raise WorkerUnverifiedError('Provider activation expired or changed')
        context = _CONTEXT.get()
        control, mission = context if context else (None, None)
        if control:
            control.require_dispatch()

        def cancelled():
            current = control.db.get_mission(mission) if control else None
            return bool(control and (control.stopped() or current and current['state'] == 'CANCELLED'))

        result = self.runtime.run(self.contract, workspace, prompt, readonly=readonly, cancelled=cancelled)
        if control:
            control.db.record_audit_event(mission, self.worker_id, 'PROVIDER_SESSION', {
                'session_id':result['session_id'], 'readonly':readonly, 'label':result['label']})
        return result

    def execute_task(self, task_id, goal, instructions, worktree_path, files_to_modify=None, timeout_seconds=300):
        from .schemas import TaskResult
        prompt = json.dumps({'role':'implementer', 'task_id':task_id, 'worker_id':self.worker_id, 'goal':goal,
                             'instructions_untrusted':instructions, 'owns':files_to_modify,
                             'result_schema':TaskResult.model_json_schema(),
                             'policy':'Make only owned changes. Never alter acceptance tests, policy, credentials or Git controls. Return JSON.'})
        result = self.session(prompt, worktree_path)
        data = parse_data(TaskResult, result['text'])
        if data.worker != self.worker_id or data.task_id != task_id:
            raise PermissionError('Worker result identity mismatch')
        return {**data.model_dump(), 'worker_id':self.worker_id, 'session_id':result['session_id'], 'label':result['label']}


class ProductionRoles:
    """Fresh readonly reviewer sessions and spec-only tester sessions; host owns identity."""
    def __init__(self, worker: ProviderWorker):
        self.worker = worker
        self.tester_id = f'{worker.worker_id}-tester-{uuid.uuid4().hex[:8]}'
        self.reviewer_id = f'{worker.worker_id}-reviewer-{uuid.uuid4().hex[:8]}'
        self.sessions: list[dict] = []

    def prepare(self, task: Task, requirements: list[str]) -> dict[str, str]:
        prompt = json.dumps({'role':'tester', 'task_id':task.task_id, 'requirements':requirements,
                             'description':task.description, 'owns':task.owns,
                             'acceptance_criteria':task.acceptance_criteria, 'interfaces':task.reads,
                             'schema':TestArtifacts.model_json_schema(),
                             'policy':'Derive substantive pytest tests from the specification before implementation. Return JSON only. No tool execution or filesystem changes.'})
        with tempfile.TemporaryDirectory(prefix='acs-independent-tester-') as tmp:
            result = self.worker.session(prompt, Path(tmp), readonly=True)
        artifacts = parse_data(TestArtifacts, result['text'])
        for name, code in artifacts.files.items():
            p = Path(name)
            if not name.startswith('tests/') or not p.name.startswith('test_') or p.suffix != '.py' or '..' in p.parts or len(code.encode()) > 65536:
                raise PermissionError('Invalid independent test artifact')
        self.sessions.append({'role':'tester','identity':self.tester_id,'session_id':result['session_id']})
        return artifacts.files

    def review(self, task: Task, worktree: Path, implementer: str, sha: str) -> Review:
        prompt = json.dumps({'role':'reviewer', 'task_id':task.task_id, 'reviewed_commit':sha,
                             'requirements':task.acceptance_criteria, 'owns':task.owns,
                             'schema':ReviewContent.model_json_schema(),
                             'policy':'Independently inspect the current tree and tests for correctness, security, scope, baseline weakening and requirement coverage. Do not edit files. Return JSON only.'})
        result = self.worker.session(prompt, worktree, readonly=True)
        content = parse_data(ReviewContent, result['text'])
        self.sessions.append({'role':'reviewer','identity':self.reviewer_id,'session_id':result['session_id']})
        return Review(task_id=task.task_id, implementer=implementer, reviewer=self.reviewer_id,
                      commit_sha=sha, **content.model_dump(exclude={'schema_version'}))


def configured_workers() -> dict[str, BaseWorker]:
    import os
    from .config import STATE_DIR, AUTH_TOKEN_PATH, PROTECTED_PATHS
    from .providers import load_catalog

    if os.environ.get('ACS_ENABLE_PROVIDER_CONTRACTS') != '1':
        return {}
    catalog = load_catalog(Path(os.environ['ACS_PROVIDER_CONTRACT_FILE']))
    key_file = STATE_DIR/'evidence.key'
    if key_file.is_symlink() or not key_file.is_file() or key_file.stat().st_mode & 0o077:
        return {}
    activations = Activations(key_file.read_text().strip())
    workers: dict[str, BaseWorker] = {}
    for contract in catalog.providers:
        private = (STATE_DIR, AUTH_TOKEN_PATH, *PROTECTED_PATHS,
                   *(Path(p.auth_home) for p in catalog.providers if p.worker_id != contract.worker_id))
        path = STATE_DIR/'provider-activation'/f'{contract.worker_id}.json'
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192 or path.stat().st_mode & 0o077:
            continue
        receipt = json.loads(path.read_bytes())
        runtime = ProviderRuntime(private)
        worker = ProviderWorker(contract, runtime, activations, receipt)
        if worker.is_verified:
            from .providers import validate_bindings
            validate_bindings(contract, private)
            workers[contract.worker_id] = worker
    return workers
