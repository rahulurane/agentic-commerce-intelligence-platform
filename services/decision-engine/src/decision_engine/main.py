"""FastAPI app for decision-engine (docs/06 §2 ``POST /v1/decide``).

A stateless service that wraps the pure :func:`decision_engine.aggregator.aggregate`
function. It reads all thresholds/weights from :class:`acip_common.config.Settings`,
configures structured logging, and binds the request ``trace_id`` for correlation.
``GET /readyz`` is immediate — the engine holds no external state.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from acip_common.config import get_settings
from acip_common.logging import bind_trace_id, configure_logging
from acip_common.schemas import (
    AgentName,
    CandidateRoute,
    DecisionRenderedPayload,
    Verdict,
)
from decision_engine.aggregator import aggregate

configure_logging()
_log = logging.getLogger("decision_engine")

app = FastAPI(title="decision-engine", version="0.1.0")


class DecideRequest(BaseModel):
    """``POST /v1/decide`` request body.

    ``verdicts`` is keyed by :class:`acip_common.schemas.AgentName`; a missing agent is
    simply absent from the map and handled by the aggregator's missing-verdict policy.
    """

    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    verdicts: dict[AgentName, Verdict] = Field(default_factory=dict)
    candidate_routes: list[CandidateRoute] = Field(default_factory=list)
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
    """Readiness probe: the stateless engine is always ready."""
    return HealthResponse(status="ready")


@app.post("/v1/decide", response_model=DecisionRenderedPayload)
def decide(req: DecideRequest) -> DecisionRenderedPayload:
    """Aggregate verdicts into a final decision (docs/02 §5)."""
    bind_trace_id(req.trace_id)
    try:
        settings = get_settings()
        payload = aggregate(req.verdicts, req.candidate_routes, settings)
        _log.info(
            "decision rendered",
            extra={
                "transaction_id": req.transaction_id,
                "decision": payload.decision.value,
                "composite_score": payload.composite_score,
                "strategy": payload.strategy,
            },
        )
        return payload
    finally:
        bind_trace_id(None)
