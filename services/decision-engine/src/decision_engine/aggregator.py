"""Pure verdict-aggregation strategy (docs/02 §5).

``aggregate`` turns the set of agent :class:`~acip_common.schemas.Verdict` values into
one :class:`~acip_common.schemas.DecisionRenderedPayload`, implementing the default
"weighted veto" strategy from docs/02 §5 in order:

1. **Hard veto** — a ``policy`` DECLINE, or ``fraud`` score ``>= fraud_block_threshold``
   forces DECLINE regardless of everything else (safety first).
2. **Weighted composite** — ``w_risk * risk + w_fraud * fraud``, banded by
   ``approve_max`` / ``challenge_max`` into APPROVE / CHALLENGE / DECLINE.
3. **Routing overlay** — on a non-DECLINE, attach the top-ranked route + alternatives.
4. **Merchant soft constraints** — may upgrade APPROVE to CHALLENGE (e.g. high value),
   never relaxes a DECLINE.
5. **Checkout-personalization** — advisory ``recommended_method`` only; never changes
   the decision.

Every threshold and weight is read from :class:`acip_common.config.Settings`; nothing
is hardcoded. Missing ``risk``/``fraud`` verdicts fall back to
``Settings.missing_risk_fraud_policy`` (default CHALLENGE); missing advisory agents use
defaults so the transaction still progresses (docs/02 §5 missing-verdict policy).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from acip_common.config import Settings
from acip_common.schemas import (
    AgentName,
    CandidateRoute,
    DecisionHint,
    DecisionRenderedPayload,
    Verdict,
)

_STRATEGY = "weighted_veto"

# Merchant soft-constraint signal names (docs/02 §5 step 4). The merchant agent
# surfaces these as evidence signals on its verdict; the engine reads them without
# hardcoding any merchant-specific thresholds.
_FORCE_CHALLENGE_SIGNAL = "force_challenge"


def _ordered_routes(routes: Sequence[CandidateRoute]) -> list[str]:
    """Return processors ranked by success rate (healthiest first)."""
    return [r.processor for r in sorted(routes, key=lambda r: r.success_rate, reverse=True)]


def _merchant_forces_challenge(verdict: Verdict | None) -> bool:
    """Whether the merchant verdict carries a force-CHALLENGE soft constraint."""
    if verdict is None:
        return False
    if verdict.decision_hint is DecisionHint.CHALLENGE:
        return True
    return any(ev.signal == _FORCE_CHALLENGE_SIGNAL and ev.value >= 1.0 for ev in verdict.evidence)


def _band(composite: float, settings: Settings) -> DecisionHint:
    """Band a composite score into APPROVE / CHALLENGE / DECLINE (docs/02 §5)."""
    if composite <= settings.approve_max:
        return DecisionHint.APPROVE
    if composite <= settings.challenge_max:
        return DecisionHint.CHALLENGE
    return DecisionHint.DECLINE


def aggregate(
    verdicts: Mapping[AgentName, Verdict],
    candidate_routes: Sequence[CandidateRoute],
    settings: Settings,
) -> DecisionRenderedPayload:
    """Aggregate ``verdicts`` into a final decision (docs/02 §5)."""
    risk = verdicts.get(AgentName.RISK)
    fraud = verdicts.get(AgentName.FRAUD)
    policy = verdicts.get(AgentName.POLICY)
    merchant = verdicts.get(AgentName.MERCHANT)
    personalization = verdicts.get(AgentName.CHECKOUT_PERSONALIZATION)

    contributing = sorted(verdicts.keys(), key=lambda a: a.value)
    degraded = sorted((a for a, v in verdicts.items() if v.degraded), key=lambda a: a.value)

    # Routing overlay inputs (used by every non-DECLINE branch below). The routing
    # agent scores every candidate route; absent an explicit ranking the engine ranks
    # by success rate (healthiest first) so a top route + failover alternatives exist.
    ranked = _ordered_routes(candidate_routes)
    top_route = ranked[0] if ranked else None
    alternatives = ranked[1:] if len(ranked) > 1 else []

    recommended_method = _recommended_method(personalization)

    # --- (1) Hard veto -------------------------------------------------------
    policy_denies = policy is not None and policy.decision_hint is DecisionHint.DECLINE
    fraud_blocks = fraud is not None and fraud.score >= settings.fraud_block_threshold
    if policy_denies or fraud_blocks:
        if policy_denies:
            reason = "policy denial"
        else:
            fraud_score = fraud.score if fraud is not None else 0.0
            reason = (
                f"fraud score {fraud_score:.2f} >= block threshold "
                f"{settings.fraud_block_threshold:.2f}"
            )
        return DecisionRenderedPayload(
            decision=DecisionHint.DECLINE,
            composite_score=1.0 if fraud_blocks else 0.0,
            strategy=_STRATEGY,
            route=None,
            route_alternatives=[],
            recommended_method=recommended_method,
            contributing_verdicts=contributing,
            explanation=f"Hard veto: {reason}.",
            degraded_agents=degraded,
        )

    # --- missing risk/fraud policy ------------------------------------------
    if risk is None or fraud is None:
        fallback = _missing_policy_decision(settings)
        return DecisionRenderedPayload(
            decision=fallback,
            composite_score=0.0,
            strategy=_STRATEGY,
            route=top_route if fallback is not DecisionHint.DECLINE else None,
            route_alternatives=alternatives if fallback is not DecisionHint.DECLINE else [],
            recommended_method=recommended_method,
            contributing_verdicts=contributing,
            explanation=(
                "Missing risk/fraud verdict; applied configured missing-verdict "
                f"policy -> {fallback.value}."
            ),
            degraded_agents=degraded,
        )

    # --- (2) Weighted composite + band --------------------------------------
    composite = settings.w_risk * risk.score + settings.w_fraud * fraud.score
    decision = _band(composite, settings)

    # --- (4) Merchant soft constraints --------------------------------------
    if decision is DecisionHint.APPROVE and _merchant_forces_challenge(merchant):
        decision = DecisionHint.CHALLENGE
        constraint_note = " Merchant constraint forced step-up."
    else:
        constraint_note = ""

    # --- (3) Routing overlay (non-DECLINE only) -----------------------------
    if decision is DecisionHint.DECLINE:
        route, route_alternatives = None, []
    else:
        route, route_alternatives = top_route, alternatives

    explanation = (
        f"composite {composite:.2f} = {settings.w_risk:.2f}*risk {risk.score:.2f} + "
        f"{settings.w_fraud:.2f}*fraud {fraud.score:.2f}; "
        f"banded to {decision.value}.{constraint_note}"
    )

    return DecisionRenderedPayload(
        decision=decision,
        composite_score=composite,
        strategy=_STRATEGY,
        route=route,
        route_alternatives=route_alternatives,
        recommended_method=recommended_method,
        contributing_verdicts=contributing,
        explanation=explanation,
        degraded_agents=degraded,
    )


def _missing_policy_decision(settings: Settings) -> DecisionHint:
    """Resolve the configured missing-risk/fraud fallback decision."""
    try:
        return DecisionHint(settings.missing_risk_fraud_policy)
    except ValueError:
        # Defensive: an unparseable config value fails safe to CHALLENGE (docs/02 §5).
        return DecisionHint.CHALLENGE


def _recommended_method(personalization: Verdict | None) -> str | None:
    """Pull the advisory recommended method from the personalization verdict.

    The checkout-personalization agent carries its top recommendation in the verdict
    rationale/evidence; its ``rationale`` holds the method name. Advisory only — this
    never changes the decision (docs/02 §3.2, §5).
    """
    if personalization is None:
        return None
    return personalization.rationale or None


__all__ = ["aggregate"]
