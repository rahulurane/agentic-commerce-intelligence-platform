"""Pydantic v2 domain models and event schemas for ACIP.

This single module holds the contracts shared across every service:

* the common **event envelope** (docs/03 §1),
* the **shared transaction representation** (docs/03 §8), computed once per
  transaction and read by all agents,
* the **Verdict** schema an agent emits (docs/02 §4),
* every **event payload** on the Kafka topic catalog (docs/03 §2, docs/06 §3).

Inbound models forbid extra fields so malformed events fail fast at the edge.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Base for inbound models: reject unknown fields, validate on assignment."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class DecisionHint(str, Enum):
    """Per-agent and final decision outcomes (docs/02 §4, §5)."""

    APPROVE = "APPROVE"
    CHALLENGE = "CHALLENGE"
    DECLINE = "DECLINE"
    ROUTE = "ROUTE"


class MethodType(str, Enum):
    """Payment method types (docs/03 §3, docs/07 ENABLED_METHOD_TYPES)."""

    CARD = "card"
    UPI = "upi"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    COD = "cod"


class AgentName(str, Enum):
    """The six evaluating agents (docs/02 §3)."""

    RISK = "risk"
    FRAUD = "fraud"
    ROUTING = "routing"
    POLICY = "policy"
    MERCHANT = "merchant"
    CHECKOUT_PERSONALIZATION = "checkout_personalization"


class EventType(str, Enum):
    """Event types on the Kafka topic catalog (docs/03 §2)."""

    TXN_CREATED = "txn.created"
    TXN_EVALUATE_REQUESTED = "txn.evaluate.requested"
    AGENT_VERDICT_PRODUCED = "agent.verdict.produced"
    DECISION_RENDERED = "decision.rendered"
    TXN_EXECUTED = "txn.executed"
    TXN_DECLINED = "txn.declined"
    TXN_CHALLENGED = "txn.challenged"


# --------------------------------------------------------------------------- #
# Shared transaction representation (docs/03 §8)
# --------------------------------------------------------------------------- #
class TransactionCore(_Strict):
    """The raw transaction facts carried in the representation (docs/03 §8)."""

    amount: float
    currency: str
    method_type: MethodType
    merchant_id: str
    customer_id: str


class MethodHistoryEntry(_Strict):
    """Per-method success/failure counts for a customer (docs/03 §3)."""

    successes: int = 0
    failures: int = 0


class CandidateRoute(_Strict):
    """A scorable payment route for the transaction (docs/02 §3.1, docs/03 §8)."""

    processor: str
    success_rate: float
    cost_bps: int | None = None
    p50_latency_ms: int | None = None


class SharedRepresentation(_Strict):
    """The single object every agent scores against (docs/03 §8).

    Built once per transaction by ``representation-service`` and attached to
    ``txn.evaluate.requested`` so all six agents see identical inputs.
    """

    representation_version: int = 1
    transaction_id: str
    built_at: datetime
    transaction: TransactionCore
    features: dict[str, float] = Field(default_factory=dict)
    graph_signals: dict[str, float] = Field(default_factory=dict)
    method_history: dict[str, MethodHistoryEntry] = Field(default_factory=dict)
    candidate_routes: list[CandidateRoute] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Verdict (docs/02 §4)
# --------------------------------------------------------------------------- #
class Evidence(_Strict):
    """A single explainability signal behind a verdict (docs/02 §4)."""

    signal: str
    value: float
    weight: float


class Verdict(_Strict):
    """An agent's verdict over the shared representation (docs/02 §4)."""

    decision_hint: DecisionHint
    score: float
    confidence: float
    rationale: str
    evidence: list[Evidence] = Field(default_factory=list)
    model_version: str
    degraded: bool = False


# --------------------------------------------------------------------------- #
# Payment method + context (docs/06 §1)
# --------------------------------------------------------------------------- #
class PaymentMethodRef(_Strict):
    """Tokenized payment instrument reference (docs/06 §1). PANs never stored raw."""

    type: MethodType
    token: str | None = None
    bin: str | None = None
    last4: str | None = None


class CheckoutContext(_Strict):
    """Device/network context for a checkout (docs/06 §1)."""

    device_fingerprint: str | None = None
    ip: str | None = None
    user_agent: str | None = None


# --------------------------------------------------------------------------- #
# Event payloads (docs/03 §2, docs/06 §3)
# --------------------------------------------------------------------------- #
class TxnCreatedPayload(_Strict):
    """``txn.created`` body (docs/06 §3)."""

    merchant_id: str
    customer_id: str
    amount: float
    currency: str
    payment_method: PaymentMethodRef
    context: CheckoutContext = Field(default_factory=CheckoutContext)
    idempotency_key: str | None = None


class TxnEvaluateRequestedPayload(_Strict):
    """``txn.evaluate.requested`` body — carries the representation (docs/06 §3)."""

    representation: SharedRepresentation
    expected_agents: list[AgentName]
    deadline_ms: int


class AgentVerdictProducedPayload(_Strict):
    """``agent.verdict.produced`` body (docs/02 §4)."""

    agent: AgentName
    produced_at: datetime
    verdict: Verdict


class DecisionRenderedPayload(_Strict):
    """``decision.rendered`` body (docs/02 §5)."""

    decision: DecisionHint
    composite_score: float
    strategy: str
    route: str | None = None
    route_alternatives: list[str] = Field(default_factory=list)
    recommended_method: str | None = None
    contributing_verdicts: list[AgentName] = Field(default_factory=list)
    explanation: str
    degraded_agents: list[AgentName] = Field(default_factory=list)


class TxnTerminalPayload(_Strict):
    """``txn.executed`` / ``txn.declined`` / ``txn.challenged`` body (docs/06 §3)."""

    decision: DecisionHint
    route: str | None = None
    processor_result: dict[str, object] | None = None
    composite_score: float
    decided_at: datetime


# --------------------------------------------------------------------------- #
# Event envelope (docs/03 §1)
# --------------------------------------------------------------------------- #
class EventEnvelope(_Strict):
    """The common envelope wrapping every ACIP event (docs/03 §1).

    ``event_id`` is the idempotency key; ``transaction_id`` is the Kafka partition
    key so all events for a transaction keep order. ``payload`` holds the typed body
    for ``event_type`` — validate it with the matching payload model above.
    """

    event_id: str
    event_type: EventType
    event_version: int = 1
    transaction_id: str
    trace_id: str
    occurred_at: datetime
    producer: str
    payload: dict[str, object] = Field(default_factory=dict)


__all__ = [
    "AgentName",
    "AgentVerdictProducedPayload",
    "CandidateRoute",
    "CheckoutContext",
    "DecisionHint",
    "DecisionRenderedPayload",
    "EventEnvelope",
    "EventType",
    "Evidence",
    "MethodHistoryEntry",
    "MethodType",
    "PaymentMethodRef",
    "SharedRepresentation",
    "TransactionCore",
    "TxnCreatedPayload",
    "TxnEvaluateRequestedPayload",
    "TxnTerminalPayload",
    "Verdict",
]
