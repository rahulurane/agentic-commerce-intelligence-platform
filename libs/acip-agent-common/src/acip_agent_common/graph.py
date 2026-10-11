"""The uniform per-agent LangGraph graph (docs/02 §2.2, §3).

Every evaluating agent is the SAME five-node machine; only the injected scoring function
differs (docs/02 §2.2). The node sequence is:

    parse_request -> gather_signals -> score -> reason -> assemble_verdict

* ``parse_request``   — validate the inbound ``TxnEvaluateRequestedPayload`` and pull the
  shared representation (docs/03 §8) onto the state.
* ``gather_signals``  — optional, injected ``gather_fn``: derive the agent-specific
  signal slice (e.g. a graph lookup) from the representation; defaults to a no-op.
* ``score``           — the injected ``score_fn`` turns the representation (+ gathered
  signals) into ``(score, decision_hint, evidence, model_version)``.
* ``reason``          — attach a rationale via the templated-fallback LLM helper so the
  agent never blocks on the LLM (docs/02 §1).
* ``assemble_verdict``— build the ``acip_common`` :class:`~acip_common.schemas.Verdict`.

Behavior differs by INJECTION (``score_fn``/``gather_fn``), not by forking this code
(docs/02 §2.2/§3). The graph is deliberately dependency-light: it threads a plain
``TypedDict`` state and takes the ``score_fn`` and ``settings`` off the LangGraph config so
the compiled graph stays stateless and reusable across transactions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from acip_agent_common.rationale import llm_rationale
from acip_common.config import Settings
from acip_common.schemas import (
    DecisionHint,
    Evidence,
    SharedRepresentation,
    TxnEvaluateRequestedPayload,
    Verdict,
)


@dataclass
class ScoreResult:
    """What an agent's ``score_fn`` returns for a representation slice (docs/02 §2.2, §4)."""

    score: float
    decision_hint: DecisionHint
    model_version: str
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 1.0


# An agent's scoring function: representation (+ gathered signals) -> ScoreResult. This is
# the ONLY per-agent variation; everything else in the graph is shared (docs/02 §2.2).
ScoreFn = Callable[[SharedRepresentation, dict[str, Any]], ScoreResult]

# Optional signal-gathering: derive an agent-specific slice (e.g. graph lookup) from the
# representation. Defaults to a no-op so most agents inject only a ``score_fn``.
GatherFn = Callable[[SharedRepresentation], dict[str, Any]]


@dataclass
class AgentGraphResult:
    """The output of a single graph run: the verdict + the representation it scored."""

    verdict: Verdict
    representation: SharedRepresentation


class AgentGraphState(TypedDict, total=False):
    """Typed state threaded through the per-agent graph (docs/02 §2.2)."""

    payload: dict[str, Any]
    trace_id: str
    representation: dict[str, Any]
    signals: dict[str, Any]
    agent_score: float
    decision_hint: str
    model_version: str
    confidence: float
    evidence: list[dict[str, Any]]
    rationale: str
    degraded: bool
    verdict: dict[str, Any]


def _agent_name(config: dict[str, Any]) -> str:
    return str(config["configurable"]["agent_name"])


def _score_fn(config: dict[str, Any]) -> ScoreFn:
    return cast(ScoreFn, config["configurable"]["score_fn"])


def _gather_fn(config: dict[str, Any]) -> GatherFn | None:
    return cast("GatherFn | None", config["configurable"].get("gather_fn"))


def _settings(config: dict[str, Any]) -> Settings:
    return cast(Settings, config["configurable"]["settings"])


def _parse_request_node(state: AgentGraphState, config: dict[str, Any]) -> dict[str, Any]:
    """Validate the inbound payload and pull the shared representation onto the state."""
    payload = TxnEvaluateRequestedPayload.model_validate(state["payload"])
    return {"representation": payload.representation.model_dump(mode="json")}


def _gather_signals_node(state: AgentGraphState, config: dict[str, Any]) -> dict[str, Any]:
    """Run the optional injected ``gather_fn`` to derive the agent-specific signal slice."""
    gather = _gather_fn(config)
    if gather is None:
        return {"signals": {}}
    representation = SharedRepresentation.model_validate(state["representation"])
    return {"signals": gather(representation)}


def _score_node(state: AgentGraphState, config: dict[str, Any]) -> dict[str, Any]:
    """Run the injected ``score_fn`` — the only per-agent behavior (docs/02 §2.2)."""
    representation = SharedRepresentation.model_validate(state["representation"])
    result = _score_fn(config)(representation, state.get("signals", {}))
    return {
        "agent_score": result.score,
        "decision_hint": result.decision_hint.value,
        "model_version": result.model_version,
        "confidence": result.confidence,
        "evidence": [e.model_dump(mode="json") for e in result.evidence],
    }


def _reason_node(state: AgentGraphState, config: dict[str, Any]) -> dict[str, Any]:
    """Attach a rationale via the templated-fallback LLM helper (docs/02 §1)."""
    agent = _agent_name(config)
    settings = _settings(config)
    system = f"You are the {agent} agent explaining a payment verdict."
    prompt = (
        f"agent={agent} score={state.get('agent_score')} "
        f"decision_hint={state.get('decision_hint')} "
        f"evidence={state.get('evidence')}"
    )
    result = llm_rationale(
        settings,
        system=system,
        prompt=prompt,
        trace_id=state.get("trace_id", ""),
    )
    return {"rationale": result.text, "degraded": result.degraded}


def _assemble_verdict_node(state: AgentGraphState, config: dict[str, Any]) -> dict[str, Any]:
    """Build the ``acip_common`` ``Verdict`` from the scored + reasoned state (docs/02 §4)."""
    verdict = Verdict(
        decision_hint=DecisionHint(state["decision_hint"]),
        score=state["agent_score"],
        confidence=state.get("confidence", 1.0),
        rationale=state.get("rationale", ""),
        evidence=[Evidence.model_validate(e) for e in state.get("evidence", [])],
        model_version=state["model_version"],
        degraded=state.get("degraded", False),
    )
    return {"verdict": verdict.model_dump(mode="json")}


def build_agent_graph() -> Any:
    """Build and compile the uniform per-agent graph (docs/02 §2.2).

    The ``score_fn``/``gather_fn``/``settings``/``agent_name`` come off the LangGraph
    config at run time (see :func:`run_agent_graph`), so the compiled graph is stateless
    and shared across all transactions and agents.
    """
    graph = StateGraph(AgentGraphState)

    def _node(fn: Callable[[AgentGraphState, dict[str, Any]], dict[str, Any]]) -> Any:
        # Nodes take ``(state, config)``; LangGraph accepts that at runtime while its typed
        # stub lists only the single-arg form, so cast to the Callable the stub expects.
        return cast("Callable[[Any], Any]", fn)

    graph.add_node("parse_request", _node(_parse_request_node))
    graph.add_node("gather_signals", _node(_gather_signals_node))
    graph.add_node("score", _node(_score_node))
    graph.add_node("reason", _node(_reason_node))
    graph.add_node("assemble_verdict", _node(_assemble_verdict_node))

    graph.add_edge(START, "parse_request")
    graph.add_edge("parse_request", "gather_signals")
    graph.add_edge("gather_signals", "score")
    graph.add_edge("score", "reason")
    graph.add_edge("reason", "assemble_verdict")
    graph.add_edge("assemble_verdict", END)

    return graph.compile()


def run_agent_graph(
    *,
    compiled: Any,
    agent_name: str,
    score_fn: ScoreFn,
    settings: Settings,
    payload: dict[str, Any],
    trace_id: str,
    gather_fn: GatherFn | None = None,
) -> AgentGraphResult:
    """Run the compiled per-agent graph for one evaluate request (docs/02 §2.2).

    ``payload`` is the raw ``TxnEvaluateRequestedPayload`` dict off the inbound envelope.
    Returns the produced :class:`~acip_common.schemas.Verdict` and the scored
    representation.
    """
    initial: AgentGraphState = {"payload": payload, "trace_id": trace_id}
    config = {
        "configurable": {
            "agent_name": agent_name,
            "score_fn": score_fn,
            "gather_fn": gather_fn,
            "settings": settings,
        }
    }
    final_state: AgentGraphState = compiled.invoke(initial, config=config)
    verdict = Verdict.model_validate(final_state["verdict"])
    representation = SharedRepresentation.model_validate(final_state["representation"])
    return AgentGraphResult(verdict=verdict, representation=representation)


__all__ = [
    "AgentGraphResult",
    "AgentGraphState",
    "GatherFn",
    "ScoreFn",
    "ScoreResult",
    "build_agent_graph",
    "run_agent_graph",
]
