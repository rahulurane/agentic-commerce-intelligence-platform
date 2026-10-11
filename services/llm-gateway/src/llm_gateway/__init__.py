"""ACIP llm-gateway: one provider-agnostic completion contract (docs/04).

Providers sit behind an adapter interface and are selected by config. A per-provider
circuit breaker degrades to the mock provider when the primary fails or ADC resolution
raises, so the full stack runs with no cloud credentials (docs/04 §4, §5).
"""

from __future__ import annotations

__all__: list[str] = []
