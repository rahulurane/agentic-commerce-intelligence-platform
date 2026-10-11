"""Runtime Postgres read-model bootstrap, independent of ``scripts/seed.py`` (docs/03 §4).

The demo seed (``scripts/seed.py``) creates the four read-model tables when it runs, but
a fresh stack brought up with NO seed must still be able to persist and serve reads. This
module provides :func:`ensure_read_model_schema`, which issues ``CREATE TABLE IF NOT
EXISTS`` for the exact table shapes defined in ``scripts/seed.py`` so the orchestrator's
``persist_decision`` can run against a never-seeded database.

The table shapes here are IDENTICAL to ``scripts/seed.py`` (docs/03 §4):

* ``transactions(id PK, customer_id, amount NUMERIC, status, decision, created_at)``
* ``decisions(transaction_id PK, decision, composite_score NUMERIC, strategy)``
* ``agent_verdicts(transaction_id, agent, score NUMERIC, decision_hint, PK(txn, agent))``
* ``event_journal(event_id PK, transaction_id, event_type, occurred_at)``

Best-effort posture (consistent with the write path in docs/03 §8): a connection or
operational failure is logged and swallowed (returns ``False``) rather than raising, so a
database outage degrades the stack instead of crashing it. The ``psycopg`` import is lazy
so importing this module needs no running Postgres and no hard dependency at import time.
"""

from __future__ import annotations

import logging

_log = logging.getLogger("acip_common.bootstrap")

# CREATE TABLE IF NOT EXISTS for the four read-model tables, column-for-column identical
# to scripts/seed.py (docs/03 §4). Keep this in lockstep with the seed if either changes.
_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        amount NUMERIC NOT NULL,
        status TEXT NOT NULL,
        decision TEXT,
        created_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decisions (
        transaction_id TEXT PRIMARY KEY,
        decision TEXT NOT NULL,
        composite_score NUMERIC,
        strategy TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_verdicts (
        transaction_id TEXT NOT NULL,
        agent TEXT NOT NULL,
        score NUMERIC,
        decision_hint TEXT,
        PRIMARY KEY (transaction_id, agent)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS event_journal (
        event_id TEXT PRIMARY KEY,
        transaction_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        occurred_at TIMESTAMPTZ DEFAULT now()
    )
    """,
)


def ensure_read_model_schema(postgres_dsn: str) -> bool:
    """Create the four read-model tables if absent (docs/03 §4). Returns ``True`` on success.

    Opens a short-lived ``psycopg`` connection (lazy import) and runs ``CREATE TABLE IF
    NOT EXISTS`` for each read-model table, so a fresh, never-seeded stack still has the
    tables the orchestrator persists into and checkout-api reads from. Best-effort: a
    connection or operational failure is logged and swallowed (returns ``False``) so a DB
    outage never crashes the caller.
    """
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - dependency guard
        _log.warning("psycopg not installed; skipping schema bootstrap", extra={"error": str(exc)})
        return False

    try:
        with psycopg.connect(postgres_dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            for statement in _SCHEMA_STATEMENTS:
                cur.execute(statement)
        return True
    except Exception as exc:
        _log.warning(
            "read-model schema bootstrap failed; continuing degraded",
            extra={"error": str(exc)},
        )
        return False


__all__ = ["ensure_read_model_schema"]
