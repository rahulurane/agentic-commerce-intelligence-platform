"""Wire the risk scorer into the shared agent runner (docs/02 §2.2, §6).

:func:`build_runner` injects the risk :func:`~risk_agent.scorer.build_score_fn` into an
:class:`acip_agent_common.AgentRunner`, so the risk agent is the uniform
consume/score/publish machine with only its scoring behavior swapped in. Dependencies
(the ml-scoring client, Kafka producer/consumer) are injectable so tests drive the
runner with mocks.
"""

from __future__ import annotations

from acip_agent_common import AgentRunner
from acip_common.config import Settings
from acip_common.kafka import EventConsumer, EventProducer
from acip_common.schemas import AgentName
from risk_agent.scorer import MlScoringClient, build_score_fn


def build_runner(
    settings: Settings,
    *,
    client: MlScoringClient | None = None,
    producer: EventProducer | None = None,
    consumer: EventConsumer | None = None,
) -> AgentRunner:
    """Build the risk :class:`AgentRunner` with its ml-scoring-backed score_fn."""
    scoring_client = client or MlScoringClient(settings.ml_scoring_url)
    return AgentRunner(
        AgentName.RISK,
        build_score_fn(scoring_client, settings),
        settings,
        producer=producer,
        consumer=consumer,
    )


__all__ = ["build_runner"]
