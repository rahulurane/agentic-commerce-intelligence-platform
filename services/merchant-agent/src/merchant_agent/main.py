"""FastAPI entrypoint for merchant-agent (docs/02 §6, docs/07 §1).

Builds the shared agent health app over a merchant
:class:`~acip_agent_common.AgentRunner`; its lifespan starts the Kafka consume loop
(group ``merchant-agents`` on ``txn.evaluate``) in a daemon thread. Structured logging
is configured on import (docs/01 §6).
"""

from __future__ import annotations

from acip_agent_common import make_health_app
from acip_common.config import get_settings
from acip_common.logging import configure_logging
from merchant_agent.agent import build_runner

configure_logging()

runner = build_runner(get_settings())
app = make_health_app(runner)

__all__ = ["app", "runner"]
