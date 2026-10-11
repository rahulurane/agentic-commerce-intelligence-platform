"""The graph-projector Kafka loop: consume lifecycle/verdict/decision, project (docs/01 §6).

:class:`ProjectorConsumer` runs one :class:`acip_common.kafka.EventConsumer` subscribed to
``txn.lifecycle`` + ``agent.verdicts`` + ``decision.log`` in the ``graph-projector``
consumer group. For each decoded ``EventEnvelope`` it binds the trace id, projects into
both Neo4j (docs/03 §3) and Postgres (docs/03 §4), then commits the consumer offset ONLY
AFTER a successful project. Commit-after-project gives at-least-once delivery: a crash
between project and commit replays the event and re-applies the (idempotent) upserts
rather than dropping it, so no event is lost and none is double-counted (docs/01 §6).

Store outages degrade rather than crash: each projector swallows and logs its own store
errors, so the loop keeps consuming. The consumer/projectors are injected so tests drive
the loop with mocked Kafka/Neo4j/Postgres; nothing here opens a broker at import time.
"""

from __future__ import annotations

import logging

from acip_common.kafka import EventConsumer
from acip_common.logging import bind_trace_id
from acip_common.topics import AGENT_VERDICTS, DECISION_LOG, TXN_LIFECYCLE
from graph_projector.neo4j_projector import Neo4jProjector
from graph_projector.postgres_projector import PostgresProjector

_log = logging.getLogger("graph_projector.consumer")

# The one consumer group that owns projection; all three source topics on one consumer.
CONSUMER_GROUP = "graph-projector"
SOURCE_TOPICS = [TXN_LIFECYCLE, AGENT_VERDICTS, DECISION_LOG]


class ProjectorConsumer:
    """Consume lifecycle/verdict/decision events and project them, commit after (docs/01 §6)."""

    def __init__(
        self,
        settings_kafka_bootstrap: str,
        postgres_projector: PostgresProjector,
        neo4j_projector: Neo4jProjector,
        *,
        consumer: EventConsumer | None = None,
    ) -> None:
        self._postgres = postgres_projector
        self._neo4j = neo4j_projector
        self._consumer = consumer or EventConsumer(
            settings_kafka_bootstrap,
            CONSUMER_GROUP,
            SOURCE_TOPICS,
        )
        self._running = False

    @property
    def running(self) -> bool:
        """Whether the consume loop is active (drives the health app readiness)."""
        return self._running

    @property
    def postgres(self) -> PostgresProjector:
        """The Postgres projector (the schema owner the lifespan bootstraps; fix A.1)."""
        return self._postgres

    def consume_forever(self, poll_timeout: float = 1.0) -> None:
        """Run the commit-after-project loop over the three source topics (docs/01 §6).

        For each envelope: bind the trace id, project to Postgres and Neo4j (both
        best-effort), then commit the offset AFTER the project. The projectors swallow
        their own store errors, so a store outage degrades without crashing the loop.
        """
        self._running = True
        try:
            for envelope in self._consumer.stream(poll_timeout):
                bind_trace_id(envelope.trace_id)
                try:
                    self._postgres.project(envelope)
                    self._neo4j.project(envelope)
                    _log.info(
                        "event projected",
                        extra={
                            "transaction_id": envelope.transaction_id,
                            "event_id": envelope.event_id,
                            "event_type": envelope.event_type.value,
                        },
                    )
                finally:
                    bind_trace_id(None)
                # Commit AFTER a successful project (docs/01 §6).
                self._consumer.commit()
        finally:
            self._running = False

    def close(self) -> None:
        """Close the consumer and the Neo4j driver cleanly."""
        self._consumer.close()
        self._neo4j.close()


__all__ = ["CONSUMER_GROUP", "SOURCE_TOPICS", "ProjectorConsumer"]
