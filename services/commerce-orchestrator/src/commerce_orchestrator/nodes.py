"""LangGraph node functions for the evaluation graph (docs/02 §2.1, docs/01 §4).

Each node is a pure-ish function ``(state) -> partial state update`` so the graph in
``graph.py`` can wire them with typed edges and so they are trivially unit-testable
with mocked dependencies. The node sequence mirrors the transaction lifecycle:

    build_representation -> fan_out -> collect_verdicts
      --(all_received)--> decide ----\
      --(deadline)------> decide_partial --> execute -> finalize

Dependencies (HTTP clients, Kafka producer/consumer, Settings) are carried on the
state under ``deps`` so the same node code runs in production and under test — the
test swaps ``deps`` for mocks. Nothing here imports confluent-kafka or httpx at module
scope, so the module imports with no broker/creds (docs/01 §6).

PHASE 2 CRITICAL PATH (FEAT-003 guarantee): with NO agents running, ``collect_verdicts``
polls ``agent.verdicts`` until the deadline, collects zero verdicts, and the routing
function :func:`route_after_collect` returns ``"decide_partial"``. ``decide_partial``
then calls decision-engine with the empty verdict set, so the missing-verdict policy
(``MISSING_RISK_FRAUD_POLICY``) still yields a decision. This is logged explicitly.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict

from acip_common.schemas import (
    AgentName,
    AgentVerdictProducedPayload,
    DecisionHint,
    DecisionRenderedPayload,
    EventEnvelope,
    EventType,
    SharedRepresentation,
    TxnEvaluateRequestedPayload,
    TxnTerminalPayload,
    Verdict,
)
from acip_common.topics import TXN_EVALUATE, TXN_LIFECYCLE

_log = logging.getLogger("commerce_orchestrator.nodes")

_PRODUCER = "commerce-orchestrator"

# The six agents the orchestrator expects to hear from (docs/02 §3). In Phase 2 none
# are running, so the deadline path is the live one.
_EXPECTED_AGENTS: list[AgentName] = list(AgentName)

# Final decisions that trigger a real charge (docs/06 §4). Everything else short-circuits.
_EXECUTE_DECISIONS = {DecisionHint.APPROVE, DecisionHint.ROUTE}

# Map a final decision to its terminal lifecycle event type (docs/06 §3).
_TERMINAL_EVENT: dict[DecisionHint, EventType] = {
    DecisionHint.APPROVE: EventType.TXN_EXECUTED,
    DecisionHint.ROUTE: EventType.TXN_EXECUTED,
    DecisionHint.CHALLENGE: EventType.TXN_CHALLENGED,
    DecisionHint.DECLINE: EventType.TXN_DECLINED,
}


class OrchestratorState(TypedDict, total=False):
    """Typed LangGraph state threaded through the evaluation graph (docs/02 §2.1)."""

    transaction_id: str
    trace_id: str
    # Transaction core fields needed to build the representation / charge.
    amount: float
    currency: str
    method_type: str
    merchant_id: str
    customer_id: str
    txn_geo: str | None
    device_fingerprint: str | None
    # Produced as the graph runs.
    representation: dict[str, Any] | None
    verdicts: dict[str, Any]
    deadline_reached: bool
    decision: dict[str, Any] | None
    processor_result: dict[str, Any] | None


def _deps(config: dict[str, Any]) -> Any:
    """Pull the injected dependencies off the LangGraph ``config``.

    Dependencies (HTTP clients, Kafka producer/consumer, Settings, persist callable)
    are passed via ``config["configurable"]["deps"]`` rather than carried on the graph
    state, so the checkpointer never tries to serialize non-serializable live objects
    (httpx/Kafka clients). Only the plain-data state channels are checkpointed.
    """
    return config["configurable"]["deps"]


def _envelope(
    event_type: EventType,
    transaction_id: str,
    trace_id: str,
    payload: dict[str, Any],
) -> EventEnvelope:
    """Build a versioned event envelope (docs/03 §1)."""
    return EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        transaction_id=transaction_id,
        trace_id=trace_id,
        occurred_at=datetime.now(tz=UTC),
        producer=_PRODUCER,
        payload=payload,
    )


def build_representation_node(state: OrchestratorState, config: dict[str, Any]) -> dict[str, Any]:
    """Call representation-service and attach the shared representation (docs/03 §8)."""
    deps = _deps(config)
    representation = deps.clients.build_representation(
        transaction_id=state["transaction_id"],
        trace_id=state["trace_id"],
        amount=state["amount"],
        currency=state["currency"],
        method_type=state["method_type"],
        merchant_id=state["merchant_id"],
        customer_id=state["customer_id"],
        txn_geo=state.get("txn_geo"),
        device_fingerprint=state.get("device_fingerprint"),
    )
    _log.info("representation built", extra={"transaction_id": state["transaction_id"]})
    return {"representation": representation.model_dump(mode="json")}


def fan_out_node(state: OrchestratorState, config: dict[str, Any]) -> dict[str, Any]:
    """Publish ``txn.evaluate.requested`` to ``txn.evaluate`` for the agents (docs/06 §3)."""
    deps = _deps(config)
    representation = SharedRepresentation.model_validate(state["representation"])
    payload = TxnEvaluateRequestedPayload(
        representation=representation,
        expected_agents=_EXPECTED_AGENTS,
        deadline_ms=deps.settings.decision_deadline_ms,
    )
    envelope = _envelope(
        EventType.TXN_EVALUATE_REQUESTED,
        state["transaction_id"],
        state["trace_id"],
        payload.model_dump(mode="json"),
    )
    deps.producer.publish(TXN_EVALUATE, envelope)
    deps.producer.flush()
    _log.info(
        "fan-out published to agents",
        extra={
            "transaction_id": state["transaction_id"],
            "expected_agents": [a.value for a in _EXPECTED_AGENTS],
            "deadline_ms": deps.settings.decision_deadline_ms,
        },
    )
    return {"verdicts": {}, "deadline_reached": False}


def collect_verdicts_node(state: OrchestratorState, config: dict[str, Any]) -> dict[str, Any]:
    """Consume ``agent.verdicts`` until all expected arrive OR the deadline elapses.

    Filters by ``transaction_id`` and accumulates verdicts keyed by agent name. The
    loop ends on the first of: all six expected verdicts collected, or
    ``decision_deadline_ms`` elapsed. With no agents running (Phase 2) this returns an
    empty verdict map with ``deadline_reached=True`` — the critical path.
    """
    deps = _deps(config)
    deadline_s = deps.settings.decision_deadline_ms / 1000.0
    started = time.monotonic()
    verdicts: dict[str, Any] = dict(state.get("verdicts") or {})

    while len(verdicts) < len(_EXPECTED_AGENTS):
        remaining = deadline_s - (time.monotonic() - started)
        if remaining <= 0:
            break
        envelope = deps.consumer.poll(min(remaining, 0.25))
        if envelope is None:
            continue
        if envelope.event_type is not EventType.AGENT_VERDICT_PRODUCED:
            continue
        if envelope.transaction_id != state["transaction_id"]:
            continue
        parsed = AgentVerdictProducedPayload.model_validate(envelope.payload)
        verdicts[parsed.agent.value] = parsed.verdict.model_dump(mode="json")
        deps.consumer.commit()

    deadline_reached = len(verdicts) < len(_EXPECTED_AGENTS)
    if deadline_reached:
        _log.warning(
            (
                "no verdicts received, deadline elapsed, applying missing-verdict policy"
                if not verdicts
                else "partial verdicts received, deadline elapsed, applying missing-verdict policy"
            ),
            extra={
                "transaction_id": state["transaction_id"],
                "collected": len(verdicts),
                "expected": len(_EXPECTED_AGENTS),
                "deadline_ms": deps.settings.decision_deadline_ms,
            },
        )
    else:
        _log.info(
            "all expected verdicts collected",
            extra={"transaction_id": state["transaction_id"], "collected": len(verdicts)},
        )
    return {"verdicts": verdicts, "deadline_reached": deadline_reached}


def route_after_collect(state: OrchestratorState) -> str:
    """Conditional edge: ``decide`` when all verdicts arrived, else ``decide_partial``."""
    return "decide_partial" if state.get("deadline_reached") else "decide"


def _parsed_verdicts(state: OrchestratorState) -> dict[AgentName, Verdict]:
    """Rebuild the typed verdict map from the serialized state."""
    out: dict[AgentName, Verdict] = {}
    for name, raw in (state.get("verdicts") or {}).items():
        out[AgentName(name)] = Verdict.model_validate(raw)
    return out


def _decide(state: OrchestratorState, config: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    """Shared decision call used by both ``decide`` and ``decide_partial``."""
    deps = _deps(config)
    representation = SharedRepresentation.model_validate(state["representation"])
    verdicts = _parsed_verdicts(state)
    decision = deps.clients.decide(
        transaction_id=state["transaction_id"],
        trace_id=state["trace_id"],
        verdicts=verdicts,
        candidate_routes=representation.candidate_routes,
    )
    _log.info(
        "decision rendered",
        extra={
            "transaction_id": state["transaction_id"],
            "decision": decision.decision.value,
            "partial": partial,
            "verdict_count": len(verdicts),
        },
    )
    return {"decision": decision.model_dump(mode="json")}


def decide_node(state: OrchestratorState, config: dict[str, Any]) -> dict[str, Any]:
    """Full-set decision: all expected verdicts collected (docs/02 §5)."""
    return _decide(state, config, partial=False)


def decide_partial_node(state: OrchestratorState, config: dict[str, Any]) -> dict[str, Any]:
    """Partial/empty-set decision after the deadline — the missing-verdict path.

    decision-engine applies ``MISSING_RISK_FRAUD_POLICY`` to the partial (often empty)
    verdict set, so a decision is still produced with NO agents running (FEAT-003).
    """
    return _decide(state, config, partial=True)


def execute_node(state: OrchestratorState, config: dict[str, Any]) -> dict[str, Any]:
    """On APPROVE/ROUTE charge the processor; otherwise short-circuit (docs/06 §4)."""
    deps = _deps(config)
    decision = DecisionRenderedPayload.model_validate(state["decision"])
    representation = SharedRepresentation.model_validate(state["representation"])

    if decision.decision not in _EXECUTE_DECISIONS:
        _log.info(
            "non-executable decision; skipping charge",
            extra={"transaction_id": state["transaction_id"], "decision": decision.decision.value},
        )
        return {"processor_result": None}

    route = decision.route or (
        representation.candidate_routes[0].processor
        if representation.candidate_routes
        else "processor_default"
    )
    try:
        result = deps.clients.charge(
            transaction_id=state["transaction_id"],
            trace_id=state["trace_id"],
            amount=representation.transaction.amount,
            currency=representation.transaction.currency,
            route=route,
        )
    except Exception as exc:
        _log.warning(
            "charge failed; recording declined processor result",
            extra={"transaction_id": state["transaction_id"], "route": route, "error": str(exc)},
        )
        result = {"status": "DECLINED", "processor": route, "auth_code": None, "latency_ms": 0}
    return {"processor_result": result}


def finalize_node(state: OrchestratorState, config: dict[str, Any]) -> dict[str, Any]:
    """Emit the terminal lifecycle event and persist the decision trace (docs/06 §3)."""
    deps = _deps(config)
    decision = DecisionRenderedPayload.model_validate(state["decision"])
    representation = SharedRepresentation.model_validate(state["representation"])
    verdicts = _parsed_verdicts(state)

    terminal_payload = TxnTerminalPayload(
        decision=decision.decision,
        route=decision.route,
        processor_result=state.get("processor_result"),
        composite_score=decision.composite_score,
        decided_at=datetime.now(tz=UTC),
    )
    envelope = _envelope(
        _TERMINAL_EVENT[decision.decision],
        state["transaction_id"],
        state["trace_id"],
        terminal_payload.model_dump(mode="json"),
    )
    deps.producer.publish(TXN_LIFECYCLE, envelope)
    deps.producer.flush()

    persisted = deps.persist(
        representation=representation,
        decision=decision,
        verdicts={agent.value: verdict for agent, verdict in verdicts.items()},
    )
    _log.info(
        "transaction finalized",
        extra={
            "transaction_id": state["transaction_id"],
            "decision": decision.decision.value,
            "persisted": persisted,
        },
    )
    return {}


__all__ = [
    "OrchestratorState",
    "build_representation_node",
    "collect_verdicts_node",
    "decide_node",
    "decide_partial_node",
    "execute_node",
    "fan_out_node",
    "finalize_node",
    "route_after_collect",
]
