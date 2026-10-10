"""Train the risk (XGBoost) and fraud (LightGBM) models (docs/05 §4, §5).

Loads the synthetic Parquet from ``generate_dataset.py``, builds the feature matrix
from the shared feature columns, does a validation split, trains both models, reports
AUC + PR-AUC, serializes versioned artifacts under ``ml/models/``, and writes a
``model_card.json`` that carries the synthetic-data honesty caveat (docs/05 §6.1):
reported metrics show the pipeline works end to end, not real-world accuracy.

Usage:
    python training/train.py --data data/transactions.parquet --models-dir models
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import lightgbm as lgb
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

from acip_common.features import FEATURE_COLUMNS

_BASE = Path(__file__).resolve().parent.parent
_DEFAULT_DATA = _BASE / "data" / "transactions.parquet"
_DEFAULT_MODELS_DIR = _BASE / "models"

# docs/05 §6.1 honesty caveat — kept verbatim in spirit in the model card.
_SYNTHETIC_CAVEAT = (
    "Models were trained on fully synthetic, reproducibly generated data. The reported "
    "AUC/PR-AUC demonstrate that the end-to-end training pipeline works; they are NOT "
    "evidence of real-world fraud-detection or credit-risk accuracy. The models learned "
    "only the patterns deliberately planted in the synthetic dataset."
)


def _metrics(y_true: pd.Series, y_prob: Any) -> dict[str, float]:
    """Compute AUC + PR-AUC, guarding single-class validation folds."""
    if y_true.nunique() < 2:
        return {"auc": float("nan"), "pr_auc": float("nan")}
    return {
        "auc": float(roc_auc_score(y_true, y_prob)),
        "pr_auc": float(average_precision_score(y_true, y_prob)),
    }


def _train_risk(
    x_train: pd.DataFrame, y_train: pd.Series, x_val: pd.DataFrame
) -> tuple[xgb.XGBClassifier, Any]:
    """Train the XGBoost risk model; return model + validation probabilities."""
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(x_train, y_train)
    return model, model.predict_proba(x_val)[:, 1]


def _train_fraud(
    x_train: pd.DataFrame, y_train: pd.Series, x_val: pd.DataFrame
) -> tuple[lgb.LGBMClassifier, Any]:
    """Train the LightGBM fraud model; return model + validation probabilities."""
    model = lgb.LGBMClassifier(
        n_estimators=300,
        num_leaves=31,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        verbose=-1,
    )
    model.fit(x_train, y_train)
    return model, model.predict_proba(x_val)[:, 1]


def train(data_path: Path, models_dir: Path) -> dict[str, Any]:
    """Train both models from ``data_path`` and write artifacts to ``models_dir``."""
    df = pd.read_parquet(data_path)
    features = df[list(FEATURE_COLUMNS)]

    today = date.today().strftime("%Y.%m.%d")
    models_dir.mkdir(parents=True, exist_ok=True)

    # --- risk (XGBoost on bad_outcome) --- #
    xr_tr, xr_val, yr_tr, yr_val = train_test_split(
        features, df["bad_outcome"], test_size=0.2, random_state=42, stratify=df["bad_outcome"]
    )
    risk_model, risk_prob = _train_risk(xr_tr, yr_tr, xr_val)
    risk_metrics = _metrics(yr_val, risk_prob)
    risk_version = f"risk-xgb-{today}"
    risk_path = models_dir / f"{risk_version}.json"
    risk_model.save_model(str(risk_path))

    # --- fraud (LightGBM on is_fraud) --- #
    xf_tr, xf_val, yf_tr, yf_val = train_test_split(
        features, df["is_fraud"], test_size=0.2, random_state=42, stratify=df["is_fraud"]
    )
    fraud_model, fraud_prob = _train_fraud(xf_tr, yf_tr, xf_val)
    fraud_metrics = _metrics(yf_val, fraud_prob)
    fraud_version = f"fraud-lgbm-{today}"
    fraud_path = models_dir / f"{fraud_version}.txt"
    fraud_model.booster_.save_model(str(fraud_path))

    model_card = {
        "generated_at": date.today().isoformat(),
        "feature_columns": list(FEATURE_COLUMNS),
        "dataset": str(data_path),
        "synthetic_data_caveat": _SYNTHETIC_CAVEAT,
        "models": {
            "risk": {
                "algo": "xgboost",
                "target": "bad_outcome",
                "version": risk_version,
                "artifact": risk_path.name,
                "metrics": risk_metrics,
            },
            "fraud": {
                "algo": "lightgbm",
                "target": "is_fraud",
                "version": fraud_version,
                "artifact": fraud_path.name,
                "metrics": fraud_metrics,
            },
        },
    }
    card_path = models_dir / "model_card.json"
    card_path.write_text(json.dumps(model_card, indent=2))
    return model_card


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ACIP risk + fraud models")
    parser.add_argument("--data", type=Path, default=_DEFAULT_DATA)
    parser.add_argument("--models-dir", type=Path, default=_DEFAULT_MODELS_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    card = train(args.data, args.models_dir)
    for name, info in card["models"].items():
        metrics = info["metrics"]
        print(
            f"{name:>6} [{info['version']}] "
            f"AUC={metrics['auc']:.4f} PR-AUC={metrics['pr_auc']:.4f} -> {info['artifact']}"
        )
    print(f"wrote model card: {args.models_dir / 'model_card.json'}")


if __name__ == "__main__":
    main()
