"""Tests for merchant-agent soft-constraints + runner publish/commit (docs/02 §3, §6, §1).

llm-gateway and Kafka are mocked/injected; the merchant agent makes no ml call. The
FEAT-002 contracts are asserted: the high_value_midrisk slice (amount 4800 >= 4000)
emits a ``force_challenge`` evidence row and a CHALLENGE hint (so the decision-engine
upgrades APPROVE -> CHALLENGE); a low-value slice emits APPROVE with no constraint and
never vetoes; an llm-gateway failure degrades the rationale; and the runner publishes
then commits in that order.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from merchant_agent.agent import build_runner
from merchant_agent.scorer import build_score_fn

from acip_common.config import Settings
from acip_common.schemas import (
    AgentName,
    DecisionHint,
    EventEnvelope,
    EventType,
    MethodType,
    SharedRepresentation,
    TransactionCore,
    TxnEvaluateRequestedPayload,
)
from acip_common.topics import AGENT_VERDICTS


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


def _representation(
    txn_id: str = "txn_merchant", *, amount: float = 4800.0
) -> SharedRepresentation:
    return SharedRepresentation(
        representation_version=1,
        transaction_id=txn_id,
        built_at=datetime.now(tz=UTC),
        transaction=TransactionCore(
            amount=amount,
            currency="USD",
            method_type=MethodType.CARD,
            merchant_id="mer_1",
            customer_id="cus_midrisk",
        ),
    )


def _evaluate_envelope(txn_id: str = "txn_midrisk", amount: float = 4800.0) -> EventEnvelope:
    payload = TxnEvaluateRequestedPayload(
        representation=_representation(txn_id, amount=amount),
        expected_agents=list(AgentName),
        deadline_ms=800,
    )
    return EventEnvelope(
        event_id="evt_1",
        event_type=EventType.TXN_EVALUATE_REQUESTED,
        transaction_id=txn_id,
        trace_id="trace_1",
        occurred_at=datetime.now(tz=UTC),
        producer="commerce-orchestrator",
        payload=payload.model_dump(mode="json"),
    )


class _RecordingProducer:
    def __init__(self, events: list[str]) -> None:
        self.published: list[tuple[str, EventEnvelope]] = []
        self._events = events

    def publish(self, topic: str, envelope: EventEnvelope) -> None:
        self.published.append((topic, envelope))
        self._events.append("publish")

    def flush(self, timeout: float = 10.0) -> int:
        return 0


class _ReplayConsumer:
    def __init__(self, envelopes: list[EventEnvelope], events: list[str]) -> None:
        self._envelopes = envelopes
        self._events = events
        self.commits = 0

    def stream(self, timeout: float = 1.0) -> Any:
        yield from self._envelopes

    def commit(self) -> None:
        self.commits += 1
        self._events.append("commit")

    def close(self) -> None:
        return None


def _mock_gateway(monkeypatch: pytest.MonkeyPatch, *, fail: bool) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        if fail:
            raise httpx.ConnectError("gateway down")
        return httpx.Response(200, json={"text": "high value; step up"})

    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def _factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("acip_agent_common.rationale.httpx.Client", _factory)


def test_high_value_forces_challenge() -> None:
    score_fn = build_score_fn(_settings())
    result = score_fn(_representation(amount=4800.0), {})
    assert result.decision_hint is DecisionHint.CHALLENGE
    assert any(ev.signal == "force_challenge" and ev.value >= 1.0 for ev in result.evidence)


def test_low_value_approves_without_constraint() -> None:
    score_fn = build_score_fn(_settings())
    result = score_fn(_representation(amount=120.0), {})
    assert result.decision_hint is DecisionHint.APPROVE
    assert result.evidence == []


def test_merchant_never_declines() -> None:
    score_fn = build_score_fn(_settings())
    # Even an extreme amount only ever CHALLENGEs from the merchant agent.
    result = score_fn(_representation(amount=1_000_000.0), {})
    assert result.decision_hint is not DecisionHint.DECLINE


def test_run_once_publishes_then_commit_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=False)
    events: list[str] = []
    producer = _RecordingProducer(events)
    consumer = _ReplayConsumer([_evaluate_envelope()], events)
    runner = build_runner(
        _settings(),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    runner.consume_forever()

    assert len(producer.published) == 1
    topic, envelope = producer.published[0]
    assert topic == AGENT_VERDICTS
    assert envelope.event_type is EventType.AGENT_VERDICT_PRODUCED
    assert envelope.transaction_id == "txn_midrisk"
    assert events == ["publish", "commit"]
    assert consumer.commits == 1


def test_llm_failure_yields_degraded_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=True)
    producer = _RecordingProducer([])
    consumer = _ReplayConsumer([], [])
    runner = build_runner(
        _settings(),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    verdict = runner.run_once(_evaluate_envelope())

    assert verdict.degraded is True
    assert "templated" in verdict.rationale
    assert verdict.decision_hint is DecisionHint.CHALLENGE
