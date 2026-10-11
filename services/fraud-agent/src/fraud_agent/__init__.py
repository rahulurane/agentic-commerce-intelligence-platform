"""ACIP fraud-agent (docs/02 §3, §4).

The fraud agent scores a transaction's fraud likelihood by combining an ml-scoring
``model='fraud'`` probability with graph signals from the shared representation — the
shared-device ring size and 1h velocity — so a device-sharing ring yields a high fraud
score. When the score crosses ``Settings.fraud_block_threshold`` it emits a DECLINE
hint; the decision-engine's hard veto then declines the transaction (docs/02 §5). It is
the uniform agent machine with only its ``score_fn`` injected (docs/02 §2.2).
"""

from __future__ import annotations

__version__ = "0.1.0"
