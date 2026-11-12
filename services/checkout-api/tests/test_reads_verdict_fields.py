"""Per-agent rationale/evidence on the GET endpoints (additive fields, docs/06 §1).

``psycopg.connect`` is monkeypatched with a fake connection so the real
:class:`PostgresReadModel` (query selection, UndefinedColumn fallback, serialisation) runs
without a live Postgres, and is then served through the real routes.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from checkout_api.main import app, get_read_model
from checkout_api.reads import PostgresReadModel
from fastapi.testclient import TestClient

_TXN = {
    "id": "txn_1",
    "customer_id": "cus_1",
    "amount": Decimal("120.00"),
    "status": "EXECUTED",
    "decision": "APPROVE",
    "created_at": None,
}
_DECISION = {"decision": "APPROVE", "composite_score": Decimal("0.2"), "strategy": "weighted_veto"}

_FULL_ROW = {
    "agent": "risk",
    "score": Decimal("0.1"),
    "decision_hint": "APPROVE",
    "rationale": "low risk",
    "confidence": Decimal("0.9"),
    "degraded": False,
    "model_version": "risk-1",
    "evidence": [{"signal": "velocity", "value": 1.0, "weight": 0.5}],
}
_LEGACY_ROW = {"agent": "fraud", "score": Decimal("0.2"), "decision_hint": "APPROVE"}

_ADDITIVE_KEYS = {"rationale", "confidence", "degraded", "model_version", "evidence"}


class _Cursor:
    def __init__(self, verdict_rows: list[dict[str, Any]], legacy_only: bool) -> None:
        self._verdict_rows = verdict_rows
        self._legacy_only = legacy_only
        self._last = ""
        self.sql: list[str] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self._last = " ".join(sql.split())
        self.sql.append(self._last)
        if "FROM agent_verdicts" in self._last and "rationale" in self._last and self._legacy_only:
            raise psycopg.errors.UndefinedColumn('column "rationale" does not exist')

    def fetchone(self) -> dict[str, Any] | None:
        return _TXN if "FROM transactions" in self._last else _DECISION

    def fetchall(self) -> list[dict[str, Any]]:
        return self._verdict_rows


class _Conn:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self._cursor


def _install(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]], *, legacy_only: bool = False
) -> list[_Cursor]:
    cursors: list[_Cursor] = []

    def _connect(*args: Any, **kwargs: Any) -> _Conn:
        cursor = _Cursor(rows, legacy_only)
        cursors.append(cursor)
        return _Conn(cursor)

    monkeypatch.setattr(psycopg, "connect", _connect)
    return cursors


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_read_model] = lambda: PostgresReadModel("postgresql://x")
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_and_explain_return_optional_verdict_keys(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    _install(monkeypatch, [_FULL_ROW])

    for path in ("/v1/transactions/txn_1", "/v1/transactions/txn_1/explain"):
        resp = client.get(path)
        assert resp.status_code == 200
        verdict = resp.json()["verdicts"][0]
        # Existing keys unchanged.
        assert (verdict["agent"], verdict["score"], verdict["hint"]) == ("risk", 0.1, "APPROVE")
        # New keys present and typed.
        assert verdict["rationale"] == "low risk"
        assert verdict["confidence"] == 0.9
        assert verdict["degraded"] is False
        assert verdict["model_version"] == "risk-1"
        assert verdict["evidence"] == [{"signal": "velocity", "value": 1.0, "weight": 0.5}]


def test_legacy_table_falls_back_and_serialises_nulls(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    cursors = _install(monkeypatch, [_LEGACY_ROW], legacy_only=True)

    resp = client.get("/v1/transactions/txn_1")

    assert resp.status_code == 200
    verdict = resp.json()["verdicts"][0]
    assert (verdict["agent"], verdict["score"], verdict["hint"]) == ("fraud", 0.2, "APPROVE")
    assert _ADDITIVE_KEYS <= set(verdict)
    assert verdict["rationale"] is None
    assert verdict["confidence"] is None
    assert verdict["degraded"] is None
    assert verdict["model_version"] is None
    assert verdict["evidence"] == []
    # First attempt used the extended query, the retry the legacy 4-column one.
    assert any("rationale" in s for s in cursors[0].sql)
    assert not any("rationale" in s for s in cursors[1].sql)


def test_legacy_rows_without_new_columns_on_new_table_serialise(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    # Migrated table, but the row was written before the upgrade: NULLs / evidence NULL.
    row = {**_LEGACY_ROW, **dict.fromkeys(_ADDITIVE_KEYS)}
    _install(monkeypatch, [row])

    verdict = client.get("/v1/transactions/txn_1/explain").json()["verdicts"][0]

    assert verdict["rationale"] is None
    assert verdict["evidence"] == []
