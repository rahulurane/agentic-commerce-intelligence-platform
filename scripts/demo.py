"""Minimal core-path smoke for ACIP Phase 2 (docs/06 §1, §4).

POSTs ``scripts/sample_checkout.json`` to the running ``checkout-api`` on the published
host port and prints the decision JSON. This proves the no-agents end-to-end path: with
no agents running the orchestrator's deadline/``decide_partial`` path still returns a
decision (the Phase 2 guarantee), llm-gateway runs on the mock provider with no cloud
creds, and ml-scoring serves a score (artifact or heuristic).

This is the minimal core-path smoke; the full four-scenario demo driver with all six
agents is deferred to Phase 4. Usage:

    uv run python scripts/demo.py                  # sync, default
    CHECKOUT_URL=http://localhost:8080 uv run python scripts/demo.py

Exit code is 0 when a decision is returned, non-zero otherwise, so ``make demo`` fails
loudly if the stack is not up.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

_SAMPLE = Path(__file__).parent / "sample_checkout.json"


def main() -> int:
    """Run the smoke: POST the sample checkout and print the decision."""
    base_url = os.environ.get("CHECKOUT_URL", "http://localhost:8080")
    body = json.loads(_SAMPLE.read_text())

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{base_url}/v1/checkout", json=body)
    except httpx.HTTPError as exc:
        print(f"smoke failed: could not reach checkout-api at {base_url}: {exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"smoke failed: HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    decision = resp.json()
    print(json.dumps(decision, indent=2))
    if not decision.get("decision"):
        print("smoke failed: response carried no decision", file=sys.stderr)
        return 1
    print(f"\nOK: decision={decision['decision']} transaction_id={decision['transaction_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
