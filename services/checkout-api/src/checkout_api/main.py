"""FastAPI app for checkout-api — the public checkout edge (docs/06 §1, §4, §5).

``POST /v1/checkout`` is the single public write endpoint. It:

1. validates the request body against the docs/06 §1 shape (Pydantic -> 422 on bad
   input), reusing ``PaymentMethodRef``/``CheckoutContext`` from ``acip_common``;
2. mints a ``transaction_id``;
3. honors ``idempotency_key`` (docs/06 §5): a repeat key returns the ORIGINAL stored
   decision and never re-triggers evaluation or a charge (Redis-backed store);
4. emits a ``txn.created`` event on the ``txn.lifecycle`` topic for the event log,
   using ``acip_common`` ``topic_for`` + the Kafka ``EventProducer``;
5. in the DEFAULT **sync** mode calls the orchestrator's ``POST /internal/evaluate``
   and returns the decision JSON (docs/06 §1). In **async** mode (``?mode=async`` or
   ``X-ACIP-Mode: async``) it returns ``202`` + a ``status_url``.

``GET /v1/transactions/{id}`` and ``/v1/transactions/{id}/explain`` read the Postgres
read models the orchestrator's ``finalize`` node persisted; unknown ids answer ``404``.

Phase-2 reality: with no agents running the orchestrator still returns a decision via
its deadline/``decide_partial`` path, so the ``verdicts`` block in the response may be
empty — this edge tolerates that and always returns the top-level decision fields.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from acip_common.config import Settings, get_settings
from acip_common.kafka import EventProducer
from acip_common.logging import bind_trace_id, configure_logging
from acip_common.schemas import (
    CheckoutContext,
    EventEnvelope,
    EventType,
    PaymentMethodRef,
    TxnCreatedPayload,
)
from acip_common.topics import topic_for
from checkout_api.idempotency import IdempotencyStore, StoredDecision
from checkout_api.reads import PostgresReadModel, ReadModel

configure_logging()
_log = logging.getLogger("checkout_api")

app = FastAPI(title="checkout-api", version="0.1.0")

_PRODUCER_NAME = "checkout-api"


class CheckoutRequest(BaseModel):
    """``POST /v1/checkout`` request body (docs/06 §1).

    Reuses ``acip_common`` ``PaymentMethodRef``/``CheckoutContext`` so the public edge
    speaks the same contract as the event payloads. Unknown fields are rejected (422).
    """

    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    customer_id: str
    amount: float
    currency: str
    payment_method: PaymentMethodRef
    context: CheckoutContext = CheckoutContext()
    idempotency_key: str | None = None


class HealthResponse(BaseModel):
    """Liveness/readiness probe body."""

    status: str


# --------------------------------------------------------------------------- #
# Dependency wiring (overridden in tests via app.dependency_overrides)
# --------------------------------------------------------------------------- #
def get_producer() -> EventProducer:
    """Return the Kafka producer used to emit ``txn.created`` (overridable in tests)."""
    return EventProducer(get_settings().kafka_bootstrap)


def get_idempotency_store() -> IdempotencyStore:
    """Return the Redis idempotency store (overridable in tests)."""
    return IdempotencyStore(get_settings().redis_url)


def get_read_model() -> ReadModel:
    """Return the Postgres read model for the GET endpoints (overridable in tests)."""
    return PostgresReadModel(get_settings().postgres_dsn)


# Annotated dependency aliases keep the ``Depends(...)`` call out of argument defaults
# (ruff B008) while using FastAPI's injection so tests can override via
# ``app.dependency_overrides``.
ProducerDep = Annotated[EventProducer, Depends(get_producer)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
ReadModelDep = Annotated[ReadModel, Depends(get_read_model)]


def _emit_txn_created(
    producer: EventProducer,
    *,
    transaction_id: str,
    trace_id: str,
    req: CheckoutRequest,
) -> None:
    """Publish the ``txn.created`` lifecycle event for the event log (docs/06 §3)."""
    payload = TxnCreatedPayload(
        merchant_id=req.merchant_id,
        customer_id=req.customer_id,
        amount=req.amount,
        currency=req.currency,
        payment_method=req.payment_method,
        context=req.context,
        idempotency_key=req.idempotency_key,
    )
    envelope = EventEnvelope(
        event_id=f"evt_{uuid.uuid4().hex}",
        event_type=EventType.TXN_CREATED,
        transaction_id=transaction_id,
        trace_id=trace_id,
        occurred_at=datetime.now(tz=UTC),
        producer=_PRODUCER_NAME,
        payload=payload.model_dump(mode="json"),
    )
    try:
        producer.publish(topic_for(EventType.TXN_CREATED), envelope)
        producer.flush(timeout=2.0)
    except Exception as exc:
        # The event log is for audit/async consumers; a broker hiccup must not fail the
        # synchronous checkout (the orchestrator sync trigger carries the decision).
        _log.warning(
            "txn.created publish failed; continuing degraded",
            extra={"transaction_id": transaction_id, "error": str(exc)},
        )


def _evaluate_sync(
    settings: Settings, *, transaction_id: str, trace_id: str, req: CheckoutRequest
) -> dict[str, Any]:
    """Call the orchestrator ``POST /internal/evaluate`` and shape the response (docs/06 §1)."""
    body = {
        "transaction_id": transaction_id,
        "trace_id": trace_id,
        "amount": req.amount,
        "currency": req.currency,
        "method_type": req.payment_method.type.value,
        "merchant_id": req.merchant_id,
        "customer_id": req.customer_id,
        "device_fingerprint": req.context.device_fingerprint,
    }
    timeout = max(2.0, settings.decision_deadline_ms / 1000 + 2.0)
    url = f"{settings.orchestrator_url}/internal/evaluate"
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=body)
        resp.raise_for_status()
        rendered = resp.json()
    return _public_decision(transaction_id, trace_id, rendered)


def _public_decision(
    transaction_id: str, trace_id: str, rendered: dict[str, Any]
) -> dict[str, Any]:
    """Map the orchestrator ``DecisionRenderedPayload`` to the public response (docs/06 §1).

    The ``verdicts`` block mirrors the per-agent view in docs/06 §1 but tolerates the
    Phase-2 no-agents reality: with no verdicts it is an empty object, and the top-level
    decision/route/score fields are always present.
    """
    alternatives = rendered.get("route_alternatives") or []
    return {
        "transaction_id": transaction_id,
        "decision": rendered.get("decision"),
        "route": rendered.get("route"),
        "composite_score": rendered.get("composite_score"),
        "explanation": rendered.get("explanation"),
        "recommended_method": rendered.get("recommended_method"),
        "partial": not rendered.get("contributing_verdicts"),
        "degraded_agents": rendered.get("degraded_agents") or [],
        "route_alternatives": alternatives,
        "verdicts": {},
        "trace_id": trace_id,
    }


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness probe: the process is up."""
    return HealthResponse(status="ok")


@app.get("/readyz", response_model=HealthResponse)
def readyz() -> HealthResponse:
    """Readiness probe: the edge is ready (downstream stores gate themselves)."""
    return HealthResponse(status="ready")


@app.post("/v1/checkout")
def checkout(
    req: CheckoutRequest,
    request: Request,
    response: Response,
    producer: ProducerDep,
    idempotency: IdempotencyDep,
    mode: str = Query(default="sync"),
) -> Any:
    """Create a checkout and return the decision (sync) or a status url (async)."""
    settings = get_settings()
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
    bind_trace_id(trace_id)
    header_mode = request.headers.get("x-acip-mode")
    async_mode = (header_mode or mode).lower() == "async"

    try:
        # Idempotency replay (docs/06 §5): a repeat key returns the ORIGINAL decision
        # and never re-evaluates or re-charges.
        if req.idempotency_key is not None:
            prior = idempotency.get(req.idempotency_key)
            if prior is not None:
                _log.info(
                    "idempotent replay",
                    extra={
                        "transaction_id": prior.transaction_id,
                        "idempotency_key": req.idempotency_key,
                    },
                )
                return JSONResponse(status_code=200, content=prior.decision)

        transaction_id = f"txn_{uuid.uuid4().hex[:16]}"
        _emit_txn_created(producer, transaction_id=transaction_id, trace_id=trace_id, req=req)

        if async_mode:
            _log.info("checkout accepted (async)", extra={"transaction_id": transaction_id})
            accepted = {
                "transaction_id": transaction_id,
                "status_url": f"/v1/transactions/{transaction_id}",
            }
            # Honor idempotency in async mode exactly like sync (docs/06 §5): store the
            # minted id + the 202 body so a repeat key replays the SAME transaction_id
            # (no re-mint, no second txn.created) via the replay check above.
            if req.idempotency_key is not None:
                idempotency.put(
                    req.idempotency_key,
                    StoredDecision(transaction_id=transaction_id, decision=accepted),
                )
            response.status_code = 202
            return accepted

        decision = _evaluate_sync(
            settings, transaction_id=transaction_id, trace_id=trace_id, req=req
        )
        if req.idempotency_key is not None:
            idempotency.put(
                req.idempotency_key,
                StoredDecision(transaction_id=transaction_id, decision=decision),
            )
        _log.info(
            "checkout decided",
            extra={"transaction_id": transaction_id, "decision": decision.get("decision")},
        )
        return decision
    finally:
        bind_trace_id(None)


@app.get("/v1/transactions/{transaction_id}")
def get_transaction(
    transaction_id: str,
    reads: ReadModelDep,
) -> dict[str, Any]:
    """Return current state + decision + verdicts from the read models (docs/06 §1)."""
    view = reads.read_transaction(transaction_id)
    if view is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return view


@app.get("/v1/transactions/{transaction_id}/explain")
def explain_transaction(
    transaction_id: str,
    reads: ReadModelDep,
) -> dict[str, Any]:
    """Return the full decision trace from the read models (docs/06 §1)."""
    view = reads.read_explain(transaction_id)
    if view is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return view


__all__ = ["app"]
