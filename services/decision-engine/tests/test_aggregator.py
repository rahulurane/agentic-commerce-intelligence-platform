"""Tests for the decision-engine aggregation strategy (docs/02 §5)."""

from __future__ import annotations

from decision_engine.aggregator import aggregate
from decision_engine.main import app
from fastapi.testclient import TestClient

from acip_common.config import Settings
from acip_common.schemas import (
    AgentName,
    CandidateRoute,
    DecisionHint,
    Evidence,
    Verdict,
)


def _settings(**overrides: object) -> Settings:
    # Settings fields use env aliases, so populate via the alias (upper-case) keys.
    base: dict[str, object] = {
        "FRAUD_BLOCK_THRESHOLD": 0.85,
        "APPROVE_MAX": 0.35,
        "CHALLENGE_MAX": 0.70,
        "W_RISK": 0.5,
        "W_FRAUD": 0.5,
        "MISSING_RISK_FRAUD_POLICY": "CHALLENGE",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _verdict(
    hint: DecisionHint,
    score: float,
    *,
    rationale: str = "",
    degraded: bool = False,
    evidence: list[Evidence] | None = None,
) -> Verdict:
    return Verdict(
        decision_hint=hint,
        score=score,
        confidence=0.9,
        rationale=rationale,
        evidence=evidence or [],
        model_version="test-v1",
        degraded=degraded,
    )


_ROUTES = [
    CandidateRoute(processor="processor_a", success_rate=0.97),
    CandidateRoute(processor="processor_b", success_rate=0.90),
]


def test_approve_low_scores() -> None:
    verdicts = {
        AgentName.RISK: _verdict(DecisionHint.APPROVE, 0.10),
        AgentName.FRAUD: _verdict(DecisionHint.APPROVE, 0.12),
    }
    out = aggregate(verdicts, _ROUTES, _settings())
    assert out.decision is DecisionHint.APPROVE
    assert out.route == "processor_a"
    assert out.route_alternatives == ["processor_b"]
    assert out.strategy == "weighted_veto"


def test_challenge_band() -> None:
    verdicts = {
        AgentName.RISK: _verdict(DecisionHint.CHALLENGE, 0.58),
        AgentName.FRAUD: _verdict(DecisionHint.APPROVE, 0.41),
    }
    out = aggregate(verdicts, _ROUTES, _settings())
    # composite = 0.5*0.58 + 0.5*0.41 = 0.495 -> CHALLENGE band
    assert out.decision is DecisionHint.CHALLENGE
    assert abs(out.composite_score - 0.495) < 1e-9


def test_decline_band_high_composite() -> None:
    verdicts = {
        AgentName.RISK: _verdict(DecisionHint.DECLINE, 0.80),
        AgentName.FRAUD: _verdict(DecisionHint.CHALLENGE, 0.70),
    }
    out = aggregate(verdicts, _ROUTES, _settings())
    # composite = 0.75 > challenge_max 0.70 -> DECLINE, no route overlay
    assert out.decision is DecisionHint.DECLINE
    assert out.route is None
    assert out.route_alternatives == []


def test_hard_veto_fraud_block() -> None:
    verdicts = {
        AgentName.RISK: _verdict(DecisionHint.APPROVE, 0.05),
        AgentName.FRAUD: _verdict(DecisionHint.DECLINE, 0.92),
    }
    out = aggregate(verdicts, _ROUTES, _settings())
    assert out.decision is DecisionHint.DECLINE
    assert out.composite_score == 1.0
    assert "fraud score" in out.explanation


def test_hard_veto_policy_deny() -> None:
    verdicts = {
        AgentName.RISK: _verdict(DecisionHint.APPROVE, 0.05),
        AgentName.FRAUD: _verdict(DecisionHint.APPROVE, 0.05),
        AgentName.POLICY: _verdict(DecisionHint.DECLINE, 0.0),
    }
    out = aggregate(verdicts, _ROUTES, _settings())
    assert out.decision is DecisionHint.DECLINE
    assert "policy denial" in out.explanation


def test_merchant_forces_challenge_on_approve() -> None:
    verdicts = {
        AgentName.RISK: _verdict(DecisionHint.APPROVE, 0.10),
        AgentName.FRAUD: _verdict(DecisionHint.APPROVE, 0.10),
        AgentName.MERCHANT: _verdict(
            DecisionHint.CHALLENGE,
            0.0,
            evidence=[Evidence(signal="force_challenge", value=1.0, weight=1.0)],
        ),
    }
    out = aggregate(verdicts, _ROUTES, _settings())
    assert out.decision is DecisionHint.CHALLENGE
    assert "Merchant constraint" in out.explanation


def test_personalization_is_advisory_only() -> None:
    verdicts = {
        AgentName.RISK: _verdict(DecisionHint.APPROVE, 0.10),
        AgentName.FRAUD: _verdict(DecisionHint.APPROVE, 0.10),
        AgentName.CHECKOUT_PERSONALIZATION: _verdict(DecisionHint.APPROVE, 0.0, rationale="upi"),
    }
    out = aggregate(verdicts, _ROUTES, _settings())
    assert out.decision is DecisionHint.APPROVE
    assert out.recommended_method == "upi"


def test_missing_risk_fraud_defaults_to_challenge() -> None:
    # No risk/fraud verdicts at all (deadline hit) -> configured default CHALLENGE.
    out = aggregate({}, _ROUTES, _settings())
    assert out.decision is DecisionHint.CHALLENGE
    assert out.route == "processor_a"


def test_missing_risk_fraud_policy_decline() -> None:
    verdicts = {AgentName.FRAUD: _verdict(DecisionHint.APPROVE, 0.1)}
    out = aggregate(verdicts, _ROUTES, _settings(MISSING_RISK_FRAUD_POLICY="DECLINE"))
    assert out.decision is DecisionHint.DECLINE
    assert out.route is None


def test_degraded_agents_surfaced() -> None:
    verdicts = {
        AgentName.RISK: _verdict(DecisionHint.APPROVE, 0.10, degraded=True),
        AgentName.FRAUD: _verdict(DecisionHint.APPROVE, 0.10),
    }
    out = aggregate(verdicts, _ROUTES, _settings())
    assert out.degraded_agents == [AgentName.RISK]


def test_decide_endpoint() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/decide",
        json={
            "transaction_id": "txn_1",
            "verdicts": {
                "risk": {
                    "decision_hint": "APPROVE",
                    "score": 0.1,
                    "confidence": 0.9,
                    "rationale": "low risk",
                    "evidence": [],
                    "model_version": "risk-v1",
                },
                "fraud": {
                    "decision_hint": "APPROVE",
                    "score": 0.1,
                    "confidence": 0.9,
                    "rationale": "low fraud",
                    "evidence": [],
                    "model_version": "fraud-v1",
                },
            },
            "candidate_routes": [{"processor": "processor_a", "success_rate": 0.97}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "APPROVE"
    assert body["route"] == "processor_a"


def test_decide_endpoint_zero_verdicts_defaults_challenge() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/decide",
        json={"transaction_id": "txn_2", "verdicts": {}, "candidate_routes": []},
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "CHALLENGE"


def test_health_and_ready() -> None:
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
