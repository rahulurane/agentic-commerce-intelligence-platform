# Implementation Plan — ACIP Phase 2 (Core Decision Path)

Phase 2 builds the SEVEN core-path services that make a transaction flow end-to-end and
produce a decision WITH NO AGENTS and NO CLOUD CREDS. The six agents and graph-projector
are Phase 3 and are NOT built here. Everything reuses `acip-common` (import name
`acip_common`) — services never redefine schemas, config, feature transforms, or the
Kafka wrapper; they import them.

This plan is the fallback the build loop runs if the workflow tail is not restructured.
It is also mirrored as FEAT artifacts under `.agents/tasks/task-acip-phase2-core-path/`.

## Environment confirmed during exploration

- `uv 0.5.4` and `docker` are available. Python 3.11+ (root `requires-python = ">=3.11"`).
- Phase 1 is committed (HEAD b799ab4). `libs/acip-common` exports (verified in source):
  - `acip_common.config.Settings` / `get_settings()` — all docs/07 §2 env vars with defaults.
  - `acip_common.schemas` — `EventEnvelope`, `EventType`, `SharedRepresentation`,
    `TransactionCore`, `MethodHistoryEntry`, `CandidateRoute`, `Verdict`, `Evidence`,
    `DecisionHint`, `MethodType`, `AgentName`, `PaymentMethodRef`, `CheckoutContext`,
    `TxnCreatedPayload`, `TxnEvaluateRequestedPayload`, `AgentVerdictProducedPayload`,
    `DecisionRenderedPayload`, `TxnTerminalPayload`.
  - `acip_common.features` — `build_feature_row(raw)` + `FEATURE_COLUMNS` (7 columns).
  - `acip_common.kafka` — `EventProducer` (publish envelope keyed by `transaction_id`),
    `EventConsumer` (manual-commit, `poll`/`stream`/`commit`/`close`).
  - `acip_common.logging` — `configure_logging`, `bind_trace_id`, `get_trace_id`.
- Models already trained locally under `ml/models/` (gitignored): `risk-xgb-2026.10.10.json`
  (XGBoost `save_model` JSON), `fraud-lgbm-2026.10.10.txt` (LightGBM booster text), and
  `model_card.json` indexing them (`models.<risk|fraud>.{version,artifact,algo}`).
  **The system clock is 2026**, so artifact dates vary — services MUST discover artifacts
  via `model_card.json`, never a hardcoded date/filename.

## Gaps found and resolved decisions (doc-silent, noted inline)

1. **Kafka topic names ≠ event-type strings.** The compose `kafka-init` creates topics
   `txn.lifecycle`, `txn.evaluate`, `agent.verdicts`, `decision.log` (+ `.dlq`), and
   docs/03 §2 maps event types onto those four topics. `acip-common` has NO topic
   constants. Decision: add a `acip_common.topics` module (TOPIC name constants +
   `topic_for(event_type)` map) so every service agrees on the mapping. This is the one
   addition to `acip-common` in Phase 2; it adds no new dependency.
2. **Model artifact discovery.** Resolve the active artifact from `model_card.json`
   (`models.risk.artifact`, `models.fraud.artifact`) at startup; the models dir path is
   config (`ML_MODELS_DIR`, default `/app/ml/models` in-container, `ml/models` local).
3. **Heuristic fallback** (docs/05 §5): when artifacts are missing, ml-scoring serves a
   deterministic function of the feature row so the path still runs; `model_version` is
   reported as `heuristic-v1` and `degraded`-style note logged.
4. **Orchestrator ↔ checkout-api sync trigger.** Use `POST /internal/evaluate` on the
   orchestrator (docs/06 §2) as the sync entry; it runs the LangGraph graph to a decision
   and returns the decision JSON. checkout-api still emits `txn.created` for the event log.
5. **Minimal Postgres persistence** for GET/`/explain`: the orchestrator's `finalize`
   node writes `transactions`, `decisions`, `agent_verdicts` (table shapes already created
   by `scripts/seed.py`). `/explain` reads these. No graph-projector (Phase 3).
6. **Config additions.** New env keys needed by Phase 2 services are added to
   `acip_common.config.Settings` + `.env.example` with defaults: service URLs
   (`REPRESENTATION_URL`, `ML_SCORING_URL`, `LLM_GATEWAY_URL`, `DECISION_ENGINE_URL`,
   `PAYMENT_PROCESSOR_URL`, `ORCHESTRATOR_URL`), `ML_MODELS_DIR`, `SIM_FAILURE_MODE`,
   `MISSING_RISK_FRAUD_POLICY` (default `CHALLENGE`). All optional with defaults so the
   stack boots with no `.env`.

## Per-service file layout (identical skeleton)

```
services/<name>/
├── Dockerfile              # python:3.11-slim, uv install, non-root user
├── pyproject.toml          # uv workspace member, path dep on acip-common
├── src/<module>/__init__.py
├── src/<module>/main.py    # FastAPI app: /healthz, /readyz + routes
├── src/<module>/...        # service logic modules
└── tests/test_*.py         # pytest unit tests
```
Every service adds `services/<name>` to root `pyproject.toml` `[tool.uv.workspace] members`
and declares `acip-common = { workspace = true }` under `[tool.uv.sources]`.

---

## Ordered build sequence

- [ ] 1. **Carryover KAFKA_BOOTSTRAP fix + shared topic map + config/workspace prep.**
      Change `kafka_bootstrap` default `kafka:9092` → `redpanda:9092` in
      `libs/acip-common/src/acip_common/config.py` and `KAFKA_BOOTSTRAP` in `.env.example`
      (matches compose `--advertise-kafka-addr=PLAINTEXT://redpanda:9092`). Confirm no
      other `kafka:9092` alias remains (grep). Add `acip_common/topics.py` with constants
      `TXN_LIFECYCLE="txn.lifecycle"`, `TXN_EVALUATE="txn.evaluate"`,
      `AGENT_VERDICTS="agent.verdicts"`, `DECISION_LOG="decision.log"`, DLQ variants, and
      `topic_for(event_type: EventType) -> str` per docs/03 §2; export in `__all__`; add a
      unit test. Add the Phase 2 config keys (gap #6) to `Settings` + `.env.example`.
      Add `services/*` to root `pyproject.toml` workspace members glob.
      Files: `libs/acip-common/src/acip_common/config.py`,
      `libs/acip-common/src/acip_common/topics.py`,
      `libs/acip-common/tests/test_topics.py`, `.env.example`, `pyproject.toml`.
      Verify: `uv run pytest libs/acip-common` passes; `uv run ruff check libs` clean;
      `grep -rn "kafka:9092" .` returns nothing outside docs.

- [ ] 2. **payment-processor-sim** (FastAPI) — `POST /v1/charge` (docs/06 §2). Simulated
      acquirer driven by `SIM_APPROVAL_RATE`, `SIM_LATENCY_MS`, `SIM_FAILURE_MODE` from
      `Settings`. Returns `{status: CAPTURED|DECLINED, processor, auth_code, latency_ms}`
      or a failure per `SIM_FAILURE_MODE`. Deterministic under a seed for tests. `/healthz`
      + `/readyz`. No inter-service deps (build first among callees).
      Files: `services/payment-processor-sim/{Dockerfile,pyproject.toml,src/payment_processor_sim/{__init__,main,sim}.py,tests/test_sim.py}`.
      Reuses: `Settings`, `configure_logging`.
      Verify: `uv run pytest services/payment-processor-sim` passes (approval/decline/failure branches).

- [ ] 3. **ml-scoring-service** (FastAPI) — `POST /v1/score` (docs/05 §2). At startup load
      risk + fraud artifacts resolved from `model_card.json` in `ML_MODELS_DIR` (XGBoost
      from `.json`, LightGBM from `.txt`), do a warm-up prediction, gate `/readyz` on load.
      Score the posted `features` dict (ordered by `FEATURE_COLUMNS`), return
      `{score, model, model_version, top_features, latency_ms}`; `top_features` from
      gain/contribution. If artifacts missing, serve the deterministic heuristic
      (`model_version="heuristic-v1"`) so the path still runs (docs/05 §5).
      Files: `services/ml-scoring-service/{Dockerfile,pyproject.toml,src/ml_scoring_service/{__init__,main,loader,scorer,heuristic}.py,tests/test_scoring.py}`.
      Reuses: `FEATURE_COLUMNS`, `Settings`, `configure_logging`. Deps: `xgboost`,
      `lightgbm`, `numpy` (pinned to match `ml/pyproject.toml`).
      Verify: `uv run pytest services/ml-scoring-service` passes incl. heuristic-fallback test
      (no artifacts) and score-shape test.

- [ ] 4. **llm-gateway** (FastAPI) — `POST /v1/complete` (docs/04). Define `LLMProvider`
      Protocol (`complete`, `health`) + `LLMRequest`/`LLMResponse` dataclasses (docs/04 §2).
      Implement `MockAdapter` (deterministic structured rationale, no network) and
      `GeminiAdapter` (Google GenAI/Vertex via ADC, imported lazily). Provider chosen by
      `LLM_PROVIDER`; `LLM_FALLBACK_PROVIDER=mock`. Timeout + retry + circuit breaker that
      degrades to mock when primary fails or ADC creds absent (stack runs with NO creds).
      Structured rationale + evidence per `response_schema`.
      Files: `services/llm-gateway/{Dockerfile,pyproject.toml,src/llm_gateway/{__init__,main,providers/{base,mock,gemini}.py,breaker}.py,tests/test_gateway.py}`.
      Reuses: `Settings`, `configure_logging`. Gemini SDK optional dep, lazily imported.
      Verify: `uv run pytest services/llm-gateway` passes incl. provider-selection + fallback-to-mock
      (no creds) tests.

- [ ] 5. **decision-engine** (FastAPI) — `POST /v1/decide` (docs/06 §2) implementing docs/02
      §5: (1) hard vetoes (policy deny OR `fraud_score >= FRAUD_BLOCK_THRESHOLD` → DECLINE);
      (2) weighted composite `W_RISK·risk + W_FRAUD·fraud` banded by `APPROVE_MAX`/
      `CHALLENGE_MAX`; (3) routing overlay (top candidate route + alternatives);
      (4) merchant soft constraints; (5) checkout-personalization advisory
      `recommended_method`. Apply missing-verdict policy: missing risk/fraud →
      `MISSING_RISK_FRAUD_POLICY` (default CHALLENGE); missing advisory → defaults. All
      thresholds/weights from `Settings`, never hardcoded. Output = `DecisionRenderedPayload`
      shape (docs/02 §5). Pure aggregation lives in a testable module.
      Files: `services/decision-engine/{Dockerfile,pyproject.toml,src/decision_engine/{__init__,main,aggregator}.py,tests/test_aggregator.py}`.
      Reuses: `Settings`, `Verdict`, `DecisionHint`, `AgentName`, `DecisionRenderedPayload`,
      `CandidateRoute`.
      Verify: `uv run pytest services/decision-engine` passes covering: fraud veto, policy
      deny veto, approve band, challenge band, decline band, missing risk/fraud → CHALLENGE,
      all-missing (Phase 2 zero-verdict) → CHALLENGE.

- [ ] 6. **representation-service** (FastAPI) — builds the SHARED TRANSACTION REPRESENTATION
      (docs/03 §8). `POST /v1/representation` takes the transaction payload, hydrates graph
      signals from Neo4j (ring size, 30d count, chargebacks, method history, candidate
      routes per `scripts/seed.py` model) + hot features from Redis, computes features via
      `build_feature_row`, returns a `SharedRepresentation`. Cache by `transaction_id` in
      Redis. Sparse-graph fallback to sensible defaults so the path runs on an unseeded DB.
      `/readyz` tolerates store absence (degraded-but-up).
      Files: `services/representation-service/{Dockerfile,pyproject.toml,src/representation_service/{__init__,main,builder,stores}.py,tests/test_builder.py}`.
      Reuses: `build_feature_row`, `FEATURE_COLUMNS`, `SharedRepresentation`,
      `TransactionCore`, `CandidateRoute`, `MethodHistoryEntry`, `Settings`. Deps: `neo4j`,
      `redis` (pinned).
      Verify: `uv run pytest services/representation-service` passes incl. sparse-graph
      fallback (mocked stores) producing a valid `SharedRepresentation` with all 7 features.

- [ ] 7. **commerce-orchestrator** (FastAPI + LangGraph) — the brain (docs/02 §2.1). Build a
      `StateGraph` with nodes `build_representation` (call representation-service) → `fan_out`
      (publish `txn.evaluate.requested` to `txn.evaluate` via `EventProducer`) →
      `collect_verdicts` (consume `agent.verdicts` keyed by `transaction_id` with deadline
      `DECISION_DEADLINE_MS`; conditional edge `all_received`→`decide`, `deadline`→
      `decide_partial`) → `decide`/`decide_partial` (call decision-engine) → `execute`
      (APPROVE/ROUTE → call payment-processor-sim; else short-circuit) → `finalize` (emit
      terminal event on `txn.lifecycle`, persist decision trace to Postgres). Checkpoint
      state in Redis (LangGraph Redis checkpointer or an equivalent `acip_common.kafka`-free
      Redis saver) for crash-resume. **Phase 2 critical path:** with no agents, the deadline
      elapses with zero verdicts → `decide_partial` applies the missing-verdict policy and
      the flow still produces a decision; log this clearly. Expose `POST /internal/evaluate`
      (docs/06 §2) that runs the graph synchronously and returns the decision JSON.
      Files: `services/commerce-orchestrator/{Dockerfile,pyproject.toml,src/commerce_orchestrator/{__init__,main,graph,nodes,clients,persistence}.py,tests/test_graph.py}`.
      Reuses: `EventProducer`, `EventConsumer`, `topic_for`, `EventEnvelope`, `EventType`,
      `TxnEvaluateRequestedPayload`, `SharedRepresentation`, `AgentName`, `Settings`,
      `bind_trace_id`. Deps: `langgraph`, `httpx`, `redis`, `psycopg` (pinned).
      Verify: `uv run pytest services/commerce-orchestrator` passes incl. the
      zero-verdict/deadline → `decide_partial` → decision transition with all deps mocked.

- [ ] 8. **checkout-api** (FastAPI) — public `POST /v1/checkout` (docs/06 §1): validate with
      Pydantic (`TxnCreatedPayload` fields), assign `transaction_id`, honor `idempotency_key`
      (repeat returns original decision, never re-charges — docs/06 §5), emit `txn.created`
      on `txn.lifecycle`. DEFAULT sync mode: call orchestrator `POST /internal/evaluate` and
      return the decision JSON; async mode returns `202 + status_url`. Implement
      `GET /v1/transactions/{id}` and `/v1/transactions/{id}/explain` reading the Postgres
      read models the orchestrator persisted. Only service that exposes a host port.
      Files: `services/checkout-api/{Dockerfile,pyproject.toml,src/checkout_api/{__init__,main,idempotency,reads}.py,tests/test_checkout.py}`.
      Reuses: `EventProducer`, `topic_for`, `EventEnvelope`, `EventType`, `TxnCreatedPayload`,
      `PaymentMethodRef`, `CheckoutContext`, `Settings`, `bind_trace_id`. Deps: `httpx`,
      `redis` (idempotency store), `psycopg`.
      Verify: `uv run pytest services/checkout-api` passes incl. idempotency (same key →
      same decision, no second charge) and sync/async mode selection (orchestrator mocked).

- [ ] 9. **Compose + Makefile wiring.** Extend `deploy/docker-compose.yml` with the seven
      services: `build:` from each Dockerfile, `env_file: ../.env` (+ inline defaults),
      `depends_on` infra healthchecks, on `acip-net`, only `checkout-api` publishes a host
      port (e.g. `8080:8080`); mount `../ml/models` read-only into ml-scoring-service. Do
      NOT change the infra-only services. Update Makefile: per-service `build` now covers
      services (compose build), `up` includes services, flesh out `demo`/`logs` stubs with a
      minimal core-path smoke (POST a clean checkout, assert a decision returns).
      Files: `deploy/docker-compose.yml`, `Makefile`, (optional) `scripts/demo.py`.
      Verify: `docker compose -f deploy/docker-compose.yml config` validates (no YAML/schema
      errors); `make help` lists updated targets.

- [ ] 10. **Full-stack verification + core-path smoke.** Run the whole gate:
      `uv sync`; `uv run ruff check .`; `uv run black --check .`; `uv run mypy` (per
      configured roots incl. new services); `uv run pytest` across `acip-common` + all seven
      services. Then boot infra + services (`make up`), and POST `/v1/checkout` with a clean
      transaction proving a decision returns WITH NO AGENTS and NO CLOUD CREDS (deadline →
      decide_partial → CHALLENGE/configured default; llm-gateway on mock). Clean up any temp
      files.
      Files: none (verification only).
      Verify: all lint/type/test commands exit 0; `curl -s -XPOST localhost:8080/v1/checkout -d @sample.json`
      returns a JSON decision; orchestrator logs show the zero-verdict `decide_partial` path.

## Verification commands (reference)

```
uv sync
uv run ruff check .
uv run black --check .
uv run mypy libs/acip-common/src services
uv run pytest libs/acip-common services
docker compose -f deploy/docker-compose.yml config
# core-path smoke (after make up):
curl -s -X POST localhost:8080/v1/checkout -H 'content-type: application/json' -d @scripts/sample_checkout.json
```

## What is explicitly NOT in Phase 2 (Phase 3)

The six agents (risk, fraud, routing, policy, merchant, checkout-personalization) and
`graph-projector`. Phase 2 proves the core path reaches a decision without them via the
`decide_partial` missing-verdict path.
