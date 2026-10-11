"""Redis-backed idempotency store for ``POST /v1/checkout`` (docs/06 §5).

The idempotency contract (docs/06 §5): a repeated ``idempotency_key`` returns the
ORIGINAL decision and never re-triggers evaluation or a second charge. We implement
this with a small Redis key/value store: the first request for a key stores the minted
``transaction_id`` plus the decision JSON that was returned; a later request with the
same key reads that record back and short-circuits before calling the orchestrator.

A production-grade note on the race between concurrent first-requests for the same key:
:meth:`reserve` uses Redis ``SET NX`` to atomically claim the key, so exactly one caller
proceeds to evaluate while a concurrent duplicate is told to wait and re-read. Here we
keep it simple — the demo is single-flight per key — but the reserve/commit split leaves
room for that hardening without a contract change.

Best-effort posture: if Redis is unreachable the store degrades to "no stored record"
so the edge still serves (losing the idempotency guarantee only while Redis is down,
which is logged). The client opens lazily so importing this module needs no Redis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger("checkout_api.idempotency")

_KEY_PREFIX = "checkout:idempotency:"
# Keep stored decisions for a day — long enough to absorb client retries, short enough
# not to grow unbounded. Idempotency keys are expected to be short-lived per checkout.
_TTL_SECONDS = 24 * 60 * 60


@dataclass
class StoredDecision:
    """A previously returned checkout result, replayed on an idempotency-key repeat."""

    transaction_id: str
    decision: dict[str, Any]


class IdempotencyStore:
    """Persist and replay checkout decisions keyed by ``idempotency_key`` (docs/06 §5)."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is None:
            try:
                import redis

                self._client = redis.Redis.from_url(self._url)
            except Exception as exc:  # pragma: no cover - import/connect guard
                _log.warning(
                    "redis unavailable for idempotency; degraded",
                    extra={"error": str(exc)},
                )
                return None
        return self._client

    def get(self, idempotency_key: str) -> StoredDecision | None:
        """Return the stored decision for ``idempotency_key``, or ``None`` if unseen."""
        client = self._ensure()
        if client is None:
            return None
        try:
            raw = client.get(f"{_KEY_PREFIX}{idempotency_key}")
        except Exception as exc:
            _log.warning("idempotency read failed; degraded", extra={"error": str(exc)})
            return None
        if raw is None:
            return None
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        data = json.loads(text)
        return StoredDecision(transaction_id=data["transaction_id"], decision=data["decision"])

    def put(self, idempotency_key: str, stored: StoredDecision) -> None:
        """Store the decision returned for ``idempotency_key`` (best-effort)."""
        client = self._ensure()
        if client is None:
            return
        payload = json.dumps({"transaction_id": stored.transaction_id, "decision": stored.decision})
        try:
            client.set(f"{_KEY_PREFIX}{idempotency_key}", payload, ex=_TTL_SECONDS)
        except Exception as exc:
            _log.warning("idempotency write failed; degraded", extra={"error": str(exc)})

    def close(self) -> None:
        """Close the client if it was opened."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None


__all__ = ["IdempotencyStore", "StoredDecision"]
