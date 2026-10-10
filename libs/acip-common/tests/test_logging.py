"""Logging tests: JSON records carry the bound trace id."""

from __future__ import annotations

import json
import logging

from acip_common.logging import JsonFormatter, bind_trace_id, get_trace_id


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="acip.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_log_line_is_valid_json_with_trace_id() -> None:
    bind_trace_id("trace_abc")
    try:
        formatted = JsonFormatter().format(_record("evaluating transaction"))
        parsed = json.loads(formatted)
        assert parsed["message"] == "evaluating transaction"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "acip.test"
        assert parsed["trace_id"] == "trace_abc"
        assert "timestamp" in parsed
    finally:
        bind_trace_id(None)


def test_trace_id_absent_when_unbound() -> None:
    # Reset context explicitly.
    bind_trace_id(None)
    assert get_trace_id() is None
    parsed = json.loads(JsonFormatter().format(_record("no trace")))
    assert "trace_id" not in parsed


def test_extra_fields_are_folded_in() -> None:
    bind_trace_id(None)
    record = _record("with extra")
    record.__dict__["agent"] = "fraud"
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["agent"] == "fraud"
