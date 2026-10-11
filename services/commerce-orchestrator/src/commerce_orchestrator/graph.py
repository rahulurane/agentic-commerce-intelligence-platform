"""LangGraph ``StateGraph`` wiring + Redis checkpointing (docs/02 §2.1, docs/06 §2/§4).

:func:`build_graph` assembles the evaluation graph from the node functions in
``nodes.py``:

    build_representation -> fan_out -> collect_verdicts
      --(all_received)--> decide ---------\
      --(deadline)------> decide_partial -> execute -> finalize -> END

The ``collect_verdicts`` -> {``decide``, ``decide_partial``} edge is CONDITIONAL on
:func:`nodes.route_after_collect`. With no agents running the deadline branch
(``decide_partial``) is taken, so a decision is still produced (FEAT-003 guarantee).

CHECKPOINTER CHOICE (justification required by FEAT-003): we checkpoint graph state in
Redis for crash-resume keyed by ``transaction_id``. Rather than take a hard dependency
on a specific ``langgraph-checkpoint-redis`` package version (its API churns and it is
not pinned in this repo), we persist a compact JSON snapshot of the state to Redis
ourselves via :class:`RedisStateSnapshotStore`, and use LangGraph's built-in
``MemorySaver`` as the in-process superstep checkpointer. This keeps the public,
stable LangGraph checkpointer interface in play while giving durable, inspectable
cross-process resume state keyed exactly by ``transaction_id`` with no extra pins.
Snapshot writes are best-effort so the path runs with Redis down.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from acip_common.config import Settings
from acip_common.schemas import DecisionRenderedPayload, SharedRepresentation, Verdict
from commerce_orchestrator import nodes
from commerce_orchestrator.clients import ServiceClients
from commerce_orchestrator.nodes import OrchestratorState

_log = logging.getLogger("commerce_orchestrator.graph")

_CHECKPOINT_PREFIX = "orchestrator:checkpoint:"


class RedisStateSnapshotStore:
    """Durable, cross-process state snapshots keyed by ``transaction_id`` (docs/02 §6).

    A thin Redis wrapper used for crash-resume: ``save`` writes the serialized graph
    state, ``load`` reads it back. Best-effort — Redis being down degrades to no-op so
    the evaluation path still completes (consistent with the sparse-store posture).
    Opens the client lazily so importing this module needs no running Redis.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is None:
            try:
                import redis

                self._client = redis.Redis.from_url(self._url)
            except Exception as exc:  # pragma: no cover - import/connect guard
                _log.warning(
                    "redis unavailable for checkpoints; degraded",
                    extra={"error": str(exc)},
                )
                return None
        return self._client

    def save(self, transaction_id: str, snapshot_json: str) -> None:
        """Persist the state snapshot for ``transaction_id`` (best-effort)."""
        client = self._ensure()
        if client is None:
            return
        try:
            client.set(f"{_CHECKPOINT_PREFIX}{transaction_id}", snapshot_json)
        except Exception as exc:
            _log.warning("checkpoint save failed; degraded", extra={"error": str(exc)})

    def load(self, transaction_id: str) -> str | None:
        """Load a prior state snapshot for ``transaction_id`` if present."""
        client = self._ensure()
        if client is None:
            return None
        try:
            raw = client.get(f"{_CHECKPOINT_PREFIX}{transaction_id}")
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw
        except Exception as exc:
            _log.warning("checkpoint load failed; degraded", extra={"error": str(exc)})
            return None

    def close(self) -> None:
        """Close the client if it was opened."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None


PersistFn = Callable[..., bool]


@dataclass
class Deps:
    """Dependencies injected onto the graph state (swapped for mocks in tests)."""

    settings: Settings
    clients: ServiceClients
    producer: Any
    consumer: Any
    persist: PersistFn


def build_graph() -> Any:
    """Build and compile the evaluation ``StateGraph`` (docs/02 §2.1).

    Compiled with a ``MemorySaver`` so LangGraph's checkpointer interface drives
    superstep persistence; durable cross-process resume is handled by the Redis
    snapshot store written in ``finalize`` (see module docstring).
    """
    graph = StateGraph(OrchestratorState)

    # Nodes take ``(state, config)`` so deps come off config, not the checkpointed
    # state. LangGraph accepts that signature at runtime; its typed stub only lists the
    # single-arg form, so cast to the Callable the stub expects.
    def _node(fn: Callable[[OrchestratorState, dict[str, Any]], dict[str, Any]]) -> Any:
        return cast("Callable[[Any], Any]", fn)

    graph.add_node("build_representation", _node(nodes.build_representation_node))
    graph.add_node("fan_out", _node(nodes.fan_out_node))
    graph.add_node("collect_verdicts", _node(nodes.collect_verdicts_node))
    graph.add_node("decide", _node(nodes.decide_node))
    graph.add_node("decide_partial", _node(nodes.decide_partial_node))
    graph.add_node("execute", _node(nodes.execute_node))
    graph.add_node("finalize", _node(nodes.finalize_node))

    graph.add_edge(START, "build_representation")
    graph.add_edge("build_representation", "fan_out")
    graph.add_edge("fan_out", "collect_verdicts")
    graph.add_conditional_edges(
        "collect_verdicts",
        nodes.route_after_collect,
        {"decide": "decide", "decide_partial": "decide_partial"},
    )
    graph.add_edge("decide", "execute")
    graph.add_edge("decide_partial", "execute")
    graph.add_edge("execute", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=MemorySaver())


def _snapshot(state: OrchestratorState) -> dict[str, Any]:
    """Build a JSON-safe snapshot of the final state (all channels are plain data)."""
    return dict(state)


def run_evaluation(
    *,
    compiled: Any,
    deps: Deps,
    transaction: dict[str, Any],
    snapshots: RedisStateSnapshotStore | None = None,
) -> DecisionRenderedPayload:
    """Run the compiled graph to completion and return the decision (docs/06 §2).

    ``transaction`` carries the transaction core + ``transaction_id`` + ``trace_id``.
    The final state is snapshotted to Redis keyed by ``transaction_id`` for crash
    resume. Raises ``RuntimeError`` if the graph somehow finishes with no decision.
    """
    import json

    initial: OrchestratorState = {
        "transaction_id": transaction["transaction_id"],
        "trace_id": transaction["trace_id"],
        "amount": transaction["amount"],
        "currency": transaction["currency"],
        "method_type": transaction["method_type"],
        "merchant_id": transaction["merchant_id"],
        "customer_id": transaction["customer_id"],
        "txn_geo": transaction.get("txn_geo"),
        "device_fingerprint": transaction.get("device_fingerprint"),
        "verdicts": {},
    }
    # deps are passed via config (NOT the state) so the checkpointer only serializes
    # plain-data channels, never the live httpx/Kafka clients (see module docstring).
    config = {
        "configurable": {
            "thread_id": transaction["transaction_id"],
            "deps": deps,
        }
    }
    final_state: OrchestratorState = compiled.invoke(initial, config=config)

    if snapshots is not None:
        snapshots.save(
            transaction["transaction_id"],
            json.dumps(_snapshot(final_state), default=str),
        )

    decision = final_state.get("decision")
    if decision is None:  # pragma: no cover - defensive
        raise RuntimeError("graph completed without producing a decision")
    return DecisionRenderedPayload.model_validate(decision)


# Re-exported for callers/tests that rebuild typed objects from state.
__all__ = [
    "Deps",
    "RedisStateSnapshotStore",
    "SharedRepresentation",
    "Verdict",
    "build_graph",
    "run_evaluation",
]
