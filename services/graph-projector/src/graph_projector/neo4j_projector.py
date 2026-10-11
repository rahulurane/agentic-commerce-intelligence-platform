"""Neo4j graph projection (docs/03 §3 node labels + relationships).

:class:`Neo4jProjector` turns each inbound ``EventEnvelope`` into idempotent ``MERGE``
upserts against the transaction-intelligence graph (docs/03 §3). All node/edge keys are
ids, so replaying an event re-``MERGE``s the same node/edge rather than creating a
duplicate (docs/01 §6):

* TXN_CREATED -> ``MERGE (c:Customer {id})``, ``MERGE (t:Transaction {id})`` with its
  amount/currency/status/method_type, and ``MERGE (c)-[:PLACED]->(t)``. When the payload
  context carries a device fingerprint it also ``MERGE``s the ``Device`` node, the
  ``(t)-[:FROM_DEVICE]->(d)`` edge, and the ``(d)-[:LINKED_TO]->(c)`` edge.
* DECISION_RENDERED -> ``MERGE (de:DecisionEvent {id: event_id})`` with its decision/score
  /at and ``MERGE (t)-[:HAS_DECISION]->(de)``; when a chosen route is present it also
  ``MERGE``s the ``Processor`` node and ``(t)-[:ROUTED_TO]->(p)``.

The driver opens lazily and the projector is degradation-tolerant: a connect/read failure
is logged and skipped so a Neo4j outage degrades the stack rather than crashing the
consumer loop (docs/03 §8). Importing this module needs no running Neo4j.
"""

from __future__ import annotations

import logging
from typing import Any

from acip_common.schemas import (
    DecisionRenderedPayload,
    EventEnvelope,
    EventType,
    TxnCreatedPayload,
)

_log = logging.getLogger("graph_projector.neo4j_projector")


def _parse_neo4j_auth(auth: str) -> tuple[str, str]:
    """Split ``NEO4J_AUTH`` (``user/password``) into a tuple (matches scripts/seed.py)."""
    user, _, password = auth.partition("/")
    return user, password


class Neo4jProjector:
    """Project events into the Neo4j graph with idempotent ``MERGE`` upserts (docs/03 §3)."""

    def __init__(self, neo4j_uri: str, neo4j_auth: str) -> None:
        self._uri = neo4j_uri
        self._auth = _parse_neo4j_auth(neo4j_auth)
        self._driver: Any = None

    def _ensure_driver(self) -> Any:
        """Open the driver lazily; return ``None`` (logged) if Neo4j is unreachable."""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase

                self._driver = GraphDatabase.driver(self._uri, auth=self._auth)
            except Exception as exc:
                _log.warning(
                    "neo4j driver unavailable; skipping graph projection",
                    extra={"error": str(exc)},
                )
                return None
        return self._driver

    def project(self, envelope: EventEnvelope) -> None:
        """Project one envelope into the graph (best-effort; a store error is logged + skipped)."""
        event_type = envelope.event_type
        if event_type is EventType.TXN_CREATED:
            statements = self._created_statements(envelope)
        elif event_type is EventType.DECISION_RENDERED:
            statements = self._decision_statements(envelope)
        else:
            return

        driver = self._ensure_driver()
        if driver is None:
            return
        try:
            with driver.session() as session:
                for cypher, params in statements:
                    session.run(cypher, **params)
        except Exception as exc:
            _log.warning(
                "neo4j projection failed; continuing degraded",
                extra={
                    "transaction_id": envelope.transaction_id,
                    "event_id": envelope.event_id,
                    "event_type": event_type.value,
                    "error": str(exc),
                },
            )

    def _created_statements(self, envelope: EventEnvelope) -> list[tuple[str, dict[str, Any]]]:
        """Build TXN_CREATED MERGEs: Customer/Transaction/PLACED plus an optional Device."""
        payload = TxnCreatedPayload.model_validate(envelope.payload)
        statements: list[tuple[str, dict[str, Any]]] = [
            (
                """
                MERGE (c:Customer {id: $customer_id})
                MERGE (t:Transaction {id: $transaction_id})
                  SET t.amount = $amount,
                      t.currency = $currency,
                      t.status = $status,
                      t.method_type = $method_type
                MERGE (c)-[:PLACED]->(t)
                """,
                {
                    "customer_id": payload.customer_id,
                    "transaction_id": envelope.transaction_id,
                    "amount": payload.amount,
                    "currency": payload.currency,
                    "status": "CREATED",
                    "method_type": payload.payment_method.type.value,
                },
            )
        ]
        fingerprint = payload.context.device_fingerprint
        if fingerprint:
            statements.append(
                (
                    """
                    MATCH (t:Transaction {id: $transaction_id})
                    MATCH (c:Customer {id: $customer_id})
                    MERGE (d:Device {id: $device_id})
                    MERGE (t)-[:FROM_DEVICE]->(d)
                    MERGE (d)-[:LINKED_TO]->(c)
                    """,
                    {
                        "transaction_id": envelope.transaction_id,
                        "customer_id": payload.customer_id,
                        "device_id": fingerprint,
                    },
                )
            )
        return statements

    def _decision_statements(self, envelope: EventEnvelope) -> list[tuple[str, dict[str, Any]]]:
        """Build DECISION_RENDERED MERGEs: a DecisionEvent plus an optional Processor route."""
        payload = DecisionRenderedPayload.model_validate(envelope.payload)
        statements: list[tuple[str, dict[str, Any]]] = [
            (
                """
                MERGE (t:Transaction {id: $transaction_id})
                MERGE (de:DecisionEvent {id: $event_id})
                  SET de.decision = $decision,
                      de.score = $score,
                      de.at = $at
                MERGE (t)-[:HAS_DECISION]->(de)
                """,
                {
                    "transaction_id": envelope.transaction_id,
                    "event_id": envelope.event_id,
                    "decision": payload.decision.value,
                    "score": payload.composite_score,
                    "at": envelope.occurred_at.isoformat(),
                },
            )
        ]
        if payload.route:
            statements.append(
                (
                    """
                    MATCH (t:Transaction {id: $transaction_id})
                    MERGE (p:Processor {id: $route})
                    MERGE (t)-[:ROUTED_TO]->(p)
                    """,
                    {
                        "transaction_id": envelope.transaction_id,
                        "route": payload.route,
                    },
                )
            )
        return statements

    def close(self) -> None:
        """Close the driver if it was opened."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None


__all__ = ["Neo4jProjector"]
