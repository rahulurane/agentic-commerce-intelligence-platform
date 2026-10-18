#!/usr/bin/env bash
#
# ACIP one-command local bring-up (docs/07 §3).
#
# A non-expert can run `./start.sh` from the repo root and get the full stack built,
# started, seeded, and demoed with no further steps. It orchestrates the open-source
# tools exactly as deploy/docker-compose.yml defines them (Redpanda/Kafka, Neo4j,
# Postgres, Redis, Prometheus, Grafana, Jaeger) plus the 14 ACIP application services;
# it does NOT redefine any service. Build/up reuse the Makefile targets so there is one
# source of truth for the compose commands.
#
# Steps: preconditions -> .env -> models -> build+up -> wait-for-health -> seed -> demo
# -> summary. Idempotent: re-running brings the stack to the same healthy, seeded state.
#
# Tear the stack down with ./stop.sh (add -v to also drop the data volumes).
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE="docker compose -f deploy/docker-compose.yml"

# Host-side connection strings: when we seed / drive the demo from the HOST (not from
# inside a container), the stores are reachable on localhost via the published ports,
# NOT on the compose service names. The agents inside the network still use the service
# names from the compose env.
HOST_POSTGRES_DSN="postgresql://acip:acip@localhost:5432/acip"
HOST_NEO4J_URI="bolt://localhost:7687"
HOST_REDIS_URL="redis://localhost:6379/0"
CHECKOUT_URL="http://localhost:8080"

HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-300}" # seconds to wait for the stack to come up

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die() {
	printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2
	exit 1
}

# --- 1. preconditions ------------------------------------------------------- #
say "Checking prerequisites"
command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH."
docker compose version >/dev/null 2>&1 ||
	die "'docker compose' (v2) is not available. Install Docker Compose v2."
docker info >/dev/null 2>&1 ||
	die "The Docker daemon is not running. Start Docker Desktop (or dockerd) and retry."
echo "docker + docker compose available; daemon is up."

# --- 2. .env ---------------------------------------------------------------- #
say "Ensuring .env exists"
if [ -f .env ]; then
	echo ".env already present; leaving it untouched."
else
	cp .env.example .env
	echo "Created .env from .env.example (edit it to add real creds; the default stack needs none)."
fi

# --- 3. ml models ----------------------------------------------------------- #
say "Checking trained ML artifacts"
if [ -f ml/models/model_card.json ]; then
	echo "models present (ml/models/model_card.json), skipping train."
else
	echo "No trained models found; running 'make train' (first run only, this can take a few minutes)."
	make train
fi

# --- 4. build + up ---------------------------------------------------------- #
# Raise uv's HTTP timeout inside the image builds so a slow mirror does not fail the
# build on the default 30s cap.
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-180}"
say "Building images (infra + 14 services)"
make build
say "Starting the full stack (detached)"
make up

# --- 5. wait for health ----------------------------------------------------- #
say "Waiting for the stack to become healthy (timeout ${HEALTH_TIMEOUT}s)"

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
		missing) die "container $name is not running; 'make up' did not start it." ;;
		esac
		sleep 3
	done
	die "timed out waiting for $name to become healthy (last status: ${state:-unknown})."
}

for c in acip-redpanda acip-neo4j acip-postgres acip-redis; do
	wait_for_container_health "$c"
done

# checkout-api has no compose healthcheck; poll its /healthz over the published port.
say "Waiting for checkout-api /healthz at ${CHECKOUT_URL}"
deadline=$((SECONDS + HEALTH_TIMEOUT))
until curl -fsS "${CHECKOUT_URL}/healthz" >/dev/null 2>&1; do
	[ "$SECONDS" -lt "$deadline" ] || die "timed out waiting for checkout-api at ${CHECKOUT_URL}/healthz."
	sleep 3
done
echo "  checkout-api: ok"

# Give the agent consumers a moment to join their consumer groups so the first
# transactions are evaluated by the full set of agents.
echo "Giving the agent consumers a few seconds to join their groups..."
sleep 8

# --- 6. seed ---------------------------------------------------------------- #
say "Seeding Neo4j + Postgres with the demo scenarios"
POSTGRES_DSN="$HOST_POSTGRES_DSN" NEO4J_URI="$HOST_NEO4J_URI" REDIS_URL="$HOST_REDIS_URL" \
	uv run python scripts/seed.py

# --- 7. demo ---------------------------------------------------------------- #
say "Running the five-scenario demo"
CHECKOUT_URL="$CHECKOUT_URL" uv run python scripts/demo.py

# --- 8. summary ------------------------------------------------------------- #
say "ACIP is up. Summary"
cat <<EOF

  Checkout API (public):  ${CHECKOUT_URL}
    health:               ${CHECKOUT_URL}/healthz
  Neo4j Browser:          http://localhost:7474   (user neo4j / password 'password')
  Grafana:                http://localhost:3000   (admin / admin, anon enabled)
  Jaeger (traces):        http://localhost:16686
  Prometheus:             http://localhost:9090

  Try a checkout:
    curl -s ${CHECKOUT_URL}/v1/checkout \\
      -H 'content-type: application/json' \\
      -d '{"merchant_id":"mrc_demo","customer_id":"cus_clean","amount":120.0,
           "currency":"INR","payment_method":{"type":"upi","token":"tok_demo"},
           "context":{"device_fingerprint":"dev_clean"},"idempotency_key":"idem_try_1"}'

  Tail logs:   make logs       (or: ${COMPOSE} logs -f <service>)
  Re-run demo: CHECKOUT_URL=${CHECKOUT_URL} uv run python scripts/demo.py
  Stop:        ./stop.sh       (add -v to also remove data volumes)

EOF
