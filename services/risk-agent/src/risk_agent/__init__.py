"""ACIP risk-agent (docs/02 §3).

The risk agent scores a transaction's default/chargeback risk by calling
``ml-scoring-service`` with ``model='risk'`` over the shared representation's feature
row, then bands the returned probability into an APPROVE / CHALLENGE / DECLINE hint.
It is the SAME machine as every other agent — only its injected ``score_fn`` differs
(docs/02 §2.2) — wired into the ``acip_agent_common`` runner.
"""

from __future__ import annotations

__version__ = "0.1.0"
