"""Synchronous HTTP clients for the services the orchestrator calls (docs/06 §2).

Thin ``httpx`` wrappers around representation-service, decision-engine, and
payment-processor-sim, each with an explicit timeout and the ``trace_id`` propagated
so a single transaction correlates across services (docs/01 §6). The clients return
already-validated ``acip-common`` models / plain dicts; they never redefine contracts.

Timeouts are derived from ``Settings.decision_deadline_ms`` with headroom so a slow
callee surfaces as a client error rather than hanging the graph.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from acip_common.config import Settings
from acip_common.schemas import (
    AgentName,
    CandidateRoute,
    DecisionRenderedPayload,
    SharedRepresentation,
    Verdict,
)

_log = logging.getLogger("commerce_orchestrator.clients")


def _timeout_seconds(settings: Settings) -> float:
    """Per-call HTTP timeout: the decision deadline plus generous headroom."""
    return max(2.0, (settings.decision_deadline_ms / 1000.0) + 2.0)


class ServiceClients:
    """Grouped sync clients for the orchestrator's downstream calls (docs/06 §2)."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=_timeout_seconds(settings))

    def build_representation(
        self,
        *,
        transaction_id: str,
        trace_id: str,
        amount: float,
        currency: str,
        method_type: str,
        merchant_id: str,
        customer_id: str,
        txn_geo: str | None = None,
        device_fingerprint: str | None = None,
    ) -> SharedRepresentation:
        """POST representation-service ``/v1/representation`` (docs/03 §8)."""
        resp = self._client.post(
            f"{self._settings.representation_url}/v1/representation",
            json={
                "transaction_id": transaction_id,
                "trace_id": trace_id,
                "amount": amount,
                "currency": currency,
                "method_type": method_type,
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "txn_geo": txn_geo,
                "device_fingerprint": device_fingerprint,
            },
        )
        resp.raise_for_status()
        return SharedRepresentation.model_validate(resp.json())

    def decide(
        self,
        *,
        transaction_id: str,
        trace_id: str,
        verdicts: dict[AgentName, Verdict],
        candidate_routes: list[CandidateRoute],
    ) -> DecisionRenderedPayload:
        """POST decision-engine ``/v1/decide`` (docs/02 §5, docs/06 §2)."""
        resp = self._client.post(
            f"{self._settings.decision_engine_url}/v1/decide",
            json={
                "transaction_id": transaction_id,
                "trace_id": trace_id,
                "verdicts": {
                    agent.value: verdict.model_dump() for agent, verdict in verdicts.items()
                },
                "candidate_routes": [route.model_dump() for route in candidate_routes],
            },
        )
        resp.raise_for_status()
        return DecisionRenderedPayload.model_validate(resp.json())

    def charge(
        self,
        *,
        transaction_id: str,
        trace_id: str,
        amount: float,
        currency: str,
        route: str,
    ) -> dict[str, Any]:
        """POST payment-processor-sim ``/v1/charge`` (docs/06 §2).

        Returns the processor result as a dict. A processor failure surfaces as a 503
        from the sim; the caller catches it and records a declined terminal state.
        """
        resp = self._client.post(
            f"{self._settings.payment_processor_url}/v1/charge",
            json={
                "transaction_id": transaction_id,
                "trace_id": trace_id,
                "amount": amount,
                "currency": currency,
                "route": route,
            },
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()


__all__ = ["ServiceClients"]
