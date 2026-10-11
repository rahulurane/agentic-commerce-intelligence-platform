"""FastAPI app for representation-service (docs/03 §8, docs/01 §4 step 2).

``POST /v1/representation`` takes the transaction core plus ``transaction_id`` /
``trace_id``, hydrates graph signals (Neo4j) and hot features (Redis), builds the
shared representation via :func:`representation_service.builder.build_representation`,
caches it in Redis keyed by ``transaction_id`` (docs/03 §8), and returns it.

Store adapters are degradation-tolerant: with Neo4j/Redis empty or unreachable the
builder fills sensible defaults and the result is logged as degraded, so the whole
evaluation path still runs with nothing seeded (FEAT-003 sparse-graph fallback).
``GET /readyz`` tolerates store absence — it reports up-but-degraded rather than
failing, because the service is designed to serve a representation regardless.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from acip_common.config import Settings, get_settings
from acip_common.logging import bind_trace_id, configure_logging
from acip_common.schemas import MethodType, SharedRepresentation
from representation_service.builder import build_representation
from representation_service.stores import GraphStore, HotStore

configure_logging()
_log = logging.getLogger("representation_service")

app = FastAPI(title="representation-service", version="0.1.0")


class RepresentationRequest(BaseModel):
    """``POST /v1/representation`` request body (docs/03 §8, docs/06 §2)."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    amount: float
    currency: str
    method_type: MethodType
    merchant_id: str
    customer_id: str
    txn_geo: str | None = None
    device_fingerprint: str | None = None
    trace_id: str | None = None


class HealthResponse(BaseModel):
    """Liveness/readiness probe body."""

    status: str


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness probe: the process is up."""
    return HealthResponse(status="ok")


@app.get("/readyz", response_model=HealthResponse)
def readyz() -> HealthResponse:
    """Readiness probe: always ready; store absence is tolerated (docs/03 §8)."""
    return HealthResponse(status="ready")


@app.post("/v1/representation", response_model=SharedRepresentation)
def representation(req: RepresentationRequest) -> SharedRepresentation:
    """Build and cache the shared representation for a transaction (docs/03 §8)."""
    bind_trace_id(req.trace_id)
    settings: Settings = get_settings()
    graph_store = GraphStore(settings.neo4j_uri, settings.neo4j_auth)
    hot_store = HotStore(settings.redis_url)
    try:
        graph, graph_degraded = graph_store.fetch(
            req.customer_id, req.device_fingerprint, req.method_type.value
        )
        hot, hot_degraded = hot_store.fetch(req.customer_id)

        result = build_representation(
            transaction_id=req.transaction_id,
            amount=req.amount,
            currency=req.currency,
            method_type=req.method_type.value,
            merchant_id=req.merchant_id,
            customer_id=req.customer_id,
            txn_geo=req.txn_geo,
            device_fingerprint=req.device_fingerprint,
            graph=graph,
            hot=hot,
            representation_version=settings.representation_version,
            graph_degraded=graph_degraded,
            hot_degraded=hot_degraded,
        )

        hot_store.cache_representation(req.transaction_id, result.representation.model_dump_json())

        if result.degraded:
            _log.warning(
                "representation built in degraded mode (sparse/unreachable stores)",
                extra={
                    "transaction_id": req.transaction_id,
                    "graph_degraded": graph_degraded,
                    "hot_degraded": hot_degraded,
                },
            )
        else:
            _log.info(
                "representation built",
                extra={"transaction_id": req.transaction_id},
            )
        return result.representation
    finally:
        graph_store.close()
        hot_store.close()
        bind_trace_id(None)


__all__ = ["app"]
