"""Policy scoring: deterministic compliance rules, hard-veto on violation (docs/02 §3).

The policy agent owns no model. It applies configured rules to the shared representation
and, on any violation, emits a DECLINE hint with ``score=1.0`` — the decision-engine
already treats a policy DECLINE as a HARD VETO (docs/02 §5), so a violation declines the
transaction regardless of the other agents. With no violation it allows: APPROVE,
``score=0.0``.

THRESHOLD SEPARATION (design, not a demo workaround). A policy DECLINE is a HARD VETO,
while the merchant agent's high-value rule is only a SOFT CHALLENGE upgrade. Those are
two different controls, so they must never fire on the same signal at the same threshold
— the decision-engine checks the policy veto BEFORE the merchant upgrade, so sharing a
threshold would turn every high-value step-up into a decline. The policy amount rule
therefore uses its own absolute ceiling ``Settings.policy_amount_hard_cap`` (default
10000.0), kept well above ``Settings.merchant_high_value_challenge`` (4000.0). A 4800
transaction is thus a merchant CHALLENGE, not a policy DECLINE; only an amount above the
hard cap is a policy veto.

Rules (each a named ``violated_rules`` entry surfaced as evidence, ``signal=rule name``):

* ``sanctioned_geo`` — the customer home geo OR the transaction geo is in
  ``Settings.policy_sanctioned_geos`` (default ``['XX']``).
* ``amount_over_hard_cap`` — ``amount > Settings.policy_amount_hard_cap``.

The scorer is pure over the representation + settings, so it is directly unit-testable.
"""

from __future__ import annotations

from typing import Any

from acip_agent_common import ScoreFn, ScoreResult
from acip_common.config import Settings
from acip_common.schemas import DecisionHint, Evidence, SharedRepresentation

_MODEL_VERSION = "policy-rules-v1"

_RULE_SANCTIONED_GEO = "sanctioned_geo"
_RULE_AMOUNT_OVER_CAP = "amount_over_hard_cap"


def evaluate_rules(representation: SharedRepresentation, settings: Settings) -> list[str]:
    """Return the names of the policy rules this transaction violates (docs/02 §3)."""
    violated: list[str] = []

    sanctioned = {geo.upper() for geo in settings.policy_sanctioned_geos}
    geos = {
        geo.upper() for geo in (representation.home_geo, representation.txn_geo) if geo is not None
    }
    if geos & sanctioned:
        violated.append(_RULE_SANCTIONED_GEO)

    if representation.transaction.amount > settings.policy_amount_hard_cap:
        violated.append(_RULE_AMOUNT_OVER_CAP)

    return violated


def build_score_fn(settings: Settings) -> ScoreFn:
    """Build the injected policy ``score_fn`` (docs/02 §2.2, §3).

    On any violated rule: DECLINE, ``score=1.0``, one evidence row per violated rule
    (``signal=rule name``, ``value=1.0``) — a hard veto. Otherwise: APPROVE, ``score=0.0``.
    """

    def _score(representation: SharedRepresentation, signals: dict[str, Any]) -> ScoreResult:
        violated = evaluate_rules(representation, settings)
        if violated:
            evidence = [Evidence(signal=rule, value=1.0, weight=1.0) for rule in violated]
            return ScoreResult(
                score=1.0,
                decision_hint=DecisionHint.DECLINE,
                model_version=_MODEL_VERSION,
                evidence=evidence,
            )
        return ScoreResult(
            score=0.0,
            decision_hint=DecisionHint.APPROVE,
            model_version=_MODEL_VERSION,
            evidence=[],
        )

    return _score


__all__ = ["build_score_fn", "evaluate_rules"]
