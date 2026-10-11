# ACIP Phase 1 (Foundation Layer) — Semantic Review

Phase 1 lays the foundation every later ACIP phase builds on: a uv workspace, the `acip-common` shared library (config, schemas, features, logging, Kafka), the synthetic ML dataset+training layer, the demo seed, an infrastructure-only Docker Compose stack, and a Makefile. No application services are implemented — `services/*` is 14 empty dirs with `.gitkeep`. The implementation tracks `plan.md` items 1–15 closely and stays faithful to the referenced docs (`docs/00`–`docs/07`) and the LOCKED DECISIONS. The single most important design property — the no-train/serve-skew seam — is correctly realized: `ml/training/generate_dataset.py` imports `acip_common.features.build_feature_row` / `FEATURE_COLUMNS`, so train and serve share one feature definition.

Watch for: a cosmetic Kafka host-alias mismatch between the config default (`kafka:9092`) and the Redpanda container's advertised name (`redpanda:9092`) with no `kafka` network alias (confirmed, non-blocking — no service connects this phase). Live Docker bring-up, healthchecks, `rpk` topic creation, and live seed idempotency were NOT verified because the Docker daemon was down (confirmed from verification §8); the compose file validates statically and these are legitimately deferrable to the phase that first needs a running stack.

**Verdict**: APPROVED

## High-level view

The scope boundary is honored exactly. Fourteen service directories carry only `.gitkeep`, the compose stack contains infra services only (`redpanda, kafka-init, neo4j, postgres, redis, prometheus, grafana, jaeger`), and the Makefile stubs app-service targets (`demo`, `logs`) with later-phase echoes. Nothing application-level leaked into Phase 1.

The locked decisions are all present and correct: Python 3.11+, uv workspace with `acip-common` as a path/workspace member, Redpanda for the Kafka API, `confluent-kafka` as the client (justified in a module docstring), Pydantic v2 everywhere, pinned deps, Neo4j 5 / Postgres 16 / Redis 7, and secrets via env only. The decision thresholds (`approve_max=0.35`, `challenge_max=0.70`, `fraud_block=0.85`), equal `0.5/0.5` weights, and every `docs/07 §2` env var land in `config.py` and `.env.example` with the documented defaults.

The train/serve-skew seam is the correctness linchpin and it holds. `FEATURE_COLUMNS` and `build_feature_row` are defined once in `acip_common.features` (pure, numpy/pandas-free) and imported by the dataset generator; `train.py` reads the same `FEATURE_COLUMNS` to build its matrix. Feature names and ordering are single-sourced.

The synthetic-data honesty caveat is present and strong — `train.py` writes a verbatim `_SYNTHETIC_CAVEAT` into `model_card.json` stating the metrics prove the pipeline works, not real-world accuracy. This matters because the POC targets leadership.

The known gaps are environment-bound, not code gaps: live broker/store bring-up could not run because the Docker daemon was down. The static compose validation passed and the wiring (healthchecks, `kafka-init` topic creation, seed connection guards) is in place and reviewable.

<details>
<summary>Issues (2)</summary>

1. **Kafka host-alias mismatch (non-blocking)** — `config.py`/`.env.example` default `KAFKA_BOOTSTRAP=kafka:9092` (matching `docs/07 §2` verbatim), but the Redpanda container advertises `PLAINTEXT://redpanda:9092` with no `kafka` network alias. No service connects this phase, so it does not break anything now; the phase that wires the first consumer must either add a `kafka` alias to the redpanda service or change the default to `redpanda:9092`.
2. **Live stack not exercised (deferred, documented)** — compose bring-up, healthcheck-green, `rpk topic create`, and live `seed.py` idempotency were not run (Docker daemon down). Acceptable for Phase 1 since the compose config validates statically and the code paths are wired; must be verified in the phase that first stands up the stack.

</details>

<details>
<summary>Details</summary>

### Scope boundary held exactly

`git ls-files` confirms the 14 service dirs each hold only `.gitkeep` and no Python. `docker compose config --services` (verification §7) lists exactly the eight infra services with zero app containers. The Makefile's `demo`/`logs` targets echo "implemented in a later phase" rather than invoking anything. This is the hardest scope line to hold in a foundation phase and it is clean — no premature service, no half-built orchestrator.

### Config fidelity to the locked decisions

`config.py` is a single `pydantic-settings` `Settings` class carrying every `docs/07 §2` variable with the locked defaults: thresholds `0.85/0.35/0.70`, weights `0.5/0.5`, `DECISION_DEADLINE_MS=800`, `REPRESENTATION_VERSION=1`, LLM provider/model/fallback, and the sim knobs. `ENABLED_METHOD_TYPES` is parsed from the comma string via a `mode="before"` validator with `NoDecode` so pydantic-settings does not try to JSON-decode it — the correct and non-obvious fix for that class of bug. `.env.example` mirrors the defaults line for line. Secrets (`NEO4J_AUTH`, `POSTGRES_DSN`, `GOOGLE_APPLICATION_CREDENTIALS`) come from env with `.env` gitignored.

One cosmetic snag: the `KAFKA_BOOTSTRAP` default is `kafka:9092`, faithfully copied from `docs/07 §2`, but the Redpanda service advertises `redpanda:9092` and defines no `kafka` network alias. Because no service opens a producer/consumer this phase, nothing is broken — but a future consumer booting with the default would fail DNS resolution inside `acip-net`. Flagging now so it is fixed when the first service wires up, not debugged live.

### No train/serve skew — the seam is real

`features.py` defines `FEATURE_COLUMNS` (7 canonical columns in fixed order) and `build_feature_row`, both pure and dependency-light. `generate_dataset.py` builds every training row through `build_feature_row` and frames the matrix with `columns=list(FEATURE_COLUMNS)`; `train.py` selects `df[list(FEATURE_COLUMNS)]`. The feature contract is single-sourced, so an online scorer importing the same functions cannot drift from training. The 7 columns match `docs/05 §6.2` / `docs/03 §8` exactly.

### Schemas match the data contracts

`schemas.py` implements the envelope (`docs/03 §1`), the shared representation (`docs/03 §8`, including nested `TransactionCore`/`MethodHistoryEntry`/`CandidateRoute`), the `Verdict` (`docs/02 §4`), and all event payloads (`docs/03 §2`, `docs/06 §3`) with enums for decision hints / method types / agent names / event types. Inbound models extend a `_Strict` base (`extra="forbid"`, `validate_assignment=True`) so malformed events fail fast. The event catalog enum and the compose topic names agree: `txn.lifecycle`, `txn.evaluate`, `agent.verdicts`, `decision.log` plus `.dlq` siblings. `test_schemas.py` round-trips every payload and asserts strict rejection + enum validation.

### Kafka wrapper reflects the delivery semantics the docs require

`kafka.py` opens with the required justification for `confluent-kafka` over `aiokafka`. The producer config is idempotent (`enable.idempotence`, `acks=all`, bounded in-flight, retries) and keys by `transaction_id` for per-transaction ordering; the consumer disables auto-commit and exposes a manual `commit()` so callers commit only after publishing (`docs/02 §6`). Imports are lazy, so the module imports without a broker — which is what lets the tests and the review run offline.

### Seed scenarios and store guards

`seed.py` builds the five named scenarios (`clean_shopper`→APPROVE, `ring_member`→DECLINE, `high_value_midrisk`→CHALLENGE, `sanctioned_geo`→DECLINE, `unhealthy_preferred_route`→APPROVE-on-alternate) and writes `USED_METHOD_TYPE {successes, failures, last_used}` edges and candidate routes with varying health, matching `docs/03 §3` and `docs/05 §6.3`. Idempotency is implemented via `MATCH (n) DETACH DELETE n` + MERGE on Neo4j and `TRUNCATE ... INSERT` on the four Postgres read-model tables (`transactions`, `decisions`, `agent_verdicts`, `event_journal` per `docs/03 §4`). Both connections are guarded and raise `SeedError` naming the unreachable store, with `main()` returning exit 1 — verification §6 confirms the Neo4j failure path exits non-zero with the store named.

### Honesty caveat and gitignore hygiene

`train.py` writes `model_card.json` with a verbatim `_SYNTHETIC_CAVEAT` stating the metrics show the pipeline works and are not real-world accuracy — exactly the `docs/05 §6.1` stance, important for a leadership-facing POC. Spot-checked `git check-ignore`: `.env`, `ml/data/*.parquet`, and `ml/models/model_card.json` are ignored while `ml/data/.gitkeep` and `ml/models/.gitkeep` remain tracked. Model artifacts follow the `<model>-<algo>-<date>` naming from `docs/05 §4`.

### Verification evidence vs. the diff

The coder's `verification.md` records `uv sync` (both root and `ml/`), the lint/format/type gate (ruff/black clean, mypy clean on `acip-common` with a documented `confluent_kafka` override), 20 passing unit tests, a small dataset+train run producing finite AUC/PR-AUC for both models, the seed failure path, and static compose validation. The one explicit gap — live Docker bring-up — is honestly scoped to the daemon being down and is deferrable. Spot-checks performed here (services count = 14, gitignore behavior, config/feature/schema source) corroborate the evidence; the suite was not re-run per the review constraints.

</details>

<details>
<summary>File map</summary>

- `pyproject.toml`, `.python-version` — uv workspace root, dev tooling pinned, scripts deps in dev group, ruff/black/mypy config.
- `.gitignore`, `.env.example` — artifact/secret ignores; every `docs/07 §2` env var with locked defaults.
- `libs/acip-common/` — shared library: `config.py`, `schemas.py`, `features.py`, `logging.py`, `kafka.py`, `py.typed`, and 4 test modules.
- `ml/pyproject.toml`, `ml/training/{generate_dataset,train}.py` — synthetic dataset generator + risk/fraud trainer with model card.
- `scripts/seed.py` — idempotent Neo4j + Postgres demo seed with guarded connections.
- `deploy/docker-compose.yml`, `deploy/prometheus/prometheus.yml`, `deploy/grafana/provisioning/datasources/datasource.yml` — infra-only stack.
- `Makefile` — foundation targets working; app-service targets stubbed.
- `services/*/.gitkeep` — 14 empty service placeholders.

Full diff: `git diff 602911b HEAD`.

</details>
