"""Tests for checkout-personalization scoring + runner publish/commit (docs/02 §3.2, §6).

llm-gateway and Kafka are mocked/injected; the agent makes no ml call. The FEAT-002
contracts are asserted: the scorer ranks methods by historical success rate and surfaces
the top method as the verdict rationale (so the decision-engine reads it as the
recommended method) with the ranking in evidence; the agent is advisory (always APPROVE,
never a veto); the recommended method survives even when the llm-gateway fails (rationale
override takes precedence) while still marking the verdict degraded; and the runner
publishes then commits in that order.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from checkout_personalization_agent.agent import build_runner
from checkout_personalization_agent.scorer import build_score_fn, rank_methods

from acip_common.config import Settings
from acip_common.schemas import (
    AgentName,
    DecisionHint,
    EventEnvelope,
    EventType,
    MethodHistoryEntry,
    MethodType,
    SharedRepresentation,
    TransactionCore,
    TxnEvaluateRequestedPayload,
)
from acip_common.topics import AGENT_VERDICTS


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


def _representation(txn_id: str = "txn_personalize") -> SharedRepresentation:
    return SharedRepresentation(
        representation_version=1,
        transaction_id=txn_id,
        built_at=datetime.now(tz=UTC),
        transaction=TransactionCore(
            amount=120.0,
            currency="INR",
            method_type=MethodType.UPI,
            merchant_id="mer_1",
            customer_id="cus_clean",
        ),
        method_history={
            "upi": MethodHistoryEntry(successes=18, failures=1),
            "card": MethodHistoryEntry(successes=2, failures=4),
        },
    )


def _evaluate_envelope(txn_id: str = "txn_personalize") -> EventEnvelope:
    payload = TxnEvaluateRequestedPayload(
        representation=_representation(txn_id),
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
        return httpx.Response(200, json={"text": "prefer upi"})

    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def _factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("acip_agent_common.rationale.httpx.Client", _factory)


def test_rank_methods_orders_by_success_rate() -> None:
    ranked = rank_methods(_representation())
    assert [m.method for m in ranked] == ["upi", "card"]
    assert ranked[0].success_rate == pytest.approx(18 / 19)


def test_scorer_recommends_top_method_and_is_advisory() -> None:
    score_fn = build_score_fn(_settings())
    result = score_fn(_representation(), {})
    assert result.decision_hint is DecisionHint.APPROVE
    assert result.rationale_override == "upi"
    assert result.score == pytest.approx(0.0)
    assert result.evidence[0].signal == "upi"
    assert result.confidence == pytest.approx(18 / 19)


def test_recommended_method_surfaces_in_rationale(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=False)
    producer = _RecordingProducer([])
    consumer = _ReplayConsumer([], [])
    runner = build_runner(
        _settings(),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    verdict = runner.run_once(_evaluate_envelope())

    # The rationale IS the recommended method name, not the LLM text (override wins).
    assert verdict.rationale == "upi"
    assert verdict.decision_hint is DecisionHint.APPROVE


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
    assert envelope.transaction_id == "txn_personalize"
    assert events == ["publish", "commit"]
    assert consumer.commits == 1


def test_llm_failure_still_recommends_method_but_marks_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    # The structured recommendation survives an LLM failure (override, not LLM text).
    assert verdict.rationale == "upi"
    assert verdict.decision_hint is DecisionHint.APPROVE
