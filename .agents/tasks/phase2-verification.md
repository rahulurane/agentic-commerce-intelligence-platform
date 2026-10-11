# ACIP Phase 2 — Verification Evidence

This file records the commands run to verify each Phase 2 FEAT and their results, so
the reviewer does not have to re-run the suites. Append-only: each FEAT adds its own
section. (FEAT-001/002/003 evidence lives in their respective
`.agents/tasks/task-acip-phase2-core-path/features/FEAT-00x.json` `findings` fields;
this document starts at FEAT-004, which owns the full-stack wiring + end-to-end gate.)

---

## FEAT-004 — checkout-api + compose/Makefile wiring + core-path smoke

Branch: `feat/phase1-foundation` (no new branch; no commit made in this step — the
finalize step commits).

### What was built

- `services/checkout-api/` — FastAPI public edge, uv workspace member, path dep on
  `acip-common`, non-root `python:3.11-slim` Dockerfile, `GET /healthz` + `/readyz`,
  structured logging + `trace_id`.
  - `POST /v1/checkout`: Pydantic validation (422 on bad/extra fields via
    `CheckoutRequest` reusing `PaymentMethodRef`/`CheckoutContext`); mints
    `txn_<hex16>`; honors `idempotency_key` (Redis-backed `IdempotencyStore` — repeat
    key returns the ORIGINAL stored decision, never re-calls the orchestrator / never
    re-charges); emits `txn.created` `EventEnvelope` (payload `TxnCreatedPayload`) to
    the `txn.lifecycle` topic via `topic_for` + `EventProducer`. DEFAULT **sync** mode
    calls `ORCHESTRATOR_URL` `POST /internal/evaluate` and returns the docs/06 §1
    decision JSON (`transaction_id, decision, route, composite_score, explanation,
    recommended_method, verdicts{}, route_alternatives, degraded_agents, partial,
    trace_id`). **async** mode (`?mode=async` or header `X-ACIP-Mode: async`) returns
    `202` + `{transaction_id, status_url}`.
  - `GET /v1/transactions/{id}` and `/v1/transactions/{id}/explain`: read the Postgres
    read models the orchestrator `finalize` persisted (`transactions`, `decisions`,
    `agent_verdicts` — shapes per `scripts/seed.py`), via `reads.PostgresReadModel`
    behind a `ReadModel` protocol; `404` on unknown id.
  - Pinned deps: `fastapi==0.115.6`, `uvicorn[standard]==0.34.0`, `httpx==0.28.1`,
    `redis==5.2.1`, `psycopg[binary]==3.2.3`.
- Workspace wiring: removed `services/checkout-api` from root
  `pyproject.toml [tool.uv.workspace].exclude`; added `checkout-api = { workspace =
  true }` to `[tool.uv.sources]` and `"checkout-api"` to `[dependency-groups].dev`.
- `deploy/docker-compose.yml`: added ALL SEVEN services (checkout-api,
  commerce-orchestrator, representation-service, ml-scoring-service, llm-gateway,
  decision-engine, payment-processor-sim), each `build:` from its Dockerfile with
  `context: ..` (repo root) so `acip-common` is available; `env_file: ../.env`
  (`required: false`) + inline `environment:` defaults; `depends_on` the infra
  healthchecks + sensible inter-service ordering; all on `acip-net`; `ml/models`
  mounted read-only into ml-scoring-service; ONLY checkout-api publishes a host port
  (`8080:8000`). Infra services unchanged.
- `Makefile`: `build`/`up` now cover infra + services; added `up-infra` (infra only),
  `smoke` (+ `demo` alias) running `scripts/demo.py`, and fleshed out `logs`
  (`compose logs -f`) and `test` (`pytest libs/acip-common services`). Phase 1
  infra/ml/seed/tooling targets preserved.
- `scripts/sample_checkout.json` (clean low-value UPI txn) + `scripts/demo.py`
  (POSTs the sample to the running checkout-api and prints the decision).

### Verification commands + results

| Command | Result |
|---|---|
| `uv sync` | PASS — `Resolved 78 packages`, workspace (incl. checkout-api) resolves |
| `uv run ruff check .` | PASS — `All checks passed!` |
| `uv run black --check .` | PASS — `58 files would be left unchanged` |
| `uv run mypy libs/acip-common/src services` | PASS — `Success: no issues found in 47 source files` (strict) |
| `uv run pytest libs/acip-common services -q` | PASS — **77 passed** (66 prior + 11 new checkout-api) |
| `uv run pytest services/checkout-api -v` | PASS — 11 passed (9 unit + 2 integration) |
| `docker compose -f deploy/docker-compose.yml config -q` | PASS — validates |
| `docker compose -f deploy/docker-compose.yml config --services` | PASS — lists 8 infra + 7 services (15 total) |
| `make help` | PASS — lists updated build/up/up-infra/down/topics/train/seed/lint/format/test/demo/smoke/logs |

New checkout-api tests (all green):
- `test_invalid_body_returns_422`, `test_unknown_field_returns_422` — Pydantic 422.
- `test_sync_happy_path_returns_decision` — sync decision shape + `txn.created` emitted.
- `test_idempotent_repeat_returns_original_and_does_not_recharge` — same key → same
  decision, orchestrator called exactly once (no re-charge).
- `test_async_mode_returns_202_with_status_url`, `test_async_mode_via_header` — 202 shape.
- `test_get_transaction_found_and_404`, `test_explain_found_and_404` — GET endpoints +
  404 against a fake read model.
- `test_health_and_ready` — probes.
- `test_core_path_no_agents_returns_decision` — see below.
- `test_edge_and_orchestrator_apps_are_the_production_modules`.

### Core-path smoke — what was verified vs NOT

**Docker daemon was DOWN/unavailable in this environment** (`docker info` → daemon
down; `docker ps` → cannot list), so a LIVE stack run (`make up` + curl) was NOT
performed. This is reported honestly — no live run is claimed.

Per the FEAT-004 fallback instruction, the no-agents end-to-end path is instead proven
by an **in-process integration smoke**
(`services/checkout-api/tests/test_integration_core_path.py::
test_core_path_no_agents_returns_decision`, PASSED): it drives the REAL public edge
(`checkout-api` `POST /v1/checkout` sync mode, real `CheckoutRequest` validation,
real `_public_decision` shaping) → the REAL commerce-orchestrator LangGraph graph
(`build_graph` / `run_evaluation`, real `collect_verdicts` deadline → conditional edge
→ `decide_partial`) → the REAL `decision_engine.aggregator.aggregate`, with only the
leaf inter-service clients (representation/decision-engine/payment-sim HTTP),
Kafka producer/consumer, Postgres, and Redis mocked. With ZERO verdicts the deadline
elapses, the missing-verdict policy (`MISSING_RISK_FRAUD_POLICY`, default `CHALLENGE`)
applies, and the client receives a decision JSON (`decision=CHALLENGE`,
`transaction_id=txn_...`, `partial=true`, `trace_id` set) — the Phase 2 no-agents
guarantee, surfaced through the actual edge the demo hits. llm-gateway is not on this
core path (it is an agent-tier dependency), so no cloud creds are involved.

To run the live smoke once Docker is available:
```
make up            # infra + the 7 services; checkout-api on :8080
make seed          # create the Postgres read-model tables + demo rows
make smoke         # POST scripts/sample_checkout.json, print the decision
# or: curl -s -X POST localhost:8080/v1/checkout -H 'content-type: application/json' \
#        -d @scripts/sample_checkout.json
make down
```
