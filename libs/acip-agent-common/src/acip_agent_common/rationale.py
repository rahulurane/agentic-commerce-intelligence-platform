"""Templated-fallback LLM rationale for agents (docs/02 §1).

An agent's rationale is an EXPLANATION, never a gate: the decision is already made by the
agent's ``score_fn`` before the LLM is consulted. :func:`llm_rationale` POSTs to the
llm-gateway ``POST /v1/complete`` (docs/04 §6) for a natural-language rationale, but on
ANY failure — timeout, connection error, non-2xx, malformed body — it returns a TEMPLATED
rationale string with ``degraded=True`` so the agent never blocks on the LLM and the stack
runs with no cloud creds (docs/02 §1, context: llm-gateway degrades to mock).

The gateway client is created per call with a short timeout; this module imports no broker
or gateway at import time.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from acip_common.config import Settings

# Keep the gateway call short — the rationale is explanatory, so a slow LLM must not stall
# the agent. The templated fallback covers any overrun.
_LLM_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class RationaleResult:
    """The rationale text plus whether it came from the templated fallback (docs/02 §1)."""

    text: str
    degraded: bool


def _templated(system: str, prompt: str) -> str:
    """Build the deterministic fallback rationale used when the LLM is unavailable."""
    return (
        f"[templated] {system.strip()} Decision derived from scored signals: "
        f"{prompt.strip()} (LLM unavailable; using deterministic rationale)."
    )


def llm_rationale(
    settings: Settings,
    *,
    system: str,
    prompt: str,
    trace_id: str,
) -> RationaleResult:
    """Return an LLM rationale, or a templated fallback with ``degraded=True`` (docs/02 §1).

    POSTs ``{system, prompt, metadata:{trace_id}}`` to ``{llm_gateway_url}/v1/complete``.
    On any error (timeout, connection, non-2xx, missing ``text``) returns the templated
    rationale with ``degraded=True`` so the agent never blocks on the LLM.
    """
    url = f"{settings.llm_gateway_url}/v1/complete"
    body = {"system": system, "prompt": prompt, "metadata": {"trace_id": trace_id}}
    try:
        with httpx.Client(timeout=_LLM_TIMEOUT_SECONDS) as client:
            resp = client.post(url, json=body)
            resp.raise_for_status()
            text = resp.json().get("text")
        if not text:
            return RationaleResult(text=_templated(system, prompt), degraded=True)
        return RationaleResult(text=str(text), degraded=False)
    except Exception:
        # Any failure degrades to the templated rationale — the agent must not block.
        return RationaleResult(text=_templated(system, prompt), degraded=True)


__all__ = ["RationaleResult", "llm_rationale"]
