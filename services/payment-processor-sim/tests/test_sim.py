"""Tests for payment-processor-sim: deterministic outcomes + failure modes (docs/06 §2)."""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient
from payment_processor_sim.main import app
from payment_processor_sim.sim import (
    ChargeStatus,
    ProcessorFailure,
    SimFailureMode,
    simulate_charge,
)

from acip_common.config import Settings


def _settings(**overrides: object) -> Settings:
    # Settings fields use env aliases, so populate via the alias (upper-case) keys.
    base: dict[str, object] = {
        "SIM_APPROVAL_RATE": 0.9,
        "SIM_LATENCY_MS": 40,
        "SIM_FAILURE_MODE": "none",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_capture_is_deterministic_under_fixed_seed() -> None:
    result_a = simulate_charge(route="processor_a", settings=_settings(), rng=random.Random(42))
    result_b = simulate_charge(route="processor_a", settings=_settings(), rng=random.Random(42))
    assert result_a == result_b
    assert result_a.status is ChargeStatus.CAPTURED
    assert result_a.processor == "processor_a"
    assert result_a.auth_code is not None
    assert result_a.latency_ms == 40


def test_zero_approval_rate_declines() -> None:
    result = simulate_charge(
        route="processor_b", settings=_settings(SIM_APPROVAL_RATE=0.0), rng=random.Random(1)
    )
    assert result.status is ChargeStatus.DECLINED
    assert result.auth_code is None


def test_full_approval_rate_captures() -> None:
    result = simulate_charge(
        route="processor_a", settings=_settings(SIM_APPROVAL_RATE=1.0), rng=random.Random(7)
    )
    assert result.status is ChargeStatus.CAPTURED


@pytest.mark.parametrize("mode", ["timeout", "error"])
def test_failure_mode_raises(mode: str) -> None:
    with pytest.raises(ProcessorFailure) as exc:
        simulate_charge(
            route="processor_a",
            settings=_settings(SIM_FAILURE_MODE=mode),
            rng=random.Random(0),
        )
    assert exc.value.mode is SimFailureMode(mode)


def test_charge_endpoint_captures() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/charge",
        json={
            "transaction_id": "txn_1",
            "amount": 149.99,
            "currency": "USD",
            "route": "processor_a",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"CAPTURED", "DECLINED"}
    assert body["processor"] == "processor_a"
    assert body["latency_ms"] == 40


def test_charge_endpoint_failure_mode_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIM_FAILURE_MODE", "timeout")
    client = TestClient(app)
    resp = client.post(
        "/v1/charge",
        json={
            "transaction_id": "txn_2",
            "amount": 10.0,
            "currency": "USD",
            "route": "processor_a",
        },
    )
    assert resp.status_code == 503


def test_health_and_ready() -> None:
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
