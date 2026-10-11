"""Tests for the graph-projector (docs/03 §3-4, docs/01 §6).

Kafka (EventConsumer), Postgres (psycopg) and Neo4j (the neo4j driver) are mocked, so the
suite runs with no broker and no stores. The four contracts FEAT-003 calls out are
asserted:

* **routing** — each ``event_type`` reaches the right projector method / table / node:
  TXN_CREATED -> ``transactions`` + ``Customer``/``Transaction``; AGENT_VERDICT_PRODUCED
  -> ``agent_verdicts``; DECISION_RENDERED -> ``decisions`` + ``DecisionEvent``; a terminal
  event -> a ``transactions`` status update; and every event -> one ``event_journal`` row;
* **idempotency** — Postgres writes use ``ON CONFLICT`` and Neo4j uses ``MERGE``, and
  applying the same envelope twice leaves a single row / single node in the fake stores;
* **commit-after-project** — the consumer commits only AFTER both projectors ran;
* **degradation** — a store outage is swallowed (logged) and the loop keeps consuming.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from graph_projector.consumer import SOURCE_TOPICS, ProjectorConsumer
from graph_projector.neo4j_projector import Neo4jProjector
from graph_projector.postgres_projector import PostgresProjector

from acip_common.schemas import (
    AgentName,
    AgentVerdictProducedPayload,
    CheckoutContext,
    DecisionHint,
    DecisionRenderedPayload,
    EventEnvelope,
    EventType,
    MethodType,
    PaymentMethodRef,
    TxnCreatedPayload,
    TxnTerminalPayload,
    Verdict,
)
from acip_common.topics import AGENT_VERDICTS, DECISION_LOG, TXN_LIFECYCLE


# --------------------------------------------------------------------------- #
# Envelope builders
# --------------------------------------------------------------------------- #
def _envelope(event_type: EventType, payload: dict[str, Any], *, event_id: str) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        transaction_id="txn_1",
        trace_id="trace_1",
        occurred_at=datetime(2024, 1, 1, tzinfo=UTC),
        producer="test",
        payload=payload,
    )


def _created(event_id: str = "evt_created", *, fingerprint: str | None = "dev_1") -> EventEnvelope:
    payload = TxnCreatedPayload(
        merchant_id="mer_1",
        customer_id="cus_1",
        amount=120.0,
        currency="INR",
        payment_method=PaymentMethodRef(type=MethodType.UPI),
        context=CheckoutContext(device_fingerprint=fingerprint),
    )
    return _envelope(EventType.TXN_CREATED, payload.model_dump(mode="json"), event_id=event_id)


def _verdict(event_id: str = "evt_verdict") -> EventEnvelope:
    payload = AgentVerdictProducedPayload(
        agent=AgentName.RISK,
        produced_at=datetime(2024, 1, 1, tzinfo=UTC),
        verdict=Verdict(
            decision_hint=DecisionHint.APPROVE,
            score=0.1,
            confidence=0.9,
            rationale="low risk",
            model_version="risk-1",
        ),
    )
    return _envelope(
        EventType.AGENT_VERDICT_PRODUCED, payload.model_dump(mode="json"), event_id=event_id
    )


def _decision(
    event_id: str = "evt_decision", *, route: str | None = "processor_a"
) -> EventEnvelope:
    payload = DecisionRenderedPayload(
        decision=DecisionHint.APPROVE,
        composite_score=0.2,
        strategy="weighted_veto",
        route=route,
        explanation="approved",
    )
    return _envelope(
        EventType.DECISION_RENDERED, payload.model_dump(mode="json"), event_id=event_id
    )


def _terminal(event_id: str = "evt_terminal") -> EventEnvelope:
    payload = TxnTerminalPayload(
        decision=DecisionHint.APPROVE,
        route="processor_a",
        composite_score=0.2,
        decided_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    return _envelope(EventType.TXN_EXECUTED, payload.model_dump(mode="json"), event_id=event_id)


# --------------------------------------------------------------------------- #
# Fake Postgres (psycopg) — a tiny in-memory store honoring ON CONFLICT semantics
# --------------------------------------------------------------------------- #
class _FakeCursor:
    def __init__(self, store: dict[str, dict[Any, dict[str, Any]]], sql_log: list[str]) -> None:
        self._store = store
        self._sql_log = sql_log

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self._sql_log.append(sql)
        normalized = " ".join(sql.split())
        table = _table_of(normalized)
        if normalized.startswith("INSERT INTO event_journal"):
            # ON CONFLICT (event_id) DO NOTHING — keyed by event_id (params[0]).
            self._store.setdefault("event_journal", {}).setdefault(
                params[0], {"event_type": params[2]}
            )
        elif normalized.startswith("INSERT INTO transactions"):
            # ON CONFLICT (id) DO UPDATE — keyed by id (params[0]).
            self._store.setdefault("transactions", {})[params[0]] = {
                "customer_id": params[1],
                "amount": params[2],
                "status": params[3],
                "decision": params[4],
            }
        elif normalized.startswith("INSERT INTO decisions"):
            self._store.setdefault("decisions", {})[params[0]] = {
                "decision": params[1],
                "composite_score": params[2],
                "strategy": params[3],
            }
        elif normalized.startswith("INSERT INTO agent_verdicts"):
            # ON CONFLICT (transaction_id, agent) DO UPDATE — composite key.
            self._store.setdefault("agent_verdicts", {})[(params[0], params[1])] = {
                "score": params[2],
                "decision_hint": params[3],
            }
        elif normalized.startswith("UPDATE transactions"):
            # UPDATE ... WHERE id = <last param>.
            txn = self._store.setdefault("transactions", {}).setdefault(params[-1], {})
            if "status = %s, decision = %s" in normalized:
                txn["status"] = params[0]
                txn["decision"] = params[1]
            else:  # decision = %s, status = %s
                txn["decision"] = params[0]
                txn["status"] = params[1]
        elif table == "unknown":  # pragma: no cover - guard
            raise AssertionError(f"unexpected SQL: {normalized}")


def _table_of(sql: str) -> str:
    match = re.match(r"(?:INSERT INTO|UPDATE)\s+(\w+)", sql)
    return match.group(1) if match else "unknown"


class _FakeConn:
    def __init__(self, store: dict[str, dict[Any, dict[str, Any]]], sql_log: list[str]) -> None:
        self._store = store
        self._sql_log = sql_log

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._store, self._sql_log)


class _FakePsycopg:
    """A stand-in for the ``psycopg`` module whose ``connect`` returns a fake connection."""

    def __init__(self, store: dict[str, dict[Any, dict[str, Any]]], sql_log: list[str]) -> None:
        self._store = store
        self._sql_log = sql_log
        self.connect_calls = 0

    def connect(self, dsn: str, connect_timeout: int = 5) -> _FakeConn:
        self.connect_calls += 1
        return _FakeConn(self._store, self._sql_log)


def _patch_psycopg(monkeypatch: Any, fake: _FakePsycopg) -> None:
    import builtins

    real_import = builtins.__import__

    def _fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "psycopg":
            return fake
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)


# --------------------------------------------------------------------------- #
# Fake Neo4j driver — records Cypher and merges nodes by id
# --------------------------------------------------------------------------- #
class _FakeSession:
    def __init__(self, cypher_log: list[str], nodes: dict[str, set[str]]) -> None:
        self._cypher_log = cypher_log
        self._nodes = nodes

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def run(self, cypher: str, **params: Any) -> None:
        self._cypher_log.append(cypher)
        for label, key in (
            ("Customer", "customer_id"),
            ("Transaction", "transaction_id"),
            ("Device", "device_id"),
            ("DecisionEvent", "event_id"),
            ("Processor", "route"),
        ):
            if f"({label[0].lower()}" in cypher and f":{label} " in cypher and key in params:
                self._nodes.setdefault(label, set()).add(params[key])


class _FakeDriver:
    def __init__(self, cypher_log: list[str], nodes: dict[str, set[str]]) -> None:
        self._cypher_log = cypher_log
        self._nodes = nodes

    def session(self) -> _FakeSession:
        return _FakeSession(self._cypher_log, self._nodes)

    def close(self) -> None:
        return None


def _neo4j_projector(cypher_log: list[str], nodes: dict[str, set[str]]) -> Neo4jProjector:
    projector = Neo4jProjector("bolt://neo4j:7687", "neo4j/password")
    projector._driver = _FakeDriver(cypher_log, nodes)  # inject the fake driver
    return projector


# --------------------------------------------------------------------------- #
# Fake Kafka consumer — streams a fixed list once; records commit ordering
# --------------------------------------------------------------------------- #
class _ReplayConsumer:
    def __init__(self, envelopes: list[EventEnvelope], events: list[str]) -> None:
        self._envelopes = envelopes
        self._events = events
        self.commits = 0

    def stream(self, timeout: float = 1.0) -> Any:
        yield from self._envelopes

    def commit(self) -> None:
        self.commits += 1
        self._events.append("commit")

    def close(self) -> None:
        return None


# --------------------------------------------------------------------------- #
# Postgres routing + journaling
# --------------------------------------------------------------------------- #
def test_postgres_routes_each_event_type_and_journals(monkeypatch: Any) -> None:
    store: dict[str, dict[Any, dict[str, Any]]] = {}
    sql_log: list[str] = []
    fake = _FakePsycopg(store, sql_log)
    _patch_psycopg(monkeypatch, fake)
    projector = PostgresProjector("postgresql://x")

    projector.project(_created())
    projector.project(_verdict())
    projector.project(_decision())
    projector.project(_terminal())

    # TXN_CREATED -> transactions row (status CREATED).
    assert store["transactions"]["txn_1"]["customer_id"] == "cus_1"
    # AGENT_VERDICT_PRODUCED -> agent_verdicts row keyed by (txn, agent).
    assert store["agent_verdicts"][("txn_1", "risk")]["decision_hint"] == "APPROVE"
    # DECISION_RENDERED -> decisions row + transaction decision/status updated.
    assert store["decisions"]["txn_1"]["strategy"] == "weighted_veto"
    # terminal TXN_EXECUTED -> transactions status EXECUTED.
    assert store["transactions"]["txn_1"]["status"] == "EXECUTED"
    # Every event journaled, keyed by event_id.
    assert set(store["event_journal"]) == {
        "evt_created",
        "evt_verdict",
        "evt_decision",
        "evt_terminal",
    }
    # Idempotent SQL shape: journal uses ON CONFLICT DO NOTHING; upserts use DO UPDATE.
    joined = " ".join(" ".join(s.split()) for s in sql_log)
    assert "ON CONFLICT (event_id) DO NOTHING" in joined
    assert "ON CONFLICT (id) DO UPDATE" in joined
    assert "ON CONFLICT (transaction_id) DO UPDATE" in joined
    assert "ON CONFLICT (transaction_id, agent) DO UPDATE" in joined


def test_postgres_idempotent_on_replay(monkeypatch: Any) -> None:
    store: dict[str, dict[Any, dict[str, Any]]] = {}
    sql_log: list[str] = []
    _patch_psycopg(monkeypatch, _FakePsycopg(store, sql_log))
    projector = PostgresProjector("postgresql://x")

    # Apply the exact same envelope twice.
    projector.project(_verdict())
    projector.project(_verdict())

    # ON CONFLICT upserts collapse to a single row and a single journal entry.
    assert len(store["agent_verdicts"]) == 1
    assert len(store["event_journal"]) == 1


# --------------------------------------------------------------------------- #
# Neo4j routing + idempotency
# --------------------------------------------------------------------------- #
def test_neo4j_created_merges_customer_transaction_device() -> None:
    cypher_log: list[str] = []
    nodes: dict[str, set[str]] = {}
    projector = _neo4j_projector(cypher_log, nodes)

    projector.project(_created())

    joined = " ".join(cypher_log)
    assert "MERGE (c:Customer {id: $customer_id})" in joined
    assert "MERGE (t:Transaction {id: $transaction_id})" in joined
    assert "MERGE (c)-[:PLACED]->(t)" in joined
    assert "MERGE (d:Device {id: $device_id})" in joined
    assert "MERGE (t)-[:FROM_DEVICE]->(d)" in joined
    assert "MERGE (d)-[:LINKED_TO]->(c)" in joined
    assert nodes["Customer"] == {"cus_1"}
    assert nodes["Transaction"] == {"txn_1"}
    assert nodes["Device"] == {"dev_1"}


def test_neo4j_created_without_device_skips_device_merge() -> None:
    cypher_log: list[str] = []
    nodes: dict[str, set[str]] = {}
    projector = _neo4j_projector(cypher_log, nodes)

    projector.project(_created(fingerprint=None))

    assert "Device" not in nodes
    assert all(":Device" not in c for c in cypher_log)


def test_neo4j_decision_merges_decision_event_and_route() -> None:
    cypher_log: list[str] = []
    nodes: dict[str, set[str]] = {}
    projector = _neo4j_projector(cypher_log, nodes)

    projector.project(_decision())

    joined = " ".join(cypher_log)
    assert "MERGE (de:DecisionEvent {id: $event_id})" in joined
    assert "MERGE (t)-[:HAS_DECISION]->(de)" in joined
    assert "MERGE (p:Processor {id: $route})" in joined
    assert "MERGE (t)-[:ROUTED_TO]->(p)" in joined
    assert nodes["DecisionEvent"] == {"evt_decision"}
    assert nodes["Processor"] == {"processor_a"}


def test_neo4j_idempotent_on_replay() -> None:
    cypher_log: list[str] = []
    nodes: dict[str, set[str]] = {}
    projector = _neo4j_projector(cypher_log, nodes)

    projector.project(_created())
    projector.project(_created())

    # MERGE keyed by id -> replay yields a single node per key (no duplicates).
    assert nodes["Transaction"] == {"txn_1"}
    assert nodes["Customer"] == {"cus_1"}
    assert nodes["Device"] == {"dev_1"}


def test_neo4j_non_graph_event_is_a_no_op() -> None:
    cypher_log: list[str] = []
    nodes: dict[str, set[str]] = {}
    projector = _neo4j_projector(cypher_log, nodes)

    projector.project(_verdict())  # verdicts are Postgres-only

    assert cypher_log == []
    assert nodes == {}


# --------------------------------------------------------------------------- #
# Consumer: subscriptions, commit-after-project, degradation
# --------------------------------------------------------------------------- #
def test_consumer_subscribes_to_all_three_source_topics() -> None:
    assert SOURCE_TOPICS == [TXN_LIFECYCLE, AGENT_VERDICTS, DECISION_LOG]


def test_consumer_commits_after_project(monkeypatch: Any) -> None:
    store: dict[str, dict[Any, dict[str, Any]]] = {}
    sql_log: list[str] = []
    _patch_psycopg(monkeypatch, _FakePsycopg(store, sql_log))
    events: list[str] = []

    class _OrderPostgres(PostgresProjector):
        def project(self, envelope: EventEnvelope) -> None:
            super().project(envelope)
            events.append("project")

    postgres = _OrderPostgres("postgresql://x")
    neo4j = _neo4j_projector([], {})
    consumer = _ReplayConsumer([_created()], events)
    projector_consumer = ProjectorConsumer(
        "redpanda:9092", postgres, neo4j, consumer=consumer  # type: ignore[arg-type]
    )

    projector_consumer.consume_forever()

    # The project happens BEFORE the commit (docs/01 §6).
    assert events == ["project", "commit"]
    assert consumer.commits == 1


def test_store_outage_is_swallowed_and_loop_continues(monkeypatch: Any) -> None:
    """A Postgres connect failure degrades (logged) without crashing the consume loop."""

    class _FailingPsycopg:
        def connect(self, dsn: str, connect_timeout: int = 5) -> Any:
            raise RuntimeError("postgres down")

    _patch_psycopg(monkeypatch, _FailingPsycopg())  # type: ignore[arg-type]

    class _FailingDriver:
        def session(self) -> Any:
            raise RuntimeError("neo4j down")

        def close(self) -> None:
            return None

    events: list[str] = []
    postgres = PostgresProjector("postgresql://x")
    neo4j = Neo4jProjector("bolt://neo4j:7687", "neo4j/password")
    neo4j._driver = _FailingDriver()  # inject a driver whose session() raises
    # Two events: if the first outage crashed the loop, the second would never commit.
    consumer = _ReplayConsumer([_created(), _verdict()], events)
    projector_consumer = ProjectorConsumer(
        "redpanda:9092", postgres, neo4j, consumer=consumer  # type: ignore[arg-type]
    )

    projector_consumer.consume_forever()

    # Both events were consumed and committed despite both stores being down.
    assert consumer.commits == 2
    assert events == ["commit", "commit"]
