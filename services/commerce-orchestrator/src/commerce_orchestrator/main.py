"""FastAPI app for commerce-orchestrator (docs/06 §2, docs/02 §2.1).

``POST /internal/evaluate`` is the synchronous trigger checkout-api uses (docs/06 §2):
it takes a transaction, runs the LangGraph evaluation graph to completion, and returns
the rendered decision JSON. The graph drives
``build_representation -> fan_out -> collect_verdicts -> decide/decide_partial ->
execute -> finalize``; with no agents running the deadline path still reaches a
decision (FEAT-003 guarantee).

The compiled graph is built once at import; per-request dependencies (HTTP clients,
Kafka producer/consumer) are constructed per call and closed in a ``finally`` so a
failed request never leaks a connection. ``GET /readyz`` is immediate — the
orchestrator holds no external state it must load before serving (its callees have
their own readiness).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from acip_common.config import Settings, get_settings
from acip_common.kafka import EventConsumer, EventProducer
from acip_common.logging import bind_trace_id, configure_logging
from acip_common.schemas import DecisionRenderedPayload, MethodType
from acip_common.topics import AGENT_VERDICTS
from commerce_orchestrator.clients import ServiceClients
from commerce_orchestrator.graph import Deps, RedisStateSnapshotStore, build_graph, run_evaluation
from commerce_orchestrator.persistence import persist_decision

configure_logging()
_log = logging.getLogger("commerce_orchestrator")

app = FastAPI(title="commerce-orchestrator", version="0.1.0")

# Compile the graph once; it is stateless aside from the injected per-request deps.
_COMPILED = build_graph()

# Consumer group for verdict collection (docs/02 §6). A stable group id lets the
# orchestrator resume consuming after a restart.
_VERDICT_GROUP = "commerce-orchestrator-verdicts"


class EvaluateRequest(BaseModel):
    """``POST /internal/evaluate`` request body (docs/06 §2)."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str | None = None
    trace_id: str | None = None
    amount: float
    currency: str
    method_type: MethodType
    merchant_id: str
    customer_id: str
    txn_geo: str | None = None
    device_fingerprint: str | None = None


class HealthResponse(BaseModel):
    """Liveness/readiness probe body."""

    status: str


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness probe: the process is up."""
    return HealthResponse(status="ok")


@app.get("/readyz", response_model=HealthResponse)
def readyz() -> HealthResponse:
    """Readiness probe: the orchestrator is always ready (callees gate themselves)."""
    return HealthResponse(status="ready")


@app.post("/internal/evaluate", response_model=DecisionRenderedPayload)
def evaluate(req: EvaluateRequest) -> DecisionRenderedPayload:
    """Run the evaluation graph synchronously and return the decision (docs/06 §2)."""
    settings: Settings = get_settings()
    transaction_id = req.transaction_id or f"txn_{uuid.uuid4().hex[:16]}"
    trace_id = req.trace_id or str(uuid.uuid4())
    bind_trace_id(trace_id)

    clients = ServiceClients(settings)
    producer = EventProducer(settings.kafka_bootstrap)
    consumer = EventConsumer(settings.kafka_bootstrap, _VERDICT_GROUP, [AGENT_VERDICTS])
    snapshots = RedisStateSnapshotStore(settings.redis_url)

    def _persist(**kwargs: object) -> bool:
        return persist_decision(settings.postgres_dsn, **kwargs)  # type: ignore[arg-type]

    deps = Deps(
        settings=settings,
        clients=clients,
        producer=producer,
        consumer=consumer,
        persist=_persist,
    )
    try:
        _log.info("evaluation started", extra={"transaction_id": transaction_id})
        decision = run_evaluation(
            compiled=_COMPILED,
            deps=deps,
            transaction={
                "transaction_id": transaction_id,
                "trace_id": trace_id,
                "amount": req.amount,
                "currency": req.currency,
                "method_type": req.method_type.value,
                "merchant_id": req.merchant_id,
                "customer_id": req.customer_id,
                "txn_geo": req.txn_geo,
                "device_fingerprint": req.device_fingerprint,
            },
            snapshots=snapshots,
        )
        _log.info(
            "evaluation complete",
            extra={"transaction_id": transaction_id, "decision": decision.decision.value},
        )
        return decision
    finally:
        clients.close()
        consumer.close()
        snapshots.close()
        bind_trace_id(None)


__all__ = ["app"]
