# Implementation Plan — ACIP Phase 3 (Six Agents + Graph-Projector + Carryover Fixes)

Phase 3 completes the ACIP decision loop. Phase 2 proved the core path reaches a
decision WITH NO AGENTS via the orchestrator deadline → `decide_partial` path. Phase 3
lands the six evaluating agents so real verdicts flow through `decision-engine`
aggregation (producing genuine APPROVE/DECLINE/CHALLENGE), the `graph-projector` that
owns runtime read-model population, three carryover fixes, and the compose/Makefile/
workspace wiring + a five-scenario demo. Everything REUSES `acip-common` (import name
`acip_common`) — agents never redefine schemas, config, feature transforms, the Kafka
wrapper, or the topic map; they import them.

Branch: STAY ON `feat/phase1-foundation`. Do NOT branch/reset/rebase/amend/force-push.
Do NOT modify anything under `docs/`. All new deps pinned to exact versions. Secrets via
env only. The whole stack runs with NO cloud creds (llm-gateway mock fallback; agent
`degraded=true` templated rationale acceptable; decision never blocks on the LLM).

This plan is the fallback the build loop runs if the workflow tail is not restructured.
It is also mirrored as FEAT artifacts under
`.agents/tasks/task-acip-phase3/` (task.json, context.json, features/FEAT-001..004.json).

## Environment confirmed during exploration

- `uv 0.5.4` and `docker 27.3.1` are available. Python 3.11+ (`requires-python >= 3.11`).
- Phase 2 is committed (HEAD `92f90e1`), full gate green there (66 tests). The seven
  core-path services exist under `services/`; the eight Phase-3 dirs
  (`risk-agent`, `fraud-agent`, `routing-agent`, `policy-agent`, `merchant-agent`,
  `checkout-personalization-agent`, `graph-projector`) are empty (`.gitkeep` only) and
  listed in root `pyproject.toml` `[tool.uv.workspace].exclude`.
- `acip_common` exports (verified in source): `config.Settings`/`get_settings`,
  `schemas.*` (incl. `AgentName`, `Verdict`, `Evidence`, `SharedRepresentation`,
  `AgentVerdictProducedPayload`, `TxnEvaluateRequestedPayload`, `DecisionRenderedPayload`,
  `TxnTerminalPayload`, `EventEnvelope`, `EventType`, `CandidateRoute`,
  `MethodHistoryEntry`), `features.build_feature_row`/`FEATURE_COLUMNS`,
  `kafka.EventProducer`/`EventConsumer` (manual commit; publish keyed by
  `transaction_id`), `logging.configure_logging`/`bind_trace_id`,
  `topics.{TXN_LIFECYCLE,TXN_EVALUATE,AGENT_VERDICTS,DECISION_LOG,*_DLQ,topic_for}`.
- Phase-2 contracts the agents must match (from FEAT findings + source):
  - `TxnEvaluateRequestedPayload{representation, expected_agents:[AgentName], deadline_ms}`
    is published by the orchestrator `fan_out` node to topic `txn.evaluate`
    (`EventType.TXN_EVALUATE_REQUESTED`), keyed by `transaction_id`.
  - Agents publish `AgentVerdictProducedPayload{agent, produced_at, verdict:Verdict}`
    wrapped in an `EventEnvelope` (`EventType.AGENT_VERDICT_PRODUCED`) to topic
    `agent.verdicts`, keyed by `transaction_id` — exactly what the orchestrator
    `collect_verdicts` node consumes and filters by `transaction_id`.
  - `decision-engine` reads the verdicts map keyed by `AgentName.value`
    (`risk|fraud|routing|policy|merchant|checkout_personalization`). It already reads:
    policy DECLINE and `fraud.score >= fraud_block_threshold` as hard vetoes; merchant
    `force_challenge` evidence or merchant CHALLENGE hint to upgrade APPROVE→CHALLENGE;
    personalization `rationale` as the `recommended_method`; routes ranked by
    `success_rate`. Agents must emit verdicts shaped to drive these existing branches.
  - `ml-scoring-service` `POST /v1/score` req `{model:'risk'|'fraud', model_version,
    features:dict[str,float], metadata}` → `{score, model, model_version,
    top_features:[{name,contribution}], latency_ms}`. Agents order features by
    `FEATURE_COLUMNS`.
  - `llm-gateway` `POST /v1/complete` req `{system, prompt, temperature, max_tokens,
    response_schema?, metadata}` → `{text, structured, provider, model, usage,
    latency_ms}`. Degrades to mock with no creds.
  - Postgres read-model table shapes (from `scripts/seed.py`, matched by the
    orchestrator `persistence.py` and read by checkout-api `reads.py`):
    `transactions(id PK, customer_id, amount, status, decision, created_at)`,
    `decisions(transaction_id PK, decision, composite_score, strategy)`,
    `agent_verdicts(transaction_id, agent, score, decision_hint, PK(transaction_id,
    agent))`, `event_journal(event_id PK, transaction_id, event_type, occurred_at)`.
  - Neo4j model (docs/03 §3, seed.py): `Customer`, `Device`, `MethodType`, `Processor`,
    edges `Device-[:LINKED_TO]->Customer`, `Customer-[:USED_METHOD_TYPE{successes,
    failures,last_used}]->MethodType`.
  - All services listen on container port 8000 (uvicorn `0.0.0.0:8000`), non-root uid
    10001 `python:3.11-slim`, built with `uv sync --frozen --no-dev --package <name>`,
    repo root as Docker build context. Pinned base deps: `fastapi==0.115.6`,
    `uvicorn[standard]==0.34.0`, `httpx==0.28.1`; `confluent-kafka` version used by
    acip-common; `neo4j==5.27.0`, `psycopg[binary]==3.2.3`, `redis==5.2.1` where needed.

## Resolved design decisions (doc-silent, noted inline per decision)

1. **Agents are async Kafka consumers (not FastAPI-request-driven).** docs/02 §2.2 +
   §6 and the task require: consume `txn.evaluate.requested` from `TXN_EVALUATE`,
   publish `agent.verdict.produced` to `AGENT_VERDICTS`, commit offset AFTER publish.
   Each agent therefore runs a background consumer loop (started in the FastAPI
   lifespan) while the FastAPI app exists only for `/healthz`+`/readyz` (docs/01 §6
   requires health edges on every service). Decision: lifespan starts a daemon thread
   running `EventConsumer.stream` filtered to `AGENT_VERDICT_PRODUCED`'s sibling
   `TXN_EVALUATE_REQUESTED`; `/readyz` reports ready once the consumer thread is live.
   This mirrors the orchestrator's manual-commit posture and keeps the health contract.
2. **Distinct consumer group per agent.** Each agent subscribes to `TXN_EVALUATE` with
   `group.id = "<agent-name>-agents"` so all six independently receive every
   `txn.evaluate.requested` (consumer-group fan-out: one group per agent = each gets a
   full copy). Justified in each agent's consumer module docstring.
3. **Shared agent scaffolding in a tiny per-agent `_base` module, NOT in acip-common.**
   The uniform per-agent LangGraph graph (parse_request → gather_signals → score →
   reason → assemble_verdict, docs/02 §2.2) and the consumer-loop runner are identical
   across agents. Decision: implement them ONCE in a new internal package
   `libs/acip-agent-common` (a new workspace lib, import name `acip_agent_common`) that
   depends on `acip-common`. This avoids six copies and keeps `acip-common` (the
   cross-cutting contract lib) free of agent-runtime code. Each agent injects its own
   `score_fn` + `policy` so behavior differs by injection, per docs/02 §2.2/§3.
4. **ML-backed vs rule-based signal per agent.** `risk`/`fraud` call
   `ml-scoring-service` (`model=risk` / `model=fraud`). `routing`, `policy`, `merchant`,
   `checkout_personalization` have no trained model; they compute deterministic signals
   from the representation slice (route health; sanctions/geo/limit rules; merchant
   soft-constraints; method-success ranking). Noted in each agent's scorer docstring.
5. **Policy sanctions/limits from config, not hardcoded.** Add `POLICY_SANCTIONED_GEOS`
   (default `"XX"`) and `POLICY_HIGH_VALUE_THRESHOLD` (default `4000.0`) and
   `MERCHANT_HIGH_VALUE_CHALLENGE` (default `4000.0`) to `acip_common.config.Settings`
   with env aliases + `.env.example`, so the five seeded scenarios resolve
   (`sanctioned_geo` → policy DECLINE via `home_geo == XX`; `high_value_midrisk` →
   merchant/`force_challenge`). This is the one `acip-common` addition in Phase 3; it
   adds no dependency. Reconciles with seed.py scenario shapes.
6. **Runtime read-model bootstrap (fix A.1) in a shared `acip_common.bootstrap` helper.**
   `ensure_read_model_schema(postgres_dsn)` issues the exact `CREATE TABLE IF NOT EXISTS`
   for the four tables with columns IDENTICAL to `scripts/seed.py`. Both the
   graph-projector (on startup) and the orchestrator (before first persist) call it, so
   a fresh stack with NO seed still persists and serves reads. This is additive to
   acip-common (no dependency change).
7. **graph-projector consumes `txn.lifecycle` + `agent.verdicts` + `decision.log`** (one
   consumer, three topics, group `graph-projector`), projecting idempotent upserts into
   Neo4j (entities + relationships, keyed by id) and Postgres read models (keyed by
   `event_id`/`transaction_id`), writing `event_journal` rows for every event. It calls
   the bootstrap helper on startup (fix A.1). Decision: it does NOT remove the
   orchestrator's own persist — both upsert the same rows idempotently (`ON CONFLICT DO
   UPDATE`), so whichever runs is safe; the projector is the always-on owner that keeps
   reads populated even when a transaction was created by a path that skipped the
   orchestrator persist.

## Per-service skeleton (identical, matches Phase 2)

```
services/<name>/
├── Dockerfile              # python:3.11-slim, uv sync --frozen --no-dev --package <name>, non-root 10001
├── pyproject.toml          # uv workspace member; acip-common + acip-agent-common = { workspace = true }
├── src/<module>/__init__.py
├── src/<module>/main.py    # FastAPI /healthz + /readyz; lifespan starts the consumer loop
├── src/<module>/scorer.py  # the agent's numeric signal (pure, unit-tested)
├── src/<module>/agent.py   # policy + verdict assembly wiring (injected into the shared runner)
└── tests/test_*.py         # pytest unit tests, llm-gateway + kafka + ml-scoring mocked
```

Workspace wiring per new member (exactly as Phase 2 did): REMOVE the dir from root
`pyproject.toml` `[tool.uv.workspace].exclude`, add it under `[tool.uv.sources]` as
`{ workspace = true }` AND to `[dependency-groups].dev`, then `uv sync`.

---

## Ordered build sequence

- [ ] 1. **Carryover fixes + shared bootstrap + agent-scaffolding lib + config keys.**
      (a) Add `libs/acip-common/src/acip_common/bootstrap.py` with
      `ensure_read_model_schema(postgres_dsn)` running the exact `CREATE TABLE IF NOT
      EXISTS` for `transactions`/`decisions`/`agent_verdicts`/`event_journal` with
      columns identical to `scripts/seed.py` (reconcile drift); export in `__all__`; add
      a unit test (mock psycopg connection, assert all four `CREATE TABLE IF NOT EXISTS`
      issued). (b) FIX A.1: call `ensure_read_model_schema` in the orchestrator
      `persist_decision` before the upserts (so a fresh stack with no seed persists).
      (c) FIX A.2: make checkout-api `PostgresReadModel._fetch` treat a missing table
      (`psycopg.errors.UndefinedTable`) as "unknown id" → return `None` → 404, never
      500; a genuinely-unknown id already returns None/404 — add tests for both. (d) FIX
      A.3: on the ASYNC `/v1/checkout` branch, store an idempotency record so a repeated
      key replays like sync (same `transaction_id`, no duplicate eval/charge): write the
      idempotency record on the async path too (reusing `IdempotencyStore`), and on
      replay in async mode return the stored `{transaction_id, status_url}` — add a test
      asserting a repeated async key returns the SAME transaction_id and does not emit a
      second `txn.created`. (e) Add config keys `POLICY_SANCTIONED_GEOS` (default
      `"XX"`), `POLICY_HIGH_VALUE_THRESHOLD` (default `4000.0`),
      `MERCHANT_HIGH_VALUE_CHALLENGE` (default `4000.0`) to `Settings` + `.env.example`
      (comma-split validator for the geo list, like `enabled_method_types`). (f) Create
      the `libs/acip-agent-common` workspace lib (`acip_agent_common`): the uniform
      per-agent LangGraph `StateGraph` (parse_request → gather_signals → score → reason
      → assemble_verdict, docs/02 §2.2), an `AgentRunner` that consumes `TXN_EVALUATE`,
      runs the graph, publishes `agent.verdict.produced` to `AGENT_VERDICTS`, and commits
      AFTER publish; an `llm_rationale(client, ...)` helper with a TEMPLATED fallback
      (`degraded=True`) so it never blocks; a `make_health_app(runner)` returning a
      FastAPI app with `/healthz`+`/readyz`. Add it to root workspace members/sources/dev.
      Files: `libs/acip-common/src/acip_common/bootstrap.py`,
      `libs/acip-common/src/acip_common/config.py`, `libs/acip-common/tests/test_bootstrap.py`,
      `.env.example`,
      `services/commerce-orchestrator/src/commerce_orchestrator/persistence.py`,
      `services/checkout-api/src/checkout_api/reads.py`,
      `services/checkout-api/src/checkout_api/main.py`,
      `services/checkout-api/src/checkout_api/idempotency.py` (if a reserve/async helper
      is needed),
      `services/checkout-api/tests/test_checkout.py`,
      `libs/acip-agent-common/{pyproject.toml,src/acip_agent_common/{__init__,graph,runner,rationale,health}.py,tests/test_graph.py}`,
      `pyproject.toml`.
      Reuses: `Settings`, `EventProducer`/`EventConsumer`, `topic_for`, `EventEnvelope`,
      `EventType`, `TxnEvaluateRequestedPayload`, `AgentVerdictProducedPayload`,
      `Verdict`, `SharedRepresentation`, `AgentName`, `configure_logging`/`bind_trace_id`.
      Verify: `uv sync`; `uv run pytest libs/acip-common libs/acip-agent-common
      services/checkout-api services/commerce-orchestrator` all pass (incl. the two
      new 404-on-missing-table tests and the async-idempotency replay test);
      `uv run ruff check .` + `uv run black --check .` + `uv run mypy libs services`
      clean.

- [ ] 2. **The six agents (one coherent same-pattern unit).** Create all six services
      from the shared skeleton, each injecting its own scorer + policy into the
      `acip_agent_common` runner/graph. Each: consume `txn.evaluate.requested`, read its
      slice of the shared representation (NO feature rebuild), compute the numeric
      signal, get an LLM rationale via `llm-gateway` with a templated fallback
      (`degraded=True`), assemble a `Verdict`, publish `agent.verdict.produced` keyed by
      `transaction_id`, commit AFTER publish. FastAPI `/healthz`+`/readyz`, non-root
      `python:3.11-slim` Dockerfile, `Settings` config, structured logging + `trace_id`
      from the envelope, pytest unit tests for the scoring/verdict logic with llm-gateway
      + kafka mocked.
      - `risk-agent`: calls `ml-scoring-service` `model=risk` with the representation
        features; `score` = risk prob; `decision_hint` banded (APPROVE/CHALLENGE/DECLINE)
        from `approve_max`/`challenge_max`. (`AgentName.RISK`.)
      - `fraud-agent`: calls `ml-scoring-service` `model=fraud`, emphasizing graph
        signals (`shared_device_ring_size`, `velocity_1h`); emits a high score for the
        `ring_member` scenario so the engine's `fraud.score >= fraud_block_threshold`
        hard-veto fires → DECLINE. (`AgentName.FRAUD`.)
      - `routing-agent` (docs/02 §3.1, ROUTE-SCORING): score EVERY
        `representation.candidate_routes` on predicted `success × cost × latency`
        (weights from config/defaults), return ranked routes + `chosen_route`; emit a
        `ROUTE` hint carrying the ranked routes as `evidence` and `chosen_route` so the
        engine's routing overlay surfaces them. (`AgentName.ROUTING`.)
      - `policy-agent`: allow/deny + `violated_rules[]`; DENY is a hard veto. DENY when
        `transaction.home_geo`/`txn_geo` in `POLICY_SANCTIONED_GEOS` or amount over a
        configured per-merchant limit; emit `decision_hint=DECLINE` with the violated
        rules as evidence so the engine's policy hard-veto fires (`sanctioned_geo` →
        DECLINE). (`AgentName.POLICY`.)
      - `merchant-agent`: merchant soft-constraints + preference adjustments; advisory.
        Emit a `force_challenge` evidence signal (value ≥ 1.0) or a CHALLENGE hint when
        amount ≥ `MERCHANT_HIGH_VALUE_CHALLENGE` so the engine upgrades APPROVE→CHALLENGE
        (`high_value_midrisk` → CHALLENGE). Never a hard veto. (`AgentName.MERCHANT`.)
      - `checkout-personalization-agent` (docs/02 §3.2, ADVISORY): rank methods by
        predicted success from `representation.method_history`, return
        `recommended_method` + confidence; put the recommended method in the verdict
        `rationale` (the engine reads `_recommended_method` from `personalization.rationale`).
        Never vetoes. (`AgentName.CHECKOUT_PERSONALIZATION`.)
      Files: `services/{risk-agent,fraud-agent,routing-agent,policy-agent,merchant-agent,checkout-personalization-agent}/{Dockerfile,pyproject.toml,src/<module>/{__init__,main,scorer,agent}.py,tests/test_*.py}`;
      root `pyproject.toml` (remove the six from exclude; add to sources + dev).
      Reuses: `acip_agent_common` runner/graph/rationale/health, `Verdict`, `Evidence`,
      `AgentName`, `SharedRepresentation`, `CandidateRoute`, `TxnEvaluateRequestedPayload`,
      `AgentVerdictProducedPayload`, `EventProducer`/`EventConsumer`, `topic_for`,
      `Settings`, `build_feature_row`/`FEATURE_COLUMNS` (for feature ordering only).
      Verify: `uv sync`; `uv run pytest services/risk-agent services/fraud-agent
      services/routing-agent services/policy-agent services/merchant-agent
      services/checkout-personalization-agent` all pass (each: score→verdict with
      ml-scoring + llm-gateway mocked, templated-fallback degraded test, publish-then-
      commit ordering test); `uv run ruff check .` + `uv run mypy libs services` clean.

- [ ] 3. **Reconcile orchestrator expected_agents + decision-engine keys.** The
      orchestrator already fans out to all six `AgentName` and `collect_verdicts` waits
      for all six; the decision-engine already keys on all six `AgentName.value`. Confirm
      no gap: `collect_verdicts` returns the full six-verdict map on the all-received
      path and `route_after_collect` routes to `decide` (not `decide_partial`) so real
      APPROVE/DECLINE/CHALLENGE is produced. Add an orchestrator unit test that feeds six
      mocked verdicts (one per `AgentName`) through `collect_verdicts` → `decide` and
      asserts the decision reflects aggregation (e.g. a fraud-veto verdict → DECLINE),
      proving the six verdicts flow end-to-end instead of always `decide_partial`.
      Files: `services/commerce-orchestrator/tests/test_graph.py` (add the six-verdict
      aggregation test); no production change expected unless a gap is found — if the
      `expected_agents` set or a key mismatches, fix it in `nodes.py`/`clients.py`.
      Reuses: `AgentName`, `Verdict`, `AgentVerdictProducedPayload`.
      Verify: `uv run pytest services/commerce-orchestrator` passes incl. the new
      six-verdict → aggregated-decision test.

- [ ] 4. **graph-projector (Kafka consumer service, docs/01 §2, docs/03).** Create
      `services/graph-projector/` from the skeleton: one `EventConsumer` subscribed to
      `txn.lifecycle` + `agent.verdicts` + `decision.log` (group `graph-projector`),
      dispatching by `event_type` to idempotent projectors — Neo4j upserts
      (`Customer`/`Device`/`Transaction`/`Processor` + relationships per docs/03 §3,
      MERGE keyed by id) and Postgres read-model upserts (`transactions`/`decisions`/
      `agent_verdicts` `ON CONFLICT DO UPDATE`, plus an `event_journal` row per event
      keyed by `event_id`). It OWNS runtime read-model population and calls
      `acip_common.bootstrap.ensure_read_model_schema` on startup (fix A.1). Health edge
      (`/healthz`+`/readyz`, ready once the consumer thread is live), structured logging
      + `trace_id`, non-root `python:3.11-slim` Dockerfile, `Settings` config. Tests with
      Kafka/Neo4j/Postgres mocked: assert each `event_type` routes to the right projector
      and that upserts are idempotent (same event applied twice → one row/one node).
      Files: `services/graph-projector/{Dockerfile,pyproject.toml,src/graph_projector/{__init__,main,consumer,neo4j_projector,postgres_projector}.py,tests/test_projector.py}`;
      root `pyproject.toml` (remove from exclude; add to sources + dev).
      Reuses: `EventConsumer`, `topic_for`, `EventEnvelope`, `EventType`,
      `TxnTerminalPayload`, `AgentVerdictProducedPayload`, `DecisionRenderedPayload`,
      `TxnCreatedPayload`, `Settings`, `acip_common.bootstrap.ensure_read_model_schema`.
      Deps: `neo4j==5.27.0`, `psycopg[binary]==3.2.3`.
      Verify: `uv sync`; `uv run pytest services/graph-projector` passes (routing +
      idempotency tests); `uv run ruff check .` + `uv run mypy libs services` clean.

- [ ] 5. **Compose + Makefile + workspace + demo wiring.** Add the seven new services
      (six agents + graph-projector) to `deploy/docker-compose.yml`: `build` from each
      Dockerfile with repo-root context, `env_file: ../.env (required:false)` + inline
      env defaults, `depends_on` infra healthchecks (agents on `redpanda` healthy +
      `llm-gateway`/`ml-scoring-service` started; graph-projector on `redpanda`/`neo4j`/
      `postgres` healthy), all on `acip-net`, NO new host ports (only checkout-api
      stays published). Agents set `LLM_GATEWAY_URL`/`ML_SCORING_URL` to call those
      services over HTTP (NO model mount on agents — only ml-scoring-service mounts
      `ml/models`). Update Makefile `up` to include the new services (the generic
      `$(COMPOSE) up -d` already starts all; confirm `up` brings up the full stack).
      Replace `scripts/demo.py` with a five-scenario driver that POSTs each seeded
      scenario to `/v1/checkout` and prints the decision, asserting the expected outcome:
      `clean_shopper`→APPROVE, `ring_member`→DECLINE (fraud), `high_value_midrisk`→
      CHALLENGE, `sanctioned_geo`→DECLINE (policy), `unhealthy_preferred_route`→APPROVE
      on alternate route. Add per-scenario sample JSON (or build bodies in `demo.py` from
      the seed scenario fields). Keep `make seed` as the prerequisite that populates the
      graph so the agents produce the expected verdicts.
      Files: `deploy/docker-compose.yml`, `Makefile`, `scripts/demo.py`,
      (optional) `scripts/scenarios/*.json`.
      Reuses: n/a (wiring).
      Verify: `docker compose -f deploy/docker-compose.yml config` validates (22 services
      enumerated, no YAML/schema errors); `make help` lists targets; `uv run ruff check .`
      clean on the updated `demo.py`.

- [ ] 6. **Full-stack verification gate.** Run the whole gate from repo root: `uv sync`;
      `uv run ruff check .`; `uv run black --check .`; `uv run mypy libs services`;
      `uv run pytest libs/acip-common libs/acip-agent-common services` across acip-common,
      acip-agent-common, and all 14 services; `docker compose -f deploy/docker-compose.yml
      config`. If Docker is available: `make up`, `make seed`, then `make demo` and
      confirm all five scenarios return their expected decisions (real agent verdicts,
      NO cloud creds — llm-gateway on mock, agents `degraded=true` templated rationale
      acceptable). If Docker is unavailable, substitute an in-process integration test
      that drives six real agent scorers → a real `aggregate` call per scenario and
      asserts the five expected decisions, and say so explicitly. Clean up any temp files.
      Files: none (verification only; may add one integration test under
      `services/commerce-orchestrator/tests/` or `scripts/`).
      Verify: all lint/type/test commands exit 0; `docker compose config` valid; the
      five-scenario demo (live or in-process) yields APPROVE/DECLINE/CHALLENGE/DECLINE/
      alternate-route as expected.

## Verification commands (reference)

```
uv sync
uv run ruff check .
uv run black --check .
uv run mypy libs services
uv run pytest libs/acip-common libs/acip-agent-common services
docker compose -f deploy/docker-compose.yml config
# live five-scenario demo (after make up + make seed):
make demo
```

## Assumptions / gaps noted

- Agents run as background Kafka consumers with a thin FastAPI health edge (decision 1).
  If a reviewer prefers a request-driven agent, the scorer/verdict logic is isolated in
  `scorer.py`/`agent.py` and reusable unchanged.
- `routing`/`policy`/`merchant`/`checkout_personalization` are rule/representation-driven
  (no trained model exists for them); their thresholds come from `Settings` (decision 5).
- Both the orchestrator persist and the graph-projector write the same read-model rows
  idempotently; this is intentional redundancy so reads stay populated (decision 7).
- Live `make up` smoke depends on a running Docker daemon; if unavailable the gate falls
  back to an in-process five-scenario integration test (noted in step 6).
