"""Store adapters that hydrate the shared representation (docs/03 §3, §5, §8).

Two read-only adapters pull the signals the builder needs:

* :class:`GraphStore` reads the Neo4j transaction-intelligence graph (docs/03 §3):
  the shared-device ring size (the ``FROM_DEVICE`` device-sharing traversal), the
  customer's 30-day transaction count and lifetime chargeback count, per-method
  success/failure history (``USED_METHOD_TYPE``), and the candidate Processor routes.
* :class:`HotStore` reads hot features from Redis (docs/03 §5), e.g. ``velocity_1h``.

Both adapters are **degradation-tolerant** (docs/03 §8, FEAT-003 sparse-graph
fallback): if the store is unreachable or empty they return empty signals rather than
raising, so the builder can fall back to sensible defaults and the evaluation path
still runs with NO graph seeded and NO stores up. Connections open lazily so importing
this module needs no running Neo4j/Redis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger("representation_service.stores")


@dataclass
class GraphSignals:
    """Signals hydrated from the Neo4j graph for one transaction (docs/03 §3)."""

    ring_size: int = 0
    customer_txn_count_30d: int = 0
    customer_chargeback_count: int = 0
    home_geo: str | None = None
    method_history: dict[str, tuple[int, int]] = field(default_factory=dict)
    candidate_routes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HotSignals:
    """Hot features hydrated from Redis for one transaction (docs/03 §5)."""

    velocity_1h: int = 0


def _parse_neo4j_auth(auth: str) -> tuple[str, str]:
    """Split ``NEO4J_AUTH`` (``user/password``) into a tuple."""
    user, _, password = auth.partition("/")
    return user, password


class GraphStore:
    """Read-only Neo4j adapter for graph signals (docs/03 §3). Degradation-tolerant."""

    def __init__(self, uri: str, auth: str) -> None:
        self._uri = uri
        self._user, self._password = _parse_neo4j_auth(auth)
        self._driver: Any = None

    def _ensure(self) -> Any:
        """Open the driver lazily; return ``None`` if the driver cannot be built."""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase

                self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
            except Exception as exc:  # pragma: no cover - import/connect guard
                _log.warning("neo4j driver unavailable; degraded", extra={"error": str(exc)})
                return None
        return self._driver

    def fetch(
        self, customer_id: str, device_fingerprint: str | None, method_type: str
    ) -> tuple[GraphSignals, bool]:
        """Hydrate graph signals; return ``(signals, degraded)``.

        ``degraded`` is ``True`` when the store was unreachable so the caller can fill
        defaults and label the representation degraded (docs/03 §8). The shared-device
        ring size follows the ``FROM_DEVICE`` device-sharing pattern (docs/03 §3):
        count the distinct customers linked to the transaction's device.
        """
        driver = self._ensure()
        if driver is None:
            return GraphSignals(), True
        try:
            with driver.session() as session:
                signals = GraphSignals()

                customer = session.run(
                    "MATCH (c:Customer {id: $cid}) "
                    "RETURN c.home_geo AS home_geo, "
                    "       coalesce(c.txn_count_30d, 0) AS txn_count_30d, "
                    "       coalesce(c.chargeback_count, 0) AS chargeback_count",
                    cid=customer_id,
                ).single()
                if customer is not None:
                    signals.home_geo = customer.get("home_geo")
                    signals.customer_txn_count_30d = int(customer.get("txn_count_30d") or 0)
                    signals.customer_chargeback_count = int(customer.get("chargeback_count") or 0)

                if device_fingerprint:
                    ring = session.run(
                        "MATCH (d:Device {id: $did})-[:LINKED_TO]->(c:Customer) "
                        "RETURN count(DISTINCT c) AS ring_size",
                        did=device_fingerprint,
                    ).single()
                    if ring is not None:
                        signals.ring_size = int(ring.get("ring_size") or 0)

                method = session.run(
                    "MATCH (c:Customer {id: $cid})-[r:USED_METHOD_TYPE]->"
                    "(mt:MethodType {name: $method}) "
                    "RETURN coalesce(r.successes, 0) AS successes, "
                    "       coalesce(r.failures, 0) AS failures",
                    cid=customer_id,
                    method=method_type,
                ).single()
                if method is not None:
                    signals.method_history[method_type] = (
                        int(method.get("successes") or 0),
                        int(method.get("failures") or 0),
                    )

                routes = session.run(
                    "MATCH (p:Processor) "
                    "RETURN p.id AS processor, "
                    "       coalesce(p.success_rate, 0.0) AS success_rate, "
                    "       p.cost_bps AS cost_bps, "
                    "       p.p50_latency_ms AS p50_latency_ms "
                    "ORDER BY success_rate DESC"
                )
                for record in routes:
                    signals.candidate_routes.append(
                        {
                            "processor": str(record.get("processor")),
                            "success_rate": float(record.get("success_rate") or 0.0),
                            "cost_bps": record.get("cost_bps"),
                            "p50_latency_ms": record.get("p50_latency_ms"),
                        }
                    )
                return signals, False
        except Exception as exc:
            _log.warning("neo4j read failed; degraded", extra={"error": str(exc)})
            return GraphSignals(), True

    def close(self) -> None:
        """Close the driver if it was opened."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None


class HotStore:
    """Read-only Redis adapter for hot features (docs/03 §5). Degradation-tolerant."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Any = None

    def _ensure(self) -> Any:
        """Open the client lazily; return ``None`` if the client cannot be built."""
        if self._client is None:
            try:
                import redis

                self._client = redis.Redis.from_url(self._url)
            except Exception as exc:  # pragma: no cover - import/connect guard
                _log.warning("redis client unavailable; degraded", extra={"error": str(exc)})
                return None
        return self._client

    def fetch(self, customer_id: str) -> tuple[HotSignals, bool]:
        """Hydrate hot features; return ``(signals, degraded)`` (docs/03 §5, §8)."""
        client = self._ensure()
        if client is None:
            return HotSignals(), True
        try:
            raw = client.get(f"velocity:1h:{customer_id}")
            velocity = int(raw) if raw is not None else 0
            return HotSignals(velocity_1h=velocity), False
        except Exception as exc:
            _log.warning("redis read failed; degraded", extra={"error": str(exc)})
            return HotSignals(), True

    def cache_representation(self, transaction_id: str, representation_json: str) -> None:
        """Cache the built representation JSON keyed by transaction id (docs/03 §8).

        Best-effort: a cache failure must not fail the build (degradation-tolerant).
        """
        client = self._ensure()
        if client is None:
            return
        try:
            client.set(f"representation:{transaction_id}", representation_json)
        except Exception as exc:
            _log.warning("redis cache write failed; degraded", extra={"error": str(exc)})

    def close(self) -> None:
        """Close the client if it was opened."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None


__all__ = ["GraphSignals", "GraphStore", "HotSignals", "HotStore"]
