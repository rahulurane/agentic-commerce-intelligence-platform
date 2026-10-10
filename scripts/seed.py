"""Layer 2 graph + demo seed for Neo4j and Postgres (docs/05 §6.3, docs/03 §3-4).

Loads a small, hand-shaped set of named scenarios so the live demo produces meaningful
graph signals and predictable outcomes. The seed is idempotent: re-running resets to
the same known state (MERGE on all nodes/edges, truncate + reinsert on the Postgres
read models), which is what makes the demo walkthrough deterministic.

Scenarios (docs/05 §6.3):
    clean_shopper             -> APPROVE
    ring_member               -> DECLINE (fraud veto)
    high_value_midrisk        -> CHALLENGE (step-up)
    sanctioned_geo            -> DECLINE (policy veto)
    unhealthy_preferred_route -> APPROVE on alternate route

Connection config comes from ``acip_common.config.Settings``. On a connection failure
the script exits non-zero with a clear message naming the unreachable store, so the
operator knows which dependency to bring up (guarded per plan item 12).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from acip_common.config import Settings


@dataclass(frozen=True)
class Scenario:
    """A named demo scenario and its seeded shape (docs/05 §6.3)."""

    customer_id: str
    name: str
    home_geo: str
    amount: float
    method_type: str
    expected_decision: str
    device_id: str
    ring_size: int = 0
    chargeback_count: int = 0
    risk_tier: str = "low"
    method_history: dict[str, dict[str, int]] = field(default_factory=dict)


# The five named scenarios. Kept small (tens of entities) and readable.
SCENARIOS: list[Scenario] = [
    Scenario(
        customer_id="cus_clean",
        name="clean_shopper",
        home_geo="IN",
        amount=120.0,
        method_type="upi",
        expected_decision="APPROVE",
        device_id="dev_clean",
        risk_tier="low",
        method_history={"upi": {"successes": 18, "failures": 1}},
    ),
    Scenario(
        customer_id="cus_ring",
        name="ring_member",
        home_geo="IN",
        amount=90.0,
        method_type="card",
        expected_decision="DECLINE",
        device_id="dev_shared",
        ring_size=5,
        risk_tier="high",
        method_history={"card": {"successes": 2, "failures": 4}},
    ),
    Scenario(
        customer_id="cus_midrisk",
        name="high_value_midrisk",
        home_geo="US",
        amount=4800.0,
        method_type="card",
        expected_decision="CHALLENGE",
        device_id="dev_midrisk",
        chargeback_count=1,
        risk_tier="medium",
        method_history={"card": {"successes": 9, "failures": 2}},
    ),
    Scenario(
        customer_id="cus_sanctioned",
        name="sanctioned_geo",
        home_geo="XX",
        amount=200.0,
        method_type="wallet",
        expected_decision="DECLINE",
        device_id="dev_sanctioned",
        risk_tier="medium",
        method_history={"wallet": {"successes": 4, "failures": 0}},
    ),
    Scenario(
        customer_id="cus_reroute",
        name="unhealthy_preferred_route",
        home_geo="GB",
        amount=260.0,
        method_type="card",
        expected_decision="APPROVE",
        device_id="dev_reroute",
        risk_tier="low",
        method_history={"card": {"successes": 15, "failures": 1}},
    ),
]

# Candidate routes with varying health so route-scoring is visible (docs/05 §6.3).
ROUTES: list[dict[str, object]] = [
    {"processor": "processor_a", "success_rate": 0.97, "cost_bps": 85, "p50_latency_ms": 220},
    {"processor": "processor_b", "success_rate": 0.94, "cost_bps": 70, "p50_latency_ms": 180},
    # The preferred route for cus_reroute is degraded, forcing a failover in the demo.
    {"processor": "processor_pref", "success_rate": 0.42, "cost_bps": 60, "p50_latency_ms": 950},
]


class SeedError(RuntimeError):
    """Raised when a store cannot be reached or seeded."""


def _parse_neo4j_auth(auth: str) -> tuple[str, str]:
    """Split ``NEO4J_AUTH`` (``user/password``) into a tuple."""
    user, _, password = auth.partition("/")
    return user, password


def seed_neo4j(settings: Settings) -> None:
    """Seed the Neo4j transaction intelligence graph (docs/03 §3). Idempotent (MERGE)."""
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise SeedError(f"neo4j driver not installed: {exc}") from exc

    user, password = _parse_neo4j_auth(settings.neo4j_auth)
    try:
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception as exc:
        raise SeedError(f"cannot connect to Neo4j at {settings.neo4j_uri}: {exc}") from exc

    try:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")  # reset to known state
            for scenario in SCENARIOS:
                session.run(
                    """
                    MERGE (c:Customer {id: $customer_id})
                      SET c.risk_tier = $risk_tier, c.home_geo = $home_geo
                    MERGE (d:Device {id: $device_id})
                    MERGE (d)-[:LINKED_TO]->(c)
                    """,
                    customer_id=scenario.customer_id,
                    risk_tier=scenario.risk_tier,
                    home_geo=scenario.home_geo,
                    device_id=scenario.device_id,
                )
                for method, hist in scenario.method_history.items():
                    session.run(
                        """
                        MATCH (c:Customer {id: $customer_id})
                        MERGE (mt:MethodType {name: $method})
                        MERGE (c)-[r:USED_METHOD_TYPE]->(mt)
                          SET r.successes = $successes,
                              r.failures = $failures,
                              r.last_used = datetime()
                        """,
                        customer_id=scenario.customer_id,
                        method=method,
                        successes=hist["successes"],
                        failures=hist["failures"],
                    )
            for route in ROUTES:
                session.run(
                    "MERGE (p:Processor {id: $processor}) "
                    "SET p.success_rate = $success_rate, p.cost_bps = $cost_bps, "
                    "    p.p50_latency_ms = $p50_latency_ms",
                    **route,
                )
    finally:
        driver.close()


def seed_postgres(settings: Settings) -> None:
    """Seed the Postgres read-model tables (docs/03 §4). Idempotent (truncate+insert)."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise SeedError(f"psycopg not installed: {exc}") from exc

    try:
        conn = psycopg.connect(settings.postgres_dsn, connect_timeout=5)
    except Exception as exc:
        raise SeedError(f"cannot connect to Postgres at {settings.postgres_dsn}: {exc}") from exc

    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    amount NUMERIC NOT NULL,
                    status TEXT NOT NULL,
                    decision TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    transaction_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    composite_score NUMERIC,
                    strategy TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_verdicts (
                    transaction_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    score NUMERIC,
                    decision_hint TEXT,
                    PRIMARY KEY (transaction_id, agent)
                );
                CREATE TABLE IF NOT EXISTS event_journal (
                    event_id TEXT PRIMARY KEY,
                    transaction_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TIMESTAMPTZ DEFAULT now()
                );
                """
            )
            # Reset to a known state (idempotent).
            cur.execute("TRUNCATE transactions, decisions, agent_verdicts, event_journal")
            for i, scenario in enumerate(SCENARIOS):
                txn_id = f"txn_seed_{i:02d}"
                cur.execute(
                    "INSERT INTO transactions (id, customer_id, amount, status, decision) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        txn_id,
                        scenario.customer_id,
                        scenario.amount,
                        "SEEDED",
                        scenario.expected_decision,
                    ),
                )
                cur.execute(
                    "INSERT INTO decisions (transaction_id, decision, composite_score, strategy) "
                    "VALUES (%s, %s, %s, %s)",
                    (txn_id, scenario.expected_decision, 0.0, "weighted_veto"),
                )
    finally:
        conn.close()


def main() -> int:
    """Seed both stores; return a process exit code (0 ok, non-zero on failure)."""
    settings = Settings()
    try:
        seed_neo4j(settings)
        seed_postgres(settings)
    except SeedError as exc:
        print(f"seed failed: {exc}", file=sys.stderr)
        return 1
    print(f"seeded {len(SCENARIOS)} scenarios into Neo4j + Postgres")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
