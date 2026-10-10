"""Shared feature transforms — the single definition that prevents train/serve skew.

The 7 core feature columns (docs/05 §6.2, docs/03 §8) are computed here by pure
functions that take plain scalars/dicts (no numpy/pandas, keeping ``acip-common``
light). Both the offline dataset generator (``ml/training/generate_dataset.py``) and
the online scoring path import ``build_feature_row`` / ``FEATURE_COLUMNS`` so the
feature names and transforms are identical on train and serve (docs/05 §3).
"""

from __future__ import annotations

from collections.abc import Mapping

# Canonical, stable ordering of the model feature vector. Do not reorder: downstream
# model artifacts are trained against this exact column order.
FEATURE_COLUMNS: tuple[str, ...] = (
    "amount_zscore",
    "velocity_1h",
    "method_age_days",
    "geo_mismatch",
    "shared_device_ring_size",
    "customer_txn_count_30d",
    "customer_chargeback_count",
)


def amount_zscore(amount: float, customer_mean: float, customer_std: float) -> float:
    """Standard score of ``amount`` against the customer's spend baseline.

    Guards a zero/near-zero std (new customers) by returning 0.0 — no deviation can
    be asserted without a baseline.
    """
    if customer_std <= 1e-9:
        return 0.0
    return (amount - customer_mean) / customer_std


def velocity_1h(txn_count_last_hour: int) -> float:
    """Number of transactions by this customer in the trailing hour."""
    return float(max(0, txn_count_last_hour))


def method_age_days(method_first_seen_days: float) -> float:
    """Age in days of the payment method on file (0.0 for a brand-new method)."""
    return float(max(0.0, method_first_seen_days))


def geo_mismatch(txn_geo: str | None, home_geo: str | None) -> float:
    """1.0 when the transaction geo differs from the customer's home geo, else 0.0.

    Unknown geo on either side is treated as a mismatch (conservative).
    """
    if not txn_geo or not home_geo:
        return 1.0
    return 0.0 if txn_geo == home_geo else 1.0


def shared_device_ring_size(ring_size: int) -> float:
    """Count of distinct customers sharing this transaction's device (graph signal)."""
    return float(max(0, ring_size))


def customer_txn_count_30d(txn_count_30d: int) -> float:
    """Number of transactions by this customer in the trailing 30 days."""
    return float(max(0, txn_count_30d))


def customer_chargeback_count(chargeback_count: int) -> float:
    """Lifetime chargeback count for this customer (risk signal)."""
    return float(max(0, chargeback_count))


def _as_float(value: object, default: float = 0.0) -> float:
    """Coerce a raw mapping value to float, falling back to ``default``."""
    if value is None:
        return default
    return float(value)  # type: ignore[arg-type]


def _as_int(value: object, default: int = 0) -> int:
    """Coerce a raw mapping value to int, falling back to ``default``."""
    if value is None:
        return default
    return int(value)  # type: ignore[call-overload, no-any-return]


def _as_str(value: object) -> str | None:
    """Coerce a raw mapping value to str, or ``None``."""
    if value is None:
        return None
    return str(value)


def build_feature_row(raw: Mapping[str, object]) -> dict[str, float]:
    """Compute the full feature row from a raw signal mapping.

    ``raw`` carries the inputs each transform needs (see keys below). The returned
    dict has exactly ``FEATURE_COLUMNS`` as keys, in that order. This is the one
    function both training and serving call, so there is no train/serve skew.

    Expected ``raw`` keys:
        amount, customer_mean, customer_std,
        txn_count_last_hour, method_first_seen_days,
        txn_geo, home_geo, ring_size, txn_count_30d, chargeback_count
    """
    row: dict[str, float] = {
        "amount_zscore": amount_zscore(
            _as_float(raw.get("amount")),
            _as_float(raw.get("customer_mean")),
            _as_float(raw.get("customer_std")),
        ),
        "velocity_1h": velocity_1h(_as_int(raw.get("txn_count_last_hour"))),
        "method_age_days": method_age_days(_as_float(raw.get("method_first_seen_days"))),
        "geo_mismatch": geo_mismatch(_as_str(raw.get("txn_geo")), _as_str(raw.get("home_geo"))),
        "shared_device_ring_size": shared_device_ring_size(_as_int(raw.get("ring_size"))),
        "customer_txn_count_30d": customer_txn_count_30d(_as_int(raw.get("txn_count_30d"))),
        "customer_chargeback_count": customer_chargeback_count(
            _as_int(raw.get("chargeback_count"))
        ),
    }
    # Return in canonical column order.
    return {col: row[col] for col in FEATURE_COLUMNS}


__all__ = [
    "FEATURE_COLUMNS",
    "amount_zscore",
    "build_feature_row",
    "customer_chargeback_count",
    "customer_txn_count_30d",
    "geo_mismatch",
    "method_age_days",
    "shared_device_ring_size",
    "velocity_1h",
]
