"""Gemini adapter over the Google GenAI / Vertex SDK via ADC (docs/04 §2, §4).

The SDK is imported lazily inside the adapter so this module (and the whole package)
imports with no SDK installed and no credentials present. Auth relies on the ADC chain
(``GOOGLE_APPLICATION_CREDENTIALS`` or Workload Identity) — keys are never hardcoded.
If the SDK is missing or ADC resolution fails, construction/health raises and the
circuit breaker degrades to the mock provider (docs/04 §4).
"""

from __future__ import annotations

import json
import time
from typing import Any

from llm_gateway.providers.base import (
    LLMRequest,
    LLMResponse,
    ProviderHealth,
    TokenUsage,
)


class GeminiAdapter:
    """A :class:`LLMProvider` backed by the Google GenAI SDK (ADC auth)."""

    name = "gemini"

    def __init__(self, model: str) -> None:
        self.model = model
        self._client: Any = None

    def _ensure_client(self) -> Any:
        """Lazily construct the GenAI client; raise if SDK/creds are unavailable.

        The import and client construction are deferred to call time so importing this
        module never requires the SDK or ADC credentials (docs/04 §4).
        """
        if self._client is None:
            from google import genai  # lazy import (docs/04 §4)

            # Vertex AI path uses ADC — no API key in code. Raises if ADC cannot be
            # resolved, which the breaker treats as a provider failure.
            self._client = genai.Client(vertexai=True)
        return self._client

    async def complete(self, req: LLMRequest) -> LLMResponse:
        """Call Gemini and normalize to :class:`LLMResponse`."""
        from google.genai import types  # lazy import (docs/04 §4)

        client = self._ensure_client()
        started = time.perf_counter()
        config = types.GenerateContentConfig(
            system_instruction=req.system,
            temperature=req.temperature,
            max_output_tokens=req.max_tokens,
            response_mime_type="application/json" if req.response_schema else None,
            response_schema=req.response_schema,
        )
        result = await client.aio.models.generate_content(
            model=self.model, contents=req.prompt, config=config
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = result.text or ""
        structured: dict[str, object] | None = None
        if req.response_schema is not None:
            try:
                structured = json.loads(text)
            except (ValueError, TypeError):
                structured = None

        usage = _usage_from(result)
        return LLMResponse(
            text=text,
            structured=structured,
            provider=self.name,
            model=self.model,
            usage=usage,
            latency_ms=latency_ms,
        )

    async def health(self) -> ProviderHealth:
        """Probe that the client can be constructed (ADC resolves)."""
        try:
            self._ensure_client()
        except Exception as exc:  # noqa: BLE001 - any SDK/ADC error means unhealthy
            return ProviderHealth(provider=self.name, healthy=False, detail=str(exc))
        return ProviderHealth(provider=self.name, healthy=True)


def _usage_from(result: Any) -> TokenUsage:
    """Extract token usage from a GenAI result, tolerating missing metadata."""
    meta = getattr(result, "usage_metadata", None)
    if meta is None:
        return TokenUsage()
    return TokenUsage(
        prompt_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
        completion_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
    )


__all__ = ["GeminiAdapter"]
