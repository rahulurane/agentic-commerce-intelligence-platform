# ACIP Technical Design — Document Index

**Project:** Agentic Commerce Intelligence Platform (ACIP)
**Version:** 2.0 (Production-grade POC)
**Status:** Design — pending review (no implementation yet)

This folder is the technical design and system architecture for ACIP. It expands
the master specification (`requirement_document/gemini-code-1791469912356.md`) into
an implementable, microservice-based, production-shaped blueprint.

## Design decisions (locked)

| Area | Decision |
|------|----------|
| Language / runtime | Python 3.11+ |
| Agent orchestration | LangGraph |
| Sync service edges | FastAPI + Uvicorn |
| Eventing / fan-out | Apache Kafka |
| Graph store | Neo4j (transaction intelligence graph) |
| Read-model / state store | PostgreSQL |
| Cache / low-latency features | Redis |
| ML scoring | XGBoost / LightGBM in a dedicated service (sub-50ms target) |
| LLM provider (default) | Gemini via Google Cloud ADC, behind a provider-agnostic adapter |
| Packaging / deploy | Docker + Docker Compose (POC); Kubernetes-ready |
| Decisioning model | Hybrid — ML score + LLM rationale per agent, over a shared transaction representation |

## Reading order

1. [`01-system-architecture.md`](./01-system-architecture.md) — the big picture: services, boundaries, topology, cross-cutting concerns.
2. [`02-agent-architecture.md`](./02-agent-architecture.md) — LangGraph graphs, the six agents, the decision engine.
3. [`03-data-architecture.md`](./03-data-architecture.md) — Neo4j graph model, event sourcing, Kafka topics, Postgres read models.
4. [`04-llm-sdk-layer.md`](./04-llm-sdk-layer.md) — provider-agnostic LLM adapter and hot-swap.
5. [`05-ml-scoring-services.md`](./05-ml-scoring-services.md) — feature pipeline, model serving, latency budget.
6. [`06-api-contracts.md`](./06-api-contracts.md) — REST contracts, Kafka event schemas, sequence flows.
7. [`07-deployment-and-ops.md`](./07-deployment-and-ops.md) — Docker Compose, config/secrets, observability, demo walkthrough.

## Scope of this POC

- Runnable end-to-end on a laptop via Docker Compose.
- Real Neo4j, Kafka, Postgres, Redis. Real Gemini calls when ADC is configured; a
  deterministic mock provider when it is not (demo still runs with no cloud creds).
- ML models trained offline on synthetic data; a `train` job ships with the repo.
- The payment processor is a simulator (configurable latency + approval behavior).
