"""Tests for fraud-agent scoring + runner publish/commit (docs/02 §3, §4, §6, §1).

ml-scoring-service, llm-gateway, and Kafka are mocked/injected. The FEAT-002 contracts
are asserted: the ring_member slice (large shared-device ring) scores at/above the
fraud block threshold -> DECLINE with ring + velocity evidence; an llm-gateway failure
degrades the rationale; the runner publishes ``agent.verdict.produced`` to
``agent.verdicts`` then commits AFTER the publish.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fraud_agent.agent import build_runner
from fraud_agent.scorer import (
    MlScoringClient,
    ScoreResponse,
    build_score_fn,
    gather_graph_signals,
    graph_component,
)

from acip_common.config import Settings
from acip_common.schemas import (
    AgentName,
    CandidateRoute,
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
    txn_id: str = "txn_ring",
    *,
    ring_size: float = 5.0,
    velocity: float = 3.0,
) -> SharedRepresentation:
    return SharedRepresentation(
        representation_version=1,
        transaction_id=txn_id,
        built_at=datetime.now(tz=UTC),
        transaction=TransactionCore(
            amount=90.0,
            currency="INR",
            method_type=MethodType.CARD,
            merchant_id="mer_1",
            customer_id="cus_ring",
        ),
        features={"shared_device_ring_size": ring_size, "velocity_1h": velocity},
        graph_signals={"ring_size": ring_size, "velocity_1h": velocity},
        candidate_routes=[CandidateRoute(processor="processor_a", success_rate=0.97)],
    )


def _evaluate_envelope(txn_id: str = "txn_ring") -> EventEnvelope:
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


class _FakeScoringClient(MlScoringClient):
    def __init__(self, response: ScoreResponse) -> None:  # noqa: D107 - stub
        self._response = response

    def score(self, model: str, features: Any, trace_id: str) -> ScoreResponse:
        assert model == "fraud"
        return self._response


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
        return httpx.Response(200, json={"text": "device-sharing ring detected"})

    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def _factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("acip_agent_common.rationale.httpx.Client", _factory)


# A weak base ml probability so the graph component is what drives the DECLINE.
_RING_ML_RESPONSE = ScoreResponse(score=0.2, model_version="fraud-lgbm-test", top_features=[])
_CLEAN_ML_RESPONSE = ScoreResponse(score=0.05, model_version="fraud-lgbm-test", top_features=[])


def test_graph_component_saturates_on_ring() -> None:
    assert graph_component(5.0, 0.0) == pytest.approx(1.0)
    assert graph_component(0.0, 0.0) == pytest.approx(0.0)
    assert 0.0 < graph_component(1.0, 0.0) < 1.0


def test_scorer_rings_decline_above_block_threshold() -> None:
    settings = _settings()
    representation = _representation(ring_size=5.0, velocity=3.0)
    signals = gather_graph_signals(representation)
    score_fn = build_score_fn(_FakeScoringClient(_RING_ML_RESPONSE), settings)
    result = score_fn(representation, signals)

    assert result.score >= settings.fraud_block_threshold
    assert result.decision_hint is DecisionHint.DECLINE
    signal_names = {ev.signal for ev in result.evidence}
    assert "shared_device_ring_size" in signal_names
    assert "velocity_1h" in signal_names


def test_scorer_no_ring_does_not_block() -> None:
    settings = _settings()
    representation = _representation(ring_size=0.0, velocity=0.0)
    signals = gather_graph_signals(representation)
    score_fn = build_score_fn(_FakeScoringClient(_CLEAN_ML_RESPONSE), settings)
    result = score_fn(representation, signals)

    assert result.score < settings.fraud_block_threshold
    assert result.decision_hint is DecisionHint.APPROVE


def test_run_once_publishes_then_commit_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=False)
    events: list[str] = []
    producer = _RecordingProducer(events)
    consumer = _ReplayConsumer([_evaluate_envelope()], events)
    runner = build_runner(
        _settings(),
        client=_FakeScoringClient(_RING_ML_RESPONSE),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    runner.consume_forever()

    assert len(producer.published) == 1
    topic, envelope = producer.published[0]
    assert topic == AGENT_VERDICTS
    assert envelope.event_type is EventType.AGENT_VERDICT_PRODUCED
    assert envelope.transaction_id == "txn_ring"
    assert events == ["publish", "commit"]
    assert consumer.commits == 1


def test_llm_failure_yields_degraded_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=True)
    events: list[str] = []
    producer = _RecordingProducer(events)
    consumer = _ReplayConsumer([_evaluate_envelope()], events)
    runner = build_runner(
        _settings(),
        client=_FakeScoringClient(_RING_ML_RESPONSE),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    verdict = runner.run_once(_evaluate_envelope())

    assert verdict.degraded is True
    assert "templated" in verdict.rationale
    assert verdict.decision_hint is DecisionHint.DECLINE
