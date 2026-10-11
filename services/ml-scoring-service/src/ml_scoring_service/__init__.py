"""ACIP ml-scoring-service: serves risk/fraud model scores (docs/05).

Resolves model artifacts from ``<ML_MODELS_DIR>/model_card.json`` at startup, warms up
the models, and gates ``/readyz`` on load. When artifacts are absent it serves a
deterministic heuristic (``heuristic-v1``) so the demo still runs (docs/05 §5).
"""

from __future__ import annotations

__all__: list[str] = []
