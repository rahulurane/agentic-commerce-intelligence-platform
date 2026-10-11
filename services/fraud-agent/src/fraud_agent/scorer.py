"""Fraud scoring: ml probability combined with graph ring/velocity signals (docs/02 §3, §4).

The fraud agent POSTs the representation feature row to ``ml-scoring-service``
``POST /v1/score`` with ``model='fraud'`` for a base probability, then WEIGHTS graph
signals from the representation — the shared-device ring size and the 1h velocity — so a
device-sharing ring (``shared_device_ring_size`` large) drives the fraud score up even
when the base model is uncertain (docs/02 §3). The final score is the greater of the ml
probability and a graph-derived component, clamped to ``[0, 1]``, so neither signal can
hide a strong fraud indicator from the other.

When the score reaches ``Settings.fraud_block_threshold`` the agent emits a DECLINE hint;
the decision-engine's hard veto (``fraud.score >= fraud_block_threshold``) then declines
the transaction (docs/02 §5). Evidence surfaces ``shared_device_ring_size`` and
``velocity_1h`` (docs/02 §4 example). Below the block threshold the score is banded by
``approve_max`` / ``challenge_max`` like risk.

The graph-signal gathering is a pure ``gather_fn`` and the ml call sits behind
:class:`MlScoringClient`, so the injected ``score_fn`` is unit-testable with a fake.
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

_MODEL = "fraud"
_SCORE_TIMEOUT_SECONDS = 3.0

# Graph-signal weighting (docs/02 §3). A shared-device ring saturates the fraud score
# fast: at ``_RING_SATURATION`` distinct customers on one device the graph component is
# 1.0. Velocity contributes a smaller, bounded bump. These are deterministic defaults
# documented here (no trained model for the graph overlay); the ml probability still
# feeds in and the final score is the max of the two components.
_RING_SATURATION = 5.0
_VELOCITY_SATURATION = 20.0
_VELOCITY_WEIGHT = 0.3


@dataclass(frozen=True)
class ScoreResponse:
    """The slice of the ml-scoring ``/v1/score`` response the agent consumes."""

    score: float
    model_version: str
    top_features: list[tuple[str, float]]


class MlScoringClient:
    """Minimal ``ml-scoring-service`` client for the fraud model (docs/05 §2)."""

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


def _ring_size(representation: SharedRepresentation) -> float:
    """Shared-device ring size from graph signals (handles both key spellings)."""
    signals = representation.graph_signals
    for key in ("shared_device_ring_size", "ring_size"):
        if key in signals:
            return float(signals[key])
    return float(representation.features.get("shared_device_ring_size", 0.0))


def _velocity_1h(representation: SharedRepresentation) -> float:
    """1h transaction velocity from graph signals / features."""
    if "velocity_1h" in representation.graph_signals:
        return float(representation.graph_signals["velocity_1h"])
    return float(representation.features.get("velocity_1h", 0.0))


def gather_graph_signals(representation: SharedRepresentation) -> dict[str, Any]:
    """Derive the fraud agent's graph-signal slice (docs/02 §3). Injected ``gather_fn``."""
    return {
        "shared_device_ring_size": _ring_size(representation),
        "velocity_1h": _velocity_1h(representation),
    }


def graph_component(ring_size: float, velocity_1h: float) -> float:
    """Graph-derived fraud component in ``[0, 1]`` (docs/02 §3).

    A ring at/above ``_RING_SATURATION`` members contributes 1.0; velocity adds a
    bounded bump weighted by ``_VELOCITY_WEIGHT``. The result is clamped to ``[0, 1]``.
    """
    ring = min(max(ring_size, 0.0) / _RING_SATURATION, 1.0)
    velocity = min(max(velocity_1h, 0.0) / _VELOCITY_SATURATION, 1.0) * _VELOCITY_WEIGHT
    return min(ring + velocity, 1.0)


def _ordered_features(representation: SharedRepresentation) -> dict[str, float]:
    """Return the representation feature row in canonical column order (no skew)."""
    return {col: float(representation.features.get(col, 0.0)) for col in FEATURE_COLUMNS}


def _hint(score: float, settings: Settings) -> DecisionHint:
    """DECLINE at/above the block threshold, else band like risk (docs/02 §3)."""
    if score >= settings.fraud_block_threshold:
        return DecisionHint.DECLINE
    if score <= settings.approve_max:
        return DecisionHint.APPROVE
    if score <= settings.challenge_max:
        return DecisionHint.CHALLENGE
    return DecisionHint.DECLINE


def build_score_fn(client: MlScoringClient, settings: Settings) -> ScoreFn:
    """Build the injected fraud ``score_fn`` bound to an ml-scoring client (docs/02 §2.2).

    Combines the ml ``model='fraud'`` probability with the graph component (max of the
    two), emits ``shared_device_ring_size`` + ``velocity_1h`` as evidence, and sets the
    decision hint via :func:`_hint`. Pure given the injected client + gathered signals.
    """

    def _score(representation: SharedRepresentation, signals: dict[str, Any]) -> ScoreResult:
        trace_id = str(signals.get("trace_id", representation.transaction_id))
        ring_size = float(signals.get("shared_device_ring_size", _ring_size(representation)))
        velocity = float(signals.get("velocity_1h", _velocity_1h(representation)))

        response = client.score(_MODEL, _ordered_features(representation), trace_id)
        graph = graph_component(ring_size, velocity)
        score = max(response.score, graph)

        evidence = [
            Evidence(signal="shared_device_ring_size", value=ring_size, weight=1.0),
            Evidence(signal="velocity_1h", value=velocity, weight=_VELOCITY_WEIGHT),
        ]
        return ScoreResult(
            score=score,
            decision_hint=_hint(score, settings),
            model_version=response.model_version,
            evidence=evidence,
        )

    return _score


__all__ = [
    "MlScoringClient",
    "ScoreResponse",
    "build_score_fn",
    "gather_graph_signals",
    "graph_component",
]
