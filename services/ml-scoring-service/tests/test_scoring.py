"""Tests for ml-scoring-service: heuristic fallback + artifact loading (docs/05)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ml_scoring_service.heuristic import HEURISTIC_VERSION, score_heuristic
from ml_scoring_service.loader import load_registry
from ml_scoring_service.scorer import score as score_features

from acip_common.features import FEATURE_COLUMNS

# The real trained artifacts live under ml/models (gitignored, written by `make train`).
_ML_MODELS = Path(__file__).resolve().parents[3] / "ml" / "models"
_HAS_ARTIFACTS = (_ML_MODELS / "model_card.json").is_file()

_FEATURES = {
    "amount_zscore": 2.1,
    "velocity_1h": 11.0,
    "method_age_days": 3.0,
    "geo_mismatch": 1.0,
    "shared_device_ring_size": 4.0,
    "customer_txn_count_30d": 12.0,
    "customer_chargeback_count": 1.0,
}


def test_heuristic_score_is_bounded_and_deterministic() -> None:
    score_a, top_a = score_heuristic("fraud", _FEATURES)
    score_b, top_b = score_heuristic("fraud", _FEATURES)
    assert 0.0 <= score_a <= 1.0
    assert score_a == score_b
    assert top_a == top_b
    assert len(top_a) <= 3
    assert all(name in FEATURE_COLUMNS for name, _ in top_a)


def test_degraded_registry_serves_heuristic(tmp_path: Path) -> None:
    # Empty dir -> no model_card.json -> degraded registry.
    registry = load_registry(str(tmp_path))
    assert registry.degraded is True
    result = score_features(registry, "fraud", _FEATURES)
    assert result.model_version == HEURISTIC_VERSION
    assert 0.0 <= result.score <= 1.0
    assert len(result.top_features) <= 3


def test_score_endpoint_heuristic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ML_MODELS_DIR", str(tmp_path))
    from ml_scoring_service.main import app

    with TestClient(app) as client:
        assert client.get("/readyz").json()["status"] == "ready-degraded"
        resp = client.post(
            "/v1/score",
            json={"model": "fraud", "model_version": "latest", "features": _FEATURES},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["model"] == "fraud"
        assert body["model_version"] == HEURISTIC_VERSION
        assert 0.0 <= body["score"] <= 1.0
        assert "latency_ms" in body


@pytest.mark.skipif(not _HAS_ARTIFACTS, reason="trained artifacts absent (run `make train`)")
def test_loads_real_artifacts_via_model_card() -> None:
    registry = load_registry(str(_ML_MODELS))
    assert registry.degraded is False
    for name in ("risk", "fraud"):
        loaded = registry.get(name)
        assert loaded is not None
        # Version resolved from the card, never hardcoded (artifact carries a 2026 date).
        assert "2026" in loaded.version or loaded.version != HEURISTIC_VERSION
        result = score_features(registry, name, _FEATURES)
        assert 0.0 <= result.score <= 1.0
        assert result.model_version == loaded.version
        assert len(result.top_features) <= 3


def test_health() -> None:
    from ml_scoring_service.main import app

    with TestClient(app):
        client = TestClient(app)
        assert client.get("/healthz").json() == {"status": "ok"}
