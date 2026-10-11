"""ACIP routing-agent (docs/02 §3.1 ROUTE-SCORING).

The routing agent scores every candidate route in the shared representation on predicted
success x cost x latency, ranks them, and recommends the highest-scoring (healthiest)
route. It is advisory for the decision outcome — never a hard veto — emitting a ROUTE
hint and the ranked routes as evidence so the decision-engine's routing overlay can
surface the chosen route and failover alternatives (docs/02 §3.1, §5). It is the uniform
agent machine with only its ``score_fn`` injected (docs/02 §2.2).
"""

from __future__ import annotations

__version__ = "0.1.0"
