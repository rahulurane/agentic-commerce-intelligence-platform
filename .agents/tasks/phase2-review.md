# checkout-api public edge + full-stack compose/Makefile wiring (FEAT-004)

FEAT-004 lands the public write edge of ACIP Phase 2 and the wiring that makes the whole
stack runnable. `checkout-api` exposes `POST /v1/checkout` (sync-default, async opt-in),
Redis-backed idempotency, and the two Postgres-backed read endpoints; it calls the
commerce-orchestrator `POST /internal/evaluate` for the decision and emits a `txn.created`
event for the log. `deploy/docker-compose.yml` gains all seven Phase 2 services with only
checkout-api publishing a host port, and the Makefile grows `up`/`up-infra`/`build`/`smoke`/
`demo`/`logs`/`test` targets without dropping any Phase 1 target. The service reuses
`acip_common` schemas, config, kafka wrapper, and topic map throughout — it defines no
parallel contracts. The no-agents core path is proven to reach a `CHALLENGE` decision.

Watch for: the end-to-end gate was NOT run live — Docker was down in the build environment,
so the live `make up` + curl smoke is unexecuted and substituted by an in-process
integration test (confirmed). The public `verdicts` block is hardwired empty and
`route_alternatives` is surfaced at top level rather than nested under `verdicts.routing` as
docs/06 §1 depicts, a deliberate Phase-2-no-agents shaping (confirmed). Async mode does not
persist the idempotency record, so a repeated async key re-mints a transaction (likely).

**Verdict**: APPROVED

## High-level view

The edge-to-orchestrator contract lines up exactly. checkout-api sends `transaction_id`,
`trace_id`, `amount`, `currency`, `method_type`, `merchant_id`, `customer_id`,
`device_fingerprint` to `/internal/evaluate`; the orchestrator's `EvaluateRequest` accepts
precisely those fields (`extra="forbid"`), coercing `method_type` into the shared
`MethodType` enum — which is what `payment_method.type.value` produces. The response is
mapped from the orchestrator's `DecisionRenderedPayload`, reading `decision`, `route`,
`composite_score`, `explanation`, `recommended_method`, `contributing_verdicts`,
`route_alternatives`, and `degraded_agents` by their real field names.

Reuse of `acip-common` is clean: `PaymentMethodRef`/`CheckoutContext` back the request body,
`TxnCreatedPayload`/`EventEnvelope`/`EventType` back the emitted event, `topic_for` resolves
the lifecycle topic, and `Settings` supplies every URL/DSN. No schema, topic string, or
config key is redefined locally.

Idempotency is a real replay: the first call stores `{transaction_id, decision}` in Redis
under a prefixed key with a 24h TTL, and a repeat key short-circuits before the orchestrator
call so no second charge can occur. The store degrades to "no record" when Redis is down
(fail-open on the guarantee), while the read path fails closed on a dead Postgres — an
intentional asymmetry the code documents.

Compose adds the seven services building from the repo root (so the workspace lib resolves),
each `env_file: ../.env (required:false)` plus inline defaults, infra `depends_on`
healthchecks, all on `acip-net`, and only checkout-api maps `8080:8000`. Infra services are
untouched. The Makefile keeps every Phase 1 target and adds the stack/smoke targets.

The known gaps are all Phase-2-shape artifacts, not defects: the public `verdicts` object is
empty because no agents run yet, async idempotency isn't persisted, and inter-service
`depends_on` uses `service_started` rather than a readiness gate. None block the FEAT-004
acceptance criteria.

<details>
<summary>Issues (3)</summary>

1. **Live end-to-end smoke unexecuted** — Docker was down, so `make up` + curl was never
   run; the no-agents guarantee is proven by an in-process integration test instead. Run the
   live smoke once a Docker daemon is available before the leadership demo.
2. **Public `verdicts` block hardwired empty + `route_alternatives` not nested** — the
   docs/06 §1 response nests per-agent verdicts (incl. `routing.alternatives`) under
   `verdicts`; the edge returns `verdicts: {}` and lifts `route_alternatives` to top level.
   Acceptable for no-agents Phase 2; revisit when agents land so the contract matches docs.
3. **Async mode skips idempotency persistence** — a repeated `idempotency_key` in async mode
   re-mints a transaction_id rather than replaying. Harmless in sync-default demo flow; store
   the mapping on the async path when async becomes a real client mode.

</details>

<details>
<summary>Details</summary>

### Edge-to-orchestrator contract fidelity

`_evaluate_sync` builds the request body from the validated `CheckoutRequest` and posts to
`{orchestrator_url}/internal/evaluate` with a timeout derived from `decision_deadline_ms + 2s`
(floored at 2s). The orchestrator's `EvaluateRequest` declares `transaction_id`, `trace_id`,
`amount`, `currency`, `method_type: MethodType`, `merchant_id`, `customer_id`, `txn_geo`,
`device_fingerprint`, all with `extra="forbid"`. checkout-api sends a subset that is exactly
the required fields plus `device_fingerprint`; `txn_geo` is optional and omitted. The
`method_type` wire value comes from `req.payment_method.type.value`, and `PaymentMethodRef.type`
is the shared `MethodType` enum, so the string the orchestrator coerces back is guaranteed to
be a valid member. The two services agree field-for-field; no contract drift.

The response_model on the orchestrator side is `DecisionRenderedPayload`, so the JSON
checkout-api receives carries `decision`, `composite_score`, `strategy`, `route`,
`route_alternatives`, `recommended_method`, `contributing_verdicts`, `explanation`, and
`degraded_agents`. `_public_decision` reads each of those by name; `partial` is computed as
`not rendered.get("contributing_verdicts")`, which correctly flags the zero-verdict path as
partial. The integration test confirms the real aggregator populates `route`
("processor_default") and `decision` ("CHALLENGE") on that path, so the top-level fields are
never unexpectedly null for the demo transaction.

### Idempotency and the fail-open/fail-closed split

The idempotency store claims a key only after a successful sync evaluation (`idempotency.put`
runs post-`_evaluate_sync`), and the replay check runs first thing in the handler, before any
`txn.created` emit or orchestrator call. That ordering is what guarantees "never re-charge":
a duplicate key returns the stored decision with a 200 and never reaches `_evaluate_sync`. The
`test_idempotent_repeat_returns_original_and_does_not_recharge` test asserts the orchestrator
mock is hit exactly once across two identical requests, which is the right behavioral check.

The store is deliberately fail-open — if Redis is unreachable, `get` returns `None` and the
request proceeds as a fresh evaluation, logged as degraded. That means the idempotency
guarantee is best-effort while Redis is down, a trade-off the module documents explicitly. By
contrast `reads.PostgresReadModel` raises on a dead connection rather than returning `None`,
so a GET surfaces a real error instead of a false 404. The asymmetry is intentional and
correct: losing idempotency briefly is tolerable, silently reporting a known transaction as
missing is not.

The async path is the one place the guarantee is incomplete: async mode returns 202 after
emitting `txn.created` but never writes an idempotency record (the `put` only happens on the
sync branch). A client retrying an async checkout with the same key would mint a new
transaction. For the sync-default demo this never triggers, but it is a real gap if async
becomes a supported client mode.

### Compose topology and the single public port

```
                       host :8080
                          │
                          ▼
                    checkout-api ──http──▶ commerce-orchestrator
                          │                      │
                     txn.created            ┌────┼───────────────┐
                          │                 ▼    ▼               ▼
                       redpanda      representation  decision-engine  payment-sim
                                           │                            (+ ml, llm)
                                     neo4j/redis
```

All seven services build with `context: ..` and their service-relative Dockerfile, so
`uv sync` sees the `acip-common` workspace member. Each takes `env_file: ../.env` with
`required: false` (stack boots with no `.env`) plus inline `environment:` defaults that mirror
`Settings`. Only checkout-api maps a host port (`8080:8000`); every other service stays on
`acip-net` with the internal 8000. ml-scoring-service mounts `../ml/models:ro` and sets
`ML_MODELS_DIR=/app/ml/models`, matching the artifact-discovery design. The infra block
(redpanda, kafka-init, neo4j, postgres, redis, prometheus, grafana, jaeger) is unchanged, so
`up-infra` still brings up exactly the Phase 1 stack. `docker compose config` validated per the
evidence (15 services enumerated).

One soft spot: checkout-api and commerce-orchestrator depend on their downstreams with
`condition: service_started`, not `service_healthy`, so Compose will start them as soon as the
dependency process launches rather than when it is ready. The services expose `/readyz`, so
this is survivable (requests early on may get a transient 5xx until downstreams are ready), but
a healthcheck-gated dependency would make `make up` more deterministic for the demo.

### Secrets, pinning, and committed artifacts

No credentials appear in the diff — DSNs and URLs are env-interpolated with non-secret local
defaults (`acip:acip@postgres`), and `.env` is gitignored. All checkout-api deps are exact-
pinned (`fastapi==0.115.6`, `uvicorn[standard]==0.34.0`, `httpx==0.28.1`, `redis==5.2.1`,
`psycopg[binary]==3.2.3`) and the lockfile moved with them. The `__pycache__` and
`.pytest_cache` directories present in the working tree are confirmed gitignored, so they will
not be committed; the only tracked deletion is the `services/checkout-api/.gitkeep` placeholder,
which is correct now that the package exists.

### Test coverage

The suite (11 tests) covers 422 on missing and on extra fields, the sync happy path with the
`txn.created` emission assertion, idempotent replay with the single-call charge check, async
via both query param and header, both GET endpoints with 404s against a fake read model, the
health probes, and an in-process integration smoke that drives the real edge into the real
orchestrator graph and real decision-engine aggregator to prove the no-agents CHALLENGE path.
External dependencies are injected via `app.dependency_overrides` and `httpx.MockTransport`, so
nothing needs a live broker/Redis/Postgres.

Not tested: the live `make up` + curl end-to-end run (Docker was down — honestly reported in the
evidence, not claimed); the Redis-down degraded idempotency branch and the Postgres-down read
error branch (the guards exist but no test exercises them); the async idempotency gap noted
above. These are acceptable for the Phase-2 gate but worth noting as the untested edges.

</details>

<details>
<summary>File map</summary>

- `services/checkout-api/src/checkout_api/main.py` — FastAPI edge: `/v1/checkout` sync/async,
  the two GET read endpoints, health probes, orchestrator call + response shaping.
- `services/checkout-api/src/checkout_api/idempotency.py` — Redis-backed replay store, fail-open.
- `services/checkout-api/src/checkout_api/reads.py` — Postgres read models for GET/`/explain`,
  fail-closed, behind a `ReadModel` protocol.
- `services/checkout-api/tests/test_checkout.py` — 9 unit tests (validation, idempotency,
  modes, GETs, probes).
- `services/checkout-api/tests/test_integration_core_path.py` — in-process edge→graph no-agents
  smoke + module-identity assertion.
- `services/checkout-api/{Dockerfile,pyproject.toml}` — slim non-root image; pinned deps,
  workspace dep on acip-common.
- `deploy/docker-compose.yml` — adds the seven services; only checkout-api publishes `8080:8000`.
- `Makefile` — `build`/`up`/`up-infra`/`down`/`test`/`demo`/`smoke`/`logs`; Phase 1 targets kept.
- `pyproject.toml` + `uv.lock` — checkout-api into workspace members/sources/dev group.
- `scripts/{sample_checkout.json,demo.py}` — clean UPI sample + smoke driver for `make demo`.
- `services/checkout-api/.gitkeep` — deleted (package now exists).

Full diff: `git diff HEAD` plus the untracked `services/checkout-api/` tree and `scripts/`.

</details>
