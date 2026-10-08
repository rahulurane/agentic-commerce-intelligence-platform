# Implementation Plan — ACIP Phase 1 (Foundation Layer)

Phase 1 builds ONLY the foundation every later phase depends on: repo scaffolding, the
`acip-common` shared library, the ML dataset/training layer, the demo seed, and the
infrastructure-only Docker Compose stack with its Makefile. The 14 application services
are NOT implemented here — `services/*` gets empty dirs with `.gitkeep`.

All decisions are grounded in `docs/00`–`docs/07`. Where a doc is silent, a
production-grade choice is made and noted inline. Locked decisions (from the step
prompt and `docs/00`, `docs/07`): Python 3.11+, uv workspace, Redpanda for the Kafka
API, checkout default mode = sync, thresholds approve_max=0.35 / challenge_max=0.70 /
fraud_block=0.85, equal risk/fraud weights 0.5/0.5, FastAPI + Pydantic v2 at edges,
Neo4j 5 / Postgres 16 / Redis 7, tooling Ruff + Black + mypy + pytest, pinned deps,
secrets via env only.

Environment confirmed during exploration: repo has only `docs/` and
`requirement_document/` (nothing committed on `main`); `uv 0.5.4` and
`docker 27.3.1` are available.

## Key decisions (grounded in docs)

- **uv workspace** (`docs/01` §7 lists "Poetry/uv"; step prompt locks uv). Root
  `pyproject.toml` declares `[tool.uv.workspace]` members `libs/*` and (later)
  `services/*`. `acip-common` is a workspace package so services depend on it by path.
  Rationale: single lockfile, one resolver, path deps resolve without publishing.
- **Kafka client library = `confluent-kafka`** (`docs/01` §2 / `docs/07` §1 allow a
  standard broker lib; prompt says confluent-kafka or aiokafka). Choice: `confluent-kafka`
  — librdkafka-backed, the most widely deployed Kafka client, works unchanged against
  Redpanda's Kafka API, and gives production-grade delivery semantics (idempotent
  producer, manual offset commit for the "commit after publish" rule in `docs/02` §6).
  Justified in the module docstring per the prompt. (aiokafka was the alternative; it is
  async-native but pure-Python and less battle-tested for exactly-once-ish producer
  config — confluent-kafka better fits the "production-shaped" stance.)
- **Redpanda image** for the Kafka API (`docs/07` §1 "Redpanda or Confluent Kafka";
  prompt locks Redpanda). Single broker, `redpanda-console` omitted this phase to keep
  the infra set to what `docs/07` §1 enumerates.
- **Structured logging = stdlib `logging` + custom JSON formatter** (no extra heavy
  dep). `trace_id` carried via a `contextvars` context so every log line in a
  transaction correlates (`docs/01` §6, `docs/07` §5). Rationale: zero-dependency,
  deterministic, enough for the POC; OTel wiring is a later-phase service concern.
- **Config via `pydantic-settings`** exactly as `docs/01` §6 / `docs/07` §2 mandate,
  one `Settings` class reading the env vars in `docs/07` §2 with the locked defaults.
- **Shared feature transforms** live in `acip-common.features` and are imported by BOTH
  `ml/training/generate_dataset.py` and (future) live scoring — the no-train/serve-skew
  seam from `docs/05` §3 and §6.2. The 7 core feature columns are fixed by `docs/05`
  §6.2: `amount_zscore`, `velocity_1h`, `method_age_days`, `geo_mismatch`,
  `shared_device_ring_size`, `customer_txn_count_30d`, `customer_chargeback_count`.

## Dependency versions (pinned)

Root dev tooling (workspace-wide dev group): `ruff==0.8.4`, `black==24.10.0`,
`mypy==1.13.0`, `pytest==8.3.4`.

`libs/acip-common` runtime: `pydantic==2.10.4`, `pydantic-settings==2.7.1`,
`confluent-kafka==2.6.1`. (Type stubs for tests: none required beyond pydantic's.)

`ml/` runtime (declared in `ml/pyproject.toml`, not a workspace lib but a uv project):
`numpy==2.1.3`, `pandas==2.2.3`, `pyarrow==18.1.0`, `faker==33.1.0`,
`xgboost==2.1.3`, `lightgbm==4.5.0`, `scikit-learn==1.6.0`, plus a path dep on
`acip-common`.

`scripts/seed.py` deps (declared where scripts resolve — see item 9):
`neo4j==5.27.0`, `psycopg[binary]==3.2.3`, plus `acip-common`.

Versions are current-stable at planning time and compatible with Python 3.11+. The
implementer must run `uv sync` (item 2 verify) and bump any that fail to resolve,
keeping them pinned.

---

- [ ] 1. Create repo scaffolding directories and `.gitkeep` placeholders per `docs/01` §8.
      Create `libs/`, `services/` with one empty subdir per the 14 services from
      `docs/01` §2 each containing a `.gitkeep`, `ml/training/`, `ml/data/`,
      `ml/models/`, `deploy/`, `deploy/prometheus/`, `deploy/grafana/provisioning/`,
      `scripts/`. `ml/data/` and `ml/models/` get a `.gitkeep` (content is gitignored).
      Files: `services/{checkout-api,commerce-orchestrator,risk-agent,fraud-agent,routing-agent,policy-agent,merchant-agent,checkout-personalization-agent,decision-engine,ml-scoring-service,representation-service,llm-gateway,payment-processor-sim,graph-projector}/.gitkeep`,
      `ml/data/.gitkeep`, `ml/models/.gitkeep`
      Verify: `ls services | wc -l` returns 14 and `test -f ml/data/.gitkeep` succeeds.

- [ ] 2. Create the uv workspace root: `pyproject.toml` (workspace members `libs/*`;
      dev group with ruff/black/mypy/pytest pinned; `[tool.ruff]`, `[tool.black]`,
      `[tool.mypy]` config targeting py311, line length 100), `.python-version` (`3.11`),
      `.gitignore` (ignore `.env`, `ml/data/*`, `ml/models/*` with `!*.gitkeep`,
      `__pycache__/`, `.venv/`, `*.pyc`, `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`,
      `*.parquet`, model artifacts), and `.env.example` with every variable from
      `docs/07` §2 and the locked defaults.
      Files: `pyproject.toml`, `.python-version`, `.gitignore`, `.env.example`
      Verify: `uv sync` resolves and creates `.venv` with no error; `uv run ruff --version`
      prints the pinned version.

- [ ] 3. Create the `acip-common` package skeleton and its `pyproject.toml`.
      Package at `libs/acip-common/` with `pyproject.toml` (name `acip-common`,
      requires-python `>=3.11`, deps pydantic/pydantic-settings/confluent-kafka pinned,
      hatchling build backend), `src/acip_common/__init__.py` (exports version), and a
      `py.typed` marker.
      Files: `libs/acip-common/pyproject.toml`, `libs/acip-common/src/acip_common/__init__.py`,
      `libs/acip-common/src/acip_common/py.typed`
      Verify: `uv sync` resolves the workspace; `uv run python -c "import acip_common"`
      succeeds.

- [ ] 4. Implement `acip_common.config` — the typed `Settings` (pydantic-settings) with
      every env var from `docs/07` §2 and locked defaults (KAFKA_BOOTSTRAP, NEO4J_URI,
      NEO4J_AUTH, POSTGRES_DSN, REDIS_URL, LLM_PROVIDER=gemini, LLM_MODEL=gemini-1.5-pro,
      LLM_FALLBACK_PROVIDER=mock, GOOGLE_APPLICATION_CREDENTIALS, DECISION_DEADLINE_MS=800,
      FRAUD_BLOCK_THRESHOLD=0.85, APPROVE_MAX=0.35, CHALLENGE_MAX=0.70, W_RISK=0.5,
      W_FRAUD=0.5, REPRESENTATION_VERSION=1, ENABLED_METHOD_TYPES, SIM_APPROVAL_RATE=0.9,
      SIM_LATENCY_MS=40). `ENABLED_METHOD_TYPES` parsed from comma string to list.
      Files: `libs/acip-common/src/acip_common/config.py`
      Verify: covered by item 8's pytest (defaults + env override round-trip).

- [ ] 5. Implement `acip_common.schemas` — Pydantic v2 domain models and event schemas.
      One coherent module (or `schemas/` package) containing: the common EVENT ENVELOPE
      (`docs/03` §1: event_id, event_type, event_version, transaction_id, trace_id,
      occurred_at, producer, payload); the SHARED TRANSACTION REPRESENTATION exactly per
      `docs/03` §8 (representation_version, transaction, built_at, features,
      graph_signals, method_history, candidate_routes with their nested shapes); the
      Verdict schema per `docs/02` §4 (decision_hint, score, confidence, rationale,
      evidence[], model_version, degraded); and all event payload models — `txn.created`,
      `txn.evaluate.requested` (carries representation + expected_agents + deadline_ms per
      `docs/06` §3), `agent.verdict.produced`, `decision.rendered` (`docs/02` §5),
      `txn.executed`/`txn.declined`/`txn.challenged`. Use enums for decision hints and
      method types; model_config forbids extra fields on inbound.
      Files: `libs/acip-common/src/acip_common/schemas.py` (or `schemas/` package with
      `envelope.py`, `representation.py`, `verdict.py`, `events.py`)
      Verify: covered by item 8's pytest (JSON round-trip for every event + representation).

- [ ] 6. Implement `acip_common.features` — the shared feature-transform functions.
      Pure functions that compute the 7 core features from `docs/05` §6.2 /`docs/03` §8
      (`amount_zscore`, `velocity_1h`, `method_age_days`, `geo_mismatch`,
      `shared_device_ring_size`, `customer_txn_count_30d`, `customer_chargeback_count`)
      plus a `FEATURE_COLUMNS` constant and a `build_feature_row(...)` that both the
      dataset generator (item 10) and live scoring (future) import — the single
      definition that prevents train/serve skew (`docs/05` §3, §6.2). No pandas/numpy
      dependency here (keep acip-common light); functions take plain scalars/dicts.
      Files: `libs/acip-common/src/acip_common/features.py`
      Verify: covered by item 8's pytest (deterministic transform outputs for known inputs).

- [ ] 7. Implement `acip_common.logging` + `acip_common.kafka` — observability and the
      Kafka client wrapper. `logging.py`: `configure_logging()` installing a JSON
      formatter, a `trace_id` contextvar, and `bind_trace_id()`/`get_trace_id()` helpers
      so every log line carries the trace (`docs/01` §6, `docs/07` §5). `kafka.py`:
      thin producer/consumer helpers over `confluent-kafka` targeting the Kafka API
      (Redpanda), with a module docstring justifying confluent-kafka over aiokafka;
      producer configured idempotent, keyed by `transaction_id`; consumer helper exposes
      manual commit so callers commit only after publishing (`docs/02` §6); envelope
      (de)serialization uses item 5's schemas. No live broker needed to import.
      Files: `libs/acip-common/src/acip_common/logging.py`,
      `libs/acip-common/src/acip_common/kafka.py`
      Verify: `uv run python -c "import acip_common.kafka, acip_common.logging"` imports
      clean; JSON log line asserted in item 8's pytest.

- [ ] 8. Add `acip-common` unit tests — schema round-trips, config, and feature transforms.
      Tests under `libs/acip-common/tests/`: `test_schemas.py` (serialize→deserialize
      every event + the shared representation, assert field integrity and enum
      validation), `test_config.py` (defaults match `docs/07`, env override works),
      `test_features.py` (each transform returns expected value for crafted inputs;
      `FEATURE_COLUMNS` ordering stable), `test_logging.py` (log record is valid JSON and
      includes bound trace_id).
      Files: `libs/acip-common/tests/{test_schemas,test_config,test_features,test_logging}.py`,
      `libs/acip-common/tests/__init__.py`
      Verify: `uv run pytest libs/acip-common` — all tests pass. Then
      `uv run ruff check libs/acip-common ml && uv run black --check libs/acip-common ml && uv run mypy libs/acip-common` — clean.

- [ ] 9. Create the `ml/` uv project manifest and `scripts/` resolution.
      `ml/pyproject.toml` declaring the ML runtime deps (numpy, pandas, pyarrow, faker,
      xgboost, lightgbm, scikit-learn pinned) + path dep on `acip-common`, and
      `scripts/pyproject.toml` (or fold scripts deps into root dev group) declaring
      neo4j + psycopg[binary] + path dep on `acip-common`. Decision: keep `ml/` as its
      own uv-managed project (heavy ML deps isolated from the light `acip-common`), and
      resolve `scripts/` deps via the root dev group so `make seed` runs under the root
      venv. Note this split in the file header comment.
      Files: `ml/pyproject.toml`, root `pyproject.toml` (add scripts deps to dev group)
      Verify: `cd ml && uv sync` resolves ML deps including the `acip-common` path dep.

- [ ] 10. Implement `ml/training/generate_dataset.py` — Layer 1 synthetic generator per
      `docs/05` §6.2. CLI (argparse) with defaults n_customers=10000, n_merchants=500,
      n_transactions=100000, fraud_rate=0.025, label_noise=0.03, seed=42. Generation
      order entities→transactions→labels: build customer/merchant/device/IP/method
      populations with the distributions in §6.2; inject fraud signatures (device-sharing
      rings, velocity bursts, geo mismatch, brand-new method on high value) and risk
      signatures (prior chargebacks, high amount_zscore); derive `is_fraud` + `bad_outcome`
      from planted signals plus `label_noise` flips. Feature columns come from
      `acip_common.features.build_feature_row` / `FEATURE_COLUMNS` (no skew). Faker for
      names/addresses/IPs. Output Parquet + small CSV sample under `ml/data/`; print
      class-balance and per-feature summary.
      Files: `ml/training/generate_dataset.py`, `ml/training/__init__.py`
      Verify: `cd ml && uv run python training/generate_dataset.py --n-customers 200 --n-merchants 20 --n-transactions 1000 --seed 42`
      writes `ml/data/*.parquet` + CSV sample and prints a class-balance report with
      roughly `fraud_rate` positives.

- [ ] 11. Implement `ml/training/train.py` — trains risk (XGBoost) + fraud (LightGBM) per
      `docs/05` §5. Load the Parquet from item 10, build features via the shared
      transforms, do a validation split (scikit-learn), train both models, compute AUC +
      PR-AUC on validation, serialize versioned artifacts (`<model>-<algo>-<date>`) under
      `ml/models/`, and write `model_card.json` INCLUDING the honesty caveat from
      `docs/05` §6.1 verbatim in spirit (synthetic data → illustrative metrics, not
      real-world accuracy). CLI accepts a `--data` path and `--models-dir`.
      Files: `ml/training/train.py`
      Verify: after item 10's small run, `cd ml && uv run python training/train.py --data ml/data/<generated>.parquet`
      writes two model artifacts + `ml/models/model_card.json` and prints AUC/PR-AUC for
      both models; `model_card.json` contains the synthetic-data caveat.

- [ ] 12. Implement `scripts/seed.py` — Layer 2 Neo4j + Postgres demo seed per `docs/05`
      §6.3. Idempotent (re-run resets to the same known state): build the five named
      scenarios (`clean_shopper`→APPROVE, `ring_member`→fraud DECLINE,
      `high_value_midrisk`→CHALLENGE, `sanctioned_geo`→policy DECLINE,
      `unhealthy_preferred_route`→alternate route) as Neo4j nodes/relationships per the
      `docs/03` §3 graph model, write `USED_METHOD_TYPE {successes,failures,last_used}`
      edges for method-success history, and candidate routes with varying health; create
      the Postgres read-model tables (`transactions`, `decisions`, `agent_verdicts`,
      `event_journal` per `docs/03` §4) and seed matching rows. Read connection config
      from `acip_common.config.Settings`; on connection failure exit non-zero with a
      clear message naming the unreachable store (guarded per prompt).
      Files: `scripts/seed.py`
      Verify: `uv run python scripts/seed.py` against a running stack (item 13) is
      idempotent across two runs; with stores DOWN it exits non-zero with a clear
      connection error naming Neo4j or Postgres (test the error path without a stack).

- [ ] 13. Create `deploy/docker-compose.yml` — INFRASTRUCTURE ONLY per `docs/07` §1.
      Services: `redpanda` (Kafka API, single broker, healthcheck), `kafka-init` (one-shot
      that creates topics `txn.lifecycle`, `txn.evaluate`, `agent.verdicts`,
      `decision.log` and their `.dlq` siblings from `docs/03` §2 using `rpk topic create`,
      depends_on redpanda healthy), `neo4j:5` (bolt + browser, healthcheck,
      `NEO4J_AUTH` from env), `postgres:16` (healthcheck, acip/acip/acip DSN),
      `redis:7` (healthcheck), `prometheus` (scrape config from `deploy/prometheus/`),
      `grafana` (provisioning from `deploy/grafana/provisioning/`), `jaeger` (all-in-one).
      Private `acip-net` network; host ports exposed only where `docs/07` warrants
      (Neo4j browser, Grafana, Jaeger UI, and broker/stores for local tooling). NO
      application-service containers this phase. Add `deploy/prometheus/prometheus.yml`
      and minimal `deploy/grafana/provisioning/` datasource config.
      Files: `deploy/docker-compose.yml`, `deploy/prometheus/prometheus.yml`,
      `deploy/grafana/provisioning/datasources/datasource.yml`
      Verify: `docker compose -f deploy/docker-compose.yml config` validates with no
      error and lists exactly the infra services (no app services).

- [ ] 14. Create the `Makefile` per `docs/07` §3. Working targets this phase:
      `build`/`up`/`down` (compose up/down for infra), `topics` (idempotent topic
      creation via the init path), `train` (runs generate_dataset then train under
      `ml/`), `seed` (runs `scripts/seed.py`), `lint` (ruff check), `format`
      (black + ruff format), `test` (pytest on acip-common). App-service targets
      (`demo`, `logs`, per-service build) are stubbed to echo
      "implemented in a later phase". Variables point at `deploy/docker-compose.yml`.
      Files: `Makefile`
      Verify: `make lint && make test` run green (reuse item 8); `make -n up` and
      `make -n train` print the expected commands; `make demo` prints the
      later-phase stub.

- [ ] 15. Final integration verification across the foundation.
      Run the full gate end to end to confirm the layers compose: `uv sync`, then
      `uv run ruff check libs/acip-common ml scripts && uv run black --check libs/acip-common ml scripts && uv run mypy libs/acip-common`,
      then `uv run pytest libs/acip-common`, then the small-override dataset+train run
      from items 10–11, then `docker compose -f deploy/docker-compose.yml config`.
      Files: none (verification only); fix any failures surfaced in the touched files.
      Verify: every command above exits 0; `ml/data/` and `ml/models/` contain the
      generated artifacts and are gitignored (`git status` shows them untracked/ignored).

## Notes & assumptions

- `docs` is silent on exact pinned versions; the versions above are current-stable and
  must survive `uv sync` — the implementer bumps any that fail resolution, keeping pins.
- `docs/07` §1 lists the infra set; `redpanda-console` is intentionally omitted to match
  that list. Add it later if the demo needs a topic UI.
- Grafana/Prometheus/Jaeger get minimal provisioning now (datasource + scrape stub);
  full dashboards are a later-phase concern tied to real service metrics.
- The checkout default mode (sync) is a service behavior; this phase only records it in
  `.env.example`/config, since no application service is built yet.
