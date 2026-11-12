# ACIP — Demo Walkthrough (Leadership)

**Agentic Commerce Intelligence Platform (ACIP)** — a real-time, pre-transaction
payment-decisioning platform. This guide is a scripted walkthrough for presenting the
working system. It assumes nothing: follow it top to bottom.

> **One-liner for the room:** *"Before a payment is attempted, ACIP runs six specialist
> AI agents in parallel over a shared view of the transaction, and returns an
> explainable APPROVE / DECLINE / CHALLENGE decision in under a second — running
> entirely on open-source infrastructure, with no cloud dependency."*

---

## 1. What this is (30-second framing)

Most payment stacks decide *after* the fact. ACIP decides *before* the payment runs. It:

- **Intercepts** every checkout and evaluates it in real time.
- **Runs six specialized agents in parallel** — Risk, Fraud, Routing, Policy, Merchant,
  and Checkout-Personalization — each looking at the *same shared signals*.
- **Aggregates** their verdicts into one decision with a clear, auditable explanation.
- **Explains every decision** — each agent produces a rationale and evidence, so no
  decision is a black box.
- **Runs locally on open-source tools** (Kafka, Neo4j, Postgres, Redis) — no cloud
  account, no vendor lock-in, no credentials required to demo.

## 2. The decision outcomes

Every transaction resolves to one of:

| Decision | Meaning |
|----------|---------|
| **APPROVE** | Low risk — let it through (and route it to the healthiest processor). |
| **CHALLENGE** | Borderline — step up (e.g. extra authentication) before allowing. |
| **DECLINE** | Blocked — a hard rule (fraud or policy) vetoed it. |

## 3. Architecture in one picture

```text
Customer → checkout-api → commerce-orchestrator ──(builds the SHARED REPRESENTATION)
                                   │
                                   │  fan out (Kafka)
          ┌──────────┬────────────┼────────────┬──────────────┬───────────────────┐
          ▼          ▼            ▼            ▼              ▼                   ▼
        Risk       Fraud       Routing      Policy        Merchant     Checkout-Personalization
          │          │            │            │              │                   │
          └──────────┴──────► verdicts (Kafka) ◄──────────────┴───────────────────┘
                                   │
                            Decision Engine  → APPROVE / DECLINE / CHALLENGE (+ explanation)
                                   │
                         Payment Processor (simulated)
```

- The **shared representation** = one unified view of the transaction (features + graph
  signals) built once and read by every agent, so all decisions see the same facts.
- **Kafka** carries the fan-out and the verdicts; it is also the event log the system is
  rebuilt from (nothing is overwritten — full auditability).
- **Neo4j** is the intelligence graph: it links customers, devices, and transactions, so
  fraud rings that are invisible in isolation become obvious as connections.

*(Full technical detail lives in `docs/01`–`docs/07`.)*

---

## 4. Before the demo — start the platform

**Prerequisite:** Docker Desktop running. Nothing else.

From the repo root:

```sh
./start.sh
```

This single command: checks Docker, creates config, trains the ML models on first run,
builds and starts the whole stack (infrastructure + 14 services), waits for everything
to be healthy, seeds the demo data, and runs the five scenarios. First run takes a few
minutes (image builds + model training); later runs are faster.

When it finishes it prints the live URLs. Keep that output handy — you'll use it.

> **Tip:** run `./start.sh` once *before* the meeting so the images are built and the
> models trained. Then it comes up in well under a minute when you present.

### The URLs it gives you

| What | URL | Login |
|------|-----|-------|
| Demo UI (React, start here) | <http://localhost:8090> | — |
| Checkout API (the product) | <http://localhost:8080> | — |
| Neo4j Browser (the graph) | <http://localhost:7474> | `neo4j` / `password` |
| Jaeger (request traces) | <http://localhost:16686> | — |

> **Show the Demo UI and the Neo4j graph.** Grafana (:3000) and Prometheus (:9090) also
> start with the stack, but the services do not export metrics yet, so they have no
> dashboards or data. Leave them out of the demo.

### Alternative: run locally (host processes)

For development you can run a **local mode** instead: the open-source infra stays in
Docker, but the 14 application services run as host `uvicorn` processes and the React UI
runs via the Vite dev server. The all-Docker `./start.sh` above is unchanged; the two
modes use different ports.

**Prerequisite (in addition to Docker):** **Node 20** on the host (the Vite dev server
needs it; `./start.sh` does not). `start-local.sh` checks for it and fails with an
install hint if missing.

```sh
make up-local     # infra in Docker, 14 services as host processes, Vite UI on 5173
make down-local   # stop host processes (leaves infra up)
```

In local mode the **Demo UI is at <http://localhost:5173>** (vs <http://localhost:8090>
in Docker mode); `checkout-api` stays on <http://localhost:8080>. Host port map:

| Service | Port | Service | Port |
|---------|------|---------|------|
| checkout-api | 8080 | risk-agent | 8091 |
| commerce-orchestrator | 8081 | fraud-agent | 8092 |
| representation-service | 8082 | routing-agent | 8093 |
| ml-scoring-service | 8083 | policy-agent | 8094 |
| llm-gateway | 8084 | merchant-agent | 8095 |
| decision-engine | 8085 | checkout-personalization-agent | 8096 |
| payment-processor-sim | 8086 | graph-projector | 8097 |

View logs with `tail -f logs/*.log`. Stop with `./stop-local.sh` (add `--all` to also
stop the Docker infra, or `-v` to also drop the data volumes). The five scenarios in §5
below work identically — just point the browser at :5173 instead of :8090.

---

## 5. The demo — five scenarios

The heart of the demo is one command that runs all five scenarios and prints each
decision:

```sh
make demo
# (or, if the stack is already up and seeded)
uv run python scripts/demo.py
```

You'll see one line per scenario. Here is what each one proves — **walk the room through
these one at a time.**

| # | Scenario | Amount | What's special about it | Decision | Why |
|---|----------|--------|-------------------------|----------|-----|
| 1 | `clean_shopper` | ₹120 | Normal customer, good history | **APPROVE** | Low risk + low fraud → approved and routed to the healthiest processor |
| 2 | `ring_member` | ₹90 | Device shared across a fraud ring | **DECLINE** | The Fraud agent sees the shared-device ring in the graph and vetoes it |
| 3 | `high_value_midrisk` | ₹4,800 | Large but legitimate purchase | **CHALLENGE** | The Merchant agent steps it up for review — not blocked, just verified |
| 4 | `sanctioned_geo` | ₹200 | Customer in a blocked region | **DECLINE** | The Policy agent applies a hard compliance veto |
| 5 | `unhealthy_preferred_route` | ₹260 | Preferred processor is degraded | **APPROVE** (alternate route) | The Routing agent scores every route and picks a healthy alternate |

**The story these tell together:**
- Scenarios 2 & 4 show **two different kinds of "no"** — fraud (pattern-based) vs. policy
  (rule-based).
- Scenario 3 shows the system is **not just a blocklist** — it can say *"allow, but
  verify,"* which protects revenue (you don't lose a good ₹4,800 sale, you just confirm
  it).
- Scenario 5 shows **resilience** — a failing processor doesn't fail the payment; the
  system reroutes in real time.

### Expected output

```text
[OK] clean_shopper: decision=APPROVE route=processor_a transaction_id=txn_...
[OK] ring_member: decision=DECLINE route=None transaction_id=txn_...
[OK] high_value_midrisk: decision=CHALLENGE route=None transaction_id=txn_...
[OK] sanctioned_geo: decision=DECLINE route=None transaction_id=txn_...
[OK] unhealthy_preferred_route: decision=APPROVE route=processor_a transaction_id=txn_...

OK: all 5 scenarios returned their expected decision
```

---

### Demo UI (React)

Prefer a browser over the terminal? Open the **Demo UI** at
<http://localhost:8090> (brought up by `./start.sh` as the `demo-ui` container). It is a
thin React front end over the same `checkout-api`:

- One click on a scenario button POSTs it to `/v1/checkout` and shows a prominent
  **colored decision banner** — green APPROVE, amber CHALLENGE, red DECLINE.
- It then polls `GET /v1/transactions/{id}` and fills in the **six agent verdict cards**
  (risk, fraud, routing, policy, merchant, checkout-personalization), tolerating the
  brief window where the agents are still committing.
- A **custom checkout** form and a **recent transactions** list (with click-through to
  re-inspect) and a **decision trace / explain** view round it out.

This is the most leadership-friendly way to walk the five scenarios — the colored
banner and the agent cards make the "six specialists in parallel" story visual. The
terminal `make demo` below is the equivalent scripted path.

---

## 6. Show a single transaction live (the "wow" moment)

Run one checkout by hand so the room sees a real API call return a real decision:

```sh
curl -s http://localhost:8080/v1/checkout \
  -H 'content-type: application/json' \
  -d '{"merchant_id":"mrc_demo","customer_id":"cus_clean","amount":120.0,
       "currency":"INR","payment_method":{"type":"upi","token":"tok_demo"},
       "context":{"device_fingerprint":"dev_clean"},"idempotency_key":"idem_live_1"}' | python3 -m json.tool
```

You get back the decision, the chosen route, the composite score, and a plain-English
explanation. Note the `transaction_id` — you'll use it next.

### Then show the *explanation* (this is the differentiator)

```sh
curl -s http://localhost:8080/v1/transactions/<transaction_id>/explain | python3 -m json.tool
```

This returns the full decision trace: the inputs, the strategy, and the final decision.
**Talking point:** *"Every decision is reconstructable and auditable — critical for a
regulated payments business. Nothing is a black box."*

### Show the fraud graph (optional, high-impact)

Open **Neo4j Browser** (<http://localhost:7474>, login `neo4j` / `password`) and run
this to reveal the fraud ring — a single device linked to several customers:

```cypher
MATCH (d:Device)-[:LINKED_TO]->(c:Customer)
WITH d, collect(c) AS customers
WHERE size(customers) > 1
RETURN d, customers
```

To just see the whole seeded graph:

```cypher
MATCH (d:Device)-[:LINKED_TO]->(c:Customer) RETURN d, c LIMIT 50
```

Point at the shared device (`dev_shared`) fanning out to multiple customers — *"this is
the fraud ring the Fraud agent caught in scenario 2. A single-transaction view can't see
this; the graph can."*

---

## 7. Suggested 5-minute demo flow

1. **(0:00) Framing** — read the one-liner from the top. State the problem: decisions
   happen too late, in siloed models.
2. **(0:30) Show it's real** — `./start.sh` output (or already up); show the stack of
   14 services in one `docker compose ps` if asked.
3. **(1:30) Run `make demo`** — walk the five scenarios using the table in §5. This is
   the core.
4. **(3:30) One live call** — the `curl` in §6, then the `/explain` call. Land the
   "explainable, auditable" point.
5. **(4:30) Close** — "all open-source, runs on a laptop, no cloud bill, and every piece
   is a service we can scale or swap independently." Mention the roadmap (§9).

---

## 8. If something goes wrong (quick recovery)

| Symptom | Fix |
|---------|-----|
| `./start.sh` says Docker isn't running | Start Docker Desktop, re-run. |
| A scenario shows `FAIL` | The seed may not have loaded. Run `make seed`, then `make demo`. |
| Agents seem to miss a decision | Give consumers a few seconds to join, then re-run `make demo`. |
| Want a totally clean slate | `./stop.sh -v` then `./start.sh`. |
| Need to see what a service is doing | `make logs` (or `docker compose -f deploy/docker-compose.yml logs -f <service>`). |

Stop everything when done:

```sh
./stop.sh        # stop containers, keep data
./stop.sh -v     # stop + wipe data for a fresh next run
```

---

## 9. Talking points & what's next

**Why the architecture matters (if asked):**
- **Six independent agents** → each scales and evolves on its own; a slow fraud model
  never blocks routing.
- **Shared representation** → every agent sees the same signals (consistency), and it's
  the clean seam where a richer learned model could drop in later.
- **Event-sourced** → the full history is replayable; decisions are auditable end to end.
- **Provider-agnostic AI** → the LLM layer is pluggable (Gemini, OpenAI, etc.); the demo
  runs on a built-in mock so it needs no cloud keys at all.

**Honest scope (so expectations are right):**
- This is a **working POC**, architected production-grade. The ML models are trained on
  **synthetic data**, so the accuracy numbers are illustrative of the pipeline, not of
  real-world fraud detection.
- The payment processor is **simulated** (configurable success/latency) so the demo is
  deterministic.

**Natural next steps:**
- Point the ML models at real (anonymized) transaction data.
- Add service metrics (a shared `/metrics` endpoint) and Grafana dashboards per agent
  (latency, decision mix, LLM provider usage). Prometheus and Grafana already run in the
  stack but are not yet fed by the services.
- Deploy the same images to Kubernetes (the layout is already K8s-ready).

---

*Deeper technical docs: `docs/01-system-architecture.md` through
`docs/07-deployment-and-ops.md`.*
