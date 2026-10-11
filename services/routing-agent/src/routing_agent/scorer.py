"""Route scoring: rank candidate routes by success x cost x latency (docs/02 §3.1).

The routing agent enumerates ``representation.candidate_routes`` and scores EACH route on
a weighted blend of three normalized factors (docs/02 §3.1 ROUTE-SCORING):

* **success** — the route's ``success_rate`` (already in ``[0, 1]``), weight
  ``_W_SUCCESS``;
* **cost** — ``cost_bps`` normalized across the candidate set to ``[0, 1]`` then inverted
  (cheaper is better), weight ``_W_COST``;
* **latency** — ``p50_latency_ms`` normalized across the candidate set then inverted
  (faster is better), weight ``_W_LATENCY``.

The weights default to the constants below (documented here because there is no trained
route model and ``Settings`` carries no routing weights); success dominates so a degraded
preferred route loses to a healthy alternate. ``None`` cost/latency is treated as neutral
(0.5 after normalization) so a route missing a dimension is neither rewarded nor punished.

The agent emits one :class:`~acip_common.schemas.Evidence` per route
(``signal=processor``, ``value=route score``), its ``score`` is the chosen (top) route's
score, and the hint is always ``ROUTE`` — routing never vetoes (docs/02 §3.1). The ranked
list lets the decision-engine routing overlay pick the chosen route + failover
alternatives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acip_agent_common import ScoreFn, ScoreResult
from acip_common.config import Settings
from acip_common.schemas import CandidateRoute, DecisionHint, Evidence, SharedRepresentation

# Blend weights (sum to 1.0). Success dominates so route health drives the ranking and a
# degraded preferred route is beaten by a healthy alternate (docs/02 §3.1).
_W_SUCCESS = 0.7
_W_COST = 0.15
_W_LATENCY = 0.15

# A route missing cost/latency is treated as neutral after normalization.
_NEUTRAL = 0.5

_MODEL_VERSION = "routing-rules-v1"


@dataclass(frozen=True)
class RankedRoute:
    """A scored candidate route (docs/02 §3.1)."""

    processor: str
    score: float


def _normalize(value: float | None, lo: float, hi: float) -> float:
    """Normalize ``value`` into ``[0, 1]`` across ``[lo, hi]``; neutral when unknown."""
    if value is None:
        return _NEUTRAL
    if hi <= lo:
        return _NEUTRAL
    return (float(value) - lo) / (hi - lo)


def _bounds(values: list[float | None]) -> tuple[float, float]:
    """Return (min, max) over the present values; (0, 0) when none are present."""
    present = [float(v) for v in values if v is not None]
    if not present:
        return 0.0, 0.0
    return min(present), max(present)


def score_routes(routes: list[CandidateRoute]) -> list[RankedRoute]:
    """Score + rank every candidate route (healthiest first) (docs/02 §3.1).

    Cost and latency are normalized across the candidate set then inverted (cheaper /
    faster is better). Ties keep input order via a stable sort.
    """
    if not routes:
        return []

    cost_lo, cost_hi = _bounds([r.cost_bps for r in routes])
    lat_lo, lat_hi = _bounds([r.p50_latency_ms for r in routes])

    ranked: list[RankedRoute] = []
    for route in routes:
        cost_norm = _normalize(route.cost_bps, cost_lo, cost_hi)
        lat_norm = _normalize(route.p50_latency_ms, lat_lo, lat_hi)
        score = (
            _W_SUCCESS * route.success_rate
            + _W_COST * (1.0 - cost_norm)
            + _W_LATENCY * (1.0 - lat_norm)
        )
        ranked.append(RankedRoute(processor=route.processor, score=score))

    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


def build_score_fn(settings: Settings) -> ScoreFn:
    """Build the injected routing ``score_fn`` (docs/02 §2.2, §3.1).

    Ranks the candidate routes, emits one evidence row per route (``signal=processor``,
    ``value=score``) in ranked order, sets ``score`` to the chosen route's score, and
    always returns a ``ROUTE`` hint (never a veto). Pure over the representation.
    """

    def _score(representation: SharedRepresentation, signals: dict[str, Any]) -> ScoreResult:
        ranked = score_routes(representation.candidate_routes)
        evidence = [
            Evidence(signal=route.processor, value=route.score, weight=1.0) for route in ranked
        ]
        chosen_score = ranked[0].score if ranked else 0.0
        return ScoreResult(
            score=chosen_score,
            decision_hint=DecisionHint.ROUTE,
            model_version=_MODEL_VERSION,
            evidence=evidence,
        )

    return _score


__all__ = ["RankedRoute", "build_score_fn", "score_routes"]
