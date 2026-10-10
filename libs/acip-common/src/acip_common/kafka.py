"""Kafka client wrappers over confluent-kafka, targeting the Redpanda Kafka API.

Why confluent-kafka over aiokafka (plan key decision; docs/01 §2, docs/07 §1):
confluent-kafka is librdkafka-backed, the most widely deployed Kafka client, works
unchanged against Redpanda's Kafka API, and exposes production-grade delivery
semantics — an idempotent producer and manual offset commit — which we need for the
"commit the consumer offset only after the verdict is published" rule in docs/02 §6.
aiokafka is async-native but pure-Python and less battle-tested for that exactly-once
producer posture, so it does not fit the production-shaped stance as well.

Events are (de)serialized through the ``acip_common.schemas.EventEnvelope`` so the
wire format is the versioned JSON envelope from docs/03 §1, keyed by ``transaction_id``
so all events for a transaction land on one partition and keep order (docs/01 §6).

Importing this module does not open a broker connection — producers/consumers connect
lazily when first used, so services and tests import it without a running broker.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from acip_common.schemas import EventEnvelope

if TYPE_CHECKING:  # pragma: no cover - typing only
    from confluent_kafka import Message


def _producer_config(bootstrap: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an idempotent, ordered producer config (docs/02 §6)."""
    config: dict[str, Any] = {
        "bootstrap.servers": bootstrap,
        "enable.idempotence": True,
        "acks": "all",
        "max.in.flight.requests.per.connection": 5,
        "retries": 10,
    }
    if extra:
        config.update(extra)
    return config


def _consumer_config(
    bootstrap: str, group_id: str, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a manual-commit consumer config (commit after publish; docs/02 §6)."""
    config: dict[str, Any] = {
        "bootstrap.servers": bootstrap,
        "group.id": group_id,
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    }
    if extra:
        config.update(extra)
    return config


class EventProducer:
    """Thin idempotent producer that publishes ``EventEnvelope`` values.

    Keyed by ``transaction_id`` for per-transaction ordering (docs/01 §6).
    """

    def __init__(self, bootstrap: str, extra: dict[str, Any] | None = None) -> None:
        self._config = _producer_config(bootstrap, extra)
        self._producer: Any = None

    def _ensure(self) -> Any:
        if self._producer is None:
            from confluent_kafka import Producer

            self._producer = Producer(self._config)
        return self._producer

    def publish(self, topic: str, envelope: EventEnvelope) -> None:
        """Serialize and publish ``envelope`` to ``topic``, keyed by transaction id."""
        producer = self._ensure()
        producer.produce(
            topic=topic,
            key=envelope.transaction_id.encode("utf-8"),
            value=envelope.model_dump_json().encode("utf-8"),
        )
        producer.poll(0)

    def flush(self, timeout: float = 10.0) -> int:
        """Block until outstanding messages are delivered; returns remaining count."""
        return int(self._ensure().flush(timeout))


class EventConsumer:
    """Thin manual-commit consumer that yields decoded ``EventEnvelope`` values.

    Callers commit via :meth:`commit` only after they have published any downstream
    event, giving the at-least-once / commit-after-publish behavior in docs/02 §6.
    """

    def __init__(
        self,
        bootstrap: str,
        group_id: str,
        topics: list[str],
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._config = _consumer_config(bootstrap, group_id, extra)
        self._topics = topics
        self._consumer: Any = None

    def _ensure(self) -> Any:
        if self._consumer is None:
            from confluent_kafka import Consumer

            self._consumer = Consumer(self._config)
            self._consumer.subscribe(self._topics)
        return self._consumer

    def poll(self, timeout: float = 1.0) -> EventEnvelope | None:
        """Poll once; return a decoded envelope, or ``None`` on timeout.

        Raises :class:`confluent_kafka.KafkaException` on a broker-level error.
        """
        from confluent_kafka import KafkaException

        msg: Message | None = self._ensure().poll(timeout)
        if msg is None:
            return None
        if msg.error():
            raise KafkaException(msg.error())
        value = msg.value()
        if value is None:
            return None
        return EventEnvelope.model_validate_json(value)

    def stream(self, timeout: float = 1.0) -> Iterator[EventEnvelope]:
        """Yield decoded envelopes indefinitely (skipping idle polls)."""
        while True:
            envelope = self.poll(timeout)
            if envelope is not None:
                yield envelope

    def commit(self) -> None:
        """Commit current offsets (call only after downstream publish)."""
        self._ensure().commit(asynchronous=False)

    def close(self) -> None:
        """Close the consumer and leave the group cleanly."""
        if self._consumer is not None:
            self._consumer.close()


__all__ = ["EventConsumer", "EventProducer"]
