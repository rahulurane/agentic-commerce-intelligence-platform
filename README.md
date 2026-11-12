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
Jaeger, plus Grafana and Prometheus, which run but have no service metrics wired in yet)
and a sample `curl`.

Open the **Demo UI** at <http://localhost:8090> to run the scenarios from a browser and
watch the six agent verdicts populate. The UI source lives in [`ui/`](ui/README.md).

Tear everything down with:

```sh
./stop.sh        # stop + remove containers (keep data volumes)
./stop.sh -v     # also remove the data volumes (fresh state next start)
```

## Run locally (host processes)

The platform runs two ways. The default above is **all-Docker** (`./start.sh` builds and
runs everything, including the 14 services, in containers; the Demo UI is served at
<http://localhost:8090>). There is also a **local mode** that keeps the open-source infra
in Docker but runs the 14 application services as host `uvicorn` processes and the React
UI via the Vite dev server — handy for fast edit/reload while developing. The all-Docker
path is unchanged; the two modes use different ports and never clash.

**Prerequisites:** Docker running, `uv`, and **Node 20** on the host (the Vite dev server
needs it — `./start.sh` does not). `start-local.sh` checks for Node and fails with an
install hint if it's missing.

```sh
make up-local     # == ./start-local.sh
make down-local   # == ./stop-local.sh  (stops host processes; leaves infra up)
```

`start-local.sh` starts the infra in Docker (`make up-infra`), waits for health, trains
the models on first run, seeds the demo data, launches the 14 services as background host
processes (logs in `logs/`, PIDs in `run/`), starts the Vite dev server, and runs the
five-scenario demo. Config comes from `.env.local` (copied from `.env.local.example` if
absent) which points every store and service URL at `localhost`.

Host port map:

| Service | Port | Service | Port |
|---------|------|---------|------|
| checkout-api | 8080 | risk-agent | 8091 |
| commerce-orchestrator | 8081 | fraud-agent | 8092 |
| representation-service | 8082 | routing-agent | 8093 |
| ml-scoring-service | 8083 | policy-agent | 8094 |
| llm-gateway | 8084 | merchant-agent | 8095 |
| decision-engine | 8085 | checkout-personalization-agent | 8096 |
| payment-processor-sim | 8086 | graph-projector | 8097 |

The Demo UI is at <http://localhost:5173> (local mode) vs <http://localhost:8090>
(Docker mode). View logs with `tail -f logs/*.log`. Stop with:

```sh
./stop-local.sh          # stop host processes; leave infra up
./stop-local.sh --all    # also stop the Docker infra (keep data volumes)
./stop-local.sh -v       # also remove the data volumes (fresh next start)
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
