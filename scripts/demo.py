"""Five-scenario end-to-end demo for ACIP (docs/05 §6.3, docs/06 §1, §4).

POSTs one checkout per seeded scenario to the running ``checkout-api`` on the published
host port and asserts the decision each one produces. This exercises the full agentic
path: the orchestrator fans out ``txn.evaluate.requested``, the six agents read their
slice of the shared representation (built from the seeded Neo4j graph), publish verdicts,
and the decision-engine aggregates them into a real APPROVE / DECLINE / CHALLENGE.

Each request body is built from the matching ``scripts.seed.SCENARIOS`` entry so the
seeded graph signals drive the agents, and ``context.device_fingerprint`` is set to the
scenario's ``device_id`` so the fraud ring resolves (docs/05 §6.3):

    clean_shopper             -> APPROVE
    ring_member               -> DECLINE (fraud veto)
    high_value_midrisk        -> CHALLENGE (merchant step-up)
    sanctioned_geo            -> DECLINE (policy veto)
    unhealthy_preferred_route -> APPROVE on an alternate route (route != processor_pref)

Run ``make seed`` first so the stores hold the demo scenarios. The stack runs with NO
cloud creds (llm-gateway on the mock provider; agents emit a templated rationale with
``degraded=true`` so the decision never blocks on the LLM). Usage:

    uv run python scripts/demo.py
    CHECKOUT_URL=http://localhost:8080 uv run python scripts/demo.py

Exit code is 0 only when all five scenarios return their expected decision, so
``make demo`` fails loudly if any scenario does not match.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

# ``scripts/demo.py`` is run as a top-level script (``uv run python scripts/demo.py``),
# so its own directory is on ``sys.path`` and the sibling seed module imports directly.
from seed import SCENARIOS, Scenario

# The degraded preferred route seeded for unhealthy_preferred_route; the routing agent
# must pick a healthier alternate, so the chosen route must NOT be this one.
_DEGRADED_ROUTE = "processor_pref"


def _request_body(scenario: Scenario) -> dict[str, Any]:
    """Build the ``POST /v1/checkout`` body for a seeded scenario (docs/06 §1).

    The ``device_fingerprint`` is the scenario's seeded ``device_id`` so the fraud
    agent resolves the shared-device ring; the amount/method drive the merchant and
    personalization agents.
    """
    return {
        "merchant_id": "mrc_demo",
        "customer_id": scenario.customer_id,
        "amount": scenario.amount,
        "currency": "INR",
        "payment_method": {
            "type": scenario.method_type,
            "token": f"tok_{scenario.name}",
        },
        "context": {
            "device_fingerprint": scenario.device_id,
            "ip": "203.0.113.9",
            "user_agent": "acip-demo/1.0",
        },
        "idempotency_key": f"idem_demo_{scenario.name}",
    }


def _check_scenario(scenario: Scenario, decision: dict[str, Any]) -> list[str]:
    """Return a list of failure messages for a scenario's decision (empty == pass)."""
    failures: list[str] = []
    got = decision.get("decision")
    if got != scenario.expected_decision:
        failures.append(
            f"decision {got!r} != expected {scenario.expected_decision!r}",
        )
    # The reroute scenario must APPROVE on an alternate route, never the degraded one.
    if scenario.name == "unhealthy_preferred_route":
        route = decision.get("route")
        if route == _DEGRADED_ROUTE:
            failures.append(
                f"route {route!r} is the degraded preferred route; expected an alternate",
            )
        elif route is None:
            failures.append("no route chosen; expected a healthy alternate route")
    return failures


def _run_scenario(client: httpx.Client, base_url: str, scenario: Scenario) -> list[str]:
    """POST one scenario and return its failure messages (empty == pass)."""
    try:
        resp = client.post(f"{base_url}/v1/checkout", json=_request_body(scenario))
    except httpx.HTTPError as exc:
        return [f"could not reach checkout-api at {base_url}: {exc}"]
    if resp.status_code != 200:
        return [f"HTTP {resp.status_code}: {resp.text}"]

    decision = resp.json()
    failures = _check_scenario(scenario, decision)
    status = "OK" if not failures else "FAIL"
    route = decision.get("route")
    print(
        f"[{status}] {scenario.name}: decision={decision.get('decision')} "
        f"route={route} transaction_id={decision.get('transaction_id')}"
    )
    for failure in failures:
        print(f"       - {failure}")
    return failures


def main() -> int:
    """Drive the five seeded scenarios and assert each decision."""
    base_url = os.environ.get("CHECKOUT_URL", "http://localhost:8080")
    any_failed = False

    with httpx.Client(timeout=30.0) as client:
        for scenario in SCENARIOS:
            failures = _run_scenario(client, base_url, scenario)
            any_failed = any_failed or bool(failures)

    if any_failed:
        print("\ndemo FAILED: one or more scenarios did not match", file=sys.stderr)
        return 1
    print(f"\nOK: all {len(SCENARIOS)} scenarios returned their expected decision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
