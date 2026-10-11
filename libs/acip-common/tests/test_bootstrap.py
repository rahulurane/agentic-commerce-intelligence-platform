"""Bootstrap tests: ``ensure_read_model_schema`` issues the four CREATE TABLE statements.

A fake ``psycopg`` module is monkeypatched into ``sys.modules`` so the lazy
``import psycopg`` inside :func:`acip_common.bootstrap.ensure_read_model_schema` resolves
to the fake. The fake records the executed SQL and lets a test force a connection failure,
proving the best-effort posture (returns ``False`` without raising).
"""

from __future__ import annotations

import sys
import types

import pytest

from acip_common.bootstrap import ensure_read_model_schema

_EXPECTED_TABLES = ("transactions", "decisions", "agent_verdicts", "event_journal")


class _FakeCursor:
    """Records every executed statement."""

    def __init__(self, executed: list[str]) -> None:
        self._executed = executed

    def execute(self, statement: str) -> None:
        self._executed.append(statement)

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeConnection:
    """Context-manager connection yielding the recording cursor."""

    def __init__(self, executed: list[str]) -> None:
        self._executed = executed

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._executed)

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _install_fake_psycopg(
    monkeypatch: pytest.MonkeyPatch, *, executed: list[str], fail: bool = False
) -> None:
    """Register a fake ``psycopg`` module for the lazy import inside bootstrap."""

    def _connect(dsn: str, connect_timeout: int = 5) -> _FakeConnection:
        if fail:
            raise RuntimeError("cannot connect")
        return _FakeConnection(executed)

    fake = types.ModuleType("psycopg")
    fake.connect = _connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg", fake)


def test_issues_all_four_create_table_statements(monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []
    _install_fake_psycopg(monkeypatch, executed=executed)

    assert ensure_read_model_schema("postgresql://x") is True

    joined = " ".join(executed)
    for table in _EXPECTED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in joined
    # One statement issued per table.
    assert len(executed) == len(_EXPECTED_TABLES)


def test_connection_failure_returns_false_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []
    _install_fake_psycopg(monkeypatch, executed=executed, fail=True)

    assert ensure_read_model_schema("postgresql://unreachable") is False
    assert executed == []
