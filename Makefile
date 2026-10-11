# ACIP operator UX (docs/07 §3). Phase 1 implements the foundation targets; the
# application-service targets are stubbed until those services exist.

COMPOSE := docker compose -f deploy/docker-compose.yml

.DEFAULT_GOAL := help
.PHONY: help build up up-infra down topics train seed lint format test demo smoke logs

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  %-10s %s\n", $$1, $$2}'

# --- stack (docs/07 §1): infra + the seven Phase 2 services ---
build: ## Build/pull all images (infra + the seven services)
	$(COMPOSE) build

up: ## Start the full stack (infra + services); only checkout-api on :8080
	$(COMPOSE) up -d

up-infra: ## Start infra only (Kafka/Neo4j/Postgres/Redis/observability)
	$(COMPOSE) up -d redpanda kafka-init neo4j postgres redis prometheus grafana jaeger

down: ## Stop the stack and remove containers
	$(COMPOSE) down

topics: ## Create Kafka topics (idempotent)
	$(COMPOSE) up kafka-init

# --- ML (docs/05) ---
train: ## Generate the synthetic dataset then train risk + fraud models
	cd ml && uv run python training/generate_dataset.py
	cd ml && uv run python training/train.py

# --- demo data (docs/05 §6.3) ---
seed: ## Seed Neo4j + Postgres with the demo scenarios
	uv run python scripts/seed.py

# --- tooling ---
lint: ## Ruff lint across the codebase
	uv run ruff check libs/acip-common ml scripts

format: ## Format with black + ruff
	uv run black libs/acip-common ml scripts
	uv run ruff format libs/acip-common ml scripts

test: ## Run unit tests across acip-common + all services
	uv run pytest libs/acip-common services

# --- demo / smoke (docs/06 §1, §4) ---
# Minimal core-path smoke: POST a clean checkout to the running checkout-api and print
# the decision. Proves the no-agents end-to-end path reaches a decision. The full
# four-scenario demo with all agents is a later phase.
demo: smoke ## Run the minimal core-path smoke (alias of `smoke`)

smoke: ## POST a sample checkout to the running stack and print the decision
	uv run python scripts/demo.py

logs: ## Tail aggregated service logs (Ctrl-C to stop)
	$(COMPOSE) logs -f
