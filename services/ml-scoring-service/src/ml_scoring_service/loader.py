"""Model artifact resolution + loading from ``model_card.json`` (docs/05 §4, §7).

The clock in this project is set to 2026, so artifact filenames carry 2026 dates. The
loader therefore NEVER hardcodes a date: it resolves the current artifacts by reading
``<ML_MODELS_DIR>/model_card.json`` (``models.risk.artifact`` /
``models.fraud.artifact``) and loads whatever it names. Risk is an XGBoost ``.json``
loaded via ``Booster.load_model``; fraud is a LightGBM ``.txt`` loaded via
``lightgbm.Booster(model_file=...)``. A warm-up predict runs on boot to avoid
first-request latency (docs/05 §7). When the card or an artifact is missing the loader
reports a degraded state so the service serves the heuristic (docs/05 §5).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from acip_common.features import FEATURE_COLUMNS

_log = logging.getLogger("ml_scoring_service.loader")

_MODEL_CARD = "model_card.json"


def _as_scalar(value: Any) -> float:
    """Coerce a model importance (which may be a scalar or 1-element list) to float."""
    if isinstance(value, list | tuple):
        return float(value[0]) if value else 0.0
    return float(value)


@dataclass
class LoadedModel:
    """A loaded tree model plus its reported version + gain-based importances."""

    name: str
    version: str
    booster: Any
    kind: str  # "xgboost" | "lightgbm"
    importances: dict[str, float]


@dataclass
class ModelRegistry:
    """The set of loaded models. ``degraded`` means the heuristic should serve."""

    models: dict[str, LoadedModel]
    degraded: bool

    def get(self, name: str) -> LoadedModel | None:
        """Return the loaded model for ``name`` if present."""
        return self.models.get(name)


def _warmup_row() -> np.ndarray[Any, Any]:
    """A single all-zero feature row in canonical column order for warm-up."""
    return np.zeros((1, len(FEATURE_COLUMNS)), dtype=np.float64)


def _load_xgboost(path: Path) -> tuple[Any, dict[str, float]]:
    """Load an XGBoost booster from a saved ``.json`` and compute gain importances."""
    import xgboost as xgb

    booster = xgb.Booster()
    booster.load_model(str(path))
    booster.feature_names = list(FEATURE_COLUMNS)
    # Warm-up predict to JIT internal buffers (docs/05 §7).
    booster.predict(xgb.DMatrix(_warmup_row(), feature_names=list(FEATURE_COLUMNS)))
    score_map = booster.get_score(importance_type="gain")
    importances = {col: _as_scalar(score_map.get(col, 0.0)) for col in FEATURE_COLUMNS}
    return booster, importances


def _load_lightgbm(path: Path) -> tuple[Any, dict[str, float]]:
    """Load a LightGBM booster from a saved ``.txt`` and compute gain importances."""
    import lightgbm as lgb

    booster = lgb.Booster(model_file=str(path))
    booster.predict(_warmup_row())  # warm-up (docs/05 §7)
    gains = booster.feature_importance(importance_type="gain")
    names = booster.feature_name()
    importances = {col: 0.0 for col in FEATURE_COLUMNS}
    for name, gain in zip(names, gains, strict=False):
        if name in importances:
            importances[name] = _as_scalar(gain)
    return booster, importances


_LOADERS = {"xgboost": _load_xgboost, "lightgbm": _load_lightgbm}


def load_registry(models_dir: str) -> ModelRegistry:
    """Resolve + load models from ``models_dir/model_card.json`` (docs/05 §4, §7).

    Returns a degraded registry (no models) when the card or any artifact is absent or
    fails to load, so the service transparently serves the heuristic (docs/05 §5).
    """
    base = Path(models_dir)
    card_path = base / _MODEL_CARD
    if not card_path.is_file():
        _log.warning(
            "model_card.json not found; serving heuristic",
            extra={"models_dir": models_dir, "degraded": True},
        )
        return ModelRegistry(models={}, degraded=True)

    try:
        card = json.loads(card_path.read_text())
        entries: dict[str, Any] = card["models"]
    except (ValueError, KeyError, OSError) as exc:
        _log.warning(
            "model_card.json unreadable; serving heuristic",
            extra={"error": str(exc), "degraded": True},
        )
        return ModelRegistry(models={}, degraded=True)

    loaded: dict[str, LoadedModel] = {}
    for name, info in entries.items():
        algo = str(info.get("algo", ""))
        artifact = str(info.get("artifact", ""))
        version = str(info.get("version", name))
        loader = _LOADERS.get(algo)
        artifact_path = base / artifact
        if loader is None or not artifact_path.is_file():
            _log.warning(
                "artifact missing/unsupported; serving heuristic",
                extra={"model": name, "algo": algo, "artifact": artifact, "degraded": True},
            )
            return ModelRegistry(models={}, degraded=True)
        try:
            booster, importances = loader(artifact_path)
        except Exception as exc:  # noqa: BLE001 - any load error -> degrade safely
            _log.warning(
                "artifact load failed; serving heuristic",
                extra={"model": name, "error": str(exc), "degraded": True},
            )
            return ModelRegistry(models={}, degraded=True)
        loaded[name] = LoadedModel(
            name=name, version=version, booster=booster, kind=algo, importances=importances
        )

    _log.info("models loaded", extra={"models": sorted(loaded.keys()), "degraded": False})
    return ModelRegistry(models=loaded, degraded=False)


__all__ = ["LoadedModel", "ModelRegistry", "load_registry"]
