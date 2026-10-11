"""Tests for the uniform per-agent scaffolding (docs/02 §2.2, §6, §1).

Kafka (EventProducer/EventConsumer) and the llm-gateway are mocked, so the suite runs
with no broker and no gateway. The three contracts FEAT-001 calls out are asserted:

* the uniform graph produces an ``acip_common`` ``Verdict`` from an injected ``score_fn``;
* ``AgentRunner.run_once`` publishes ``agent.verdict.produced`` to ``agent.verdicts`` and
  the consume loop commits AFTER the publish, in that order (docs/02 §6);
* an LLM failure yields a ``degraded=True`` templated rationale (docs/02 §1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from acip_agent_common.graph import ScoreResult, build_agent_graph, run_agent_graph
from acip_agent_common.rationale import llm_rationale
from acip_agent_common.runner import AgentRunner
from acip_common.config import Settings
from acip_common.schemas import (
    AgentName,
    CandidateRoute,
    DecisionHint,
    EventEnvelope,
    EventType,
    Evidence,
    MethodType,
    SharedRepresentation,
    TransactionCore,
    TxnEvaluateRequestedPayload,
    Verdict,
)
from acip_common.topics import AGENT_VERDICTS


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


def _representation(transaction_id: str = "txn_1") -> SharedRepresentation:
    return SharedRepresentation(
        representation_version=1,
        transaction_id=transaction_id,
        built_at=datetime.now(tz=UTC),
        transaction=TransactionCore(
            amount=120.0,
            currency="INR",
            method_type=MethodType.UPI,
            merchant_id="mer_1",
            customer_id="cus_1",
        ),
        candidate_routes=[CandidateRoute(processor="processor_a", success_rate=0.97)],
    )


def _evaluate_envelope(transaction_id: str = "txn_1") -> EventEnvelope:
    payload = TxnEvaluateRequestedPayload(
        representation=_representation(transaction_id),
        expected_agents=list(AgentName),
        deadline_ms=800,
    )
    return EventEnvelope(
        event_id="evt_1",
        event_type=EventType.TXN_EVALUATE_REQUESTED,
        transaction_id=transaction_id,
        trace_id="trace_1",
        occurred_at=datetime.now(tz=UTC),
        producer="commerce-orchestrator",
        payload=payload.model_dump(mode="json"),
    )


def _approve_score(_: SharedRepresentation, __: dict[str, Any]) -> ScoreResult:
    """A trivial injected score_fn: APPROVE with one evidence row."""
    return ScoreResult(
        score=0.1,
        decision_hint=DecisionHint.APPROVE,
        model_version="test-1",
        evidence=[Evidence(signal="amount", value=120.0, weight=0.1)],
        confidence=0.9,
    )


class _RecordingProducer:
    """Records published envelopes and the order of publish vs the consumer commit."""

    def __init__(self, events: list[str]) -> None:
        self.published: list[tuple[str, EventEnvelope]] = []
        self._events = events

    def publish(self, topic: str, envelope: EventEnvelope) -> None:
        self.published.append((topic, envelope))
        self._events.append("publish")

    def flush(self, timeout: float = 10.0) -> int:
        return 0


class _ReplayConsumer:
    """Yields a fixed list of envelopes once, then stops; records commit ordering."""

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
    """Point the rationale httpx client at a MockTransport (success or failure)."""

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


def test_graph_produces_verdict_from_injected_score_fn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_gateway(monkeypatch, fail=False)
    compiled = build_agent_graph()
    result = run_agent_graph(
        compiled=compiled,
        agent_name="risk",
        score_fn=_approve_score,
        settings=_settings(),
        payload=_evaluate_envelope().payload,
        trace_id="trace_1",
    )
    assert isinstance(result.verdict, Verdict)
    assert result.verdict.decision_hint is DecisionHint.APPROVE
    assert result.verdict.model_version == "test-1"
    assert result.verdict.rationale == "clean shopper, low risk"
    assert result.verdict.degraded is False
    assert result.verdict.evidence[0].signal == "amount"


def test_run_once_publishes_then_commit_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=False)
    events: list[str] = []
    producer = _RecordingProducer(events)
    consumer = _ReplayConsumer([_evaluate_envelope()], events)
    runner = AgentRunner(
        AgentName.RISK,
        _approve_score,
        _settings(),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    runner.consume_forever()

    # Exactly one verdict published to agent.verdicts, keyed by the transaction id.
    assert len(producer.published) == 1
    topic, envelope = producer.published[0]
    assert topic == AGENT_VERDICTS
    assert envelope.event_type is EventType.AGENT_VERDICT_PRODUCED
    assert envelope.transaction_id == "txn_1"
    # Commit happens AFTER the publish (docs/02 §6).
    assert events == ["publish", "commit"]
    assert consumer.commits == 1


def test_non_evaluate_events_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_gateway(monkeypatch, fail=False)
    events: list[str] = []
    other = _evaluate_envelope()
    other.event_type = EventType.TXN_CREATED
    producer = _RecordingProducer(events)
    consumer = _ReplayConsumer([other], events)
    runner = AgentRunner(
        AgentName.RISK,
        _approve_score,
        _settings(),
        producer=producer,  # type: ignore[arg-type]
        consumer=consumer,  # type: ignore[arg-type]
    )

    runner.consume_forever()

    assert producer.published == []
    assert consumer.commits == 0


def test_llm_failure_yields_degraded_templated_rationale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_gateway(monkeypatch, fail=True)
    result = llm_rationale(
        _settings(),
        system="You are the risk agent.",
        prompt="score=0.1",
        trace_id="trace_1",
    )
    assert result.degraded is True
    assert "templated" in result.text
    assert "score=0.1" in result.text


def test_graph_degraded_rationale_sets_verdict_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_gateway(monkeypatch, fail=True)
    compiled = build_agent_graph()
    result = run_agent_graph(
        compiled=compiled,
        agent_name="risk",
        score_fn=_approve_score,
        settings=_settings(),
        payload=_evaluate_envelope().payload,
        trace_id="trace_1",
    )
    assert result.verdict.degraded is True
    assert "templated" in result.verdict.rationale
