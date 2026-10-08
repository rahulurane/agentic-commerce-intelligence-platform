# 05 — ML Scoring Service

## 1. Goal & latency budget

`ml-scoring-service` serves XGBoost/LightGBM models for **risk** and **fraud** scoring
with a **sub-50ms** target at p95. It is a stateless FastAPI service that loads
serialized models at startup and scores pre-built feature vectors.

Latency budget (p95):

| Stage | Budget |
|-------|--------|
| Feature assembly (caller side, Redis + graph) | ≤ 20ms |
| Transport to scoring service (intra-Compose) | ≤ 5ms |
| Model inference (tree ensemble) | ≤ 15ms |
| Serialization / overhead | ≤ 10ms |
| **Total scoring path** | **≤ 50ms** |

The LLM rationale is explicitly **off** this path (handled asynchronously after the
score), so the number that gates the decision is always fast.

## 2. Service contract

```http
POST /v1/score
{
  "model": "fraud",                 // "risk" | "fraud"
  "model_version": "latest",
  "features": {
    "amount_zscore": 2.1,
    "velocity_1h": 11,
    "shared_device_ring_size": 4,
    "method_age_days": 3,
    "geo_mismatch": 1
  },
  "metadata": { "trace_id": "...", "txn_id": "txn_..." }
}
→ 200
{
  "score": 0.87,
  "model": "fraud",
  "model_version": "fraud-xgb-2026.10.01",
  "top_features": [
    { "name": "shared_device_ring_size", "contribution": 0.42 },
    { "name": "velocity_1h", "contribution": 0.31 }
  ],
  "latency_ms": 12
}
```

`top_features` are per-prediction contributions (SHAP or gain-based fallback) — these
feed the LLM rationale, closing the explainability loop.

## 3. Feature pipeline

- **Offline (training):** a reproducible pipeline over synthetic transaction data
  builds the training matrix and labels. Lives in `ml/training/`.
- **Online (serving):** callers (agents) assemble the feature dict from Redis hot
  features + Neo4j graph signals + the transaction payload, then call the scoring
  service. Feature definitions are shared via `acip-common` so offline and online use
  the same names and transforms (avoids train/serve skew).

## 4. Models

| Model | Type | Target | Notes |
|-------|------|--------|-------|
| `risk` | XGBoost classifier | P(default/bad outcome) | credit/behavioral features |
| `fraud` | LightGBM classifier | P(fraud) | graph + velocity features |

Artifacts are versioned (`<model>-<algo>-<date>`) and stored under `ml/models/`.
The service can hold multiple versions and route by `model_version` for safe rollout.

## 5. Training job

`ml/training/` ships a `train.py` that:

1. Loads the synthetic labeled dataset (see §6 for how it is generated).
2. Builds features via the shared transforms.
3. Trains XGBoost (risk) and LightGBM (fraud) with a basic validation split.
4. Emits metrics (AUC, PR-AUC) and serializes artifacts + a `model_card.json`.

Runs as a one-shot Docker job (`make train`) before the stack serves real scores.
Until trained, the service can serve a deterministic heuristic so the demo still runs.

## 6. Dataset design (synthetic)

ACIP ships **no real payment data** — real card/payment data is sensitive and out of
scope. All data is **generated synthetically** and reproducibly. There are two distinct
layers, produced by two generators, for two different purposes.

### 6.1 Why synthetic, and the honesty caveat

- No external downloads, no PII, fully offline, deterministic (fixed seed).
- The models learn the patterns **we plant**, so reported AUC/PR-AUC illustrate that the
  pipeline works end to end — they are **not** evidence of real-world fraud-detection
  accuracy. This caveat is written into `model_card.json` so results are not misread.

### 6.2 Layer 1 — ML training dataset (`ml/training/generate_dataset.py`)

A labeled tabular dataset the risk and fraud models train on.

**Generation order (entities → transactions → labels):**

1. **Entities.** A population of customers, merchants, devices, IPs, and payment
   methods, with realistic distributions:
   - customers: mostly low-risk, a long tail of high-risk; varied account age and
     method-success history
   - merchants: spread across categories and risk appetites
   - devices/IPs: mostly 1:1 with customers, a few shared (the raw material for rings)
2. **Transactions.** Normal purchases plus deliberately injected signatures so there is
   something learnable:
   - *Fraud signatures:* device-sharing rings (one device across many unrelated
     customers), velocity bursts (many txns in minutes), geo mismatch, brand-new method
     on a high-value order
   - *Risk signatures:* prior defaults/chargebacks, amount far above the customer's
     baseline (`amount_zscore`)
3. **Labels.** `is_fraud` and `bad_outcome` derived from the planted signatures **plus
   controlled noise**, so the data is not trivially separable (believable AUC, not 1.0).

**Parameters (config, with defaults):**

| Param | Default | Meaning |
|-------|---------|---------|
| `n_customers` | 10,000 | entity population |
| `n_merchants` | 500 | merchant population |
| `n_transactions` | 100,000 | dataset size |
| `fraud_rate` | 0.025 | ~2.5% positive class |
| `label_noise` | 0.03 | flips to avoid perfect separability |
| `seed` | 42 | reproducibility |

**Feature columns** match the shared representation (doc 03 §8) exactly — the transform
functions live in `acip-common` and are imported by both the generator and the live
serving path, so there is **no train/serve skew**. Core features: `amount_zscore`,
`velocity_1h`, `method_age_days`, `geo_mismatch`, `shared_device_ring_size`,
`customer_txn_count_30d`, `customer_chargeback_count`.

**Output:** Parquet (+ CSV sample) under `ml/data/`, consumed by `train.py`. A
class-balance report and a feature histogram are printed so the dataset is auditable.

**Tools:** Python + NumPy + pandas, `Faker` for names/addresses/IPs. No ML needed to
generate it — it is rule-based with randomized noise.

### 6.3 Layer 2 — Graph & demo seed (`scripts/seed.py`)

A smaller, hand-shaped set loaded into **Neo4j + Postgres** so the live demo produces
meaningful graph signals and **predictable** outcomes. It builds named scenarios:

| Scenario customer | Shape | Expected decision |
|-------------------|-------|-------------------|
| `clean_shopper` | good history, normal amount | **APPROVE** (+ recommended method, healthiest route) |
| `ring_member` | device shared across a fraud ring, velocity burst | **DECLINE** (fraud veto) |
| `high_value_midrisk` | mid risk score, large amount | **CHALLENGE** (step-up) |
| `sanctioned_geo` | customer in a blocked region | **DECLINE** (policy veto) |
| `unhealthy_preferred_route` | preferred processor degraded | **APPROVE on alternate route** (route-scoring + failover) |

It also writes per-customer method-success history (`USED_METHOD_TYPE` edges) so the
checkout-personalization agent has something to recommend, and candidate routes with
varying health so route-scoring is visible in the Neo4j browser.

The seed is small (tens of customers) and idempotent (re-running `make seed` resets to
the same known state), which is what makes the `make demo` walkthrough deterministic.

### 6.4 How the two layers relate

- Layer 1 trains the **models** (statistical behavior over a large population).
- Layer 2 seeds the **live graph** (a few readable, inspectable scenarios).
- Both draw features from the **same shared definitions**, so a transaction seeded in
  Layer 2 is scored by models trained on Layer 1 without any schema mismatch.

## 7. Serving characteristics

- Models loaded once at startup; thread-safe inference; no per-request disk I/O.
- Warm-up prediction on boot to avoid first-request latency spikes.
- Horizontal scale: stateless, so N replicas behind the Compose/K8s service.
- Health/readiness endpoints gate traffic until models are loaded.

## 8. Metrics

- Inference latency histogram per model + version.
- Score distribution (drift watch).
- Request rate / error rate.
- Exposed to Prometheus; dashboards in Grafana.
