# 03 — Data Architecture

Three stores, each with a distinct role:

- **Kafka** — the append-only event log (the system of record for *what happened*).
- **Neo4j** — the transaction intelligence graph (connected entities + event paths).
- **PostgreSQL** — read models / projections (fast, flat queries for APIs & demo UI).
- **Redis** — hot features and LangGraph checkpoints (low-latency, ephemeral).

On top of these sits the **shared transaction representation** (§8): one unified
feature + graph-signal object built per transaction and consumed by every agent. It is
the data embodiment of ACIP's "same signals feed every decision" stance.

## 1. Event sourcing

State is never mutated in place. Every lifecycle change is an immutable event on
Kafka. Neo4j and Postgres are **projections** rebuilt by `graph-projector` consuming
the log. Rebuilding from the log reconstructs the full state — this is what delivers
the "state never overwritten / fully traceable" principle.

### Event envelope (common to all events)

```json
{
  "event_id": "uuid",            // unique per event, idempotency key
  "event_type": "txn.created",   // see topic/event catalog below
  "event_version": 1,            // schema version
  "transaction_id": "txn_...",   // partition key, aggregate id
  "trace_id": "uuid",            // distributed trace correlation
  "occurred_at": "ISO-8601",
  "producer": "checkout-api",
  "payload": { }                 // event-specific body
}
```

Partitioning: Kafka key = `transaction_id` → ordered per-transaction processing.

## 2. Kafka topic & event catalog

| Topic | Event types | Producer → Consumers |
|-------|-------------|----------------------|
| `txn.lifecycle` | `txn.created`, `txn.executed`, `txn.declined`, `txn.challenged` | checkout-api / orchestrator → orchestrator, projector |
| `txn.evaluate` | `txn.evaluate.requested` (carries the shared representation) | orchestrator → 6 agents |
| `agent.verdicts` | `agent.verdict.produced` | agents → orchestrator, projector |
| `decision.log` | `decision.rendered` | decision-engine → projector |
| `*.dlq` | poison messages | all consumers → ops |

Schemas are versioned JSON (`event_version`), with a Schema-Registry/Avro upgrade path
documented but JSON used for the POC for debuggability.

## 3. Neo4j graph model

### Node labels

- `(:Customer {id, created_at, risk_tier})`
- `(:Merchant {id, name, category, risk_appetite})`
- `(:Transaction {id, amount, currency, status, created_at, method_type})`
- `(:PaymentMethod {id, type, bin, last4_hash})`  // type ∈ card | upi | netbanking | wallet | cod
- `(:Device {id, fingerprint, first_seen})`
- `(:IPAddress {addr, geo})`
- `(:Processor {id, name})`
- `(:DecisionEvent {id, decision, score, at})`

### Relationships

```text
(Customer)-[:PLACED]->(Transaction)
(Transaction)-[:AT_MERCHANT]->(Merchant)
(Transaction)-[:USED_METHOD]->(PaymentMethod)
(Transaction)-[:FROM_DEVICE]->(Device)
(Transaction)-[:FROM_IP]->(IPAddress)
(Transaction)-[:ROUTED_TO]->(Processor)
(Transaction)-[:HAS_DECISION]->(DecisionEvent)
(Customer)-[:OWNS]->(PaymentMethod)
(Device)-[:LINKED_TO]->(Customer)
(Customer)-[:USED_METHOD_TYPE {successes, failures, last_used}]->(MethodType)
```

The `(:MethodType {name})` nodes + the `USED_METHOD_TYPE` edge carry each customer's
per-method success history. This is what the **checkout-personalization agent** reads
to recommend the method most likely to succeed, and what the **routing agent** uses
alongside processor stats.

### Why a graph

Fraud and risk signals are *relational*: a device shared across many customers, a
payment method tied to prior chargebacks, rings of entities transacting in bursts.
These are cheap traversals in Neo4j and awkward joins in SQL. The fraud agent queries,
e.g., "size of the device-sharing ring in the last 24h" directly as a traversal.

Example signal query (fraud ring size):

```cypher
MATCH (t:Transaction {id:$txn})-[:FROM_DEVICE]->(d:Device)<-[:FROM_DEVICE]-(o:Transaction)
WHERE o.created_at > datetime() - duration('PT24H')
RETURN count(DISTINCT o) AS ring_size
```

## 4. PostgreSQL read models

Flat, query-optimized projections for the APIs and demo dashboard:

- `transactions` — current state snapshot (id, amount, status, decision, timestamps).
- `decisions` — one row per rendered decision with composite score + strategy.
- `agent_verdicts` — per-agent verdict rows for audit/explainability views.
- `event_journal` — denormalized copy of the event log for querying/replay in the demo.

These are **derived**; truth lives in Kafka. They exist for speed and simple reads.

## 5. Redis

- **Hot features** — velocity counters, recent-activity windows, cached graph signals
  with TTL, read on the latency-critical scoring path.
- **LangGraph checkpoints** — orchestrator per-transaction state for durable resume.

## 6. Feature flow (write + serve)

```text
events ──▶ graph-projector ──▶ Neo4j (relationships) ──┐
                           └──▶ Postgres (read models)  │
                                                        ├─▶ feature builder ─▶ Redis (hot features)
                                                        │
agents on scoring path ──▶ Redis (hot) + Neo4j (graph signals) ──▶ ml-scoring-service
```

## 7. Data retention & privacy (POC posture)

- PANs/sensitive identifiers are never stored raw — only hashed/tokenized
  (`last4_hash`, tokenized method ids).
- Event log retention configurable; projections rebuildable from the log.
- Clear separation lets a production deployment add encryption-at-rest and PCI scoping
  without reshaping the model.

## 8. Shared transaction representation

The shared representation is the single object every agent scores against. It is built
once per transaction by `representation-service` from the three stores and attached to
`txn.evaluate.requested`, so all six agents see identical inputs.

```json
{
  "representation_version": 1,
  "transaction_id": "txn_...",
  "built_at": "ISO-8601",
  "transaction": { "amount": 149.99, "currency": "USD", "method_type": "upi", "merchant_id": "mrc_123", "customer_id": "cus_456" },
  "features": {
    "amount_zscore": 2.1,
    "velocity_1h": 11,
    "method_age_days": 3,
    "geo_mismatch": 1
  },
  "graph_signals": {
    "shared_device_ring_size": 4,
    "customer_txn_count_30d": 12,
    "customer_chargeback_count": 0
  },
  "method_history": {
    "upi":  { "successes": 18, "failures": 1 },
    "card": { "successes": 3,  "failures": 2 }
  },
  "candidate_routes": [
    { "processor": "processor_a", "success_rate": 0.97, "cost_bps": 85, "p50_latency_ms": 220 },
    { "processor": "processor_b", "success_rate": 0.94, "cost_bps": 70, "p50_latency_ms": 180 }
  ]
}
```

Design properties:

- **Versioned** (`representation_version`) so the schema can evolve without breaking
  agents.
- **Computed once**, not per agent — avoids six duplicate feature builds and guarantees
  consistency across verdicts.
- **An extensible seam.** Today the representation is a transparent dict of features +
  graph signals. A richer learned transaction embedding could later be produced here
  (behind `representation-service`) and added as an extra field, with agents consuming
  it unchanged.
- **Cached** in Redis keyed by `transaction_id` so a retried evaluation reuses it.
