"""ACIP policy-agent (docs/02 §3).

The policy agent applies hard compliance rules to the shared representation: it DENIES
(a hard-veto DECLINE) when the transaction's home/transaction geo is in the configured
sanctioned-geo list, or when the amount exceeds the absolute policy hard cap. Otherwise
it allows (APPROVE, score 0.0). The violated rules are surfaced as evidence. It is the
uniform agent machine with only its ``score_fn`` injected (docs/02 §2.2).
"""

from __future__ import annotations

__version__ = "0.1.0"
