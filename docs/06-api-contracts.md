# 06 — API Contracts & Sequence Flows

## 1. Public REST API (`checkout-api`)

### POST `/v1/checkout`

Request:

```json
{
  "merchant_id": "mrc_123",
  "customer_id": "cus_456",
  "amount": 149.99,
  "currency": "USD",
  "payment_method": {
    "type": "card",
    "token": "tok_...",
    "bin": "411111",
    "last4": "1111"
  },
  "context": {
    "device_fingerprint": "fp_...",
    "ip": "203.0.113.9",
    "user_agent": "..."
  },
  "idempotency_key": "idem_..."
}
```

Response (sync mode, bounded wait):

```json
{
  "transaction_id": "txn_789",
  "decision": "APPROVE",
  "route": "processor_a",
  "composite_score": 0.21,
  "explanation": "Low risk and fraud; approved and routed to processor_a.",
  "recommended_method": "upi",
  "verdicts": {
    "risk":   { "score": 0.18, "hint": "APPROVE" },
    "fraud":  { "score": 0.12, "hint": "APPROVE" },
    "policy": { "allow": true },
    "routing":{ "route": "processor_a", "alternatives": ["processor_b"] },
    "merchant":{ "constraints": [] },
    "checkout_personalization": { "recommended_method": "upi", "confidence": 0.88 }
  },
  "trace_id": "..."
}
```

Response (async mode): `202 Accepted` + `{ "transaction_id": "...", "status_url": "/v1/transactions/txn_789" }`.

### GET `/v1/transactions/{id}`

Returns current state + decision + per-agent verdicts (from Postgres read models).

### GET `/v1/transactions/{id}/explain`

Returns the full decision trace: inputs, each agent's rationale + evidence, strategy,
weights, final decision — the explainability view.

## 2. Internal service endpoints

| Service | Endpoint | Purpose |
|---------|----------|---------|
| commerce-orchestrator | `POST /internal/evaluate` | (optional) sync trigger used by checkout-api in sync mode |
| decision-engine | `POST /v1/decide` | aggregate verdicts → decision |
| ml-scoring-service | `POST /v1/score` | model scoring (see doc 05) |
| llm-gateway | `POST /v1/complete` | provider-agnostic completion (see doc 04) |
| payment-processor-sim | `POST /v1/charge` | simulated charge, configurable outcome/latency |
| all | `GET /healthz`, `GET /readyz` | liveness / readiness |

### `payment-processor-sim` contract

```json
// POST /v1/charge
{ "transaction_id":"txn_789","amount":149.99,"currency":"USD","route":"processor_a" }
// → 200
{ "status":"CAPTURED","processor":"processor_a","auth_code":"A1B2C3","latency_ms":42 }
```

Behavior is config-driven: `SIM_APPROVAL_RATE`, `SIM_LATENCY_MS`, `SIM_FAILURE_MODE`
let the demo show approvals, declines, and processor failures/retries.

## 3. Kafka event contracts

All events use the common envelope (doc 03 §1). Payloads:

### `txn.created`

```json
{ "merchant_id":"mrc_123","customer_id":"cus_456","amount":149.99,
  "currency":"USD","payment_method":{...},"context":{...} }
```

### `txn.evaluate.requested`

```json
{ "representation": {
    "representation_version": 1,
    "transaction": {...},
    "features": { "velocity_1h":11, "amount_zscore":2.1 },
    "graph_signals": { "shared_device_ring_size":4, "customer_txn_count_30d":12 },
    "method_history": { "upi": {"successes":18,"failures":1} },
    "candidate_routes": [ {"processor":"processor_a","success_rate":0.97} ] },
  "expected_agents": ["risk","fraud","routing","policy","merchant","checkout_personalization"],
  "deadline_ms": 800 }
```

See `03-data-architecture.md` §8 for the full shared-representation schema.

### `agent.verdict.produced`

See doc 02 §4.

### `decision.rendered`

See doc 02 §5.

### `txn.executed` / `txn.declined` / `txn.challenged`

```json
{ "decision":"APPROVE","route":"processor_a","processor_result":{...},
  "composite_score":0.21,"decided_at":"..." }
```

## 4. End-to-end sequence (sync mode)

```text
Client            checkout-api     Kafka          orchestrator      agents(x5)   ml/llm   decision-engine   proc-sim
  │  POST /checkout   │              │                 │               │           │           │              │
  │──────────────────▶│              │                 │               │           │           │              │
  │                   │ txn.created  │                 │               │           │           │              │
  │                   │─────────────▶│                 │               │           │           │              │
  │                   │              │  consume        │               │           │           │              │
  │                   │              │────────────────▶│ build repr    │           │           │              │
  │                   │              │                 │ txn.evaluate  │           │           │              │
  │                   │              │◀────────────────│──────────────▶│ score/reason          │              │
  │                   │              │                 │               │──────────▶│           │              │
  │                   │              │  6× verdicts     │◀─────────────│           │           │              │
  │                   │              │────────────────▶│ collect       │           │           │              │
  │                   │              │                 │ POST /decide  │           │           │              │
  │                   │              │                 │──────────────────────────────────────▶│              │
  │                   │              │                 │   decision    │           │           │              │
  │                   │              │                 │◀──────────────────────────────────────│              │
  │                   │              │                 │ POST /charge (if APPROVE) │           │              │
  │                   │              │                 │──────────────────────────────────────────────────── ▶│
  │                   │              │ txn.executed    │◀───────────────────────────────────────────────────-│
  │                   │              │◀────────────────│ finalize      │           │           │              │
  │   decision JSON   │◀─────────────│                 │               │           │           │              │
  │◀──────────────────│              │                 │               │           │           │              │
```

## 5. Error & edge contracts

- **Validation errors** → `422` with field detail (Pydantic).
- **Idempotency** → repeat `idempotency_key` returns the original decision, never
  re-charges.
- **Deadline exceeded** → decision engine applies missing-verdict policy; response
  flags `partial: true` and lists `degraded_agents`.
- **Processor failure** → routing retry to an alternate processor if available, else
  DECLINE with reason.
- **Poison events** → routed to `*.dlq` after max retries; metrics + alert.
