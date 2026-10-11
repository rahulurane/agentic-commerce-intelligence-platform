"""Deterministic heuristic scorer used when trained artifacts are absent (docs/05 §5).

Until ``make train`` writes artifacts, the service still answers so the demo runs. The
heuristic is a bounded logistic over a small set of hand-weighted feature signals from
``acip_common.features.FEATURE_COLUMNS``. It is fully deterministic, needs no model
files, and reports ``model_version='heuristic-v1'`` plus the top contributing features
so callers (and the LLM rationale) still get an explainable score.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from acip_common.features import FEATURE_COLUMNS

HEURISTIC_VERSION = "heuristic-v1"

# Per-model signal weights (docs/05 §4): risk leans on amount/behavioral signals,
# fraud on graph/velocity signals. Weights are intentionally simple and bounded.
_RISK_WEIGHTS: dict[str, float] = {
    "amount_zscore": 0.6,
    "customer_chargeback_count": 0.9,
    "customer_txn_count_30d": -0.02,
    "method_age_days": -0.01,
}
_FRAUD_WEIGHTS: dict[str, float] = {
    "shared_device_ring_size": 0.7,
    "velocity_1h": 0.15,
    "geo_mismatch": 0.8,
    "amount_zscore": 0.3,
}

_WEIGHTS: dict[str, dict[str, float]] = {"risk": _RISK_WEIGHTS, "fraud": _FRAUD_WEIGHTS}
_BIAS = -1.5


def _sigmoid(x: float) -> float:
    """Numerically stable logistic sigmoid, bounded to (0, 1)."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def score_heuristic(
    model: str, features: Mapping[str, float], top_k: int = 3
) -> tuple[float, list[tuple[str, float]]]:
    """Return a bounded ``(score, top_features)`` for ``model`` using the heuristic.

    ``top_features`` are the ``top_k`` signals ranked by absolute contribution
    (weight * value), so the explainability shape matches the trained path.
    """
    weights = _WEIGHTS.get(model, _FRAUD_WEIGHTS)
    contributions: dict[str, float] = {}
    linear = _BIAS
    for name in FEATURE_COLUMNS:
        weight = weights.get(name, 0.0)
        if weight == 0.0:
            continue
        contribution = weight * float(features.get(name, 0.0))
        contributions[name] = contribution
        linear += contribution

    score = _sigmoid(linear)
    top = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_k]
    return score, top


__all__ = ["HEURISTIC_VERSION", "score_heuristic"]
