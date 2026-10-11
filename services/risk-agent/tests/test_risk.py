"""Tests for risk-agent scoring + runner publish/commit (docs/02 §3, §6, §1).

ml-scoring-service, llm-gateway, and Kafka are all mocked/injected so the suite runs
with no infra. The three FEAT-002 contracts are asserted: the scorer maps the
clean_shopper slice to a low-risk APPROVE verdict, an llm-gateway failure degrades the
rationale (``degraded=True``), and the runner publishes ``agent.verdict.produced`` to
``agent.verdicts`` then commits AFTER the publish.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from risk_agent.agent import build_runner
from risk_agent.scorer import MlScoringClient, ScoreResponse, band, build_score_fn

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


def _representation(txn_id: str = "txn_clean", amount: float = 120.0) -> SharedRepresentation:
    return SharedRepresentation(
        representation_version=1,
        transaction_id=txn_id,
        built_at=datetime.now(tz=UTC),
        transaction=TransactionCore(
            amount=amount,
            currency="INR",
            method_type=MethodType.UPI,
            merchant_id="mer_1",
            customer_id="cus_clean",
        ),
        features={"amount_zscore": 0.1, "velocity_1h": 0.0},
        candidate_routes=[CandidateRoute(processor="processor_a", success_rate=0.97)],
    )


def _evaluate_envelope(txn_id: str = "txn_clean") -> EventEnvelope:
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
    """An ml-scoring client stub returning a fixed response (no HTTP)."""

    def __init__(self, response: ScoreResponse) -> None:  # noqa: D107 - stub
        self._response = response

    def score(self, model: str, features: Any, trace_id: str) -> ScoreResponse:
        assert model == "risk"
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
        return httpx.Response(200, json={"text": "clean shopper, low risk"})

    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def _factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("acip_agent_common.rationale.httpx.Client", _factory)


_CLEAN_RESPONSE = ScoreResponse(
    score=0.08,
    model_version="risk-xgb-test",
    top_features=[("amount_zscore", 0.02), ("velocity_1h", 0.01)],
)


def test_band_thresholds() -> None:
    settings = _settings()
    assert band(0.1, settings) is DecisionHint.APPROVE
    assert band(0.5, settings) is DecisionHint.CHALLENGE
    assert band(0.9, settings) is DecisionHint.DECLINE


def test_scorer_maps_clean_shopper_to_low_risk_approve() -> None:
    settings = _settings()
    score_fn = build_score_fn(_FakeScoringClient(_CLEAN_RESPONSE), settings)
    result = score_fn(_representation(), {})
    assert result.decision_hint is DecisionHint.APPROVE
    assert result.score == pytest.approx(0.08)
    assert result.model_version == "risk-xgb-test"
    assert result.evidence[0].signal == "amount_zscore"


def test_run_once_publishes_then_commit_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=False)
    events: list[str] = []
    producer = _RecordingProducer(events)
    consumer = _ReplayConsumer([_evaluate_envelope()], events)
    runner = build_runner(
        _settings(),
        client=_FakeScoringClient(_CLEAN_RESPONSE),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    runner.consume_forever()

    assert len(producer.published) == 1
    topic, envelope = producer.published[0]
    assert topic == AGENT_VERDICTS
    assert envelope.event_type is EventType.AGENT_VERDICT_PRODUCED
    assert envelope.transaction_id == "txn_clean"
    assert events == ["publish", "commit"]
    assert consumer.commits == 1


def test_llm_failure_yields_degraded_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=True)
    events: list[str] = []
    producer = _RecordingProducer(events)
    consumer = _ReplayConsumer([_evaluate_envelope()], events)
    runner = build_runner(
        _settings(),
        client=_FakeScoringClient(_CLEAN_RESPONSE),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    verdict = runner.run_once(_evaluate_envelope())

    assert verdict.degraded is True
    assert "templated" in verdict.rationale
    assert verdict.decision_hint is DecisionHint.APPROVE
