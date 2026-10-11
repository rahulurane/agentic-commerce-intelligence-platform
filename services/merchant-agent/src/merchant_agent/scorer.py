"""Merchant scoring: advisory soft-constraints, never a hard veto (docs/02 §3, §5).

The merchant agent owns no model. It emits merchant preference adjustments and soft
constraints over the shared representation. Its one demo-relevant constraint is a
high-value step-up: when ``amount >= Settings.merchant_high_value_challenge`` (default
4000.0) it emits a ``force_challenge`` evidence row (``value=1.0``) AND a CHALLENGE hint,
so the decision-engine upgrades an APPROVE to CHALLENGE (it reads a ``force_challenge``
evidence signal or a CHALLENGE merchant hint — docs/02 §5 step 4). Otherwise it emits an
APPROVE hint with no constraint.

The merchant agent is ADVISORY — it NEVER vetoes. A policy DECLINE or a fraud block is a
hard veto handled by the policy/fraud agents; the merchant step-up only ever tightens an
APPROVE into a CHALLENGE, never a DECLINE (that threshold separation is enforced by the
policy agent owning the hard-veto amount cap). The scorer is pure over the
representation + settings, so it is directly unit-testable.
"""

from __future__ import annotations

from typing import Any

from acip_agent_common import ScoreFn, ScoreResult
from acip_common.config import Settings
from acip_common.schemas import DecisionHint, Evidence, SharedRepresentation

_MODEL_VERSION = "merchant-rules-v1"

# The soft-constraint signal the decision-engine reads to upgrade APPROVE -> CHALLENGE
# (docs/02 §5 step 4). Must match decision_engine.aggregator._FORCE_CHALLENGE_SIGNAL.
_FORCE_CHALLENGE_SIGNAL = "force_challenge"


def build_score_fn(settings: Settings) -> ScoreFn:
    """Build the injected merchant ``score_fn`` (docs/02 §2.2, §3).

    High value (``amount >= merchant_high_value_challenge``) -> CHALLENGE hint + a
    ``force_challenge`` evidence row (``value=1.0``), ``score=0.0`` (advisory, not a
    risk score). Otherwise -> APPROVE, no constraint. Never DECLINE.
    """

    def _score(representation: SharedRepresentation, signals: dict[str, Any]) -> ScoreResult:
        amount = representation.transaction.amount
        if amount >= settings.merchant_high_value_challenge:
            return ScoreResult(
                score=0.0,
                decision_hint=DecisionHint.CHALLENGE,
                model_version=_MODEL_VERSION,
                evidence=[Evidence(signal=_FORCE_CHALLENGE_SIGNAL, value=1.0, weight=1.0)],
            )
        return ScoreResult(
            score=0.0,
            decision_hint=DecisionHint.APPROVE,
            model_version=_MODEL_VERSION,
            evidence=[],
        )

    return _score


__all__ = ["build_score_fn"]
