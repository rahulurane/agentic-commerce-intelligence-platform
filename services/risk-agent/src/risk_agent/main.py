"""FastAPI entrypoint for risk-agent (docs/02 §6, docs/07 §1).

Builds the shared agent health app (``GET /healthz`` + ``GET /readyz``) over a risk
:class:`~acip_agent_common.AgentRunner`; the app's lifespan starts the Kafka consume
loop (group ``risk-agents`` on ``txn.evaluate``) in a daemon thread. Structured logging
is configured on import so every log line is JSON with the request ``trace_id`` bound by
the runner (docs/01 §6).
"""

from __future__ import annotations

from acip_agent_common import make_health_app
from acip_common.config import get_settings
from acip_common.logging import configure_logging
from risk_agent.agent import build_runner

configure_logging()

runner = build_runner(get_settings())
app = make_health_app(runner)

__all__ = ["app", "runner"]
