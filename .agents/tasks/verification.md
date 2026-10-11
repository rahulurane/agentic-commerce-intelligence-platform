# ACIP Phase 1 — Verification Evidence

First iteration (no `review.json` present). All 15 plan items implemented and the
verification gate run against the real toolchain. Commands were executed from the repo
root unless noted. Generated ML artifacts and `.venv`s are gitignored and were NOT
committed.

Environment: macOS (arm64), `uv 0.5.4`, `docker 27.3.1` (CLI only — daemon not running,
see §8), Python 3.11.10. `libomp` (OpenMP runtime) was installed via Homebrew because
LightGBM's native lib requires it on macOS (see §5).

## 1. `uv sync` resolves and creates `.venv`
Command: `uv sync`
Result: exit 0. "Resolved 26 packages", `.venv/` created. `uv run ruff --version` →
`ruff 0.8.4`. `uv run python -c "import acip_common"` → `0.1.0`.
`cd ml && uv sync` → exit 0, "Resolved 25 packages", `ml/.venv/` created.

## 2. Lint / format / type gate
Commands:
- `uv run ruff check libs/acip-common ml scripts` → exit 0, "All checks passed!"
- `uv run black --check libs/acip-common ml scripts` → exit 0, 15 files unchanged
- `uv run mypy libs/acip-common` → exit 0, "Success: no issues found in 11 source files"

mypy scope is `libs/acip-common` per the plan. A `[[tool.mypy.overrides]]` entry marks
`confluent_kafka` as `ignore_missing_imports` (it ships no stubs / `py.typed`).

## 3. Unit tests
Command: `uv run pytest libs/acip-common -q`
Result: exit 0, **20 passed**. Covers: schema JSON round-trips for every event +
the shared representation + the envelope, strict-model rejection of unknown fields,
enum validation; config defaults (docs/07 §2) + env override round-trip including the
comma-separated `ENABLED_METHOD_TYPES`; feature transforms with known inputs + stable
`FEATURE_COLUMNS` ordering; JSON log line with bound `trace_id`.

## 4. Dataset generation (small override, plan item 10)
Command (from `ml/`):
`uv run python training/generate_dataset.py --n-customers 200 --n-merchants 20 --n-transactions 1000 --seed 42`
Result: exit 0. Wrote `ml/data/transactions.parquet` + `ml/data/transactions_sample.csv`.
Feature columns present and in canonical order: `amount_zscore`, `velocity_1h`,
`method_age_days`, `geo_mismatch`, `shared_device_ring_size`, `customer_txn_count_30d`,
`customer_chargeback_count`.
Class balance: `is_fraud` = 56/1000 (0.0560), `bad_outcome` = 166/1000 (0.1660) — both
non-degenerate (two classes present). The fraud positive rate sits above the 0.025
`fraud_rate` target because at only 1000 rows the quantile cutoff is clamped to the
signal floor (0.3); the generator is deterministic and reproduces identical output on
re-run with the same seed.

## 5. Model training (plan item 11)
Pre-step: `brew install libomp` (exit 0) — LightGBM's `lib_lightgbm.dylib` requires
`@rpath/libomp.dylib`, absent on this machine. This is a system runtime dependency, not
a code change. XGBoost trained without it.
Command (from `ml/`): `uv run python training/train.py --data data/transactions.parquet`
Result: exit 0. Output:
```
  risk [risk-xgb-2026.10.10] AUC=0.8385 PR-AUC=0.5265 -> risk-xgb-2026.10.10.json
 fraud [fraud-lgbm-2026.10.10] AUC=0.7989 PR-AUC=0.5801 -> fraud-lgbm-2026.10.10.txt
```
Artifacts written under `ml/models/`: `risk-xgb-<date>.json`, `fraud-lgbm-<date>.txt`,
`model_card.json`. AUC/PR-AUC are finite for both models. `model_card.json` contains the
synthetic-data honesty caveat (docs/05 §6.1): metrics demonstrate the pipeline works,
NOT real-world accuracy; models learned only the planted synthetic patterns.

## 6. Seed connection-failure path (plan item 12, no stack required)
Command: `NEO4J_URI="bolt://127.0.0.1:7687" uv run python scripts/seed.py`
Result: **exit 1** with a clear message naming the unreachable store:
`seed failed: cannot connect to Neo4j at bolt://127.0.0.1:7687: ... Connection refused`.
The script guards both Neo4j and Postgres connections and exits non-zero with the store
name. Idempotency against a live stack (MERGE / TRUNCATE+insert) is implemented but was
NOT run live because the Docker daemon is down (§8).

## 7. Compose config validation (plan item 13)
Command: `docker compose -f deploy/docker-compose.yml config`
Result: exit 0 (valid). `--services` lists exactly the infra set, no app services:
`grafana, jaeger, kafka-init, neo4j, postgres, prometheus, redis, redpanda`.

## 8. Compose live bring-up — NOT RUN (environment limitation)
`docker compose ... up` and the topic-creation / healthcheck confirmation could **not**
be executed: the Docker CLI is present (27.3.1) but the Docker Desktop **daemon is not
running** (`docker info` → "Cannot connect to the Docker daemon ..."). Starting Docker
Desktop is outside this step's control, so live healthchecks and `rpk topic create`
were not verified. The compose file validates statically (§7) and the `kafka-init`
service is wired to create the four lifecycle topics plus their `.dlq` siblings once a
daemon is available.

## 9. Makefile targets (plan item 14)
- `make lint` → exit 0 (ruff clean)
- `make test` → exit 0 (20 passed)
- `make -n up` → prints `docker compose -f deploy/docker-compose.yml up -d`
- `make -n train` → prints the generate_dataset then train commands
- `make demo` → prints `demo: implemented in a later phase`

## 10. Final integration gate + gitignore check (plan item 15)
Ran, in order: `uv sync` (0) → ruff (0) → black --check (0) → mypy (0) →
`pytest libs/acip-common` (0) → small dataset+train (0) → `docker compose config` (0).
`git status --short ml/` shows only source files untracked; `git check-ignore`
confirms `ml/data/transactions.parquet`, `ml/models/model_card.json`, and the model
artifacts are ignored. `ml/data/.gitkeep` and `ml/models/.gitkeep` remain NOT ignored
(tracked placeholders). `.venv` and `ml/.venv` are ignored.

## Summary
| Item | Status |
|------|--------|
| 1 scaffolding (14 services + gitkeeps) | ✅ verified |
| 2 uv workspace root | ✅ verified |
| 3 acip-common skeleton | ✅ verified |
| 4 config | ✅ verified (tests) |
| 5 schemas | ✅ verified (tests) |
| 6 features | ✅ verified (tests) |
| 7 logging + kafka | ✅ verified (import + tests) |
| 8 unit tests | ✅ 20 passed |
| 9 ml/ project + scripts resolution | ✅ verified (uv sync) |
| 10 generate_dataset.py | ✅ verified (small run) |
| 11 train.py | ✅ verified (small run; needed libomp) |
| 12 seed.py failure path | ✅ verified (exit 1, names Neo4j) |
| 13 docker-compose config | ✅ verified (config valid, infra-only) |
| 14 Makefile | ✅ verified |
| 15 full integration gate | ✅ verified; live Docker bring-up NOT run (daemon down) |

NOT verified (explicitly): live Docker Compose bring-up, healthcheck green status,
`rpk` topic creation, and live `seed.py` idempotency — all blocked by the Docker daemon
being down. Everything that does not require a running broker/stores was verified.
