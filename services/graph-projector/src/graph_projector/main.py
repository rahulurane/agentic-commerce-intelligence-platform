"""FastAPI app for graph-projector (docs/03 §3-4, docs/07 §1).

The HTTP surface is only health probes — the real work is the Kafka consume loop. A
lifespan handler calls :meth:`PostgresProjector.ensure_schema` once at startup (fix A.1:
the always-on owner of runtime read-model population) and then starts the projector's
:meth:`ProjectorConsumer.consume_forever` in a daemon thread, mirroring the agent health
app pattern, so the projector begins consuming as soon as the app is up and the thread
does not block process shutdown.

``GET /healthz`` is liveness (the process is up); ``GET /readyz`` is readiness (the
consume loop is live). Thresholds/connection config come from
:class:`acip_common.config.Settings`.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from acip_common.config import get_settings
from acip_common.logging import configure_logging
from graph_projector.consumer import ProjectorConsumer
from graph_projector.neo4j_projector import Neo4jProjector
from graph_projector.postgres_projector import PostgresProjector

configure_logging()
_log = logging.getLogger("graph_projector")


class HealthResponse(BaseModel):
    """Liveness/readiness probe body."""

    status: str


def _build_consumer() -> ProjectorConsumer:
    """Wire the projectors + Kafka consumer from Settings (docs/07 §2)."""
    settings = get_settings()
    postgres = PostgresProjector(settings.postgres_dsn)
    neo4j = Neo4jProjector(settings.neo4j_uri, settings.neo4j_auth)
    return ProjectorConsumer(settings.kafka_bootstrap, postgres, neo4j)


# The consumer is built once at import so the health routes can read its readiness and the
# lifespan can bootstrap the read-model schema via its PostgresProjector (fix A.1).
_consumer = _build_consumer()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bootstrap the read-model schema (fix A.1), then start the consume loop in a thread."""
    _consumer.postgres.ensure_schema()
    thread = threading.Thread(
        target=_consumer.consume_forever,
        name="graph-projector-consume",
        daemon=True,
    )
    thread.start()
    _log.info("graph-projector consume loop started")
    try:
        yield
    finally:
        _consumer.close()


app = FastAPI(title="graph-projector", version="0.1.0", lifespan=_lifespan)


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness probe: the process is up."""
    return HealthResponse(status="ok")


@app.get("/readyz", response_model=HealthResponse)
def readyz() -> HealthResponse:
    """Readiness probe: ready once the consume loop is live (docs/01 §6)."""
    if not _consumer.running:
        raise HTTPException(status_code=503, detail="consumer not started")
    return HealthResponse(status="ready")
