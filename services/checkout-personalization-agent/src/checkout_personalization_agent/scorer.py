"""Personalization scoring: rank methods by predicted success (docs/02 §3.2, ADVISORY).

The checkout-personalization agent owns no model. It ranks the customer's payment methods
by their historical success rate — ``successes / (successes + failures)`` from the shared
representation's ``method_history`` — and recommends the highest. A method with no history
is treated with a neutral prior (``_NEUTRAL_PRIOR``) so it is neither strongly preferred
nor avoided.

It is ADVISORY only and NEVER vetoes (docs/02 §3.2): it always emits an APPROVE hint. The
recommended method name is carried in the verdict rationale via
``ScoreResult.rationale_override`` — the decision-engine reads ``personalization.rationale``
as the recommended method (docs/02 §5) — and the full ranking + confidence go into the
evidence (``signal=method``, ``value=success rate``). ``confidence`` is the top method's
success rate. The scorer is pure over the representation, so it is directly unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acip_agent_common import ScoreFn, ScoreResult
from acip_common.config import Settings
from acip_common.schemas import DecisionHint, Evidence, SharedRepresentation

_MODEL_VERSION = "personalization-rules-v1"

# A method with no observed history gets a neutral prior success rate.
_NEUTRAL_PRIOR = 0.5


@dataclass(frozen=True)
class RankedMethod:
    """A payment method ranked by predicted success (docs/02 §3.2)."""

    method: str
    success_rate: float


def rank_methods(representation: SharedRepresentation) -> list[RankedMethod]:
    """Rank the customer's methods by historical success rate, best first (docs/02 §3.2).

    ``success_rate = successes / (successes + failures)``; a method with no observations
    uses ``_NEUTRAL_PRIOR``. Ties keep input order via a stable sort.
    """
    ranked: list[RankedMethod] = []
    for method, hist in representation.method_history.items():
        total = hist.successes + hist.failures
        rate = hist.successes / total if total > 0 else _NEUTRAL_PRIOR
        ranked.append(RankedMethod(method=method, success_rate=rate))
    ranked.sort(key=lambda m: m.success_rate, reverse=True)
    return ranked


def build_score_fn(settings: Settings) -> ScoreFn:
    """Build the injected personalization ``score_fn`` (docs/02 §2.2, §3.2).

    Ranks the methods, recommends the top one via ``rationale_override`` (the method
    name), puts the ranking in evidence, sets ``confidence`` to the top success rate,
    and always returns an APPROVE hint with ``score=0.0`` (advisory, never a veto).
    """

    def _score(representation: SharedRepresentation, signals: dict[str, Any]) -> ScoreResult:
        ranked = rank_methods(representation)
        evidence = [Evidence(signal=m.method, value=m.success_rate, weight=1.0) for m in ranked]
        recommended = ranked[0].method if ranked else ""
        confidence = ranked[0].success_rate if ranked else 0.0
        return ScoreResult(
            score=0.0,
            decision_hint=DecisionHint.APPROVE,
            model_version=_MODEL_VERSION,
            evidence=evidence,
            confidence=confidence,
            rationale_override=recommended,
        )

    return _score


__all__ = ["RankedMethod", "build_score_fn", "rank_methods"]
