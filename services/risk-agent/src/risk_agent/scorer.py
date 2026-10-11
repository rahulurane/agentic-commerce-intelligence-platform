"""Risk scoring: ml-scoring probability banded into a decision hint (docs/02 §3).

The risk agent owns no model. It POSTs the shared representation's feature row (ordered
by :data:`acip_common.features.FEATURE_COLUMNS`) to ``ml-scoring-service``
``POST /v1/score`` with ``model='risk'``, takes the returned probability as its score,
and bands it via ``Settings.approve_max`` / ``Settings.challenge_max`` into APPROVE /
CHALLENGE / DECLINE (docs/02 §3). The model version and the top features from the score
response flow onto the verdict as its ``model_version`` and explainability evidence.

The HTTP call is isolated behind :class:`MlScoringClient` so the scoring logic injected
into the graph (:func:`build_score_fn`) is a pure, unit-testable mapping once a client
(real or fake) is supplied.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from acip_agent_common import ScoreFn, ScoreResult
from acip_common.config import Settings
from acip_common.features import FEATURE_COLUMNS
from acip_common.schemas import DecisionHint, Evidence, SharedRepresentation

_MODEL = "risk"
_SCORE_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class ScoreResponse:
    """The slice of the ml-scoring ``/v1/score`` response the agent consumes."""

    score: float
    model_version: str
    top_features: list[tuple[str, float]]


class MlScoringClient:
    """Minimal ``ml-scoring-service`` client for the risk/fraud model (docs/05 §2)."""

    def __init__(self, base_url: str, *, timeout: float = _SCORE_TIMEOUT_SECONDS) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/score"
        self._timeout = timeout

    def score(self, model: str, features: Mapping[str, float], trace_id: str) -> ScoreResponse:
        """POST ``features`` for ``model`` and return the parsed score response."""
        body = {
            "model": model,
            "features": dict(features),
            "metadata": {"trace_id": trace_id},
        }
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(self._url, json=body)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        top = [(str(tf["name"]), float(tf["contribution"])) for tf in data.get("top_features", [])]
        return ScoreResponse(
            score=float(data["score"]),
            model_version=str(data["model_version"]),
            top_features=top,
        )


def band(score: float, settings: Settings) -> DecisionHint:
    """Band a risk probability into APPROVE / CHALLENGE / DECLINE (docs/02 §3).

    ``<= approve_max`` APPROVE, ``<= challenge_max`` CHALLENGE, else DECLINE.
    """
    if score <= settings.approve_max:
        return DecisionHint.APPROVE
    if score <= settings.challenge_max:
        return DecisionHint.CHALLENGE
    return DecisionHint.DECLINE


def _ordered_features(representation: SharedRepresentation) -> dict[str, float]:
    """Return the representation feature row in canonical column order (no skew)."""
    return {col: float(representation.features.get(col, 0.0)) for col in FEATURE_COLUMNS}


def build_score_fn(client: MlScoringClient, settings: Settings) -> ScoreFn:
    """Build the injected risk ``score_fn`` bound to an ml-scoring client (docs/02 §2.2).

    The returned function maps a representation slice to a :class:`ScoreResult`: it calls
    ml-scoring for ``model='risk'``, bands the probability, and turns the response's top
    features into evidence. Pure given the injected client, so tests inject a fake.
    """

    def _score(representation: SharedRepresentation, signals: dict[str, Any]) -> ScoreResult:
        trace_id = str(signals.get("trace_id", representation.transaction_id))
        response = client.score(_MODEL, _ordered_features(representation), trace_id)
        evidence = [
            Evidence(signal=name, value=contribution, weight=1.0)
            for name, contribution in response.top_features
        ]
        return ScoreResult(
            score=response.score,
            decision_hint=band(response.score, settings),
            model_version=response.model_version,
            evidence=evidence,
        )

    return _score


__all__ = [
    "MlScoringClient",
    "ScoreResponse",
    "band",
    "build_score_fn",
]
