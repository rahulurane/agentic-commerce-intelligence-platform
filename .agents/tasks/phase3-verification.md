# ACIP Phase 3 — FEAT-004 live verification

Full-stack, end-to-end verification of the Phase-3 wiring (six agents + graph-projector
in compose, Makefile `up`, the five-scenario `scripts/demo.py`, and the one-command
`./start.sh` / `./stop.sh`). Run on the live Docker daemon (Docker 27.3.1 / Compose
v2.29.7) with NO cloud credentials.

## Static gate (repo root)

| Check | Result |
| --- | --- |
| `uv sync` | ok (86 packages resolved) |
| `uv run ruff check .` | clean |
| `uv run black --check .` | clean (102 files) |
| `uv run mypy libs services` | clean, strict (97 source files) |
| `uv run pytest libs/acip-common libs/acip-agent-common services` | 127 passed |
| `docker compose -f deploy/docker-compose.yml config` | valid, 22 services |

Published host ports: only `checkout-api` 8080 among the app services; all six agents +
graph-projector publish NO host port. The remaining published ports are the pre-existing
infra UIs (Redpanda 19092, Neo4j 7474/7687, Postgres 5432, Redis 6379, Prometheus 9090,
Grafana 3000, Jaeger 16686/4317).

## Live smoke — `./start.sh` from a clean state

`./stop.sh -v` first (removed all volumes), then `./start.sh`:

- Built all 14 application images and brought up the full stack (14 app services + infra).
- Waited for Redpanda/Neo4j/Postgres/Redis healthy and `checkout-api /healthz` ok.
- Seeded Neo4j + Postgres from the host (localhost store hostnames).
- Ran the five-scenario demo; all five matched.
- `llm-gateway` served every completion on the **mock** provider (no cloud creds);
  agent rationales are the templated/mock path and never block the decision.
- All 14 app services confirmed `running` afterwards (`docker compose ps`).

### Per-scenario decisions (actual, as returned by checkout-api)

| Scenario | Expected | Actual | Route | Driver |
| --- | --- | --- | --- | --- |
| clean_shopper | APPROVE | **APPROVE** | processor_a | low risk + fraud |
| ring_member | DECLINE | **DECLINE** | — | fraud hard veto (shared-device ring size 5) |
| high_value_midrisk | CHALLENGE | **CHALLENGE** | processor_a | merchant high-value step-up (amount 4800) |
| sanctioned_geo | DECLINE | **DECLINE** | — | policy hard veto (home_geo XX) |
| unhealthy_preferred_route | APPROVE | **APPROVE** | processor_a | routing picked a healthy alternate over the degraded processor_pref |

`scripts/demo.py` exited 0 (all five matched); it exits non-zero on any mismatch, so
`make demo` fails loudly.

Teardown: `./stop.sh -v` removed the containers and all data volumes.

## Two fixes required to make the seeded scenarios resolve as documented

The compose/Makefile/demo wiring alone surfaced a train/serve skew that declined every
scenario. Both fixes make the system match the *already-documented* expected decisions;
neither changes the intended product behavior.

1. **Shared-device ring size — train/serve skew (representation-service store query).**
   `ml/training/generate_dataset.py` defines `shared_device_ring_size` as the shared
   member count, **0 when the device is not shared** (and the fraud label fires at
   `ring_size >= 3`). The live `GraphStore` query returned `count(DISTINCT c)` over the
   device, which is **1 for a solo customer** — so the fraud model flagged every lone
   shopper as a ring member and the hard veto declined everyone. Fix: the query now
   reports 0 when only one customer uses the device (`CASE WHEN shared > 1 THEN shared
   ELSE 0 END`), matching the trained feature definition. Degradation-tolerance is
   unchanged.

2. **The fraud ring was never materialized in the seed (`scripts/seed.py`).** Each
   scenario seeded a 1:1 device->customer link, so `dev_shared` had a single owner and
   resolved to ring size 0 even for `ring_member`. The seed now links `ring_size`
   distinct customers to the one device when `scenario.ring_size > 1`, so the
   device-sharing traversal returns a genuine ring (5 for `ring_member`) and the fraud
   veto fires as documented.

Operational note: `checkout-api` honors `idempotency_key`, and `scripts/demo.py` uses a
fixed key per scenario (so the demo itself is idempotent). On a fresh stack (empty Redis)
the first demo run evaluates each scenario live. Re-running the demo after a code change
on a WARM stack replays the cached decision — flush Redis (or `./stop.sh -v && ./start.sh`)
to re-evaluate. The clean `./start.sh` verification above started from empty volumes.
