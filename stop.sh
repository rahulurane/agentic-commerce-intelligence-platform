#!/usr/bin/env bash
#
# ACIP teardown (docs/07 §3). Companion to ./start.sh.
#
#   ./stop.sh        stop + remove containers (keeps the data volumes)
#   ./stop.sh -v     also remove the named data volumes (fresh state next start)
#
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE="docker compose -f deploy/docker-compose.yml"

REMOVE_VOLUMES=false
case "${1:-}" in
"") ;;
-v | --volumes) REMOVE_VOLUMES=true ;;
-h | --help)
	echo "Usage: ./stop.sh [-v|--volumes]"
	echo "  (no flag)      stop and remove containers; keep data volumes"
	echo "  -v|--volumes   also remove the data volumes (Redpanda/Neo4j/Postgres/Redis/Grafana)"
	exit 0
	;;
*)
	echo "unknown argument: $1 (use -v to also remove volumes, -h for help)" >&2
	exit 2
	;;
esac

if [ "$REMOVE_VOLUMES" = true ]; then
	echo "==> Stopping the stack and removing containers + data volumes"
	$COMPOSE down -v
	echo "Done: containers removed and data volumes deleted (next ./start.sh starts fresh)."
else
	echo "==> Stopping the stack and removing containers (data volumes kept)"
	$COMPOSE down
	echo "Done: containers removed; data volumes kept (run ./stop.sh -v to also drop them)."
fi
