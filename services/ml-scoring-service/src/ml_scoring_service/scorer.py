"""Scoring over a loaded model or the heuristic fallback (docs/05 §2, §5).

Builds the feature vector in the canonical ``acip_common.features.FEATURE_COLUMNS``
order (no train/serve skew), predicts the probability, and derives ``top_features``
from per-prediction contributions (SHAP-style ``pred_contribs`` where available,
falling back to gain-based importance * feature value). When the registry is degraded
the heuristic produces both the score and the top features (docs/05 §5).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from acip_common.features import FEATURE_COLUMNS
from ml_scoring_service.heuristic import HEURISTIC_VERSION, score_heuristic
from ml_scoring_service.loader import LoadedModel, ModelRegistry


@dataclass
class ScoreResult:
    """A scoring result for one request (docs/05 §2)."""

    score: float
    model_version: str
    top_features: list[tuple[str, float]]


def _vectorize(features: Mapping[str, float]) -> np.ndarray[Any, Any]:
    """Build the 1-row feature matrix in canonical column order."""
    row = [float(features.get(col, 0.0)) for col in FEATURE_COLUMNS]
    return np.asarray([row], dtype=np.float64)


def _top_from_contribs(contribs: np.ndarray[Any, Any], top_k: int) -> list[tuple[str, float]]:
    """Rank feature columns by |contribution| from a per-prediction contribution row."""
    # The contribution row has one entry per feature plus a trailing bias term.
    values = contribs[: len(FEATURE_COLUMNS)]
    pairs = [(FEATURE_COLUMNS[i], float(values[i])) for i in range(len(FEATURE_COLUMNS))]
    pairs.sort(key=lambda kv: abs(kv[1]), reverse=True)
    return pairs[:top_k]


def _score_xgboost(
    model: LoadedModel, matrix: np.ndarray[Any, Any], top_k: int
) -> tuple[float, list[tuple[str, float]]]:
    import xgboost as xgb

    dmatrix = xgb.DMatrix(matrix, feature_names=list(FEATURE_COLUMNS))
    score = float(model.booster.predict(dmatrix)[0])
    contribs = model.booster.predict(dmatrix, pred_contribs=True)[0]
    return score, _top_from_contribs(np.asarray(contribs), top_k)


def _score_lightgbm(
    model: LoadedModel, matrix: np.ndarray[Any, Any], top_k: int
) -> tuple[float, list[tuple[str, float]]]:
    score = float(model.booster.predict(matrix)[0])
    contribs = model.booster.predict(matrix, pred_contrib=True)[0]
    return score, _top_from_contribs(np.asarray(contribs), top_k)


def score(
    registry: ModelRegistry,
    model_name: str,
    features: Mapping[str, float],
    top_k: int = 3,
) -> ScoreResult:
    """Score ``features`` with the named model, or the heuristic when degraded."""
    loaded = registry.get(model_name)
    if registry.degraded or loaded is None:
        heur_score, top = score_heuristic(model_name, features, top_k=top_k)
        return ScoreResult(score=heur_score, model_version=HEURISTIC_VERSION, top_features=top)

    matrix = _vectorize(features)
    if loaded.kind == "xgboost":
        raw_score, top = _score_xgboost(loaded, matrix, top_k)
    else:
        raw_score, top = _score_lightgbm(loaded, matrix, top_k)
    return ScoreResult(score=raw_score, model_version=loaded.version, top_features=top)


__all__ = ["ScoreResult", "score"]
