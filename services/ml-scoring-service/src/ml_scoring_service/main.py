"""FastAPI app for ml-scoring-service (docs/05 §2, §5, §7).

At startup the lifespan handler resolves + loads model artifacts via
``<ML_MODELS_DIR>/model_card.json`` and warms them up; ``/readyz`` reports ready only
after that load completes. ``POST /v1/score`` returns a probability, the serving
model version, and per-prediction ``top_features``. With artifacts absent the service
serves the deterministic heuristic (``heuristic-v1``) and logs a degraded notice.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from acip_common.config import get_settings
from acip_common.logging import bind_trace_id, configure_logging
from ml_scoring_service.loader import ModelRegistry, load_registry
from ml_scoring_service.scorer import score as score_features

configure_logging()
_log = logging.getLogger("ml_scoring_service")


class _State:
    """Holds the loaded registry; readiness gates on ``registry`` being set."""

    registry: ModelRegistry | None = None


_state = _State()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Load + warm up models on boot so ``/readyz`` can gate on it (docs/05 §7)."""
    settings = get_settings()
    _state.registry = load_registry(settings.ml_models_dir)
    if _state.registry.degraded:
        _log.warning(
            "serving heuristic fallback (no trained artifacts)",
            extra={"models_dir": settings.ml_models_dir},
        )
    yield


app = FastAPI(title="ml-scoring-service", version="0.1.0", lifespan=lifespan)


class ScoreRequest(BaseModel):
    """``POST /v1/score`` request body (docs/05 §2)."""

    # protected_namespaces=() so the ``model``/``model_version`` fields (docs/05 §2)
    # are allowed without clashing with pydantic's ``model_`` reserved namespace.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model: str  # "risk" | "fraud"
    model_version: str = "latest"
    features: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class TopFeature(BaseModel):
    """A per-prediction feature contribution (docs/05 §2)."""

    name: str
    contribution: float


class ScoreResponse(BaseModel):
    """``POST /v1/score`` response body (docs/05 §2)."""

    model_config = ConfigDict(protected_namespaces=())

    score: float
    model: str
    model_version: str
    top_features: list[TopFeature]
    latency_ms: int


class HealthResponse(BaseModel):
    """Liveness/readiness probe body."""

    status: str


def _registry() -> ModelRegistry:
    """Return the loaded registry (lifespan guarantees it is set before serving)."""
    if _state.registry is None:
        # Defensive: load lazily if a request somehow arrives before lifespan ran.
        _state.registry = load_registry(get_settings().ml_models_dir)
    return _state.registry


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness probe: the process is up."""
    return HealthResponse(status="ok")


@app.get("/readyz", response_model=HealthResponse)
def readyz() -> HealthResponse:
    """Readiness probe: ready only once models are loaded (docs/05 §7)."""
    if _state.registry is None:
        return HealthResponse(status="loading")
    status = "ready-degraded" if _state.registry.degraded else "ready"
    return HealthResponse(status=status)


@app.post("/v1/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    """Score the feature vector for ``req.model`` (docs/05 §2, §5)."""
    trace_id = req.metadata.get("trace_id")
    bind_trace_id(str(trace_id) if trace_id is not None else None)
    try:
        started = time.perf_counter()
        result = score_features(_registry(), req.model, req.features)
        latency_ms = int((time.perf_counter() - started) * 1000)
        _log.info(
            "score served",
            extra={
                "model": req.model,
                "model_version": result.model_version,
                "latency_ms": latency_ms,
            },
        )
        return ScoreResponse(
            score=result.score,
            model=req.model,
            model_version=result.model_version,
            top_features=[
                TopFeature(name=name, contribution=contribution)
                for name, contribution in result.top_features
            ],
            latency_ms=latency_ms,
        )
    finally:
        bind_trace_id(None)
