# agentic-commerce-intelligence-platform

Agentic Commerce Intelligence Platform (ACIP) — a payment-decisioning POC that runs an
agentic decision path (six evaluating agents aggregated into an APPROVE / DECLINE /
CHALLENGE decision) over a local stack of open-source infrastructure.

## Quickstart (one command)

From the repo root, with Docker running:

```sh
./start.sh
```

`start.sh` checks prerequisites, creates `.env` from `.env.example` if absent, trains the
ML models on first run, builds and starts the full stack (backing infra + the 14
application services), waits for health, seeds the demo scenarios, and runs the
five-scenario demo. When it finishes it prints the service URLs (the React Demo UI on
<http://localhost:8090>, checkout-api on <http://localhost:8080>, Neo4j Browser,
Grafana, Jaeger, Prometheus) and a sample `curl`.

Open the **Demo UI** at <http://localhost:8090> to run the scenarios from a browser and
watch the six agent verdicts populate. The UI source lives in [`ui/`](ui/README.md).

Tear everything down with:

```sh
./stop.sh        # stop + remove containers (keep data volumes)
./stop.sh -v     # also remove the data volumes (fresh state next start)
```

## Make targets

Run `make help` for the full list. Common ones:

- `make up` / `make down` — start / stop the full stack
- `make seed` — seed Neo4j + Postgres with the demo scenarios
- `make demo` — run the five-scenario demo against the running stack
- `make train` — generate the synthetic dataset and train the risk + fraud models
- `make logs` — tail aggregated service logs

The stack runs with no cloud credentials: the LLM gateway degrades to a mock provider,
so agents emit a templated rationale and the decision never blocks on the LLM.
