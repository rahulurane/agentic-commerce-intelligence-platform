"""FastAPI app for payment-processor-sim (docs/06 §2).

A stateless service: ``POST /v1/charge`` returns a simulated charge result whose
outcome and latency come from :class:`acip_common.config.Settings`. ``GET /healthz``
and ``GET /readyz`` give liveness/readiness; the simulator holds no external state so
readiness is immediate. Structured logging is configured via ``acip_common.logging``
and each request binds the ``trace_id`` supplied in the body metadata.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from acip_common.config import Settings, get_settings
from acip_common.logging import bind_trace_id, configure_logging
from payment_processor_sim.sim import ProcessorFailure, simulate_charge

configure_logging()
_log = logging.getLogger("payment_processor_sim")

app = FastAPI(title="payment-processor-sim", version="0.1.0")


class ChargeRequest(BaseModel):
    """``POST /v1/charge`` request body (docs/06 §2)."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    amount: float
    currency: str
    route: str
    trace_id: str | None = None


class ChargeResponse(BaseModel):
    """``POST /v1/charge`` response body (docs/06 §2)."""

    status: str
    processor: str
    auth_code: str | None = None
    latency_ms: int


class HealthResponse(BaseModel):
    """Liveness/readiness probe body."""

    status: str


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness probe: the process is up."""
    return HealthResponse(status="ok")


@app.get("/readyz", response_model=HealthResponse)
def readyz() -> HealthResponse:
    """Readiness probe: the stateless simulator is always ready."""
    return HealthResponse(status="ready")


@app.post("/v1/charge", response_model=ChargeResponse)
def charge(req: ChargeRequest) -> ChargeResponse:
    """Simulate a charge; outcome/latency driven by Settings (docs/06 §2)."""
    bind_trace_id(req.trace_id)
    try:
        settings: Settings = get_settings()
        try:
            result = simulate_charge(route=req.route, settings=settings)
        except ProcessorFailure as exc:
            # Model a processor timeout/error as a 503 so the caller (routing retry /
            # decision engine) can fail over to an alternate route (docs/06 §5).
            _log.warning(
                "processor charge failed",
                extra={
                    "transaction_id": req.transaction_id,
                    "route": req.route,
                    "failure_mode": exc.mode.value,
                },
            )
            raise HTTPException(
                status_code=503, detail=f"processor failure: {exc.mode.value}"
            ) from exc

        _log.info(
            "processor charge settled",
            extra={
                "transaction_id": req.transaction_id,
                "route": req.route,
                "status": result.status.value,
                "latency_ms": result.latency_ms,
            },
        )
        return ChargeResponse(
            status=result.status.value,
            processor=result.processor,
            auth_code=result.auth_code,
            latency_ms=result.latency_ms,
        )
    finally:
        bind_trace_id(None)
