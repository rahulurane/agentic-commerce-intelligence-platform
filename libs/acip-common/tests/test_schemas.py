"""Schema tests: JSON round-trip for every event + the shared representation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from acip_common.schemas import (
    AgentName,
    AgentVerdictProducedPayload,
    CandidateRoute,
    DecisionHint,
    DecisionRenderedPayload,
    EventEnvelope,
    EventType,
    Evidence,
    MethodHistoryEntry,
    MethodType,
    PaymentMethodRef,
    SharedRepresentation,
    TransactionCore,
    TxnCreatedPayload,
    TxnEvaluateRequestedPayload,
    TxnTerminalPayload,
    Verdict,
)

_NOW = datetime(2026, 10, 8, 12, 0, 0, tzinfo=UTC)


def _representation() -> SharedRepresentation:
    return SharedRepresentation(
        representation_version=1,
        transaction_id="txn_789",
        built_at=_NOW,
        transaction=TransactionCore(
            amount=149.99,
            currency="USD",
            method_type=MethodType.UPI,
            merchant_id="mrc_123",
            customer_id="cus_456",
        ),
        features={"amount_zscore": 2.1, "velocity_1h": 11.0},
        graph_signals={"shared_device_ring_size": 4.0, "customer_txn_count_30d": 12.0},
        method_history={"upi": MethodHistoryEntry(successes=18, failures=1)},
        candidate_routes=[CandidateRoute(processor="processor_a", success_rate=0.97, cost_bps=85)],
    )


def _verdict() -> Verdict:
    return Verdict(
        decision_hint=DecisionHint.DECLINE,
        score=0.87,
        confidence=0.91,
        rationale="High fraud likelihood: device shared across a ring.",
        evidence=[Evidence(signal="shared_device_ring_size", value=4, weight=0.42)],
        model_version="fraud-lgbm-2026.10.08",
        degraded=False,
    )


def test_representation_round_trip() -> None:
    rep = _representation()
    restored = SharedRepresentation.model_validate_json(rep.model_dump_json())
    assert restored == rep
    assert restored.transaction.method_type is MethodType.UPI
    assert restored.method_history["upi"].successes == 18


def test_verdict_round_trip() -> None:
    verdict = _verdict()
    restored = Verdict.model_validate_json(verdict.model_dump_json())
    assert restored == verdict
    assert restored.decision_hint is DecisionHint.DECLINE


@pytest.mark.parametrize(
    "payload",
    [
        TxnCreatedPayload(
            merchant_id="mrc_123",
            customer_id="cus_456",
            amount=149.99,
            currency="USD",
            payment_method=PaymentMethodRef(type=MethodType.CARD, bin="411111", last4="1111"),
        ),
        TxnEvaluateRequestedPayload(
            representation=_representation(),
            expected_agents=list(AgentName),
            deadline_ms=800,
        ),
        AgentVerdictProducedPayload(agent=AgentName.FRAUD, produced_at=_NOW, verdict=_verdict()),
        DecisionRenderedPayload(
            decision=DecisionHint.CHALLENGE,
            composite_score=0.63,
            strategy="weighted_veto",
            route="processor_b",
            route_alternatives=["processor_a"],
            recommended_method="upi",
            contributing_verdicts=list(AgentName),
            explanation="step-up required",
        ),
        TxnTerminalPayload(
            decision=DecisionHint.APPROVE,
            route="processor_a",
            processor_result={"status": "CAPTURED"},
            composite_score=0.21,
            decided_at=_NOW,
        ),
    ],
)
def test_payload_round_trip(payload: object) -> None:
    cls = type(payload)
    restored = cls.model_validate_json(payload.model_dump_json())  # type: ignore[attr-defined]
    assert restored == payload


def test_envelope_round_trip() -> None:
    env = EventEnvelope(
        event_id="evt_1",
        event_type=EventType.TXN_CREATED,
        event_version=1,
        transaction_id="txn_789",
        trace_id="trace_1",
        occurred_at=_NOW,
        producer="checkout-api",
        payload={"amount": 149.99},
    )
    restored = EventEnvelope.model_validate_json(env.model_dump_json())
    assert restored == env
    assert restored.event_type is EventType.TXN_CREATED


def test_strict_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Verdict.model_validate(
            {
                "decision_hint": "APPROVE",
                "score": 0.1,
                "confidence": 0.9,
                "rationale": "ok",
                "model_version": "v1",
                "unexpected": True,
            }
        )


def test_enum_validation_rejects_bad_value() -> None:
    with pytest.raises(ValidationError):
        TransactionCore(
            amount=1.0,
            currency="USD",
            method_type="crypto",  # type: ignore[arg-type]
            merchant_id="m",
            customer_id="c",
        )
