"""Per-provider circuit breaker with timeout + retry, degrading to a fallback (docs/04 §5).

The gateway wraps the primary provider in a :class:`CircuitBreaker`. On a timeout or
error the call is retried with exponential backoff; after ``failure_threshold``
consecutive failures the circuit opens and requests short-circuit to the fallback
(mock) until a cooldown elapses. This is what lets the stack run with no cloud
credentials: a Gemini primary whose ADC resolution raises simply trips the breaker and
the mock answers (docs/04 §4).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from llm_gateway.providers.base import LLMProvider, LLMRequest, LLMResponse

_log = logging.getLogger("llm_gateway.breaker")


@dataclass
class BreakerConfig:
    """Tunables for the breaker (docs/04 §5)."""

    timeout_s: float = 1.5
    max_retries: int = 2
    backoff_base_s: float = 0.05
    failure_threshold: int = 3
    cooldown_s: float = 30.0


class CircuitBreaker:
    """Guards a ``primary`` provider and falls back to ``fallback`` when open."""

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        config: BreakerConfig | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._config = config or BreakerConfig()
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        """Whether the circuit is currently open (short-circuiting to fallback)."""
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self._config.cooldown_s:
            # Cooldown elapsed: half-open — allow the next call to probe the primary.
            self._opened_at = None
            self._consecutive_failures = 0
            return False
        return True

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._config.failure_threshold:
            self._opened_at = time.monotonic()

    async def _call_primary(self, req: LLMRequest) -> LLMResponse:
        """Call the primary with timeout + bounded retry/backoff."""
        last_exc: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._primary.complete(req), timeout=self._config.timeout_s
                )
            except Exception as exc:  # noqa: BLE001 - timeout/transport errors retried
                last_exc = exc
                if attempt < self._config.max_retries:
                    await asyncio.sleep(self._config.backoff_base_s * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def complete(self, req: LLMRequest) -> LLMResponse:
        """Return a completion, degrading to the fallback on open/failed primary."""
        if self.is_open:
            _log.warning(
                "circuit open; serving fallback",
                extra={"provider": self._primary.name, "fallback": self._fallback.name},
            )
            return await self._fallback.complete(req)

        try:
            response = await self._call_primary(req)
        except Exception as exc:  # noqa: BLE001 - any failure degrades to fallback
            self._record_failure()
            _log.warning(
                "primary provider failed; serving fallback",
                extra={
                    "provider": self._primary.name,
                    "fallback": self._fallback.name,
                    "error": str(exc),
                },
            )
            return await self._fallback.complete(req)

        self._record_success()
        return response


__all__ = ["BreakerConfig", "CircuitBreaker"]
