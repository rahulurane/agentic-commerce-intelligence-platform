"""LLM provider protocol + request/response dataclasses (docs/04 §2).

Every concrete adapter implements :class:`LLMProvider`; agents never import a vendor
SDK, they call the gateway which normalizes every provider to :class:`LLMResponse`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class LLMRequest:
    """A normalized completion request (docs/04 §2)."""

    system: str
    prompt: str
    temperature: float = 0.2
    max_tokens: int = 512
    response_schema: dict[str, object] | None = None
    metadata: dict[str, object] | None = None


@dataclass
class TokenUsage:
    """Token accounting for cost visibility (docs/04 §2, §7)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Sum of prompt + completion tokens."""
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResponse:
    """A normalized completion response (docs/04 §2)."""

    text: str
    structured: dict[str, object] | None
    provider: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: int = 0


@dataclass
class ProviderHealth:
    """Health snapshot for a provider (docs/04 §2)."""

    provider: str
    healthy: bool
    detail: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    """The adapter interface every provider implements (docs/04 §2)."""

    name: str

    async def complete(self, req: LLMRequest) -> LLMResponse:
        """Produce a completion for ``req``."""
        ...

    async def health(self) -> ProviderHealth:
        """Report provider health."""
        ...


__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "ProviderHealth",
    "TokenUsage",
]
