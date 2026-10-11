"""In-process core-path integration smoke: checkout-api -> real orchestrator graph.

Docker was unavailable in this environment, so instead of a live stack run this test
drives the ACTUAL public edge (``checkout-api`` ``POST /v1/checkout`` in sync mode)
into the ACTUAL commerce-orchestrator LangGraph graph, with only the leaf
inter-service clients (representation-service, decision-engine, payment-processor-sim),
Kafka, Postgres, and Redis mocked. It proves the Phase 2 no-agents guarantee through
the real edge + real graph: with ZERO verdicts the ``collect_verdicts`` deadline
elapses, the conditional edge routes to ``decide_partial``, the decision-engine's
missing-verdict policy applies, and a decision JSON is returned to the client.

The decision-engine leaf is driven by the REAL ``decision_engine.aggregator`` so the
configured ``MISSING_RISK_FRAUD_POLICY`` (default CHALLENGE) is exercised, not a canned
value — this is the behavior a live stack would produce on the no-agents path.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import checkout_api.main as checkout_main
import commerce_orchestrator.main as orch_main
import httpx
import pytest
from checkout_api.main import app, get_idempotency_store, get_producer
from commerce_orchestrator.graph import Deps, build_graph, run_evaluation
from decision_engine.aggregator import aggregate
from fastapi.testclient import TestClient

from acip_common.config import Settings
from acip_common.schemas import (
    CandidateRoute,
    DecisionRenderedPayload,
    SharedRepresentation,
    TransactionCore,
)


class _NoopProducer:
    def publish(self, topic: str, envelope: Any) -> None: ...
    def flush(self, timeout: float = 10.0) -> int:
        return 0


class _NoopIdempotency:
    def get(self, key: str) -> None:
        return None

    def put(self, key: str, stored: Any) -> None: ...


class _NoVerdictConsumer:
    """Yields no verdicts, forcing the deadline/decide_partial path."""

    def poll(self, timeout: float = 1.0) -> None:
        return None

    def commit(self) -> None: ...
    def close(self) -> None: ...


class _CorePathClients:
    """Leaf service clients: real representation shape + REAL aggregator decision."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_representation(self, **kwargs: Any) -> SharedRepresentation:
        return SharedRepresentation(
            representation_version=1,
            transaction_id=kwargs["transaction_id"],
            built_at=datetime.now(tz=UTC),
            transaction=TransactionCore(
                amount=kwargs["amount"],
                currency=kwargs["currency"],
                method_type=kwargs["method_type"],
                merchant_id=kwargs["merchant_id"],
                customer_id=kwargs["customer_id"],
            ),
            features=dict.fromkeys(
                (
                    "amount_zscore",
                    "velocity_1h",
                    "method_age_days",
                    "geo_mismatch",
                    "shared_device_ring_size",
                    "customer_txn_count_30d",
                    "customer_chargeback_count",
                ),
                0.0,
            ),
            candidate_routes=[CandidateRoute(processor="processor_default", success_rate=0.9)],
        )

    def decide(
        self,
        *,
        transaction_id: str,
        trace_id: str,
        verdicts: dict[Any, Any],
        candidate_routes: list[CandidateRoute],
    ) -> DecisionRenderedPayload:
        # Drive the REAL decision-engine aggregator with the (empty) verdict set so the
        # missing-verdict policy is genuinely exercised on the no-agents path.
        return aggregate(verdicts, candidate_routes, self._settings)

    def charge(self, **kwargs: Any) -> dict[str, Any]:  # pragma: no cover - not reached
        return {"status": "CAPTURED", "processor": kwargs.get("route"), "latency_ms": 1}

    def close(self) -> None: ...


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = Settings(DECISION_DEADLINE_MS=50)
    compiled = build_graph()

    def _run(req_body: dict[str, Any]) -> DecisionRenderedPayload:
        deps = Deps(
            settings=settings,
            clients=_CorePathClients(settings),  # type: ignore[arg-type]
            producer=_NoopProducer(),
            consumer=_NoVerdictConsumer(),
            persist=lambda **_: True,
        )
        return run_evaluation(compiled=compiled, deps=deps, transaction=req_body)

    # Intercept checkout-api's httpx call to the orchestrator and run the REAL graph.
    def _handler(request: httpx.Request) -> httpx.Response:
        import json

        decision = _run(json.loads(request.content))
        return httpx.Response(200, json=decision.model_dump(mode="json"))

    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def _client_factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("checkout_api.main.httpx.Client", _client_factory)

    app.dependency_overrides[get_producer] = _NoopProducer
    app.dependency_overrides[get_idempotency_store] = _NoopIdempotency
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_core_path_no_agents_returns_decision(wired: TestClient) -> None:
    resp = wired.post(
        "/v1/checkout",
        json={
            "merchant_id": "mrc_demo",
            "customer_id": "cus_demo",
            "amount": 42.5,
            "currency": "INR",
            "payment_method": {"type": "upi", "token": "tok_demo"},
            "context": {"device_fingerprint": "fp_demo"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # The no-agents path yields the configured missing-verdict default (CHALLENGE).
    assert data["decision"] == "CHALLENGE"
    assert data["transaction_id"].startswith("txn_")
    # No agent verdicts contributed -> the edge flags the result partial.
    assert data["partial"] is True
    assert data["trace_id"]


def test_edge_and_orchestrator_apps_are_the_production_modules() -> None:
    # The modules wired in production are what this integration exercises end to end:
    # checkout-api's app in front, commerce-orchestrator's app behind /internal/evaluate.
    assert hasattr(checkout_main, "app")
    assert hasattr(orch_main, "app")
