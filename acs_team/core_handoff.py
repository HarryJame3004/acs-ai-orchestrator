"""Optional ACS AI-owned v1 escalation interface; no ACS Core API is assumed.

Ordinary work is returned to Core without invoking intelligence. Analysis adapters
must enforce their declared charge ceiling and timeout outside model control.
There is deliberately no native paid adapter until such a ceiling is supported.
"""
from __future__ import annotations

import hashlib
import time
from contextlib import contextmanager
from typing import Annotated, Literal, Protocol

from pydantic import Field

from .db import DatabaseManager
from .human_approval import HumanApprovalGate
from .schemas import Data, Identifier, Text
from .security import redact

Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class EscalationPolicy(Data):
    enabled: bool = False
    total_budget_microusd: int = Field(default=0, ge=0, le=100_000_000)
    per_request_microusd: int = Field(default=0, ge=0, le=10_000_000)
    approval_threshold_microusd: int = Field(default=0, ge=0)
    max_attempts_per_job: int = Field(default=2, ge=1, le=3)
    repeated_failure_threshold: int = Field(default=3, ge=2, le=10)
    timeout_seconds: int = Field(default=60, ge=1, le=300)


class EscalationRequest(Data):
    request_id: Identifier
    core_job_id: Identifier
    reason: Literal['ordinary', 'repeated_failure', 'complex_planning', 'important_review']
    failed_attempts: int = Field(default=0, ge=0, le=1000)
    failure_fingerprint: str = Field(default='', pattern=r'^(?:[a-f0-9]{64})?$')
    risk: Literal['low', 'medium', 'high'] = 'medium'
    context: Text
    evidence_sha256: list[Digest] = Field(min_length=1, max_length=32)
    max_cost_microusd: int = Field(default=0, ge=0, le=10_000_000)
    expires_at: int = Field(ge=1)


class AnalysisAdvice(Data):
    summary: Text
    steps: list[Text] = Field(min_length=1, max_length=32)
    evidence_sha256: list[Digest] = Field(min_length=1, max_length=32)
    # Advice is data for Core's own validation/approvals, never executable tools.
    requires_human_review: Literal[True] = True


class CoreHandoff(Data):
    request_id: Identifier
    core_job_id: Identifier
    response_id: str = Field(pattern=r'^core-v1-[a-f0-9]{64}$')
    request_sha256: Digest
    action: Literal['CONTINUE_CORE', 'REVIEW_THEN_RESUME_CORE', 'BLOCKED']
    explanation: Text
    advice: AnalysisAdvice | None = None
    reserved_microusd: int = Field(default=0, ge=0, le=10_000_000)
    accounting: Literal['NO_CALL', 'CEILING_CHARGED_NOT_METERED'] = 'NO_CALL'
    classification: Literal['CLOUD_REAL', 'CLOUD_SIMULATED', 'LOCAL_VERIFICATION_REQUIRED'] = 'CLOUD_REAL'


class BoundedAnalyzer(Protocol):
    """Trusted host adapter contract, NOT a property returned by an LLM.

    Must refuse before launch when a provider cannot enforce the given monetary
    ceiling; timeout must cancel/reap its owned execution tree. A model estimate,
    a token estimate or a read-only sandbox is not a billing ceiling.
    """
    classification: Literal['CLOUD_SIMULATED', 'LOCAL_VERIFICATION_REQUIRED']

    def analyze(self, request: EscalationRequest, *, ceiling_microusd: int,
                timeout_seconds: int) -> AnalysisAdvice: ...


class CoreEscalationService:
    """Durable at-most-once dispatch with conservative, never-refunded charges.

    RESERVED after a crash is uncertain, not permission to launch another call.
    Every reservation, including failed/invalid/timeout responses, consumes both
    the job attempt and the complete ceiling. SQLite serializes competing hosts.
    """
    def __init__(self, db: DatabaseManager, policy: EscalationPolicy,
                 analyzer: BoundedAnalyzer | None = None, clock=time.time):
        self.db, self.policy, self.analyzer, self.clock = (
            db, EscalationPolicy.model_validate(policy.model_dump()), analyzer, clock)
        if analyzer is not None and analyzer.classification not in {'CLOUD_SIMULATED', 'LOCAL_VERIFICATION_REQUIRED'}:
            raise PermissionError('Analysis adapters must declare simulated or unverified authenticated provenance')
        with self._durable_connection() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS core_escalations_v1 (
                request_id TEXT PRIMARY KEY, job TEXT NOT NULL, digest TEXT NOT NULL,
                reserved INTEGER NOT NULL CHECK(reserved>=0),
                state TEXT NOT NULL CHECK(state IN ('NO_CALL','RESERVED','FINISHED')),
                response TEXT, created REAL NOT NULL, label TEXT NOT NULL)''')

    @contextmanager
    def _durable_connection(self):
        with self.db.connection() as con:
            con.execute('PRAGMA synchronous=FULL')
            if con.execute('PRAGMA synchronous').fetchone()[0] != 2:
                raise PermissionError('Escalation reservations require synchronous FULL')
            yield con

    @staticmethod
    def digest(request: EscalationRequest) -> str:
        return hashlib.sha256(request.model_dump_json().encode()).hexdigest()

    def handle(self, request: EscalationRequest, *, approval_id: str | None = None) -> CoreHandoff:
        request = EscalationRequest.model_validate(request.model_dump())
        digest = self.digest(request)
        if redact(request.model_dump()) != request.model_dump():
            raise PermissionError('Escalation context contains credential-like data')

        def handoff(action, explanation, **kwargs):
            return CoreHandoff(request_id=request.request_id, core_job_id=request.core_job_id,
                               request_sha256=digest, response_id='core-v1-' + digest,
                               action=action, explanation=explanation, **kwargs)

        with self._durable_connection() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM core_escalations_v1 WHERE request_id=?',
                              (request.request_id,)).fetchone()
            if row:
                if row['digest'] != digest:
                    raise PermissionError('Request identifier replayed with different content')
                if row['response'] is None:
                    return handoff('BLOCKED', 'Prior call has uncertain outcome; reconcile without automatic redispatch',
                                   reserved_microusd=row['reserved'], accounting='CEILING_CHARGED_NOT_METERED',
                                   classification=row['label'])
                return CoreHandoff.model_validate_json(row['response'])
            eligible = request.reason in {'complex_planning', 'important_review'} or (
                request.reason == 'repeated_failure' and bool(request.failure_fingerprint)
                and request.failed_attempts >= self.policy.repeated_failure_threshold)
            if not self.policy.enabled or not eligible:
                response = handoff('CONTINUE_CORE', 'Core remains the executor; no intelligence call authorized')
            elif request.expires_at <= self.clock():
                response = handoff('BLOCKED', 'Request expired; return control to Core without an intelligence call')
            elif self.analyzer is None:
                response = handoff('BLOCKED', 'No validated bounded analysis adapter; paid execution disabled')
            else:
                spent = con.execute('SELECT COALESCE(SUM(reserved),0) FROM core_escalations_v1').fetchone()[0]
                attempts = con.execute("SELECT COUNT(*) FROM core_escalations_v1 WHERE job=? AND state IN ('RESERVED','FINISHED')",
                                       (request.core_job_id,)).fetchone()[0]
                cost = request.max_cost_microusd
                if cost > self.policy.per_request_microusd or spent + cost > self.policy.total_budget_microusd or attempts >= self.policy.max_attempts_per_job:
                    response = handoff('BLOCKED', 'Escalation budget or maximum attempts exhausted')
                elif (request.risk == 'high' or cost >= self.policy.approval_threshold_microusd) and (
                    not approval_id or not HumanApprovalGate(self.db).is_operation_approved(
                        approval_id, mission_id=request.core_job_id, commit_sha=digest,
                        action='core-escalation-v1:' + digest)):
                    response = handoff('BLOCKED', 'Exact request requires human approval before analysis')
                else:
                    con.execute("INSERT INTO core_escalations_v1 VALUES (?,?,?,?,'RESERVED',NULL,?,?)",
                                (request.request_id, request.core_job_id, digest, cost, self.clock(),
                                 self.analyzer.classification))
                    response = None
            if response is not None:
                # All responses are idempotent. A changed authorization or
                # configuration requires a fresh request identifier.
                con.execute("INSERT INTO core_escalations_v1 VALUES (?,?,?,?,'NO_CALL',?,?,?)",
                            (request.request_id, request.core_job_id, digest, 0,
                             response.model_dump_json(), self.clock(), response.classification))
                return response
        # Reservation commits before provider invocation. No SQLite writer lock
        # is held over an external operation, and a concurrent replay cannot run.
        assert self.analyzer is not None
        try:
            started = self.clock()
            timeout = min(self.policy.timeout_seconds, int(request.expires_at - started))
            if timeout < 1:
                raise TimeoutError('Request expired before analysis launch')
            advice = AnalysisAdvice.model_validate(self.analyzer.analyze(
                request, ceiling_microusd=request.max_cost_microusd,
                timeout_seconds=timeout).model_dump())
            if self.clock() >= request.expires_at or self.clock() - started > timeout:
                raise TimeoutError('Late analysis response rejected')
            if not set(advice.evidence_sha256).issubset(request.evidence_sha256):
                raise ValueError('Analysis cites evidence outside the request')
            if redact(advice.model_dump()) != advice.model_dump():
                raise ValueError('Unsafe analysis response')
            response = handoff('REVIEW_THEN_RESUME_CORE', 'Advisory handoff only; Core must validate and execute its own plan',
                               advice=advice, reserved_microusd=request.max_cost_microusd,
                               accounting='CEILING_CHARGED_NOT_METERED', classification=self.analyzer.classification)
        except Exception as error:
            response = handoff('BLOCKED', 'Analysis failed; no automatic retry: ' + type(error).__name__,
                               reserved_microusd=request.max_cost_microusd,
                               accounting='CEILING_CHARGED_NOT_METERED', classification=self.analyzer.classification)
        with self._durable_connection() as con:
            con.execute("UPDATE core_escalations_v1 SET state='FINISHED',response=? WHERE request_id=? AND digest=? AND state='RESERVED'",
                        (response.model_dump_json(), request.request_id, digest))
        self.db.record_audit_event(request.core_job_id, 'core-escalation-v1', 'CORE_HANDOFF', {
            'request_id': request.request_id, 'digest': digest, 'action': response.action,
            'reserved_microusd': response.reserved_microusd, 'classification': response.classification})
        return response


def execute(args):
    """File-based ACS AI interface; never connects to a presumed Core endpoint."""
    from pathlib import Path
    from .schemas import parse_data

    def read(model, filename):
        path = Path(filename)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
            raise PermissionError('Contract input must be a bounded regular JSON file')
        return parse_data(model, path.read_bytes(), 32768)

    request = read(EscalationRequest, args.request)
    policy = read(EscalationPolicy, args.policy) if args.policy else EscalationPolicy()
    result = CoreEscalationService(DatabaseManager(), policy).handle(request)
    print(result.model_dump_json())
    if result.action == 'BLOCKED':
        raise SystemExit(2)


def register(subparsers):
    parser = subparsers.add_parser('core-handoff', help='Optional Core-first v1 handoff; no automatic paid execution')
    parser.add_argument('--request', required=True, help='Owner-supplied v1 escalation JSON; no credentials')
    parser.add_argument('--policy', help='Optional v1 policy JSON; default disabled with zero budget')
    parser.set_defaults(func=execute)
