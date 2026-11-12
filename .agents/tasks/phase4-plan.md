# ACIP Phase 4 — Implementation Plan (REACT Demo UI + Local Run Mode)

Branch: stay on `feat/phase1-foundation` (HEAD `8f74aa0`). Do NOT branch/reset/rebase/amend/force-push.
Both deliverables are purely ADDITIVE. The all-Docker path (`./start.sh`, `make up`, every existing
compose service definition, `.env.example`) must behave EXACTLY as today — the ONLY backend code change
permitted is an additive CORS middleware on checkout-api.

> This file OVERWRITES a prior Phase 4 plan that proposed a server-rendered FastAPI + Jinja2 + htmx
> `services/demo-ui`. That approach was WRONG and has been reverted. The UI this time is a **React SPA**
> (Vite + TypeScript + React 18) living in a self-contained top-level `ui/` directory — a Node project,
> **NOT** a uv workspace member.

---

## Exploration findings that shape this plan (grounded in the repo)

1. **checkout-api is the only public service.** `deploy/docker-compose.yml` publishes only
   `checkout-api` on host `8080:8000`. Its FastAPI app is `services/checkout-api/src/checkout_api/main.py`
   (`app = FastAPI(...)`). Endpoints: `POST /v1/checkout` (sync default), `GET /v1/transactions/{id}`,
   `GET /v1/transactions/{id}/explain`, `GET /healthz`, `GET /readyz`.
2. **Per-agent verdicts are NOT in the POST response.** `_public_decision()` always returns
   `"verdicts": {}`. The six agent verdicts are persisted by graph-projector and read via
   `GET /v1/transactions/{id}` → `reads._verdicts_list` → list of `{agent, score, hint}`. The React UI
   MUST POST `/v1/checkout`, take `transaction_id` from the response, then poll `GET /v1/transactions/{id}`
   a few times to render the six agent cards, tolerating an empty/partial list (agents may not have
   committed yet; a never-seeded/unknown id returns 404).
3. **POST /v1/checkout response shape** (from `_public_decision`): `transaction_id, decision, route,
   composite_score, explanation, recommended_method, partial, degraded_agents, route_alternatives,
   verdicts (always {}), trace_id`.
4. **GET /v1/transactions/{id} shape** (from `reads._transaction_view`): `transaction_id, customer_id,
   amount, status, decision, composite_score, strategy, verdicts: [{agent, score, hint}], created_at`.
5. **GET /v1/transactions/{id}/explain shape** (from `reads._explain_view`): `transaction_id,
   inputs:{customer_id, amount}, verdicts:[{agent,score,hint}], strategy,
   final_decision:{decision, composite_score, status}`.
6. **CORS is required.** The browser calls checkout-api cross-origin (UI on :8090 Docker or :5173 local,
   API on :8080). checkout-api has no CORS middleware today. Add `CORSMiddleware` additively, configurable
   via `CORS_ALLOW_ORIGINS` (default `"*"` for the demo). This is the ONLY backend code change.
7. **Redpanda already advertises a host listener.** The redpanda command advertises
   `OUTSIDE://localhost:19092` and publishes `19092:19092`. **No compose edit** for local mode Kafka.
8. **Port binding is a uvicorn CLI arg, not Settings.** Every service Dockerfile CMD is
   `uvicorn <pkg>.main:app --host 0.0.0.0 --port 8000`. Local mode passes a distinct `--port <N>` on the
   host uvicorn command line — **no Settings/Dockerfile/compose change** for port binding. Docker stays
   on :8000 untouched.
9. **All 14 app services launch via `uvicorn <module>.main:app`.** The six agents + graph-projector expose
   a FastAPI app whose lifespan starts the Kafka consumer thread, so the host-launch command is uniform.
   Module names (src dir → module): checkout-api→`checkout_api`, commerce-orchestrator→`commerce_orchestrator`,
   representation-service→`representation_service`, ml-scoring-service→`ml_scoring_service`,
   llm-gateway→`llm_gateway`, decision-engine→`decision_engine`, payment-processor-sim→`payment_processor_sim`,
   risk-agent→`risk_agent`, fraud-agent→`fraud_agent`, routing-agent→`routing_agent`,
   policy-agent→`policy_agent`, merchant-agent→`merchant_agent`,
   checkout-personalization-agent→`checkout_personalization_agent`, graph-projector→`graph_projector`.
10. **ENVIRONMENT CONSTRAINT: Node/npm are NOT installed on this host** (`node`/`npm` → not found);
    Docker IS present. Consequences:
    - The React **Docker image build is self-contained** (stage 1 `node:20-alpine`), so Docker-mode works
      with no host Node.
    - Host-side frontend steps — `npm ci`, `npm run build/lint`, `vitest run`, and the local-mode Vite dev
      server — REQUIRE Node 20 on the host. The implementer MUST install Node 20 (nvm or official pkg)
      before running those steps, and `start-local.sh` must detect a missing `node`/`npm` and fail with a
      clear install message. If Node cannot be installed in the execution environment, the frontend gate is
      run **inside the Docker build** (`docker compose build demo-ui` exercises `npm ci && npm run build`)
      and the Vite-dev-server local step is documented-but-skipped, stated explicitly in the report.
11. **Docker-mode UI config approach (DECISION): build-time `VITE_CHECKOUT_API_URL`.** The browser always
    reaches checkout-api on the host's published `http://localhost:8080`, so baking the URL at image build
    time (Docker `ARG VITE_CHECKOUT_API_URL` → passed to `vite build`) is the simplest robust approach and
    avoids a runtime `/config.js` entrypoint. Default `http://localhost:8080`. Documented in `ui/README.md`.
12. **Styling (DECISION): hand-rolled CSS**, not Tailwind — avoids a heavyweight build/config for a small
    demo SPA while still looking presentable.
13. **`ui/` is NOT a uv workspace member.** Root `pyproject.toml` `members = ["libs/*","services/*"]` does
    not include `ui/`, so a top-level `ui/` directory is invisible to uv. Do NOT add it to
    `[tool.uv.sources]` or `[dependency-groups]`. Keep `ui/` fully self-contained (own package.json +
    package-lock.json).

## Pinned dependency versions (frontend `ui/package.json`)

- Runtime: `react@18.3.1`, `react-dom@18.3.1`.
- Build/dev: `vite@5.4.10`, `@vitejs/plugin-react@4.3.3`, `typescript@5.6.3`.
- Test: `vitest@2.1.5`, `@testing-library/react@16.0.1`, `@testing-library/jest-dom@6.6.3`,
  `@testing-library/user-event@14.5.2`, `jsdom@25.0.1`.
- Lint/format: `eslint@9.14.0`, `@typescript-eslint/parser@8.14.0`,
  `@typescript-eslint/eslint-plugin@8.14.0`, `eslint-plugin-react-hooks@5.0.0`,
  `eslint-plugin-react-refresh@0.4.14`, `prettier@3.3.3`.
- Types: `@types/react@18.3.12`, `@types/react-dom@18.3.1`, `@types/node@20.17.6`.

> If a pinned version is unavailable at implementation time, pick the nearest stable patch of the SAME
> minor and record the substitution in the FEAT `findings`. `package-lock.json` MUST be committed
> (generated by `npm install` once, then `npm ci` thereafter).

## Host port map (local mode; Docker is unaffected — everything stays :8000 in containers)

| Service | Local host port | Docker (unchanged) |
|---|---|---|
| checkout-api | 8080 | 8080:8000 (published) |
| commerce-orchestrator | 8081 | internal :8000 |
| representation-service | 8082 | internal :8000 |
| ml-scoring-service | 8083 | internal :8000 |
| llm-gateway | 8084 | internal :8000 |
| decision-engine | 8085 | internal :8000 |
| payment-processor-sim | 8086 | internal :8000 |
| risk-agent | 8091 | internal :8000 |
| fraud-agent | 8092 | internal :8000 |
| routing-agent | 8093 | internal :8000 |
| policy-agent | 8094 | internal :8000 |
| merchant-agent | 8095 | internal :8000 |
| checkout-personalization-agent | 8096 | internal :8000 |
| graph-projector | 8097 | internal :8000 |
| React UI — Vite dev server (local mode) | 5173 | n/a |
| demo-ui (Docker static nginx) | n/a | 8090:80 (NEW published) |

Infra stays in Docker (localhost via published ports): postgres 5432, neo4j 7687/7474, redis 6379,
redpanda 19092, prometheus 9090, grafana 3000, jaeger 16686.

## Scenario request bodies (mirror `scripts/demo.py` + `scripts/seed.py`, canonical)

Each POST body: `merchant_id="mrc_demo"`, `currency="INR"`, `context.device_fingerprint = <device_id>`
(so the fraud ring resolves), `context.ip="203.0.113.9"`, `context.user_agent="acip-demo/1.0"`,
`idempotency_key = "idem_demo_<name>"` (the UI may append a nonce to allow re-runs), token `tok_<name>`.

| Scenario (button) | customer_id | amount | payment_method.type | device_fingerprint | expected |
|---|---|---|---|---|---|
| clean_shopper | cus_clean | 120.0 | upi | dev_clean | APPROVE |
| ring_member | cus_ring | 90.0 | card | dev_shared | DECLINE |
| high_value_midrisk | cus_midrisk | 4800.0 | card | dev_midrisk | CHALLENGE |
| sanctioned_geo | cus_sanctioned | 200.0 | wallet | dev_sanctioned | DECLINE |
| unhealthy_preferred_route | cus_reroute | 260.0 | card | dev_reroute | APPROVE (alternate route) |

---

## Ordered plan

### A. Backend — additive CORS (the only backend code change)

- [ ] 1. Add configurable CORS middleware to checkout-api.
      Add `CORSMiddleware` to `app` in `services/checkout-api/src/checkout_api/main.py`, reading
      allowed origins from env `CORS_ALLOW_ORIGINS` (comma-separated; default `"*"`). Keep it minimal and
      additive — it must not change any decision behavior. Add a small test in
      `services/checkout-api/tests/test_checkout.py` (or a new `test_cors.py`) asserting an
      `access-control-allow-origin` header is present on a response (e.g. a request with an `Origin` header,
      or an OPTIONS preflight to `/v1/checkout`).
      Files: `services/checkout-api/src/checkout_api/main.py`,
      `services/checkout-api/tests/test_checkout.py` (or new `tests/test_cors.py`)
      Verify: `uv run pytest services/checkout-api` — all prior tests + the new CORS test pass.

### B. React UI (`ui/` — self-contained Node project, NOT a uv workspace member)

- [ ] 2. Scaffold the Vite + TS + React 18 project skeleton with pinned deps and tooling config.
      Create `ui/package.json` (pinned deps per the list above; scripts: `dev` = `vite`,
      `build` = `tsc -b && vite build`, `preview` = `vite preview`, `lint` = `eslint .`,
      `test` = `vitest run`), `ui/package-lock.json` (committed, from `npm install`), `ui/tsconfig.json`,
      `ui/tsconfig.node.json`, `ui/vite.config.ts` (React plugin; dev server `port: 5173`; Vitest config
      with `environment: "jsdom"`, `setupFiles` for jest-dom), `ui/.eslintrc.cjs` (or `eslint.config.js`),
      `ui/.prettierrc`, `ui/index.html`, `ui/.gitignore` (node_modules, dist), `ui/vitest.setup.ts`,
      `ui/README.md` (how to run dev/build/test; the build-time `VITE_CHECKOUT_API_URL` decision).
      Files: `ui/package.json`, `ui/package-lock.json`, `ui/tsconfig.json`, `ui/tsconfig.node.json`,
      `ui/vite.config.ts`, `ui/.eslintrc.cjs`, `ui/.prettierrc`, `ui/index.html`, `ui/.gitignore`,
      `ui/vitest.setup.ts`, `ui/README.md`
      Verify: `cd ui && npm ci && npm run build` produces `ui/dist/index.html`; `npm run lint` passes.
      (Requires Node 20 on host; otherwise exercised by the Docker build in step 7.)

- [ ] 3. Implement the API client + TypeScript domain types as a thin layer over checkout-api.
      Create `ui/src/api/types.ts` (TS interfaces mirroring the three response shapes in findings 3–5:
      `CheckoutResponse`, `TransactionView`, `ExplainView`, `AgentVerdict`) and `ui/src/api/client.ts`
      (`postCheckout(body)`, `getTransaction(id)`, `getExplain(id)`, plus `pollTransaction(id, attempts,
      delayMs)` that refetches until the verdicts list is non-empty or attempts exhausted — tolerating 404
      during the window). Base URL from `import.meta.env.VITE_CHECKOUT_API_URL` with default
      `http://localhost:8080`. NO decision logic here — HTTP only.
      Files: `ui/src/api/types.ts`, `ui/src/api/client.ts`
      Verify: covered by `npm run build` (typecheck) and the client/unit tests in step 6.

- [ ] 4. Implement the scenario definitions + the decision→color mapping helper.
      Create `ui/src/scenarios.ts` (the five scenario POST bodies EXACTLY mirroring the table above /
      `scripts/demo.py`, each with a human label and expected decision) and
      `ui/src/decision.ts` (`decisionColor(decision)` → `"approve" | "challenge" | "decline"` CSS class /
      banner color: APPROVE→green, CHALLENGE→amber, DECLINE→red; handle null/unknown gracefully).
      Files: `ui/src/scenarios.ts`, `ui/src/decision.ts`
      Verify: covered by step 6 tests (scenario-button payloads; banner mapping).

- [ ] 5. Build the React components, app shell, and styling.
      Create `ui/src/main.tsx` (React root), `ui/src/App.tsx` (state: current decision, polled transaction,
      recent-transactions session list, loading/error flags; orchestrates POST→poll), and components under
      `ui/src/components/`: `ScenarioButtons.tsx` (five buttons), `CheckoutForm.tsx` (free-form: merchant,
      customer, amount, currency, payment method type, device fingerprint), `DecisionBanner.tsx` (prominent
      colored banner with decision, composite_score, route + alternatives, recommended_method, explanation),
      `AgentCards.tsx` (six verdict cards from the polled transaction: agent, score, hint; tolerate
      empty/partial with a "waiting for agents…" state), `RecentTransactions.tsx` (session list with
      click-through), `ExplainView.tsx` (renders the `/explain` trace), plus `ui/src/styles.css`
      (hand-rolled, presentable). Include clear loading + error states (checkout-api unreachable → explicit
      message).
      Files: `ui/src/main.tsx`, `ui/src/App.tsx`, `ui/src/components/*.tsx`, `ui/src/styles.css`
      Verify: `cd ui && npm run build` succeeds; `npm run lint` passes.

- [ ] 6. Add Vitest + React Testing Library tests (HTTP mocked, pinned deps).
      Create tests under `ui/src/` (e.g. `ui/src/__tests__/`): banner color/decision mapping for APPROVE,
      DECLINE, CHALLENGE; AgentCards rendering for a POPULATED verdicts list AND an EMPTY list (no crash,
      shows waiting state); scenario-button payloads match the canonical bodies; client error state when the
      fetch rejects. Mock `fetch`/the client (no live checkout-api).
      Files: `ui/src/__tests__/*.test.tsx`, `ui/src/__tests__/*.test.ts`
      Verify: `cd ui && npm run test` (`vitest run`) — all tests pass.

### C. UI Dockerization + compose wiring (Docker mode)

- [ ] 7. Add the multi-stage UI Dockerfile + nginx SPA config.
      Create `ui/Dockerfile`: stage 1 `node:20-alpine` runs `npm ci && npm run build` (accepting
      `ARG VITE_CHECKOUT_API_URL` with default `http://localhost:8080`, exported to the build env); stage 2
      `nginx:alpine` copies `dist/` to the web root and uses a custom `ui/nginx.conf` with SPA history
      fallback (`try_files $uri /index.html`), listening on container port 80. Create `ui/nginx.conf`.
      Add `ui/.dockerignore` (node_modules, dist).
      Files: `ui/Dockerfile`, `ui/nginx.conf`, `ui/.dockerignore`
      Verify: `docker build -f ui/Dockerfile --build-arg VITE_CHECKOUT_API_URL=http://localhost:8080 -t acip-demo-ui-test .`
      (context = repo root) succeeds and produces an image. (This also exercises `npm ci && npm run build`
      without host Node.)

- [ ] 8. Wire `demo-ui` into `deploy/docker-compose.yml` (ADDITIVE — do not touch other services).
      Add service `demo-ui`: `build: {context: .., dockerfile: ui/Dockerfile, args: {VITE_CHECKOUT_API_URL:
      "http://localhost:8080"}}`, `container_name: acip-demo-ui`, `depends_on: {checkout-api:
      {condition: service_started}}`, `networks: [acip-net]`, `ports: ["8090:80"]`. Do not modify any
      existing service block.
      Files: `deploy/docker-compose.yml`
      Verify: `docker compose -f deploy/docker-compose.yml config` is valid and lists `demo-ui` with
      `8090:80`; a git diff of the compose file shows ONLY the added block (existing services byte-identical).

- [ ] 9. Surface the Demo UI in `start.sh` summary + docs (Docker mode).
      Add the Demo UI URL `http://localhost:8090` to the `start.sh` printed summary (as the primary thing to
      show a leader). Add a short "Demo UI (React)" section to `docs/DEMO-WALKTHROUGH.md` and the UI URL to
      the README quickstart. Do NOT modify `docs/01–07`. `start.sh` must remain byte-for-byte behaviorally
      unchanged otherwise (the summary heredoc is the only edit).
      Files: `start.sh`, `docs/DEMO-WALKTHROUGH.md`, `README.md`
      Verify: `grep 8090 start.sh docs/DEMO-WALKTHROUGH.md README.md` shows the references; `bash -n start.sh`
      parses.

### D. Local run mode (host processes; Docker behavior identical)

- [ ] 10. Create `.env.local.example` (committed; localhost overrides for host execution).
      Header comment: infra stays in Docker (`make up-infra`); the 14 app services run as host processes;
      the React UI runs via `npm run dev` on 5173. Set `KAFKA_BOOTSTRAP=localhost:19092`,
      `NEO4J_URI=bolt://localhost:7687`, `POSTGRES_DSN=postgresql://acip:acip@localhost:5432/acip`,
      `REDIS_URL=redis://localhost:6379/0`, and each `*_URL` → `http://localhost:<port>` per the port map
      (REPRESENTATION 8082, ML_SCORING 8083, LLM_GATEWAY 8084, DECISION_ENGINE 8085, PAYMENT_PROCESSOR 8086,
      ORCHESTRATOR 8081). Keep the non-URL config (thresholds, LLM mock, etc.) same as `.env.example`.
      Files: `.env.local.example`
      Verify: `grep -E 'localhost:(19092|8081|8082|8083|8084|8085|8086)' .env.local.example` confirms the
      overrides.

- [ ] 11. Create `start-local.sh` (executable, `set -euo pipefail`).
      Steps: header note; prereq + Docker-daemon checks (reuse `start.sh` style) PLUS a `node`/`npm` check
      that fails with a clear "install Node 20" message; `make up-infra`; wait for
      redpanda/neo4j/postgres/redis container health (reuse the `start.sh` health-wait helper); train models
      if `ml/models/model_card.json` missing; `cp .env.local.example .env.local` if absent; schema bootstrap
      + `scripts/seed.py` against host DSNs (export `POSTGRES_DSN`/`NEO4J_URI`/`REDIS_URL` from `.env.local`);
      launch all 14 app services as background processes using a service→(module, port) table —
      `uv run uvicorn <module>.main:app --host 127.0.0.1 --port <N>` with env loaded from `.env.local`,
      stdout/stderr → `logs/<svc>.log`, PID → `run/<svc>.pid`; wait for checkout-api (`http://localhost:8080/healthz`);
      start the React Vite dev server (`cd ui && (npm ci if node_modules missing) && VITE_CHECKOUT_API_URL=http://localhost:8080 npm run dev -- --port 5173`)
      as a tracked background process (log `logs/ui.log`, PID `run/ui.pid`);
      run `CHECKOUT_URL=http://localhost:8080 uv run python scripts/demo.py`;
      print a URL summary with the UI at `http://localhost:5173` first, checkout-api at `:8080`,
      how to tail logs (`tail -f logs/*.log`), and how to stop (`./stop-local.sh`).
      Files: `start-local.sh`
      Verify: `bash -n start-local.sh`; `[ -x start-local.sh ]`; the service→port table matches the port map.

- [ ] 12. Create `stop-local.sh` (executable, `set -euo pipefail`).
      Kill tracked host PIDs from `run/*.pid` (SIGTERM, verify, remove stale pid files) INCLUDING the Vite
      dev server (`run/ui.pid`). Flags: default LEAVES infra up; `--all` runs `docker compose ... stop` of
      infra; `-v` runs `down -v` (wipe volumes); `-h` prints usage. Print exactly what it did; running with
      no pid files is a clean no-op.
      Files: `stop-local.sh`
      Verify: `bash -n stop-local.sh`; `[ -x stop-local.sh ]`; no-pid-files run is a clean no-op.

- [ ] 13. Add Makefile `up-local` / `down-local` targets and update `make help`.
      `up-local:` runs `./start-local.sh`; `down-local:` runs `./stop-local.sh` (document pass-through args).
      Add `## ` help strings and both names to `.PHONY`.
      Files: `Makefile`
      Verify: `make help` lists up-local/down-local; `make -n up-local` shows the script invocation.

- [ ] 14. Gitignore the local run + frontend artifacts.
      Add to `.gitignore`: `logs/`, `run/`, `.env.local`, `ui/node_modules/`, `ui/dist/`.
      Files: `.gitignore`
      Verify: after a local run, `git status --porcelain` shows none of `logs/`, `run/`, `.env.local`,
      `ui/node_modules/`, `ui/dist/` as untracked.

- [ ] 15. Document LOCAL run mode + the React UI in README + DEMO-WALKTHROUGH (do NOT modify docs/01–07).
      Add a "Run locally (host processes)" section (prereqs incl. Node 20, `make up-local`/`make down-local`,
      the note that infra stays in Docker and Docker-mode `./start.sh` is unchanged, the host port map, UI at
      :5173 local vs :8090 Docker, how to view logs/stop) and a "Demo UI (React)" subsection.
      Files: `README.md`, `docs/DEMO-WALKTHROUGH.md`
      Verify: `grep -i "up-local" README.md docs/DEMO-WALKTHROUGH.md` shows the new section.

---

## Verification — the acceptance gate (run at the end)

Backend static gate (from repo root):
- `uv sync`
- `uv run ruff check .`
- `uv run black --check .`
- `uv run mypy libs services`
- `uv run pytest libs/acip-common libs/acip-agent-common services` — expect prior 127 + the new CORS test,
  all pass. (The React `ui/` is excluded from the Python gate — it is not a workspace member.)

Frontend gate (`ui/`, requires Node 20 on host; if Node cannot be installed, these are exercised by the
Docker build in the compose step and that substitution is stated in the report):
- `cd ui && npm ci`
- `npm run build` (produces `ui/dist`)
- `npm run lint`
- `npm run test` (`vitest run`) — all tests pass.

Compose:
- `docker compose -f deploy/docker-compose.yml config` — valid; now lists `demo-ui` at `8090:80`; all other
  services byte-identical to before (git diff of the compose file shows only the added block).

DOCKER mode (unchanged backend behavior; UI additive):
- `./start.sh` brings up the full stack, seeds, and the five-scenario demo passes (clean_shopper→APPROVE,
  ring_member→DECLINE, high_value_midrisk→CHALLENGE, sanctioned_geo→DECLINE,
  unhealthy_preferred_route→APPROVE on an alternate route).
- Demo UI reachable at `http://localhost:8090`; a scenario run shows the colored banner + six agent cards.
- `./stop.sh` (and `-v`) behave as before.

LOCAL mode (new, additive):
- `make up-local` (or `./start-local.sh`): infra in Docker, 14 app services as host processes, React UI via
  the Vite dev server; `scripts/demo.py` passes against `http://localhost:8080`; UI reachable at
  `http://localhost:5173`.
- `./stop-local.sh` kills host processes (incl. the Vite dev server) and leaves infra up by default;
  `--all`/`-v` tear down infra/volumes.
- Docker mode and local mode do not clash on ports (map above); `.env` (Docker) and `.env.local` (local)
  are separate files.

If Docker is unavailable in the execution environment, run the full backend static gate + the frontend gate
(via host Node or the Docker build), state clearly that the live Docker/local smoke was not run, and leave
the scripts verified by `bash -n` and the service→port table review.

## Git hygiene
Stage only source files. NEVER commit `.env`, `.env.local`, `logs/`, `run/`, `ui/node_modules/`,
`ui/dist/`, `ml/data`, `ml/models` artifacts, or `.agents/tasks` bookkeeping. Commit with
`git commit -F <msgfile>` or a single short `-m` one-liner — never a multi-line inline message. Stay on
`feat/phase1-foundation`; never push.
