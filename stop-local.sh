#!/usr/bin/env bash
#
# ACIP LOCAL teardown. Companion to ./start-local.sh.
#
#   ./stop-local.sh         stop the host app services + Vite dev server; LEAVE infra up
#   ./stop-local.sh --all   also stop the Docker infra (containers kept, data volumes kept)
#   ./stop-local.sh -v      also remove the data volumes (fresh state next start)
#   ./stop-local.sh -h      show this usage
#
# Kills the tracked host PIDs recorded in run/*.pid (the 14 app services + run/ui.pid for
# the Vite dev server), then — only with --all/-v — tears the Docker infra down. Running
# with no pid files is a clean no-op.
set -euo pipefail

cd "$(dirname "$0")"

COMPOSE="docker compose -f deploy/docker-compose.yml"
RUN_DIR="run"

STOP_INFRA=false
REMOVE_VOLUMES=false
case "${1:-}" in
"") ;;
--all) STOP_INFRA=true ;;
-v | --volumes) REMOVE_VOLUMES=true ;;
-h | --help)
	echo "Usage: ./stop-local.sh [--all | -v|--volumes | -h|--help]"
	echo "  (no flag)      stop host app services + Vite dev server; leave infra up"
	echo "  --all          also stop the Docker infra (keep data volumes)"
	echo "  -v|--volumes   also remove the data volumes (Redpanda/Neo4j/Postgres/Redis/Grafana)"
	exit 0
	;;
*)
	echo "unknown argument: $1 (use --all to also stop infra, -v to also remove volumes, -h for help)" >&2
	exit 2
	;;
esac

# --- stop the tracked host processes --------------------------------------- #
stopped=0
if [ -d "$RUN_DIR" ]; then
	for pidfile in "$RUN_DIR"/*.pid; do
		[ -e "$pidfile" ] || continue # no matches -> clean no-op
		svc="$(basename "$pidfile" .pid)"
		pid="$(cat "$pidfile" 2>/dev/null || true)"
		if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
			kill "$pid" >/dev/null 2>&1 || true
			# Give it a moment to exit, then confirm it is gone.
			for _ in 1 2 3 4 5 6 7 8 9 10; do
				kill -0 "$pid" >/dev/null 2>&1 || break
				sleep 1
			done
			if kill -0 "$pid" >/dev/null 2>&1; then
				echo "  ${svc}: pid ${pid} did not exit after SIGTERM (still running)"
			else
				echo "  ${svc}: stopped (pid ${pid})"
				stopped=$((stopped + 1))
			fi
		else
			echo "  ${svc}: not running (stale pid file)"
		fi
		rm -f "$pidfile"
	done
fi

if [ "$stopped" -eq 0 ]; then
	echo "No running host processes found (nothing to stop)."
else
	echo "Stopped ${stopped} host process(es)."
fi

# --- optionally tear down the Docker infra --------------------------------- #
if [ "$REMOVE_VOLUMES" = true ]; then
	echo "==> Stopping the Docker infra and removing containers + data volumes"
	$COMPOSE down -v
	echo "Done: infra containers removed and data volumes deleted."
elif [ "$STOP_INFRA" = true ]; then
	echo "==> Stopping the Docker infra (data volumes kept)"
	$COMPOSE stop
	echo "Done: infra stopped; data volumes kept."
else
	echo "Left the Docker infra running (use --all to stop it, -v to also drop volumes)."
fi
