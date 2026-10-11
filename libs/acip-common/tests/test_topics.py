"""Topic-catalog tests: event-type routing (docs/03 §2) and name parity with compose."""

from __future__ import annotations

from acip_common import topics
from acip_common.schemas import EventType
from acip_common.topics import topic_for


def test_topic_for_covers_every_event_type() -> None:
    expected = {
        EventType.TXN_CREATED: topics.TXN_LIFECYCLE,
        EventType.TXN_EXECUTED: topics.TXN_LIFECYCLE,
        EventType.TXN_DECLINED: topics.TXN_LIFECYCLE,
        EventType.TXN_CHALLENGED: topics.TXN_LIFECYCLE,
        EventType.TXN_EVALUATE_REQUESTED: topics.TXN_EVALUATE,
        EventType.AGENT_VERDICT_PRODUCED: topics.AGENT_VERDICTS,
        EventType.DECISION_RENDERED: topics.DECISION_LOG,
    }
    # Every EventType member is routed (no KeyError) and lands on the expected topic.
    for event_type in EventType:
        assert topic_for(event_type) == expected[event_type]


def test_constants_match_kafka_init_names() -> None:
    # Must equal the names created by deploy/docker-compose.yml kafka-init.
    assert topics.TXN_LIFECYCLE == "txn.lifecycle"
    assert topics.TXN_EVALUATE == "txn.evaluate"
    assert topics.AGENT_VERDICTS == "agent.verdicts"
    assert topics.DECISION_LOG == "decision.log"
    assert topics.TXN_LIFECYCLE_DLQ == "txn.lifecycle.dlq"
    assert topics.TXN_EVALUATE_DLQ == "txn.evaluate.dlq"
    assert topics.AGENT_VERDICTS_DLQ == "agent.verdicts.dlq"
    assert topics.DECISION_LOG_DLQ == "decision.log.dlq"
