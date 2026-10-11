"""Tests for routing-agent scoring + runner publish/commit (docs/02 §3.1, §6, §1).

llm-gateway and Kafka are mocked/injected; the routing agent makes no ml call. The
FEAT-002 contracts are asserted: for the unhealthy_preferred_route slice the scorer
ranks a healthy alternate above the degraded preferred processor and emits a ROUTE hint
with one evidence row per route; an llm-gateway failure degrades the rationale; the
runner publishes ``agent.verdict.produced`` to ``agent.verdicts`` then commits AFTER the
publish.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from routing_agent.agent import build_runner
from routing_agent.scorer import build_score_fn, score_routes

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

# Mirrors scripts/seed.py ROUTES: processor_pref is degraded (0.42).
_ROUTES = [
    CandidateRoute(processor="processor_a", success_rate=0.97, cost_bps=85, p50_latency_ms=220),
    CandidateRoute(processor="processor_b", success_rate=0.94, cost_bps=70, p50_latency_ms=180),
    CandidateRoute(processor="processor_pref", success_rate=0.42, cost_bps=60, p50_latency_ms=950),
]


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


def _representation(txn_id: str = "txn_reroute") -> SharedRepresentation:
    return SharedRepresentation(
        representation_version=1,
        transaction_id=txn_id,
        built_at=datetime.now(tz=UTC),
        transaction=TransactionCore(
            amount=260.0,
            currency="INR",
            method_type=MethodType.CARD,
            merchant_id="mer_1",
            customer_id="cus_reroute",
        ),
        candidate_routes=_ROUTES,
    )


def _evaluate_envelope(txn_id: str = "txn_reroute") -> EventEnvelope:
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
        return httpx.Response(200, json={"text": "preferred route degraded; failover"})

    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def _factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("acip_agent_common.rationale.httpx.Client", _factory)


def test_score_routes_ranks_healthy_over_degraded_preferred() -> None:
    ranked = score_routes(_ROUTES)
    assert [r.processor for r in ranked][0] in {"processor_a", "processor_b"}
    # The degraded preferred route ranks last.
    assert ranked[-1].processor == "processor_pref"


def test_scorer_emits_route_hint_and_per_route_evidence() -> None:
    score_fn = build_score_fn(_settings())
    result = score_fn(_representation(), {})
    assert result.decision_hint is DecisionHint.ROUTE
    assert len(result.evidence) == len(_ROUTES)
    # Evidence is in ranked order; the top route's score is the verdict score.
    assert result.evidence[0].value == pytest.approx(result.score)
    assert result.evidence[0].signal in {"processor_a", "processor_b"}


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
    assert envelope.transaction_id == "txn_reroute"
    assert events == ["publish", "commit"]
    assert consumer.commits == 1


def test_llm_failure_yields_degraded_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=True)
    events: list[str] = []
    producer = _RecordingProducer(events)
    consumer = _ReplayConsumer([_evaluate_envelope()], events)
    runner = build_runner(
        _settings(),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    verdict = runner.run_once(_evaluate_envelope())

    assert verdict.degraded is True
    assert "templated" in verdict.rationale
    assert verdict.decision_hint is DecisionHint.ROUTE
