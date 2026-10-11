"""FastAPI app for llm-gateway (docs/04 §6 ``POST /v1/complete``).

Selects the active provider from :class:`acip_common.config.Settings` and wraps it in a
per-provider circuit breaker that degrades to the fallback (mock) provider, so the
service answers even with no cloud credentials (docs/04 §4, §5). Every provider is
normalized to :class:`llm_gateway.providers.base.LLMResponse`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from acip_common.config import Settings, get_settings
from acip_common.logging import bind_trace_id, configure_logging
from llm_gateway.breaker import CircuitBreaker
from llm_gateway.providers.base import LLMProvider, LLMRequest
from llm_gateway.providers.gemini import GeminiAdapter
from llm_gateway.providers.mock import MockAdapter

configure_logging()
_log = logging.getLogger("llm_gateway")

app = FastAPI(title="llm-gateway", version="0.1.0")


def _build_provider(name: str, settings: Settings) -> LLMProvider:
    """Construct an adapter by name. Unknown providers fall back to mock.

    Construction never performs network/credential resolution (the Gemini client is
    built lazily at call time), so this is safe with no ADC present (docs/04 §4).
    """
    key = name.strip().lower()
    if key == "mock":
        return MockAdapter(model=settings.llm_model)
    if key == "gemini":
        return GeminiAdapter(model=settings.llm_model)
    # Other providers (openai/anthropic/llama) are not implemented in this POC; the
    # safe default is the offline mock so the stack always answers (docs/04 §3).
    _log.warning("unknown llm provider; using mock", extra={"requested": name})
    return MockAdapter(model=settings.llm_model)


def _build_breaker(settings: Settings) -> CircuitBreaker:
    """Build the primary provider guarded by a breaker that degrades to the fallback."""
    primary = _build_provider(settings.llm_provider, settings)
    fallback = _build_provider(settings.llm_fallback_provider, settings)
    return CircuitBreaker(primary=primary, fallback=fallback)


class CompleteRequest(BaseModel):
    """``POST /v1/complete`` request body (docs/04 §6)."""

    model_config = ConfigDict(extra="forbid")

    system: str
    prompt: str
    temperature: float = 0.2
    max_tokens: int = 512
    response_schema: dict[str, object] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class TokenUsageModel(BaseModel):
    """Serialized token usage."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class CompleteResponse(BaseModel):
    """Normalized completion response (docs/04 §2, §6)."""

    text: str
    structured: dict[str, object] | None = None
    provider: str
    model: str
    usage: TokenUsageModel
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
    """Readiness probe: the gateway is ready once providers are wired.

    Readiness never depends on the primary being reachable — a degraded primary is
    handled by the breaker, so the gateway is ready as long as the fallback exists.
    """
    return HealthResponse(status="ready")


@app.post("/v1/complete", response_model=CompleteResponse)
async def complete(req: CompleteRequest) -> CompleteResponse:
    """Produce a normalized completion, degrading to mock if needed (docs/04 §6)."""
    trace_id = req.metadata.get("trace_id")
    bind_trace_id(str(trace_id) if trace_id is not None else None)
    try:
        settings = get_settings()
        breaker = _build_breaker(settings)
        llm_req = LLMRequest(
            system=req.system,
            prompt=req.prompt,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            response_schema=req.response_schema,
            metadata=req.metadata,
        )
        resp = await breaker.complete(llm_req)
        _log.info(
            "completion served",
            extra={"provider": resp.provider, "model": resp.model, "latency_ms": resp.latency_ms},
        )
        return CompleteResponse(
            text=resp.text,
            structured=resp.structured,
            provider=resp.provider,
            model=resp.model,
            usage=TokenUsageModel(
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
                total_tokens=resp.usage.total_tokens,
            ),
            latency_ms=resp.latency_ms,
        )
    finally:
        bind_trace_id(None)
