"""Wire the fraud scorer into the shared agent runner (docs/02 §2.2, §6).

Injects the fraud :func:`~fraud_agent.scorer.build_score_fn` and its graph-signal
:func:`~fraud_agent.scorer.gather_graph_signals` ``gather_fn`` into an
:class:`acip_agent_common.AgentRunner`, so the fraud agent is the uniform
consume/score/publish machine with only its scoring + signal-gathering behavior swapped
in. Dependencies are injectable so tests drive the runner with mocks.
"""

from __future__ import annotations

from acip_agent_common import AgentRunner
from acip_common.config import Settings
from acip_common.kafka import EventConsumer, EventProducer
from acip_common.schemas import AgentName
from fraud_agent.scorer import MlScoringClient, build_score_fn, gather_graph_signals


def build_runner(
    settings: Settings,
    *,
    client: MlScoringClient | None = None,
    producer: EventProducer | None = None,
    consumer: EventConsumer | None = None,
) -> AgentRunner:
    """Build the fraud :class:`AgentRunner` with its ml + graph-signal score_fn."""
    scoring_client = client or MlScoringClient(settings.ml_scoring_url)
    return AgentRunner(
        AgentName.FRAUD,
        build_score_fn(scoring_client, settings),
        settings,
        gather_fn=gather_graph_signals,
        producer=producer,
        consumer=consumer,
    )


__all__ = ["build_runner"]
