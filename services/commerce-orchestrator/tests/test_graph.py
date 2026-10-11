"""Tests for the commerce-orchestrator LangGraph evaluation graph (docs/02 §2.1).

All external dependencies (representation-service, decision-engine,
payment-processor-sim, Kafka producer/consumer, Postgres persistence) are mocked, so
the graph transitions are exercised in-process with no broker, HTTP, or DB.

The two paths FEAT-003 calls out are asserted:

* **zero-verdict deadline -> decide_partial** — the Phase 2 no-agents guarantee: the
  consumer yields no verdicts, ``collect_verdicts`` hits the deadline, the conditional
  edge routes to ``decide_partial``, and a decision is still produced.
* **all_received -> decide** — when the consumer supplies all six verdicts before the
  deadline, the edge routes to ``decide`` instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from commerce_orchestrator.graph import Deps, build_graph, run_evaluation
from commerce_orchestrator.nodes import route_after_collect

from acip_common.config import Settings
from acip_common.schemas import (
    AgentName,
    AgentVerdictProducedPayload,
    CandidateRoute,
    DecisionHint,
    DecisionRenderedPayload,
    EventEnvelope,
    EventType,
    MethodType,
    SharedRepresentation,
    TransactionCore,
    Verdict,
)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"DECISION_DEADLINE_MS": 150}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


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
        features={
            "amount_zscore": 0.0,
            "velocity_1h": 0.0,
            "method_age_days": 0.0,
            "geo_mismatch": 0.0,
            "shared_device_ring_size": 0.0,
            "customer_txn_count_30d": 0.0,
            "customer_chargeback_count": 0.0,
        },
        candidate_routes=[CandidateRoute(processor="processor_a", success_rate=0.97)],
    )


class _FakeClients:
    """Mocked downstream HTTP clients recording what the graph asked for."""

    def __init__(self, decision: DecisionRenderedPayload) -> None:
        self._decision = decision
        self.decide_calls: list[dict[AgentName, Verdict]] = []
        self.charge_calls: list[str] = []

    def build_representation(self, **_: object) -> SharedRepresentation:
        return _representation()

    def decide(
        self,
        *,
        transaction_id: str,
        trace_id: str,
        verdicts: dict[AgentName, Verdict],
        candidate_routes: list[CandidateRoute],
    ) -> DecisionRenderedPayload:
        self.decide_calls.append(verdicts)
        return self._decision

    def charge(self, *, route: str, **_: object) -> dict[str, Any]:
        self.charge_calls.append(route)
        return {"status": "CAPTURED", "processor": route, "auth_code": "AUTH1", "latency_ms": 10}

    def close(self) -> None:  # pragma: no cover - not used in tests
        pass


class _FakeProducer:
    """Mocked Kafka producer recording published (topic, event_type) pairs."""

    def __init__(self) -> None:
        self.published: list[tuple[str, EventType]] = []

    def publish(self, topic: str, envelope: EventEnvelope) -> None:
        self.published.append((topic, envelope.event_type))

    def flush(self, timeout: float = 10.0) -> int:
        return 0


class _FakeConsumer:
    """Mocked verdict consumer that yields a fixed queue of envelopes then None."""

    def __init__(self, envelopes: list[EventEnvelope] | None = None) -> None:
        self._queue = list(envelopes or [])
        self.commits = 0

    def poll(self, timeout: float = 1.0) -> EventEnvelope | None:
        return self._queue.pop(0) if self._queue else None

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:  # pragma: no cover - not used in tests
        pass


def _verdict_envelope(agent: AgentName, hint: DecisionHint, score: float) -> EventEnvelope:
    payload = AgentVerdictProducedPayload(
        agent=agent,
        produced_at=datetime.now(tz=UTC),
        verdict=Verdict(
            decision_hint=hint,
            score=score,
            confidence=0.9,
            rationale="",
            evidence=[],
            model_version="test-v1",
        ),
    )
    return EventEnvelope(
        event_id="evt_1",
        event_type=EventType.AGENT_VERDICT_PRODUCED,
        transaction_id="txn_1",
        trace_id="trace_1",
        occurred_at=datetime.now(tz=UTC),
        producer="risk-agent",
        payload=payload.model_dump(mode="json"),
    )


def _deps(clients: _FakeClients, consumer: _FakeConsumer) -> tuple[Deps, list[dict[str, Any]]]:
    persisted: list[dict[str, Any]] = []

    def _persist(**kwargs: object) -> bool:
        persisted.append(dict(kwargs))
        return True

    deps = Deps(
        settings=_settings(),
        clients=clients,  # type: ignore[arg-type]
        producer=_FakeProducer(),
        consumer=consumer,
        persist=_persist,
    )
    return deps, persisted


def _transaction() -> dict[str, Any]:
    return {
        "transaction_id": "txn_1",
        "trace_id": "trace_1",
        "amount": 120.0,
        "currency": "INR",
        "method_type": "upi",
        "merchant_id": "mer_1",
        "customer_id": "cus_1",
        "txn_geo": "IN",
        "device_fingerprint": "dev_1",
    }


def _challenge_decision() -> DecisionRenderedPayload:
    return DecisionRenderedPayload(
        decision=DecisionHint.CHALLENGE,
        composite_score=0.0,
        strategy="weighted_veto",
        route="processor_a",
        explanation="missing-verdict policy -> CHALLENGE",
    )


def _approve_decision() -> DecisionRenderedPayload:
    return DecisionRenderedPayload(
        decision=DecisionHint.APPROVE,
        composite_score=0.1,
        strategy="weighted_veto",
        route="processor_a",
        explanation="composite 0.10 banded to APPROVE",
    )


def test_route_after_collect_branches() -> None:
    assert route_after_collect({"deadline_reached": True}) == "decide_partial"
    assert route_after_collect({"deadline_reached": False}) == "decide"


def test_zero_verdict_deadline_reaches_decide_partial_decision() -> None:
    # Phase 2 critical path: no agents -> deadline -> decide_partial -> a decision.
    clients = _FakeClients(_challenge_decision())
    consumer = _FakeConsumer(envelopes=[])  # no verdicts ever arrive
    deps, persisted = _deps(clients, consumer)

    compiled = build_graph()
    decision = run_evaluation(compiled=compiled, deps=deps, transaction=_transaction())

    # A decision IS produced despite zero verdicts.
    assert decision.decision is DecisionHint.CHALLENGE
    # decide was called exactly once, with an EMPTY verdict set (the partial path).
    assert len(clients.decide_calls) == 1
    assert clients.decide_calls[0] == {}
    # CHALLENGE is non-executable -> no charge.
    assert clients.charge_calls == []
    # finalize persisted the trace.
    assert len(persisted) == 1


def test_all_verdicts_before_deadline_takes_decide_path_and_charges() -> None:
    clients = _FakeClients(_approve_decision())
    envelopes = [_verdict_envelope(agent, DecisionHint.APPROVE, 0.1) for agent in AgentName]
    consumer = _FakeConsumer(envelopes=envelopes)
    deps, persisted = _deps(clients, consumer)

    compiled = build_graph()
    decision = run_evaluation(compiled=compiled, deps=deps, transaction=_transaction())

    assert decision.decision is DecisionHint.APPROVE
    # All six verdicts were collected and passed to decide (the full-set path).
    assert len(clients.decide_calls) == 1
    assert set(clients.decide_calls[0].keys()) == set(AgentName)
    assert consumer.commits == len(list(AgentName))
    # APPROVE is executable -> processor charged on the chosen route.
    assert clients.charge_calls == ["processor_a"]
    assert len(persisted) == 1


def test_evaluate_endpoint_runs_with_no_broker(monkeypatch: Any) -> None:
    # The /internal/evaluate endpoint should run end to end with mocked deps.
    import commerce_orchestrator.main as main_mod
    from fastapi.testclient import TestClient

    clients = _FakeClients(_challenge_decision())
    consumer = _FakeConsumer(envelopes=[])

    monkeypatch.setattr(main_mod, "ServiceClients", lambda settings: clients)
    monkeypatch.setattr(main_mod, "EventProducer", lambda *a, **k: _FakeProducer())
    monkeypatch.setattr(main_mod, "EventConsumer", lambda *a, **k: consumer)
    monkeypatch.setattr(main_mod, "persist_decision", lambda *a, **k: True)

    class _NoopSnapshots:
        def save(self, *a: object, **k: object) -> None: ...
        def close(self) -> None: ...

    monkeypatch.setattr(main_mod, "RedisStateSnapshotStore", lambda url: _NoopSnapshots())

    client = TestClient(main_mod.app)
    resp = client.post(
        "/internal/evaluate",
        json={
            "transaction_id": "txn_1",
            "amount": 120.0,
            "currency": "INR",
            "method_type": "upi",
            "merchant_id": "mer_1",
            "customer_id": "cus_1",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "CHALLENGE"


def test_health_and_ready() -> None:
    import commerce_orchestrator.main as main_mod
    from fastapi.testclient import TestClient

    client = TestClient(main_mod.app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
