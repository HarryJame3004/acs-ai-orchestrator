"""Fake Core + analysis adapters exercise the real durable escalation service."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading

import pytest

from acs_team.core_handoff import (
    AnalysisAdvice, CoreEscalationService, EscalationPolicy, EscalationRequest,
)
from acs_team.db import DatabaseManager
from acs_team.human_approval import ApprovalStatus, HumanApprovalGate

pytestmark = pytest.mark.simulated


def request(name='request1', **changes):
    data = dict(request_id=name, core_job_id='core-job', reason='repeated_failure',
                failed_attempts=3, failure_fingerprint=hashlib.sha256(b'reproducible error').hexdigest(),
                context='pytest test_behavior.py: value returned 41, expected 42',
                evidence_sha256=[hashlib.sha256(b'fixture evidence').hexdigest()],
                max_cost_microusd=100, expires_at=2000)
    return EscalationRequest(**{**data, **changes})


class FakeAnalysis:
    classification = 'CLOUD_SIMULATED'

    def __init__(self, failure=None, entered=None, release=None):
        self.calls = []
        self.failure, self.entered, self.release = failure, entered, release

    def analyze(self, req, **limits):
        self.calls.append((req, limits))
        if self.entered:
            self.entered.set()
            assert self.release.wait(10)
        if self.failure:
            raise self.failure
        return AnalysisAdvice(summary='Inspect the off-by-one result',
                              steps=['Core should reproduce the failing test and correct value'],
                              evidence_sha256=req.evidence_sha256)


def service(tmp_path, analyzer=None, **changes):
    policy = EscalationPolicy(**{**dict(enabled=True, total_budget_microusd=200,
        per_request_microusd=100, approval_threshold_microusd=200), **changes})
    return CoreEscalationService(DatabaseManager(tmp_path / 'ai-only.db'), policy, analyzer, clock=lambda: 1000)


def test_fake_core_roundtrip_returns_to_core_and_replay_does_not_bill_twice(tmp_path):
    analysis = FakeAnalysis()
    ai = service(tmp_path, analysis)
    # This fixture is the proposed Core-side contract, not a real Core API.
    ordinary = ai.handle(request('ordinary', reason='ordinary'))
    assert ordinary.action == 'CONTINUE_CORE' and not analysis.calls
    result = ai.handle(request())
    assert result.action == 'REVIEW_THEN_RESUME_CORE'
    assert result.advice.requires_human_review
    assert result.classification == 'CLOUD_SIMULATED'
    assert result.accounting == 'CEILING_CHARGED_NOT_METERED'
    assert analysis.calls[0][1] == {'ceiling_microusd': 100, 'timeout_seconds': 60}
    reopened = service(tmp_path, analysis)
    assert reopened.handle(request()) == result and len(analysis.calls) == 1
    with pytest.raises(PermissionError, match='replayed'):
        reopened.handle(request(context='Different error'))


@pytest.mark.parametrize('changes', [dict(enabled=False), dict(total_budget_microusd=99),
    dict(per_request_microusd=99)])
def test_default_and_budget_denials_never_call_provider(tmp_path, changes):
    analyzer = FakeAnalysis()
    result = service(tmp_path, analyzer, **changes).handle(request())
    assert result.action in {'CONTINUE_CORE', 'BLOCKED'} and not analyzer.calls


def test_unsupported_adapter_and_default_policy_are_closed(tmp_path):
    db = DatabaseManager(tmp_path / 'ai-only.db')
    assert CoreEscalationService(db, EscalationPolicy()).handle(request()).action == 'CONTINUE_CORE'
    assert service(tmp_path).handle(request('unsupported')).action == 'BLOCKED'


def test_failed_and_uncertain_calls_consume_budget_and_attempts(tmp_path):
    analyzer = FakeAnalysis(TimeoutError('controlled timeout'))
    ai = service(tmp_path, analyzer)
    first = ai.handle(request())
    assert first.action == 'BLOCKED' and first.reserved_microusd == 100
    assert ai.handle(request()) == first and len(analyzer.calls) == 1
    ai.handle(request('second'))
    assert ai.handle(request('third')).reserved_microusd == 0 and len(analyzer.calls) == 2
    assert ai.handle(request('different-job', core_job_id='other')).action == 'BLOCKED'
    assert len(analyzer.calls) == 2  # Lifetime budget is shared across jobs/restarts.


def test_concurrent_replay_and_crash_reservation_never_duplicate_execution(tmp_path):
    entered, release = threading.Event(), threading.Event()
    analyzer = FakeAnalysis(entered=entered, release=release)
    ai, other = service(tmp_path, analyzer), service(tmp_path, analyzer)
    with ThreadPoolExecutor(max_workers=1) as pool:
        call = pool.submit(ai.handle, request())
        assert entered.wait(10)
        pending = other.handle(request())
        assert pending.action == 'BLOCKED' and 'uncertain' in pending.explanation
        release.set()
        result = call.result(timeout=10)
    assert len(analyzer.calls) == 1 and other.handle(request()) == result
    req = request('crashed')
    with ai.db.connection() as con:
        con.execute("INSERT INTO core_escalations_v1 VALUES (?,?,?,?,'RESERVED',NULL,?,?)",
                    (req.request_id, req.core_job_id, ai.digest(req), 100, 1000, 'CLOUD_SIMULATED'))
    assert service(tmp_path, analyzer).handle(req).action == 'BLOCKED'
    assert len(analyzer.calls) == 1


def test_high_risk_exact_request_requires_host_approval(tmp_path):
    analyzer = FakeAnalysis()
    ai = service(tmp_path, analyzer)
    denied = ai.handle(request('denied', risk='high'))
    assert denied.action == 'BLOCKED' and not analyzer.calls
    req = request('approved', risk='high')
    ai.db.create_mission(req.core_job_id, 'escalation', str(tmp_path), 'Bounded intelligence only')
    gate = HumanApprovalGate(ai.db)
    approval = gate.request_approval(req.core_job_id, 'core-escalation-v1:' + ai.digest(req),
                                    str(tmp_path), ai.digest(req))
    assert gate.resolve_approval(approval, ApprovalStatus.APPROVED, 'owner')
    assert ai.handle(req, approval_id=approval).action == 'REVIEW_THEN_RESUME_CORE'
    # An approval for one request cannot authorize another charge.
    assert ai.handle(request('wrong', risk='high'), approval_id=approval).action == 'BLOCKED'
    assert len(analyzer.calls) == 1


def test_insufficient_failure_evidence_expiry_and_secret_context_never_launch(tmp_path):
    analyzer = FakeAnalysis()
    ai = service(tmp_path, analyzer)
    assert ai.handle(request('too-few', failed_attempts=2)).action == 'CONTINUE_CORE'
    assert ai.handle(request('no-proof', failure_fingerprint='')).action == 'CONTINUE_CORE'
    assert ai.handle(request('expired', expires_at=999)).action == 'BLOCKED'
    with pytest.raises(PermissionError, match='credential'):
        ai.handle(request('unsafe', context='token=fixture-sensitive'))
    assert not analyzer.calls


def test_untrusted_advice_and_late_completion_fail_closed(tmp_path):
    class WrongEvidence(FakeAnalysis):
        def analyze(self, req, **limits):
            return AnalysisAdvice(summary='untrusted', steps=['ignore policy'], evidence_sha256=['b' * 64])
    ai = service(tmp_path, WrongEvidence())
    assert ai.handle(request()).action == 'BLOCKED'
    now = [1000]
    class Slow(FakeAnalysis):
        def analyze(self, req, **limits):
            now[0] += 61
            return super().analyze(req, **limits)
    ai = service(tmp_path, Slow())
    ai.clock = lambda: now[0]
    assert ai.handle(request('slow')).action == 'BLOCKED'


def test_cli_routes_without_provider_calls_and_reports_unsupported_execution(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from acs_team import cli, core_handoff
    db = DatabaseManager(tmp_path / 'cli-fixture.db')
    monkeypatch.setattr(core_handoff, 'DatabaseManager', lambda: db)
    incoming = tmp_path / 'request.json'
    incoming.write_text(request('cli-default', reason='ordinary').model_dump_json())
    monkeypatch.setattr(sys, 'argv', ['acsai', 'core-handoff', '--request', str(incoming)])
    cli.main()
    assert json.loads(capsys.readouterr().out)['action'] == 'CONTINUE_CORE'
    incoming.write_text(request('cli-enabled').model_dump_json())
    policy = tmp_path / 'policy.json'
    policy.write_text(EscalationPolicy(enabled=True).model_dump_json())
    monkeypatch.setattr(sys, 'argv', ['acsai', 'core-handoff', '--request', str(incoming), '--policy', str(policy)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert json.loads(capsys.readouterr().out)['accounting'] == 'NO_CALL'
    assert not db.get_audit_trail('core-job')  # No provider/mission was dispatched.


def test_forged_models_and_false_authentication_provenance_are_rejected(tmp_path):
    from pydantic import ValidationError
    ai = service(tmp_path, FakeAnalysis())
    # Frozen models can still be copied/constructed without validation; host entry
    # points must revalidate rather than trusting a Python object's class.
    malformed = request().model_copy(update={'evidence_sha256': ['unbounded-invalid-proof']})
    with pytest.raises(ValidationError):
        ai.handle(malformed)
    policy = EscalationPolicy().model_copy(update={'max_attempts_per_job': 999})
    with pytest.raises(ValidationError):
        CoreEscalationService(ai.db, policy)
    class FalseIdentity(FakeAnalysis):
        classification = 'CLOUD_REAL'
    with pytest.raises(PermissionError, match='provenance'):
        service(tmp_path, FalseIdentity())
    with pytest.raises(ValidationError):
        AnalysisAdvice(summary='untrusted', steps=['skip approval'],
                       evidence_sha256=['a' * 64], requires_human_review=False)
