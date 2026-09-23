"""”/bars?lookback=N 分页端点集成测试（V722）。

mock fetch_paged_bars，验证参数分流与响应元信息契约；
lookback=0 时走原单页路径（向后兼容）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from easy_tdx.web.app import _create_app


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    app = _create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _master(n: int = 1200) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2022-01-03", periods=n),
            "close": [float(i) for i in range(n)],
        }
    )


def test_bars_lookback_paginated(client) -> None:
    df = _master()
    with patch(
        "easy_tdx.web.klines.fetch_paged_bars", new_callable=AsyncMock
    ) as m:
        m.return_value = df
        resp = client.get(
            "/api/v1/bars",
            params={"market": "SZ", "code": "000001", "category": "DAY", "lookback": 1200},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1200
    assert body["total_returned"] == 1200
    assert body["earliest_ts"] == "2022-01-03"
    assert len(body["data"]) == 1200


def test_bars_lookback_zero_keeps_single_page(client) -> None:
    """lookback=0（缺省）不走分页路径：契约与 V720 完全一致。"""
    df = _master(100)
    with patch(
        "easy_tdx.web.klines.fetch_paged_bars", new_callable=AsyncMock
    ) as m:
        m.return_value = df
        resp = client.get(
            "/api/v1/bars", params={"market": "SZ", "code": "000001", "category": "DAY"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("total_returned") is None  # 未启用分页


def test_bars_lookback_over_limit_422(client) -> None:
    resp = client.get(
        "/api/v1/bars",
        params={"market": "SZ", "code": "000001", "lookback": 99999},
    )
    assert resp.status_code == 422
