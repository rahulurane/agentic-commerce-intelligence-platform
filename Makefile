# ACIP operator UX (docs/07 §3). Phase 1 implements the foundation targets; the
# application-service targets are stubbed until those services exist.

COMPOSE := docker compose -f deploy/docker-compose.yml

.DEFAULT_GOAL := help
.PHONY: help build up down topics train seed lint format test demo logs

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  %-10s %s\n", $$1, $$2}'

# --- infrastructure (docs/07 §1) ---
build: ## Pull/build the infra stack images
	$(COMPOSE) build

up: ## Start the infra stack (Kafka/Neo4j/Postgres/Redis/observability)
	$(COMPOSE) up -d

down: ## Stop the infra stack and remove containers
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

test: ## Run acip-common unit tests
	uv run pytest libs/acip-common

# --- application services (implemented in a later phase) ---
demo: ## (later phase) run the demo driver
	@echo "demo: implemented in a later phase"

logs: ## (later phase) tail aggregated service logs
	@echo "logs: implemented in a later phase"
