"""ACIP checkout-personalization-agent (docs/02 §3.2, ADVISORY).

The checkout-personalization agent ranks payment methods by predicted success from the
shared representation's ``method_history`` (successes / (successes + failures)) and
recommends the top method. It is ADVISORY only — it NEVER vetoes: it emits an APPROVE
hint, carries the recommended method name in the verdict rationale (the decision-engine
reads it as the recommended method), and puts the ranking + confidence in evidence. It
is the uniform agent machine with only its ``score_fn`` injected (docs/02 §2.2).
"""

from __future__ import annotations

__version__ = "0.1.0"
