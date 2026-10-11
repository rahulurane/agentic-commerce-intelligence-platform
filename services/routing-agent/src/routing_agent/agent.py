"""Wire the routing scorer into the shared agent runner (docs/02 §2.2, §3.1, §6).

Injects the routing :func:`~routing_agent.scorer.build_score_fn` into an
:class:`acip_agent_common.AgentRunner`, so the routing agent is the uniform
consume/score/publish machine with only its route-ranking behavior swapped in.
Dependencies are injectable so tests drive the runner with mocks.
"""

from __future__ import annotations

from acip_agent_common import AgentRunner
from acip_common.config import Settings
from acip_common.kafka import EventConsumer, EventProducer
from acip_common.schemas import AgentName
from routing_agent.scorer import build_score_fn


def build_runner(
    settings: Settings,
    *,
    producer: EventProducer | None = None,
    consumer: EventConsumer | None = None,
) -> AgentRunner:
    """Build the routing :class:`AgentRunner` with its route-ranking score_fn."""
    return AgentRunner(
        AgentName.ROUTING,
        build_score_fn(settings),
        settings,
        producer=producer,
        consumer=consumer,
    )


__all__ = ["build_runner"]
