"""Feature-transform tests: deterministic outputs and stable column ordering."""

from __future__ import annotations

from acip_common.features import (
    FEATURE_COLUMNS,
    amount_zscore,
    build_feature_row,
    geo_mismatch,
)


def test_feature_columns_order_stable() -> None:
    assert FEATURE_COLUMNS == (
        "amount_zscore",
        "velocity_1h",
        "method_age_days",
        "geo_mismatch",
        "shared_device_ring_size",
        "customer_txn_count_30d",
        "customer_chargeback_count",
    )


def test_amount_zscore_guards_zero_std() -> None:
    assert amount_zscore(100.0, 50.0, 0.0) == 0.0
    assert amount_zscore(150.0, 100.0, 25.0) == 2.0


def test_geo_mismatch() -> None:
    assert geo_mismatch("IN", "IN") == 0.0
    assert geo_mismatch("IN", "US") == 1.0
    assert geo_mismatch(None, "US") == 1.0
    assert geo_mismatch("US", None) == 1.0


def test_build_feature_row_known_inputs() -> None:
    raw = {
        "amount": 300.0,
        "customer_mean": 100.0,
        "customer_std": 50.0,
        "txn_count_last_hour": 11,
        "method_first_seen_days": 3.0,
        "txn_geo": "US",
        "home_geo": "IN",
        "ring_size": 4,
        "txn_count_30d": 12,
        "chargeback_count": 0,
    }

    row = build_feature_row(raw)

    # Keys are exactly the canonical columns, in order.
    assert list(row.keys()) == list(FEATURE_COLUMNS)
    assert row["amount_zscore"] == 4.0
    assert row["velocity_1h"] == 11.0
    assert row["method_age_days"] == 3.0
    assert row["geo_mismatch"] == 1.0
    assert row["shared_device_ring_size"] == 4.0
    assert row["customer_txn_count_30d"] == 12.0
    assert row["customer_chargeback_count"] == 0.0


def test_build_feature_row_defaults_empty() -> None:
    row = build_feature_row({})
    assert list(row.keys()) == list(FEATURE_COLUMNS)
    # Missing geo on both sides is a conservative mismatch.
    assert row["geo_mismatch"] == 1.0
    assert row["amount_zscore"] == 0.0
