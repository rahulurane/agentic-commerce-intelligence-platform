"""The uniform agent health app (docs/02 §6, docs/07 §1).

:func:`make_health_app` builds the FastAPI app every agent process exposes: ``GET
/healthz`` (liveness — the process is up) and ``GET /readyz`` (readiness — the Kafka
consume loop is live). A lifespan handler starts the runner's
:meth:`~acip_agent_common.runner.AgentRunner.consume_forever` in a daemon thread on
startup, so the agent begins consuming ``txn.evaluate`` as soon as the app is up and the
thread does not block process shutdown.

Agents mount this instead of hand-rolling probes, keeping the "every service has
/healthz + /readyz" invariant uniform across the fleet.
"""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from acip_agent_common.runner import AgentRunner


class HealthResponse(BaseModel):
    """Liveness/readiness probe body."""

    status: str


def make_health_app(runner: AgentRunner) -> FastAPI:
    """Build the agent's FastAPI health app, starting its consume loop on startup.

    ``/healthz`` returns ``{"status": "ok"}`` once the process is up; ``/readyz`` returns
    ``{"status": "ready"}`` once the runner's consume thread is live, else ``503``. The
    lifespan starts :meth:`AgentRunner.consume_forever` in a daemon thread.
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        thread = threading.Thread(
            target=runner.consume_forever,
            name=f"{runner.agent_name.value}-consume",
            daemon=True,
        )
        thread.start()
        try:
            yield
        finally:
            runner.close()

    app = FastAPI(title=f"{runner.agent_name.value}-agent", version="0.1.0", lifespan=_lifespan)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        """Liveness probe: the process is up."""
        return HealthResponse(status="ok")

    @app.get("/readyz", response_model=HealthResponse)
    def readyz() -> HealthResponse:
        """Readiness probe: ready once the consume loop is live (docs/02 §6)."""
        if not runner.running:
            from fastapi import HTTPException

            raise HTTPException(status_code=503, detail="consumer not started")
        return HealthResponse(status="ready")

    return app


__all__ = ["HealthResponse", "make_health_app"]
