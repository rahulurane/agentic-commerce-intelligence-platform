"""ACIP merchant-agent (docs/02 §3, advisory soft-constraints).

The merchant agent emits merchant preference adjustments and soft constraints. On a
high-value transaction (amount >= ``Settings.merchant_high_value_challenge``) it emits a
``force_challenge`` evidence row and a CHALLENGE hint so the decision-engine upgrades an
APPROVE to CHALLENGE (docs/02 §5 step 4). It is NEVER a hard veto. It is the uniform
agent machine with only its ``score_fn`` injected (docs/02 §2.2).
"""

from __future__ import annotations

__version__ = "0.1.0"
