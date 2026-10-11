"""Postgres persistence for the decision trace (docs/03 §4, scripts/seed.py tables).

:func:`persist_decision` writes the three read-model rows the demo + checkout-api read
(docs/06): a ``transactions`` row, a ``decisions`` row, and one ``agent_verdicts`` row
per contributing verdict. Writes are **idempotent upserts** keyed by the table's
primary key (``ON CONFLICT ... DO UPDATE``) so a crash-resume replay of ``finalize``
produces the same state rather than duplicate rows.

The table shapes match ``scripts/seed.py`` exactly:

* ``transactions(id PK, customer_id, amount, status, decision, created_at)``
* ``decisions(transaction_id PK, decision, composite_score, strategy)``
* ``agent_verdicts(transaction_id, agent, score, decision_hint, PK(transaction_id, agent))``

Writes are **best-effort**: a Postgres outage logs a warning and returns ``False``
rather than failing the evaluation, so the core path still produces a decision with no
database up (consistent with the sparse-store posture of docs/03 §8). The connection
opens lazily so importing this module needs no running Postgres.
"""

from __future__ import annotations

import logging

from acip_common.bootstrap import ensure_read_model_schema
from acip_common.schemas import DecisionHint, DecisionRenderedPayload, SharedRepresentation, Verdict

_log = logging.getLogger("commerce_orchestrator.persistence")

# Terminal transaction status per final decision (docs/06 §3 lifecycle events).
_STATUS_BY_DECISION: dict[DecisionHint, str] = {
    DecisionHint.APPROVE: "EXECUTED",
    DecisionHint.ROUTE: "EXECUTED",
    DecisionHint.CHALLENGE: "CHALLENGED",
    DecisionHint.DECLINE: "DECLINED",
}


def status_for_decision(decision: DecisionHint) -> str:
    """Map a final decision to the persisted transaction status (docs/06 §3)."""
    return _STATUS_BY_DECISION.get(decision, "DECLINED")


def persist_decision(
    postgres_dsn: str,
    *,
    representation: SharedRepresentation,
    decision: DecisionRenderedPayload,
    verdicts: dict[str, Verdict],
) -> bool:
    """Upsert the decision trace into Postgres (docs/03 §4). Returns ``True`` on success.

    Idempotent: re-running with the same ``transaction_id`` overwrites the prior rows
    (``ON CONFLICT DO UPDATE``) so crash-resume never duplicates. A connection failure
    is logged and swallowed (returns ``False``) so the core path survives a DB outage.

    Runs :func:`acip_common.bootstrap.ensure_read_model_schema` first (docs/03 §4) so a
    fresh stack brought up with NO seed still has the tables and persists/serves reads;
    the bootstrap is itself best-effort and never raises.
    """
    ensure_read_model_schema(postgres_dsn)
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - dependency guard
        _log.warning("psycopg not installed; skipping persistence", extra={"error": str(exc)})
        return False

    txn_id = representation.transaction_id
    status = status_for_decision(decision.decision)
    try:
        with psycopg.connect(postgres_dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO transactions (id, customer_id, amount, status, decision) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET "
                "  customer_id = EXCLUDED.customer_id, amount = EXCLUDED.amount, "
                "  status = EXCLUDED.status, decision = EXCLUDED.decision",
                (
                    txn_id,
                    representation.transaction.customer_id,
                    representation.transaction.amount,
                    status,
                    decision.decision.value,
                ),
            )
            cur.execute(
                "INSERT INTO decisions (transaction_id, decision, composite_score, strategy) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (transaction_id) DO UPDATE SET "
                "  decision = EXCLUDED.decision, composite_score = EXCLUDED.composite_score, "
                "  strategy = EXCLUDED.strategy",
                (
                    txn_id,
                    decision.decision.value,
                    decision.composite_score,
                    decision.strategy,
                ),
            )
            for agent, verdict in verdicts.items():
                cur.execute(
                    "INSERT INTO agent_verdicts (transaction_id, agent, score, decision_hint) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (transaction_id, agent) DO UPDATE SET "
                    "  score = EXCLUDED.score, decision_hint = EXCLUDED.decision_hint",
                    (txn_id, agent, verdict.score, verdict.decision_hint.value),
                )
        return True
    except Exception as exc:
        _log.warning(
            "postgres persistence failed; continuing degraded",
            extra={"transaction_id": txn_id, "error": str(exc)},
        )
        return False


__all__ = ["persist_decision", "status_for_decision"]
