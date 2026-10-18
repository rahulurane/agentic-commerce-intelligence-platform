# ACIP Phase 3 — six agents, graph-projector, and the five-scenario demo

Phase 3 lands the agentic core on top of the Phase-2 edge: six evaluating agents, a graph-projector, the three Phase-2 carryover fixes, and the full-stack wiring that makes `./start.sh` bring up a 14-service stack and run a five-scenario demo end to end. The six agents consume `txn.evaluate.requested`, read their slice of the shared representation, and publish `agent.verdict.produced` that the existing decision-engine aggregates into real APPROVE/DECLINE/CHALLENGE — closing the Phase-2 gap where the orchestrator fell back to `decide_partial` with no agents running. The change reuses `acip-common` contracts throughout (schema changes are additive), introduces one new workspace lib (`acip-agent-common`) as the uniform agent scaffolding, and adds no new host ports. Watch for: nothing blocking — the full static gate is green, every contract is imported not redefined, and the five scenarios resolve as documented on the mock LLM provider with no cloud credentials (confirmed both in the recorded live run and by re-running the static gate here).

**Verdict**: APPROVED

## High-level view

The static gate is green on this machine: `uv sync`, `ruff`, `black --check` (102 files), `mypy --strict` (97 files), `pytest` (127 passed), and `docker compose config` (22 services) all pass. These were re-run independently for this review, not taken on trust from the FEAT findings.

The three carryover fixes are present and correct. Read-model bootstrap (`acip_common.bootstrap.ensure_read_model_schema`) issues `CREATE TABLE IF NOT EXISTS` for the four tables with shapes identical to `scripts/seed.py` and is best-effort (returns False, never raises). The 404-not-500 fix catches `psycopg.errors.UndefinedTable` in the read path and returns None (→ 404) while still raising on real operational faults (fail-closed). Async idempotency now stores the 202 body under the key so a repeat async key replays the same transaction_id with a single `txn.created` emit.

The six agents share one scaffolding lib. `AgentRunner` publishes `agent.verdict.produced` to `agent.verdicts` keyed by `transaction_id`, then commits the consumer offset only after a successful publish (at-least-once; a crash between publish and commit replays rather than drops). Each agent injects only a pure `score_fn`, so behavior differs by injection not by forked code. The emitted verdicts drive the pre-existing `decision_engine.aggregate()` branches — policy DECLINE and fraud-over-threshold are hard vetoes, merchant `force_challenge` upgrades APPROVE→CHALLENGE, routing supplies the ranked route, personalization is advisory.

The graph-projector consumes the three source topics on one group, projects every event to both Postgres (`ON CONFLICT` upserts keyed by PK/`event_id`) and Neo4j (`MERGE` keyed by id), and commits after a successful project, so replays dedupe. It owns runtime read-model population via the same bootstrap helper on startup, and swallows store outages so the loop stays up.

Wiring adds the seven new services to compose following the Phase-2 pattern (repo-root build context, `env_file required:false`, inline threshold defaults, infra `depends_on`, on `acip-net`) with no published host ports — only checkout-api keeps 8080. The five-scenario `scripts/demo.py` POSTs one checkout per seeded scenario and asserts each decision, including that the reroute scenario lands on a route other than the degraded `processor_pref`, exiting non-zero on any mismatch. The recorded live run on Docker (mock LLM provider, no creds) matched all five.

Two train/serve fixes were needed so the seeded scenarios resolve as documented (a shared-device ring-size query that counted a solo customer as a ring, and a seed that never materialized the ring). Both align the live system with the already-documented expected decisions rather than changing product behavior; they are reasonable and well-scoped.

<details>
<summary>Issues (0)</summary>

No blocking or actionable concerns. All required Phase-3 elements are present, the full gate is green, and the five scenarios resolve to the documented outcomes.

</details>

<details>
<summary>Details</summary>

### Carryover fixes verified in code

`reads.PostgresReadModel._fetch` wraps the query in `try/except psycopg.errors.UndefinedTable -> return None`; a genuine connection/operational error still propagates, preserving the fail-closed posture on real faults while treating a never-seeded stack as a 404. Both GET endpoints route None → `HTTPException(404)`. `bootstrap.ensure_read_model_schema` lazy-imports psycopg, runs the four `CREATE TABLE IF NOT EXISTS` statements with columns matching `scripts/seed.py`, and returns False on any failure. The async branch of `checkout()` now calls `idempotency.put(key, StoredDecision(transaction_id, accepted))` with the 202 body; the top-of-handler replay check returns that body on a repeat key, so the async path replays the same transaction_id and emits `txn.created` exactly once — matching the sync contract.

### Verdict flow drives real decisions

`AgentRunner.run_once` builds `AgentVerdictProducedPayload{agent, produced_at, verdict}` and publishes an `AGENT_VERDICT_PRODUCED` envelope keyed by `transaction_id`; `consume_forever` commits only after `run_once` returns, and skips the commit on failure so the offset replays. `decision_engine.aggregator.aggregate()` (unchanged Phase-2 code) reads these: a `policy` DECLINE or `fraud.score >= fraud_block_threshold` is a hard veto; otherwise a weighted `w_risk*risk + w_fraud*fraud` composite is banded; the merchant `force_challenge` evidence signal upgrades APPROVE→CHALLENGE; routing supplies the ranked route and alternatives; personalization contributes only `recommended_method`. With the six agents now producing verdicts, the orchestrator no longer needs the `decide_partial` fallback for the demo path.

### Graph-projector idempotency

Postgres: `event_journal` insert is `ON CONFLICT (event_id) DO NOTHING`; `transactions`, `decisions`, and `agent_verdicts` use `ON CONFLICT (...) DO UPDATE` keyed by their primary keys. Neo4j: `MERGE` on `Customer`/`Transaction`/`Device`/`DecisionEvent`/`Processor` nodes and their edges, all keyed by id, so a replayed envelope produces no duplicate node or row. The consumer projects then commits, giving at-least-once delivery that the idempotent writes dedupe. Store outages are logged and swallowed so a Neo4j/Postgres hiccup degrades rather than crashes the loop.

### Compose and host-port posture

The rendered `docker compose config` has 22 services. Published host ports: checkout-api 8080 (the only app edge) plus the pre-existing infra UIs (redpanda 19092, neo4j 7474/7687, postgres 5432, redis 6379, prometheus 9090, grafana 3000, jaeger 16686/4317). All six agents and the graph-projector publish no host port. No cloud-credential env vars appear anywhere in the compose file; the recorded live run served every completion on the llm-gateway mock provider, and agent rationales take the templated/degraded path without blocking the decision.

### Contract reuse, docs, deps

The only `acip-common` schema change is two additive optional fields on `SharedRepresentation` (`home_geo`, `txn_geo`) so the policy agent can match a specific sanctioned geo; no service or `acip-agent-common` redefines `EventEnvelope`, `Verdict`, `AgentName`, or the payload types — all are imported. `docs/` is untouched in the diff. Every new `pyproject.toml` pins exact versions (langgraph==0.2.60, fastapi==0.115.6, uvicorn[standard]==0.34.0, httpx==0.28.1, neo4j==5.27.0, psycopg[binary]==3.2.3); no `>=`/`^`/`~` ranges.

### Static gate (re-run for this review)

`uv sync` ok (86 packages); `ruff check .` clean; `black --check .` clean (102 files); `mypy libs services` clean strict (97 files); `pytest libs/acip-common libs/acip-agent-common services` = 127 passed; `docker compose -f deploy/docker-compose.yml config` valid (22 services, no new host ports). The five-scenario demo was verified live on Docker in the recorded run (`.agents/tasks/phase3-verification.md`): clean_shopper→APPROVE, ring_member→DECLINE (fraud veto), high_value_midrisk→CHALLENGE (merchant step-up), sanctioned_geo→DECLINE (policy veto), unhealthy_preferred_route→APPROVE on processor_a (not the degraded processor_pref).

</details>

<details>
<summary>File map</summary>

- `libs/acip-common/src/acip_common/{bootstrap,config,schemas}.py` — read-model bootstrap, new policy/merchant config keys, additive `home_geo`/`txn_geo`.
- `libs/acip-agent-common/**` — new workspace lib: uniform LangGraph graph, `AgentRunner`, templated llm_rationale, health app.
- `services/{risk,fraud,routing,policy,merchant,checkout-personalization}-agent/**` — six agents (Dockerfile, pyproject, scorer, agent, main, tests).
- `services/graph-projector/**` — Kafka→Neo4j+Postgres projector with idempotent upserts.
- `services/checkout-api/src/checkout_api/{main,reads}.py` — async idempotency + 404-not-500 read fixes.
- `services/commerce-orchestrator/.../persistence.py`, `services/representation-service/.../{builder,stores}.py` — bootstrap call + ring train/serve fix + home_geo/txn_geo wiring.
- `deploy/docker-compose.yml`, `Makefile`, root `pyproject.toml`, `uv.lock`, `.env.example` — wiring; no new host ports.
- `scripts/{demo,seed}.py`, `start.sh`, `stop.sh`, `README.md` — five-scenario driver, ring seed, one-command bring-up.

Full diff: `git diff 92f90e1` on branch `feat/phase1-foundation`.

</details>
