"""The uniform agent Kafka loop: consume evaluate requests, publish verdicts (docs/02 §6).

:class:`AgentRunner` is the shared consume/evaluate/publish machine every agent runs. It
subscribes to ``txn.evaluate`` in a per-agent consumer group, filters to
``txn.evaluate.requested`` envelopes, runs the uniform per-agent graph with the injected
``score_fn``, and publishes an ``agent.verdict.produced`` envelope to ``agent.verdicts``
keyed by ``transaction_id`` — then commits the consumer offset ONLY AFTER the publish
succeeds (docs/02 §6). Commit-after-publish gives at-least-once delivery: a crash between
publish and commit replays the request and re-publishes the (idempotent) verdict rather
than dropping it.

Dependencies (producer, consumer, compiled graph) are injected so tests drive the runner
with mocked Kafka and a fake gateway; nothing here opens a broker at import time.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from acip_agent_common.graph import GatherFn, ScoreFn, build_agent_graph, run_agent_graph
from acip_common.config import Settings
from acip_common.kafka import EventConsumer, EventProducer
from acip_common.logging import bind_trace_id
from acip_common.schemas import (
    AgentName,
    AgentVerdictProducedPayload,
    EventEnvelope,
    EventType,
    Verdict,
)
from acip_common.topics import TXN_EVALUATE, topic_for

_log = logging.getLogger("acip_agent_common.runner")


class AgentRunner:
    """Consume evaluate requests, score, publish ``agent.verdict.produced`` (docs/02 §6).

    Construct with the agent name, its injected ``score_fn`` (and optional ``gather_fn``),
    and ``Settings``. :meth:`run_once` scores one envelope and publishes its verdict;
    :meth:`consume_forever` runs the commit-after-publish loop over ``txn.evaluate``.
    """

    def __init__(
        self,
        agent_name: AgentName,
        score_fn: ScoreFn,
        settings: Settings,
        *,
        gather_fn: GatherFn | None = None,
        producer: EventProducer | None = None,
        consumer: EventConsumer | None = None,
        compiled: Any | None = None,
    ) -> None:
        self.agent_name = agent_name
        self._score_fn = score_fn
        self._gather_fn = gather_fn
        self._settings = settings
        self._producer = producer or EventProducer(settings.kafka_bootstrap)
        self._consumer = consumer or EventConsumer(
            settings.kafka_bootstrap,
            f"{agent_name.value}-agents",
            [TXN_EVALUATE],
        )
        self._compiled = compiled if compiled is not None else build_agent_graph()
        self._running = False

    @property
    def running(self) -> bool:
        """Whether the consume loop is active (drives the health app readiness)."""
        return self._running

    def run_once(self, envelope: EventEnvelope) -> Verdict:
        """Score one evaluate request and publish its ``agent.verdict.produced`` (docs/02 §6).

        Runs the uniform per-agent graph, builds the ``AgentVerdictProducedPayload``, and
        publishes an ``agent.verdict.produced`` envelope to ``agent.verdicts`` keyed by
        ``transaction_id``. Returns the produced verdict. Does NOT commit — the loop
        commits after this returns so the offset only advances once the publish landed.
        """
        bind_trace_id(envelope.trace_id)
        try:
            result = run_agent_graph(
                compiled=self._compiled,
                agent_name=self.agent_name.value,
                score_fn=self._score_fn,
                settings=self._settings,
                payload=envelope.payload,
                trace_id=envelope.trace_id,
                gather_fn=self._gather_fn,
            )
            verdict = result.verdict
            payload = AgentVerdictProducedPayload(
                agent=self.agent_name,
                produced_at=datetime.now(tz=UTC),
                verdict=verdict,
            )
            out = EventEnvelope(
                event_id=f"evt_{uuid.uuid4().hex}",
                event_type=EventType.AGENT_VERDICT_PRODUCED,
                transaction_id=envelope.transaction_id,
                trace_id=envelope.trace_id,
                occurred_at=datetime.now(tz=UTC),
                producer=f"{self.agent_name.value}-agent",
                payload=payload.model_dump(mode="json"),
            )
            self._producer.publish(topic_for(EventType.AGENT_VERDICT_PRODUCED), out)
            self._producer.flush(timeout=5.0)
            _log.info(
                "verdict produced",
                extra={
                    "transaction_id": envelope.transaction_id,
                    "agent": self.agent_name.value,
                    "decision_hint": verdict.decision_hint.value,
                    "degraded": verdict.degraded,
                },
            )
            return verdict
        finally:
            bind_trace_id(None)

    def consume_forever(self, poll_timeout: float = 1.0) -> None:
        """Run the commit-after-publish loop over ``txn.evaluate`` (docs/02 §6).

        Filters to ``txn.evaluate.requested`` envelopes, runs :meth:`run_once` to publish
        the verdict, then commits the consumer offset AFTER the publish. The commit only
        runs on a successful publish, so a failure replays the request on restart.
        """
        self._running = True
        try:
            for envelope in self._consumer.stream(poll_timeout):
                if envelope.event_type != EventType.TXN_EVALUATE_REQUESTED:
                    continue
                try:
                    self.run_once(envelope)
                except Exception as exc:
                    # Do NOT commit on failure: the offset stays so the request replays.
                    _log.warning(
                        "verdict production failed; not committing offset",
                        extra={
                            "transaction_id": envelope.transaction_id,
                            "agent": self.agent_name.value,
                            "error": str(exc),
                        },
                    )
                    continue
                # Commit AFTER a successful publish (docs/02 §6).
                self._consumer.commit()
        finally:
            self._running = False

    def close(self) -> None:
        """Close the consumer and leave the group cleanly."""
        self._consumer.close()


__all__ = ["AgentRunner"]
