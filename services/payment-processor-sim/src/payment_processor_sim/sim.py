"""Pure charge-simulation logic (docs/06 §2 'payment-processor-sim contract').

The outcome is driven entirely by configuration: ``sim_approval_rate`` sets the
CAPTURED/DECLINED draw, ``sim_latency_ms`` the reported latency, and
``sim_failure_mode`` (``none`` | ``timeout`` | ``error``) lets the demo surface
processor failures. The approve/decline draw takes an injectable ``random.Random`` so
tests are deterministic under a fixed seed.
"""

from __future__ import annotations

import random
import secrets
import string
from dataclasses import dataclass
from enum import Enum

from acip_common.config import Settings


class ChargeStatus(str, Enum):
    """Terminal charge outcomes for the simulator."""

    CAPTURED = "CAPTURED"
    DECLINED = "DECLINED"


class SimFailureMode(str, Enum):
    """Simulated failure modes selected by ``Settings.sim_failure_mode``."""

    NONE = "none"
    TIMEOUT = "timeout"
    ERROR = "error"


class ProcessorFailure(Exception):
    """Raised when ``sim_failure_mode`` requests a simulated processor failure."""

    def __init__(self, mode: SimFailureMode) -> None:
        self.mode = mode
        super().__init__(f"simulated processor failure: {mode.value}")


@dataclass(frozen=True)
class ChargeResult:
    """The result of a simulated charge."""

    status: ChargeStatus
    processor: str
    auth_code: str | None
    latency_ms: int


_AUTH_ALPHABET = string.ascii_uppercase + string.digits


def _auth_code(rng: random.Random) -> str:
    """Generate a short, opaque authorization code (6 chars)."""
    return "".join(rng.choice(_AUTH_ALPHABET) for _ in range(6))


def simulate_charge(
    *,
    route: str,
    settings: Settings,
    rng: random.Random | None = None,
) -> ChargeResult:
    """Simulate a charge on ``route`` using ``settings``.

    ``rng`` is injectable so tests get a deterministic approve/decline draw; when
    omitted a cryptographically seeded generator is used so production draws are not
    predictable. Raises :class:`ProcessorFailure` when ``sim_failure_mode`` is not
    ``none`` so the caller can model processor timeouts/errors (docs/06 §5).
    """
    draw = rng if rng is not None else random.Random(secrets.randbits(64))

    mode = SimFailureMode(settings.sim_failure_mode)
    if mode is not SimFailureMode.NONE:
        raise ProcessorFailure(mode)

    captured = draw.random() < settings.sim_approval_rate
    status = ChargeStatus.CAPTURED if captured else ChargeStatus.DECLINED
    return ChargeResult(
        status=status,
        processor=route,
        auth_code=_auth_code(draw) if captured else None,
        latency_ms=max(0, settings.sim_latency_ms),
    )


__all__ = [
    "ChargeResult",
    "ChargeStatus",
    "ProcessorFailure",
    "SimFailureMode",
    "simulate_charge",
]
