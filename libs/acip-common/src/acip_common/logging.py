"""Structured JSON logging with trace correlation (docs/01 §6, docs/07 §5).

Zero extra dependencies: stdlib ``logging`` plus a JSON formatter and a ``trace_id``
carried in a ``contextvars`` context so every log line emitted while handling a
transaction correlates to its trace. OpenTelemetry wiring is a later-phase service
concern; this gives correlated structured logs now.
"""

from __future__ import annotations

import contextvars
import json
import logging
from datetime import UTC, datetime

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "acip_trace_id", default=None
)

# Standard LogRecord attributes we do not want duplicated inside the JSON "extra" dump.
_RESERVED = set(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}


def bind_trace_id(trace_id: str | None) -> contextvars.Token[str | None]:
    """Bind ``trace_id`` to the current context; returns a reset token."""
    return _trace_id_var.set(trace_id)


def get_trace_id() -> str | None:
    """Return the trace id bound to the current context, if any."""
    return _trace_id_var.get()


class JsonFormatter(logging.Formatter):
    """Render a ``LogRecord`` as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace_id = get_trace_id()
        if trace_id is not None:
            payload["trace_id"] = trace_id

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        # Fold any structured `extra=...` fields in.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


__all__ = ["JsonFormatter", "bind_trace_id", "configure_logging", "get_trace_id"]
