"""Tests for llm-gateway: mock structured output + breaker fallback (docs/04)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from llm_gateway.breaker import BreakerConfig, CircuitBreaker
from llm_gateway.main import app
from llm_gateway.providers.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderHealth,
)
from llm_gateway.providers.mock import MockAdapter


def test_mock_adapter_structured_output() -> None:
    adapter = MockAdapter()
    req = LLMRequest(
        system="explain",
        prompt="Score 0.87. Top signals: shared_device_ring_size=4, velocity_1h=11.",
        response_schema={"rationale": "string", "evidence": "array"},
    )
    resp = asyncio.run(adapter.complete(req))
    assert resp.provider == "mock"
    assert resp.structured is not None
    evidence = resp.structured["evidence"]
    assert isinstance(evidence, list)
    names = {e["signal"] for e in evidence}
    assert "shared_device_ring_size" in names
    assert "velocity_1h" in names


def test_mock_adapter_is_deterministic() -> None:
    adapter = MockAdapter()
    req = LLMRequest(system="s", prompt="risk=0.5 fraud=0.1")
    first = asyncio.run(adapter.complete(req))
    second = asyncio.run(adapter.complete(req))
    assert first.structured == second.structured
    assert first.text == second.text


class _FailingProvider:
    """A provider whose completion always raises (models a dead primary / bad ADC)."""

    name = "gemini"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        raise RuntimeError("ADC resolution failed")

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, healthy=False, detail="no creds")


def test_breaker_degrades_to_fallback() -> None:
    primary: LLMProvider = _FailingProvider()
    fallback = MockAdapter()
    breaker = CircuitBreaker(
        primary=primary,
        fallback=fallback,
        config=BreakerConfig(max_retries=0, timeout_s=0.1),
    )
    resp = asyncio.run(breaker.complete(LLMRequest(system="s", prompt="score=0.9")))
    assert resp.provider == "mock"
    assert resp.structured is not None


def test_breaker_opens_after_threshold() -> None:
    primary: LLMProvider = _FailingProvider()
    fallback = MockAdapter()
    breaker = CircuitBreaker(
        primary=primary,
        fallback=fallback,
        config=BreakerConfig(max_retries=0, failure_threshold=2, cooldown_s=60.0),
    )
    req = LLMRequest(system="s", prompt="x=1")
    asyncio.run(breaker.complete(req))
    assert not breaker.is_open
    asyncio.run(breaker.complete(req))
    assert breaker.is_open


class _SlowProvider:
    """A provider that sleeps past the breaker timeout."""

    name = "gemini"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        await asyncio.sleep(1.0)
        return LLMResponse(text="late", structured=None, provider=self.name, model="m")

    async def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, healthy=True)


def test_breaker_times_out_to_fallback() -> None:
    breaker = CircuitBreaker(
        primary=_SlowProvider(),
        fallback=MockAdapter(),
        config=BreakerConfig(max_retries=0, timeout_s=0.05),
    )
    resp = asyncio.run(breaker.complete(LLMRequest(system="s", prompt="y=2")))
    assert resp.provider == "mock"


def test_complete_endpoint_gemini_no_creds_degrades_to_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # LLM_PROVIDER=gemini with no ADC: the breaker must degrade to mock and still 200.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "mock")
    client = TestClient(app)
    resp = client.post(
        "/v1/complete",
        json={
            "system": "You are a fraud explainability assistant.",
            "prompt": "Score 0.87. shared_device_ring_size=4.",
            "response_schema": {"rationale": "string", "evidence": "array"},
            "metadata": {"trace_id": "trace-1", "agent": "fraud"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "mock"
    assert body["structured"] is not None


def test_complete_endpoint_mock_provider() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/complete",
        json={"system": "s", "prompt": "risk=0.2", "metadata": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["provider"] in {"mock", "gemini"}


def test_health_and_ready() -> None:
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
