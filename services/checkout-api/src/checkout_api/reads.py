"""Postgres read-model access for the two GET endpoints (docs/06 §1, docs/03 §4).

The commerce-orchestrator ``finalize`` node persists the decision trace into three
tables (shapes defined in ``scripts/seed.py`` and written by the orchestrator's
``persistence.persist_decision``):

* ``transactions(id, customer_id, amount, status, decision, created_at)``
* ``decisions(transaction_id, decision, composite_score, strategy)``
* ``agent_verdicts(transaction_id, agent, score, decision_hint)``

:func:`read_transaction` composes the ``GET /v1/transactions/{id}`` view (current state +
decision + per-agent verdicts); :func:`read_explain` composes the richer
``/explain`` trace view (inputs, verdicts, strategy, final decision). Both return
``None`` when the transaction id is unknown so the route can answer ``404``.

The reader is defined behind a small :class:`ReadModel` protocol so tests inject a fake
store without a live Postgres. The concrete :class:`PostgresReadModel` opens its
connection per query (short-lived) and raises on connection failure — unlike the
write path, a read that cannot reach the DB is a real error the caller surfaces, not a
silently-degraded success.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

_log = logging.getLogger("checkout_api.reads")


class ReadModel(Protocol):
    """The read-model surface the GET endpoints depend on (mocked in tests)."""

    def read_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        """Return the transaction state + decision + verdicts, or ``None`` if unknown."""
        ...

    def read_explain(self, transaction_id: str) -> dict[str, Any] | None:
        """Return the full decision trace, or ``None`` if the transaction is unknown."""
        ...


class PostgresReadModel:
    """Reads the orchestrator-persisted trace from Postgres (docs/03 §4)."""

    def __init__(self, postgres_dsn: str) -> None:
        self._dsn = postgres_dsn

    def _fetch(self, transaction_id: str) -> tuple[Any, Any, list[Any]] | None:
        """Load the (transaction, decision, verdicts) rows for ``transaction_id``.

        Returns ``None`` when the id is unknown OR when a read-model table does not yet
        exist (``psycopg.errors.UndefinedTable``) — a never-seeded stack is a 404, not a
        500 (docs/06 §1). A genuine connection/operational error still raises so the
        route surfaces it as a 500 (fail-closed on real faults).
        """
        import psycopg
        from psycopg.rows import dict_row

        try:
            with psycopg.connect(self._dsn, connect_timeout=5, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, customer_id, amount, status, decision, created_at "
                        "FROM transactions WHERE id = %s",
                        (transaction_id,),
                    )
                    txn = cur.fetchone()
                    if txn is None:
                        return None
                    cur.execute(
                        "SELECT decision, composite_score, strategy "
                        "FROM decisions WHERE transaction_id = %s",
                        (transaction_id,),
                    )
                    decision = cur.fetchone()
                    cur.execute(
                        "SELECT agent, score, decision_hint "
                        "FROM agent_verdicts WHERE transaction_id = %s ORDER BY agent",
                        (transaction_id,),
                    )
                    verdicts = list(cur.fetchall())
            return txn, decision, verdicts
        except psycopg.errors.UndefinedTable:
            # A missing read-model table (fresh/never-seeded stack) is an unknown id, not
            # a server fault: return None so the route answers 404 rather than 500.
            _log.info(
                "read-model table missing; treating as unknown id",
                extra={"transaction_id": transaction_id},
            )
            return None

    def read_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        """Compose the ``GET /v1/transactions/{id}`` view (docs/06 §1)."""
        rows = self._fetch(transaction_id)
        if rows is None:
            return None
        return _transaction_view(*rows)

    def read_explain(self, transaction_id: str) -> dict[str, Any] | None:
        """Compose the ``/explain`` decision-trace view (docs/06 §1)."""
        rows = self._fetch(transaction_id)
        if rows is None:
            return None
        return _explain_view(*rows)


def _verdicts_list(verdicts: list[Any]) -> list[dict[str, Any]]:
    """Normalize the agent_verdicts rows into a JSON-friendly list."""
    return [
        {
            "agent": row["agent"],
            "score": float(row["score"]) if row["score"] is not None else None,
            "hint": row["decision_hint"],
        }
        for row in verdicts
    ]


def _transaction_view(
    txn: dict[str, Any], decision: dict[str, Any] | None, verdicts: list[Any]
) -> dict[str, Any]:
    """Build the current-state view returned by ``GET /v1/transactions/{id}``."""
    return {
        "transaction_id": txn["id"],
        "customer_id": txn["customer_id"],
        "amount": float(txn["amount"]) if txn["amount"] is not None else None,
        "status": txn["status"],
        "decision": txn["decision"],
        "composite_score": (
            float(decision["composite_score"])
            if decision is not None and decision["composite_score"] is not None
            else None
        ),
        "strategy": decision["strategy"] if decision is not None else None,
        "verdicts": _verdicts_list(verdicts),
        "created_at": txn.get("created_at"),
    }


def _explain_view(
    txn: dict[str, Any], decision: dict[str, Any] | None, verdicts: list[Any]
) -> dict[str, Any]:
    """Build the full decision-trace view returned by ``/explain`` (docs/06 §1)."""
    return {
        "transaction_id": txn["id"],
        "inputs": {
            "customer_id": txn["customer_id"],
            "amount": float(txn["amount"]) if txn["amount"] is not None else None,
        },
        "verdicts": _verdicts_list(verdicts),
        "strategy": decision["strategy"] if decision is not None else None,
        "final_decision": {
            "decision": decision["decision"] if decision is not None else txn["decision"],
            "composite_score": (
                float(decision["composite_score"])
                if decision is not None and decision["composite_score"] is not None
                else None
            ),
            "status": txn["status"],
        },
    }


__all__ = ["PostgresReadModel", "ReadModel"]
