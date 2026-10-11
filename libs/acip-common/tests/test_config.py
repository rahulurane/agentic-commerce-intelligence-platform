"""Config tests: locked defaults (docs/07 §2) and env override round-trip."""

from __future__ import annotations

import pytest

from acip_common.config import Settings


def test_defaults_match_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure a clean env so defaults are exercised (ignore any ambient .env values).
    for var in (
        "KAFKA_BOOTSTRAP",
        "NEO4J_URI",
        "DECISION_DEADLINE_MS",
        "FRAUD_BLOCK_THRESHOLD",
        "APPROVE_MAX",
        "CHALLENGE_MAX",
        "W_RISK",
        "W_FRAUD",
        "REPRESENTATION_VERSION",
        "ENABLED_METHOD_TYPES",
        "LLM_PROVIDER",
        "SIM_APPROVAL_RATE",
        "SIM_LATENCY_MS",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings()

    assert settings.kafka_bootstrap == "redpanda:9092"
    assert settings.neo4j_uri == "bolt://neo4j:7687"
    assert settings.decision_deadline_ms == 800
    assert settings.fraud_block_threshold == 0.85
    assert settings.approve_max == 0.35
    assert settings.challenge_max == 0.70
    assert settings.w_risk == 0.5
    assert settings.w_fraud == 0.5
    assert settings.representation_version == 1
    assert settings.llm_provider == "gemini"
    assert settings.sim_approval_rate == 0.9
    assert settings.sim_latency_ms == 40
    assert settings.enabled_method_types == ["card", "upi", "netbanking", "wallet", "cod"]


def test_env_override_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP", "localhost:19092")
    monkeypatch.setenv("APPROVE_MAX", "0.4")
    monkeypatch.setenv("ENABLED_METHOD_TYPES", "card, upi")

    settings = Settings()

    assert settings.kafka_bootstrap == "localhost:19092"
    assert settings.approve_max == 0.4
    assert settings.enabled_method_types == ["card", "upi"]
