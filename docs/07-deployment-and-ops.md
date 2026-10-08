# 07 — Deployment & Operations

## 1. Local topology (Docker Compose)

One `docker-compose.yml` under `deploy/` brings up the full platform on a laptop.

Infrastructure containers:

| Container | Image | Purpose |
|-----------|-------|---------|
| `kafka` | Redpanda or Confluent Kafka | event bus (Kafka API) |
| `kafka-init` | one-shot | creates topics (`txn.lifecycle`, `txn.evaluate`, `agent.verdicts`, `decision.log`, DLQs) |
| `neo4j` | neo4j:5 | transaction intelligence graph |
| `postgres` | postgres:16 | read models |
| `redis` | redis:7 | hot features + LangGraph checkpoints |
| `prometheus` | prom/prometheus | metrics |
| `grafana` | grafana/grafana | dashboards |
| `jaeger` | jaegertracing/all-in-one | traces |

Application containers: the 12 services from doc 01 §2, each with its own
`Dockerfile`, all on a private `acip-net` network. Only `checkout-api` (and Grafana/
Neo4j browser for inspection) expose host ports.

Service dependency order is enforced with healthchecks + `depends_on: condition:
service_healthy` so agents don't start before Kafka/Neo4j are ready.

## 2. Configuration (12-factor)

All config via environment, typed with `pydantic-settings` in `acip-common.config`.
Key variables:

```env
# messaging
KAFKA_BOOTSTRAP=kafka:9092
# stores
NEO4J_URI=bolt://neo4j:7687
NEO4J_AUTH=neo4j/password
POSTGRES_DSN=postgresql://acip:acip@postgres:5432/acip
REDIS_URL=redis://redis:6379/0
# llm
LLM_PROVIDER=gemini
LLM_MODEL=gemini-1.5-pro
LLM_FALLBACK_PROVIDER=mock
GOOGLE_APPLICATION_CREDENTIALS=/secrets/adc.json
# decisioning
DECISION_DEADLINE_MS=800
FRAUD_BLOCK_THRESHOLD=0.85
APPROVE_MAX=0.35
CHALLENGE_MAX=0.70
W_RISK=0.5
W_FRAUD=0.5
# representation + methods
REPRESENTATION_VERSION=1
ENABLED_METHOD_TYPES=card,upi,netbanking,wallet,cod
# processor sim
SIM_APPROVAL_RATE=0.9
SIM_LATENCY_MS=40
```

Secrets (ADC key, DB passwords) are mounted via Docker secrets / `.env` not baked into
images. `.env.example` ships; `.env` is gitignored.

## 3. Make targets (operator UX)

```make
make build        # build all service images
make up           # start infra + services
make topics       # create Kafka topics (idempotent)
make train        # run offline ML training, write artifacts
make seed         # seed Neo4j + Postgres with demo customers/merchants
make demo         # run the demo driver (scripts/demo.py)
make logs         # tail aggregated logs
make down         # stop and clean
```

## 4. Demo walkthrough

1. `make build && make up` — stack boots; healthchecks go green.
2. `make train` — trains risk + fraud models into `ml/models/`.
3. `make seed` — loads sample customers, merchants, devices, and a fraud ring into
   Neo4j so graph signals are meaningful.
4. `make demo` — the driver posts a mix of checkouts to `checkout-api`:
   - a clean low-value purchase → **APPROVE**, routed to the healthiest scored route,
     with a **recommended payment method** (checkout personalization)
   - a high-velocity shared-device transaction → **DECLINE** (fraud veto)
   - a mid-risk high-value purchase → **CHALLENGE** (step-up)
   - a policy-violating (sanctioned geo) transaction → **DECLINE** (policy veto)
   - a transaction whose preferred route is unhealthy → **APPROVE on an alternate
     route** (demonstrates route-scoring + failover)
5. Inspect results:
   - `GET /v1/transactions/{id}/explain` shows per-agent rationale + evidence.
   - **Neo4j Browser** shows the transaction graph and the fraud ring.
   - **Grafana** shows agent latencies, decision mix, LLM provider usage.
   - **Jaeger** shows the end-to-end trace for a single `trace_id`.

If no ADC credentials are present, `llm-gateway` runs the `mock` provider and the demo
still produces full rationales — nothing requires cloud access to run.

## 5. Observability

- **Logs:** structured JSON, correlated by `trace_id`.
- **Metrics (Prometheus):** per-agent verdict latency, decision mix, deadline misses,
  LLM provider latency/tokens, ML inference latency, DLQ counts.
- **Traces (Jaeger/OTel):** `trace_id` propagated from `txn.created` through verdicts,
  decision, and execution — one trace per transaction.
- **Dashboards (Grafana):** provisioned at startup from `deploy/grafana/`.

## 6. Resilience & operations

- Healthchecks + readiness gates on every service.
- Retries + backoff + circuit breakers on LLM/ML/processor calls.
- DLQ topics for poison events; consumers never block the stream on one bad message.
- Idempotent consumers (upsert by `event_id`/`transaction_id`) → safe at-least-once.
- Orchestrator state checkpointed → crash-resume mid-evaluation.

## 7. Production path (beyond the POC)

The layout is deliberately K8s-ready:

- Each service already has a clean image, config-via-env, and health endpoints.
- `deploy/k8s/` (future) holds Deployments/Services/HPA + a Helm chart.
- Managed equivalents swap in by config only: MSK/Confluent (Kafka), Aura (Neo4j),
  Cloud SQL (Postgres), Memorystore (Redis), Vertex AI (Gemini via Workload Identity).
- Schema Registry + Avro replaces JSON envelopes for stricter contracts.
- Add network policies, mTLS between services, and PCI scoping for the card data path.
