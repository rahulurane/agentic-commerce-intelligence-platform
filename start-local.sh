#!/usr/bin/env bash
#
# ACIP LOCAL (host-process) bring-up. Companion to the all-Docker ./start.sh.
#
# This mode keeps the open-source backing infra in Docker (Redpanda/Kafka, Neo4j,
# Postgres, Redis, Prometheus, Grafana, Jaeger via `make up-infra`) but runs the 14 ACIP
# application services as HOST uvicorn processes — each on its own local port — and the
# React demo UI via the Vite dev server on http://localhost:5173. It does NOT touch the
# all-Docker path: ./start.sh, `make up`, and the compose service blocks are unchanged,
# and the ports here (app 8080-8086/8091-8097, UI 5173) never clash with the Docker UI on
# 8090. Env comes from .env.local (copied from .env.local.example if absent).
#
# Steps: prereqs (incl. Node 20) -> infra up -> wait-for-health -> models -> .env.local
# -> seed -> launch 14 host services -> wait checkout-api -> Vite dev server -> demo
# -> summary. Logs land in logs/, PIDs in run/. Stop everything with ./stop-local.sh.
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE="docker compose -f deploy/docker-compose.yml"

# Host-side connection strings for seeding from the HOST (localhost + published ports).
HOST_POSTGRES_DSN="postgresql://acip:acip@localhost:5432/acip"
HOST_NEO4J_URI="bolt://localhost:7687"
HOST_REDIS_URL="redis://localhost:6379/0"
CHECKOUT_URL="http://localhost:8080"

HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}" # seconds to wait for infra / checkout-api

LOG_DIR="logs"
RUN_DIR="run"

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die() {
	printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2
	exit 1
}

# service -> local port map (checkout-api is the only public service; the rest are the
# core path + the six agents + graph-projector). Module names are the Python packages.
# Keep in sync with .env.local.example's *_URL ports and FEAT-002's port map.
SERVICES=(
	"checkout_api:8080"
	"commerce_orchestrator:8081"
	"representation_service:8082"
	"ml_scoring_service:8083"
	"llm_gateway:8084"
	"decision_engine:8085"
	"payment_processor_sim:8086"
	"risk_agent:8091"
	"fraud_agent:8092"
	"routing_agent:8093"
	"policy_agent:8094"
	"merchant_agent:8095"
	"checkout_personalization_agent:8096"
	"graph_projector:8097"
)

# --- 1. preconditions ------------------------------------------------------- #
say "Checking prerequisites"
command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH."
docker compose version >/dev/null 2>&1 ||
	die "'docker compose' (v2) is not available. Install Docker Compose v2."
docker info >/dev/null 2>&1 ||
	die "The Docker daemon is not running. Start Docker Desktop (or dockerd) and retry."
command -v uv >/dev/null 2>&1 || die "uv is not installed or not on PATH."
# Local mode runs the React UI via the Vite dev server, which needs a host Node 20.
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
	die "node/npm not found. Local mode runs the React UI via the Vite dev server, which needs Node 20. Install Node 20 (e.g. 'brew install node@20' or https://nodejs.org) and retry. (The all-Docker path ./start.sh needs no host Node.)"
fi
echo "docker + docker compose + uv + node/npm available; daemon is up."

mkdir -p "$LOG_DIR" "$RUN_DIR"

# --- 2. infra (Docker) ------------------------------------------------------ #
say "Starting backing infra in Docker (make up-infra)"
make up-infra

# --- 3. wait for infra health ----------------------------------------------- #
say "Waiting for infra to become healthy (timeout ${HEALTH_TIMEOUT}s)"

wait_for_container_health() {
	# $1 = container name. Waits until docker reports health 'healthy'.
	local name="$1" deadline=$((SECONDS + HEALTH_TIMEOUT)) state
	while [ "$SECONDS" -lt "$deadline" ]; do
		state="$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || echo missing)"
		case "$state" in
		healthy)
			echo "  $name: healthy"
			return 0
			;;
		missing) die "container $name is not running; 'make up-infra' did not start it." ;;
		esac
		sleep 3
	done
	die "timed out waiting for $name to become healthy (last status: ${state:-unknown})."
}

for c in acip-redpanda acip-neo4j acip-postgres acip-redis; do
	wait_for_container_health "$c"
done

# --- 4. ml models ----------------------------------------------------------- #
say "Checking trained ML artifacts"
if [ -f ml/models/model_card.json ]; then
	echo "models present (ml/models/model_card.json), skipping train."
else
	echo "No trained models found; running 'make train' (first run only, this can take a few minutes)."
	make train
fi

# --- 5. .env.local ---------------------------------------------------------- #
say "Ensuring .env.local exists"
if [ -f .env.local ]; then
	echo ".env.local already present; leaving it untouched."
else
	cp .env.local.example .env.local
	echo "Created .env.local from .env.local.example (localhost overrides for host processes)."
fi

# --- 6. seed ---------------------------------------------------------------- #
say "Seeding Neo4j + Postgres with the demo scenarios"
POSTGRES_DSN="$HOST_POSTGRES_DSN" NEO4J_URI="$HOST_NEO4J_URI" REDIS_URL="$HOST_REDIS_URL" \
	uv run python scripts/seed.py

# --- 7. launch the 14 app services as host processes ------------------------ #
say "Launching the 14 application services as host uvicorn processes"
for entry in "${SERVICES[@]}"; do
	module="${entry%%:*}"
	port="${entry##*:}"
	svc="${module//_/-}"
	# Each service reads env from .env.local; stdout/stderr -> logs/<svc>.log; PID -> run/<svc>.pid.
	# The container port is hardcoded in each Dockerfile CMD; here we override only the
	# uvicorn --port CLI arg (no Settings/Dockerfile/compose change).
	( set -a; . ./.env.local; set +a; \
		exec uv run uvicorn "${module}.main:app" --host 127.0.0.1 --port "${port}" ) \
		>"${LOG_DIR}/${svc}.log" 2>&1 &
	echo $! >"${RUN_DIR}/${svc}.pid"
	echo "  ${svc}: pid $(cat "${RUN_DIR}/${svc}.pid") on 127.0.0.1:${port} (logs/${svc}.log)"
done

# --- 8. wait for checkout-api ----------------------------------------------- #
say "Waiting for checkout-api /healthz at ${CHECKOUT_URL}"
deadline=$((SECONDS + HEALTH_TIMEOUT))
until curl -fsS "${CHECKOUT_URL}/healthz" >/dev/null 2>&1; do
	[ "$SECONDS" -lt "$deadline" ] || die "timed out waiting for checkout-api at ${CHECKOUT_URL}/healthz (see logs/checkout-api.log)."
	sleep 3
done
echo "  checkout-api: ok"

# Give the agent consumers a moment to join their consumer groups so the first
# transactions are evaluated by the full set of agents.
echo "Giving the agent consumers a few seconds to join their groups..."
sleep 8

# --- 9. React UI (Vite dev server) ------------------------------------------ #
say "Starting the React demo UI (Vite dev server on 5173)"
if [ ! -d ui/node_modules ]; then
	echo "ui/node_modules missing; running 'npm ci' in ui/ (first run only)."
	( cd ui && npm ci )
fi
( cd ui && VITE_CHECKOUT_API_URL="${CHECKOUT_URL}" exec npm run dev -- --port 5173 ) \
	>"${LOG_DIR}/ui.log" 2>&1 &
echo $! >"${RUN_DIR}/ui.pid"
echo "  ui: pid $(cat "${RUN_DIR}/ui.pid") on http://localhost:5173 (logs/ui.log)"

# --- 10. demo --------------------------------------------------------------- #
say "Running the five-scenario demo"
CHECKOUT_URL="$CHECKOUT_URL" uv run python scripts/demo.py

# --- 11. summary ------------------------------------------------------------ #
say "ACIP is up in LOCAL mode. Summary"
cat <<EOF

  Demo UI (React, Vite dev):  http://localhost:5173   (start here for the walkthrough)
  Checkout API (public):      ${CHECKOUT_URL}
    health:                   ${CHECKOUT_URL}/healthz
  Neo4j Browser:              http://localhost:7474   (user neo4j / password 'password')
  Grafana:                    http://localhost:3000   (admin / admin, anon enabled)
  Jaeger (traces):            http://localhost:16686
  Prometheus:                 http://localhost:9090

  App services run as HOST processes (infra stays in Docker):
    checkout-api 8080   commerce-orchestrator 8081   representation-service 8082
    ml-scoring-service 8083   llm-gateway 8084   decision-engine 8085
    payment-processor-sim 8086   risk-agent 8091   fraud-agent 8092
    routing-agent 8093   policy-agent 8094   merchant-agent 8095
    checkout-personalization-agent 8096   graph-projector 8097

  Tail logs:   tail -f ${LOG_DIR}/*.log
  Re-run demo: CHECKOUT_URL=${CHECKOUT_URL} uv run python scripts/demo.py
  Stop:        ./stop-local.sh            (stops host processes; leaves infra up)
               ./stop-local.sh --all      (also stops the Docker infra)
               ./stop-local.sh -v         (also removes the data volumes)

EOF
