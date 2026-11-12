# ACIP Demo UI Redesign: Design + Implementation Plan (v2, branding-aware)

Supersedes the earlier dark-default plan. Branch `feat/phase1-foundation`, work in the repo root (no separate worktree). Scope: `ui/` plus one small additive backend change (Decision D1).

## 0. What the API actually returns (read from code)

| Endpoint | Fields (verified in `services/checkout-api/src/checkout_api/main.py::_public_decision`, `reads.py`) |
|---|---|
| `POST /v1/checkout` (synchronous) | `transaction_id, decision, route, composite_score, explanation, recommended_method, partial, degraded_agents[], route_alternatives[], verdicts:{} (always empty), trace_id` |
| `GET /v1/transactions/{id}` | `transaction_id, customer_id, amount, status, decision, composite_score, strategy, verdicts[{agent,score,hint}], created_at` |
| `GET /v1/transactions/{id}/explain` | `inputs{customer_id,amount}, verdicts[{agent,score,hint}], strategy, final_decision{decision,composite_score,status}` |
| `GET /healthz` | `{status:"ok"}`; CORS is `*` by default so the browser can call it |

Facts that shape the design:

- **Rationale/evidence is NOT persisted.** `AgentVerdictProducedPayload.verdict` carries `rationale, evidence[{signal,value,weight}], confidence, model_version, degraded`, but `graph-projector/postgres_projector.py::_apply_verdict` writes only `score, decision_hint` into `agent_verdicts`. So it cannot be shown today. See D1.
- Agent keys are `risk, fraud, routing, policy, merchant, checkout_personalization` (underscore).
- Vetoes return a **sentinel** `composite_score` (1.0 for a fraud veto, 0.0 for a policy veto; `aggregator.py`). The gauge must not present it as a real composite. Veto explanations start with `Hard veto: policy denial.` or `Hard veto: fraud score 0.97 >= block threshold 0.85.`
- Merchant step-up explanation ends with `Merchant constraint forced step-up.`; missing-verdict fallback reads `Missing risk/fraud verdict; applied configured missing-verdict policy -> X.`; normal path reads `composite 0.28 = 0.50*risk 0.20 + 0.50*fraud 0.36; banded to APPROVE.`
- `route` is null on DECLINE. The API returns nothing about the simulated charge result, the shared representation's feature values, or per-stage timings. None of these may be invented.
- Defaults (`libs/acip-common/src/acip_common/config.py`): `approve_max 0.35, challenge_max 0.70, fraud_block 0.85, w_risk 0.5, w_fraud 0.5, decision_deadline_ms 800`.
- UI baseline: React 18.3.1 + Vite 5.4.10 + Vitest 2.1.5, 24 passing tests, ESLint 9 flat config (explicit `globals` list, must be extended), Prettier (`.prettierrc`: double quotes, width 100) is installed but has no npm script. No router, no icon or font package. Dockerfile runs `npm ci && npm run build`, so `package-lock.json` must stay consistent.

## 1. Design decisions (rationale in 1-2 sentences each)

- **D1 Expose rationale/evidence via an additive backend change.** The data exists on the event but is dropped by the projector, and it is the single biggest "understand each step" win. Add nullable columns to `agent_verdicts` (`rationale TEXT, confidence NUMERIC, degraded BOOLEAN, model_version TEXT, evidence JSONB`) via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (so existing Postgres volumes migrate), have the projector write them, and have `reads.py` return them as extra optional keys on each verdict. Old clients ignore extra keys. The UI treats all of them as optional and falls back to static "general description" text, so it works against an un-upgraded API too. Isolated as FEAT-001 (independent of the UI work).
- **D2 Zero new runtime or dev dependencies.** System font stack (no CDN, no font package), hand-written inline SVG icons, hand-rolled focus trap, tooltip and tour. `package-lock.json` therefore does not change. Playwright and axe are used from a scratch dir outside the repo (section 9).
- **D3 Light default, no `prefers-color-scheme`.** The brief says light wins for the demo, so the theme is `light` unless `localStorage["acip.theme"] === "dark"`. An inline script in `index.html` sets `data-theme` on `<html>` before first paint (no flash). `prefers-color-scheme` is deliberately ignored and documented.
- **D4 "Why" is derived from returned data, explanation text is the primary signal.** `why.ts` classifies using the engine's own `explanation` markers first (they are authoritative and available even when verdicts are missing), and corroborates with verdicts (`policy.hint === DECLINE`, `fraud.score >= FRAUD_BLOCK`). It never recomputes a decision. The raw `explanation` is always shown verbatim beside the derived headline.
- **D5 "Rerouted around unhealthy processor" cannot be derived honestly** from the API (no route health returned). For APPROVE the Why panel says which processor was chosen and the failover order, and shows the Routing agent's rationale if D1 supplies it. The Scenario guide explains (static, labelled "what this scenario is set up to show") that the reroute scenario seeds a degraded preferred processor.
- **D6 Replay, not live progress.** While the POST is in flight, all stages show an indeterminate "Evaluating" state (no fake progress). After the response, stages reveal in sequence (about 450 ms apart, instant under reduced motion) as a labelled replay. Only the real client round trip (`performance.now()` around `postCheckout`) is shown as a time.
- **D7 Jaeger link goes to the Jaeger home page** (`VITE_JAEGER_URL`, default `http://localhost:16686`) with the trace_id copyable, since it is unverified that the UUID is the exported OTel trace id.
- **D8 Component state lives in one reducer hook** (`useCheckoutRun`) taken out of `App.tsx`, so the journey and cards are pure functions of state and testable.

## 2. Layout

Header (sticky, 64px): brand slot (left) | "Decision Intelligence" title | connection pill | Tour | Help (with `?` hint) | theme toggle.

- **>= 1100px:** two columns. Left rail 380px (Scenario launcher, collapsible custom checkout form, Recent transactions). Right main: Outcome banner (gauge + decision chip) -> Why this decision -> Decision Journey (six stages; Stage 3 contains the six agent cards) -> Decision trace (explain, collapsible).
- **768-1099px:** single column. Launcher first as a 2-column card grid, then the right-column content. Agent cards 2x3.
- **>= 1600px / projector:** root font size scales (`clamp(16px, 0.55vw + 11px, 20px)`), all sizing in `rem`, so text stays large. Max content width 1680px.
- **Idle:** the journey renders as a preview of the six stages ("Standing by", stage descriptions visible) and six agent cards in idle state, above a prominent empty-state card: "Start here: pick a scenario on the left. Takes about a second."

## 3. Brand design tokens

### 3.1 Files

- `ui/src/styles/brand.css`: **only** brand colours (header comment: *hex values are approximations taken from third-party listings; replace with official Global Payments values; editing this one file re-skins the UI*). Defines `--brand-deep`, `--brand-blue`, `--brand-teal` and their derived text/fill variants for light and dark.
- `ui/src/styles/tokens.css`: semantic tokens built on brand.css: surfaces, text, borders, status, focus ring, type scale, spacing, radius, elevation, motion. `:root, [data-theme="light"]` and `[data-theme="dark"]` blocks.
- `base.css` (reset, typography, focus, utilities, reduced-motion), `layout.css`, `components.css`. Import order in `main.tsx`: brand, tokens, base, layout, components. Delete `styles.css`.

### 3.2 Palette and AA check (WCAG contrast ratios computed for this plan)

Brand colours are approximate, so values are adjusted where needed. Text needs 4.5:1, non-text UI parts need 3:1.

| Role | Light theme | Ratio | Dark theme | Ratio |
|---|---|---|---|---|
| Page bg / surface | `#F4F7FA` / `#FFFFFF` | n/a | `#0B1726` / `#12263F` | n/a |
| Primary text | `#12263F` on white | 15.28 | `#E8EEF5` on `#12263F` | 13.08 |
| Muted text | `#4A5D75` on `#F4F7FA` | 6.27 | `#9FB3C8` on `#12263F` | 7.10 |
| Brand deep `#003B71` (headings, primary button fill with white text) | on white / on `#F4F7FA` | 11.27 / 10.48 | n/a (dark uses `--brand-deep` only as a fill under light text) | n/a |
| Brand blue `#00639A` (links, accents, focus ring) | on white / `#F4F7FA` | 6.46 / 6.01 | replaced by `#6DB7EA` (lighter tint) on `#12263F` / `#0B1726` | 6.99 / 8.25 |
| Brand teal as **graphic** `#129B75` | 3.52 on white (passes 3:1 for non-text only, **fails as text**) | 3.52 | `#3FC9A0` on `#12263F` | 7.33 |
| Brand teal as **text** (adjusted) `#0B7A5C` | on white / `#F4F7FA` | 5.31 / 4.94 | `#3FC9A0` | 7.33 |
| White text on `#003B71` / `#00639A` buttons | n/a | 11.27 / 6.46 | `#0B1726` text on `#6DB7EA` button | 8.25 |
| APPROVE green | `#1B7A34` on white; on tint `#E8F5EC` | 5.41; 4.82 | `#4ADE80` on `#12263F`; on tint `#12301F` | 8.77; 8.21 |
| CHALLENGE amber | `#8A5A00` on white; on tint `#FFF4D6` | 5.93; 5.41 | `#FBBF24` on `#12263F`; on tint `#33260A` | 9.15; 8.84 |
| DECLINE red | `#B42318` on white; on tint `#FDECEA` | 6.57; 5.75 | `#F87171` on `#12263F`; on tint `#3A1512` | 5.52; 5.86 |

Adjustments to record in brand.css comments: teal text uses `#0B7A5C` (light) because the logo teal `#129B75` is 3.52:1; blue and teal are lightened in dark mode. Status colours are separate tokens (`--status-approve-*`, etc.) and never alias brand tokens. Because teal and approve-green are both green-ish, **teal is never used to mean success**; status is always icon + text label + tinted chip (check circle / alert triangle / x circle), so colour is never the only signal. Teal is limited to accents (gradient strip, step connectors, "VETO capable" outline is NOT teal; it uses brand blue).

The implementer must re-run a contrast script (inline Python, same formula as above) after any value change, and the reviewer re-checks. Add a Vitest unit test `contrast.test.ts` that parses the hex pairs from a small exported list in `src/styles/contrast-pairs.ts` (same numbers as the table) and asserts >= 4.5 (text) / >= 3 (graphics), so a re-skin that breaks AA fails CI. The test imports the pairs from that TS file, and `brand.css` header says "update contrast-pairs.ts when swapping values".

### 3.3 Other tokens

- **Type:** `--font-sans: Inter, "Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif` (Inter only if installed locally; nothing is fetched). Scale (rem): 0.8125, 0.9375, 1, 1.125, 1.375, 1.75, 2.25, 3. Headings 650-700 weight, deep blue (light) / near-white (dark). Mono stack for IDs.
- **Spacing:** 4px base: `--space-1..9` = 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6 rem.
- **Radius:** 6 / 10 / 16 / pill. **Elevation:** 3 levels of soft blue-tinted shadows (light), border + darker overlay (dark).
- **Motion:** `--ease-out: cubic-bezier(.2,.8,.2,1)`, durations 120/240/450 ms. A single `@media (prefers-reduced-motion: reduce)` block sets durations to ~0, disables the shimmer, gauge sweep and reveal translate; JS also reads `useReducedMotion()` to skip the replay delay.
- **Focus ring:** 3px `--focus-ring` (brand blue light, `#6DB7EA` dark) with 2px offset on every interactive element.

### 3.4 Brand slot

`ui/src/assets/brand/README.md` documents: "To use the official logo, save it as `logo.svg` (or `logo.png`) in this folder and restart/rebuild. Nothing is shipped here; the logo is never redrawn." `src/brand/logo.ts` uses `import.meta.glob("../assets/brand/logo.{svg,png}", { eager: true, query: "?url", import: "default" })`. `BrandMark` takes an optional `logoUrl` prop (defaults to the glob result): with a URL render `<img alt="Global Payments">` plus ACIP name; otherwise render the text wordmark **ACIP** (bold, deep blue) with the line "in partnership with Global Payments" ("Global Payments" co-brand line) beneath/aside. Document in `ui/README.md`.

## 4. Component list

Shared: `Icon` (inline SVG set: shield, network, scale, route, receipt, bolt, user, device, card, wallet, check-circle, alert-triangle, x-circle, help, info, copy, chevron, sun, moon, play, refresh, link, layers, lock), `InfoTip` (button with `aria-describedby` popover; opens on hover, focus and click, closes on Esc/blur), `StatusBadge` (decision chip: icon + text), `ScoreGauge`, `ScoreBar`, `CopyButton` (aria-live "Copied"), `Disclosure` (button `aria-expanded` + `aria-controls`, region), `Skeleton/Shimmer`.

Shell: `AppHeader`, `BrandMark`, `ThemeToggle` (`ThemeProvider`), `ConnectionStatus`, `HelpButton`.

Journey: `OutcomeBanner` (decision chip, gauge, key numbers, round trip), `WhyPanel`, `DecisionJourney`, `JourneyStage`, `ReplayNotice`, `AgentCards` + `AgentCard`, `TraceView` (explain, restyled).

Input: `ScenarioLauncher` + `ScenarioCard`, `CheckoutForm`, `RecentTransactions`, `EmptyState`.

Help: `HelpDrawer`, `GuidedTour`, `useFocusTrap`.

Domain (pure TS, no React): `config/thresholds.ts`, `domain/agents.ts`, `domain/why.ts`, `domain/journey.ts`, `decision.ts` (kept, extended), `content/*`.

`config/thresholds.ts` is the ONE constants module: `APPROVE_MAX=0.35, CHALLENGE_MAX=0.70, FRAUD_BLOCK=0.85, W_RISK=0.5, W_FRAUD=0.5, DECISION_DEADLINE_MS=800`, commented as mirroring `libs/acip-common/src/acip_common/config.py` defaults and "may differ if the deployment overrides them"; UI labels always say "default".

## 5. Content (verbatim copy for implementation)

Tone: plain and confident, short sentences, no em dashes, jargon only with an (i).

### 5.1 Header and empty state

- Title: "Decision Intelligence". Subtitle: "Every checkout, decided before the payment runs."
- Empty-state card: "Start here. Pick a scenario on the left and press Run. In about a second you will see the decision, why it was made, and what each of the six agents said. New here? Take the 60-second tour." Buttons: [Start tour] [Open help guide].

### 5.2 Journey stages (title / summary / How it works / What happened template)

1. **Checkout received** / "Your checkout arrives at the front door."
   - How: "checkout-api checks the request, gives it a transaction ID and a trace ID, and checks the idempotency key (i) so a retry never charges twice. Then it hands the checkout to the orchestrator."
   - Happened: "Received {amount} {currency} from {customer_id} for {merchant_id}. Transaction {transaction_id}. Round trip measured in your browser: {ms} ms." (request details come from the body we sent; for recents only id, customer and amount from the GET.)
2. **Shared representation built** / "One unified view of the transaction, built once."
   - How: "Before any agent looks at the checkout, the orchestrator builds one shared representation (i): the transaction's features plus signals from the Neo4j graph, such as devices shared with other customers, and fast counters from Redis. All six agents read this same view, so they never disagree about the facts."
   - Happened: "{n} agents produced verdicts from it, which confirms it was built." If n = 0: "Not confirmed yet: no agent verdicts have arrived." Always add the note: "The API does not return the representation itself, so its feature values are not shown here."
3. **Six agents evaluate in parallel** / "Six specialists review the same facts at the same time."
   - How: "Each agent answers its own question with a fast ML score. None waits for another. If an agent is slow, the decision engine moves on after a short deadline (default 800 ms) using safe defaults."
   - Happened: "{received} of 6 verdicts received." plus degraded note "Degraded: {names}. Their scores are valid; only the written explanation fell back to a template." plus the agent cards.
4. **Decision engine aggregates** / "Safety rules first, then a weighted score."
   - How (default thresholds, labelled): "1. Hard vetoes (i) first: if Policy denies, or the Fraud score is 0.85 or higher, the answer is DECLINE straight away. 2. Otherwise it blends Risk and Fraud into a composite score (i): 0.5 x risk + 0.5 x fraud. At or below 0.35 is APPROVE, up to 0.70 is CHALLENGE, above that is DECLINE. 3. Merchant rules can raise an APPROVE to a CHALLENGE. 4. Personalization only suggests a payment method; it never changes the outcome."
   - Happened: decision chip, composite (or "Scoring skipped: a veto ended the evaluation"), strategy name, and the engine's own words in a quote block: "Decision engine said: {explanation}".
5. **Route and execute** / "Pick the healthiest processor, keep the rest as backup."
   - How: "The Routing agent scores every payment processor on predicted success, cost and speed. The best one is chosen and the others are kept in order for failover (i) if it fails. The charge is sent to a simulated processor, so no real money moves. Only APPROVE attempts a charge."
   - Happened (APPROVE): "Routed to {route}. Failover order: {alts or 'none'}. Suggested payment method: {recommended_method}. Status: {status}." (CHALLENGE): "Held for extra verification. Route {route} is reserved; no charge is attempted until the customer steps up." (DECLINE): "No route chosen and no charge attempted." Always: "The simulated charge result is not returned by the API."
6. **Recorded** / "Everything is written down, so it can be explained later."
   - How: "Each step is saved as an event in the event log (i) in Kafka, and nothing is overwritten. A projector copies it into the Neo4j graph, so future checkouts learn from this one, and into Postgres, the audit trail behind this screen. The trace ID (i) ties all the logs together."
   - Happened: "Transaction {id} · Trace {trace_id} · Status {status} · {n} agent verdicts stored." Links: [Copy IDs] [Open Jaeger]. Hint: "In Jaeger, search service checkout-api."

### 5.3 Why this decision (derived in `why.ts`)

| kind | Trigger (first match) | Headline | Body |
|---|---|---|---|
| `policy_veto` | decision DECLINE and (explanation includes "policy denial" or policy hint DECLINE) | "Declined: policy veto" | "The Policy agent denied this checkout, for example because of a sanctions or compliance rule. A policy denial is final: no score can override it." |
| `fraud_veto` | DECLINE and (explanation includes "fraud score" under "Hard veto" or fraud score >= FRAUD_BLOCK) | "Declined: fraud veto" | "The Fraud agent scored this checkout {score}, at or above the default block threshold of 0.85. A veto ends the evaluation straight away, whatever the other agents said." |
| `generic_veto` | DECLINE and explanation starts "Hard veto" (other) | "Declined: hard veto" | "A hard rule ended the evaluation. See the engine's note below." |
| `missing_verdict` | explanation includes "Missing risk/fraud verdict" | "Safe default applied" | "A required Risk or Fraud verdict did not arrive in time, so the platform used its safe default ({decision})." |
| `score_decline` | DECLINE, no veto markers | "Declined: score too high" | "The composite score {x} is above the challenge limit (default 0.70)." |
| `merchant_step_up` | CHALLENGE and explanation includes "Merchant constraint" | "Challenge: merchant step-up" | "The risk and fraud scores alone would have approved this. The merchant's rules ask for extra verification on this kind of purchase, so it is stepped up." |
| `score_challenge` | other CHALLENGE | "Challenge: borderline score" | "The composite score {x} sits in the step-up band (above 0.35, up to 0.70), so extra verification is requested." |
| `low_risk_approve` | APPROVE | "Approved: low risk" | "No vetoes fired and the composite score {x} is at or below 0.35. Routed to {route}; {alts} kept as failover." + "Routing note: {rationale}" when present |
| `pending` | decision null/unknown | "Waiting for a decision" | "" |

`why()` returns `{kind, headline, body, drivers: AgentKey[], factors: string[]}`; `drivers` are highlighted on the cards (fraud_veto -> fraud; policy_veto -> policy; merchant_step_up -> merchant; score_* and approve -> risk, fraud, plus routing on approve). Free-form checkouts work because only response data is used, never scenario names.

### 5.4 Agents (`domain/agents.ts`)

| key | Name | Role (plain English) | What it looks at (general description, labelled "General description") | Badge |
|---|---|---|---|---|
| risk | Risk | "Judges how likely this customer is to cause a loss." | "Customer history, spending speed, past chargebacks, amount compared with normal." | "Scores 50%" (default weight) |
| fraud | Fraud | "Spots signs of fraud, including fraud rings." | "Shared devices, linked accounts in the graph, IP and location, bursts of activity." | "VETO capable" + "Scores 50%" |
| routing | Routing | "Chooses the best payment processor." | "Each processor's success rate, cost and speed, and the merchant's preference." | "ADVISORY: picks the route" |
| policy | Policy | "Enforces compliance and merchant rules." | "Identity checks, sanctions flags, merchant limits, geography rules." | "VETO capable" |
| merchant | Merchant | "Applies the merchant's own preferences." | "The merchant's risk appetite, allowed payment methods and overrides." | "ADVISORY: can request step-up" |
| checkout_personalization | Personalization | "Suggests the payment method most likely to work for this customer." | "The customer's past success with each payment method." | "ADVISORY: never changes the outcome" |

Card states (section 7): waiting, received, degraded, missing, idle. Contents: icon, name, role, what-it-looks-at, score bar (0-1, numeric readout; the fraud card shows a tick at the default 0.85 block threshold), hint chip (APPROVE/CHALLENGE/DECLINE with icon, or "no hint"), badge(s), and, when D1 data exists, "Reported by this agent": rationale text, confidence %, evidence list (`signal: value (weight)`), "Templated explanation" tag when `degraded`. A "Drove this outcome" ribbon (icon + text) on `drivers`.

### 5.5 Tooltips (InfoTip text, used next to the term everywhere)

- Shared representation: "One unified view of the transaction (its features plus graph signals), built once and read by every agent."
- Composite score: "A single number from 0 to 1 that blends the Risk and Fraud scores. Lower is safer."
- Veto: "A rule that ends the evaluation immediately. Policy deny or a very high Fraud score both veto."
- Challenge (step-up): "Not a no. The customer is asked for extra verification, such as a one-time code, before the payment is allowed."
- Decline: "The payment is blocked and no charge is attempted."
- Route: "The payment processor chosen to carry this charge."
- Failover: "If the chosen processor fails, the next one in the list is tried automatically."
- Idempotency key: "A unique key for one checkout attempt. Sending the same key again returns the same result instead of charging twice."
- Trace ID: "An ID that follows this checkout through every service. Use it to find its logs and traces."
- Event log: "A permanent, ordered record of everything that happened (Kafka). Nothing is overwritten."
- Decision engine: "The service that turns six verdicts into one decision."
- Degraded: "The agent's score is valid, but its written explanation fell back to a template."
- Advisory: "This agent informs the decision or the route but cannot block a payment."
- Round trip: "Time from sending the request to receiving the decision, measured in your browser."
- Simulated processor: "A stand-in for a real payment processor. No real money moves."
- Block threshold (default 0.85), approve limit (default 0.35), challenge limit (default 0.70): "Default setting. Your deployment may change it."

### 5.6 Help drawer sections (side nav inside the drawer, anchor links, `aria-current`)

1. **What is ACIP.** "ACIP decides every checkout before the payment is attempted. Six specialist AI agents look at the same shared facts at the same time. A decision engine combines their answers into APPROVE, CHALLENGE or DECLINE, with a plain-English reason. It runs entirely on open-source tools on this machine. Think commerce made easy, with less complexity and more confidence."
2. **How to read this screen.** Left: launch a checkout (scenarios, custom form, recent). Right top: the outcome and why. Middle: the decision journey, six steps, open any step to see what happened and how it works. Below: the full trace. Header: connection status, tour, help, theme.
3. **Decision journey step by step.** Six short entries repeating the stage "How it works" copy, plus: "While a checkout is being evaluated you will see a pulsing Evaluating state. When the result arrives, the steps light up one after another. That is a replay of the real result, not live timing. The only timing shown is the real round trip."
4. **The six agents.** The table in 5.4 as cards, including badges.
5. **Decision outcomes.** APPROVE: "Low risk. Let it through and send it to the best processor." CHALLENGE: "Borderline. Ask for extra verification first." DECLINE: "Blocked. Either a hard rule vetoed it or the score is too high. No charge is attempted." Plus "Score bands (defaults): up to 0.35 approve, up to 0.70 challenge, above that decline. Fraud 0.85 or higher is an automatic decline."
6. **Scenario guide** (static, labelled "What each scenario is set up to show"):
   - Clean shopper: "A regular customer with a good UPI history and a small amount. Risk and fraud scores are low, so the composite lands in the approve band. Expect APPROVE."
   - Fraud ring member: "Shares a device with a ring of linked accounts in the graph. The Fraud agent scores very high and vetoes. Expect DECLINE with no route."
   - High-value mid-risk: "A legitimate but large card purchase (4,800) from a customer with one past chargeback. Scores sit in the middle, and merchant rules ask for extra verification. Expect CHALLENGE."
   - Sanctioned geography: "A customer in a blocked region. Policy denies, which is final whatever the scores say. Expect DECLINE."
   - Unhealthy preferred route: "The merchant's preferred processor is set up as degraded. The customer is fine, so it is approved, and routing picks a healthier processor with the others as failover. Expect APPROVE on an alternate route."
7. **Glossary.** Shared representation, composite score, veto, challenge/step-up, route/failover, idempotency, trace ID, event log (text as in 5.5, one paragraph each; also add "Verdict: one agent's score and hint").
8. **Troubleshooting.**
   - "Agent cards are empty." -> "Verdicts land a moment after the decision banner. The screen checks for a few seconds. If they still do not appear, the agent services may be busy; run the checkout again."
   - "I see 'Cannot reach checkout-api'." -> "Start the platform with ./start.sh (Docker) or ./start-local.sh (local mode), then press Retry. Check http://localhost:8080/healthz."
   - "A scenario returned a different decision." -> "Re-seed with make seed, then try again. Free-form checkouts can legitimately land anywhere."
   - "Some agents say Degraded." -> "Expected on the local mock AI provider. Scores are valid; only the explanation text is templated."
   - "The tour did not appear." -> "It shows once. Use Help > Replay tour."
   - "Where are the agent explanations?" -> "They appear on each card when the API provides them; otherwise the card shows a general description."
   - "Where can I see traces?" -> "Jaeger at http://localhost:16686, service checkout-api; Neo4j Browser at http://localhost:7474."

### 5.7 Guided tour (6 steps, `data-tour` anchors; popover with "Step n of 6", Back / Next / Skip tour, Esc skips)

1. `brand`: "Welcome to ACIP. This takes under a minute. We will show you how every checkout gets decided."
2. `launcher`: "Start here. Each card is a ready-made story. Press Run on one to send a checkout."
3. `journey`: "This is the decision journey. Six steps from 'received' to 'recorded'. Open any step to see what happened and how it works."
4. `agents`: "Six specialist agents review the same facts in parallel. Cards marked VETO can stop a payment on their own."
5. `outcome`: "The outcome and a plain-English reason appear here. Green approves, amber asks for extra verification, red declines. Each also has an icon and a word."
6. `help`: "Stuck on a term? Press the Help button or the ? key any time. You can replay this tour from there."

Completion or skip sets `localStorage["acip.tour.done"]="1"`. Auto-starts about 600 ms after first load when unset. Replay: Help drawer button and header "Tour" button.

### 5.8 Scenario cards (keep `scenarioBody()` payload fields EXACTLY as is)

Add to `scenarios.ts`: `icon`, `story`, `demonstrates`. Name / story / expected chip / "What this demonstrates":
- Clean shopper / "A regular customer buys a small order by UPI." / APPROVE / "Low risk flows straight through."
- Fraud ring member / "A card used on a device shared with a ring of accounts." / DECLINE / "A fraud veto, found through the graph."
- High-value mid-risk / "A big card purchase from a customer with one past chargeback." / CHALLENGE / "Borderline cases are stepped up, not blocked."
- Sanctioned geography / "A wallet payment from a blocked region." / DECLINE / "A policy veto that no score can override."
- Unhealthy preferred route / "A good customer, but the preferred processor is struggling." / APPROVE / "Smart routing with failover."

Card states: ready (Run button), running (spinner + "Running", `aria-busy`), done (check + last decision chip), disabled while another run is in flight. The expected chip is labelled "Expected".

## 6. State matrix

Run phases (`useCheckoutRun`): `idle | evaluating | verdicts_pending | complete | partial | error`.

| Phase | Outcome banner | Why | Stages 1/4/5/6 | Stage 2 | Stage 3 + cards | Notice |
|---|---|---|---|---|---|---|
| idle | hidden; empty-state card | hidden | preview ("Standing by") | preview | 6 idle cards | none |
| evaluating (POST in flight) | skeleton | hidden | indeterminate "Evaluating" shimmer, `aria-busy` | indeterminate | indeterminate, cards "Evaluating" | live region: "Evaluating checkout" |
| verdicts_pending (POST done, polling GET) | shown with decision, gauge | shown (explanation-based) | revealed via replay, done | "Checking" | cards `waiting` | replay notice |
| complete (6 verdicts) | shown | shown | all done | done | 6 `received` (or `degraded`) | replay notice (dismissible) |
| partial (1-5 verdicts, or `partial` true, or `degraded_agents`) | shown, "Partial" tag | shown | done | done if n>=1 | mix of received / `missing` | "Some agents did not report in time. The engine used its safe defaults." |
| empty verdicts after polling | shown | shown | done | "Not confirmed" | 6 `missing` ("No verdict stored yet") | Same notice + Retry fetch button |
| error: POST failed | hidden | hidden | all stages `error` state with icon | error | error | role=alert: "Could not reach checkout-api. {detail} Start the platform with ./start.sh or ./start-local.sh, then retry." (keeps the phrase checked by the existing test) |
| recent selected (GET only) | shown from GET (decision, score) | derived from GET only (no explanation text, so `why` uses verdicts + composite) | stages 1, 3, 4, 6 from GET, 5 shows "Route details are only available right after a checkout" | per verdicts | per verdicts | "Loaded from history" |
| 404 on recent | message "No stored record yet" | | | | | |

Connection pill states: `checking` (neutral, pulse), `connected` (check + "Connected"), `unreachable` (x + "Cannot reach checkout-api", with Retry and a one-line fix in a popover). Polls `/healthz` on mount and every 15 s when the tab is visible, 3 s timeout via `AbortController`.

## 7. Behaviour details

- `useCheckoutRun` keeps: last request body (for stage 1), response, transaction view, `roundTripMs`, phase, `replayIndex`. Replay: `setInterval`/chained timeouts reveal stages; "Show all now" button and reduced-motion skip it. Stage expansion: the active stage opens during replay; at the end Stages 3 and 4 are open; "Expand all / Collapse all" toggle.
- `aria-live="polite"` region announces: "Evaluating", "Decision: DECLINE. Declined: fraud veto.", "Verdicts received: 6 of 6".
- Keyboard: `?` opens help unless focus is in `input, textarea, select, [contenteditable]` or a modifier key is held; `Esc` closes drawer, tour or open tooltip (innermost first).
- Help drawer: `role="dialog" aria-modal="true" aria-labelledby`, slide-over from right (full width under 600px), `useFocusTrap` (Tab cycles, initial focus on close button, focus returns to the trigger on close), backdrop click closes, `inert`/`aria-hidden` on the app root while open, nav list scrolls to sections, `HelpDrawer` is `React.lazy`-loaded (Suspense fallback is a small spinner) so help content is code-split.
- Storage: `lib/storage.ts` wraps `localStorage` in try/catch; keys `acip.theme`, `acip.tour.done`.
- Clipboard: `navigator.clipboard.writeText` with a hidden-textarea fallback; copy buttons have `aria-label="Copy transaction ID"`.
- Custom form: keep existing fields and defaults (read `CheckoutForm.tsx` first), add inline validation (required, amount > 0, currency 3 letters) with `aria-invalid` and `aria-describedby`, `InfoTip`s on device fingerprint ("Identifies the buyer's device. Devices shared across many customers raise the Fraud score.") and idempotency key, and a clear "Run custom checkout" primary button.
- Trace view: structured `<dl>` for inputs, strategy, final decision; a verdict table; "Raw JSON" disclosure; copy buttons for transaction_id.
- Thin-client rule: no function in `ui/src` computes a decision. Allowed: presentation maps, `why()` classification of the backend's explanation/verdicts, band **labels** for the gauge from `thresholds.ts`.

## 8. File-by-file plan

Backend (FEAT-001):
- `libs/acip-common/src/acip_common/bootstrap.py`: after the `agent_verdicts` CREATE, add 5 `ALTER TABLE agent_verdicts ADD COLUMN IF NOT EXISTS ...` statements to `_SCHEMA_STATEMENTS`; update docstring.
- `scripts/seed.py` (~line 230): add the same columns to its DDL (or call the same ALTERs) so seed and bootstrap agree.
- `services/graph-projector/src/graph_projector/postgres_projector.py::_apply_verdict`: insert/upsert the new columns (`json.dumps` for evidence). Append new params AFTER the existing four so the test fake cursor (`tests/test_projector.py` line ~150 reads `params[0], params[1]`) keeps working.
- `services/checkout-api/src/checkout_api/reads.py`: select the new columns in `_fetch`; on `psycopg.errors.UndefinedColumn` retry with the legacy 4-column query; `_verdicts_list` adds `rationale, confidence, degraded, model_version, evidence` (None / [] when absent). Update the module docstring.
- Tests: `services/graph-projector/tests/test_projector.py` (new columns persisted, replay idempotent), `services/checkout-api/tests/test_checkout.py` (GET and /explain return the extra optional keys; legacy rows without them still serialise). 
- `docs/06-api-contracts.md`: document the optional per-verdict fields.

UI (FEAT-002 to FEAT-004), all under `ui/`:
- Modify: `index.html` (theme bootstrap script, meta theme-color, title), `src/main.tsx`, `src/App.tsx` (compose only), `src/api/types.ts` (optional verdict fields), `src/api/client.ts` (`getHealth`, keep existing exports and `pollTransaction`), `src/scenarios.ts` (additive display fields only), `src/decision.ts` (add `decisionIcon`, `decisionTone`), `eslint.config.js` (add globals `HTMLElement, HTMLDivElement, HTMLButtonElement, KeyboardEvent, MouseEvent, Node, localStorage, navigator, performance, AbortController, requestAnimationFrame, cancelAnimationFrame, setInterval, clearInterval, getComputedStyle, matchMedia via window`), `package.json` (scripts only: `"format": "prettier --write ."`, `"format:check": "prettier --check ."`, `"typecheck": "tsc -b --noEmit"`; no dep changes), `vitest.setup.ts` (clear localStorage before each test, preset `acip.tour.done=1`, stub `matchMedia`, `scrollIntoView`, `performance` fine), `README.md`.
- Create: styles (5 files), `src/assets/brand/README.md`, `src/brand/logo.ts`, `src/config/thresholds.ts`, `src/domain/{agents,why,journey}.ts`, `src/content/{stages,help,glossary,tour,tooltips}.ts`, `src/lib/{storage,clipboard,format,useFocusTrap,useReducedMotion}.ts`, `src/state/useCheckoutRun.ts`, `src/theme/ThemeProvider.tsx`, `src/styles/contrast-pairs.ts`, and the components listed in section 4 under `src/components/{layout,journey,agents,input,help,ui}/`.
- Delete: `src/styles.css`, `components/ScenarioButtons.tsx`, `components/DecisionBanner.tsx` (superseded). Stale `ui/dist`, `ui/*.tsbuildinfo`, `vite.config.js/.d.ts` are build artefacts: check `git ls-files ui` and do not commit them if untracked.
- Unchanged: `Dockerfile`, `nginx.conf`, `vite.config.ts`, `start.sh`, `start-local.sh`, `VITE_CHECKOUT_API_URL` handling. (Optional doc text only.)

## 9. Test plan (Vitest 2.1.5 + RTL; run `cd ui && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`)

Update the 24 existing tests (`App`, `AgentCards`, `DecisionBanner` -> `OutcomeBanner`, `client`, `decision`, `scenarios`). New or rewritten:

- `decision.test.ts`: status mapping for APPROVE/CHALLENGE/DECLINE/unknown (class, label, icon, never colour-only text present).
- `why.test.ts`: one case per kind: policy veto, fraud veto, generic veto, missing verdict, merchant step-up, score challenge, score decline, low-risk approve with routing note, pending; plus a **free-form** fixture (customer `cus_custom_42`, amount 777, route `processor_b`) that classifies correctly; explanation-only (no verdicts) classification; drivers per kind.
- `journey.test.ts`: stage models for idle, evaluating, verdicts_pending, complete, partial, empty verdicts, error, history-selected; asserts no stage carries a timing other than `roundTripMs`; stage 5 text for APPROVE / CHALLENGE / DECLINE.
- `AgentCards.test.tsx`: waiting, received, degraded (both `degraded_agents` and `verdict.degraded`), missing, idle; VETO badge on policy and fraud only; ADVISORY on routing, merchant, personalization; driver ribbon; rationale/evidence rendered only when supplied; general description always labelled.
- `ScoreGauge.test.tsx`: exposes `role="img"` with text alternative; veto hides the gauge and shows "Scoring skipped".
- `HelpDrawer.test.tsx`: opens by button and by `?` (not when typing in an input), closes by Esc and close button, focus moves into drawer, Tab wraps (trap), focus returns to trigger, `aria-modal` and labelled.
- `GuidedTour.test.tsx`: auto-start when unset; Next/Back; Skip persists; finishing persists; no auto-start when set; replay from Help; Esc skips.
- `Theme.test.tsx`: light by default with empty storage (even if `matchMedia` says dark), toggle sets `data-theme=dark` and persists, reload (remount) restores; corrupt/unavailable storage does not throw.
- `BrandMark.test.tsx`: no logo -> text wordmark "ACIP" and "Global Payments" co-brand line; with `logoUrl` -> `<img alt="Global Payments">`.
- `scenarios.test.ts`: payloads for the five scenarios deep-equal the `scripts/demo.py::_request_body` values (merchant `mrc_demo`, currency `INR`, `ip 203.0.113.9`, UA `acip-demo/1.0`, token `tok_<name>`, device = seeded `device_id`, idem `idem_demo_<name>[_nonce]`); the new display fields do not leak into the body.
- `App.test.tsx`: unreachable POST -> alert contains "could not reach checkout-api"; success path shows outcome, why, journey; evaluating state visible while POST is pending; empty state on load; connection pill states (connected / unreachable with Retry); replay notice present; recent select; copy button.
- `contrast.test.ts`: all pairs in `contrast-pairs.ts` meet AA.
- `InfoTip.test.tsx`: keyboard focus shows the tip, Esc hides, `aria-describedby` wired.
- Backend: see section 8 (`uv run pytest libs/acip-common services/checkout-api services/graph-projector`, `uv run ruff check libs/acip-common ml scripts`).

## 10. Visual verification plan (not committed)

Setup outside the repo: `mkdir -p /tmp/acip-pw && cd /tmp/acip-pw && npm init -y && npm i playwright@1.48.2 @axe-core/playwright@4.10.1 && npx playwright install chromium` (needs network once; if blocked, report it and fall back to `npm run build` + manual notes). Script at `.agents/tasks/ui-screenshots/shoot.mjs`, run with `cd /tmp/acip-pw && node <repo>/.agents/tasks/ui-screenshots/shoot.mjs`. Output PNGs in `.agents/tasks/ui-screenshots/`. Ensure `git status` shows nothing from that folder staged (finalize must `git add` specific paths only).

Live stack: `curl -s localhost:8080/healthz`; if down run `./stop-local.sh && ./start-local.sh` (also needed after FEAT-001 so services reload; the projector's `ensure_schema` migrates the existing volume). Vite dev at `http://localhost:5173`; also verify the production build once with `npm run build && npx vite preview --port 4173`.

Shots (each at 1440x900 and 768x1024, light first, then dark where marked * ): `01-empty-onboarding*`, `02-tour-step`, `03-evaluating` (Playwright `route` delays POST by 2 s then continues), `04-approve*` (clean_shopper, journey expanded), `05-challenge` (high_value_midrisk), `06-decline-fraud-veto*` (ring_member), `07-decline-policy-veto` (sanctioned_geo), `08-partial-empty-verdicts` (route-mock GET `/v1/transactions/*` -> `verdicts:[]`), `09-unreachable` (abort `**/localhost:8080/**`), `10-help-drawer*`, `11-reroute-approve`. Run `AxeBuilder` on states 01, 04, 06, 10 in both themes: zero `serious`/`critical` violations (color-contrast included). Also tab through once and screenshot a focus ring.

The reviewer and fixer must open the PNGs (image read) and fix visible defects (overflow, clipped text, low contrast, misaligned gauge, broken tablet layout) before approving. Also check the Docker path builds: `docker build -f ui/Dockerfile -t acip-ui-check .` if Docker is up, otherwise note `npm run build` result.

## 11. Implementation plan (ordered)

- [ ] 1. Backend: persist and expose per-agent rationale/evidence (D1). Files: `libs/acip-common/src/acip_common/bootstrap.py`, `scripts/seed.py`, `services/graph-projector/src/graph_projector/postgres_projector.py`, `services/checkout-api/src/checkout_api/reads.py`, tests in `services/graph-projector/tests/test_projector.py`, `services/checkout-api/tests/test_checkout.py`, `docs/06-api-contracts.md`. Verify: `uv run pytest libs/acip-common services/checkout-api services/graph-projector -q` passes; `uv run ruff check libs/acip-common ml scripts` clean.
- [ ] 2. UI foundation: tokens (brand.css, tokens.css, base/layout/components css), theme provider and inline bootstrap, brand slot, icons, shared primitives (InfoTip, StatusBadge, ScoreBar, CopyButton, Disclosure), thresholds module, domain modules (agents, why), types/client (`getHealth`, optional verdict fields), ESLint globals and npm scripts, AppHeader + ConnectionStatus + ScenarioLauncher/CheckoutForm/RecentTransactions restyle, `useCheckoutRun`, App composition with the old result view temporarily kept. Verify: `cd ui && npm run lint && npm run typecheck && npm test && npm run build`.
- [ ] 3. Journey and agents: `journey.ts`, `DecisionJourney`, `JourneyStage`, `OutcomeBanner` + `ScoreGauge`, `WhyPanel`, `AgentCards`/`AgentCard`, `TraceView`, replay and evaluating states; remove superseded components and `styles.css`; update and add tests. Verify: same command set, all journey/why/agent tests pass.
- [ ] 4. Help system and docs: `HelpDrawer` (lazy), `GuidedTour`, tooltips wired to every key term, empty state, `?` shortcut, content modules, `ui/README.md` (design system, theming, brand slot, thresholds, help/tour, env vars), `ui/src/assets/brand/README.md`. Verify: full UI command set plus `npm run build` output shows a separate help chunk.
- [ ] 5. Integration and visual verification (convergence loop, iteration 1): full backend and UI suites, restart local stack, run the section 10 script, view the screenshots, fix defects. Verify: all commands green, axe clean, screenshots reviewed.
- [ ] 6. Finalize: stage only intended paths (never `.agents/`, `ui/dist`, `logs/`), commit locally on `feat/phase1-foundation`, do not push.

## 12. Assumptions and gaps

- Brand hex values are approximate and the site/Vega were unreadable (HTTP 403 on the one allowed fetch); the single-file re-skin plus contrast test are the mitigation.
- With the local mock LLM provider every verdict is `degraded=true`; cards will show "Templated explanation". That is honest and expected.
- Neo4j/Redis internals in stage 2 are described from the docs, not returned by the API; the UI says so.
- Jaeger deep link is unverified, so the home link is used (D7).
- The simulated charge outcome is not exposed by the API; the UI states that instead of inventing one.
