"""Deterministic mock provider — no network, no creds (docs/04 §2, §4).

Used when no cloud credentials are present so the full demo runs offline. Produces a
structured ``{rationale, evidence}`` payload derived deterministically from the request
so the output is stable and testable.
"""

from __future__ import annotations

import re

from llm_gateway.providers.base import (
    LLMRequest,
    LLMResponse,
    ProviderHealth,
    TokenUsage,
)

_SIGNAL_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?\d+(?:\.\d+)?)")


class MockAdapter:
    """A deterministic, offline :class:`LLMProvider` implementation."""

    name = "mock"

    def __init__(self, model: str = "mock-1") -> None:
        self.model = model

    def _structured(self, req: LLMRequest) -> dict[str, object]:
        """Build a deterministic ``{rationale, evidence}`` object from the prompt.

        Signals of the form ``name=value`` in the prompt become evidence entries, so
        the mock mirrors the structured rationale a real provider would return
        (docs/04 §5 structured output).
        """
        evidence: list[dict[str, object]] = [
            {"signal": name, "value": float(value)}
            for name, value in _SIGNAL_RE.findall(req.prompt)
        ]
        rationale = (
            "Deterministic mock rationale: decision explained from "
            f"{len(evidence)} extracted signal(s)."
        )
        return {"rationale": rationale, "evidence": evidence}

    async def complete(self, req: LLMRequest) -> LLMResponse:
        """Return a deterministic structured completion (no network)."""
        structured = self._structured(req)
        text = str(structured["rationale"])
        usage = TokenUsage(
            prompt_tokens=len(req.prompt.split()),
            completion_tokens=len(text.split()),
        )
        return LLMResponse(
            text=text,
            structured=structured,
            provider=self.name,
            model=self.model,
            usage=usage,
            latency_ms=0,
        )

    async def health(self) -> ProviderHealth:
        """The mock is always healthy."""
        return ProviderHealth(provider=self.name, healthy=True, detail="mock always available")


__all__ = ["MockAdapter"]
