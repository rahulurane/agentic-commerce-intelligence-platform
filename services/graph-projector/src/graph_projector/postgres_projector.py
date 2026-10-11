"""Postgres read-model projection (docs/03 §4, scripts/seed.py table shapes).

:class:`PostgresProjector` turns each inbound ``EventEnvelope`` into idempotent upserts
against the four read-model tables whose shapes are defined in ``scripts/seed.py`` and
mirrored by ``acip_common.bootstrap.ensure_read_model_schema`` (docs/03 §4):

* ``transactions(id PK, customer_id, amount, status, decision, created_at)``
* ``decisions(transaction_id PK, decision, composite_score, strategy)``
* ``agent_verdicts(transaction_id, agent, score, decision_hint, PK(transaction_id, agent))``
* ``event_journal(event_id PK, transaction_id, event_type, occurred_at)``

Every envelope writes one ``event_journal`` row keyed by ``event_id`` with
``ON CONFLICT DO NOTHING`` (idempotent by event id). Each event type additionally upserts
the row(s) it carries with ``ON CONFLICT ... DO UPDATE`` keyed by primary key, so
replaying an event produces no duplicate rows (docs/01 §6).

The projector OWNS runtime read-model population: :meth:`ensure_schema` calls
``acip_common.bootstrap.ensure_read_model_schema`` (the always-on side of fix A.1) so a
fresh stack with no seed still has the tables. Writes are best-effort: a Postgres outage
is logged and swallowed so the consumer loop degrades rather than crashing (docs/03 §8).
The ``psycopg`` import is lazy so importing this module needs no running Postgres.
"""

from __future__ import annotations

import logging
from typing import Any

from acip_common.bootstrap import ensure_read_model_schema
from acip_common.schemas import (
    AgentVerdictProducedPayload,
    DecisionHint,
    DecisionRenderedPayload,
    EventEnvelope,
    EventType,
    TxnCreatedPayload,
    TxnTerminalPayload,
)

_log = logging.getLogger("graph_projector.postgres_projector")

# Terminal transaction status per decision on a txn.lifecycle terminal event (docs/06 §3).
_TERMINAL_STATUS: dict[EventType, str] = {
    EventType.TXN_EXECUTED: "EXECUTED",
    EventType.TXN_DECLINED: "DECLINED",
    EventType.TXN_CHALLENGED: "CHALLENGED",
}


class PostgresProjector:
    """Project events into the Postgres read models with idempotent upserts (docs/03 §4)."""

    def __init__(self, postgres_dsn: str) -> None:
        self._dsn = postgres_dsn

    def ensure_schema(self) -> bool:
        """Create the read-model tables if absent (fix A.1 always-on owner, docs/03 §4)."""
        return ensure_read_model_schema(self._dsn)

    def project(self, envelope: EventEnvelope) -> None:
        """Project one envelope into Postgres (best-effort; a DB error is logged + swallowed).

        Opens a short-lived connection, journals the event, and applies the type-specific
        upserts in one transaction. A connection/operational failure logs and returns so
        the consumer loop keeps running (docs/03 §8).
        """
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - dependency guard
            _log.warning("psycopg not installed; skipping projection", extra={"error": str(exc)})
            return

        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as conn, conn.cursor() as cur:
                self._journal(cur, envelope)
                self._apply(cur, envelope)
        except Exception as exc:
            _log.warning(
                "postgres projection failed; continuing degraded",
                extra={
                    "transaction_id": envelope.transaction_id,
                    "event_id": envelope.event_id,
                    "event_type": envelope.event_type.value,
                    "error": str(exc),
                },
            )

    def _journal(self, cur: Any, envelope: EventEnvelope) -> None:
        """Record one ``event_journal`` row keyed by ``event_id`` (idempotent)."""
        cur.execute(
            "INSERT INTO event_journal (event_id, transaction_id, event_type, occurred_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (event_id) DO NOTHING",
            (
                envelope.event_id,
                envelope.transaction_id,
                envelope.event_type.value,
                envelope.occurred_at,
            ),
        )

    def _apply(self, cur: Any, envelope: EventEnvelope) -> None:
        """Dispatch the type-specific read-model upsert(s) for ``envelope``."""
        event_type = envelope.event_type
        if event_type is EventType.TXN_CREATED:
            self._apply_created(cur, envelope)
        elif event_type is EventType.DECISION_RENDERED:
            self._apply_decision(cur, envelope)
        elif event_type is EventType.AGENT_VERDICT_PRODUCED:
            self._apply_verdict(cur, envelope)
        elif event_type in _TERMINAL_STATUS:
            self._apply_terminal(cur, envelope)

    def _apply_created(self, cur: Any, envelope: EventEnvelope) -> None:
        """TXN_CREATED -> upsert the ``transactions`` row (status CREATED, no decision)."""
        payload = TxnCreatedPayload.model_validate(envelope.payload)
        cur.execute(
            "INSERT INTO transactions (id, customer_id, amount, status, decision) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "  customer_id = EXCLUDED.customer_id, amount = EXCLUDED.amount",
            (
                envelope.transaction_id,
                payload.customer_id,
                payload.amount,
                "CREATED",
                None,
            ),
        )

    def _apply_decision(self, cur: Any, envelope: EventEnvelope) -> None:
        """DECISION_RENDERED -> upsert ``decisions`` and update the transaction decision/status."""
        payload = DecisionRenderedPayload.model_validate(envelope.payload)
        cur.execute(
            "INSERT INTO decisions (transaction_id, decision, composite_score, strategy) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (transaction_id) DO UPDATE SET "
            "  decision = EXCLUDED.decision, composite_score = EXCLUDED.composite_score, "
            "  strategy = EXCLUDED.strategy",
            (
                envelope.transaction_id,
                payload.decision.value,
                payload.composite_score,
                payload.strategy,
            ),
        )
        cur.execute(
            "UPDATE transactions SET decision = %s, status = %s WHERE id = %s",
            (
                payload.decision.value,
                _status_for_decision(payload.decision),
                envelope.transaction_id,
            ),
        )

    def _apply_verdict(self, cur: Any, envelope: EventEnvelope) -> None:
        """AGENT_VERDICT_PRODUCED -> upsert the per-agent ``agent_verdicts`` row."""
        payload = AgentVerdictProducedPayload.model_validate(envelope.payload)
        cur.execute(
            "INSERT INTO agent_verdicts (transaction_id, agent, score, decision_hint) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (transaction_id, agent) DO UPDATE SET "
            "  score = EXCLUDED.score, decision_hint = EXCLUDED.decision_hint",
            (
                envelope.transaction_id,
                payload.agent.value,
                payload.verdict.score,
                payload.verdict.decision_hint.value,
            ),
        )

    def _apply_terminal(self, cur: Any, envelope: EventEnvelope) -> None:
        """TXN_EXECUTED/DECLINED/CHALLENGED -> update the transaction status/decision."""
        payload = TxnTerminalPayload.model_validate(envelope.payload)
        cur.execute(
            "UPDATE transactions SET status = %s, decision = %s WHERE id = %s",
            (
                _TERMINAL_STATUS[envelope.event_type],
                payload.decision.value,
                envelope.transaction_id,
            ),
        )


# Decision -> transaction status on a decision.rendered projection (docs/06 §3). Mirrors
# commerce_orchestrator.persistence.status_for_decision so the two write paths agree.
_STATUS_BY_DECISION: dict[DecisionHint, str] = {
    DecisionHint.APPROVE: "EXECUTED",
    DecisionHint.ROUTE: "EXECUTED",
    DecisionHint.CHALLENGE: "CHALLENGED",
    DecisionHint.DECLINE: "DECLINED",
}


def _status_for_decision(decision: DecisionHint) -> str:
    """Map a rendered decision to the persisted transaction status (docs/06 §3)."""
    return _STATUS_BY_DECISION.get(decision, "DECLINED")


__all__ = ["PostgresProjector"]
