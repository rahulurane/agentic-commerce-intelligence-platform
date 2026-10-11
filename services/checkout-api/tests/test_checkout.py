"""Tests for checkout-api (docs/06 §1, §5).

All external dependencies are faked via FastAPI ``dependency_overrides`` (Kafka
producer, Redis idempotency store, Postgres read model) and the orchestrator sync
call is intercepted with ``httpx.MockTransport``, so the suite runs with no broker,
Redis, Postgres, or orchestrator process.

Covered:

* request validation -> 422 on a malformed body;
* idempotency (docs/06 §5): a repeat ``idempotency_key`` returns the ORIGINAL decision
  and does NOT re-call the orchestrator (no second charge);
* sync happy path returns the docs/06 §1 decision shape;
* async mode returns 202 + a ``status_url``;
* the two GET endpoints against a fake read model, including 404 on an unknown id.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from checkout_api.idempotency import StoredDecision
from checkout_api.main import (
    app,
    get_idempotency_store,
    get_producer,
    get_read_model,
)
from fastapi.testclient import TestClient


class _FakeProducer:
    """Records published (topic, event_type) pairs instead of hitting a broker."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    def publish(self, topic: str, envelope: Any) -> None:
        self.published.append((topic, envelope.event_type.value))

    def flush(self, timeout: float = 10.0) -> int:
        return 0


class _FakeIdempotency:
    """In-memory stand-in for the Redis idempotency store."""

    def __init__(self) -> None:
        self._store: dict[str, StoredDecision] = {}

    def get(self, key: str) -> StoredDecision | None:
        return self._store.get(key)

    def put(self, key: str, stored: StoredDecision) -> None:
        self._store[key] = stored


class _FakeReadModel:
    """Fake Postgres read model seeded with a single known transaction."""

    def __init__(self) -> None:
        self.txns: dict[str, dict[str, Any]] = {
            "txn_known": {
                "transaction_id": "txn_known",
                "customer_id": "cus_1",
                "amount": 120.0,
                "status": "CHALLENGED",
                "decision": "CHALLENGE",
                "composite_score": 0.0,
                "strategy": "weighted_veto",
                "verdicts": [],
                "created_at": None,
            }
        }

    def read_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        return self.txns.get(transaction_id)

    def read_explain(self, transaction_id: str) -> dict[str, Any] | None:
        txn = self.txns.get(transaction_id)
        if txn is None:
            return None
        return {
            "transaction_id": txn["transaction_id"],
            "inputs": {"customer_id": txn["customer_id"], "amount": txn["amount"]},
            "verdicts": txn["verdicts"],
            "strategy": txn["strategy"],
            "final_decision": {
                "decision": txn["decision"],
                "composite_score": txn["composite_score"],
                "status": txn["status"],
            },
        }


_RENDERED_CHALLENGE = {
    "decision": "CHALLENGE",
    "composite_score": 0.0,
    "strategy": "weighted_veto",
    "route": "processor_default",
    "route_alternatives": [],
    "recommended_method": None,
    "contributing_verdicts": [],
    "explanation": "no verdicts received, deadline elapsed, applying missing-verdict policy",
    "degraded_agents": [],
}


@pytest.fixture
def fakes() -> Iterator[dict[str, Any]]:
    producer = _FakeProducer()
    idem = _FakeIdempotency()
    reads = _FakeReadModel()
    app.dependency_overrides[get_producer] = lambda: producer
    app.dependency_overrides[get_idempotency_store] = lambda: idem
    app.dependency_overrides[get_read_model] = lambda: reads
    yield {"producer": producer, "idem": idem, "reads": reads}
    app.dependency_overrides.clear()


@pytest.fixture
def mock_orchestrator(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Intercept the orchestrator sync call, counting invocations (detects re-charge)."""
    counter = {"calls": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        counter["calls"] += 1
        return httpx.Response(200, json=_RENDERED_CHALLENGE)

    transport = httpx.MockTransport(_handler)
    real_client = httpx.Client

    def _client_factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("checkout_api.main.httpx.Client", _client_factory)
    return counter


def _valid_body() -> dict[str, Any]:
    return {
        "merchant_id": "mrc_1",
        "customer_id": "cus_1",
        "amount": 120.0,
        "currency": "INR",
        "payment_method": {"type": "upi", "token": "tok_1"},
        "context": {"device_fingerprint": "fp_1"},
    }


def test_invalid_body_returns_422(fakes: dict[str, Any]) -> None:
    client = TestClient(app)
    bad = _valid_body()
    del bad["amount"]  # required field missing
    assert client.post("/v1/checkout", json=bad).status_code == 422


def test_unknown_field_returns_422(fakes: dict[str, Any]) -> None:
    client = TestClient(app)
    bad = _valid_body()
    bad["surprise"] = "nope"  # extra fields forbidden
    assert client.post("/v1/checkout", json=bad).status_code == 422


def test_sync_happy_path_returns_decision(
    fakes: dict[str, Any], mock_orchestrator: dict[str, int]
) -> None:
    client = TestClient(app)
    resp = client.post("/v1/checkout", json=_valid_body())
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "CHALLENGE"
    assert data["transaction_id"].startswith("txn_")
    assert data["route"] == "processor_default"
    assert "verdicts" in data
    assert "trace_id" in data
    assert data["partial"] is True
    # txn.created was emitted on the lifecycle topic.
    assert fakes["producer"].published == [("txn.lifecycle", "txn.created")]
    assert mock_orchestrator["calls"] == 1


def test_idempotent_repeat_returns_original_and_does_not_recharge(
    fakes: dict[str, Any], mock_orchestrator: dict[str, int]
) -> None:
    client = TestClient(app)
    body = _valid_body()
    body["idempotency_key"] = "idem_123"

    first = client.post("/v1/checkout", json=body)
    assert first.status_code == 200
    first_txn = first.json()["transaction_id"]

    second = client.post("/v1/checkout", json=body)
    assert second.status_code == 200
    # Same decision and transaction id replayed from the store.
    assert second.json()["transaction_id"] == first_txn
    assert second.json() == first.json()
    # The orchestrator (and thus any charge) was called exactly once, not twice.
    assert mock_orchestrator["calls"] == 1


def test_async_idempotent_repeat_returns_same_txn_and_emits_once(fakes: dict[str, Any]) -> None:
    """A repeated async idempotency_key replays the same txn id and emits txn.created once."""
    client = TestClient(app)
    body = _valid_body()
    body["idempotency_key"] = "idem_async_1"

    first = client.post("/v1/checkout?mode=async", json=body)
    assert first.status_code == 202
    first_txn = first.json()["transaction_id"]

    second = client.post("/v1/checkout?mode=async", json=body)
    # Replayed from the store: same transaction id, same body, no re-mint.
    assert second.json()["transaction_id"] == first_txn
    assert second.json() == first.json()
    # txn.created was published exactly once across the two identical async requests.
    assert fakes["producer"].published == [("txn.lifecycle", "txn.created")]


def test_async_mode_returns_202_with_status_url(fakes: dict[str, Any]) -> None:
    client = TestClient(app)
    resp = client.post("/v1/checkout?mode=async", json=_valid_body())
    assert resp.status_code == 202
    data = resp.json()
    assert data["transaction_id"].startswith("txn_")
    assert data["status_url"] == f"/v1/transactions/{data['transaction_id']}"


def test_async_mode_via_header(fakes: dict[str, Any]) -> None:
    client = TestClient(app)
    resp = client.post("/v1/checkout", json=_valid_body(), headers={"X-ACIP-Mode": "async"})
    assert resp.status_code == 202


def test_get_transaction_found_and_404(fakes: dict[str, Any]) -> None:
    client = TestClient(app)
    ok = client.get("/v1/transactions/txn_known")
    assert ok.status_code == 200
    assert ok.json()["decision"] == "CHALLENGE"
    assert client.get("/v1/transactions/txn_missing").status_code == 404


def test_explain_found_and_404(fakes: dict[str, Any]) -> None:
    client = TestClient(app)
    ok = client.get("/v1/transactions/txn_known/explain")
    assert ok.status_code == 200
    body = ok.json()
    assert body["final_decision"]["decision"] == "CHALLENGE"
    assert body["strategy"] == "weighted_veto"
    assert client.get("/v1/transactions/txn_missing/explain").status_code == 404


class _MissingTableReadModel:
    """Read model that simulates a never-seeded stack: tables do not exist -> None.

    ``PostgresReadModel._fetch`` catches ``psycopg.errors.UndefinedTable`` and returns
    ``None`` so the route answers 404; this fake short-circuits to that same ``None`` so
    the route behavior (404, not 500) is exercised without a live Postgres.
    """

    def read_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        return None

    def read_explain(self, transaction_id: str) -> dict[str, Any] | None:
        return None


def test_missing_table_returns_404_not_500(fakes: dict[str, Any]) -> None:
    # Swap in a read model that behaves as a never-seeded stack (no tables -> None).
    app.dependency_overrides[get_read_model] = lambda: _MissingTableReadModel()
    client = TestClient(app)
    assert client.get("/v1/transactions/txn_any").status_code == 404
    assert client.get("/v1/transactions/txn_any/explain").status_code == 404


def test_postgres_read_model_missing_table_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``PostgresReadModel._fetch`` maps a missing table to ``None`` (unknown id -> 404)."""
    import psycopg
    from checkout_api.reads import PostgresReadModel

    def _raise_undefined_table(*args: Any, **kwargs: Any) -> Any:
        raise psycopg.errors.UndefinedTable('relation "transactions" does not exist')

    # reads.py imports psycopg lazily inside _fetch, so patch the real module attribute.
    monkeypatch.setattr(psycopg, "connect", _raise_undefined_table)
    model = PostgresReadModel("postgresql://unseeded")
    assert model.read_transaction("txn_x") is None
    assert model.read_explain("txn_x") is None


def test_health_and_ready() -> None:
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
