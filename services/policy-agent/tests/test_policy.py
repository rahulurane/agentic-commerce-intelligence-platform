"""Tests for policy-agent compliance rules + runner publish/commit (docs/02 §3, §6, §1).

llm-gateway and Kafka are mocked/injected; the policy agent makes no ml call. The
FEAT-002 contracts and the threshold-separation design are asserted: a sanctioned-geo
slice (home_geo 'XX') hard-veto DECLINEs with a ``sanctioned_geo`` evidence rule; an
amount ABOVE ``policy_amount_hard_cap`` DECLINEs; the 4800 high-value slice does NOT
policy-decline (it sits below the hard cap, so the merchant agent challenges it); a
clean slice ALLOWs; an llm-gateway failure degrades the rationale; and the runner
publishes then commits in that order.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from policy_agent.agent import build_runner
from policy_agent.scorer import build_score_fn, evaluate_rules

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
    txn_id: str = "txn_policy",
    *,
    home_geo: str | None = "IN",
    txn_geo: str | None = None,
    amount: float = 200.0,
) -> SharedRepresentation:
    return SharedRepresentation(
        representation_version=1,
        transaction_id=txn_id,
        built_at=datetime.now(tz=UTC),
        transaction=TransactionCore(
            amount=amount,
            currency="INR",
            method_type=MethodType.WALLET,
            merchant_id="mer_1",
            customer_id="cus_1",
        ),
        home_geo=home_geo,
        txn_geo=txn_geo,
    )


def _evaluate_envelope(txn_id: str = "txn_sanctioned") -> EventEnvelope:
    payload = TxnEvaluateRequestedPayload(
        representation=_representation(txn_id, home_geo="XX"),
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
        return httpx.Response(200, json={"text": "sanctioned geography; deny"})

    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def _factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("acip_agent_common.rationale.httpx.Client", _factory)


def test_sanctioned_geo_declines() -> None:
    settings = _settings()
    score_fn = build_score_fn(settings)
    result = score_fn(_representation(home_geo="XX"), {})
    assert result.decision_hint is DecisionHint.DECLINE
    assert result.score == pytest.approx(1.0)
    assert [ev.signal for ev in result.evidence] == ["sanctioned_geo"]


def test_amount_above_hard_cap_declines() -> None:
    settings = _settings()
    score_fn = build_score_fn(settings)
    # Above the 10000.0 hard cap -> policy hard veto.
    result = score_fn(_representation(home_geo="IN", amount=15000.0), {})
    assert result.decision_hint is DecisionHint.DECLINE
    assert "amount_over_hard_cap" in {ev.signal for ev in result.evidence}


def test_high_value_midrisk_does_not_policy_decline() -> None:
    settings = _settings()
    # 4800 is above the merchant challenge band (4000) but BELOW the policy hard cap
    # (10000), so policy must NOT decline it — the merchant agent challenges it instead.
    assert settings.merchant_high_value_challenge < 4800.0 < settings.policy_amount_hard_cap
    score_fn = build_score_fn(settings)
    result = score_fn(_representation(home_geo="US", amount=4800.0), {})
    assert result.decision_hint is DecisionHint.APPROVE
    assert result.evidence == []


def test_clean_slice_allows() -> None:
    score_fn = build_score_fn(_settings())
    result = score_fn(_representation(home_geo="IN", amount=120.0), {})
    assert result.decision_hint is DecisionHint.APPROVE
    assert result.score == pytest.approx(0.0)


def test_evaluate_rules_matches_txn_geo_too() -> None:
    settings = _settings()
    violated = evaluate_rules(_representation(home_geo="IN", txn_geo="XX"), settings)
    assert violated == ["sanctioned_geo"]


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
    assert envelope.transaction_id == "txn_sanctioned"
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
    assert verdict.decision_hint is DecisionHint.DECLINE
