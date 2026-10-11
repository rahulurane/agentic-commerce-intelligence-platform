"""Assemble the shared transaction representation (docs/03 §8, docs/01 §4 step 2).

:func:`build_representation` is the heart of the service. It:

1. hydrates graph signals (Neo4j) and hot features (Redis) via the store adapters,
2. assembles the raw signal mapping the feature transforms expect,
3. calls :func:`acip_common.features.build_feature_row` to compute the 7
   ``FEATURE_COLUMNS`` (one definition, no train/serve skew — docs/05 §3),
4. returns a :class:`acip_common.schemas.SharedRepresentation`.

SPARSE-GRAPH FALLBACK (FEAT-003, docs/03 §8): when Neo4j/Redis are empty or
unreachable the adapters return empty signals, so the builder fills sensible defaults
(zeros, and a single default candidate route) and marks the result ``degraded`` so the
evaluation path still runs with nothing seeded. The function is pure given the two
signal objects, which keeps it unit-testable with mocked/absent stores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from acip_common.features import build_feature_row
from acip_common.schemas import (
    CandidateRoute,
    MethodHistoryEntry,
    SharedRepresentation,
    TransactionCore,
)
from representation_service.stores import GraphSignals, HotSignals

# When the graph has no Processor nodes (sparse/unreachable), fall back to a single
# default route so routing/decision overlays still have something to rank (docs/03 §8).
_DEFAULT_ROUTE = CandidateRoute(processor="processor_default", success_rate=0.9)


@dataclass
class BuildResult:
    """A built representation plus whether any store was degraded (docs/03 §8)."""

    representation: SharedRepresentation
    degraded: bool


def _candidate_routes(graph: GraphSignals) -> list[CandidateRoute]:
    """Map graph route rows to :class:`CandidateRoute`, defaulting when sparse."""
    if not graph.candidate_routes:
        return [_DEFAULT_ROUTE]
    routes: list[CandidateRoute] = []
    for raw in graph.candidate_routes:
        routes.append(
            CandidateRoute(
                processor=str(raw["processor"]),
                success_rate=float(raw["success_rate"]),
                cost_bps=raw.get("cost_bps"),
                p50_latency_ms=raw.get("p50_latency_ms"),
            )
        )
    return routes


def build_representation(
    *,
    transaction_id: str,
    amount: float,
    currency: str,
    method_type: str,
    merchant_id: str,
    customer_id: str,
    txn_geo: str | None,
    device_fingerprint: str | None,
    graph: GraphSignals,
    hot: HotSignals,
    representation_version: int,
    graph_degraded: bool,
    hot_degraded: bool,
) -> BuildResult:
    """Build the shared representation from hydrated signals (docs/03 §8).

    ``graph`` / ``hot`` are the already-hydrated signals; ``*_degraded`` flags say
    whether the respective store was absent/unreachable so the result can be labelled
    degraded. All 7 feature columns are always populated via ``build_feature_row``.
    """
    method_entry = graph.method_history.get(method_type)
    successes = method_entry[0] if method_entry else 0
    failures = method_entry[1] if method_entry else 0

    # Assemble the raw signal mapping build_feature_row expects. Baselines we do not
    # keep online (customer_mean/std, method_first_seen_days) default to 0.0, which the
    # transforms handle gracefully (zscore guards zero-std; a new method ages at 0).
    raw_signals: dict[str, object] = {
        "amount": amount,
        "customer_mean": 0.0,
        "customer_std": 0.0,
        "txn_count_last_hour": hot.velocity_1h,
        "method_first_seen_days": 0.0,
        "txn_geo": txn_geo,
        "home_geo": graph.home_geo,
        "ring_size": graph.ring_size,
        "txn_count_30d": graph.customer_txn_count_30d,
        "chargeback_count": graph.customer_chargeback_count,
    }
    features = build_feature_row(raw_signals)

    graph_signals: dict[str, float] = {
        "ring_size": float(graph.ring_size),
        "customer_txn_count_30d": float(graph.customer_txn_count_30d),
        "customer_chargeback_count": float(graph.customer_chargeback_count),
        "velocity_1h": float(hot.velocity_1h),
    }

    method_history = {
        method_type: MethodHistoryEntry(successes=successes, failures=failures),
    }

    representation = SharedRepresentation(
        representation_version=representation_version,
        transaction_id=transaction_id,
        built_at=datetime.now(tz=UTC),
        transaction=TransactionCore(
            amount=amount,
            currency=currency,
            method_type=method_type,  # type: ignore[arg-type]
            merchant_id=merchant_id,
            customer_id=customer_id,
        ),
        features=features,
        graph_signals=graph_signals,
        method_history=method_history,
        candidate_routes=_candidate_routes(graph),
    )
    return BuildResult(representation=representation, degraded=graph_degraded or hot_degraded)


__all__ = ["BuildResult", "build_representation"]
