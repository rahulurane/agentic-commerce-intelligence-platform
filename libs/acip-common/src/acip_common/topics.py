"""Kafka topic catalog and event-type -> topic mapping (docs/03 §2).

Topic names are NOT the dotted event-type strings: several event types share a
single topic. docs/03 §2 defines the catalog below and ``topic_for`` resolves an
``acip_common.schemas.EventType`` to the topic it is published on. The DLQ names
mirror the ``kafka-init`` topic creation in ``deploy/docker-compose.yml``.
"""

from __future__ import annotations

from acip_common.schemas import EventType

# --- topics (docs/03 §2) ---
TXN_LIFECYCLE = "txn.lifecycle"
TXN_EVALUATE = "txn.evaluate"
AGENT_VERDICTS = "agent.verdicts"
DECISION_LOG = "decision.log"

# --- dead-letter queues (deploy/docker-compose.yml kafka-init) ---
TXN_LIFECYCLE_DLQ = "txn.lifecycle.dlq"
TXN_EVALUATE_DLQ = "txn.evaluate.dlq"
AGENT_VERDICTS_DLQ = "agent.verdicts.dlq"
DECISION_LOG_DLQ = "decision.log.dlq"

# Event-type -> topic routing (docs/03 §2). The txn lifecycle events
# (created/executed/declined/challenged) all land on txn.lifecycle.
_EVENT_TOPIC: dict[EventType, str] = {
    EventType.TXN_CREATED: TXN_LIFECYCLE,
    EventType.TXN_EXECUTED: TXN_LIFECYCLE,
    EventType.TXN_DECLINED: TXN_LIFECYCLE,
    EventType.TXN_CHALLENGED: TXN_LIFECYCLE,
    EventType.TXN_EVALUATE_REQUESTED: TXN_EVALUATE,
    EventType.AGENT_VERDICT_PRODUCED: AGENT_VERDICTS,
    EventType.DECISION_RENDERED: DECISION_LOG,
}


def topic_for(event_type: EventType) -> str:
    """Return the Kafka topic an ``event_type`` is published on (docs/03 §2)."""
    return _EVENT_TOPIC[event_type]


__all__ = [
    "AGENT_VERDICTS",
    "AGENT_VERDICTS_DLQ",
    "DECISION_LOG",
    "DECISION_LOG_DLQ",
    "TXN_EVALUATE",
    "TXN_EVALUATE_DLQ",
    "TXN_LIFECYCLE",
    "TXN_LIFECYCLE_DLQ",
    "topic_for",
]
