"""Tests for the representation builder + endpoint (docs/03 §8).

Covers the two cases FEAT-003 calls out:

* **sparse-graph fallback** — absent/empty stores still yield a valid
  :class:`SharedRepresentation` with all 7 ``FEATURE_COLUMNS`` populated and a single
  default candidate route, flagged degraded.
* **full-graph** — hydrated graph + hot signals flow through ``build_feature_row`` and
  the method history / candidate routes land on the representation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from representation_service.builder import build_representation
from representation_service.main import app
from representation_service.stores import GraphSignals, HotSignals

from acip_common.features import FEATURE_COLUMNS


def _build(**overrides: object):  # type: ignore[no-untyped-def]
    base: dict[str, object] = {
        "transaction_id": "txn_1",
        "amount": 120.0,
        "currency": "INR",
        "method_type": "upi",
        "merchant_id": "mer_1",
        "customer_id": "cus_1",
        "txn_geo": "IN",
        "device_fingerprint": "dev_1",
        "graph": GraphSignals(),
        "hot": HotSignals(),
        "representation_version": 1,
        "graph_degraded": True,
        "hot_degraded": True,
    }
    base.update(overrides)
    return build_representation(**base)  # type: ignore[arg-type]


def test_sparse_graph_fallback_populates_all_features() -> None:
    # Both stores absent -> degraded, defaults filled, every feature present.
    result = _build(graph_degraded=True, hot_degraded=True)
    rep = result.representation
    assert result.degraded is True
    # All 7 canonical feature columns present.
    assert set(rep.features.keys()) == set(FEATURE_COLUMNS)
    assert len(rep.features) == len(FEATURE_COLUMNS)
    # A single default candidate route so routing/decision overlays still work.
    assert len(rep.candidate_routes) == 1
    assert rep.candidate_routes[0].processor == "processor_default"
    # Empty graph -> zeroed graph-derived features.
    assert rep.features["shared_device_ring_size"] == 0.0
    assert rep.features["customer_txn_count_30d"] == 0.0
    assert rep.features["customer_chargeback_count"] == 0.0


def test_full_graph_flows_through_feature_row() -> None:
    graph = GraphSignals(
        ring_size=5,
        customer_txn_count_30d=12,
        customer_chargeback_count=2,
        home_geo="IN",
        method_history={"upi": (18, 1)},
        candidate_routes=[
            {"processor": "processor_a", "success_rate": 0.97, "cost_bps": 85},
            {"processor": "processor_b", "success_rate": 0.90, "cost_bps": 70},
        ],
    )
    hot = HotSignals(velocity_1h=3)
    result = _build(
        graph=graph,
        hot=hot,
        txn_geo="IN",
        graph_degraded=False,
        hot_degraded=False,
    )
    rep = result.representation
    assert result.degraded is False
    assert set(rep.features.keys()) == set(FEATURE_COLUMNS)
    assert rep.features["shared_device_ring_size"] == 5.0
    assert rep.features["customer_txn_count_30d"] == 12.0
    assert rep.features["customer_chargeback_count"] == 2.0
    assert rep.features["velocity_1h"] == 3.0
    assert rep.features["geo_mismatch"] == 0.0  # txn_geo == home_geo
    # Method history + candidate routes surface on the representation.
    assert rep.method_history["upi"].successes == 18
    assert rep.method_history["upi"].failures == 1
    assert [r.processor for r in rep.candidate_routes] == ["processor_a", "processor_b"]


def test_geo_mismatch_when_geos_differ() -> None:
    graph = GraphSignals(home_geo="US")
    result = _build(graph=graph, txn_geo="IN", graph_degraded=False, hot_degraded=False)
    assert result.representation.features["geo_mismatch"] == 1.0


def test_endpoint_degrades_without_stores() -> None:
    # No Neo4j/Redis running in tests -> endpoint still returns a valid representation.
    client = TestClient(app)
    resp = client.post(
        "/v1/representation",
        json={
            "transaction_id": "txn_api",
            "amount": 250.0,
            "currency": "INR",
            "method_type": "card",
            "merchant_id": "mer_1",
            "customer_id": "cus_api",
            "txn_geo": "IN",
            "device_fingerprint": "dev_api",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transaction_id"] == "txn_api"
    assert set(body["features"].keys()) == set(FEATURE_COLUMNS)
    assert len(body["candidate_routes"]) >= 1


def test_health_and_ready() -> None:
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
