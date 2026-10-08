# 01 — System Architecture

## 1. Purpose & architectural stance

ACIP is a **real-time, pre-transaction autonomous decisioning layer**. It intercepts
a payment *before* execution, runs six specialized agents in parallel over a **shared
transaction representation**, aggregates their verdicts, and returns an
APPROVE / DECLINE / CHALLENGE / ROUTE decision with a traceable, explainable rationale.

ACIP's design principle is that **the same signals feed every decision**: a single
shared transaction representation is computed once and read by every agent. This gives
unified, consistent intelligence across routing, fraud, risk, policy, merchant, and
checkout decisions while keeping each agent independently **explainable** — every
verdict carries its own rationale and evidence.

The system is built as a set of **independently deployable microservices** that
communicate through two planes:

- **Synchronous plane (FastAPI/HTTP):** the request edge — checkout intake, the
  orchestrator's decision API, the ML scoring service, health/readiness probes.
- **Asynchronous plane (Kafka):** agent fan-out, verdict collection, event sourcing,
  and graph/state projection.

### Guiding principles (from the master spec)

1. **Graph first** — entities and events are modeled as a connected graph in Neo4j.
2. **Event sourcing** — transaction state is never overwritten; every lifecycle event
   is an immutable record on an append-only Kafka log.
3. **Explainability** — every decision carries evidence, confidence, and per-agent
   rationale.
4. **Parallel agent decisioning** — agents evaluate independently and concurrently.
5. **Composable & provider-agnostic** — every capability is a service; LLM providers
   are decoupled behind an adapter.

## 2. Service catalog (microservices)

| # | Service | Responsibility | Plane | Stack |
|---|---------|----------------|-------|-------|
| 1 | `checkout-api` | Public intake. Validates the checkout request, creates a transaction, emits `txn.created`. | Sync (edge) | FastAPI |
| 2 | `commerce-orchestrator` | LangGraph brain. Builds evaluation context, fans out to agents over Kafka, waits for verdicts, calls Decision Engine, drives execution. | Sync + Async | FastAPI + LangGraph |
| 3 | `risk-agent` | Credit/behavioral risk scoring + rationale. | Async | FastAPI (health) + consumer |
| 4 | `fraud-agent` | Fraud likelihood (graph signals + ML) + rationale. | Async | FastAPI (health) + consumer |
| 5 | `routing-agent` | Scores **every** available payment route and picks the healthiest + rationale. | Async | FastAPI (health) + consumer |
| 6 | `policy-agent` | Compliance, limits, business policy checks. | Async | FastAPI (health) + consumer |
| 7 | `merchant-agent` | Merchant-specific config, preferences, SLAs. | Async | FastAPI (health) + consumer |
| 8 | `checkout-personalization-agent` | Recommends the payment method most likely to succeed for this customer. | Async | FastAPI (health) + consumer |
| 9 | `decision-engine` | Aggregates agent verdicts into a final decision with a weighted/policy strategy. | Sync (lib + service) | FastAPI |
| 10 | `ml-scoring-service` | XGBoost/LightGBM serving. Sub-50ms risk + fraud predictions. | Sync | FastAPI |
| 11 | `representation-service` | Builds the **shared transaction representation** (unified feature + graph-signal vector) all agents consume. | Sync | FastAPI |
| 12 | `llm-gateway` | Provider-agnostic LLM access (Gemini default). Shared by all agents. | Sync | FastAPI + adapter SDK |
| 13 | `payment-processor-sim` | Simulated acquirer/processor (configurable latency + outcomes). | Sync | FastAPI |
| 14 | `graph-projector` | Consumes the event log, projects into Neo4j + Postgres read models. | Async | Kafka consumer |

Shared Python library: `acip-common` (event schemas, Kafka client wrappers, tracing,
config, domain models, **shared-representation schema**) imported by every service.

## 3. Logical architecture

```text
                          ┌────────────────────────────┐
  Customer / Web App ───▶ │        checkout-api         │  POST /v1/checkout
                          └──────────────┬──────────────┘
                                         │ emit txn.created (Kafka)
                                         ▼
                          ┌────────────────────────────┐
                          │   commerce-orchestrator     │  (LangGraph)
                          │  build context → fan out    │
                          └──────────────┬──────────────┘
                                         │ 1. call representation-service (shared repr)
                                         │ 2. publish txn.evaluate.requested (repr attached)
                                         ▼
                   ┌─────────────────────────────────────────┐
                   │   SHARED TRANSACTION REPRESENTATION       │ ◀─ one vector, all agents read it
                   │  (unified features + graph signals)       │
                   └──────────────────────┬────────────────────┘
             ┌───────────────┬────────────┼────────────┬───────────────┬──────────────────┐
             ▼               ▼            ▼            ▼               ▼                  ▼
        risk-agent      fraud-agent  routing-agent policy-agent  merchant-agent  checkout-personalization
             │               │            │            │               │                  │
             └── each calls ml-scoring-service and/or llm-gateway as needed ───────────────┘
             │               │            │            │               │                  │
             └───────────────┴────────────┼────────────┴───────────────┴──────────────────┘
                                          │ publish agent.verdict.produced (×6)
                                          ▼
                          ┌────────────────────────────┐
                          │   commerce-orchestrator     │  collect 6 verdicts
                          └──────────────┬──────────────┘
                                         │ call
                                         ▼
                          ┌────────────────────────────┐
                          │      decision-engine        │  aggregate → final decision
                          └──────────────┬──────────────┘
                                         │ if APPROVE/ROUTE
                                         ▼
                          ┌────────────────────────────┐
                          │   payment-processor-sim     │
                          └──────────────┬──────────────┘
                                         │ emit txn.executed / txn.declined
                                         ▼
                          ┌────────────────────────────┐
                          │  graph-projector  ──▶ Neo4j + Postgres (read models) │
                          └────────────────────────────┘
```

## 4. Request lifecycle (happy path)

1. `checkout-api` validates the request, assigns `transaction_id`, writes a
   `txn.created` event to Kafka, returns `202 Accepted` with a decision-polling
   handle (or holds the HTTP connection for a bounded sync decision — see §6).
2. `commerce-orchestrator` consumes `txn.created`, calls `representation-service` to
   build the **shared transaction representation** (one unified feature + graph-signal
   vector hydrated from Neo4j + Redis), then publishes `txn.evaluate.requested` with
   that representation attached to the agent fan-out topic.
3. All six agents consume the same event in parallel and read the **same shared
   representation** (the "same signals matter to every decision" principle). Each
   produces a verdict (score + decision hint + rationale + evidence) by combining an ML
   score (via `ml-scoring-service`) and an LLM rationale (via `llm-gateway`), then
   publishes `agent.verdict.produced`.
4. The orchestrator collects verdicts keyed by `transaction_id` until all six arrive
   or a deadline elapses (partial-verdict policy in §6).
5. `decision-engine` aggregates verdicts into a final decision.
6. On APPROVE/ROUTE, the orchestrator calls `payment-processor-sim`; the outcome is
   emitted as `txn.executed` or `txn.declined`.
7. `graph-projector` consumes every event and updates Neo4j + Postgres read models.

## 5. Why these boundaries

- **Agents are separate services** so they scale, fail, and deploy independently
  (principle 4). A slow fraud model never blocks the routing decision.
- **Kafka fan-out, not direct HTTP** so the orchestrator never couples to agent
  availability and the event log doubles as the event-sourcing spine (principles 2 & 4).
- **ML and LLM are shared services, not libraries baked into agents**, so model
  rollouts and provider swaps happen without redeploying agents (principle 5).
- **A single shared representation**, built once per transaction and read by all
  agents, means every decision sees the same signals (unified, consistent intelligence)
  while keeping the agents independently explainable. It is also the clean seam where a
  richer learned representation could later be produced behind `representation-service`
  without touching the agents.
- **Projection is a separate consumer** so write-path latency is independent of
  graph/read-model maintenance.

## 6. Cross-cutting concerns

- **Decision latency & partial verdicts.** The orchestrator enforces a decision
  deadline (default 800ms). If an agent misses it, the decision engine applies a
  configurable missing-verdict policy (fail-safe/decline for risk+fraud, ignore for
  advisory agents). This keeps the system responsive and is documented in
  `06-api-contracts.md`.
- **Idempotency.** Every event carries `transaction_id` + `event_id`; consumers are
  idempotent (upsert by key). Kafka keys are the `transaction_id` so all events for a
  transaction land on the same partition and preserve order.
- **Observability.** Structured JSON logs, OpenTelemetry traces propagated via a
  `trace_id` on every event, Prometheus metrics (latency histograms per agent,
  verdict counts, decision mix). Jaeger + Prometheus + Grafana in Compose.
- **Resilience.** Timeouts + retries with backoff on LLM/ML calls, circuit breakers
  in `llm-gateway` and `ml-scoring-service` clients, DLQ topics for poison messages.
- **Security.** Secrets via env/Docker secrets (ADC key mount for Gemini); internal
  services on a private Compose network; input validation at the edge with Pydantic.
- **Config.** 12-factor: all config via environment, typed with `pydantic-settings`,
  centralized in `acip-common.config`.

## 7. Technology stack summary

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ |
| Agent graph | LangGraph |
| Web / API | FastAPI + Uvicorn + Pydantic v2 |
| Messaging | Apache Kafka (Redpanda-compatible for local) |
| Graph DB | Neo4j 5.x |
| Relational / read models | PostgreSQL 16 |
| Cache / features | Redis 7 |
| ML | XGBoost, LightGBM, scikit-learn, pandas |
| LLM | Gemini (Vertex AI / Google GenAI SDK) via adapter; OpenAI/Anthropic/Llama swappable |
| Serialization | JSON event envelopes (schema-versioned); Avro/Schema-Registry-ready |
| Observability | OpenTelemetry, Prometheus, Grafana, Jaeger |
| Packaging | Docker, Docker Compose; Helm/K8s-ready layout |
| Tooling | Poetry/uv, Ruff, Black, mypy, pytest |

## 8. Repository layout (target)

```text
agentic-commerce-intelligence-platform/
├── docs/                      # this design set
├── libs/
│   └── acip-common/           # shared: schemas, kafka, config, tracing, domain
├── services/
│   ├── checkout-api/
│   ├── commerce-orchestrator/
│   ├── risk-agent/
│   ├── fraud-agent/
│   ├── routing-agent/
│   ├── policy-agent/
│   ├── merchant-agent/
│   ├── checkout-personalization-agent/
│   ├── decision-engine/
│   ├── ml-scoring-service/
│   ├── representation-service/
│   ├── llm-gateway/
│   ├── payment-processor-sim/
│   └── graph-projector/
├── ml/
│   ├── training/              # offline training jobs
│   └── models/                # serialized artifacts
├── deploy/
│   ├── docker-compose.yml
│   ├── kafka/ neo4j/ postgres/ grafana/ ...
│   └── k8s/                   # (future) manifests/helm
├── scripts/                   # seed data, demo driver, topic creation
└── Makefile
```
