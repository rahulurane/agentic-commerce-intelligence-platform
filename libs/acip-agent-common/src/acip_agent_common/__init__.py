"""ACIP shared agent scaffolding (docs/02 §2.2, §3, §6).

Every one of the six evaluating agents (docs/02 §3) is the SAME machine with a different
scoring function injected: a uniform per-agent LangGraph graph
(``parse_request -> gather_signals -> score -> reason -> assemble_verdict``), a Kafka
consume/evaluate/publish loop (:class:`~acip_agent_common.runner.AgentRunner`), a
templated-fallback LLM rationale (:func:`~acip_agent_common.rationale.llm_rationale`), and
a health app (:func:`~acip_agent_common.health.make_health_app`). Behavior differs by the
injected ``score_fn``/``gather_fn``, not by forking this code (docs/02 §2.2).

This is a NEW shared lib — it reuses the ``acip_common`` contracts (schemas, config,
kafka, topics, logging) and never redefines them.
"""

from acip_agent_common.graph import (
    AgentGraphResult,
    GatherFn,
    ScoreFn,
    ScoreResult,
    build_agent_graph,
)
from acip_agent_common.health import make_health_app
from acip_agent_common.rationale import llm_rationale
from acip_agent_common.runner import AgentRunner

__version__ = "0.1.0"

__all__ = [
    "AgentGraphResult",
    "AgentRunner",
    "GatherFn",
    "ScoreFn",
    "ScoreResult",
    "build_agent_graph",
    "llm_rationale",
    "make_health_app",
]
