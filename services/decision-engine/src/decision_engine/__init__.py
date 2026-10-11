"""ACIP decision-engine: aggregates agent verdicts into one decision (docs/02 §5).

Exposes ``POST /v1/decide`` wrapping a pure aggregation function that implements the
default weighted-veto strategy from docs/02 §5 with every threshold/weight read from
``acip_common.config.Settings`` (never hardcoded).
"""

from __future__ import annotations

__all__: list[str] = []
