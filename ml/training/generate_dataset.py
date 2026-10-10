"""Layer 1 synthetic dataset generator (docs/05 §6.2).

Produces a labeled tabular dataset the risk and fraud models train on. ACIP ships no
real payment data; this generator plants learnable fraud/risk signatures plus
controlled label noise so the data is believable but not trivially separable
(docs/05 §6.1).

Generation order is entities -> transactions -> labels. Feature columns come from
``acip_common.features.build_feature_row`` / ``FEATURE_COLUMNS`` so the training matrix
uses the exact same transforms as live scoring (no train/serve skew; docs/05 §3).

Usage:
    python training/generate_dataset.py \
        --n-customers 10000 --n-merchants 500 --n-transactions 100000 \
        --fraud-rate 0.025 --label-noise 0.03 --seed 42
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

from acip_common.features import FEATURE_COLUMNS, build_feature_row

# Default output location (gitignored); keep in sync with .gitignore + train.py.
_DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "data"

_GEOS = ["IN", "US", "GB", "SG", "AE", "DE"]
_METHOD_TYPES = ["card", "upi", "netbanking", "wallet", "cod"]


@dataclass(frozen=True)
class GenConfig:
    """Generation parameters (docs/05 §6.2 defaults)."""

    n_customers: int = 10_000
    n_merchants: int = 500
    n_transactions: int = 100_000
    fraud_rate: float = 0.025
    label_noise: float = 0.03
    seed: int = 42


def _build_customers(rng: np.random.Generator, faker: Faker, n: int) -> pd.DataFrame:
    """Build the customer population: mostly low-risk, a long high-risk tail."""
    # risk_base in [0,1): most customers low, a tail high (beta skews low).
    risk_base = rng.beta(1.5, 6.0, size=n)
    return pd.DataFrame(
        {
            "customer_id": [f"cus_{i:06d}" for i in range(n)],
            "home_geo": rng.choice(_GEOS, size=n, p=[0.5, 0.2, 0.1, 0.08, 0.07, 0.05]),
            "risk_base": risk_base,
            # Spend baseline: lognormal, so a realistic right-skewed amount distribution.
            "spend_mean": rng.lognormal(mean=4.0, sigma=0.6, size=n).round(2),
            "spend_std": (rng.lognormal(mean=2.8, sigma=0.5, size=n)).round(2),
            # Lifetime chargebacks: Poisson, higher for riskier customers.
            "chargeback_count": rng.poisson(lam=0.2 + 2.0 * risk_base),
            "txn_count_30d": rng.poisson(lam=rng.uniform(2, 25, size=n)),
            "account_age_days": rng.integers(1, 1500, size=n),
        }
    )


def _build_merchants(rng: np.random.Generator, n: int) -> pd.DataFrame:
    """Build the merchant population across categories and risk appetites."""
    categories = ["retail", "travel", "gaming", "digital", "food", "electronics"]
    return pd.DataFrame(
        {
            "merchant_id": [f"mrc_{i:05d}" for i in range(n)],
            "category": rng.choice(categories, size=n),
            "risk_appetite": rng.uniform(0.2, 0.9, size=n).round(2),
        }
    )


def _assign_device_rings(
    rng: np.random.Generator, n_customers: int
) -> tuple[np.ndarray, dict[int, int]]:
    """Assign each customer a device; a few devices are shared across a ring.

    Returns per-customer device ids and a map device_id -> ring size (shared count).
    """
    device_ids = np.arange(n_customers)  # start 1:1 customer:device
    # Pick a small number of fraud rings; each pulls several customers onto one device.
    n_rings = max(1, n_customers // 500)
    ring_sizes: dict[int, int] = {}
    for _ in range(n_rings):
        ring_device = int(rng.integers(0, n_customers))
        size = int(rng.integers(3, 9))
        members = rng.choice(n_customers, size=size, replace=False)
        device_ids[members] = ring_device
        ring_sizes[ring_device] = size
    return device_ids, ring_sizes


def generate(config: GenConfig) -> pd.DataFrame:
    """Generate the labeled transaction dataset per ``config``."""
    rng = np.random.default_rng(config.seed)
    faker = Faker()
    faker.seed_instance(config.seed)

    customers = _build_customers(rng, faker, config.n_customers)
    _build_merchants(rng, config.n_merchants)  # populated for realism / future use
    device_ids, ring_sizes = _assign_device_rings(rng, config.n_customers)

    # Vectorized per-transaction customer selection.
    cust_idx = rng.integers(0, config.n_customers, size=config.n_transactions)
    cust = customers.iloc[cust_idx].reset_index(drop=True)

    n = config.n_transactions
    # Base transaction amount around the customer's spend baseline.
    amount = np.maximum(
        1.0,
        rng.normal(cust["spend_mean"].to_numpy(), cust["spend_std"].to_numpy() + 1e-6),
    ).round(2)

    # Transaction geo: usually home, sometimes elsewhere.
    txn_geo = np.where(
        rng.random(n) < 0.85,
        cust["home_geo"].to_numpy(),
        rng.choice(_GEOS, size=n),
    )

    # Device ring size per transaction (0 when device is not shared).
    cust_device = device_ids[cust_idx]
    ring_size = np.array([ring_sizes.get(int(d), 0) for d in cust_device])

    # Velocity: baseline low, bursts for a fraction of transactions.
    velocity = rng.poisson(lam=2.0, size=n)
    burst_mask = rng.random(n) < 0.03
    velocity = np.where(burst_mask, velocity + rng.integers(8, 20, size=n), velocity)

    # Payment method + age: brand-new methods for some high-value orders.
    method_type = rng.choice(_METHOD_TYPES, size=n)
    method_age = rng.integers(0, 720, size=n).astype(float)
    new_method_mask = rng.random(n) < 0.1
    method_age = np.where(new_method_mask, rng.integers(0, 3, size=n).astype(float), method_age)

    # Build feature rows via the shared transform (no skew).
    feature_rows: list[dict[str, float]] = []
    for i in range(n):
        feature_rows.append(
            build_feature_row(
                {
                    "amount": float(amount[i]),
                    "customer_mean": float(cust["spend_mean"].iat[i]),
                    "customer_std": float(cust["spend_std"].iat[i]),
                    "txn_count_last_hour": int(velocity[i]),
                    "method_first_seen_days": float(method_age[i]),
                    "txn_geo": str(txn_geo[i]),
                    "home_geo": str(cust["home_geo"].iat[i]),
                    "ring_size": int(ring_size[i]),
                    "txn_count_30d": int(cust["txn_count_30d"].iat[i]),
                    "chargeback_count": int(cust["chargeback_count"].iat[i]),
                }
            )
        )
    features = pd.DataFrame(feature_rows, columns=list(FEATURE_COLUMNS))

    # --- Labels ---------------------------------------------------------- #
    # Fraud signal: device ring, velocity burst, geo mismatch, new method on high value.
    high_value = amount > (cust["spend_mean"].to_numpy() * 2.5)
    fraud_signal = (
        0.35 * (ring_size >= 3)
        + 0.30 * (velocity >= 8)
        + 0.20 * (features["geo_mismatch"].to_numpy() == 1.0)
        + 0.25 * (new_method_mask & high_value)
    )
    # Calibrate a threshold so positives land near fraud_rate.
    fraud_cutoff = np.quantile(fraud_signal, 1.0 - config.fraud_rate)
    is_fraud = (fraud_signal >= max(fraud_cutoff, 0.3)).astype(int)

    # Risk signal: prior chargebacks + high amount z-score (bad outcome).
    risk_signal = (
        0.5 * (cust["chargeback_count"].to_numpy() >= 1)
        + 0.5 * (features["amount_zscore"].to_numpy() > 2.0)
        + 0.3 * cust["risk_base"].to_numpy()
    )
    risk_cutoff = np.quantile(risk_signal, 0.85)
    bad_outcome = (risk_signal >= risk_cutoff).astype(int)

    # Controlled label noise so the data is not perfectly separable.
    noise_fraud = rng.random(n) < config.label_noise
    noise_risk = rng.random(n) < config.label_noise
    is_fraud = np.where(noise_fraud, 1 - is_fraud, is_fraud)
    bad_outcome = np.where(noise_risk, 1 - bad_outcome, bad_outcome)

    out = features.copy()
    out.insert(0, "transaction_id", [f"txn_{i:08d}" for i in range(n)])
    out["method_type"] = method_type
    out["amount"] = amount
    out["is_fraud"] = is_fraud
    out["bad_outcome"] = bad_outcome
    return out


def _report(df: pd.DataFrame) -> None:
    """Print a class-balance + per-feature summary so the dataset is auditable."""
    n = len(df)
    print(f"rows: {n}")
    print(f"is_fraud positives:   {df['is_fraud'].sum()} ({df['is_fraud'].mean():.4f})")
    print(f"bad_outcome positives:{df['bad_outcome'].sum()} ({df['bad_outcome'].mean():.4f})")
    print("feature summary:")
    print(df[list(FEATURE_COLUMNS)].describe().T[["mean", "std", "min", "max"]].to_string())


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ACIP synthetic training dataset")
    parser.add_argument("--n-customers", type=int, default=10_000)
    parser.add_argument("--n-merchants", type=int, default=500)
    parser.add_argument("--n-transactions", type=int, default=100_000)
    parser.add_argument("--fraud-rate", type=float, default=0.025)
    parser.add_argument("--label-noise", type=float, default=0.03)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    config = GenConfig(
        n_customers=args.n_customers,
        n_merchants=args.n_merchants,
        n_transactions=args.n_transactions,
        fraud_rate=args.fraud_rate,
        label_noise=args.label_noise,
        seed=args.seed,
    )
    df = generate(config)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "transactions.parquet"
    csv_sample_path = out_dir / "transactions_sample.csv"

    df.to_parquet(parquet_path, index=False)
    df.head(200).to_csv(csv_sample_path, index=False)

    _report(df)
    print(f"wrote parquet: {parquet_path}")
    print(f"wrote csv sample: {csv_sample_path}")


if __name__ == "__main__":
    main()
